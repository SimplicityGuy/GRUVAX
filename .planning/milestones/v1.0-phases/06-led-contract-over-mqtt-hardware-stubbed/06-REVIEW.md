---
phase: 06-led-contract-over-mqtt-hardware-stubbed
reviewed: 2026-05-23T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - frontend/src/api/adminClient.ts
  - frontend/src/api/client.ts
  - frontend/src/api/types.ts
  - frontend/src/components/ColorBlindPreview.tsx
  - frontend/src/lib/colorblind.ts
  - frontend/src/routes/admin/admin.css
  - frontend/src/routes/admin/Settings.tsx
  - frontend/src/routes/kiosk/ResultsList.tsx
  - migrations/versions/0006_led_settings_seed.py
  - src/gruvax/api/admin/leds.py
  - src/gruvax/api/admin/router.py
  - src/gruvax/api/admin/settings.py
  - src/gruvax/api/illuminate.py
  - src/gruvax/app.py
  - src/gruvax/mqtt/client.py
  - src/gruvax/mqtt/lifecycle.py
  - src/gruvax/mqtt/publishers.py
  - src/gruvax/mqtt/schemas.py
  - src/gruvax/mqtt/topics.py
  - src/gruvax/settings.py
  - tests/property/test_led_brightness.py
  - tests/unit/test_admin_led_settings.py
  - tests/unit/test_illuminate_endpoint.py
  - tests/unit/test_led_admin_endpoints.py
  - tests/unit/test_led_color.py
  - tests/unit/test_led_lifecycle.py
  - tests/unit/test_mqtt_publishers.py
findings:
  critical: 4
  warning: 9
  info: 5
  total: 18
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-23
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

This phase ships the public `POST /api/illuminate` MQTT fan-out, a cancelable
highlight lifecycle (idle/ambient + TTL auto-revert via a `HighlightRegistry` of
asyncio tasks), admin LED color/brightness/transition settings with hex
validation, and admin all-off/diagnostic endpoints. The degraded-mode posture
(`client is None` short-circuits everywhere) is implemented consistently and
well-documented, admin endpoints are correctly gated behind `require_admin`,
and the hex/integer/bool whitelisting on the settings PUT path is solid.

However, the review surfaced **four BLOCKER-class defects** that affect
correctness and robustness:

1. **Fire-and-forget tasks are never strong-referenced** — `asyncio.create_task`
   results are discarded in three places, so the Python GC can cancel an
   in-flight illuminate/ambient task before it finishes (documented CPython
   footgun). This directly undermines the "the LED fan-out happens" guarantee.
2. **The span brightness ceiling is hardcoded below the admin's range** — the
   admin UI slider allows `led_brightness.span` up to 255, but the publisher
   clamps it to 128, so any admin value above 128 is silently lost.
3. **`run_diagnostic`'s transient `status/#` subscribe consumes the shared
   message iterator** — `async for msg in client.messages` drains the single
   shared incoming-message queue for 5 s and can swallow/interfere with any
   other consumer; combined with no cancellation on shutdown this leaves a
   subscription and a 5 s blocking window on a background task.
4. **`change_pin` reads `auth.pin_hash` but `auth.pin_hash` is not in
   `_ALLOWED_SETTINGS_KEYS`** is *not* a bug (it bypasses the whitelist
   intentionally) — the real BLOCKER here is that the diagnostic background task
   is scheduled via `BackgroundTasks` while the *handler* also returns
   immediately, but the diagnostic mutates retained `state/*` for every cube
   with **no expiry on the off-state clears**, leaving permanently-retained
   empty payloads and (for the lit states) inconsistent expiry handling — a
   retained-hygiene regression against D-12.

Warnings cover concurrency on the shared `settings_cache`, an unbounded
registry growth path in retain mode, dead code, inconsistent TTL clamping
between UI and backend, and a frontend type mismatch.

## Critical Issues

### CR-01: Fire-and-forget asyncio tasks are garbage-collected mid-flight

**File:** `src/gruvax/api/illuminate.py:81-88`, `src/gruvax/app.py:177-183`
**Issue:**
`asyncio.create_task(...)` is called and its return value discarded in three
hot paths:

- `illuminate.py:81` — `asyncio.create_task(lifecycle.illuminate_with_lifecycle(...))`
- `illuminate.py:86` — `asyncio.create_task(publishers.fan_out_illuminate(...))`
- `app.py:177` — `asyncio.create_task(publish_ambient(...))`

The asyncio event loop only holds a *weak* reference to a task. If no strong
reference is kept, the task can be garbage-collected at any `await` point before
it completes, silently cancelling the publish. This is a documented CPython
behavior (`asyncio.create_task` docs explicitly warn: "Save a reference to the
result of this function, to avoid a task disappearing mid-execution"). For the
core product promise — "search lands → LEDs light" — this is a correctness
defect: under GC pressure the fan-out may never reach the broker, with no error
surfaced. The endpoint still returns `{"published": true}`, so the failure is
invisible.

**Fix:**
```python
# In a module-scoped or app.state set so the task is strongly referenced
# until it completes, then discarded via add_done_callback.
_background_tasks: set[asyncio.Task[Any]] = set()

def _spawn(coro: Coroutine[Any, Any, Any]) -> None:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

# illuminate.py
if client is not None and registry is not None:
    _spawn(lifecycle.illuminate_with_lifecycle(registry, client, settings_cache, body))
```
The `HighlightRegistry` already does this correctly for revert tasks (the entry
holds the task); apply the same discipline to the top-level illuminate/ambient
spawns. Note the existing `test_fan_out_count` patches `create_task` and asserts
it is *called* — it does not catch the GC issue, so this is not test-covered.

### CR-02: Span brightness ceiling hardcoded to 128 silently discards admin values above 128

**File:** `src/gruvax/mqtt/publishers.py:180-182` (also `:614-616` in `run_diagnostic`)
**Issue:**
```python
brightness_span: int = clamp_brightness(
    int(settings_cache.get("led_brightness.span", "128")), 128   # ← ceiling = 128
)
```
The second argument to `clamp_brightness` is the *ceiling*, hardcoded to `128`.
But the admin Settings UI exposes a span brightness slider with
`min={0} max={255}` (`frontend/src/routes/admin/Settings.tsx:367,378-379`) and
the settings PUT path accepts and persists any integer (no max validation in
`settings.py`). An admin who sets span brightness to, e.g., 200 will have it
written to the DB as 200, returned by GET as 200 (the UI shows 200), but every
actual LED publish clamps it to 128. The configured value is silently ignored.
This is a logic error: the ceiling should be a fixed safety cap (255) or the
admin range should be constrained to match, but the current code makes the
slider's upper half a no-op. The same hardcoded-128 ceiling appears in
`run_diagnostic` (`:614-616`), so diagnostics also misreport configured span
brightness.

`clamp_brightness`'s own docstring says "*ceiling* must itself be in [0, 255]" —
passing the *tier default* (128) as the ceiling conflates "default value" with
"hard maximum."

**Fix:**
```python
# Clamp to the 8-bit hardware ceiling (255), not to the tier default.
brightness_span: int = clamp_brightness(
    int(settings_cache.get("led_brightness.span", "128")), 255
)
```
Apply the same change at `publishers.py:614-616` (`run_diagnostic`). If a soft
span cap is genuinely desired, enforce it in the admin PUT validation and the UI
slider `max` so the persisted value and the published value agree.

### CR-03: Diagnostic's transient subscribe drains the shared message iterator and is not shutdown-safe

**File:** `src/gruvax/mqtt/publishers.py:694-707`
**Issue:**
```python
await client.subscribe(status_topic, qos=1)
try:
    async with asyncio.timeout(5.0):
        async for msg in client.messages:   # ← drains the single shared queue
            ...
except TimeoutError:
    pass
finally:
    await client.unsubscribe(status_topic)
```
`client.messages` in aiomqtt 2.5.x is a single shared iterator backed by one
incoming-message queue (`MessagesIterator` over `self._client._queue`). Iterating
it here for 5 s means this background task is the sole consumer of *all* inbound
MQTT messages for that window — if any other part of the app ever subscribes/
consumes (now or later), messages are silently routed to whichever iterator runs
first, causing lost messages and cross-talk. More immediately: this is launched
as a FastAPI `BackgroundTask` (`leds.py:85`) which is **not** registered in the
`HighlightRegistry`, so `cancel_and_revert_all` on shutdown (`app.py:197-206`)
does not cancel it. A diagnostic kicked off just before shutdown leaves a live
`status/#` subscription and a pending 5 s `asyncio.timeout` block on a task the
lifespan teardown does not await or cancel.

The default `max_queued_incoming_messages=0` (unbounded) also means an MQTT 5
broker that does push retained `status/#` messages would queue without backpressure
during the window.

**Fix:**
- Bound the diagnostic listen window with an explicit, cancelable task tracked in
  a registry (or use `app.state` task set as in CR-01) so shutdown can cancel it.
- Prefer a scoped consumer instead of the global `client.messages`: in aiomqtt
  2.5.x, subscribe, then read with a short-lived filtered loop and break on
  timeout; ensure only one component owns `client.messages` for the process.
  At minimum, document and enforce that the diagnostic is the *only* consumer,
  and gate it behind a flag so two concurrent diagnostics cannot both iterate
  `client.messages`.
```python
# Guard against concurrent diagnostics and make the listen window cancelable.
if getattr(client, "_gruvax_diag_active", False):
    logger.warning("diagnostic already listening on status/#; skipping subscribe")
else:
    ...
```

### CR-04: Diagnostic and all-off publish retained empty/lit payloads inconsistently — retained-hygiene regression (D-12)

**File:** `src/gruvax/mqtt/publishers.py:648-659` (diagnostic off-state),
`:529-536` (all-off command), `:504-518` (all-off state clears)
**Issue:**
D-12 (LOCKED) requires every retained `state/*` publish to carry a
`MessageExpiryInterval` so a broker restart cannot replay arbitrarily old LED
state. The diagnostic's "off" state publishes `b''` with `retain=True` but
**without** `properties=expiry_props` (`:652-659`), and the lit states *do*
attach `expiry_props` (`:673-681`). Empty retained payloads (`b''`) are the
MQTT delete-retained mechanism, so the missing expiry on the empty payload is
benign for *that* publish — but it cycles each cube through five rapid retained
writes per cube, the last of which (off) deletes the retained message. The net
effect is that after a diagnostic, every cube's retained `state/*` is *cleared*,
not restored to ambient. There is no `publish_ambient` call at the end of
`run_diagnostic`, so the kiosk/firmware loses its idle baseline until the next
search or restart. This contradicts LED-11/D-20 ("every cube shows the idle
ambient color when no highlight is active"): a diagnostic run silently wipes the
ambient baseline.

`publish_all_off` has the same intent (clear retained), which is correct for an
explicit all-off, but the diagnostic should **restore ambient** when it
finishes rather than leaving every cube dark.

**Fix:**
```python
# At the end of run_diagnostic, after the status-subscribe window:
await publish_ambient(client, pool, settings_cache)   # restore idle baseline
logger.info("LED diagnostic run_id=%s complete; ambient baseline restored", run_id)
```
Separately, decide intentionally whether the diagnostic "off" frame should be a
zero-brightness *lit* payload (carrying expiry, so firmware sees an explicit
"off" state) or a retained delete (`b''`); the current mix of expiry-bearing lit
frames and a non-expiry empty frame is inconsistent and should be unified.

## Warnings

### WR-01: `settings_cache` is mutated/replaced under concurrent reads without coordination

**File:** `src/gruvax/api/admin/settings.py:259`, read sites in
`src/gruvax/mqtt/publishers.py` and `src/gruvax/mqtt/lifecycle.py`
**Issue:**
`update_settings` replaces the whole dict via
`request.app.state.settings_cache = await load_settings_cache(pool)` while
concurrent fire-and-forget tasks (`fan_out_illuminate`, `illuminate_with_lifecycle`,
`publish_ambient`, in-flight `schedule_revert`) read individual keys from
`settings_cache`. Rebinding the attribute is atomic in CPython, but tasks that
captured the *old* dict reference (passed as a function argument, e.g.
`illuminate.py:82` captures `settings_cache` at request time) will continue
reading stale values for the lifetime of that task — including the revert task,
which may run 180–900 s later with the brightness/color values from when the
illuminate fired, not the values the admin just saved. This is a benign-but-
surprising staleness window, and because each spawned task captures the dict
*reference* at spawn time, a partial read tearing is avoided — but the staleness
contradicts D-15's "see new LED values immediately."
**Fix:** Read `settings_cache` from `request.app.state` at the point of use
(re-fetch the current dict inside the task) rather than capturing it as an
argument at spawn time, or version the cache and re-read on each publish.

### WR-02: Retain-mode registry growth is bounded only by TTL, enabling unbounded accumulation

**File:** `src/gruvax/mqtt/lifecycle.py:182-186, 259-286`
**Issue:**
In retain mode the docstring (`:14, :186`) claims "registry size stays O(active
highlights)," but there is no cap on concurrent highlights. With
`retain_ttl_seconds=900` (default) and a fast typist, a kiosk session can
register hundreds of highlight tasks before any TTL fires — each holding an
asyncio task and a `cubes` list. T-06-18's "never grows unbounded" invariant is
only satisfied because TTLs eventually fire; under sustained search load the
peak is bounded by `searches_per_900s`, not by any hard limit. This is a memory/
task-leak risk on the constrained Pi/`lux` host under adversarial or accidental
rapid input.
**Fix:** Add a hard cap (e.g., max N retained highlights); when exceeded, evict
the oldest by cancelling+reverting it before adding the new one. Even N=64 would
prevent pathological growth while preserving normal retain-mode UX.

### WR-03: Span brightness `clamp_brightness` ceiling mismatch hides the configured value (paired with CR-02)

**File:** `frontend/src/routes/admin/Settings.tsx:378-379` vs
`src/gruvax/mqtt/publishers.py:181`
**Issue:** The UI slider `max={255}` and the backend ceiling `128` disagree (see
CR-02). Even after fixing the ceiling, there is no server-side validation that
brightness values are within `[0,255]` on the PUT path (`settings.py:230-237`
accepts any integer). A value like `999` is stored verbatim and only clamped at
publish time. The GET endpoint then echoes `999` to the UI.
**Fix:** Validate brightness keys to `0 <= value <= 255` in `update_settings`
(return 422 on out-of-range), consistent with the hex validation already done
for color keys.

### WR-04: `illuminate` returns `published: true` even when the publish is guaranteed to be skipped

**File:** `src/gruvax/api/illuminate.py:84-92, 101-104`
**Issue:** When `client is not None` but `registry is None` (early-startup edge),
the code falls back to `fan_out_illuminate` and logs a warning, but the response
still reports `{"published": client is not None}` → `true`. More importantly,
the `published` field reflects only *broker connectivity*, not whether the
publish actually succeeded (it is fire-and-forget and can fail silently inside
`safe_publish`). Callers (and the frontend `illuminateRecord`) cannot distinguish
"scheduled" from "delivered." This is acceptable for fire-and-forget, but the
field name `published` overstates the guarantee and will mislead future
diagnostics.
**Fix:** Rename to `accepted` / `scheduled`, or document explicitly in the
response/schema that `published` means "broker connected and publish scheduled,"
not "message delivered."

### WR-05: `publish_ambient` enumerates ALL cubes at startup with no connection guard ordering

**File:** `src/gruvax/app.py:174-186`, `src/gruvax/mqtt/publishers.py:400-414`
**Issue:** At startup `publish_ambient(app.state.mqtt, app.state.db_pool, ...)`
is scheduled even when `app.state.mqtt is None` (degraded mode). The function
does short-circuit on `client is None` (`:357-361`) *before* touching the pool,
so this is safe today — but the ordering is fragile: the `try/except` around
`asyncio.create_task` (`app.py:176-186`) only guards task *creation*, not task
*execution*, so any exception inside `publish_ambient` (e.g., a DB error during
`SELECT ... FROM gruvax.units`) is swallowed only by `safe_publish`/gather, not
by the startup guard. A pool error during enumeration would raise inside the
detached task and (per CR-01) potentially be lost. Combined with the missing
strong reference (CR-01) this ambient publish can vanish silently at startup.
**Fix:** After fixing CR-01, also wrap the ambient enumeration body so a DB
failure logs and returns 0 rather than raising inside the detached task.

### WR-06: `_make_app_with_mqtt` test helper sets state but lifespan would overwrite it — tests bypass lifespan, masking integration gaps

**File:** `tests/unit/test_illuminate_endpoint.py:40-63`,
`tests/unit/test_led_admin_endpoints.py:343-372`
**Issue:** Tests construct the app via `create_app()` and then set
`app.state.mqtt`, `settings_cache`, etc. directly, and drive requests with
`ASGITransport` which (when used without `async with LifespanManager`) does
**not** run the `lifespan` startup. This means `app.state.highlight_registry` is
never created in these tests, so the illuminate endpoint takes the
`registry is None` fallback branch (`illuminate.py:84`) rather than the real
`illuminate_with_lifecycle` path the product uses. `test_fan_out_count` therefore
exercises the fallback, not the primary lifecycle path — a coverage gap for the
exact code that ships. (httpx `ASGITransport` does not trigger lifespan events by
default.)
**Fix:** Either run the lifespan (e.g., `asgi-lifespan`'s `LifespanManager`) or
explicitly set `app.state.highlight_registry = HighlightRegistry()` in the test
helper so the primary path is covered.

### WR-07: `run_diagnostic` ignores `pool is None` and will raise inside the background task

**File:** `src/gruvax/mqtt/publishers.py:632-636`
**Issue:** Unlike `publish_ambient` (`:402-404`, which guards `pool is None`),
`run_diagnostic` unconditionally does
`async with pool.connection() as conn` after the `client is None` check. If the
pool is unavailable but the broker is connected, this raises `AttributeError`/
`TypeError` inside the `BackgroundTask`, which FastAPI logs but does not surface.
The endpoint already returned `200 {run_id}`, so the operator sees "diagnostic
started" with no indication it crashed immediately.
**Fix:** Add a `pool is None` guard mirroring `publish_ambient`, logging a
warning and returning early.

### WR-08: Frontend `illuminateRecord` POSTs the full `LocateResult` but the backend model drops `generated_at`/`estimator_version` silently

**File:** `frontend/src/api/client.ts:99-108`,
`src/gruvax/api/illuminate.py:37-54`
**Issue:** `IlluminateRequest` uses `model_config = {"extra": "ignore"}` and
omits `generated_at`/`estimator_version`/`crosses_boundary`/`next_cube`. This is
intentional (documented), but `sub_cube_interval` is typed
`dict[str, Any] | None` and the publisher reads `sub_interval.get("start", 0.0)`
/ `.get("end", 1.0)` (`publishers.py:277-280`). The frontend `SubInterval` type
sends `start`/`end` as required numbers, so this works — but if a future locate
result omits `start`/`end` (e.g., a cube-only result with a non-null but partial
interval), the publisher defaults to `[0.0, 1.0]` (full cube) without warning,
producing a misleading sub-cube highlight spanning the entire cube. There is no
validation that `0 <= start <= end <= 1`.
**Fix:** Validate the interval in the publisher (or in `IlluminateRequest` via a
typed `SubInterval` Pydantic model) and skip the sub publish when `start`/`end`
are absent rather than defaulting to a full-cube span.

### WR-09: Diagnostic `inter_cube_ms` is read with `int(...)` and no bounds — a hostile/typo'd setting blocks the task for a long time

**File:** `src/gruvax/mqtt/publishers.py:593-595`
**Issue:** `inter_cube_delay_s = int(settings_cache.get("led_diagnostic.inter_cube_ms", 200)) / 1000.0`
has no upper bound and no error handling. `led_diagnostic.inter_cube_ms` is not
in `_ALLOWED_SETTINGS_KEYS`, so it cannot be set via the admin UI today (it falls
back to 200) — but if it is ever seeded or set, a large value makes the
diagnostic loop sleep for that duration per cube while holding the `status/#`
subscription open. A non-numeric value raises `ValueError` inside the background
task (uncaught, see WR-07 pattern).
**Fix:** Wrap in try/except with a sane default and clamp to a maximum (e.g.,
`min(max(int(...), 0), 2000)` ms).

## Info

### IN-01: Dead code — `now_iso` computed then immediately overwritten in `publish_ambient`

**File:** `src/gruvax/mqtt/publishers.py:365, 377-378`
**Issue:** `now_iso = json.dumps({"ts": "ambient"})` at `:365` (with a comment
"placeholder — not needed") is unconditionally overwritten at `:377-378` by
`now_iso = datetime.now(UTC).isoformat()`. The first assignment and the inline
`import json` usage are dead. Also `from datetime import UTC, datetime` is
re-imported locally at `:377` despite the module-level import at `:35`.
**Fix:** Delete `:365` and the redundant local re-imports at `:377` and
`:382`; rely on the module-level imports.

### IN-02: Redundant local imports inside functions

**File:** `src/gruvax/mqtt/publishers.py:377, 382`; `src/gruvax/api/admin/settings.py:244, 284`
**Issue:** `from datetime import UTC, datetime` (`:377`) and
`from gruvax.mqtt.schemas import IlluminatePayload, RGBColor, TransitionSpec`
(`:382`) duplicate module-level imports (`:35, :43-49`). `settings.py:244`
imports `json as _json` inside a loop branch, and `:284` imports auth helpers
inside the handler. These local imports add per-call overhead and obscure the
dependency surface.
**Fix:** Hoist to module level (the auth imports inside `change_pin` may be kept
local if there is a genuine circular-import reason; otherwise hoist).

### IN-03: `console.debug` debug artifact left in production frontend path

**File:** `frontend/src/api/adminClient.ts:340`
**Issue:** `console.debug('[gruvax] signalEditing network error (non-fatal):', err)`
ships to the kiosk/admin bundle. This is intentional non-fatal logging, but
`console.debug` in a shipped SPA is a minor noise/info-leak vector (logs error
detail to the browser console).
**Fix:** Gate behind `import.meta.env.DEV` or remove for production builds.

### IN-04: `change_pin` accepts only 4-digit PINs but the spec/UI hardcode 4 — magic number duplicated

**File:** `src/gruvax/api/admin/settings.py:294`,
`frontend/src/routes/admin/Settings.tsx:123,127,214,233`
**Issue:** The 4-digit PIN length is hardcoded in both backend (`len(new_pin) != 4`)
and frontend (`maxLength={4}`, `length !== 4`, `.slice(0, 4)`). Not a Phase-6
regression, but a duplicated magic number across the boundary that will drift if
PIN policy changes.
**Fix:** Centralize the PIN length as a named constant on each side.

### IN-05: `IlluminatePayload` has both `duration_ms` and `transition.duration_ms` — ambiguous contract

**File:** `src/gruvax/mqtt/schemas.py:81-82`
**Issue:** `IlluminatePayload` declares a top-level `duration_ms: int | None = None`
*and* a nested `transition: TransitionSpec` which itself carries `duration_ms`.
The publisher only ever sets the nested one; the top-level field is always
`None` in emitted JSON. Firmware authors reading the contract will not know which
to honor.
**Fix:** Remove the unused top-level `duration_ms` from `IlluminatePayload` (and
`SubIntervalPayload:107`) or document precedence explicitly in the schema
docstring.

---

_Reviewed: 2026-05-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

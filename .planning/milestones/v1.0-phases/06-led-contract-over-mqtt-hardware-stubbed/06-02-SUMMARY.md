---
phase: 06-led-contract-over-mqtt-hardware-stubbed
plan: 02
subsystem: mqtt-lifecycle
tags: [mqtt, led, lifecycle, ambient, tdd, revert-registry, retain-mode]
dependency_graph:
  requires:
    - gruvax.mqtt.publishers (fan_out_illuminate, safe_publish, _make_expiry_props, hex_to_rgb, clamp_brightness)
    - gruvax.mqtt.topics (state_topic)
    - gruvax.mqtt.schemas (IlluminatePayload, RGBColor, TransitionSpec)
    - gruvax.mqtt.client (connect_mqtt — app.state.mqtt)
    - gruvax.settings (MQTT_TOPIC_PREFIX, MQTT_STATE_EXPIRY_SECONDS)
    - gruvax.db.queries (load_settings_cache — app.state.settings_cache)
  provides:
    - gruvax.mqtt.lifecycle (HighlightRegistry, schedule_revert, illuminate_with_lifecycle, cancel_and_revert_all)
    - gruvax.mqtt.publishers.publish_ambient (ambient baseline for cubes)
    - app.state.highlight_registry (cancelable revert task registry, created in lifespan)
    - /api/illuminate now routes through lifecycle path (TTL revert + default cancel-prior + retain accumulate)
  affects:
    - src/gruvax/app.py (asyncio import, HighlightRegistry creation, ambient baseline startup task, cancel_and_revert_all teardown)
    - src/gruvax/api/illuminate.py (create_task target: lifecycle.illuminate_with_lifecycle when registry present)
tech_stack:
  added: []
  patterns:
    - asyncio.Task + HighlightRegistry for bounded, leak-free in-process revert registry
    - Injectable sleep seam (schedule_revert sleep= kwarg) for unit-testable TTL without real waits
    - asyncio.Event().wait() as a blocking-until-cancelled sleep stub in retain-mode tests
    - asyncio.gather(return_exceptions=True) for concurrent ambient state/* publishes
    - finally-pop pattern in schedule_revert to guarantee registry cleanup on completion, cancellation, or error
key_files:
  created:
    - src/gruvax/mqtt/lifecycle.py
    - tests/unit/test_led_lifecycle.py
  modified:
    - src/gruvax/mqtt/publishers.py
    - src/gruvax/api/illuminate.py
    - src/gruvax/app.py
decisions:
  - "schedule_revert accepts pool=None path (cubes passed explicitly) for revert path — no DB round-trip during TTL revert"
  - "asyncio.Event().wait() in test_retain_mode_accumulates: blocks without yielding so revert tasks do not fire during the test, works correctly with cancel"
  - "illuminate.py fallback to fan_out_illuminate when registry=None (early startup edge case, degraded-mode parity)"
  - "publish_ambient uses IlluminatePayload schema for state/* ambient payload (firmware schema compat), style=instant/duration_ms=0"
  - "asyncio.create_task wraps publish_ambient at startup in try/except — never blocks lifespan on broker-down"
metrics:
  duration_minutes: 12
  completed_date: "2026-05-24"
  tasks_completed: 3
  files_created: 2
  files_modified: 3
---

# Phase 6 Plan 02: LED Highlight Lifecycle Summary

Server-scheduled highlight lifecycle with bounded revert registry: every cube shows the configurable idle/ambient baseline (LED-11/D-20), active highlights revert server-side after a configurable TTL or on the next search (LED-12/D-21/D-22), and optional retain mode accumulates a recently-found trail with independent per-highlight timeouts (LED-13/D-23).

## Tasks Completed

| Task | Description | Commit | Key Files |
|------|-------------|--------|-----------|
| 1 | Wave-0 RED scaffold — 9 lifecycle tests (ambient baseline, TTL revert, default cancel-prior, retain accumulate, leak guard, degraded) | 171223c | tests/unit/test_led_lifecycle.py |
| 2 | lifecycle.py + publish_ambient GREEN — HighlightRegistry, schedule_revert (injectable sleep), illuminate_with_lifecycle (default/retain branch), cancel_and_revert_all | d5c1508 | src/gruvax/mqtt/lifecycle.py, src/gruvax/mqtt/publishers.py |
| 3 | Wire lifecycle into /api/illuminate + app lifespan (registry create + ambient baseline at startup + shutdown cancel) | 07f2cff | src/gruvax/api/illuminate.py, src/gruvax/app.py |

## What Was Built

### HighlightRegistry (src/gruvax/mqtt/lifecycle.py)

Bounded in-process registry mapping `highlight_id` (uuid str) → `_RegistryEntry(task, cubes)`.
- `add(highlight_id, task, cubes)` — register an entry
- `pop(highlight_id)` — idempotent remove (returns None if absent)
- `items()` / `values()` — snapshot copies for safe iteration
- `__len__` — current registry size

Size invariant (T-06-18): default mode keeps at most 1 active entry; retain mode grows by 1 per search and shrinks as TTLs fire. Each `schedule_revert` task pops its own entry in a `finally` block, guaranteeing cleanup on completion, cancellation, or error.

### schedule_revert (src/gruvax/mqtt/lifecycle.py)

Revert task body:
1. `await sleep(delay_seconds)` — injectable clock seam (D-22 testability)
2. `await publish_ambient(client, None, settings_cache, cubes=cubes)` — republish retained ambient `state/*` for exactly the affected cubes (no DB call — cubes passed explicitly)
3. `finally: registry.pop(highlight_id)` — leak-free cleanup

Degraded mode: if `client is None`, logs warning and returns; `finally` still pops.

### illuminate_with_lifecycle (src/gruvax/mqtt/lifecycle.py)

Lifecycle-aware illuminate entry point:

**Default mode** (`led_highlight.retain_mode=false`, D-22):
1. Iterates `registry.items()` — cancels each prior task, pops entry, immediately calls `publish_ambient` for those cubes (next-search-reverts-prior)
2. Calls `fan_out_illuminate` to light the new selection
3. Schedules `schedule_revert` via `asyncio.create_task`, TTL from `led_highlight.active_ttl_seconds` (default 180s)

**Retain mode** (`led_highlight.retain_mode=true`, D-23):
1. Does NOT cancel prior entries — accumulates highlights
2. Calls `fan_out_illuminate` for the new selection
3. Schedules independent `schedule_revert` with TTL from `led_highlight.retain_ttl_seconds` (default 900s)

T-06-19: Default mode guarantees O(1) active task; retain mode bounded by TTL expiry.

### cancel_and_revert_all (src/gruvax/mqtt/lifecycle.py)

Shutdown path: iterates all registry entries, calls `task.cancel()`, best-effort `publish_ambient` for their cubes, `registry.pop`. Called in lifespan teardown. Guard: `client=None` skips ambient publish but still cancels and clears (T-06-22).

### publish_ambient (src/gruvax/mqtt/publishers.py)

Ambient baseline publisher — LED-11/D-20:
- Resolves `led_color.ambient` (default `#0051A2`) and `led_brightness.ambient` (default 40)
- **D-24 LOCKED**: uses `led_brightness.ambient`, NOT `led_brightness.span` (span tier is for active highlights only)
- When `cubes=None`: enumerates all cubes via `SELECT id, rows, cols FROM gruvax.units ORDER BY ordering` (short-lived connection, closed before publishing)
- When `cubes` provided: publishes only those cubes (revert path — no DB needed)
- Concurrent publish via `asyncio.gather(return_exceptions=True)`, each with `qos=1, retain=True, message_expiry_interval`
- Returns count of successfully published cubes

### App Lifespan Changes (src/gruvax/app.py)

**Startup** (after MQTT connect):
- Creates `app.state.highlight_registry = HighlightRegistry()`
- Schedules `asyncio.create_task(publish_ambient(...))` for ambient baseline — best-effort (never blocks startup on broker-down)

**Teardown** (before disconnect):
- `await cancel_and_revert_all(registry, mqtt, settings_cache)` — cancels all pending revert tasks and empties the registry

### /api/illuminate Changes (src/gruvax/api/illuminate.py)

- Reads `registry = getattr(request.app.state, "highlight_registry", None)`
- When `client is not None and registry is not None`: `asyncio.create_task(lifecycle.illuminate_with_lifecycle(registry, client, settings_cache, body))`
- Fallback when registry missing: `asyncio.create_task(publishers.fan_out_illuminate(...))` (early startup edge case)
- Degraded mode (client=None) → `published: false`, no task created
- Still PUBLIC endpoint, still NO `require_admin` (D-03)

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/unit/test_led_lifecycle.py | 9 | PASS |
| tests/unit/test_illuminate_endpoint.py | 3 | PASS |
| Full unit + property suite | 297 | PASS (no regressions) |
| mypy --strict src/gruvax/ | 48 files | PASS (0 errors) |

Pre-existing failures (not caused by this plan):
- `tests/integration/test_migrate_0005.py::test_0005_round_trip_down_up` — ordering issue, passes when run in isolation (dev Postgres shared, Alembic downgrade/upgrade affects other tests)
- `tests/unit/test_algorithm.py::test_locate_benchmark` — benchmark plugin collection error (pre-existing)

### TDD Gate Compliance

- RED gate: `171223c` — `test(06-02)` commit with 9 failing tests (lifecycle module not yet created)
- GREEN gate: `d5c1508` — `feat(06-02)` commit making all 9 tests pass
- Wire gate: `07f2cff` — `feat(06-02)` commit integrating lifecycle into app and endpoint

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] retain-mode test used instant_sleep that allowed revert task to fire prematurely**
- **Found during:** Task 2 GREEN phase (test_retain_mode_accumulates failed)
- **Issue:** `instant_sleep` used `await asyncio.sleep(0)` which yields control, allowing the first revert task to actually fire between the two `illuminate_with_lifecycle` calls in the retain mode test
- **Fix:** Changed `instant_sleep` in that test to `blocking_sleep` using `asyncio.Event().wait()` — blocks until cancelled, so revert tasks don't fire during the test. Added explicit cleanup (cancel pending tasks at end of test)
- **Files modified:** tests/unit/test_led_lifecycle.py
- **Commit:** d5c1508

**2. [Rule 1 - Bug] mypy: publish_ambient imported from wrong module in app.py**
- **Found during:** Task 3 mypy --strict run
- **Issue:** Import in lifespan said `from gruvax.mqtt.lifecycle import ... publish_ambient` but `publish_ambient` lives in `gruvax.mqtt.publishers`
- **Fix:** Corrected import to `from gruvax.mqtt.publishers import publish_ambient`
- **Files modified:** src/gruvax/app.py
- **Commit:** 07f2cff

**3. [Rule 2 - Missing] asyncio not imported at module level in app.py**
- **Found during:** Task 3 mypy --strict run (name-defined error)
- **Issue:** `asyncio.create_task(...)` called in lifespan but `asyncio` not imported at top level
- **Fix:** Added `import asyncio` to module-level imports
- **Files modified:** src/gruvax/app.py
- **Commit:** 07f2cff

## Known Stubs

None — all lifecycle behavior implemented and exercised. The MQTT publish path operates in degraded mode when no broker is connected (by design, not a stub).

## Threat Flags

No new threat surface beyond the plan's threat model. Verified:
- T-06-18: HighlightRegistry + finally-pop + default-mode cancel → bounded O(active highlights)
- T-06-19: Default mode cancels prior before scheduling new (one active task); retain mode bounded by TTL
- T-06-20: publish_ambient uses asyncio.gather(return_exceptions=True) + safe_publish with timeout
- T-06-21: TTL values read as int() with .get defaults; non-numeric falls back to default
- T-06-22: cancel_and_revert_all in lifespan teardown; guarded by try/except

## Self-Check: PASSED

All files created: lifecycle.py, test_led_lifecycle.py, SUMMARY.md — FOUND
All commits verified: 171223c (RED), d5c1508 (GREEN), 07f2cff (wire-up) — FOUND
All acceptance criteria met:
- HighlightRegistry class: FOUND
- schedule_revert, illuminate_with_lifecycle, cancel_and_revert_all: FOUND
- publish_ambient with led_brightness.ambient (not span): FOUND
- highlight_registry = HighlightRegistry() in lifespan startup: FOUND
- cancel_and_revert_all in lifespan teardown: FOUND
- lifecycle.illuminate_with_lifecycle path in illuminate.py: FOUND
- No require_admin on illuminate endpoint: CONFIRMED
- pytest 297 passed (no regressions): PASSED
- mypy --strict 48 files (0 errors): PASSED

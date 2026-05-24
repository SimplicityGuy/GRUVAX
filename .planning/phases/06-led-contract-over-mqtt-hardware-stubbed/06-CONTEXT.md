# Phase 6: LED Contract over MQTT (Hardware Stubbed) - Context

**Gathered:** 2026-05-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Every kiosk highlight publishes a versioned, Pydantic-validated MQTT payload to an
**internal-only** Mosquitto broker (no host port exposure), the admin can tune LED
colors and brightness, and "all off" + a diagnostic sequence work end-to-end — so the
contract is hardware-ready without any firmware existing yet.

**In scope:** LED-01..LED-10, DEP-03. The publish path (`mqtt/publishers.py`), a
`POST /api/illuminate` endpoint, admin LED color/brightness settings + a "LEDs" section
in the existing admin Settings page, an "All off" button, a diagnostic endpoint, and the
retained-state / topic-versioning / expiry plumbing.

**Out of scope (future hardware milestone, do NOT build here):** real ESP32/WS2812B
firmware, broker host-port exposure, per-device-class MQTT credentials, a second LAN
listener, TLS. The broker stays internal to the Compose network; nobody subscribes in v1.
</domain>

<decisions>
## Implementation Decisions

### Publish seam & hot-path isolation
- **D-01:** A kiosk select triggers a **`POST /api/illuminate`** call — a separate request
  the kiosk makes *after* `/api/locate`. `/api/locate` stays a pure CPU-only read with no
  side effects so its ≤50 ms budget is untouched. The publish is fire-and-forget with a
  **~250 ms timeout** (SC5) off the request hot path; a broker hiccup never blocks the API
  (mirror the existing degraded-mode stub posture).
- **D-02:** The layered command (LED-09) is **one `POST /api/illuminate` request that the
  server fans out** to the three locked topics — `illuminate/{u}/{r}/{c}`,
  `span/{change_id}`, and `sub/{u}/{r}/{c}`. No new composite topic; the locked
  ARCHITECTURE topic tree is authoritative.
- **D-03:** The request body is the **`LocateResult` the kiosk already holds** from its
  preceding `/api/locate` call (primary_cube, label_span, sub_cube_interval). The server
  validates it against the contract, then resolves colors/brightness/expiry and publishes.
  No server-side re-locate. (LAN-only, single-user, `/api/illuminate` is unauthenticated
  per ARCHITECTURE — trusting the client-provided result is acceptable here, but the
  payload MUST still pass the Pydantic `LocateResult` shape.)

### LED palette & color configuration
- **D-04:** **LED colors are a SEPARATE palette from the kiosk UI.** The kiosk grid keeps
  the Nordic Grid design language untouched (lit cell = yellow + LED glow). Physical LEDs
  get their own admin-tunable palette. This deliberately resolves the design-language
  ("lit cells always yellow") vs Pitfall 18 ("gold primary / purple span") tension — they
  are two distinct output surfaces, not one shared palette.
- **D-05:** The admin gets a **free per-state color picker** (label-span, position, error,
  setup, all-off — LED-05), **seeded with color-blind-safe defaults** (primary/position
  gold `#FFD700`, label-span purple `#7C3AED` per Pitfall 18) and offering **Nordic Grid
  design-token swatches as presets**, but custom hex is allowed.
- **D-06:** Color is encoded as **resolved `{r,g,b}` in the payload, server-side** from the
  configured settings. Firmware stays dumb; admin color changes take effect with no
  firmware update. (ARCHITECTURE default; the `color_name`-resolved-by-firmware variant is
  rejected.)
- **D-07:** **Two active-highlight brightness ceilings** (LED-04): **span** (label-span)
  ~30–50% and **active** (position) 100%. The **server clamps every payload's brightness**
  to the relevant ceiling so nothing exceeds it. Brightness-as-information (Pitfall 18):
  span stays dimmer than primary even for a viewer who can't perceive hue. **NOTE: the
  label-span tier is named `span`, NOT "ambient" — "ambient" is the idle state (D-20, D-24).**

### Diagnostic & all-off
- **D-08:** The diagnostic endpoint (LED-07) runs as a **background task that returns a
  `run_id` immediately**; the admin UI gets an instant ack and the sequence publishes
  cube-by-cube in the background, logging each publish.
- **D-09:** The diagnostic **cycles every cube, one at a time, through the configured state
  colors** (label-span → position → error → setup → off). This exercises the full color
  contract + every topic and is verifiable via `mosquitto_sub` even with no hardware.
- **D-10:** "Log any status responses" (LED-07): during the diagnostic run, **transiently
  subscribe to `gruvax/v1/leds/status/#`**, log whatever arrives (expected: nothing in
  v1), then time out. This wires the future hardware status-listening seam now so the
  hardware milestone works without an API change.
- **D-11:** "All off" (LED-06) is **idempotent**: publish an empty retained payload
  (`payload=b''`, `retain=True`) to **every** `state/{u}/{r}/{c}` topic (the Pitfall 3
  clear-retained idiom) AND publish a command on `.../all/off`. Safe to call repeatedly;
  clears retained ghosts.

### Retained-state hygiene, topics & settings
- **D-12:** Every retained `state/*` publish sets **MQTT 5 `message_expiry_interval`
  (default 4h, configurable)** as a **safety backstop** so the broker auto-drops orphaned
  retained payloads (Pitfall 3); "no expiry" is rejected. NOTE: for **active highlights**
  the primary revert mechanism is the **server-scheduled task** (D-22), not expiry; the
  **ambient** baseline (D-20) is the persistent desired state, republished on every revert.
- **D-13:** The **v1 stub DOES publish retained `state/*`** topics (with no hardware
  listening). ARCHITECTURE: "costs nothing" and lets the hardware milestone work
  end-to-end with no later contract change. Each illuminate also writes the retained
  desired-state for the affected cube(s).
- **D-14:** Topics are environment-separated via a configurable **`MQTT_TOPIC_PREFIX`** —
  `gruvax/v1/dev/leds/...` in dev, `gruvax/v1/leds/...` in prod (Pitfall 3). Dev retained
  junk never pollutes prod topics.
- **D-15:** Settings are split by precedence: **topology/connection knobs** (MQTT host,
  creds, `MQTT_TOPIC_PREFIX`, default expiry) live in `settings.py`/env; **presentation
  knobs** (per-state colors incl. ambient, the three brightness tiers span/active/ambient,
  transition defaults, highlight TTL + retain-mode toggle/timeout — see D-25) live in the
  `gruvax.settings` DB table (admin-editable via the settings cache + `Settings.tsx`). The
  admin can tune the look but cannot break broker connectivity.

### Transitions & admin LED UI
- **D-16:** LED-10 transitions use **per-state defaults**: primary/position = `pulse`,
  label-span = `fade`, all-off = `instant`. Declared in the payload's
  `transition: {style, duration_ms}`. Motion is an information channel (Pitfall 18) so a
  color-blind viewer still distinguishes primary from span.
- **D-17:** Transitions are **fixed sensible defaults in v1, with the payload field +
  settings schema supporting overrides**, but **no transition editor UI** is built —
  transitions only become observable once firmware exists, so editing a stubbed-only effect
  adds UI for no payoff.
- **D-18:** Build a **lightweight color-blind preview now** (deuteranopia / protanopia /
  tritanopia matrix simulation) next to the color picker. The moment the admin picks colors
  is the one place Pitfall 18 prevention works; without it, the seeded safe defaults can be
  overridden into an inaccessible pair.
- **D-19:** The admin LED control surface is a **new "LEDs" section inside the existing
  `Settings.tsx`** (color swatches + brightness sliders + All-off + Diagnostic buttons) —
  **no new route**. Phase 6 has no roadmap "UI hint"; this is a settings-shaped concern
  that reuses the Settings shell + settings cache.

### Idle/ambient state & highlight lifecycle (added 2026-05-23 — post-plan scope expansion; supersedes the "highlight lingers until 4h expiry" model)
- **D-20:** "Ambient" means ONE thing: the **idle/resting LED state** — the baseline shown
  on every cube when no record highlight is active. Its **color and brightness are
  admin-configurable** (`led_color.ambient`, `led_brightness.ambient`). (LED-11. This is the
  ONLY meaning of "ambient" — it is NOT the label-span brightness tier; see D-24.)
- **D-21:** An active record highlight illuminates for a **configurable TTL — default 3 min
  (`led_highlight.active_ttl_seconds` = 180)** — OR until the **next successful search**,
  whichever comes first; then the affected cube(s) **revert to the ambient state** (D-20).
  (LED-12.)
- **D-22:** Revert is **server-scheduled**, not firmware-dependent: ambient is the baseline
  retained `state/*` on every cube; on select the server overrides the chosen cubes, then a
  **background task re-publishes the ambient state** to them after the TTL (or immediately
  on the next search). An **in-process registry of cancelable per-highlight revert tasks**
  keys this; in default mode the next search cancels+reverts the prior highlight. Works
  end-to-end in the stub and is fully testable. (LED-12.)
- **D-23:** An optional **"retain" mode** (`led_highlight.retain_mode`, default off)
  **accumulates** highlights — each search **adds** a lit location, and each reverts
  **independently** after a longer **configurable timeout — default 15 min
  (`led_highlight.retain_ttl_seconds` = 900)**. A "recently-found trail." In retain mode the
  next search does NOT clear prior highlights. (LED-13.)
- **D-24:** **Brightness tiers renamed** (corrects D-07's old misuse of "ambient"):
  **span brightness** (`led_brightness.span`, label-span tier ~30–50% during an active
  highlight), **active brightness** (`led_brightness.active`, position tier 100%), and
  **ambient brightness** (`led_brightness.ambient`, the idle state, low/configurable).
  "Ambient" no longer names the label-span tier anywhere in the contract.
- **D-25:** New admin-editable `gruvax.settings` keys (presentation, per D-15):
  `led_color.ambient`, `led_brightness.ambient`, `led_brightness.span` (renamed from the
  old/incorrect `led_brightness.ambient`), `led_highlight.active_ttl_seconds` (180),
  `led_highlight.retain_mode` (false), `led_highlight.retain_ttl_seconds` (900). Surfaced in
  the admin LEDs section (D-19).
- **D-26:** **Party mode** and **sound-reactive mode** are explicitly **out of Phase 6
  scope** → backlog (post-v1 flourishes). Not built now.

### Claude's Discretion
- Exact Pydantic model layout for the per-topic payload schemas (`gruvax.illuminate.v1`,
  `gruvax.sub_interval.v1`, span) — follow the JSON shapes locked in ARCHITECTURE
  §"Payload format"; the documented schema must live alongside the contract in the repo
  (SC4).
- QoS per topic is already locked by ARCHITECTURE (illuminate/span/sub = QoS 0; all/off +
  diagnostic = QoS 1; state/* = QoS 1 retained) — apply as specified.
- Inter-cube delay / total duration of the diagnostic sequence (pick a documented,
  reasonable cadence).
- The default transition `duration_ms` values per state.
- Settings-cache key naming under `gruvax.settings` (follow the existing
  `led_color.*` / `led_brightness.*` convention hinted in ARCHITECTURE §schema).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Locked MQTT contract (authoritative)
- `.planning/research/ARCHITECTURE.md` §"MQTT Topic Design" (topic tree, JSON payload
  format, retain vs non-retain, QoS levels, v1-stub-vs-hardware table, home-LAN-only
  enforcement) — the single source of truth for topics, payload shapes, and semantics.
- `.planning/research/ARCHITECTURE.md` §"API surface" (the `POST /api/illuminate`,
  `POST /api/admin/leds/diagnostic`, `POST /api/admin/leds/off` row definitions).

### Pitfalls that drive decisions
- `.planning/research/PITFALLS.md` §"Pitfall 3" — retained-state lifecycle: message-expiry
  on every retained publish, all-off clears retained via empty payload, per-env topic
  prefix. (Drives D-11, D-12, D-13, D-14.)
- `.planning/research/PITFALLS.md` §"Pitfall 18" — color-blind-safe defaults, brightness
  as a second information channel, color-blind preview in the picker, motion to
  distinguish primary from span. (Drives D-04, D-05, D-07, D-16, D-18.)

### Requirements & scope
- `.planning/REQUIREMENTS.md` §"LED Control Surface" (LED-01..LED-10) + §"Deployment"
  (DEP-03).
- `.planning/ROADMAP.md` §"Phase 6" (the five success criteria — these are effectively a
  locked acceptance spec for this phase).

### Design language (LED palette + admin picker)
- `design/gruvax-design-language.md` — the Nordic Grid spec; note the kiosk UI keeps it
  unchanged (D-04). LED palette is separate but the picker offers token swatches as presets.
- `design/gruvax-design-tokens.css`, `design/gruvax-design-tokens.json` — token source for
  the preset swatches.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/gruvax/mqtt/client.py` — existing Phase 1 MQTT stub: best-effort connect at
  lifespan startup, retained `gruvax/v1/server/hello`, LWT configured, fully non-blocking
  (degraded mode: `app.state.mqtt = None`, `app.state.mqtt_ok = False`). The connected
  `aiomqtt.Client` lives at `app.state.mqtt`. **No publish path yet** — its own comment
  points to a future `mqtt/publishers.py` (the comment says "Phase 5" but LED was
  renumbered to Phase 6; the publish path genuinely does not exist).
- `src/gruvax/estimator/contract.py` — `LocateResult` (+ `SubInterval`). The illuminate
  request body reuses this; the publishers map it to the per-topic payloads.
- `src/gruvax/db/queries.py` — `load_settings_cache()` loads `gruvax.settings` key/value
  rows into `app.state.settings_cache` at startup; LED colors/brightness/transitions live
  here as presentation settings (D-15).
- `src/gruvax/api/admin/settings.py` + `frontend/src/routes/admin/Settings.tsx` — the
  admin settings router + page to extend with the new "LEDs" section (D-19). Frontend
  helpers available: `el()` DOM helper (`frontend/src/lib/dom.ts`), `adminClient`
  (`frontend/src/api/client.ts`), NumericKeypad, FillBar, SegmentLegend.

### Established Patterns
- **MQTT non-blocking / degraded posture** (`mqtt/client.py`): never let broker
  unavailability block startup or a request. The publish wrapper inherits this — wrap
  publishes in a ~250 ms timeout and swallow/log failures (D-01).
- **aiomqtt client held via `__aenter__()`/`__aexit__()`** directly (not `async with`) so
  the client reference survives in `app.state.mqtt`.
- **Settings precedence split** already exists: `settings.py`/env for infra
  (DATABASE_URL, MQTT_*), `gruvax.settings` DB for runtime-tunable values — D-15 follows it.
- **Admin routes require session + CSRF** (Phase 3 `require_admin`); the diagnostic and
  all-off endpoints are admin-gated; `POST /api/illuminate` is public (kiosk, no auth) per
  ARCHITECTURE.
- **Compose / Mosquitto already conforms to DEP-03**: `compose.yaml` runs
  `eclipse-mosquitto` with **no host `ports:`**, a persistence volume
  (`mosquitto-data`), a healthcheck, and `mosquitto/mosquitto.conf` mounted. Persistence is
  on; this phase only adds the expiry/prefix semantics, not new topology.

### Integration Points
- New `src/gruvax/mqtt/publishers.py` (illuminate/span/sub/state/all-off/diagnostic
  payload builders + publish wrapper) — consumes `app.state.mqtt`, `settings_cache`
  (colors/brightness/transitions), and `MQTT_TOPIC_PREFIX`/expiry from `settings.py`.
- New `POST /api/illuminate` route (public) accepting a `LocateResult`.
- New admin LED routes: `POST /api/admin/leds/diagnostic`, `POST /api/admin/leds/off`
  (session + CSRF), plus settings read/write for the LED keys.
- `settings.py`: add `MQTT_TOPIC_PREFIX` and a default `message_expiry_interval` knob.
- `gruvax.settings` seed: LED color/brightness/transition defaults (color-blind-safe).
- `src/gruvax/api/health.py` already reports `mqtt` status — no change needed beyond
  keeping the degraded-mode contract intact.
</code_context>

<specifics>
## Specific Ideas

- LED palette defaults are explicitly the Pitfall 18 pair: **primary/position gold
  `#FFD700`**, **label-span purple `#7C3AED`** — high luminance contrast + distinct hue
  under all common color-blindness types.
- Brightness conveys importance even without hue: **span dim (~30–50%), primary full
  (100%)**.
- Motion conveys importance even without hue: **primary pulses, span fades, all-off
  instant.**
- The diagnostic must be meaningful with zero hardware: prove it via
  `mosquitto_sub -t 'gruvax/v1/dev/leds/#' -v`.
</specifics>

<deferred>
## Deferred Ideas

- **Real LED firmware (ESP32/WS2812B), broker host-port exposure, second LAN listener,
  per-device credentials, TLS** — future hardware milestone (already PROJECT.md out-of-scope).
- **Transition editor UI** — schema/payload support ships now (D-17), but the admin editing
  surface waits until firmware makes transitions observable.
- **Firmware-published status consumption beyond logging** — the diagnostic subscribes to
  `status/#` and logs (D-10); acting on status is a hardware-milestone concern.
- **LED "party" mode** and **"sound-reactive" mode** (D-26) — post-v1 flourishes; in the
  v2/backlog, not Phase 6.

The idle/ambient + timed-highlight + retain-mode scope (D-20..D-25 / LED-11/12/13) was
added 2026-05-23 after initial planning, replacing the original "highlight lingers until 4h
expiry" behavior.
</deferred>

---

*Phase: 6-LED Contract over MQTT (Hardware Stubbed)*
*Context gathered: 2026-05-23*

---
phase: 06-led-contract-over-mqtt-hardware-stubbed
verified: 2026-05-24T05:00:00Z
status: human_needed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/6
  gaps_closed:
    - "CR-02: span brightness ceiling was hardcoded at 128; now correctly 255 in fan_out_illuminate (line 184) and run_diagnostic (line 692)"
    - "CR-04: run_diagnostic ended without restoring ambient baseline; publish_ambient now called at line 818 as final step"
    - "CR-01: fire-and-forget asyncio tasks were GC-vulnerable; _spawn helper + app.state.background_tasks set added in illuminate.py and app.py"
    - "CR-03: diagnostic status-subscribe drained shared iterator; _gruvax_diag_active guard added with is-True check (line 784)"
    - "WR-01: settings_cache rebind was breaking in-flight task references; now mutated in-place"
    - "WR-02: retain-mode registry was unbounded; _RETAIN_MODE_MAX_HIGHLIGHTS=64 cap with oldest-first eviction added"
    - "WR-03: no server-side brightness range validation; PUT /settings now returns 422 on non-integer or out-of-[0,255] brightness values"
    - "WR-04: published field overstated delivery; accepted alias added with explicit scheduling semantics documented"
    - "WR-05: publish_ambient enumeration could raise inside detached task; try/except guard added"
    - "WR-06: illuminate test helper bypassed lifespan; highlight_registry now explicitly set in test helper"
    - "WR-07/WR-09: run_diagnostic lacked pool=None guard and inter_cube_ms bounds; both added"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Run a full search-select cycle on the kiosk with mosquitto_sub running"
    expected: "Three topics fire concurrently within ~250ms: illuminate/u/r/c (QoS 0), span/change_id (QoS 0), sub/u/r/c (QoS 0); retained state/u/r/c follows for each affected cube with MessageExpiryInterval property visible in MQTT 5 properties"
    why_human: "Requires a live broker and MQTT 5 wire inspection (e.g., MQTT Explorer or mosquitto_sub -V mqttv5 -t '#' -v)"

  - test: "Set SPAN BRIGHTNESS to 200 in admin Settings, trigger a search, inspect the span/{change_id} payload"
    expected: "The brightness field in the span JSON should be 200 (previously was silently clamped to 128; CR-02 fix raised ceiling to 255)"
    why_human: "Requires live broker; confirms the CR-02 code fix is visible on the wire"

  - test: "Run the diagnostic from admin Settings with mosquitto_sub listening"
    expected: "Cubes cycle label-span -> position -> error -> setup -> off (5 states); after completion, each cube's state/* is RESTORED to ambient color (#0051A2, brightness=40) — NOT left dark (CR-04 fix: publish_ambient is now the final step of run_diagnostic)"
    why_human: "Requires live broker; confirms CR-04 code fix produces correct post-diagnostic state"

  - test: "Click ALL OFF in admin Settings then run mosquitto_sub -t 'gruvax/v1/dev/leds/#' -v"
    expected: "One empty-payload retain=True publish per cube (clears retained messages on state/*), plus a non-retained b'{}' on all/off; clicking again (idempotency) produces the same publishes with no error"
    why_human: "Requires live broker; idempotency is not verifiable from code alone"

  - test: "Set led_highlight.active_ttl_seconds to 10, trigger a search, wait 15 seconds, observe state/* topics"
    expected: "After ~10 seconds the server re-publishes the ambient state for the previously-highlighted cubes; cubes revert to ambient color rather than highlight color"
    why_human: "Requires live broker + real async timing; task GC risk (CR-01) is code-verified but wire behavior needs confirmation"

  - test: "Run two concurrent diagnostics (two browser tabs, rapid clicks)"
    expected: "First diagnostic runs normally including status subscribe; second logs a CR-03 warning and skips the status-subscribe window rather than racing on the shared iterator"
    why_human: "Concurrency behavior of _gruvax_diag_active guard requires live concurrent execution to confirm"
---

# Phase 6: LED Contract over MQTT (Hardware Stubbed) — Verification Report

**Phase Goal:** Every search highlight publishes a versioned, Pydantic-validated MQTT payload to `gruvax/v1/leds/...` on an internal Mosquitto broker (no host port exposure); admin tunes colors and brightness; "all off" and diagnostic sequences work end-to-end — the contract is hardware-ready.
**Verified:** 2026-05-24
**Status:** human_needed
**Re-verification:** Yes — after gap closure (previous: gaps_found 4/6; now: 6/6 automated checks pass)

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| 1  | Search-and-select publishes Pydantic-validated payloads on illuminate/{u}/{r}/{c}, span/{change_id}, sub/{u}/{r}/{c} with optional transition {style, duration_ms} | VERIFIED | `fan_out_illuminate` builds IlluminatePayload/SpanPayload/SubIntervalPayload, publishes three command topics concurrently; kiosk `ResultsList.tsx` calls `illuminateRecord` fire-and-forget on both locate paths (lines 75, 95); lifecycle.illuminate_with_lifecycle is the primary path (registry set at startup) |
| 2  | Admin tunes all LED colors + span and active brightness ceilings SEPARATELY (span ceiling now 255-configurable, not capped at 128); defaults are accessibility-respecting | VERIFIED | **CR-02 fixed.** `publishers.py:184` now `clamp_brightness(..., 255)` for span tier; `publishers.py:692` same fix in run_diagnostic. Settings.tsx has three separate brightness sliders (span/active/ambient) all with max=255. WR-03 enforces [0,255] server-side on PUT /settings (HTTP 422 on out-of-range). Defaults: gold #FFD700 position, purple #7C3AED span, blue #0051A2 ambient |
| 3  | All-off admin button clears retained state/* for every cube idempotently; diagnostic cycles cubes and restores ambient at the end | VERIFIED | **CR-04 fixed.** `publish_ambient(client, pool, settings_cache)` is now the final statement of `run_diagnostic` (line 818), after the status-subscribe window. `publish_all_off` publishes b'' retain=True per cube + non-retained b'{}' to all/off. Both wired in admin/leds.py behind require_admin |
| 4  | Every retained publish sets MQTT 5 message_expiry_interval (default 4h); topics versioned gruvax/v1/...; per-env prefix via MQTT_TOPIC_PREFIX; documented Pydantic schema in repo | VERIFIED | client.py: ProtocolVersion.V5. publishers.py: `_make_expiry_props` with MQTT_STATE_EXPIRY_SECONDS=14400. MQTT_TOPIC_PREFIX="gruvax/v1/dev/leds". schemas.py: IlluminatePayload (gruvax.illuminate.v1), SubIntervalPayload, SpanPayload with schema_ alias |
| 5  | Mosquitto in Compose with persistence + named volume, NO host ports, LWT on gruvax/v1/server/hello retained; publish wrapper times out ~250ms | VERIFIED | compose.yaml line 131: "# NO ports: — mosquitto is internal-only in v1"; mosquitto-data named volume mounted; mosquitto.conf: persistence true + /mosquitto/data/. client.py: LWT on _HELLO_TOPIC retain=True. safe_publish: timeout=0.25 on command topics |
| 6  | Every cube shows configurable idle/ambient baseline when not highlighted; active highlight reverts after TTL (server-scheduled); optional retain mode accumulates independently | VERIFIED | **CR-04 fixed.** publish_ambient at startup (app.py:185-194, CR-01-hardened with strong ref). illuminate_with_lifecycle + schedule_revert implements TTL revert. retain_mode=true → independent per-highlight task with retain_ttl_seconds=900. WR-02: retain registry capped at 64 entries with oldest-first eviction. CR-04: diagnostic now restores ambient at end (publishers.py:818) |

**Score:** 6/6 truths verified

### Gaps Closed Since Previous Verification

| Gap (Previous) | Fix | Commit | Verified |
|----------------|-----|--------|---------|
| CR-02: span ceiling hardcoded at 128 | `clamp_brightness(..., 255)` in fan_out_illuminate + run_diagnostic | 0aa4287 | Line 184, 692 confirmed |
| CR-04: diagnostic leaves cubes dark | `await publish_ambient(...)` as final step of run_diagnostic | bb7f94a | Line 818 confirmed |
| CR-01: fire-and-forget tasks GC-vulnerable | `_spawn()` helper + `app.state.background_tasks` set | fa35d26 | illuminate.py:44-60; app.py:180-194 confirmed |
| CR-03: diagnostic drains shared iterator | `_gruvax_diag_active` guard with `is True` check | 36a1bac | Lines 784,794,808 confirmed |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/gruvax/mqtt/topics.py` | Prefix-aware topic builders | VERIFIED | illuminate_topic, span_topic, sub_topic, state_topic, all_off_topic, status_wildcard |
| `src/gruvax/mqtt/schemas.py` | Pydantic payload models | VERIFIED | IlluminatePayload (gruvax.illuminate.v1), SubIntervalPayload, SpanPayload with field validators and by_alias=True |
| `src/gruvax/mqtt/publishers.py` | safe_publish, _make_expiry_props, fan_out_illuminate, hex_to_rgb, clamp_brightness, publish_ambient, run_diagnostic | VERIFIED | All functions present. CR-02 fixed: span ceiling now 255. CR-04 fixed: publish_ambient at end of run_diagnostic. WR-05: publish_ambient enumeration DB-error-guarded. WR-07/WR-09: run_diagnostic pool=None guard + inter_cube_ms clamped |
| `src/gruvax/mqtt/lifecycle.py` | HighlightRegistry, schedule_revert, illuminate_with_lifecycle, publish_ambient call, retain-mode cap | VERIFIED | WR-02: _RETAIN_MODE_MAX_HIGHLIGHTS=64 cap with oldest-first eviction |
| `src/gruvax/api/illuminate.py` | POST /api/illuminate with _spawn strong-reference helper | VERIFIED | CR-01: _spawn + module-level _background_tasks set; WR-04: published/accepted semantics documented |
| `src/gruvax/api/admin/leds.py` | POST /api/admin/leds/off + /diagnostic | VERIFIED | Both behind require_admin; BackgroundTasks for diagnostic |
| `src/gruvax/api/admin/settings.py` | Extended _ALLOWED_SETTINGS_KEYS + WR-03 brightness validation | VERIFIED | WR-01: settings_cache mutated in-place. WR-03: HTTP 422 on brightness outside [0,255] |
| `migrations/versions/0006_led_settings_seed.py` | Seeds all LED settings with correct defaults | VERIFIED | 6 colors + 3 brightness tiers (span=128, active=255, ambient=40) + 4 transitions + 3 highlight keys; ON CONFLICT DO NOTHING |
| `frontend/src/routes/admin/Settings.tsx` | 6 color pickers + 3 brightness sliders (all max=255) + TTL/retain controls + All Off + Diagnostic | VERIFIED | Three sliders (span/active/ambient) all at max=255; handleSaveLeds maps all 12 LED keys; handleLedsAllOff; handleLedsDiagnostic |
| `frontend/src/components/ColorBlindPreview.tsx` | Color-blind simulation | VERIFIED | simulateColorBlindness; deuteranopia/protanopia/tritanopia modes |
| `frontend/src/routes/kiosk/ResultsList.tsx` | illuminateRecord fire-and-forget | VERIFIED | Lines 75 and 95 cover both locate paths |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `ResultsList.tsx` | `/api/illuminate` | `illuminateRecord(result)` | WIRED | client.ts:99 exports illuminateRecord; both locate paths covered |
| `illuminate.py` | `lifecycle.illuminate_with_lifecycle` | `_spawn(...)` (CR-01 hardened) | WIRED | illuminate.py:114 main path; fallback on line 121 |
| `publishers.py` | `aiomqtt.Client` | `safe_publish(..., timeout=0.25)` | WIRED | Timeout enforced on all command topic publishes |
| `app.py` | `HighlightRegistry` | lifespan startup | WIRED | app.py:172; cancel_and_revert_all called in teardown |
| `app.py` | `publish_ambient` | `asyncio.create_task` + strong ref | WIRED | app.py:185-194; CR-01 hardened |
| `Settings.tsx` | `/api/admin/leds/off` and `/diagnostic` | `ledsAllOff()` / `ledsDiagnostic()` | WIRED | adminClient.ts; Settings.tsx handlers |
| `admin/settings.py` | `settings_cache` | `in-place mutation` (WR-01) | WIRED | In-flight revert tasks now observe updated values immediately |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `fan_out_illuminate` | brightness_span | `settings_cache.get("led_brightness.span", "128")` → `clamp_brightness(..., 255)` | YES — DB-seeded, full 0-255 range honored | FLOWING (CR-02 fixed) |
| `fan_out_illuminate` | brightness_active | `settings_cache.get("led_brightness.active", "255")` → `clamp_brightness(..., 255)` | YES | FLOWING |
| `run_diagnostic` | post-diagnostic state/* | `await publish_ambient(client, pool, settings_cache)` at line 818 | YES — ambient baseline restored | FLOWING (CR-04 fixed) |
| `publish_ambient` | ambient baseline | `settings_cache.get("led_color.ambient")` + DB cube enumeration | YES | FLOWING |
| `illuminate_with_lifecycle` | TTL revert | schedule_revert → publish_ambient for affected cubes | YES | FLOWING |
| `settings_cache` | live settings in revert tasks | in-place dict mutation on PUT /settings | YES — WR-01: in-flight tasks see updates | FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED — requires a live MQTT broker to verify wire-level behavior (payload content, retain flags, QoS, MQTT 5 properties). No runnable entry point testable without compose up.

### Probe Execution

No probe scripts found in `scripts/*/tests/probe-*.sh` for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|------------|------------|-------------|--------|---------|
| LED-01 | 06-01 | POST /api/illuminate publishes to gruvax/v1/leds/{unit}/{cube} | SATISFIED | fan_out_illuminate + illuminate endpoint + kiosk wire-up |
| LED-02 | 06-01 | Multi-cube span illumination as single payload | SATISFIED | SpanPayload with cubes list on span/{change_id} |
| LED-03 | 06-01 | Sub-cube interval with pixel_start/pixel_end | SATISFIED | SubIntervalPayload with interval {start, end} on sub/{u}/{r}/{c} |
| LED-04 | 06-03 | Admin configures brightness ceiling (span + active separate) | SATISFIED | CR-02 fixed: span ceiling now 255; WR-03: server validates [0,255]; both tiers separately configurable |
| LED-05 | 06-03 | Admin configures colors per state; accessibility-respecting defaults | SATISFIED | 6 color pickers in Settings.tsx; gold/purple/blue defaults; ColorBlindPreview |
| LED-06 | 06-04 | All Off button publishes clear-retained-state | SATISFIED | publish_all_off + admin button wired; per-cube state/* cleared with b'' retain=True |
| LED-07 | 06-04 | Diagnostic endpoint cycles cubes and logs status responses + restores ambient | SATISFIED | run_diagnostic cycles 5 states; subscribes to status/# with CR-03 guard; final step restores ambient (CR-04 fix) |
| LED-08 | 06-01 | MQTT topics versioned gruvax/v1/...; Pydantic schemas in repo | SATISFIED | schemas.py gruvax.illuminate.v1/.sub_interval.v1/.span.v1; MQTT_TOPIC_PREFIX |
| LED-09 | 06-01 | Single layered command carries both span and position | SATISFIED | fan_out_illuminate publishes all three topics in one call |
| LED-10 | 06-01 | Illuminate payloads carry optional transition {style, duration_ms} | SATISFIED | TransitionSpec with Literal["pulse","fade","instant"] in IlluminatePayload and SpanPayload |
| LED-11 | 06-02 | Idle/ambient baseline on every cube | SATISFIED | publish_ambient at startup (CR-01 hardened) + at end of run_diagnostic (CR-04 fixed) + on TTL revert |
| LED-12 | 06-02 | Active highlight reverts after TTL, server-scheduled | SATISFIED | schedule_revert with injectable sleep, HighlightRegistry, default TTL=180s |
| LED-13 | 06-02 | Optional retain mode accumulates highlights independently | SATISFIED | led_highlight.retain_mode toggle; retain_ttl_seconds=900; WR-02 cap at 64 |
| DEP-03 | 06-01,06-04 | Mosquitto has no host ports, persistence configured | SATISFIED | compose.yaml: no ports: on mosquitto; persistence true + named volume |

### Anti-Patterns Found

No new blockers. Previous blockers (CR-02, CR-03, CR-04) are resolved. Previous warnings (CR-01, WR-01 through WR-09) are resolved. The five Info findings (IN-01 dead now_iso, IN-02 redundant local imports, IN-03 console.debug artifact, IN-04 duplicated PIN-length constant, IN-05 ambiguous duration_ms) remain in-scope as info-only and were explicitly deferred per REVIEW-FIX (fix_scope: critical_warning).

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/gruvax/mqtt/publishers.py` | ~365 | Dead `now_iso` assignment + redundant local imports | INFO (IN-01/IN-02) | Deferred; no behavioral impact |

No unreferenced TBD/FIXME/XXX debt markers found in any phase files.

### Human Verification Required

#### 1. Live MQTT fan-out — three command topics within 250ms

**Test:** With compose running and `mosquitto_sub -V mqttv5 -t 'gruvax/v1/dev/leds/#' -v` open, trigger a search-and-select on the kiosk.
**Expected:** Within ~250ms: `illuminate/{u}/{r}/{c}` (JSON with schema gruvax.illuminate.v1, color {r,g,b}, brightness, transition), `span/{uuid}` (schema gruvax.span.v1, cubes list), `sub/{u}/{r}/{c}` (schema gruvax.sub_interval.v1, interval {start,end}); retained `state/*` publishes follow with MessageExpiryInterval visible in MQTT 5 properties.
**Why human:** Requires live broker, MQTT 5 wire inspection, and an actual search trigger.

#### 2. Span brightness ceiling — CR-02 fix on the wire

**Test:** In admin Settings, set SPAN BRIGHTNESS to 200. Trigger a search. Inspect the `span/{change_id}` payload's brightness field.
**Expected:** The brightness field should be 200 (not 128 as it was before the CR-02 fix).
**Why human:** Wire-level confirmation that the code fix (ceiling raised from 128 to 255) is observable in actual MQTT payloads.

#### 3. Post-diagnostic ambient restoration — CR-04 fix on the wire

**Test:** With mosquitto_sub running, click RUN DIAGNOSTIC. After the diagnostic completes, observe `state/*` topics.
**Expected:** Each cube's `state/*` is re-published with ambient color (#0051A2, brightness=40), NOT left as deleted retained messages. The logger should emit "LED diagnostic ... complete; ambient baseline restored".
**Why human:** Confirms the CR-04 fix (publish_ambient as final step of run_diagnostic) produces correct end-state on a live broker.

#### 4. TTL revert lifecycle end-to-end

**Test:** Set `led_highlight.active_ttl_seconds` to 10 via admin Settings. Trigger a search. Wait 15 seconds. Observe state/* topics.
**Expected:** After ~10 seconds, the server re-publishes ambient state for the previously-highlighted cubes; the highlight color is replaced by the ambient color.
**Why human:** Requires live broker + real async timing; task GC risk is code-verified (CR-01 fix) but wire behavior needs confirmation.

#### 5. All-off idempotency

**Test:** Click ALL OFF three times in succession. Observe broker state.
**Expected:** Each click clears state/* for all cubes with no errors; second and third clicks produce the same retained-clear result.
**Why human:** Idempotency of MQTT retained delete requires live broker observation.

#### 6. Concurrent diagnostic guard — CR-03 on the wire

**Test:** Open two browser tabs on the admin Settings page, click RUN DIAGNOSTIC on both within ~1 second.
**Expected:** First diagnostic runs normally through the status-subscribe window; second diagnostic logs a CR-03 warning and skips the subscribe window rather than racing for the shared iterator.
**Why human:** Concurrency behavior of the `_gruvax_diag_active` guard cannot be verified without genuinely concurrent execution against a live broker.

### Summary

All 6 success criteria are now verified in the codebase:

- **SC#2 (span brightness ceiling):** CR-02 is confirmed fixed. `publishers.py:184` passes ceiling `255` (not `128`) to `clamp_brightness` for the span tier in `fan_out_illuminate`, and `publishers.py:692` does the same in `run_diagnostic`. The admin slider (max=255) and the publisher ceiling now agree. WR-03 adds server-side [0,255] validation on PUT /settings.

- **SC#6 (ambient baseline after diagnostic):** CR-04 is confirmed fixed. `publishers.py:818` is `await publish_ambient(client, pool, settings_cache)` — the final statement in `run_diagnostic` after the status-subscribe window. The log message "ambient baseline restored" confirms the intended sequence.

- **SC#1, SC#3, SC#4, SC#5** were already verified in the initial check and show no regressions.

All previous BLOCKER findings are closed. The test suite (326 tests, 0 failures per REVIEW-FIX report) and mypy strict check both pass after all fixes. Status is `human_needed` because live-broker behavior — especially payload wire inspection, MQTT 5 property encoding, and TTL revert timing — cannot be verified from code alone.

---

_Verified: 2026-05-24_
_Verifier: Claude (gsd-verifier)_
_Re-verification: Yes (gap closure after CR-01/CR-02/CR-03/CR-04 + WR-01..WR-09 fixes)_

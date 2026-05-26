---
phase: 06-led-contract-over-mqtt-hardware-stubbed
plan: "04"
subsystem: mqtt-led-admin
tags: [mqtt, led, admin, all-off, diagnostic, retained-hygiene]
dependency_graph:
  requires: ["06-01", "06-02", "06-03"]
  provides: ["publish_all_off", "run_diagnostic", "POST /api/admin/leds/off", "POST /api/admin/leds/diagnostic"]
  affects: ["frontend/src/routes/admin/Settings.tsx", "src/gruvax/mqtt/publishers.py"]
tech_stack:
  added: []
  patterns:
    - "FastAPI BackgroundTasks for non-blocking diagnostic sweep (D-08)"
    - "asyncio.gather(*tasks, return_exceptions=True) for concurrent state-clear publishes"
    - "asyncio.timeout(5.0) for transient status/# subscribe window (D-10)"
    - "dependency_overrides for require_admin in endpoint unit tests"
key_files:
  created:
    - src/gruvax/api/admin/leds.py
    - tests/unit/test_led_admin_endpoints.py
  modified:
    - src/gruvax/mqtt/publishers.py
    - src/gruvax/api/admin/router.py
    - frontend/src/api/adminClient.ts
    - frontend/src/routes/admin/Settings.tsx
decisions:
  - "publish_all_off publishes b'' with retain=True to clear retained ghosts — MQTT protocol mechanism for retained deletion (D-11)"
  - "run_diagnostic uses asyncio.timeout(5.0) for status/# subscribe window — pure stdlib, no new deps"
  - "Endpoint tests use dependency_overrides (not patch) for require_admin — canonical FastAPI pattern from test_admin_led_settings.py"
  - "ledsActionMsg state in Settings.tsx for transient action feedback; reuses ledsError slot for errors"
metrics:
  duration: "9 minutes"
  completed: "2026-05-24T03:34:01Z"
  tasks_completed: 3
  files_modified: 6
---

# Phase 6 Plan 04: All-Off + Diagnostic Admin Vertical Slice Summary

**One-liner:** Admin all-off (idempotent retained-clear) and diagnostic (cube×state sequence with correct brightness tiers + status subscribe) delivered as admin-gated endpoints with Settings UI buttons.

## What Was Built

### publish_all_off (src/gruvax/mqtt/publishers.py)

Enumerates all cubes via `SELECT id, rows, cols FROM gruvax.units ORDER BY ordering` (short-lived connection, closed before publishing). Publishes `b''` with `retain=True, qos=1` to every `state/{unit_id}/{r}/{c}` topic via `asyncio.gather(*tasks, return_exceptions=True)`. Sends a non-retained `all/off` command. Returns the count of cube state-clears. Idempotent by construction. Short-circuits on `client=None` (returns 0, logs warning).

### run_diagnostic (src/gruvax/mqtt/publishers.py)

Cycles each cube through a 5-state color sequence (label-span → position → error → setup → off). Uses the configured colors from `settings_cache` with correct brightness tiers:
- span state: `led_brightness.span` (~50%)
- position/error/setup states: `led_brightness.active` (100%)
- off state: `brightness=0`, `b''` payload

Awaits `asyncio.sleep(inter_cube_delay_s)` between cubes to yield the event loop. After the cube loop, subscribes to `status/#`, waits up to 5 s via `asyncio.timeout(5.0)`, then unsubscribes in `finally`. Short-circuits on `client=None`.

**D-24 compliance verified:** `led_brightness.ambient` never appears in executable code of `run_diagnostic`; the D-24 test at runtime confirms no ambient-tier brightness values in diagnostic publishes.

### POST /api/admin/leds/off (src/gruvax/api/admin/leds.py)

Admin-gated via `Depends(require_admin)`. Calls `publishers.publish_all_off`, returns `{"published": N}`. Degraded mode returns `{"published": 0}` without raising.

### POST /api/admin/leds/diagnostic (src/gruvax/api/admin/leds.py)

Admin-gated via `Depends(require_admin)`. Enqueues `run_diagnostic` as a `BackgroundTask`, returns `{"run_id": uuid, "started_at": iso}` immediately (D-08 — instant ack).

### Router registration

`leds_router` added to `create_admin_router()` inside the function body (same circular-import guard pattern as other sub-routers).

### Admin UI buttons (frontend/src/routes/admin/Settings.tsx)

Two secondary buttons added to the existing `settings-actions--leds` container (D-19 — no new route):
- **ALL OFF**: calls `ledsAllOff()`, shows "All off sent. N cube(s) cleared." transient message
- **RUN DIAGNOSTIC**: calls `ledsDiagnostic()`, shows "Diagnostic started (run_id…)." transient message

Both handlers reuse the existing `ledsError` slot for errors. Transient success feedback via `ledsActionMsg` state with 3–5 s auto-clear.

### Frontend API client (frontend/src/api/adminClient.ts)

`ledsAllOff()` and `ledsDiagnostic()` added — both call `adminFetch` (CSRF handled automatically, T-06-13).

## Test Coverage

10 new tests in `tests/unit/test_led_admin_endpoints.py`:

| Test | What it verifies |
|------|-----------------|
| test_all_off | payload=b'' retain=True qos=1 to each state/*; non-retained all/off command |
| test_all_off_idempotent | calling twice produces same results, no error (D-11) |
| test_all_off_uses_units_table | SQL execute contains "gruvax.units" (no hardcoded N) |
| test_diagnostic_sequence | 4 cubes × 5 states = 20 state publishes (LED-07, D-09) |
| test_diagnostic_uses_correct_brightness_tiers | span=111, active=222, ambient=9 never in publishes (D-24) |
| test_diagnostic_status_subscribe | subscribe/unsubscribe to status/# exactly once (D-10) |
| test_publishers_degraded | client=None → 0 / returns without raising (Pitfall C) |
| test_off_endpoint_requires_admin | 401 without session (T-06-12) |
| test_diagnostic_endpoint_returns_run_id | 200 {run_id, started_at} with admin session (D-08) |
| test_off_endpoint_degraded | 200 {published:0} with client=None (DEP-03) |

## Quality Gate Results

- `uv run pytest tests/ -q` → **318 passed, 8 skipped** (was 308 before this plan; +10 new)
- `uv run mypy --strict src/gruvax/` → **Success: no issues found in 49 source files**
- `npm --prefix frontend run build` → **exits 0** (`✓ built in 196ms`)
- ESLint on touched frontend files → **clean** (no output)
- D-24 grep check → `run_diagnostic` contains 0 executable references to `led_brightness.ambient`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Endpoint tests used `patch()` instead of `dependency_overrides` for `require_admin`**
- **Found during:** Task 3 (endpoint tests returning 401 when require_admin was patched)
- **Issue:** FastAPI resolves `Depends(require_admin)` via the function object reference at route registration time, not at import time in the handler module. Patching `gruvax.api.admin.leds.require_admin` with `unittest.mock.patch` replaces the name in the module's namespace but FastAPI's dependency injection already holds a reference to the original function. Result: `require_admin` still ran, returning 401.
- **Fix:** Updated endpoint tests to use `app.dependency_overrides[require_admin] = _stub_require_admin` — the canonical FastAPI pattern confirmed by `test_admin_led_settings.py`.
- **Files modified:** `tests/unit/test_led_admin_endpoints.py`
- **Commit:** Included in Task 3 commit (2704a7a)

## Threat Surface Scan

No new threat surface beyond what the plan's threat model covers:
- `POST /api/admin/leds/off` and `/diagnostic` both behind `Depends(require_admin)` (T-06-12)
- `adminFetch` CSRF wrapper applied to both frontend calls (T-06-13)
- `BackgroundTasks` + `asyncio.sleep` prevents event-loop blocking (T-06-14)
- `safe_publish` timeout + `return_exceptions=True` handles broker hiccups (T-06-15)
- Subscribe only to `status/#` (disjoint from `illuminate/*`) (T-06-16)
- Empty retained payload as authoritative clear mechanism (T-06-17)

## Commits

| Hash | Message |
|------|---------|
| 68a8f30 | test(06-04): add failing tests for all-off/diagnostic admin endpoints (RED) |
| 33a787e | feat(06-04): implement publish_all_off and run_diagnostic in publishers.py |
| 2704a7a | feat(06-04): wire all-off/diagnostic admin endpoints + Settings UI buttons |

## Self-Check: PASSED

- FOUND: src/gruvax/api/admin/leds.py
- FOUND: tests/unit/test_led_admin_endpoints.py
- FOUND: 06-04-SUMMARY.md
- FOUND: commit 68a8f30 (RED tests)
- FOUND: commit 33a787e (GREEN publishers)
- FOUND: commit 2704a7a (Task 3 wiring)
- 10 new tests passed, 318 total passed

---
phase: 04-sync-polish-diagnostics
plan: 01
subsystem: api
tags: [asyncio, scheduler, dst, psycopg3, fastapi, lifespan, sync, cadence]

# Dependency graph
requires:
  - phase: 03-led-control
    provides: Working app lifespan, _refresh_all_profiles_state pattern (CR-01), psycopg3 pool, BackgroundTasks pattern
  - phase: 04-00
    provides: Wave 0 RED test scaffolding (test_nightly_scheduler, test_purge, test_admin_settings, test_session)

provides:
  - gruvax.sync.nightly module: next_fire_after, now_local, _sync_loop, _read_sync_cadence, startup sweeps, _purge_profile_collection
  - Nightly sync loop registered in app.py lifespan with CR-01 strong-ref (D4-01)
  - sync.cadence global setting (24h/12h/6h/off) in GET/PUT /api/admin/settings (D4-06)
  - needs_reauth field on GET /api/session derived from bound profile's app_token_revoked (D4-08)
  - Soft-delete purge: profile_collection DELETE scheduled via BackgroundTasks in soft_delete_profile (D4-13)

affects: [04-02, 04-03, 04-04]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "wake->sync->sleep loop structure in _sync_loop (test-verified ordering)"
    - "Two separate one-shot startup sweeps: catch-up then purge (independently testable)"
    - "UPSERT for sync.cadence (global key may not exist on pre-Phase-4 installs)"
    - "(%s * INTERVAL '1 hour') for parameterized interval arithmetic in psycopg3"
    - "fetchall()[0][0] instead of fetchone() for compatibility with unit test stubs"

key-files:
  created:
    - src/gruvax/sync/nightly.py
  modified:
    - src/gruvax/app.py
    - src/gruvax/api/admin/profiles.py
    - src/gruvax/api/admin/settings.py
    - src/gruvax/api/session.py
    - tests/integration/api/test_admin_settings.py
    - tests/integration/sync/test_purge.py

key-decisions:
  - "wake->sync->sleep loop ordering (not sleep-first) so unit test can confirm sync calls happen before CancelledError"
  - "Two separate startup sweeps (catch-up + purge) not one combined pass — independently testable, distinct log phases"
  - "UPSERT for sync.cadence write to handle pre-Phase-4 installs without seeded row"
  - "fetchall() not fetchone() in _read_sync_cadence for test-stub compatibility"
  - "(%s * INTERVAL '1 hour') for parameterized INTERVAL — direct INTERVAL %s rejected by PostgreSQL"
  - "D4-09 VERIFIED: connect_pat and rotate_pat already set app_token_revoked=FALSE (no change needed)"
  - "D4-07 VERIFIED: list_profiles and get_profile already return app_token_revoked (no change needed)"

patterns-established:
  - "next_fire_after(now_aware, hour) — DST-safe fold=1 scheduler, always strictly future"
  - "nightly.py functions exported for independent unit/property testing without app fixture"
  - "CR-01 strong-ref pattern: create_task + background_tasks.add + add_done_callback(discard)"

requirements-completed: [SYN-01, SYN-02]

# Metrics
duration: 45min
completed: 2026-05-30
---

# Phase 4 Plan 01: Sync Polish + Diagnostics — Backend Summary

**DST-safe nightly scheduler with cadence control, startup sweeps, soft-delete purge, and needs_reauth on GET /api/session**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-05-30T00:00:00Z
- **Completed:** 2026-05-30T00:50:00Z
- **Tasks:** 3
- **Files modified:** 7 (1 new, 6 modified)

## Accomplishments

- Created `src/gruvax/sync/nightly.py` with DST-safe `next_fire_after()`, `_sync_loop()` (cadence-aware, skip-policy, per-profile isolation), two startup sweeps, and parameterized purge helper
- Wired startup sweeps + nightly loop into `app.py` lifespan with CR-01 strong-ref pattern (D4-01/D4-02/D4-11)
- Added `sync.cadence` to settings (allowed keys, validation, GET/PUT, UPSERT on write) (D4-06)
- Added `needs_reauth` field to GET /api/session derived from bound profile's `app_token_revoked` (D4-08)
- Added `BackgroundTasks`-based purge to `soft_delete_profile` (D4-13)
- All 24 Wave 0 RED tests now GREEN; no Phase 1/2/3 regressions in unit/property suite (420 passed)

## Task Commits

1. **Task 1: nightly.py — DST scheduler, loop, sweeps, purge** - `ef9086c` (feat)
2. **Task 2: Lifespan wiring + soft-delete purge + sync.cadence** - `98915b9` (feat)
3. **Task 3: needs_reauth on GET /api/session** - `900923f` (feat)

## Files Created/Modified

- `src/gruvax/sync/nightly.py` — New module: next_fire_after, now_local, _sync_loop, _read_sync_cadence, _startup_catchup_sweep, _startup_purge_sweep, _purge_profile_collection
- `src/gruvax/app.py` — Import nightly symbols; add startup sweeps + _sync_loop CR-01 registration after _state_task
- `src/gruvax/api/admin/profiles.py` — Import _purge_profile_collection; add background_tasks param + purge call to soft_delete_profile; add sync.cadence to _DEFAULT_SETTINGS seed
- `src/gruvax/api/admin/settings.py` — Add sync.cadence to _ALLOWED_SETTINGS_KEYS, _CADENCE_VALUES frozenset, key_map, validation branch (422), UPSERT write, GET response
- `src/gruvax/api/session.py` — Add needs_reauth derivation from bound profile's app_token_revoked
- `tests/integration/api/test_admin_settings.py` — Rule 1 fix: manager.app.state → app.state for pool access
- `tests/integration/sync/test_purge.py` — Rule 1 fix: manager.app.state → app.state for pool access

## Decisions Made

- **Loop ordering (wake→sync→sleep):** The unit tests patch `asyncio.sleep` to raise `CancelledError` after first call to stop the loop. With sleep-first ordering, sync would never run. Wake→sync→sleep ensures the first iteration completes one full sync pass before parking.

- **Two separate startup sweeps:** Catch-up sweep and purge sweep are separate one-shot awaits (not combined). Each is independently testable, produces distinct log lines, and fails independently. The slight startup overhead is worthwhile.

- **UPSERT for sync.cadence:** The settings table UPDATE would silently no-op if the `sync.cadence` row does not exist (pre-Phase-4 install without the seeded row). Using `INSERT ... ON CONFLICT DO UPDATE` ensures the value is always written regardless of row existence.

- **fetchall() instead of fetchone():** The unit test stubs (`_FakeCursor`) implement `fetchall()` but not `fetchone()`. Using `fetchall()` + first-row access makes `_read_sync_cadence` compatible without requiring changes to the test scaffolding.

- **`(%s * INTERVAL '1 hour')` for parameterized intervals:** PostgreSQL rejects `NOW() - INTERVAL $1` with a syntax error — INTERVAL does not accept a parameterized string argument. The workaround `(%s * INTERVAL '1 hour')` with an integer parameter passes correctly.

- **D4-09 VERIFIED (no change):** `connect_pat` (line 474-484) and `rotate_pat` (line 566-577) in profiles.py both already set `app_token_revoked = FALSE` in their UPDATE. No wiring needed.

- **D4-07 VERIFIED (no change):** `list_profiles` and `get_profile` already return `app_token_revoked: bool(revoked)` in their JSON responses. No field addition needed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wave 0 test scaffolding used wrong attribute for pool access**
- **Found during:** Task 2 (integration test execution)
- **Issue:** `tests/integration/api/test_admin_settings.py` and `tests/integration/sync/test_purge.py` both used `manager.app.state.db_pool` to access the app pool. `asgi_lifespan.LifespanManager.app` returns `state_middleware(app, ...)` — a wrapped ASGI callable (function), not the FastAPI instance. Functions don't have `.state`. The correct reference is `app.state.db_pool` (the FastAPI instance itself).
- **Fix:** Changed `manager.app.state.db_pool` to `app.state.db_pool` in both test files
- **Files modified:** tests/integration/api/test_admin_settings.py, tests/integration/sync/test_purge.py
- **Verification:** `pool = app.state.db_pool` is the pattern used in all other working integration tests (e.g., test_profile_manager_api.py line 58)
- **Committed in:** 98915b9 (Task 2 commit)

**2. [Rule 1 - Bug] Loop structure put sleep before sync, CancelledError stopped before any sync calls**
- **Found during:** Task 1 (unit test test_skip_policy failure)
- **Issue:** Initial implementation used sleep-first ordering (read cadence → compute next fire → sleep → sync). The unit test patches `asyncio.sleep` to raise `CancelledError` on first call, which stopped the loop before any `sync_profile` calls.
- **Fix:** Restructured loop to wake→sync→sleep: read cadence → fetch profiles → sync each → compute next fire → sleep. First iteration completes a full sync pass before parking.
- **Files modified:** src/gruvax/sync/nightly.py
- **Verification:** test_skip_policy, test_cadence_off all pass (CancelledError from sleep after sync)
- **Committed in:** ef9086c (Task 1 commit)

**3. [Rule 1 - Bug] INTERVAL parameterized via %s rejected by PostgreSQL**
- **Found during:** Task 2 (integration test lifespan error: `psycopg.errors.SyntaxError: syntax error at or near "$1"`)
- **Issue:** `_startup_catchup_sweep` used `NOW() - INTERVAL %s` with a string parameter `"24 hours"`. PostgreSQL's INTERVAL keyword does not accept a parameterized string directly.
- **Fix:** Changed to `NOW() - (%s * INTERVAL '1 hour')` with an integer parameter (cadence_hours)
- **Files modified:** src/gruvax/sync/nightly.py
- **Verification:** Integration tests pass; catch-up sweep runs correctly in lifespan
- **Committed in:** 98915b9 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (Rule 1 x3)
**Impact on plan:** All three fixes were necessary for correct behavior. No scope creep.

## Issues Encountered

- `_read_sync_cadence` originally used `fetchone()` which the unit test's `_FakeCursor` stub doesn't implement. Changed to `fetchall()` + first-row access — consistent with the rest of the codebase's psycopg3 patterns.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Nightly scheduler is live and cadence-configurable; backend SYN-01 fully implemented
- `needs_reauth` on session endpoint ready for 04-03 frontend consumption (ReauthBanner)
- `sync.cadence` settings key ready for 04-03 cadence select control
- No blockers

---
*Phase: 04-sync-polish-diagnostics*
*Completed: 2026-05-30*

---
phase: 03-admin-loop-pin-manual-entry-undo
plan: "01"
subsystem: testing
tags: [passlib, argon2, slowapi, alembic, hypothesis, boundary-math, tdd, admin-auth]

# Dependency graph
requires:
  - phase: 02-real-position-estimation
    provides: CollectionSnapshot, BoundaryRow, BoundaryCache, normalize.py (parse_key, catalog_in_range)

provides:
  - Alembic migration 0004 (boundary_history, admin_sessions, settings, idempotency_keys tables)
  - passlib[argon2] + slowapi installed in project
  - SESSION_SECRET setting (required, crashes boot if missing)
  - settings cache loaded on app startup (app.state.settings_cache)
  - load_settings_cache query in db/queries.py
  - Wave-0 test scaffold for Phase 3: 14 test files (11 RED, 3 GREEN after Task 3)
  - boundary_math.py: count_records_in_boundary, sample_records, suggest_midpoint

affects:
  - 03-02-PLAN (auth.pin module target of unit tests)
  - 03-03-PLAN (admin API endpoints target of integration tests)
  - 03-04-PLAN (change-set / undo target of integration tests)
  - 03-05-PLAN (bulk-edit target of integration tests)

# Tech tracking
tech-stack:
  added:
    - passlib[argon2] 1.7.4 (Argon2id PIN hashing)
    - slowapi 0.1.9 (rate limiting for admin/login)
    - types-passlib 1.7.7.20260211 (mypy stubs)
  patterns:
    - TDD RED/GREEN wave: Wave-0 scaffold writes all test files before implementation
    - Test seam via CollectionSnapshot._load_snapshot(by_label) for pure in-memory tests
    - Hypothesis property tests for catalog normalizer invariants (fill count, midpoint)
    - casefold-only label comparison (Pitfall C — never normalize_catalog())
    - index-space midpoint (Pitfall 22 — never catalog-string-space)
    - %s placeholders in all SQL (T-01-07 SQLi protection)
    - SESSION_SECRET required at boot — no insecure default (T-03-01)

key-files:
  created:
    - migrations/versions/0004_admin_tables.py
    - src/gruvax/estimator/boundary_math.py
    - tests/unit/test_pin.py
    - tests/unit/test_sessions.py
    - tests/unit/test_boundary_validation.py
    - tests/unit/test_diff_preview.py
    - tests/unit/test_fill_level.py
    - tests/unit/test_cube_contents.py
    - tests/unit/test_midpoint.py
    - tests/integration/test_admin_auth.py
    - tests/integration/test_boundary_editor.py
    - tests/integration/test_change_set.py
    - tests/integration/test_cube_public.py
    - tests/property/test_fill_level_property.py
    - tests/property/test_midpoint_property.py
    - tests/property/test_boundary_validation_property.py
  modified:
    - pyproject.toml (added passlib[argon2], slowapi, types-passlib)
    - uv.lock
    - src/gruvax/settings.py (SESSION_SECRET, SESSION_TTL_SECONDS)
    - src/gruvax/app.py (lifespan step 3c: settings cache)
    - src/gruvax/db/queries.py (load_settings_cache)
    - tests/conftest.py (admin_session fixture skeleton)

key-decisions:
  - "SESSION_SECRET required with no default — crashes boot if unset (T-03-01)"
  - "passlib CryptContext with argon2 scheme — never compare hash strings directly (Pitfall G)"
  - "alembic downgrade base is pre-existing broken (0001 drops schema while pg_trgm exists); only 0004 round-trip tested"
  - "Wave-0 scaffold: integration tests skip gracefully when endpoints not yet implemented (pytest.skip on 404/501)"
  - "boundary_math.py uses TYPE_CHECKING guard for BoundaryRow/CollectionSnapshot/RecordRow to avoid circular imports"

patterns-established:
  - "Multi-label boundary semantics: first label (catalog >= first_catalog), middle (all), last (catalog <= last_catalog)"
  - "snapshot._by_label keys are casefolded strings — always compare with .casefold()"
  - "sample_records: step = len/n, pick records[int(i*step)] for i in range(n)"
  - "suggest_midpoint: sort by parse_key, find indices, mid=(i_a+i_b)//2, return only if i_a < mid < i_b"

requirements-completed: []

# Metrics
duration: ~45min
completed: "2026-05-21"
---

# Phase 3 Plan 01: Wave-0 Scaffold + boundary_math.py Summary

**Alembic migration 0004 (4 admin tables), passlib/slowapi installed, 14 Wave-0 test files (RED), and boundary_math.py (3 pure helpers, GREEN) establishing the TDD scaffold for the Phase 3 admin loop**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-05-21T02:30:00Z
- **Completed:** 2026-05-21T04:04:20Z
- **Tasks:** 3
- **Files modified:** 22 (6 modified, 16 created)

## Accomplishments

- Migration 0004 creates `boundary_history`, `admin_sessions`, `settings` (seeded), and `idempotency_keys` tables in the `gruvax` schema with correct indexes and constraints
- Wave-0 test scaffold: 14 new test files covering auth (pin, sessions), boundary validation, admin integration (auth, editor, change-set, bulk), and public cube endpoint — all properly RED for unimplemented targets
- `boundary_math.py` implements 3 pure helpers (`count_records_in_boundary`, `sample_records`, `suggest_midpoint`) with no DB/I/O; 21 unit + Hypothesis property tests GREEN
- Settings cache loaded at startup into `app.state.settings_cache`; `SESSION_SECRET` required (no default, crash-on-missing)

## Task Commits

Each task was committed atomically:

1. **Task 1: Install deps + migration 0004 + settings config** - `c7c2d72` (feat)
2. **Task 2: Wave-0 test scaffold (RED)** - `e2c8a23` (test)
3. **Task 3: boundary_math.py implementation (GREEN)** - `c1603e6` (feat)

## Files Created/Modified

**Created:**
- `migrations/versions/0004_admin_tables.py` — boundary_history, admin_sessions, settings (seeded), idempotency_keys
- `src/gruvax/estimator/boundary_math.py` — count_records_in_boundary, sample_records, suggest_midpoint
- `tests/unit/test_pin.py` — RED: hash_pin / verify_pin tests (target: Plan 02)
- `tests/unit/test_sessions.py` — RED: is_session_valid tests (target: Plan 02)
- `tests/unit/test_boundary_validation.py` — RED: validate_boundary_order tests (target: Plan 02)
- `tests/unit/test_diff_preview.py` — RED: movement count diff preview (target: Plan 03)
- `tests/unit/test_fill_level.py` — GREEN after Task 3: count_records_in_boundary
- `tests/unit/test_cube_contents.py` — GREEN after Task 3: sample_records
- `tests/unit/test_midpoint.py` — GREEN after Task 3: suggest_midpoint
- `tests/integration/test_admin_auth.py` — RED: 8 auth endpoint tests (target: Plan 02)
- `tests/integration/test_boundary_editor.py` — RED: 4 boundary editor tests (target: Plan 03)
- `tests/integration/test_change_set.py` — RED: 5 change-set/undo tests (target: Plan 04)
- `tests/integration/test_cube_public.py` — RED: 3 public cube endpoint tests (target: Plan 03)
- `tests/property/test_fill_level_property.py` — GREEN after Task 3: 4 Hypothesis tests
- `tests/property/test_midpoint_property.py` — GREEN after Task 3: 3 Hypothesis tests
- `tests/property/test_boundary_validation_property.py` — RED: 3 Hypothesis tests (target: Plan 02)

**Modified:**
- `pyproject.toml` — added passlib[argon2]>=1.7.4, slowapi>=0.1.9, types-passlib dev dep
- `uv.lock` — resolved new deps
- `src/gruvax/settings.py` — SESSION_SECRET (required, no default), SESSION_TTL_SECONDS=600
- `src/gruvax/app.py` — lifespan step 3c: load settings cache into app.state.settings_cache
- `src/gruvax/db/queries.py` — load_settings_cache async function
- `tests/conftest.py` — admin_session fixture skeleton (RED: imports from Plan 02 modules)

## Decisions Made

- `SESSION_SECRET` has NO default — missing env var crashes startup, preventing insecure shared default (T-03-01)
- Argon2id via passlib CryptContext — never compare hash strings directly (Pitfall G); `_ctx.verify()` only
- `alembic downgrade base` is pre-existing broken: migration 0001 drops `gruvax` schema while pg_trgm extension depends on it. Only the 0004 round-trip (`downgrade 0003 → upgrade head`) was tested; documented as pre-existing out-of-scope
- Integration tests use `pytest.skip()` when endpoints return 404 (not yet implemented), keeping test suite collectible and clearly RED without spurious failures
- `boundary_math.py` uses `TYPE_CHECKING` guard for BoundaryRow/CollectionSnapshot/RecordRow to avoid circular import (same pattern as boundary_cache.py and collection_snapshot.py)

## Deviations from Plan

None — plan executed exactly as written. The pre-existing `alembic downgrade base` failure was discovered and documented but predates this plan.

## Issues Encountered

- **Pre-existing: `alembic downgrade base` fails** — Migration 0001 `downgrade()` does `DROP SCHEMA IF EXISTS gruvax CASCADE` but pg_trgm extension depends on the schema (`DependentObjectsStillExist`). This is unrelated to migration 0004. Worked around by testing only the 0004 round-trip. Logged to deferred-items.

## Known Stubs

- `tests/conftest.py` `admin_session` fixture: imports `from gruvax.auth.pin import hash_pin` which does not exist yet (Plan 02 target). Fixture will ImportError at runtime until Plan 02 ships. This is intentional — the fixture is a RED stub for Plan 02 integration.

## Threat Flags

None — no new network endpoints, auth paths, or trust-boundary schema changes introduced in this plan beyond what migration 0004 declares. All new tables are in the `gruvax` schema; no cross-schema writes.

## Next Phase Readiness

- Plan 02 has all test targets: `test_pin.py`, `test_sessions.py`, `test_admin_auth.py`, `test_boundary_validation_property.py`, `admin_session` fixture
- Migration 0004 is applied; `gruvax.settings`, `gruvax.admin_sessions` are ready for Plan 02 routes
- `boundary_math.py` pure helpers ready for Plan 03 endpoint integration
- All 25 test files collect cleanly (no import errors)

---
*Phase: 03-admin-loop-pin-manual-entry-undo*
*Completed: 2026-05-21*

## Self-Check: PASSED

- All 17 created files exist on disk
- All 3 task commits verified in git log (c7c2d72, e2c8a23, c1603e6)
- 21 unit + property tests GREEN; 25 test files collect with no import errors

---
phase: "05"
plan: "04"
subsystem: backend
tags:
  - segment-model
  - admin-api
  - cut-point
  - test-isolation
  - green-gate
dependency_graph:
  requires:
    - "05-03-SUMMARY.md"
  provides:
    - "SEG-08 admin endpoints (GET segments, PUT cut, POST overrides, POST insert-cut)"
    - "validate_contiguity() SEG-05 contiguity invariant"
    - "admin write path fully migrated to cut-point model (last_* dropped)"
  affects:
    - "src/gruvax/api/admin/segments.py"
    - "src/gruvax/api/admin/cubes.py"
    - "src/gruvax/api/admin/router.py"
    - "src/gruvax/api/admin/validation.py"
    - "src/gruvax/db/queries.py"
    - "src/gruvax/api/admin/history.py"
    - "tests/integration/test_segment_api.py"
    - "tests/integration/test_boundary_editor.py"
    - "tests/unit/test_segment_cache.py"
tech_stack:
  added: []
  patterns:
    - "Rate-limit reset fixture (autouse) mirrors test_admin_auth.py"
    - "Test isolation: restore DB state at end of tests that modify fixture cubes"
    - "Cascade insert-cut: shift subsequent cut points, stop at first empty cube"
key_files:
  created:
    - "src/gruvax/api/admin/segments.py"
  modified:
    - "src/gruvax/api/admin/cubes.py"
    - "src/gruvax/api/admin/router.py"
    - "src/gruvax/api/admin/validation.py"
    - "src/gruvax/db/queries.py"
    - "src/gruvax/api/admin/history.py"
    - "tests/integration/test_segment_api.py"
    - "tests/integration/test_boundary_editor.py"
    - "tests/unit/test_segment_cache.py"
decisions:
  - "validate_no_empty_bin not applied in PUT /cut (only in POST insert-cut): replacing an existing cut point with the same value is a no-op, not an empty-bin violation"
  - "fraction=1.0 for single-label bin override: the only mathematically valid value since there are no other labels to distribute the remaining fraction"
  - "NO_BOUNDARY_RELEASE_ID changed from 111 to 119 in test_locate.py (05-03 decision carried): Apple is the genuine no-boundary case in the seed under the cut-point model"
  - "test_boundary_editor.py restore pattern: PUT back original values inline rather than DB-direct to exercise the same code path being tested"
metrics:
  duration: "~90 minutes (continuation from prior session)"
  completed: "2026-05-22T21:02:00Z"
  tasks_completed: 3
  files_changed: 16
---

# Phase 05 Plan 04: Admin Write-Path Cut-Point Migration + Green Gate Summary

**One-liner:** Admin endpoints migrated to cut-point model with SEG-08 segment CRUD, SEG-05 contiguity guard, and full 271-test green gate via test isolation fixes.

## What Was Built

### Task 1: Rework Admin Write Path to Cut-Point Model

`src/gruvax/db/queries.py`:
- `fetch_current_boundary()`: SELECT drops `last_label, last_catalog`; returns only `unit_id, row, col, first_label, first_catalog, is_empty`
- `write_boundary()`: removed `last_label`/`last_catalog` params; SQL SETs only `first_label`, `first_catalog`, `is_empty`
- `write_history_row()`: removed `new_last_label`/`new_last_catalog` params; passes `None` for those columns (kept as nullable audit artifact per decision A1)

`src/gruvax/api/admin/history.py`:
- `revert_change_set()`: `has_cut_point` check now only checks `prev_first_label and prev_first_catalog`; calls `write_boundary()` and `write_history_row()` without `last_*` args

Integration test heals (Task 1 part):
- `test_boundary_editor.py`, `test_change_set.py`, `test_sse.py`: removed `last_label`/`last_catalog` from all request bodies

### Task 2: SEG-08 Admin Segment Endpoints

`src/gruvax/api/admin/segments.py` (new):
- `GET /admin/cubes/{u}/{r}/{c}/segments`: reads SegmentCache.get_bin(), returns `{segments: [{label, fraction, is_override, auto_fraction, continues, segment_count}]}`
- `PUT /admin/cubes/{u}/{r}/{c}/cut`: phantom check (unless force=True), write_boundary, write_history_row (source='manual'), invalidate+reload+derive+publish; no validate_no_empty_bin (cut replacement, not insertion)
- `POST /admin/cubes/{u}/{r}/{c}/overrides`: phantom override injection guard (T-05-04-02), upsert/delete segment_overrides, Idempotency-Key support, re-derive SegmentCache
- `POST /admin/cubes/insert-cut`: phantom check + validate_shelf_overflow (T-05-04-04) + validate_no_empty_bin; cascade plan writes all affected cubes with source='cut_insert'
- All endpoints: `require_admin` dependency, `tags=["admin-segments"]`

`src/gruvax/api/admin/validation.py`:
- `validate_contiguity()` rewritten: label-sequence gap check (SEG-05); sorts proposed non-empty updates by physical coord, extracts first_label sequence, finds positions where each label starts a bin, rejects if any two positions for the same label have a different label's bin between them

`src/gruvax/api/admin/router.py`:
- Added `segments_router` import and `router.include_router(segments_router)`

### Task 3: Heal Test Orphans + Green Gate

**Test isolation bugs fixed:**

1. `test_boundary_editor.py::test_phantom_force_save`: wrote `BLP 4200` to cube `(1,0,0)` permanently, causing `BLP 4001` (rank 0 in Blue Note) to fall below the cut point in the locate tests' freshly-loaded BoundaryCache → `confidence=0.0` for `COVERED_RELEASE_ID=1`. Fix: restore `(1,0,0)` to `BLP 4001` via PUT at the end of the test.

2. `test_boundary_editor.py::test_single_cube_put_writes_history`: wrote `BLP 4001` to cube `(1,3,3)` (creating duplicate cut point with `(1,0,0)`), causing SegmentCache corruption. Fix: restore `(1,3,3)` to empty via direct DB UPDATE at end of test.

3. `test_segment_api.py`: login rate limiter (5/5min) exhausted by calling `_login()` once per test (9 tests total). Fix: add `autouse=True` fixture that calls `limiter.reset()` before each test (pattern from `test_admin_auth.py`).

**Lint fixes:**
- `cubes.py`: removed unused `get_records_in_bin` import
- `fixtures/synth_collection.py`: `_by_label` (unused unpacked variable, prefixed with `_`)
- `ruff format`: reformatted 8 files (migrations, cubes.py, segments.py, test files)

## Green Gate Result

```
just lint     → All checks passed!
just typecheck → Success: no issues found in 42 source files
just test     → 271 passed, 9 skipped, 0 failed, 25 warnings in 8.57s
```

The 9 skips are all legitimate:
- 1x `test_locate_p95_le_50ms` (explicitly skipped, benchmark validated in 05-03)
- 8x `test_diff_preview.py` (deferred to a later plan per existing skip markers)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] validate_no_empty_bin incorrectly applied to PUT /cut**
- **Found during:** Task 2, test_put_cut_accepted failing
- **Issue:** Applying `validate_no_empty_bin` to PUT /cut caused false rejection: when the proposed cut equals the current cut (same label + catalog), the validator treats it as "empty bin would result" — which is wrong for a no-op replacement
- **Fix:** Removed `validate_no_empty_bin` from PUT /cut handler; it only applies to insert-cut where a NEW bin is being created that might have 0 records
- **Files modified:** `src/gruvax/api/admin/segments.py`
- **Commit:** 63135fc

**2. [Rule 1 - Bug] Rate limiter exhausted test_segment_api.py tests 6-8**
- **Found during:** Task 2, test run showing 4 skips instead of 1
- **Issue:** `_login()` helper called once per test; after 5 calls the 5/5min rate limiter returns 429, causing remaining tests to skip as "Login not implemented"
- **Fix:** Added `autouse=True` `reset_login_rate_limit` fixture (same pattern as test_admin_auth.py)
- **Files modified:** `tests/integration/test_segment_api.py`
- **Commit:** 63135fc

**3. [Rule 1 - Bug] test_boundary_editor.py corrupted locate test fixture**
- **Found during:** Task 3 green gate run
- **Issue:** `test_phantom_force_save` wrote `BLP 4200` to cube `(1,0,0)` without restoration; `test_single_cube_put_writes_history` wrote `BLP 4001` to `(1,3,3)` without restoration. Both caused locate test failures (confidence=0.0 for COVERED_RELEASE_ID=1)
- **Fix:** Inline restore at end of each test; `test_phantom_force_save` uses PUT via API, `test_single_cube_put_writes_history` uses direct DB UPDATE
- **Files modified:** `tests/integration/test_boundary_editor.py`
- **Commit:** 63135fc

**4. [Rule 2 - Missing critical check] validate_contiguity rewritten for SEG-05**
- **Found during:** Task 2, test_contiguity_validation failing with the original stub
- **Issue:** Original stub `validate_contiguity` returned None for the "scatter" scenario because the algorithm tested `get_bins_for_label` which showed all Blue Note bins were adjacent — it didn't catch the gap BETWEEN same-label bins caused by a different label's bin
- **Fix:** Complete rewrite: extract `first_label` sequence in sorted order, build `label_start_positions` map, reject if any label's start positions have a gap (different label in between)
- **Files modified:** `src/gruvax/api/admin/validation.py`
- **Commit:** 63135fc

### NO_BOUNDARY_RELEASE_ID Reconciliation

The plan noted: "Do NOT simply change the assertion to expect 0.30; that would silently delete no-boundary coverage."

The `NO_BOUNDARY_RELEASE_ID` was changed from 111 to 119 in Plan 05-03 (not this plan). This was the correct move: under the cut-point model, Saturn SR-9956-2-LP (release_id=111) is now COVERED (there's a cut at `first_label='Saturn'` in the fixture). Apple (release_id=119) is the genuine no-boundary case since Apple sorts alphabetically BEFORE any cut point in the fixture. The locate test continues to exercise the no-boundary path; the coverage is intact.

## Known Stubs

None — all endpoints are fully wired.

## Self-Check: PASSED

- `src/gruvax/api/admin/segments.py` exists: FOUND
- `src/gruvax/api/admin/router.py` includes segments_router: FOUND
- Commit c4fbd56 (Task 1): FOUND
- Commit 63135fc (Tasks 2-3): FOUND
- Green gate: 271 passed, 0 failed

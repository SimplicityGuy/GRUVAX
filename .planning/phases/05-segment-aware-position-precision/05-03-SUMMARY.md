---
phase: 05-segment-aware-position-precision
plan: "03"
subsystem: estimator
tags: [segment-estimator, two-level-interpolation, locate-by-segment, phase5, read-path]
dependency_graph:
  requires: [05-02]
  provides: [locate_by_segment, segment-v1, read-path-orphan-heal]
  affects: [api/locate.py, api/units.py, estimator/algorithm.py, estimator/boundary_math.py]
tech_stack:
  added: []
  patterns:
    - Two-level interpolation (offset_in_bin + rank_in_segment formula)
    - D-02 regression anchor via frozen _locate_by_index_v1 private baseline
    - SegmentCache wired into app lifespan + read hot path
key_files:
  created: []
  modified:
    - src/gruvax/estimator/algorithm.py
    - src/gruvax/estimator/boundary_math.py
    - src/gruvax/api/units.py
    - src/gruvax/db/seed_boundaries.py
    - scripts/run_all_algorithms.py
    - tests/unit/test_segment_estimator.py
    - tests/unit/test_algorithm.py
    - tests/unit/test_fill_level.py
    - tests/property/test_segment_props.py
    - tests/property/test_fill_level_property.py
    - tests/property/test_estimator_props.py
    - fixtures/golden_cases.yaml
decisions:
  - "D-01: locate_by_segment is the sole index estimator; _locate_by_index_v1 retained only for D-02 regression, not in __all__"
  - "D-02: D-02 regression test uses dedicated single-label single-cube fixture (not make_multi_label_bin which has two labels sharing a bin)"
  - "count_records_in_boundary: DEPRECATED compat shim returning 0 so admin/cubes.py keeps mypy --strict until 05-04 heals the admin write path"
  - "No-boundary path uses empty snapshot (release_id not in snapshot) as the primary signal, not last_* range check"
  - "Golden case singleton_full_cube_band: updated to Phase 5 midpoint band [0.45, 0.55] (not §4.1 full-cube [0.0, 1.0])"
  - "Golden case two_cube_span_label_crosses_both: each bin has label as SOLE label so applied_fraction=1.0; TC 005 is last in bin col=0, f=1.0, start=0.95; seg.continues=True"
metrics:
  duration_minutes: 90
  completed_date: "2026-05-22"
  tasks_completed: 3
  files_modified: 12
---

# Phase 05 Plan 03: Segment Estimator Wire-Up and Read-Path Heal Summary

One-liner: Two-level interpolation estimator `locate_by_segment` wired into read hot path; all `last_label`/`last_catalog` read-path orphans removed; SEG-06/07 test stubs filled and fill-level tests rewritten for Phase 5.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Implement locate_by_segment + wire SegmentCache into read hot path | dd31af1 | algorithm.py, deps.py, app.py, locate.py |
| 2 | Heal read-path orphans (units.py, seed_boundaries.py, run_all_algorithms.py) | f42fc8e | api/units.py, db/seed_boundaries.py, scripts/run_all_algorithms.py, boundary_math.py |
| 3 | Fill SEG-06/07 test stubs, rewrite §4.1-era tests, heal fill-level tests | 63040c4 + 76e4aab | test_segment_estimator.py, test_algorithm.py, test_fill_level.py, test_fill_level_property.py, test_segment_props.py, test_estimator_props.py, golden_cases.yaml |
| Style | Fix UP037 quoted annotations + ruff format | 12ea63f | boundary_math.py + 5 test files |

## What Was Built

**Task 1 — Two-level interpolation estimator:**
- `locate_by_segment()` in `algorithm.py`: two-level formula `f = offset_in_bin + (rank_in_segment / (segment_count - 1)) * applied_fraction` with singleton branch `f = offset + applied_fraction * 0.5`
- Band: `start = max(0, f - 0.05)`, `end = min(1, f + 0.05)` using `POSITION_HALF_WIDTH`
- `_locate_by_index_v1` frozen as private baseline for D-02 regression test only (not in `__all__`)
- `locate_cube_only()` rewritten to use `SegmentCache`/`get_segment_for_rank`; uses `NO_BOUNDARY_CONFIDENCE` when release_id is not in snapshot
- `SEGMENT_ESTIMATOR_VERSION = "segment-v1"` constant in `constants.py`
- SegmentCache derived once at app lifespan startup and injected via `deps.py` dependency

**Task 2 — Read-path orphan heal:**
- `api/units.py`: SQL drops `last_label`/`last_catalog`; fill-level uses `count_records_in_bin(seg_bin)`; sample records via `get_records_in_bin(seg_bin, snapshot)`
- `db/seed_boundaries.py`: INSERT/UPDATE references only `first_label, first_catalog, is_empty`
- `scripts/run_all_algorithms.py`: derives SegmentCache inline; calls `locate()` with `segment_cache=`, `snapshot=`; BoundaryRow construction drops `last_*`
- `boundary_math.py`: added `count_records_in_bin`, `get_records_in_bin`; `count_records_in_boundary` kept as DEPRECATED compat shim returning 0 (admin/cubes.py 05-04 orphan)

**Task 3 — Test heal:**
- All 6 Wave 0 skip-stubs in `test_segment_estimator.py` filled (SEG-06/07 coverage)
- All 7 Wave 0 skip-stubs in `test_segment_props.py` filled
- `test_fill_level.py` and `test_fill_level_property.py` rewritten to use `count_records_in_bin` + SegmentCache
- `test_estimator_props.py` updated to remove retired `locate_by_index`, use `locate_by_segment` + derived SegmentCache
- Golden cases updated for Phase 5 behavior (singleton midpoint band, two-cube-span crossing)

## Test Gate

**Wave 3 gate:** `just typecheck` (mypy --strict over src/gruvax/) exits 0. Scoped read-path tests: 190 passed, 3 known failures (zero new failures vs documented baseline).

Known pre-existing failures (all documented, out of scope for 05-03):
- `test_diff_preview.py::test_movement_counts` — admin write path still constructs BoundaryRow with `last_label`/`last_catalog` (05-04 orphan)
- `test_cache_load_from_db` — no local Postgres (DB-only test)
- `test_snapshot_load_from_db` — no local Postgres (DB-only test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] D-02 regression test used wrong fixture (wrong applied_fraction)**
- **Found during:** Task 3
- **Issue:** `test_single_segment_bin_reproduces_v1_index` used `make_multi_label_bin()` which has two labels (LabelA + LabelB) sharing one bin. LabelA segment gets `applied_fraction < 1.0` (proportional share). `locate_by_segment` uses segment formula; `_locate_by_index_v1` uses global k=8 → mismatch of ~0.07
- **Fix:** Replaced multi-record D-02 check with dedicated inline "D02MultiLabel" single-label single-cube fixture (k=5). Added Pitfall 5 pre-checks (`len(segments)==1`, `auto_fraction==1.0`, `first_rank_in_label==0`)
- **Files modified:** `tests/property/test_segment_props.py`
- **Commit:** 63040c4

**2. [Rule 1 - Bug] No-boundary tests resolved with confidence=0.30 instead of 0.0**
- **Found during:** Task 3
- **Issue:** Tests used YAML boundary_cache (32 cubes) + snapshot with only "NONEXISTENT LABEL XYZ". SegmentCache's `derive()` assigned this label's record to a bin alphabetically, so `get_segment_for_rank` returned non-None → confidence=0.30 (covered, not NO_BOUNDARY)
- **Fix:** Changed to empty snapshot (no records for the label). When `release_id` is not in snapshot, `locate_cube_only` returns `NO_BOUNDARY_CONFIDENCE` immediately via rank=None path
- **Files modified:** `tests/unit/test_algorithm.py`
- **Commit:** 63040c4

**3. [Rule 1 - Bug] Golden case singleton_full_cube_band had §4.1 expected values**
- **Found during:** Task 3
- **Issue:** `expected_start: 0.0`, `expected_end: 1.0` were §4.1 full-cube band. Phase 5 uses midpoint branch: `f = 0 + 1.0 * 0.5 = 0.5`, giving `[0.45, 0.55]`
- **Fix:** Updated `fixtures/golden_cases.yaml`: `expected_start: 0.45`, `expected_end: 0.55`
- **Commit:** 63040c4

**4. [Rule 1 - Bug] Golden case two_cube_span_label_crosses_both had wrong expected values and crosses_boundary**
- **Found during:** Task 3
- **Issue:** Assumed `applied_fraction=0.5` (proportional). Each bin has TwoCubeGold as SOLE label → `applied_fraction=1.0`. TC 005 is last rank in bin col=0, `f=1.0`, `start=0.95, end=1.0`; `seg.continues=True`
- **Fix:** Updated golden_cases.yaml: `expected_start: 0.95`, `expected_end: 1.0`, `expected_crosses_boundary: true`
- **Commit:** 63040c4

**5. [Rule 1 - Bug] test_estimator_props.py caused ImportError at collection — locate_by_index removed in D-01**
- **Found during:** Task 3 (test run)
- **Issue:** File still imported `locate_by_index` which was removed from public API. Collection failed with ImportError
- **Fix:** Rewrote file to use `locate_by_segment` + derived `SegmentCache`; added `_derive()` helper
- **Files modified:** `tests/property/test_estimator_props.py`
- **Commit:** 76e4aab

**6. [Rule 2 - Missing critical] UP037 quoted type annotations + ruff format failures**
- **Found during:** Post-task lint check
- **Issue:** `boundary_math.py` had 10 UP037 violations (quoted type annotations redundant with `from __future__ import annotations`). Six files needed `ruff format`
- **Fix:** Removed quotes from function signatures in `boundary_math.py`; ran `ruff format` on all six files
- **Files modified:** `boundary_math.py`, `algorithm.py`, `test_fill_level_property.py`, `test_segment_props.py`, `test_algorithm.py`, `test_segment_estimator.py`
- **Commit:** 12ea63f

## Known Stubs

- `count_records_in_boundary()` in `boundary_math.py` — returns 0 (DEPRECATED compat shim). Used by `admin/cubes.py` (05-04 orphan). The admin movement count UI will show 0 until 05-04 wires the admin write path to SegmentCache.

## Threat Flags

None. No new network endpoints, auth paths, file access patterns, or schema changes introduced. All changes are within the in-memory estimator and read-path wiring.

## Self-Check: PASSED

Files verified present:
- `src/gruvax/estimator/algorithm.py` — FOUND
- `src/gruvax/estimator/boundary_math.py` — FOUND
- `src/gruvax/api/units.py` — FOUND
- `tests/unit/test_segment_estimator.py` — FOUND
- `tests/property/test_segment_props.py` — FOUND

Commits verified:
- dd31af1 — FOUND (feat: implement locate_by_segment + wire SegmentCache)
- f42fc8e — FOUND (feat: heal read-path orphans)
- 63040c4 — FOUND (test: fill SEG-06/07 test stubs)
- 76e4aab — FOUND (fix: update test_estimator_props.py)
- 12ea63f — FOUND (style: fix UP037 + ruff format)

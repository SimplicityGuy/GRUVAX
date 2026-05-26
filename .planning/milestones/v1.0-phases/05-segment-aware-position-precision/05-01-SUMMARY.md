---
phase: 05-segment-aware-position-precision
plan: "01"
subsystem: estimator-foundation
tags: [migration, boundary-cache, segment-overrides, wave-0-stubs, tdd]
dependency_graph:
  requires: []
  provides:
    - migration-0005-cut-point-model
    - boundary-cache-overrides-map
    - segment-estimator-version-constant
    - synth-collection-factories
    - wave-0-test-scaffolds
  affects:
    - plans/05-02
    - plans/05-03
    - plans/05-04
tech_stack:
  added:
    - segment_overrides table (gruvax schema)
  patterns:
    - Alembic NOT VALID constraint for downgrade safety
    - TDD RED/GREEN commit sequence
    - Wave 0 skip-stub pattern for Nyquist compliance
key_files:
  created:
    - migrations/versions/0005_segment_model.py
    - tests/integration/test_migrate_0005.py
    - tests/unit/test_boundary_cache_refactor.py
    - tests/unit/test_segment_cache.py
    - tests/unit/test_segment_estimator.py
    - tests/property/test_segment_props.py
    - tests/integration/test_segment_api.py
  modified:
    - src/gruvax/estimator/boundary_cache.py
    - src/gruvax/estimator/constants.py
    - fixtures/boundaries.yaml
    - fixtures/synth_collection.py
    - tests/conftest.py
decisions:
  - "D-05 implemented: cube_boundaries stores only first_label/first_catalog (cut point); last_* derived by SegmentCache, not stored"
  - "NOT VALID constraint in downgrade allows re-adding empty_or_complete CHECK without scanning rows that lost last_* data post-upgrade"
  - "Migration round-trip uses downgrade -1 (not base) because migration 0001 has pre-existing pg_trgm/schema dependency that prevents full base downgrade"
  - "BoundaryCache._load_overrides() is a test seam — production load populates from DB; tests inject synthetic overrides"
  - "SEGMENT_ESTIMATOR_VERSION='segment-v1' placed in constants.py, not boundary_cache.py, to avoid circular imports when estimator modules reference it"
metrics:
  duration_minutes: ~35
  completed_date: "2026-05-22"
  tasks_completed: 3
  tasks_total: 3
  files_created: 7
  files_modified: 5
---

# Phase 05 Plan 01: Segment Model Foundation Summary

One-liner: Alembic migration 0005 drops last_label/last_catalog from cube_boundaries, creates segment_overrides table, and refactors BoundaryCache + BoundaryRow to the cut-point model with Wave 0 test scaffolds for all downstream plans.

## Tasks Completed

| # | Name | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Migration 0005 + round-trip test | `63fd87c` | migrations/versions/0005_segment_model.py, tests/integration/test_migrate_0005.py |
| 2 | BoundaryRow refactor (TDD RED+GREEN) | `8ace7f1` (RED), `5899983` (GREEN) | boundary_cache.py, constants.py, boundaries.yaml, synth_collection.py, conftest.py |
| 3 | Wave 0 test stubs | `931931a` | test_segment_cache.py, test_segment_estimator.py, test_segment_props.py, test_segment_api.py |

## What Was Built

**Task 1 — Migration 0005 (SEG-01)**

`migrations/versions/0005_segment_model.py` upgrades the schema:
- Drops `last_label` and `last_catalog` from `gruvax.cube_boundaries`
- Replaces the `empty_or_complete` CHECK constraint with `cut_point_complete` (requires `first_label` + `first_catalog` together when either is set)
- Extends `gruvax.boundary_history.source` CHECK to include `'cut_insert'`
- Creates `gruvax.segment_overrides(unit_id, row, col, label, fraction)` with `CHECK (fraction > 0.0 AND fraction <= 1.0)` and a composite PK

Downgrade reverses in safe order: restores `last_label`/`last_catalog` columns first, then re-adds the original `empty_or_complete` CHECK as `NOT VALID` (so existing rows without `last_*` data do not violate the constraint), then drops `segment_overrides`.

`tests/integration/test_migrate_0005.py` provides 9 integration tests:
- `segment_overrides` table and all expected columns exist
- `last_label`/`last_catalog` columns are absent
- `fraction` CHECK rejects `> 1.0` and `0.0`, accepts `1.0`
- `boundary_history.source` accepts `'cut_insert'`, rejects unknown values
- Round-trip: `downgrade -1` then `upgrade head` exits 0

**Task 2 — BoundaryRow refactor (TDD)**

RED commit (`8ace7f1`): 15 failing tests assert the desired shape before implementation.

GREEN commit (`5899983`):
- `BoundaryRow` dataclass: `last_label` and `last_catalog` fields removed; shape is now `(unit_id, row, col, first_label, first_catalog, is_empty)`
- `BoundaryCache.__init__`: `self._overrides: dict[tuple[int, int, int, str], float] = {}` added
- `BoundaryCache.load()`: SQL simplified to SELECT only cut-point columns; second SELECT populates `_overrides` from `segment_overrides`
- `BoundaryCache._load_overrides(overrides)`: test seam method for injecting synthetic overrides in unit tests
- `BoundaryCache.overrides` property exposing `_overrides`
- `BoundaryCache.invalidate()`: extended to reset `_overrides = {}`
- `constants.py`: `SEGMENT_ESTIMATOR_VERSION: str = "segment-v1"` added
- `fixtures/boundaries.yaml`: all 32 cube entries stripped of `last_label`/`last_catalog` keys
- `fixtures/synth_collection.py`: `_build_cache()` no longer takes `last_cat`; new `make_multi_label_bin()` (LabelA k=8, LabelB k=6 with duplicates) and `make_straddle()` (LabelS k=12 across two adjacent bins) factories added
- `tests/conftest.py`: `boundary_cache` fixture loader filters stale `last_*` keys from YAML

All 15 TDD RED tests pass GREEN. Full suite: 249 collected, 0 errors.

**Task 3 — Wave 0 test scaffolds**

Four files created with all skip-decorated tests for downstream plans. 28 tests collected, 0 errors:

| File | Tests | Coverage |
|------|-------|----------|
| tests/unit/test_segment_cache.py | 6 | SEG-02, SEG-03, SEG-04, SEG-05 |
| tests/unit/test_segment_estimator.py | 6 | SEG-06, SEG-07 |
| tests/property/test_segment_props.py | 7 | SEG-04, SEG-06, SEG-07 (D-02 Hypothesis invariants) |
| tests/integration/test_segment_api.py | 9 | SEG-08 admin API |

`test_single_segment_bin_reproduces_v1_index` includes the Pitfall 5 pre-check comment block (three mandatory assertions before the estimator equality assertion) per D-02.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Downgrade column-before-constraint ordering**
- **Found during:** Task 1 migration testing
- **Issue:** Original downgrade code added the `empty_or_complete` CHECK constraint before adding the `last_label`/`last_catalog` columns; Postgres rejected the constraint because the columns did not yet exist
- **Fix:** Reordered downgrade to `ADD COLUMN IF NOT EXISTS` for both columns first, then add the CHECK
- **Files modified:** migrations/versions/0005_segment_model.py
- **Commit:** 63fd87c

**2. [Rule 1 - Bug] Downgrade CHECK constraint violated by existing rows**
- **Found during:** Task 1 migration testing (second downgrade attempt)
- **Issue:** After a successful upgrade removes `last_*` data, downgrade re-adds the `empty_or_complete` CHECK (which requires non-null `last_label`/`last_catalog` for non-empty rows) and Postgres scanned existing rows — all of which had `NULL` in the newly-added columns — and rejected the constraint
- **Fix:** Added `NOT VALID` to the restored CHECK so Postgres skips the row scan and the constraint only gates future inserts/updates
- **Files modified:** migrations/versions/0005_segment_model.py
- **Commit:** 63fd87c

**3. [Rule 3 - Blocker] Migration env vars not available in worktree**
- **Found during:** Task 1 migration round-trip test
- **Issue:** `pydantic-settings` required `DATABASE_URL` and `SESSION_SECRET` env vars; `.env` was not accessible in the worktree
- **Fix:** Symlinked `/Users/Robert/Code/public/GRUVAX/.env` into the worktree; integration tests pass env vars explicitly in subprocess invocations
- **Files modified:** (symlink only, not committed)
- **Commit:** N/A (operational fix)

**4. [Rule 3 - Blocker] `downgrade base` fails at migration 0001**
- **Found during:** Task 1 round-trip design
- **Issue:** Migration 0001 downgrade cannot drop the `gruvax` schema because `pg_trgm` extension depends on it — pre-existing issue unrelated to this plan
- **Fix:** Integration test uses `downgrade -1` (to 0004 state) then `upgrade head`, proving the 0005-specific round-trip without hitting the 0001 regression
- **Files modified:** tests/integration/test_migrate_0005.py
- **Commit:** 63fd87c

### Out-of-Scope Discoveries (Deferred)

Multiple call sites in `api/admin/cubes.py`, `api/units.py`, `estimator/algorithm.py`, `boundary_math.py`, `db/queries.py`, and existing test fixtures still pass `last_label`/`last_catalog` to `BoundaryRow()`. These cause runtime `TypeError` when those code paths execute but do NOT cause collection errors (pytest can collect them). These are Plan 05-02 and 05-03 scope per the original plan design and were not touched. Noted in deferred-items.

## Known Stubs

The Wave 0 test stubs in Task 3 are intentional scaffolds — skip-decorated until Plans 05-02/03/04 implement the production code. They are not functional stubs that block the plan goal; they ARE the plan goal (Nyquist compliance for downstream plans).

## Threat Flags

None. This plan creates no new network endpoints, auth paths, or cross-boundary data flows. The `segment_overrides` table is admin-only, gated by `require_admin` (added in Plan 05-04). The `fraction CHECK (fraction > 0.0 AND fraction <= 1.0)` at the DB storage layer is the V5 security control referenced in the plan's threat model.

## TDD Gate Compliance

Task 2 followed the RED/GREEN cycle:
1. RED commit `8ace7f1`: `test(05-01): add failing TDD RED tests for BoundaryRow refactor + overrides + constants` — 15 tests collected, all failing (ImportError on SEGMENT_ESTIMATOR_VERSION, AttributeError on last_label, missing factory functions)
2. GREEN commit `5899983`: `feat(05-01): Refactor BoundaryRow + BoundaryCache; add SEGMENT_ESTIMATOR_VERSION; update fixtures` — all 15 tests pass

Both gate commits verified in git log.

## Self-Check: PASSED

Files exist:
- `migrations/versions/0005_segment_model.py` — FOUND
- `tests/integration/test_migrate_0005.py` — FOUND
- `tests/unit/test_boundary_cache_refactor.py` — FOUND
- `src/gruvax/estimator/boundary_cache.py` — FOUND (modified)
- `src/gruvax/estimator/constants.py` — FOUND (modified)
- `fixtures/boundaries.yaml` — FOUND (modified)
- `fixtures/synth_collection.py` — FOUND (modified)
- `tests/unit/test_segment_cache.py` — FOUND
- `tests/unit/test_segment_estimator.py` — FOUND
- `tests/property/test_segment_props.py` — FOUND
- `tests/integration/test_segment_api.py` — FOUND

Commits verified in git log:
- `63fd87c` feat(05-01): Migration 0005 — cut-point model + segment_overrides + round-trip test — FOUND
- `8ace7f1` test(05-01): add failing TDD RED tests for BoundaryRow refactor + overrides + constants — FOUND
- `5899983` feat(05-01): Refactor BoundaryRow + BoundaryCache; add SEGMENT_ESTIMATOR_VERSION; update fixtures — FOUND
- `931931a` test(05-01): add Wave 0 skip-stubbed test scaffolds for Plans 05-02/03/04 — FOUND

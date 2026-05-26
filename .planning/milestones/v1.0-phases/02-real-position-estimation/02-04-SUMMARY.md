---
phase: 02-real-position-estimation
plan: "04"
subsystem: testing
tags: [estimator, a-b-harness, position, mae, synthetic, pytest, hypothesis, pyyaml]

# Dependency graph
requires:
  - phase: 02-real-position-estimation
    plan: "01"
    provides: "locate/locate_cube_only estimators + all_shapes() planted-truth factories in fixtures/synth_collection.py"

provides:
  - "scripts/run_all_algorithms.py: standalone CLI + run_all_algorithms() function emitting per-shape MAE/p95/confidence for §4.1 vs §4.8"
  - "scripts/__init__.py: package init making scripts/ importable by pytest"
  - "tests/integration/test_run_all_algorithms.py: CI assertion that §4.1 MAE <= §4.8 MAE on every synthetic shape"
  - "Proof (D-07/D-08): §4.1 >= §4.8 on all 4 planted-truth shapes (uniform_dense, sparse_gappy, multi_prefix, singleton)"

affects:
  - "02-03: confidence calibration plan — MAE baseline data now available per shape"
  - "future: any algorithm comparison uses this harness pattern"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A/B harness pattern: run_all_algorithms(ci=True) returns per-shape dict consumed by both CLI print and CI tests"
    - "Standalone-script sys.path shim: _REPO_ROOT = Path(__file__).resolve().parent.parent; sys.path.insert(0, str(_REPO_ROOT)) before any fixtures.* imports"
    - "§4.8 null interval scored as 0.5 worst-case (CUBE_ONLY_NULL_MIDPOINT)"
    - "session-scoped pytest fixture runs harness once; all test functions consume shared result"
    - "scripts/__init__.py + pythonpath=[.] strategy: consistent with Plan 02-01 fixtures pattern"

key-files:
  created:
    - scripts/__init__.py
    - scripts/run_all_algorithms.py
    - tests/integration/test_run_all_algorithms.py
  modified: []

key-decisions:
  - "CUBE_ONLY_NULL_MIDPOINT=0.5: §4.8 null sub_cube_interval scored as midpoint of cube — consistent with plan spec and worst-case analysis"
  - "session-scoped harness_results fixture: run_all_algorithms(ci=True) called once per pytest session; all 4 test functions share the result (performance + determinism)"
  - "_by_label internal attribute used to derive label name for _score_shape() — acceptable dev-tool access since harness is not in the request path"

patterns-established:
  - "A/B harness pattern: produce per-shape {index, cube_only} {mae, p95_ms, confidence_mean} dict; CLI prints; CI tests assert"
  - "Standalone-script import shim: insert repo root onto sys.path before any repo-package imports when sys.path[0] is scripts/"

requirements-completed: [POS-06]

# Metrics
duration: 5min
completed: 2026-05-20
---

# Phase 02 Plan 04: Developer A/B Harness (POS-06) Summary

**§4.1 index-based estimator proven >= §4.8 cube-only on all 4 synthetic planted-truth shapes via run_all_algorithms.py CLI and CI assertion test; aggregate p95 compute 0.04 ms (well within 50 ms POS-03 budget)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-05-20T19:58:54Z
- **Completed:** 2026-05-20T20:04:21Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `scripts/run_all_algorithms.py`: standalone CLI (argparse `--ci`) + `run_all_algorithms(ci=True)` function; imports `all_shapes()` from Plan 02-01; runs both `locate()` (§4.1) and `locate_cube_only()` (§4.8) against every planted-truth release; computes per-shape MAE/p95/confidence; includes local CSV path guarded by `--ci` and `.exists()` check
- `scripts/__init__.py`: empty package init enabling `from scripts.run_all_algorithms import run_all_algorithms` in pytest (via `pythonpath=["."]`)
- `tests/integration/test_run_all_algorithms.py`: 4 CI tests — shapes present, §4.1 MAE <= §4.8 MAE per shape (D-07/D-08), aggregate p95 < 50 ms (POS-03), local CSV never read in CI mode
- Per-shape §4.1 vs §4.8 results (D-07/D-08 proven):

| Shape | §4.1 MAE | §4.8 MAE | Result |
|-------|----------|----------|--------|
| uniform_dense | 0.0025 | 0.2632 | §4.1 < §4.8 PASS |
| sparse_gappy  | 0.0907 | 0.2588 | §4.1 < §4.8 PASS |
| multi_prefix  | 0.0083 | 0.3000 | §4.1 < §4.8 PASS |
| singleton     | 0.0000 | 0.0000 | §4.1 = §4.8 PASS |

## Task Commits

Each task was committed atomically:

1. **Task 1: A/B harness CLI + scripts/__init__.py** - `eaff5bf` (feat)
2. **Task 2: CI assertion test** - `6e6e356` (test)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `/Users/Robert/Code/public/GRUVAX/scripts/__init__.py` - Empty package init; makes scripts/ importable by pytest
- `/Users/Robert/Code/public/GRUVAX/scripts/run_all_algorithms.py` - Standalone CLI + run_all_algorithms() A/B harness function
- `/Users/Robert/Code/public/GRUVAX/tests/integration/test_run_all_algorithms.py` - 4 CI tests asserting §4.1 >= §4.8 invariant

## Decisions Made

- `CUBE_ONLY_NULL_MIDPOINT = 0.5`: §4.8 always returns null sub_cube_interval; scoring as midpoint-of-cube is the plan-specified worst-case (consistent with plan spec)
- session-scoped `harness_results` fixture: runs harness once per pytest session for performance and determinism; all test functions consume the shared dict
- `snapshot._by_label` used to derive label name in `_score_shape()` — acceptable for a dev-tooling script not in the request path

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pytest.approx arithmetic TypeError in assertion**
- **Found during:** Task 2 (CI assertion test)
- **Issue:** Initial test used `cube_mae + pytest.approx(0.0, abs=1e-9)` — TypeError: float + ApproxScalar is not supported
- **Fix:** Changed to `index_mae <= cube_mae + 1e-9` (plain float tolerance)
- **Files modified:** tests/integration/test_run_all_algorithms.py
- **Verification:** `uv run pytest tests/integration/test_run_all_algorithms.py -x -q` exits 0 with 4 passed
- **Committed in:** 6e6e356 (Task 2 commit)

**2. [Rule 1 - Bug] snapshot._records AttributeError — internal attribute is _by_label**
- **Found during:** Task 1 (initial harness run)
- **Issue:** Used `snapshot._records` to derive label name; actual attribute is `snapshot._by_label` per collection_snapshot.py
- **Fix:** Changed to `snapshot._by_label`
- **Files modified:** scripts/run_all_algorithms.py
- **Verification:** `uv run python scripts/run_all_algorithms.py --ci` exits 0
- **Committed in:** eaff5bf (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs — internal API mismatch and pytest API misuse)
**Impact on plan:** Both bugs found and fixed within their respective tasks. No scope creep. Core algorithm behavior and MAE results unchanged.

## Issues Encountered

None — both bugs were found during task execution and fixed inline before task commit.

## User Setup Required

None — harness uses only synthetic in-memory data in CI mode; no external services, DB, or CSV required.

## Next Phase Readiness

- POS-06 complete: A/B harness exists and proves §4.1 >= §4.8 on all synthetic shapes
- MAE baseline data per shape now available for Plan 02-03 confidence calibration
- Phase 02 now has 4 of 4 plans complete (02-01 through 02-04)

## Self-Check: PASSED

---
*Phase: 02-real-position-estimation*
*Completed: 2026-05-20*

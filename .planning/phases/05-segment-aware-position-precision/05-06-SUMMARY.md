---
phase: 05-segment-aware-position-precision
plan: "06"
subsystem: admin-segment-api, admin-frontend
tags: [seg-05, contiguity, gap-closure, tdd, validation, live-write-paths]
dependency_graph:
  requires: [05-04-SUMMARY.md]
  provides: [SEG-05 enforced on live write paths, contiguity error surfaced in RecordPickerSheet]
  affects: [admin PUT /cut, admin POST /insert-cut, RecordPickerSheet, App routes]
tech_stack:
  added: []
  patterns:
    - build_proposed_cuts() helper — merges live BoundaryCache + one edit into validate_contiguity's input shape, unit-scoped
    - validate_contiguity() called pre-transaction on both direct write paths (Direction A — no re-routing through preview flow)
    - BulkSaveError catch branching in RecordPickerSheet.handleCommit — sheet stays open on rejection
key_files:
  created: []
  modified:
    - src/gruvax/api/admin/validation.py
    - src/gruvax/api/admin/segments.py
    - tests/integration/test_segment_api.py
    - frontend/src/routes/admin/RecordPickerSheet.tsx
    - frontend/src/App.tsx
  deleted:
    - frontend/src/routes/admin/DiffPreviewSheet.tsx
    - frontend/src/routes/admin/DiffPreviewSheet.test.tsx
    - frontend/src/routes/admin/RollbackToast.tsx
decisions:
  - "Direction A chosen for SEG-05 enforcement: add validate_contiguity to both live write paths before the DB transaction. Not Direction B (re-route through validate→preview→commit) because the owner explicitly accepted direct-save at 05-UAT.md test 5 — one validation call per path is far lower risk than re-wiring the two-step flow."
  - "build_proposed_cuts scoped to the target unit_id only. Cross-unit same-label distribution is legitimate (different physical shelves); contiguity is a per-unit shelf invariant."
  - "Cache-sync step added to the regression test: prior mutating integration tests (insert-cut) leave the in-app BoundaryCache stale after DB restore. A valid no-op PUT forces cache.invalidate()+load() before the scatter assertion."
  - "test_migrate_0005 failure is pre-existing (exists on base commit 0f88d7b, before any changes); tracked in deferred-items."
metrics:
  duration: "14 minutes"
  completed: "2026-05-23"
  tasks: 2
  files: 8
---

# Phase 05 Plan 06: SEG-05 Gap Closure — Enforce Contiguity on Live Write Paths Summary

SEG-05 label-contiguity enforced on PUT /cut and POST /insert-cut via pre-transaction validate_contiguity call; RecordPickerSheet surfaces the 400 plain-language error and stays open; orphaned DiffPreviewSheet removed.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 (RED) | Add failing integration test for scatter PUT /cut | b4da07a | tests/integration/test_segment_api.py |
| 1 (GREEN) | Enforce SEG-05 contiguity on PUT /cut and POST /insert-cut | 0379dc6 | src/gruvax/api/admin/validation.py, src/gruvax/api/admin/segments.py, tests/integration/test_segment_api.py |
| 2 | Surface contiguity 400 in RecordPickerSheet; remove orphaned preview route | c45789a | frontend/src/routes/admin/RecordPickerSheet.tsx, frontend/src/App.tsx, (deleted) DiffPreviewSheet.tsx, DiffPreviewSheet.test.tsx, RollbackToast.tsx |

## What Was Built

### Task 1: SEG-05 contiguity enforcement on live write paths

`build_proposed_cuts(cache, *, replace=None, cascade=None)` added to `validation.py`:
- Takes the live BoundaryCache + one proposed edit (replace for PUT /cut, cascade for POST /insert-cut)
- Returns the full proposed_updates list-of-dicts in the exact six-key shape validate_contiguity already consumes
- Scoped to the target unit_id only — cross-unit same-label distribution is legitimate (different physical shelves are never adjacent)

`put_bin_cut` in `segments.py`:
- Calls `build_proposed_cuts(cache, replace=(unit_id, row, col, first_label, first_catalog))` after the phantom check, before `async with pool.connection()`
- On contiguity violation: returns `JSONResponse(400, {"type":"contiguity_error","message":..., "unit_id","row","col"})` — NO DB write

`insert_cut` in `segments.py`:
- After cascade_cubes is built and after the empty-bin/overflow guards, calls `build_proposed_cuts(cache, cascade=cascade_cubes)` before the DB transaction
- On contiguity violation: returns `JSONResponse(400, {"type":"contiguity_error","message":...})` — NO DB write

Integration regression test `test_put_cut_scatter_rejected_contiguity_error`:
- Scatter scenario: unit 1 row 0 is [Blue Note, Blue Note, Creole, KC]. PUT (1,0,3) → Blue Note makes it [Blue Note, Blue Note, Creole, Blue Note] — Blue Note at positions 0,1,3 with Creole between 1 and 3.
- Asserts: 400 type=contiguity_error, message contains "split" or "non-adjacent", GET /admin/cubes confirms (1,0,3) still "KC" (no DB write)
- Includes cache-sync step to handle module-fixture isolation (prior insert-cut test leaves in-app cache stale after DB restore)

### Task 2: Frontend changes

**RecordPickerSheet.tsx**: `handleCommit` catch now branches on `BulkSaveError`:
- `if (err instanceof BulkSaveError)`: `setSaveError(err.serverMessage ?? err.message)` — sheet stays open, no onCommit/onCancel called
- Falls through to generic error message for non-BulkSaveError throws
- Comment documents that contiguity_error (SEG-05) and phantom_boundary share this 400 surfacing path

**App.tsx**: Removed `/admin/preview` route and `DiffPreviewSheet` import. The route table comment updated to remove the preview entry. All other routes (settings, cubes, history, etc.) unchanged.

**Deleted**: `DiffPreviewSheet.tsx`, `DiffPreviewSheet.test.tsx`, `RollbackToast.tsx` (RollbackToast was imported only by DiffPreviewSheet).

`HistoryView.tsx` and `revertChangeSet`/`getHistory` in adminClient unchanged. Dead DiffPreviewSheet CSS in admin.css left inert (consistent with prior CubeEditor CSS deletion accepted at VERIFICATION).

## Verification Results

### Backend gates
- `uv run pytest tests/integration/test_segment_api.py -q --tb=short` — 15 passed, 1 skipped
- `uv run pytest tests/unit/test_segment_cache.py::test_contiguity_validation -q` — 1 passed
- `uv run mypy --strict src/gruvax/` — Success: no issues found in 43 source files
- `uv run ruff check src/ tests/` — All checks passed
- `uv run ruff format --check src/ tests/` — 82 files already formatted

### Full backend suite (05-04 gate, excluding pre-existing migration failure)
- `uv run pytest tests/ --ignore=tests/integration/test_migrate_0005.py` — 267 passed, 9 skipped

### Frontend gates
- `tsc --noEmit` — clean (0 errors)
- `npm run lint` — 0 errors, 1 pre-existing warning in BinWidthEditor.tsx (not touched)
- `npm run build` — success (vite v8, 528 kB bundle)

### Grep gates
- `grep -v '^\s*#' segments.py | grep -c contiguity_error` — 7 (≥2 requirement met)
- `grep -c "DiffPreviewSheet" App.tsx` — 0
- `test ! -f frontend/src/routes/admin/DiffPreviewSheet.tsx` — DELETED

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] build_proposed_cuts initial implementation passed all-units boundary set**
- **Found during:** Task 1 GREEN — test_put_cut_accepted failed with "split creole across non-adjacent bins"
- **Issue:** The initial implementation returned ALL boundaries from the cache. Creole appears legitimately in both unit 1 (position 0,2) and unit 2 (position 1,2). The validator saw Creole "scattered" across non-adjacent positions across units.
- **Fix:** Scoped `build_proposed_cuts` to the target unit_id only. Contiguity is a per-unit shelf invariant; cross-unit same-label distribution is legitimate (different physical shelves are never adjacent).
- **Files modified:** src/gruvax/api/admin/validation.py
- **Commit:** 0379dc6

**2. [Rule 1 - Bug] Integration test needed cache-sync step for module isolation**
- **Found during:** Task 1 GREEN — scatter test passed alone but failed in full module run
- **Issue:** `test_insert_cut_cascade_preserves_bin_after_empty` restores the DB via `load_boundaries` in its finally block, but the in-app BoundaryCache (running in the module-scoped ASGI client) is NOT refreshed — it retains the post-cascade state. By the time the scatter test runs, the cache shows (1,0,3) as Creole (not KC), making the scatter test's "Blue Note → (1,0,3)" edit non-scattering.
- **Fix:** Added a load_boundaries + valid no-op PUT at (1,0,0) before the scatter assertion. The valid PUT triggers `cache.invalidate() + cache.load()` in the handler, syncing the in-app cache with the restored DB.
- **Files modified:** tests/integration/test_segment_api.py
- **Commit:** 0379dc6

### Pre-existing Issues (Out of Scope)

- `tests/integration/test_migrate_0005.py::test_0005_round_trip_down_up` fails on the base commit (0f88d7b) before any plan changes. The migration downgrade fails because the shared dev DB has `cut_insert` source rows in `boundary_history` from prior test runs, which violate the pre-0005 CHECK constraint. Tracked in deferred-items.

## Known Stubs

None — all data paths are wired. The contiguity validation reads from the live BoundaryCache and calls the existing validate_contiguity function. No mock or hardcoded values in the response path.

## Threat Flags

No new network endpoints or trust boundaries introduced. The contiguity check is pure in-memory (cache + SegmentCache), zero DB on the reject path (T-05-06-03 confirmed). The 400 response body contains only the label name already supplied by the admin — no PII (T-05-06-02 accepted).

## TDD Gate Compliance

- RED commit (b4da07a): `test(05-06): add RED test — scatter PUT /cut must return 400 contiguity_error` — test failed as expected (got 200, expected 400)
- GREEN commit (0379dc6): `feat(05-06): enforce SEG-05 contiguity on PUT /cut and POST /insert-cut (Direction A)` — test passed after implementation

## Self-Check: PASSED

Files verified:
- FOUND: src/gruvax/api/admin/validation.py — contains `def build_proposed_cuts`
- FOUND: src/gruvax/api/admin/segments.py — contains `contiguity_error` (7 occurrences, ≥2 required)
- FOUND: tests/integration/test_segment_api.py — contains `contiguity_error` (7 occurrences)
- FOUND: frontend/src/routes/admin/RecordPickerSheet.tsx — contains `contiguity` (BulkSaveError branch comment)
- FOUND: frontend/src/App.tsx — `DiffPreviewSheet` count = 0
- DELETED: frontend/src/routes/admin/DiffPreviewSheet.tsx
- DELETED: frontend/src/routes/admin/DiffPreviewSheet.test.tsx
- DELETED: frontend/src/routes/admin/RollbackToast.tsx

Commits verified:
- b4da07a — test(05-06): add RED test
- 0379dc6 — feat(05-06): GREEN implementation
- c45789a — feat(05-06): frontend changes

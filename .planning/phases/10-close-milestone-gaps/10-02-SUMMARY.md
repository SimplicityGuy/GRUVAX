---
phase: 10-close-milestone-gaps
plan: "02"
subsystem: api/admin/history
tags: [int-b, segment-cache, event-bus, revert, boundary-changed, admn-09, rtm-01]
dependency_graph:
  requires: []
  provides:
    - revert_change_set re-derives SegmentCache post-commit
    - revert_change_set publishes boundary_changed SSE event
  affects:
    - src/gruvax/api/admin/history.py
    - tests/integration/test_change_set.py
tech_stack:
  added: []
  patterns:
    - post-commit SegmentCache re-derive (mirrors cubes.py:342-362)
    - gruvax.segment_overrides SELECT before derive() for multi-bin revert safety
    - SpyEventBus via dependency_overrides for integration test SSE assertions
key_files:
  created: []
  modified:
    - src/gruvax/api/admin/history.py
    - tests/integration/test_change_set.py
decisions:
  - Use GET /api/admin/cubes/1/0/1/segments (not /api/locate) for re-derive assertion
    to avoid locate's algorithm indirection and ensure direct SegmentCache state proof
  - Fresh app instance with load_boundaries() reseed for test_revert_rederives_segment_cache
    to prevent shared-dev-DB contamination from prior mutating tests
  - test_revert_publishes_boundary_changed uses a separate fresh client + SpyEventBus override
    rather than patching the module-scoped fixture, for test isolation
metrics:
  duration: "13 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 2
---

# Phase 10 Plan 02: INT-B Revert Re-Derive + Publish Summary

Closed INT-B: `revert_change_set` in `history.py` now re-derives `SegmentCache` and publishes `boundary_changed` after an undo, matching the canonical pattern from `cubes.py:342-362`.

## What Was Built

### Task 1 — RED tests (commit cc156cf)

Added two integration tests to `tests/integration/test_change_set.py`:

- **`test_revert_rederives_segment_cache`**: Uses a fresh app instance with `load_boundaries()` reseed (fixtures/boundaries.yaml) for deterministic state. Changes cube (1,0,1) from "Blue Note" to "Riverside" via bulk write, verifies SegmentCache changed (non-empty segments differ), reverts, then asserts `GET /api/admin/cubes/1/0/1/segments` returns the original "Blue Note" labels — proving SegmentCache was re-derived, not left stale.

- **`test_revert_publishes_boundary_changed`**: Uses a fresh app instance with `SpyEventBus` injected via `app.dependency_overrides[get_event_bus]`. Makes a bulk write to cube (2,0,1), clears spy, reverts, then asserts `spy.published` contains a `boundary_changed` event with `cube_ids=[{"unit": 2, "row": 0, "col": 1}]` (key `"unit"`, not `"unit_id"`) and the new revert `change_set_id`.

Both tests were **RED** against the unfixed `history.py` with the expected error messages:
- `test_revert_rederives_segment_cache`: `AssertionError: SegmentCache was NOT re-derived after revert`
- `test_revert_publishes_boundary_changed`: `AssertionError: spy.published is empty — INT-B: revert never calls bus.publish()`

### Task 2 — GREEN fix (commit 894834c)

Modified `src/gruvax/api/admin/history.py`:

1. **Added imports**: `get_collection_snapshot`, `get_event_bus`, `get_segment_cache` from `gruvax.api.deps`; `CollectionSnapshot` from `gruvax.estimator.collection_snapshot`; `SegmentCache` from `gruvax.estimator.segment_cache`; `EventBus` from `gruvax.events.bus`.

2. **Added three `Depends()` params** to `revert_change_set`: `segment_cache: SegmentCache = Depends(get_segment_cache)`, `snapshot: CollectionSnapshot = Depends(get_collection_snapshot)`, `bus: EventBus = Depends(get_event_bus)`.

3. **Replaced the 2-line post-commit cache reload** (lines 193-195) with the full pattern:
   ```python
   if reverted:
       cache.invalidate()
       try:
           await cache.load(pool)
           # Re-read ALL overrides from gruvax.segment_overrides
           overrides: dict[tuple[int, int, int, str], float] = {}
           async with pool.connection() as conn2, conn2.cursor() as cur2:
               await cur2.execute("SELECT unit_id, row, col, label, fraction FROM gruvax.segment_overrides")
               override_rows = await cur2.fetchall()
           for uid_o, r_o, c_o, lbl_o, frac_o in override_rows:
               overrides[(int(uid_o), int(r_o), int(c_o), str(lbl_o))] = float(frac_o)
           segment_cache.invalidate()
           segment_cache.derive(cache, snapshot, overrides)
       finally:
           await bus.publish("boundary_changed", {
               "cube_ids": [{"unit": r["unit_id"], "row": r["row"], "col": r["col"]} for r in reverted],
               "change_set_id": new_change_set_id,
           })
   ```

## Verification

All acceptance criteria met:

- `grep -c "get_segment_cache\|get_collection_snapshot\|get_event_bus" history.py` → 6 (>= 3)
- `grep -c "segment_cache.derive\|segment_cache.invalidate" history.py` → 2
- `gruvax.segment_overrides` SELECT present
- `bus.publish("boundary_changed"` with `cube_ids` list and `"unit"` key present
- Block gated on `if reverted:` and sits after `async with pool.connection() as conn, conn.transaction():` (Pitfall A)
- `uv run pytest tests/integration/test_change_set.py -x` → 7 passed (0 failed)
- `uv run pytest tests/` → 462 passed, 4 skipped, 0 failed
- `uv run mypy --strict src/gruvax/api/admin/history.py` → clean

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Revised test_revert_rederives_segment_cache to use segments endpoint**

- **Found during:** Task 2 GREEN verification
- **Issue:** The original test used `/api/locate` for Riverside release 136 to detect SegmentCache re-derive. After investigation: (a) the module fixture for `test_change_set.py` does not reseed boundaries, so the shared dev DB had polluted state where cube 2/0/0 was no longer "Riverside"; (b) the locate algorithm's fallback behavior meant changing cube 2/0/0 didn't change the `primary_cube` returned for Riverside (the algorithm found an equivalent bin). Both issues made the test unreliable on the shared dev DB.
- **Fix:** Changed `test_revert_rederives_segment_cache` to: (a) use a fresh app instance with `load_boundaries()` reseed for deterministic state; (b) assert via `GET /api/admin/cubes/1/0/1/segments` (direct SegmentCache state read) instead of `/api/locate` (indirect algorithm result). This is a stronger proof of SegmentCache re-derivation and immune to algorithm fallback behavior.
- **Files modified:** `tests/integration/test_change_set.py`
- **Commit:** 894834c

## Known Stubs

None. All logic is fully wired.

## Threat Flags

None. All new surface covered by plan's threat model (T-10-03, T-10-04).

## Self-Check: PASSED

- `src/gruvax/api/admin/history.py` exists: FOUND
- `tests/integration/test_change_set.py` exists: FOUND
- Task 1 commit cc156cf: FOUND
- Task 2 commit 894834c: FOUND

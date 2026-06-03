---
phase: 06-safe-boundaries-live-device-lifecycle
plan: 01
subsystem: backend-admin-writes
tags: [data-integrity, multi-profile, sse, security, profile-scoping]
dependency_graph:
  requires: []
  provides:
    - write_boundary with profile_id WHERE clause + rowcount return
    - fetch_current_boundary scoped by profile_id
    - get_write_target FastAPI dep returning (profile_id, per-profile EventBus)
    - All 6 admin boundary-write routes profile-scoped via get_write_target
    - signal_editing SSE fan-out scoped to resolved profile's bus
  affects:
    - src/gruvax/db/queries.py
    - src/gruvax/api/deps.py
    - src/gruvax/api/admin/cubes.py
    - src/gruvax/api/admin/segments.py
    - src/gruvax/api/admin/import_.py
    - src/gruvax/api/admin/history.py
    - src/gruvax/api/admin/editing.py
tech_stack:
  added: []
  patterns:
    - get_write_target FastAPI dependency (profile_id + per-profile EventBus in one dep)
    - profile_id = %s::uuid in WHERE clauses for cube_boundaries writes
    - rows_affected = 0 → 404 boundary_not_found (D-10 per-cube + D-11 bulk/transactional)
key_files:
  created:
    - tests/integration/test_06_01_profile_scoped_writes.py
    - tests/integration/test_06_01_write_callsite_scoping.py
  modified:
    - src/gruvax/db/queries.py
    - src/gruvax/api/deps.py
    - src/gruvax/api/admin/cubes.py
    - src/gruvax/api/admin/segments.py
    - src/gruvax/api/admin/import_.py
    - src/gruvax/api/admin/history.py
    - src/gruvax/api/admin/editing.py
decisions:
  - Profile-id defaults to None in write_boundary/fetch_current_boundary for backward compat (unscoped legacy path retained; admin routes always pass the resolved value)
  - get_write_target added after get_bus_for_profile — same registry-lookup pattern, no path-profile_id validation (write routes don't have profile_id in path unlike read routes)
  - set_bin_overrides in segments.py replaced get_event_bus with get_write_target even though it doesn't call write_boundary — plan acceptance criteria requires no Depends(get_event_bus) in any admin write file
  - Ruff auto-fixed 5 unused EventBus TYPE_CHECKING imports after the dep switch
metrics:
  duration_seconds: 1548
  completed_date: "2026-05-31"
  tasks_completed: 2
  files_modified: 7
  files_created: 2
requirements-completed: [DATA-01]
---

# Phase 6 Plan 01: Profile-Scoped Boundary Writes + Per-Profile SSE Fan-Out Summary

**One-liner:** Closed DATA-01 cross-profile corruption hole — `write_boundary` + `fetch_current_boundary` now scope to `WHERE profile_id = %s::uuid`, `get_write_target` dep replaces `get_event_bus` on all 6 write routes + signal_editing, and 0-row writes return loud 404 (transactional for bulk).

## Tasks Completed

| # | Task | Commit | Status |
|---|------|--------|--------|
| T1 | Scope write_boundary + fetch_current_boundary; add get_write_target dep | 36e7356 | Done |
| T2 | Scope all 6 write call sites + signal_editing; 0-row→404; transactional bulk abort | 0afb00c | Done |

## What Was Built

### Task 1 — queries.py + deps.py

**`write_boundary`** (queries.py:658):
- Added `profile_id: str | None = None` parameter (default None for backward compat)
- Added `WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s` branch when `profile_id` supplied
- Changed return type from `None` to `int` — returns `cur.rowcount` (enables D-10/D-11 0-row detection)
- Uses `async with conn.cursor()` so `rowcount` is readable after execute

**`fetch_current_boundary`** (queries.py:602):
- Added `profile_id: str | None = None` parameter
- Added scoped SQL branch: `WHERE profile_id = %s::uuid AND unit_id = ...`
- Unscoped fallback (legacy path) retained for non-write callers

**`get_write_target`** (deps.py — after `get_bus_for_profile`):
- Async FastAPI dependency: `get_write_target(request, pool) -> tuple[str, Any]`
- Calls `resolve_profile_from_request`, propagating 400/403 verbatim (D-02 — no default fallback)
- Looks up `event_bus_registry[str(profile_id)]`, raises 503 on missing registry, 404 on missing profile
- Returns `(profile_id, per_profile_bus)`

### Task 2 — 5 admin files

All 6 boundary-write routes + signal_editing now use `Depends(get_write_target)` instead of `Depends(get_event_bus)`. Summary of changes per file:

**cubes.py** (put_cube_boundary + bulk_write_cubes):
- Both routes: `_write_target: tuple[str, Any] = Depends(get_write_target)` replaces `bus: EventBus = Depends(get_event_bus)`
- Body unpacks: `profile_id, bus = _write_target`
- `fetch_current_boundary(..., profile_id=profile_id)`, `write_boundary(..., profile_id=profile_id)`
- 0-row check: `if rows_affected == 0: raise HTTPException(404, boundary_not_found)` (D-10)
- Bulk: 0-row check INSIDE `conn.transaction()` — raises abort whole change-set (D-11)
- `write_history_row(..., profile_id=profile_id)` — resolved profile, not DEFAULT_PROFILE_UUID
- `SELECT ... WHERE profile_id = %s::uuid ...` for fetching updated row after write

**segments.py** (put_bin_cut + set_bin_overrides + insert_cut):
- All 3 routes replaced `get_event_bus` with `get_write_target`
- put_bin_cut: `fetch_current_boundary` + `write_boundary` + `write_history_row` all scoped
- insert_cut: cascade loop — each `write_boundary` scoped, 0-row check in txn (D-11)
- set_bin_overrides: bus retarget only (no `write_boundary` call — segment_overrides write); `_profile_id, bus = _write_target`

**import_.py** (import_boundaries):
- `_write_target` dep replaces `get_event_bus`
- `profile_id, bus = _write_target` at function start
- `fetch_current_boundary` + `write_boundary` + `write_history_row` all scoped
- 0-row check INSIDE `conn.transaction()` (D-11 bulk abort)

**history.py** (revert_change_set):
- `_write_target` dep replaces `get_event_bus`
- `write_boundary` + `write_history_row` scoped to resolved profile
- 0-row check INSIDE `conn.transaction()` (D-11 transactional abort for bulk revert)

**editing.py** (signal_editing):
- `_write_target` dep replaces `get_event_bus` — bus retarget only (no DB write)
- `admin_editing` now fans out to per-profile bus only (D-04 — no cross-profile shimmer)

## Verification Results

### Acceptance Criteria

- write_boundary UPDATE WHERE: `profile_id = %s::uuid AND unit_id = %s ...` — PASS
- write_boundary returns `int` rowcount — PASS
- fetch_current_boundary SELECT WHERE scoped by `profile_id` — PASS
- get_write_target returns 2-tuple, looks up `event_bus_registry` — PASS
- Zero `Depends(get_event_bus)` in cubes/segments/import_/history/editing — PASS
- `Depends(get_write_target)` count across admin files: 8 (>= 7) — PASS
- `boundary_not_found` in all write paths — PASS
- All 6 `write_boundary` calls pass `profile_id=profile_id` — PASS

### Test Results

- Existing boundary/bulk/editing integration suites: **12/12 pass** (no regressions)
- Full sequential suite: **705 passed, 6 skipped** — PASS (no prior-phase regressions)
- TDD RED tests (06-01): committed at 75101be (queries), 038409b (call sites)
- TDD GREEN implementation: 36e7356 (Task 1), 0afb00c (Task 2)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Unused EventBus imports after dep switch**
- **Found during:** Task 2 implementation
- **Issue:** After replacing `get_event_bus` with `get_write_target`, the `TYPE_CHECKING` block `from gruvax.events.bus import EventBus` became unused in 5 admin files (the bus is now typed as `Any` from the tuple)
- **Fix:** `uv run ruff check --fix` auto-removed 8 unused imports across 5 files (cubes.py, segments.py, import_.py, history.py, editing.py)
- **Commit:** included in 0afb00c

**2. [Rule 2 - Missing Critical] set_bin_overrides had get_event_bus but no write_boundary**
- **Found during:** Task 2 — scanning all `get_event_bus` occurrences in segments.py
- **Issue:** `set_bin_overrides` is not one of the 6 `write_boundary` call sites, but it used `get_event_bus` for SSE fan-out. The plan's acceptance criteria requires zero `Depends(get_event_bus)` in any admin write file
- **Fix:** Replaced with `Depends(get_write_target)` — bus retarget only (no boundary write, no 0-row check needed)
- **Files modified:** segments.py
- **Commit:** 0afb00c

## Known Stubs

None — all scoping is fully wired to resolved `profile_id`; no placeholder values introduced.

## Threat Flags

None — this plan closes existing threat surface (T-06-01 through T-06-04) without introducing new endpoints or auth paths.

## Self-Check: PASSED

All 10 files exist on disk. All 4 commits verified in git log.

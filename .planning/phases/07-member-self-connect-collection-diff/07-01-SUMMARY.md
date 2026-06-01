---
phase: 07-member-self-connect-collection-diff
plan: 01
subsystem: api
tags: [postgres, alembic, migration, fastapi, sse, profile-sync, diff-count]

# Dependency graph
requires:
  - phase: 06-safe-boundaries-live-device-lifecycle
    provides: write_boundary profile-scoping, device SSE lifecycle — foundation for per-profile diff state
  - phase: v2.0-p1-walking-skeleton
    provides: staging-swap sync (_swap_inside_tx), profile_collection cache, SSE event bus

provides:
  - migration 0012 with profile_invite_codes table, first_seen_at column, and profile diff columns
  - collection-diff computation (new_record_count, is_initial_import) atomic inside swap transaction
  - extended collection_changed SSE payload with new_record_count + is_initial_import
  - has_token boolean derivation on admin profiles API (no ciphertext leak)
  - last_new_record_count + last_sync_is_initial on GET /api/admin/profiles + GET /api/admin/profiles/{id}
  - last_new_record_count + last_sync_is_initial on GET /api/admin/diagnostics
  - Wave-0 test scaffolds for AUTH-02 (xfail pending Plan 02) and API-04 (green)

affects:
  - 07-02 (invite_codes.py endpoint — needs profile_invite_codes table from migration 0012)
  - 07-03 (frontend — consumes has_token + diff fields from admin profiles API)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pre-DELETE COUNT(*) in swap TX for retry-safe arrival count (Pitfall 9 / D-06)"
    - "Read last_sync_at IS NULL BEFORE UPDATE for is_initial_import detection (Pitfall 4 / D-07)"
    - "has_token derived in SQL as (app_token_encrypted IS NOT NULL AND length > 1)::bool (T-07-01 / Pitfall 7)"
    - "Diff state stored atomically in profiles UPDATE inside the swap transaction (T-07-02 / D-08)"

key-files:
  created:
    - migrations/versions/0012_invite_codes_and_first_seen_at.py
    - tests/integration/test_invite_codes.py
    - tests/unit/test_profile_sync_diff.py
    - tests/unit/test_fake_discogsography.py
  modified:
    - src/gruvax/sync/profile_sync.py
    - src/gruvax/api/admin/profiles.py
    - src/gruvax/api/admin/diagnostics.py

key-decisions:
  - "D-06: new_record_count uses pre-DELETE scalar COUNT(*) join (not per-row first_seen_at) for retry-safety"
  - "D-07: is_initial_import reads last_sync_at IS NULL before the UPDATE that sets it (Pitfall 4)"
  - "T-07-01: has_token derived in SQL — raw app_token_encrypted never included in SELECT projection"
  - "D-08: last_new_record_count + last_sync_is_initial stored atomically with the swap, persisted until next sync"
  - "Migration 0012: first_seen_at nullable (Pitfall 3 — online migration, NULL backfill acceptable)"

patterns-established:
  - "Arrival count: max(0, row_count - existing_count) where existing_count is pre-DELETE staging JOIN"
  - "is_initial_import: bool(row['last_sync_at'] is None) captured BEFORE the UPDATE"
  - "_refresh_profile_caches accepts new_record_count + is_initial_import as keyword args (defaults 0/False)"

requirements-completed: [API-04]

# Metrics
duration: ~45min
completed: 2026-06-01
---

# Phase 7 Plan 01: API-04 Backend + Migration 0012 + Wave-0 Test Scaffolds Summary

**Collection-diff count (new_record_count, is_initial_import) computed atomically in the staging swap and surfaced on the collection_changed SSE payload and admin profiles/diagnostics APIs, with migration 0012 landing the profile_invite_codes table and diff columns.**

## Performance

- **Duration:** ~45 min
- **Started:** 2026-06-01T15:00:00Z
- **Completed:** 2026-06-01T16:25:00Z
- **Tasks:** 3 (Task 0: test scaffolds, Task 1: migration 0012, Task 2: production code)
- **Files modified:** 7 (3 created tests, 1 migration, 3 production source files)

## Accomplishments

- Migration 0012 round-trips cleanly: profile_invite_codes table (UUID PK, ON DELETE CASCADE, 1-hour TTL), first_seen_at on profile_collection (nullable, Pitfall 3), last_new_record_count + last_sync_is_initial on profiles (D-08)
- _swap_inside_tx now returns (new_record_count, is_initial_import) computed atomically: reads last_sync_at IS NULL before the UPDATE (Pitfall 4), counts existing staging matches before DELETE (Pitfall 9 retry-safe), new_record_count = max(0, row_count - existing_count) always >= 0 (D-06)
- collection_changed SSE payload extended with new_record_count and is_initial_import (API-04 Pattern 5)
- Admin profiles list + single GET now return has_token bool derived in SQL (T-07-01 — ciphertext never leaves Postgres) and last_new_record_count + last_sync_is_initial (D-08)
- Admin diagnostics GET now returns last_new_record_count + last_sync_is_initial per profile
- Wave-0 test scaffold: 12 named integration tests (8 AUTH-02 xfail(strict=False) pending Plan 02, 4 API-04 green); unit tests for diff arithmetic, is_initial_import detection, and collection_changed payload shape

## Task Commits

Each task was committed atomically:

1. **Task 0: Wave-0 test scaffolds for AUTH-02 + API-04** - `813d316` (test)
2. **Task 1: Migration 0012** - `ff9f572` (feat)
3. **Task 2: Compute arrival count + is_initial_import; extend SSE payload; surface on admin APIs** - `a060759` (feat)

## Files Created/Modified

- `migrations/versions/0012_invite_codes_and_first_seen_at.py` — new migration: profile_invite_codes table, first_seen_at, diff columns
- `src/gruvax/sync/profile_sync.py` — extended _swap_inside_tx (returns diff result), _refresh_profile_caches (new params), sync_profile (threads diff result)
- `src/gruvax/api/admin/profiles.py` — list_profiles + get_profile extended with has_token, last_new_record_count, last_sync_is_initial
- `src/gruvax/api/admin/diagnostics.py` — per-profile diagnostics extended with last_new_record_count, last_sync_is_initial
- `tests/integration/test_invite_codes.py` — 12 Wave-0 tests (AUTH-02 xfail, API-04 green)
- `tests/unit/test_profile_sync_diff.py` — unit tests for diff arithmetic and payload structure
- `tests/unit/test_fake_discogsography.py` — test_limit_one regression guard

## Decisions Made

- Pre-DELETE scalar COUNT(*) join approach chosen for arrival count (over per-row first_seen_at timestamps) for retry-safety (Pitfall 9) — count is inherently correct on retry since staging is rebuilt fresh each sync call
- is_initial_import captured BEFORE the UPDATE (Pitfall 4) — the SELECT reads last_sync_at IS NULL; after the UPDATE that sets last_sync_at = NOW(), the query would always return False
- has_token derived in SQL as `(app_token_encrypted IS NOT NULL AND length(app_token_encrypted) > 1)::bool AS has_token` — the ciphertext never travels over the wire (T-07-01)

## Deviations from Plan

### Worktree PYTHONPATH note

The plan's verification command (`cd /Users/Robert/Code/public/GRUVAX && uv run pytest tests/unit/test_profile_sync_diff.py ...`) assumes the production source is the main repo's src. In worktree mode the modified source lives in the worktree directory. Tests were verified using `PYTHONPATH=/path/to/worktree/src:$PYTHONPATH` which correctly picks up the worktree's changes. This is standard worktree behavior — the changes will be on PATH after merge.

No functional deviations. Plan executed as specified.

## Issues Encountered

- Alembic round-trip test required `--config /path/to/worktree/alembic.ini` to find the new migration 0012 (the worktree has its own migrations directory, separate from the main repo). Used the worktree alembic.ini; round-trip verified successfully.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Migration 0012 is landed: Plan 02 can build invite_codes.py endpoints directly against the profile_invite_codes table
- has_token derivation is in place: Plan 03 frontend can use the field
- Wave-0 test scaffolds are in place: Plans 02 and 03 fill in the xfail tests as endpoints land
- Admin profiles API extended: Plan 03 frontend can render last_new_record_count and is_initial_import without additional backend changes

---
*Phase: 07-member-self-connect-collection-diff*
*Completed: 2026-06-01*

## Self-Check: PASSED

### Files exist:
- migrations/versions/0012_invite_codes_and_first_seen_at.py: FOUND
- src/gruvax/sync/profile_sync.py: FOUND (modified)
- src/gruvax/api/admin/profiles.py: FOUND (modified)
- src/gruvax/api/admin/diagnostics.py: FOUND (modified)
- tests/integration/test_invite_codes.py: FOUND
- tests/unit/test_profile_sync_diff.py: FOUND
- tests/unit/test_fake_discogsography.py: FOUND

### Commits exist:
- 813d316: test(07-01): add Wave-0 test scaffolds
- ff9f572: feat(07-01): add migration 0012
- a060759: feat(07-01): compute arrival count + extend APIs

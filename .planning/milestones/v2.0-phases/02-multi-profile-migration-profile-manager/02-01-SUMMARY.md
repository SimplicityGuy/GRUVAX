---
phase: 02-multi-profile-migration-profile-manager
plan: "01"
subsystem: migrations
tags: [alembic, postgres, profile-id, not-null, composite-pk, schema-migration]
dependency_graph:
  requires: ["02-00"]
  provides: ["PROF-04", "SC#3-schema-enforcement"]
  affects: ["cube_boundaries", "settings", "record_stats", "segment_overrides", "boundary_history"]
tech_stack:
  added: []
  patterns:
    - "Residual-NULL backfill before SET NOT NULL (PROF-03 carry-forward)"
    - "Fail-fast DO $$ NULL guards before tightening"
    - "Idempotent PK rebuild via pg_constraint current-PK-columns guard"
    - "FK swap (profile-aware) to unblock PK rewrite (DependentObjectsStillExist fix)"
    - "DROP NOT NULL after PK restore in downgrade (profile_id-in-PK prevents DROP NOT NULL)"
key_files:
  created:
    - migrations/versions/0010_profile_id_not_null.py
  modified: []
decisions:
  - "Used raw op.execute() SQL (not op.alter_column(nullable=False)) to avoid Alembic reflection mis-handling FK + composite-PK tables (RESEARCH anti-pattern)"
  - "segment_overrides -> cube_boundaries FK swapped from (unit_id,row,col) to (profile_id,unit_id,row,col) to unblock cube_boundaries_pkey rebuild (DependentObjectsStillExist)"
  - "admin_sessions and idempotency_keys profile_id stays nullable — these are global/infra tables, not per-profile data (Pitfall 5/6)"
  - "boundary_history keeps surrogate id PK (BIGSERIAL) — only SET NOT NULL applies, no PK rebuild"
  - "Reused prior-attempt reference migration 0010_prior_migration.py verbatim — it was round-trip verified and contained the two non-obvious bug fixes"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-05-28"
  tasks_completed: 2
  files_created: 1
  files_modified: 0
---

# Phase 02 Plan 01: profile_id NOT NULL + Composite PKs (Migration 0010) Summary

Migration 0010 promotes `profile_id` to NOT NULL on 5 per-profile data tables and
reconstructs composite primary keys with `profile_id` as the leading column,
making per-profile data isolation structurally enforced at the Postgres schema level (SC#3 / PROF-04).

## Tasks Completed

| Task | Description | Commit | Status |
|------|-------------|--------|--------|
| 1 | Write migration 0010 upgrade — backfill, composite PKs, SET NOT NULL | b8c05f2 | Done |
| 2 | Verify full round-trip (upgrade head → downgrade base → upgrade head) | b8c05f2 | Done (same file) |

## Verification Results

All 4 `test_migrate_0010.py` tests GREEN:

| Test | Result |
|------|--------|
| `test_not_null_on_five_data_tables` | PASS |
| `test_nullable_stays_on_two_infra_tables` | PASS |
| `test_composite_pks` | PASS |
| `test_roundtrip_clean` | PASS |

`just migrate` exits 0. `just migrate-roundtrip` (upgrade head → downgrade base → upgrade head) exits 0.

## Schema State After Migration 0010

### NOT NULL enforced (5 data tables)

| Table | Before 0010 | After 0010 |
|-------|-------------|------------|
| `gruvax.cube_boundaries` | `profile_id` nullable | NOT NULL |
| `gruvax.settings` | `profile_id` nullable | NOT NULL |
| `gruvax.record_stats` | `profile_id` nullable | NOT NULL |
| `gruvax.segment_overrides` | `profile_id` nullable | NOT NULL |
| `gruvax.boundary_history` | `profile_id` nullable | NOT NULL |

### Nullable kept (2 infra tables)

| Table | profile_id |
|-------|-----------|
| `gruvax.admin_sessions` | nullable (global/infra) |
| `gruvax.idempotency_keys` | nullable (global/infra) |

### Composite PK reconstruction (4 tables)

| Table | Old PK | New PK |
|-------|--------|--------|
| `cube_boundaries` | `(unit_id, row, col)` | `(profile_id, unit_id, row, col)` |
| `settings` | `(key)` | `(profile_id, key)` |
| `record_stats` | `(release_id)` | `(profile_id, release_id)` |
| `segment_overrides` | `(unit_id, row, col, label)` | `(profile_id, unit_id, row, col, label)` |
| `boundary_history` | `(id)` — UNCHANGED | `(id)` — UNCHANGED |

### FK updated

`segment_overrides_unit_id_row_col_fkey` → `segment_overrides_profile_id_unit_id_row_col_fkey`
(now references `cube_boundaries(profile_id, unit_id, row, col)` ON DELETE CASCADE)

## Deviations from Plan

### Reuse of prior-attempt reference migration

The plan referenced `/tmp/gruvax-p02-reference/0010_prior_migration.py` as a prior
round-trip-clean artifact containing two non-obvious bug fixes. The migration was adopted
verbatim. This is not a deviation from intent — the plan explicitly called out the reference
and its proven correctness.

### Two known non-obvious bugs (from prior run, pre-fixed in reference)

These were discovered in the prior interrupted run. The reference already contained the fixes;
they are documented here for downstream reference.

**[Rule 1 - Bug] segment_overrides -> cube_boundaries FK blocked PK rewrite**
- **Found during:** Prior attempt (live round-trip only — not catchable by static analysis)
- **Issue:** `segment_overrides_unit_id_row_col_fkey` references `cube_boundaries(unit_id, row, col)` — the exact columns whose PK was being rewritten. Postgres raises `DependentObjectsStillExist` on `DROP CONSTRAINT cube_boundaries_pkey`
- **Fix:** upgrade() drops the old FK before rebuilding the PK, then re-adds it profile-aware: `(profile_id, unit_id, row, col) REFERENCES cube_boundaries(profile_id, unit_id, row, col) ON DELETE CASCADE`. downgrade() reverses the swap.
- **Files modified:** `migrations/versions/0010_profile_id_not_null.py`
- **Commit:** b8c05f2

**[Rule 2 - Missing critical functionality] Residual-NULL backfill before SET NOT NULL**
- **Found during:** Prior attempt
- **Issue:** 0009's D-11 backfill only fixes rows present at migration time. Rows written after 0009 (dev/seed inserts, admin edits) keep `NULL profile_id`. The `_VERIFY_NO_NULLS` fail-fast guard then permanently blocks the migration on a live DB.
- **Fix:** Added `_BACKFILL_*` UPDATE statements (WHERE profile_id IS NULL) for each of the 5 data tables immediately before the verify guards. Idempotent; zero-cost on clean tables.
- **Files modified:** `migrations/versions/0010_profile_id_not_null.py`
- **Commit:** b8c05f2

**[Rule 1 - Bug] Downgrade ordering (DROP NOT NULL vs PK membership)**
- **Found during:** Prior attempt
- **Issue:** Postgres rejects `ALTER COLUMN profile_id DROP NOT NULL` while the column is still part of a PRIMARY KEY (`column "profile_id" is in a primary key`)
- **Fix:** downgrade() reorders: drop profile-aware FK → restore original PKs (removes profile_id from keys) → re-add original FK → DROP NOT NULL last.
- **Files modified:** `migrations/versions/0010_profile_id_not_null.py`
- **Commit:** b8c05f2

## Known Stubs

None — migration 0010 contains no stubs, placeholders, or TODOs.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes at external
trust boundaries introduced by this plan. Migration 0010 operates entirely within the
`gruvax` schema on the local Postgres instance.

## Self-Check: PASSED

- `migrations/versions/0010_profile_id_not_null.py` exists and is committed (b8c05f2)
- All 4 `test_migrate_0010.py` tests GREEN
- `just migrate` exits 0
- `just migrate-roundtrip` exits 0
- `ruff check` + `ruff format --check` clean
- `grep -v '^#' ... | grep 'op.alter_column'` — 1 match in docstring (text reference only, no actual call)

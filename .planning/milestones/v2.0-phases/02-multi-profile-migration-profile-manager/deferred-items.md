## Deferred Items — Phase 02 Plan 02-02

### Pre-existing: seed_boundaries.py ON CONFLICT mismatch after migration 0010

**Discovered during:** Task 2 integration regression verification
**Scope:** OUT OF SCOPE (pre-existing from Plan 02-01)

**Issue:** `tests/integration/test_locate.py` fails at setup because
`src/gruvax/db/seed_boundaries.py` uses `ON CONFLICT (unit_id, row, col)` for
the `cube_boundaries` upsert. After migration 0010 (Plan 02-01), the PK became
`(profile_id, unit_id, row, col)` — the old single-column conflict spec no longer
matches any unique constraint, causing `psycopg.errors.InvalidColumnReference`.

**Status:** Pre-existing from wave 1 merge. The `seed_boundaries.py` and its
callers in `test_locate.py` need to be updated to include `profile_id` in the
`ON CONFLICT` clause and pass a `profile_id` when seeding fixture data.

**Assigned to:** Plan 02-XX or a standalone fix plan.

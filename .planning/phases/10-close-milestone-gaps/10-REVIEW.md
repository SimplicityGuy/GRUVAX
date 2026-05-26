---
phase: 10-close-milestone-gaps
reviewed: 2026-05-25T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - src/gruvax/api/admin/segments.py
  - src/gruvax/api/admin/history.py
  - frontend/src/routes/kiosk/KioskView.tsx
  - tests/integration/test_segment_api.py
  - tests/integration/test_change_set.py
findings:
  critical: 2
  warning: 3
  info: 1
  total: 6
status: issues_found
---

# Phase 10: Code Review Report

**Reviewed:** 2026-05-25T00:00:00Z
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 10 fixes two integration blockers (INT-A: SSE payload key rename; INT-B: revert
wiring). The INT-A fix (segments.py `boundary_changed` payload shape) is correct and
consistent with cubes.py's canonical producer. The INT-B fix (history.py
revert_change_set) correctly follows the post-transaction Pitfall A pattern and uses
the DB-read override approach that `set_bin_overrides` and `insert_cut` also use.

Two blockers were found that were present before this phase but are exposed by the
new code paths and tests: (1) a systematic override-data-loss pattern in `put_bin_cut`
that is inconsistent with the approach adopted by `set_bin_overrides`/`insert_cut`/
`revert_change_set`, and (2) a type mismatch in the conflict-detection path
(`changed_at` converted to ISO string then compared as `timestamptz` in PostgreSQL).
Three warnings cover test fragility, dead invalidation on the kiosk SSE handler, and
an unbound reference pattern in `set_bin_overrides`.

---

## Critical Issues

### CR-01: `put_bin_cut` drops all segment-width overrides for every bin except the one being edited

**File:** `src/gruvax/api/admin/segments.py:282-293`

**Issue:** After `cache.invalidate()`, `put_bin_cut` reads overrides from the still-live
(stale) `segment_cache` for only the one affected bin and passes only those overrides to
`segment_cache.derive()`. Because `segment_cache.derive()` is called with a partial
overrides dict, every override set for any other bin is silently zeroed out. This
contrasts directly with the three other write paths in the same file (`set_bin_overrides`
lines 423-433, `insert_cut` lines 669-678) and with `revert_change_set` (history.py
lines 220-227), all of which re-read ALL overrides from `gruvax.segment_overrides` via a
post-commit DB query.

A label's physical-width proportion set by the admin (e.g., "Blue Note takes 60% of this
cube") is silently reset to auto_fraction the moment an admin edits any other cube's cut
point — a data-loss regression invisible to the user until they notice the bar widths have
changed.

This is the exact pattern `cubes.py::bulk_write_cubes` also uses (lines 803-809 in
cubes.py), so the bug predates Phase 10 and exists on the `PUT /admin/cubes/{u}/{r}/{c}/boundary`
and `POST /admin/cubes/bulk` paths too, but the Phase 10 code introduces a new instance
in `put_bin_cut` rather than fixing the established inconsistency.

**Fix:** Replace the stale-cache override read in `put_bin_cut` with the same DB
re-read pattern used by `set_bin_overrides`:

```python
# ── Invalidate + re-derive SegmentCache AFTER commit (Pitfall A) ─────────
cache.invalidate()
try:
    await cache.load(pool)
    overrides: dict[tuple[int, int, int, str], float] = {}
    async with pool.connection() as conn2:
        async with conn2.cursor() as cur:
            await cur.execute(
                "SELECT unit_id, row, col, label, fraction"
                " FROM gruvax.segment_overrides"
            )
            override_rows = await cur.fetchall()
    for uid_o, r_o, c_o, lbl_o, frac_o in override_rows:
        overrides[(int(uid_o), int(r_o), int(c_o), str(lbl_o))] = float(frac_o)
    segment_cache.invalidate()
    segment_cache.derive(cache, snapshot, overrides)
finally:
    await bus.publish(...)
```

The same fix is needed in `cubes.py::put_cube_boundary` (line 343-354) and
`cubes.py::bulk_write_cubes` (line 797-811), but those files are outside this
review's scope.

---

### CR-02: `changed_at` type corruption silently degrades conflict detection in `revert_change_set`

**File:** `src/gruvax/api/admin/history.py:135-138`

**Issue:** `fetch_change_set_rows()` (in `db/queries.py`) converts the `changed_at`
timestamp column from a Python `datetime` object to an ISO 8601 string via `.isoformat()`
(queries.py line 833). The resulting `hist["changed_at"]` string is then passed as
`original_changed_at` to `has_newer_changes()` (history.py line 138), which in turn
binds it to the SQL `AND changed_at > %s` (queries.py line 867).

psycopg3 sends a Python `str` over the wire as PostgreSQL type `text`. The comparison
`timestamptz > text` in PostgreSQL requires either an explicit cast (`%s::timestamptz`)
or an implicit cast path. PostgreSQL's implicit cast registry does include `text` →
`timestamptz`, so in practice this does not raise a runtime error. However:

1. The implicit cast is timezone-sensitive: `.isoformat()` on an aware datetime emits
   `+00:00`, but on a naive datetime emits no timezone. A mismatch between the stored
   `TIMESTAMPTZ` value and the text representation's timezone marker can cause
   incorrect ordering (a "newer" row appears to be the same age or older).
2. psycopg3 with strict type-checking or when the server uses `standard_conforming_strings=off`
   may fail with a `ProgrammingError` instead of performing the implicit cast.
3. This path is exercised by `test_revert_conflict_skip` which passes today, but only
   because PostgreSQL's default `UTC` session timezone happens to match the ISO string
   emitted. A deployment with a different session timezone would silently skip conflicts
   that should be detected, allowing silent clobber of newer edits — the exact scenario
   that T-03-21 guards against.

**Fix:** Either preserve the original `datetime` object in `fetch_change_set_rows` under
a separate key, or cast explicitly in the SQL inside `has_newer_changes`:

```python
# In queries.py::has_newer_changes — use explicit cast:
sql = """
SELECT 1 FROM gruvax.boundary_history
WHERE unit_id = %s AND row = %s AND col = %s
  AND changed_at > %s::timestamptz
LIMIT 1
"""
```

Or, preferably, stop converting `changed_at` to a string in `fetch_change_set_rows` and
preserve it as a datetime for internal use (the string conversion is only needed for the
HTTP response body, not for the conflict check).

---

## Warnings

### WR-01: `test_revert_publishes_boundary_changed` uses fragile last-event indexing

**File:** `tests/integration/test_change_set.py:671`

**Issue:** The test clears `spy.published` before calling revert (line 639), then at
line 671 uses `boundary_events[-1]` (the LAST boundary_changed event) with the comment
"the revert's publish is the last one." If anything else publishes a `boundary_changed`
after the revert handler runs (e.g., a future cache-refresh hook, a concurrent test
leaking into the spy, or an additional publish added to the revert path), the assertion
silently validates the wrong event and the payload `change_set_id` check becomes a
false-green.

The spy is fresh per test (defined inline in the test function) so cross-test leakage is
not possible today, but the last-event assumption is fragile against future code changes.

**Fix:** Use `boundary_events[0]` instead of `boundary_events[-1]`, or add an assertion
that exactly one boundary_changed event was published from the revert:

```python
assert len(boundary_events) == 1, (
    f"Expected exactly one boundary_changed from revert, got: {boundary_events}"
)
event_name, payload = boundary_events[0]
```

---

### WR-02: KioskView `server_hello` handler invalidates `['admin', 'settings']` — dead code on kiosk route

**File:** `frontend/src/routes/kiosk/KioskView.tsx:289`

**Issue:** The `server_hello` SSE listener calls:

```typescript
void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
```

The inline comment in `resync()` (line 218) explicitly states: "Admin keys (['admin', ...])
are never mounted on the kiosk route, so invalidating them here is dead code that risks
racing an admin optimistic update if the same SPA ever shares this consumer."

The `server_hello` handler contradicts the rule stated immediately above it by
invalidating an admin query key. While harmless on the kiosk route today (TanStack Query
ignores invalidations for unmounted query keys), it creates an inconsistency that makes
the boundary between kiosk-owned and admin-owned query keys harder to audit, and it is
the exact pattern the `resync()` comment warns against.

**Fix:** Remove the admin key invalidation from the `server_hello` handler:

```typescript
es.addEventListener('server_hello', () => {
  resync()
  // Removed: void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
})
```

---

### WR-03: `set_bin_overrides` leaves `response_body` potentially unbound if transaction raises mid-loop

**File:** `src/gruvax/api/admin/segments.py:403-445`

**Issue:** `response_body` is assigned at line 403 inside the `async with pool.connection() as conn, conn.transaction()` block, after the loop over `body.overrides`. If the transaction block raises an exception before reaching line 403 (e.g., a DB error during the upsert loop at line 400), `response_body` is never assigned. The exception propagates and the function returns without reaching line 445, so there is no runtime `NameError` in practice. However, this pattern is a latent maintenance hazard: if a future refactor adds a `try`/`except` around the transaction block to return a 500 response body, `response_body` will be unbound.

mypy `--strict` does not catch this because the assignment is syntactically reachable
(Python does not perform definite-assignment analysis). The pattern also makes the code
harder to read — it is not obvious that `response_body` at line 445 is always bound
when line 445 is reached.

**Fix:** Initialize `response_body` before the transaction block:

```python
response_body: dict[str, Any] = {}  # populated inside transaction
async with pool.connection() as conn, conn.transaction():
    ...
    response_body = {
        "unit_id": unit_id,
        "row": row,
        "col": col,
        "applied": applied,
        "cleared": cleared,
    }
    ...
```

---

## Info

### IN-01: `validate_contiguity` `segment_cache` parameter is permanently unused dead API surface

**File:** `src/gruvax/api/admin/validation.py` (called from `segments.py:239`, `segments.py:635`)

**Issue:** `validate_contiguity(proposed, segment_cache)` accepts `segment_cache` as a
required second argument but explicitly documents it as "RESERVED for a deferred
step-5 occupancy cross-check; currently UNUSED." Every call site must pass the
`segment_cache` dependency even though the function ignores it. This inflates the
dependency surface of `put_bin_cut` and `insert_cut`, both of which inject
`segment_cache` partly to pass it to a function that discards it.

This is tracked as WR-01 in the validation module's own deferred notes. It is not a
bug but it does make the call contract misleading — callers cannot know from the
signature alone whether `segment_cache` is used or not.

**Fix:** When the deferred step-5 is implemented, the parameter becomes real. Until
then, consider removing it from the signature and adding it back as part of the
enhancement plan; or document at the call sites that the argument is currently a
placeholder.

---

_Reviewed: 2026-05-25T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

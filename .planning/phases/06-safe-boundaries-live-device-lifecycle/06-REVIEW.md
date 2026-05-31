---
phase: 06-safe-boundaries-live-device-lifecycle
reviewed: 2026-05-30T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - src/gruvax/api/deps.py
  - src/gruvax/db/queries.py
  - src/gruvax/api/admin/cubes.py
  - src/gruvax/api/admin/segments.py
  - src/gruvax/api/admin/import_.py
  - src/gruvax/api/admin/history.py
  - src/gruvax/api/admin/editing.py
  - frontend/src/App.tsx
  - frontend/src/api/client.ts
  - frontend/src/state/sessionStore.ts
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/DeviceLifecycle.tsx
  - frontend/src/routes/kiosk/DeviceLifecycle.css
  - frontend/src/api/client.revoke.test.ts
  - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
  - tests/integration/test_two_profile_isolation.py
  - tests/integration/test_06_01_profile_scoped_writes.py
  - tests/integration/test_06_01_write_callsite_scoping.py
  - tests/integration/test_boundary_editor.py
  - tests/integration/test_change_set.py
  - tests/integration/test_editing.py
  - tests/integration/test_import.py
  - tests/integration/test_import_roundtrip_identity.py
  - tests/integration/test_segment_api.py
  - tests/integration/test_sse.py
  - tests/integration/test_wizard.py
findings:
  critical: 3
  warning: 6
  info: 3
  total: 12
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-05-30T00:00:00Z
**Depth:** standard
**Files Reviewed:** 24
**Status:** issues_found

## Summary

Phase 6 closed DATA-01 (profile-scoped admin boundary writes + per-profile SSE
fan-out) and DEV-05 (kiosk device-lifecycle SSE consumer). The two headline
mechanisms — `get_write_target` resolving `(profile_id, per_profile_bus)` and the
`profile_id` WHERE-clause in `write_boundary` / `fetch_current_boundary` — are
implemented correctly. Dependency ordering, the 400/403/404 contract, the
per-profile bus selection on all six write call sites, and the frontend
terminal-revoke / reassign handling (idempotent `triggerRevoke`, single App-level
handler, EventSource cleanup) are all sound, and the integration tests
(`test_two_profile_isolation.py`) directly exercise the write-scoping and fan-out
isolation guarantees.

However, the profile-scoping was applied **only to the write path**. Every
*supporting* query that the write routes call — the phantom check
(`cube_exact_match`), the near-miss lookup (`find_boundary_near_misses`), the
`segment_overrides` re-read on cache re-derive, the revert conflict check
(`has_newer_changes`), and the admin read endpoints (`get_admin_cubes`,
`get_cube_boundary`) — was left **unscoped or pinned to the default profile
UUID**. With more than one active profile these defeat the very isolation
DATA-01 set out to establish: an admin bound to profile B has their boundary
edits validated against profile A's collection, has profile A's width overrides
re-applied to B's SegmentCache, and sees a grid that interleaves rows from every
profile. These are the three BLOCKERs below.

## Critical Issues

### CR-01: Phantom check and near-miss lookup are not profile-scoped — DATA-01 isolation defeated on the validation path

**File:** `src/gruvax/api/admin/cubes.py:283`, `cubes.py:286`, `cubes.py:439`, `cubes.py:442`, `cubes.py:733`, `cubes.py:736`; `src/gruvax/api/admin/segments.py:217`, `segments.py:219`, `segments.py:510`, `segments.py:512`; `src/gruvax/api/admin/import_.py:368`, `import_.py:370`

**Issue:** Every write route resolves the authoritative `profile_id` via
`get_write_target` and correctly threads it into `write_boundary` /
`fetch_current_boundary` / `write_history_row`. But the *phantom* gate that
decides whether a write is even allowed calls:

```python
first_exists = await cube_exact_match(pool, first_label, first_catalog)
near_misses = await find_boundary_near_misses(pool, first_label, first_catalog)
```

with no `profile_id` argument. Both functions default to
`DEFAULT_PROFILE_UUID` (`queries.py:987`, `queries.py:463`). So when an admin is
bound to profile B and edits a cut point, the value is validated against profile
**A's** collection. Consequences with ≥2 profiles:

- A `(label, catalog)` pair that genuinely exists in B's collection is rejected
  as `phantom_boundary` (false negative) because it is absent from A.
- A pair that exists only in A is accepted into B's boundaries (false positive),
  writing a phantom boundary into B that `get_phantom_boundary_count` will later
  flag.
- The near-miss suggestions returned to the B admin are drawn from A's labels.

This is the exact cross-profile leakage DATA-01 was meant to eliminate; the write
itself is scoped but the gate guarding it is not, so the guarantee is hollow.

**Fix:** Thread the resolved `profile_id` through every phantom/near-miss call.
Both query functions already accept `profile_id`:

```python
profile_id, bus = _write_target  # already destructured in each handler
...
first_exists = await cube_exact_match(pool, first_label, first_catalog, profile_id=profile_id)
if not first_exists:
    near_misses = await find_boundary_near_misses(
        pool, first_label, first_catalog, profile_id=profile_id
    )
```

Apply to all six write handlers (`put_cube_boundary`, `bulk_write_cubes`,
`validate_boundary`* , `put_bin_cut`, `insert_cut`, `import_boundaries`).
*`validate_boundary` has no `get_write_target` dep at all (see WR-01) and must
acquire the profile_id first.

### CR-02: SegmentCache re-derive re-reads `segment_overrides` unscoped and writes overrides to the hardcoded default profile

**File:** `src/gruvax/api/admin/segments.py:401`, `segments.py:407-426` (write), `segments.py:451-459` (re-read); `src/gruvax/api/admin/history.py:239-243` (re-read); `src/gruvax/api/admin/import_.py:546-564` (write)

**Issue:** Two related defects break override isolation:

1. **Writes are pinned to the default profile.** `set_bin_overrides` resolves
   `_profile_id, bus = _write_target` (segments.py:363) but then **discards
   `_profile_id`** and hardcodes
   `_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"`
   (segments.py:401) for both the DELETE (segments.py:412) and the
   INSERT…ON CONFLICT (segments.py:425). `import_.py` does the same with
   `_IMPORT_DEFAULT_PROFILE_UUID` (import_.py:546-557). So an admin bound to
   profile B writes width overrides into profile A's `segment_overrides` rows
   (the composite PK is `(profile_id, unit_id, row, col, label)`), corrupting A
   and silently dropping B's intended override.

2. **The re-derive re-read is unscoped.** After commit, segments.py:451,
   history.py:239, and segments.py:693 all run
   `SELECT unit_id, row, col, label, fraction FROM gruvax.segment_overrides`
   with **no `WHERE profile_id`**. The resulting `new_overrides` dict therefore
   mixes every profile's overrides and feeds them into
   `segment_cache.derive(...)` for the single in-app SegmentCache, applying A's
   physical-width overrides to B's bins.

The comment at segments.py:399 ("Admin segment writes operate on the default
profile … per-profile segment editor deferred to Phase 3") acknowledges (1) was
deliberately stubbed, but Phase 6's stated goal is profile-scoped admin writes —
shipping a write route that ignores the resolved profile and a re-read that
ignores profile boundaries is a data-integrity BLOCKER for any multi-profile
deployment.

**Fix:** Use the resolved profile for the writes and scope every re-read:

```python
profile_id, bus = _write_target  # do NOT discard it
...
# write
sql_del = "... WHERE profile_id = %s::uuid AND unit_id = %s ..."
await conn.execute(sql_del, (profile_id, unit_id, row, col, ov.label))
# re-read
sql_overrides = (
    "SELECT unit_id, row, col, label, fraction "
    "FROM gruvax.segment_overrides WHERE profile_id = %s::uuid"
)
await cur.execute(sql_overrides, (profile_id,))
```

Apply the same scoping to history.py:239 (use the revert's `profile_id`) and the
import override writes/reads in import_.py.

### CR-03: Admin read endpoints `get_admin_cubes` and `get_cube_boundary` are not profile-scoped — cross-profile row leakage / duplication

**File:** `src/gruvax/api/admin/cubes.py:182-189` (`get_admin_cubes`), `cubes.py:229-235` (`get_cube_boundary`); also `src/gruvax/api/admin/import_.py:253-259` (full-address-space read)

**Issue:** Migration 0010 changed the `cube_boundaries` primary key from
`(unit_id, row, col)` to `(profile_id, unit_id, row, col)`. These read paths
still query without a `profile_id` filter:

```sql
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
ORDER BY unit_id, row, col          -- get_admin_cubes: no WHERE profile_id
```

```sql
SELECT ... FROM gruvax.cube_boundaries
WHERE unit_id = %s AND row = %s AND col = %s   -- get_cube_boundary: no profile_id
```

With ≥2 profiles:
- `get_admin_cubes` returns one row **per profile** for each physical
  coordinate, so the loop at cubes.py:192-206 appends duplicate cube dicts and
  the grid shows another profile's `first_label`/`is_empty` interleaved with the
  current admin's.
- `get_cube_boundary` returns an arbitrary profile's row (`fetchone()` over an
  unfiltered result), so the focused bin editor can display and then act on a
  different profile's cut point.
- `import_boundaries` builds `current_index` (import_.py:262-269) and the
  full-address-space fill from this unscoped read, so the G3 identity-skip and
  the replace-all fill reason over an arbitrary/duplicated address set —
  potentially skipping phantom checks based on another profile's committed state
  (interacts with CR-01).

**Fix:** Add `WHERE profile_id = %s::uuid` to all three reads. `get_cube_boundary`
must gain a profile source (either `get_write_target`-style resolution or
`resolve_profile_from_request`); `get_admin_cubes` and the import read should use
the resolved profile_id and pass it as a bound parameter.

## Warnings

### WR-01: `validate_boundary` dry-run is unscoped and lacks a profile source — preview disagrees with commit

**File:** `src/gruvax/api/admin/cubes.py:389-398`, `cubes.py:439`, `cubes.py:442`

**Issue:** `validate_boundary` (the dry-run diff endpoint) does **not** depend on
`get_write_target` and runs `cube_exact_match` / `find_boundary_near_misses`
unscoped (defaulting to the default profile). The matching commit path
(`put_cube_boundary` / `bulk_write_cubes`) is bound to the resolved profile (and
should be, per CR-01). The preview an admin sees for profile B is therefore
computed against profile A and can diverge from what the commit actually does —
validating a value the commit rejects, or vice versa. Because validate performs
no write it is not a BLOCKER, but a preview that contradicts the commit
undermines the entire validate→commit UX.

**Fix:** Add `_write_target: tuple[str, Any] = Depends(get_write_target)` to
`validate_boundary`, destructure `profile_id, _ = _write_target`, and pass
`profile_id=profile_id` into the phantom/near-miss calls so preview and commit
share one profile scope.

### WR-02: `has_newer_changes` revert conflict check is not profile-scoped — false conflicts / missed conflicts across profiles

**File:** `src/gruvax/db/queries.py:971-976`; called from `src/gruvax/api/admin/history.py:141`

**Issue:** The revert conflict guard queries `boundary_history` by
`(unit_id, row, col, changed_at)` only:

```sql
SELECT 1 FROM gruvax.boundary_history
WHERE unit_id = %s AND row = %s AND col = %s
  AND changed_at > %s
LIMIT 1
```

`boundary_history` carries a `profile_id` column (written at queries.py:766), but
the conflict check ignores it. A newer edit to the **same physical coordinate in
a different profile** will be seen as a conflict for this profile's revert
(skipping a cube that should revert), and the reverse is also possible. The
`list_change_sets` (queries.py:880-889) and `fetch_change_set_rows`
(queries.py:921-929) queries are likewise unscoped, so `/admin/history` lists and
reverts change-sets from all profiles intermixed.

**Fix:** Add `AND profile_id = %s::uuid` to `has_newer_changes`,
`list_change_sets`, and `fetch_change_set_rows`, threading the revert's resolved
`profile_id` (already available at history.py:119) through `fetch_change_set_rows`
and `has_newer_changes`.

### WR-03: `write_boundary` / `fetch_current_boundary` default `profile_id=None` to an unscoped all-profiles SQL path

**File:** `src/gruvax/db/queries.py:666` and `queries.py:705-712` (`write_boundary`); `queries.py:607` and `queries.py:642-648` (`fetch_current_boundary`)

**Issue:** Both functions accept `profile_id: str | None = None` and, when it is
`None`, fall through to a legacy branch whose UPDATE/SELECT has **no profile
filter** — i.e. `UPDATE gruvax.cube_boundaries SET ... WHERE unit_id=%s AND
row=%s AND col=%s`, which now matches one row *per profile*. All Phase-6 call
sites do pass `profile_id`, so this is latent rather than live, but it is a
loaded footgun: any future caller (or a refactor that drops the kwarg) silently
mutates every profile's boundary at that coordinate. Defaulting a
profile-scoping parameter to "scope to nothing" inverts the safe default.

**Fix:** Either make `profile_id` a required positional parameter (preferred —
the compiler/type-checker then catches omissions), or keep the kwarg but raise
`ValueError` when it is `None` instead of executing an unscoped statement. Delete
the unscoped SQL branch once the default-profile legacy callers are gone.

### WR-04: Python-3.14-only tuple-`except` syntax is used pervasively, including a semantically suspect `except AttributeError, Exception:`

**File:** `src/gruvax/api/admin/cubes.py:155`, `src/gruvax/api/admin/import_.py:713`, `import_.py:748`; `tests/integration/test_two_profile_isolation.py:429,468,491,577,614,637`; and (out of changed set but related) `tests/integration/conftest.py:100`

**Issue:** `except TypeError, ValueError:` is the parenthesis-free tuple-except
form that only became legal in Python 3.14. The project pins
`requires-python = ">=3.14"` and CI runs 3.14, so it parses and catches both
types — but it is a fragile idiom: on any 3.13 interpreter (the documented
discogsography "hard match" baseline in CLAUDE.md) every one of these modules is
a hard `SyntaxError` at import, taking the whole app down. More concerning,
`conftest.py:100` reads `except AttributeError, Exception:` — catching `Exception`
makes the `AttributeError` term redundant and signals the author may have
intended Python-2 `except E, name:` binding semantics. Reviewers cannot tell
intent from the syntax, which is exactly why the parenthesised form exists.

**Fix:** Use explicit tuples everywhere: `except (TypeError, ValueError):`. For
conftest.py:100 decide whether `Exception` alone (it subsumes `AttributeError`)
or a narrower set is meant. This also restores 3.13 portability if discogsography
alignment is ever required.

### WR-05: `_get_nominal_capacity` swallows lookup failures with a 3.14-only except and a misleading default

**File:** `src/gruvax/api/admin/cubes.py:153-156`

**Issue:**

```python
try:
    return max(1, int(raw))
except TypeError, ValueError:
    return 95
```

Beyond WR-04's syntax concern, the `except` only covers `TypeError`/`ValueError`.
`settings_cache.get("cube.nominal_capacity", 95)` can return any JSONB-decoded
value; e.g. a `bool` (`True`) passes `int()` and yields `1`, and a `list`/`dict`
raises `TypeError` (caught) — but the function silently substitutes the literal
`95` rather than the caller-configured default, so a misconfigured setting is
masked instead of surfaced. Fill levels then compute against a capacity the admin
never set.

**Fix:** Use `except (TypeError, ValueError):`, and consider logging at WARNING
when the configured value is unparseable so a bad setting is observable rather
than silently defaulted.

### WR-06: `check403Revoke` swallows JSON-parse failures, masking real 403s as silent no-ops

**File:** `frontend/src/api/client.ts:29-46`

**Issue:** The shared 403 intercept reads `res.json()` inside a `try` whose
`catch` only re-throws when `err.message === 'device_revoked'`:

```ts
try {
  const body = await res.json() ...
  if (body?.detail?.type === 'device_revoked') { ...; throw new Error('device_revoked') }
} catch (err) {
  if (err instanceof Error && err.message === 'device_revoked') throw err
  // else: swallowed
}
return res
```

Two issues: (1) a 403 with a non-JSON body (e.g. an HTML error page from a proxy)
has its parse error swallowed and `check403Revoke` returns normally, so the
caller's generic `throw new Error('... failed: 403')` still fires — acceptable,
but the body is consumed, so any caller wanting to inspect it cannot. (2) More
subtly, `res.json()` consumes the response stream; callers that fall through to
their own error handling after `check403Revoke` cannot re-read the body. Today no
caller does, but it is a latent coupling. The behavior is correct for the tested
`device_revoked` path; flagging because the broad swallow hides diagnostic
information for every other 403 shape.

**Fix:** Clone the response before reading (`res.clone().json()`), or narrow the
`catch` to only swallow `SyntaxError` from `json()` and let unexpected errors
propagate. Add a debug log on the swallowed branch.

## Info

### IN-01: `validate_boundary` `movement_counts` returns `records_after == records_before` by design — preview delta is always 0

**File:** `src/gruvax/api/admin/cubes.py:532-547`

**Issue:** `_compute_movement_counts` sets `records_after = records_before` with a
comment that the real diff is computed post-commit, so `delta` is always 0 and
`fill_level_after == fill_level_before`. The dry-run "movement preview" therefore
conveys no movement information. This is documented as an intentional
approximation, but a preview field that is structurally always zero is
misleading to the consumer and worth either removing or labeling as "current
count only" in the response.

**Fix:** Either drop `records_after`/`delta`/`fill_level_after` from the preview
payload or rename them to make the "current snapshot, not projected" semantics
explicit.

### IN-02: `did_you_mean` only surfaced when result set is empty — silently dropped on near-empty noisy matches

**File:** `src/gruvax/db/queries.py:360-363`

**Issue:** `did_you_mean_query` is invoked only `if not rows`. A query that
returns one weak/irrelevant FTS hit suppresses the suggestion even when the
trigram suggestion would be more useful. This matches the documented "conservative
D-11" decision, so it is informational, not a defect.

**Fix:** No change required; noted for product awareness. If typo-tolerance
becomes a complaint, gate `did_you_mean` on a max top-rank threshold rather than
strict emptiness.

### IN-03: `get_phantom_boundary_count` counts phantoms across all profiles' boundaries against one profile's collection

**File:** `src/gruvax/db/queries.py:1213-1227`

**Issue:** The `NOT EXISTS` subquery is correctly scoped to
`v.profile_id = %s::uuid`, but the outer `cube_boundaries cb` scan has no
`profile_id` filter, so it counts non-empty boundaries from *every* profile and
tests each against the one supplied profile's collection. With multiple profiles
this over-counts phantoms (every other profile's legitimate boundary is "phantom"
relative to this profile's collection). Out of the strict Phase-6 write/SSE scope,
but the same class of unscoped-read bug as CR-03/WR-02.

**Fix:** Add `cb.profile_id = %s::uuid` to the outer query and bind the same
profile_id used in the `NOT EXISTS`.

---

_Reviewed: 2026-05-30T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---
phase: 05-close-v2-0-integration-gaps-kiosk-collection-changed-listener
reviewed: 2026-05-30T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/gruvax/api/search.py
  - src/gruvax/api/locate.py
  - tests/integration/test_search_b02.py
  - tests/integration/test_locate_b02.py
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: resolved
fixes_applied:
  applied: 2026-05-30
  scope: "Critical + Warning (4 warnings)"
  warnings_fixed: 4   # WR-01 037413b, WR-02 0088072, WR-03 fbeda50, WR-04 e38fc22
  info_deferred: 3    # IN-01/02/03 (Info, out of --fix default scope)
  verification: "backend 35 passed + ruff + mypy --strict clean; frontend 6 passed + tsc clean"
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-30
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 5 closes two v2.0 integration gaps: B-02 (optional `profile_id` on `/api/search` and `/api/locate` with cookie-authoritative fallback) and B-01/B-02-frontend (a `collection_changed` SSE listener in KioskView plus gating the search query on `boundProfileId`).

The central security invariant — that the omitted-`profile_id` path never trusts a client-supplied value over the cookie and never defaults to a guessable UUID — is **upheld**. Both handlers call `resolve_profile_from_request` first and only fall back to its return value when `profile_id` is omitted; when supplied, the exact-match `profile_mismatch` (403) check is preserved (search.py:79-84, locate.py:123-128). The no-cookie path still propagates 400 `session_unbound` from `resolve_profile_from_request` (deps.py:228-232). There is **no cross-profile data leak path** in the new code, and no guessable default UUID is ever substituted. The frontend single-cleanup invariant holds: exactly one runtime `es.close()` at KioskView.tsx:347; the `collection_changed` listener (lines 340-343) is correctly placed inside the effect before the cleanup return. The `enabled` gate now includes `!!boundProfileId` (line 171).

No BLOCKERs found. The warnings concern redundant authoritative-profile resolution (multiple DB round-trips and duplicated `last_seen_at` writes per request, with a small TOCTOU window), a UUID-format brittleness in the mismatch comparison, and a test mock whose shape does not match the real API contract.

## Warnings

### WR-01: Authoritative profile resolved 2–3× per request (redundant DB round-trips + duplicated `last_seen_at` writes + TOCTOU window)

**File:** `src/gruvax/api/locate.py:116,133-138` and `src/gruvax/api/search.py:72,89`
**Issue:** Both handlers call `resolve_profile_from_request(request, pool)` explicitly, then call profile-scoped deps that each call `resolve_profile_from_request` *again* internally.
- `locate_endpoint` resolves **3×**: explicit (line 116), inside `get_segment_cache_for_profile` (deps.py:336), inside `get_snapshot_for_profile` (deps.py:303).
- `search` resolves **2×**: explicit (line 72), inside `get_snapshot_for_profile` (deps.py:303).

Each resolution for a fingerprinted device issues a throttled `UPDATE gruvax.devices SET last_seen_at = NOW()` with its own `conn.commit()` (deps.py:218-221), so a single locate request can fire that write up to 3 times. Beyond the wasted round-trips (out of scope as pure performance), there is a genuine correctness exposure: a device that is revoked between resolution #1 and #2 would be observed inconsistently within one request, and the duplicated writes are a behavioral change from the pre-Phase-5 single-dep resolution. The pattern also defeats the throttle's intent.

**Fix:** Resolve once and pass the trusted `effective_profile_id` to registry-only lookups, bypassing the re-resolution. Either add internal helpers that take an already-resolved id, or inline the registry `.get()` after the single resolution. Example for search:
```python
resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
effective_profile_id = resolved_profile_id if profile_id is None else profile_id
if profile_id is not None and resolved_profile_id != profile_id:
    raise HTTPException(403, detail={"type": "profile_mismatch"})
# registry-only validation (no second resolve):
registry = getattr(request.app.state, "snapshot_registry", None)
if registry is None:
    raise HTTPException(503, detail="Snapshot registry not ready")
if registry.get(str(effective_profile_id)) is None:
    raise HTTPException(404, detail={"type": "profile_not_found"})
```
At minimum, document that this triple-resolution is intentional and that the `last_seen_at` throttle absorbs the extra writes.

### WR-02: `profile_mismatch` comparison is case/format-sensitive on raw cookie/query strings

**File:** `src/gruvax/api/search.py:79` and `src/gruvax/api/locate.py:123`
**Issue:** The mismatch check is a raw string comparison: `if resolved_profile_id != profile_id`. `resolved_profile_id` may originate from the DB device row as `str(profile_id)` (canonical lowercase UUID, deps.py:222) or from the raw browse-binding cookie value (deps.py:233), while the query-param `profile_id` is whatever the client sent. A client that supplies the *same* UUID but in uppercase (or with surrounding format differences) gets a spurious 403 `profile_mismatch` even though it is the same profile. This fails closed (no security leak) but is a latent correctness/UX bug: the supplied-param path is the documented "existing path" and clients legitimately round-trip the UUID.
**Fix:** Normalize both sides before comparison, e.g. parse to `uuid.UUID` and compare canonical forms, returning 422/400 on an unparseable supplied value:
```python
from uuid import UUID
try:
    supplied = UUID(profile_id)
except ValueError:
    raise HTTPException(422, detail={"type": "invalid_profile_id"})
if UUID(resolved_profile_id) != supplied:
    raise HTTPException(403, detail={"type": "profile_mismatch"})
```

### WR-03: Test mock for `searchCollection` returns the wrong shape (`results`/`total` instead of `items`)

**File:** `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx:36`
**Issue:** The mock returns `{ results: [], total: 0, took_ms: 1, did_you_mean: null }`, but the real `searchCollection` resolves a `SearchResponse` whose result list is `items` (client.ts:13-26; KioskView reads `searchData?.items` at line 479). The mock contract diverges from the production contract. The current assertions happen to not depend on the shape (they only count calls), so the tests pass — but this mock will silently mask any future regression where the component depends on the result list, and it gives a false sense of contract coverage.
**Fix:** Align the mock with `SearchResponse`:
```ts
searchCollection: vi.fn().mockResolvedValue({ items: [], took_ms: 1, did_you_mean: null }),
```

### WR-04: `did_you_mean` from `searchData` is read without the `boundProfileId` gate accounted for in `EmptyCollectionState` branch

**File:** `frontend/src/routes/kiosk/KioskView.tsx:171,531`
**Issue:** The search `useQuery` is now gated `enabled: !!boundProfileId && debouncedQuery.trim().length > 0` (line 171). When `boundProfileId` is null but a user has already typed (debouncedQuery non-empty), the query is disabled, so `searchData` stays `undefined`. `ResultsList` receives `didYouMean={searchData?.did_you_mean ?? null}` and `items={... ? searchResults : []}` — these resolve to safe defaults, so there is no crash. However, the `showNoResults` derivation (lines 480-484) becomes true while the query is *disabled* (not actually fetched): `debouncedQuery` non-empty, `!isFetching` true, `searchResults.length === 0`, `!isError`. This can flash a "no results" affordance during the brief unbound-but-typed window even though no search ran. This is a robustness/UX defect, not a crash.
**Fix:** Include `boundProfileId` in the `showNoResults` guard so the no-results state only appears once a search has actually been permitted to run:
```ts
const showNoResults =
  !!boundProfileId &&
  debouncedQuery.trim().length > 0 &&
  !isFetching &&
  searchResults.length === 0 &&
  !isError
```

## Info

### IN-01: Search snapshot dependency is fetched purely for validation and its return value is discarded

**File:** `src/gruvax/api/search.py:89`
**Issue:** `await get_snapshot_for_profile(effective_profile_id, request, pool)` is called only to reproduce the pre-Phase-5 `_snapshot` validation dependency; the returned snapshot is unused by search. This is functionally correct (it preserves the 404 `profile_not_found` / 503 registry taxonomy) but the intent is non-obvious — a future reader may delete it as dead. Pairs with the redundant-resolution concern in WR-01.
**Fix:** Add a one-line comment clarifying the call is validation-only (registry + taxonomy), or fold it into a dedicated `validate_profile_registered(...)` helper that does not return a snapshot.

### IN-02: `collection_changed` listener does not narrow invalidation, re-invalidates `['units']`/`['cubes']` already covered by `resync()`

**File:** `frontend/src/routes/kiosk/KioskView.tsx:340-343`
**Issue:** The new `collection_changed` handler calls `invalidateQueries({ queryKey: ['search'] })` then `resync()`, which invalidates `['units']` and `['cubes']` and re-locates the active selection. This is correct and matches the phase intent (invalidate search + resync grid/locate). Minor note: the publisher sends no payload (per the inline comment referencing `profile_sync.py`), so the no-arg listener form is appropriate and the absence of a `try/catch` is justified (no `JSON.parse`). No change required; recorded for traceability of the B-01 closure.
**Fix:** None required.

### IN-03: locate `release_id` missing explicit `Query()` typing comment vs `profile_id`

**File:** `src/gruvax/api/locate.py:81-82`
**Issue:** `release_id: int` relies on implicit FastAPI query coercion (422 on non-int, per the module docstring T-01-09), while `profile_id` uses an explicit `Query(default=None)`. The behavior is correct, but the asymmetry makes the 422-on-non-int contract less discoverable at the signature.
**Fix:** Optionally make it explicit: `release_id: int = Query()` to mirror the documented typed-param contract.

---

_Reviewed: 2026-05-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

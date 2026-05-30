---
phase: 05-close-v2-0-integration-gaps-kiosk-collection-changed-listener
fixed_at: 2026-05-30T15:16:00Z
review_path: .planning/phases/05-close-v2-0-integration-gaps-kiosk-collection-changed-listene/05-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 4
skipped: 0
status: all_fixed
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-05-30T15:16:00Z
**Source review:** `.planning/phases/05-close-v2-0-integration-gaps-kiosk-collection-changed-listene/05-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 4 (WR-01, WR-02, WR-03, WR-04)
- Fixed: 4
- Skipped: 0

## Fixed Issues

### WR-01: Authoritative profile resolved 2-3x per request

**Files modified:** `src/gruvax/api/search.py`, `src/gruvax/api/locate.py`
**Commit:** `037413b`
**Applied fix:** Removed calls to `get_snapshot_for_profile` (search.py) and `get_segment_cache_for_profile` / `get_snapshot_for_profile` (locate.py). These deps each called `resolve_profile_from_request` internally, firing extra DB round-trips and duplicate throttled `last_seen_at` writes. Replaced with direct registry-only lookups (`getattr(request.app.state, "snapshot_registry", None)` etc.) that reproduce the same 503/404 error taxonomy against the already-resolved `effective_profile_id`. Also removed now-unused imports of those deps. All 35 backend integration tests (test_search_b02, test_locate_b02, test_search, test_locate) remain green. Ruff and mypy --strict clean.

### WR-02: profile_mismatch check is case/format-sensitive on raw strings

**Files modified:** `src/gruvax/api/search.py`, `src/gruvax/api/locate.py`
**Commit:** `0088072`
**Applied fix:** Added `from uuid import UUID` import to both files. The raw `resolved_profile_id != profile_id` string comparison was replaced with normalized UUID comparison: parse `profile_id` via `UUID(...)`, return 422 `invalid_profile_id` on `ValueError` (using `raise ... from None` per B904). For `resolved_profile_id`, guard the parse with a try/except so a non-UUID resolved value (e.g. legacy browse-binding cookie) falls back to the original string compare rather than raising an uncaught 500. All 35 backend integration tests remain green. Ruff and mypy --strict clean.

### WR-03: searchCollection mock returns wrong shape

**Files modified:** `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx`
**Commit:** `fbeda50`
**Applied fix:** Changed line 36 from `{ results: [], total: 0, took_ms: 1, did_you_mean: null }` to `{ items: [], took_ms: 1, did_you_mean: null }`, matching the real `SearchResponse` interface (items, took_ms, did_you_mean). All 6 EventSource tests pass; TypeScript (`npx tsc --noEmit`) clean.

### WR-04: showNoResults flashes when search is disabled (boundProfileId null)

**Files modified:** `frontend/src/routes/kiosk/KioskView.tsx`
**Commit:** `e38fc22`
**Applied fix:** Added `!!boundProfileId &&` as the first condition in the `showNoResults` derivation (lines 480-486). The search query is `enabled: !!boundProfileId && debouncedQuery.trim().length > 0`; without the same guard on `showNoResults`, a user who types before the profile is bound sees a spurious no-results affordance while the query is disabled. The fix ensures no-results only renders once a search has actually been permitted to run. All 6 EventSource tests pass; TypeScript clean.

## Skipped Issues

None — all four in-scope findings were successfully fixed.

---

_Fixed: 2026-05-30T15:16:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

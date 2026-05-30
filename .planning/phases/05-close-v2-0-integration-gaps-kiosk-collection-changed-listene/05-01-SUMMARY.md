---
phase: 05-close-v2-0-integration-gaps-kiosk-collection-changed-listene
plan: "01"
subsystem: backend-api
tags: [b02, profile-resolution, optional-param, search, locate, integration-tests]
dependency_graph:
  requires: []
  provides:
    - optional-profile_id-on-search-and-locate
    - b02-backend-closed
  affects:
    - src/gruvax/api/search.py
    - src/gruvax/api/locate.py
tech_stack:
  added: []
  patterns:
    - resolve_profile_from_request called directly in handler body (cookie/device authoritative)
    - profile_id: str | None = Query(default=None) with explicit mismatch guard
key_files:
  created:
    - tests/integration/test_search_b02.py
    - tests/integration/test_locate_b02.py
  modified:
    - src/gruvax/api/search.py
    - src/gruvax/api/locate.py
decisions:
  - "Resolve effective profile in handler body (not via Depends) so optional profile_id does not break dep signatures"
  - "Call get_snapshot_for_profile / get_segment_cache_for_profile directly with resolved UUID to preserve 503/404 taxonomy"
  - "profile_id None-path calls resolve_profile_from_request once; supplied-path calls it once then checks mismatch — no double-resolution"
metrics:
  duration: "6 minutes"
  completed: "2026-05-30"
  tasks_completed: 2
  files_changed: 4
requirements: [API-02]
---

# Phase 5 Plan 01: B-02 Backend — Optional profile_id with Cookie-Authoritative Fallback Summary

Make `/api/search` and `/api/locate` accept an omitted `profile_id` query param and resolve the effective profile from the `gruvax_browse_binding` cookie via `resolve_profile_from_request`, eliminating the B-02 422 error on session-unresolved kiosk searches.

## What Was Built

**B-02 backend closure:** Both `GET /api/search` and `GET /api/locate` now accept `profile_id` as an optional query parameter (`str | None = Query(default=None)`). When omitted, the handler body calls `resolve_profile_from_request(request, pool)` to derive the authoritative profile from the browse-binding (or device fingerprint) cookie. When supplied, the same resolver runs and the result is checked against the supplied value — returning 403 `profile_mismatch` on any divergence.

The D2-04 error taxonomy is fully preserved:
- No cookie → 400 `session_unbound` (from `resolve_profile_from_request`)
- Unknown/revoked fingerprint → 403 `device_unknown` / `device_revoked` (same)
- Supplied UUID mismatches cookie-resolved UUID → 403 `profile_mismatch` (inline check)
- Registry missing → 503 (from `get_snapshot_for_profile` / `get_segment_cache_for_profile`)
- Profile not in registry → 404 `profile_not_found` (same deps)

The `_snapshot` Depends and `segment_cache`/`snapshot` Depends were removed from the handler signatures and replaced with direct calls in the handler body using the resolved effective UUID. This is semantically equivalent (the dep's internal mismatch check passes because effective_profile_id == resolved_profile_id) while allowing the optional param change.

**RED integration tests** were written first and confirmed failing with 422 before the fix.

## Tasks Completed

| Task | Description | Commit |
|------|-------------|--------|
| 1 | Write RED integration tests for search and locate B-02 paths | 0d61b9f |
| 2 | Make profile_id optional + cookie-authoritative fallback in search.py and locate.py | 083d003 |

## Verification Results

```
uv run pytest tests/integration/test_search_b02.py tests/integration/test_locate_b02.py
tests/integration/test_search.py tests/integration/test_locate.py
→ 35 passed, 0 failed
```

- `uv run ruff check src/gruvax/api/search.py src/gruvax/api/locate.py` — clean
- `uv run mypy src/gruvax/api/search.py src/gruvax/api/locate.py` — clean (0 issues)

## Deviations from Plan

None — plan executed exactly as written. The `_snapshot` dep removal from the handler signature was anticipated in the plan's action section (lines 167-176).

## Known Stubs

None — both handlers are fully wired. The omitted-param path resolves the live profile from the cookie and queries real profile_collection data.

## Threat Flags

No new trust-boundary surface introduced. The plan's T-05-01 and T-05-02 mitigations are confirmed by the test suite:

- **T-05-01 (Elevation of Privilege):** Test 4 (`test_supplied_correct_profile_id`) proves supplied-correct path still returns 200; test 3 (`test_mismatched_profile_id_returns_403`) proves supplied-mismatch still returns 403. The effective UUID passed to `search_collection` / `get_release_for_locate` is always the resolver-authoritative value, never a client-trusted raw value.
- **T-05-02 (Information Disclosure):** Test 2 (`test_no_cookie_returns_session_unbound`) proves 400 fires before any data query runs when no session is bound.

## Self-Check: PASSED

Files exist:
- `tests/integration/test_search_b02.py` ✓
- `tests/integration/test_locate_b02.py` ✓
- `src/gruvax/api/search.py` modified ✓
- `src/gruvax/api/locate.py` modified ✓

Commits exist:
- `0d61b9f` ✓
- `083d003` ✓

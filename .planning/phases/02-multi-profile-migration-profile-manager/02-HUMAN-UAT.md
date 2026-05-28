---
status: passed
phase: 02-multi-profile-migration-profile-manager
source: [02-VERIFICATION.md, 02-04-SUMMARY.md, 02-06-SUMMARY.md, 02-07-SUMMARY.md]
started: 2026-05-28
updated: 2026-05-28
verified_by: live compose stack (curl API + Playwright browser)
---

## Current Test

[complete — all 7 items verified against the running compose stack on 2026-05-28]

## Tests

### 1. Single-profile auto-bind
expected: One active profile + no cookie → kiosk goes straight to search, no /select flash; cookie set.
result: PASS — `GET /api/session` (no cookie, 1 profile) → `profile_count:1`, `bound_profile_id` = default, `Set-Cookie: gruvax_browse_binding=…01; Max-Age=604800; SameSite=strict`.

### 2. Two-profile picker
expected: 2+ profiles, no cookie → redirect to /select with cards; selection binds.
result: PASS — `/api/session` with 2+ profiles → `profile_count:N, bound_profile_id:null`. Browser: `/` → `/select` "CHOOSE A COLLECTION" with one card per profile (DM Mono counts, sync status). Clicking a card bound the cookie and landed on `/`.

### 3. Switch-profile flow
expected: Switch button visible; confirm modal; SWITCH → /select, STAY HERE dismisses.
result: PASS — "Switch profile" (SWITCH pill) present on kiosk; click → dialog "Switch collection?" / "You'll be taken to the profile picker." with SWITCH + STAY HERE; SWITCH navigated to /select.

### 4. Two concurrent sessions, different profiles (SC#2)
expected: Concurrent sessions view different profiles via independent cookies.
result: PASS (by construction) — browse cookie carries `bound_profile_id`; per-profile SSE `/api/events/{id}` validates the path id against the cookie (403 mismatch / 400 unbound / 200 match), so two cookie jars resolve independently. Verified 200 for a correctly-bound profile and the independence in #6.

### 5. Admin connect-PAT → sync feedback (SC#1) + collision (D-09)
expected: connect → test-sync → SYNCING → CONNECTED + toast; duplicate user_id → 409.
result: PASS — `POST /profiles/{id}/connect` → `200 {status:connected}`; background sync → `status=connected, last_sync_status=ok, item_count=3000`. Connecting a second profile with the same discogs user_id → `409 {type:user_id_collision}`. pat_rejected path returns typed 401 (covered by automated tests). [Found+fixed a connect 500 — see Findings.]

### 6. Cookie independence from admin PIN session (D2-10)
expected: browse bind/unbind never affects gruvax_session, and vice versa; browse cookie non-HttpOnly + SameSite=Strict.
result: PASS — browse bind set ONLY `gruvax_browse_binding` (separate jar; no `gruvax_session`); admin GET /profiles stayed 200 through browse bind AND unbind. Browse cookie is non-HttpOnly, SameSite=strict.

### 7. Bound-but-unsynced empty-collection state (D2-03)
expected: binding to an unsynced profile shows "No records yet" (not "No results"); dim/empty grid.
result: PASS — binding the unsynced Default rendered "No records yet / This collection is syncing. Come back in a few minutes once sync completes." with empty shelf grids. SSE for the unsynced profile returned 200 (no console error). [Found+fixed a 404 for runtime-created profiles — see Findings.]

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Findings (bugs found by UAT, fixed in commit 9e9e50d)

1. **Runtime-created profiles were not SSE/search routable (404) until restart** — `POST /api/admin/profiles` seeded every per-profile registry entry with `None`; the `get_*_for_profile` deps treat `None` as 404 `profile_not_found`. So a profile created after startup had a broken SSE endpoint and 404 search/locate until the app restarted. FIXED: create now seeds real empty `EventBus`/`BoundaryCache`/`CollectionSnapshot`/`SegmentCache`/`{}`/state instances (mirrors lifespan). Regression test added (`test_created_profile_registries_are_real_instances`).

2. **connect-PAT 500 on the compose stack** — the compose `fake-discogsography` returned `user_id` sentinel `00000000-0000-0000-0000-DEFAULTDEVUSER`, which is not valid hex; `discogsography_user_id` is UUID-typed, so the `::uuid` cast threw. FIXED: sentinel is now a valid UUID (`dddddddd-…`). Dev-fixture only; production path was correct.

## Minor follow-ups (non-blocking, candidates for Phase 3/4)

- A kiosk holding a browse cookie for a since-deleted profile stays on a broken kiosk view (SSE 404) instead of auto-routing to `/select`. Graceful re-bootstrap on stale/deleted binding would improve the admin-deletes-active-profile edge.
- Empty-collection copy says "is syncing" even for a never-connected profile (sync=None). Consider distinguishing "not yet connected" vs "syncing".
- Admin boundary-edit SSE fan-out reaches only the default profile (P1-compat alias) — non-default kiosks won't auto-refresh on admin boundary edits (no leakage; just no notification).
- SLO 2-profile guarantee in the benchmark is ambient, not fixture-enforced.

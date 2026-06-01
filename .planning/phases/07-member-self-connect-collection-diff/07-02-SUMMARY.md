---
phase: 07-member-self-connect-collection-diff
plan: 02
subsystem: api
tags: [auth, invite-codes, pat-encryption, rate-limiting, fastapi, postgres]

# Dependency graph
requires:
  - phase: 07-01
    provides: profile_invite_codes table (migration 0012), has_token derivation, AUTH-02 xfail scaffolds

provides:
  - POST /api/admin/profiles/{id}/invite (PIN-gated owner endpoint — 1-hour single-use invite, D-01/D-09)
  - GET /api/invite-codes/{code} (public validate endpoint — uniform 404 on negative cases)
  - POST /api/invite-codes/{code}/redeem (public redeem — PAT validation, Fernet encryption, auto-sync)
  - _REDEEM_RATE constant in limiter.py (5/10minutes per-IP, T-07-05)
  - All 12 AUTH-02 + API-04 integration tests passing (xfail markers removed)

affects:
  - 07-03 (frontend — invite link generation UI in ProfileDrawer, RedeemPage)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pool-isolation discipline: _run_test_sync HTTP call runs with NO pool slot held (Pitfall 1 / T-07-11)"
    - "Atomic single-use consume: UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id (T-07-06)"
    - "Uniform 404 oracle prevention: all negative invite cases return identical 404 invite_not_found (T-07-10)"
    - "Two-router split: owner_router (PIN-gated via require_admin) + public_router (no PIN, registered pre-StaticFiles)"
    - "_free_fake_account() pattern required before any redeem/sync test claiming the constant fake user_id"

key-files:
  created:
    - src/gruvax/api/invite_codes.py
  modified:
    - src/gruvax/api/admin/limiter.py
    - src/gruvax/api/admin/router.py
    - src/gruvax/app.py
    - tests/integration/test_invite_codes.py

key-decisions:
  - "D-01: 1-hour invite TTL via gen_random_uuid() + NOW() + INTERVAL '1 hour' in INSERT"
  - "D-09: void prior invite atomically in same transaction as INSERT (single active per profile)"
  - "D-10: token overwrite on re-redeem — COALESCE preserves existing user_id if set, no guard rejects existing token"
  - "D-04: background sync auto-starts after successful redeem (mirrors connect_pat)"
  - "Pool-isolation: _run_test_sync duplicated from profiles.py (private function — avoid cross-module private import)"
  - "L-05 runbook: member PAT travels over plaintext HTTP on home LAN — acceptable for home-LAN-only deployment; HTTPS required if ever exposed beyond the LAN"

# Metrics
duration: ~19min
completed: 2026-06-01
---

# Phase 7 Plan 02: AUTH-02 Backend — Invite-Code Endpoints Summary

**Single-use 1-hour invite link flow shipped: owner generates via PIN-gated endpoint; member redeems publicly with their own PAT; PAT validated against discogsography, Fernet-encrypted, stored; second/expired/invalid redeem returns uniform 404; redeem auto-starts the initial sync.**

## Performance

- **Duration:** ~19 min
- **Started:** 2026-06-01T17:12:54Z
- **Completed:** 2026-06-01T17:32:00Z
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- `src/gruvax/api/invite_codes.py` created with two routers:
  - `owner_router`: POST /profiles/{id}/invite — voids prior invite (D-09), inserts new UUID code 1-hour TTL (D-01), returns {code, url, expires_at}
  - `public_router`: GET /invite-codes/{code} (uniform 404 for all negative cases) + POST /invite-codes/{code}/redeem (rate-limited, atomic consume, pool-isolated PAT validation, Fernet encrypt, background sync)
- `_REDEEM_RATE = parse_limit("5/10minutes")` added to limiter.py (T-07-05)
- `owner_router` registered in create_admin_router() under /api/admin (PIN-gated)
- `public_router` registered in app.py before StaticFiles mount (Pitfall 8 / D-03)
- All 8 xfail AUTH-02 tests in test_invite_codes.py promoted to live tests; all 12 tests pass (0 failures)
- Full backend suite: 768 passed, 6 skipped, 0 failures (no Phase 1-6 regressions)

## Task Commits

1. **Task 1: invite_codes.py + limiter.py _REDEEM_RATE** - `d61f4ac` (feat)
2. **Task 2: Register routers + un-xfail AUTH-02 tests** - `3a4ef57` (feat)

## Files Created/Modified

- `src/gruvax/api/invite_codes.py` — new: owner_router + public_router with all three endpoints, pool-isolation discipline, atomic consume, Fernet storage, rate limiting
- `src/gruvax/api/admin/limiter.py` — added _REDEEM_RATE = parse_limit("5/10minutes")
- `src/gruvax/api/admin/router.py` — added invite_owner_router import + include_router call
- `src/gruvax/app.py` — added invite_public_router import + include_router before StaticFiles
- `tests/integration/test_invite_codes.py` — removed xfail markers; fixed test_redeem_rotates_token URL (/connect not /connect-pat); added _free_fake_account() calls to redeem tests

## Decisions Made

- Pool-isolation discipline exactly mirrors connect_pat flow: consume (pool checkout+release) → _run_test_sync (no pool slot) → collision check (pool checkout+release) → store (pool checkout+release) → background task
- `_run_test_sync` duplicated from profiles.py rather than importing a private function cross-module — avoids tight coupling to profiles internals
- `test_redeem_rotates_token` uses `/api/admin/profiles/{id}/connect` (not `/connect-pat`) — the correct route path per profiles.py
- `_free_fake_account(db_pool, profile_id)` called before any redeem test that triggers a sync to avoid uq_profiles_dgs_user_id_active constraint collision (fake returns constant user_id)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed wrong endpoint URL in test_redeem_rotates_token**
- **Found during:** Task 2 test run (connect-pat returned 404 → test was being skipped)
- **Issue:** The scaffold used `/api/admin/profiles/{id}/connect-pat` which doesn't exist; the real endpoint is `/api/admin/profiles/{id}/connect`
- **Fix:** Updated the URL and skip message in test_redeem_rotates_token
- **Files modified:** tests/integration/test_invite_codes.py
- **Commit:** 3a4ef57

**2. [Rule 2 - Missing Critical Functionality] Added _free_fake_account() to redeem tests**
- **Found during:** Task 2 test design
- **Issue:** Wave-1 context explicitly warned that redeem tests triggering sync must call `_free_fake_account()` before the redeem to avoid uq_profiles_dgs_user_id_active collision. The scaffold was missing these calls in test_redeem_success, test_redeem_second_use_rejected, and test_redeem_rotates_token.
- **Fix:** Added `db_pool` fixture parameter and `await _free_fake_account(db_pool, _DEFAULT_PROFILE_UUID)` calls to the three affected tests
- **Files modified:** tests/integration/test_invite_codes.py
- **Commit:** 3a4ef57

## Security Notes (Threat Register)

All mitigations from the plan's threat register implemented:

| Threat ID | Mitigation Implemented |
|-----------|----------------------|
| T-07-05 | UUID4 code (gen_random_uuid) + per-IP rate limit 5/10min (_REDEEM_RATE, "invite_redeem" namespace) |
| T-07-06 | Atomic UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id |
| T-07-07 | Redeem returns {status, profile_id} only; no PAT in response |
| T-07-08 | No PAT in any log line or error detail string; structlog redactor is defense-in-depth |
| T-07-09 | encrypt_pat() (Fernet/authenticated encryption) before bytea write |
| T-07-10 | All negative invite cases return uniform 404 {type: invite_not_found} |
| T-07-11 | _run_test_sync runs outside pool.connection() context (pool-isolation discipline) |
| T-07-12 | D-10 accepted: token overwrite safe because only owner can mint the invite |

**L-05 Runbook Note:** Member PAT travels over plaintext HTTP on the home LAN during POST /api/invite-codes/{code}/redeem. This is acceptable for home-LAN-only deployment (no public exposure). HTTPS is required if the API is ever exposed beyond the LAN.

## Known Stubs

None — all endpoints are fully implemented and wired.

## Threat Flags

No new threat surfaces introduced beyond those already in the plan's threat register. The two new public endpoints (GET + POST /api/invite-codes/*) are in the threat model as T-07-05 through T-07-11.

---
*Phase: 07-member-self-connect-collection-diff*
*Completed: 2026-06-01*

## Self-Check: PASSED

### Files exist:
- src/gruvax/api/invite_codes.py: FOUND
- src/gruvax/api/admin/limiter.py: FOUND (modified)
- src/gruvax/api/admin/router.py: FOUND (modified)
- src/gruvax/app.py: FOUND (modified)
- tests/integration/test_invite_codes.py: FOUND (modified)
- .planning/phases/07-member-self-connect-collection-diff/07-02-SUMMARY.md: FOUND

### Commits exist:
- d61f4ac: feat(07-02): implement invite_codes.py with owner generate + public validate + public redeem
- 3a4ef57: feat(07-02): register invite routers + un-xfail AUTH-02 integration tests

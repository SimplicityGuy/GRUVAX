---
phase: 07-member-self-connect-collection-diff
verified: 2026-06-01T19:00:00Z
status: passed
score: 19/19
overrides_applied: 0
---

# Phase 7: Member Self-Connect + Collection Diff Verification Report

**Phase Goal:** Member Self-Connect + Collection Diff — invite-token flow (member pastes their own Discogs PAT via a one-time invite link); a "N new records" badge/pill after sync; migration 0012 folded in.
**Verified:** 2026-06-01T19:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Migration 0012 exists with profile_invite_codes table (UUID PK, FK ON DELETE CASCADE, expires_at, consumed_at), profile_collection.first_seen_at, and profiles.last_new_record_count + last_sync_is_initial | VERIFIED | `migrations/versions/0012_invite_codes_and_first_seen_at.py` lines 52–102 — all five DDL constants present and correct; revision="0012", down_revision="0011" |
| 2 | After any sync, collection_changed SSE payload includes new_record_count (int >= 0) and is_initial_import (bool) | VERIFIED | `src/gruvax/sync/profile_sync.py` lines 404–409 — bus.publish("collection_changed", {profile_id, new_record_count, is_initial_import}) |
| 3 | First-ever sync reports is_initial_import=true; subsequent syncs report false | VERIFIED | `profile_sync.py` lines 301–308 — reads `last_sync_at IS NULL` BEFORE the UPDATE that sets last_sync_at (Pitfall 4 correctly applied) |
| 4 | new_record_count equals genuinely new releases (arrivals only, never negative) | VERIFIED | `profile_sync.py` line 324 — `new_record_count = max(0, row_count - existing_count)` with pre-DELETE scalar COUNT join (Pitfall 9 / D-06) |
| 5 | Admin profiles list/get exposes has_token (bool) and never the raw/encrypted PAT | VERIFIED | `profiles.py` lines 195–199 — derives `has_token` in SQL as `(app_token_encrypted IS NOT NULL AND length > 1)::bool`; ciphertext not in SELECT projection; confirmed in both list_profiles and get_profile |
| 6 | Admin profiles list/get exposes last_new_record_count and last_sync_is_initial | VERIFIED | `profiles.py` lines 195–239 and 255–303 — both endpoints include both fields in response dict |
| 7 | Admin diagnostics API exposes last_new_record_count and last_sync_is_initial per profile | VERIFIED | `diagnostics.py` lines 104–126 — SELECT includes both columns; each profile_diagnostics dict includes both fields |
| 8 | Diff state persists across requests until the next sync (D-08) | VERIFIED | `profile_sync.py` lines 341–354 — UPDATE profiles atomically sets last_new_record_count + last_sync_is_initial inside _swap_inside_tx alongside other sync fields |
| 9 | Owner can POST /api/admin/profiles/{id}/invite (PIN-gated), receive {code, url, expires_at}, 1-hour TTL | VERIFIED | `invite_codes.py` lines 180–243 — owner_router endpoint with Depends(require_admin); _INSERT_INVITE uses NOW() + INTERVAL '1 hour' |
| 10 | Generating a new invite voids prior unredeemed invite (one active per profile) | VERIFIED | `invite_codes.py` lines 73–79, 222 — _VOID_PRIOR_INVITE runs before _INSERT_INVITE in same transaction |
| 11 | Public GET /api/invite-codes/{code} returns profile display_name; uniform 404 for all negative cases | VERIFIED | `invite_codes.py` lines 249–278 — _SELECT_INVITE filters consumed_at IS NULL AND expires_at > NOW(); invalid UUID raises 404 via _parse_invite_uuid |
| 12 | Public POST /api/invite-codes/{code}/redeem: rate-limited, single-use atomic consume, PAT validated/encrypted, auto-sync | VERIFIED | `invite_codes.py` lines 284–396 — rate limit checked first; atomic _CONSUME_INVITE; pool-isolation discipline (step 1 pool released before step 2 HTTP); Fernet encrypt; background_tasks.add_task |
| 13 | Second redeem of same code returns 404; expired/invalid codes return uniform 404 | VERIFIED | `invite_codes.py` lines 318–328 — _CONSUME_INVITE WHERE consumed_at IS NULL AND expires_at > NOW() returns no row on second call or expired code; all raise 404 invite_not_found |
| 14 | WR-02: redeem 503 handlers use static messages, not str(exc) | VERIFIED | `invite_codes.py` lines 342–353 — both RateLimitExhausted and (ServerError, NetworkError) raise with hardcoded message string "Discogs is temporarily unavailable. Please try again shortly."; no str(exc) in detail |
| 15 | WR-03: generate_invite existence preflight guards against FK violation on soft-deleted/unknown profiles | VERIFIED | `invite_codes.py` lines 209–218 — SELECT 1 FROM gruvax.profiles WHERE id = %s AND deleted_at IS NULL; 404 if not found |
| 16 | Frontend /redeem/:code public page exists (5 states: loading/active/invalid/submitting/success), wired to public endpoints | VERIFIED | `frontend/src/routes/redeem/RedeemPage.tsx` (265 lines) — success state at lines 160–165: "CONNECTED" heading + "Your collection is importing. You can close this page."; route at App.tsx line 142 outside /admin nest |
| 17 | Owner invite affordance in ProfileDrawer with TTL countdown and copy-to-clipboard | VERIFIED | `ProfileDrawer.tsx` — generateInvite called at line 338; setInterval TTL countdown at lines 280–302; navigator.clipboard.writeText at line 352; INVITE LINK section at line 558 |
| 18 | Admin diagnostics NEW RECORDS / IMPORTED row driven by last_new_record_count; WR-04 deriveProfileStatus maps failed→pending | VERIFIED | `ProfileDiagnosticsCard.tsx` line 35 — `if (profile.last_sync_status === 'failed') return 'pending'`; NEW RECORDS row at line 102+; WR-05 types.ts line 398 — `last_new_record_count: number | null` |
| 19 | Kiosk yellow new-records pill from collection_changed SSE payload; WR-04/05/frontend review fixes all applied | VERIFIED | `KioskView.tsx` lines 346–374 — collection_changed handler takes (e: MessageEvent), defensively parses e.data, no es.close() inside handler; newRecordState state drives pill at lines 608–621 |

**Score:** 19/19 truths verified

---

## Required Artifacts

| Artifact | Status | Evidence |
|----------|--------|----------|
| `migrations/versions/0012_invite_codes_and_first_seen_at.py` | VERIFIED | Exists, 137 lines; all required DDL constants present; revision="0012", down_revision="0011"; no f-strings in upgrade/downgrade |
| `src/gruvax/api/invite_codes.py` | VERIFIED | Exists, 396 lines (>120 required); owner_router + public_router defined; all SQL as module-level constants; no f-strings interpolating SQL |
| `src/gruvax/sync/profile_sync.py` | VERIFIED | _swap_inside_tx returns tuple[int, bool]; new_record_count; is_initial_import; _refresh_profile_caches accepts and publishes both |
| `src/gruvax/api/admin/profiles.py` | VERIFIED | has_token derived in SQL; last_new_record_count + last_sync_is_initial in list and get responses |
| `src/gruvax/api/admin/diagnostics.py` | VERIFIED | last_new_record_count + last_sync_is_initial in per-profile diagnostics SELECT and response dict |
| `src/gruvax/api/admin/router.py` | VERIFIED | invite_owner_router imported and registered at line 57 inside create_admin_router() |
| `src/gruvax/app.py` | VERIFIED | invite_public_router registered at line 488 with prefix="/api" before StaticFiles mount at line 497 |
| `src/gruvax/api/admin/limiter.py` | VERIFIED | _REDEEM_RATE = parse_limit("5/10minutes") at line 51 |
| `frontend/src/api/inviteClient.ts` | VERIFIED | 123 lines; publicFetch with credentials 'omit'; getInviteCode, redeemInviteCode (public), generateInvite (adminFetch) |
| `frontend/src/routes/redeem/RedeemPage.tsx` | VERIFIED | 265 lines; contains "CONNECTED"; success terminal state correct; 5-state machine |
| `frontend/src/routes/redeem/RedeemPage.css` | VERIFIED | Exists; no hardcoded hex (grep returned empty) |
| `frontend/src/api/types.ts` | VERIFIED | AdminProfile extended with has_token: boolean, last_new_record_count: number \| null, last_sync_is_initial: boolean |
| `frontend/src/routes/admin/ProfileDrawer.tsx` | VERIFIED | INVITE LINK section, TTL countdown, clipboard, generateInvite import |
| `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` | VERIFIED | deriveProfileStatus maps failed→pending (WR-04); NEW RECORDS / IMPORTED row |
| `frontend/src/routes/kiosk/KioskView.tsx` | VERIFIED | new_record_count parsed from SSE; newRecordState drives pill; no es.close() in handler |

---

## Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `profile_sync.py::_swap_inside_tx` | `profile_sync.py::_refresh_profile_caches` | `(new_record_count, is_initial_import)` tuple returned and passed as keyword args | VERIFIED |
| `profile_sync.py::_refresh_profile_caches` | EventBus.publish collection_changed | `await bus.publish("collection_changed", {profile_id, new_record_count, is_initial_import})` | VERIFIED |
| `invite_codes.py redeem endpoint` | `gruvax.profile_invite_codes` | `_CONSUME_INVITE UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id` | VERIFIED |
| `invite_codes.py redeem endpoint` | `_run_test_sync + encrypt_pat + _run_sync_background` | pool released → _run_test_sync (no pool slot) → encrypt_pat(body.pat) → background_tasks.add_task | VERIFIED |
| `src/gruvax/app.py` | invite_codes public_router | `app.include_router(invite_public_router, prefix="/api")` at line 488, before StaticFiles at line 497 | VERIFIED |
| `frontend/src/App.tsx` | RedeemPage at /redeem/:code | `<Route path="/redeem/:code" element={<RedeemPage />} />` at line 142 outside /admin nest | VERIFIED |
| `frontend/src/routes/kiosk/KioskView.tsx` | collection_changed SSE payload | `JSON.parse(e.data)` reads `payload.new_record_count` in collection_changed handler | VERIFIED |
| `frontend/src/routes/admin/ProfileDrawer.tsx` | POST /api/admin/profiles/{id}/invite | `generateInvite(profileId)` + `navigator.clipboard.writeText(inviteInfo.url)` | VERIFIED |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| AUTH-02 | 07-02, 07-03 | Owner issues 1-hour single-use invite; member redeems with their own PAT; PAT Fernet-encrypted; owner sees only has_token; second/expired/invalid redeem returns uniform 404; auto-sync starts | SATISFIED | invite_codes.py owner_router + public_router fully implemented; all 12 integration tests pass per SUMMARY; human-verify checkpoint approved |
| API-04 | 07-01, 07-03 | Kiosk and admin surface per-profile "N new records since last sync"; diff count computed in staging-swap; delivered on collection_changed SSE payload | SATISFIED | _swap_inside_tx computes new_record_count + is_initial_import; collection_changed payload extended; admin profiles/diagnostics expose stored diff; kiosk pill and admin diagnostics row verified |

---

## Anti-Patterns Found

No debt markers (TBD, FIXME, XXX) found in any phase-7 modified files. No hardcoded hex in RedeemPage.css or kiosk.css new-records pill section. No empty return stubs or placeholder implementations identified.

---

## Human Verification

**Status: Previously approved by developer.**

The phase 07-03 plan included a `checkpoint:human-verify` task (Task 3, gate=blocking) covering 6 surfaces. Per the SUMMARY.md, the developer approved all 6 surfaces:

1. INVITE GENERATION (admin ProfileDrawer) — verified
2. REDEEM flow (member, incognito browser) — verified
3. SINGLE-USE: reload after redemption — verified (error card, no form)
4. DIFF INDICATOR (admin diagnostics card) — verified
5. KIOSK PILL after sync — verified
6. No raw PAT visible in admin UI — verified

No outstanding human verification items remain.

---

## Gaps Summary

No gaps. All must-haves verified against the actual codebase.

---

_Verified: 2026-06-01T19:00:00Z_
_Verifier: Claude (gsd-verifier)_

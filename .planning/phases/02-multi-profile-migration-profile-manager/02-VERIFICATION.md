---
phase: 02-multi-profile-migration-profile-manager
verified: 2026-05-29T21:00:00Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed:
    - "After connecting/syncing a profile, the admin drawer transitions SYNCING → CONNECTED with a completion toast without a manual refresh (02-08)"
    - "A user can tell whether a profile's cube highlighting is unavailable because the shelf layout isn't configured (02-09)"
    - "ResultsList passes bound profile_id to both locate calls so /api/locate never 422s (02-09 root-cause fix)"
  gaps_remaining: []
  regressions: []
---

# Phase 2: Multi-profile Migration + Profile Manager — Re-Verification Report (Post Gap-Closure)

**Phase Goal:** Multiple owner-managed profiles operate independently with their own collection caches, boundaries, segments, settings, LED config, and stats; browser sessions on LAN can choose which profile to view; admin can create, connect, rotate, rename, and soft-delete profiles.
**Verified:** 2026-05-29T21:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure plans 02-08 (poll-until-terminal) and 02-09 (shelf-layout-unconfigured affordance + ResultsList root-cause fix)

---

## Context

The phase was initially verified passed and then underwent user-driven UAT (02-UAT.md) that found two issues:

- **Test 8 (major):** Admin sync drawer stuck on SYNCING; never auto-transitioned to CONNECTED + toast without manual refresh. Closed by plan 02-08. Live-approved by user.
- **Test 5 (minor):** Kiosk showed no affordance when a result IS in the collection but the profile has zero cube boundaries. Additionally, `ResultsList` was calling `locateRelease` without `profile_id`, causing every auto-locate/select to 422 silently — the real root cause. Closed by plan 02-09. Live-approved by user.

This re-verification confirms: (1) the original 5 ROADMAP Success Criteria still hold, and (2) the two gap-closure must_haves are satisfied in the codebase.

---

## Goal Achievement

### Observable Truths

#### Original ROADMAP Success Criteria (5) — Regression Check

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Owner can create/connect/sync a profile and see async sync complete with last_sync_status='ok' (SC#1) | VERIFIED | `profiles.py` + `profile_sync.py` backend unchanged. Original automated tests still pass (50/50 frontend suite). |
| 2 | Two browser sessions on LAN show different profiles; single-profile deployment auto-binds and skips picker (SC#2) | VERIFIED | Session/bind/unbind backend unchanged. `ProfilePicker.tsx`, `SwitchProfileButton.tsx`, `SwitchProfileConfirm.tsx` unchanged. UAT tests 2, 3, 4 passed live. |
| 3 | profile_id NOT NULL migration: 5 data tables tightened, 2 infra tables stay nullable, composite PKs rebuilt, round-trip clean (SC#3) | VERIFIED | Migration 0010 unchanged since initial verification. |
| 4 | Per-profile SSE /api/events/{profile_id} invalidates only affected profile's caches; cross-profile leakage impossible by construction (SC#4) | VERIFIED | SSE routing and event bus wiring unchanged. Documented WARNING (admin boundary_changed is default-profile-only via P1-compat alias) still present and still not a leakage. |
| 5 | p95 /api/search ≤ 200 ms and /api/locate ≤ 50 ms SLOs hold with 2+ profiles cached (SC#5) | VERIFIED | Backend SLO code paths unchanged. WARNING (second_profile fixture not wired as dep) still present; not a regression. |

#### Gap-Closure Must-Haves (02-08 + 02-09)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 6 | After connecting/syncing a profile, the admin drawer transitions SYNCING → CONNECTED with a completion toast without a manual refresh | VERIFIED | `ProfileDrawer.tsx` lines 132–135: `refetchInterval` returns `false` only for `'ok'` or `'failed'`; returns `2000` for everything else including `null` and `'in_progress'`. `ProfileDrawer.test.tsx` 3/3 tests pass including transient-tick regression test. Live-approved by user. |
| 7 | Selecting a search result whose record IS in the collection but lands no cube shows a 'shelf layout not configured' affordance instead of a silent no-op | VERIFIED | `store.ts` line 144: `shelfLayoutUnavailable: result.primary_cube == null && result.confidence === 0`; reset on `clearSearch`. `ShelfLayoutNotConfigured.tsx` exists (35 lines, no hardcoded hex). `KioskView.tsx` line 509: renders `<ShelfLayoutNotConfigured />` when `shelfLayoutUnavailable && !isEmptyCollection && selectedReleaseId != null`. `ResultsList.tsx` lines 75, 97: both locate paths pass `useSessionStore.getState().boundProfileId`. `ShelfLayoutNotConfigured.test.tsx` 10/10 pass. Live-approved by user. |

**Score:** 7/7 truths verified

---

### Required Artifacts — Gap-Closure Plans

#### 02-08 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/routes/admin/ProfileDrawer.tsx` | Poll-until-terminal `refetchInterval` (stop only on 'ok'/'failed') | VERIFIED | Lines 132–135: `const status = query.state.data?.last_sync_status` / `return status === 'ok' \|\| status === 'failed' ? false : 2000`. Contains `refetchInterval`. |
| `frontend/src/routes/admin/ProfileDrawer.test.tsx` | Vitest poll-sequence regression test | VERIFIED | 3 tests: transient-tick → ok → transition + toast; failed path; call-count assertion across transient sequence. 3/3 pass. |
| `src/gruvax/api/admin/profile_sync.py` | Atomic in_progress→terminal write semantics documented | VERIFIED | Module-level docstring (lines 1–28) documents poller contract, audited transition sequence (null → in_progress → ok\|failed), and `_swap_inside_tx` atomicity. |

#### 02-09 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `frontend/src/routes/kiosk/ShelfLayoutNotConfigured.tsx` | Nordic-Grid affordance, plain-language copy, tokens only | VERIFIED | 35 lines. Heading "Shelf layout not set up yet", body paragraph with plain-language explanation. CSS classes `shelf-layout-unconfigured` / `__heading` / `__body` — no hardcoded hex. |
| `frontend/src/routes/kiosk/ShelfLayoutNotConfigured.test.tsx` | Vitest test: affordance renders on null-cube/zero-confidence locate result | VERIFIED | 10 tests covering store flag set/reset, component render, class names, and no-inline-hex assertion. 10/10 pass. |
| `frontend/src/state/store.ts` | `shelfLayoutUnavailable` derived flag set when locate returns null primary_cube + 0 confidence | VERIFIED | Lines 71, 144, 149, 161: field declared in interface, set inside `setLocateResult`, initialized `false`, reset in `clearSearch`. |

---

### Key Link Verification — Gap-Closure Plans

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `frontend/src/routes/admin/ProfileDrawer.tsx` | `getAdminProfile` poll | TanStack Query `refetchInterval` returning `2000` unless status terminal | VERIFIED | Line 132: `refetchInterval: (query) => { const status = query.state.data?.last_sync_status; return status === 'ok' \|\| status === 'failed' ? false : 2000 }` |
| `frontend/src/routes/kiosk/KioskView.tsx` | `ShelfLayoutNotConfigured` | Render when `shelfLayoutUnavailable && !isEmptyCollection && selectedReleaseId != null` | VERIFIED | Lines 11, 509–511: import confirmed, conditional render with all three guards present. |
| `frontend/src/state/store.ts` | `setLocateResult` | Sets `shelfLayoutUnavailable = (primary_cube == null && confidence === 0)` | VERIFIED | Line 144: `shelfLayoutUnavailable: result.primary_cube == null && result.confidence === 0` |
| `frontend/src/routes/kiosk/ResultsList.tsx` | `/api/locate` (both paths) | `useSessionStore.getState().boundProfileId` passed as `profile_id` | VERIFIED | Lines 75, 97: both auto-select and explicit-select paths read `boundProfileId` via `getState()` (stale-closure-safe) and pass it to `locateRelease`. |

---

### Data-Flow Trace (Level 4) — Gap-Closure Additions

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `ProfileDrawer.tsx` `polledProfile` | `last_sync_status` | TanStack Query `refetchInterval: 2000 unless terminal` → `GET /api/admin/profiles/{id}` → live DB row | Yes — live DB query, terminal status written atomically by `_swap_inside_tx` | FLOWING |
| `KioskView.tsx` `shelfLayoutUnavailable` | store flag | `setLocateResult` ← `locateRelease(id, boundProfileId)` ← `/api/locate?profile_id=...` → per-profile segment cache | Yes — HTTP 200 response with `primary_cube:null, confidence:0.0` from real locate path | FLOWING |
| `ResultsList.tsx` locate path | `boundProfileId` | `useSessionStore.getState().boundProfileId` ← `POST /api/session/bind` ← `gruvax.profiles` DB | Yes — resolves to live profile UUID from DB-backed session | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ProfileDrawer regression tests (poll-until-terminal) | `npx vitest run src/routes/admin/ProfileDrawer.test.tsx` | 3/3 pass | PASS |
| ShelfLayoutNotConfigured + store flag tests | `npx vitest run src/routes/kiosk/ShelfLayoutNotConfigured.test.tsx` | 10/10 pass | PASS |
| Full frontend suite | `npx vitest run` | 50/50 pass (7 test files) | PASS |
| TypeScript compile | `npx tsc -b` | Clean, no errors | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROF-01 | 02-05 | `profiles` table with Fernet PAT storage, soft-delete, partial-unique indexes | SATISFIED | Unchanged from initial verification. `profiles.py` confirmed. |
| PROF-02 | 02-05, 02-07, 02-08, 02-09 | Profile manager admin UI: list/create/connect/rotate/rename/soft-delete + sync feedback + kiosk affordance for unconfigured profile | SATISFIED | 02-08 added poll-until-terminal to close the sync-feedback gap. 02-09 added `ShelfLayoutNotConfigured` affordance and ResultsList root-cause fix. Both live-approved. |
| PROF-04 | 02-01 | `profile_id NOT NULL` migration (5 data tables; 2 infra stay nullable) | SATISFIED | Migration 0010 unchanged. |
| API-02 | 02-02, 02-03 | Positioning/search/locate off per-profile cache; p95 SLOs with 2+ profiles | SATISFIED with WARNING | Unchanged; WARNING (fixture dep not enforced) documented. 02-09 additionally fixed locate calls in ResultsList to always carry `profile_id` — the prior 422-silent-failure was masking the full correctness of this path. |
| SYN-02 | 02-02, 02-03, 02-04 | Staleness = `now() - profiles.last_sync_at` per profile; banner per-kiosk-view per-profile | SATISFIED | Unchanged from initial verification. |

All 5 required requirement IDs (PROF-01, PROF-02, PROF-04, API-02, SYN-02) accounted for.

---

### Anti-Patterns Found

No new TBD / FIXME / XXX markers introduced in 02-08 or 02-09 files. Previously documented warnings carry over unchanged:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/gruvax/api/admin/cubes.py` | 260, 679 | `Depends(get_event_bus)` — P1-compat single-instance bus | WARNING | `boundary_changed` events from admin edits publish only to default profile SSE bus. No cross-profile leakage. Documented in `app.py:270-278`. |
| `src/gruvax/api/admin/segments.py` | 200, 337, 468 | `Depends(get_event_bus)` | WARNING | Same as above. |
| `src/gruvax/api/admin/editing.py` | 63 | `Depends(get_event_bus)` | WARNING | Same as above. |
| `src/gruvax/api/admin/history.py` | 94 | `Depends(get_event_bus)` | WARNING | Same as above. |
| `src/gruvax/api/admin/import_.py` | 158 | `Depends(get_event_bus)` | WARNING | Same as above. |
| `frontend/src/routes/admin/BinWidthEditor.tsx` | 442 | Missing `useEffect` dep `updateCaption` | INFO | Pre-existing; unrelated to Phase 2. |
| `tests/integration/test_search_benchmark.py` | 57 | `search_client(db_pool)` — `second_profile` not declared as fixture dep | WARNING | Unchanged. |

---

### Human Verification Required

The 7 original UAT items were completed live by the user on 2026-05-28 (see `02-HUMAN-UAT.md`). The two gap-closure plans each included `checkpoint:human-verify` tasks that were also live-approved by the user (recorded in `02-08-SUMMARY.md` and `02-09-SUMMARY.md`).

**No further human verification is required.**

---

### Gaps Summary

**No blockers.** All 7 must-haves verified.

The two UAT gaps are closed:

1. **02-08 (test 8):** Poll-until-terminal `refetchInterval` in `ProfileDrawer.tsx` now stops only on `'ok'`/`'failed'`, passing through `'in_progress'`, `null`, and any transient value. Backend terminal-write atomicity documented. 3/3 regression tests pass. Live-approved.

2. **02-09 (test 5):** `ShelfLayoutNotConfigured` affordance renders when `shelfLayoutUnavailable && !isEmptyCollection && selectedReleaseId != null`. Root-cause fix: `ResultsList.tsx` now passes `boundProfileId` to both locate code paths so `/api/locate` never 422s silently. 10/10 tests pass. Live-approved.

Documented warnings from initial verification are unchanged: P1-compat `get_event_bus` in admin boundary endpoints, `second_profile` fixture dep not enforced in benchmark. Neither blocks the phase goal.

---

_Verified: 2026-05-29T21:00:00Z_
_Verifier: Claude (gsd-verifier) — re-verification after gap-closure plans 02-08 + 02-09_

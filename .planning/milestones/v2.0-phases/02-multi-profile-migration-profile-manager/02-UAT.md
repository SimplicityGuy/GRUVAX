---
status: resolved
phase: 02-multi-profile-migration-profile-manager
source: [02-01-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md, 02-05-SUMMARY.md, 02-06-SUMMARY.md, 02-07-SUMMARY.md]
started: 2026-05-28
updated: 2026-05-29
mode: user-driven
note: independent of 02-HUMAN-UAT.md (automated run). Stack live at http://localhost:8000.
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: With the stack started from scratch (`docker compose up -d`), the API container reaches healthy, alembic is at head 0010 (migration 0011 removed), and `GET /api/health` + `GET /api/session` return live JSON without errors.
result: pass

### 2. Single-profile auto-bind
expected: With exactly one active profile and a fresh browser (no cookie), opening the kiosk at `/` goes straight to the search UI — no `/select` flash — and the Switch-profile button is hidden.
result: pass

### 3. Multi-profile picker (/select)
expected: With 2+ active profiles and no cookie, the kiosk redirects to `/select` showing one card per profile under "CHOOSE A COLLECTION", each with record count + sync status. Tapping a card binds it and lands on `/`.
result: pass

### 4. Switch profile + confirm
expected: On the kiosk with 2+ profiles, the "SWITCH" button (bottom-right) opens a "Switch collection?" confirm modal; SWITCH returns to `/select`, STAY HERE dismisses.
result: pass

### 5. Search within a synced profile
expected: Bound to a synced profile (e.g. LiveVerify, 3,000 records), typing an artist/label/title in the search box returns matches and highlights the correct cube on the grid within ~200 ms.
result: issue
reported: "all artists show as [screenshot — results render fine]; the bin doesn't light up"
severity: minor
diagnosis: |
  Search scoping WORKS (results render, profile-scoped). The cube did not light up because
  LiveVerify has 0 cube_boundaries (Default has 32). Boundaries are admin-configured per profile
  and are NOT created by sync, so a freshly-created+synced profile has no shelf layout for locate
  to map records onto. Verified the locate→cube path is functional on Default:
  /api/locate?release_id=1351 → primary_cube {unit_id:1,row:1,col:1}, confidence 0.85.
  Root cause is missing-boundaries (expected for a new profile) + a UX-feedback gap (no affordance
  telling the user the shelf layout isn't configured for this profile).

### 6. Empty-collection state (unsynced profile)
expected: Bound to an unsynced profile (Default), the results area shows "No records yet / This collection is syncing…" (not "No results") and the shelf grid renders dim/empty.
result: pass

### 7. Admin — create profile
expected: At `/admin` (PIN), the PROFILES tab shows a profile list with status badges and a "+ ADD PROFILE" row. Adding a name creates a PENDING profile that appears in the list.
result: pass

### 8. Admin — connect PAT → sync feedback
expected: Connecting a PAT shows CONNECTING… → SYNCING (animated badge, ~2s poll, "N items processed") → CONNECTED, with a "Sync complete — N,### records" toast. A duplicate-account token is rejected with plain-language copy (no HTTP codes).
result: issue
reported: "we never exit this screen [Syncing… 3,000 items processed]; but a refresh shows synced"
severity: major
notes: Partial — duplicate-account 409 copy correct (no HTTP codes); CONNECTING → SYNCING reached + PAT encryption help copy correct. BUT the drawer never transitions SYNCING → CONNECTED/complete + toast; a manual page refresh shows it connected.
diagnosis: |
  Backend is correct: GET /api/admin/profiles/{id} returns last_sync_status:"ok", status:"connected",
  last_sync_item_count:3000 after sync. The bug is the frontend poll in
  frontend/src/routes/admin/ProfileDrawer.tsx (lines ~122-128):
    refetchInterval: (query) => query.state.data?.last_sync_status === 'in_progress' ? 2000 : false
  This stops polling on ANY non-'in_progress' value. Combined with non-atomic backend updates of
  last_sync_item_count vs last_sync_status (item_count reaches 3000 before/around the status flip),
  the poll can fetch a transient non-'in_progress', non-'ok' row and halt — so the terminal 'ok' is
  never observed and the useEffect (status==='ok' → setConnectState('idle')+toast) never fires.
  Manual refresh re-fetches and catches 'ok'. Fix: poll UNTIL terminal — refetchInterval should
  return 2000 unless status is 'ok' or 'failed' (i.e. keep polling through pending/transient states),
  and/or make the backend item_count+status write atomic.

### 9. Admin — rotate PAT
expected: ROTATE PAT with a same-account token succeeds; a different-account token is rejected with "This token belongs to a different account…".
result: pass
notes: Same-account rotate verified live (succeeds). Different-account rejection not exercisable on the single-account dev fake; covered by automated test suite.

### 10. Admin — rename profile
expected: Renaming a profile updates its name in the list (and the /select picker); a duplicate name is rejected.
result: pass

### 11. Admin — soft-delete profile
expected: DELETE shows a confirm modal ("Delete this profile? … permanently remove {NAME} and its N,### records. This cannot be undone."); confirming removes it from the list and from the /select picker. The Default profile cannot be deleted.
result: pass

### 12. Profile status badges
expected: Badges reflect live state — CONNECTED (green), PENDING (amber), SYNCING (blue, pulsing), RE-AUTH REQUIRED (red) — and update as a profile's state changes.
result: pass

## Summary

total: 12
passed: 10
issues: 2
pending: 0
skipped: 0

## Gaps

- truth: "A user can tell whether a profile's cube highlighting is unavailable because the shelf layout isn't configured (vs. search being broken)"
  status: resolved
  reason: "User reported: bin doesn't light up. Diagnosis: LiveVerify has 0 cube_boundaries; locate path verified working on Default. No in-kiosk affordance signals an unconfigured shelf layout, and there is no clear path for a newly-created profile to acquire boundaries."
  severity: minor
  test: 5
  artifacts: [src/gruvax/api/locate.py, frontend/src/routes/kiosk/KioskView.tsx, src/gruvax/api/admin/profiles.py]
  missing: ["kiosk affordance for 'shelf layout not configured for this profile'", "onboarding path to configure cube boundaries for a new profile"]

- truth: "After connecting/syncing a profile, the admin drawer transitions SYNCING → CONNECTED with a completion toast without a manual refresh"
  status: resolved
  reason: "User reported: sync drawer stuck on 'Syncing… 3,000 items processed'; refresh shows synced. ProfileDrawer.tsx refetchInterval polls only while last_sync_status==='in_progress' and stops on any other value, so a transient/non-atomic status update halts polling before the terminal 'ok' is observed."
  severity: major
  test: 8
  artifacts: [frontend/src/routes/admin/ProfileDrawer.tsx, src/gruvax/sync/profile_sync.py, src/gruvax/api/admin/profile_sync.py]
  missing: ["poll-until-terminal refetchInterval (stop only on 'ok'/'failed')", "atomic last_sync_item_count + last_sync_status write at sync completion"]

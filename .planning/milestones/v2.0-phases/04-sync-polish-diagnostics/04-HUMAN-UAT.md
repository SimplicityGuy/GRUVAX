---
status: passed
phase: 04-sync-polish-diagnostics
source: [04-VERIFICATION.md]
started: 2026-05-30
updated: 2026-05-30
---

## Current Test

[complete — interactive UAT run 2026-05-30 against local uvicorn + gruvax-dev-pg via Playwright]

## Tests

### 1. Re-auth badge + kiosk banner end-to-end (SYN-02 / SC2)
expected: After revoking a profile's PAT and triggering a sync, the Profiles admin UI shows a re-auth-required badge on the affected profile AND the kiosk renders an inline banner directing the owner to rotate the connection (jargon-free copy). After a successful rotate + test sync, both the badge and banner auto-clear on the next list/session read.
result: PASS (surfacing). Kiosk banner renders with `role="alert"` and exact jargon-free copy; `/api/session` returns `needs_reauth:true` for the revoked bound profile. Profiles-list re-auth badge initially showed PENDING after a real 401 (gap — see Gaps) and was FIXED + verified live (RE-AUTH REQUIRED). The rotate→auto-clear half (D4-09) is code-verified (connect_pat/rotate_pat already reset app_token_revoked=FALSE) and requires a live discogsography PAT to exercise end-to-end.

### 2. Kiosk banner is non-blocking (SYN-02 / SC2 / D4-10)
expected: With the re-auth banner visible on the kiosk, the search input, cube grid, and all kiosk interactivity remain fully live.
result: PASS. Typed "Miles Davis" into the search box with the banner visible; input accepted text (Clear button appeared) and the A1–H4 cube grid stayed fully interactive. Nothing gated on needs_reauth.

### 3. Diagnostics cards — Nordic Grid typography (SYN-02 / SC3)
expected: /admin/diagnostics shows a per-profile PROFILES section with LAST SYNC, STATUS, ITEMS, LAST ERROR per non-deleted profile in Nordic Grid styling.
result: PASS. PROFILES section renders below system diagnostics with a card per profile (4 data rows + status badge showing RE-AUTH REQUIRED). Structured logs + log-ring buffer + PAT redaction (`pin_attempt=redacted`) visible in RECENT LOGS.

### 4. Sync now — spinner + elapsed + completion toast (SYN-02 / SC5 / D4-17)
expected: "Sync now" shows an indeterminate spinner + elapsed-seconds counter until terminal, then a completion toast.
result: CODE-VERIFIED (not exercised live). No live discogsography available locally to drive a real sync. Verifier confirmed SyncProgressSection has the `syncStartedAt` prop + 1s `setInterval` elapsed counter and ProfileDrawer wires the completion toast.

### 5. Cadence select persists across reload (SYN-01 / SC1 / D4-06)
expected: Changing the sync cadence auto-saves and persists across reload/restart; takes effect on the next loop tick without restart.
result: PASS. Set cadence to 12h via the select; upserted to a single row under the default-profile UUID (composite PK); the select reflects "Every 12 hours". Nightly loop confirmed sleep-first live (`next_fire=03:00`, no sync-on-boot) and re-reads cadence each tick.

## Summary

total: 5
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0
code_verified: 1

## Gaps

- **[RESOLVED] Profiles-list re-auth badge unreachable after a real 401 (SC2 / D4-07).** `_profile_status()` keyed `re-auth-required` on `app_token_revoked AND last_sync_status=='ok'`, but a 401 forces `last_sync_status='failed'` + `last_sync_error='pat_rejected'`, so the badge showed PENDING for an actually-revoked profile. Fixed to key on `last_sync_error=='pat_rejected'` / non-null `last_sync_at` (matching D4-07 + the diagnostics card), preserving never-connected→pending. Added `last_sync_error` to the list query + 7 unit tests. Verified live (RE-AUTH REQUIRED renders). Commit on main.

---
status: partial
phase: 04-sync-polish-diagnostics
source: [04-VERIFICATION.md]
started: 2026-05-30
updated: 2026-05-30
---

## Current Test

[awaiting human testing]

## Tests

### 1. Re-auth badge + kiosk banner end-to-end (SYN-02 / SC2)
expected: After revoking a profile's PAT and triggering a sync, the Profiles admin UI shows a re-auth-required badge on the affected profile AND the kiosk renders an inline banner directing the owner to rotate the connection (jargon-free copy). After a successful rotate + test sync, both the badge and banner auto-clear on the next list/session read.
result: [pending]

### 2. Kiosk banner is non-blocking (SYN-02 / SC2 / D4-10)
expected: With the re-auth banner visible on the kiosk, the search input, cube grid, and all kiosk interactivity remain fully live — typing a search still highlights the right cube off the cached collection. Nothing is gated on needs_reauth.
result: [pending]

### 3. Diagnostics cards — Nordic Grid typography (SYN-02 / SC3)
expected: /admin/diagnostics shows a per-profile PROFILES section below the system diagnostics. Each card reports LAST SYNC, STATUS, ITEMS, LAST ERROR for every non-deleted profile, styled in the Nordic Grid type system (Barlow Condensed headings, Space Grotesk body, DM Mono for counts/timestamps) per 04-UI-SPEC.md Surface 1.
result: [pending]

### 4. Sync now — spinner + elapsed + completion toast (SYN-02 / SC5 / D4-17)
expected: Clicking "Sync now" shows an indeterminate spinner with an elapsed-seconds counter until the sync reaches a terminal state, then fires a completion toast (e.g. "Sync complete — N,NNN records"). Search/admin stay responsive during the sync.
result: [pending]

### 5. Cadence select persists across reload (SYN-01 / SC1 / D4-06)
expected: In /admin/settings, changing the sync cadence (e.g. to 12h) auto-saves; reloading the page shows the saved value (persists across server restart too). The cadence sub-label renders in the correct muted style. Changing cadence takes effect on the next loop tick without a restart.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

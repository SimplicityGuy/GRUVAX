---
status: partial
phase: 06-safe-boundaries-live-device-lifecycle
source: [06-VERIFICATION.md]
started: 2026-05-31
updated: 2026-05-31
---

## Current Test

[awaiting human testing]

## Tests

### 1. Kiosk device revoke navigates to pairing screen live (Success Criterion 1, DEV-05)
expected: With the kiosk open in a browser, revoke its device from Admin → Devices. A full-screen "SCREEN REMOVED" (RevokeNotice) overlay appears, then after ~2.5s the kiosk navigates to `/pair` automatically — no manual reload. The terminal-revoke chain (SSE `device_revoked` OR a 403 `device_revoked` from any in-flight call → `triggerRevoke()` → App-level timer → `clearBoundProfile()` + `navigate('/pair')`) is wired in `App.tsx` + `KioskView.tsx` + `client.ts` and passes vitest, but live browser execution must be observed by a human.
result: [pending]

### 2. Kiosk device reassign re-binds and shows new profile's collection live (Success Criterion 2, DEV-05)
expected: With the kiosk bound to Profile A, reassign it to Profile B from Admin → Devices. A "MOVED TO [Profile B name]" yellow reassign banner appears for ~2.5s, then the Kallax grid switches to Profile B's collection — no manual reload. `getSession()` re-fetch, `setSession()`, SSE channel reconnect, and TanStack Query invalidation are wired, but the correct `display_name` in the banner and the live grid switch require a two-profile runtime to confirm.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps

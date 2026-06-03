---
status: complete
phase: 06-safe-boundaries-live-device-lifecycle
source: [06-VERIFICATION.md]
started: 2026-05-31
updated: 2026-06-03
---

## Current Test

[testing complete — verified via Playwright on 2026-06-03; see 06-UAT.md tests 6 & 7]

## Tests

### 1. Kiosk device revoke navigates to pairing screen live (Success Criterion 1, DEV-05)
expected: With the kiosk open in a browser, revoke its device from Admin → Devices. A full-screen "SCREEN REMOVED" (RevokeNotice) overlay appears, then after ~2.5s the kiosk navigates to `/pair` automatically — no manual reload. The terminal-revoke chain (SSE `device_revoked` OR a 403 `device_revoked` from any in-flight call → `triggerRevoke()` → App-level timer → `clearBoundProfile()` + `navigate('/pair')`) is wired in `App.tsx` + `KioskView.tsx` + `client.ts` and passes vitest, but live browser execution must be observed by a human.
result: pass
evidence: "Playwright two-tab run 2026-06-03: RevokeNotice 'SCREEN REMOVED — re-pair to continue' rendered; live SPA nav / → /pair (no reload); DB revoked_at set, session is_device_paired=false. See 06-UAT.md test 6."

### 2. Kiosk device reassign re-binds and shows new profile's collection live (Success Criterion 2, DEV-05)
expected: With the kiosk bound to Profile A, reassign it to Profile B from Admin → Devices. A "MOVED TO [Profile B name]" yellow reassign banner appears for ~2.5s, then the Kallax grid switches to Profile B's collection — no manual reload. `getSession()` re-fetch, `setSession()`, SSE channel reconnect, and TanStack Query invalidation are wired, but the correct `display_name` in the banner and the live grid switch require a two-profile runtime to confirm.
result: pass
evidence: "Playwright two-tab run 2026-06-03 with Default + Profile B: captured banner 'MOVED TO DEFAULT' (display_name from authoritative session, not SSE payload); live GET /api/session showed bound_profile_id flip Default↔Profile B with no reload; DB devices.profile_id tracked each reassign. See 06-UAT.md test 7."

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

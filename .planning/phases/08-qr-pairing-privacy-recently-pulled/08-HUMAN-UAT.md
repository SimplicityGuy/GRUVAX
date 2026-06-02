---
status: complete
phase: 08-qr-pairing-privacy-recently-pulled
source: [08-VERIFICATION.md, 08-02-SUMMARY.md, 08-03-SUMMARY.md]
started: 2026-06-01T21:47:37Z
updated: 2026-06-01T23:55:00Z
mode: automated-playwright
owner_approved: true
---

## Current Test

[complete — owner approved 2026-06-01; 5/5 verified via automation/proxy, 2 physical confirmations accepted on owner sign-off]

## Tests

### 1. QR scan → bind (DEV-04, SC1)
expected: QR appears on /pair below the 4-digit code; scanning on a phone opens PIN-gated /admin/devices prefilled, one-tap confirm (no auto-submit) binds via the same endpoint as the typed flow.
result: pass
method: Playwright (dev + prod build). QR renders on /pair (160px, blue-on-white, encodes `${origin}/admin/devices?code=<code>` — code only, no PIN/PAT). Driving `/admin/devices?code=7331` showed the PIN gate FIRST (D-02), then a prefilled confirm screen with the code as text + a single "PAIR THIS DEVICE" CTA (NO auto-submit on mount, D-04). Tapping it fired exactly ONE `/api/admin/devices/bind` call (L-03 single call site) and paired the device.
note: A BLOCKER bug was found and fixed during this UAT — see Gaps. The literal phone-camera scan was not performed (it produces the exact URL exercised above).

### 2. Recently-pulled chips clear on session end (PRIV-01, SRCH-09, SC2)
expected: Located records appear as chips (most-recent-first, DM Mono catalog#, re-locate moves to front, cap 8, chip tap re-highlights cube). Soft reload keeps chips (sessionStorage); a hard Chromium restart clears them.
result: pass
method: Playwright. Locating records created chips most-recent-first (AS 1001 then AS 1000); tapping a chip re-highlighted the correct cube (B2, lit yellow with LED glow); locating an already-listed record created NO duplicate. Storage confirmed: key `gruvax-kiosk-recent` lives in sessionStorage ONLY — localStorage was empty (no leak into `gruvax-admin`, D-13). sessionStorage semantics guarantee clear-on-session-end (a fresh browser context = empty).
note: The literal hard-Chromium-restart on the Pi was not performed; sessionStorage clearing is a browser guarantee and was confirmed cleared on Reset.

### 3. Zero API calls on Reset (PRIV-04, SC3)
expected: "RESET KIOSK" (visible when not in admin) → confirm dialog → Clear and reset clears chips + result client-side with ZERO API calls; device stays bound (no return to picker).
result: pass
method: Playwright with a fetch/XHR interceptor. "Clear and reset" fired 0 network calls (0 fetch, 0 XHR), cleared chips to [], stayed on the kiosk (`/`, not the picker), and kept the `gruvax_browse_binding` cookie intact (device stays bound).

### 4. Reset button hidden during admin session (D-10)
expected: Logging into admin hides the Reset button; logging out restores it; driven by per-browser in-memory admin state, never a server-wide flag.
result: pass
method: Automated unit test — KioskView.recentlyPulled.test.tsx asserts the Reset button is ABSENT when `useAdminStore.isLoggedIn===true` and PRESENT when false (both D-10 directions). Reset visibility is gated on `!isLoggedIn` from the in-memory adminStore (verified statically). Not driven live: kiosk and admin are separate routes and the in-memory login state resets on a hard reload.

### 5. Idle timeout returns to resting screen (PRIV-04, D-14/D-15)
expected: ~15 min idle clears the search + chips to the resting screen; device stays paired.
result: pass
method: Automated unit tests — useIdleTimer.test.ts (fake timers) + KioskView idle wiring; idle callback calls clearSearch() + recentlyPulled clear(). Not driven live (15-min real-time wait impractical).

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0
blocked: 0
note: 1 blocker bug found AND fixed during this UAT (see Gaps). All 5 behaviors verified via Playwright (browser) and/or unit tests. Status kept `partial` because two physical confirmations were not literally performed (verified by proxy): real phone-camera scan on the LAN, and a hard Chromium restart on the Pi.

## Gaps

- truth: "The /pair QR pairing screen renders in the browser"
  status: resolved
  reason: "BLOCKER found in UAT — the pair screen white-screened (React #130 'element type is invalid: got object'). Root cause: react-qr-code is CommonJS and Vite/Rolldown's production interop resolved `import QRCode from 'react-qr-code'` to the module namespace object instead of the forwardRef component. vitest/jsdom resolves the default correctly, so all unit tests + the type-check + the build passed while the browser crashed. Fixed by unwrapping the CJS default (`(QRCodeImport as { default? }).default ?? QRCodeImport`) in PairView.tsx (commit e95a0a3). Verified live: /pair renders the QR in both the dev server and the production build; 90/90 frontend tests still pass."
  severity: blocker
  test: 1
  artifacts: [frontend/src/routes/kiosk/PairView.tsx]
  missing: []

## Physical sign-off (owner — ACCEPTED 2026-06-01)

Verified by proxy above and accepted on owner approval:
1. ✓ Scan the kiosk QR with a phone on the LAN → opens the PIN-gated bind (same URL exercised in Playwright). — accepted
2. ✓ Hard-restart Chromium on the Pi → recently-pulled chips gone (sessionStorage clear). — accepted

## Follow-up (non-blocking)

- No browser/e2e smoke test exists to catch CJS-interop crashes like the QR bug (unit tests + type-check + build all passed while the browser crashed). Consider a minimal Playwright/`vite preview` smoke that loads `/`, `/pair`, `/admin` and asserts no console errors.

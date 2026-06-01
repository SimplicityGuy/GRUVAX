---
status: partial
phase: 08-qr-pairing-privacy-recently-pulled
source: [08-VERIFICATION.md, 08-02-SUMMARY.md, 08-03-SUMMARY.md]
started: 2026-06-01T21:47:37Z
updated: 2026-06-01T21:47:37Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Physical QR scan → bind (DEV-04, SC1)
expected: On the kiosk /pair screen a QR appears below the 4-digit code captioned "OR SCAN WITH PHONE" and rerolls in lockstep with the digits. Scanning it on a phone on the same LAN opens /admin/devices, prompts for the admin PIN first (D-02), then shows a prefilled one-tap "PAIR THIS DEVICE" confirm (NOT an auto-submitting keypad, D-04). One tap pairs the device and the kiosk leaves the pairing screen. The typed-code path produces the same successful bind and an identical audit entry (L-03 single call site).
result: [pending]

### 2. Hard Chromium restart clears chips (PRIV-01, SRCH-09, SC2)
expected: After locating 2-3 records, each appears as a chip (most-recent-first, catalog number in DM Mono, re-locate moves to front, cap 8, tapping a chip re-highlights the cube). A soft reload preserves the chips (sessionStorage); a HARD Chromium quit+relaunch clears them entirely.
result: [pending]

### 3. Zero network calls on Reset (PRIV-04, SC3)
expected: A subtle "RESET KIOSK" button is visible bottom-right when NOT in an admin session. Tapping it shows a "Reset kiosk?" dialog ("Clear and reset" / "Keep recent searches"). Confirming clears chips + current result, the kiosk stays paired (no return to picker), and the DevTools Network tab shows ZERO requests on confirm.
result: [pending]

### 4. Reset button hidden during admin session (D-10)
expected: Logging into admin on this browser hides the Reset button; logging out restores it. Visibility is driven by the per-browser in-memory admin login state, never a server-wide flag.
result: [pending]

### 5. Idle timeout returns to resting screen (PRIV-04, D-14/D-15)
expected: Leaving the kiosk untouched (or temporarily shortening the ~15-min timeout) clears the search + chips to the resting screen while the device stays paired/bound.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps

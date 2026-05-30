---
status: complete
phase: 03-devices-pairing
source: [03-VERIFICATION.md]
started: 2026-05-29T00:00:00Z
updated: 2026-05-30T00:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. End-to-end pairing completes in under 30 seconds (real hardware)
expected: On a fresh RPi kiosk on the home LAN, the `/pair` screen renders a 4-digit code; an admin enters it via the mobile admin UI numeric keypad, picks a profile, and labels the device; the kiosk auto-navigates to the bound-profile search UI — total elapsed time from code display to kiosk landing on the search UI is < 30 seconds.
result: pass

### 2. Fingerprint cookie survives a physical Pi reboot
expected: After pairing, run `sudo reboot` on the Pi. Chromium relaunches via the `gruvax-kiosk.service` systemd unit with the persistent `--user-data-dir` on the SD card; the kiosk returns directly to its bound-profile search UI without re-pairing (the HttpOnly + SameSite=Strict fingerprint cookie persisted across the OS power-cycle). The Playwright test only simulates browser close/relaunch, so this kernel-restart path needs manual confirmation per `deploy/kiosk/README.md`.
result: pass

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

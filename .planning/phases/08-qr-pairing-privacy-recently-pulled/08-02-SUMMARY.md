---
phase: 08-qr-pairing-privacy-recently-pulled
plan: "02"
subsystem: frontend
tags: [qr-pairing, dev-04, kiosk, admin, react, tdd]
dependency_graph:
  requires: []
  provides: [qr-pairing-flow, prefill-confirm-bind, admin-devices-prefill]
  affects: [PairView, DevicesManager, DeviceDrawer]
tech_stack:
  added: [react-qr-code@2.0.21]
  patterns: [tdd-red-green, qr-code-pairing, url-param-prefill, single-call-site-bind]
key_files:
  created: []
  modified:
    - frontend/package.json
    - frontend/package-lock.json
    - frontend/src/routes/kiosk/PairView.tsx
    - frontend/src/routes/kiosk/pair.css
    - frontend/src/routes/kiosk/PairView.test.tsx
    - frontend/src/routes/admin/DevicesManager.tsx
    - frontend/src/routes/admin/DeviceDrawer.tsx
    - frontend/src/routes/admin/DeviceDrawer.test.tsx
    - frontend/src/routes/admin/DevicesManager.test.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "QR encodes only the short-TTL 4-digit pairing code in a bind URL (never a credential): D-01"
  - "usePrefill local state lets 'Enter a different code' drop to NumericKeypad without mutating the prop"
  - "eslint react-hooks/set-state-in-effect suppressed for URL-param one-shot mount read: canonical pattern"
metrics:
  duration: 881s
  completed_date: "2026-06-01"
  tasks: 2
  files: 10
---

# Phase 08 Plan 02: QR Pairing Path — Summary

QR pairing alongside the 4-digit code: react-qr-code@2.0.21 renders a scannable SVG below the digit card in PairView; scanning lands on /admin/devices pre-filled via ?code=; admin confirms with an explicit "PAIR THIS DEVICE" CTA that calls the same handleBind() endpoint as the typed flow.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Failing QR block tests for PairView | 52137c0 | PairView.test.tsx, package.json |
| 1 (GREEN) | QR block in PairView + pair.css | 8ba0e0f | PairView.tsx, pair.css, PairView.test.tsx |
| 2 (RED) | Failing prefill-confirm tests | bea3032 | DeviceDrawer.test.tsx, DevicesManager.test.tsx |
| 2 (GREEN) | Prefill-confirm in DevicesManager + DeviceDrawer | 965eedf | DevicesManager.tsx, DeviceDrawer.tsx, admin.css |

## Verification Results

- `npm run test` — 14 tests across PairView/DeviceDrawer/DevicesManager: 14/14 pass
- `npm run lint` — 0 errors (1 pre-existing warning in BinWidthEditor.tsx, out of scope)
- `npm run build` — succeeds, 2290 modules transformed
- No hardcoded hex in new pair.css rules (grep returns empty)
- No hardcoded hex in new admin.css rules added by this plan (lines >6000 grep returns empty)
- `grep -n "admin/devices?code=" PairView.tsx` confirms bind URL pattern
- `grep -n "useSearchParams"` confirms DevicesManager reads and strips ?code=

## Acceptance Criteria Status

- [x] `frontend/package.json` lists `react-qr-code` at `^2.0.21` (exact pin via npm install)
- [x] PairView.tsx imports react-qr-code and renders `.pair-qr-container` gated on `pairingCode && !isExpired && !isPaired`
- [x] bindUrl uses `window.location.origin` and `/admin/devices?code=` (inline in JSX, no useMemo)
- [x] pair.css contains `.pair-qr-container` and `.pair-qr-caption` with zero hardcoded hex
- [x] PairView tests pass including QR present/absent assertions (6/6 green)
- [x] DevicesManager.tsx contains `useSearchParams` and deletes the `code` param with `{ replace: true }`
- [x] DeviceDrawer.tsx adds `prefillCode?: string` to DeviceDrawerProps and renders confirm screen
- [x] CTA handler calls `handleBind(prefillCode)` — same function as typed flow (single `handleBind` definition)
- [x] No auto-submit: `handleBind` not called from mount effect when prefillCode is present
- [x] admin.css prefill-confirm rules contain zero hardcoded hex
- [x] DeviceDrawer.test.tsx asserts bind API NOT called on prefill mount (D-04) and called exactly once on confirm tap (L-03)
- [x] DevicesManager.test.tsx asserts ?code= opens drawer with prefill
- [x] `npm run lint` and `npm run build` succeed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing functionality] usePrefill local state for "Enter a different code"**
- **Found during:** Task 2 implementation
- **Issue:** The plan says clicking "Enter a different code" should "drop back to the NumericKeypad" but `prefillCode` comes from props (parent-managed); there's no way to un-set a prop from within the component.
- **Fix:** Added `usePrefill: boolean` local state (initialized from `!!prefillCode`). Setting `setUsePrefill(false)` drops the component back to the typed-code NumericKeypad path without mutating the parent prop. The parent's `prefillCode` prop is still honored on next open.
- **Files modified:** `DeviceDrawer.tsx`
- **Commit:** 965eedf

**2. [Rule 1 - Bug] Test 6 (QR absent on expiry) needed never-resolving reroll fetch**
- **Found during:** Task 1 GREEN verification
- **Issue:** Initial test used an already-expired code, but `clampedInitial=0` sets `pairStatus='expiring'` (not `'expired'`), so QR was still shown. After reroll, QR reappears with the new code.
- **Fix:** Changed to a 1100ms TTL code with a never-resolving reroll promise — keeps pairStatus in 'expired' state for the assertion after 2s timer advance.
- **Files modified:** `PairView.test.tsx`
- **Commit:** 8ba0e0f

**3. [Rule 2 - ESLint] react-hooks/set-state-in-effect suppression for URL mount read**
- **Found during:** Task 2 lint verification
- **Issue:** The eslint rule `react-hooks/set-state-in-effect` flags `setPrefillCode` + `setDrawerTarget` inside the mount effect.
- **Fix:** Added the suppression comment (same pattern used throughout PairView.tsx for the countdown and initial fetch). This is the canonical pattern for one-shot URL-param consumption on mount, documented in the suppression comment.
- **Files modified:** `DevicesManager.tsx`
- **Commit:** 965eedf

## Known Stubs

None. All functionality is wired end-to-end through the existing `handleBind` -> `POST /api/admin/devices/bind` call site.

## Threat Flags

None. All new surface was already covered in the plan's `<threat_model>`:

| Threat | Mitigation | Status |
|--------|------------|--------|
| T-08-QR-01 | QR encodes only the short-TTL code, never credentials | Verified: `window.location.origin + /admin/devices?code=` |
| T-08-QR-02 | Stale code yields `mapBindError` via existing backend atomic consume | Existing backend, unchanged |
| T-08-QR-03 | No auto-submit on prefill mount | DeviceDrawer test 4 asserts 0 bind calls on mount |
| T-08-QR-04 | Scan lands on PIN-gated /admin/devices; PinOverlay is modal (URL survives) | Confirmed AdminShell.tsx pattern |
| T-08-QR-05 | Both paths call single `handleBind` -> POST /api/admin/devices/bind | DeviceDrawer test 5 asserts exactly 1 call |
| T-08-QR-SC | react-qr-code pinned to 2.0.21; slopcheck OK; MIT; no postinstall | Installed and locked |

## Human Verification Pending (end-of-phase)

Per the checkpoint override directive, the final `type="checkpoint:human-verify"` task is DEFERRED and recorded here as required.

### What was built

The kiosk pairing screen now shows a QR code below the 4-digit code. Scanning it on a phone opens the PIN-gated /admin/devices page prefilled with the code, where one tap of "PAIR THIS DEVICE" completes pairing through the same bind endpoint as the typed flow.

### How to verify (verbatim from checkpoint)

1. Start the kiosk + API locally (per the project local-UAT recipe: one uvicorn against gruvax-dev-pg; set the admin PIN via gruvax-set-pin). Open the kiosk at the /pair (unpaired) screen in Chromium.
2. Confirm a QR code appears below the 4-digit code with the caption "OR SCAN WITH PHONE". Wait for the 5-minute reroll (or force a reroll) and confirm the QR updates in lockstep with the new digits.
3. On a phone on the same LAN, scan the QR. Confirm it opens /admin/devices and prompts for the admin PIN first (D-02). Enter the PIN.
4. Confirm the bind drawer shows the prefilled 4-digit code and a single "PAIR THIS DEVICE" button (NOT a pre-filled keypad that auto-submits). Tap it once.
5. Confirm the device pairs successfully and the kiosk leaves the pairing screen.
6. Confirm the typed-code path still works (enter the code manually on /admin/devices) and produces the same successful bind.
7. (L-03 / success criterion 1) Confirm BOTH paths produce an identical successful bind: the scanned-prefill confirm and the typed code both result in the same device-paired outcome and the same success toast — they go through one bind endpoint, so the audit entry is identical.

### Resume signal

Type "approved" or describe issues (e.g., QR doesn't scan, auto-submit fires, PIN gate skipped).

## Self-Check: PASSED

- PairView.tsx: present with QR import, .pair-qr-container, bind URL pattern
- pair.css: present with .pair-qr-container and .pair-qr-caption, no hex
- DevicesManager.tsx: present with useSearchParams + prefillCode state + { replace: true }
- DeviceDrawer.tsx: present with prefillCode? prop + usePrefill state + handleBind call
- DeviceDrawer.test.tsx: present with tests 4-6 for prefill (D-04 + L-03)
- DevicesManager.test.tsx: present at `.planning/phases/../DevicesManager.test.tsx`
- admin.css: present with device-prefill-* rules, no hex in new rules
- Commits: 52137c0, 8ba0e0f, bea3032, 965eedf all in git log

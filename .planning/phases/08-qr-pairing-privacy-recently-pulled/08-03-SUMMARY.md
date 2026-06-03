---
phase: 08-qr-pairing-privacy-recently-pulled
plan: "03"
subsystem: frontend
tags: [recently-pulled, privacy, sessionStorage, idle-timer, kiosk-reset, SRCH-09, PRIV-01, PRIV-04]
dependency_graph:
  requires: []
  provides:
    - recentlyPulledStore (sessionStorage-backed Zustand slice)
    - useIdleTimer (15-min kiosk idle hook)
    - RecentlyPulledStrip (horizontal chip strip component)
    - ResetConfirmDialog (alertdialog confirm component)
    - KioskView wiring (locate→addItem, Reset button, idle clear)
  affects:
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css
tech_stack:
  added:
    - Zustand persist with createJSONStorage(() => sessionStorage)
  patterns:
    - sessionStorage-backed Zustand slice (PRIV-01)
    - useRef/setTimeout idle timer hook (D-14)
    - alertdialog focus trap (D-11)
    - store getState() in effects (Pitfall 5 avoidance)
key_files:
  created:
    - frontend/src/state/recentlyPulledStore.ts
    - frontend/src/state/recentlyPulledStore.test.ts
    - frontend/src/hooks/useIdleTimer.ts
    - frontend/src/hooks/useIdleTimer.test.ts
    - frontend/src/routes/kiosk/RecentlyPulledStrip.tsx
    - frontend/src/routes/kiosk/ResetConfirmDialog.tsx
    - frontend/src/routes/kiosk/ResetConfirmDialog.test.tsx
    - frontend/src/routes/kiosk/KioskView.recentlyPulled.test.tsx
  modified:
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css
decisions:
  - "sessionStorage (not localStorage) for recently-pulled list — PRIV-01; clears on hard Chromium restart (D-13)"
  - "useRecentlyPulledStore.getState() in effects/callbacks — avoids stale closures (Pitfall 5)"
  - "role=alertdialog on ResetConfirmDialog — correct ARIA role for destructive confirm dialogs"
  - "Cancel-first focus in ResetConfirmDialog — safer default for destructive action (D-11)"
  - "animationToken as addItem effect dependency — fires on every locate including re-locates, deduped by store"
  - "mockAdminState object shared between mock factory and test scope — avoids vi.mock hoisting issue with outer const"
metrics:
  duration: "19 minutes"
  completed: "2026-06-01"
  tasks: 3
  files: 10
requirements-completed: [PRIV-01, PRIV-04, SRCH-09]
---

# Phase 8 Plan 3: Recently-Pulled Strip + Privacy Reset + Idle Timeout Summary

Session-only recently-pulled chip strip, no-PIN client-side-only "Reset kiosk" button, and 15-minute idle timeout — all implemented client-side with zero API calls, sessionStorage-backed, excluded from localStorage (PRIV-01).

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | recentlyPulledStore + useIdleTimer | f1b7c16 | recentlyPulledStore.ts, useIdleTimer.ts + tests |
| 2 | RecentlyPulledStrip + ResetConfirmDialog | a16f9b0 | RecentlyPulledStrip.tsx, ResetConfirmDialog.tsx + test |
| 3 | Wire strip + Reset + idle into KioskView | 6d60441 | KioskView.tsx, kiosk.css + test |

## Test Results

- **27 tests passing** across 5 test files
- `recentlyPulledStore.test.ts`: 5 tests (dedupe, cap-8, clear, storage-key PRIV-01 isolation, primary_artist field)
- `useIdleTimer.test.ts`: 4 tests (fire after timeout, pointermove reset, touchstart reset, unmount cleanup)
- `ResetConfirmDialog.test.tsx`: 6 tests (onConfirm, L-05 zero-fetch behavioral gate, onCancel, Escape, alertdialog role, Cancel-first focus)
- `KioskView.recentlyPulled.test.tsx`: 4 tests (POSITIVE locate→addItem, NEGATIVE D-05 guard, Reset hidden when admin logged in, Reset shown when not)
- `KioskView.EventSource.test.tsx`: 8 tests (pre-existing, all still passing)

## Deviations from Plan

### Approach Changes

**1. [Rule 2 - Auto-add] Test mock pattern for adminStore**
- **Found during:** Task 3 test implementation
- **Issue:** `useAdminStore.setState({ isLoggedIn: false })` triggers the Zustand persist middleware which writes to localStorage; jsdom's localStorage isn't available in the test environment when stores are created at import time
- **Fix:** Mocked the `adminStore` module via `vi.mock` with a shared `mockAdminState` object that test cases can mutate directly — avoids the persist middleware entirely in tests
- **Files modified:** `KioskView.recentlyPulled.test.tsx`
- **Commit:** 6d60441

**2. [Rule 3 - Auto-fix] ResetConfirmDialog test used unavailable user-event**
- **Found during:** Task 2 test implementation
- **Issue:** `@testing-library/user-event` is not installed in the project; only `fireEvent` from `@testing-library/react` is used
- **Fix:** Replaced `userEvent.click()` with `fireEvent.click()` and `userEvent.keyboard('{Escape}')` with `fireEvent.keyDown(document, { key: 'Escape' })`
- **Files modified:** `ResetConfirmDialog.test.tsx`
- **Commit:** a16f9b0

## Human Verification Pending (end-of-phase)

Per `workflow.human_verify_mode: end-of-phase`, the final `checkpoint:human-verify` task is deferred for human UAT. Automated verification (27 tests + lint + build) has passed. The following physical verification steps remain:

**Task:** Verify recently-pulled strip, Reset kiosk, and idle timeout in a real Chromium kiosk session.

**How to verify:**
1. Start the kiosk locally (project local-UAT recipe). Search and successfully locate 2-3 records. Confirm each appears as a chip below the shelf area, most-recent-first, with the catalog number in DM Mono. Re-locate one already in the list and confirm it moves to the front with no duplicate (cap 8).
2. Tap a chip and confirm the correct cube re-highlights (re-locate works).
3. Reload the page (soft reload) and confirm the chips survive (sessionStorage). Then do a HARD Chromium restart (quit + relaunch) and confirm the chips are GONE (success criterion 2).
4. Confirm a subtle "RESET KIOSK" button is visible bottom-right while NOT logged into admin. Tap it → confirm the "Reset kiosk?" dialog with "Clear and reset" / "Keep recent searches". Confirm → chips + current result clear, the kiosk stays paired/bound (no return to picker), and no network request fires (check devtools Network tab shows zero calls on confirm).
5. Log into admin on THIS browser and confirm the Reset button is hidden (D-10). Log out and confirm it returns.
6. (Optional, fast-forward) Confirm idle behavior: leave the kiosk untouched (or temporarily shorten the timeout for the test) and confirm the search + chips clear to the resting screen while the device stays paired.

**Resume signal:** Type "approved" or describe issues (e.g., chips survive hard restart, Reset fires an API call, button shows during admin).

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes were introduced. All new code is client-side only. The threat model mitigations from the plan were implemented:

| Threat | Disposition | Implementation |
|--------|-------------|----------------|
| T-08-PR-01 (Info Disclosure via persistence) | Mitigated | sessionStorage key `gruvax-kiosk-recent`, excluded from `gruvax-admin` localStorage — verified by storage-key test |
| T-08-PR-03 (Reset as privileged action) | Mitigated | Zero API calls — verified by behavioral L-05 gate in ResetConfirmDialog.test.tsx |
| T-08-PR-04 (Reset driven by server flag) | Mitigated | Reset visibility driven by per-browser in-memory `adminStore.isLoggedIn`, not a server flag — verified by KioskView tests |

## Self-Check: PASSED

All 9 created/modified files verified present. All 3 task commits verified in git log.

| Item | Status |
|------|--------|
| recentlyPulledStore.ts | FOUND |
| recentlyPulledStore.test.ts | FOUND |
| useIdleTimer.ts | FOUND |
| useIdleTimer.test.ts | FOUND |
| RecentlyPulledStrip.tsx | FOUND |
| ResetConfirmDialog.tsx | FOUND |
| ResetConfirmDialog.test.tsx | FOUND |
| KioskView.recentlyPulled.test.tsx | FOUND |
| 08-03-SUMMARY.md | FOUND |
| Commit f1b7c16 | FOUND |
| Commit a16f9b0 | FOUND |
| Commit 6d60441 | FOUND |

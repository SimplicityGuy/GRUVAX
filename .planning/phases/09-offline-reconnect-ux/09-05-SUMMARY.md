---
phase: 09-offline-reconnect-ux
plan: "05"
subsystem: frontend
tags: [offline-ux, sse, store, connectivity, gap-closure]
dependency_graph:
  requires: ["09-03", "09-04"]
  provides: ["offline-confirmed bannerVisible gate", "everConnected latch"]
  affects: ["frontend/src/state/store.ts", "frontend/src/routes/kiosk/OfflineBanner.tsx", "frontend/src/routes/kiosk/KioskView.tsx"]
tech_stack:
  added: []
  patterns: ["offline-confirmed state gate (everConnected one-way latch)"]
key_files:
  created: []
  modified:
    - frontend/src/state/store.ts
    - frontend/src/state/store.connectivity.test.ts
    - frontend/src/routes/kiosk/OfflineBanner.tsx
    - frontend/src/routes/kiosk/OfflineBanner.test.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
    - frontend/src/routes/kiosk/KioskView.recentlyPulled.test.tsx
    - frontend/src/routes/kiosk/ShelfLayoutNotConfigured.test.tsx
decisions:
  - "everConnected is a one-way latch in the Zustand store; once true after the first SSE onopen it never reverts, so bannerVisible = !sseConnected && everConnected correctly represents the offline-confirmed state for the lifetime of the session"
  - "OfflineBanner reads bannerVisible directly (not sseConnected) so it is automatically correct at all render points without any additional logic"
  - "KioskView still uses sseConnected for show-when-connected secondary UI (StalenessBar, ReauthBanner, SwitchProfileButton, new-records pill) — D-04 suppression of secondary UI while disconnected remains correct; only the offline BANNER and degraded read-only lockouts (isOffline / onCubeTap) switch to bannerVisible"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-02"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 8
requirements-completed: [OFF-01]
---

# Phase 09 Plan 05: Gap-Closure — Offline-Confirmed Banner Gate Summary

**One-liner:** Introduced `everConnected` one-way latch and `bannerVisible = !sseConnected && everConnected` so the offline banner and degraded mode never appear on initial bootstrap or 403 device_unknown rejections — unblocking UAT Test 1.

## What Was Built

### Root cause fixed
UAT Test 1 reported the offline banner stuck on initial load: `/api/events/{profile_id}` returned 403 `device_unknown` (stale fingerprint cookie + empty devices table), `EventSource.onerror` fired immediately, `setSseConnected(false)` set `bannerVisible: !connected = true`, and the banner appeared before any successful connection was ever established. Since `onopen` never fired, the banner never cleared — kiosk permanently bricked.

### Fix: offline-confirmed state gate
- **`store.ts`**: Added `everConnected: boolean` to `ConnectivityState`. It is a one-way latch: starts `false`, becomes `true` on the first `setSseConnected(true)` call (onopen), and never reverts. `bannerVisible` is now computed as `!connected && everConnected` — representing "was connected, then lost" rather than just "currently disconnected".

- **`OfflineBanner.tsx`**: Changed selector from `sseConnected` to `bannerVisible`. Early return changed from `if (sseConnected) return null` to `if (!bannerVisible) return null`. The component is now inert until an actual drop-after-connect occurs.

- **`KioskView.tsx`**: Added `bannerVisible` selector. Three sites updated:
  - `SearchBox isOffline={bannerVisible}` (degraded mode only when offline-confirmed)
  - `{bannerVisible && <OfflineBanner />}` (render only when offline-confirmed)
  - `onCubeTap={!bannerVisible ? setTappedCube : undefined}` (cube-tap lock only when offline-confirmed, both ShelfGrid instances)
  - `show-when-connected` secondary UI unchanged (`sseConnected &&` gates for StalenessBar, ReauthBanner, SwitchProfileButton, new-records pill remain correct per D-04)
  - Updated `wasOffline` comment to describe the refined offline-confirmed contract

- **Tests updated** (all green, 130/130):
  - `store.connectivity.test.ts`: Added tests for never-connected, connect→disconnect, reconnect, and everConnected latch; updated resetStore to include `everConnected: false`
  - `OfflineBanner.test.tsx`: Added never-connected test suite asserting banner ABSENT when `sseConnected=false, everConnected=false`; updated all setState calls to include `everConnected`
  - `KioskView.EventSource.test.tsx`: Updated beforeEach and Blocker-1 test setState to include `everConnected: false`
  - `KioskView.recentlyPulled.test.tsx`, `ShelfLayoutNotConfigured.test.tsx`: Fixed missing `everConnected` in `ConnectivityState` setState calls (Rule 3 auto-fix — tsc type error)

## SC1/SC3 Preservation

- **SC1** (connect → stop server → banner): onopen fires first → `everConnected = true`; onerror fires → `bannerVisible = !false && true = true` → banner appears. Confirmed by `Phase 9 OFF-01` EventSource test.
- **SC3** (reconnect → banner clears): onopen fires again → `setSseConnected(true)` → `bannerVisible = !true && true = false` → banner disappears, "Back online" toast appears. Confirmed by `Phase 9 OFF-04` EventSource test.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing everConnected in ConnectivityState setState calls**
- **Found during:** Task 3 (`npm run build`)
- **Issue:** tsc reported `Property 'everConnected' is missing in type` for `KioskView.recentlyPulled.test.tsx:170` and `ShelfLayoutNotConfigured.test.tsx:34`
- **Fix:** Added `everConnected: false` to both test file setState calls
- **Files modified:** `KioskView.recentlyPulled.test.tsx`, `ShelfLayoutNotConfigured.test.tsx`
- **Commit:** 6bdb52c

## Known Stubs

None — all behavior is fully wired.

## Threat Flags

None — this is a frontend-only state management fix with no new network endpoints, auth paths, or trust boundary changes.

## Self-Check: PASSED

- [x] `frontend/src/state/store.ts` contains `everConnected`
- [x] `frontend/src/state/store.ts` contains `!connected && everConnected`
- [x] `frontend/src/routes/kiosk/OfflineBanner.tsx` contains `if (!bannerVisible) return null`
- [x] `frontend/src/routes/kiosk/KioskView.tsx` contains `bannerVisible && <OfflineBanner`
- [x] Commits 96e2750, ec91f4d, 6bdb52c exist
- [x] `npm run build` clean
- [x] `npm test` 130/130 green

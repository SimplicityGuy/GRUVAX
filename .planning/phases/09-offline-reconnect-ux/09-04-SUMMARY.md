---
phase: 09-offline-reconnect-ux
plan: "04"
subsystem: frontend-sse-reconnect
tags: [gap-closure, sse, search-invalidation, toast, offline-ux]
dependency_graph:
  requires: ["09-03"]
  provides: ["OFF-04-complete", "SC4-satisfied", "WR-01-resolved", "WR-02-resolved"]
  affects: ["frontend/src/routes/kiosk/KioskView.tsx", "frontend/src/routes/kiosk/KioskView.EventSource.test.tsx"]
tech_stack:
  added: []
  patterns: ["useCallback for stable toast dismiss callback", "active query invalidation on SSE reconnect"]
key_files:
  modified:
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
decisions:
  - "SC4: active ['search'] invalidation on resync() (not passive staleTime) — user decision 2026-06-01 supersedes D-73/D-74"
  - "WR-01: useCallback for handleBackOnlineDismiss so toast timer is not re-armed by re-renders"
  - "WR-02: setShowBackOnlineToast(false) in both es.onerror and server_shutdown to prevent dual-banner state"
metrics:
  duration_minutes: 15
  completed: "2026-06-01"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
requirements: [OFF-04]
---

# Phase 9 Plan 04: SC4 Search Invalidation + WR-01/WR-02 Toast Fixes Summary

**One-liner:** Active `['search']` invalidation in `resync()` plus stable `useCallback` dismiss + toast-cleared-on-disconnect to satisfy ROADMAP SC4 and resolve two flaky-LAN reconnect defects.

## What Was Built

Three targeted fixes to `KioskView.tsx` (one file) and four new tests in the EventSource test file, closing the gap-closure items identified in the 09-VERIFICATION report.

### Task 1: SC4 — Actively invalidate `['search']` in `resync()`

Added `void queryClient.invalidateQueries({ queryKey: ['search'] })` to the `resync()` function alongside the existing `['units']` and `['cubes']` invalidations. Because `resync()` is called from both `es.onopen` and the `server_hello` SSE event handler, search results are now flushed on every genuine reconnect — satisfying ROADMAP SC4 literally ("stale search and boundary data is refreshed on server_hello").

**Decision (user, 2026-06-01):** Supersedes the D-73/D-74 passive-staleTime approach from CONTEXT.md. Active invalidation is the correct implementation of the ROADMAP wording.

### Task 2: WR-01 + WR-02 — Stable dismiss callback + toast cleared on disconnect

**WR-01:** Added `useCallback` to the React import. Defined `handleBackOnlineDismiss = useCallback(() => setShowBackOnlineToast(false), [])` near the other state/hook declarations. Replaced the inline arrow `onDismiss={() => setShowBackOnlineToast(false)}` on the SyncToast with `onDismiss={handleBackOnlineDismiss}`. The stable identity prevents SyncToast's 4s auto-dismiss timer from being re-armed by background re-renders (health polling, session polling).

**WR-02:** Added `setShowBackOnlineToast(false)` to both `es.onerror` (after the existing `setSseConnected(false)`) and the `server_shutdown` addEventListener handler. A disconnect within 4s of a reconnect now correctly clears the "Back online" toast — the OfflineBanner and the toast are never visible simultaneously.

### Task 3: New EventSource tests for SC4 and WR-02

Added four new tests to `KioskView.EventSource.test.tsx`:

1. **SC4 — onopen invalidates `['search']`:** Spies on `queryClient.invalidateQueries` after `onopen` fires; asserts `['search']` is among the called keys alongside `['units']` and `['cubes']`.

2. **SC4 — server_hello invalidates `['search']`:** Dispatches `server_hello` SSE event; asserts `['search']` is invalidated via the same `resync()` path.

3. **WR-02 — onerror clears toast:** Connect → disconnect → reconnect (toast appears) → disconnect again via `onerror`; asserts toast is gone and OfflineBanner is shown instead.

4. **WR-02 — server_shutdown clears toast:** Same setup but triggers `server_shutdown` instead; asserts toast clears and `sseConnected` is false.

## Verification

- `tsc -b --noEmit`: clean (no errors)
- `vite build`: succeeds (chunk-size warning pre-existing, unrelated)
- `vitest run` (all 17 test files, 124 tests): all pass
- `KioskView.EventSource.test.tsx` (15 tests): all pass

## Acceptance Criteria Met

| Criterion | Status |
|-----------|--------|
| `resync()` contains `invalidateQueries({ queryKey: ['search'] })` | Done |
| `useCallback` imported; `handleBackOnlineDismiss` defined with `[]` deps | Done |
| `handleBackOnlineDismiss` passed to SyncToast `onDismiss` | Done |
| `setShowBackOnlineToast(false)` present in `es.onerror` | Done |
| `setShowBackOnlineToast(false)` present in `server_shutdown` listener | Done |
| New SC4 + WR-02 tests green | Done |
| Full frontend test suite green (124/124) | Done |

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None — all changes are fully implemented with real behavior.

## Threat Flags

None — no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `6742cd6` | `feat(09-04): SC4 — invalidate ['search'] in resync() on reconnect` |
| 2 | `8bc2bf7` | `feat(09-04): WR-01 + WR-02 — stable onDismiss callback + clear toast on disconnect` |
| 3 | `ecfdf12` | `test(09-04): add SC4 search invalidation + WR-02 toast-clear-on-disconnect tests` |

## Self-Check: PASSED

- `frontend/src/routes/kiosk/KioskView.tsx` — exists and contains all required changes
- `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` — exists with 4 new tests
- Commits `6742cd6`, `8bc2bf7`, `ecfdf12` — all present in git log
- 124/124 tests green; tsc clean; vite build succeeds

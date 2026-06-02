---
phase: 09-offline-reconnect-ux
plan: "02"
subsystem: frontend
tags: [connectivity, store, tanstack-query, offline-ux, tdd]
dependency_graph:
  requires: []
  provides: [connectivity.bannerVisible-boolean, QueryClient.networkMode-always]
  affects: [frontend/src/state/store.ts, frontend/src/App.tsx]
tech_stack:
  added: []
  patterns: [TDD RED/GREEN, Zustand store slice extension, TanStack Query networkMode config]
key_files:
  created: []
  modified:
    - frontend/src/state/store.ts
    - frontend/src/state/store.connectivity.test.ts
    - frontend/src/App.tsx
decisions:
  - "bannerVisible derives from !connected inside setSseConnected — single source of truth, no separate toggle"
  - "networkMode: 'always' (not 'offlineFirst') — D8 confirmed: prevents TanStack Query from pausing on navigator.onLine=false; SSE state does the real gating"
  - "Initial state bannerVisible: false preserved — the literal false value in initial state is compatible with the widened boolean interface"
metrics:
  duration: "162s"
  completed: "2026-06-02"
  tasks_completed: 2
  files_modified: 3
---

# Phase 9 Plan 02: Connectivity Store Contract + QueryClient Network Policy Summary

**One-liner:** `bannerVisible: boolean` flipped by `setSseConnected(!connected)` + `networkMode: 'always'` on QueryClient — the store contract and network policy that the banner/degraded-mode plan (09-03) builds on.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing tests for bannerVisible flip | e5f7139 | frontend/src/state/store.connectivity.test.ts |
| 1 (GREEN) | Unlock bannerVisible and flip in setSseConnected | d21d821 | frontend/src/state/store.ts |
| 2 | Add networkMode 'always' to QueryClient defaultOptions | 0dbb631 | frontend/src/App.tsx |

## What Was Built

### Task 1: Connectivity Store Contract (TDD)

**RED:** Added 5 new test cases to `store.connectivity.test.ts`:
- `setSseConnected(false)` → `bannerVisible === true`
- `setSseConnected(true)` → `bannerVisible === false`
- `setSseConnected(true)` still updates `sseConnected=true` and bumps `lastSeenAt`
- `setSseConnected(false)` preserves the previous `lastSeenAt`
- (Plus existing test for initial state already in suite)

All new tests failed as expected against the stub implementation.

**GREEN:** Two changes to `store.ts`:
1. `ConnectivityState.bannerVisible`: widened from literal type `false` to `boolean` (removes the Phase 4 stub comment; activates the Phase 9 contract)
2. `setSseConnected` action: added `bannerVisible: !connected` to the connectivity updater object alongside the existing `sseConnected` and `lastSeenAt` lines

Initial state `connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false }` is unchanged — the `false` value is now a `boolean` value, no type conflict.

### Task 2: QueryClient Network Policy

Added `networkMode: 'always'` to `App.tsx` QueryClient `defaultOptions.queries`. Existing `retry: 1` and `refetchOnWindowFocus: false` options unchanged.

## Verification

- `npx tsc --noEmit` exits 0 (clean)
- `npx vitest run src/state/store.connectivity.test.ts`: 12/12 tests pass
- `grep` confirms both `bannerVisible: boolean` (interface) and `bannerVisible: !connected` (action) in store.ts
- `grep` confirms `networkMode: 'always'` present alongside `retry: 1` and `refetchOnWindowFocus: false` in App.tsx

## Deviations from Plan

None — plan executed exactly as written. The TDD sequence followed RED/GREEN gate order without any unexpected failures.

## Known Stubs

None. `bannerVisible` is now a real boolean derived from `!connected`. The 09-03 plan (banner/degraded-mode) consumes this contract directly.

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (test) | e5f7139 | PASS — 1 test failed as expected; 11 existing passed |
| GREEN (feat) | d21d821 | PASS — all 12 tests pass after implementation |
| REFACTOR | (not needed) | No cleanup required; implementation is already minimal |

## Self-Check: PASSED

| Item | Status |
|------|--------|
| frontend/src/state/store.ts | FOUND |
| frontend/src/state/store.connectivity.test.ts | FOUND |
| frontend/src/App.tsx | FOUND |
| 09-02-SUMMARY.md | FOUND |
| Commit e5f7139 (RED) | FOUND |
| Commit d21d821 (GREEN) | FOUND |
| Commit 0dbb631 (Task 2) | FOUND |

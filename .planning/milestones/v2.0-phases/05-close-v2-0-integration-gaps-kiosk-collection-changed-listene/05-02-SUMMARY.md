---
phase: 05-close-v2-0-integration-gaps-kiosk-collection-changed-listene
plan: "02"
subsystem: frontend
tags: [sse, tanstack-query, kiosk, b-01, b-02, tdd]
dependency_graph:
  requires: []
  provides: [collection_changed-listener, boundProfileId-search-gate]
  affects: [frontend/src/routes/kiosk/KioskView.tsx]
tech_stack:
  added: []
  patterns:
    - "es.addEventListener('collection_changed', () => { ... }) — payload-less SSE event handler mirroring server_hello idiom"
    - "enabled: !!boundProfileId && debouncedQuery.trim().length > 0 — compound gate on session state + query length"
    - "vi.mock searchCollection alongside locateRelease so spying on queryFn works in tests"
key_files:
  created: []
  modified:
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
decisions:
  - "Test approach for B-02: spy on mocked searchCollection (the queryFn) rather than global.fetch — fetch's call signature in jsdom doesn't match expect.stringContaining reliably; spying on the queryFn directly is unambiguous"
  - "Mock searchCollection in vi.mock block alongside locateRelease so the query spy works correctly and the component doesn't make real network calls in tests"
  - "Use fireEvent.change + 300ms real-timer advance to drive debouncedQuery through the 250ms SearchBox debounce in the B-02 test"
metrics:
  duration_minutes: 8
  completed_date: "2026-05-30"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 2
requirements: [SYN-01, SYN-02, API-02]
---

# Phase 5 Plan 02: Kiosk collection_changed Listener + boundProfileId Gate Summary

**One-liner:** `collection_changed` SSE listener busts the search cache on sync completion; search `useQuery` gated on `!!boundProfileId` so no request fires before session bootstrap.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write RED Vitest tests for collection_changed invalidation and the boundProfileId gate | 5030865 | `KioskView.EventSource.test.tsx` |
| 2 | Add collection_changed listener and gate search enabled on boundProfileId | 9fdb52a | `KioskView.tsx` |

## What Was Built

### B-01: `collection_changed` SSE listener (KioskView.tsx)

Added `es.addEventListener('collection_changed', () => { ... })` inside the existing SSE `useEffect`, immediately after the `server_shutdown` listener and before the cleanup `return`. The handler:
- Calls `void queryClient.invalidateQueries({ queryKey: ['search'] })` — prefix-key invalidation busts all `['search', q, profileId]` entries at once so visible search results refetch live after a nightly/manual sync
- Calls `resync()` — invalidates `['units']`/`['cubes']` and re-locates the active selection

Mirrors the `server_hello` idiom: no payload from the publisher (`profile_sync.py` sends `bus.publish('collection_changed')` with no data), so no `e` parameter and no `try/catch` needed. No second `es.close()` added (Pitfall 4 preserved). Effect dep array unchanged (`[queryClient, boundProfileId]`).

### B-02 frontend: search `enabled` gate (KioskView.tsx line 171)

Changed:
```typescript
enabled: debouncedQuery.trim().length > 0,
```
to:
```typescript
enabled: !!boundProfileId && debouncedQuery.trim().length > 0,
```

Prevents any `/api/search` request from firing while `boundProfileId` is null (session bootstrap pending). The backend Plan 01 tolerant-`profile_id` fix is the authoritative guard; this is defense-in-depth per T-05-03.

### Tests (KioskView.EventSource.test.tsx)

Two new tests added at the end of the `describe` block:

1. **`collection_changed invalidates search query key (B-01)`** — renders via `renderKioskAndFlush`, spies on `qc.invalidateQueries`, dispatches `collection_changed`, asserts `calledKeys` contains `['search']`.

2. **`search query is disabled when boundProfileId is null (B-02)`** — overrides session store to unbound state, renders, fires `fireEvent.change` on search input to set query to "Blue Note", advances 300ms past the debounce, asserts `vi.mocked(searchCollection)` was NOT called.

`searchCollection` was added to the `vi.mock('../../api/client')` block alongside the existing `locateRelease` mock so the queryFn spy works correctly without real network calls.

## Verification Results

```
Tests:  6 passed (6)           ← all EventSource tests GREEN
ESLint: clean
tsc:    clean
es.close() count: 1 actual call (remaining occurrences in comments)
collection_changed grep count in KioskView.tsx: 3 (comment + listener registration + comment)
!!boundProfileId && debouncedQuery grep count: 1
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] B-02 test approach changed from fetch spy to searchCollection spy**
- **Found during:** Task 1 — initial B-02 test using `vi.spyOn(global, 'fetch')` with `expect.stringContaining('/api/search')` passed for the wrong reason (fetch's argument in jsdom didn't match the string matcher reliably)
- **Issue:** The test passed even before the fix because the `fetch` spy pattern wasn't catching calls through the mocked module
- **Fix:** Added `searchCollection: vi.fn().mockResolvedValue(...)` to the `vi.mock` block and spied on `vi.mocked(searchCollection)` directly — this is unambiguous and confirmed the RED state (test showed `searchCollection` called once with `('Blue Note', 10, undefined)` before the gate was added)
- **Files modified:** `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx`
- **Commit:** 5030865

**2. [Rule 2 - Missing functionality] Added `fireEvent` import and real timer advance for B-02**
- **Found during:** Task 1 — initial attempt to drive `debouncedQuery` using raw DOM `dispatchEvent` with `Object.assign` failed with TypeError
- **Fix:** Added `fireEvent` to the `@testing-library/react` import and used `fireEvent.change(input, { target: { value: 'Blue Note' } })` + `await new Promise(r => setTimeout(r, 300))` to properly drive the SearchBox debounce
- **Files modified:** `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx`
- **Commit:** 5030865

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The `collection_changed` listener only triggers TanStack Query cache invalidation (no JSON parsing, no new state surface). T-05-04 (DoS via duplicate frames) is accepted per the threat register — `invalidateQueries` is debounced/coalesced by the TanStack Query layer.

## Known Stubs

None. Both B-01 and B-02 are fully wired end-to-end.

## Self-Check: PASSED

- [x] `frontend/src/routes/kiosk/KioskView.tsx` — modified, contains `collection_changed` listener and `!!boundProfileId` gate
- [x] `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` — modified, contains both new tests
- [x] Commit 5030865 exists (`git log --oneline | grep 5030865`)
- [x] Commit 9fdb52a exists (`git log --oneline | grep 9fdb52a`)
- [x] All 6 tests pass (exit 0)
- [x] ESLint clean, tsc clean

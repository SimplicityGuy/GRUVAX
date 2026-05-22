---
phase: 04-realtime-live-updates
plan: "02"
subsystem: realtime
tags: [sse, locate, highlight, re-glow, kiosk, testing, vitest]
dependency_graph:
  requires:
    - "04-01 (SSE EventSource consumer + boundary_changed listener + locateRelease import)"
    - "02-01 (locateRelease API + setLocateResult + animationToken/GSAP mechanism)"
  provides:
    - "boundary_changed → active-selection re-locate (D-05)"
    - "resync() → active-selection re-locate on reconnect (D-11)"
    - "D-06 re-glow via existing animationToken/GSAP — no new animation code"
    - "MockEventSource vitest scaffold for EventSource consumer tests"
  affects:
    - "frontend/src/routes/kiosk/KioskView.tsx (locateRelease import + relocateActiveSelection helper)"
    - "frontend/src/routes/kiosk/KioskView.EventSource.test.tsx (created)"
tech_stack:
  added: []
  patterns:
    - "relocateActiveSelection() reads selectedReleaseId via .getState() (Pitfall 5 stale closure guard)"
    - "locateRelease(id).then(setLocateResult) mirrors ResultsList.tsx L70-89 imperative pattern"
    - "setLocateResult increments animationToken → existing GSAP useLayoutEffect fires (D-06 re-glow)"
    - "MockEventSource: static instances array + dispatchEvent(name, data) test helper"
    - "vi.mock('../../api/client') for ESM-compatible locateRelease mock (vi.spyOn alone insufficient)"
    - "Set selectedReleaseId AFTER render in tests to avoid clearSearch() on empty debouncedQuery"
key_files:
  created:
    - "frontend/src/routes/kiosk/KioskView.EventSource.test.tsx"
  modified:
    - "frontend/src/routes/kiosk/KioskView.tsx (locateRelease import + relocateActiveSelection)"
decisions:
  - "locate is imperative (locateRelease(id).then(setLocateResult)), not a TanStack query key — D-05 re-runs it directly rather than invalidating ['locate', id] (confirmed by codebase grep)"
  - "relocateActiveSelection() defined inside the useEffect to co-locate with the SSE listener; shared between boundary_changed and resync() avoiding duplication"
  - "vi.mock at module scope required for ESM named export interception — vi.spyOn alone does not intercept the component's binding to locateRelease"
  - "selectedReleaseId must be set after renderKioskAndFlush() because KioskView's clearSearch useEffect resets it when debouncedQuery is empty on mount"
metrics:
  duration: "~35 minutes"
  completed: "2026-05-22T01:43:57Z"
  tasks_completed: 2
  files_changed: 2
---

# Phase 4 Plan 02: Highlight Follows Record (D-05 + D-06 Re-glow) Summary

Wires the active-selection re-locate into the existing boundary_changed SSE listener and resync helper so the visitor's highlight follows a relocated record to its new cube, presented as a re-glow via the existing animationToken/GSAP mechanism.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | MockEventSource test scaffold (D-05 RED + D-11 GREEN) | 0a4e7b4 | frontend/src/routes/kiosk/KioskView.EventSource.test.tsx |
| 2 | Re-locate active selection on boundary_changed (D-05 + D-06) | 33eafc8 | frontend/src/routes/kiosk/KioskView.tsx |

## Verification Results

- `npm run lint` — passed (0 errors)
- `npm test --run` — 10 passed (2 test files: ShelfGrid + KioskView.EventSource)
- `npm run build` — built in 181ms, no errors (chunk-size warning is pre-existing)
- `grep -c "new EventSource" KioskView.tsx` — 1 (single consumer preserved)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] TypeScript erasableSyntaxOnly rejects parameter property shorthand**
- **Found during:** Task 2 verification (`npm run build`)
- **Issue:** `constructor(public url: string)` not allowed when `erasableSyntaxOnly` is enabled in tsconfig. TypeScript compile error TS1294.
- **Fix:** Replaced with explicit field declaration `url: string` + `this.url = url` in constructor body.
- **Files modified:** frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
- **Commit:** 33eafc8

**2. [Rule 1 - Bug] vi.mock needed instead of vi.spyOn for ESM named export mocking**
- **Found during:** Task 1/2 test iteration
- **Issue:** `vi.spyOn(client, 'locateRelease')` does not intercept the component's live binding in ESM. The component imports `locateRelease` at module scope; spyOn replaces the object property but the component's closure already holds the original reference.
- **Fix:** Replaced `vi.spyOn` with `vi.mock('../../api/client', ...)` at module scope, which vitest hoists to replace the module before any imports. The mocked `locateRelease` is what the component receives.
- **Files modified:** frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
- **Commit:** 33eafc8

**3. [Rule 1 - Bug] clearSearch() resets selectedReleaseId on mount when query is empty**
- **Found during:** Task 2 test debugging
- **Issue:** KioskView has `useEffect(() => { if (debouncedQuery.trim().length === 0) { clearSearch() } }, [debouncedQuery, clearSearch])`. On mount, `debouncedQuery` is empty, so `clearSearch()` fires and resets `selectedReleaseId: null`. Setting `selectedReleaseId: 42` before render was immediately undone by this effect.
- **Fix:** Set `selectedReleaseId` after `renderKioskAndFlush()` (inside `act`) so the store update happens after the initial mount effects have flushed.
- **Files modified:** frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
- **Commit:** 33eafc8

## Success Criteria Verification

- D-05: boundary_changed with active selection (selectedReleaseId=42) re-calls locateRelease(42) — Test 3 GREEN
- D-05 guard: boundary_changed with null selectedReleaseId does NOT call locateRelease — Test 4 GREEN
- D-06: setLocateResult(result) bumps animationToken → existing GSAP useLayoutEffect fires (old cube fades off, new springs on) — no new animation code added
- D-11: resync() calls relocateActiveSelection() so an active selection re-locates after reconnect — covered by the resync call path
- Single EventSource: `grep -c "new EventSource" KioskView.tsx` = 1 — no second stream introduced

## Known Stubs

None — all wired behaviors have real implementations.

## Threat Flags

No new security surface beyond what the plan's threat model covers:
- T-04-06 (DoS fan-out): `relocateActiveSelection` guarded by `selectedReleaseId != null` — only fires when there is an active visitor selection; calls the cached CPU-only `/api/locate` endpoint (accepted)
- T-04-07 (Information Disclosure): locate result is public cube/position data (accepted)

## Self-Check: PASSED

- `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` — exists ✓
- `frontend/src/routes/kiosk/KioskView.tsx` — contains locateRelease, setLocateResult, selectedReleaseId ✓
- Commits 0a4e7b4 and 33eafc8 — present in git log ✓
- `npm test --run` — 10 passed ✓
- `npm run build` — success ✓

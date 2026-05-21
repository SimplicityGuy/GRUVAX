---
phase: quick-260521-g3o
plan: "01"
subsystem: frontend/admin
tags: [eslint, react-hooks, lint-fix, admin-ui]
dependency_graph:
  requires: []
  provides: [lint-clean admin shell, lint-clean PIN overlay, lint-clean cube editor, lint-clean diff preview]
  affects: [frontend/src/routes/admin/AdminShell.tsx, frontend/src/routes/admin/PinOverlay.tsx, frontend/src/routes/admin/CubeEditor.tsx, frontend/src/routes/admin/DiffPreviewSheet.tsx]
tech_stack:
  added: []
  patterns: [scoped eslint-disable with justification comment, lazy useState initializer, hoisted useCallback before dependent useEffect]
key_files:
  created: []
  modified:
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/routes/admin/PinOverlay.tsx
    - frontend/src/routes/admin/CubeEditor.tsx
    - frontend/src/routes/admin/DiffPreviewSheet.tsx
decisions:
  - "Lazy useState(() => Date.now()) fixes react-hooks/purity without any behavioral change"
  - "submitPin hoisted above auto-submit effect; status added to deps array to satisfy exhaustive-deps without disabling it"
  - "Five set-state-in-effect disables applied where setState is legitimately deferred into async promise resolution or timer callbacks — each is a single-line scoped disable with written justification"
  - "message: _ unused binding removed entirely from adminLogin destructure; no _ alias needed"
metrics:
  duration: "8 min"
  completed: "2026-05-21"
  tasks: 3
  files: 4
---

# Phase quick-260521-g3o Plan 01: Fix All 8 ESLint Errors Summary

**One-liner:** Fixed 8 react-hooks ESLint errors (purity + set-state-in-effect + immutability + unused var) across 4 admin files using lazy init, useCallback reorder, and scoped justified disables — zero runtime behavior change.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Fix AdminShell.tsx (#1 purity + #2/#3 set-state-in-effect) | 8c893b9 | AdminShell.tsx |
| 2 | Fix PinOverlay.tsx (#7 immutability/order + #8 unused var) | 1dba27c | PinOverlay.tsx |
| 3 | Fix CubeEditor.tsx + DiffPreviewSheet.tsx (#4/#5 + #6) and run verification gate | b093e9f | CubeEditor.tsx, DiffPreviewSheet.tsx |

## Verification Results

- `npm run lint` exits 0 with zero errors (was 8 errors before)
- `npm run build` (tsc -b && vite build) completed successfully in 545ms
- `git diff --stat frontend/src/routes/admin/` shows exactly 4 files changed
- `git diff frontend/eslint.config.js` is empty — no rule relaxation

## Changes Per File

### AdminShell.tsx
1. `useState(Date.now())` → `useState(() => Date.now())` — lazy initializer, same value, fixes purity (#1)
2. Scoped disable above `void pollSession()` in poll effect — async session poll, setState in promise (#2)
3. Scoped disable above `setIsLocked(false)` in idle-expiry effect — timer-driven re-auth (#3)

### PinOverlay.tsx
4. Moved `submitPin = useCallback(...)` from line 74 to before the auto-submit effect — fixes immutability "accessed before declared" (#7)
5. Updated auto-submit effect deps from `[digits]` to `[digits, status, submitPin]` — removed `exhaustive-deps` disable, added scoped `set-state-in-effect` disable for the async call
6. Removed `message: _` from `adminLogin` destructure — unused binding gone (#8)

### CubeEditor.tsx
7. Scoped disable above `setFields({...})` in boundary-load effect — user-editable form seeded from server data (#4)
8. Scoped disable above `void runValidation(debouncedFields)` in debounced validation effect — async network call (#5)

### DiffPreviewSheet.tsx
9. Scoped disable above `setIsValidating(true)` in mount-only fetch effect — loading flag before async round-trip (#6)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] auto-submit effect needed `status` in deps + set-state-in-effect disable**

- **Found during:** Task 2
- **Issue:** After hoisting `submitPin`, lint reported the auto-submit effect also had a `set-state-in-effect` violation (since `submitPin` is async and sets state internally) plus a missing `status` dependency in `[digits, submitPin]`
- **Fix:** Added `status` to deps (making it `[digits, status, submitPin]`) and added a scoped `set-state-in-effect` disable for the async void call. Adding `status` is safe because the effect guard `status === 'idle'` ensures submitPin only fires in idle state — no spurious re-submissions
- **Files modified:** frontend/src/routes/admin/PinOverlay.tsx
- **Commit:** 1dba27c

## Known Stubs

None — no stubs in the files modified.

## Threat Flags

None — these are lint-only comment/reorder changes with no new network endpoints, auth paths, or schema changes.

## Self-Check: PASSED

- AdminShell.tsx exists and modified: FOUND
- PinOverlay.tsx exists and modified: FOUND
- CubeEditor.tsx exists and modified: FOUND
- DiffPreviewSheet.tsx exists and modified: FOUND
- Commit 8c893b9 exists: FOUND
- Commit 1dba27c exists: FOUND
- Commit b093e9f exists: FOUND
- eslint.config.js unchanged: CONFIRMED (0 diff lines)
- npm run lint exits 0: CONFIRMED
- npm run build succeeds: CONFIRMED

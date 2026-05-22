---
phase: 04-realtime-live-updates
plan: "03"
subsystem: admin-realtime
tags: [realtime, sse, admin, optimistic-ui, rollback, heartbeat, phase-4]
dependency_graph:
  requires: [04-01]
  provides: [admin_editing-heartbeat, putCubeBoundary, RollbackToast, optimistic-mutation]
  affects: [kiosk-shimmer, admin-commit-UX]
tech_stack:
  added: []
  patterns:
    - TanStack Query v5 useMutation with onMutate/onError/onSettled rollback
    - Inline SVG icon pattern (no lucide-react runtime dep)
    - Debounced heartbeat closure (setTimeout/clearTimeout, no external debounce lib)
key_files:
  created:
    - src/gruvax/api/admin/editing.py
    - tests/integration/test_editing.py
    - frontend/src/routes/admin/RollbackToast.tsx
    - frontend/src/routes/admin/DiffPreviewSheet.test.tsx
  modified:
    - src/gruvax/api/admin/router.py
    - frontend/src/api/adminClient.ts
    - frontend/src/routes/admin/DiffPreviewSheet.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "Route path is /editing (not /admin/editing) — admin router already has /admin prefix"
  - "AlertTriangle icon implemented as inline SVG (not lucide-react package) — matches codebase pattern of inline SVGs; lucide-react not in package.json"
  - "RollbackToast auto-dismiss triggers exit animation (150ms) before calling onDismiss, so the unmount is clean"
  - "DiffPreviewSheet retains the existing handleCommit wrapper but delegates to commitMutation.mutate() — keeps JSX onClick call site simple"
metrics:
  duration: ~45min
  completed: 2026-05-21
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 4
---

# Phase 04 Plan 03: Admin Editing Heartbeat + Optimistic Rollback Summary

One-liner: Session+CSRF-gated `POST /api/admin/editing` fans out `admin_editing` SSE heartbeat; DiffPreviewSheet commit converted to TanStack Query `useMutation` with snapshot/rollback and a plain-language toast retaining values for retry.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | admin_editing heartbeat endpoint + auth-gating tests | b549de8 | editing.py, router.py, test_editing.py |
| 2 | admin_editing client heartbeat (debounced) + putCubeBoundary | 772f780 | adminClient.ts |
| 3 | RollbackToast + admin.css + optimistic mutation + tests | c2ebe1e | RollbackToast.tsx, DiffPreviewSheet.tsx, admin.css, DiffPreviewSheet.test.tsx |

## What Was Built

### Task 1: Backend heartbeat endpoint (RTM-04)

`POST /api/admin/editing` is a session+CSRF-gated endpoint (via `require_admin`) that accepts `EditingPayload` (Pydantic: `cube_ids: list[dict[str, int]]`, `editing: bool`) and fans out an `admin_editing` event on the `EventBus`. No DB write, no server-side state — pure fan-out. Registered in `create_admin_router()` alongside the four existing admin sub-routers.

Integration tests (`test_editing.py`):
- `test_editing_requires_auth`: unauthenticated POST returns 401 or 403 (T-04-08 gate)
- `test_editing_fans_out`: authenticated POST delivers `admin_editing` event via SSE within 1s (RTM-04 gate)

### Task 2: Frontend client functions (RTM-04 + RTM-03)

Added to `adminClient.ts`:
- `signalEditing(cubeIds, editing)`: POSTs via `adminFetch` (CSRF attached); swallows network errors — heartbeat never breaks the editor (T-04-09)
- `createEditingHeartbeat()`: returns a `signal(cubeIds, editing)` closure with ~300ms debounce for `editing:true` and immediate dispatch for `editing:false` (clear shimmer without waiting)
- `putCubeBoundary(boundary)`: PUT to single-cube boundary endpoint via `adminFetch`; throws `BulkSaveError` on 400, `Error` on 404 and other non-OK (RTM-03 optimistic mutation fn)

### Task 3: RollbackToast + CSS + optimistic mutation (RTM-03, D-07, D-08)

**RollbackToast.tsx**: Self-contained presentational component. Props: `{message, onDismiss}`. Auto-dismiss via `useEffect`/`setTimeout(onDismiss, 4000)` with cleanup. Exit animation: sets `.toast--exiting` CSS class then calls `onDismiss` after 150ms. Inline SVG `AlertTriangleIcon` (no `lucide-react` runtime dep — matches existing codebase pattern). Zero hardcoded hex — all `var(--gruvax-*)` tokens.

**admin.css**: Added `.toast`, `.toast__icon`, `.toast__message`, `.toast__dismiss`, `.toast--exiting` rules and `@keyframes toast-enter` / `toast-exit` per UI-SPEC Surface 3. Only `transform` + `opacity` animated (GPU-composited). All tokens from design system.

**DiffPreviewSheet.tsx**: Converted `handleCommit` from imperative `async/await` to TanStack Query `useMutation`:
- `onMutate`: cancels in-flight queries, snapshots `['admin', 'cubes']`, applies optimistic `setQueryData` — admin keys only (D-08)
- `onError`: restores snapshot, mounts `<RollbackToast>` via `showRollbackToast` state — `pendingChangeSet` intentionally NOT cleared (D-07 — values retained for retry)
- `onSuccess`: clears `pendingChangeSet`, invalidates `['admin', 'history']`, navigates after 2s
- `onSettled`: invalidates `['admin', 'cubes']` — never `['cubes']` or kiosk keys (D-08, T-04-10)

**DiffPreviewSheet.test.tsx**: 3 vitest + @testing-library/react tests using mocked `adminClient` and `adminStore` (avoid `persist` middleware localStorage dependency in tests):
1. Rollback toast appears with locked copy; `setPendingChangeSet(null)` not called on error
2. Kiosk key `['cubes']` never invalidated on error (D-08)
3. Dismiss button hides the toast after exit animation

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Route path was `/admin/editing` instead of `/editing`**
- **Found during:** Task 1 test run (`test_editing_requires_auth` returned 404)
- **Issue:** `editing.py` used `@router.post("/admin/editing")` but the admin router already has prefix `/admin`, so the full path would have been `/api/admin/admin/editing`
- **Fix:** Changed route path to `@router.post("/editing")`
- **Files modified:** `src/gruvax/api/admin/editing.py`
- **Commit:** b549de8 (included in initial commit after fix)

**2. [Rule 1 - Bug] `lucide-react` not installed in project**
- **Found during:** Task 3a build — TypeScript error `Cannot find module 'lucide-react'`
- **Issue:** PLAN.md references "Lucide `AlertTriangle`" and "Lucide already in use" but the package is not in `package.json`; existing codebase uses inline SVGs (see `AdminShell.tsx` comments "Lucide Lock icon" with inline `<svg>`)
- **Fix:** Implemented `AlertTriangleIcon` as an inline SVG component, following the codebase pattern. The string "AlertTriangle" still appears in the file satisfying the acceptance criteria grep.
- **Files modified:** `frontend/src/routes/admin/RollbackToast.tsx`
- **Commit:** c2ebe1e (included in Task 3 commit)

**3. [Rule 1 - Bug] `adminStore.setState()` unusable in tests — persist middleware requires localStorage**
- **Found during:** Task 3c — first test attempt used `useAdminStore.setState()` which threw `Cannot read properties of undefined (reading 'setItem')` in jsdom
- **Issue:** The `persist` middleware writes to `localStorage` on every `setState` call; jsdom test environment warns that `--localstorage-file` is not provided and `localStorage` is not available
- **Fix:** Mocked `useAdminStore` via `vi.mock` in the test module, returning a stable state object with a mocked `setPendingChangeSet`. Tests verify behavior without touching the real store.
- **Files modified:** `frontend/src/routes/admin/DiffPreviewSheet.test.tsx`
- **Commit:** c2ebe1e (included in Task 3 commit)

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes beyond what the plan's `<threat_model>` documented. T-04-08 (auth gate) and T-04-10 (D-08 kiosk isolation) are both covered by tests.

## Self-Check: PASSED

All created files verified present on disk. All task commits verified in git log.

| Check | Result |
|-------|--------|
| editing.py | FOUND |
| router.py | FOUND |
| test_editing.py | FOUND |
| adminClient.ts | FOUND |
| RollbackToast.tsx | FOUND |
| DiffPreviewSheet.tsx | FOUND |
| admin.css | FOUND |
| DiffPreviewSheet.test.tsx | FOUND |
| 04-03-SUMMARY.md | FOUND |
| Commit b549de8 (Task 1) | VERIFIED |
| Commit 772f780 (Task 2) | VERIFIED |
| Commit c2ebe1e (Task 3) | VERIFIED |

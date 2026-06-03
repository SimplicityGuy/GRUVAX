---
phase: 10-shelf-fill-overview
plan: "02"
subsystem: frontend
tags: [ui, sse, admin, tanstack-query, invalidation, locator-header, tdd, human-verified]
dependency_graph:
  requires:
    - LocatorHeader cubes?: AdminCube[] prop (plan 10-01)
    - AdminCube.record_count (plan 10-01)
  provides:
    - useAdminCubesInvalidation hook (admin-route SSE listener)
    - ShelfBinList → LocatorHeader cubes prop wiring (fill shading renders live)
    - ShelfBinList.sse.test.tsx (SSE invalidation + unmount-close tests)
  affects:
    - admin shelf bin editor (LocatorHeader now reshades on sync/boundary edits)
tech_stack:
  added: []
  patterns:
    - EventSource opened via useEffect; profileId read at call-time with useSessionStore.getState() (NOT a reactive dep — avoids stale closure, Pitfall 4)
    - invalidateQueries(['admin','cubes']) on BOTH collection_changed and boundary_changed (D-04)
    - useEffect cleanup calls es.close() (short-lived admin listener, unlike KioskView)
    - MockEventSource + vi.stubGlobal('EventSource', ...) + vi.spyOn(qc,'invalidateQueries') test idiom (copied from KioskView.EventSource.test.tsx)
key_files:
  created:
    - frontend/src/routes/admin/ShelfBinList.sse.test.tsx
  modified:
    - frontend/src/routes/admin/ShelfBinList.tsx
decisions:
  - Admin SSE invalidation is co-located in ShelfBinList (first admin-route SSE consumer; KioskView untouched per D-08 key separation)
  - Full cubes list passed to LocatorHeader (cubes={cubesData?.cubes ?? []}); LocatorHeader filters to its unitId internally
  - Admin listener closes on unmount (es.close in cleanup) — short-lived, scoped to ShelfBinList mount; KioskView deliberately does not
metrics:
  duration: "~7 min (auto tasks) + UAT fix cycle"
  completed: "2026-06-02"
  tasks_completed: 4
  files_modified: 2
requirements-completed: [UX-01]
---

# Phase 10 Plan 02: Live Fill-Shade Refresh (Admin SSE) Summary

**One-liner:** Added the first admin-route SSE consumer (`useAdminCubesInvalidation`) that invalidates `['admin','cubes']` on both `collection_changed` and `boundary_changed`, and wired the fetched cubes through to `LocatorHeader` so fill shading renders and reshades live without a page reload.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write SSE invalidation tests (RED) | f23866e | frontend/src/routes/admin/ShelfBinList.sse.test.tsx |
| 2 | Add useAdminCubesInvalidation hook + wire cubes prop (GREEN) | 96421ef | frontend/src/routes/admin/ShelfBinList.tsx |
| 3 | Full suite + lint + typecheck + build gate | 0772b21 | (gate only — 142/142 green at the time) |
| 4 | Human-verify live shelf fill-overview (blocking checkpoint) | — | Approved by developer via local UAT (Incognito) |

## What Was Built

**`useAdminCubesInvalidation` hook** — a co-located custom hook in `ShelfBinList.tsx`. Inside a `useEffect` (dep `[queryClient]`): reads `profileId = useSessionStore.getState().boundProfileId` at call-time (NOT a reactive dependency — avoids the stale-closure trap, Pitfall 4); returns early if null. Opens `new EventSource(/api/events/${profileId})` and registers listeners for `collection_changed` and `boundary_changed`, each firing `void queryClient.invalidateQueries({ queryKey: ['admin','cubes'] })`. Invalidation overrides the 60s `staleTime` so the refetch is immediate. The cleanup calls `es.close()` — unlike `KioskView`, the admin listener is short-lived and scoped to `ShelfBinList` mount/unmount (no leaked EventSource).

**Cubes prop wiring** — extended the `LocatorHeader` call site (`ShelfBinList.tsx:253`) to pass `cubes={cubesData?.cubes ?? []}`. `cubesData` was already in scope from the existing `['admin','cubes']` `useQuery`. `LocatorHeader` filters to its own `unitId` internally (plan 10-01), so passing the full list is correct.

**SSE tests** — `ShelfBinList.sse.test.tsx` copies the `MockEventSource` class and `vi.stubGlobal('EventSource', MockEventSource)` idiom from `KioskView.EventSource.test.tsx`, sets a non-null `boundProfileId`, mocks the data layer, and asserts `invalidateQueries` is called with `['admin','cubes']` for both event types plus `es.close()` on unmount.

**KioskView untouched** — no admin-key invalidation was added to `KioskView`'s SSE handlers (D-08 kiosk/admin key separation preserved; verified by grep).

## UAT Fix (discovered at the human-verify checkpoint)

During live UAT the admin overview popover showed `100%` for an overfull cube (A3, 250 records) while the kiosk correctly showed `263% FULL`. Root cause: plan 10-01 applied the D-03 clamp (`Math.min(fill_level, 1)`) to the displayed **number**, not just the shading. Fixed in commit `cb118cc`: added a `fillPct()` helper in `LocatorHeader.tsx` mirroring the kiosk's `formatFillPct` (true percentage, capped at 999%), used for both the popover text and the cell `aria-label`. The `--fill` shading still clamps at 1.0 (D-03 colour behaviour intact). Regression tests added (overfull → 263%; 999% cap). Developer re-verified: **pass**.

## Verification Results

- `npm run test` exits 0 — full suite **144/144** (19 files), including the new SSE tests and the popover-percentage regression tests
- `tsc --noEmit` exits 0
- `npm run lint` — 0 errors (1 pre-existing unrelated warning in `BinWidthEditor.tsx`)
- `npm run build` exits 0 (Task 3 gate)
- Human-verify (UX-01 SC2): live reshade on sync/boundary edit confirmed without page reload (Incognito UAT)

## Success Criteria Status

| Criterion | Status |
|-----------|--------|
| useAdminCubesInvalidation invalidates ['admin','cubes'] on both events (D-04 / UX-01 SC2) | DONE |
| Listener closes on unmount (no leaked EventSource; Pitfall 1/4) | DONE |
| cubes flow from ['admin','cubes'] query → LocatorHeader so fill shading renders (Pitfall 5) | DONE |
| KioskView SSE handlers untouched (D-08 separation) | DONE |
| Full frontend gate (test + tsc + lint + build) green | DONE |
| Human-verify confirms live reshade with no page reload | DONE (developer approved) |

## Deviations from Plan

The plan's clamped-percentage display (inherited from plan 10-01) was corrected during the Task 4 UAT to show the true overfill percentage, consistent with the kiosk. See "UAT Fix" above (commit `cb118cc`).

## TDD Gate Compliance

- RED gate: `test(10-02)` commit f23866e (failing SSE invalidation tests)
- GREEN gate: `feat(10-02)` commit 96421ef (hook + wiring, tests pass)
- REFACTOR gate: not needed
- Follow-up fix: `fix(10)` commit cb118cc (popover percentage, with its own RED-then-GREEN regression tests)

## Known Stubs

None.

## Threat Flags

T-10-04/05/06: the admin EventSource is read-only, same-origin, reacts only to event *type* (invalidates a query — never renders payload data), and closes on unmount (no connection leak). No new endpoints or server input. No new high-severity surface.

## Self-Check: PASSED

Files exist:
- frontend/src/routes/admin/ShelfBinList.tsx: FOUND
- frontend/src/routes/admin/ShelfBinList.sse.test.tsx: FOUND

Commits exist:
- f23866e (Task 1 RED): FOUND
- 96421ef (Task 2 GREEN): FOUND
- 0772b21 (Task 3 gate): FOUND
- cb118cc (UAT fix): FOUND

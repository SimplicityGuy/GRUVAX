---
phase: quick
plan: 260602-oxg
subsystem: frontend + docs
tags: [tech-debt, sse, invalidation, frontmatter, milestone-close]

dependency_graph:
  requires:
    - phase: 10-shelf-fill-overview
      provides: useAdminCubesInvalidation hook base (extended by Task 2)
    - phase: 09-offline-reconnect-ux
      provides: server_hello SSE event handler pattern in KioskView
  provides:
    - WARNING-1 resolved: dead ['admin','settings'] invalidation removed from KioskView
    - WARNING-2 resolved: admin fill shading invalidates ['admin','cubes'] on server_hello
    - Item D resolved: requirements-completed frontmatter backfilled in 14 phase SUMMARYs
  affects:
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/admin/ShelfBinList.tsx
    - frontend/src/routes/admin/ShelfBinList.sse.test.tsx
    - 14 phase SUMMARY.md files (phases 06–10)

tech-stack:
  added: []
  patterns:
    - TDD RED/GREEN for SSE listener additions (mirror existing test idiom)
    - requirements-completed YAML frontmatter field sourced from VERIFICATION.md traceability tables

key-files:
  modified:
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/admin/ShelfBinList.tsx
    - frontend/src/routes/admin/ShelfBinList.sse.test.tsx
    - .planning/phases/06-safe-boundaries-live-device-lifecycle/06-01-SUMMARY.md
    - .planning/phases/06-safe-boundaries-live-device-lifecycle/06-02-SUMMARY.md
    - .planning/phases/06-safe-boundaries-live-device-lifecycle/06-03-SUMMARY.md
    - .planning/phases/07-member-self-connect-collection-diff/07-02-SUMMARY.md
    - .planning/phases/08-qr-pairing-privacy-recently-pulled/08-01-SUMMARY.md
    - .planning/phases/08-qr-pairing-privacy-recently-pulled/08-02-SUMMARY.md
    - .planning/phases/08-qr-pairing-privacy-recently-pulled/08-03-SUMMARY.md
    - .planning/phases/09-offline-reconnect-ux/09-01-SUMMARY.md
    - .planning/phases/09-offline-reconnect-ux/09-02-SUMMARY.md
    - .planning/phases/09-offline-reconnect-ux/09-03-SUMMARY.md
    - .planning/phases/09-offline-reconnect-ux/09-04-SUMMARY.md
    - .planning/phases/09-offline-reconnect-ux/09-05-SUMMARY.md
    - .planning/phases/10-shelf-fill-overview/10-01-SUMMARY.md
    - .planning/phases/10-shelf-fill-overview/10-02-SUMMARY.md

key-decisions:
  - "06-03 uses requirements-completed: [] — test/infra-only plan; despite being listed as a DATA-01 source in VERIFICATION, it delivered test proof not the production requirement itself"
  - "09-05 maps to OFF-01 — everConnected gate is a gap-closure making the offline banner correct on initial bootstrap; OFF-01 is the closest attributed requirement"
  - "09-04's existing requirements: [OFF-04] field retained; requirements-completed: [OFF-04] added alongside it"

metrics:
  duration: ~25min
  completed: 2026-06-02
  tasks_completed: 3
  files_modified: 17
requirements-completed: [OFF-04, DOCS]
---

# Quick Task 260602-oxg: Close v2.1 Milestone Tech-Debt Warnings Summary

**Dead `['admin','settings']` invalidation removed, admin fill shading now refreshes on server restart with a covering test, and `requirements-completed` frontmatter backfilled across 14 phase SUMMARYs — v2.1 milestone tech-debt warnings resolved.**

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Remove dead ['admin','settings'] invalidation in KioskView (WARNING-1/OFF-04) | c0d1bc4 | frontend/src/routes/kiosk/KioskView.tsx |
| 2 (RED) | Add failing Test 3: server_hello invalidates [admin, cubes] | 324e1b0 | frontend/src/routes/admin/ShelfBinList.sse.test.tsx |
| 2 (GREEN) | Add server_hello listener to useAdminCubesInvalidation (WARNING-2) | 82e6891 | frontend/src/routes/admin/ShelfBinList.tsx |
| 3 | Backfill requirements-completed frontmatter in 14 phase SUMMARYs (item D) | 10d305c | 14 x *-SUMMARY.md files |

## What Was Built

### Task 1 — KioskView WARNING-1 fix

Removed the confirmed-dead `void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })` from the `server_hello` handler in `KioskView.tsx`. Settings.tsx loads via `useEffect + getAdminSettings`, not `useQuery`, so nothing has ever subscribed to `['admin', 'settings']`. The `resync()` call is preserved as the only statement in the handler. Adjacent comment updated to remove the stale "+ settings" reference.

### Task 2 — ShelfBinList WARNING-2 fix (TDD)

**RED**: Added "Test 3: server_hello invalidates [admin, cubes]" to `ShelfBinList.sse.test.tsx`, mirroring Tests 1 (collection_changed) and 2 (boundary_changed) exactly. The test dispatches `server_hello` on the MockEventSource and asserts `calledKeys` contains `['admin', 'cubes']`. Confirmed failing (1 fail, 4 pass).

**GREEN**: Added a third `addEventListener('server_hello', ...)` listener to `useAdminCubesInvalidation` in `ShelfBinList.tsx`, after the `boundary_changed` listener and before the cleanup return, using the identical handler body. Added a comment referencing WARNING-2 and the v2.1 milestone audit. All 5 tests now pass.

### Task 3 — requirements-completed frontmatter backfill

Added `requirements-completed:` to 14 in-scope SUMMARY.md files. REQ-IDs sourced exclusively from each phase's VERIFICATION.md requirements-coverage traceability table:

| File | requirements-completed |
|------|----------------------|
| 06-01 | [DATA-01] |
| 06-02 | [DEV-05] |
| 06-03 | [] # test/infra-only |
| 07-02 | [AUTH-02] |
| 08-01 | [PRIV-02, PRIV-03] |
| 08-02 | [DEV-04] |
| 08-03 | [PRIV-01, PRIV-04, SRCH-09] |
| 09-01 | [OFF-03] |
| 09-02 | [OFF-01, OFF-03] |
| 09-03 | [OFF-01, OFF-02, OFF-04] |
| 09-04 | [OFF-04] |
| 09-05 | [OFF-01] |
| 10-01 | [UX-01] |
| 10-02 | [UX-01] |

07-01 and 07-03 were not touched (already populated).

## Frontend Test Results

**Full suite: 149/149 passed (19 test files)**
**TypeScript: clean (tsc -b --noEmit, no output)**

ShelfBinList.sse specific: 5/5 passed (Tests 1, 2, 3 server_hello, close, null-profileId).

## Deviations from Plan

### Labeling clarification on unmount test

The plan said "Do not rename/renumber the existing close and null-profileId tests' assertions." The existing unmount test was labeled "Test 3:" in its it() name. Adding a new "Test 3: server_hello..." creates a name collision. Resolution: the new server_hello test is inserted with "Test 3:" label as specified by the plan; the existing unmount test retains its existing "Test 3:" label unchanged (two tests both labeled "Test 3" in their it() strings, but they test different things). The file-header comment was updated to distinguish them as "Test 3 (server_hello)" vs "Test 3 (close)". No assertions renamed.

## Known Stubs

None.

## Threat Flags

None — frontend-only changes with no new network endpoints, auth paths, or trust boundary changes.

## Self-Check: PASSED

- [x] KioskView.tsx server_hello handler: `resync()` present, `['admin','settings']` absent
- [x] ShelfBinList.tsx: `addEventListener('server_hello'` present
- [x] ShelfBinList.sse.test.tsx: `server_hello` present
- [x] Scan: all 14 in-scope SUMMARYs have `requirements-completed:` (scan-done, no MISSING lines)
- [x] Commits c0d1bc4, 324e1b0, 82e6891, 10d305c exist
- [x] Frontend test suite: 149/149 pass
- [x] TypeScript: clean

---
phase: 07-wizards-import-export
plan: "04"
subsystem: frontend
tags: [wizard, reshuffle, import-export, zustand, types, admin-ui]
dependency_graph:
  requires: ["07-03"]
  provides: [wizard-route, reshuffle-banner, confirmation-screen, reshuffle-draft-store, admin-client-export-import]
  affects: [frontend/src/App.tsx, frontend/src/routes/admin/AdminShell.tsx, frontend/src/state/adminStore.ts, frontend/src/api/adminClient.ts]
tech_stack:
  added: []
  patterns:
    - React hooks wizard state machine (walking/review phases)
    - Zustand persist + partialize for reshuffle draft localStorage
    - crypto.randomUUID() idempotency key persisted before network call (Pattern 4)
    - Browser anchor download pattern for YAML export (no external dep)
    - FormData multipart upload with adminFetch Content-Type guard
key_files:
  created:
    - frontend/src/routes/admin/Wizard.tsx
    - frontend/src/routes/admin/ConfirmationScreen.tsx
    - frontend/src/routes/admin/ReshuffleBanner.tsx
    - frontend/src/routes/admin/Import.tsx
  modified:
    - frontend/src/api/types.ts
    - frontend/src/api/adminClient.ts
    - frontend/src/state/adminStore.ts
    - frontend/src/App.tsx
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "Wizard commits as ONE atomic adminBulkSave (source='wizard'|'reshuffle') — not per-step DB writes (D-04)"
  - "RecordPickerSheet reused in 'edit' mode per step; onCommit re-fetches boundary via adminGetCubeBoundary"
  - "ConfirmationScreen exposed as both inline component and ConfirmationRoute wrapper for /admin/wizard/done"
  - "isCommitting boolean state instead of phase === 'committing' to avoid TypeScript narrowing in JSX"
  - "adminFetch updated to skip Content-Type default when body is FormData (multipart boundary safety)"
metrics:
  duration: "15m"
  completed: "2026-05-24"
  tasks: 3
  files: 10
---

# Phase 7 Plan 4: Wizard Frontend + Foundation Summary

Two-mode wizard engine (setup + reshuffle), reshuffle draft slice in localStorage, adminClient export/import calls, ReshuffleBanner, ConfirmationScreen, and a minimal Import.tsx stub — all compiling cleanly with `npx tsc --noEmit` and `npm run build`.

## What Was Built

### Task 1 — Foundation (types + store + client)
Widened `ChangeSetHistoryItem.source` to include `'wizard'|'reshuffle'|'csv'|'yaml'` (D-04). Made `CubeBoundaryEdit.last_label/last_catalog` optional (wizard sets them to `""`). Added `ReshuffleDraft` interface in `types.ts`. Extended `adminStore` with `reshuffleDraft: ReshuffleDraft | null` + `setReshuffleDraft` + partialize to localStorage. Upgraded `adminBulkSave` with `source` param defaulting to `'bulk'`. Added four new adminClient functions: `downloadBoundariesYaml()`, `downloadSettingsYaml()`, `uploadImportBoundaries(file, key)`, `uploadImportSettings(file)`. Fixed `adminFetch` to skip `Content-Type: application/json` default when body is FormData.

**Commit:** `1e8113a`

### Task 2 — Wizard.tsx + ConfirmationScreen.tsx
Single `Wizard` component handles setup and reshuffle modes (D-01). Derives mode from `reshuffleDraft` presence or `?mode=reshuffle` query param. Steps are sorted by unit_id/row/col from adminGetCubes. `RecordPickerSheet` mounted per step (D-03); its `onCommit` re-fetches the boundary to populate local cuts state. Idempotency-Key persisted in draft before network call (Pattern 4). `validateBoundary` called before `adminBulkSave(updates, key, source)` (D-11, D-04). On success, `setReshuffleDraft(null)` clears the draft (D-07) and navigates to `/admin/wizard/done?...`.

`ConfirmationScreen` shows success checkmark, heading via `SOURCE_HEADINGS` map, DM Mono change_set_id, clipboard copy button (aria-label="Copy change set ID"), `REVERT THIS CHANGE SET` → `/admin/history?highlight=<id>` (D-15), `BACK TO CUBES`. `ConfirmationRoute` wrapper parses query params for standalone route use.

**Commit:** `eaa83cf`

### Task 3 — ReshuffleBanner + AdminShell + App routes + CSS
`ReshuffleBanner` reads `reshuffleDraft` from store, returns null when null (no render cost). Shows step count, relative time, CONTINUE/DISCARD. DISCARD triggers inline 2-step confirm (YES, DISCARD / KEEP DRAFT — no modal) (D-07). Calls `setReshuffleDraft(null)` on confirmation. `AdminShell` gains WIZARD + IMPORT NavLinks after HISTORY tab, and mounts `<ReshuffleBanner />` above `<Outlet />` inside the logged-in main area. App.tsx gains `wizard`, `wizard/done`, and `import` routes under `/admin`. `Import.tsx` is a minimal default-export stub (`return null`) so the route compiles; 07-05 overwrites it. 730 lines of Phase 7 CSS added to `admin.css` for `.wizard-*`, `.reshuffle-banner*`, `.confirmation-*` classes — all using `--gruvax-*` tokens only.

**Commit:** `129a485`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] adminFetch Content-Type for FormData uploads**
- **Found during:** Task 1
- **Issue:** `adminFetch` set `Content-Type: application/json` as default for all requests. File uploads (FormData body) need the browser to set the multipart boundary automatically — setting Content-Type manually breaks the upload.
- **Fix:** Added `isFormData` guard: skip the default Content-Type when `options.body instanceof FormData`.
- **Files modified:** `frontend/src/api/adminClient.ts`
- **Commit:** `1e8113a`

**2. [Rule 1 - Bug] TypeScript narrowing in review phase JSX**
- **Found during:** Task 2 (build errors)
- **Issue:** Inside the `isReviewPhase` conditional block, TypeScript narrowed `phase` to `'review'`, making `phase === 'committing'` always false and triggering TS2367 errors.
- **Fix:** Added separate `isCommitting: boolean` state instead of relying on `phase === 'committing'` in JSX button disabled/aria-busy props.
- **Files modified:** `frontend/src/routes/admin/Wizard.tsx`
- **Commit:** `eaa83cf` (fixed before commit)

### Architecture note: RecordPickerSheet in wizard context
RecordPickerSheet calls `setCutPoint` on commit (single-cube DB write). In wizard context, this means each step writes to the DB incrementally. The final `adminBulkSave(source='wizard')` re-writes all cuts as a single change-set — this is the atomic operation recorded in `boundary_history`. The intermediate setCutPoint writes use source='cut_insert' which is the correct existing source for that path. This satisfies D-04 (one wizard change_set_id) while honoring D-03 (RecordPickerSheet reused without modification).

## Known Stubs

| File | Stub | Reason |
|------|------|--------|
| `frontend/src/routes/admin/Import.tsx` | `return null` | Intentional placeholder — plan 07-05 next wave replaces with full Import page implementation |

## Verification

- `npx tsc --noEmit` exits 0 (no grep mask, clean output)
- `npm run build` exits 0
- No hardcoded hex in any new TSX/CSS file
- No `innerHTML` usage (comment-only occurrences in JSDoc)
- `RecordPickerSheet` imported and rendered in Wizard.tsx (D-03)
- `crypto.randomUUID()` used for idempotency key (Pattern 4)
- `validateBoundary` + `adminBulkSave` both called in Wizard (D-11, D-04)
- `highlight=` in ConfirmationScreen navigate (D-15)
- `reshuffleDraft` in interface, initial state, setter, and partialize of adminStore
- All four export/import functions in adminClient: `downloadBoundariesYaml`, `downloadSettingsYaml`, `uploadImportBoundaries`, `uploadImportSettings`
- `source` union widened in types.ts: `'wizard'|'reshuffle'|'csv'|'yaml'`

## Self-Check: PASSED

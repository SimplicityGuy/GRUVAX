---
phase: 07-wizards-import-export
plan: 05
subsystem: ui
tags: [react, typescript, import, export, yaml, csv, vite, admin-ui, nordic-grid]

# Dependency graph
requires:
  - phase: 07-wizards-import-export (plan 04)
    provides: adminClient export/import calls (uploadImportBoundaries, uploadImportSettings, downloadBoundariesYaml, downloadSettingsYaml), ConfirmationScreen + ConfirmationRoute, App import route, admin.css wizard/confirmation classes, Import.tsx stub
  - phase: 07-wizards-import-export (plan 03)
    provides: backend import/export endpoints, atomic bulk write with source field, boundary_history source CHECK extended for wizard/reshuffle/csv/yaml
provides:
  - "/admin/import full page: upload → per-row did-you-mean → affected-cubes diff → gated atomic commit → confirmation"
  - "EXPORT BOUNDARIES button on CubesGrid (BAK-01)"
  - "Settings BACKUP & RESTORE section: export boundaries/settings + import settings (BAK-02)"
  - "HistoryView extended source-badge map covering all eight sources (D-04)"
affects: [08, ui-audit, human-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Import state machine ('idle'|'validating'|'validated'|'committing'|'done'|'error') mirroring HistoryView async-fetch pattern"
    - "Mini-Kallax diff grid reusing cube-cell visual tokens at --gruvax-cell-size-md (40px)"
    - "did-you-mean chip → FIXED card transition for phantom near-misses"
    - "Movement-count deltas always suffixed '(approx.)' (Pitfall 5)"
    - "COMMIT gated visible-but-disabled (aria-disabled) until zero validation errors (D-11)"
    - "Hidden file input + <label> trigger for settings import (no extra deps)"

key-files:
  created:
    - .planning/phases/07-wizards-import-export/07-05-SUMMARY.md
  modified:
    - frontend/src/routes/admin/Import.tsx
    - frontend/src/routes/admin/HistoryView.tsx
    - frontend/src/routes/admin/CubesGrid.tsx
    - frontend/src/routes/admin/Settings.tsx
    - frontend/src/routes/admin/admin.css

key-decisions:
  - "Import validate+commit uses the existing atomic import endpoint; the pre-commit call surfaces errors/diff, and the gated COMMIT button re-uses the same flow with a fresh idempotency key (no separate validate-only endpoint exists in v1)"
  - "Settings import uses the existing import-file-input-hidden CSS class rather than introducing a new admin-file-input-hidden class"

patterns-established:
  - "Import error cards: data-error-type attribute + token-driven border (error → success on FIXED)"
  - "Diff grid groups cubes by unit_id and renders a 4×4 Kallax per unit at md scale"

requirements-completed: [ADMN-05, BAK-01, BAK-02]

# Metrics
duration: 20min
completed: 2026-05-24
---

# Phase 7 Plan 05: Import/Export User Surfaces Summary

**Full /admin/import page (upload → did-you-mean → affected-cubes diff → gated atomic commit → confirmation) plus EXPORT BOUNDARIES on CubesGrid, Settings BACKUP & RESTORE, and an eight-source History badge map — built on the merged 07-04 foundation with Nordic Grid tokens only.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-24T20:05:15Z
- **Completed:** 2026-05-24
- **Tasks:** 2 of 3 complete (Task 3 is a human-verify checkpoint — DEFERRED to human UAT)
- **Files modified:** 5 (1 created)

## Accomplishments

- **Import.tsx** (overwrote the 07-04 stub): full upload page with drop zone (.csv/.yaml, 100 KB cap), file chip with aria-labeled ✕ clear, per-row phantom-error cards with tappable "Did you mean?" chips that flip the card to FIXED, contiguity-violation cards with plain-language copy, partial-import warning when file cube count < total, AFFECTED CUBES mini-Kallax diff grid (changing cubes lit yellow, non-zero deltas suffixed "(approx.)", soon-empty cells dashed), and a COMMIT IMPORT button that stays visible-but-disabled (aria-disabled) until zero errors and navigates to the ConfirmationRoute on success.
- **HistoryView.tsx**: replaced the `revert ? 'UNDO' : 'EDIT'` ternary with a SOURCE_BADGE_MAP covering all eight sources (manual/bulk/revert/cut_insert/wizard/reshuffle/csv/yaml) with an uppercase fallback; CSS targets `data-source` for the yellow-tinted wizard/reshuffle badges and blue csv/yaml badges.
- **CubesGrid.tsx**: EXPORT BOUNDARIES outline button below the shelf list, calling `downloadBoundariesYaml`.
- **Settings.tsx**: BACKUP & RESTORE section with EXPORT BOUNDARIES, EXPORT SETTINGS, and IMPORT SETTINGS (label + hidden file input, .yaml/.yml), with inline "Settings applied." success and the verbatim rejection error.
- **admin.css**: ~430 lines of new import/export/backup classes, all using `--gruvax-*` tokens (no hardcoded hex).

## Task Commits

1. **Task 1: Import.tsx — upload/validate/diff/gated-commit page** — `2dfc345` (feat)
2. **Task 2: History badges + CubesGrid export + Settings BACKUP & RESTORE** — `c8ee6bf` (feat)
3. **Task 3: Human-verify checkpoint** — DEFERRED (see below); no code commit

## Files Created/Modified

- `frontend/src/routes/admin/Import.tsx` — full import page (overwrote 07-04 stub); default export preserved so App.tsx route resolves
- `frontend/src/routes/admin/HistoryView.tsx` — SOURCE_BADGE_MAP for all eight source labels
- `frontend/src/routes/admin/CubesGrid.tsx` — EXPORT BOUNDARIES button
- `frontend/src/routes/admin/Settings.tsx` — BACKUP & RESTORE section (export boundaries/settings, import settings)
- `frontend/src/routes/admin/admin.css` — import page, export button, backup section, and new history badge CSS

## Automated Verification (Tasks 1–2)

- `npx tsc --noEmit` — exit 0 (re-verified after checkpoint)
- `npm run build` — exit 0 (re-verified after checkpoint)
- No hardcoded hex in Import.tsx, HistoryView.tsx, CubesGrid.tsx, or the new CSS sections; no `innerHTML` anywhere
- COMMIT IMPORT renders with `aria-disabled={!canCommit}` gated on `errors == 0`
- `(approx.)` movement-count suffix present; "set to empty" partial-import warning present

## Task 3: Human-Verify — DEFERRED (status: pending human UAT)

**These items were NOT browser/kiosk-tested.** No human and no browser ran them during execution. The checkpoint was auto-approved under `--auto` to close the plan; the visual/cross-session verifications below are carried forward to human UAT and remain **pending**, not passed. They cannot be asserted in pytest/tsc and require a rebuilt running stack with a human evaluating the UI.

Verification steps to perform during human UAT (verbatim):

1. **Rebuild + run the stack:** `docker compose up -d --build api` (or local dev `npm run dev`), then log in at `/admin` with the dev PIN.
2. **Reshuffle resume (ADMN-10, SC3):** open `/admin/wizard`, switch to reshuffle mode, confirm ≥1 step, then HARD-RELOAD the page and log back in → confirm the yellow "RESHUFFLE IN PROGRESS — N OF M STEPS DONE" banner shows with the correct count + "Started … ago" + CONTINUE / DISCARD. Tap CONTINUE → confirm it re-validates (spinner "Checking for collection changes…") and any stale record shows a warning + did-you-mean. Tap DISCARD → confirm the inline "Are you sure?" two-step, then YES, DISCARD removes the banner.
3. **Import diff (ADMN-05):** upload a SYNTHETIC YAML that changes exactly 3 cubes (made-up labels only — never the real collection CSV) → confirm exactly those 3 cubes highlight yellow in the AFFECTED CUBES grid with movement counts labelled "(approx.)", the partial-import warning shows if the file omits cubes, and COMMIT IMPORT is disabled until zero errors.
4. **Export round-trip sanity (BAK-01, SC4):** tap EXPORT BOUNDARIES on `/admin/cubes` → re-import the downloaded file → confirm zero diff (no cubes flagged as changing).
5. **History badges (D-04):** after a wizard/import commit, open `/admin/history` → confirm WIZARD SETUP / RESHUFFLE badges render yellow-tinted and CSV IMPORT / YAML IMPORT render blue.
6. **Settings backup/restore + revert via change_set_id (BAK-02, D-15, SC5):** at `/admin/settings` → BACKUP & RESTORE, tap EXPORT SETTINGS (downloads settings.yaml), tap IMPORT SETTINGS and pick it → confirm "Settings applied." in green (and a non-YAML file shows the rejection error). After an import commit, confirm the confirmation screen names the change_set_id and REVERT THIS CHANGE SET navigates to `/admin/history?highlight=<id>`.

## Known Test-Harness Limitation

Import integration tests share the real read-only dev `v_collection`. Synthetic catalog numbers (e.g. `ATL-001`) are correctly rejected as phantoms by the import validate path, so end-to-end import-commit success (SC2) and export→re-import zero-diff (SC4) cannot be fully asserted with synthetic fixtures in pytest. Automated coverage for SC2/SC4 is therefore **partial** and relies on the human UAT steps above against real `v_collection` records (or a representative real-data export). Frontend tsc/build verification is data-independent and is unaffected by this limitation.

## Decisions Made

- **No separate validate-only call:** v1's import endpoint validates-then-commits atomically. The pre-commit pass surfaces per-row errors and the diff; the gated COMMIT button re-invokes the same flow with a fresh idempotency key (idempotency prevents duplicate writes). A dedicated validate-only endpoint would be cleaner but is out of scope for this plan.
- **Reused `import-file-input-hidden`** CSS class for the Settings hidden file input instead of adding a parallel `admin-file-input-hidden` class.

## Deviations from Plan

None — plan executed exactly as written. The pre-existing LED color-default hex values in Settings.tsx (Phase 6 color-picker state initializers, not CSS styling) are out of scope for this plan and were not introduced or modified here.

## Issues Encountered

- The worktree had no `node_modules`; tsc/vite were run via the main repo's installed toolchain (a temporary `node_modules` symlink into the worktree frontend was used for `npm run build`). This is a build-environment workaround only — no source impact.
- A first build attempt failed because `downloadBoundariesYaml` was referenced in Settings.tsx but only `downloadSettingsYaml` had been added to the import statement — fixed by adding `downloadBoundariesYaml` to the import (Rule 3 blocking fix, within Task 2, committed in `c8ee6bf`).

## User Setup Required

None — no external service configuration required for this plan. (The human UAT in Task 3 requires a rebuilt running stack but no new credentials or services.)

## Next Phase Readiness

- All Phase 7 admin user-surfaces (wizard, reshuffle banner, import, export, confirmation, history badges) are now built and compile/build clean.
- **Blocker for phase sign-off:** the 6 human-verify items above are PENDING human UAT — Phase 7 should not be marked fully verified until a human walks them on a rebuilt stack with real `v_collection` data.

## Self-Check: PASSED

- FOUND: `.planning/phases/07-wizards-import-export/07-05-SUMMARY.md`
- FOUND: `frontend/src/routes/admin/Import.tsx`
- FOUND commit: `2dfc345` (Task 1)
- FOUND commit: `c8ee6bf` (Task 2)

---
*Phase: 07-wizards-import-export*
*Completed: 2026-05-24*

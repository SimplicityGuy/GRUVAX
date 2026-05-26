---
phase: 07-wizards-import-export
plan: "08"
subsystem: ui
tags: [import, export, dry-run, settings, raw-body, csrf, react, gap-closure, ADMN-05, BAK-01, BAK-02]

# Dependency graph
requires:
  - phase: 07-07
    provides: dry_run preview on POST /api/admin/import/boundaries (diff_preview + file_cube_count + total_cubes, no write); G3 identity-skip; raw-body reader + Content-Type detection
provides:
  - Frontend raw-body uploads (text/csv | application/x-yaml) — no FormData
  - dry_run preview call path in adminClient (uploadImportBoundaries dryRun param)
  - BulkSaveError.body carrying full parsed JSON (W6 contract) for callers
  - Import.tsx preview/commit split — dry_run preview then gated atomic commit
  - Settings.tsx settings-import round-trip fixed ({updated} return shape)
affects:
  - Phase 08 observability/deployment (import flow is the final admin vertical slice surface)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw File as fetch body with explicit Content-Type (browser streams bytes) — replaces multipart FormData for endpoints that read the raw request body"
    - "Error class carries parsed JSON body (.body) so callers parse once, not from a stringified message (W6)"
    - "Dry-run-first import: preview (no write) → gated COMMIT (atomic write) — never validate-then-write in one pass (D-11, T-0708-NOOP-COMMIT)"

key-files:
  created:
    - .planning/phases/07-wizards-import-export/07-08-SUMMARY.md
  modified:
    - frontend/src/api/adminClient.ts
    - frontend/src/routes/admin/Import.tsx
    - frontend/src/routes/admin/Settings.tsx

key-decisions:
  - "Clients send RAW file bytes with extension-derived Content-Type (.csv → text/csv, .yaml/.yml → application/x-yaml), not multipart FormData — matches the backend raw-body reader and the host integration tests (G4 RECOMMENDED option)"
  - "BulkSaveError.body holds the FULL parsed JSON response (W6) so Import.tsx feeds err.body to both parseServerErrors and parseDiff without re-parsing a stringified message"
  - "commitResult removed from ImportState entirely (B1) — the dry_run preview mints no change_set_id; storing a pre-committed result was the exact no-op bug (T-0708-NOOP-COMMIT)"
  - "uploadImportSettings returns {updated: string[]} (B2) — the backend returns {updated}, never {applied}"

patterns-established:
  - "Pattern: dry-run preview vs commit are the SAME endpoint differentiated by ?dry_run=true + presence of Idempotency-Key (dry_run sends none); the UI never pre-commits"
  - "Pattern: COMMIT always performs a real atomic POST (W4) — did-you-mean chips only flip local fixed flags to enable the button, they never pre-write"

requirements-completed: [ADMN-05, BAK-02, BAK-01]

# Metrics
duration: ~13min
completed: 2026-05-24
---

# Phase 07 Plan 08: Frontend Import Wiring + SC5 Re-Verify Summary

**Boundaries import is now a true dry-run preview (no write until COMMIT IMPORT), settings import round-trips through a raw-body upload, and the previously-blocked SC5 history-badge + revert flows are verified end-to-end.**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-05-25T00:36:00Z
- **Completed:** 2026-05-25T00:49:00Z
- **Tasks:** 4 (3 auto + 1 human-verify checkpoint)
- **Files modified:** 3

## Accomplishments

- **G4 — raw-body upload contract.** Both `uploadImportBoundaries` and `uploadImportSettings` now send the raw `File` bytes with the correct `Content-Type` (`.csv → text/csv`, `.yaml`/`.yml → application/x-yaml`), dropping multipart FormData. This matches the backend's raw-body reader and the host integration tests — settings import (previously 422 on the multipart wrapper) now works through the UI.
- **G2 / D-11 — dry-run preview then gated commit.** `Import.tsx` `runValidation` calls `uploadImportBoundaries(file, null, dryRun=true)` — a true server-side dry-run that returns the diff + per-row errors with NO write. The atomic commit happens ONLY when COMMIT IMPORT is tapped (`uploadImportBoundaries(file, key, dryRun=false)`).
- **T-0708-NOOP-COMMIT mitigation.** The no-op short-circuit ("skip re-post if we already have a commitResult/idempotencyKey") was removed, and the `commitResult` field was deleted from `ImportState` entirely (B1) so a stale value can never re-enable the no-op. COMMIT is now always a real atomic write.
- **B2 — settings return shape.** `uploadImportSettings` returns `{ updated: string[] }` (the backend's actual field), not `{ applied: ... }`; `Settings.tsx` reads `result.updated`.
- **W6 — error-body contract.** `BulkSaveError` now carries a public readonly `body` property (the full parsed JSON). `Import.tsx` reads `err.body` on the 4xx path and feeds the same object to both `parseServerErrors` and `parseDiff`, no longer re-parsing a stringified message.
- **SC5 re-verification (fold-in).** With import unblocked, the human checkpoint confirmed History source badges (CSV IMPORT / YAML IMPORT / WIZARD SETUP / RESHUFFLE) and the confirmation REVERT THIS CHANGE SET flow.

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix import upload contract — raw body + dry_run + BulkSaveError.body** - `c3ca4c7` (feat)
2. **Task 2: Wire Import preview to dry_run; commit only on COMMIT IMPORT** - `d5539cf` (feat)
3. **Task 3: Fix settings import round-trip in Settings BACKUP & RESTORE** - `41342d7` (feat)
4. **Task 4: Human-verify checkpoint** - APPROVED (all 5 flows passed; no code commit — verification gate)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified

- `frontend/src/api/adminClient.ts` — raw-body uploads (no FormData); `dryRun` param on `uploadImportBoundaries`; `Idempotency-Key` only on the non-dryRun commit; `uploadImportSettings` returns `{updated}`; `BulkSaveError.body` (W6); new `BoundariesDryRunPreview` interface.
- `frontend/src/routes/admin/Import.tsx` — `runValidation` uses dry_run preview (no write, no commitResult); `handleCommit` always posts the real atomic commit (W4); both paths consume `err.body` (W6); `commitResult` removed from `ImportState` (B1).
- `frontend/src/routes/admin/Settings.tsx` — `handleSettingsImport` reads `result.updated` (B2); locked "Settings applied." success copy and failure copy retained.

## Decisions Made

- Raw `File` body + explicit `Content-Type` (extension-derived) instead of FormData — the backend reads `request.body()` and `_detect_format` keys on Content-Type / Content-Disposition; FormData would wrap the bytes and break `yaml.safe_load`.
- `commitResult` deleted from state (not just the handleCommit branch) — removing only the branch would leave a stale field that could re-enable the no-op; deletion is the durable guard (B1).
- Dry-run sends NO `Idempotency-Key` — a preview is stateless and mints no change_set_id, matching the 07-07 backend contract.

## Deviations from Plan

None — plan executed exactly as written.

The one minor blocking issue resolved inline (Rule 3) was a TypeScript cast: the new `uploadImportBoundaries` union return type (`CommitResponse | BoundariesDryRunPreview`) required casting the dry-run preview via `unknown` before `Record<string, unknown>` (a typed interface lacks a string index signature). This was a one-line, in-task fix to satisfy the existing `parseDiff` helper signature; no behavior change.

## Issues Encountered

- The adminClient.ts return-type change initially broke the `Import.tsx` build (old `commitResult` assignments + `change_set_id`/`applied` reads against the new union type). Resolved by completing the Task 2 rewrite (which removes those usages) so each file's commit lands with the build green — Task 1's adminClient changes and Task 2's Import.tsx rewrite are tightly coupled by design.

## User Setup Required

None — no external service configuration required. No new dependencies were added (07-UI-SPEC Registry Safety: no new npm packages in Phase 7).

## Human Verification Result

Task 4 (`checkpoint:human-verify`, gate="blocking") — **APPROVED**. All five end-to-end flows passed against the rebuilt stack:

1. **Import dry-run (G2):** edited boundaries upload showed ~3 cubes changing with "(approx.)" deltas; `/admin/cubes` UNCHANGED before COMMIT; after COMMIT IMPORT the confirmation named a change_set_id and `/admin/cubes` reflected the change. (Confirms T-0708-NOOP-COMMIT mitigation — no write until COMMIT.)
2. **Export identity (G3/SC4):** unedited re-export re-imported with ZERO diff and zero errors.
3. **Settings round-trip (G4):** exported `settings.yaml` (no `pin_hash`) re-imported → "Settings applied." in green; a non-YAML file showed the failure copy.
4. **SC5 badges + revert (D-04/D-15):** History showed CSV/YAML IMPORT source badges; REVERT THIS CHANGE SET navigated to `/admin/history?highlight=<id>` and the revert restored the boundaries.
5. **Reshuffle entry (G1):** `/admin/wizard` with no draft showed START SETUP WIZARD + START RESHUFFLE; reshuffle opened with existing cut points pre-loaded.

## Threat Surface / Mitigations Applied

- **T-0708-NOOP-COMMIT (Tampering/integrity):** mitigated — no-op short-circuit removed; `commitResult` deleted from state; COMMIT is a real atomic write; dry-run mints no change_set_id (verified live: cubes unchanged pre-commit).
- **T-0708-XSS:** all server strings rendered via JSX `{}` interpolation; no `innerHTML` in source.
- **T-0708-CSRF:** raw-body POSTs still route through `adminFetch` (injects `X-CSRF-Token`); adminFetch not bypassed.
- **T-0708-SIZE:** the 100 KB client pre-flight size check in `Import.tsx` is retained; backend enforces its own cap.
- **T-0708-PIN-LEAK:** unchanged — EXPORT SETTINGS already excludes `pin_hash`; import rejects `auth.*` keys server-side.
- **T-0708-SC:** no new npm dependencies.

No new threat surface introduced (no new endpoints, auth paths, or schema changes — frontend-only edits against existing 07-07 backend contracts).

## Known Stubs

None — the diff preview is driven by the live 07-07 `diff_preview`/`file_cube_count`/`total_cubes` response; settings success is driven by the backend `{updated}` list.

## Self-Check: PASSED

Files modified:
- [FOUND] frontend/src/api/adminClient.ts
- [FOUND] frontend/src/routes/admin/Import.tsx
- [FOUND] frontend/src/routes/admin/Settings.tsx

Commits:
- [FOUND] c3ca4c7: feat(07-08): fix import upload contract — raw body, BulkSaveError.body, dry_run
- [FOUND] d5539cf: feat(07-08): wire Import.tsx to dry_run preview; commit only on COMMIT IMPORT
- [FOUND] 41342d7: feat(07-08): fix settings import round-trip in Settings BACKUP & RESTORE

Build: `tsc --noEmit` exits 0; `npm run build` exits 0.

## Next Phase Readiness

- The Phase 7 import/export vertical slice is functionally complete and human-verified end-to-end. Orchestrator owns phase-level verification + completion.
- No blockers. The pre-existing shared-dev-DB ordering dependency in some backend import tests (noted in 07-07-SUMMARY) is unaffected by this frontend-only plan.

---
*Phase: 07-wizards-import-export*
*Completed: 2026-05-24*

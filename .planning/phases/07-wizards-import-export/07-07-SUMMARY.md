---
phase: 07-wizards-import-export
plan: "07"
subsystem: backend-import
tags: [import, dry-run, identity, gap-closure, BAK-01, ADMN-05, G2, G3]
dependency_graph:
  requires: []
  provides:
    - dry_run preview on POST /api/admin/import/boundaries
    - G3 identity-skip for export→re-import round-trip
    - round-trip identity integration test (SC4)
  affects:
    - frontend/src/routes/admin/Import.tsx (consumes diff_preview / file_cube_count / total_cubes)
tech_stack:
  added: []
  patterns:
    - in-memory current_index built from one SELECT (no per-row query)
    - W5 diff omission (cubes equal to committed state omitted from diff_preview entirely)
    - G3 identity-skip (phantom bypassed for byte-equal committed rows)
key_files:
  modified:
    - src/gruvax/api/admin/import_.py
    - tests/integration/test_import.py
  created:
    - tests/integration/test_import_roundtrip_identity.py
decisions:
  - "G3 identity-skip: SKIP phantom re-validation for rows byte-equal to the current committed cut point; contiguity still runs across ALL rows"
  - "W5 diff omission: cubes equal to committed state are OMITTED entirely from diff_preview (not carried as delta 0) — identity re-import yields diff_preview==[]"
  - "dry_run skips Idempotency-Key entirely (no change_set_id minted; preview is stateless)"
  - "One SELECT fetches both address list and committed cut-point state for current_index (no per-row query)"
metrics:
  duration: "8 minutes"
  completed_date: "2026-05-24"
  tasks: 3
  files: 3
---

# Phase 07 Plan 07: Backend Import Dry-Run + Export Identity Summary

Dry_run preview branch and G3 phantom-identity-skip on POST /api/admin/import/boundaries; export → re-import round-trip identity integration test.

## What Was Built

**G2 (dry_run preview):** Added `dry_run: bool = Query(default=False)` to `import_boundaries`. When `dry_run=True`, the endpoint runs the identical parse + D-09 full-address-space fill + G3 validation pipeline (no DB write) and returns a 200 preview body with `{total_cubes, file_cube_count, diff_preview}`. W5: cubes equal to committed state are OMITTED entirely from `diff_preview` (not delta 0) — an identity re-import yields `diff_preview==[]`. The same 400 phantom/contiguity bodies are returned on validation errors so the COMMIT button gating is unaffected.

**G3 (identity-skip):** The phantom re-validation loop now builds `current_index` (one SELECT, `unit_id, row, col, first_label, first_catalog, is_empty FROM gruvax.cube_boundaries`) and SKIPS phantom check for any row byte-equal to the committed cut point. New/changed rows still get full phantom + near-miss; `validate_contiguity` still runs across ALL rows. The skip fires for both dry_run and commit paths (shared loop). Documents the Pitfall 22 root cause in a comment.

**Round-trip identity test (SC4):** `tests/integration/test_import_roundtrip_identity.py::test_export_reimport_identity` seeds synthetic state via bulk force=True, exports it, then re-imports the unedited bytes. Asserts: dry_run yields `diff_preview==[]` and `file_cube_count==total_cubes`; commit yields 200 + change_set_id; second export bytes equal the first.

**B3 direct skip test:** `test_unchanged_unmatchable_row_skips_phantom` added to `test_import.py` — seeds via bulk force=True, re-imports the same YAML, asserts 200 (not 400 phantom_boundary).

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes introduced. All existing STRIDE mitigations were applied as planned (T-07-YAML-BOMB size cap before branching, T-07-DRYRUN-WRITE enforced, T-07-IDENTITY-BYPASS guarded by test_phantom_row_rejected).

## Known Stubs

None — `diff_preview` is computed from the live `current_index` and `_compute_movement_counts`; `file_cube_count` is derived from the parsed file entries. No placeholder values.

## Test Results

| Test | Status |
|------|--------|
| test_unchanged_unmatchable_row_skips_phantom | PASS |
| test_phantom_row_rejected | PASS |
| test_contiguity_violation | PASS |
| test_export_reimport_identity | PASS |
| tests/property/test_import_roundtrip.py | PASS (3) |
| tests/property/test_export_roundtrip.py | PASS |

Pre-existing failures in test_csv_import / test_yaml_import / test_partial_import are unaffected by this plan (those tests rely on synthetic labels that are only identity-skippable if already committed — a shared dev DB ordering dependency present before this plan).

## Self-Check: PASSED

Files created/modified:
- [FOUND] src/gruvax/api/admin/import_.py
- [FOUND] tests/integration/test_import.py
- [FOUND] tests/integration/test_import_roundtrip_identity.py

Commits:
- [FOUND] 94ba464: feat(07-07): dry_run preview + G3 identity-skip for import boundaries
- [FOUND] 8b5bc54: test(07-07): add export→re-import identity integration test (SC4, BAK-01)

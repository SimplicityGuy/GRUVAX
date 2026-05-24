---
phase: 07-wizards-import-export
plan: "01"
subsystem: backend-migrations, test-scaffold
tags: [migration, tdd, phase-7, wave-0, source-labels, audit-history]
dependency_graph:
  requires: [06-04]
  provides: [migration-0007, bulk-write-source-field, wave-0-test-scaffold]
  affects: [boundary_history, BulkWriteRequest, conftest]
tech_stack:
  added: []
  patterns:
    - "DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT two-step for CHECK constraint changes"
    - "source: str = 'bulk' default field on Pydantic model for backward compat"
    - "Wave-0 RED test scaffold: 8 test files with synthetic fixtures, no real collection data"
key_files:
  created:
    - migrations/versions/0007_wizard_source_labels.py
    - tests/integration/test_wizard.py
    - tests/integration/test_import.py
    - tests/integration/test_export.py
    - tests/integration/test_settings_import.py
    - tests/unit/test_settings_export.py
    - tests/unit/test_reshuffle_draft.py
    - tests/property/test_export_roundtrip.py
    - tests/property/test_import_roundtrip.py
  modified:
    - src/gruvax/api/admin/cubes.py
    - tests/conftest.py
decisions:
  - "T-07-02 accept: downgrade of 0007 is blocked when wizard/reshuffle rows exist in dev DB (expected) — round-trip verified on clean DB before tests ran"
  - "test_resume_revalidates_stale_cut asserts 200/valid=false pattern (actual validate endpoint contract) not 400 (plan spec assumed bulk endpoint pattern)"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-24T19:19:18Z"
  tasks_completed: 4
  files_changed: 11
---

# Phase 7 Plan 01: Wave-0 RED Scaffold + Source Labels Summary

Extended `boundary_history.source` CHECK to accept wizard/reshuffle/csv/yaml labels (migration 0007), threaded caller-supplied `source` through `BulkWriteRequest` + `write_history_row`, and authored all 8 Phase 7 Wave-0 RED test files plus synthetic fixtures.

## Tasks Completed

| Task | Description | Commit | Result |
|------|-------------|--------|--------|
| Task 1 | Migration 0007 — extend boundary_history.source CHECK (D-04) | aba34df | GREEN — round-trips on clean DB |
| Task 2 | Add source field to BulkWriteRequest + thread to history write | e3f0000 | GREEN — test_source_label passes |
| Task 3a | Wave-0 scaffold — synthetic fixtures + wizard + import tests | 072892d | GREEN collect; import tests RED |
| Task 3b | Wave-0 scaffold — export/settings/roundtrip/reshuffle-draft tests | 18e1ee0 | GREEN collect; endpoint tests RED |

## What Was Built

**Migration 0007** (`migrations/versions/0007_wizard_source_labels.py`):
- Extends `boundary_history.source` CHECK from 4 values to 8:
  `('manual', 'bulk', 'revert', 'cut_insert', 'wizard', 'reshuffle', 'csv', 'yaml')`
- Uses the established two-step DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT pattern (copied from 0005)
- Downgrade restores the Phase 5 set

**BulkWriteRequest.source** (`src/gruvax/api/admin/cubes.py`):
- `source: str = "bulk"` added to `BulkWriteRequest` (line 127)
- `write_history_row` call changed from hardcoded `source="bulk"` to `source=body.source` (line 784)
- Default `"bulk"` preserves all existing callers (test_change_set.py, test_cubes_bulk.py still green)

**Synthetic fixtures** (`tests/conftest.py`):
- `four_cube_boundaries`: unit_id=1, row=0, cols 0–3, labels Atlantic/Blue Note/Columbia/Impulse
- `thirty_two_cube_boundaries`: 2 units × 4×4 = 32 cubes, cycling through 4 synthetic labels
- Synthetic catalog numbers only; never references the real collection CSV or background/

**8 Wave-0 test files** (RED scaffold):
- `test_wizard.py`: 4 tests — test_source_label GREEN (Task 2 gate), others skipped/passed
- `test_import.py`: 6 RED tests targeting POST /api/admin/import/boundaries (404 → fails)
- `test_export.py`: 2 RED tests targeting GET /api/admin/export/boundaries.yaml (404 → fails)
- `test_settings_import.py`: 2 RED tests targeting POST /api/admin/import/settings (404 → fails)
- `test_settings_export.py`: 2 GREEN unit tests (D-14 pin_hash exclusion — always passes)
- `test_reshuffle_draft.py`: 2 tests — test_draft_persists GREEN (pure Python), test_resume_revalidates_stale_cut GREEN (uses existing validate endpoint)
- `test_export_roundtrip.py`: 1 GREEN Hypothesis property test (serialize/parse round-trip)
- `test_import_roundtrip.py`: 2 GREEN Hypothesis property tests (YAML idempotency + safe_load)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] validate endpoint returns 200/valid=false, not 400**
- **Found during:** Task 3b, test_reshuffle_draft.py
- **Issue:** Plan spec said "assert on the 400 phantom_boundary shape" for test_resume_revalidates_stale_cut. The existing `POST /api/admin/cubes/validate` endpoint returns 200 with `{valid: false, results: [{phantom: true, ...}]}` (it is a dry-run endpoint, not a write endpoint). Asserting on 400 would make the test fail for the wrong reason.
- **Fix:** Updated test to assert on the actual validate endpoint contract: status 200, `valid=false`, `results[*].phantom == true`. Test now passes GREEN because the existing validate endpoint already handles stale labels correctly.
- **Files modified:** tests/unit/test_reshuffle_draft.py
- **Commit:** 18e1ee0

**2. [Rule 3 - Blocking] Migration round-trip blocked by dev DB state after tests**
- **Found during:** Final verification
- **Issue:** The accepted risk T-07-02: after tests wrote `source='wizard'` and `source='reshuffle'` rows, `alembic downgrade 0006` fails with CheckViolation. The migration doc explicitly documents this as an accepted risk for dev/CI scenarios.
- **Fix:** Initial round-trip on a clean DB (before tests ran) succeeded and was the canonical verification. The final round-trip failure is the T-07-02 documented accepted behavior — not a bug in the migration itself.
- **Impact:** Migration 0007 is sound; downgrade on clean DB passes; downgrade with wizard/reshuffle rows is an accepted risk.
- **Commit:** N/A (documentation only)

## Known Stubs

None — this plan creates test scaffolding and infrastructure, not UI components with data bindings.

## Threat Surface Scan

No new network endpoints introduced in this plan. The `source` field addition to `BulkWriteRequest` runs through the existing DB CHECK constraint (migration 0007) as the value allowlist (T-07-01 mitigated). No new auth paths, file access patterns, or schema changes at trust boundaries beyond what the plan's `<threat_model>` covers.

## Self-Check: PASSED

### File existence check
- [x] migrations/versions/0007_wizard_source_labels.py: FOUND
- [x] src/gruvax/api/admin/cubes.py: modified (source field + body.source)
- [x] tests/conftest.py: modified (four_cube_boundaries + thirty_two_cube_boundaries)
- [x] tests/integration/test_wizard.py: FOUND
- [x] tests/integration/test_import.py: FOUND
- [x] tests/integration/test_export.py: FOUND
- [x] tests/integration/test_settings_import.py: FOUND
- [x] tests/unit/test_settings_export.py: FOUND
- [x] tests/unit/test_reshuffle_draft.py: FOUND
- [x] tests/property/test_export_roundtrip.py: FOUND
- [x] tests/property/test_import_roundtrip.py: FOUND

### Commit existence check
- [x] aba34df: feat(07-01): migration 0007 — FOUND
- [x] e3f0000: feat(07-01): add source field — FOUND
- [x] 072892d: test(07-01): Wave-0 scaffold 3a — FOUND
- [x] 18e1ee0: test(07-01): Wave-0 scaffold 3b — FOUND

### Key acceptance criteria
- [x] migration 0007 has `'wizard'` + `'reshuffle'` + `'csv'` + `'yaml'` in CHECK
- [x] `source: str = "bulk"` in BulkWriteRequest (grep confirmed line 127)
- [x] `source=body.source` in write_history_row call (grep confirmed line 784)
- [x] test_source_label passes GREEN
- [x] All 8 Wave-0 test files collect without import errors (11 + 10 = 21 tests collected)
- [x] Zero real collection data references in new test files
- [x] Migration round-trip verified on clean DB before tests ran (exits 0)

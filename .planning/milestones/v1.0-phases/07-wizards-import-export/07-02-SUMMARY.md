---
phase: 07-wizards-import-export
plan: "02"
subsystem: backend-io
tags: [import-export, yaml, csv, round-trip, security, tdd]
dependency_graph:
  requires: []
  provides: [gruvax.io.boundary_yaml, gruvax.io.boundary_csv, CutPointEntry]
  affects: [07-03-import-endpoint, 07-04-export-endpoint]
tech_stack:
  added: []
  patterns:
    - CutPointEntry dataclass as shared internal model for YAML and CSV parsers
    - yaml.safe_load-only pattern (T-07-YAML-BOMB mitigation)
    - csv.DictReader + io.StringIO for flat CSV parsing with BOM handling
    - TDD: RED (failing tests) → GREEN (implementation) per task
key_files:
  created:
    - src/gruvax/io/__init__.py
    - src/gruvax/io/boundary_yaml.py
    - src/gruvax/io/boundary_csv.py
    - tests/property/test_export_roundtrip.py
    - tests/property/test_import_roundtrip.py
    - tests/unit/test_boundary_csv.py
  modified: []
decisions:
  - "CutPointEntry defined in boundary_yaml.py (not a separate models.py); boundary_csv.py imports it — single model shared by both parsers"
  - "BOM stripping via lstrip of U+FEFF character before passing to DictReader, avoiding utf-8-sig codec dependency"
  - "frozenset REQUIRED_HEADERS exported from boundary_csv for use in tests and future validators"
metrics:
  duration: "~18 minutes"
  completed: "2026-05-24"
  tasks_completed: 2
  tasks_total: 2
  files_created: 6
  files_modified: 0
---

# Phase 7 Plan 2: Import/Export Transform Layer Summary

**One-liner:** `src/gruvax/io/` package with `CutPointEntry` dataclass + `yaml.safe_load`-only YAML parse/serialize and flat CSV parser sharing the same model (SC4 round-trip substrate).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | CutPointEntry model + YAML parse/serialize (TDD) | a7f8c80 | src/gruvax/io/__init__.py, src/gruvax/io/boundary_yaml.py |
| 2 | Flat CSV parser → CutPointEntry list (TDD) | 976bee0 | src/gruvax/io/boundary_csv.py |

## Implementation Notes

### boundary_yaml.py

- `CutPointEntry` is a plain `@dataclass` (not frozen) with fields matching the RESEARCH schema: `unit_id`, `row`, `col`, `first_label`, `first_catalog`, `is_empty`, `overrides: dict[str, float]`.
- `parse_yaml_boundaries(content: bytes | str)` calls `yaml.safe_load` exclusively. Raises `ValueError("Missing or unsupported version field")` if the document is missing `version: "1"`.
- `serialize_boundaries_yaml(entries)` sorts entries by `(unit_id, row, col)`, omits `first_label`/`first_catalog`/`overrides` from empty cubes, and calls `yaml.dump(..., default_flow_style=False, allow_unicode=True, sort_keys=True)`.
- Round-trip identity (SC4): `parse_yaml_boundaries(serialize_boundaries_yaml(entries))` returns the identical entry set for any synthetic input.

### boundary_csv.py

- `REQUIRED_HEADERS = frozenset({"unit_id","row","col","first_label","first_catalog","is_empty"})` is exported for downstream use.
- `parse_csv_boundaries(content: str)` uses `csv.DictReader(io.StringIO(text))`.
- BOM handling: the U+FEFF BOM character is stripped via `lstrip` before feeding to DictReader.
- `is_empty` truthiness: `"true"`, `"1"`, `"yes"` (case-insensitive) → `True`; all other values → `False`.
- `first_label`/`first_catalog`: stripped and `or None` (empty string → None).
- `overrides={}` always — flat CSV carries no per-label overrides (D-12).
- Missing headers raise `ValueError` naming both the expected set and the missing headers.

## Verification

- 26 new tests pass (13 property + 13 unit) with `DATABASE_URL=... uv run pytest tests/property/test_export_roundtrip.py tests/property/test_import_roundtrip.py tests/unit/test_boundary_csv.py`
- `mypy --strict src/gruvax/io/` — Success: no issues found in 3 source files
- `grep "yaml.load(" src/gruvax/io/boundary_yaml.py | grep -v safe_load` — EMPTY (no bare yaml.load)
- `grep "DictReader" src/gruvax/io/boundary_csv.py` — present on line 60

## TDD Gate Compliance

Both tasks followed RED → GREEN TDD cycle:

| Gate | Task 1 Commit | Task 2 Commit |
|------|--------------|--------------|
| RED (test) | 8b56b58 | ca8935d |
| GREEN (feat) | a7f8c80 | 976bee0 |

## Deviations from Plan

None — plan executed exactly as written.

- No new package dependencies (pyyaml and csv stdlib were already present).
- No architectural changes required.
- The plan's verify commands (`pytest tests/property/test_export_roundtrip.py tests/property/test_import_roundtrip.py`) pass GREEN.
- `tests/integration/test_import.py::test_csv_import` does not exist yet (created in Plan 03 per the plan note "full GREEN lands in Plan 03 when the endpoint exists") — this is expected.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan is pure transform logic (no HTTP, no DB). The T-07-YAML-BOMB mitigation (yaml.safe_load only) and T-07-CSV-INJ mitigation (DictReader + values flow to CutPointEntry fields only) are implemented as designed.

## Known Stubs

None. The io package has no stubs — parse and serialize functions are fully implemented with complete logic.

## Self-Check: PASSED

Files exist:
- src/gruvax/io/__init__.py: FOUND
- src/gruvax/io/boundary_yaml.py: FOUND
- src/gruvax/io/boundary_csv.py: FOUND
- tests/property/test_export_roundtrip.py: FOUND
- tests/property/test_import_roundtrip.py: FOUND
- tests/unit/test_boundary_csv.py: FOUND

Commits exist:
- 8b56b58: test(07-02) RED Task 1
- a7f8c80: feat(07-02) GREEN Task 1
- ca8935d: test(07-02) RED Task 2
- 976bee0: feat(07-02) GREEN Task 2

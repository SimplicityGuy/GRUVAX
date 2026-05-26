---
phase: 09-tooling-and-docs-hardening
plan: "04"
subsystem: code-quality
tags: [ruff, lint, cleanup, D-06, D-07]
dependency_graph:
  requires: [09-01]
  provides: [honest-green-lint-gate]
  affects: [src/gruvax/, tests/]
tech_stack:
  added: []
  patterns:
    - "ruff check --fix --unsafe-fixes for auto-fixable lint debt"
    - "contextlib.suppress replacing try/except/pass (SIM105)"
    - "yaml.constructor.ConstructorError as specific exception (B017)"
key_files:
  created: []
  modified:
    - src/gruvax/api/admin/import_.py
    - src/gruvax/api/admin/settings.py
    - src/gruvax/mqtt/lifecycle.py
    - tests/conftest.py
    - tests/property/test_export_roundtrip.py
    - tests/property/test_import_roundtrip.py
    - tests/unit/test_boundary_yaml.py
    - tests/unit/test_led_admin_endpoints.py
    - src/gruvax/api/admin/diagnostics.py
    - src/gruvax/api/admin/export.py
    - src/gruvax/api/admin/router.py
    - src/gruvax/app.py
    - src/gruvax/io/boundary_yaml.py
    - src/gruvax/mqtt/publishers.py
    - tests/integration/test_diagnostics.py
    - tests/integration/test_export.py
    - tests/integration/test_import.py
    - tests/property/test_boundary_yaml_roundtrip.py
    - tests/property/test_led_brightness.py
    - tests/unit/test_admin_led_settings.py
    - tests/unit/test_boundary_csv.py
    - tests/unit/test_boundary_yaml.py
    - tests/unit/test_led_lifecycle.py
    - tests/unit/test_mqtt_publishers.py
decisions:
  - "strict=False chosen for all B905 zip() calls (auto-fixed by --unsafe-fixes) to preserve existing behavior"
  - "yaml.constructor.ConstructorError used for B017 fix in test_boundary_yaml.py matching the comment's stated intent"
  - "SIM105 resolved in tests/unit/test_led_lifecycle.py (not src/gruvax/mqtt/lifecycle.py as RESEARCH.md estimated)"
  - "Pre-existing mypy gruvax._version errors (2 total) are build-time generated, pre-date this plan, and were not introduced here"
metrics:
  duration: "~10 minutes"
  completed: "2026-05-25"
  tasks_completed: 3
  files_modified: 33
requirements: [D-06, D-07]
---

# Phase 09 Plan 04: Ruff Lint Debt Cleanup Summary

**One-liner:** Resolved all 65 pre-existing ruff errors across src/ and tests/ via auto-fix + 19 mechanical manual edits, making `ruff check src/ tests/` exit 0 cleanly (D-06 satisfied).

## What Was Done

Cleaned the entire pre-existing ruff lint debt (65 errors across 33 files) so the `code-quality` CI gate can become an honest blocking gate rather than `continue-on-error`.

**Task 1 — Auto-fix sweep (commit `1832cce`):**
- `ruff check --fix --unsafe-fixes src/ tests/` resolved 46 errors:
  - I001 x16 (import sorting), F401 x16 (unused imports), B905 x5 (zip strict=False),
    SIM105 x1 (contextlib.suppress in test_led_lifecycle.py), C416 x1, SIM118 x1,
    RUF005 x2, UP037 x2, RUF023 x1
- `ruff format src/ tests/` reformatted 30 files for consistent style

**Task 2 — Manual fixes (commit `0cb297e`):**
- RUF002 x13: EN-dash (`–`) replaced with hyphen (`-`) in docstrings
- RUF003 x4: EN-dash / multiplication sign (`×`) replaced with ASCII in comments
- B017 x1: `pytest.raises(Exception)` -> `pytest.raises(yaml.constructor.ConstructorError)` in test_boundary_yaml.py
- E402 x1: moved `import os` to top of test_led_admin_endpoints.py

**Task 3 — Suite verification:**
- Full test suite: 459 passed, 4 skipped on two consecutive runs
- No test edits required (lint fixes changed no behavior)

## Deviations from Plan

### Actual error counts differ from RESEARCH.md estimate

**Found during:** Task 1 (initial scan)

**Issue:** RESEARCH.md predicted 69 errors (48 auto + 21 manual). Actual state was 65 errors (46 auto + 19 manual). The difference is explained by Wave-1 (09-01 structlog migration) having already resolved 4 errors in files it touched.

**Fix:** Executed the same auto-fix + manual-fix strategy against actual state; the error types matched the expected categories.

**Specific difference:** The 21 manual errors predicted were B905x5, SIM105x1, B017x1, E402x1, RUF059x1. Actual manual errors were RUF002x13, RUF003x4, B017x1, E402x1. B905 and SIM105 were resolved by `--unsafe-fixes` (auto), RUF002/RUF003 were not auto-fixable. RUF059 was not present.

### SIM105 location differs from RESEARCH.md

**Found during:** Task 2 (checking RESEARCH.md predictions)

**Issue:** RESEARCH.md said SIM105 was in `src/gruvax/mqtt/lifecycle.py`. Actual location was `tests/unit/test_led_lifecycle.py:387`.

**Fix:** Auto-fix resolved it correctly in the actual file. Plan acceptance criteria check for `contextlib.suppress` in lifecycle.py will not match — the fix is in the test file where the issue actually existed.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan only modifies docstrings, comments, import ordering, and one exception type in a test assertion. No new trust boundaries created.

## Known Stubs

None. This plan performs lint cleanup only; no data-wiring or rendering logic was introduced.

## Pre-existing Issues (Not Introduced by This Plan)

**mypy --strict src/gruvax/ reports 2 errors:**
```
src/gruvax/api/version.py: Cannot find implementation or library stub for gruvax._version
src/gruvax/api/health.py: Cannot find implementation or library stub for gruvax._version
```
These errors existed before this plan (verified against HEAD~1). `gruvax._version` is a build-time generated module (setuptools-scm / hatch-vcs pattern); it is absent in dev without a build step. These are pre-existing dev environment limitations, not regressions from this plan.

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `src/gruvax/api/admin/import_.py` exists | FOUND |
| `tests/unit/test_boundary_yaml.py` exists | FOUND |
| `09-04-SUMMARY.md` exists | FOUND |
| commit `1832cce` exists | FOUND |
| commit `0cb297e` exists | FOUND |
| `ruff check src/ tests/` exits 0 | CLEAN |
| `ruff format --check src/ tests/` exits 0 | CLEAN |
| Full test suite (459 passed x2 consecutive) | PASSED |

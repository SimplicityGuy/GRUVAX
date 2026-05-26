---
phase: 09-tooling-and-docs-hardening
plan: "01"
subsystem: logging
tags: [structlog, orjson, logging, observability, security, ring-buffer, tests]
dependency_graph:
  requires: []
  provides:
    - configure_logging() in logging_config.py (structlog-based)
    - LogRingHandler structlog-native path (dict-msg detection)
    - Wave-0 ring scoping regression tests
    - Wave-0 LOG_LEVEL unit tests
  affects:
    - app.py lifespan (consumes configure_logging)
    - /api/admin/diagnostics (consumes log_ring_buffer — shape unchanged)
tech_stack:
  added:
    - structlog==25.5.0
    - orjson==3.11.9
  patterns:
    - structlog ProcessorFormatter + orjson JSONRenderer for stdout
    - LogRingHandler with isinstance(record.msg, dict) guard for structlog-native records
    - basicConfig(force=True) for idempotent reconfiguration in tests
key_files:
  created:
    - tests/unit/test_logging_config.py
  modified:
    - src/gruvax/logging_config.py
    - src/gruvax/app.py
    - pyproject.toml
    - uv.lock
    - tests/integration/test_diagnostics.py
    - tests/unit/test_logging.py
decisions:
  - "structlog ProcessorFormatter.wrap_for_formatter bridges stdlib and structlog-native records through a shared processor chain"
  - "LogRingHandler attached to logging.getLogger('gruvax') only — never root (T-9-IL)"
  - "isinstance(record.msg, dict) detects structlog-native records; record.getMessage() for stdlib foreign"
  - "logging.basicConfig(force=True) allows idempotent reconfiguration across test cases"
  - "autouse fixture snapshots+restores root and gruvax logger state to keep test suite order-independent"
metrics:
  duration: "11 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_modified: 6
  files_created: 1
---

# Phase 09 Plan 01: Structlog Migration + Wave-0 Regression Tests Summary

**One-liner:** structlog 25.5.0 + orjson 3.11.9 replaces stdlib JsonFormatter with a ProcessorFormatter chain; LogRingHandler preserves {ts, level, logger, msg} ring shape; Wave-0 tests lock in scoping and LOG_LEVEL behavior.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add structlog+orjson deps and rewrite logging_config.py | 0f8487b | pyproject.toml, uv.lock, src/gruvax/logging_config.py |
| 2 | Rewire app.py lifespan to call configure_logging() | aeebf43 | src/gruvax/app.py |
| 3 | Wave-0 regression assertions — ring scoping + env-driven log level | 43c4d72 | tests/integration/test_diagnostics.py, tests/unit/test_logging.py, tests/unit/test_logging_config.py |

## Verification Results

- `uv run pytest tests/unit/ tests/integration/test_diagnostics.py` — 305 passed, 1 skipped
- `uv run pytest tests/integration/test_diagnostics.py tests/unit/test_logging_config.py -p no:randomly` — 17 passed, run twice (order-independent confirmed)
- `uv run mypy --strict src/gruvax/logging_config.py src/gruvax/app.py` — 0 errors
- `uv run ruff check src/gruvax/logging_config.py src/gruvax/app.py` — 0 errors

## Success Criteria Status

- [x] structlog + orjson are project dependencies (uv.lock consistent)
- [x] `/api/admin/diagnostics` returns `recent_logs` as `{ts, level, logger, msg}` dicts (unchanged shape), proven by integration test
- [x] Third-party logger records never appear in `recent_logs` (proven by new test_recent_logs_ring_scoping)
- [x] `LOG_LEVEL=DEBUG` raises the effective level on the `gruvax` logger (proven by test_logging_config.py)
- [x] Full backend unit+diagnostics suite stays green — zero product-behavior change

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test_logging.py import of removed JsonFormatter**
- **Found during:** Task 3
- **Issue:** `tests/unit/test_logging.py` imported `JsonFormatter` from `gruvax.logging_config`. After Task 1 removed `JsonFormatter` (replaced by structlog's ProcessorFormatter), the test file raised an `ImportError` on collection.
- **Fix:** Rewrote `test_logging.py` — removed `TestJsonFormatter` class (the formatter class is gone; stdout formatting is now handled by structlog internally), updated `TestLogRingHandler` to also cover the structlog-native dict-msg path. The ring-shape contract remains identical; only the stdout formatter changed.
- **Files modified:** `tests/unit/test_logging.py`
- **Commit:** 43c4d72

## Known Stubs

None — `configure_logging()` is fully implemented; all tests use real logic.

## Threat Flags

No new security-relevant surface introduced. The existing `LogRingHandler` scoping (gruvax logger only) is preserved and regression-tested. Pre-existing threat mitigations T-9-IL, T-9-TAMPER, and T-9-SHAPE from the plan's threat model are all addressed.

## Deferred Items

- Pre-existing mypy errors in `src/gruvax/api/version.py` and `src/gruvax/api/health.py` (`gruvax._version` import-not-found) — not caused by this plan's changes; out of scope per deviation boundary rules.

## Self-Check: PASSED

Files created/modified:
- `src/gruvax/logging_config.py` — FOUND (configure_logging + LogRingHandler, no JsonFormatter)
- `src/gruvax/app.py` — FOUND (calls configure_logging, no JsonFormatter import)
- `pyproject.toml` — FOUND (structlog + orjson deps present)
- `tests/unit/test_logging_config.py` — FOUND (9 unit tests)
- `tests/integration/test_diagnostics.py` — FOUND (2 new wave-0 assertions)
- `tests/unit/test_logging.py` — FOUND (updated for structlog migration)

Commits:
- 0f8487b — FOUND (feat(09-01): add structlog+orjson deps and rewrite logging_config.py)
- aeebf43 — FOUND (feat(09-01): rewire app.py lifespan to call configure_logging())
- 43c4d72 — FOUND (test(09-01): Wave-0 regression assertions — ring scoping + env-driven log level)

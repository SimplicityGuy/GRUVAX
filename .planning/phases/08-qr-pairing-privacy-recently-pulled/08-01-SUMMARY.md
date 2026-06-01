---
phase: 08-qr-pairing-privacy-recently-pulled
plan: "01"
subsystem: backend-tests
tags: [privacy, priv-02, priv-03, test-only, ci-lock, ring-buffer]
dependency_graph:
  requires: []
  provides: [PRIV-02-ci-lock, PRIV-03-ci-lock]
  affects: [tests/integration/test_08_privacy.py]
tech_stack:
  added: []
  patterns: [asgi-lifespan-client, ring-buffer-assertion, psycopg3-cursor-api]
key_files:
  created:
    - tests/integration/test_08_privacy.py
  modified: []
decisions:
  - "Yield original app (not manager.app) from privacy_client fixture — manager.app is the ASGI callable wrapper; only the FastAPI app instance owns app.state.log_ring_buffer"
  - "schema discovery via SELECT current_schema() at runtime — never hardcode gruvax or gruvax_dev"
metrics:
  duration: ~8m
  completed: "2026-06-01"
  tasks_completed: 1
  tasks_total: 1
---

# Phase 8 Plan 01: Privacy CI-Lock (PRIV-02 + PRIV-03) Summary

**One-liner:** Three in-process regression tests CI-lock query-never-logged (PRIV-02), uvicorn.access suppression (PRIV-02), and no-search_log-table (PRIV-03) via ring-buffer assertion + schema-dynamic regclass check.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write test_08_privacy.py with PRIV-02 + PRIV-03 assertions | d6e90a7 | tests/integration/test_08_privacy.py |

## What Was Built

`tests/integration/test_08_privacy.py` — 163-line test module with three assertions:

1. **`test_query_never_in_logs`** — drives a real `/api/search?q=probe_priv02_xyz&limit=5` request through the ASGI client (app under `LifespanManager`), then inspects every entry in `app.state.log_ring_buffer`. Fails loudly with the offending entry if the probe term appears in any `msg` field (PRIV-02).

2. **`test_uvicorn_access_log_suppressed`** — asserts `logging.getLogger("uvicorn.access").level >= logging.WARNING`. Regression guard for `logging_config.py:188` — if the suppression is ever removed, this test turns red immediately (PRIV-02).

3. **`test_no_search_log_table`** — resolves the active schema at runtime via `SELECT current_schema()` (never hardcodes `gruvax` or `gruvax_dev`), then asserts `to_regclass('{schema}.search_log')` returns `NULL`. Ensures statistics remain aggregate-only (PRIV-03).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed fixture yielding manager.app instead of app for ring-buffer access**
- **Found during:** Task 1 (first test run)
- **Issue:** The plan's analog fixture (`test_diagnostics.py`) yields `manager.app` (the ASGI callable wrapper). Tests in that module access the ring buffer through the HTTP API (`/api/admin/diagnostics`), not directly via `app.state`. The new privacy test accesses `app.state.log_ring_buffer` directly — but `manager.app` is a callable wrapper with no `.state` attribute; `AttributeError: 'function' object has no attribute 'state'`.
- **Fix:** Changed `yield ac, manager.app` to `yield ac, app` in the `privacy_client` fixture. The ASGI transport uses `manager.app` (correct — the lifespan-wrapped callable), but the fixture now exposes the original FastAPI `app` instance so tests can access `app.state` directly.
- **Files modified:** `tests/integration/test_08_privacy.py` (fixture yield line)
- **Commit:** d6e90a7 (same commit — fix applied before the task commit)

## Verification Evidence

```
uv run pytest tests/integration/test_08_privacy.py -x -q
...                                                                      [100%]
3 passed, 1 warning in <time>s
EXIT_CODE: 0
```

All three privacy tests passed. No production code under `src/gruvax/` was modified (`git diff --name-only` shows only the new test file).

## Acceptance Criteria Checklist

- [x] `uv run pytest tests/integration/test_08_privacy.py -x -q` exits 0 with 3 passed
- [x] `test_query_never_in_logs` drives a search request (grep: `/api/search` + `log_ring_buffer` present)
- [x] Probe term `probe_priv02_xyz` appears as a single constant, asserted absent from every ring entry
- [x] `test_uvicorn_access_log_suppressed` asserts `>= logging.WARNING` on `uvicorn.access`
- [x] `test_no_search_log_table` resolves schema via `current_schema()` — no hardcoded `gruvax.search_log` / `gruvax_dev.search_log` literal in SQL queries
- [x] No file under `src/gruvax/` is modified (git diff shows only the new test file)

## Known Stubs

None — this plan adds tests only; no wired data or production stubs.

## Threat Flags

None — this plan adds tests only; no new network endpoints, auth paths, file access patterns, or schema changes introduced.

## Self-Check: PASSED

- [x] `tests/integration/test_08_privacy.py` exists and is 163 lines
- [x] Commit `d6e90a7` exists: `git log --oneline | grep d6e90a7` ✓
- [x] No production code modified (`git diff --name-only HEAD a4f4af6` shows only the test file)

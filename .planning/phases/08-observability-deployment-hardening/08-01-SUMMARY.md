---
phase: 08-observability-deployment-hardening
plan: "01"
subsystem: backend-observability-spine
tags: [observability, logging, slow-query, version-endpoint, sync-staleness, background-task, tdd]
dependency_graph:
  requires: []
  provides:
    - app.state.log_ring_buffer (deque maxlen=200, JSON log records)
    - app.state.slow_query_ring (deque maxlen=50, slow request entries)
    - app.state.sync_age_seconds (float | None, refreshed every 60s)
    - GET /api/version (public, returns git_sha/build_timestamp/environment)
    - JsonFormatter + LogRingHandler (src/gruvax/logging_config.py)
    - SLO_THRESHOLDS_MS + record_slow_query (src/gruvax/middleware/timing.py)
  affects:
    - src/gruvax/app.py (lifespan enriched, version router registered)
    - Plans 03/04/05 (consume app.state.log_ring_buffer, slow_query_ring, sync_age_seconds)
tech_stack:
  added: []
  patterns:
    - stdlib logging.Formatter subclass for JSON output (no new dependencies)
    - deque(maxlen=N) for in-memory ring buffers (O(1) append + auto-eviction)
    - inline record_slow_query() helper (zero middleware overhead vs BaseHTTPMiddleware)
    - CR-01 background task strong-reference pattern (app.state.background_tasks set)
    - try/except ImportError fallback for _version.py (Pitfall 4 compliance)
key_files:
  created:
    - src/gruvax/logging_config.py
    - src/gruvax/middleware/__init__.py
    - src/gruvax/middleware/timing.py
    - src/gruvax/_version.py
    - src/gruvax/api/version.py
    - tests/unit/test_logging.py
    - tests/unit/test_slow_query.py
    - tests/integration/test_version.py
  modified:
    - src/gruvax/app.py
decisions:
  - "Inline record_slow_query() helper chosen over BaseHTTPMiddleware (RESEARCH A5/Pitfall 3): zero overhead on 50ms locate SLO"
  - "stdlib logging.Formatter subclass over structlog: no new dependency, 30-line implementation, wires cleanly into existing logging.getLogger() pattern"
  - "_version.py committed as dev placeholder (GIT_SHA='dev'); Plan 03 adds .gitignore and Docker build-time generation"
  - "LogRingHandler stores ts as float (record.created) not ISO string for diagnostics sort/filter without string parsing"
metrics:
  duration: "13 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_changed: 9
---

# Phase 8 Plan 01: Observability Spine Summary

Backend observability spine wired: structured-JSON logging with in-memory log ring buffer, slow-query timing helper with per-endpoint SLO thresholds, public `/api/version` endpoint with build-time metadata, and background sync-staleness refresh publishing `app.state.sync_age_seconds`.

## What Was Built

### Task 1: JsonFormatter + LogRingHandler + slow-query timing (TDD)

`src/gruvax/logging_config.py` provides:
- `JsonFormatter` — emits each log record as a single-line JSON object `{ts, level, logger, msg}` with optional `exc` key on error records. `ts` is an ISO-8601 UTC string (`time.gmtime(record.created)`).
- `LogRingHandler` — appends `{ts: float, level, logger, msg}` dicts to a caller-supplied `deque`. Stores `ts` as a float (Unix epoch) for efficient numeric comparison in the diagnostics layer.

`src/gruvax/middleware/timing.py` provides:
- `SLO_THRESHOLDS_MS = {"/api/search": 200.0, "/api/locate": 50.0}` (D-09).
- `record_slow_query(app, path, total_ms, db_ms)` — appends a slow-request entry `{path, total_ms, db_ms, threshold_ms, ts}` to `app.state.slow_query_ring` only when `total_ms > threshold`. Total and DB ms are rounded to 1 decimal. No-ops for unknown paths, fast requests, or absent ring.

**TDD gates:** 36 unit tests (18 per module). RED committed first (ModuleNotFoundError confirmed). GREEN committed after implementation passes all 36.

### Task 2: _version.py + GET /api/version + router registration

`src/gruvax/_version.py` — dev placeholder (`GIT_SHA="dev"`, `BUILD_TIMESTAMP="unknown"`, `ENVIRONMENT="development"`). **Note for Plan 03:** this file must be added to `.gitignore` and generated at Docker build time via `ARG GIT_SHA` + `ARG BUILD_TIMESTAMP` injection in Stage 3, before the `USER gruvax` switch.

`src/gruvax/api/version.py` — `GET /api/version` router with `try/except ImportError` fallback (Pitfall 4 compliance). Returns only `git_sha`, `build_timestamp`, `environment` — no settings, DSN, PIN, or session secrets (T-08-01 mitigation). Public endpoint (no auth required).

`src/gruvax/app.py` — `version_router` registered in `create_app()` before the `StaticFiles` mount (Pitfall 3 order maintained). Import is inside `create_app()` body to prevent circular imports.

6 integration tests in `tests/integration/test_version.py` verify: 200 status, required keys, no forbidden secret keys, all values are non-empty strings, endpoint accessible without session cookie, exactly 3 keys in response.

### Task 3: Wire logging + ring buffers + sync-age refresh into app.py lifespan

Three additions to `lifespan()`:

**(a) Section 0 — configure logging** (before pool opens): reads `settings.LOG_LEVEL`, sets root logger level, replaces handlers with a single `StreamHandler(JsonFormatter())`, creates `deque(maxlen=200)` and assigns to `app.state.log_ring_buffer`, adds `LogRingHandler` to root logger.

**(b) Section 1b — ring buffer initialization** (after pool opens): `app.state.slow_query_ring = deque(maxlen=50)` (D-08) and `app.state.sync_age_seconds = None` seed (prevents `KeyError` in health.py before first background refresh).

**(c) Section 1c — sync-age background refresh** (after `background_tasks` set is created): `_refresh_sync_age()` coroutine queries `SELECT EXTRACT(EPOCH FROM (now() - max(synced_at))) FROM gruvax.v_collection` every 60 seconds via `pool.connection()` (Pitfall 1 — search_path preserved). On exception: logs warning, sets `None`. Registered on `app.state.background_tasks` (CR-01 strong-reference). Exception-logging done-callback added per Pitfall 2.

## Verification Results

```
Unit tests:  36 passed (test_logging.py + test_slow_query.py)
Integration: 11 passed, 1 skipped (test_health.py + test_version.py)
mypy --strict src/gruvax/: Success — no issues found in 59 source files
ruff check (plan files): All checks passed
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Inline helper approach chosen over BaseHTTPMiddleware**
- **Found during:** Task 1 implementation
- **Issue:** Plan action mentioned both inline and BaseHTTPMiddleware approaches; RESEARCH A5/Pitfall 3 clearly recommends inline.
- **Fix:** Implemented only `record_slow_query()` inline helper (no BaseHTTPMiddleware class). Consistent with plan's `<action>` directive: "Do NOT also add a BaseHTTPMiddleware class — inline is the chosen approach."
- **Files modified:** src/gruvax/middleware/timing.py
- **Commit:** d39ad3a

**2. [Rule 1 - Bug] Ruff linting fixes on newly-created files**
- **Found during:** Task 3 verification
- **Issues:** Unused `noqa: A003` directive (logging_config.py), EN DASH in docstring (timing.py), unused `pytest` imports in test files, unused variable in test_version.py
- **Fix:** Removed unused noqa, replaced EN DASH with hyphen, removed unused imports, prefixed unused variable with underscore
- **Files modified:** src/gruvax/logging_config.py, src/gruvax/middleware/timing.py, tests/unit/test_logging.py, tests/unit/test_slow_query.py, tests/integration/test_version.py
- **Commit:** 0ed6e8c

**3. [Rule 1 - Bug] mypy --strict type errors in app.py**
- **Found during:** Task 3 mypy run
- **Issues:** `deque[dict]` missing type args, `app.state.sync_age_seconds: float | None = None` annotation syntax on non-self attribute
- **Fix:** Changed to `deque[dict[str, Any]]` with `from typing import Any` import; removed inline annotation, added `# float | None` comment
- **Files modified:** src/gruvax/app.py
- **Commit:** 0ed6e8c

## Plan 03 Note

This plan committed `src/gruvax/_version.py` as a dev placeholder so that `from gruvax._version import ...` never raises `ImportError` in dev or CI environments. Plan 03 (Dockerfile + Docker Compose hardening) must:
1. Add `src/gruvax/_version.py` to `.gitignore`
2. Add `ARG GIT_SHA`, `ARG BUILD_TIMESTAMP`, `ARG GRUVAX_ENV=production` to Dockerfile Stage 3
3. Add the `RUN python3 -c "..."` generation step before `USER gruvax`
4. Enrich the `just build` recipe to pass `--build-arg GIT_SHA=$(git rev-parse --short HEAD) --build-arg BUILD_TIMESTAMP=...`

## Known Stubs

None. All three in-memory structures (`log_ring_buffer`, `slow_query_ring`, `sync_age_seconds`) are functional. The `_version.py` dev placeholder values (`"dev"`, `"unknown"`, `"development"`) are intentional pending Plan 03 Docker build integration — not UI-facing stubs.

## Threat Flags

No new threat surface introduced beyond what was in the plan's threat model.

- `GET /api/version` is public but returns only `git_sha`/`build_timestamp`/`environment` (T-08-01 mitigated, verified by integration test asserting no forbidden keys).
- Log ring buffer accumulates all log lines in memory; read-only via admin-gated diagnostics endpoint (Plan 04). No raw query text or PINs are logged (verified by reading search.py/queries.py patterns).
- Sync-age refresh task has 60s cadence, trivial load, exceptions caught and logged (T-08-03 accepted).

## Self-Check: PASSED

Files exist:
- src/gruvax/logging_config.py: FOUND
- src/gruvax/middleware/__init__.py: FOUND
- src/gruvax/middleware/timing.py: FOUND
- src/gruvax/_version.py: FOUND
- src/gruvax/api/version.py: FOUND
- tests/unit/test_logging.py: FOUND
- tests/unit/test_slow_query.py: FOUND
- tests/integration/test_version.py: FOUND

Commits verified:
- e0aba76: test(08-01) RED phase
- d39ad3a: feat(08-01) GREEN phase modules
- 6dc40b5: feat(08-01) version endpoint
- 0ed6e8c: feat(08-01) lifespan wiring

---
phase: 08-observability-deployment-hardening
plan: "03"
subsystem: backend-observability-api
tags: [observability, health, version, counters, slow-query, docker, privacy]
dependency_graph:
  requires: [08-01, 08-02]
  provides:
    - /api/health returns GIT_SHA version + sync_age_seconds (OBS-01, OBS-04, OBS-06)
    - search.py fires increment_search_count for top result release_id (OBS-07/D-04)
    - locate.py fires increment_selection_count on success path (OBS-07/D-04)
    - search.py and locate.py call record_slow_query (OBS-05/D-07)
    - Dockerfile Stage 3 bakes GIT_SHA/BUILD_TIMESTAMP/GRUVAX_ENV into _version.py at build time (OBS-04)
  affects:
    - src/gruvax/api/health.py
    - src/gruvax/api/search.py
    - src/gruvax/api/locate.py
    - Dockerfile
    - .gitignore
tech_stack:
  added: []
  patterns:
    - try/except ImportError for _version.py (Pitfall 4 — mandatory fallback)
    - getattr(request.app.state, field, default) for no-live-probe health reads
    - asyncio.create_task + CR-01 strong-ref + exception-logging done-callback (fire-and-forget)
    - time.perf_counter() for sub-millisecond timing in CPU-only endpoint
    - Dockerfile ARG injection before USER switch (needs root write to /app/src)
key_files:
  created: []
  modified:
    - src/gruvax/api/health.py
    - src/gruvax/api/search.py
    - src/gruvax/api/locate.py
    - Dockerfile
    - .gitignore
    - tests/integration/test_health.py
decisions:
  - "GIT_SHA imported via try/except ImportError (fallback 'dev') — _version.py gitignored; Docker build generates it"
  - "sync_age_seconds read from app.state only — no per-request DB probe per Plan 01 no-live-probe rule"
  - "Fire-and-forget counter tasks registered on app.state.background_tasks (CR-01 strong-ref)"
  - "locate timing uses time.perf_counter() at handler entry — CPU-only so db_ms=0.0 (POS-03)"
  - "search passes took_ms as both total_ms and db_ms to record_slow_query (Pitfall 3 inline approach)"
  - "selection_count NOT incremented on 404 path (D-04 explicit requirement)"
  - "Only int release_id flows to counter functions — never q/label/catalog text (OBS-07/PRIV-02)"
  - "_version.py removed from git tracking via git rm --cached; Plan 01 dev placeholder no longer committed"
metrics:
  duration: "7 minutes"
  completed_date: "2026-05-25"
  tasks_completed: 3
  files_changed: 6
---

# Phase 8 Plan 03: Observability API Surface + Docker Version Injection Summary

Instrumentation spine surfaced into user-facing contracts: `/api/health` now reports the git-SHA version and sync staleness; search/locate fire durable counters and slow-query ring entries; Docker builds bake `GIT_SHA`/`BUILD_TIMESTAMP`/`ENVIRONMENT` into `_version.py` at build time.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Enrich /api/health — git-SHA version + sync_age_seconds | 53e429a | src/gruvax/api/health.py, tests/integration/test_health.py |
| 2 | Instrument search/locate — counter increments + slow-query | 789cb3c | src/gruvax/api/search.py, src/gruvax/api/locate.py |
| 3 | Dockerfile ARG injection + .gitignore entry | 67ecf47 | Dockerfile, .gitignore, src/gruvax/_version.py (deleted from tracking) |

## What Was Built

### Task 1: Enriched /api/health

`src/gruvax/api/health.py`:
- Added `try: from gruvax._version import GIT_SHA / except ImportError: GIT_SHA = "dev"` at module top (Pitfall 4 compliance).
- Replaced `"version": "0.1.0"` with `"version": GIT_SHA`.
- Added `"sync_age_seconds": getattr(request.app.state, "sync_age_seconds", None)` — reads app.state only, no DB probe (OBS-06).
- No secrets leaked (T-08-09 mitigated; `session_secret`/`database_url`/`pin` confirmed absent by test).

`tests/integration/test_health.py`:
- `required_keys` set extended to include `sync_age_seconds`.
- New `test_version_is_git_sha`: asserts `body["version"] == _GIT_SHA` and `!= "0.1.0"`.
- New `test_sync_age_seconds_type`: asserts value is float, int, or None.
- New `test_no_secrets_in_health`: asserts no forbidden key (`session_secret`, `database_url`, `pin`) in response body.

### Task 2: Instrumented /api/search + /api/locate

`src/gruvax/api/search.py`:
- Imports `asyncio`, `increment_search_count`, `record_slow_query`.
- After `search_collection()`, calls `record_slow_query(request.app, "/api/search", took_ms, took_ms)` (Pitfall 3 — search total ~= DB time).
- When `rows` is non-empty: `asyncio.create_task(increment_search_count(pool, rows[0]["release_id"]))` with CR-01 strong-ref and exception-logging done-callback.
- Only `int release_id` reaches the counter — never `q` or `did_you_mean` (OBS-07/PRIV-02).

`src/gruvax/api/locate.py`:
- Imports `asyncio`, `time`, `increment_selection_count`, `record_slow_query`.
- `t0 = time.perf_counter()` at handler entry before the DB lookup.
- On 404 path: raises HTTPException without incrementing (D-04).
- On success path: `asyncio.create_task(increment_selection_count(pool, release_id))` with CR-01 strong-ref and exception-logging done-callback.
- `total_ms = (time.perf_counter() - t0) * 1000` then `record_slow_query(request.app, "/api/locate", total_ms, 0.0)` (CPU-only, POS-03).

### Task 3: Dockerfile ARG injection + .gitignore

`Dockerfile` Stage 3 (before `USER gruvax`):
```dockerfile
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ARG GRUVAX_ENV=production

RUN python3 -c "\
content = 'GIT_SHA = \"${GIT_SHA}\"\nBUILD_TIMESTAMP = \"${BUILD_TIMESTAMP}\"\nENVIRONMENT = \"${GRUVAX_ENV}\"\n';\
import pathlib; pathlib.Path('/app/src/gruvax/_version.py').write_text(content)\
"
```

`.gitignore` added `src/gruvax/_version.py`. The Plan 01 dev placeholder was removed from git tracking via `git rm --cached`. Both `version.py` and `health.py` have `try/except ImportError` fallbacks so the app boots cleanly without the file in dev.

**Docker build verified:** `docker build --build-arg GIT_SHA=testsha ...` → `gruvax._version.GIT_SHA == "testsha"` confirmed via `docker run`.

## Verification Results

```
uv run pytest tests/integration/test_health.py tests/integration/test_search.py tests/integration/test_locate.py -q
→ 33 passed, 1 skipped (SPA static/ not built — expected in non-Docker dev)

uv run mypy --strict src/gruvax/
→ Success: no issues found in 59 source files

uv run ruff check src/gruvax/api/health.py src/gruvax/api/search.py src/gruvax/api/locate.py tests/integration/test_health.py
→ All checks passed!

docker build --build-arg GIT_SHA=testsha ... → GIT_SHA=="testsha" in container: OK
```

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Pre-existing Ruff Issues (out of scope)

`uv run ruff check src/ tests/` reports 64 errors in pre-existing files (`admin/export.py`, `admin/import_.py`, `mqtt/lifecycle.py`, several test files). None of these were introduced by this plan. Per scope boundary: only the 6 modified files were linted for this plan — all pass cleanly. Pre-existing issues logged here for awareness.

## Known Stubs

None. All three observable behaviors are fully wired:
- `/api/health` returns the actual `GIT_SHA` value (not a UI placeholder).
- Counter increments are fire-and-forget but real — they write to `gruvax.record_stats` via the query functions from Plan 02.
- Slow-query ring buffer appends are real — they land in `app.state.slow_query_ring` for Plan 04's diagnostics endpoint to read.

## Threat Flags

No new threat surface beyond the plan's threat model:

| Threat ID | Status |
|-----------|--------|
| T-08-09 (Information Disclosure — /api/health body) | Mitigated: 4 tests assert GIT_SHA/sync_age_seconds present, no forbidden keys |
| T-08-10 (Information Disclosure — counter args) | Mitigated: only int release_id reaches increment_*; verified by reading call sites |
| T-08-11 (DoS — fire-and-forget tasks) | Mitigated: CR-01 strong-ref + exception-logging done-callback; failures logged, never delay response |
| T-08-12 (Tampering — no new packages) | N/A: no new packages added (stdlib asyncio/time + already-installed deps only) |

## Self-Check

Files verified:
- [x] src/gruvax/api/health.py — EXISTS, contains `sync_age_seconds` and `GIT_SHA`, does NOT contain `"0.1.0"`
- [x] src/gruvax/api/search.py — EXISTS, contains `increment_search_count` and `record_slow_query`
- [x] src/gruvax/api/locate.py — EXISTS, contains `increment_selection_count` and `record_slow_query`
- [x] Dockerfile — EXISTS, contains `ARG GIT_SHA` before `USER gruvax`
- [x] .gitignore — EXISTS, contains `src/gruvax/_version.py`
- [x] tests/integration/test_health.py — EXISTS, contains `test_version_is_git_sha`, `test_sync_age_seconds_type`, `test_no_secrets_in_health`

Commits verified:
- 53e429a: feat(08-03): enrich /api/health with git-SHA version + sync_age_seconds
- 789cb3c: feat(08-03): instrument search/locate — counter increments + slow-query recording
- 67ecf47: feat(08-03): Dockerfile ARG injection for _version.py + gitignore entry

## Self-Check: PASSED

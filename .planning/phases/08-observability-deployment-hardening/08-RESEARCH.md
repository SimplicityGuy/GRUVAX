# Phase 8: Observability + Deployment Hardening — Research

**Researched:** 2026-05-24
**Domain:** Python structured logging, FastAPI middleware, psycopg pool stats, GitHub Actions CI, pytest-benchmark, Docker Compose logging
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Staleness thresholds: admin diagnostics yellow >3d, red >14d; kiosk banner at >14d.
- **D-02:** Kiosk shows a banner only. No-results page stays generic. No-results staleness hint is DESCOPED.
- **D-03:** Sync timestamp exposed through `v_collection.synced_at`. `last_synced = max(v_collection.synced_at)`. Pitfall 5 preserved — no direct `collection_items` read.
- **D-04:** Two separate metrics per record: search count (increments on top result of search submission) and selection count (increments on `/api/locate` call with a specific `release_id`). Keyed by `release_id` only. No query text stored.
- **D-05:** All-time + recent 7-day columns for each metric.
- **D-06:** Counters are DURABLE — one new `gruvax` schema table. Diagnostics shows top-N. PIN-gated "Reset stats" admin action. Counting happens server-side.
- **D-07:** Slow-query log measures both request-total time AND DB-time component per request.
- **D-08:** In-memory ring buffer for slow queries (last N entries, resets on restart). Zero schema.
- **D-09:** Per-endpoint SLO thresholds: `/api/search` >200 ms, `/api/locate` >50 ms. Same timing path feeds `pytest-benchmark` gate.
- **D-10:** New `/admin/diagnostics` route, admin-gated (Phase 3 PIN/session + CSRF).
- **D-11:** Manual refresh button only. No polling, no SSE for telemetry.
- **D-12:** Recent log lines from in-memory log ring buffer (same pattern as D-08). No container log coupling.

### Claude's Discretion

- Structured-JSON logging approach (stdlib `logging` + JSON formatter vs. `structlog`).
- `/api/version` git SHA + build timestamp injection method.
- CI from scratch (GitHub Actions): lint/type/test + Alembic round-trip + `pytest-benchmark` p95 gate.
- Compose log limits values (`max-size` / `max-file`).
- Volume permissions doc (Pitfall 14).
- `just demo` smoke script mechanics.
- Phantom-boundary count query and psycopg pool stats sources.

### Deferred Ideas (OUT OF SCOPE)

- No-results page staleness hint (descoped D-02).
- External metrics/APM stack (Prometheus, Grafana, OpenTelemetry).
- Durable/historical slow-query trend.
- Rich search analytics (per-time-of-day, per-visitor, query-text).
- Disk-usage / log-volume diagnostics row.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| OBS-01 | `/healthz` endpoint reports overall status + per-subsystem reachability (Postgres, MQTT) and version | `src/gruvax/api/health.py` already exists; enrich with git SHA + `sync_age_seconds`; `app.state.db_ok`, `mqtt_ok`, `discogsography_view_ok` already present |
| OBS-02 | Service logs structured JSON; log level configurable via env var | `LOG_LEVEL` already in `settings.py`; stdlib `logging` + custom `JsonFormatter` recommended; in-memory log ring buffer wired as a `logging.Handler` |
| OBS-03 | CI proves Alembic migration round-trips clean on every push | `just migrate-roundtrip` recipe already exists; GitHub Actions workflow needs creating; Postgres service container needed |
| OBS-04 | `/version` endpoint reports git SHA, build timestamp, environment | Docker `ARG GIT_SHA` + `ARG BUILD_TIMESTAMP` injected at build time; written to `src/gruvax/_version.py` at build; `ENV GRUVAX_ENV` in Dockerfile |
| OBS-05 | Admin diagnostics surface a slow-query log (search >200 ms flagged) | Starlette `BaseHTTPMiddleware` + per-request `time.perf_counter()` with psycopg timing hook; feeds in-memory `deque(maxlen=N)` |
| OBS-06 | Admin diagnostics show discogsography-sync staleness | `v_collection` already has `synced_at` column (confirmed in migration 0002); query `SELECT max(synced_at) FROM gruvax.v_collection` |
| OBS-07 | Admin diagnostics aggregate top-N most-searched records (no per-query text persisted) | New `gruvax.record_stats` table; increment on search/locate paths; diagnostics read top-10 |
| DEP-04 | Each Compose service declares log-size limits | Add `logging:` key to `api` and `mosquitto` services in `compose.yaml` |
| DEP-05 | Each Compose service declares healthcheck + `restart: unless-stopped` | Already present on all three services (`api`, `gruvax-dev-pg`, `mosquitto`); verify/round out |
</phase_requirements>

---

## Summary

Phase 8 is almost entirely enrichment and cross-cutting plumbing — there are no new core services to introduce. The v1 operational shape is already established: a FastAPI app with a psycopg pool, an Alembic migration chain (currently at `0007`), Compose stack with three services, and a comprehensive test suite.

**Critical discoveries that directly answer CONTEXT.md open questions:**

1. **`v_collection.synced_at` already exists.** Migration 0002 (`_CREATE_VIEW`) selects `ci.updated_at AS synced_at` from `collection_items`. The staleness query is `SELECT max(synced_at) FROM gruvax.v_collection` — no view change needed. D-03 is fully satisfied by the existing schema. `[VERIFIED: codebase read]`

2. **stdlib `logging` + a hand-rolled `JsonFormatter` is the right choice** over `structlog`. No new dependency; `structlog` is not in `pyproject.toml` and would require a new dep. A `JsonFormatter` subclassing `logging.Formatter` with `format()` returning `json.dumps({...})` integrates cleanly with the existing `logger = logging.getLogger(__name__)` pattern used in every module. The log ring buffer is a custom `logging.Handler` that appends to a `collections.deque(maxlen=200)` stored in `app.state.log_ring_buffer`. `[VERIFIED: codebase read]`

3. **Git SHA injection:** use two Docker `ARG` declarations (`GIT_SHA`, `BUILD_TIMESTAMP`) in the runtime stage, written to `src/gruvax/_version.py` via a `RUN` command before the `USER gruvax` switch. `GRUVAX_ENV` detected from an env var (default `"production"` in prod image, `"development"` when running outside Docker). `[VERIFIED: codebase read + Docker best practice]`

4. **CI from scratch:** no `.github/workflows/` exists. A single `ci.yml` workflow using `ubuntu-latest`, `astral-sh/setup-uv`, `setup-python`, and a `postgres:18` service container covers lint/type/test + Alembic round-trip + benchmark gate. Pattern aligned with discogsography's `code-quality.yml` and `build.yml`. `[VERIFIED: gh api read of discogsography]`

5. **psycopg pool stats:** `pool.get_stats()` returns a `dict[str, int]` with keys `pool_size`, `pool_available`, `pool_min`, `pool_max`, `requests_num`, `requests_waiting`, etc. The diagnostics endpoint reads `pool.get_stats()["pool_size"] - pool.get_stats()["pool_available"]` for `size_used` and `pool.get_stats()["pool_min"]` for `size_min`. `[VERIFIED: uv run python introspection]`

6. **Phantom-boundary count query:** a phantom is a cube boundary row whose `(first_label, first_catalog)` does not appear in `gruvax.v_collection`. The query is a LEFT JOIN between `cube_boundaries` (non-empty rows only) and `v_collection` returning COUNT where the match is NULL. `[VERIFIED: codebase read of `cube_exact_match` in queries.py + boundary validation patterns]`

7. **pytest-benchmark `5.2.3` is already a dev dependency.** The algorithm benchmark test (`test_locate_benchmark`) already uses it and asserts `benchmark.stats["mean"] * 1000 < 50`. The search endpoint benchmark needs a new integration test using `httpx.AsyncClient` with `pytest-benchmark`'s async mode. `[VERIFIED: pyproject.toml + test_algorithm.py]`

**Primary recommendation:** Implement Phase 8 as five vertical slices: (1) health/version enrichment slice, (2) structured-logging + ring-buffer slice, (3) diagnostics backend slice (staleness + counters + pool/phantom stats + slow-query middleware), (4) diagnostics frontend slice (the new page + kiosk banner), and (5) CI + Compose hardening slice. Each slice is end-to-end and independently testable.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Git SHA / build timestamp injection | Container build (Dockerfile ARG) | Settings / `_version.py` module | Build-time data must be baked in at image build; runtime settings read from the generated file |
| Structured JSON log output | API / Backend (`app.py` lifespan) | — | All Python logging routes through stdlib `logging`; formatter wired once at app init |
| In-memory log ring buffer | API / Backend (`app.state`) | — | Ephemeral; lives in the running process; no persistence tier |
| Slow-query timing (request-total) | API / Backend (Starlette middleware) | — | Wraps the full ASGI dispatch; only place with both request-in and response-out times |
| Slow-query DB time measurement | API / Backend (psycopg cursor timing) | — | DB time measured inside `search_collection()` and `get_release_for_locate()` via `time.perf_counter()` — already present in `search_collection` returning `took_ms` |
| Search/selection counters | API / Backend + Database (gruvax schema) | — | Counters are durable; one new table; incremented on search/locate paths server-side |
| Sync staleness read | Database / Storage (v_collection) | API / Backend | `max(synced_at)` is a single DB read; result cached per-request or at health-check cache level |
| `/api/health` enrichment | API / Backend (`health.py`) | — | Existing endpoint; enriched with fields from `app.state` |
| `/api/version` | API / Backend (new `version.py` router) | — | Public endpoint; reads `_version.py` + `settings.GRUVAX_ENV` |
| Diagnostics backend API | API / Backend (`api/admin/diagnostics.py`) | — | Admin-gated; aggregates pool stats, ring buffers, DB reads |
| Diagnostics frontend page | Frontend (React SPA) | — | `/admin/diagnostics` route; `el()` / `replaceChildren()` DOM pattern |
| Kiosk staleness banner | Frontend (kiosk SPA) | — | Reads `sync_age_seconds` from `/api/health` response; mounts banner if >14d |
| Compose log limits | Container / Ops (`compose.yaml`) | — | Driver-level log rotation; no application code change |
| GitHub Actions CI | CI/CD pipeline | — | Lint + test + Alembic round-trip + benchmark gate |

---

## Standard Stack

### Core (all already in pyproject.toml)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `logging` | 3.14 built-in | Log emission + JSON formatter + ring buffer handler | Already used everywhere; no new dependency |
| `collections.deque` | 3.14 built-in | Ring buffer for slow-query log and log lines | O(1) append + `maxlen` auto-eviction; no new dep |
| `time.perf_counter` | 3.14 built-in | Request-total and DB-time measurement | Already used in `queries.search_collection` |
| `psycopg_pool.AsyncConnectionPool.get_stats()` | psycopg-pool 3.3.1 (installed) | Pool `size_used` / `size_min` read | Official pool stats API; `[VERIFIED: uv run introspection]` |
| `pytest-benchmark` | 5.2.3 (installed) | p95 SLO gate for search + locate | Already a dev dep; `test_locate_benchmark` uses it |
| `alembic` | 1.18.4 (installed) | Migration `0008` (record_stats table) | Already the project migration tool |
| Starlette `BaseHTTPMiddleware` | bundled with fastapi | Slow-query timing wrapper | Already available; no new dep; request lifecycle hooks |

### New (this phase)

| Library | Version | Purpose | Why |
|---------|---------|---------|-----|
| None | — | No new runtime dependencies | Phase 8 uses stdlib + already-installed packages exclusively |

**Zero new runtime dependencies.** This is consistent with the footprint constraint.

---

## Package Legitimacy Audit

No new packages are introduced in this phase. All tooling is stdlib or already in `pyproject.toml`.

| Package | Status |
|---------|--------|
| No new packages | N/A — stdlib + existing deps only |

---

## Architecture Patterns

### System Architecture Diagram

```mermaid
flowchart TD
    subgraph Build["Build time (Dockerfile)"]
        ARG["ARG GIT_SHA / BUILD_TIMESTAMP"]
        GEN["RUN: write src/gruvax/_version.py"]
        ARG --> GEN
    end

    subgraph App["Runtime: FastAPI app"]
        LF["lifespan: wire JsonFormatter\n+ LogRingHandler → root logger"]
        MW["SlowQueryMiddleware\n(BaseHTTPMiddleware)"]
        SRB["app.state.slow_query_ring\n(deque maxlen=50)"]
        LRB["app.state.log_ring_buffer\n(deque maxlen=200)"]
        POOL["app.state.db_pool\n(AsyncConnectionPool)"]
        LF --> MW
        LF --> SRB
        LF --> LRB
    end

    subgraph Endpoints["API layer"]
        HEA["GET /api/health\n+ version (git SHA)\n+ sync_age_seconds"]
        VER["GET /api/version\n(git SHA, build_ts, env)"]
        DIAG["GET /api/admin/diagnostics\n(session + CSRF gated)"]
        RST["POST /api/admin/diagnostics/reset-stats\n(session + CSRF gated)"]
        SRCH["GET /api/search\n(increments search_count)"]
        LOC["GET /api/locate\n(increments selection_count)"]
    end

    subgraph DB["gruvax schema"]
        VC["v_collection\n(synced_at already present)"]
        RS["record_stats\n(NEW migration 0008)\nrelease_id, search_count, selection_count\nlast_searched_at, last_selected_at"]
    end

    subgraph CI["GitHub Actions ci.yml"]
        LINT["ruff + mypy"]
        TEST["pytest (unit + integration)\nAlembic round-trip"]
        BENCH["pytest-benchmark\np95 search ≤200ms\np95 locate ≤50ms"]
        LINT --> TEST --> BENCH
    end

    GEN -->|"_version.py read at import"| VER
    GEN -->|"_version.py read at import"| HEA
    VC -->|"max(synced_at)"| HEA
    VC -->|"max(synced_at)"| DIAG
    RS -->|"top-N counts"| DIAG
    POOL -->|"get_stats()"| DIAG
    SRB -->|"slow query entries"| DIAG
    LRB -->|"recent log lines"| DIAG
    MW -->|"request >SLO → append"| SRB
    MW -->|"times every request"| SRCH
    MW -->|"times every request"| LOC
    SRCH -->|"UPSERT search_count"| RS
    LOC -->|"UPSERT selection_count"| RS
    RST -->|"TRUNCATE / zero counters"| RS
```

### Recommended Project Structure for New Files

```
src/gruvax/
├── _version.py              # NEW — generated at Docker build time (git SHA, build_ts, env)
├── logging_config.py        # NEW — JsonFormatter + LogRingHandler classes
├── middleware/
│   └── timing.py            # NEW — SlowQueryMiddleware (BaseHTTPMiddleware)
├── api/
│   ├── health.py            # ENRICH — add version (git SHA) + sync_age_seconds
│   ├── version.py           # NEW — GET /api/version router
│   └── admin/
│       ├── diagnostics.py   # NEW — GET /api/admin/diagnostics + POST reset-stats
│       └── router.py        # ENRICH — add diagnostics_router
├── db/
│   └── queries.py           # ENRICH — add staleness_query(), record_stats queries,
│                            #           phantom_boundary_count()
migrations/
└── versions/
    └── 0008_record_stats.py # NEW — gruvax.record_stats table
frontend/src/routes/admin/
├── Diagnostics.tsx          # NEW — /admin/diagnostics page (el()/replaceChildren())
├── Diagnostics.css          # NEW — scoped CSS using design tokens
└── AdminShell.tsx           # ENRICH — add DIAGNOSTICS nav tab
frontend/src/routes/kiosk/
└── KioskApp.tsx (or similar) # ENRICH — staleness banner component
.github/workflows/
└── ci.yml                   # NEW — lint + test + Alembic round-trip + benchmark gate
```

---

## Open Question 1: `v_collection.synced_at` — RESOLVED

**Finding:** The column already exists. Migration `0002_v_collection_view.py` line 49 selects `ci.updated_at AS synced_at` from `collection_items`. No view change is needed.

**Staleness query (psycopg `%s` style, via `gruvax.v_collection`):**

```python
# Source: codebase read of migration 0002 + queries.py pattern
async def get_sync_staleness_seconds(pool: AsyncConnectionPool) -> float | None:
    """Return seconds since last discogsography sync, or None if v_collection is empty."""
    sql = "SELECT EXTRACT(EPOCH FROM (now() - max(synced_at))) FROM gruvax.v_collection"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        row = await cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])
```

The result is cached in `app.state.sync_age_seconds` (updated at startup + periodically or on each health check) to avoid a DB round-trip on every `/api/health` call. A lightweight refresh every 60 seconds via `asyncio.create_task` in lifespan is sufficient.

---

## Open Question 2: Structured-JSON Logging — RECOMMENDATION

**Decision: stdlib `logging` + a project-local `JsonFormatter`.**

Rationale: `structlog` is not in the project (confirmed — `uv run python -c "import structlog"` fails). Adding it would introduce a new dependency for functionality that can be achieved with 30 lines of stdlib code. The existing codebase uses `logging.getLogger(__name__)` uniformly; the formatter is wired once at app startup and requires zero per-module changes.

### JsonFormatter Implementation Pattern

```python
# Source: stdlib logging docs + project patterns
# Location: src/gruvax/logging_config.py
import json
import logging
import time
from collections import deque
from typing import Any

class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": message,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class LogRingHandler(logging.Handler):
    """Handler that appends formatted records to an in-memory deque (D-12).

    Thread-safe via logging's built-in handler lock (self.acquire/release).
    The deque is stored on app.state.log_ring_buffer so the diagnostics
    endpoint can tail it without coupling to journald or the container runtime.
    """

    def __init__(self, ring: deque[dict[str, Any]], level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._ring = ring

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ring.append({
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            })
        except Exception:
            self.handleError(record)
```

### Wiring in `app.py` lifespan (before `yield`)

```python
# Source: codebase read of app.py + stdlib logging docs
import logging
import os
from collections import deque
from gruvax.logging_config import JsonFormatter, LogRingHandler

def _configure_logging(app: FastAPI) -> None:
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)

    # JSON stdout handler
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]  # replace any default handlers

    # In-memory ring buffer for diagnostics (D-12)
    ring: deque[dict] = deque(maxlen=200)
    app.state.log_ring_buffer = ring
    ring_handler = LogRingHandler(ring, level=logging.DEBUG)
    root.addHandler(ring_handler)
```

Call `_configure_logging(app)` at the very start of the `lifespan()` context manager (before any `logger.info` calls).

---

## Open Question 3: `/api/version` + Git SHA Injection — RECOMMENDATION

### Dockerfile injection pattern

```dockerfile
# In Stage 3 (runtime) of Dockerfile — AFTER COPY --from=python-builder
# Source: Docker best-practice for build-time metadata
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ARG GRUVAX_ENV=production

# Write _version.py before switching to non-root user
RUN python3 -c "
content = '''# Auto-generated at build time. Do not edit.
GIT_SHA = \"${GIT_SHA}\"
BUILD_TIMESTAMP = \"${BUILD_TIMESTAMP}\"
ENVIRONMENT = \"${GRUVAX_ENV}\"
'''
import pathlib
pathlib.Path('/app/src/gruvax/_version.py').write_text(content)
"
```

### Build invocation (in GitHub Actions / justfile)

```bash
docker build \
  --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
  --build-arg BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
  --build-arg GRUVAX_ENV=production \
  -t gruvax-api:local .
```

### `/api/version` endpoint

```python
# Source: codebase read of health.py pattern + _version module
# Location: src/gruvax/api/version.py
from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from gruvax._version import GIT_SHA, BUILD_TIMESTAMP, ENVIRONMENT
except ImportError:
    GIT_SHA = "dev"
    BUILD_TIMESTAMP = "unknown"
    ENVIRONMENT = "development"

router = APIRouter(tags=["version"])

@router.get("/version")
async def get_version() -> JSONResponse:
    """Public endpoint: git SHA, build timestamp, environment."""
    return JSONResponse({
        "git_sha": GIT_SHA,
        "build_timestamp": BUILD_TIMESTAMP,
        "environment": ENVIRONMENT,
        "version": "0.1.0",  # pyproject.toml version
    })
```

The same `GIT_SHA` import replaces the hardcoded `"0.1.0"` in `health.py`'s `version` field.

**`settings.py` change:** No new Settings field needed — `GRUVAX_ENV` is baked into `_version.py` at build time, not read from env at runtime. This avoids requiring an env var be set in compose.yaml.

---

## Open Question 4: CI from Scratch — RECOMMENDATION

### GitHub Actions `ci.yml` design

Pattern follows discogsography's `code-quality.yml` (uses `astral-sh/setup-uv`, `actions/checkout`, `actions/setup-python`, `extractions/setup-just`). Key differences: GRUVAX has a Postgres dependency for integration tests.

```yaml
# Source: discogsography code-quality.yml pattern + GitHub Actions docs
# Location: .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  CI: true
  PYTHON_VERSION: "3.14"

permissions:
  contents: read

jobs:
  ci:
    runs-on: ubuntu-latest
    timeout-minutes: 15

    services:
      postgres:
        image: postgres:18
        env:
          POSTGRES_USER: gruvax
          POSTGRES_PASSWORD: gruvax
          POSTGRES_DB: gruvax
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U gruvax -d gruvax"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 20

    env:
      DATABASE_URL: "postgresql+psycopg://gruvax:gruvax@localhost:5432/gruvax"
      OBSERVED_DISCOGSOGRAPHY_SCHEMA: "gruvax_dev"
      SESSION_SECRET: "ci-test-secret-not-real"
      LOG_LEVEL: "WARNING"

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v8
        with:
          version: latest
          enable-cache: true

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: uv sync --frozen

      - name: Lint
        run: uv run ruff check src/ tests/

      - name: Format check
        run: uv run ruff format --check src/ tests/

      - name: Type check
        run: uv run mypy --strict src/gruvax/

      - name: Seed synthetic collection
        run: psql postgresql://gruvax:gruvax@localhost:5432/gruvax < fixtures/synth_collection.sql

      - name: Alembic round-trip
        run: |
          uv run alembic upgrade head
          uv run alembic downgrade base
          uv run alembic upgrade head

      - name: Test suite
        run: uv run pytest tests/ -q --tb=short

      - name: Benchmark SLO gate (synthetic data only)
        run: |
          uv run pytest tests/unit/test_algorithm.py::test_locate_benchmark \
            tests/integration/test_search_benchmark.py \
            --benchmark-only --benchmark-json=benchmark.json -q
          uv run python scripts/check_benchmark.py benchmark.json
```

**Benchmark gate strategy:** Fail the build on regression (`--benchmark-only` mode; a `check_benchmark.py` script reads the JSON and asserts p95 search ≤200ms and p95 locate ≤50ms). Rationale: the SLO is a v1 acceptance criterion (SC5); silent regression would break the Core Value.

**`tests/integration/test_search_benchmark.py`** — new file needed for the `/api/search` p95 gate using `httpx.AsyncClient` against the live ASGI app with a Postgres fixture.

**Note on CI `NODE_VERSION`:** The frontend build is not gated in CI for this phase — the benchmark only covers the backend. A separate `build.yml` can add frontend checks. `[ASSUMED]`

---

## Open Question 5: Slow-Query Instrumentation — RECOMMENDATION

### Timing middleware pattern

```python
# Source: Starlette docs + FastAPI middleware patterns + codebase read
# Location: src/gruvax/middleware/timing.py
import time
from collections import deque
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Per-endpoint SLO thresholds (D-09)
SLO_THRESHOLDS_MS: dict[str, float] = {
    "/api/search": 200.0,
    "/api/locate": 50.0,
}

class SlowQueryMiddleware(BaseHTTPMiddleware):
    """Record request-total + DB-time for requests exceeding per-endpoint SLO (D-07/08/09).

    DB-time is carried on the request scope via a context variable set by
    the query layer (search_collection / get_release_for_locate already
    return took_ms; the endpoint handlers store it on request.state).

    Only records slow requests (above threshold). Ring buffer is in app.state.
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        t0 = time.perf_counter()
        response = await call_next(request)
        total_ms = (time.perf_counter() - t0) * 1000.0

        path = request.url.path
        threshold = SLO_THRESHOLDS_MS.get(path)
        if threshold is not None and total_ms > threshold:
            db_ms: float = getattr(request.state, "db_took_ms", 0.0)
            ring: deque[dict[str, Any]] = getattr(
                request.app.state, "slow_query_ring", deque()
            )
            ring.append({
                "path": path,
                "total_ms": round(total_ms, 1),
                "db_ms": round(db_ms, 1),
                "threshold_ms": threshold,
                "ts": time.time(),
            })
        return response
```

### DB-time propagation

`search_collection()` already returns `took_ms`. The `/api/search` handler stores it: `request.state.db_took_ms = took_ms`. Same pattern for `/api/locate` (which is CPU-only per POS-03 — `db_ms` will be near 0 for locate).

### Wiring in `app.py`

```python
# In create_app() BEFORE routers, AFTER app creation:
from gruvax.middleware.timing import SlowQueryMiddleware
app.add_middleware(SlowQueryMiddleware)

# In lifespan (startup):
from collections import deque
app.state.slow_query_ring = deque(maxlen=50)  # D-08: last 50 entries
```

---

## Open Question 6: Most-Searched Counters — RECOMMENDATION

### Table shape (migration `0008`)

```sql
-- Source: D-04/D-05/D-06 locked decisions + schema patterns from migration 0004
CREATE TABLE gruvax.record_stats (
    release_id          BIGINT PRIMARY KEY,
    search_count        BIGINT  NOT NULL DEFAULT 0,
    selection_count     BIGINT  NOT NULL DEFAULT 0,
    last_searched_at    TIMESTAMPTZ,
    last_selected_at    TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_record_stats_search_count
    ON gruvax.record_stats (search_count DESC);
```

**All-time + 7-day pattern (D-05):** Use timestamped `last_searched_at` / `last_selected_at` columns rather than rolling-bucket columns. The "recent 7-day" count is derived at query time with a separate lightweight approach: add `search_count_7d` and `selection_count_7d` columns and increment them alongside the all-time counters, but reset (set to 0) when `last_searched_at` rolls past 7 days on the next write. This avoids a `COUNT(*) WHERE ts > now() - 7d` query over potentially many rows. The reset-check happens atomically in the UPSERT.

**Recommended UPSERT shape for search count increment:**

```sql
-- Source: Postgres UPSERT pattern + D-04 requirements
INSERT INTO gruvax.record_stats
    (release_id, search_count, search_count_7d, last_searched_at, updated_at)
VALUES (%s, 1, 1, now(), now())
ON CONFLICT (release_id) DO UPDATE SET
    search_count     = gruvax.record_stats.search_count + 1,
    search_count_7d  = CASE
        WHEN gruvax.record_stats.last_searched_at > now() - INTERVAL '7 days'
        THEN gruvax.record_stats.search_count_7d + 1
        ELSE 1
    END,
    last_searched_at = now(),
    updated_at       = now()
```

This makes the 7-day window a rolling count without a separate events table. `[ASSUMED]` — planner should confirm rolling-bucket approach is acceptable vs. events table.

**Migration 0008 adds columns:** `release_id`, `search_count`, `search_count_7d`, `selection_count`, `selection_count_7d`, `last_searched_at`, `last_selected_at`, `updated_at`.

**Hook points:**
- `/api/search`: increment `search_count` + `search_count_7d` for the TOP result only (`rows[0]["release_id"]` when `rows` is non-empty). Fire-and-forget via `asyncio.create_task` to avoid blocking the response.
- `/api/locate`: increment `selection_count` + `selection_count_7d` for the `release_id` param. Same fire-and-forget pattern.

**Reset stats:** `TRUNCATE gruvax.record_stats` (fastest; equivalent to DELETE all + reset sequences, but there are no sequences here).

**Top-N diagnostics query:**

```sql
-- Source: D-05 diagnostics display + v_collection join pattern from queries.py
SELECT
    rs.release_id,
    v.title,
    v.primary_artist,
    rs.search_count,
    rs.search_count_7d,
    rs.selection_count,
    rs.selection_count_7d
FROM gruvax.record_stats rs
JOIN gruvax.v_collection v ON v.release_id = rs.release_id
ORDER BY rs.search_count DESC
LIMIT %s
```

---

## Open Question 7: Pool Stats + Phantom-Boundary Count — RESOLVED

### psycopg pool stats

`pool.get_stats()` returns `dict[str, int]`. Relevant keys confirmed via introspection:

```python
# Source: uv run python introspection (verified)
stats = pool.get_stats()
size_used = stats["pool_size"] - stats["pool_available"]  # connections currently checked out
size_min  = stats["pool_min"]   # min_size from create_pool() = 2
```

Pool object is at `request.app.state.db_pool`. `get_stats()` is synchronous and non-blocking.

### Phantom-boundary count query

A phantom boundary is a `cube_boundaries` row where `is_empty = FALSE` and the `(first_label, first_catalog)` pair does not exist in `gruvax.v_collection`. This matches the existing `cube_exact_match()` pattern in `queries.py`.

```sql
-- Source: codebase read of cube_exact_match() + boundary_validation patterns
-- All %s parameterized; reads ONLY v_collection (Pitfall 5 preserved)
SELECT COUNT(*)
FROM gruvax.cube_boundaries cb
WHERE cb.is_empty = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM gruvax.v_collection v
      WHERE lower(v.label) = lower(cb.first_label)
        AND v.catalog_number = cb.first_catalog
  )
```

This is an O(boundaries × v_collection) scan but cube_boundaries has ≤32 rows — effectively free.

---

## OBS-01: Enriched `/api/health` Fields

Current `health.py` returns: `db`, `discogsography_view_check`, `mqtt`, `status`, `version` (hardcoded `"0.1.0"`), `started_at`.

**New fields to add:**

```python
# Source: codebase read of health.py + research findings above
body: dict[str, Any] = {
    "status": overall,
    "db": db_status,
    "discogsography_view_check": view_status,
    "mqtt": mqtt_status,
    "version": GIT_SHA,            # replaces "0.1.0" hardcode
    "started_at": started_at.isoformat(),
    "sync_age_seconds": getattr(request.app.state, "sync_age_seconds", None),
}
```

`sync_age_seconds` is updated in `app.state` by a background refresh task (not a live DB probe per-request). The kiosk SPA reads this field directly from the existing `/api/health` response — no new endpoint needed for the kiosk banner trigger.

---

## DEP-04: Compose Log Limits

Add `logging:` to `api` and `mosquitto` services. `gruvax-dev-pg` (the dev Postgres) is less critical on lux production but should also have limits.

```yaml
# Source: Docker Compose logging driver docs + home-LAN disk constraint
# Recommended values for a home server with bounded disk
logging:
  driver: "json-file"
  options:
    max-size: "10m"   # 10 MB per log file
    max-file: "3"     # keep last 3 rotations → max 30 MB per service
```

Rationale: `10m × 3 = 30 MB` per service (api + mosquitto = 60 MB total) is a safe upper bound for a home LAN server. Aligns with common Docker home-server guidance. `[ASSUMED]` — operator can tune based on lux's actual disk headroom.

---

## DEP-05: Healthcheck Verification

**Already present (confirmed by codebase read of `compose.yaml`):**

- `api`: `healthcheck` uses `python -c "import urllib.request; urllib.request.urlopen(...).read()"` against `http://127.0.0.1:8000/api/health`; `interval: 30s`; `restart: unless-stopped`. Complete.
- `gruvax-dev-pg`: `pg_isready`; `interval: 5s`; `restart: unless-stopped`. Complete.
- `mosquitto`: `mosquitto_sub -t '$$SYS/broker/uptime' -C 1 -W 3`; `interval: 30s`; `restart: unless-stopped`. Complete.

**Action for DEP-05:** Verify only — no code change needed. The verification task confirms the above healthchecks survive a `docker compose down && docker compose up` sequence and that `docker compose ps` shows `(healthy)` for all three services. The volume permissions documentation (Pitfall 14) is a runbook addition, not a code change.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON log formatting | Custom serialization | `json.dumps()` in a `logging.Formatter` subclass | 30 lines; stdlib only; handles exc_info |
| Ring buffer | Circular list with manual eviction | `collections.deque(maxlen=N)` | Thread-safe appends; O(1) eviction; stdlib |
| Pool statistics | `SELECT COUNT(*) FROM pg_stat_activity` | `pool.get_stats()` | Official psycopg_pool API; no DB round-trip |
| Benchmark gate | Custom timing harness | `pytest-benchmark` (already installed) | Already used in `test_locate_benchmark`; p95 statistic built-in |
| CI Postgres service | Docker Compose in CI | GitHub Actions `services:` block | Native GH Actions feature; healthcheck-aware |
| Git SHA at runtime | `subprocess.run(["git", "rev-parse"])` | `ARG GIT_SHA` → `_version.py` | Git not present in runtime image; ARG is the standard pattern |

---

## Common Pitfalls

### Pitfall 1: v_collection search_path required for `max(synced_at)`

**What goes wrong:** `SELECT max(synced_at) FROM gruvax.v_collection` fails with "relation does not exist" when the pool connection's `search_path` doesn't include `gruvax` and the observed schema.

**Why it happens:** The staleness query is a new code path that might be called outside the pool (e.g., in a test with a raw connection). The `search_path` is set only via `_configure_connection` in `pool.py`.

**How to avoid:** Always issue staleness queries through the standard pool (`Depends(get_pool)` or `pool.connection()` from `app.state.db_pool`). Tests that need staleness data must use the `db_pool` fixture which uses `create_pool()`.

**Warning signs:** `psycopg.errors.UndefinedTable: relation "gruvax.v_collection" does not exist` in tests.

### Pitfall 2: Fire-and-forget counter increments fail silently

**What goes wrong:** `asyncio.create_task(increment_search_count(...))` raises an exception (network hiccup, pool exhausted) that is never awaited and therefore silently swallowed.

**Why it happens:** Asyncio tasks that are not awaited eat exceptions. The existing `background_tasks` strong-reference pattern (CR-01 in `app.py`) must be reused.

**How to avoid:** Add a `done_callback` that logs exceptions:

```python
task = asyncio.create_task(increment_search_count(pool, release_id))
app.state.background_tasks.add(task)
task.add_done_callback(app.state.background_tasks.discard)
# Add exception logger:
def _log_task_exc(t: asyncio.Task) -> None:
    if not t.cancelled() and t.exception():
        logger.warning("Background stats increment failed: %s", t.exception())
task.add_done_callback(_log_task_exc)
```

**Warning signs:** Stats counters stuck at 0 despite searches happening.

### Pitfall 3: SlowQueryMiddleware adds latency on the fast path

**What goes wrong:** `BaseHTTPMiddleware` in Starlette incurs overhead (~0.5–1 ms per request) due to response streaming buffering. For `locate` with a 50 ms SLO, this matters.

**Why it happens:** `BaseHTTPMiddleware` buffers the response body. For streaming responses (SSE), this breaks entirely.

**How to avoid:** Use `Starlette.BaseHTTPMiddleware` for non-streaming endpoints only. The SSE endpoint (`/api/events`) should be excluded from timing. Starlette's `route_class` approach or an ASGI-level middleware is better for zero-overhead, but `BaseHTTPMiddleware` is acceptable for this SLO level. Alternatively, skip middleware altogether and instrument `search()` and `locate()` directly — they already have `took_ms` context. Direct instrumentation is safer than adding middleware overhead.

**Recommended alternative:** Inline instrumentation in the route handlers rather than middleware:

```python
# In search() handler, after rows, took_ms, did_you_mean = await search_collection(...)
request.state.db_took_ms = took_ms
total_ms = took_ms  # for search, total ≈ DB time (small framework overhead)
_maybe_record_slow(request.app, "/api/search", total_ms, took_ms, 200.0)
```

This avoids the middleware overhead concern entirely. The middleware approach remains valid but inline is simpler and has zero overhead on the fast path. `[ASSUMED]` — planner should pick one approach.

**Warning signs:** `/api/locate` p95 starts drifting above 50 ms after adding middleware.

### Pitfall 4: `_version.py` missing in dev (ImportError)

**What goes wrong:** The `ImportError` fallback in `version.py` (`GIT_SHA = "dev"`) must be present or the app crashes when running `uv run uvicorn ...` outside Docker.

**Why it happens:** `_version.py` is generated at Docker build time, not committed to the repo.

**How to avoid:** The `try/except ImportError` fallback (shown in the code example above) is mandatory. Add `src/gruvax/_version.py` to `.gitignore`. Also provide `just build-version` recipe for local use:

```bash
# justfile addition
build-version:
    python3 -c "
import pathlib, subprocess, datetime
sha = subprocess.check_output(['git','rev-parse','--short','HEAD']).decode().strip()
ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
pathlib.Path('src/gruvax/_version.py').write_text(
    f'GIT_SHA = \"{sha}\"\nBUILD_TIMESTAMP = \"{ts}\"\nENVIRONMENT = \"development\"\n'
)
"
```

**Warning signs:** `AttributeError: module 'gruvax._version' has no attribute 'GIT_SHA'` in local dev.

### Pitfall 5: pytest-benchmark in CI needs `--benchmark-disable` for normal test runs

**What goes wrong:** `pytest-benchmark` by default runs benchmarks as part of the test suite, slowing down every `pytest` invocation. CI runs `pytest tests/ -q` and benchmarks inflate the runtime.

**Why it happens:** Benchmark tests run normally unless the `--benchmark-disable` or `--benchmark-only` flags are passed.

**How to avoid:** Add `--benchmark-disable` to `addopts` in `pyproject.toml` (for all normal `just test` runs), and run benchmarks separately in CI with `--benchmark-only`:

```toml
# pyproject.toml
[tool.pytest.ini_options]
addopts = "-q --tb=short --benchmark-disable"
```

**Warning signs:** `just test` takes 30+ seconds instead of the usual ~10 seconds.

### Pitfall 6 (Pitfall 14 carry-forward): Fresh-host volume permissions

Already documented in `.planning/research/PITFALLS.md` Pitfall 14. For Phase 8 the action is documentation + verification:

- GRUVAX container user is `gruvax` (non-root) — confirmed in `Dockerfile`.
- `mosquitto-data` and `mosquitto-log` are named volumes; Mosquitto image handles its own uid internally.
- No writable bind mounts to host directories in `compose.yaml` for the runtime container.
- Runbook addition: "On fresh host, `docker compose up` succeeds first time. No `chown` required for named volumes."

---

## Code Examples

### `just demo` smoke script pattern

```bash
# justfile — new recipe
# Source: project patterns + SC5 requirement
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== GRUVAX Core Value smoke test ==="
    docker compose up --build -d
    echo "Waiting for api to be healthy..."
    until curl -sf http://localhost:8000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['status']=='ok' else 1)"; do
        sleep 2
    done

    # Confirm search SLO: use a known synth artist
    RESULT=$(curl -sf "http://localhost:8000/api/search?q=Miles+Davis&limit=1")
    TOOK_MS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['took_ms'])")
    echo "Search took: ${TOOK_MS}ms"
    python3 -c "
ms = float('$TOOK_MS')
assert ms < 200, f'Search SLO FAILED: {ms:.1f}ms > 200ms'
print(f'Search SLO: PASS ({ms:.1f}ms)')
"
    # Confirm locate SLO: use the first release_id from the search result
    RELEASE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['release_id'])")
    LOC_RESULT=$(curl -sf "http://localhost:8000/api/locate?release_id=${RELEASE_ID}")
    echo "Locate result: $(echo $LOC_RESULT | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d[\"primary_cube\"])')"
    echo "=== PASS ==="
```

### Migration 0008 skeleton

```python
# Source: migration 0007 pattern + research findings
# Location: migrations/versions/0008_record_stats.py
revision: str = "0008"
down_revision: str | None = "0007"

_CREATE_TABLE = """
CREATE TABLE gruvax.record_stats (
    release_id          BIGINT        PRIMARY KEY,
    search_count        BIGINT        NOT NULL DEFAULT 0,
    search_count_7d     BIGINT        NOT NULL DEFAULT 0,
    selection_count     BIGINT        NOT NULL DEFAULT 0,
    selection_count_7d  BIGINT        NOT NULL DEFAULT 0,
    last_searched_at    TIMESTAMPTZ,
    last_selected_at    TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
)
"""
_CREATE_IDX = "CREATE INDEX ix_record_stats_search_count ON gruvax.record_stats (search_count DESC)"
_DROP_TABLE = "DROP TABLE IF EXISTS gruvax.record_stats"
_DROP_IDX   = "DROP INDEX IF EXISTS ix_record_stats_search_count"

def upgrade() -> None:
    op.execute(_CREATE_TABLE)
    op.execute(_CREATE_IDX)

def downgrade() -> None:
    op.execute(_DROP_IDX)
    op.execute(_DROP_TABLE)
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `logging.basicConfig()` default (dict output) | `JsonFormatter` emitting `json.dumps(...)` per record | Structured logs parseable by log aggregators; no new dep |
| Hardcoded `"0.1.0"` in health.py | Git SHA from `_version.py` | Each image tagged to an exact commit |
| No CI | GitHub Actions `ci.yml` with Postgres service container | Alembic round-trip + benchmark gate on every push |
| No `logging:` in compose.yaml | `logging: driver: json-file, max-size: 10m, max-file: 3` | Prevents disk exhaustion on lux |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CI benchmark gate: `tests/integration/test_search_benchmark.py` is a new file that uses `httpx.AsyncClient` against the live ASGI app | CI design section | If the existing benchmark approach (pure in-memory, no HTTP) is preferred for CI, the task shape changes; search SLO gate might not cover HTTP overhead |
| A2 | Rolling 7-day buckets (`search_count_7d` UPSERT reset approach) is acceptable vs. a timestamped-events table | Counter table design | Events table is more accurate and flexible; rolling bucket is an approximation. If the owner wants exact 7-day counts, an events table (with a nightly trim job or TTL approach) is needed |
| A3 | Compose log limits `max-size: 10m, max-file: 3` (30 MB/service) fit lux's disk headroom | DEP-04 | If lux has very limited disk, values may need tuning downward; if it has plenty, can be larger |
| A4 | The frontend build step is NOT gated in the CI workflow (only backend) | CI design | If frontend lint/build should also be CI-gated, the workflow needs a Node.js setup step |
| A5 | Inline instrumentation (in route handlers) preferred over `BaseHTTPMiddleware` for slow-query timing | Pitfall 3 | If the planner prefers centralized middleware (simpler to add endpoints later), the middleware approach is also valid |

---

## Open Questions

1. **7-day counter approach (A2):** Rolling-bucket UPSERT vs. timestamped events table? The bucket approach (recommended) is simpler and fits the footprint constraint; an events table gives exact rolling counts but needs a trim job. Recommend rolling-bucket unless the owner wants historical replay.

2. **Frontend benchmark in CI (A4):** Should `npm run build` + basic lint be included in `ci.yml`? Not required by SC5 (which is backend-only), but avoids broken SPA builds going undetected. Recommend adding as a non-gating step (continue-on-error) initially.

3. **Inline vs. middleware slow-query instrumentation (A5):** Inline in route handlers is zero-overhead and already has `took_ms` from `search_collection()`. Middleware is more extensible but adds latency. Recommendation: inline for this phase.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.14 | Runtime + CI | ✓ (Docker) | 3.14 (Dockerfile) | — |
| psycopg_pool | Pool stats | ✓ | 3.3.1 (installed) | — |
| pytest-benchmark | SLO gate | ✓ | 5.2.3 (installed dev dep) | — |
| alembic | Migration 0008 | ✓ | 1.18.4 (installed) | — |
| GitHub Actions | CI | ✓ (repo is GitHub) | — | — |
| postgres:18 (in CI) | Alembic round-trip + integration tests | ✓ | 18 (GitHub Actions services) | — |

**No missing dependencies with no fallback.**

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 + pytest-benchmark 5.2.3 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/ tests/property/ -x -q` |
| Full suite command | `uv run pytest tests/ -q --tb=short` |
| Benchmark command | `uv run pytest tests/unit/test_algorithm.py::test_locate_benchmark --benchmark-only` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| OBS-01 | `/api/health` returns `sync_age_seconds` + git SHA `version` | integration | `pytest tests/integration/test_health.py -x` | ✅ (needs enrichment) |
| OBS-02 | Logs are structured JSON; level respects `LOG_LEVEL` | unit | `pytest tests/unit/test_logging_config.py -x` | ❌ Wave 0 |
| OBS-03 | Alembic upgrade→downgrade→upgrade round-trips clean | integration (CI) | `alembic upgrade head && alembic downgrade base && alembic upgrade head` | ✅ `just migrate-roundtrip` |
| OBS-04 | `/api/version` returns `git_sha`, `build_timestamp`, `environment` | integration | `pytest tests/integration/test_version.py -x` | ❌ Wave 0 |
| OBS-05 | Slow queries >SLO appear in ring buffer | unit | `pytest tests/unit/test_timing.py -x` | ❌ Wave 0 |
| OBS-06 | Diagnostics endpoint returns `sync_age_seconds` > 0 | integration | `pytest tests/integration/test_diagnostics.py::test_staleness -x` | ❌ Wave 0 |
| OBS-07 | Counter increments after search/locate; top-N appears in diagnostics | integration | `pytest tests/integration/test_diagnostics.py::test_counters -x` | ❌ Wave 0 |
| DEP-04 | compose.yaml declares `logging:` for api + mosquitto | manual-only | `grep -q 'max-size' compose.yaml` | N/A |
| DEP-05 | All services have `healthcheck:` + `restart: unless-stopped` | manual-only | `grep -c 'restart: unless-stopped' compose.yaml` (expect 3) | N/A |
| SC5 locate | `/api/locate` p95 ≤ 50 ms (CPU-only, synthetic data) | benchmark | `pytest tests/unit/test_algorithm.py::test_locate_benchmark --benchmark-only` | ✅ |
| SC5 search | `/api/search` p95 ≤ 200 ms (synthetic data, live ASGI) | benchmark | `pytest tests/integration/test_search_benchmark.py --benchmark-only` | ❌ Wave 0 |
| Kiosk banner | Banner renders when `sync_age_seconds > 1_209_600` | unit (frontend logic) | React component test or Cypress E2E | ❌ Wave 0 (or manual) |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/unit/ tests/property/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q --tb=short`
- **Phase gate:** Full suite green + benchmark SLO pass before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_logging_config.py` — covers OBS-02 (JsonFormatter + LogRingHandler)
- [ ] `tests/integration/test_version.py` — covers OBS-04
- [ ] `tests/unit/test_timing.py` — covers OBS-05 (ring buffer append logic)
- [ ] `tests/integration/test_diagnostics.py` — covers OBS-06 + OBS-07
- [ ] `tests/integration/test_search_benchmark.py` — covers SC5 search SLO
- [ ] `src/gruvax/_version.py` stub — created by `just build-version` or hardcoded for tests
- [ ] `pyproject.toml` update — add `--benchmark-disable` to `addopts`

---

## Security Domain

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes (diagnostics endpoint) | Phase 3 `require_admin` dependency (session + CSRF) — reused unchanged |
| V3 Session Management | Yes (diagnostics + reset-stats) | Phase 3 signed cookie + sliding window — unchanged |
| V4 Access Control | Yes (reset-stats is destructive) | `require_admin` dependency + CSRF double-submit |
| V5 Input Validation | Minimal (diagnostics is read-only; reset-stats has no body) | No user input to validate in diagnostics |
| V6 Cryptography | No new cryptographic operations | — |

**Threat specific to this phase:**

- **Diagnostic data exposure:** `/api/admin/diagnostics` exposes internal data (pool stats, log lines, query timings). Already admin-gated behind Phase 3 session + CSRF. No additional threat surface.
- **Reset-stats CSRF:** The `POST /api/admin/diagnostics/reset-stats` is a destructive write. It MUST pass the CSRF double-submit check (`require_admin` dependency handles this for all POST methods). The UI-SPEC confirms no re-PIN is needed (session already authenticated); the confirmation step in the frontend is the UX gate, not a second auth factor.
- **Log ring buffer content:** Log lines may contain path parameters, search queries, or error details. The ring buffer is only accessible to admin-authenticated users via the diagnostics endpoint. Raw query text must NOT appear in log lines — the existing codebase logs query results (row counts, timing) not the query string itself. This is verified by reading `search.py` and `queries.py`.

---

## Sources

### Primary (HIGH confidence — verified by codebase read)

- `src/gruvax/api/health.py` — confirmed current fields, hardcoded `"0.1.0"` version
- `src/gruvax/settings.py` — confirmed `LOG_LEVEL` present
- `src/gruvax/app.py` — confirmed lifespan pattern, `app.state` attributes, `background_tasks` set
- `src/gruvax/db/queries.py` — confirmed `took_ms` return from `search_collection()`, `cube_exact_match()` pattern, all SQL uses `%s`
- `src/gruvax/db/pool.py` — confirmed `_configure_connection` sets `search_path`, `create_pool(min_size=2, max_size=10)`
- `migrations/versions/0002_v_collection_view.py` — confirmed `synced_at` column exists (`ci.updated_at AS synced_at`)
- `compose.yaml` — confirmed healthchecks + `restart: unless-stopped` on all three services; no `logging:` key yet
- `pyproject.toml` — confirmed `pytest-benchmark>=5.2.3` in dev deps; `pytest-asyncio>=1.3.0`; Python `>=3.14`
- `Dockerfile` — confirmed Python 3.14-slim runtime, non-root `gruvax` user, `ARG` pattern available
- `justfile` — confirmed `migrate-roundtrip` recipe already exists
- `tests/unit/test_algorithm.py` lines 657–690 — confirmed `test_locate_benchmark` uses `benchmark.stats["mean"] * 1000 < 50`

### Primary (HIGH confidence — verified by tool introspection)

- `psycopg_pool.AsyncConnectionPool.get_stats()` — `uv run python` confirms keys: `pool_size`, `pool_available`, `pool_min`, `pool_max`, `requests_waiting`
- `psycopg_pool` version 3.3.1, `psycopg` version 3.3.4 — confirmed installed
- `pytest-benchmark` version 5.2.3 — confirmed installed

### Secondary (MEDIUM confidence — verified via gh api)

- discogsography `.github/workflows/code-quality.yml` — `astral-sh/setup-uv@v8`, `actions/setup-python@v5`, `ubuntu-latest`, `PYTHON_VERSION: "3.13"` — CI pattern reference
- discogsography `.github/actions/setup-python-uv/action.yml` — composite action pattern

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages verified as installed; no new deps
- Architecture: HIGH — based on direct codebase reads; patterns confirmed
- Pitfalls: HIGH — derived from direct code analysis + existing PITFALLS.md
- CI design: MEDIUM — discogsography pattern referenced but GRUVAX CI is greenfield

**Research date:** 2026-05-24
**Valid until:** 2026-06-24 (stable stack; 30-day window)

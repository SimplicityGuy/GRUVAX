# Phase 8: Observability + Deployment Hardening — Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 18 new/modified files
**Analogs found:** 17 / 18 (GitHub Actions CI is greenfield with external analog only)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/gruvax/api/health.py` | controller | request-response | itself (enrich) | exact |
| `src/gruvax/api/version.py` | controller | request-response | `src/gruvax/api/health.py` | exact |
| `src/gruvax/api/admin/diagnostics.py` | controller | request-response | `src/gruvax/api/admin/leds.py` | exact |
| `src/gruvax/api/admin/router.py` | route | request-response | itself (enrich) | exact |
| `src/gruvax/logging_config.py` | utility | transform | `src/gruvax/settings.py` (pattern; no direct analog) | partial |
| `src/gruvax/middleware/timing.py` | middleware | request-response | `src/gruvax/app.py` (lifespan/middleware wiring) | role-match |
| `src/gruvax/_version.py` | config | transform | `Dockerfile` ARG pattern | partial |
| `src/gruvax/app.py` | config | event-driven | itself (enrich) | exact |
| `src/gruvax/settings.py` | config | request-response | itself (enrich) | exact |
| `src/gruvax/db/queries.py` | utility | CRUD | itself (enrich) | exact |
| `migrations/versions/0008_record_stats.py` | migration | CRUD | `migrations/versions/0007_wizard_source_labels.py` | exact |
| `frontend/src/routes/admin/Diagnostics.tsx` | component | request-response | `frontend/src/routes/admin/Settings.tsx` | exact |
| `frontend/src/routes/admin/Diagnostics.css` | config | transform | `frontend/src/routes/admin/admin.css` (existing) | role-match |
| `frontend/src/routes/admin/AdminShell.tsx` | component | request-response | itself (enrich) | exact |
| `frontend/src/api/adminClient.ts` | utility | request-response | itself (enrich) | exact |
| `frontend/src/routes/kiosk/StalenessBar.tsx` | component | request-response | `frontend/src/routes/admin/ReshuffleBanner.tsx` | role-match |
| `compose.yaml` | config | transform | itself (enrich) | exact |
| `Dockerfile` | config | transform | itself (enrich) | exact |
| `.github/workflows/ci.yml` | config | batch | discogsography `code-quality.yml` (external) | external-analog |
| `justfile` | utility | batch | itself (enrich) | exact |
| `tests/unit/test_logging_config.py` | test | request-response | `tests/unit/test_algorithm.py` | role-match |
| `tests/unit/test_timing.py` | test | request-response | `tests/unit/test_algorithm.py` | role-match |
| `tests/integration/test_version.py` | test | request-response | `tests/integration/test_health.py` | exact |
| `tests/integration/test_diagnostics.py` | test | request-response | `tests/integration/test_health.py` | exact |
| `tests/integration/test_search_benchmark.py` | test | batch | `tests/unit/test_algorithm.py` lines 657–690 | role-match |
| `scripts/check_benchmark.py` | utility | batch | `tests/unit/test_algorithm.py` (benchmark assertion logic) | partial |

---

## Pattern Assignments

### `src/gruvax/api/health.py` (controller — enrich existing)

**Analog:** itself — enrich, do not replace.

**Current imports** (lines 1–21):
```python
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])
```

**Current `app.state` read pattern** (lines 37–41):
```python
db_ok: bool = getattr(request.app.state, "db_ok", False)
view_ok: bool = getattr(request.app.state, "discogsography_view_ok", False)
mqtt_ok: bool = getattr(request.app.state, "mqtt_ok", False)
started_at: datetime = getattr(request.app.state, "started_at", datetime.now(UTC))
```

**Current response body** (lines 47–54 — two fields to replace/add):
```python
body: dict[str, Any] = {
    "status": overall,
    "db": db_status,
    "discogsography_view_check": view_status,
    "mqtt": mqtt_status,
    "version": "0.1.0",          # ← replace with GIT_SHA from _version.py
    "started_at": started_at.isoformat(),
    # ADD: "sync_age_seconds": getattr(request.app.state, "sync_age_seconds", None)
}
```

**Changes required:**
- Import `GIT_SHA` from `gruvax._version` (with `try/except ImportError` fallback).
- Replace hardcoded `"0.1.0"` with `GIT_SHA`.
- Add `"sync_age_seconds": getattr(request.app.state, "sync_age_seconds", None)` to body.
- `sync_age_seconds` is written to `app.state` by a background refresh task in `app.py` lifespan.

---

### `src/gruvax/api/version.py` (controller, request-response — new file)

**Analog:** `src/gruvax/api/health.py`

**Imports pattern** (copy from health.py, trim to what's needed):
```python
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

try:
    from gruvax._version import BUILD_TIMESTAMP, ENVIRONMENT, GIT_SHA
except ImportError:
    GIT_SHA = "dev"
    BUILD_TIMESTAMP = "unknown"
    ENVIRONMENT = "development"

router = APIRouter(tags=["version"])
```

**Core handler pattern** (modeled on health.py lines 26–56, simplified):
```python
@router.get("/version")
async def get_version() -> JSONResponse:
    """Public endpoint: git SHA, build timestamp, environment."""
    return JSONResponse({
        "git_sha": GIT_SHA,
        "build_timestamp": BUILD_TIMESTAMP,
        "environment": ENVIRONMENT,
    })
```

**Router registration** (copy from `app.py` lines 247–257 pattern):
```python
# In create_app() in app.py, BEFORE StaticFiles mount:
from gruvax.api.version import router as version_router
app.include_router(version_router, prefix="/api")
```

---

### `src/gruvax/api/admin/diagnostics.py` (controller, request-response — new file)

**Analog:** `src/gruvax/api/admin/leds.py`

**Imports pattern** (lines 1–31 of leds.py — adapt for diagnostics):
```python
from __future__ import annotations

import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, Request
from psycopg_pool import AsyncConnectionPool

from gruvax.api.deps import get_pool, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-diagnostics"])
```

**Admin-gated GET pattern** (leds.py lines 37–58, simplified to read-only GET):
```python
@router.get("/diagnostics")
async def get_diagnostics(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Return all diagnostics data (staleness, counters, ring buffers, pool/phantom stats)."""
    # Read from app.state — same pattern as leds.py reading mqtt client
    slow_ring: deque = getattr(request.app.state, "slow_query_ring", deque())
    log_ring: deque = getattr(request.app.state, "log_ring_buffer", deque())
    db_pool: AsyncConnectionPool = request.app.state.db_pool
    ...
```

**Admin-gated POST (destructive) pattern** (leds.py lines 61–97, run_id → reset):
```python
@router.post("/diagnostics/reset-stats")
async def reset_stats(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Truncate gruvax.record_stats (PIN-gated, CSRF-checked via require_admin)."""
    async with pool.connection() as conn:
        await conn.execute("TRUNCATE gruvax.record_stats")
    logger.info("record_stats truncated by admin")
    return {"reset": True}
```

**`app.state` read with getattr fallback** (leds.py lines 54–55):
```python
client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
settings_cache: dict[str, Any] = getattr(request.app.state, "settings_cache", {})
# → same pattern for slow_ring, log_ring, sync_age_seconds
```

---

### `src/gruvax/api/admin/router.py` (route — enrich existing)

**Analog:** itself.

**Current import-and-register pattern** (lines 14–46):
```python
def create_admin_router() -> APIRouter:
    from gruvax.api.admin.cubes import router as cubes_router
    from gruvax.api.admin.leds import router as leds_router
    # ... other imports ...

    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(leds_router)
    # ... other include_router calls ...
    return router
```

**Change required:** Add inside `create_admin_router()`:
```python
from gruvax.api.admin.diagnostics import router as diagnostics_router
router.include_router(diagnostics_router)
```
Add after the existing `include_router(import_router)` line (line 44), before `return router`.

---

### `src/gruvax/logging_config.py` (utility, transform — new file)

**Analog:** No direct file analog. Pattern is stdlib `logging.Formatter` subclass. The `settings.py` `LOG_LEVEL` field (line 49) shows the log-level integration point.

**`LOG_LEVEL` settings pattern** (settings.py lines 48–49):
```python
# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"
```

**`logger = logging.getLogger(__name__)` pattern** — used in every module (health.py line 21, leds.py line 32, app.py line 40). The new `logging_config.py` provides the formatter and ring handler used by all of them.

**Core implementation pattern** (from RESEARCH.md Open Question 2 — verified stdlib):
```python
import json
import logging
import time
from collections import deque
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class LogRingHandler(logging.Handler):
    """Append formatted records to a deque (D-12). Stored on app.state.log_ring_buffer."""

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

---

### `src/gruvax/middleware/timing.py` (middleware, request-response — new file)

**Analog:** `src/gruvax/app.py` (middleware wiring pattern at lines 260–267 shows `app.add_middleware()`).

**Middleware wiring pattern** (app.py lines 253–267, analogous middleware add call):
```python
# In create_app(), BEFORE routers and BEFORE StaticFiles:
from gruvax.middleware.timing import SlowQueryMiddleware
app.add_middleware(SlowQueryMiddleware)
```

**Ring buffer initialization pattern** (app.py lifespan lines 81–86 — same pattern for slow_query_ring):
```python
# In lifespan() startup, after pool open:
from collections import deque
app.state.slow_query_ring = deque(maxlen=50)   # D-08: last 50 slow entries
```

**Core middleware pattern** (from RESEARCH.md Open Question 5, Starlette BaseHTTPMiddleware):
```python
import time
from collections import deque
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

SLO_THRESHOLDS_MS: dict[str, float] = {
    "/api/search": 200.0,
    "/api/locate": 50.0,
}


class SlowQueryMiddleware(BaseHTTPMiddleware):
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

**Note:** RESEARCH.md Pitfall 3 documents that BaseHTTPMiddleware adds ~0.5–1 ms overhead. The planner should decide between inline instrumentation (zero overhead, `took_ms` already returned by `search_collection`) or centralized middleware. Both are valid; inline is recommended for the `/api/locate` path with its 50 ms SLO.

---

### `src/gruvax/_version.py` (config — generated at build time, new file)

**Analog:** `Dockerfile` — the ARG/RUN injection pattern (lines 59–66 of Dockerfile stage 2/3).

**Dockerfile ARG injection pattern** (Dockerfile — add to Stage 3 runtime, after COPY from python-builder):
```dockerfile
# In Stage 3 (runtime), BEFORE USER gruvax:
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ARG GRUVAX_ENV=production

RUN python3 -c "
content = '''# Auto-generated at Docker build time. Do not edit.
GIT_SHA = \"${GIT_SHA}\"
BUILD_TIMESTAMP = \"${BUILD_TIMESTAMP}\"
ENVIRONMENT = \"${GRUVAX_ENV}\"
'''
import pathlib
pathlib.Path('/app/src/gruvax/_version.py').write_text(content)
"
```

**Dev fallback content** (the file that ships in the repo as a placeholder — `.gitignore` this):
```python
# Auto-generated at Docker build time. Do not edit.
# Dev placeholder — run `just build-version` to populate from git.
GIT_SHA = "dev"
BUILD_TIMESTAMP = "unknown"
ENVIRONMENT = "development"
```

**Import pattern with fallback** (used in version.py and health.py):
```python
try:
    from gruvax._version import BUILD_TIMESTAMP, ENVIRONMENT, GIT_SHA
except ImportError:
    GIT_SHA = "dev"
    BUILD_TIMESTAMP = "unknown"
    ENVIRONMENT = "development"
```

---

### `src/gruvax/app.py` (config — enrich existing lifespan)

**Analog:** itself.

**Existing lifespan startup pattern** (lines 78–199) — new additions slot into sections 1 and 3e:

**Section 1 addition — configure logging** (insert at top of lifespan, before pool open):
```python
# ── 0. Structured-JSON logging + log ring buffer (OBS-02, D-12) ─────────────
from collections import deque
from gruvax.logging_config import JsonFormatter, LogRingHandler
import logging as _logging

_log_level = getattr(_logging, settings.LOG_LEVEL.upper(), _logging.INFO)
_root = _logging.getLogger()
_root.setLevel(_log_level)
_json_handler = _logging.StreamHandler()
_json_handler.setFormatter(JsonFormatter())
_root.handlers = [_json_handler]  # replace default handlers

_log_ring: deque = deque(maxlen=200)
app.state.log_ring_buffer = _log_ring
_root.addHandler(LogRingHandler(_log_ring, level=_logging.DEBUG))
```

**Existing CR-01 background_tasks set pattern** (lines 180–194) — reuse for counter tasks:
```python
app.state.background_tasks = set()

# CR-01: strong reference pattern for fire-and-forget tasks
task = asyncio.create_task(some_async_fn())
app.state.background_tasks.add(task)
task.add_done_callback(app.state.background_tasks.discard)
```

**Slow-query ring buffer initialization** (insert after pool open):
```python
app.state.slow_query_ring = deque(maxlen=50)   # D-08: in-memory, resets on restart
```

**Sync-staleness background refresh** (insert as a periodic asyncio task in lifespan):
```python
# ── 1b. Sync-staleness background refresh (OBS-06) ─────────────────────────
async def _refresh_sync_age() -> None:
    """Update app.state.sync_age_seconds every 60s. Never blocks a request."""
    while True:
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT EXTRACT(EPOCH FROM (now() - max(synced_at))) FROM gruvax.v_collection"
                )
                row = await cur.fetchone()
            app.state.sync_age_seconds = float(row[0]) if (row and row[0] is not None) else None
        except Exception as exc:
            logger.warning("sync_age refresh failed: %s", exc)
            app.state.sync_age_seconds = None
        await asyncio.sleep(60)

_age_task = asyncio.create_task(_refresh_sync_age())
app.state.background_tasks.add(_age_task)
_age_task.add_done_callback(app.state.background_tasks.discard)
```

**Middleware registration in create_app()** (after `app = FastAPI(...)`, before routers):
```python
from gruvax.middleware.timing import SlowQueryMiddleware
app.add_middleware(SlowQueryMiddleware)
```

---

### `src/gruvax/settings.py` (config — verify only, no change expected)

**Analog:** itself.

**Current `LOG_LEVEL` field** (lines 48–49):
```python
# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"
```

No new Settings fields are needed for Phase 8. `GRUVAX_ENV` is baked into `_version.py` at build time. `LOG_LEVEL` already exists and is read in `app.py` lifespan. The `compose.yaml` already passes `LOG_LEVEL: "${LOG_LEVEL:-info}"`.

---

### `src/gruvax/db/queries.py` (utility — enrich, CRUD pattern)

**Analog:** itself — add three new async functions following the existing function structure.

**Core query function pattern** (lines 62–110 — `did_you_mean_query` structure):
```python
async def get_sync_staleness_seconds(
    pool: AsyncConnectionPool,
) -> float | None:
    """Return seconds since last discogsography sync, or None if v_collection is empty.

    Reads gruvax.v_collection exclusively (Pitfall 5).
    All SQL uses %s placeholders (T-01-07).
    """
    sql = "SELECT EXTRACT(EPOCH FROM (now() - max(synced_at))) FROM gruvax.v_collection"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        row = await cur.fetchone()
    if row is None or row[0] is None:
        return None
    return float(row[0])
```

**UPSERT search counter pattern** (modeled on `store_idempotency` lines 707–730 + psycopg %s style):
```python
async def increment_search_count(
    pool: AsyncConnectionPool,
    release_id: int,
) -> None:
    """Fire-and-forget: upsert search_count for top result (D-04, D-06).
    Uses rolling 7-day bucket approach (D-05). No query text stored (OBS-07).
    """
    sql = """
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
"""
    async with pool.connection() as conn:
        await conn.execute(sql, (release_id,))
```

**Phantom-boundary count pattern** (modeled on `cube_exact_match` lines 868–899):
```python
async def get_phantom_boundary_count(
    pool: AsyncConnectionPool,
) -> int:
    """Count boundaries whose (first_label, first_catalog) is not in v_collection.

    Reads only v_collection (Pitfall 5). All SQL uses %s placeholders.
    cube_boundaries has ≤ 32 rows — effectively free.
    """
    sql = """
SELECT COUNT(*)
FROM gruvax.cube_boundaries cb
WHERE cb.is_empty = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM gruvax.v_collection v
      WHERE lower(v.label) = lower(cb.first_label)
        AND v.catalog_number = cb.first_catalog
  )
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        row = await cur.fetchone()
    return int(row[0]) if row else 0
```

**Top-N most-searched pattern** (modeled on `list_change_sets` lines 750–787):
```python
async def get_top_searched(
    pool: AsyncConnectionPool,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Return top-N records by all-time search count (D-05).

    Joins record_stats with v_collection for display fields.
    All SQL uses %s placeholders (T-01-07).
    """
    sql = """
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
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (limit,))
        rows_raw = await cur.fetchall()
        cols = [desc[0] for desc in (cur.description or [])]
    return [dict(zip(cols, row, strict=True)) for row in rows_raw]
```

---

### `migrations/versions/0008_record_stats.py` (migration — new file)

**Analog:** `migrations/versions/0007_wizard_source_labels.py` (structural pattern) and `migrations/versions/0002_v_collection_view.py` (CREATE TABLE style).

**Header and revision chain pattern** (0007 lines 1–28):
```python
"""Create gruvax.record_stats — durable search/selection counters (D-04/D-05/D-06).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-24

Phase 8: Adds the record_stats table for OBS-07 (most-searched diagnostics).
Counters are release_id-keyed aggregates; no query text is ever stored.

Conventions (carried from 0001-0007):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() fully reverses upgrade().
- alembic_version in public; search_path via connect listener (env.py).
"""

from __future__ import annotations

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None
```

**DDL string + op.execute() pattern** (0007 lines 30–61):
```python
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
_CREATE_IDX = (
    "CREATE INDEX ix_record_stats_search_count "
    "ON gruvax.record_stats (search_count DESC)"
)
_DROP_TABLE = "DROP TABLE IF EXISTS gruvax.record_stats"
_DROP_IDX   = "DROP INDEX IF EXISTS gruvax.ix_record_stats_search_count"


def upgrade() -> None:
    op.execute(_CREATE_TABLE)
    op.execute(_CREATE_IDX)


def downgrade() -> None:
    op.execute(_DROP_IDX)
    op.execute(_DROP_TABLE)
```

---

### `frontend/src/routes/admin/Diagnostics.tsx` (component, request-response — new file)

**Analog:** `frontend/src/routes/admin/Settings.tsx`

**Imports pattern** (Settings.tsx lines 1–24):
```tsx
import { useEffect, useState } from 'react'
import { getDiagnostics, resetStats } from '../../api/adminClient'
import './admin.css'
// Note: Diagnostics.tsx imports its own scoped CSS too:
import './Diagnostics.css'
```

**State management pattern** (Settings.tsx lines 26–68 — declare state per logical section):
```tsx
type LoadStatus = 'idle' | 'loading' | 'loaded' | 'error'
type ResetState = 'idle' | 'confirm' | 'resetting' | 'success' | 'error'

export function DiagnosticsPage() {
  const [loadStatus, setLoadStatus] = useState<LoadStatus>('idle')
  const [diagnostics, setDiagnostics] = useState<DiagnosticsData | null>(null)
  const [loadError, setLoadError] = useState('')
  const [resetState, setResetState] = useState<ResetState>('idle')
  const [resetError, setResetError] = useState('')
  const [lastRefreshedAt, setLastRefreshedAt] = useState<Date | null>(null)
  ...
```

**Data-on-mount + explicit refresh pattern** (Settings.tsx lines 71–91 — useEffect + fetch):
```tsx
// D-11: data loads on mount + explicit Refresh. No polling, no SSE.
useEffect(() => {
  void load()
}, [])

const load = async () => {
  setLoadStatus('loading')
  setLoadError('')
  try {
    const data = await getDiagnostics()
    setDiagnostics(data)
    setLastRefreshedAt(new Date())
    setLoadStatus('loaded')
  } catch {
    setLoadStatus('error')
    setLoadError('Could not load diagnostics. Check that the API is reachable.')
  }
}
```

**Inline destructive confirm pattern** (Settings.tsx lines 127–148 — inline state swap, no modal):
```tsx
// Mirrors the PIN-change inline-validation pattern in Settings.tsx.
// "RESET STATS" → "CONFIRM RESET?" + "YES, RESET" / "KEEP STATS"
const handleReset = async () => {
  if (resetState === 'idle') {
    setResetState('confirm')
    return
  }
}
const handleResetConfirm = async () => {
  setResetState('resetting')
  setResetError('')
  try {
    await resetStats()
    setResetState('success')
    setTimeout(() => { setResetState('idle'); void load() }, 3000)
  } catch {
    setResetState('error')
    setResetError('Could not reset stats. Try again.')
    setResetState('idle')
  }
}
```

**Section card markup pattern** (Settings.tsx lines 232–288 — `settings-section` + `settings-heading`):
```tsx
return (
  <div className="settings-page">
    {/* ── DiagnosticsToolbar ───────────────────────────────────────────── */}
    <div className="diag-toolbar">
      <button
        type="button"
        className="settings-btn-primary"
        aria-label="Refresh diagnostics"
        onClick={() => { void load() }}
        disabled={loadStatus === 'loading'}
      >
        {loadStatus === 'loading' ? 'REFRESHING…' : 'REFRESH'}
      </button>
      {lastRefreshedAt && (
        <span className="settings-hint">Last refreshed: {formatRelativeTime(lastRefreshedAt)}</span>
      )}
    </div>

    {/* ── StalenessSection ─────────────────────────────────────────────── */}
    <section className="settings-section" aria-labelledby="diag-staleness-heading">
      <h2 id="diag-staleness-heading" className="settings-heading">SYNC STATUS</h2>
      {/* ... single staleness row ... */}
    </section>

    {/* ... TopSearchedSection, SlowQuerySection, SystemStatusSection, RecentLogsSection ... */}
  </div>
)
```

**Error state pattern** (Settings.tsx lines 272–274 and 334–337):
```tsx
{loadError && (
  <p className="settings-error" role="alert">{loadError}</p>
)}
{settingsStatus === 'saved' && (
  <p className="settings-success" role="status">Settings saved.</p>
)}
```

---

### `frontend/src/routes/admin/AdminShell.tsx` (component — enrich, add nav tab)

**Analog:** itself.

**Existing NavLink pattern** (lines 159–198 — copy and append):
```tsx
<NavLink
  to="/admin/diagnostics"
  className={({ isActive }) =>
    `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
  }
>
  DIAGNOSTICS
</NavLink>
```

Insert after the existing IMPORT NavLink (after line 194). Position: `SETTINGS → CUBES → HISTORY → WIZARD → IMPORT → DIAGNOSTICS`.

---

### `frontend/src/api/adminClient.ts` (utility — enrich, add two functions)

**Analog:** itself.

**GET fetch pattern** (lines 136–143 — `getAdminSettings`):
```ts
/** GET /api/admin/diagnostics — admin-gated diagnostics data. */
export async function getDiagnostics(): Promise<DiagnosticsData> {
  const res = await adminFetch('/api/admin/diagnostics')
  if (!res.ok) {
    throw new Error(`Diagnostics fetch failed: ${res.status}`)
  }
  return res.json() as Promise<DiagnosticsData>
}
```

**POST with CSRF pattern** (lines 556–561 — `ledsAllOff`):
```ts
/** POST /api/admin/diagnostics/reset-stats — PIN-gated, CSRF-checked via adminFetch. */
export async function resetStats(): Promise<{ reset: boolean }> {
  const res = await adminFetch('/api/admin/diagnostics/reset-stats', { method: 'POST' })
  if (!res.ok) {
    throw new Error(`Reset stats failed: ${res.status}`)
  }
  return res.json() as Promise<{ reset: boolean }>
}
```

Note: `adminFetch` automatically attaches `X-CSRF-Token` for POST requests (lines 63–76).

---

### `frontend/src/routes/kiosk/StalenessBar.tsx` (component, request-response — new file)

**Analog:** `frontend/src/routes/admin/ReshuffleBanner.tsx` (persistent banner pattern, conditional render).

**Conditional render + token-only CSS pattern** (ReshuffleBanner.tsx lines 39–115):
```tsx
/**
 * StalenessBar — kiosk persistent banner when sync_age > 14d (D-01/D-02).
 *
 * Reads sync_age_seconds from the /api/health response (passed as prop).
 * Hidden when offline (offline banner takes precedence) or condition is false.
 * Not dismissible — this is an operational signal, not a notification.
 */

const STALE_THRESHOLD_SECONDS = 14 * 24 * 60 * 60  // 14 days = 1_209_600s (D-01)

interface Props {
  syncAgeSeconds: number | null
}

export function StalenessBar({ syncAgeSeconds }: Props) {
  // Never render if age is unknown (health endpoint unavailable → offline banner leads)
  if (syncAgeSeconds === null || syncAgeSeconds < STALE_THRESHOLD_SECONDS) {
    return null
  }

  const days = Math.floor(syncAgeSeconds / 86400)

  return (
    <div
      className="staleness-bar"
      role="alert"      // fires once on mount (aria-live="polite" for subsequent renders)
      aria-live="polite"
    >
      {/* Inline SVG AlertTriangle (Lucide pattern from Settings.tsx lines 585-601) */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18" height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        <line x1="12" y1="9" x2="12" y2="13"/>
        <line x1="12" y1="17" x2="12.01" y2="17"/>
      </svg>
      {/* UI-SPEC §Banner copy — sentence case, plain language, no jargon */}
      {`Collection data may be outdated — last synced ${days}d ago`}
    </div>
  )
}
```

**CSS token pattern** (no hardcoded hex — token names from UI-SPEC §Color):
```css
/* Diagnostics.css — staleness bar */
.staleness-bar {
  background: var(--gruvax-yellow);
  color: var(--gruvax-blue-darker);  /* #002855 — 3.1:1 on yellow at 18px */
  font-family: var(--gruvax-font-body);
  font-size: 18px;  /* UI-SPEC: accessibility floor for yellow-on-dark contrast */
  font-weight: 400;
  padding: var(--gruvax-space-3) var(--gruvax-space-4);
  display: flex;
  align-items: center;
  gap: var(--gruvax-space-2);
  width: 100%;
  border-radius: 0;
}
```

**KioskView integration point** (KioskView.tsx lines 53–65 — useQuery data pattern):
```tsx
// Add a health query to KioskView to drive the staleness banner:
const { data: healthData } = useQuery({
  queryKey: ['health'],
  queryFn: () => fetch('/api/health').then(r => r.json()),
  staleTime: 60_000,           // re-fetch health every 60s
  refetchInterval: 60_000,     // poll every 60s (banner-only use case, LAN-local)
})

// In JSX, above the ShelfGrid:
<StalenessBar syncAgeSeconds={healthData?.sync_age_seconds ?? null} />
```

---

### `compose.yaml` (config — enrich, add logging limits)

**Analog:** itself — existing healthcheck + restart pattern (lines 80–90).

**Existing healthcheck block pattern** (lines 80–90 — same level as `logging:` block goes):
```yaml
    healthcheck:
      test:
        - "CMD"
        - "python"
        - "-c"
        - "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()"
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 30s
    restart: unless-stopped
```

**Logging limits to add** (DEP-04 — add after `restart: unless-stopped` on `api` and `mosquitto`):
```yaml
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Add the `logging:` block to both `api` (after line 90) and `mosquitto` (after line 143). The `gruvax-dev-pg` service should also get this block for consistency on `lux`.

---

### `Dockerfile` (config — enrich, add ARG injection in Stage 3)

**Analog:** itself.

**Existing non-root USER pattern** (Dockerfile lines 71–104 — Stage 3):
```dockerfile
# Create a non-root user (security baseline for 2026)
RUN groupadd --system gruvax && useradd --system --gid gruvax gruvax

WORKDIR /app

COPY --from=python-builder /app/.venv /app/.venv
COPY --from=python-builder /build/src /app/src
# ... more COPYs ...

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

USER gruvax
```

**ARG injection pattern** (insert BEFORE `USER gruvax`, after `ENV PYTHONPATH`):
```dockerfile
# ── Build-time metadata (OBS-04) ─────────────────────────────────────────────
ARG GIT_SHA=unknown
ARG BUILD_TIMESTAMP=unknown
ARG GRUVAX_ENV=production

# Write _version.py before switching to non-root user (needs write access to /app/src)
RUN python3 -c "\
content = 'GIT_SHA = \"${GIT_SHA}\"\nBUILD_TIMESTAMP = \"${BUILD_TIMESTAMP}\"\nENVIRONMENT = \"${GRUVAX_ENV}\"\n';\
import pathlib; pathlib.Path('/app/src/gruvax/_version.py').write_text(content)\
"
```

**Build invocation in justfile** (existing `build` recipe — enrich):
```bash
# justfile: enrich the build recipe
build:
    docker compose build \
      --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
      --build-arg BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
      --build-arg GRUVAX_ENV=production
```

---

### `.github/workflows/ci.yml` (config — new file, greenfield)

**Analog:** discogsography `.github/workflows/code-quality.yml` (external, MEDIUM confidence). Key signals: `astral-sh/setup-uv@v8`, `actions/setup-python@v5`, `ubuntu-latest`, `uv sync --frozen`, `uv run ruff`, `uv run mypy`.

**Critical delta from discogsography:** GRUVAX needs a `services: postgres:` block for integration tests + Alembic round-trip.

**Pattern from RESEARCH.md Open Question 4** (verified against discogsography workflow):
```yaml
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
      - name: Benchmark SLO gate
        run: |
          uv run pytest tests/unit/test_algorithm.py::test_locate_benchmark \
            tests/integration/test_search_benchmark.py \
            --benchmark-only --benchmark-json=benchmark.json -q
          uv run python scripts/check_benchmark.py benchmark.json
```

---

### `justfile` (utility — enrich, add new recipes)

**Analog:** itself.

**Existing recipe pattern** (lines 5–44):
```makefile
# Round-trip migration check (upgrade → downgrade → upgrade)
migrate-roundtrip:
    uv run alembic upgrade head
    uv run alembic downgrade base
    uv run alembic upgrade head
```

**New recipes to add** (modeled on existing pattern):
```makefile
# Generate _version.py from the current git state (for local dev outside Docker)
build-version:
    uv run python3 -c "\
import pathlib, subprocess, datetime; \
sha = subprocess.check_output(['git','rev-parse','--short','HEAD']).decode().strip(); \
ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'); \
pathlib.Path('src/gruvax/_version.py').write_text(f'GIT_SHA = \"{sha}\"\nBUILD_TIMESTAMP = \"{ts}\"\nENVIRONMENT = \"development\"\n') \
"

# Core Value smoke test: docker compose up → search → locate → assert SLO (SC5)
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== GRUVAX Core Value smoke test ==="
    docker compose up --build -d
    echo "Waiting for api to be healthy..."
    until curl -sf http://localhost:8000/api/health | python3 -c \
      "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['status']=='ok' else 1)"; do
        sleep 2
    done
    RESULT=$(curl -sf "http://localhost:8000/api/search?q=Miles+Davis&limit=1")
    TOOK_MS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['took_ms'])")
    python3 -c "ms=float('$TOOK_MS'); assert ms < 200, f'SLO FAILED: {ms:.1f}ms > 200ms'; print(f'Search SLO: PASS ({ms:.1f}ms)')"
    echo "=== PASS ==="
```

---

### `tests/integration/test_search_benchmark.py` (test — new file)

**Analog:** `tests/unit/test_algorithm.py` lines 657–690 (`test_locate_benchmark`).

**pytest-benchmark async fixture pattern** (test_algorithm.py lines 657–690):
```python
def test_locate_benchmark(benchmark) -> None:  # type: ignore[no-untyped-def]
    """p95 over 100 locate() calls must be < 50 ms (POS-03)."""
    ...
    benchmark(run_all)
    assert benchmark.stats["mean"] * 1000 < 50, (
        f"benchmark mean {benchmark.stats['mean'] * 1000:.2f}ms exceeds 50ms budget"
    )
```

**New integration benchmark pattern** (httpx.AsyncClient against live ASGI, follows same assertion style):
```python
import pytest
from httpx import AsyncClient, ASGITransport

from gruvax.app import create_app


@pytest.mark.benchmark
def test_search_slo_benchmark(benchmark) -> None:
    """p95 /api/search round-trip must be < 200 ms on synthetic data (SC5)."""
    import asyncio

    app = create_app()

    async def run_search() -> float:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/search", params={"q": "Miles Davis", "limit": "5"})
        return resp.json()["took_ms"]

    def sync_run() -> float:
        return asyncio.get_event_loop().run_until_complete(run_search())

    benchmark(sync_run)
    assert benchmark.stats["mean"] * 1000 < 200, (
        f"search SLO FAILED: mean {benchmark.stats['mean'] * 1000:.2f}ms > 200ms"
    )
```

**pyproject.toml addopts update** (Pitfall 5 — add `--benchmark-disable` to normal test runs):
```toml
[tool.pytest.ini_options]
addopts = "-q --tb=short --benchmark-disable"
```

---

## Shared Patterns

### Authentication / CSRF (admin endpoints)
**Source:** `src/gruvax/api/deps.py` via `Depends(require_admin)`
**Apply to:** `diagnostics.py` GET and POST endpoints
```python
# Every admin endpoint:
_admin: dict[str, str] = Depends(require_admin)
```
`require_admin` enforces session cookie + CSRF double-submit. No additional auth logic needed in the endpoint body.

### `app.state` attribute read with fallback
**Source:** `src/gruvax/api/health.py` lines 37–41
**Apply to:** `diagnostics.py`, `health.py` (enriched), `timing.py`
```python
value = getattr(request.app.state, "attribute_name", default_value)
```
Always use `getattr(..., default)` — attributes may not exist if startup partially failed.

### Background task strong-reference (CR-01)
**Source:** `src/gruvax/app.py` lines 180–194
**Apply to:** Any `asyncio.create_task()` call for fire-and-forget counter increments
```python
task = asyncio.create_task(increment_search_count(pool, release_id))
app.state.background_tasks.add(task)
task.add_done_callback(app.state.background_tasks.discard)
# Also add exception logging callback:
def _log_task_exc(t: asyncio.Task) -> None:
    if not t.cancelled() and t.exception():
        logger.warning("Background stats increment failed: %s", t.exception())
task.add_done_callback(_log_task_exc)
```

### psycopg `%s` parameterized SQL
**Source:** `src/gruvax/db/queries.py` — every function
**Apply to:** all new query functions in `queries.py`, all SQL in `diagnostics.py`
```python
# Every SQL statement:
await cur.execute(sql, (param1, param2))  # never f-string user input
```

### `pool.connection()` async context manager
**Source:** `src/gruvax/db/queries.py` lines 95–103
**Apply to:** all new query functions
```python
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(sql, (params,))
    row = await cur.fetchone()
```

### Token-only CSS (no hardcoded hex)
**Source:** `frontend/src/routes/admin/admin.css` (existing), `design/gruvax-design-tokens.css`
**Apply to:** `Diagnostics.css`, kiosk staleness banner CSS
```css
/* Always: */
background: var(--gruvax-yellow);
color: var(--gruvax-blue-darker);
/* Never: */
background: #FFDA00;
```

### `el()` + `replaceChildren()` DOM pattern
**Source:** `frontend/src/lib/dom.ts` (lines 52–123)
**Apply to:** Diagnostics.tsx if any section needs imperative DOM updates (log terminal rendering)
```tsx
import { el } from '../../lib/dom'
// For the dark log terminal section where performance matters:
const container = containerRef.current
container.replaceChildren(
  ...logLines.map(line =>
    el('div', { className: `log-line log-line--${line.level.toLowerCase()}` },
      el('span', { className: 'log-ts', textContent: formatTs(line.ts) }),
      el('span', { textContent: ` ${line.msg}` })
    )
  )
)
```

### `useEffect` on mount + explicit refresh (no polling)
**Source:** `frontend/src/routes/admin/Settings.tsx` lines 71–91
**Apply to:** `Diagnostics.tsx` (D-11 locked — no polling, no SSE for telemetry)
```tsx
useEffect(() => {
  void load()
}, [])   // empty deps = mount only
```

### `adminFetch` CSRF wrapper
**Source:** `frontend/src/api/adminClient.ts` lines 58–85
**Apply to:** `getDiagnostics()` and `resetStats()` additions to `adminClient.ts`
```ts
// GET:
const res = await adminFetch('/api/admin/diagnostics')
// POST (CSRF auto-attached by adminFetch for mutating methods):
const res = await adminFetch('/api/admin/diagnostics/reset-stats', { method: 'POST' })
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `.github/workflows/ci.yml` | config | batch | No `.github/workflows/` exists in GRUVAX yet. External analog: discogsography `code-quality.yml` (MEDIUM confidence). The Postgres `services:` block has no codebase precedent. |

---

## Metadata

**Analog search scope:** `src/gruvax/`, `frontend/src/`, `migrations/versions/`, `compose.yaml`, `Dockerfile`, `justfile`, `tests/`
**Files scanned:** 26 source files read directly
**Pattern extraction date:** 2026-05-24

### Key Constraints Verified
- `v_collection.synced_at` exists (migration 0002 line 50: `ci.updated_at AS synced_at`) — no view change needed.
- `just migrate-roundtrip` recipe already exists (justfile lines 43–46) — CI uses it directly.
- `pytest-benchmark` 5.2.3 is already installed — `test_locate_benchmark` uses `benchmark.stats["mean"] * 1000 < 50`.
- `app.state.background_tasks` set already exists (app.py line 180) — reuse for counter tasks.
- `LOG_LEVEL` already in `settings.py` (line 49) and `compose.yaml` (line 64) — no new field needed.
- All three Compose services already have `healthcheck:` + `restart: unless-stopped` — DEP-05 is verify-only.
- The `gruvax-dev-pg` container is `postgres:18` in compose.yaml (line 99) — CI uses the same image.

# Phase 3: Admin Loop (PIN + Manual Entry + Undo) — Pattern Map

**Mapped:** 2026-05-20
**Files analyzed:** 27 new/modified files
**Analogs found:** 24 / 27

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `src/gruvax/auth/__init__.py` | utility | — | `src/gruvax/estimator/__init__.py` | role-match |
| `src/gruvax/auth/pin.py` | utility | request-response | `src/gruvax/db/queries.py` (hash helpers) | partial |
| `src/gruvax/auth/sessions.py` | service | CRUD | `src/gruvax/db/queries.py` | role-match |
| `src/gruvax/auth/csrf.py` | utility | request-response | `src/gruvax/api/deps.py` | partial |
| `src/gruvax/api/deps.py` | middleware | request-response | `src/gruvax/api/deps.py` (self — extend) | exact |
| `src/gruvax/api/admin/__init__.py` | config | — | `src/gruvax/api/__init__.py` | exact |
| `src/gruvax/api/admin/router.py` | route | request-response | `src/gruvax/app.py` | role-match |
| `src/gruvax/api/admin/login.py` | controller | request-response | `src/gruvax/api/health.py` + `src/gruvax/api/search.py` | role-match |
| `src/gruvax/api/admin/cubes.py` | controller | CRUD | `src/gruvax/api/units.py` | exact |
| `src/gruvax/api/admin/history.py` | controller | CRUD | `src/gruvax/api/units.py` | role-match |
| `src/gruvax/api/admin/settings.py` | controller | CRUD | `src/gruvax/api/units.py` | role-match |
| `src/gruvax/api/units.py` | controller | CRUD | `src/gruvax/api/units.py` (self — extend) | exact |
| `src/gruvax/db/queries.py` | service | CRUD | `src/gruvax/db/queries.py` (self — extend) | exact |
| `src/gruvax/settings.py` | config | — | `src/gruvax/settings.py` (self — extend) | exact |
| `src/gruvax/app.py` | config | — | `src/gruvax/app.py` (self — extend) | exact |
| `migrations/versions/0004_admin_tables.py` | migration | batch | `migrations/versions/0001_create_schema.py` | exact |
| `scripts/set_pin.py` | utility | batch | `src/gruvax/db/pool.py` (`get_pool_context`) | partial |
| `frontend/src/state/store.ts` | store | event-driven | `frontend/src/state/store.ts` (self — extend) | exact |
| `frontend/src/api/client.ts` | service | request-response | `frontend/src/api/client.ts` (self — extend) | exact |
| `frontend/src/api/adminClient.ts` | service | request-response | `frontend/src/api/client.ts` | exact |
| `frontend/src/api/types.ts` | model | — | `frontend/src/api/types.ts` (self — extend) | exact |
| `frontend/src/routes/admin/Login.tsx` | component | request-response | `frontend/src/routes/kiosk/KioskView.tsx` | role-match |
| `frontend/src/routes/admin/AdminShell.tsx` | component | event-driven | `frontend/src/routes/kiosk/KioskView.tsx` | role-match |
| `frontend/src/routes/admin/CubesGrid.tsx` | component | request-response | `frontend/src/routes/kiosk/ShelfGrid.tsx` | exact |
| `frontend/src/routes/admin/CubeEditor.tsx` | component | request-response | `frontend/src/routes/kiosk/KioskView.tsx` | role-match |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx` | component | request-response | `frontend/src/routes/kiosk/ResultsList.tsx` | role-match |
| `frontend/src/routes/admin/HistoryView.tsx` | component | CRUD | `frontend/src/routes/kiosk/ResultsList.tsx` | role-match |
| `frontend/src/routes/admin/Settings.tsx` | component | CRUD | `frontend/src/routes/kiosk/KioskView.tsx` | role-match |
| `frontend/src/routes/admin/PinOverlay.tsx` | component | request-response | `frontend/src/routes/kiosk/SearchBox.tsx` | partial |
| `frontend/src/routes/admin/NumericKeypad.tsx` | component | event-driven | `frontend/src/routes/kiosk/SearchBox.tsx` | partial |
| `frontend/src/routes/admin/FillBar.tsx` | component | transform | `frontend/src/routes/kiosk/SubCubeBar.tsx` | exact |
| `frontend/src/routes/admin/CubeContentsPanel.tsx` | component | request-response | `frontend/src/routes/kiosk/ResultsList.tsx` | role-match |
| `frontend/src/routes/admin/AlphaRail.tsx` | component | event-driven | no analog | none |
| `tests/unit/test_pin.py` | test | — | `tests/unit/test_normalize.py` | exact |
| `tests/unit/test_sessions.py` | test | — | `tests/unit/test_algorithm.py` | role-match |
| `tests/unit/test_boundary_validation.py` | test | — | `tests/unit/test_normalize.py` | exact |
| `tests/unit/test_fill_level.py` | test | — | `tests/unit/test_collection_snapshot.py` | exact |
| `tests/unit/test_cube_contents.py` | test | — | `tests/unit/test_collection_snapshot.py` | exact |
| `tests/unit/test_midpoint.py` | test | — | `tests/unit/test_algorithm.py` | role-match |
| `tests/unit/test_diff_preview.py` | test | — | `tests/unit/test_algorithm.py` | role-match |
| `tests/integration/test_admin_auth.py` | test | — | `tests/integration/test_search.py` | exact |
| `tests/integration/test_boundary_editor.py` | test | — | `tests/integration/test_search.py` | exact |
| `tests/integration/test_change_set.py` | test | — | `tests/integration/test_search.py` | exact |
| `tests/integration/test_cube_public.py` | test | — | `tests/integration/test_search.py` | exact |
| `tests/property/test_fill_level_property.py` | test | — | `tests/property/test_parser_props.py` | exact |
| `tests/property/test_midpoint_property.py` | test | — | `tests/property/test_parser_props.py` | exact |
| `tests/property/test_boundary_validation_property.py` | test | — | `tests/property/test_parser_props.py` | exact |

---

## Pattern Assignments

### `src/gruvax/auth/__init__.py` (utility, empty)

**Analog:** `src/gruvax/estimator/__init__.py`

Empty `__init__.py` — no exports needed. The auth module is imported only from `api/deps.py` and `scripts/set_pin.py`.

---

### `src/gruvax/auth/pin.py` (utility, request-response)

**Analog:** `src/gruvax/db/queries.py`

**Imports pattern** (copy from `src/gruvax/db/queries.py` lines 1–25, adapt):
```python
from __future__ import annotations

from passlib.context import CryptContext
```

**Core pattern:**
```python
# src/gruvax/auth/pin.py
_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

def hash_pin(pin: str) -> str:
    """Hash a 4-digit PIN using Argon2id. Store result in gruvax.settings."""
    return _ctx.hash(pin)

def verify_pin(pin: str, hashed: str) -> bool:
    """Constant-time verify via passlib. Returns False (not raises) on mismatch.

    NEVER log `pin`. NEVER compare hash strings with == (use ctx.verify()).
    """
    return _ctx.verify(pin, hashed)
```

**Never-log rule:** The login route must log `{"pin_attempt": "redacted"}` at INFO, never the raw digits.

**Test fixture note:** Use `CryptContext(schemes=["argon2"], deprecated="auto")` with `time_cost=1` override in test fixtures to keep Argon2id fast under pytest.

---

### `src/gruvax/auth/sessions.py` (service, CRUD)

**Analog:** `src/gruvax/db/queries.py` (psycopg `%s` pattern, `async with pool.connection()`)

**Imports pattern** (copy from `src/gruvax/db/queries.py` lines 1–25, adapt):
```python
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from itsdangerous import URLSafeSerializer
from fastapi import Request, Response
```

**Session cookie constants:**
```python
SESSION_COOKIE = "gruvax_session"
CSRF_COOKIE = "gruvax_csrf"
```

**Core CRUD pattern** (follow `src/gruvax/db/queries.py` `%s` placeholder + `async with pool.connection() as conn, conn.cursor() as cur` pattern, lines 99–108):
```python
async def create_session(conn, response: Response, secret_key: str,
                         idle_ttl_seconds: int, hard_cap_seconds: int = 1800) -> str:
    token = secrets.token_urlsafe(32)
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=idle_ttl_seconds)
    hard_expires_at = now + timedelta(seconds=hard_cap_seconds)

    await conn.execute(
        "INSERT INTO gruvax.admin_sessions"
        " (id, created_at, last_seen_at, expires_at, hard_expires_at)"
        " VALUES (%s, %s, %s, %s, %s)",
        (session_id, now, now, expires_at, hard_expires_at),
    )
    await conn.commit()

    signer = URLSafeSerializer(secret_key, salt="session")
    signed = signer.dumps(session_id)
    csrf_token = secrets.token_hex(32)

    # Session cookie: HttpOnly=True (SPA cannot read — security)
    response.set_cookie(SESSION_COOKIE, signed, httponly=True,
                        samesite="strict", secure=False)
    # CSRF cookie: httponly=False (SPA MUST read it to echo as X-CSRF-Token)
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False,
                        samesite="strict", secure=False)
    return csrf_token
```

**get_session_id helper:**
```python
async def get_session_id(request: Request, secret_key: str) -> str | None:
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    try:
        signer = URLSafeSerializer(secret_key, salt="session")
        return signer.loads(cookie)
    except Exception:
        return None
```

---

### `src/gruvax/auth/csrf.py` (utility, request-response)

**Analog:** `src/gruvax/api/deps.py` lines 1–36

No standalone module needed. CSRF check lives inside `require_admin` in `deps.py`. Create `csrf.py` only if the check is reused in more than two places; otherwise inline in `require_admin`.

---

### `src/gruvax/api/deps.py` — EXTEND (middleware, request-response)

**Analog:** `src/gruvax/api/deps.py` (self)

**Existing provider pattern** (lines 17–36) — copy exactly for `require_admin`:
```python
# src/gruvax/api/deps.py lines 17–36
def get_pool(request: Request) -> Any:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool not ready",
        )
    return pool
```

**New `require_admin` — add after existing providers** (follow same structure: get state attr, raise HTTPException on failure, type-annotated return):
```python
# New — add to src/gruvax/api/deps.py
async def require_admin(
    request: Request,
    pool: Any = Depends(get_pool),
) -> dict[str, str]:
    """Verify session cookie + CSRF token. Raises 401/403 on failure.

    Acquires then releases a pool connection (does not hold it for the
    lifetime of the endpoint — avoids pool exhaustion for future SSE endpoints).
    """
    from datetime import datetime, timezone, timedelta
    from gruvax.auth.sessions import get_session_id
    from gruvax.settings import settings

    session_id = await get_session_id(request, settings.SESSION_SECRET)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")

    # CSRF: mutating methods require X-CSRF-Token == gruvax_csrf cookie value
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_header = request.headers.get("X-CSRF-Token", "")
        csrf_cookie = request.cookies.get("gruvax_csrf", "")
        if not csrf_header or csrf_header != csrf_cookie:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="CSRF check failed")

    # Session validity check — acquire + release connection immediately
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, expires_at, hard_expires_at, revoked_at"
            " FROM gruvax.admin_sessions WHERE id = %s",
            (session_id,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Session not found")
    _, expires_at, hard_expires_at, revoked_at = row
    now = datetime.now(timezone.utc)
    if revoked_at or now > expires_at or now > hard_expires_at:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Session expired")

    # Sliding window: refresh expires_at
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.admin_sessions"
            " SET last_seen_at = %s, expires_at = %s WHERE id = %s",
            (now, now + timedelta(seconds=settings.SESSION_TTL_SECONDS), session_id),
        )
        await conn.commit()

    return {"session_id": session_id}
```

---

### `src/gruvax/api/admin/router.py` (route, request-response)

**Analog:** `src/gruvax/app.py` lines 136–148 (router import + registration pattern)

**Router factory pattern** — mirrors how `create_app()` imports routers to avoid circular imports. Create `create_admin_router()` that `app.py`'s `create_app()` will call:
```python
# src/gruvax/api/admin/router.py
from fastapi import APIRouter

def create_admin_router() -> APIRouter:
    """Return a combined /api/admin/* router.

    Imported inside create_app() (not at module level) to mirror the
    circular-import guard from app.py lines 139-146.
    """
    from gruvax.api.admin.login import router as login_router
    from gruvax.api.admin.cubes import router as cubes_router
    from gruvax.api.admin.history import router as history_router
    from gruvax.api.admin.settings import router as settings_router

    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(login_router)
    router.include_router(cubes_router)
    router.include_router(history_router)
    router.include_router(settings_router)
    return router
```

**Registration in `src/gruvax/app.py`** — add inside `create_app()` after existing routers, before StaticFiles mount (lines 139–156). Follow exact pattern of lines 139–148:
```python
# In create_app(), after existing include_router calls:
from gruvax.api.admin.router import create_admin_router
app.include_router(create_admin_router(), prefix="/api")
```

---

### `src/gruvax/api/admin/login.py` (controller, request-response)

**Analog:** `src/gruvax/api/search.py` (router definition, Query params, dict return) + `src/gruvax/api/health.py` (simple GET with no query params)

**Imports pattern** (copy from `src/gruvax/api/search.py` lines 1–30, adapt):
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address

from gruvax.api.deps import get_pool
from gruvax.auth.pin import verify_pin
from gruvax.auth.sessions import create_session, get_session_id, SESSION_COOKIE, CSRF_COOKIE

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-auth"])
limiter = Limiter(key_func=get_remote_address)
```

**Core POST pattern** (follow `src/gruvax/api/search.py` lines 34–64 — router decorator + async handler + dict return):
```python
@router.post("/login")
@limiter.limit("5/5minutes")
async def login(
    request: Request,
    response: Response,
    pool: Any = Depends(get_pool),
) -> dict[str, Any]:
    # PIN never logged — log "redacted" at INFO
    logger.info("Login attempt from %s, pin_attempt=redacted", request.client)
    body = await request.json()
    pin: str = body.get("pin", "")
    # ... verify + create session
```

**Error handling pattern** (copy from `src/gruvax/api/locate.py` lines 92–100 — HTTPException with detail dict):
```python
    if not verify_pin(pin, pin_hash):
        raise HTTPException(
            status_code=401,
            detail={"type": "invalid_pin"},
        )
```

---

### `src/gruvax/api/admin/cubes.py` (controller, CRUD)

**Analog:** `src/gruvax/api/units.py` — closest existing match: same role (controller), same data flow (CRUD), same pattern (`pool.connection()` + `op.execute()` + dict return).

**Imports pattern** (copy from `src/gruvax/api/units.py` lines 1–27, adapt):
```python
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from gruvax.api.deps import get_boundary_cache, get_collection_snapshot, get_pool, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-cubes"])
```

**Core GET pattern** (copy from `src/gruvax/api/units.py` lines 87–124 — path params via `Path(ge=...)`, inline SQL, `async with pool.connection()`, 404 pattern):
```python
@router.get("/cubes/{unit_id}/{row}/{col}/boundary")
async def get_cube_boundary(
    request: Request,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    sql = """
SELECT unit_id, row, col, first_label, first_catalog,
       last_label, last_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE unit_id = %s AND row = %s AND col = %s
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (unit_id, row, col))
        row_raw = await cur.fetchone()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    if row_raw is None:
        raise HTTPException(
            status_code=404,
            detail={"type": "cube_not_found", "unit_id": unit_id,
                    "row": row, "col": col},
        )
    return dict(zip(cols_meta, row_raw, strict=True))
```

**Core PUT / bulk POST pattern** — after DB commit, call `cache.invalidate()` then `await cache.load(pool)` (BEFORE returning HTTP 200). This ordering is critical (Pitfall A from RESEARCH.md):
```python
# AFTER conn.commit() / transaction context exit — BEFORE return
cache.invalidate()
await cache.load(pool)
return {"change_set_id": change_set_id, "applied": len(body.updates)}
```

**Idempotency check pattern** — check `idempotency_keys` table at top of bulk handler, before any business logic:
```python
idempotency_key = request.headers.get("Idempotency-Key")
if idempotency_key:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT response_json FROM gruvax.idempotency_keys WHERE key = %s",
            (idempotency_key,),
        )
        cached = await cur.fetchone()
    if cached:
        return JSONResponse(cached[0])
```

---

### `src/gruvax/api/admin/history.py` (controller, CRUD)

**Analog:** `src/gruvax/api/units.py`

**Core GET list pattern** (copy from `src/gruvax/api/units.py` lines 33–56 — simple SELECT, fetchall, dict zip):
```python
@router.get("/history")
async def get_history(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    sql = """
SELECT change_set_id, source, changed_at, count(*) AS cube_count
FROM gruvax.boundary_history
GROUP BY change_set_id, source, changed_at
ORDER BY changed_at DESC
LIMIT 100
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    return {"history": [dict(zip(cols_meta, r, strict=True)) for r in rows_raw]}
```

**Revert POST pattern** — uses same transaction pattern as bulk cubes, plus conflict detection:
```python
# Conflict detection (Pitfall D — never silently clobber)
# Query for newer boundary_history rows BEFORE writing inverse:
await cur.execute(
    "SELECT 1 FROM gruvax.boundary_history"
    " WHERE unit_id=%s AND row=%s AND col=%s AND changed_at > %s LIMIT 1",
    (unit_id, row, col, original_changed_at),
)
```

---

### `src/gruvax/api/admin/settings.py` (controller, CRUD)

**Analog:** `src/gruvax/api/units.py`

**Core GET/PUT pattern** — reads from `gruvax.settings` JSONB table. Follow `units.py` inline-SQL + dict-return convention. PUT uses `ON CONFLICT (key) DO UPDATE` (same pattern as `set_pin.py`):
```python
@router.put("/settings")
async def update_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    body = await request.json()
    # Only Phase 3 keys allowed: cube.nominal_capacity, session.idle_ttl_seconds
    ALLOWED_KEYS = {"cube.nominal_capacity", "session.idle_ttl_seconds"}
    async with pool.connection() as conn:
        for key, value in body.items():
            if key not in ALLOWED_KEYS:
                continue
            await conn.execute(
                "UPDATE gruvax.settings SET value = %s::jsonb, updated_at = now()"
                " WHERE key = %s",
                (str(value), key),
            )
        await conn.commit()
    return {"updated": True}
```

---

### `src/gruvax/api/units.py` — EXTEND (controller, CRUD)

**Analog:** `src/gruvax/api/units.py` (self)

The public `GET /api/cubes/{unit_id}/{row}/{col}` endpoint already exists (lines 87–124) but returns only boundary metadata. Phase 3 **extends** this same endpoint to also return fill level + sample records. The endpoint signature stays the same; add `CollectionSnapshot` and settings as dependencies.

**Extended return shape** (add to existing dict, follow `locate.py` lines 113–126 serialization pattern):
```python
# Add to the existing endpoint — new deps:
#   snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
#   capacity: int — read from gruvax.settings cache or app.state.settings_cache

# New return fields appended to existing dict:
result["total_count"] = len(records_in_range)
result["fill_level"] = len(records_in_range) / max(capacity, 1)
result["sample_records"] = [
    {"release_id": r.release_id, "label": r.label,
     "catalog_number": r.catalog_number}
    for r in sample_records(records_in_range, n=7)
]
```

---

### `src/gruvax/db/queries.py` — EXTEND (service, CRUD)

**Analog:** `src/gruvax/db/queries.py` (self)

**Existing `%s` placeholder pattern** to copy exactly (lines 84–108 — parameterized SQL, `async with pool.connection() as conn, conn.cursor() as cur`, fetchone/fetchall):
```python
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(sql, (q, q, DID_YOU_MEAN_THRESHOLD))
    row = await cur.fetchone()
```

**New boundary trigram near-miss query** — copy `did_you_mean_query` structure (lines 60–108), adapting for the two-field (label + catalog) similarity:
```python
# Copy the try/except psycopg.errors.UndefinedFunction pattern from
# did_you_mean_query (lines 99–108) for graceful degradation when pg_trgm absent.
BOUNDARY_TRGM_THRESHOLD: float = 0.40  # slightly above DID_YOU_MEAN_THRESHOLD

async def find_boundary_near_misses(pool, label: str, catalog: str, limit: int = 5):
    sql = """
SELECT label, catalog_number,
       similarity(lower(label), lower(%s)) * 0.5
       + similarity(lower(catalog_number), lower(%s)) * 0.5 AS sim
FROM gruvax.v_collection
WHERE similarity(lower(label), lower(%s)) > %s
   OR similarity(lower(catalog_number), lower(%s)) > %s
ORDER BY sim DESC
LIMIT %s
"""
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql, (label, catalog, label,
                                    BOUNDARY_TRGM_THRESHOLD,
                                    catalog, BOUNDARY_TRGM_THRESHOLD, limit))
            rows = await cur.fetchall()
        return [{"label": r[0], "catalog_number": r[1],
                 "similarity": float(r[2])} for r in rows]
    except psycopg.errors.UndefinedFunction:
        return []  # pg_trgm absent — allow force-save without near-misses
```

**New admin write queries** — follow the `%s` placeholder + `conn.execute()` + `conn.commit()` pattern from pool.py's `_configure_connection` and the set_pin sketch. Keep ALL SQL parameterized with `%s`, zero f-string interpolation (T-01-07).

---

### `src/gruvax/settings.py` — EXTEND (config, —)

**Analog:** `src/gruvax/settings.py` (self)

**Existing pattern** (lines 1–38) — add two new env-var fields following the same `BaseSettings` conventions:
```python
# Existing pattern — copy from lines 20–33, add:
SESSION_SECRET: str        # required; no default — crash boot if missing
SESSION_TTL_SECONDS: int = 600   # 10-minute idle TTL; matches D-04
```

`SESSION_SECRET` has no default so a missing value crashes at startup rather than silently using an insecure default (matches existing `DATABASE_URL` pattern at line 22).

---

### `src/gruvax/app.py` — EXTEND (config, —)

**Analog:** `src/gruvax/app.py` (self)

**Existing lifespan additions pattern** (lines 63–103) — add settings cache loading after snapshot load (step 3b), following the exact `try/except + logger.error + proceed` idiom:
```python
# After existing snapshot load (line 103), add:
# ── 3c. Settings cache (Phase 3) ────────────────────────────────────────────
from gruvax.db.queries import load_settings_cache
try:
    settings_map = await load_settings_cache(pool)
    app.state.settings_cache = settings_map
    logger.info("Settings cache loaded (%d keys)", len(settings_map))
except Exception as exc:
    logger.error("Settings cache load failed: %s", exc)
    app.state.settings_cache = {}
```

**SlowAPI middleware** — add to `create_app()` after `FastAPI(...)` constructor, before router registration:
```python
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

---

### `migrations/versions/0004_admin_tables.py` (migration, batch)

**Analog:** `migrations/versions/0001_create_schema.py` — exact match: same `op.execute()` DDL pattern, same naming convention, same `down_revision` chaining, same `downgrade()` drop-in-reverse order.

**Header pattern** (copy from `0001_create_schema.py` lines 1–19 exactly, change revision identifiers):
```python
from __future__ import annotations
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None
```

**`upgrade()` pattern** (copy from `0001_create_schema.py` lines 22–73 — all DDL via `op.execute()`, explicit constraint names, named indexes):
```python
def upgrade() -> None:
    op.execute("""
        CREATE TABLE gruvax.boundary_history (
            id              BIGSERIAL PRIMARY KEY,
            change_set_id   UUID NOT NULL,
            unit_id         SMALLINT NOT NULL,
            row             SMALLINT NOT NULL,
            col             SMALLINT NOT NULL,
            prev_first_label   TEXT,  prev_first_catalog TEXT,
            prev_last_label    TEXT,  prev_last_catalog  TEXT,
            prev_is_empty      BOOLEAN NOT NULL,
            new_first_label    TEXT,  new_first_catalog  TEXT,
            new_last_label     TEXT,  new_last_catalog   TEXT,
            new_is_empty       BOOLEAN NOT NULL,
            changed_by      TEXT NOT NULL DEFAULT 'admin',
            changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            source          TEXT NOT NULL
                CHECK (source IN ('manual', 'bulk', 'revert'))
        )
    """)
    op.execute("CREATE INDEX bh_changed_at_idx ON gruvax.boundary_history (changed_at DESC)")
    op.execute("CREATE INDEX bh_change_set_idx ON gruvax.boundary_history (change_set_id)")
    # ... admin_sessions, settings (with seed INSERT), idempotency_keys
```

**`downgrade()` pattern** (copy from `0001_create_schema.py` lines 76–81 — drop tables in reverse order, `IF EXISTS`):
```python
def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gruvax.idempotency_keys")
    op.execute("DROP TABLE IF EXISTS gruvax.settings")
    op.execute("DROP TABLE IF EXISTS gruvax.admin_sessions")
    op.execute("DROP TABLE IF EXISTS gruvax.boundary_history")
```

**`search_path` / `alembic_version` conventions:** Do NOT change `migrations/env.py`. The existing `version_table_schema="public"` and `connect` event listener (lines 70–77, 104–117) already handle Phase 4 tables correctly — no modification needed.

---

### `scripts/set_pin.py` (utility, batch)

**Analog:** `src/gruvax/db/pool.py` lines 101–122 (`get_pool_context` async context manager pattern)

**Imports and pool usage** (copy `get_pool_context` import and usage from `pool.py` lines 101–122):
```python
import asyncio
import getpass
import sys

from gruvax.db.pool import get_pool_context
from gruvax.auth.pin import hash_pin


async def _set_pin(pin: str) -> None:
    if not pin.isdigit() or len(pin) != 4:
        sys.exit("PIN must be exactly 4 digits")
    h = hash_pin(pin)
    async with get_pool_context() as pool:
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings (key, value, description, updated_at)"
                " VALUES ('auth.pin_hash', %s, 'Argon2id-hashed admin PIN', now())"
                " ON CONFLICT (key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (f'"{h}"',),   # JSONB requires JSON-encoded string
            )
            await conn.commit()
    print("PIN set successfully.")


def main() -> None:
    pin = getpass.getpass("Enter new PIN (4 digits): ")
    asyncio.run(_set_pin(pin))
```

**Registration in `pyproject.toml`** — add under `[project.scripts]`:
```toml
[project.scripts]
gruvax-set-pin = "scripts.set_pin:main"
```

---

### `frontend/src/state/store.ts` — EXTEND (store, event-driven)

**Analog:** `frontend/src/state/store.ts` (self)

**Existing store extension pattern** (lines 1–92) — add `admin` slice alongside existing slices. Follow the `set((s) => {...})` functional-update pattern (lines 59–77):

```typescript
// Add to GruvaxStore interface — copy interface block pattern from lines 4–46:
interface ChangeSet {
  cubeEdits: Record<string, CubeBoundaryEdit>  // key = "unitId-row-col"
}

interface AdminSlice {
  isLoggedIn: boolean
  sessionExpiresAt: number      // Unix ms — drives countdown
  hardCapExpiresAt: number      // Unix ms — hard cap independent of activity
  csrfToken: string | null      // read from gruvax_csrf cookie on login
  pendingChangeSet: ChangeSet | null   // accumulated edits, localStorage-persisted
  setAdminLoggedIn: (expiresAt: number, hardCapAt: number, csrf: string) => void
  setAdminLoggedOut: () => void
  setPendingChangeSet: (cs: ChangeSet | null) => void
}
```

**Functional update pattern** (copy from lines 59–77 — use `set((s) => ({...}))` for derived state):
```typescript
setAdminLoggedIn: (expiresAt, hardCapAt, csrf) =>
  set({ isLoggedIn: true, sessionExpiresAt: expiresAt,
        hardCapExpiresAt: hardCapAt, csrfToken: csrf }),

setAdminLoggedOut: () =>
  set({ isLoggedIn: false, sessionExpiresAt: 0,
        hardCapExpiresAt: 0, csrfToken: null }),
```

**`pendingChangeSet` persistence:** Use Zustand `persist` middleware (import from `zustand/middleware`) on the `pendingChangeSet` field only — not the full store. This survives tab reload / Wi-Fi blip without losing in-progress boundary edits (RESEARCH.md Pattern 10).

---

### `frontend/src/api/client.ts` — EXTEND (service, request-response)

**Analog:** `frontend/src/api/client.ts` (self)

**Existing fetch wrapper pattern** (lines 12–50) — add `fetchCubeContents()` following the exact same shape (async function, URLSearchParams, `res.ok` check, typed return):
```typescript
// Copy fetch pattern from lines 12–22:
export async function fetchCubeContents(
  unitId: number, row: number, col: number,
): Promise<CubeContentsResponse> {
  const res = await fetch(`${BASE}/api/cubes/${unitId}/${row}/${col}`)
  if (!res.ok) {
    if (res.status === 404) throw new Error('cube_not_found')
    throw new Error(`Cube contents fetch failed: ${res.status}`)
  }
  return res.json() as Promise<CubeContentsResponse>
}
```

---

### `frontend/src/api/adminClient.ts` (service, request-response)

**Analog:** `frontend/src/api/client.ts`

**Imports + BASE pattern** (copy lines 1–10 from `client.ts`):
```typescript
import { useGruvaxStore } from '../state/store'

const BASE = ''

/**
 * Admin fetch wrappers — all mutating requests include X-CSRF-Token header.
 * CSRF token is read from the Zustand admin slice (populated from gruvax_csrf
 * cookie on login — cookie is NOT HttpOnly so the SPA can read it).
 */
async function adminFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const csrf = useGruvaxStore.getState().csrfToken
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(csrf ? { 'X-CSRF-Token': csrf } : {}),
      ...(init.headers ?? {}),
    },
    credentials: 'same-origin',
  })
  return res
}
```

**Typed export functions** — follow the exact pattern of `client.ts` (async function, check `res.ok`, typed Promise return):
```typescript
export async function adminLogin(pin: string): Promise<{ csrf_token: string; expires_at: number }> {
  const res = await fetch(`${BASE}/api/admin/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
    credentials: 'same-origin',
  })
  if (!res.ok) throw new Error(`Login failed: ${res.status}`)
  return res.json()
}

export async function adminLogout(): Promise<void> {
  await adminFetch('/api/admin/logout', { method: 'POST' })
}

export async function adminGetSession(): Promise<{ expires_at: number; hard_cap_at: number }> {
  const res = await adminFetch('/api/admin/session')
  if (!res.ok) throw new Error(`Session check failed: ${res.status}`)
  return res.json()
}

export async function adminBulkSave(
  updates: CubeBoundaryEdit[],
  idempotencyKey: string,
): Promise<{ change_set_id: string; applied: number }> {
  const res = await adminFetch('/api/admin/cubes/bulk', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ updates }),
  })
  if (!res.ok) throw new Error(`Bulk save failed: ${res.status}`)
  return res.json()
}
```

---

### `frontend/src/api/types.ts` — EXTEND (model, —)

**Analog:** `frontend/src/api/types.ts` (self)

**Existing interface pattern** (lines 9–82) — add new admin + cube-contents interfaces following the same `export interface` + field-per-line style:
```typescript
// Add after existing CubesResponse (line 78):

export interface CubeBoundaryEdit {
  unit_id: number
  row: number
  col: number
  first_label: string | null
  first_catalog: string | null
  last_label: string | null
  last_catalog: string | null
  is_empty: boolean
  force?: boolean    // phantom override
}

export interface SampleRecord {
  release_id: number
  label: string
  catalog_number: string
}

export interface CubeContentsResponse {
  unit_id: number
  row: number
  col: number
  first_label: string | null
  first_catalog: string | null
  last_label: string | null
  last_catalog: string | null
  is_empty: boolean
  total_count: number
  fill_level: number   // 0.0+ ; > 1.0 means overstuffed
  sample_records: SampleRecord[]
}

export interface ChangeSetHistoryItem {
  change_set_id: string
  source: 'manual' | 'bulk' | 'revert'
  changed_at: string
  cube_count: number
  cubes?: CubeHistoryEntry[]
}

export interface NearMiss {
  label: string
  catalog_number: string
  similarity: number
}

export interface ValidateResponse {
  valid: boolean
  phantom?: boolean
  near_misses?: NearMiss[]
  movement_counts?: MovementCount[]
}

export interface MovementCount {
  cube: CubeRef
  records_before: number
  records_after: number
  delta: number
}
```

---

### `frontend/src/routes/admin/FillBar.tsx` (component, transform)

**Analog:** `frontend/src/routes/kiosk/SubCubeBar.tsx` — exact match by role (presentational component, pure CSS rendering, data-attribute driven).

**Read `SubCubeBar.tsx`** for the prop interface + inline style pattern. `FillBar` follows the same shape:
```typescript
// Copy prop interface pattern from SubCubeBar:
interface FillBarProps {
  fillLevel: number    // 0.0 = empty, 1.0 = full, >1.0 = overstuffed
  heightPx?: number   // 4 on kiosk main, 3 on admin compact
}

export function FillBar({ fillLevel, heightPx = 4 }: FillBarProps) {
  // Token-driven color — never hardcode hex:
  const color =
    fillLevel <= 0 ? 'transparent'
    : fillLevel < 0.80 ? 'var(--gruvax-blue-light)'
    : fillLevel <= 1.0 ? 'var(--gruvax-yellow)'
    : 'var(--gruvax-error)'

  const widthPct = Math.min(fillLevel, 1.0) * 100

  return (
    <div
      className="fill-bar"
      style={{ width: `${widthPct}%`, height: heightPx, backgroundColor: color }}
      aria-hidden="true"
    />
  )
}
```

---

### `frontend/src/routes/admin/CubesGrid.tsx` (component, request-response)

**Analog:** `frontend/src/routes/kiosk/ShelfGrid.tsx`

**ShelfGrid reuse pattern** (lines 1–120) — `CubesGrid` imports and renders `ShelfGrid` with compact cell size, adding fill bars per cube and tap handler for cube navigation. Copy the `useQuery` pattern from `KioskView.tsx` lines 47–67 for fetching units + cubes data.

**Fill-level data** — fetch from `GET /api/admin/cubes` (returns all cube boundaries + fill levels). Use `useQuery` with `queryKey: ['admin', 'cubes']`. Merge fill-level data into each `Cube` via a new `fillLevel` prop.

**Navigation on tap** — add `onClick={() => navigate(`/admin/cubes/${unitId}/${row}/${col}`)}` to each `Cube` wrapper (React Router `useNavigate` pattern).

---

### `frontend/src/routes/admin/CubeEditor.tsx` (component, request-response)

**Analog:** `frontend/src/routes/kiosk/KioskView.tsx` (TanStack Query usage + Zustand store updates)

**TanStack Query mutation pattern** (copy `useQuery` pattern from `KioskView.tsx` lines 69–79, switch to `useMutation` for saves):
```typescript
import { useQuery, useMutation } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
```

**`react-hook-form` form pattern:**
```typescript
const { register, handleSubmit, watch, setValue, formState: { errors } } =
  useForm<CubeBoundaryEdit>({ resolver: zodResolver(CubeBoundarySchema) })
```

**Two-step dependent autocomplete** — disable catalog# field until label is selected:
```typescript
const selectedLabel = watch('first_label')
// catalog# field: disabled when !selectedLabel
```

**`pendingChangeSet` accumulation** — on form submit (before commit), add to Zustand `pendingChangeSet` via `useGruvaxStore.getState().setPendingChangeSet(...)`. Navigate to diff preview. Do NOT POST to API yet.

---

### `frontend/src/routes/admin/PinOverlay.tsx` (component, request-response)

**Analog:** `frontend/src/routes/kiosk/SearchBox.tsx` (controlled input, error state handling, design token usage)

**Error state pattern** (copy from `SearchBox.tsx` — check for existing error flash/shake CSS class pattern in `kiosk.css`). `PinOverlay` adds shake animation via CSS class toggle:
```typescript
const [shake, setShake] = useState(false)

const handleWrongPin = () => {
  setShake(true)
  setTimeout(() => setShake(false), 350)
}

// In JSX: className={`pin-card${shake ? ' pin-card--shake' : ''}`}
```

**ARIA pattern** (copy from `ShelfGrid.tsx` `aria-label` usage):
```typescript
// role="dialog" aria-modal="true" aria-labelledby="pin-heading"
// Each digit key: type="button" aria-label={String(digit)}
```

---

### `frontend/src/routes/admin/NumericKeypad.tsx` (component, event-driven)

**Analog:** No close analog. Closest: `frontend/src/routes/kiosk/SearchBox.tsx` (keyboard input handling).

**Pattern:** Pure presentational component — renders a 3×4 grid of `<button type="button">` elements. Caller provides `onDigit`, `onBackspace` callbacks. Each button: `min-height: 44px` (WCAG 2.5.5, D-17 Pitfall 4). Use `var(--gruvax-space-*)` tokens for sizing — never raw px in component code.

---

### `frontend/src/routes/admin/AlphaRail.tsx` (component, event-driven)

**Analog:** None in codebase.

**Pattern:** Vertical strip of A–Z buttons. Each `<button>`: 32px wide × 44px min-height. Calls `onLetterSelect(letter: string)` prop. Use CSS Grid or flex column. Ref RESEARCH.md pattern for the jump rail spec.

---

### `frontend/src/routes/admin/CubeContentsPanel.tsx` (component, request-response)

**Analog:** `frontend/src/routes/kiosk/ResultsList.tsx` (list rendering + open/dismiss state)

**TanStack Query pattern** (copy from `KioskView.tsx` lines 69–79 — `useQuery` with `enabled: cubeTapped`):
```typescript
const { data } = useQuery({
  queryKey: ['cube-contents', unitId, row, col],
  queryFn: () => fetchCubeContents(unitId, row, col),
  enabled: panelOpen,
  staleTime: 30_000,
})
```

**Admin shortcut button** (D-16) — show "EDIT THIS CUBE" link-button only when `useGruvaxStore(s => s.isLoggedIn)` is true.

---

## Test Patterns

### `tests/unit/test_pin.py`, `tests/unit/test_boundary_validation.py`

**Analog:** `tests/unit/test_normalize.py`

**Imports + structure** (copy from `tests/unit/test_normalize.py` lines 1–25 — `from __future__ import annotations`, plain `import`, no fixtures needed for pure-function tests):
```python
from __future__ import annotations
import pytest
from gruvax.auth.pin import hash_pin, verify_pin
```

**Pure-function test pattern** — no `@pytest.mark.asyncio`, no fixtures. Each test is a `def test_*()` function:
```python
def test_verify_correct_pin() -> None:
    h = hash_pin("1234")
    assert verify_pin("1234", h)

def test_verify_wrong_pin() -> None:
    h = hash_pin("1234")
    assert not verify_pin("5678", h)
```

---

### `tests/unit/test_sessions.py`, `tests/unit/test_fill_level.py`, `tests/unit/test_cube_contents.py`, `tests/unit/test_midpoint.py`, `tests/unit/test_diff_preview.py`

**Analog:** `tests/unit/test_collection_snapshot.py` and `tests/unit/test_algorithm.py`

**Snapshot fixture pattern** (copy from `test_algorithm.py` lines 26–43 — import `RecordRow`, `CollectionSnapshot`, use `snapshot._load_snapshot({})` to bypass DB):
```python
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow

def make_snapshot(records_by_label: dict[str, list[RecordRow]]) -> CollectionSnapshot:
    snap = CollectionSnapshot()
    snap._load_snapshot({k.casefold(): v for k, v in records_by_label.items()})
    return snap
```

---

### `tests/integration/test_admin_auth.py`, `tests/integration/test_boundary_editor.py`, `tests/integration/test_change_set.py`, `tests/integration/test_cube_public.py`

**Analog:** `tests/integration/test_search.py`

**Module-scoped `client` fixture pattern** (copy from `test_search.py` lines 27–39 — `LifespanManager` + `AsyncClient` + `ASGITransport`):
```python
from __future__ import annotations
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from gruvax.app import create_app

@pytest_asyncio.fixture(scope="module")
async def client(db_pool):
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac
```

**Test body pattern** (copy from `test_search.py` lines 41–57):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_login_success(client) -> None:
    response = await client.post("/api/admin/login", json={"pin": "1234"})
    assert response.status_code == 200
    assert "gruvax_session" in response.cookies
    assert "gruvax_csrf" in response.cookies
    # CSRF cookie must NOT be HttpOnly (SPA must read it)
    csrf_cookie = response.cookies.get("gruvax_csrf")
    assert csrf_cookie is not None
```

**`admin_session` fixture** — add to `tests/conftest.py` following the `db_pool` session pattern (lines 42–58):
```python
@pytest_asyncio.fixture(scope="module")
async def admin_session(client):
    """POST /api/admin/login with test PIN; return (session_cookie, csrf_token)."""
    # Requires test DB to have auth.pin_hash seeded (conftest setup or migration seed)
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    assert res.status_code == 200
    csrf = res.cookies.get("gruvax_csrf") or res.json().get("csrf_token")
    return {"cookies": res.cookies, "csrf_token": csrf}
```

---

### `tests/property/test_fill_level_property.py`, `tests/property/test_midpoint_property.py`, `tests/property/test_boundary_validation_property.py`

**Analog:** `tests/property/test_parser_props.py`

**Hypothesis pattern** (copy `@given` + `@settings` usage from `test_parser_props.py`):
```python
from hypothesis import given, settings
from hypothesis import strategies as st

@given(
    fill_level=st.floats(min_value=0, max_value=2, allow_nan=False),
    capacity=st.integers(min_value=1, max_value=200),
)
def test_fill_level_nonnegative(fill_level: float, capacity: int) -> None:
    # fill_level(boundary, snapshot, capacity) >= 0.0
    ...
```

---

## Shared Patterns

### Authentication (`require_admin` dependency)

**Source:** `src/gruvax/api/deps.py` (new addition, extends lines 1–79)
**Apply to:** All `src/gruvax/api/admin/*.py` mutating endpoints (POST, PUT, PATCH, DELETE)

The `require_admin` dependency follows the **exact same structural pattern** as existing providers (`get_pool`, `get_boundary_cache`, `get_collection_snapshot`):
- Accept `Request` + `pool` via `Depends`
- Raise `HTTPException` with specific status codes on failure
- Type-annotated return
- Import inside function body to avoid circular imports if needed

```python
# Pattern: copy get_pool (deps.py lines 17-36), add async + DB check:
async def require_admin(request: Request, pool: Any = Depends(get_pool)) -> dict[str, str]:
    ...raise HTTPException(status_code=401, detail="Not authenticated")...
```

### Database Query Pattern

**Source:** `src/gruvax/db/queries.py` lines 84–108, `src/gruvax/api/units.py` lines 44–56
**Apply to:** All new SQL in `src/gruvax/api/admin/*.py` and `src/gruvax/db/queries.py`

- Use `%s` placeholders — NEVER f-string interpolation in SQL (T-01-07)
- Pattern: `async with pool.connection() as conn, conn.cursor() as cur:`
- Column names from `cur.description` — `[desc[0] for desc in (cur.description or [])]`
- Row to dict: `dict(zip(cols_meta, row_raw, strict=True))`

```python
# Copy from units.py lines 44-55:
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(sql, (param1, param2))
    rows_raw = await cur.fetchall()
    cols_meta = [desc[0] for desc in (cur.description or [])]
result = [dict(zip(cols_meta, r, strict=True)) for r in rows_raw]
```

### Cache Invalidation After Commit

**Source:** `src/gruvax/app.py` lines 83–91 (BoundaryCache load pattern)
**Apply to:** All endpoints in `src/gruvax/api/admin/cubes.py` and `src/gruvax/api/admin/history.py` that write to `cube_boundaries`

```python
# AFTER conn.commit() / transaction exits — BEFORE HTTP response:
cache.invalidate()
await cache.load(pool)
# Do NOT invalidate inside the transaction (Pitfall A).
```

### Error Response Format

**Source:** `src/gruvax/api/locate.py` lines 92–100 (HTTPException with detail dict)
**Apply to:** All admin endpoints

```python
# Copy from locate.py lines 92-100:
raise HTTPException(
    status_code=404,
    detail={"type": "cube_not_found", "unit_id": unit_id, "row": row, "col": col},
)
```

### Design Token CSS

**Source:** `design/gruvax-design-tokens.css`
**Apply to:** All frontend CSS (`.module.css` files for admin components)

Per `CLAUDE.md` and UI-SPEC: **never hardcode hex values**. All colors via `var(--gruvax-*)`. All spacing via `var(--gruvax-space-*)`. The three font families (Barlow Condensed, Space Grotesk, DM Mono) are already loaded in `frontend/src/main.tsx`.

### TanStack Query + Zustand Pattern (frontend)

**Source:** `frontend/src/routes/kiosk/KioskView.tsx` lines 46–80
**Apply to:** All admin route components (`CubesGrid.tsx`, `CubeEditor.tsx`, `HistoryView.tsx`, `Settings.tsx`, `CubeContentsPanel.tsx`)

```typescript
// Copy useQuery pattern from KioskView.tsx lines 46-57:
const { data, isFetching } = useQuery({
  queryKey: ['admin', 'cubes'],
  queryFn: fetchAdminCubes,
  staleTime: 30_000,
})

// For mutations — add:
const mutation = useMutation({
  mutationFn: adminBulkSave,
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] }),
})
```

### Integration Test ASGI Client

**Source:** `tests/integration/test_search.py` lines 27–39
**Apply to:** All `tests/integration/test_admin_*.py` and `tests/integration/test_cube_public.py`

The `LifespanManager` + `AsyncClient` + `ASGITransport` pattern is the only supported approach for ASGI integration tests in this project. Copy verbatim; adjust `scope="module"` for isolation between test modules.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `frontend/src/routes/admin/AlphaRail.tsx` | component | event-driven | No scrollable A–Z jump rail exists in kiosk UI; kiosk uses text input only |
| `frontend/src/routes/admin/NumericKeypad.tsx` | component | event-driven | No in-app virtual keypad exists; kiosk uses native keyboard input (SearchBox) |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx` | component | request-response | No bottom-sheet / modal sheet pattern exists in current kiosk UI |

For these three, implement using the design-token + CSS Modules + React pattern established in the kiosk components (`Cube.tsx`, `SubCubeBar.tsx`) as the structural reference, but the specific UX pattern (sheet, keypad, jump rail) must be built from scratch using the 03-UI-SPEC.md dimension specifications.

---

## Metadata

**Analog search scope:** `src/gruvax/`, `frontend/src/`, `migrations/`, `tests/`
**Files scanned:** 22 Python source files, 19 TypeScript/TSX files, 4 migration files, 13 test files
**Pattern extraction date:** 2026-05-20

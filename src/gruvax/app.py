"""FastAPI application factory + lifespan for GRUVAX.

Factory function ``create_app()`` is the ASGI entry point::

    uvicorn gruvax.app:create_app --factory

Lifespan sequence (startup):
  1. Open the psycopg ``AsyncConnectionPool``.
  2. Probe ``SELECT 1 FROM gruvax.v_collection LIMIT 1`` (D-07, Pitfall 5).
     On failure: log error, set ``app.state.discogsography_view_ok = False``.
     Never crash — search returns 503, health reports degraded.
  3. Load the ``BoundaryCache`` from ``gruvax.cube_boundaries`` (POS-04, D-03).
  4. Attempt MQTT connection (non-blocking best-effort; DEP-01, T-01-11).

Router registration order (CRITICAL — Pitfall 3):
  All ``include_router`` calls MUST precede the ``StaticFiles`` mount.
  The ``html=True`` catch-all intercepts every unmatched path, including
  ``/api/*``, if it is registered first.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from gruvax.db.pool import create_pool
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.mqtt.client import connect_mqtt, disconnect_mqtt

logger = logging.getLogger(__name__)


class SpaStaticFiles(StaticFiles):
    """StaticFiles that marks text/html responses ``Cache-Control: no-store``.

    Prevents a browser from serving a stale ``index.html`` (and thus stale JS)
    after a redeploy (T-01-13). Vite content-hashes JS/CSS asset filenames, so
    those are safely cacheable; only the HTML entry document must not be cached.
    ``StaticFiles(html=True)`` only enables SPA fallback routing — it does NOT
    set any cache-control header, so this subclass adds it explicitly.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """FastAPI lifespan: startup setup → yield → teardown."""

    # ── 1. DB pool ───────────────────────────────────────────────────────────
    pool = create_pool(min_size=2, max_size=10)
    await pool.open()
    app.state.db_pool = pool
    app.state.db_ok = True
    app.state.started_at = datetime.now(UTC)

    # ── 2. v_collection startup probe (D-07, Pitfall 5) ─────────────────────
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1 FROM gruvax.v_collection LIMIT 1")
        app.state.discogsography_view_ok = True
        logger.info("v_collection probe: OK")
    except Exception as exc:
        app.state.discogsography_view_ok = False
        logger.error(
            "v_collection probe FAILED — search will return 503 until resolved. "
            "Upstream schema change? Details: %s",
            exc,
        )

    # ── 3. Boundary cache (POS-04) ───────────────────────────────────────────
    cache = BoundaryCache()
    try:
        await cache.load(pool)  # type: ignore[arg-type]
        logger.info("Boundary cache loaded (%d rows)", len(list(cache.get_boundaries())))
    except Exception as exc:
        logger.error("Boundary cache load failed: %s", exc)
        # Proceed with empty cache — locate will return no-boundary results.
    app.state.boundary_cache = cache

    # ── 3b. Collection snapshot (POS-03) ─────────────────────────────────────
    from gruvax.estimator.collection_snapshot import CollectionSnapshot

    snapshot = CollectionSnapshot()
    try:
        await snapshot.load(pool)  # type: ignore[arg-type]
        logger.info("Collection snapshot loaded (%d labels)", len(snapshot._by_label))
    except Exception as exc:
        logger.error("Collection snapshot load failed: %s", exc)
        # Proceed with empty snapshot — locate falls back to cube-only-v1.
    app.state.collection_snapshot = snapshot

    # ── 3c. Settings cache (Phase 3) ─────────────────────────────────────────
    # Loads gruvax.settings key/value rows into app.state.settings_cache so
    # endpoints can read nominal_capacity, idle TTL, etc. without a DB hit.
    # Mirrors the try/except + logger.error + proceed pattern of steps 3 and 3b.
    from gruvax.db.queries import load_settings_cache

    try:
        settings_map = await load_settings_cache(pool)
        app.state.settings_cache = settings_map
        logger.info("Settings cache loaded (%d keys)", len(settings_map))
    except Exception as exc:
        logger.error("Settings cache load failed — proceeding with empty cache: %s", exc)
        app.state.settings_cache = {}

    # ── 4. MQTT (non-blocking best-effort; DEP-01) ───────────────────────────
    await connect_mqtt(app)

    yield  # ── App serves requests here ──────────────────────────────────────

    # ── Teardown ─────────────────────────────────────────────────────────────
    await disconnect_mqtt(app)
    await pool.close()
    logger.info("GRUVAX API shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the GRUVAX FastAPI application.

    This is the ASGI factory referenced by Uvicorn::

        uvicorn gruvax.app:create_app --factory

    Returns:
        A fully configured ``FastAPI`` instance with all routers registered
        and (optionally) the SPA ``StaticFiles`` mount at ``/``.
    """
    app = FastAPI(
        title="GRUVAX",
        description=(
            "Touchscreen kiosk + REST API to locate vinyl records in a Kallax shelf collection."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # ── SlowAPI rate-limiting (Phase 3: login rate limit, T-03-04) ──────────────
    # The @limiter.limit() decorator on login.py handles rate-limit enforcement
    # directly — it calls _check_request_limit(in_middleware=False) which reads
    # from _route_limits and correctly accumulates the per-IP counter.
    #
    # SlowAPIMiddleware (BaseHTTPMiddleware) is intentionally NOT added here.
    # BaseHTTPMiddleware stores _rate_limiting_complete on request.state and in
    # certain ASGI transport configurations (including httpx ASGITransport used in
    # tests) this state leaks across requests, causing the rate-limit counter to
    # stop accumulating after the first request.  The decorator-only pattern is the
    # correct approach for per-route limits; the middleware is only needed for
    # global/application-level limits which we don't use.
    #
    # app.state.limiter must still be set so the RateLimitExceeded exception
    # handler has access to header-injection helpers and so that any future
    # application-level limits can be added without changing this block.
    from gruvax.api.admin.limiter import limiter as admin_limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app.state.limiter = admin_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # ── Register /api/* routers FIRST (Pitfall 3: StaticFiles catch-all order) ──
    # Import here (not at module level) to avoid circular imports:
    # app.py → api/*.py → deps.py → (no back-reference to app.py)
    from gruvax.api.health import router as health_router
    from gruvax.api.locate import router as locate_router
    from gruvax.api.search import router as search_router
    from gruvax.api.units import router as units_router

    app.include_router(health_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(locate_router, prefix="/api")
    app.include_router(units_router, prefix="/api")

    # ── Admin router (Phase 3) — BEFORE StaticFiles mount (Pitfall 3) ──────────
    from gruvax.api.admin.router import create_admin_router

    app.include_router(create_admin_router(), prefix="/api")

    # ── StaticFiles SPA mount LAST ───────────────────────────────────────────
    # Plan 04 (React SPA) builds the frontend and copies the dist/ into static/.
    # Guard: only mount if the directory exists so startup doesn't crash during
    # development or before the first SPA build.
    static_dir = Path("static")
    if static_dir.exists() and static_dir.is_dir():
        # SpaStaticFiles adds Cache-Control: no-store on index.html (T-01-13).
        app.mount("/", SpaStaticFiles(directory=str(static_dir), html=True), name="spa")
        logger.info("StaticFiles SPA mounted from %s", static_dir.resolve())
    else:
        logger.info(
            "StaticFiles not mounted: 'static/' directory not found "
            "(expected after 'npm run build' in Plan 04)"
        )

    return app


# Module-level ASGI app so `uvicorn gruvax.app:app` (the Dockerfile CMD and
# standard tooling entrypoint) resolves. create_app() is side-effect-free at
# construction — the DB pool open, v_collection probe, and boundary-cache load
# all run in the lifespan on server startup, not at import time. Tests still call
# create_app() directly for isolated instances.
app = create_app()


# Note: FastAPI dependency providers live in gruvax.api.deps to avoid
# circular imports (app.py → api/*.py → deps.py, no back-reference to app.py).

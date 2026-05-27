"""FastAPI application factory + lifespan for GRUVAX.

Factory function ``create_app()`` is the ASGI entry point::

    uvicorn gruvax.app:create_app --factory

Lifespan sequence (startup):
  1. Open the psycopg ``AsyncConnectionPool``.
  2. Probe ``SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id =
     DEFAULT_PROFILE_UUID`` (Plan 01-05, D-13). On failure: log error, set
     ``app.state.profile_collection_ready = False``. Never crash — search
     returns 503, health reports degraded. Replaces v1's v_collection probe
     (the view was dropped in migration 0009).
  3. Load the ``BoundaryCache`` from ``gruvax.cube_boundaries`` (POS-04, D-03).
  4. Attempt MQTT connection (non-blocking best-effort; DEP-01, T-01-11).
  5. Schedule the 60s ``_refresh_default_profile_state`` background task —
     replaces v1's ``_refresh_sync_age`` (which read max(v_collection.synced_at);
     P1's task reads ``profiles.last_sync_at`` for the default profile).

Router registration order (CRITICAL — Pitfall 3):
  All ``include_router`` calls MUST precede the ``StaticFiles`` mount.
  The ``html=True`` catch-all intercepts every unmatched path, including
  ``/api/*``, if it is registered first.
"""

from __future__ import annotations

import asyncio
from collections import deque
import contextlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from gruvax.api.admin.router import create_admin_router
from gruvax.api.events import router as events_router
from gruvax.api.health import router as health_router
from gruvax.api.illuminate import router as illuminate_router
from gruvax.api.locate import router as locate_router
from gruvax.api.search import router as search_router
from gruvax.api.units import router as units_router
from gruvax.api.version import router as version_router
from gruvax.db.pool import create_pool
from gruvax.db.queries import load_settings_cache
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus
from gruvax.logging_config import configure_logging
from gruvax.mqtt.client import connect_mqtt, disconnect_mqtt
from gruvax.mqtt.lifecycle import HighlightRegistry, cancel_and_revert_all
from gruvax.mqtt.publishers import publish_ambient
from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from starlette.responses import Response
    from starlette.types import Scope


logger = logging.getLogger(__name__)


# Plan 01-05 / D-02: the single-profile UUID seeded by migration 0009. Used by
# the lifespan startup probe + the 60s default-profile-state background task.
# Mirrors ``tests/conftest.py::default_profile_uuid`` and the constant baked
# into migration 0009.
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"


class SpaStaticFiles(StaticFiles):
    """StaticFiles that marks text/html responses ``Cache-Control: no-store``.

    Prevents a browser from serving a stale ``index.html`` (and thus stale JS)
    after a redeploy (T-01-13). Vite content-hashes JS/CSS asset filenames, so
    those are safely cacheable; only the HTML entry document must not be cached.
    ``StaticFiles(html=True)`` only enables SPA fallback routing — it does NOT
    set any cache-control header, so this subclass adds it explicitly.

    It also serves ``index.html`` for unmatched extensionless paths so that
    client-side routes (``/admin``, ``/admin/cubes``, ``/admin/cubes/:u/:r/:c``)
    deep-link and survive a browser refresh. Starlette's ``html=True`` only
    serves ``index.html`` for *directory* requests, so a direct GET to a route
    path 404s without this fallback (ADMN-01: mobile-first admin access).
    Real missing assets (paths with a file extension, e.g. ``foo.js``) still
    return 404 so broken asset references stay visible.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            # Starlette's StaticFiles raises 404 for missing paths. Serve the SPA
            # entry for unmatched extensionless routes so client-side routing works;
            # re-raise for real missing assets (paths with a file extension).
            if exc.status_code == 404 and "." not in path.rsplit("/", 1)[-1]:
                response = await super().get_response("index.html", scope)
            else:
                raise
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """FastAPI lifespan: startup setup → yield → teardown."""

    # ── 0. Structured-JSON logging + log ring buffer (OBS-02, D-12) ─────────
    # Configure before the pool opens so all subsequent log calls emit JSON.
    # configure_logging() wires the structlog processor chain for stdout JSON,
    # and attaches LogRingHandler to the gruvax logger only (WR-02 / T-9-IL).
    _log_ring: deque[dict[str, Any]] = deque(maxlen=200)
    app.state.log_ring_buffer = _log_ring
    configure_logging(settings.LOG_LEVEL, _log_ring)

    # ── 1. DB pool ───────────────────────────────────────────────────────────
    pool = create_pool(min_size=2, max_size=10)
    await pool.open()
    app.state.db_pool = pool
    app.state.db_ok = True
    app.state.started_at = datetime.now(UTC)

    # ── 1b. In-memory ring buffers (OBS-05/06, D-08) ────────────────────────
    # Slow-query ring: last 50 requests above SLO threshold (resets on restart).
    app.state.slow_query_ring = deque(maxlen=50)
    # Sync-age seed: None until first background refresh completes.
    # Set before scheduling the task so health.py never KeyErrors on this attribute.
    app.state.sync_age_seconds = None  # float | None

    # ── 2. profile_collection startup probe (Plan 01-05, D-13) ──────────────
    # Replaces v1's v_collection probe — the view was dropped in migration 0009.
    # Same "never crash on startup, log + flip flag + continue" pattern as v1.
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT 1 FROM gruvax.profile_collection WHERE profile_id = %s::uuid LIMIT 1",
                (DEFAULT_PROFILE_UUID,),
            )
            await cur.fetchone()
        app.state.profile_collection_ready = True
        logger.info("profile_collection probe: OK")
    except Exception as exc:
        app.state.profile_collection_ready = False
        logger.error(
            "profile_collection probe FAILED — search will return 503 until resolved. "
            "Run `alembic upgrade head` and `gruvax-sync --profile default`. Details: %s",
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
    snapshot = CollectionSnapshot()
    try:
        await snapshot.load(pool)  # type: ignore[arg-type]
        logger.info("Collection snapshot loaded (%d labels)", len(snapshot._by_label))
    except Exception as exc:
        logger.error("Collection snapshot load failed: %s", exc)
        # Proceed with empty snapshot — locate falls back to cube-only-v1.
    app.state.collection_snapshot = snapshot

    # ── 3c. SegmentCache (Phase 5) ───────────────────────────────────────────
    # Derived from BoundaryCache + CollectionSnapshot (both already populated above).
    # CPU-only; no DB access during derive() or any lookup. Mirrors the try/except
    # + logger.error + proceed pattern of steps 3 and 3b.
    segment_cache = SegmentCache()
    try:
        segment_cache.derive(cache, snapshot, cache.overrides)
        logger.info("SegmentCache derived (%d bins)", len(segment_cache._bins))
    except Exception as exc:
        logger.error("SegmentCache derive failed — locate will fall back to cube-only-v1: %s", exc)
        # Proceed with empty segment_cache — locate() falls back to cube-only-v1.
    app.state.segment_cache = segment_cache

    # ── 3e. Settings cache (Phase 3) ─────────────────────────────────────────
    # Loads gruvax.settings key/value rows into app.state.settings_cache so
    # endpoints can read nominal_capacity, idle TTL, etc. without a DB hit.
    # Mirrors the try/except + logger.error + proceed pattern of steps 3 and 3b.
    try:
        settings_map = await load_settings_cache(pool)
        app.state.settings_cache = settings_map
        logger.info("Settings cache loaded (%d keys)", len(settings_map))
    except Exception as exc:
        logger.error("Settings cache load failed — proceeding with empty cache: %s", exc)
        app.state.settings_cache = {}

    # ── 3f. Event bus (Phase 4) ──────────────────────────────────────────────
    event_bus = EventBus()
    app.state.event_bus = event_bus
    try:
        await event_bus.publish("server_hello", {"version": "0.1.0"})
        logger.info("EventBus ready; server_hello published")
    except Exception as exc:
        logger.error("EventBus server_hello publish failed: %s", exc)

    # ── 4. MQTT (non-blocking best-effort; DEP-01) ───────────────────────────
    await connect_mqtt(app)

    # ── 5. Highlight registry + ambient baseline (Phase 6 / LED-11/D-20) ─────
    app.state.highlight_registry = HighlightRegistry()

    # CR-01: the asyncio event loop holds only a WEAK reference to a task created
    # via asyncio.create_task.  A fire-and-forget task whose return value is
    # discarded can be garbage-collected mid-execution, silently cancelling an
    # in-flight publish.  Keep a strong reference in this app-scoped set until the
    # task completes, then discard via add_done_callback.  The illuminate endpoint
    # reuses this same set (see gruvax.api.illuminate).
    app.state.background_tasks = set()

    # ── 1c. Default-profile-state background refresh (Plan 01-05, D-13) ─────
    # Replaces v1's _refresh_sync_age. Reads gruvax.profiles.last_sync_at +
    # last_sync_status + app_token_revoked for the default profile every 60s
    # and caches on app.state.default_profile_* (consumed by health.py).
    # sync_age_seconds is derived from last_sync_at (NOT from
    # max(v_collection.synced_at) — that view was dropped in migration 0009).
    # Initial safe defaults (set BEFORE scheduling so health.py never KeyErrors
    # if a request races the first task iteration):
    app.state.default_profile_last_sync_at = None
    app.state.default_profile_last_sync_status = None
    # Default to True so health derives 'failed' until first task iteration
    # confirms otherwise. Better-default-safe than to optimistically claim 'ok'.
    app.state.default_profile_app_token_revoked = True

    async def _refresh_default_profile_state() -> None:
        while True:
            try:
                async with pool.connection() as conn, conn.cursor() as cur:
                    await cur.execute(
                        "SELECT last_sync_at, last_sync_status, app_token_revoked "
                        "FROM gruvax.profiles "
                        "WHERE id = %s::uuid AND deleted_at IS NULL",
                        (DEFAULT_PROFILE_UUID,),
                    )
                    row = await cur.fetchone()
                if row is not None:
                    app.state.default_profile_last_sync_at = row[0]
                    app.state.default_profile_last_sync_status = row[1]
                    app.state.default_profile_app_token_revoked = bool(row[2])
                    now = datetime.now(UTC)
                    app.state.sync_age_seconds = (now - row[0]).total_seconds() if row[0] else None
            except Exception as exc:
                logger.warning("default profile state refresh failed: %s", exc)
            await asyncio.sleep(60)

    _state_task = asyncio.create_task(_refresh_default_profile_state())
    # CR-01: strong reference so the GC cannot cancel the task mid-flight.
    app.state.background_tasks.add(_state_task)
    _state_task.add_done_callback(app.state.background_tasks.discard)

    # Pitfall 2: log exceptions from the background refresh task.
    def _log_state_task_exc(t: asyncio.Task) -> None:  # type: ignore[type-arg]
        if not t.cancelled() and t.exception() is not None:
            logger.warning(
                "default_profile_state background task exited unexpectedly: %s",
                t.exception(),
            )

    _state_task.add_done_callback(_log_state_task_exc)
    logger.info("default_profile_state background refresh task scheduled (60s cadence)")

    # Publish ambient baseline for every cube — best-effort.  Never blocks startup.
    # Guard: only attempt when MQTT is connected (degraded mode → mqtt is None).
    try:
        ambient_task = asyncio.create_task(
            publish_ambient(
                app.state.mqtt,
                app.state.db_pool,
                app.state.settings_cache,
            )
        )
        # CR-01: strong-reference the task so the GC cannot cancel it mid-flight.
        app.state.background_tasks.add(ambient_task)
        ambient_task.add_done_callback(app.state.background_tasks.discard)
        logger.info("Ambient baseline publish task scheduled at startup (LED-11/D-20)")
    except Exception as exc:
        logger.warning("Failed to schedule ambient baseline publish at startup: %s", exc)

    yield  # ── App serves requests here ──────────────────────────────────────

    # ── Teardown ─────────────────────────────────────────────────────────────
    # Publish server_shutdown before closing (clients will reconnect)
    with contextlib.suppress(Exception):
        await event_bus.publish("server_shutdown", {})

    # Cancel all pending highlight revert tasks (T-06-22 leak guard).
    try:
        registry: HighlightRegistry = getattr(app.state, "highlight_registry", HighlightRegistry())
        await cancel_and_revert_all(
            registry,
            getattr(app.state, "mqtt", None),
            getattr(app.state, "settings_cache", {}),
        )
    except Exception as exc:
        logger.warning("cancel_and_revert_all on shutdown raised (ignored): %s", exc)

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

    # ── Register /api/* routers FIRST (Pitfall 3: StaticFiles catch-all order) ──
    # Routers are module-top imports — verified during the discogsography tooling
    # alignment that no api.* / api.admin.* / api.events module imports back from
    # gruvax.app, so the earlier function-scope "circular guard" pattern was
    # overcautious.
    app.include_router(health_router, prefix="/api")
    app.include_router(search_router, prefix="/api")
    app.include_router(locate_router, prefix="/api")
    app.include_router(units_router, prefix="/api")
    app.include_router(illuminate_router, prefix="/api")  # Phase 6: public LED fan-out (D-03)
    app.include_router(version_router, prefix="/api")  # Phase 8: build metadata (OBS-04)

    # ── Admin router (Phase 3) — BEFORE StaticFiles mount (Pitfall 3) ──────────
    app.include_router(create_admin_router(), prefix="/api")

    # ── Events router (Phase 4 / RTM-01) — BEFORE StaticFiles mount (Pitfall 3) ─
    app.include_router(events_router, prefix="/api")

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
# construction — the DB pool open, profile_collection probe, and boundary-cache
# load all run in the lifespan on server startup, not at import time. Tests
# still call create_app() directly for isolated instances.
app = create_app()


# Note: FastAPI dependency providers live in gruvax.api.deps to avoid
# circular imports (app.py → api/*.py → deps.py, no back-reference to app.py).

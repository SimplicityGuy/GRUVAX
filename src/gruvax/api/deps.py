"""FastAPI dependency providers for GRUVAX API endpoints.

Separated from ``app.py`` to avoid circular imports between the
app factory and the routers that depend on app.state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request, status

from gruvax.auth.sessions import BROWSE_BINDING_COOKIE, CSRF_COOKIE, get_session_id
from gruvax.settings import settings


if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryCache
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache
    from gruvax.events.bus import EventBus


def get_pool(request: Request) -> Any:
    """FastAPI dependency: return the app-level psycopg pool.

    Returns HTTP 503 (not an unhandled AttributeError/500) if the pool is not
    yet on ``app.state`` — e.g. a request that races the lifespan startup or
    arrives during shutdown.

    Usage::

        @router.get("/api/example")
        async def example(pool = Depends(get_pool)) -> ...:
            async with pool.connection() as conn: ...
    """
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database pool not ready",
        )
    return pool


def get_boundary_cache(request: Request) -> BoundaryCache:
    """FastAPI dependency: return the app-level BoundaryCache.

    Returns HTTP 503 if the cache is not yet on ``app.state`` (request races
    lifespan startup / arrives during shutdown).

    Usage::

        @router.get("/api/locate")
        async def locate(..., cache: BoundaryCache = Depends(get_boundary_cache)):
            ...
    """
    cache: BoundaryCache | None = getattr(request.app.state, "boundary_cache", None)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Boundary cache not ready",
        )
    return cache


def get_collection_snapshot(request: Request) -> CollectionSnapshot:
    """FastAPI dependency: return the app-level CollectionSnapshot.

    Returns HTTP 503 if the snapshot is not yet on ``app.state`` (request races
    lifespan startup / arrives during shutdown). The locate endpoint uses this
    to feed the §4.1 index-based estimator (POS-03 — no DB calls during compute).

    Usage::

        @router.get("/api/locate")
        async def locate(..., snapshot: CollectionSnapshot = Depends(get_collection_snapshot)):
            ...
    """
    snapshot: CollectionSnapshot | None = getattr(request.app.state, "collection_snapshot", None)
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collection snapshot not ready",
        )
    return snapshot


def get_segment_cache(request: Request) -> SegmentCache:
    """FastAPI dependency: return the app-level SegmentCache.

    Returns HTTP 503 if the cache is not yet on ``app.state`` (request races
    lifespan startup / arrives during shutdown). The locate endpoint uses this
    to feed the segment-aware two-level interpolation estimator (SEG-06/07).

    Usage::

        @router.get("/api/locate")
        async def locate(..., segment_cache: SegmentCache = Depends(get_segment_cache)):
            ...
    """
    cache: SegmentCache | None = getattr(request.app.state, "segment_cache", None)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Segment cache not ready",
        )
    return cache


def get_event_bus(request: Request) -> Any:
    """FastAPI dependency: return the app-level EventBus.

    Returns HTTP 503 if the bus is not yet on ``app.state`` — e.g. a request
    that races lifespan startup or arrives during shutdown.

    The SSE endpoint depends ONLY on this — never on ``get_pool`` (D-09, Pitfall 10).

    .. deprecated::
        P2 (Plan 02-02) replaces this with ``get_bus_for_profile``.
        Plan 02-03 will update ``api/events.py`` to use the per-profile dep.
        This dep will return 503 once ``app.state.event_bus`` is removed.

    Usage::

        @router.get("/api/events")
        async def stream_events(bus: EventBus = Depends(get_event_bus)) -> ...:
            ...
    """

    bus: EventBus | None = getattr(request.app.state, "event_bus", None)
    if bus is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event bus not ready",
        )
    return bus


# ── Per-profile resolution deps (D2-04) ──────────────────────────────────────
#
# Each dep validates the path profile_id against the browse-binding session
# cookie (gruvax_browse_binding) before resolving the registry entry.
# Error taxonomy (T-02-02-01 / D2-04):
#   400 session_unbound  — no browse-binding cookie (profile picker not visited)
#   403 profile_mismatch — cookie != path profile_id (spoofing attempt)
#   503 registry missing — registry attr not on app.state (races lifespan)
#   404 profile_not_found — profile_id not in registry (deleted / unknown)
#
# BROWSE_BINDING_COOKIE is imported from gruvax.auth.sessions (Plan 02-04
# promoted the constant from a local literal to the canonical sessions.py location).


def get_boundary_cache_for_profile(
    profile_id: str,
    request: Request,
) -> BoundaryCache:
    """Resolve boundary cache for the session-validated profile_id (D2-04).

    Validates the path profile_id against the browse-binding cookie; never
    trusts the path param as authoritative (T-02-02-01).

    Raises:
        HTTP 400 (session_unbound)   — no browse-binding cookie present.
        HTTP 403 (profile_mismatch)  — cookie != path profile_id.
        HTTP 503 (registry not ready) — registry attr missing on app.state.
        HTTP 404 (profile_not_found) — profile_id key absent from registry.
    """
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)
    if not bound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "session_unbound"},
        )
    if bound != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"type": "profile_mismatch"},
        )
    registry: dict[str, BoundaryCache] | None = getattr(
        request.app.state, "boundary_cache_registry", None
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache registry not ready",
        )
    cache: BoundaryCache | None = registry.get(str(profile_id))
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    return cache


def get_snapshot_for_profile(
    profile_id: str,
    request: Request,
) -> CollectionSnapshot:
    """Resolve collection snapshot for the session-validated profile_id (D2-04).

    Same 400/403/503/404 error taxonomy as ``get_boundary_cache_for_profile``.
    """
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)
    if not bound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "session_unbound"},
        )
    if bound != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"type": "profile_mismatch"},
        )
    registry: dict[str, CollectionSnapshot] | None = getattr(
        request.app.state, "snapshot_registry", None
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Snapshot registry not ready",
        )
    snapshot: CollectionSnapshot | None = registry.get(str(profile_id))
    if snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    return snapshot


def get_segment_cache_for_profile(
    profile_id: str,
    request: Request,
) -> SegmentCache:
    """Resolve segment cache for the session-validated profile_id (D2-04).

    Same 400/403/503/404 error taxonomy as ``get_boundary_cache_for_profile``.
    """
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)
    if not bound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "session_unbound"},
        )
    if bound != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"type": "profile_mismatch"},
        )
    registry: dict[str, SegmentCache] | None = getattr(
        request.app.state, "segment_cache_registry", None
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Segment cache registry not ready",
        )
    seg: SegmentCache | None = registry.get(str(profile_id))
    if seg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    return seg


def get_bus_for_profile(
    profile_id: str,
    request: Request,
) -> Any:
    """Resolve EventBus for the session-validated profile_id (D2-04).

    Reads ONLY app.state — never get_pool (Pitfall 10 preserved: the SSE
    endpoint must not hold a DB connection for the lifetime of the stream).

    Same 400/403/503/404 error taxonomy as ``get_boundary_cache_for_profile``.
    """
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)
    if not bound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "session_unbound"},
        )
    if bound != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"type": "profile_mismatch"},
        )
    registry: dict[str, EventBus] | None = getattr(
        request.app.state, "event_bus_registry", None
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event bus registry not ready",
        )
    bus: EventBus | None = registry.get(str(profile_id))
    if bus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    return bus


async def require_admin(
    request: Request,
    pool: Any = Depends(get_pool),
) -> dict[str, str]:
    """FastAPI dependency: verify admin session cookie + CSRF token.

    Enforces the full auth contract (ADMN-01, ADMN-02, D-04, T-03-05..T-03-09):
      1. Reads and verifies the ``gruvax_session`` signed cookie (itsdangerous).
      2. For mutating methods (POST/PUT/PATCH/DELETE), checks that the
         ``X-CSRF-Token`` header matches the ``gruvax_csrf`` cookie value
         (double-submit pattern, Pitfall 13, T-03-05).
      3. Queries ``gruvax.admin_sessions`` to confirm the session row exists,
         is not revoked, and is within both the idle TTL and hard cap.
      4. Updates ``expires_at`` (sliding window) on every valid request.

    Each DB connection is acquired and released immediately — never held for the
    lifetime of the endpoint, avoiding pool exhaustion (Pitfall B).

    Returns:
        ``{"session_id": "<uuid>"}`` on success.

    Raises:
        HTTP 401 — missing/invalid cookie, session not found, session expired.
        HTTP 403 — CSRF check failed (mutating request without X-CSRF-Token).
    """
    session_id = await get_session_id(request, settings.SESSION_SECRET)
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    # CSRF double-submit: mutating methods must echo the gruvax_csrf cookie value.
    # IN-01: Use secrets.compare_digest for constant-time comparison to prevent
    # timing-oracle attacks (even if negligible on a home LAN, it's one line).
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_header = request.headers.get("X-CSRF-Token", "")
        csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
        if not csrf_header or not secrets.compare_digest(csrf_header, csrf_cookie):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF check failed",
            )

    # Session row validity — acquire + release immediately (Pitfall B)
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, expires_at, hard_expires_at, revoked_at"
            " FROM gruvax.admin_sessions WHERE id = %s",
            (session_id,),
        )
        row = await cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )

    _, expires_at, hard_expires_at, revoked_at = row
    now = datetime.now(UTC)

    if revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked",
        )
    if now > expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired",
        )
    if now > hard_expires_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session hard cap exceeded",
        )

    # Sliding window: refresh expires_at on every valid request (D-04)
    new_expires_at = now + timedelta(seconds=settings.SESSION_TTL_SECONDS)
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.admin_sessions SET last_seen_at = %s, expires_at = %s WHERE id = %s",
            (now, new_expires_at, session_id),
        )
        await conn.commit()

    return {"session_id": session_id}

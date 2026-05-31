"""FastAPI dependency providers for GRUVAX API endpoints.

Separated from ``app.py`` to avoid circular imports between the
app factory and the routers that depend on app.state.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import secrets
from typing import TYPE_CHECKING, Any

from fastapi import Depends, HTTPException, Request, status

from gruvax.auth.sessions import (
    BROWSE_BINDING_COOKIE,
    CSRF_COOKIE,
    FINGERPRINT_COOKIE,
    get_session_id,
)
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


# ── Device-aware profile resolution helper (D3-04 / D3-05 / D3-07) ──────────
#
# resolve_profile_from_request is the single authoritative path for deriving a
# profile_id from an incoming request.  It checks the device fingerprint cookie
# first (D3-05 — device binding wins over browse-binding).
#
# Resolution precedence (D3-05):
#   1. Fingerprint present + device row exists + not revoked + profile_id IS NOT NULL
#      → return (device.profile_id, device.id)  — paired device, device binding wins
#   2. Fingerprint present + device row exists + not revoked + profile_id IS NULL
#      → orphaned device, fall through to browse-binding (picker reverts, D3-03)
#   3. Fingerprint present + device row is REVOKED  → 403 device_revoked  (D3-07)
#   4. Fingerprint present + no device row          → 403 device_unknown   (D3-07)
#   5. No fingerprint → fall through to browse-binding cookie
#   6. No browse-binding cookie                     → 400 session_unbound
#
# Pitfall 10 / D3-13 preserved: for SSE the pool is acquired + released INSIDE
# this dep; the generator body reads only the asyncio.Queue — zero pool holding.

# SQL used by resolve_profile_from_request (module-level constant, parameterised %s)
_SELECT_DEVICE_FOR_RESOLUTION = (
    "SELECT id, profile_id, revoked_at FROM gruvax.devices WHERE fingerprint = %s"
)

# Throttled last_seen_at update — at most once per 60 s per device (Open Question 3)
_UPDATE_LAST_SEEN = (
    "UPDATE gruvax.devices SET last_seen_at = NOW()"
    " WHERE id = %s"
    "   AND (last_seen_at IS NULL OR last_seen_at < NOW() - INTERVAL '60 seconds')"
)


async def resolve_profile_from_request(
    request: Request,
    pool: Any,
) -> tuple[str, str | None]:
    """D3-07: derive (profile_id, device_id|None) from the incoming request.

    Checks the fingerprint cookie first (device binding wins, D3-05); falls
    back to the browse-binding cookie.  Raises 403 for revoked/unknown
    fingerprints; raises 400 if neither binding source is present.

    The pool is acquired and released atomically inside this function — callers
    must NOT hold the pool across a generator boundary (Pitfall 10 / D3-13).

    Returns:
        (profile_id_str, device_id_str) when a paired device is recognised.
        (browse_cookie_str, None)        when browse-binding is used.

    Raises:
        HTTP 403 device_unknown  — fingerprint present but no matching device row.
        HTTP 403 device_revoked  — fingerprint maps to a revoked device.
        HTTP 400 session_unbound — no fingerprint and no browse-binding cookie.
    """
    fp = request.cookies.get(FINGERPRINT_COOKIE)
    if fp:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_SELECT_DEVICE_FOR_RESOLUTION, (fp,))
            row = await cur.fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"type": "device_unknown"},
            )
        device_id, profile_id, revoked_at = row
        if revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"type": "device_revoked"},
            )
        if profile_id is not None:
            # Throttled last_seen_at touch (at most once per 60s — Open Question 3)
            async with pool.connection() as conn:
                await conn.execute(_UPDATE_LAST_SEEN, (str(device_id),))
                await conn.commit()
            return str(profile_id), str(device_id)
        # Orphaned device (profile soft-deleted) — fall through to browse-binding
        # so kiosk reverts to picker (D3-03 / D3-05).

    # Fall back to browse-binding cookie
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)
    if not bound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "session_unbound"},
        )
    return bound, None


# ── Per-profile resolution deps (D2-04 / D3-04) ──────────────────────────────
#
# Each dep derives the authoritative profile_id via resolve_profile_from_request
# (device binding overrides browse cookie — D3-05), then validates the result
# against the path profile_id before resolving the registry entry.
#
# Error taxonomy (T-02-02-01 / D2-04 / D3-07):
#   400 session_unbound  — no fingerprint and no browse-binding cookie
#   403 device_unknown   — fingerprint present but no matching device row (D3-07)
#   403 device_revoked   — fingerprint maps to a revoked device (D3-07)
#   403 profile_mismatch — resolved profile_id != path profile_id (spoofing)
#   503 registry missing — registry attr not on app.state (races lifespan)
#   404 profile_not_found — profile_id not in registry (deleted / unknown)


async def get_boundary_cache_for_profile(
    profile_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
) -> BoundaryCache:
    """Resolve boundary cache for the device/session-validated profile_id (D2-04, D3-04).

    Derives the authoritative profile_id via resolve_profile_from_request
    (device binding overrides browse cookie — D3-05); never trusts the path
    param as authoritative (T-02-02-01, touchpoint #5).

    Raises:
        HTTP 400 (session_unbound)    — no fingerprint and no browse-binding cookie.
        HTTP 403 (device_unknown)     — unknown fingerprint (D3-07).
        HTTP 403 (device_revoked)     — revoked device fingerprint (D3-07).
        HTTP 403 (profile_mismatch)   — resolved profile_id != path profile_id.
        HTTP 503 (registry not ready) — registry attr missing on app.state.
        HTTP 404 (profile_not_found)  — profile_id key absent from registry.
    """
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
    if resolved_profile_id != profile_id:
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


async def get_snapshot_for_profile(
    profile_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
) -> CollectionSnapshot:
    """Resolve collection snapshot for the device/session-validated profile_id (D2-04, D3-04).

    Same 400/403/503/404 error taxonomy as ``get_boundary_cache_for_profile``.
    Device binding overrides browse cookie (D3-05).
    """
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
    if resolved_profile_id != profile_id:
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


async def get_segment_cache_for_profile(
    profile_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
) -> SegmentCache:
    """Resolve segment cache for the device/session-validated profile_id (D2-04, D3-04).

    Same 400/403/503/404 error taxonomy as ``get_boundary_cache_for_profile``.
    Device binding overrides browse cookie (D3-05).
    """
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
    if resolved_profile_id != profile_id:
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


async def get_bus_for_profile(
    profile_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
) -> Any:
    """Resolve EventBus for the device/session-validated profile_id (D2-04, D3-04).

    CRITICAL (Pitfall 10 / D3-13): this dep is async so it can call
    resolve_profile_from_request which acquires + releases the pool BEFORE
    returning the bus.  The generator body in events.py must NEVER hold a
    DB connection — it reads only the asyncio.Queue.

    Same 400/403/503/404 error taxonomy as ``get_boundary_cache_for_profile``.
    Device binding overrides browse cookie (D3-05).
    Pool is acquired and released inside this dep; zero pool holding in SSE.
    """
    # Device/browse validation — pool acquired + released atomically here.
    # The generator body (events.py) must NOT call get_pool (Pitfall 10).
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)
    if resolved_profile_id != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"type": "profile_mismatch"},
        )
    registry: dict[str, EventBus] | None = getattr(request.app.state, "event_bus_registry", None)
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


async def get_write_target(
    request: Request,
    pool: Any = Depends(get_pool),
) -> tuple[str, Any]:
    """FastAPI dependency: resolve (profile_id, per-profile EventBus) for admin write routes.

    Phase 6 (DATA-01 / 06-01): replaces ``get_event_bus`` on every admin boundary-write
    route so that:
      - The resolved profile_id scopes every DB write (T-06-01 WHERE clause).
      - The per-profile bus is used for boundary_changed / admin_editing fan-out
        instead of the default app.state.event_bus (T-06-03 SSE leakage fix).

    Calls ``resolve_profile_from_request`` and propagates its errors verbatim
    (D-02 — no default-profile fallback):
      HTTP 400 session_unbound  — no fingerprint cookie AND no browse-binding cookie.
      HTTP 403 device_unknown   — fingerprint present but no matching device row.
      HTTP 403 device_revoked   — fingerprint maps to a revoked device.

    After resolving the profile_id:
      HTTP 503 registry_not_ready — event_bus_registry missing from app.state.
      HTTP 404 profile_not_found  — profile_id key absent from registry (deleted profile).

    Returns:
        ``(profile_id_str, per_profile_bus)`` — the same bus used by
        ``get_bus_for_profile`` for read-only SSE consumers (D-04).

    Usage::

        @router.put("/cubes/{unit_id}/{row}/{col}/boundary")
        async def put_cube_boundary(
            ...
            profile_id_and_bus: tuple[str, EventBus] = Depends(get_write_target),
            _admin: dict[str, Any] = Depends(require_admin),
        ) -> JSONResponse:
            profile_id, bus = profile_id_and_bus
            ...
    """
    profile_id, _ = await resolve_profile_from_request(request, pool)
    registry: dict[str, Any] | None = getattr(request.app.state, "event_bus_registry", None)
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event bus registry not ready",
        )
    bus: Any = registry.get(str(profile_id))
    if bus is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    return profile_id, bus


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

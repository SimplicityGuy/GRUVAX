"""FastAPI dependency providers for GRUVAX API endpoints.

Separated from ``app.py`` to avoid circular imports between the
app factory and the routers that depend on app.state.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot


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
    from gruvax.auth.sessions import CSRF_COOKIE, get_session_id
    from gruvax.settings import settings

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
            "UPDATE gruvax.admin_sessions"
            " SET last_seen_at = %s, expires_at = %s WHERE id = %s",
            (now, new_expires_at, session_id),
        )
        await conn.commit()

    return {"session_id": session_id}

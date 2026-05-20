"""FastAPI dependency providers for GRUVAX API endpoints.

Separated from ``app.py`` to avoid circular imports between the
app factory and the routers that depend on app.state.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status

from gruvax.estimator.boundary_cache import BoundaryCache


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

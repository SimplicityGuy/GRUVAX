"""Async psycopg connection pool factory.

The pool sets ``search_path`` on every connection checkout so that:
  - ``gruvax.*`` unqualified references resolve against the gruvax schema.
  - PostgreSQL built-ins and shared extensions (``pg_trgm`` lives in
    ``public``) remain reachable.

Post-P1 (D-12): the cross-schema dependency on the v1 cross-schema view is
retired in migration 0009; the pool no longer branches on the
legacy observed-discogsography-schema setting. The legacy dual-schema
search_path (``gruvax, gruvax_dev, public``) is re-introduced ONLY inside
migration 0009's downgrade body so the recreated v1 view body can resolve
its unqualified source-schema tables (Pitfall 5).
"""

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from psycopg_pool import AsyncConnectionPool

from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from psycopg import AsyncConnection


# Re-export for convenience.
__all__ = ["create_pool", "get_pool_context"]


def _conninfo(database_url: str) -> str:
    """Convert a SQLAlchemy-style URL to a plain psycopg conninfo string.

    SQLAlchemy/Alembic use ``postgresql+psycopg://...``.  psycopg's
    ``AsyncConnectionPool`` expects the plain ``postgresql://...`` form
    (or a psycopg conninfo keyword string).

    Accepts either form so the factory is robust regardless of which style
    is present in the environment.
    """
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


async def _configure_connection(conn: AsyncConnection) -> None:
    """Pool ``configure`` callback: set search_path on each new connection.

    Per D-12 the search_path is a single literal ``gruvax, public`` — the
    pre-P1 dev/prod dual-schema branch (gruvax_dev / discogsography) was
    removed when the v1 cross-schema view retired in migration 0009. The
    gruvax_dev path is re-introduced INSIDE migration 0009's downgrade only
    (Pitfall 5), never in runtime code.

    The configure callback MUST leave the connection in ``IDLE`` transaction
    status (psycopg_pool enforces this and discards the connection otherwise).
    We use ``autocommit=True`` around the set_config call so no implicit
    transaction is started.
    """
    # pg_catalog.set_config(setting, value, is_local) fully parameterises the
    # value, preserving the SQLi-safe convention from the prior dual-schema
    # implementation.
    search_path_value = "gruvax, public"
    await conn.set_autocommit(True)
    try:
        await conn.execute(
            "SELECT pg_catalog.set_config('search_path', %s, false)",
            (search_path_value,),
        )
    finally:
        # Always restore autocommit=False so a connection never returns to the
        # pool (or is reused) in the wrong transaction mode if set_config raises.
        await conn.set_autocommit(False)


def create_pool(
    *,
    min_size: int = 2,
    max_size: int = 10,
    open: bool = False,
) -> AsyncConnectionPool:
    """Create (but do not open) an async psycopg connection pool.

    Args:
        min_size: Minimum connections kept alive.
        max_size: Maximum connections allowed.
        open: If True, open the pool immediately (for testing).

    Returns:
        An ``AsyncConnectionPool`` with ``search_path`` configured on every
        connection checkout via the ``configure`` callback.
    """
    conninfo = _conninfo(settings.DATABASE_URL)
    return AsyncConnectionPool(
        conninfo=conninfo,
        min_size=min_size,
        max_size=max_size,
        configure=_configure_connection,
        open=open,
    )


@asynccontextmanager
async def get_pool_context(
    *,
    min_size: int = 2,
    max_size: int = 10,
) -> AsyncGenerator[AsyncConnectionPool]:
    """Async context manager that opens a pool and closes it on exit.

    Convenience wrapper for use in tests and scripts.

    Example::

        async with get_pool_context() as pool:
            async with pool.connection() as conn:
                await conn.execute("SELECT 1")
    """
    pool = create_pool(min_size=min_size, max_size=max_size, open=False)
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()

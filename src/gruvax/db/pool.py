"""Async psycopg connection pool factory.

The pool sets ``search_path`` on every connection checkout so that:
  - ``gruvax.v_collection`` resolves correctly against the gruvax schema.
  - Unqualified table names in the view body (collection_items, releases,
    artists) resolve against the schema named by
    ``settings.OBSERVED_DISCOGSOGRAPHY_SCHEMA`` — "gruvax_dev" in dev/CI,
    "discogsography" in production.

This is the sole place in application code that handles the dev/prod schema
branch; everything else uses ``gruvax.v_collection`` unqualified.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from gruvax.settings import settings

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


async def _configure_connection(conn: AsyncConnection) -> None:  # type: ignore[type-arg]
    """Pool ``configure`` callback: set search_path on each new connection.

    search_path order:
      1. ``gruvax``      — owns units, cube_boundaries, v_collection.
      2. The observed discogsography schema — "gruvax_dev" (dev) or
         "discogsography" (prod).  This makes the unqualified table names in
         the v_collection view body resolve to the right source schema.
      3. ``public``      — PostgreSQL built-ins, extensions.

    ``pg_catalog.set_config`` accepts a parameterised value so this is safe
    against injection even though OBSERVED_DISCOGSOGRAPHY_SCHEMA comes from
    validated settings (not end-user input).

    The configure callback MUST leave the connection in ``IDLE`` transaction
    status (psycopg_pool enforces this and discards the connection otherwise).
    We use ``autocommit=True`` around the set_config call so no implicit
    transaction is started.
    """
    schema = settings.OBSERVED_DISCOGSOGRAPHY_SCHEMA
    # pg_catalog.set_config(setting, value, is_local) fully parameterises the
    # value, avoiding any SQL injection risk from the schema name.
    search_path_value = f"gruvax, {schema}, public"
    await conn.set_autocommit(True)
    await conn.execute(
        "SELECT pg_catalog.set_config('search_path', %s, false)",
        (search_path_value,),
    )
    await conn.set_autocommit(False)


def create_pool(
    *,
    min_size: int = 2,
    max_size: int = 10,
    open: bool = False,
) -> AsyncConnectionPool:  # type: ignore[type-arg]
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
) -> AsyncGenerator[AsyncConnectionPool]:  # type: ignore[type-arg]
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

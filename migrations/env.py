"""Alembic environment for GRUVAX — async engine, gruvax settings.

Uses the ``DATABASE_URL`` from ``gruvax.settings`` so that the migration runner
picks up the same value as the application (via .env or environment variable).
"""

import asyncio
from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import event, pool
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config


# Make ``src/`` importable when running ``alembic`` from the project root.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from typing import TYPE_CHECKING

from gruvax.settings import settings


if TYPE_CHECKING:
    from sqlalchemy.engine import Connection


# ── Alembic Config object ─────────────────────────────────────────────────────
config = context.config

# Inject the DATABASE_URL from our pydantic-settings so it takes precedence
# over the placeholder value in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Set up logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate support: if we ever add SQLAlchemy ORM models, point here.
target_metadata = None


# ── offline mode ──────────────────────────────────────────────────────────────
def run_migrations_offline() -> None:
    """Run migrations with only a URL (no live DB connection required)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ── online mode ───────────────────────────────────────────────────────────────
def do_run_migrations(connection: Connection) -> None:
    """Run migrations via Alembic's managed transaction.

    search_path is set at the engine level via a ``connect`` event listener
    (see ``_make_engine`` below) so that no SQL is executed before
    ``context.configure()``.  Executing SQL before configure() triggers
    SQLAlchemy's autobegin, which sets ``_in_external_transaction = True``
    inside Alembic, causing ``begin_transaction()`` to return a no-op context
    manager — Alembic then never calls COMMIT and every migration rolls back
    on connection close.

    alembic_version lands in ``public`` (the default) so that the downgrade's
    ``DROP SCHEMA gruvax`` does not cascade-delete the version row before
    Alembic's own bookkeeping can clean it up.
    """
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        transaction_per_migration=True,
        # Pin alembic_version to the public schema so that the downgrade's
        # DROP SCHEMA gruvax does not cascade-delete the version table before
        # Alembic can clean it up internally.
        version_table_schema="public",
    )

    with context.begin_transaction():
        context.run_migrations()


async def _make_engine() -> AsyncEngine:
    """Create the async engine and wire the search_path connect event.

    The ``connect`` event fires synchronously on the raw DBAPI connection
    (psycopg ``Connection``) immediately after it is created, before any
    SQLAlchemy-level autobegin.  Setting search_path here means the first
    execute inside ``do_run_migrations`` is Alembic's own ``has_version_table``
    probe — not our set_config call — so ``_in_external_transaction`` stays
    False and Alembic retains full transaction ownership.

    The search_path ``gruvax, {schema}, public`` lets the ``v_collection``
    view body (which uses unqualified table names) resolve against the correct
    source schema at DDL validation time during migration 0002.
    """
    schema = settings.OBSERVED_DISCOGSOGRAPHY_SCHEMA
    search_path_value = f"gruvax, {schema}, public"

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    @event.listens_for(connectable.sync_engine, "connect")
    def set_search_path(dbapi_conn: object, connection_record: object) -> None:
        """Set search_path on each new DBAPI connection via a cursor execute.

        When using the async psycopg dialect, ``dbapi_conn`` is an
        ``AsyncAdapt_psycopg_connection`` (SQLAlchemy's synchronous adapter
        over an async psycopg connection).  Its ``.cursor().execute()`` method
        is synchronous and safe to call from this hook — we are in the
        DBAPI-level connect callback, not in an async context.
        """
        # Use parameterised pg_catalog.set_config to avoid SQL injection
        # (semgrep rule: formatted-sql-query).
        cursor = dbapi_conn.cursor()  # type: ignore[union-attr]
        cursor.execute(
            "SELECT pg_catalog.set_config('search_path', %s, false)",
            (search_path_value,),
        )
        cursor.close()

    # Ensure the gruvax schema exists before Alembic opens the migration
    # connection.  Use a dedicated psycopg async connection with autocommit so
    # the schema creation is not inside a transaction that could be rolled back.
    # We bypass SQLAlchemy here to avoid the connect event firing and starting
    # an implicit transaction on the bootstrap connection.
    import psycopg

    bootstrap_url = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    async with await psycopg.AsyncConnection.connect(
        bootstrap_url, autocommit=True
    ) as bootstrap_conn:
        await bootstrap_conn.execute("CREATE SCHEMA IF NOT EXISTS gruvax")

    return connectable


async def run_async_migrations() -> None:
    """Create async engine, connect, and run migrations."""
    connectable = await _make_engine()

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online mode — drives the async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

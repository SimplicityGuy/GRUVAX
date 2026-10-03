"""Owned fresh databases and explicitly routed pools for migration tests."""

from contextlib import contextmanager
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import psycopg
from psycopg import sql
from psycopg_pool import AsyncConnectionPool
import pytest
import pytest_asyncio

from gruvax.settings import settings


ROOT = Path(__file__).resolve().parents[2]


def migrate(url: str, action: str, target: str) -> subprocess.CompletedProcess[str]:
    target_ok = target in {"head", "base"} or re.fullmatch(r"(?:[0-9]{4}|-[1-9][0-9]*)", target)
    if action not in {"upgrade", "downgrade"} or not target_ok:
        raise ValueError("Unsupported test migration command")
    # Fixed interpreter/argv, allowlisted test literals, and no shell execution.
    return subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", action, target],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=60,
    )


@contextmanager
def disposable_migration_database():  # type: ignore[no-untyped-def]
    name = "gruvax_migration_" + uuid.uuid4().hex
    parent = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(parent, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(sql.Identifier(name)))
    conninfo = psycopg.conninfo.make_conninfo(parent, dbname=name)
    url = conninfo
    # SQLAlchemy URLs and libpq conninfo differ; preserve host/auth and replace database.
    from sqlalchemy.engine import make_url

    url = str(
        make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
    )
    try:
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute((ROOT / "tests/fixtures/legacy/synth_collection.sql").read_text())
        upgraded = migrate(url, "upgrade", "head")
        assert upgraded.returncode == 0, upgraded.stderr
        yield conninfo, url
    finally:
        with psycopg.connect(parent, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


@pytest.fixture
def migration_db():  # type: ignore[no-untyped-def]
    with disposable_migration_database() as database:
        yield database


@pytest_asyncio.fixture(loop_scope="session")
async def migration_pool(migration_db):  # type: ignore[no-untyped-def]
    conninfo, _url = migration_db
    pool = AsyncConnectionPool(
        conninfo,
        kwargs={"options": "-c search_path=gruvax,public"},
        min_size=1,
        max_size=4,
        open=False,
    )
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()

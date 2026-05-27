"""Integration-test conftest: module-scoped autouse seed for gruvax.profile_collection.

Closes Gap #1 (BLOCKER) and Gap #3 (WARNING cascade) from
01-VERIFICATION.md by re-applying ``tests/fixtures/synth_profile_collection.sql``
before every integration test module runs. Lifts the proven sync-psycopg pattern
from ``tests/integration/test_search_benchmark.py`` (Plan 01-06) to apply
suite-wide, so a fresh checkout reaches green without manual
``psql < tests/fixtures/synth_profile_collection.sql``.

Uses ``psycopg.connect()`` (NOT the session-scoped async ``db_pool``) — the
async-pool path deadlocks here per the PoolTimeout debugging note in
01-06-SUMMARY.md (Rule 1 fix). pytest auto-loads both ``tests/conftest.py``
(root) and this file (integration-only); fixtures here add to, not replace,
the root-conftest fixtures.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

from gruvax.settings import settings


# Resolve from tests/integration/conftest.py → tests/ → tests/fixtures/synth_profile_collection.sql
_SYNTH_SQL_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "synth_profile_collection.sql"
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _schema_at_head(cur: psycopg.Cursor) -> bool:
    """Return True iff gruvax.profiles exists (the head-marker table from migration 0009)."""
    cur.execute("SELECT to_regclass('gruvax.profiles')")
    return cur.fetchone()[0] is not None


def _alembic_upgrade_head() -> None:
    """Run ``alembic upgrade head`` via subprocess (no event-loop conflict)."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="module", autouse=True)
def _seeded_profile_collection() -> None:
    """Idempotently seed gruvax.profile_collection for every integration test module.

    Closes Gap #1 (BLOCKER) and Gap #3 (WARNING cascade) from 01-VERIFICATION.md.

    Self-healing — if a prior test (e.g. ``test_migrate_0009::test_alembic_round_trip_is_clean``)
    left the dev DB at a non-head revision, this fixture restores it via
    ``alembic upgrade head`` before seeding. Required because the integration suite
    shares a single dev Postgres (no isolated test DB; see integration_test_harness
    project memory) and migration tests are destructive by design.

    Reads DATABASE_URL via pydantic-settings (NOT os.environ) — pydantic-settings
    loads .env directly without populating the OS environment.

    Uses a fresh sync psycopg connection (NOT the session-scoped async ``db_pool``)
    because the synchronous fixture runs in pytest's collection phase, before
    pytest-asyncio constructs the event loop the async pool needs.

    Idempotent: ``synth_profile_collection.sql`` starts with
    ``TRUNCATE gruvax.profile_collection RESTART IDENTITY CASCADE``, so calling
    once per module is safe across the whole suite.
    """
    assert _SYNTH_SQL_PATH.is_file(), f"synth fixture missing at {_SYNTH_SQL_PATH}"
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        if not _schema_at_head(cur):
            # Migration test (or aborted run) left DB at a lower revision — restore it.
            _alembic_upgrade_head()
        sql = _SYNTH_SQL_PATH.read_text()
        cur.execute(sql)
        conn.commit()
    yield
    # No teardown — the table stays seeded for subsequent modules.

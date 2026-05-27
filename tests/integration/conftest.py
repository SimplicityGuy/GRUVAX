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

import os
from pathlib import Path

import psycopg
import pytest


# Resolve from tests/integration/conftest.py → tests/ → tests/fixtures/synth_profile_collection.sql
_SYNTH_SQL_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "synth_profile_collection.sql"


@pytest.fixture(scope="module", autouse=True)
def _seeded_profile_collection() -> None:
    """Idempotently seed gruvax.profile_collection for every integration test module.

    Closes Gap #1 (BLOCKER) and Gap #3 (WARNING cascade) from
    01-VERIFICATION.md.

    Uses a fresh sync psycopg connection (NOT the session-scoped async ``db_pool``)
    because the synchronous fixture is being invoked from pytest's collection
    phase, before pytest-asyncio has constructed the event loop the async pool
    needs (this is the same root cause as the PoolTimeout debugging note in
    Plan 01-06's SUMMARY decisions block).

    Idempotent: ``synth_profile_collection.sql`` starts with
    ``TRUNCATE gruvax.profile_collection RESTART IDENTITY CASCADE``, so calling
    once per module is safe across the whole suite.
    """
    assert _SYNTH_SQL_PATH.is_file(), f"synth fixture missing at {_SYNTH_SQL_PATH}"
    dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
    sql = _SYNTH_SQL_PATH.read_text()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(sql)
        conn.commit()
    yield
    # No teardown — the table stays seeded for subsequent modules (per the
    # proven pattern in test_search_benchmark.py which has been green since
    # Plan 01-06).

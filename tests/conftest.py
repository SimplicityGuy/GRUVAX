"""Shared pytest fixtures for GRUVAX tests.

Provides:
  - ``db_pool``        — session-scoped async psycopg pool connected to the
                         test Postgres instance (reads DATABASE_URL from env).
  - ``boundary_cache`` — the parsed contents of ``fixtures/boundaries.yaml``
                         as a list of dicts, for unit tests that don't need DB.

Integration tests that need a live DB should use ``db_pool``; unit tests
should use ``boundary_cache`` or plain Python fixtures.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import yaml

from gruvax.db.pool import create_pool

# Path to the committed synthetic boundary fixture
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
BOUNDARIES_YAML = FIXTURE_DIR / "boundaries.yaml"


# ── event loop ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.DefaultEventLoopPolicy:
    """Use the default event loop policy (no uvloop in tests for simplicity)."""
    return asyncio.DefaultEventLoopPolicy()


# ── database ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def db_pool():  # type: ignore[no-untyped-def]
    """Session-scoped async psycopg pool.

    Opens the pool once per test session and closes it at teardown.
    Requires DATABASE_URL to be set (via .env or environment variable).

    Usage::

        async def test_something(db_pool):
            async with db_pool.connection() as conn:
                result = await conn.execute("SELECT 1")
    """
    pool = create_pool(min_size=1, max_size=5, open=False)
    await pool.open()
    yield pool
    await pool.close()


# ── boundary fixture ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def boundary_cache() -> list[dict[str, Any]]:
    """Load ``fixtures/boundaries.yaml`` and return the flat list of cube rows.

    Each row is a dict matching the ``gruvax.cube_boundaries`` column shape:
      unit_id, row, col, first_label, first_catalog, last_label, last_catalog,
      is_empty.

    This fixture does NOT require a live database and is safe to use in unit
    and property tests.
    """
    data: dict[str, Any] = yaml.safe_load(BOUNDARIES_YAML.read_text())
    cubes: list[dict[str, Any]] = []
    for unit in data["units"]:
        unit_id: int = unit["unit_id"]
        for cube in unit["cubes"]:
            cubes.append({**cube, "unit_id": unit_id})
    return cubes

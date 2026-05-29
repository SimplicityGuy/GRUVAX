"""Integration tests for migration 0010 — profile_id NOT NULL + composite PKs.

Covers Plan 02-01 behaviors:

  1. Round-trip upgrade head → downgrade base → upgrade head is clean.
  2. profile_id is NOT NULL (is_nullable = 'NO') on the 5 per-profile data tables:
     cube_boundaries, settings, record_stats, segment_overrides, boundary_history.
  3. profile_id STAYS nullable (is_nullable = 'YES') on the 2 infra tables:
     admin_sessions, idempotency_keys.
  4. The 4 composite PKs include profile_id as the leading column:
     cube_boundaries (profile_id, unit_id, row, col),
     settings (profile_id, key),
     record_stats (profile_id, release_id),
     segment_overrides (profile_id, unit_id, row, col, label).

These tests are authored RED (Plan 02-00) — they fail until migration 0010 lands
in Plan 02-01. The fixture and helper patterns mirror test_migrate_0009.py exactly
(subprocess _alembic helper, asyncio.to_thread, legacy-seed precondition).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

import psycopg
import pytest

from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ── shared helpers ──────────────────────────────────────────────────────────

LEGACY_SEED_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "legacy" / "synth_collection.sql"
)


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _alembic(action: str, target: str) -> None:
    """Run ``alembic <action> <target>`` via subprocess inside the test process.

    Uses asyncio.to_thread to avoid blocking the event loop — mirrors the
    identical helper in test_migrate_0009.py exactly.
    """
    if action not in ("upgrade", "downgrade"):
        raise ValueError(action)

    cwd = Path(__file__).resolve().parents[2]
    cmd = ["uv", "run", "alembic", action, target]

    result = await asyncio.to_thread(
        subprocess.run,
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        raise AssertionError(
            f"alembic {action} {target} failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


import pytest_asyncio  # noqa: E402


@pytest_asyncio.fixture
async def fresh_head(db_pool) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    """Ensure the schema is at HEAD before each test, with the legacy seed loaded.

    Mirrors the fresh_head fixture from test_migrate_0009.py.
    """
    assert LEGACY_SEED_PATH.is_file(), f"legacy seed missing at {LEGACY_SEED_PATH}"
    seed_sql = LEGACY_SEED_PATH.read_text()
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as boot:
        await boot.execute(seed_sql)

    await _alembic("upgrade", "head")
    yield
    # Leave HEAD in place for the next test.


# ── Behaviour 1: round-trip ──────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_roundtrip_clean(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 1: upgrade head → downgrade base → upgrade head exits 0 after legacy seed.

    RED until Plan 02-01 lands migration 0010. The round-trip validates:
    - 0010 upgrade applies cleanly over the 0009 state.
    - 0010 downgrade reverses all DDL changes.
    - Re-upgrade from base succeeds (idempotent with the legacy seed present).
    """
    # Already at HEAD (fresh_head). Walk it all the way down + back up.
    await _alembic("downgrade", "base")
    await _alembic("upgrade", "head")

    # Verify the profiles table survived the round-trip.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles "
            "WHERE id = '00000000-0000-0000-0000-000000000001'::uuid"
        )
        row = await cur.fetchone()
    assert row is not None, "default profile not re-seeded after round-trip"


# ── Behaviour 2: NOT NULL on 5 per-profile data tables ──────────────────────

_NOT_NULL_TABLES = (
    "cube_boundaries",
    "settings",
    "record_stats",
    "segment_overrides",
    "boundary_history",
)


@pytest.mark.asyncio(loop_scope="session")
async def test_not_null_on_five_data_tables(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 2: profile_id is NOT NULL (is_nullable = 'NO') on the 5 data tables.

    RED until Plan 02-01 lands migration 0010. Migration 0009 added profile_id
    as nullable; 0010 promotes it to NOT NULL for these 5 tables.
    """
    async with db_pool.connection() as conn, conn.cursor() as cur:
        for tbl in _NOT_NULL_TABLES:
            await cur.execute(
                "SELECT is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'gruvax' AND table_name = %s "
                "AND column_name = 'profile_id'",
                (tbl,),
            )
            row = await cur.fetchone()
            assert row is not None, f"gruvax.{tbl}.profile_id column missing"
            assert row[0] == "NO", (
                f"gruvax.{tbl}.profile_id should be NOT NULL (is_nullable='NO') "
                f"after migration 0010, got is_nullable={row[0]!r}"
            )


# ── Behaviour 3: nullable stays on 2 infra tables ───────────────────────────

_NULLABLE_TABLES = (
    "admin_sessions",
    "idempotency_keys",
)


@pytest.mark.asyncio(loop_scope="session")
async def test_nullable_stays_on_two_infra_tables(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 3: profile_id stays nullable on admin_sessions and idempotency_keys.

    RED until Plan 02-01 lands. These two tables are infrastructure-level
    (not per-profile data) so they intentionally keep nullable profile_id.
    """
    async with db_pool.connection() as conn, conn.cursor() as cur:
        for tbl in _NULLABLE_TABLES:
            await cur.execute(
                "SELECT is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'gruvax' AND table_name = %s "
                "AND column_name = 'profile_id'",
                (tbl,),
            )
            row = await cur.fetchone()
            assert row is not None, f"gruvax.{tbl}.profile_id column missing"
            assert row[0] == "YES", (
                f"gruvax.{tbl}.profile_id should remain nullable (is_nullable='YES') "
                f"after migration 0010, got is_nullable={row[0]!r}"
            )


# ── Behaviour 4: composite PKs include profile_id as leading column ──────────

# Expected composite PK leading columns per table (in order).
_COMPOSITE_PK_EXPECTED: dict[str, list[str]] = {
    "cube_boundaries": ["profile_id", "unit_id", "row", "col"],
    "settings": ["profile_id", "key"],
    "record_stats": ["profile_id", "release_id"],
    "segment_overrides": ["profile_id", "unit_id", "row", "col", "label"],
}


@pytest.mark.asyncio(loop_scope="session")
async def test_composite_pks(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 4: the 4 composite PKs include profile_id as the leading column.

    RED until Plan 02-01 lands migration 0010. Migration 0009 added profile_id
    as a nullable FK; migration 0010 promotes the PK on these 4 tables so
    profile_id is the first column, enabling prefix-scan by profile.

    Uses pg_index / pg_constraint / pg_attribute to read the actual PK column
    order without relying on information_schema (which aggregates but doesn't
    expose column order reliably for composite PKs).
    """
    async with db_pool.connection() as conn, conn.cursor() as cur:
        for tbl, expected_cols in _COMPOSITE_PK_EXPECTED.items():
            await cur.execute(
                "SELECT a.attname "
                "FROM pg_constraint c "
                "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE "
                "JOIN pg_attribute a "
                "  ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
                "WHERE c.conrelid = ('gruvax.' || %s)::regclass "
                "  AND c.contype = 'p' "
                "ORDER BY k.ord",
                (tbl,),
            )
            pk_cols = [row[0] for row in await cur.fetchall()]
            assert pk_cols == expected_cols, (
                f"gruvax.{tbl} PK columns expected {expected_cols}, got {pk_cols}. "
                f"Migration 0010 must drop the old PK and re-create it with profile_id "
                f"as the leading column."
            )

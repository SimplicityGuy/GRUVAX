"""Integration tests for migration 0011 — devices + pairing_codes tables.

Covers Plan 03-01 behaviors:

  1. Round-trip upgrade head → downgrade -1 → upgrade head is clean.
  2. gruvax.devices table exists after upgrade and is absent after downgrade.
  3. gruvax.pairing_codes table exists after upgrade and is absent after downgrade.

These tests are authored RED (Plan 03-00) — they fail until migration 0011 lands
in Plan 03-01. The fixture and helper patterns mirror test_migrate_0010.py exactly
(subprocess _alembic helper, asyncio.to_thread, fresh_head fixture).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess

import pytest
import pytest_asyncio

from gruvax.settings import settings


# ── shared helpers ──────────────────────────────────────────────────────────


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _alembic(action: str, target: str) -> None:
    """Run ``alembic <action> <target>`` via subprocess inside the test process.

    Uses asyncio.to_thread to avoid blocking the event loop — mirrors the
    identical helper in test_migrate_0010.py exactly.
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


@pytest_asyncio.fixture
async def fresh_head(db_pool):  # type: ignore[no-untyped-def]
    """Ensure the schema is at HEAD before each test.

    Mirrors the fresh_head fixture from test_migrate_0010.py.
    """
    await _alembic("upgrade", "head")
    yield
    # Leave HEAD in place for the next test.


# ── Behaviour 1: round-trip ──────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_roundtrip_clean(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 1: upgrade head → downgrade -1 → upgrade head exits 0.

    RED until Plan 03-01 lands migration 0011. The round-trip validates:
    - 0011 upgrade applies cleanly over the 0010 state.
    - 0011 downgrade reverses all DDL changes (drops devices + pairing_codes).
    - Re-upgrade from -1 (which lands back at 0011) succeeds.

    Mirrors test_roundtrip_clean in test_migrate_0010.py.
    """
    # Already at HEAD (fresh_head). Downgrade to 0010 (explicit target, NOT the
    # HEAD-relative "-1" — once a later migration is stacked on top, "-1" no longer
    # reaches the pre-0011 state and the round-trip stops exercising 0011's downgrade).
    await _alembic("downgrade", "0010")
    # Re-upgrade to HEAD (lands at the current head, ≥ 0011).
    await _alembic("upgrade", "head")

    # Verify the profiles table survived the round-trip (sanity check)
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles "
            "WHERE id = '00000000-0000-0000-0000-000000000001'::uuid"
        )
        row = await cur.fetchone()
    assert row is not None, "default profile must still exist after 0011 round-trip"


# ── Behaviour 2: gruvax.devices exists after upgrade ────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_devices_table_created(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 2: gruvax.devices table exists after upgrade head.

    RED until Plan 03-01 lands migration 0011.

    Asserts:
    - gruvax.devices table exists in information_schema
    - Required columns: id, fingerprint, profile_id, display_name, revoked_at,
      last_seen_at, created_at
    """
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gruvax' AND table_name = 'devices'"
        )
        row = await cur.fetchone()
    assert row is not None, (
        "gruvax.devices table must exist after migration 0011 upgrade. "
        "RED until Plan 03-01 lands the migration."
    )

    # Verify required columns
    expected_columns = {
        "id",
        "fingerprint",
        "profile_id",
        "display_name",
        "revoked_at",
        "last_seen_at",
        "created_at",
    }
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'gruvax' AND table_name = 'devices'",
        )
        actual_columns = {row[0] for row in await cur.fetchall()}
    missing = expected_columns - actual_columns
    assert not missing, (
        f"gruvax.devices is missing columns: {missing}. Actual columns: {actual_columns}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_devices_table_absent_after_downgrade(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """gruvax.devices does NOT exist after downgrade -1 (back to 0010).

    RED until Plan 03-01 lands migration 0011 with a clean downgrade().
    """
    # Downgrade to 0010 (explicit target — "-1" is HEAD-relative and no longer
    # reaches the pre-0011 state once a later migration sits on top of 0011).
    await _alembic("downgrade", "0010")

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gruvax' AND table_name = 'devices'"
        )
        row = await cur.fetchone()
    assert row is None, (
        "gruvax.devices must be absent after downgrade to 0010. "
        "The migration 0011 downgrade() must DROP TABLE gruvax.devices."
    )

    # Re-upgrade so the schema is back at HEAD for subsequent tests
    await _alembic("upgrade", "head")


# ── Behaviour 3: gruvax.pairing_codes exists after upgrade ──────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_pairing_codes_table_created(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 3: gruvax.pairing_codes table exists after upgrade head.

    RED until Plan 03-01 lands migration 0011.

    Asserts:
    - gruvax.pairing_codes table exists
    - Required columns: code, fingerprint, created_at, expires_at, consumed_at
    - code column is CHAR(4) (character_maximum_length = 4)
    """
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gruvax' AND table_name = 'pairing_codes'"
        )
        row = await cur.fetchone()
    assert row is not None, (
        "gruvax.pairing_codes table must exist after migration 0011 upgrade. "
        "RED until Plan 03-01 lands the migration."
    )

    # Verify required columns
    expected_columns = {"code", "fingerprint", "created_at", "expires_at", "consumed_at"}
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'gruvax' AND table_name = 'pairing_codes'",
        )
        actual_columns = {row[0] for row in await cur.fetchall()}
    missing = expected_columns - actual_columns
    assert not missing, (
        f"gruvax.pairing_codes is missing columns: {missing}. Actual columns: {actual_columns}"
    )

    # Verify code is CHAR(4)
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT character_maximum_length FROM information_schema.columns "
            "WHERE table_schema = 'gruvax' AND table_name = 'pairing_codes' "
            "AND column_name = 'code'",
        )
        row = await cur.fetchone()
    assert row is not None, "code column metadata missing from information_schema"
    assert row[0] == 4, (
        f"pairing_codes.code must be CHAR(4) (character_maximum_length=4), "
        f"got character_maximum_length={row[0]!r}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_pairing_codes_table_absent_after_downgrade(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """gruvax.pairing_codes does NOT exist after downgrade -1 (back to 0010).

    RED until Plan 03-01 lands migration 0011 with a clean downgrade().
    """
    # Downgrade to 0010 (explicit target — "-1" is HEAD-relative and no longer
    # reaches the pre-0011 state once a later migration sits on top of 0011).
    await _alembic("downgrade", "0010")

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'gruvax' AND table_name = 'pairing_codes'"
        )
        row = await cur.fetchone()
    assert row is None, (
        "gruvax.pairing_codes must be absent after downgrade to 0010. "
        "The migration 0011 downgrade() must DROP TABLE gruvax.pairing_codes."
    )

    # Re-upgrade so the schema is back at HEAD for subsequent tests
    await _alembic("upgrade", "head")

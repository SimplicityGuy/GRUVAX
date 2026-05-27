"""Integration tests for migration 0009 — profiles + profile_collection + 7-table fanout.

Covers Plan 01-01 Task 2 behaviors 1-10:

  1. profiles table exists with all D-01 columns + CHECK constraints
  2. exactly one row seeded with the default UUID + revoked=TRUE + empty bytea
  3. partial-unique indexes enforce display_name case-collision +
     allow NULL discogsography_user_id duplicates
  4. profile_collection PK is composite (profile_id, release_id, folder_id);
     dupes-on-purpose succeed; identical triplet INSERT fails
  5. all 7 v1 tables have nullable profile_id backfilled to default UUID
  6. v_collection is DROPPED after upgrade head
  7. round-trip upgrade head → downgrade base → upgrade head is clean
  8. downgrade SET LOCAL search_path covers Pitfall 5
  9. no column-level UNIQUE on profiles.discogsography_user_id (Pitfall 7)
 10. Wave-0 legacy seed at tests/fixtures/legacy/synth_collection.sql is
     reachable (the round-trip downgrade depends on it for v_collection's
     gruvax_dev.{artists,releases,collection_items} resolution).

These tests require a live Postgres (via the project conftest's ``db_pool``
fixture). The CI test job spins up postgres:18, seeds the legacy SQL, then
runs ``just migrate-roundtrip`` separately; this file's Test 7 invokes
alembic programmatically so the round-trip is also exercised from inside
pytest in a single connection.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

import psycopg
import pytest
import pytest_asyncio

from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ── shared helpers ──────────────────────────────────────────────────────────


DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
LEGACY_SEED_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "legacy" / "synth_collection.sql"
)


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _alembic(action: str, target: str) -> None:
    """Run ``alembic <action> <target>`` via subprocess inside the test process.

    Closes Gap #2 from 01-VERIFICATION.md: the previous programmatic
    ``alembic.command.upgrade()`` path failed because env.py's
    ``asyncio.run(run_async_migrations())`` cannot be called from within
    pytest-asyncio's existing event loop. The subprocess has its own Python
    interpreter and no parent event loop, so env.py's ``asyncio.run()`` succeeds.

    The argv mirrors the canonical ``just migrate-roundtrip`` recipe
    (justfile:47-50), so the failure surface in tests matches the CI gate
    exactly. ``subprocess.run`` is wrapped in ``asyncio.to_thread`` so the
    test event loop is not blocked during the multi-second migration.
    """
    if action not in ("upgrade", "downgrade"):
        raise ValueError(action)

    # Repo root — alembic auto-discovers alembic.ini here (no -c flag needed,
    # matching the justfile recipe).
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
        # Custom AssertionError carries full stdout/stderr into the pytest
        # report; CalledProcessError truncates by default.
        raise AssertionError(
            f"alembic {action} {target} failed (exit {result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )


@pytest_asyncio.fixture
async def fresh_head(db_pool) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    """Ensure the schema is at HEAD before each test, with the legacy seed loaded.

    The legacy seed creates ``gruvax_dev.{artists,releases,collection_items}``
    — needed by migration 0009's downgrade body (Pitfall 5). Loading it here
    makes the round-trip test (Test 7) work even on a clean test DB.
    """
    # 1. Load the legacy seed (idempotent — uses CREATE … IF NOT EXISTS +
    #    TRUNCATE inside the .sql file).
    assert LEGACY_SEED_PATH.is_file(), f"legacy seed missing at {LEGACY_SEED_PATH}"
    seed_sql = LEGACY_SEED_PATH.read_text()
    async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as boot:
        # ``execute`` runs each top-level statement; the legacy file is one
        # multi-statement script.
        await boot.execute(seed_sql)

    # 2. Make sure we're at HEAD.
    await _alembic("upgrade", "head")
    yield
    # No teardown — leave HEAD in place for the next test.


# ── Behaviour tests 1-6 + 9: post-upgrade state ─────────────────────────────


async def test_profiles_table_exists_with_check_constraints(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 1: gruvax.profiles has all D-01 columns + CHECK constraints."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = 'gruvax' AND table_name = 'profiles' "
            "ORDER BY ordinal_position"
        )
        cols = {row[0]: (row[1], row[2]) for row in await cur.fetchall()}

    expected = {
        "id",
        "display_name",
        "discogs_username",
        "discogsography_user_id",
        "app_token_encrypted",
        "app_token_revoked",
        "created_at",
        "last_sync_at",
        "last_sync_status",
        "last_sync_error",
        "last_sync_item_count",
        "deleted_at",
    }
    assert expected.issubset(cols.keys()), f"profiles missing columns: {expected - cols.keys()}"
    # NOT NULL on app_token_encrypted + app_token_revoked.
    assert cols["app_token_encrypted"][1] == "NO"
    assert cols["app_token_revoked"][1] == "NO"
    # display_name NOT NULL.
    assert cols["display_name"][1] == "NO"

    # CHECK constraints on last_sync_status + last_sync_error.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT pg_get_constraintdef(oid) "
            "FROM pg_constraint "
            "WHERE conrelid = 'gruvax.profiles'::regclass AND contype = 'c'"
        )
        defs = [row[0] for row in await cur.fetchall()]
    text = " ".join(defs).lower()
    assert "last_sync_status" in text
    assert "ok" in text and "failed" in text and "in_progress" in text
    assert "last_sync_error" in text
    assert "pat_rejected" in text


async def test_default_profile_seeded(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 2: single seeded row with default UUID + revoked=TRUE + bytea."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text, display_name, app_token_revoked, app_token_encrypted "
            "FROM gruvax.profiles"
        )
        rows = await cur.fetchall()

    assert len(rows) == 1, f"expected exactly one seed row, got {len(rows)}"
    pid, name, revoked, ciphertext = rows[0]
    assert pid == DEFAULT_PROFILE_UUID
    assert name == "Default"
    assert revoked is True
    # Empty bytea placeholder — concrete value is b"" (zero-length).
    assert isinstance(ciphertext, (bytes, memoryview))
    assert bytes(ciphertext) == b""


async def test_partial_unique_indexes_and_no_column_unique(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviours 3 + 9: partial-unique enforce + no column-level UNIQUE (Pitfall 7)."""
    # Both partial-unique indexes exist with the right WHERE clauses.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = 'gruvax' AND tablename = 'profiles' "
            "ORDER BY indexname"
        )
        idx = {row[0]: row[1] for row in await cur.fetchall()}
    assert "uq_profiles_display_name_active" in idx
    assert "WHERE (deleted_at IS NULL)" in idx["uq_profiles_display_name_active"]
    assert "lower(display_name)" in idx["uq_profiles_display_name_active"].lower()
    assert "uq_profiles_dgs_user_id_active" in idx
    dgs_def = idx["uq_profiles_dgs_user_id_active"]
    assert "deleted_at IS NULL" in dgs_def
    assert "discogsography_user_id IS NOT NULL" in dgs_def

    # No column-level UNIQUE constraint on profiles (Pitfall 7).
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT conname FROM pg_constraint "
            "WHERE conrelid = 'gruvax.profiles'::regclass AND contype = 'u'"
        )
        u_constraints = [row[0] for row in await cur.fetchall()]
    assert u_constraints == [], (
        f"profiles should have no column-level UNIQUE constraints (only partial-unique "
        f"INDEXES); got {u_constraints}"
    )

    # display_name case-collision triggers unique-violation.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.UniqueViolation):
            await cur.execute(
                "INSERT INTO gruvax.profiles "
                "(display_name, app_token_encrypted, app_token_revoked) "
                "VALUES ('DEFAULT', %s::bytea, TRUE)",
                (b"",),
            )

    # Two rows with NULL discogsography_user_id are allowed (NULL is not constrained).
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO gruvax.profiles "
            "(display_name, app_token_encrypted, app_token_revoked) "
            "VALUES ('Tester', %s::bytea, TRUE)",
            (b"",),
        )
        await conn.commit()
        # Clean up so subsequent tests in the same session aren't surprised.
        await cur.execute("DELETE FROM gruvax.profiles WHERE display_name = 'Tester'")
        await conn.commit()


async def test_profile_collection_pk_is_composite(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 4: composite PK (profile_id, release_id, folder_id); dupes-on-purpose."""
    # PK has those three columns in order.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT a.attname "
            "FROM pg_constraint c "
            "JOIN unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE "
            "JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum "
            "WHERE c.conrelid = 'gruvax.profile_collection'::regclass AND c.contype = 'p' "
            "ORDER BY k.ord"
        )
        pk_cols = [row[0] for row in await cur.fetchall()]
    assert pk_cols == ["profile_id", "release_id", "folder_id"]

    # Insert: same release_id in two folders under the same profile succeeds.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            "VALUES (%s::uuid, 12345, 1, 'Test Artist', 'A', 'L', 'C-001', 1970), "
            "       (%s::uuid, 12345, 2, 'Test Artist', 'A', 'L', 'C-001', 1970)",
            (DEFAULT_PROFILE_UUID, DEFAULT_PROFILE_UUID),
        )
        await conn.commit()

    # Identical triplet → unique-violation.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        with pytest.raises(psycopg.errors.UniqueViolation):
            await cur.execute(
                "INSERT INTO gruvax.profile_collection "
                "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
                "VALUES (%s::uuid, 12345, 1, 'X', 'Y', 'Z', 'W', 1970)",
                (DEFAULT_PROFILE_UUID,),
            )

    # Cleanup.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id = 12345",
            (DEFAULT_PROFILE_UUID,),
        )
        await conn.commit()


# Per-v1-table NULL-count SELECTs as static literals (avoids any runtime SQL
# concatenation, mirroring the migration's static-statement approach).
#
# RECONCILED 2026-05-27 (Plan 01-03 deviation Rule 3 / blocking issue):
# Realigned to the real v1 tables that exist after `alembic upgrade 0008`
# (see migration 0009's `_V1_TABLES` docstring for the full history of why
# the original Plan 01-01 list was wrong).
_V1_NULL_COUNT_QUERIES: dict[str, str] = {
    "admin_sessions": "SELECT COUNT(*) FROM gruvax.admin_sessions WHERE profile_id IS NULL",
    "boundary_history": "SELECT COUNT(*) FROM gruvax.boundary_history WHERE profile_id IS NULL",
    "cube_boundaries": "SELECT COUNT(*) FROM gruvax.cube_boundaries WHERE profile_id IS NULL",
    "idempotency_keys": "SELECT COUNT(*) FROM gruvax.idempotency_keys WHERE profile_id IS NULL",
    "record_stats": "SELECT COUNT(*) FROM gruvax.record_stats WHERE profile_id IS NULL",
    "segment_overrides": "SELECT COUNT(*) FROM gruvax.segment_overrides WHERE profile_id IS NULL",
    "settings": "SELECT COUNT(*) FROM gruvax.settings WHERE profile_id IS NULL",
}


async def test_v1_tables_have_nullable_profile_id_backfilled(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 5: every v1 table has nullable profile_id; pre-existing rows backfilled."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        for tbl, null_query in _V1_NULL_COUNT_QUERIES.items():
            await cur.execute(
                "SELECT data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'gruvax' AND table_name = %s AND column_name = 'profile_id'",
                (tbl,),
            )
            row = await cur.fetchone()
            assert row is not None, f"{tbl}.profile_id missing"
            data_type, is_nullable = row
            assert data_type == "uuid", f"{tbl}.profile_id type {data_type} != uuid"
            assert is_nullable == "YES", (
                f"{tbl}.profile_id should be nullable (NOT NULL deferred to P2)"
            )

            # Any pre-existing rows must be backfilled with the default UUID
            # (rows inserted post-migration may have NULL — D-11 enforces only
            # the migration-time backfill).
            await cur.execute(null_query)
            null_count = (await cur.fetchone())[0]  # type: ignore[index]
            # Allow zero; the backfill is verified by lack of NULLs IF any rows
            # exist. We don't seed pre-migration rows in this test harness, so
            # the table may be empty — both cases (empty / fully-backfilled)
            # are valid.
            assert null_count == 0, (
                f"{tbl} has {null_count} rows with NULL profile_id — migration backfill failed"
            )


async def test_v_collection_is_dropped(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 6: gruvax.v_collection is gone after upgrade head."""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT to_regclass('gruvax.v_collection')")
        row = await cur.fetchone()
    assert row is not None
    assert row[0] is None, f"v_collection should be dropped, got {row[0]!r}"


# ── Behaviour 7: round-trip ─────────────────────────────────────────────────


async def test_alembic_round_trip_is_clean(
    db_pool,  # type: ignore[no-untyped-def]
    fresh_head: None,
) -> None:
    """Behaviour 7 + 8: upgrade head → downgrade base → upgrade head completes clean.

    The downgrade leg exercises Pitfall 5 — the SET LOCAL search_path inside
    migration 0009 must let the recreated v_collection's unqualified body
    resolve against gruvax_dev.{artists,releases,collection_items}. The
    ``fresh_head`` fixture loaded the legacy seed before this test runs.
    """
    # We're already at HEAD (fresh_head). Walk it down + back up.
    await _alembic("downgrade", "base")
    await _alembic("upgrade", "head")

    # Re-verify the post-HEAD invariants survive the round-trip.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_PROFILE_UUID,),
        )
        row = await cur.fetchone()
    assert row is not None, "default profile not re-seeded after round-trip"
    assert row[0] == DEFAULT_PROFILE_UUID


# ── Behaviour 10: legacy seed reachability ──────────────────────────────────


def test_legacy_seed_path_resolves() -> None:
    """Behaviour 10: Wave-0 legacy seed is present at the path the round-trip depends on."""
    assert LEGACY_SEED_PATH.is_file(), (
        f"Plan 01-00 should have moved fixtures/synth_collection.sql to "
        f"{LEGACY_SEED_PATH} so plan 01-01 Task 2's downgrade test can reach it."
    )
    # Sanity: the file creates the gruvax_dev schema + the three legacy tables.
    body = LEGACY_SEED_PATH.read_text()
    assert "CREATE SCHEMA IF NOT EXISTS gruvax_dev" in body
    assert "gruvax_dev.collection_items" in body
    assert "gruvax_dev.releases" in body
    assert "gruvax_dev.artists" in body

"""Integration tests for Alembic migration 0005 — segment model (SEG-01).

Tests:
  - test_segment_overrides_table_exists: segment_overrides table present after 0005 upgrade
  - test_last_label_column_absent: cube_boundaries has no last_label column post-upgrade
  - test_fraction_check_rejects_over_one: INSERT with fraction=1.5 rejected by DB CHECK (V5 / T-05-01)
  - test_fraction_check_rejects_zero: INSERT with fraction=0.0 rejected (exclusive lower bound)
  - test_fraction_check_accepts_boundary: fraction=1.0 accepted (inclusive upper bound)
  - test_source_check_accepts_cut_insert: boundary_history.source='cut_insert' accepted
  - test_source_check_rejects_unknown_source: unknown source value rejected
  - test_0005_round_trip_down_up: downgrade 0004 then upgrade head round-trip (schema intact)

All tests require a live DB at DATABASE_URL and run with @pytest.mark.asyncio(loop_scope="session").
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.pool import create_pool

# ── Session-scoped DB pool (mirrors pattern from test_locate.py) ─────────────


@pytest_asyncio.fixture(scope="module")
async def migrate_pool():  # type: ignore[no-untyped-def]
    """Module-scoped async psycopg pool for migration tests."""
    pool = create_pool(min_size=1, max_size=2, open=False)
    await pool.open()
    yield pool
    await pool.close()


# ── Helper ────────────────────────────────────────────────────────────────────


async def _table_exists(pool, table_name: str) -> bool:  # type: ignore[no-untyped-def]
    """Check whether a table exists in gruvax schema."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM information_schema.tables"
            " WHERE table_schema = 'gruvax' AND table_name = %s",
            (table_name,),
        )
        row = await cur.fetchone()
        return row is not None


async def _column_exists(pool, table_name: str, column_name: str) -> bool:  # type: ignore[no-untyped-def]
    """Check whether a column exists in a gruvax table."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM information_schema.columns"
            " WHERE table_schema = 'gruvax' AND table_name = %s AND column_name = %s",
            (table_name, column_name),
        )
        row = await cur.fetchone()
        return row is not None


async def _get_unit_id(pool) -> int:  # type: ignore[no-untyped-def]
    """Return the first unit_id from gruvax.units, or raise if none."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT id FROM gruvax.units LIMIT 1")
        row = await cur.fetchone()
    if row is None:
        pytest.skip("No rows in gruvax.units — integration DB not seeded")
    return int(row[0])


async def _get_first_cube(pool, unit_id: int) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    """Return (unit_id, row, col) for the first non-empty cube, or skip."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT unit_id, row, col FROM gruvax.cube_boundaries"
            " WHERE unit_id = %s AND NOT is_empty"
            " ORDER BY row, col LIMIT 1",
            (unit_id,),
        )
        row = await cur.fetchone()
    if row is None:
        pytest.skip(f"No non-empty cubes in cube_boundaries for unit_id={unit_id}")
    return int(row[0]), int(row[1]), int(row[2])


# ── Schema presence tests (post-upgrade assertions) ───────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_segment_overrides_table_exists(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0005 creates the gruvax.segment_overrides table (SEG-01)."""
    exists = await _table_exists(migrate_pool, "segment_overrides")
    assert exists, "gruvax.segment_overrides table should exist after migration 0005"


@pytest.mark.asyncio(loop_scope="module")
async def test_last_label_column_absent(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0005 drops last_label from cube_boundaries (D-05 / SEG-01)."""
    exists = await _column_exists(migrate_pool, "cube_boundaries", "last_label")
    assert not exists, "last_label column should NOT exist in cube_boundaries after migration 0005"


@pytest.mark.asyncio(loop_scope="module")
async def test_last_catalog_column_absent(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0005 drops last_catalog from cube_boundaries (D-05 / SEG-01)."""
    exists = await _column_exists(migrate_pool, "cube_boundaries", "last_catalog")
    assert not exists, (
        "last_catalog column should NOT exist in cube_boundaries after migration 0005"
    )


# ── fraction CHECK constraint tests (T-05-01 / V5 security control) ──────────


@pytest.mark.asyncio(loop_scope="module")
async def test_fraction_check_rejects_over_one(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """DB CHECK rejects segment_overrides.fraction > 1.0 (T-05-01 / V5 security control).

    This is the authoritative proof that the storage-layer constraint is in place
    regardless of what the application layer sends. fraction=1.5 must be rejected.
    """
    import psycopg

    unit_id = await _get_unit_id(migrate_pool)
    uid, r, c = await _get_first_cube(migrate_pool, unit_id)

    with pytest.raises((psycopg.errors.CheckViolation, Exception)) as exc_info:
        async with migrate_pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.segment_overrides"
                " (unit_id, row, col, label, fraction)"
                " VALUES (%s, %s, %s, %s, %s)",
                (uid, r, c, "TEST_LABEL_OVER_ONE", 1.5),
            )
            await conn.rollback()

    err_str = str(exc_info.value)
    assert "check" in err_str.lower() or "CheckViolation" in type(exc_info.value).__name__, (
        f"Expected a CHECK constraint violation for fraction=1.5, got: {err_str}"
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_fraction_check_rejects_zero(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """DB CHECK rejects segment_overrides.fraction = 0.0 (exclusive lower bound)."""
    import psycopg

    unit_id = await _get_unit_id(migrate_pool)
    uid, r, c = await _get_first_cube(migrate_pool, unit_id)

    with pytest.raises((psycopg.errors.CheckViolation, Exception)) as exc_info:
        async with migrate_pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.segment_overrides"
                " (unit_id, row, col, label, fraction)"
                " VALUES (%s, %s, %s, %s, %s)",
                (uid, r, c, "TEST_LABEL_ZERO", 0.0),
            )
            await conn.rollback()

    err_str = str(exc_info.value)
    assert "check" in err_str.lower() or "CheckViolation" in type(exc_info.value).__name__, (
        f"Expected a CHECK constraint violation for fraction=0.0, got: {err_str}"
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_fraction_check_accepts_boundary(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """DB CHECK accepts segment_overrides.fraction = 1.0 (inclusive upper bound)."""
    unit_id = await _get_unit_id(migrate_pool)
    uid, r, c = await _get_first_cube(migrate_pool, unit_id)

    # Use a unique label name to avoid collision with other tests
    test_label = "TEST_LABEL_BOUNDARY_1_0"
    async with migrate_pool.connection() as conn:
        # Ensure clean state
        await conn.execute(
            "DELETE FROM gruvax.segment_overrides"
            " WHERE unit_id=%s AND row=%s AND col=%s AND label=%s",
            (uid, r, c, test_label),
        )
        await conn.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (unit_id, row, col, label, fraction)"
            " VALUES (%s, %s, %s, %s, %s)",
            (uid, r, c, test_label, 1.0),
        )
        # Clean up
        await conn.execute(
            "DELETE FROM gruvax.segment_overrides"
            " WHERE unit_id=%s AND row=%s AND col=%s AND label=%s",
            (uid, r, c, test_label),
        )
        await conn.commit()


# ── boundary_history.source CHECK tests ──────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_source_check_accepts_cut_insert(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """boundary_history.source='cut_insert' is accepted after migration 0005."""
    import uuid

    unit_id = await _get_unit_id(migrate_pool)
    uid, r, c = await _get_first_cube(migrate_pool, unit_id)
    change_set_id = str(uuid.uuid4())

    async with migrate_pool.connection() as conn:
        # Get current boundary state for prev_* columns
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT first_label, first_catalog, is_empty"
                " FROM gruvax.cube_boundaries"
                " WHERE unit_id=%s AND row=%s AND col=%s",
                (uid, r, c),
            )
            row = await cur.fetchone()

        if row is None:
            pytest.skip("No cube found for history test")

        first_label, first_catalog, is_empty = row
        await conn.execute(
            "INSERT INTO gruvax.boundary_history"
            " (change_set_id, unit_id, row, col,"
            "  prev_first_label, prev_first_catalog, prev_is_empty,"
            "  new_first_label, new_first_catalog, new_is_empty, source)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                change_set_id,
                uid,
                r,
                c,
                first_label,
                first_catalog,
                is_empty,
                first_label,
                first_catalog,
                is_empty,
                "cut_insert",
            ),
        )
        # Clean up
        await conn.execute(
            "DELETE FROM gruvax.boundary_history WHERE change_set_id = %s",
            (change_set_id,),
        )
        await conn.commit()


@pytest.mark.asyncio(loop_scope="module")
async def test_source_check_rejects_unknown_source(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """boundary_history.source rejects values outside the allowed set."""
    import uuid

    import psycopg

    unit_id = await _get_unit_id(migrate_pool)
    uid, r, c = await _get_first_cube(migrate_pool, unit_id)
    change_set_id = str(uuid.uuid4())

    async with migrate_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT first_label, first_catalog, is_empty"
                " FROM gruvax.cube_boundaries"
                " WHERE unit_id=%s AND row=%s AND col=%s",
                (uid, r, c),
            )
            row = await cur.fetchone()

        if row is None:
            pytest.skip("No cube found for history test")

        first_label, first_catalog, is_empty = row

    with pytest.raises((psycopg.errors.CheckViolation, Exception)) as exc_info:
        async with migrate_pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.boundary_history"
                " (change_set_id, unit_id, row, col,"
                "  prev_first_label, prev_first_catalog, prev_is_empty,"
                "  new_first_label, new_first_catalog, new_is_empty, source)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    change_set_id,
                    uid,
                    r,
                    c,
                    first_label,
                    first_catalog,
                    is_empty,
                    first_label,
                    first_catalog,
                    is_empty,
                    "invalid_source",
                ),
            )
            await conn.rollback()

    err_str = str(exc_info.value)
    assert "check" in err_str.lower() or "CheckViolation" in type(exc_info.value).__name__, (
        f"Expected CHECK violation for source='invalid_source', got: {err_str}"
    )


# ── Round-trip test: downgrade -1 → upgrade head ─────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_0005_round_trip_down_up(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0005 round-trips clean: downgrade to 0004 then upgrade to head.

    Uses subprocess to invoke alembic to test the actual migration execution
    (the same way CI would run it) rather than calling the Python API directly.
    The test validates the final schema state after re-upgrade: segment_overrides
    must be present and last_label must be absent (same as the other schema tests).

    Note: 'alembic downgrade base' is NOT used here because downgrade of migration
    0001 has a pre-existing dependency issue (pg_trgm in gruvax schema) unrelated
    to migration 0005. The 0005-specific round-trip (downgrade -1 / upgrade head)
    is the meaningful test for this plan.
    """
    import subprocess
    import sys

    # Downgrade one step (0005 → 0004)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "-1"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic downgrade -1 failed:\n{result.stdout}\n{result.stderr}"

    # Verify segment_overrides is gone after downgrade
    exists_after_down = await _table_exists(migrate_pool, "segment_overrides")
    assert not exists_after_down, (
        "segment_overrides should NOT exist after downgrading from 0005 to 0004"
    )

    # Upgrade back to head (0004 → 0005)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade head failed:\n{result.stdout}\n{result.stderr}"

    # Verify final schema state is correct
    exists_after_up = await _table_exists(migrate_pool, "segment_overrides")
    assert exists_after_up, "segment_overrides should exist after re-upgrading to head"
    last_label_absent = not (await _column_exists(migrate_pool, "cube_boundaries", "last_label"))
    assert last_label_absent, (
        "last_label should NOT exist in cube_boundaries after re-upgrading to head"
    )

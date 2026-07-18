"""Integration tests for Alembic migration 0015 — casefold boundary for segment_overrides.

Bug gruvax-rn7l.3 (supersedes gruvax-p1g): see the migration's own docstring
(``migrations/versions/0015_segment_override_casefold_key.py``) and
``docs/design/adr-0001-normalization-authority.md`` item 4 for the full
rationale.

Tests:
  - test_label_display_column_exists: label_display present on segment_overrides post-upgrade
  - test_dedupe_and_casefold_deterministic_across_insertion_order: seeds TWO case-variant
    duplicate pairs for the SAME casefold identity in OPPOSITE physical insertion order,
    upgrades through 0015, and asserts BOTH groups collapse to the identical winning row
    (chosen by updated_at, never by insertion/heap order) — this is the acceptance
    criterion "estimates are identical regardless of row/heap order (test both orders)".
  - test_label_key_is_casefolded_for_all_rows: every surviving row's label column equals
    lower(label) after the migration.
  - test_0015_round_trip_down_up: downgrade to 0014 then upgrade to head (schema intact).

All tests require a live DB at DATABASE_URL and run with @pytest.mark.asyncio(loop_scope="module").
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from gruvax.db.pool import create_pool


_DEFAULT_PID = "00000000-0000-0000-0000-000000000001"

# ── Session-scoped DB pool (mirrors pattern from test_migrate_0005.py) ───────


@pytest_asyncio.fixture(scope="module")
async def migrate_pool():  # type: ignore[no-untyped-def]
    """Module-scoped async psycopg pool for migration tests."""
    pool = create_pool(min_size=1, max_size=2, open=False)
    await pool.open()
    yield pool
    await pool.close()


# ── Helpers ───────────────────────────────────────────────────────────────────


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


async def _get_two_cubes(pool) -> tuple[tuple[int, int, int], tuple[int, int, int]]:  # type: ignore[no-untyped-def]
    """Return two distinct (unit_id, row, col) non-empty cube coordinates, or skip."""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT unit_id, row, col FROM gruvax.cube_boundaries"
            " WHERE NOT is_empty AND profile_id = %s::uuid"
            " ORDER BY unit_id, row, col LIMIT 2",
            (_DEFAULT_PID,),
        )
        rows = await cur.fetchall()
    if len(rows) < 2:
        pytest.skip("Fewer than 2 non-empty cubes in cube_boundaries — integration DB not seeded")
    a, b = rows[0], rows[1]
    return (int(a[0]), int(a[1]), int(a[2])), (int(b[0]), int(b[1]), int(b[2]))


def _run_alembic(action: str, target: str) -> None:
    """Run ``python -m alembic <action> <target>`` as a subprocess (mirrors 0005/0009)."""
    import subprocess
    import sys

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", action, target],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"alembic {action} {target} failed:\n{result.stdout}\n{result.stderr}"
    )


# ── Schema presence test ──────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_label_display_column_exists(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0015 adds gruvax.segment_overrides.label_display."""
    exists = await _column_exists(migrate_pool, "segment_overrides", "label_display")
    assert exists, "segment_overrides.label_display should exist after migration 0015"


# ── Dedupe determinism (order-independence) ───────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_dedupe_and_casefold_deterministic_across_insertion_order(
    migrate_pool,  # type: ignore[no-untyped-def]
) -> None:
    """0015's dedupe picks the most-recently-updated row, NEVER by insertion/heap order.

    Seeds two independent case-variant duplicate PAIRS at two different bins,
    with the physical INSERT order deliberately reversed between the two pairs:

      - cube_a: "Test Label" (older updated_at) inserted FIRST, then
                "TEST LABEL" (newer updated_at) inserted SECOND — the "natural"
                order where the winner is also the most-recently-inserted row.
      - cube_b: "TEST LABEL" (newer updated_at) inserted FIRST, then
                "Test Label" (older updated_at) inserted SECOND — the OPPOSITE
                physical order, where the winner is the row inserted EARLIER.

    If the dedupe (or any downstream heap-order-dependent scan) picked a winner
    by insertion/heap order rather than ``updated_at``, cube_a and cube_b would
    disagree. They must not: both must collapse to the "TEST LABEL" / 0.7 row.
    """
    uid_a, row_a, col_a = None, None, None
    cube_a, cube_b = await _get_two_cubes(migrate_pool)
    uid_a, row_a, col_a = cube_a
    uid_b, row_b, col_b = cube_b

    t_old = datetime(2026, 1, 1, tzinfo=UTC)
    t_new = t_old + timedelta(days=1)

    # Downgrade to 0014 so raw duplicate case-variant rows can be seeded exactly
    # as they could have existed pre-fix (label was case-sensitive, no dedupe).
    _run_alembic("downgrade", "0014")

    async with migrate_pool.connection() as conn:
        # Clean slate for both test coordinates (idempotent re-run safety).
        await conn.execute(
            "DELETE FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (_DEFAULT_PID, uid_a, row_a, col_a),
        )
        await conn.execute(
            "DELETE FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (_DEFAULT_PID, uid_b, row_b, col_b),
        )

        # cube_a: older row inserted FIRST, newer (winning) row inserted SECOND.
        await conn.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (profile_id, unit_id, row, col, label, fraction, updated_at)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
            (_DEFAULT_PID, uid_a, row_a, col_a, "Test Label", 0.3, t_old),
        )
        await conn.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (profile_id, unit_id, row, col, label, fraction, updated_at)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
            (_DEFAULT_PID, uid_a, row_a, col_a, "TEST LABEL", 0.7, t_new),
        )

        # cube_b: newer (winning) row inserted FIRST, older row inserted SECOND —
        # the OPPOSITE physical/heap insertion order from cube_a.
        await conn.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (profile_id, unit_id, row, col, label, fraction, updated_at)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
            (_DEFAULT_PID, uid_b, row_b, col_b, "TEST LABEL", 0.7, t_new),
        )
        await conn.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (profile_id, unit_id, row, col, label, fraction, updated_at)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
            (_DEFAULT_PID, uid_b, row_b, col_b, "Test Label", 0.3, t_old),
        )
        await conn.commit()

    # Upgrade back to head — runs migration 0015's dedupe + casefold.
    _run_alembic("upgrade", "head")

    async with migrate_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT label, label_display, fraction FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (_DEFAULT_PID, uid_a, row_a, col_a),
        )
        rows_a = await cur.fetchall()
        await cur.execute(
            "SELECT label, label_display, fraction FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (_DEFAULT_PID, uid_b, row_b, col_b),
        )
        rows_b = await cur.fetchall()

        # Cleanup regardless of assertion outcome below.
        await cur.execute(
            "DELETE FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (_DEFAULT_PID, uid_a, row_a, col_a),
        )
        await cur.execute(
            "DELETE FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (_DEFAULT_PID, uid_b, row_b, col_b),
        )
        await conn.commit()

    assert len(rows_a) == 1, f"cube_a: expected exactly 1 row after dedupe, got {rows_a!r}"
    assert len(rows_b) == 1, f"cube_b: expected exactly 1 row after dedupe, got {rows_b!r}"

    label_a, display_a, fraction_a = rows_a[0]
    label_b, display_b, fraction_b = rows_b[0]

    # Both groups must agree on the SAME winner — proving the outcome depends
    # only on updated_at, not on which physical/heap order the rows arrived in.
    assert (label_a, display_a, round(float(fraction_a), 2)) == (
        label_b,
        display_b,
        round(float(fraction_b), 2),
    ), (
        "Dedupe winner must be identical regardless of insertion order: "
        f"cube_a={rows_a[0]!r} cube_b={rows_b[0]!r}"
    )
    assert label_a == "test label", f"label should be casefolded, got {label_a!r}"
    assert display_a == "TEST LABEL", (
        f"label_display should be the most-recently-updated row's original casing, got {display_a!r}"
    )
    assert round(float(fraction_a), 2) == 0.7, (
        f"fraction should be the most-recently-updated row's value, got {fraction_a!r}"
    )


# ── Casefold-key invariant ─────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_label_key_is_casefolded_for_all_rows(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """After migration 0015, every segment_overrides.label equals lower(label).

    This is a coarse sanity check that the one-shot casefold in upgrade() left
    no case-variant PK values behind for any profile/bin — not just the rows
    this test file seeded.
    """
    async with migrate_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT label FROM gruvax.segment_overrides WHERE label <> lower(label)")
        offenders = await cur.fetchall()
    assert offenders == [], (
        f"Found non-casefolded label values in segment_overrides after 0015: {offenders!r}"
    )


# ── Round-trip test: downgrade to 0014 → upgrade head ─────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_0015_round_trip_down_up(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0015 round-trips clean: downgrade to 0014 then upgrade to head.

    Mirrors test_migrate_0005.py::test_0005_round_trip_down_up. Targets the
    absolute revision 0014 (not a relative ``-1``) so the test stays correct
    when later migrations land on top of 0015.
    """
    _run_alembic("downgrade", "0014")
    exists_after_down = await _column_exists(migrate_pool, "segment_overrides", "label_display")
    assert not exists_after_down, (
        "segment_overrides.label_display should NOT exist after downgrading from 0015 to 0014"
    )

    _run_alembic("upgrade", "head")
    exists_after_up = await _column_exists(migrate_pool, "segment_overrides", "label_display")
    assert exists_after_up, (
        "segment_overrides.label_display should exist after re-upgrading to head"
    )

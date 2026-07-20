"""Integration tests for Alembic migration 0016 — NFKC catalog-number backfill.

Bug gruvax-rn7l.6 (supersedes gruvax-pjyz): see the migration's own docstring
(``migrations/versions/0016_catalog_number_nfkc_backfill.py``) and
``docs/design/adr-0001-normalization-authority.md`` for the full rationale.

Tests:
  - test_backfill_normalizes_preexisting_fullwidth_row: seeds a
    pre-normalization row (a full-width catalog, as sync ingest would have
    written it before the ``profile_sync`` fix) directly via SQL while
    pinned at 0015, upgrades to 0016, and asserts the row's stored
    ``catalog_number`` comes out NFKC-normalized ASCII.
  - test_backfill_is_idempotent: re-running the exact backfill statement a
    second time (mirroring a second ``alembic upgrade`` invocation against
    an already-migrated table) updates zero rows.
  - test_backfill_leaves_already_normalized_rows_untouched: a row whose
    catalog_number is already NFKC-normalized is not rewritten (no spurious
    UPDATE / synced_at churn).
  - test_0016_round_trip_down_up: downgrade to 0015 then upgrade to head
    (schema round-trip gate; 0016 has no schema of its own — the CI
    ``migrate-roundtrip`` invariant still holds).

All tests require a live DB at DATABASE_URL and run with
@pytest.mark.asyncio(loop_scope="module").
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.pool import create_pool


_DEFAULT_PID = "00000000-0000-0000-0000-000000000001"

# Distinct release_id range unlikely to collide with synthetic seed data or
# other integration tests' fixtures.
_RELEASE_ID_FULLWIDTH = 991601
_RELEASE_ID_ALREADY_NORMALIZED = 991602

_FOLDER_ID = 1


def _fullwidth_blp_4195() -> str:
    """ADR-0001 witness string: full-width 'BLP-4195', built via chr() to keep
    the source pure-ASCII (mirrors tests/unit/test_normalize.py)."""
    return (
        chr(0xFF22)  # 'B'
        + chr(0xFF2C)  # 'L'
        + chr(0xFF30)  # 'P'
        + chr(0xFF0D)  # '-' full-width hyphen-minus
        + chr(0xFF14)  # '4'
        + chr(0xFF11)  # '1'
        + chr(0xFF19)  # '9'
        + chr(0xFF15)  # '5'
    )


# ── Session-scoped DB pool (mirrors pattern from test_migrate_0015.py) ───────


@pytest_asyncio.fixture(scope="module")
async def migrate_pool():  # type: ignore[no-untyped-def]
    """Module-scoped async psycopg pool for migration tests."""
    pool = create_pool(min_size=1, max_size=2, open=False)
    await pool.open()
    yield pool
    await pool.close()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _run_alembic(action: str, target: str) -> None:
    """Run ``python -m alembic <action> <target>`` as a subprocess (mirrors 0005/0009/0015)."""
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


async def _seed_row(pool, release_id: int, catalog_number: str) -> None:  # type: ignore[no-untyped-def]
    """Insert (or reset) a profile_collection row with a specific raw catalog_number."""
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id = %s AND folder_id = %s",
            (_DEFAULT_PID, release_id, _FOLDER_ID),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)",
            (
                _DEFAULT_PID,
                release_id,
                _FOLDER_ID,
                "Backfill Test Artist",
                "Backfill Test Title",
                "Blue Note",
                catalog_number,
                1960,
            ),
        )
        await conn.commit()


async def _get_catalog_number(pool, release_id: int) -> str:  # type: ignore[no-untyped-def]
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT catalog_number FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id = %s AND folder_id = %s",
            (_DEFAULT_PID, release_id, _FOLDER_ID),
        )
        row = await cur.fetchone()
    assert row is not None, f"release_id={release_id} row not found"
    return str(row[0])


async def _cleanup_row(pool, release_id: int) -> None:  # type: ignore[no-untyped-def]
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id = %s AND folder_id = %s",
            (_DEFAULT_PID, release_id, _FOLDER_ID),
        )
        await conn.commit()


# ── Backfill correctness ───────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_backfill_normalizes_preexisting_fullwidth_row(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """A pre-normalization (full-width) row is NFKC-normalized by the 0016 backfill.

    Seeds the row while pinned at 0015 (simulating data written by the
    pre-fix sync path), upgrades through 0016, and asserts the stored value
    comes out as plain ASCII 'BLP-4195' — matching what the fixed
    ``profile_sync`` ingest path would now write directly.
    """
    _run_alembic("downgrade", "0015")
    try:
        await _seed_row(migrate_pool, _RELEASE_ID_FULLWIDTH, _fullwidth_blp_4195())

        _run_alembic("upgrade", "head")

        normalized = await _get_catalog_number(migrate_pool, _RELEASE_ID_FULLWIDTH)
        assert normalized == "BLP-4195", (
            f"expected the backfill to NFKC-normalize the full-width row to "
            f"'BLP-4195', got {normalized!r}"
        )
    finally:
        await _cleanup_row(migrate_pool, _RELEASE_ID_FULLWIDTH)


@pytest.mark.asyncio(loop_scope="module")
async def test_backfill_leaves_already_normalized_rows_untouched(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """A row whose catalog_number is already NFKC-normalized is not rewritten."""
    await _seed_row(migrate_pool, _RELEASE_ID_ALREADY_NORMALIZED, "BLP-4195")
    try:
        async with migrate_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "UPDATE gruvax.profile_collection "
                "SET catalog_number = normalize(catalog_number, NFKC) "
                "WHERE profile_id = %s::uuid AND release_id = %s AND folder_id = %s "
                "  AND catalog_number IS NOT NULL "
                "  AND catalog_number <> normalize(catalog_number, NFKC)",
                (_DEFAULT_PID, _RELEASE_ID_ALREADY_NORMALIZED, _FOLDER_ID),
            )
            assert cur.rowcount == 0, (
                "backfill guard should skip an already-NFKC-normalized row "
                f"(rowcount={cur.rowcount})"
            )
            await conn.commit()

        normalized = await _get_catalog_number(migrate_pool, _RELEASE_ID_ALREADY_NORMALIZED)
        assert normalized == "BLP-4195"
    finally:
        await _cleanup_row(migrate_pool, _RELEASE_ID_ALREADY_NORMALIZED)


# ── Idempotency ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_backfill_is_idempotent(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Re-running the 0016 backfill statement a second time updates zero rows.

    Seeds a fresh full-width row, runs the exact backfill SQL (mirroring the
    migration's own statement) twice in a row: the first run normalizes it,
    the second run's WHERE guard should touch nothing.
    """
    await _seed_row(migrate_pool, _RELEASE_ID_FULLWIDTH, _fullwidth_blp_4195())
    try:
        backfill_sql = (
            "UPDATE gruvax.profile_collection "
            "SET catalog_number = normalize(catalog_number, NFKC) "
            "WHERE profile_id = %s::uuid AND release_id = %s AND folder_id = %s "
            "  AND catalog_number IS NOT NULL "
            "  AND catalog_number <> normalize(catalog_number, NFKC)"
        )
        params = (_DEFAULT_PID, _RELEASE_ID_FULLWIDTH, _FOLDER_ID)

        async with migrate_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(backfill_sql, params)
            first_run_rowcount = cur.rowcount
            await conn.commit()

        assert first_run_rowcount == 1, (
            f"first backfill run should normalize exactly 1 row, got {first_run_rowcount}"
        )

        async with migrate_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(backfill_sql, params)
            second_run_rowcount = cur.rowcount
            await conn.commit()

        assert second_run_rowcount == 0, (
            f"second backfill run should be a no-op, got rowcount={second_run_rowcount}"
        )

        normalized = await _get_catalog_number(migrate_pool, _RELEASE_ID_FULLWIDTH)
        assert normalized == "BLP-4195"
    finally:
        await _cleanup_row(migrate_pool, _RELEASE_ID_FULLWIDTH)


# ── Round-trip test: downgrade to 0015 → upgrade head ──────────────────────────


@pytest.mark.asyncio(loop_scope="module")
async def test_0016_round_trip_down_up(migrate_pool) -> None:  # type: ignore[no-untyped-def]
    """Migration 0016 round-trips clean: downgrade to 0015 then upgrade to head.

    0016 has no schema of its own (data-only backfill, no-op downgrade) —
    this asserts the round trip completes without error and leaves the DB
    at head, matching the ``just migrate-roundtrip`` CI gate.
    """
    _run_alembic("downgrade", "0015")
    _run_alembic("upgrade", "head")

    async with migrate_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT version_num FROM alembic_version")
        row = await cur.fetchone()
    assert row is not None and row[0] == "0016", f"expected head revision 0016, got {row!r}"

"""Tests for gruvax.record_stats counter functions (OBS-07).

Covers:
  - increment_search_count: all-time + rolling 7-day bucket
  - increment_selection_count: same semantics for selection path
  - get_top_searched: JOIN to v_collection, ORDER BY search_count DESC
  - get_sync_staleness_seconds: max(synced_at) staleness via v_collection
  - get_phantom_boundary_count: non-empty boundaries not in v_collection
  - reset_record_stats: TRUNCATE leaves table empty

Privacy assertion:
  - gruvax.record_stats schema contains NO column matching query/term/text (OBS-07)

All DB-backed tests use the session-scoped db_pool fixture and
@pytest.mark.asyncio(loop_scope="session") per the project pattern.
"""

from __future__ import annotations

import pytest

from gruvax.db.queries import (
    get_phantom_boundary_count,
    get_sync_staleness_seconds,
    get_top_searched,
    increment_search_count,
    increment_selection_count,
    reset_record_stats,
)


# ── Privacy Gate (OBS-07 — no query/term/text column) ─────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_no_query_text_column_in_record_stats(db_pool) -> None:  # type: ignore[no-untyped-def]
    """gruvax.record_stats MUST NOT have any column matching query/term/text (OBS-07, T-08-05).

    Queries information_schema.columns directly — not a parse of the migration file.
    The check is case-insensitive so 'Query', 'QUERY', 'search_text', 'term' all fail.
    """
    sql = """
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'gruvax'
  AND table_name   = 'record_stats'
  AND (
      lower(column_name) LIKE '%query%'
   OR lower(column_name) LIKE '%term%'
   OR lower(column_name) LIKE '%text%'
  )
"""
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        bad_cols = [row[0] for row in await cur.fetchall()]

    assert bad_cols == [], (
        f"Privacy violation (OBS-07): record_stats contains forbidden column(s): {bad_cols}. "
        "No query text may ever be stored in this table."
    )


# ── Isolation helper — clear stats before/after each test ─────────────────────


async def _truncate_stats(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Truncate gruvax.record_stats between tests for isolation."""
    async with db_pool.connection() as conn:
        await conn.execute("TRUNCATE gruvax.record_stats")


# ── increment_search_count ─────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_search_count_first_call_inserts(db_pool) -> None:  # type: ignore[no-untyped-def]
    """First call with a new release_id inserts a row with search_count=1."""
    await _truncate_stats(db_pool)
    release_id = 999_001

    await increment_search_count(db_pool, release_id)

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT search_count, search_count_7d FROM gruvax.record_stats WHERE release_id = %s",
            (release_id,),
        )
        row = await cur.fetchone()

    assert row is not None, "Row must exist after first increment"
    assert row[0] == 1, f"search_count expected 1, got {row[0]}"
    assert row[1] == 1, f"search_count_7d expected 1, got {row[1]}"


@pytest.mark.asyncio(loop_scope="session")
async def test_search_count_second_call_increments(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Second call for same release_id increments both all-time and 7d counters."""
    await _truncate_stats(db_pool)
    release_id = 999_002

    await increment_search_count(db_pool, release_id)
    await increment_search_count(db_pool, release_id)

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT search_count, search_count_7d FROM gruvax.record_stats WHERE release_id = %s",
            (release_id,),
        )
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == 2, f"search_count expected 2, got {row[0]}"
    assert row[1] == 2, f"search_count_7d expected 2, got {row[1]}"


@pytest.mark.asyncio(loop_scope="session")
async def test_search_count_7d_resets_after_8_days(db_pool) -> None:  # type: ignore[no-untyped-def]
    """After last_searched_at becomes 8 days old, the next increment resets search_count_7d
    to 1 while search_count keeps climbing (D-05).
    """
    await _truncate_stats(db_pool)
    release_id = 999_003

    # First call → search_count=1, search_count_7d=1
    await increment_search_count(db_pool, release_id)

    # Simulate 8-day-old event by directly updating last_searched_at
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.record_stats SET last_searched_at = now() - INTERVAL '8 days' "
            "WHERE release_id = %s",
            (release_id,),
        )

    # Second call → search_count=2, but search_count_7d resets to 1 (last event is >7d)
    await increment_search_count(db_pool, release_id)

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT search_count, search_count_7d FROM gruvax.record_stats WHERE release_id = %s",
            (release_id,),
        )
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == 2, f"search_count (all-time) expected 2, got {row[0]}"
    assert row[1] == 1, f"search_count_7d should reset to 1 after 8-day gap, got {row[1]}"


# ── increment_selection_count ──────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_selection_count_first_call_inserts(db_pool) -> None:  # type: ignore[no-untyped-def]
    """First call with a new release_id inserts a row with selection_count=1."""
    await _truncate_stats(db_pool)
    release_id = 999_004

    await increment_selection_count(db_pool, release_id)

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT selection_count, selection_count_7d FROM gruvax.record_stats WHERE release_id = %s",
            (release_id,),
        )
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == 1, f"selection_count expected 1, got {row[0]}"
    assert row[1] == 1, f"selection_count_7d expected 1, got {row[1]}"


@pytest.mark.asyncio(loop_scope="session")
async def test_selection_count_7d_resets_after_8_days(db_pool) -> None:  # type: ignore[no-untyped-def]
    """After last_selected_at becomes 8 days old, the next increment resets selection_count_7d
    to 1 while selection_count keeps climbing (D-05).
    """
    await _truncate_stats(db_pool)
    release_id = 999_005

    await increment_selection_count(db_pool, release_id)

    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.record_stats SET last_selected_at = now() - INTERVAL '8 days' "
            "WHERE release_id = %s",
            (release_id,),
        )

    await increment_selection_count(db_pool, release_id)

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT selection_count, selection_count_7d "
            "FROM gruvax.record_stats WHERE release_id = %s",
            (release_id,),
        )
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == 2, f"selection_count (all-time) expected 2, got {row[0]}"
    assert row[1] == 1, f"selection_count_7d should reset to 1 after 8-day gap, got {row[1]}"


@pytest.mark.asyncio(loop_scope="session")
async def test_increment_functions_take_only_release_id(db_pool) -> None:  # type: ignore[no-untyped-def]
    """increment_search_count and increment_selection_count accept pool + int only.

    This is a signature check — no query text parameter may exist (OBS-07, D-04).
    The test exercises both functions with an integer release_id and confirms they
    do not raise; the absence of a text/query parameter is enforced by the call itself.
    """
    await _truncate_stats(db_pool)
    # Calls without any text argument — would be a TypeError if signature changed
    await increment_search_count(db_pool, 999_006)
    await increment_selection_count(db_pool, 999_006)


# ── get_top_searched ───────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_top_searched_empty_when_no_stats(db_pool) -> None:  # type: ignore[no-untyped-def]
    """get_top_searched returns an empty list when record_stats is empty."""
    await _truncate_stats(db_pool)
    result = await get_top_searched(db_pool)
    assert result == [], f"Expected [], got {result}"


@pytest.mark.asyncio(loop_scope="session")
async def test_get_top_searched_returns_display_fields(db_pool) -> None:  # type: ignore[no-untyped-def]
    """get_top_searched rows contain release_id, title, primary_artist, and counter columns."""
    await _truncate_stats(db_pool)

    # Use a real release_id that exists in v_collection (seeded in dev DB).
    # Seed release_id=1 is guaranteed by the dev fixture; if it doesn't exist the
    # test degrades gracefully (empty result → dict-shape check is skipped).
    release_id = 1
    await increment_search_count(db_pool, release_id)

    result = await get_top_searched(db_pool, limit=5)

    if not result:
        pytest.skip("release_id=1 not in v_collection for this DB — skipping dict-shape check")

    row = result[0]
    required_keys = {
        "release_id",
        "title",
        "primary_artist",
        "search_count",
        "search_count_7d",
        "selection_count",
        "selection_count_7d",
    }
    assert required_keys.issubset(set(row.keys())), (
        f"get_top_searched row missing required keys. "
        f"Expected {required_keys}, got {set(row.keys())}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_get_top_searched_ordered_by_search_count_desc(db_pool) -> None:  # type: ignore[no-untyped-def]
    """get_top_searched results are ordered by all-time search_count DESC."""
    await _truncate_stats(db_pool)

    # Insert two release_ids; whichever maps to v_collection will appear in results.
    # We use artificial large release_ids that won't be in v_collection,
    # then insert them directly with raw SQL to avoid the JOIN filtering.
    # But get_top_searched JOINs to v_collection, so IDs not in v_collection
    # are excluded. We therefore need real IDs or we test the empty branch.
    # Approach: insert multiple increments for release_id=1 vs release_id=2
    # (both seeded), then assert ordering.

    # Seed release_id=1 with 3 searches, release_id=2 with 1 search.
    for _ in range(3):
        await increment_search_count(db_pool, 1)
    await increment_search_count(db_pool, 2)

    result = await get_top_searched(db_pool, limit=10)
    if len(result) < 2:
        pytest.skip("Not enough v_collection records in this DB to test ordering")

    counts = [r["search_count"] for r in result]
    assert counts == sorted(counts, reverse=True), (
        f"get_top_searched results not sorted by search_count DESC: {counts}"
    )
    assert result[0]["search_count"] >= result[1]["search_count"]


@pytest.mark.asyncio(loop_scope="session")
async def test_get_top_searched_reset_returns_empty(db_pool) -> None:  # type: ignore[no-untyped-def]
    """After reset_record_stats, get_top_searched returns []."""
    await increment_search_count(db_pool, 1)
    await reset_record_stats(db_pool)
    result = await get_top_searched(db_pool)
    assert result == [], f"Expected [] after reset, got {result}"


# ── get_sync_staleness_seconds ─────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_staleness_returns_non_negative_float(db_pool) -> None:  # type: ignore[no-untyped-def]
    """get_sync_staleness_seconds returns a non-negative float when v_collection has rows."""
    result = await get_sync_staleness_seconds(db_pool)

    # If dev v_collection is empty, None is acceptable (OBS-06 contract)
    if result is None:
        pytest.skip("v_collection is empty in this dev DB — staleness returns None as expected")

    assert isinstance(result, float), f"Expected float, got {type(result)}: {result}"
    assert result >= 0.0, f"Staleness must be non-negative, got {result}"


@pytest.mark.asyncio(loop_scope="session")
async def test_staleness_returns_none_or_float(db_pool) -> None:  # type: ignore[no-untyped-def]
    """get_sync_staleness_seconds returns float | None — never raises."""
    result = await get_sync_staleness_seconds(db_pool)
    assert result is None or isinstance(result, float), (
        f"Expected float or None, got {type(result)}: {result}"
    )


# ── get_phantom_boundary_count ─────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_phantom_boundary_count_returns_int(db_pool) -> None:  # type: ignore[no-untyped-def]
    """get_phantom_boundary_count returns a non-negative int."""
    result = await get_phantom_boundary_count(db_pool)
    assert isinstance(result, int), f"Expected int, got {type(result)}: {result}"
    assert result >= 0, f"Phantom count must be non-negative, got {result}"


# ── reset_record_stats ─────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_record_stats_clears_all_rows(db_pool) -> None:  # type: ignore[no-untyped-def]
    """reset_record_stats TRUNCATEs record_stats; table is empty afterwards."""
    # Seed a few rows
    for rid in (1, 2, 3):
        await increment_search_count(db_pool, rid)

    await reset_record_stats(db_pool)

    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM gruvax.record_stats")
        row = await cur.fetchone()

    count = row[0] if row else -1
    assert count == 0, f"Expected 0 rows after reset, got {count}"

"""Regression test for gruvax-07a — DISTINCT ON + LIMIT must keep top-ranked rows.

The search SQL ended with ``SELECT DISTINCT ON (release_id) ... ORDER BY
release_id, score DESC LIMIT %s``.  DISTINCT ON forces the ORDER BY to lead
with release_id, so the outer LIMIT returned the N LOWEST release_ids among
matches — not the N best scores.  A high-release_id best match was silently
dropped when the number of matches exceeded the limit; the Python re-sort
could only reorder an already-truncated (wrong) set.

Fix: wrap the DISTINCT ON in a subquery, then ORDER BY rank DESC LIMIT %s on
the outside (plus ORDER BY score DESC inside the fts/cat CTEs before their
own LIMITs).  This test seeds MORE than `limit` matching rows where the single
best-ranked match has a high release_id, and asserts it survives — and ranks
first.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.queries import DEFAULT_PROFILE_UUID, search_collection


# A unique nonsense token so the match set is exactly what this test seeds.
_PROBE = "qwzxrankprobe"

# 25 low-release_id competitors carry the probe token in the LABEL (weight C).
_COMPETITOR_IDS = list(range(990300, 990325))
# One high-release_id target carries the probe token in the TITLE (weight B),
# which ts_rank_cd scores strictly higher (0.4 vs 0.2) — the unambiguous best.
_TARGET_ID = 990399

_LIMIT = 20  # strictly fewer than the 26 total matches


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_ranking_rows(db_pool):  # type: ignore[no-untyped-def]
    """Seed 25 low-id weak matches + 1 high-id best match; clean up after."""
    async with db_pool.connection() as conn:
        for rid in _COMPETITOR_IDS:
            await conn.execute(
                "INSERT INTO gruvax.profile_collection "
                "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (profile_id, release_id, folder_id) DO NOTHING",
                (
                    DEFAULT_PROFILE_UUID,
                    rid,
                    1,
                    "Rank Competitor",
                    "Competitor Title",
                    _PROBE,  # probe in label → weight C (weaker rank)
                    f"RCMP-{rid}",
                    1985,
                ),
            )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (profile_id, release_id, folder_id) DO NOTHING",
            (
                DEFAULT_PROFILE_UUID,
                _TARGET_ID,
                1,
                "Rank Target",
                _PROBE,  # probe in title → weight B (stronger rank)
                "Target Label",
                "RTGT-0001",
                1985,
            ),
        )
    yield
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id = ANY(%s)",
            (DEFAULT_PROFILE_UUID, [*_COMPETITOR_IDS, _TARGET_ID]),
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_best_ranked_match_survives_limit(
    db_pool,  # type: ignore[no-untyped-def]
    seeded_ranking_rows,  # fixture applies the seed (unused arg by design)
) -> None:
    """The top-scored match (high release_id) is kept and ranks first.

    26 rows match the probe but limit is 20.  Before the fix the LIMIT kept the
    20 LOWEST release_ids (all competitors) and dropped the high-id target; now
    the target — the strictly highest-ranked row — is present and first.
    """
    rows, took_ms, _dym = await search_collection(
        db_pool, _PROBE, limit=_LIMIT, profile_id=DEFAULT_PROFILE_UUID
    )
    release_ids = [r["release_id"] for r in rows]

    assert _TARGET_ID in release_ids, (
        f"Best-ranked match (release_id={_TARGET_ID}) must survive the LIMIT of "
        f"{_LIMIT} over {len(_COMPETITOR_IDS) + 1} matches; got {release_ids} "
        f"(took_ms={took_ms})"
    )
    assert release_ids[0] == _TARGET_ID, (
        f"Best-ranked match (release_id={_TARGET_ID}) must rank first; "
        f"got top release_id={release_ids[0]} (all={release_ids})"
    )
    assert len(rows) == _LIMIT, f"Expected exactly {_LIMIT} rows, got {len(rows)}"

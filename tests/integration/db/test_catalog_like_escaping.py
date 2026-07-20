"""Regression test for gruvax-rn7l.4 — escape LIKE metacharacters in catalog search.

``search_collection``'s Path B (catalog-number prefix match) built its LIKE
pattern by separator-collapsing the raw query with the same
``[\\s\\-_./]+`` regex used to normalize ``catalog_number``, then appending a
trailing ``%``. That regex strips ``_`` (it's a separator) but **not** ``%``,
so a query of ``"%"`` survived collapse untouched and produced the pattern
``"%" || "%"`` — a wildcard-match-all that matched every non-null
``catalog_number`` at the fixed Path B score (0.9), outranking genuine FTS
matches.

Fix (``_catalog_like_pattern`` in ``gruvax.db.queries``): after the same
separator-collapse, backslash-escape ``%``, ``_``, and ``\\`` and bind the
pattern with ``LIKE %s ESCAPE '\\'`` instead of building the pattern in SQL.
Supersedes gruvax-efe.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.queries import DEFAULT_PROFILE_UUID, _catalog_like_pattern, search_collection


# Distinctive release_ids that don't collide with other integration tests'
# synthetic ranges (990100s/990200s/990300s are already in use elsewhere).
_PERCENT_RELEASE_ID = 990401
_PERCENT_CATALOG = "AB%99"

_UNDERSCORE_RELEASE_ID = 990402
_UNDERSCORE_CATALOG = "CD_77"


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_metachar_catalogs(db_pool):  # type: ignore[no-untyped-def]
    """Insert catalog numbers containing literal LIKE metacharacters, clean up after."""
    async with db_pool.connection() as conn:
        for release_id, catalog in (
            (_PERCENT_RELEASE_ID, _PERCENT_CATALOG),
            (_UNDERSCORE_RELEASE_ID, _UNDERSCORE_CATALOG),
        ):
            await conn.execute(
                "INSERT INTO gruvax.profile_collection "
                "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (profile_id, release_id, folder_id) DO NOTHING",
                (
                    DEFAULT_PROFILE_UUID,
                    release_id,
                    1,
                    f"Metachar Artist {release_id}",
                    f"Metachar Title {release_id}",
                    "Metachar Records",
                    catalog,
                    1980,
                ),
            )
    yield
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection "
            "WHERE profile_id = %s::uuid AND release_id IN (%s, %s)",
            (DEFAULT_PROFILE_UUID, _PERCENT_RELEASE_ID, _UNDERSCORE_RELEASE_ID),
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_bare_percent_query_matches_no_catalog_path_rows(
    db_pool,  # type: ignore[no-untyped-def]
) -> None:
    """A query of bare '%' must not wildcard-match-all via the catalog-prefix path.

    Path B stamps a fixed score of 0.9 on every row it matches — assert zero
    such rows come back for the seeded fixture (acceptance criterion 1).
    """
    rows, _took_ms, _dym = await search_collection(
        db_pool, "%", limit=50, profile_id=DEFAULT_PROFILE_UUID
    )
    catalog_path_rows = [r for r in rows if abs((r.get("rank") or 0) - 0.9) < 1e-9]
    assert catalog_path_rows == [], (
        f"query '%' must not match any catalog-path (score 0.9) rows; got "
        f"{[(r['release_id'], r['catalog_number']) for r in catalog_path_rows]}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_literal_percent_in_catalog_number_remains_findable(
    db_pool,  # type: ignore[no-untyped-def]
    seeded_metachar_catalogs,  # fixture applies the seed (unused arg by design)
) -> None:
    """A catalog number containing a literal '%' is still findable by exact query."""
    rows, _took_ms, _dym = await search_collection(
        db_pool, _PERCENT_CATALOG, limit=20, profile_id=DEFAULT_PROFILE_UUID
    )
    release_ids = [r["release_id"] for r in rows]
    assert _PERCENT_RELEASE_ID in release_ids, (
        f"Query {_PERCENT_CATALOG!r} should find release_id={_PERCENT_RELEASE_ID} "
        f"(catalog_number={_PERCENT_CATALOG!r}); got release_ids={release_ids}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_literal_underscore_in_catalog_number_remains_findable(
    db_pool,  # type: ignore[no-untyped-def]
    seeded_metachar_catalogs,  # fixture applies the seed (unused arg by design)
) -> None:
    """A catalog number containing a literal '_' is still findable by exact query."""
    rows, _took_ms, _dym = await search_collection(
        db_pool, _UNDERSCORE_CATALOG, limit=20, profile_id=DEFAULT_PROFILE_UUID
    )
    release_ids = [r["release_id"] for r in rows]
    assert _UNDERSCORE_RELEASE_ID in release_ids, (
        f"Query {_UNDERSCORE_CATALOG!r} should find release_id={_UNDERSCORE_RELEASE_ID} "
        f"(catalog_number={_UNDERSCORE_CATALOG!r}); got release_ids={release_ids}"
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("%", "\\%%"),
        ("BLP 4195", "blp4195%"),
        ("AB%99", "ab\\%99%"),
        ("CD_77", "cd77%"),  # underscore is a separator — collapsed away, not escaped
        ("back\\slash", "back\\\\slash%"),
    ],
)
def test_catalog_like_pattern_escapes_metacharacters(raw: str, expected: str) -> None:
    """Unit-level check of the pattern builder itself (fast, no DB needed)."""
    assert _catalog_like_pattern(raw) == expected

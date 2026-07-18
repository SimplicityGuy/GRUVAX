"""Regression tests for gruvax-w4a7 — accent-insensitive FTS.

The kiosk's ASCII touch keyboard cannot type é/ö, so the ASCII spelling is the
only possible query for an accented artist.  Before migration 0013 the stored
``fts_vector`` and the query-time tsquery both used the bare ``'english'``
config, which preserved accents — so an ASCII query returned zero rows AND (for
short names like Björk / Mötley Crüe) no did-you-mean suggestion.

Migration 0013 introduces the ``gruvax.gruvax_fts`` config (unaccent →
english_stem) on both sides, so accented storage and ASCII queries fold to the
same lexemes.  These tests seed accented artists and assert the ASCII spelling
finds them via ``search_collection``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.queries import DEFAULT_PROFILE_UUID, search_collection


# High release_ids well outside the synthetic seed range (1..3000) so the
# inserts never collide with the module-scoped fixture PK.
_ACCENTED_ROWS = (
    # (release_id, artist, title, label, catalog_number)
    (990101, "Björk", "Accented Artist Bjork", "One Little Indian", "ACC-9101"),
    (990102, "Mötley Crüe", "Accented Artist Motley", "Elektra", "ACC-9102"),
    (990103, "Beyoncé", "Accented Artist Beyonce", "Columbia", "ACC-9103"),
)


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_accented_rows(db_pool):  # type: ignore[no-untyped-def]
    """Insert accented artist rows for the default profile, clean up after."""
    async with db_pool.connection() as conn:
        for release_id, artist, title, label, catalog_number in _ACCENTED_ROWS:
            await conn.execute(
                "INSERT INTO gruvax.profile_collection "
                "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (profile_id, release_id, folder_id) DO NOTHING",
                (DEFAULT_PROFILE_UUID, release_id, 1, artist, title, label, catalog_number, 1990),
            )
    yield
    async with db_pool.connection() as conn:
        for release_id, *_ in _ACCENTED_ROWS:
            await conn.execute(
                "DELETE FROM gruvax.profile_collection "
                "WHERE profile_id = %s::uuid AND release_id = %s",
                (DEFAULT_PROFILE_UUID, release_id),
            )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("query", "expected_release_id"),
    [
        ("Bjork", 990101),
        ("Motley Crue", 990102),
        ("Beyonce", 990103),
    ],
)
async def test_ascii_query_finds_accented_artist(
    db_pool,  # type: ignore[no-untyped-def]
    seeded_accented_rows,  # fixture applies the seed (unused arg by design)
    query: str,
    expected_release_id: int,
) -> None:
    """ASCII spelling (no accents) finds the accented artist via FTS.

    Björk/Bjork, Mötley Crüe/Motley Crue, Beyoncé/Beyonce all fold to the same
    lexemes under gruvax.gruvax_fts, so the record is a real FTS hit — not
    merely a did-you-mean suggestion.
    """
    rows, took_ms, _did_you_mean = await search_collection(
        db_pool, query, limit=20, profile_id=DEFAULT_PROFILE_UUID
    )
    release_ids = [r["release_id"] for r in rows]
    assert expected_release_id in release_ids, (
        f"ASCII query {query!r} should FTS-match the accented artist "
        f"(release_id={expected_release_id}); got release_ids={release_ids} "
        f"(took_ms={took_ms})"
    )

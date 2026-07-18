"""Regression test for gruvax-yd92 — hyphenated catalog found by bare number.

PostgreSQL FTS tokenizes a hyphen as a numeric sign, so before migration 0014
the stored ``fts_vector`` turned ``'ZX-90847'`` into lexemes ``'zx'`` +
``'-90847'`` (a signed int) — the bare number ``'90847'`` did NOT match, while
the space form ``'ZX 90847'`` did.  Hyphenated catalog numbers were silently
omitted from bare-number search (the core ``catalog number → cube`` value).

Migration 0014 separator-normalizes the catalog A-weight before tokenizing, so
``'ZX-90847'`` tokenizes to ``'zx'`` + ``'90847'`` and the bare number finds it
via the catalog branch's C-weighted fts_vector component.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.queries import DEFAULT_PROFILE_UUID, search_collection


# Distinctive catalog whose bare number does not collide with the synthetic
# seed (1000-range) or appear elsewhere in the fixture.
_HYPHEN_RELEASE_ID = 990201
_HYPHEN_CATALOG = "ZX-90847"
_BARE_NUMBER = "90847"


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_hyphen_catalog(db_pool):  # type: ignore[no-untyped-def]
    """Insert a hyphenated-catalog row for the default profile, clean up after."""
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (profile_id, release_id, folder_id) DO NOTHING",
            (
                DEFAULT_PROFILE_UUID,
                _HYPHEN_RELEASE_ID,
                1,
                "Hyphen Catalog Artist",
                "Hyphen Catalog Title",
                "Hyphen Records",
                _HYPHEN_CATALOG,
                1980,
            ),
        )
    yield
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid AND release_id = %s",
            (DEFAULT_PROFILE_UUID, _HYPHEN_RELEASE_ID),
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_bare_number_finds_hyphenated_catalog(
    db_pool,  # type: ignore[no-untyped-def]
    seeded_hyphen_catalog,  # fixture applies the seed (unused arg by design)
) -> None:
    """Bare number '90847' finds the hyphenated 'ZX-90847' record."""
    rows, took_ms, _did_you_mean = await search_collection(
        db_pool, _BARE_NUMBER, limit=20, profile_id=DEFAULT_PROFILE_UUID
    )
    release_ids = [r["release_id"] for r in rows]
    assert _HYPHEN_RELEASE_ID in release_ids, (
        f"Bare number {_BARE_NUMBER!r} should find hyphenated catalog "
        f"{_HYPHEN_CATALOG!r} (release_id={_HYPHEN_RELEASE_ID}); got "
        f"release_ids={release_ids} (took_ms={took_ms})"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_space_form_still_finds_hyphenated_catalog(
    db_pool,  # type: ignore[no-untyped-def]
    seeded_hyphen_catalog,  # fixture applies the seed (unused arg by design)
) -> None:
    """The prefixed 'ZX 90847' form keeps finding the record (no regression)."""
    rows, _took_ms, _dym = await search_collection(
        db_pool, "ZX 90847", limit=20, profile_id=DEFAULT_PROFILE_UUID
    )
    release_ids = [r["release_id"] for r in rows]
    assert _HYPHEN_RELEASE_ID in release_ids, (
        f"Prefixed 'ZX 90847' should still find release_id={_HYPHEN_RELEASE_ID}; got {release_ids}"
    )

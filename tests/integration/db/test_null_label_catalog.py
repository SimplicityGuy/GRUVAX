"""Regression tests for gruvax-jn3: NULL label/catalog rows in profile_collection.

Root cause: ``profile_collection.label`` / ``catalog_number`` are nullable
(Discogs releases routinely lack a catalog number; sync writes NULLs
verbatim — see ``profile_sync._release_to_tuple``). Two query helpers
omitted the ``IS NOT NULL`` guard every sibling helper applies:

  - Defect A: ``find_boundary_near_misses`` — a NULL label or catalog made
    the combined similarity score NULL. Postgres sorts NULLs FIRST on
    ``ORDER BY sim DESC``, so the phantom row landed at position 1, and
    ``float(row[2])`` on ``None`` raised ``TypeError`` — a 500 from what is
    supposed to be the graceful "did you mean" error-handling path.
  - Defect B: ``get_catalogs_for_label`` — a NULL catalog rendered via
    ``str(row[1])`` as the literal string ``"None"``, offered to the admin
    catalog picker as a real option. Picking it round-trips back into
    Defect A (the delivery vehicle for the crash).

Uses only synthetic, made-up labels/catalogs — no real collection data.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.db.queries import (
    DEFAULT_PROFILE_UUID,
    find_boundary_near_misses,
    get_catalogs_for_label,
)


# Release IDs deliberately far outside the synth fixture's range to avoid
# any collision with tests/fixtures/synth_profile_collection.sql.
_NULL_CATALOG_RELEASE_ID = 900_001
_NULL_LABEL_RELEASE_ID = 900_002


@pytest_asyncio.fixture(loop_scope="session")
async def _null_rows(db_pool):  # type: ignore[no-untyped-def]
    """Insert two synthetic NULL-label/-catalog rows, clean up afterward."""
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            "VALUES (%s::uuid, %s, 1, 'Jn3 Test Artist', 'Jn3 Test Title (no catalog)', "
            "        'Jn3 Test Label', NULL, 2020)",
            (DEFAULT_PROFILE_UUID, _NULL_CATALOG_RELEASE_ID),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection "
            "(profile_id, release_id, folder_id, artist, title, label, catalog_number, year) "
            "VALUES (%s::uuid, %s, 1, 'Jn3 Test Artist', 'Jn3 Test Title (no label)', "
            "        NULL, 'JN3TEST-9999', 2020)",
            (DEFAULT_PROFILE_UUID, _NULL_LABEL_RELEASE_ID),
        )
        await conn.commit()
    try:
        yield
    finally:
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.profile_collection "
                "WHERE profile_id = %s::uuid AND release_id = ANY(%s)",
                (DEFAULT_PROFILE_UUID, [_NULL_CATALOG_RELEASE_ID, _NULL_LABEL_RELEASE_ID]),
            )
            await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_find_boundary_near_misses_null_label_no_crash(  # type: ignore[no-untyped-def]
    db_pool, _null_rows
) -> None:
    """Defect A: a NULL-label row with a near-exact catalog match must not
    crash ``find_boundary_near_misses`` with a ``TypeError`` on ``float(None)``.

    The row's catalog_number ("JN3TEST-9999") is an exact trigram match for
    the query below, which is exactly the "OR lets a one-field match pass"
    condition the bug describes: pre-fix, this row entered the result set
    with a NULL combined ``sim`` (NULL label similarity poisons the average),
    sorted first by Postgres's NULLS-FIRST-on-DESC default, and blew up
    ``float(row[2])``.
    """
    # Must not raise (pre-fix: psycopg wraps the underlying TypeError, or the
    # bare float() call inside the try surfaces as TypeError directly).
    results = await find_boundary_near_misses(
        db_pool, "Totally Nonexistent Label Xyz", "JN3TEST-9999"
    )
    # The NULL-label row must be excluded from the candidate set entirely —
    # never surfaced with a None/null-ish label.
    assert all(r["label"] is not None for r in results)


@pytest.mark.asyncio(loop_scope="session")
async def test_find_boundary_near_misses_null_catalog_no_crash(  # type: ignore[no-untyped-def]
    db_pool, _null_rows
) -> None:
    """Mirror of the above with the NULL field on catalog_number instead of label."""
    results = await find_boundary_near_misses(db_pool, "Jn3 Test Label", "anything")
    assert all(r["catalog_number"] is not None for r in results)


@pytest.mark.asyncio(loop_scope="session")
async def test_get_catalogs_for_label_excludes_null_catalog(  # type: ignore[no-untyped-def]
    db_pool, _null_rows
) -> None:
    """Defect B: a NULL catalog_number must never surface as the literal
    string ``"None"`` in the catalog picker's option list.
    """
    results = await get_catalogs_for_label(db_pool, "Jn3 Test Label", DEFAULT_PROFILE_UUID)
    catalogs = [r["catalog_number"] for r in results]
    assert "None" not in catalogs, (
        f"NULL catalog_number leaked as the literal string 'None': {catalogs!r}"
    )
    release_ids = [r["release_id"] for r in results]
    assert _NULL_CATALOG_RELEASE_ID not in release_ids, (
        "the NULL-catalog row must be excluded from the picker entirely"
    )

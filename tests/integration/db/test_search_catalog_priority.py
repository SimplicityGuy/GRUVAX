"""Catalog exact and prefix scores cannot be outranked by repetitive text."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from gruvax.db.queries import search_collection
from tests.integration.db.test_search_correctness import client as client, profile as profile


if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("q", ["BLP 4195", "BLP 41", "blp4195"])
async def test_catalog_beats_repeated_title(
    db_pool: Any, profile: str, client: AsyncClient, q: str
) -> None:
    rows, _, _ = await search_collection(db_pool, q, 20, profile)
    assert rows[0]["release_id"] == 920006
    assert all(row["rank"] <= 1.0 for row in rows)
    response = await client.get("/api/search", params={"q": q, "limit": 1})
    assert response.status_code == 200
    assert response.json()["items"][0]["release_id"] == 920006


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_catalog_beats_prefix(db_pool: Any, profile: str) -> None:
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profile_collection (profile_id, release_id, folder_id, title, catalog_number)"
            " VALUES (%s::uuid, 920008, 1, 'Catalog extension', 'BLP 4195X')",
            (profile,),
        )
        await conn.commit()
    try:
        rows, _, _ = await search_collection(db_pool, "blp4195", 20, profile)
        assert rows[0]["release_id"] == 920006
        scores = {row["release_id"]: row["rank"] for row in rows}
        assert scores[920006] > scores[920008]
    finally:
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid AND release_id = 920008",
                (profile,),
            )
            await conn.commit()

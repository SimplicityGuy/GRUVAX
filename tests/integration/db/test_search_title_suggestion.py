"""Misspelled titles recover through profile-scoped conservative suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest

from gruvax.db.queries import search_collection
from tests.integration.db.test_search_correctness import client as client, profile as profile


if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("q", "expected", "rid"),
    [("Destroyr", "Destroyer", 920004), ("Synchroncity", "Synchronicity", 920005)],
)
async def test_title_typo_recovery(
    db_pool: Any, profile: str, client: AsyncClient, q: str, expected: str, rid: int
) -> None:
    rows, _, suggestion = await search_collection(db_pool, q, 20, profile)
    assert rows == []
    assert suggestion == expected
    response = await client.get("/api/search", params={"q": q})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["did_you_mean"] == expected
    recovered = await client.get("/api/search", params={"q": expected})
    assert recovered.status_code == 200
    assert rid in [row["release_id"] for row in recovered.json()["items"]]
    assert recovered.json()["did_you_mean"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_title_suggestions_do_not_cross_profiles(
    db_pool: Any, profile: str, client: AsyncClient
) -> None:
    other = str(uuid4())
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked) VALUES (%s::uuid, 'Other search profile', %s, TRUE)",
            (other, b""),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection (profile_id, release_id, folder_id, title) VALUES (%s::uuid, 920020, 1, 'XylophonicMoonlight')",
            (other,),
        )
        await conn.commit()
    try:
        response = await client.get("/api/search", params={"q": "XylophonicMoonligh"})
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["did_you_mean"] is None
        rows, _, suggestion = await search_collection(db_pool, "XylophonicMoonligh", 20, other)
        assert rows == []
        assert suggestion == "XylophonicMoonlight"
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (other,))
            await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_unrelated_query_has_no_suggestion(db_pool: Any, profile: str) -> None:
    rows, _, suggestion = await search_collection(db_pool, "QzxvUnknown999", 20, profile)
    assert rows == []
    assert suggestion is None

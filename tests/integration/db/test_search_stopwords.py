"""Empty English tsqueries still find literal artists without self suggestions."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from gruvax.db.queries import did_you_mean_query, search_collection
from tests.integration.db.test_search_correctness import client as client, profile as profile


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("q", "rid"), [("The Who", 920001), ("the the", 920002), ("Was (Not Was)", 920003)]
)
async def test_stopword_artist_found(
    db_pool: Any, profile: str, client: AsyncClient, q: str, rid: int
) -> None:
    rows, _, suggestion = await search_collection(db_pool, q, 20, profile)
    assert [row["release_id"] for row in rows] == [rid]
    assert suggestion is None
    response = await client.get("/api/search", params={"q": q})
    assert response.status_code == 200
    assert [row["release_id"] for row in response.json()["items"]] == [rid]
    assert response.json()["did_you_mean"] is None


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("q", ["The Who", "the who", "THE THE", "Was (Not Was)"])
async def test_suggestion_never_repeats_input(db_pool: Any, profile: str, q: str) -> None:
    suggestion = await did_you_mean_query(db_pool, q, profile)
    assert suggestion is None or suggestion.casefold() != q.casefold()


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("q", ["Who Else", "the unlikely", "The%Who", "NobodyAtAll"])
async def test_literal_artist_fallback_does_not_widen(db_pool: Any, profile: str, q: str) -> None:
    rows, _, _ = await search_collection(db_pool, q, 20, profile)
    assert rows == []


if TYPE_CHECKING:
    from httpx import AsyncClient

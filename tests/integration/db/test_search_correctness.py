"""Real profile-owned collection and HTTP regressions for search correctness."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from gruvax.db.queries import search_collection
from tests.cookies import cookie_header


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def profile(db_pool: Any):  # type: ignore[no-untyped-def]
    pid = str(uuid4())
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked)"
            " VALUES (%s::uuid, 'Search proofs', %s, TRUE)",
            (pid, b""),
        )
        for rid, artist, title, label, catalog in [
            (920001, "The Who", "Tommy", "Track", "TRK-001"),
            (920002, "The The", "Soul Mining", "Some Bizarre", "SB-002"),
            (920003, "Was (Not Was)", "What Up Dog", "Fontana", "FN-003"),
            (920004, "Kiss", "Destroyer", "Casablanca", "CA-004"),
            (920005, "The Police", "Synchronicity", "A&M", "AM-005"),
            (920006, "Catalog Artist", "Genuine Catalog", "Blue Note", "BLP 4195"),
            (920007, "Repetition Artist", "BLP 4195 " * 30, "Other Label", "OTHER-007"),
        ]:
            await conn.execute(
                "INSERT INTO gruvax.profile_collection"
                " (profile_id, release_id, folder_id, artist, title, label, catalog_number)"
                " VALUES (%s::uuid, %s, 1, %s, %s, %s, %s)",
                (pid, rid, artist, title, label, catalog),
            )
        await conn.commit()
    try:
        yield pid
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (pid,))
            await conn.commit()


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def client(profile: str):  # type: ignore[no-untyped-def]
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
            headers=cookie_header({"gruvax_browse_binding": profile}),
        ) as ac,
    ):
        yield ac


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("q", [" ", "\t\n", "-", ".", "/", "_", " -_./ "])
async def test_separator_only_is_empty(
    db_pool: Any, profile: str, client: AsyncClient, q: str
) -> None:
    rows, _, suggestion = await search_collection(db_pool, q, 20, profile)
    assert rows == []
    assert suggestion is None
    response = await client.get("/api/search", params={"q": q})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["did_you_mean"] is None


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("q", ["BLP 4195", "blp-4195", "BLP_4195", "blp.4195", "blp/4195"])
async def test_meaningful_catalog_separators(db_pool: Any, profile: str, q: str) -> None:
    rows, _, _ = await search_collection(db_pool, q, 20, profile)
    assert 920006 in [row["release_id"] for row in rows]


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("form", ["upper", "hex", "urn", "braces"])
async def test_uuid_forms_preserve_real_search_and_locate(
    client: AsyncClient, profile: str, form: str
) -> None:
    supplied = {
        "upper": profile.upper(),
        "hex": profile.replace("-", ""),
        "urn": "urn:uuid:" + profile,
        "braces": "{" + profile + "}",
    }[form]
    search = await client.get("/api/search", params={"q": "Tommy", "profile_id": supplied})
    assert search.status_code == 200, search.text
    assert [row["release_id"] for row in search.json()["items"]] == [920001]
    locate = await client.get("/api/locate", params={"release_id": 920001, "profile_id": supplied})
    assert locate.status_code == 200, locate.text
    assert locate.json()["release_id"] == 920001
    for path, params in [("/api/search", {"q": "Tommy"}), ("/api/locate", {"release_id": 920001})]:
        denied = await client.get(path, params={**params, "profile_id": str(uuid4())})
        assert denied.status_code == 403, denied.text
        assert denied.json()["detail"]["type"] == "profile_mismatch"

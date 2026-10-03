"""Real history routes: old change-set lookup remains authorized and profile-scoped."""

from __future__ import annotations

from typing import Any
import uuid

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def history_data(db_pool: Any):  # type: ignore[no-untyped-def]
    owned, foreign = str(uuid.uuid4()), str(uuid.uuid4())
    changes = [str(uuid.uuid4()) for _ in range(101)]
    foreign_change = str(uuid.uuid4())
    async with db_pool.connection() as conn:
        for profile, name in ((owned, "History owned"), (foreign, "History foreign")):
            await conn.execute(
                "INSERT INTO gruvax.profiles"
                " (id, display_name, app_token_encrypted, app_token_revoked)"
                " VALUES (%s::uuid, %s, %s, TRUE)",
                (profile, name, b""),
            )
        for index, change in enumerate(changes):
            await conn.execute(
                "INSERT INTO gruvax.boundary_history"
                " (profile_id, change_set_id, unit_id, row, col, prev_is_empty, new_is_empty, source, changed_at)"
                " VALUES (%s::uuid, %s::uuid, 1, 0, 0, TRUE, TRUE, 'manual',"
                " '2026-01-01T00:00:00Z'::timestamptz + %s * INTERVAL '1 second')",
                (owned, change, index),
            )
        await conn.execute(
            "INSERT INTO gruvax.boundary_history"
            " (profile_id, change_set_id, unit_id, row, col, prev_is_empty, new_is_empty, source)"
            " VALUES (%s::uuid, %s::uuid, 1, 0, 0, TRUE, TRUE, 'manual')",
            (foreign, foreign_change),
        )
        await conn.commit()
    yield {
        "owned": owned,
        "foreign": foreign,
        "oldest": changes[0],
        "latest": changes[-1],
        "foreign_change": foreign_change,
    }
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profiles WHERE id = ANY(%s::uuid[])", ([owned, foreign],)
        )
        await conn.commit()


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def client(db_pool: Any, history_data: dict[str, str]):  # type: ignore[no-untyped-def]
    # Profiles exist before startup so the real resolver has both profile registries.
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as http,
    ):
        yield http


def bound_headers(admin_session: dict[str, Any], profile: str) -> dict[str, str]:
    return cookie_header(admin_session["cookies"], {"gruvax_browse_binding": profile})


@pytest.mark.asyncio(loop_scope="session")
async def test_exact_history_lookup_reaches_beyond_latest_100(client, admin_session, history_data):  # type: ignore[no-untyped-def]
    headers = bound_headers(admin_session, history_data["owned"])
    recent = await client.get("/api/admin/history", headers=headers)
    assert recent.status_code == 200
    items = recent.json()["history"]
    assert len(items) == 100
    assert items[0]["change_set_id"] == history_data["latest"]
    assert history_data["oldest"] not in {item["change_set_id"] for item in items}
    target = await client.get(
        "/api/admin/history", params={"change_set_id": history_data["oldest"]}, headers=headers
    )
    assert target.status_code == 200
    assert [item["change_set_id"] for item in target.json()["history"]] == [history_data["oldest"]]
    assert target.json()["history"][0]["cube_count"] == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_targeted_history_cannot_reveal_another_profiles_change(
    client, admin_session, history_data
):  # type: ignore[no-untyped-def]
    headers = bound_headers(admin_session, history_data["owned"])
    foreign = await client.get(
        "/api/admin/history",
        params={"change_set_id": history_data["foreign_change"]},
        headers=headers,
    )
    missing = await client.get(
        "/api/admin/history", params={"change_set_id": str(uuid.uuid4())}, headers=headers
    )
    assert foreign.status_code == missing.status_code == 200
    assert foreign.json() == missing.json() == {"history": []}
    own_foreign = await client.get(
        "/api/admin/history",
        params={"change_set_id": history_data["foreign_change"]},
        headers=bound_headers(admin_session, history_data["foreign"]),
    )
    assert own_foreign.status_code == 200
    assert [item["change_set_id"] for item in own_foreign.json()["history"]] == [
        history_data["foreign_change"]
    ]


@pytest.mark.asyncio(loop_scope="session")
async def test_targeted_history_preserves_admin_and_binding_guards(
    client, admin_session, history_data
):  # type: ignore[no-untyped-def]
    params = {"change_set_id": history_data["oldest"]}
    unauthenticated = await client.get(
        "/api/admin/history",
        params=params,
        headers=cookie_header({"gruvax_browse_binding": history_data["owned"]}),
    )
    assert unauthenticated.status_code == 401
    unbound = await client.get(
        "/api/admin/history", params=params, headers=cookie_header(admin_session["cookies"])
    )
    assert unbound.status_code == 400
    assert unbound.json()["detail"]["type"] == "session_unbound"


@pytest.mark.asyncio(loop_scope="session")
async def test_targeted_history_rejects_malformed_uuid(client, admin_session, history_data):  # type: ignore[no-untyped-def]
    response = await client.get(
        "/api/admin/history",
        params={"change_set_id": "not-a-uuid"},
        headers=bound_headers(admin_session, history_data["owned"]),
    )
    assert response.status_code == 422

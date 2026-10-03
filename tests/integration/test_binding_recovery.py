"""Real session/delete routes recover bindings while preserving live device authority."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.api.admin.profiles import router as profiles_router
from gruvax.api.deps import require_admin
from gruvax.api.session import router as session_router
from gruvax.auth.sessions import BROWSE_BINDING_COOKIE, FINGERPRINT_COOKIE


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest_asyncio.fixture(loop_scope="session")
async def binding_client(db_pool: Any) -> AsyncIterator[tuple[AsyncClient, list[str]]]:
    ids = [str(uuid4()) for _ in range(3)]
    async with db_pool.connection() as conn:
        cur = await conn.execute("SELECT id FROM gruvax.profiles WHERE deleted_at IS NULL")
        previous = [row[0] for row in await cur.fetchall()]
        await conn.execute("UPDATE gruvax.profiles SET deleted_at=NOW() WHERE deleted_at IS NULL")
        for pid in ids:
            await conn.execute(
                "INSERT INTO gruvax.profiles "
                "(id, display_name, app_token_encrypted, app_token_revoked) VALUES (%s,%s,%s,TRUE)",
                (pid, "Binding test " + pid, b""),
            )
    app = FastAPI()
    app.state.db_pool = db_pool
    app.include_router(session_router, prefix="/api")
    app.include_router(profiles_router, prefix="/api/admin")
    # Authentication is outside this binding regression; deletion itself remains the real route.
    app.dependency_overrides[require_admin] = lambda: {}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, ids
    finally:
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.devices WHERE profile_id=ANY(%s::uuid[])", (ids,)
            )
            await conn.execute("DELETE FROM gruvax.profiles WHERE id=ANY(%s::uuid[])", (ids,))
            await conn.execute(
                "UPDATE gruvax.profiles SET deleted_at=NULL WHERE id=ANY(%s::uuid[])", (previous,)
            )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("active_count", [0, 1, 2])
async def test_deleted_browse_binding_recovers(
    binding_client: tuple[AsyncClient, list[str]], db_pool: Any, active_count: int
) -> None:
    client, ids = binding_client
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET deleted_at=NOW() WHERE id=ANY(%s::uuid[])",
            (ids[active_count + 1 :],),
        )
    bound = await client.post("/api/session/bind", json={"profile_id": ids[0]})
    assert bound.status_code == 200
    deleted = await client.delete(f"/api/admin/profiles/{ids[0]}")
    assert deleted.status_code == 200
    response = await client.get("/api/session")
    assert response.status_code == 200
    assert response.json()["profile_count"] == active_count
    assert response.json()["is_device_paired"] is False
    assert response.json()["bound_profile_id"] == (ids[1] if active_count == 1 else None)
    cookies = response.headers.get_list("set-cookie")
    assert len(cookies) == 1 and cookies[0].startswith(BROWSE_BINDING_COOKIE + "=")
    if active_count == 1:
        assert response.cookies[BROWSE_BINDING_COOKIE] == ids[1]
    else:
        assert "max-age=0" in cookies[0].lower()
    # The next bootstrap is stable, rather than echoing the old cookie again.
    next_response = await client.get("/api/session")
    assert next_response.json()["bound_profile_id"] == response.json()["bound_profile_id"]


@pytest.mark.asyncio(loop_scope="session")
async def test_live_paired_device_wins_over_stale_browse_binding(
    binding_client: tuple[AsyncClient, list[str]], db_pool: Any
) -> None:
    client, ids = binding_client
    fingerprint = "isolated-binding-device-" + str(uuid4())
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.devices (fingerprint, profile_id) VALUES (%s,%s)",
            (fingerprint, ids[1]),
        )
    bound = await client.post("/api/session/bind", json={"profile_id": ids[0]})
    assert bound.status_code == 200
    deleted = await client.delete(f"/api/admin/profiles/{ids[0]}")
    assert deleted.status_code == 200
    client.cookies.set(FINGERPRINT_COOKIE, fingerprint)
    response = await client.get("/api/session")
    assert response.status_code == 200
    assert response.json()["bound_profile_id"] == ids[1]
    assert response.json()["is_device_paired"] is True
    assert response.json()["needs_reauth"] is True
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert fingerprint not in response.text


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("cookie", ["not-a-profile", "00000000-0000-0000-0000-000000000099"])
async def test_forged_browse_cookie_clears_without_affecting_profiles(
    binding_client: tuple[AsyncClient, list[str]], cookie: str
) -> None:
    client, _ = binding_client
    response = await client.get(
        "/api/session", headers={"Cookie": f"{BROWSE_BINDING_COOKIE}={cookie}"}
    )
    assert response.status_code == 200
    assert response.json()["profile_count"] == 3
    assert response.json()["bound_profile_id"] is None
    assert "max-age=0" in response.headers["set-cookie"].lower()


@pytest.mark.asyncio(loop_scope="session")
async def test_valid_browse_binding_stays_bound(
    binding_client: tuple[AsyncClient, list[str]],
) -> None:
    client, ids = binding_client
    response = await client.get(
        "/api/session", headers={"Cookie": f"{BROWSE_BINDING_COOKIE}={ids[1]}"}
    )
    assert response.status_code == 200
    assert response.json()["bound_profile_id"] == ids[1]
    assert response.json()["needs_reauth"] is True
    assert "set-cookie" not in response.headers

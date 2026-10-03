"""The shared authentication fixture must seed its own PIN on a fresh database."""

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def client(db_pool):  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn:
        await conn.execute("DELETE FROM gruvax.settings WHERE key = 'auth.pin_hash'")
        await conn.commit()
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        assert not hasattr(ac, "app"), "httpx clients expose only their transport"
        yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_shared_session_authenticates_without_prior_pin(client, admin_session) -> None:  # type: ignore[no-untyped-def]
    response = await client.get(
        "/api/admin/settings", headers=cookie_header(admin_session["cookies"])
    )
    assert response.status_code == 200, response.text
    assert admin_session["csrf_token"]

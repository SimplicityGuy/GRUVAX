"""PAT redaction must cover the authenticated diagnostics HTTP emission channel."""

import logging

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def client(db_pool):  # type: ignore[no-untyped-def]
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_authenticated_diagnostics_redacts_interpolated_pat(client, admin_session) -> None:  # type: ignore[no-untyped-def]
    token = "dscg_synthetic_http_probe"
    logger = logging.getLogger("gruvax.diagnostics_privacy_probe")
    logger.warning("Diagnostic upstream failed: %s", RuntimeError(f"Bearer {token}"))

    response = await client.get(
        "/api/admin/diagnostics", headers=cookie_header(admin_session["cookies"])
    )
    assert response.status_code == 200, response.text
    entries = [row for row in response.json()["recent_logs"] if row["logger"] == logger.name]
    assert entries, "the emitted probe must appear in the real diagnostics response"
    assert entries[-1]["msg"] == "Diagnostic upstream failed: [REDACTED]"
    assert token not in response.text

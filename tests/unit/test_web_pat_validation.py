"""Web shape errors reject secret inputs before any DB/upstream work."""

from typing import Any

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.api.admin.profiles import ConnectPatRequest, router as profiles_router
from gruvax.api.deps import require_admin
from gruvax.api.invite_codes import RedeemRequest, public_router


@pytest.mark.parametrize("model", [RedeemRequest, ConnectPatRequest])
def test_shape_boundary_accepts_cli_contract(model: Any) -> None:
    pat = "dscg_" + "x" * 45
    assert model(pat=pat).pat == pat


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route",
    [
        "/api/invite-codes/00000000-0000-0000-0000-000000000099/redeem",
        "/api/admin/profiles/00000000-0000-0000-0000-000000000099/connect",
        "/api/admin/profiles/00000000-0000-0000-0000-000000000099/rotate",
    ],
)
@pytest.mark.parametrize("pat", ["mistyped_secret_" + "x" * 50, "dscg_" + "x" * 44, "", 123])
async def test_invalid_pat_is_sanitized_before_route_work(route: str, pat: Any) -> None:
    class NoDatabaseWork:
        def connection(self) -> None:
            pytest.fail("malformed PAT reached database work")

    app = FastAPI()
    app.state.db_pool = NoDatabaseWork()
    app.dependency_overrides[require_admin] = lambda: {}
    app.include_router(public_router, prefix="/api")
    app.include_router(profiles_router, prefix="/api/admin")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(route, json={"pat": pat})
    assert response.status_code == 422
    assert response.json()["detail"]["type"] == "invalid_pat"
    assert "input" not in response.json()["detail"]
    if pat:
        assert str(pat) not in response.text

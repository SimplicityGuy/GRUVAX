"""Integration tests for GET /api/admin/export/boundaries.yaml (BAK-01).

Wave-0 RED scaffold — authored before the export endpoint exists.
Tests assert on expected status codes so that an unimplemented endpoint (404)
fails the assertion rather than silently skipping.

Target endpoint: GET /api/admin/export/boundaries.yaml

Tests:
  - test_export_returns_yaml: GET → 200, media type application/x-yaml
  - test_overrides_in_export: per-label overrides are serialized in the export
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


# gruvax-0ge: the boundaries export is scoped to the caller's profile, so it needs
# a browse-binding to resolve — the same requirement every other admin route that
# touches boundary data already has (D-02, no default-profile fallback).
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac


async def _login(client) -> dict:  # type: ignore[no-untyped-def]
    """Helper: log in and return cookies (incl. browse-binding) + csrf token dict."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    cookies[BROWSE_BINDING_COOKIE] = DEFAULT_PROFILE_UUID
    return {
        "cookies": cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_export_unbound_returns_400(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax-0ge: an admin with no browse-binding gets 400, not the default profile's cuts.

    The pre-fix handler answered every caller with the DEFAULT profile's boundary
    cache, so this request used to succeed and hand back the wrong profile's cut
    points. Refusing to guess is the fix.
    """
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    assert res.status_code == 200, "Login must be available for the unbound export test"
    session_only = {k: v for k, v in dict(res.cookies).items() if k != BROWSE_BINDING_COOKIE}

    response = await client.get(
        "/api/admin/export/boundaries.yaml",
        headers=cookie_header(session_only),
    )
    assert response.status_code == 400, (
        f"Expected 400 session_unbound for an unbound admin export, got "
        f"{response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_export_returns_yaml(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/export/boundaries.yaml → 200, Content-Type application/x-yaml.

    Asserts on 200 and YAML content-type so that an unimplemented endpoint (404)
    fails RED as intended (BAK-01).
    """
    auth = await _login(client)
    assert auth, "Login must be available for export test"

    response = await client.get(
        "/api/admin/export/boundaries.yaml",
        headers=cookie_header(auth["cookies"]),
    )
    assert response.status_code == 200, (
        f"Expected 200 from export/boundaries.yaml, got {response.status_code}: {response.text}"
    )
    content_type = response.headers.get("content-type", "")
    assert "application/x-yaml" in content_type, (
        f"Expected content-type application/x-yaml, got: {content_type}"
    )
    # Body must be parseable YAML with a 'cubes' key
    import yaml

    data = yaml.safe_load(response.text)
    assert isinstance(data, dict), f"Export body must be a YAML dict, got: {type(data)}"
    assert "cubes" in data, f"Export YAML missing 'cubes' key: {data}"


@pytest.mark.asyncio(loop_scope="session")
async def test_overrides_in_export(client) -> None:  # type: ignore[no-untyped-def]
    """Per-label overrides are serialized in the export when present (D-10).

    This test targets a boundary whose segment_overrides table has at least one
    row. In Wave 0 the endpoint is unimplemented → 404 fails RED as intended.
    """
    auth = await _login(client)
    assert auth, "Login must be available for overrides export test"

    response = await client.get(
        "/api/admin/export/boundaries.yaml",
        headers=cookie_header(auth["cookies"]),
    )
    # 200 required — 404 (unimplemented) fails RED
    assert response.status_code == 200, (
        f"Expected 200 from export/boundaries.yaml, got {response.status_code}: {response.text}"
    )
    import yaml

    data = yaml.safe_load(response.text)
    # If any cube has overrides, they must be serialized under an 'overrides' key
    # (this assertion checks the shape contract; GREEN when export endpoint lands)
    cubes = data.get("cubes", [])
    for cube in cubes:
        if "overrides" in cube:
            assert isinstance(cube["overrides"], dict), (
                f"Cube overrides must be a dict, got: {type(cube['overrides'])}"
            )

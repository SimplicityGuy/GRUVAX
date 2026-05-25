"""Integration tests for GET /api/version.

Tests:
  - test_version_returns_200: GET /api/version → 200.
  - test_version_has_required_keys: response contains git_sha, build_timestamp, environment.
  - test_version_no_secrets: response body contains none of the secret-looking keys.
  - test_version_values_are_strings: all three values are non-empty strings.
  - test_version_not_gated: no session cookie needed (public endpoint).

Harness mirrors test_health.py: LifespanManager + AsyncClient + db_pool fixture.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app

# Keys that must NEVER appear in the version response (T-08-01 mitigation).
_FORBIDDEN_KEYS = {"session_secret", "database_url", "pin", "csrf", "password", "secret"}


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    Mirrors the pattern in test_health.py.
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, app


@pytest.mark.asyncio(loop_scope="session")
async def test_version_returns_200(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/version returns HTTP 200."""
    ac, _app = client
    response = await ac.get("/api/version")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_version_has_required_keys(client) -> None:  # type: ignore[no-untyped-def]
    """Response contains git_sha, build_timestamp, environment keys."""
    ac, _app = client
    response = await ac.get("/api/version")
    body = response.json()
    required_keys = {"git_sha", "build_timestamp", "environment"}
    assert required_keys.issubset(body.keys()), (
        f"Missing keys: {required_keys - body.keys()}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_version_no_secrets(client) -> None:  # type: ignore[no-untyped-def]
    """Response body contains none of the forbidden secret-looking keys (T-08-01)."""
    ac, _app = client
    response = await ac.get("/api/version")
    body = response.json()
    present_forbidden = _FORBIDDEN_KEYS.intersection(body.keys())
    assert not present_forbidden, (
        f"Secret-looking keys found in /api/version response: {present_forbidden}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_version_values_are_strings(client) -> None:  # type: ignore[no-untyped-def]
    """git_sha, build_timestamp, environment are all non-empty strings."""
    ac, _app = client
    response = await ac.get("/api/version")
    body = response.json()
    for key in ("git_sha", "build_timestamp", "environment"):
        val = body.get(key)
        assert isinstance(val, str), f"{key!r} is not a string: {val!r}"
        assert val, f"{key!r} must not be empty"


@pytest.mark.asyncio(loop_scope="session")
async def test_version_not_gated(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/version is accessible without an admin session cookie (public endpoint)."""
    _ac, _app = client
    # Issue a fresh client with no session cookies
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
            # No cookies set — unauthenticated request
        ) as fresh_client,
    ):
        response = await fresh_client.get("/api/version")
    # Should still be 200 (not 401/403/redirect)
    assert response.status_code == 200, (
        f"Expected 200 (public endpoint), got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_version_exactly_three_keys(client) -> None:  # type: ignore[no-untyped-def]
    """Response body has exactly the three documented keys (no extras)."""
    ac, _app = client
    response = await ac.get("/api/version")
    body = response.json()
    assert set(body.keys()) == {"git_sha", "build_timestamp", "environment"}, (
        f"Unexpected extra keys in response: {set(body.keys())}"
    )

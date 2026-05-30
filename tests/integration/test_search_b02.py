"""Integration tests for B-02 backend fix — GET /api/search optional profile_id.

B-02 symptom: when profile_id is omitted from the query, the backend was returning 422
(unprocessable entity) instead of resolving the profile from the gruvax_browse_binding
cookie and returning 200.

Tests (RED before the fix in search.py, GREEN after):
  - test_omitted_profile_id_with_cookie: no profile_id + valid cookie → 200 (was 422, B-02)
  - test_no_cookie_returns_session_unbound: no profile_id, no cookie → 400 session_unbound
  - test_mismatched_profile_id_returns_403: supplied mismatched profile_id → 403 profile_mismatch
  - test_supplied_correct_profile_id: supplied correct profile_id + cookie → 200 (existing path)

Plan 05-01: B-02 closure (profile_id optional, cookie-authoritative fallback).
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


# Default profile UUID (D-02) + browse-binding cookie name (D2-10).
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    Sets the gruvax_browse_binding cookie to the default profile so that
    all profile-scoped endpoints (search, locate) validate correctly (D2-04).
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
            cookies={BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID},
        ) as ac,
    ):
        yield ac


@pytest_asyncio.fixture(scope="module")
async def no_cookie_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client WITHOUT the browse-binding cookie.

    Used to verify 400 session_unbound is returned when neither fingerprint
    nor browse-binding cookie is present.
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_omitted_profile_id_with_cookie(client) -> None:  # type: ignore[no-untyped-def]
    """B-02 RED test: omitted profile_id + valid browse-binding cookie → 200.

    Before the fix: returns 422 (profile_id is a required param).
    After the fix: returns 200 scoped to the cookie-bound profile.
    """
    response = await client.get("/api/search", params={"q": "Blue Note"})
    assert response.status_code == 200, (
        f"Expected 200 with omitted profile_id + valid cookie (B-02), got "
        f"{response.status_code}: {response.text}"
    )
    body = response.json()
    assert "items" in body, f"Response missing 'items' key: {body}"


@pytest.mark.asyncio(loop_scope="session")
async def test_no_cookie_returns_session_unbound(no_cookie_client) -> None:  # type: ignore[no-untyped-def]
    """D2-04 preservation: omitted profile_id + no cookie → 400 session_unbound.

    This path is already correct before the B-02 fix (422 → 400 after fix, but
    the no-cookie 400 must be preserved exactly after the fix too).
    """
    response = await no_cookie_client.get("/api/search", params={"q": "Blue Note"})
    assert response.status_code == 400, (
        f"Expected 400 session_unbound, got {response.status_code}: {response.text}"
    )
    detail = response.json().get("detail", {})
    assert detail.get("type") == "session_unbound", (
        f"Expected detail.type == 'session_unbound', got: {detail}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_mismatched_profile_id_returns_403(client) -> None:  # type: ignore[no-untyped-def]
    """D2-04 preservation: supplied mismatched profile_id → 403 profile_mismatch.

    When a profile_id is supplied that does not match the cookie-authoritative
    resolved profile, the backend must return 403 profile_mismatch (no cross-profile
    data leak).
    """
    response = await client.get(
        "/api/search",
        params={"q": "Blue Note", "profile_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"},
    )
    assert response.status_code == 403, (
        f"Expected 403 profile_mismatch, got {response.status_code}: {response.text}"
    )
    detail = response.json().get("detail", {})
    assert detail.get("type") == "profile_mismatch", (
        f"Expected detail.type == 'profile_mismatch', got: {detail}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_supplied_correct_profile_id(client) -> None:  # type: ignore[no-untyped-def]
    """Existing path: supplied correct profile_id + matching cookie → 200 (no regression)."""
    response = await client.get(
        "/api/search",
        params={"q": "Blue Note", "profile_id": DEFAULT_PROFILE_UUID},
    )
    assert response.status_code == 200, (
        f"Expected 200 with correct supplied profile_id, got "
        f"{response.status_code}: {response.text}"
    )
    body = response.json()
    assert "items" in body, f"Response missing 'items' key: {body}"

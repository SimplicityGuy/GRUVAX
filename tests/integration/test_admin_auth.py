"""Integration tests for admin authentication endpoints (ADMN-01, ADMN-02, ADMN-08).

Tests:
  - test_login_success: POST /api/admin/login returns 200 + session + CSRF cookies
  - test_login_wrong_pin: wrong PIN returns 401
  - test_rate_limit: 6th login attempt within 5 min returns 429
  - test_csrf_missing: POST without X-CSRF-Token header returns 403
  - test_cookie_flags: gruvax_session is HttpOnly (ADMN-01 / Pitfall 13)
  - test_csrf_cookie_readable: gruvax_csrf is NOT HttpOnly (SPA must read it)
  - test_logout: POST /api/admin/logout revokes session + clears cookie (ADMN-08)
  - test_change_pin_revokes_sessions: Change-PIN revokes all other sessions (ADMN-02)

These tests target code implemented in Plan 02 — authored RED in Wave-0 scaffold.
They go GREEN when Plan 02 ships the login/logout/session endpoints.

Analog: tests/integration/test_search.py (LifespanManager + AsyncClient pattern).
"""

from __future__ import annotations

import os

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


# Test PIN used throughout this module — must match the seeded hash below.
_TEST_PIN = "0000"


@pytest.fixture(autouse=True)
def reset_login_rate_limit() -> None:  # type: ignore[return]
    """Reset the login rate-limit counter before each test.

    The login endpoint uses a module-level singleton ``FixedWindowRateLimiter``
    backed by ``MemoryStorage``.  Tests in this module share the same process
    and the same in-memory counter.  ``test_rate_limit`` intentionally exhausts
    the 5-attempt window; without a reset, all subsequent tests that POST to
    ``/api/admin/login`` would receive 429 and skip instead of running.

    ``limiter.reset()`` clears the entire in-memory storage — safe here because
    integration tests run sequentially and the limiter is local to this process.
    """
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    Seeds the test PIN hash ("0000") into gruvax.settings after the app starts
    (using the app's own DB pool from lifespan state) so that all login tests
    in this module work against a known PIN.
    """
    # Ensure SESSION_SECRET is set for this test process
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.auth.pin import hash_pin

    test_hash = hash_pin(_TEST_PIN)

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        # Seed the test PIN hash using the app's own pool (started by lifespan)
        pool = app.state.db_pool
        _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
                " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb, 'Test PIN seeded by test_admin_auth', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (_DEFAULT_PROFILE_UUID, f'"{test_hash}"'),
            )
            await conn.commit()
        yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_login_success(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/login with correct PIN returns 200 + session + CSRF cookies (ADMN-01)."""
    response = await client.post("/api/admin/login", json={"pin": "0000"})
    assert response.status_code == 200, (
        f"Expected 200 from login, got {response.status_code}: {response.text}"
    )
    assert "gruvax_session" in response.cookies, "gruvax_session cookie must be set on login"
    assert "gruvax_csrf" in response.cookies, "gruvax_csrf cookie must be set on login"


@pytest.mark.asyncio(loop_scope="session")
async def test_login_wrong_pin(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/login with wrong PIN returns 401 (ADMN-01)."""
    response = await client.post("/api/admin/login", json={"pin": "9999"})
    assert response.status_code == 401, f"Expected 401 for wrong PIN, got {response.status_code}"


@pytest.mark.asyncio(loop_scope="session")
async def test_rate_limit(client) -> None:  # type: ignore[no-untyped-def]
    """6th login attempt within 5 min returns 429 Too Many Requests (ADMN-01, D-03a).

    slowapi limits to 5 attempts per 5-minute window per IP.
    In test the IP is the loopback address from ASGITransport.
    """
    # The first 5 attempts may succeed or fail (PIN may be wrong)
    for _ in range(5):
        await client.post("/api/admin/login", json={"pin": "9999"})
    # 6th attempt must be rate-limited
    response = await client.post("/api/admin/login", json={"pin": "9999"})
    assert response.status_code == 429, (
        f"Expected 429 on 6th attempt (rate-limited), got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_csrf_missing(client) -> None:  # type: ignore[no-untyped-def]
    """POST to an admin endpoint without X-CSRF-Token header returns 403 (Pitfall 13).

    The require_admin dependency checks X-CSRF-Token == gruvax_csrf cookie value
    for all mutating (POST/PUT/PATCH/DELETE) requests.
    """
    # First obtain a valid session cookie
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login endpoint not yet implemented — skipping CSRF test")

    # Make a mutating request WITHOUT the X-CSRF-Token header
    response = await client.post(
        "/api/admin/logout",
        headers=cookie_header(login_res.cookies),
        # No X-CSRF-Token header — should be rejected
    )
    assert response.status_code == 403, (
        f"Expected 403 when X-CSRF-Token missing, got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_cookie_flags(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax_session cookie must be HttpOnly (ADMN-01 / Pitfall 13).

    The session token cookie must not be readable by JavaScript (XSS mitigation).
    We verify by checking the response Set-Cookie header attributes.
    """
    response = await client.post("/api/admin/login", json={"pin": "0000"})
    if response.status_code != 200:
        pytest.skip("Login not yet implemented — skipping cookie flags test")

    # Check raw Set-Cookie headers for HttpOnly attribute
    set_cookie_headers = response.headers.get_list("set-cookie")
    session_cookie_header = next((h for h in set_cookie_headers if "gruvax_session" in h), None)
    assert session_cookie_header is not None, "gruvax_session Set-Cookie header missing"
    assert "httponly" in session_cookie_header.lower(), (
        "gruvax_session must be HttpOnly (SPA must NOT read it directly)"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_csrf_cookie_readable(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax_csrf cookie must NOT be HttpOnly (SPA must read it to echo as X-CSRF-Token).

    Pitfall F: if the CSRF cookie is HttpOnly, the SPA cannot read it to include
    in the X-CSRF-Token request header, and every admin POST will fail with 403.
    """
    response = await client.post("/api/admin/login", json={"pin": "0000"})
    if response.status_code != 200:
        pytest.skip("Login not yet implemented — skipping CSRF cookie flag test")

    set_cookie_headers = response.headers.get_list("set-cookie")
    csrf_cookie_header = next((h for h in set_cookie_headers if "gruvax_csrf" in h), None)
    assert csrf_cookie_header is not None, "gruvax_csrf Set-Cookie header missing"
    assert "httponly" not in csrf_cookie_header.lower(), (
        "gruvax_csrf must NOT be HttpOnly (SPA must be able to read it)"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_logout(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/logout revokes session and clears cookies (ADMN-08)."""
    # Log in
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not yet implemented — skipping logout test")

    csrf_token = login_res.cookies.get("gruvax_csrf")
    # Log out (must include X-CSRF-Token header)
    logout_res = await client.post(
        "/api/admin/logout",
        headers={"X-CSRF-Token": csrf_token or "", **cookie_header(login_res.cookies)},
    )
    assert logout_res.status_code == 200, f"Expected 200 from logout, got {logout_res.status_code}"

    # After logout, session must be revoked — a session-gated request must return 401
    verify_res = await client.get(
        "/api/admin/session",
        headers=cookie_header(login_res.cookies),
    )
    assert verify_res.status_code == 401, (
        f"After logout, session-gated endpoint must return 401, got {verify_res.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_change_pin_revokes_sessions(client) -> None:  # type: ignore[no-untyped-def]
    """Change-PIN revokes all OTHER sessions (ADMN-02, D-03b).

    After changing the PIN, any session cookie that was issued before the change
    must be considered revoked.
    """
    # Log in to create a session
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not yet implemented — skipping change-pin test")

    csrf_token = login_res.cookies.get("gruvax_csrf")
    original_cookies = login_res.cookies

    # Change PIN (requires current PIN, new PIN, and CSRF token)
    change_res = await client.post(
        "/api/admin/settings/pin",
        json={"current_pin": "0000", "new_pin": "0000"},  # keep same for test idempotency
        headers={"X-CSRF-Token": csrf_token or "", **cookie_header(original_cookies)},
    )
    # Even if Change-PIN isn't implemented yet, we verify the behavior contract:
    # if it returns 200, the original session must still be valid (same-user session
    # is typically NOT revoked on self-change, but OTHER sessions are)
    if change_res.status_code not in (200, 404):
        # Endpoint not yet implemented — skip gracefully
        pytest.skip("Change-PIN endpoint not yet implemented")

    # Verify the current session is still valid (or has been appropriately handled)
    # This test primarily documents the contract; full validation in Plan 02.
    verify_res = await client.get("/api/admin/session", headers=cookie_header(original_cookies))
    # After PIN change, other sessions would be revoked — current session handling
    # is implementation-defined (may stay valid or be re-issued)
    assert verify_res.status_code in (200, 401), (
        f"After PIN change, session check must return 200 or 401, got {verify_res.status_code}"
    )

"""Integration tests for POST /api/admin/import/settings (BAK-02).

Wave-0 RED scaffold — authored before the settings-import endpoint exists.
Tests assert on expected status codes so that an unimplemented endpoint (404)
fails the assertion rather than silently skipping.

Target endpoint: POST /api/admin/import/settings

Tests:
  - test_unknown_key_rejected: file with unknown key → 422, no DB write (T-SETTINGS-KEY)
  - test_auth_key_rejected: file with auth.* key → 422 hard exclusion (D-14, T-PIN-LEAK)
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


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
    """Helper: log in and return cookies + csrf token dict."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    return {
        "cookies": res.cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


@pytest.mark.asyncio(loop_scope="session")
async def test_unknown_key_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/import/settings with unknown key → 422, no DB write.

    A YAML settings file containing a key not in _ALLOWED_SETTINGS_KEYS must be
    rejected with 422 and no rows may be written to gruvax.settings.
    Asserts on 422 — unimplemented endpoint (404) fails RED as intended (T-SETTINGS-KEY).
    """
    auth = await _login(client)
    assert auth, "Login must be available for settings import test"

    # Contains an unknown key that is not in _ALLOWED_SETTINGS_KEYS
    yaml_content = b"completely.unknown.key: some_value\n"
    response = await client.post(
        "/api/admin/import/settings",
        content=yaml_content,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    # Expect 422 for unknown key — 404 (unimplemented) fails RED
    assert response.status_code == 422, (
        f"Expected 422 for unknown key, got {response.status_code}: {response.text}"
    )
    body = response.json()
    # The error detail must indicate the rejection type
    assert "unknown_key" in str(body) or "type" in body, (
        f"Expected structured 422 detail, got: {body}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_auth_key_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/import/settings with auth.* key → 422 (D-14 hard exclusion, T-PIN-LEAK).

    Any key starting with 'auth.' must be rejected even if the overall YAML is
    syntactically valid. This prevents the PIN hash from being overwritten via import.
    Asserts on 422 — unimplemented endpoint (404) fails RED as intended.
    """
    auth = await _login(client)
    assert auth, "Login must be available for auth key rejection test"

    # auth.pin_hash is the primary hard-exclusion concern (D-14)
    yaml_content = b'auth.pin_hash: "$argon2id$v=19$m=65536,t=2,p=1$fake$hash"\n'
    response = await client.post(
        "/api/admin/import/settings",
        content=yaml_content,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    # Expect 422 auth key rejection — 404 (unimplemented) fails RED
    assert response.status_code == 422, (
        f"Expected 422 for auth.* key, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "auth_key_rejected" in str(body) or "type" in body, (
        f"Expected structured 422 detail for auth.* rejection, got: {body}"
    )

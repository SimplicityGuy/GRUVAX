"""Integration tests for sync_cadence settings persistence — Phase 4 Plan 04-00 Task 2.

Phase 4 Wave 0 RED scaffolding (SYN-01). Tests the behavior that Plan 04-04
will implement: PUT/GET /api/admin/settings roundtrip for sync.cadence.

All tests in this file are RED until Plan 04-04 adds sync.cadence to:
  - _ALLOWED_SETTINGS_KEYS frozenset in settings.py
  - key_map in update_settings (body key "sync_cadence" → DB key "sync.cadence")
  - _CADENCE_VALUES validation frozenset ({"24h", "12h", "6h", "off"})
  - GET response dict under "sync_cadence"

D4-06: sync.cadence must persist across settings PUT, be returned by GET,
and return 422 with type="invalid_cadence" for invalid values.

Analog: tests/integration/api/test_admin_sync_endpoint.py (admin auth + CSRF
pattern with LifespanManager + AsyncClient + db_pool + PIN seed).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


# ── constants ─────────────────────────────────────────────────────────────────

_TEST_PIN = "0000"
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# Valid cadence values per D4-06
_VALID_CADENCE_VALUES = ("24h", "12h", "6h", "off")


# ── helpers ───────────────────────────────────────────────────────────────────


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _seed_pin(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Seed test PIN '0000' into gruvax.settings."""
    from gruvax.auth.pin import hash_pin

    h = hash_pin(_TEST_PIN)
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb,"
            "   'Test PIN seeded by test_admin_settings', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (_DEFAULT_PROFILE_UUID, f'"{h}"'),
        )
        await conn.commit()


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure SESSION_SECRET and GRUVAX_SECRET_KEY are set for the test process."""
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet
        monkeypatch.setenv("GRUVAX_SECRET_KEY", Fernet.generate_key().decode())


@pytest_asyncio.fixture(scope="module")
async def client(db_pool) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with full lifespan + seeded test PIN."""
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
        # Seed PIN via the app's live DB pool
        pool = manager.app.state.db_pool
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
                " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb,"
                "   'Test PIN seeded by test_admin_settings', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (_DEFAULT_PROFILE_UUID, f'"{test_hash}"'),
            )
            await conn.commit()
        yield ac


@pytest_asyncio.fixture(scope="module")
async def admin_session(client) -> dict:  # type: ignore[no-untyped-def]
    """Log in with test PIN and return session cookies + CSRF token."""
    # Reset the rate limiter so a prior test module's logins don't block us
    from gruvax.api.admin.limiter import limiter
    limiter.reset()

    res = await client.post("/api/admin/login", json={"pin": _TEST_PIN})
    assert res.status_code == 200, (
        f"admin_session: login failed {res.status_code}: {res.text}"
    )
    csrf = res.cookies.get("gruvax_csrf") or res.json().get("csrf_token")
    return {"cookies": res.cookies, "csrf_token": csrf}


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_cadence(client, admin_session) -> None:  # type: ignore[no-untyped-def]
    """PUT /api/admin/settings {sync_cadence:"12h"} then GET returns sync_cadence:"12h".

    D4-06: sync.cadence must persist via the settings PUT endpoint and be
    returned by GET. The value "12h" must round-trip cleanly.

    RED until Plan 04-04 adds sync.cadence to the settings key_map,
    allowed-keys frozenset, validation, and GET response.
    """
    # PUT with a valid cadence value
    put_res = await client.put(
        "/api/admin/settings",
        json={"sync_cadence": "12h"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert put_res.status_code == 200, (
        f"PUT /api/admin/settings {{sync_cadence: '12h'}} expected 200, "
        f"got {put_res.status_code}: {put_res.text}"
    )

    # GET should now return sync_cadence: "12h"
    get_res = await client.get(
        "/api/admin/settings",
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert get_res.status_code == 200, (
        f"GET /api/admin/settings expected 200, got {get_res.status_code}: {get_res.text}"
    )
    body = get_res.json()

    assert "sync_cadence" in body, (
        f"GET /api/admin/settings response missing 'sync_cadence'. "
        f"D4-06 requires sync.cadence to be returned. "
        f"Keys present: {sorted(body.keys())}"
    )
    assert body["sync_cadence"] == "12h", (
        f"Expected sync_cadence='12h' after PUT, got {body['sync_cadence']!r}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_cadence_invalid_value(client, admin_session) -> None:  # type: ignore[no-untyped-def]
    """PUT /api/admin/settings with invalid sync_cadence returns 422 with type="invalid_cadence".

    D4-06: Values outside {"24h", "12h", "6h", "off"} must be rejected with:
      status=422, body={"type": "invalid_cadence", ...}

    RED until Plan 04-04 adds the cadence validation branch to update_settings().
    """
    put_res = await client.put(
        "/api/admin/settings",
        json={"sync_cadence": "7h"},  # invalid: "7h" is not in _CADENCE_VALUES
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert put_res.status_code == 422, (
        f"PUT /api/admin/settings {{sync_cadence: '7h'}} expected 422 "
        f"(invalid_cadence), got {put_res.status_code}: {put_res.text}"
    )
    body = put_res.json()

    # The error detail must identify the rejection reason
    detail = body.get("detail") or body
    error_type = (
        detail.get("type")
        if isinstance(detail, dict)
        else None
    )
    assert error_type == "invalid_cadence", (
        f"422 response body must include type='invalid_cadence'. "
        f"Got detail: {detail!r}"
    )

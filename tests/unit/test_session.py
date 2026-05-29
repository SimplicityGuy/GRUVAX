"""Unit tests for GET /api/session needs_reauth field — Phase 4 Plan 04-00 Task 2.

Phase 4 Wave 0 RED scaffolding. Test asserts behavior that is NOT YET IMPLEMENTED
in gruvax.api.session (Plan 04-02 will add the needs_reauth field).

The test will FAIL (RED) until D4-08 is implemented:
  "GET /api/session returns needs_reauth: true when the bound profile has
   app_token_revoked=TRUE, and false/absent otherwise."

Analog: tests/unit/test_sessions.py (pure session-logic unit tests using
AsyncMock/dependency_overrides pattern). This file follows the module naming
convention tests/unit/test_session.py as specified by 04-VALIDATION.md.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, patch

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio


# ── constants ─────────────────────────────────────────────────────────────────

_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
_REVOKED_PROFILE_UUID = "00000000-0000-0000-0000-000000000002"


# ── fake DB profile rows ──────────────────────────────────────────────────────

def _make_profile_rows(revoked: bool) -> list[tuple[Any, ...]]:
    """Build a fake cursor result for _SELECT_ACTIVE_PROFILES.

    Columns (in order from session.py _SELECT_ACTIVE_PROFILES):
      id, display_name, last_sync_at, last_sync_status,
      last_sync_item_count, app_token_revoked
    """
    import uuid
    return [
        (
            uuid.UUID(_DEFAULT_PROFILE_UUID),  # id
            "Default",                          # display_name
            None,                               # last_sync_at
            None,                               # last_sync_status
            None,                               # last_sync_item_count
            revoked,                            # app_token_revoked
        )
    ]


class _FakeCursor:
    """Async cursor stub returning pre-seeded profile rows."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    async def execute(self, sql: str, params: Any = None) -> None:
        pass

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    async def fetchone(self) -> tuple[Any, ...] | None:
        return None  # no device row

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeConn:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakePool:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def connection(self) -> _FakeConn:
        return _FakeConn(self._rows)


# ── app factory ───────────────────────────────────────────────────────────────


def _make_app(revoked: bool) -> Any:
    """Create a GRUVAX app with a fake pool for testing needs_reauth derivation.

    Follows the unit-test pattern from test_admin_led_settings.py:
    override get_pool via dependency_overrides + inject fake pool into app.state.
    No live Postgres needed.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app

    app = create_app()
    fake_pool = _FakePool(_make_profile_rows(revoked))
    app.state.db_pool = fake_pool
    app.state.mqtt = None
    app.state.mqtt_ok = False

    return app


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_needs_reauth_true_when_token_revoked() -> None:
    """GET /api/session returns needs_reauth=true when bound profile is revoked.

    D4-08: When the bound profile has app_token_revoked=TRUE, the session
    endpoint must include needs_reauth: true in the response JSON.

    RED until Plan 04-02 adds needs_reauth derivation to get_session().
    """
    app = _make_app(revoked=True)

    # Inject browse-binding cookie so bound_profile_id is set to default profile
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={
            "gruvax_browse_binding": _DEFAULT_PROFILE_UUID,
            # No fingerprint cookie — avoid device lookup path
        },
    ) as client:
        res = await client.get("/api/session")

    assert res.status_code == 200, (
        f"GET /api/session expected 200, got {res.status_code}: {res.text}"
    )
    body = res.json()

    # D4-08: needs_reauth must be present and True when app_token_revoked=TRUE
    assert "needs_reauth" in body, (
        f"GET /api/session response missing 'needs_reauth' field. "
        f"D4-08 requires this field to signal re-auth to the kiosk SPA. "
        f"Body keys: {list(body.keys())}"
    )
    assert body["needs_reauth"] is True, (
        f"needs_reauth must be True when bound profile has app_token_revoked=TRUE. "
        f"Got: {body['needs_reauth']!r}"
    )


@pytest.mark.asyncio
async def test_needs_reauth_false_when_token_valid() -> None:
    """GET /api/session returns needs_reauth=false when bound profile is NOT revoked.

    D4-08: When the bound profile has app_token_revoked=FALSE, needs_reauth must
    be false (or absent with a falsy value). No re-auth banner should show.

    RED until Plan 04-02 adds needs_reauth derivation to get_session().
    """
    app = _make_app(revoked=False)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"gruvax_browse_binding": _DEFAULT_PROFILE_UUID},
    ) as client:
        res = await client.get("/api/session")

    assert res.status_code == 200, (
        f"GET /api/session expected 200, got {res.status_code}: {res.text}"
    )
    body = res.json()

    # D4-08: needs_reauth must be present and False when app_token_revoked=FALSE
    assert "needs_reauth" in body, (
        f"GET /api/session response missing 'needs_reauth' field. "
        f"D4-08 requires this field (always present, not just when True). "
        f"Body keys: {list(body.keys())}"
    )
    assert body["needs_reauth"] is False, (
        f"needs_reauth must be False when bound profile has app_token_revoked=FALSE. "
        f"Got: {body['needs_reauth']!r}"
    )


# needs_reauth is the canonical test ID referenced in 04-VALIDATION.md
test_needs_reauth = test_needs_reauth_true_when_token_revoked

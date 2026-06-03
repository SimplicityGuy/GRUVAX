"""Integration tests for GET /api/admin/diagnostics profiles[] section.

Phase 4 — Wave 0 RED scaffolding (Plan 04-00 Task 2 / SYN-02).

This file is the Phase 4 extension of tests/integration/test_diagnostics.py.
It adds test_profiles_section which asserts behavior NOT YET IMPLEMENTED
(D4-15 — per-profile diagnostics section).

Tests in this file will FAIL (RED) until Plan 04-03 adds the profiles[]
section to GET /api/admin/diagnostics.

Pattern: mirrors tests/integration/test_diagnostics.py (module-scoped
diag_client fixture, require_admin override via dependency_overrides,
LifespanManager + AsyncClient with db_pool, Phase 06-04 canonical pattern).
"""

from __future__ import annotations

import os

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.api.deps import require_admin
from gruvax.app import create_app


# ── Module-scoped client (authenticated via dependency_overrides) ──────────────


def _admin_stub() -> dict[str, str]:
    """Stub for require_admin dependency — returns a minimal admin dict."""
    return {"role": "admin"}


@pytest_asyncio.fixture(scope="module")
async def diag_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with require_admin bypassed.

    Follows the exact pattern from tests/integration/test_diagnostics.py
    (Phase 06-04 canonical): FastAPI resolves Depends(require_admin) by
    function reference; use app.dependency_overrides[require_admin] to
    intercept it.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    app = create_app()
    app.dependency_overrides[require_admin] = _admin_stub
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, manager.app
    app.dependency_overrides.clear()


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_profiles_section(diag_client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/diagnostics includes a profiles[] array with correct shape.

    D4-15: The diagnostics endpoint must include a per-profile section:
      profiles: [
        {
          id: str,
          display_name: str,
          last_sync_at: str | null,
          last_sync_status: str | null,
          last_sync_item_count: int | null,
          last_sync_error: str | null,
          app_token_revoked: bool,
        },
        ...
      ]

    Deleted profiles (deleted_at IS NOT NULL) must NOT appear in profiles[].

    RED until Plan 04-03 adds the profiles query to get_diagnostics().
    """
    ac, _app = diag_client
    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, (
        f"GET /api/admin/diagnostics expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()

    # D4-15: profiles[] must be present in the diagnostics response
    assert "profiles" in body, (
        f"GET /api/admin/diagnostics response missing 'profiles' key. "
        f"D4-15 requires a per-profile diagnostics section. "
        f"Present keys: {sorted(body.keys())}"
    )

    profiles = body["profiles"]
    assert isinstance(profiles, list), (
        f"diagnostics['profiles'] must be a list, got {type(profiles).__name__!r}"
    )

    # At least one profile should exist (the default profile seeded by the test suite)
    assert len(profiles) >= 1, (
        "diagnostics['profiles'] is empty — expected at least the default profile. "
        "If the dev DB is freshly reset, the default profile must still be present."
    )

    # Required keys for each profile entry
    _REQUIRED_KEYS = {
        "id",
        "display_name",
        "last_sync_at",
        "last_sync_status",
        "last_sync_item_count",
        "last_sync_error",
        "app_token_revoked",
    }

    for i, profile in enumerate(profiles):
        assert isinstance(profile, dict), (
            f"profiles[{i}] must be a dict, got {type(profile).__name__!r}: {profile!r}"
        )
        missing = _REQUIRED_KEYS - profile.keys()
        assert not missing, (
            f"profiles[{i}] is missing required keys: {sorted(missing)}. "
            f"D4-15 requires all 7 fields on each profile entry. "
            f"Got: {sorted(profile.keys())}"
        )
        # Type checks
        assert isinstance(profile["id"], str), (
            f"profiles[{i}]['id'] must be a str UUID, got {type(profile['id'])!r}"
        )
        assert isinstance(profile["display_name"], str), (
            f"profiles[{i}]['display_name'] must be a str, got {type(profile['display_name'])!r}"
        )
        assert profile["last_sync_at"] is None or isinstance(profile["last_sync_at"], str), (
            f"profiles[{i}]['last_sync_at'] must be str ISO-8601 or null"
        )
        assert profile["last_sync_item_count"] is None or isinstance(
            profile["last_sync_item_count"], int
        ), f"profiles[{i}]['last_sync_item_count'] must be int or null"
        assert isinstance(profile["app_token_revoked"], bool), (
            f"profiles[{i}]['app_token_revoked'] must be bool, "
            f"got {type(profile['app_token_revoked'])!r}"
        )

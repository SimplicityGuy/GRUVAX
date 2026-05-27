"""Plan 02 Task 2 — canonical fake-discogsography FastAPI factory.

Tests 5-10 (per PLAN.md):
  5.  Pagination: 450-row seed paginates correctly through limit=200 windows.
  6.  401 on missing / wrong-prefix Authorization header.
  7.  Magic-token 429 returns Retry-After:1 header.
  8.  Magic-token 500 returns plain 500.
  9.  Envelope shape: exactly {user_id, releases, total, offset, limit, has_more}.
  10. Canonical-shim identity: the test-fixtures re-export resolves to the
      same function object as the gruvax._internal canonical module.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def seed_450() -> list[dict[str, object]]:
    """450 synthetic releases — enough to exercise three full-page windows
    plus a partial tail."""
    return [
        {
            "id": str(i),
            "title": f"Release {i}",
            "year": 2026,
            "catalog_number": f"CAT-{i:04d}",
            "artist": f"Artist {i % 30}",
            "label": f"Label {i % 12}",
            "genres": ["Test"],
            "styles": ["Synth"],
            "rating": 0,
            "date_added": "2026-01-01",
            "folder_id": 0,
        }
        for i in range(450)
    ]


async def _client(app):  # type: ignore[no-untyped-def]
    """Helper: ASGI-bound httpx client for the in-process fake app."""
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://fake")


# ── Test 5: pagination ───────────────────────────────────────────────────────


async def test_pagination_three_pages(seed_450: list[dict[str, object]]) -> None:
    """450-row seed: offset 0 / 200 / 400 with limit=200 covers everything."""
    from gruvax._internal.fake_discogsography import create_fake_app

    app = create_fake_app(seed=seed_450)
    async with await _client(app) as client:
        headers = {"Authorization": "Bearer dscg_test_pagination"}

        # Page 1: offset=0
        r = await client.get(
            "/api/user/collection",
            params={"limit": 200, "offset": 0},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 450
        assert body["offset"] == 0
        assert body["limit"] == 200
        assert len(body["releases"]) == 200
        assert body["releases"][0]["id"] == "0"
        assert body["has_more"] is True

        # Page 2: offset=200
        r = await client.get(
            "/api/user/collection",
            params={"limit": 200, "offset": 200},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["releases"]) == 200
        assert body["releases"][0]["id"] == "200"
        assert body["has_more"] is True

        # Page 3: offset=400 → 50 rows + has_more=False
        r = await client.get(
            "/api/user/collection",
            params={"limit": 200, "offset": 400},
            headers=headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["releases"]) == 50
        assert body["has_more"] is False


# ── Test 6: 401 token routing ────────────────────────────────────────────────


async def test_401_when_authorization_missing() -> None:
    """No Authorization header → 401."""
    from gruvax._internal.fake_discogsography import create_fake_app

    app = create_fake_app(seed=[])
    async with await _client(app) as client:
        r = await client.get("/api/user/collection")
        assert r.status_code == 401


async def test_401_when_authorization_lowercase_or_non_dscg() -> None:
    """Any Authorization that doesn't start with 'Bearer dscg_' → 401."""
    from gruvax._internal.fake_discogsography import create_fake_app

    app = create_fake_app(seed=[])
    async with await _client(app) as client:
        r1 = await client.get(
            "/api/user/collection",
            headers={"Authorization": "bearer xxx"},
        )
        assert r1.status_code == 401, "lowercase 'bearer' must NOT be accepted"

        r2 = await client.get(
            "/api/user/collection",
            headers={"Authorization": "Bearer wrong_prefix_xxx"},
        )
        assert r2.status_code == 401, "non-dscg prefix must NOT be accepted"


# ── Test 7 + 8: magic-token error injection ──────────────────────────────────


async def test_magic_token_429_returns_retry_after() -> None:
    """Authorization=='Bearer dscg_force_429' → 429 + Retry-After:1."""
    from gruvax._internal.fake_discogsography import create_fake_app

    app = create_fake_app(seed=[])
    async with await _client(app) as client:
        r = await client.get(
            "/api/user/collection",
            headers={"Authorization": "Bearer dscg_force_429"},
        )
        assert r.status_code == 429
        assert r.headers.get("Retry-After") == "1"


async def test_magic_token_500_returns_server_error() -> None:
    """Authorization=='Bearer dscg_force_500' → 500."""
    from gruvax._internal.fake_discogsography import create_fake_app

    app = create_fake_app(seed=[])
    async with await _client(app) as client:
        r = await client.get(
            "/api/user/collection",
            headers={"Authorization": "Bearer dscg_force_500"},
        )
        assert r.status_code == 500


# ── Test 9: envelope shape conformance ──────────────────────────────────────


async def test_envelope_shape_exact_keys() -> None:
    """A successful response body has exactly the contract keys.

    Per D-04 + cross-repo contract: {user_id, releases, total, offset, limit,
    has_more}. user_id is a UUID string; releases is a list; has_more is bool.
    """
    from gruvax._internal.fake_discogsography import create_fake_app

    custom_user_id = "11111111-2222-3333-4444-555555555555"
    app = create_fake_app(seed=[{"id": "1", "title": "Solo"}], user_id=custom_user_id)
    async with await _client(app) as client:
        r = await client.get(
            "/api/user/collection",
            headers={"Authorization": "Bearer dscg_test"},
        )
        assert r.status_code == 200
        body = r.json()
        expected_keys = {"user_id", "releases", "total", "offset", "limit", "has_more"}
        assert set(body.keys()) == expected_keys, (
            f"unexpected envelope keys: extra={set(body) - expected_keys} "
            f"missing={expected_keys - set(body)}"
        )
        assert body["user_id"] == custom_user_id
        assert isinstance(body["releases"], list)
        assert isinstance(body["has_more"], bool)
        # Total is reported as int, not str.
        assert isinstance(body["total"], int)
        assert isinstance(body["offset"], int)
        assert isinstance(body["limit"], int)


# ── Test 10: canonical-shim identity (D-15 single-module mandate) ────────────


def test_canonical_shim_identity() -> None:
    """tests/fixtures/fake_discogsography.create_fake_app IS the same function
    object as gruvax._internal.fake_discogsography.create_fake_app.

    Enforces D-15: ONE fake-discogsography module. Both consumers (test
    fixtures + Plan 05 Compose sibling) re-export the same callable rather
    than duplicating the implementation.
    """
    from gruvax._internal.fake_discogsography import create_fake_app as canon
    from tests.fixtures.fake_discogsography import create_fake_app as shim

    assert shim is canon, (
        "tests/fixtures/fake_discogsography.py must re-export the canonical "
        "gruvax._internal.fake_discogsography.create_fake_app — DO NOT "
        "duplicate the factory."
    )

"""Unit tests for the in-process fake-discogsography fixture (D-15, API-04 CI).

Tests:
  - test_limit_one: GET /api/user/collection with limit=1 returns a single-release
    page without error. This is a regression guard for the AUTH-02 PAT-validation
    flow which calls _get_page(limit=1, offset=0) to confirm token validity.
"""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
import pytest


@pytest.mark.asyncio
async def test_limit_one() -> None:
    """GET /api/user/collection?limit=1 returns exactly one release, no error.

    Verifies that the fake-discogsography fixture correctly handles limit=1
    requests — required for AUTH-02 PAT-validation calls (RESEARCH.md §Code Examples:
    fake_discogsography limit=1 Support).

    The Query validator accepts ge=1, and seed[0:1] returns a single-item list.
    """
    from gruvax._internal.fake_discogsography import create_fake_app

    seed = [
        {
            "id": str(i),
            "title": f"Test Title {i}",
            "year": 1970 + i,
            "catalog_number": f"TEST-{i:04d}",
            "artist": f"Artist {i}",
            "label": "Test Label",
            "folder_id": 1,
        }
        for i in range(1, 6)
    ]
    app = create_fake_app(seed=seed, user_id="99999999-9999-9999-9999-999999999999")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer dscg_test_token"},
    ) as client:
        response = await client.get("/api/user/collection", params={"limit": 1, "offset": 0})

    assert response.status_code == 200, (
        f"GET /api/user/collection?limit=1 expected 200, got {response.status_code}: "
        f"{response.text}"
    )
    data = response.json()
    assert "releases" in data, "Response must include 'releases' key"
    releases = data["releases"]
    assert len(releases) == 1, (
        f"limit=1 must return exactly 1 release, got {len(releases)}: {releases}"
    )
    assert data["limit"] == 1, f"Response limit must be 1, got {data['limit']}"
    assert data["has_more"] is True, "has_more must be True when seed has more items"
    assert data["user_id"] == "99999999-9999-9999-9999-999999999999", (
        f"user_id must match the configured value, got {data['user_id']!r}"
    )


@pytest.mark.asyncio
async def test_limit_one_empty_seed() -> None:
    """GET /api/user/collection?limit=1 with an empty seed returns 0 releases, no error.

    Verifies that the slice seed[0:1] on an empty list does not raise an error —
    important because a newly-connected profile may have zero releases.
    """
    from gruvax._internal.fake_discogsography import create_fake_app

    app = create_fake_app(seed=[], user_id="99999999-9999-9999-9999-999999999999")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": "Bearer dscg_test_token"},
    ) as client:
        response = await client.get("/api/user/collection", params={"limit": 1, "offset": 0})

    assert response.status_code == 200, (
        f"GET /api/user/collection?limit=1 with empty seed expected 200, "
        f"got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert len(data["releases"]) == 0, "Empty seed must return 0 releases"
    assert data["has_more"] is False, "has_more must be False for empty seed"

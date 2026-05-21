"""Integration tests for the public cube-contents endpoint (CUBE-09).

Tests:
  - test_cube_not_found: GET /api/cubes/{u}/{r}/{c} returns 404 for nonexistent cube
  - test_cube_contents_shape: response includes total_count, fill_level, sample_records

This endpoint is PUBLIC — no auth required (D-15).
Implemented in Plans 03/04 — authored RED in Wave-0 scaffold.

Analog: tests/integration/test_search.py (LifespanManager + AsyncClient pattern).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app


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


@pytest.mark.asyncio(loop_scope="session")
async def test_cube_not_found(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/cubes/{u}/{r}/{c} returns 404 for a cube not in cube_boundaries (CUBE-09).

    Unit 999, Row 99, Col 99 — guaranteed not in the seeded test DB.
    """
    response = await client.get("/api/cubes/999/99/99")
    assert response.status_code == 404, (
        f"Expected 404 for nonexistent cube, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_cube_contents_shape(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/cubes/{u}/{r}/{c} returns total_count, fill_level, sample_records (CUBE-09).

    Uses unit_id=1, row=0, col=0 which is expected to exist in the seeded test DB.
    If the cube doesn't exist (404), the test skips gracefully.
    """
    response = await client.get("/api/cubes/1/0/0")
    if response.status_code == 404:
        pytest.skip("Cube (1,0,0) not in test DB — skipping shape test")

    assert response.status_code == 200, (
        f"Expected 200 for cube contents, got {response.status_code}: {response.text}"
    )
    body = response.json()

    # Required fields per D-14 and Pattern 9
    assert "total_count" in body, "Response must include total_count"
    assert "fill_level" in body, "Response must include fill_level"
    assert "sample_records" in body, "Response must include sample_records"

    # Type checks
    assert isinstance(body["total_count"], int), "total_count must be an integer"
    assert isinstance(body["fill_level"], (int, float)), "fill_level must be a number"
    assert isinstance(body["sample_records"], list), "sample_records must be a list"

    # fill_level must be >= 0.0
    assert body["fill_level"] >= 0.0, "fill_level must be non-negative"

    # sample_records must have ≤ 7 items (default n=7 in sample_records helper)
    assert len(body["sample_records"]) <= 7, (
        f"sample_records must have <= 7 items, got {len(body['sample_records'])}"
    )

    # Each sample record must have release_id, label, catalog_number
    for record in body["sample_records"]:
        assert "release_id" in record, "Sample record must have release_id"
        assert "label" in record, "Sample record must have label"
        assert "catalog_number" in record, "Sample record must have catalog_number"


@pytest.mark.asyncio(loop_scope="session")
async def test_cube_contents_public_no_auth(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/cubes/{u}/{r}/{c} is public — no auth cookie required (D-15).

    Visiting friends on the kiosk can browse cube contents without logging in.
    """
    # Request without any cookies — must not return 401 or 403
    response = await client.get("/api/cubes/1/0/0")
    assert response.status_code in (200, 404), (
        f"Public cube endpoint must return 200 or 404, not auth error. "
        f"Got {response.status_code}"
    )
    assert response.status_code != 401, "Public endpoint must not require authentication"
    assert response.status_code != 403, "Public endpoint must not require CSRF token"

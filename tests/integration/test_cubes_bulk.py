"""Integration tests for GET /api/cubes (bulk endpoint).

Tests:
  - test_cubes_bulk_count: returns 32 rows (2 units × 4×4 = 32 cubes).
  - test_cubes_bulk_shape: each row has {unit_id, row, col, is_empty} fields.
  - test_cubes_bulk_zero_based: row and col values are in 0..3 (0-based).
  - test_cubes_bulk_empties_flagged: at least one cube has is_empty=True
    (synthetic seed includes is_empty=true rows).
  - test_cubes_bulk_no_extra_info: first_label etc. NOT present (slim response).
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
    async with LifespanManager(app) as manager, AsyncClient(
        transport=ASGITransport(app=manager.app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_bulk_count(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/cubes returns exactly 32 rows (2 units × 4×4 grid = 32 cubes)."""
    response = await client.get("/api/cubes")
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "cubes" in body, f"Response missing 'cubes' key: {body}"
    assert len(body["cubes"]) == 32, (
        f"Expected 32 cubes, got {len(body['cubes'])}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_bulk_shape(client) -> None:  # type: ignore[no-untyped-def]
    """Each cube row contains exactly {unit_id, row, col, is_empty}."""
    response = await client.get("/api/cubes")
    assert response.status_code == 200
    body = response.json()
    required_fields = {"unit_id", "row", "col", "is_empty"}
    for cube in body["cubes"]:
        missing = required_fields - cube.keys()
        assert not missing, f"Cube row missing fields {missing}: {cube}"
        assert isinstance(cube["unit_id"], int)
        assert isinstance(cube["row"], int)
        assert isinstance(cube["col"], int)
        assert isinstance(cube["is_empty"], bool)


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_bulk_zero_based(client) -> None:  # type: ignore[no-untyped-def]
    """Row and col are 0-based (values in 0..3 for a 4×4 unit)."""
    response = await client.get("/api/cubes")
    assert response.status_code == 200
    body = response.json()
    for cube in body["cubes"]:
        assert 0 <= cube["row"] <= 3, (
            f"Expected row in 0..3, got {cube['row']} for cube {cube}"
        )
        assert 0 <= cube["col"] <= 3, (
            f"Expected col in 0..3, got {cube['col']} for cube {cube}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_bulk_empties_flagged(client) -> None:  # type: ignore[no-untyped-def]
    """At least one cube has is_empty=True (synthetic seed includes empty cubes)."""
    response = await client.get("/api/cubes")
    assert response.status_code == 200
    body = response.json()
    empty_cubes = [c for c in body["cubes"] if c["is_empty"]]
    assert empty_cubes, (
        "Expected at least one is_empty=True cube in the seed data. "
        f"All cubes: {body['cubes']}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_bulk_no_boundary_details(client) -> None:  # type: ignore[no-untyped-def]
    """Bulk endpoint returns slim rows — no first_label/last_label etc."""
    response = await client.get("/api/cubes")
    assert response.status_code == 200
    body = response.json()
    for cube in body["cubes"]:
        # Boundary detail fields belong to the single-cube endpoint only
        assert "first_label" not in cube, (
            f"Bulk endpoint should not expose first_label: {cube}"
        )
        assert "last_label" not in cube, (
            f"Bulk endpoint should not expose last_label: {cube}"
        )

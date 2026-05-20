"""Integration tests for GET /api/locate and GET /api/units.

Tests:
  - test_locate_covered: covered record returns confidence=0.30,
    sub_cube_interval=null, estimator_version="cube-only-v1".
  - test_locate_not_found: unknown release_id returns HTTP 404 with
    type="release_not_in_collection".
  - test_locate_no_boundary: record in collection but no covering boundary
    returns HTTP 200 with confidence=0, primary_cube=null, label_span=[].
  - test_locate_noninteger_id: release_id="abc" returns HTTP 422.
  - test_units: GET /api/units returns 2 units with rows=4, cols=4.
  - test_cubes_endpoint: GET /api/cubes/{unit}/{row}/{col} returns the boundary.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app
from gruvax.estimator.contract import CUBE_ONLY_CONFIDENCE

# ── Seed constants (stable for the synthetic fixture) ────────────────────────

# release_id=1: Blue Note BLP 4001 — covered by unit_id=1, row=0, col=0 boundary
COVERED_RELEASE_ID = 1
COVERED_EXPECTED_CUBE = {"unit_id": 1, "row": 0, "col": 0}

# release_id=999: not in v_collection (max is 152 in the synthetic seed)
ABSENT_RELEASE_ID = 999

# release_id=111: Saturn SR-9956-2-LP — in v_collection but no boundary covers it.
# The boundary for unit_id=2, row=1, col=3 spans "Saturn"→"ESP", but the label
# range check ("saturn" <= "saturn" <= "esp") fails because "saturn" > "esp"
# alphabetically, so confidence=0.0.
NO_BOUNDARY_RELEASE_ID = 111


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan."""
    app = create_app()
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac:
            yield ac


@pytest.mark.asyncio(loop_scope="session")
async def test_locate_covered(client) -> None:  # type: ignore[no-untyped-def]
    """Covered record returns 200 with the locked LocateResult contract.

    Asserts POS-02 contract (D-10/D-11):
    - confidence == CUBE_ONLY_CONFIDENCE (0.30)
    - sub_cube_interval == null (cube-only-v1, Phase 1)
    - estimator_version == "cube-only-v1"
    - primary_cube is the expected cube for Blue Note BLP 4001
    """
    response = await client.get("/api/locate", params={"release_id": COVERED_RELEASE_ID})
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()

    assert body["confidence"] == pytest.approx(CUBE_ONLY_CONFIDENCE), (
        f"Expected confidence={CUBE_ONLY_CONFIDENCE}, got {body['confidence']}"
    )
    assert body["sub_cube_interval"] is None, (
        f"Expected sub_cube_interval=null, got {body['sub_cube_interval']}"
    )
    assert body["estimator_version"] == "cube-only-v1", (
        f"Expected estimator_version='cube-only-v1', got {body['estimator_version']!r}"
    )
    assert body["release_id"] == COVERED_RELEASE_ID

    # primary_cube should be the expected cube for this label range
    assert body["primary_cube"] is not None, "Expected non-null primary_cube for covered record"
    assert body["primary_cube"] == COVERED_EXPECTED_CUBE, (
        f"Expected primary_cube={COVERED_EXPECTED_CUBE}, got {body['primary_cube']}"
    )

    # label_span must contain at least the primary_cube
    assert COVERED_EXPECTED_CUBE in body["label_span"], (
        f"Expected primary_cube in label_span. label_span={body['label_span']}"
    )

    # generated_at must be an ISO-8601 timestamp
    assert "T" in body.get("generated_at", ""), "generated_at must be ISO-8601"


@pytest.mark.asyncio(loop_scope="session")
async def test_locate_not_found(client) -> None:  # type: ignore[no-untyped-def]
    """Unknown release_id → HTTP 404 with type='release_not_in_collection' (D-12)."""
    response = await client.get("/api/locate", params={"release_id": ABSENT_RELEASE_ID})
    assert response.status_code == 404, (
        f"Expected 404 for absent release, got {response.status_code}: {response.text}"
    )
    body = response.json()
    detail = body.get("detail", body)
    assert detail.get("type") == "release_not_in_collection", (
        f"Expected type='release_not_in_collection' in detail, got: {detail}"
    )
    assert detail.get("release_id") == ABSENT_RELEASE_ID


@pytest.mark.asyncio(loop_scope="session")
async def test_locate_no_boundary(client) -> None:  # type: ignore[no-untyped-def]
    """Record in collection with no covering boundary → HTTP 200, confidence=0.

    Per D-12 error semantics: HTTP 200 (not 404) with:
    - confidence == 0.0
    - primary_cube == null
    - label_span == []
    """
    response = await client.get("/api/locate", params={"release_id": NO_BOUNDARY_RELEASE_ID})
    assert response.status_code == 200, (
        f"Expected 200 for no-boundary case, got {response.status_code}: {response.text}"
    )
    body = response.json()

    assert body["confidence"] == 0.0, (
        f"Expected confidence=0.0 for no-boundary case, got {body['confidence']}"
    )
    assert body["primary_cube"] is None, (
        f"Expected primary_cube=null, got {body['primary_cube']}"
    )
    assert body["label_span"] == [], (
        f"Expected label_span=[], got {body['label_span']}"
    )
    assert body["sub_cube_interval"] is None


@pytest.mark.asyncio(loop_scope="session")
async def test_locate_noninteger_id(client) -> None:  # type: ignore[no-untyped-def]
    """T-01-09: release_id='abc' returns HTTP 422 (typed int param rejects strings)."""
    response = await client.get("/api/locate", params={"release_id": "abc"})
    assert response.status_code == 422, (
        f"Expected 422 for non-integer release_id, got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_locate_response_shape(client) -> None:  # type: ignore[no-untyped-def]
    """LocateResult response has all required keys."""
    response = await client.get("/api/locate", params={"release_id": COVERED_RELEASE_ID})
    assert response.status_code == 200
    body = response.json()
    required_keys = {
        "release_id", "primary_cube", "label_span",
        "sub_cube_interval", "confidence", "generated_at", "estimator_version",
    }
    assert required_keys.issubset(body.keys()), (
        f"Missing keys in LocateResult: {required_keys - body.keys()}"
    )


# ── /api/units tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_units(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/units returns 2 units with rows=4, cols=4 (CUBE-01)."""
    response = await client.get("/api/units")
    assert response.status_code == 200
    body = response.json()
    assert "units" in body

    units = body["units"]
    assert len(units) == 2, f"Expected 2 units, got {len(units)}"

    for unit in units:
        assert unit["rows"] == 4, f"Expected rows=4, got {unit['rows']}"
        assert unit["cols"] == 4, f"Expected cols=4, got {unit['cols']}"
        assert "display_name" in unit
        assert "id" in unit
        assert "ordering" in unit


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/cubes/{unit_id}/{row}/{col} returns the boundary row."""
    # unit_id=1, row=0, col=0 is the Blue Note BLP 4001-4020 cube
    response = await client.get("/api/cubes/1/0/0")
    assert response.status_code == 200
    body = response.json()
    assert body["unit_id"] == 1
    assert body["row"] == 0
    assert body["col"] == 0
    assert body["first_label"] == "Blue Note"
    assert body["is_empty"] is False


@pytest.mark.asyncio(loop_scope="session")
async def test_cubes_not_found(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/cubes/99/99/99 returns HTTP 404 for non-existent cube."""
    response = await client.get("/api/cubes/99/99/99")
    assert response.status_code == 404

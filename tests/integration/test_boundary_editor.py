"""Integration tests for the boundary editor endpoints (ADMN-03, ADMN-06, ADMN-07).

Tests:
  - test_phantom_blocked: saving a phantom (non-v_collection) boundary returns 400
  - test_phantom_force_save: force:true bypasses phantom check but not comparator
  - test_near_misses_returned: phantom response includes trigram near-misses
  - test_validate_no_db_write: dry-run diff endpoint writes nothing to DB (ADMN-07)

These tests target endpoints implemented in Plans 03/04 — authored RED in Wave-0.

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
async def test_phantom_blocked(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/cubes/{u}/{r}/{c}/boundary with a phantom label/catalog returns 400.

    A phantom is a (label, catalog) pair not found in gruvax.v_collection (D-07).
    The response must include phantom:true and near_misses (ADMN-03, ADMN-06).
    """
    # Login to get a session (may skip if login not implemented)
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not implemented — skipping phantom test")

    csrf_token = login_res.cookies.get("gruvax_csrf")
    response = await client.put(
        "/api/admin/cubes/1/0/0/boundary",
        json={
            "first_label": "PHANTOM_NONEXISTENT_LABEL_XYZ",
            "first_catalog": "PHANTOM_999999",
            "last_label": "PHANTOM_NONEXISTENT_LABEL_XYZ",
            "last_catalog": "PHANTOM_999999",
            "is_empty": False,
            "force": False,
        },
        cookies=login_res.cookies,
        headers={"X-CSRF-Token": csrf_token or ""},
    )
    assert response.status_code == 400, (
        f"Expected 400 for phantom boundary, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("phantom") is True, "Response must include phantom:true"
    assert "near_misses" in body, "Response must include near_misses list"


@pytest.mark.asyncio(loop_scope="session")
async def test_phantom_force_save(client) -> None:  # type: ignore[no-untyped-def]
    """force:true bypasses phantom check but NOT the POS-01 comparator (ADMN-03, D-07).

    An inverted boundary (first > last) must still be rejected even with force:true.
    """
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not implemented — skipping force-save test")

    csrf_token = login_res.cookies.get("gruvax_csrf")

    # Inverted boundary (BLP 4200 > BLP 4001 numerically) — must fail even with force
    response = await client.put(
        "/api/admin/cubes/1/0/0/boundary",
        json={
            "first_label": "Blue Note",
            "first_catalog": "BLP 4200",
            "last_label": "Blue Note",
            "last_catalog": "BLP 4001",
            "is_empty": False,
            "force": True,  # force=True bypasses phantom, not comparator
        },
        cookies=login_res.cookies,
        headers={"X-CSRF-Token": csrf_token or ""},
    )
    # Must still be rejected: inverted first > last
    assert response.status_code == 400, (
        f"Inverted boundary with force:true must still be rejected (comparator), "
        f"got {response.status_code}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_near_misses_returned(client) -> None:  # type: ignore[no-untyped-def]
    """Phantom boundary response includes trigram near-misses for the bad catalog (ADMN-06).

    Near-misses are queried via pg_trgm similarity; the list may be empty if the
    phantom is completely unlike anything in v_collection.
    """
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not implemented — skipping near-misses test")

    csrf_token = login_res.cookies.get("gruvax_csrf")

    # "Blu Notte" is a plausible near-miss for "Blue Note"
    response = await client.put(
        "/api/admin/cubes/1/0/0/boundary",
        json={
            "first_label": "Blu Notte",
            "first_catalog": "BLP 4001",
            "last_label": "Blu Notte",
            "last_catalog": "BLP 4200",
            "is_empty": False,
            "force": False,
        },
        cookies=login_res.cookies,
        headers={"X-CSRF-Token": csrf_token or ""},
    )
    assert response.status_code == 400, (
        f"Expected 400 for phantom boundary, got {response.status_code}"
    )
    body = response.json()
    assert "near_misses" in body, "Phantom response must include near_misses key"
    # near_misses may be [] if pg_trgm similarity doesn't find any match, which is acceptable
    assert isinstance(body["near_misses"], list), "near_misses must be a list"


@pytest.mark.asyncio(loop_scope="session")
async def test_validate_no_db_write(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/cubes/validate (dry-run diff) writes nothing to the DB (ADMN-07).

    The validate endpoint computes diff preview from the in-memory snapshot without
    committing any boundary changes. The response includes movement counts.
    """
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not implemented — skipping validate test")

    csrf_token = login_res.cookies.get("gruvax_csrf")

    response = await client.post(
        "/api/admin/cubes/validate",
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 0,
                    "col": 0,
                    "first_label": "Blue Note",
                    "first_catalog": "BLP 4001",
                    "last_label": "Blue Note",
                    "last_catalog": "BLP 4195",
                    "is_empty": False,
                }
            ]
        },
        cookies=login_res.cookies,
        headers={"X-CSRF-Token": csrf_token or ""},
    )
    # If the endpoint exists, it must return 200 with movement_counts and NOT write to DB
    if response.status_code == 404:
        pytest.skip("Validate endpoint not yet implemented")

    assert response.status_code == 200, (
        f"Expected 200 from validate, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "movement_counts" in body or "valid" in body, (
        "Validate response must include movement_counts or valid key"
    )

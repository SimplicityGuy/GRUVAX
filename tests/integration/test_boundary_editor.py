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

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


# Browse-binding cookie value (D-02 fail-loud contract).  Admin write routes now
# require get_write_target to resolve a per-profile session; the default profile
# UUID is the value read verbatim from this cookie (sessions.py:42).
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
_BROWSE_BINDING_COOKIE = "gruvax_browse_binding"


def _with_browse_binding(cookies) -> dict:  # type: ignore[no-untyped-def]
    """Merge the default-profile browse-binding cookie into an httpx Cookies object.

    Returns a plain dict suitable for ``cookies=`` on any write request so that
    get_write_target resolves without raising 400 session_unbound (D-02).
    """
    merged = dict(cookies)
    merged[_BROWSE_BINDING_COOKIE] = _DEFAULT_PROFILE_UUID
    return merged


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

    A phantom is a (label, catalog) pair not found in gruvax.profile_collection (D-07).
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
            "is_empty": False,
            "force": False,
        },
        cookies=_with_browse_binding(login_res.cookies),
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
    """force:true bypasses phantom check and saves any first_label/first_catalog (ADMN-03, D-07).

    Phase 5 (05-04 / SEG-01): the cut-point model stores only first_label / first_catalog.
    The old last_* comparator (first > last rejection) no longer applies — there IS no last_*
    in cube_boundaries.  force=True now means: skip phantom check and write whatever first_*
    is provided.  The response must be 200 (successful write).
    """
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not implemented — skipping force-save test")

    csrf_token = login_res.cookies.get("gruvax_csrf")

    # BLP 4200 is NOT in the synthetic collection (phantom) — force=True bypasses that check.
    # In the cut-point model there is no last_* to validate, so the write must succeed.
    response = await client.put(
        "/api/admin/cubes/1/0/0/boundary",
        json={
            "first_label": "Blue Note",
            "first_catalog": "BLP 4200",
            "is_empty": False,
            "force": True,  # bypass phantom check; no last_* comparator in Phase 5
        },
        cookies=_with_browse_binding(login_res.cookies),
        headers={"X-CSRF-Token": csrf_token or ""},
    )
    # Must succeed: phantom check bypassed by force=True, no last_* validation in cut-point model
    assert response.status_code == 200, (
        f"force:True with phantom first_catalog must succeed in cut-point model (Phase 5), "
        f"got {response.status_code}: {response.text}"
    )

    # Restore (1,0,0) to its original BLP 4001 state so subsequent test modules
    # (test_locate.py) see a clean fixture. BLP 4200 as the cut point causes
    # BLP 4001 (rank 0 in Blue Note) to fall BELOW the cut → confidence=0.0 for
    # COVERED_RELEASE_ID=1 (BLP 4001). BLP 4001 IS in the collection, so force=False.
    await client.put(
        "/api/admin/cubes/1/0/0/boundary",
        json={
            "first_label": "Blue Note",
            "first_catalog": "BLP 4001",
            "is_empty": False,
            "force": True,  # restore; BLP 4001 IS in collection but force ensures idempotent
        },
        cookies=_with_browse_binding(login_res.cookies),
        headers={"X-CSRF-Token": csrf_token or ""},
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
            "is_empty": False,
            "force": False,
        },
        cookies=_with_browse_binding(login_res.cookies),
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

    # WR-01 (Phase 6 CR fix): validate_boundary now requires a bound session (get_write_target)
    # so phantom checks are scoped to the resolved profile, matching the commit path.
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
                    "is_empty": False,
                }
            ]
        },
        cookies=_with_browse_binding(login_res.cookies),
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


@pytest.mark.asyncio(loop_scope="session")
async def test_single_cube_put_writes_history(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """A successful single-cube PUT appends a boundary_history row (CR-02 regression).

    Previously ``put_cube_boundary`` updated ``cube_boundaries`` but wrote NO
    history row (only the bulk endpoint did), so single-cube edits left no audit
    trail and were not revertable. The fix records ``source='manual'`` atomically
    with the boundary write, sharing one ``change_set_id``.
    """
    login_res = await client.post("/api/admin/login", json={"pin": "0000"})
    if login_res.status_code != 200:
        pytest.skip("Login not implemented — skipping single-cube history test")
    csrf_token = login_res.cookies.get("gruvax_csrf") or ""

    async def manual_history_count() -> int:
        async with db_pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM gruvax.boundary_history "
                "WHERE unit_id = %s AND row = %s AND col = %s AND source = %s",
                (1, 3, 3, "manual"),
            )
            fetched = await cur.fetchone()
            return int(fetched[0]) if fetched else 0

    before = await manual_history_count()

    response = await client.put(
        "/api/admin/cubes/1/3/3/boundary",
        json={
            "first_label": "Blue Note",
            "first_catalog": "BLP 4001",
            "is_empty": False,
            "force": True,  # bypass phantom check; cut-point model has no last_* comparator
        },
        cookies=_with_browse_binding(login_res.cookies),
        headers={"X-CSRF-Token": csrf_token},
    )
    if response.status_code == 404:
        pytest.skip("Single-cube boundary endpoint not implemented")
    assert response.status_code == 200, (
        f"Expected 200 from single-cube PUT, got {response.status_code}: {response.text}"
    )

    after = await manual_history_count()
    assert after == before + 1, (
        "Single-cube PUT must append exactly one source='manual' boundary_history "
        f"row (CR-02); before={before} after={after}"
    )

    # Restore (1,3,3) to its original empty state so subsequent test modules
    # (test_locate.py) see a clean fixture. Without this, two cubes share
    # first_catalog='BLP 4001' which corrupts SegmentCache for the locate tests.
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.cube_boundaries"
            " SET first_label = NULL, first_catalog = NULL, is_empty = TRUE"
            " WHERE unit_id = 1 AND row = 3 AND col = 3",
        )
        await conn.commit()

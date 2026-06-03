"""Integration tests for POST /api/admin/import/boundaries (ADMN-05).

Wave-0 RED scaffold — authored before the import endpoint exists.
Tests assert on expected status codes so that an unimplemented endpoint (404)
fails the assertion rather than silently skipping.

Target endpoint: POST /api/admin/import/boundaries

Tests:
  - test_csv_import: upload a synthetic CSV → 200, source='csv' in history
  - test_yaml_import: upload a synthetic YAML → 200, source='yaml' in history
  - test_partial_import: 16-cube subset → remaining cubes become is_empty
  - test_phantom_row_rejected: file with phantom label → 400, ZERO partial DB state
  - test_contiguity_violation: non-adjacent label scatter → SEG-05 reject, no partial state
  - test_atomicity: failing row mid-import → ZERO partial state in DB

No real collection data — only made-up labels and catalog numbers.
"""

from __future__ import annotations

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


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


async def _login(client) -> dict:  # type: ignore[no-untyped-def]
    """Helper: log in and return cookies + csrf token dict.

    Merges the browse-binding cookie (D-02 fail-loud contract) so that admin
    write requests resolve the per-profile session required by get_write_target.
    """
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    # Bind the default profile so get_write_target resolves without session_unbound (D-02).
    cookies["gruvax_browse_binding"] = "00000000-0000-0000-0000-000000000001"
    return {
        "cookies": cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


def _make_synthetic_csv(cubes: list[dict]) -> bytes:
    """Build a minimal CSV import file from a list of cube dicts (synthetic data only)."""
    lines = ["unit_id,row,col,first_label,first_catalog,is_empty"]
    for c in cubes:
        is_empty_str = "true" if c.get("is_empty") else "false"
        label = c.get("first_label") or ""
        catalog = c.get("first_catalog") or ""
        lines.append(f"{c['unit_id']},{c['row']},{c['col']},{label},{catalog},{is_empty_str}")
    return "\n".join(lines).encode()


def _make_synthetic_yaml(cubes: list[dict]) -> bytes:
    """Build a minimal YAML import file from a list of cube dicts (synthetic data only)."""
    cube_lines = []
    for c in cubes:
        cube_lines.append(
            f"  - unit_id: {c['unit_id']}\n"
            f"    row: {c['row']}\n"
            f"    col: {c['col']}\n"
            f"    is_empty: {str(c.get('is_empty', False)).lower()}\n"
            + (
                f'    first_label: "{c["first_label"]}"\n'
                f'    first_catalog: "{c["first_catalog"]}"\n'
                if not c.get("is_empty")
                else ""
            )
        )
    content = 'version: "1"\ncubes:\n' + "".join(cube_lines)
    return content.encode()


async def _seed_boundaries_via_bulk(client, auth, cubes) -> None:  # type: ignore[no-untyped-def]
    """Commit ``cubes`` as the CURRENT boundary via POST /admin/cubes/bulk (force=True).

    Makes the import tests self-contained instead of depending on cross-test
    boundary state on the shared dev DB. Import phantom re-validation is skipped
    for rows that equal the current committed boundary (G3 identity-skip, 07-07),
    so once these synthetic cubes are the current boundary, re-importing the same
    set returns 200 rather than 400 phantom_boundary. ``force=True`` bypasses the
    phantom check on the bulk write itself — these synthetic labels/catalogs are
    deliberately absent from the dev v_collection.
    """
    import uuid

    updates = [
        {
            "unit_id": c["unit_id"],
            "row": c["row"],
            "col": c["col"],
            "first_label": c["first_label"],
            "first_catalog": c["first_catalog"],
            "is_empty": c.get("is_empty", False),
            "force": True,
        }
        for c in cubes
    ]
    resp = await client.post(
        "/api/admin/cubes/bulk",
        json={"updates": updates, "source": "bulk"},
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
            **cookie_header(auth["cookies"]),
        },
    )
    assert resp.status_code == 200, f"Seed via bulk failed: {resp.status_code}: {resp.text}"


@pytest.mark.asyncio(loop_scope="session")
async def test_csv_import(client, four_cube_boundaries) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/import/boundaries with a synthetic CSV → 200, source='csv' in history.

    Asserts on 200 so an unimplemented endpoint (404) fails RED (D-04).
    Synthetic labels only; no real collection CSV referenced.
    """
    auth = await _login(client)
    assert auth, "Login must be available for CSV import test"

    # Seed the synthetic cubes as the current boundary first so the import's
    # phantom re-validation is correctly skipped (G3 identity-skip) regardless of
    # what other modules left on the shared dev DB.
    await _seed_boundaries_via_bulk(client, auth, four_cube_boundaries)

    csv_bytes = _make_synthetic_csv(four_cube_boundaries)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=csv_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "text/csv",
            **cookie_header(auth["cookies"]),
        },
    )
    # Expect 200 — unimplemented endpoint returns 404 → test fails RED as intended
    assert response.status_code == 200, (
        f"Expected 200 from import/boundaries (CSV), got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "change_set_id" in body, f"Response missing change_set_id: {body}"


@pytest.mark.asyncio(loop_scope="session")
async def test_yaml_import(client, four_cube_boundaries) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/import/boundaries with a synthetic YAML → 200, source='yaml' in history.

    Asserts on 200 so an unimplemented endpoint (404) fails RED (D-04).
    Synthetic labels only; no real collection YAML referenced.
    """
    auth = await _login(client)
    assert auth, "Login must be available for YAML import test"

    # Seed the synthetic cubes as the current boundary first (see test_csv_import).
    await _seed_boundaries_via_bulk(client, auth, four_cube_boundaries)

    yaml_bytes = _make_synthetic_yaml(four_cube_boundaries)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 from import/boundaries (YAML), got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "change_set_id" in body, f"Response missing change_set_id: {body}"


@pytest.mark.asyncio(loop_scope="session")
async def test_partial_import(client) -> None:  # type: ignore[no-untyped-def]
    """Partial import (16 of 32 cubes): remaining cubes become is_empty (D-09 atomic replace).

    Upload only unit_id=1 cubes (16 cubes); unit_id=2 cubes should become is_empty.
    Asserts 200 on the import endpoint — 404 fails RED as intended.

    Uses a CONTIGUOUS unit_id=1 layout (4 synthetic labels, each in a contiguous
    run of 4 cubes matching the global sort order) so the import passes SEG-05
    contiguity validation. The shared ``thirty_two_cube_boundaries`` fixture
    cycles labels per-cube (non-contiguous) and is unsuitable for a *successful*
    import. Synthetic data only.
    """
    auth = await _login(client)
    assert auth, "Login must be available for partial import test"

    # Contiguous unit_id=1 layout: label idx//4 → 4 cubes per label, physical
    # order (row, col)=divmod(idx, 4) matches the (label, catalog) global sort.
    _labels = [("Atlantic", "ATL"), ("Blue Note", "BNL"), ("Columbia", "COL"), ("Impulse", "IMP")]
    partial_cubes = []
    for idx in range(16):
        row, col = divmod(idx, 4)
        label_name, prefix = _labels[idx // 4]
        partial_cubes.append(
            {
                "unit_id": 1,
                "row": row,
                "col": col,
                "first_label": label_name,
                "first_catalog": f"{prefix}-{idx + 1:03d}",
                "is_empty": False,
            }
        )
    # Seed those cubes as the current boundary first so the re-import's phantom
    # re-validation is skipped (G3 identity-skip); unit_id=2 cubes become is_empty.
    await _seed_boundaries_via_bulk(client, auth, partial_cubes)
    yaml_bytes = _make_synthetic_yaml(partial_cubes)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    # 200 expected — import fills missing cubes with is_empty; 404 fails RED
    assert response.status_code == 200, (
        f"Expected 200 from partial import, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_phantom_row_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """Import with a phantom label/catalog pair → 400, ZERO partial DB state (Pitfall 6/7).

    The phantom check must fire before any write. On 400, no rows may be
    committed to cube_boundaries or boundary_history.
    Asserts 400 — unimplemented endpoint returns 404 → fails RED as intended.
    """
    auth = await _login(client)
    assert auth, "Login must be available for phantom row rejection test"

    # Label/catalog that does not exist in v_collection (phantom)
    phantom_cubes = [
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": "Phantom Label XYZ",
            "first_catalog": "PHANTOM-9999",
            "is_empty": False,
        }
    ]
    yaml_bytes = _make_synthetic_yaml(phantom_cubes)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    # Expect 400 phantom_boundary — unimplemented endpoint (404) fails RED
    assert response.status_code == 400, (
        f"Expected 400 from phantom row import, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("type") == "phantom_boundary", f"Expected type='phantom_boundary', got: {body}"


@pytest.mark.asyncio(loop_scope="session")
async def test_contiguity_violation(client) -> None:  # type: ignore[no-untyped-def]
    """Import with non-adjacent label scatter → SEG-05 reject, no partial state.

    A boundary set where the same label appears in non-contiguous cubes violates
    SEG-05. The endpoint must reject with 400 before any write.
    Asserts 400 — unimplemented endpoint (404) fails RED as intended.
    """
    auth = await _login(client)
    assert auth, "Login must be available for contiguity violation test"

    # Two cubes for the same label at non-adjacent positions (e.g., col 0 and col 3)
    # These labels are synthetic — force=True bypasses phantom but contiguity is checked
    non_contiguous_cubes = [
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": "Atlantic",
            "first_catalog": "ATL-C01",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 1,
            "first_label": "Columbia",
            "first_catalog": "COL-C01",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 2,
            "first_label": "Atlantic",  # non-contiguous reuse of Atlantic
            "first_catalog": "ATL-C02",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 3,
            "first_label": "Blue Note",
            "first_catalog": "BNL-C01",
            "is_empty": False,
        },
    ]
    yaml_bytes = _make_synthetic_yaml(non_contiguous_cubes)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    # Expect 400 contiguity rejection — unimplemented (404) fails RED
    assert response.status_code == 400, (
        f"Expected 400 from contiguity violation, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_unchanged_unmatchable_row_skips_phantom(client, four_cube_boundaries) -> None:  # type: ignore[no-untyped-def]
    """G3 identity-skip: a committed row whose (label, catalog) is absent from v_collection
    is SKIPPED from phantom re-validation on re-import (BAK-01, SC4, Pitfall 22).

    Without the G3 skip this test would return 400 phantom_boundary — proving the skip fires.

    Steps:
      1. Seed the four_cube_boundaries state via POST /api/admin/cubes/bulk with force=True on
         each edit (bypass phantom — synthetic labels not in dev v_collection).
      2. Build a YAML file equal to the EXACT seeded set (all four cubes — a full set, so the
         D-09 replace-all fill does not turn untouched cubes into is_empty).
      3. POST /api/admin/import/boundaries (plain, no dry_run) → assert 200 (identity-skip fired).

    Synthetic data only (four_cube_boundaries uses made-up labels not in dev v_collection).
    """
    auth = await _login(client)
    assert auth, "Login must be available for identity-skip test"

    import uuid

    # Step 1: Seed the committed state with force=True per edit (bypass phantom)
    updates_with_force = [
        {
            "unit_id": c["unit_id"],
            "row": c["row"],
            "col": c["col"],
            "first_label": c["first_label"],
            "first_catalog": c["first_catalog"],
            "is_empty": c.get("is_empty", False),
            "force": True,  # bypass phantom — these labels are NOT in dev v_collection
        }
        for c in four_cube_boundaries
    ]
    seed_resp = await client.post(
        "/api/admin/cubes/bulk",
        json={"updates": updates_with_force, "source": "bulk"},
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Idempotency-Key": str(uuid.uuid4()),
            **cookie_header(auth["cookies"]),
        },
    )
    assert seed_resp.status_code == 200, (
        f"Seed via bulk failed: {seed_resp.status_code}: {seed_resp.text}"
    )

    # Step 2: Build a YAML file that exactly matches the seeded state
    yaml_bytes = _make_synthetic_yaml(four_cube_boundaries)

    # Step 3: Import the file — identity-skip must fire, returning 200 (NOT 400 phantom_boundary)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    assert response.status_code == 200, (
        f"Expected 200 from identity re-import (G3 skip), got {response.status_code}: "
        f"{response.text}"
    )
    body = response.json()
    assert "change_set_id" in body, f"Response missing change_set_id: {body}"


@pytest.mark.asyncio(loop_scope="session")
async def test_atomicity(client, four_cube_boundaries) -> None:  # type: ignore[no-untyped-def]
    """Failing row mid-import → ZERO partial state in DB (SC2, Pitfall 7).

    A mixed payload with valid synthetic cubes plus one phantom row must result
    in a 400 with zero rows written. The transaction must be fully rolled back.
    Asserts 400 — unimplemented endpoint (404) fails RED as intended.
    Synthetic data only.
    """
    auth = await _login(client)
    assert auth, "Login must be available for atomicity test"

    # Valid cubes followed by one phantom — the phantom should roll back all writes
    mixed_cubes = [
        *list(four_cube_boundaries),
        {
            "unit_id": 1,
            "row": 3,
            "col": 3,
            "first_label": "Phantom Mid Import ZZZZ",
            "first_catalog": "PHANTOM-MID-9999",
            "is_empty": False,
        },
    ]
    yaml_bytes = _make_synthetic_yaml(mixed_cubes)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml_bytes,
        headers={
            "X-CSRF-Token": auth["csrf_token"],
            "Content-Type": "application/x-yaml",
            **cookie_header(auth["cookies"]),
        },
    )
    # Must reject with 400 and no partial state — 404 fails RED
    assert response.status_code == 400, (
        f"Expected 400 from atomicity failure, got {response.status_code}: {response.text}"
    )

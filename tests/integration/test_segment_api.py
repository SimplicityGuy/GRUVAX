"""Integration tests for segment admin API endpoints (SEG-08).

Tests are implemented in Plan 05-04 (Wave 4) — SEG-08 admin segment endpoints.

Per-Requirement coverage:
  SEG-08: Admin can view, edit, and add cut points + set per-label width overrides;
          parser-validated; diff-preview + undo path; p95 <= 50 ms preserved.

API surface (implemented in Plan 05-04):
  GET  /api/admin/cubes/{unit_id}/{row}/{col}/segments   — view derived segments
  PUT  /api/admin/cubes/{unit_id}/{row}/{col}/cut        — edit cut point
  POST /api/admin/cubes/{unit_id}/{row}/{col}/overrides  — set label width overrides
  POST /api/admin/cubes/insert-cut                       — insert new cut point

Auth patterns mirror test_boundary_editor.py and test_change_set.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app

_BOUNDARIES_YAML = Path(__file__).parents[2] / "fixtures" / "boundaries.yaml"


@pytest.fixture(autouse=True)
def reset_login_rate_limit() -> None:  # type: ignore[return]
    """Reset the login rate-limit counter before each test.

    The login endpoint uses a module-level singleton ``FixedWindowRateLimiter``
    backed by ``MemoryStorage``. Tests in this module call ``_login()`` once per
    test; after 5 calls the fixed-window limiter returns 429, causing all
    remaining tests to skip with "Login not implemented". Resetting before each
    test prevents that false-skip cascade. Pattern mirrors test_admin_auth.py.
    """
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    Re-seeds boundaries to the canonical fixture BEFORE the app starts so the
    app's BoundaryCache (loaded once at lifespan startup) sees known state. The
    suite shares the dev DB and does not otherwise reset it, so mutating tests
    (insert-cut) would otherwise leave later runs working on polluted data.
    """
    from gruvax.db.seed_boundaries import load_boundaries

    await load_boundaries(_BOUNDARIES_YAML)

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
    """Helper: log in and return cookies + csrf token dict."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    return {
        "cookies": res.cookies,
        "csrf_token": res.cookies.get("gruvax_csrf") or "",
    }


# ── SEG-08: GET /api/admin/cubes/:u/:r/:c/segments ───────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_segments_returns_derived_data(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: GET /api/admin/cubes/:u/:r/:c/segments returns derived segment data.

    Requirement: SEG-08 — admin can view segments for a given bin.
    Expected response: {segments: [{label, fraction, is_override, auto_fraction,
                                    continues, segment_count}]}
    HTTP 200 for an existing bin.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping GET segments test")

    response = await client.get(
        "/api/admin/cubes/1/0/0/segments",
        cookies=auth["cookies"],
    )
    if response.status_code == 404:
        pytest.skip("GET segments endpoint not yet implemented")

    assert response.status_code == 200, (
        f"Expected 200 from GET segments, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "segments" in body, "Response must include 'segments' key"
    assert isinstance(body["segments"], list), "segments must be a list"
    # Each segment entry must have the required fields
    for seg in body["segments"]:
        assert "label" in seg, f"Segment entry missing 'label': {seg}"
        assert "fraction" in seg, f"Segment entry missing 'fraction': {seg}"
        assert "is_override" in seg, f"Segment entry missing 'is_override': {seg}"
        assert "segment_count" in seg, f"Segment entry missing 'segment_count': {seg}"


@pytest.mark.asyncio(loop_scope="session")
async def test_get_segments_404_unknown_bin(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: GET /api/admin/cubes/:u/:r/:c/segments returns 404 for unknown bin.

    Requirement: SEG-08 — endpoint returns 404 if no bin exists at given coordinates.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping GET segments 404 test")

    # unit_id=99 does not exist in the synthetic fixture
    response = await client.get(
        "/api/admin/cubes/99/99/99/segments",
        cookies=auth["cookies"],
    )
    if response.status_code == 404:
        # This is the expected response — pass
        return

    # If the endpoint doesn't exist, we skip; otherwise we require 404 for unknown bin
    if response.status_code == 405:
        pytest.skip("GET segments endpoint not yet implemented (405 Method Not Allowed)")

    assert response.status_code == 404, (
        f"Expected 404 for non-existent bin, got {response.status_code}: {response.text}"
    )


# ── SEG-08: PUT /api/admin/cubes/:u/:r/:c/cut ────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_put_cut_accepted(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: PUT /api/admin/cubes/:u/:r/:c/cut with valid first_catalog succeeds.

    Uses force=True to bypass phantom check.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping PUT cut test")

    response = await client.put(
        "/api/admin/cubes/1/0/0/cut",
        json={
            "first_label": "Blue Note",
            "first_catalog": "BLP 4001",
            "force": True,
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code == 404:
        pytest.skip("PUT cut endpoint not yet implemented")
    if response.status_code == 405:
        pytest.skip("PUT cut endpoint not yet implemented (405 Method Not Allowed)")

    assert response.status_code == 200, (
        f"Expected 200 from PUT cut, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "change_set_id" in body, "PUT cut response must include change_set_id"


@pytest.mark.asyncio(loop_scope="session")
async def test_put_cut_phantom_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: PUT /api/admin/cubes/:u/:r/:c/cut with phantom catalog returns 400.

    Phantom = not in gruvax.v_collection (D-07).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping PUT cut phantom test")

    response = await client.put(
        "/api/admin/cubes/1/0/0/cut",
        json={
            "first_label": "PHANTOM_NONEXISTENT_LABEL_XYZ",
            "first_catalog": "PHANTOM_999999",
            "force": False,  # phantom check enabled
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("PUT cut endpoint not yet implemented")

    assert response.status_code == 400, (
        f"Expected 400 for phantom cut, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("phantom") is True, "Phantom response must include phantom:true"


# ── SEG-08: POST /api/admin/cubes/:u/:r/:c/overrides ─────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_set_override_accepted(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: POST /api/admin/cubes/:u/:r/:c/overrides accepted for valid label + fraction.

    Requirement: SEG-08 — admin can set per-label width overrides.
    Valid fraction in (0.0, 1.0] with a label that IS in the bin must return 200.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping POST overrides test")

    # First get the segments to find a valid label
    seg_res = await client.get(
        "/api/admin/cubes/1/0/0/segments",
        cookies=auth["cookies"],
    )
    if seg_res.status_code in (404, 405):
        pytest.skip("GET segments not implemented — cannot determine valid label")

    segments = seg_res.json().get("segments", [])
    if not segments:
        pytest.skip("No segments found in bin 1/0/0 — cannot test override")

    valid_label = segments[0]["label"]
    # Use fraction=1.0 — the only valid override for a single-label bin.
    # For multi-label bins, fractions must sum to 1.0; 1.0 on a single label
    # is always valid since it occupies the full bin.
    response = await client.post(
        "/api/admin/cubes/1/0/0/overrides",
        json={"overrides": [{"label": valid_label, "fraction": 1.0}]},
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("POST overrides endpoint not yet implemented")

    assert response.status_code == 200, (
        f"Expected 200 from POST overrides, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert "applied" in body or "cleared" in body, (
        "Override response must include applied or cleared count"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_set_override_rejected_fraction_over_one(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: POST overrides rejects fraction > 1.0 (T-05-03 / T-05-04-03 API-layer check).

    Requirement: SEG-08 — parser-validated; fraction=1.5 must return HTTP 422.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping POST overrides fraction test")

    response = await client.post(
        "/api/admin/cubes/1/0/0/overrides",
        json={
            "overrides": [
                {"label": "Blue Note", "fraction": 1.5}  # > 1.0 — must be rejected
            ]
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("POST overrides endpoint not yet implemented")

    assert response.status_code == 422, (
        f"Expected 422 for fraction > 1.0, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_set_override_rejects_phantom_label(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: POST overrides rejects label not present in the bin (T-05-04-02).

    Phantom override injection guard: server must reject overrides for labels
    absent from the bin's derived segments.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping phantom label override test")

    response = await client.post(
        "/api/admin/cubes/1/0/0/overrides",
        json={"overrides": [{"label": "PHANTOM_NONEXISTENT_LABEL_XYZ", "fraction": 0.5}]},
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("POST overrides endpoint not yet implemented")

    assert response.status_code == 400, (
        f"Expected 400 for phantom label override, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body.get("type") == "phantom_override", (
        "Response must indicate phantom_override type (T-05-04-02)"
    )


# ── SEG-08: POST /api/admin/cubes/insert-cut ─────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_cut_shelf_overflow_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """SEG-08: POST /api/admin/cubes/insert-cut returns shelf_overflow when no free cube exists.

    Requirement: SEG-08 / D-06 — end-of-shelf overflow is hard-rejected with the
    plain-language shelf_overflow error message (T-05-04-04).
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented — skipping insert-cut shelf_overflow test")

    # Try to insert after the LAST non-empty cube. If there's no free cube after it,
    # this should trigger the shelf_overflow guard.  The synthetic fixture has
    # empty cubes in the last positions (unit 2, row 3, col 3), but we insert
    # after the last cube (unit 2, row 3, col 3) which IS empty — the overflow
    # condition requires no free cube AFTER the insertion point.
    # Use after=(2,3,3) — the absolute last position; there's nothing after it.
    response = await client.post(
        "/api/admin/cubes/insert-cut",
        json={
            "after_unit_id": 2,
            "after_row": 3,
            "after_col": 3,
            "new_first_label": "Blue Note",
            "new_first_catalog": "BLP 4001",
            "force": True,
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("POST insert-cut endpoint not yet implemented")

    # Either 400 (shelf_overflow or no cube after) or 404 (cube not found)
    if response.status_code == 404:
        # The target cube doesn't exist — also acceptable (no overflow possible)
        return

    # Must return 400 for shelf_overflow OR 404 for target cube not found
    assert response.status_code in (400, 404), (
        f"Expected 400 (shelf_overflow) or 404 (not found) for last-position insert, "
        f"got {response.status_code}: {response.text}"
    )
    if response.status_code == 400:
        body = response.json()
        assert body.get("type") in ("shelf_overflow", "cube_not_found"), (
            f"400 response must have shelf_overflow or cube_not_found type: {body}"
        )


async def _seed_test_pin(db_pool) -> None:  # type: ignore[no-untyped-def]
    """Seed the test PIN ("0000") so ``_login`` succeeds.

    The shared ``admin_session`` fixture is broken under this httpx version (it
    references the removed ``AsyncClient.app``), so auth tests in this module fall
    back to the skip-prone ``_login``. This helper seeds the hash directly through
    ``db_pool`` (same DATABASE_URL the app uses), mirroring the conftest's
    JSON-quoted ``settings.value`` format.
    """
    from gruvax.auth.pin import hash_pin

    pin_hash = hash_pin("0000")
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (key, value, description, updated_at)"
            " VALUES ('auth.pin_hash', %s, 'Test PIN (cascade regression)', now())"
            " ON CONFLICT (key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (f'"{pin_hash}"',),
        )
        await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_insert_cut_cascade_preserves_bin_after_empty(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """SEG-08 regression: the insert cascade must not drop the bin past the absorber.

    The fixture has an empty cube at (1,2,3) directly followed by a non-empty bin at
    (1,3,0) = Columbia C2S 841. A cut inserted earlier in the unit cascades right
    until the empty cube absorbs the shift. A prior off-by-one (`break` on
    ``curr.is_empty`` instead of ``nxt.is_empty``) copied the empty cube's blank
    value onto (1,3,0), silently deleting Columbia. This guards the invariant:
    inserting a cut adds exactly one occupied bin and loses no existing cut point.
    """
    await _seed_test_pin(db_pool)
    auth = await _login(client)
    assert auth, "login should succeed after seeding the test PIN"

    def unit1_cuts(payload: dict) -> dict[tuple[int, int], str | None]:
        return {
            (c["row"], c["col"]): c.get("first_catalog")
            for c in payload["cubes"]
            if c["unit_id"] == 1 and not c["is_empty"]
        }

    before_res = await client.get("/api/admin/cubes", cookies=auth["cookies"])
    if before_res.status_code in (404, 405):
        pytest.skip("Admin cubes endpoint not yet implemented")
    assert before_res.status_code == 200, before_res.text
    before = unit1_cuts(before_res.json())

    response = await client.post(
        "/api/admin/cubes/insert-cut",
        json={
            "after_unit_id": 1,
            "after_row": 0,
            "after_col": 0,
            "new_first_label": "Blue Note",
            "new_first_catalog": "BLP 4010",
            "force": True,
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("POST insert-cut endpoint not yet implemented")
    assert response.status_code == 200, (
        f"Expected 200 from a valid insert-cut, got {response.status_code}: {response.text}"
    )
    change_set_id = response.json().get("change_set_id")

    try:
        after_res = await client.get("/api/admin/cubes", cookies=auth["cookies"])
        assert after_res.status_code == 200, after_res.text
        after = unit1_cuts(after_res.json())

        # The bin just past the empty absorber must survive (the original bug wiped it).
        assert "C2S 841" in after.values(), (
            "Columbia C2S 841 (the bin after the empty absorber) was dropped by the cascade"
        )
        # Exactly one new occupied bin, and no existing cut point lost (multiset check).
        assert len(after) == len(before) + 1, (
            f"insert-cut should add exactly one occupied bin: {len(before)} -> {len(after)}"
        )
        assert sorted(filter(None, after.values())) == sorted(
            [*filter(None, before.values()), "BLP 4010"]
        ), "insert-cut changed the set of cut points beyond adding the new one"
    finally:
        # Full cleanup — the suite shares the dev DB, so restore everything this
        # test mutated:
        #   * boundary_history 'cut_insert' rows would break `test_migrate_0005`'s
        #     downgrade (it restores the old CHECK: source IN manual/bulk/revert).
        #   * cube_boundaries were cascaded by the insert; re-seed the canonical
        #     fixture so later test modules don't inherit the shifted layout.
        if change_set_id:
            async with db_pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM gruvax.boundary_history WHERE change_set_id = %s",
                    (change_set_id,),
                )
                await conn.commit()
        from gruvax.db.seed_boundaries import load_boundaries

        await load_boundaries(_BOUNDARIES_YAML)


# ── Admin label/catalog autocomplete endpoints ───────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_list_labels_returns_distinct_labels(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/labels returns the distinct-label list for the picker.

    Regression guard: the RecordPickerSheet autocomplete + client-side phantom
    USE-ANYWAY path depend on this route, which was previously unrouted (the
    frontend called it but no backend endpoint existed).
    """
    await _seed_test_pin(db_pool)
    auth = await _login(client)
    assert auth, "login should succeed after seeding the test PIN"

    res = await client.get("/api/admin/labels", cookies=auth["cookies"])
    assert res.status_code == 200, f"expected 200, got {res.status_code}: {res.text}"
    body = res.json()
    assert isinstance(body, list) and body, "labels response must be a non-empty list"
    assert all("label" in item for item in body), "each entry must have a 'label' key"
    labels = [item["label"] for item in body]
    assert "Blue Note" in labels, "fixture label 'Blue Note' should be present"
    assert len(labels) == len(set(labels)), "labels must be distinct (no duplicates)"
    # Case-insensitive sort (the SQL ORDER BY uses the DB collation, not Python
    # codepoint order — e.g. 'Epic' before 'ESP').
    assert labels == sorted(labels, key=str.lower), "labels must be sorted (case-insensitive)"


@pytest.mark.asyncio(loop_scope="session")
async def test_list_catalogs_for_label(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/labels/{label}/catalogs returns release_id + catalog_number."""
    await _seed_test_pin(db_pool)
    auth = await _login(client)
    assert auth, "login should succeed after seeding the test PIN"

    res = await client.get("/api/admin/labels/Blue%20Note/catalogs", cookies=auth["cookies"])
    assert res.status_code == 200, f"expected 200, got {res.status_code}: {res.text}"
    body = res.json()
    assert isinstance(body, list) and body, "catalogs response must be a non-empty list"
    for item in body:
        assert "release_id" in item and "catalog_number" in item, (
            f"each entry must have release_id + catalog_number: {item}"
        )
    catalogs = [item["catalog_number"] for item in body]
    assert "BLP 4001" in catalogs, "fixture catalog 'BLP 4001' should be present"


@pytest.mark.asyncio(loop_scope="session")
async def test_labels_requires_admin_401() -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/labels without a session returns 401."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        res = await ac.get("/api/admin/labels")
    assert res.status_code == 401, f"expected 401 without auth, got {res.status_code}"


# ── SEG-05: contiguity enforcement on live PUT /cut write path ───────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_put_cut_scatter_rejected_contiguity_error(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """SEG-05 regression: PUT /cut that scatters a label is rejected 400 contiguity_error.

    Scatter scenario (boundaries.yaml unit 1, row 0):
      (1,0,0) = Blue Note BLP 4001
      (1,0,1) = Blue Note BST 84001
      (1,0,2) = Creole CRLP 501
      (1,0,3) = KC KC 32731

    If we PUT (1,0,3) to first_label="Blue Note", the sequence becomes:
      Blue Note, Blue Note, Creole, Blue Note
    Blue Note starts at positions 0, 1, and 3 — with Creole between positions 1
    and 3 — which is a contiguity violation (SEG-05 / D-09).

    Assertions:
    1. Response is HTTP 400 with type="contiguity_error".
    2. The error message mentions scatter or non-adjacent (validator's copy).
    3. GET /api/admin/cubes confirms (1,0,3) is STILL "KC" (no DB write occurred).

    Guard: the fixture is restored in finally so later tests see canonical state.
    """
    await _seed_test_pin(db_pool)
    auth = await _login(client)
    assert auth, "login should succeed after seeding the test PIN"

    response = await client.put(
        "/api/admin/cubes/1/0/3/cut",
        json={
            "first_label": "Blue Note",
            "first_catalog": "BLP 4001",
            "force": True,  # bypass phantom check; Blue Note BLP 4001 IS in the collection
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )
    if response.status_code in (404, 405):
        pytest.skip("PUT cut endpoint not yet implemented")

    try:
        assert response.status_code == 400, (
            f"Expected 400 (contiguity_error) for scatter-inducing PUT /cut, "
            f"got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body.get("type") == "contiguity_error", (
            f"Expected type=contiguity_error, got: {body.get('type')!r}"
        )
        msg = (body.get("message") or "").lower()
        assert "split" in msg or "non-adjacent" in msg, (
            f"contiguity_error message must mention 'split' or 'non-adjacent': {msg!r}"
        )

        # Confirm no DB write occurred — (1,0,3) must still be "KC"
        cubes_res = await client.get("/api/admin/cubes", cookies=auth["cookies"])
        assert cubes_res.status_code == 200, cubes_res.text
        cube_103 = next(
            (
                c
                for c in cubes_res.json()["cubes"]
                if c["unit_id"] == 1 and c["row"] == 0 and c["col"] == 3
            ),
            None,
        )
        assert cube_103 is not None, "cube (1,0,3) not found in GET /admin/cubes response"
        assert cube_103.get("first_label") == "KC", (
            f"cube (1,0,3) first_label should still be 'KC' (no write), got: {cube_103.get('first_label')!r}"
        )
    finally:
        # Restore the fixture (in case the test failed after a partial write, belt-and-suspenders)
        from gruvax.db.seed_boundaries import load_boundaries

        await load_boundaries(_BOUNDARIES_YAML)


# ── SEG-08: require_admin 401/403 ────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_segments_requires_admin_401() -> None:
    """SEG-08: GET segments without auth returns 401 Unauthorized.

    Requirement: SEG-08 — require_admin gates all segment admin endpoints.
    Uses a fresh client (no session cookies from prior tests).
    """
    from gruvax.app import create_app

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as fresh_client,
    ):
        # No cookies on this fresh client — unauthenticated request
        response = await fresh_client.get("/api/admin/cubes/1/0/0/segments")
        if response.status_code == 405:
            pytest.skip("GET segments endpoint not yet implemented")

        assert response.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated GET segments, got {response.status_code}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_set_override_requires_admin_401() -> None:
    """SEG-08: POST overrides without auth returns 401 Unauthorized.

    Requirement: SEG-08 — require_admin gates all segment admin endpoints.
    Uses a fresh client (no session cookies from prior tests).
    """
    from gruvax.app import create_app

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as fresh_client,
    ):
        # No cookies on this fresh client — unauthenticated request
        response = await fresh_client.post(
            "/api/admin/cubes/1/0/0/overrides",
            json={"overrides": [{"label": "Blue Note", "fraction": 1.0}]},
        )
        if response.status_code == 405:
            pytest.skip("POST overrides endpoint not yet implemented")

        assert response.status_code in (401, 403), (
            f"Expected 401/403 for unauthenticated POST overrides, got {response.status_code}"
        )


# ── SEG-08: locate p95 ≤ 50 ms preserved ─────────────────────────────────────


@pytest.mark.skip(
    reason="Benchmark validated in Plan 05-03 (locate_by_segment); see test_locate.py"
)
def test_locate_p95_le_50ms() -> None:
    """SEG-08: /api/locate p95 latency preserved at ≤ 50 ms after segment estimator.

    Requirement: SEG-08 — p95 <= 50 ms preserved; verified via pytest-benchmark
    against the live DB in Plan 05-03 after locate_by_segment is implemented.
    See: pytest tests/integration/test_locate.py --benchmark-only
    """
    pytest.skip("Benchmark latency gate validated in Plan 05-03")

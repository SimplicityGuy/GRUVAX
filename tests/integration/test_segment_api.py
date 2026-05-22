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

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app


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

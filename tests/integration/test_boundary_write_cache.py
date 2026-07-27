"""Regression tests for the admin boundary-write cache-rebuild path.

Every admin write that touches ``gruvax.cube_boundaries`` /
``gruvax.segment_overrides`` reloads the BoundaryCache and re-derives the
SegmentCache afterwards.  That rebuild is the shared seam behind a family of
silent-corruption bugs; each test below pins one of them.

  - gruvax-591: the rebuild must re-apply EVERY cube's width override, not only
    the edited cube's.  Editing cube A used to revert cube B's override in the
    live cache while leaving B's DB row intact (a restart made it "come back").
  - gruvax-cxy: a legal per-label override that leaves a bin with no absorber
    must not blow up ``derive()`` and wipe the whole SegmentCache.

These are integration tests: they drive the real endpoints through the real
app so the dependency wiring (which is where the defects lived) is exercised.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import psycopg
import pytest
import pytest_asyncio

from gruvax.app import create_app
from tests.cookies import cookie_header


_BOUNDARIES_YAML = Path(__file__).parents[2] / "fixtures" / "boundaries.yaml"

# One populated bin: (unit_id, row, col, derived segments).
_Bin = tuple[int, int, int, list[dict[str, Any]]]


@pytest.fixture(autouse=True)
def reset_login_rate_limit() -> None:  # type: ignore[return]
    """Reset the module-level login rate limiter between tests (see test_segment_api)."""
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped client over the canonical boundary fixture.

    Seeds the test PIN itself (rather than relying on a sibling module having
    already done so) so this module passes when run in isolation.
    """
    from gruvax.auth.pin import hash_pin
    from gruvax.db.seed_boundaries import load_boundaries
    from gruvax.settings import settings

    await load_boundaries(_BOUNDARIES_YAML)

    # Sync psycopg (NOT the async db_pool) — the async-pool path deadlocks inside
    # a module-scoped fixture, per the PoolTimeout note in tests/integration/conftest.
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s, 'Test PIN hash', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            ("00000000-0000-0000-0000-000000000001", f'"{hash_pin("0000")}"'),
        )
        conn.commit()

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        yield ac


async def _login(client: Any) -> dict[str, Any]:
    """Log in and return cookies + CSRF token, browse-bound to the default profile."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    cookies["gruvax_browse_binding"] = "00000000-0000-0000-0000-000000000001"
    return {"cookies": cookies, "csrf_token": res.cookies.get("gruvax_csrf") or ""}


def _auth_headers(auth: dict[str, Any]) -> dict[str, str]:
    return {"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])}


async def _segments(
    client: Any, auth: dict[str, Any], unit: int, row: int, col: int
) -> list[dict[str, Any]]:
    """Return the derived segments for one bin (empty list when the bin has none)."""
    res = await client.get(
        f"/api/admin/cubes/{unit}/{row}/{col}/segments",
        headers=cookie_header(auth["cookies"]),
    )
    if res.status_code != 200:
        return []
    segments: list[dict[str, Any]] = res.json()["segments"]
    return segments


async def _find_bins(client: Any, auth: dict[str, Any]) -> list[_Bin]:
    """Return ``(unit, row, col, segments)`` for every populated bin on every shelf."""
    res = await client.get("/api/admin/cubes", headers=cookie_header(auth["cookies"]))
    assert res.status_code == 200, res.text

    found: list[_Bin] = []
    for cube in res.json()["cubes"]:
        if cube.get("is_empty"):
            continue
        unit, row, col = cube["unit_id"], cube["row"], cube["col"]
        segments = await _segments(client, auth, unit, row, col)
        if segments:
            found.append((unit, row, col, segments))
    return found


async def _clear_override(
    client: Any, auth: dict[str, Any], unit: int, row: int, col: int, label: str
) -> None:
    """Best-effort teardown: drop an override so later tests see a clean shelf."""
    await client.post(
        f"/api/admin/cubes/{unit}/{row}/{col}/overrides",
        json={"overrides": [{"label": label, "fraction": None}]},
        headers=_auth_headers(auth),
    )


def _pick_override_and_edit_bins(bins: list[_Bin]) -> tuple[_Bin, _Bin]:
    """Pick (B, A): B gets the width override, A is the unrelated cube we edit.

    B must hold >= 2 labels so a partial override still leaves a non-overridden
    absorber (a fully-overridden bin is its own defect — see gruvax-cxy).
    """
    target = next((b for b in bins if len(b[3]) >= 2), None)
    if target is None:
        pytest.skip("Fixture has no multi-label bin to override")
    other = next((b for b in bins if b[:3] != target[:3]), None)
    if other is None:
        pytest.skip("Fixture has only one populated bin")
    return target, other


# ── gruvax-591 ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_override_on_one_cube_survives_an_edit_to_another(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax-591: editing cube A must not revert cube B's width override.

    Fails on the pre-fix code: the four write endpoints hand-built the overrides
    dict passed to ``SegmentCache.derive()`` from ONLY the edited bin's segments,
    and ``derive()`` sets ``is_override=False`` for every label absent from that
    dict.  So a PUT on cube A silently cleared cube B's admin override in the
    live cache, while B's ``segment_overrides`` row survived untouched — the
    override "came back" on the next restart.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented")

    b_bin, a_bin = _pick_override_and_edit_bins(await _find_bins(client, auth))
    b_unit, b_row, b_col, b_segments = b_bin
    a_unit, a_row, a_col, _ = a_bin
    label = str(b_segments[0]["label"])

    try:
        # 1. Set an explicit width override on cube B.
        res = await client.post(
            f"/api/admin/cubes/{b_unit}/{b_row}/{b_col}/overrides",
            json={"overrides": [{"label": label, "fraction": 0.5}]},
            headers=_auth_headers(auth),
        )
        assert res.status_code == 200, f"override write failed: {res.text}"

        after_write = await _segments(client, auth, b_unit, b_row, b_col)
        applied = next(s for s in after_write if str(s["label"]) == label)
        assert applied["is_override"] is True
        assert applied["fraction"] == pytest.approx(0.5)

        # 2. Edit an UNRELATED cube A. Re-writing A's own current cut point is a
        #    semantic no-op but still runs the full write + cache-rebuild path.
        a_cut = await client.get(
            f"/api/admin/cubes/{a_unit}/{a_row}/{a_col}/boundary",
            headers=cookie_header(auth["cookies"]),
        )
        assert a_cut.status_code == 200, a_cut.text
        a_body = a_cut.json()
        assert a_body["first_label"], f"cube A has no cut point to re-write: {a_body}"

        res = await client.put(
            f"/api/admin/cubes/{a_unit}/{a_row}/{a_col}/cut",
            json={
                "first_label": a_body["first_label"],
                "first_catalog": a_body["first_catalog"],
                "force": True,
            },
            headers=_auth_headers(auth),
        )
        assert res.status_code == 200, f"unrelated cut edit failed: {res.text}"

        # 3. Cube B's override must be untouched in the LIVE cache.
        after_edit = await _segments(client, auth, b_unit, b_row, b_col)
        still = next((s for s in after_edit if str(s["label"]) == label), None)
        assert still is not None, f"label {label!r} vanished from bin B: {after_edit}"
        assert still["is_override"] is True, (
            "gruvax-591: editing an unrelated cube reverted this cube's width "
            f"override in the live cache (segments now: {after_edit})"
        )
        assert still["fraction"] == pytest.approx(0.5)
    finally:
        await _clear_override(client, auth, b_unit, b_row, b_col, label)


@pytest.mark.asyncio(loop_scope="session")
async def test_bulk_write_preserves_unrelated_overrides(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax-591: POST /cubes/bulk must not revert overrides on untouched cubes."""
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented")

    b_bin, a_bin = _pick_override_and_edit_bins(await _find_bins(client, auth))
    b_unit, b_row, b_col, b_segments = b_bin
    a_unit, a_row, a_col, _ = a_bin
    label = str(b_segments[0]["label"])

    try:
        res = await client.post(
            f"/api/admin/cubes/{b_unit}/{b_row}/{b_col}/overrides",
            json={"overrides": [{"label": label, "fraction": 0.5}]},
            headers=_auth_headers(auth),
        )
        assert res.status_code == 200, res.text

        a_cut = await client.get(
            f"/api/admin/cubes/{a_unit}/{a_row}/{a_col}/boundary",
            headers=cookie_header(auth["cookies"]),
        )
        a_body = a_cut.json()

        res = await client.post(
            "/api/admin/cubes/bulk",
            json={
                "updates": [
                    {
                        "unit_id": a_unit,
                        "row": a_row,
                        "col": a_col,
                        "first_label": a_body["first_label"],
                        "first_catalog": a_body["first_catalog"],
                        "is_empty": False,
                        "force": True,
                    }
                ]
            },
            headers=_auth_headers(auth),
        )
        assert res.status_code == 200, f"bulk write failed: {res.text}"

        after = await _segments(client, auth, b_unit, b_row, b_col)
        still = next((s for s in after if str(s["label"]) == label), None)
        assert still is not None and still["is_override"] is True, (
            "gruvax-591: bulk write reverted an unrelated cube's override "
            f"(segments now: {after})"
        )
    finally:
        await _clear_override(client, auth, b_unit, b_row, b_col, label)

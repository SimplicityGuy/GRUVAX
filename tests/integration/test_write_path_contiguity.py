"""gruvax-216: the commit paths must enforce contiguity, not just the preview.

``validate_contiguity`` guarded every write path except the two that the primary
admin UI actually uses: ``POST /admin/cubes/bulk`` (the wizard's COMMIT) and
``PUT /admin/cubes/{u}/{r}/{c}/boundary``. The advisory ``POST
/admin/cubes/validate`` DID check it, so the identical payload was rejected by
the preview and accepted by the commit.

The client-side gate is soft by construction: ``Wizard.tsx`` disables COMMIT
only while ``validateErrors`` is non-empty, that state initialises to ``[]``,
and only the optional VALIDATE button ever fills it. Skip VALIDATE — or
validate, go BACK TO WALK, edit, and commit against now-stale empty errors — and
a scattered label persisted with no enforcement anywhere.

Each test therefore asserts three things: the commit is refused, the DB is
untouched, and the preview agrees with the commit.
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
_DEFAULT_PROFILE = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def reset_login_rate_limit() -> None:  # type: ignore[return]
    """Reset the module-level login rate limiter between tests."""
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped client over a freshly re-seeded canonical boundary fixture."""
    from gruvax.auth.pin import hash_pin
    from gruvax.db.seed_boundaries import load_boundaries
    from gruvax.settings import settings

    await load_boundaries(_BOUNDARIES_YAML)

    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
            " VALUES (%s::uuid, 'auth.pin_hash', %s, 'Test PIN hash', now())"
            " ON CONFLICT (profile_id, key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (_DEFAULT_PROFILE, f'"{hash_pin("0000")}"'),
        )
        conn.commit()

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        yield ac


async def _login(client: Any) -> dict[str, Any]:
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    cookies["gruvax_browse_binding"] = _DEFAULT_PROFILE
    return {"cookies": cookies, "csrf_token": res.cookies.get("gruvax_csrf") or ""}


def _headers(auth: dict[str, Any]) -> dict[str, str]:
    return {"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])}


async def _boundary(client: Any, auth: dict[str, Any], unit: int, row: int, col: int) -> dict:
    res = await client.get(
        f"/api/admin/cubes/{unit}/{row}/{col}/boundary",
        headers=cookie_header(auth["cookies"]),
    )
    assert res.status_code == 200, res.text
    return res.json()  # type: ignore[no-any-return]


async def _scatter_payload(client: Any, auth: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Build a 3-cube payload that scatters one label across non-adjacent bins.

    Takes the first three populated cubes of a unit and re-labels the MIDDLE one
    with a label that starts a later bin, so the first cube's label ends up with
    a gap in its run.
    """
    res = await client.get("/api/admin/cubes", headers=cookie_header(auth["cookies"]))
    assert res.status_code == 200, res.text
    cubes = [c for c in res.json()["cubes"] if not c["is_empty"]]

    by_unit: dict[int, list[dict[str, Any]]] = {}
    for c in sorted(cubes, key=lambda c: (c["unit_id"], c["row"], c["col"])):
        by_unit.setdefault(c["unit_id"], []).append(c)

    for run in by_unit.values():
        if len(run) < 3:
            continue
        a, b, c3 = run[0], run[1], run[2]
        # A label from a LATER bin in the same unit, distinct from A's label.
        intruder = next(
            (x for x in run[3:] if x["first_label"] != a["first_label"]),
            None,
        )
        if intruder is None or a["first_label"] != b["first_label"]:
            continue
        # a and b share a label; putting the intruder's label in the middle and
        # keeping a's label at c3 splits a's run across non-adjacent bins.
        return [
            {
                "unit_id": a["unit_id"],
                "row": a["row"],
                "col": a["col"],
                "first_label": a["first_label"],
                "first_catalog": a["first_catalog"],
                "is_empty": False,
                "force": True,
            },
            {
                "unit_id": b["unit_id"],
                "row": b["row"],
                "col": b["col"],
                "first_label": intruder["first_label"],
                "first_catalog": intruder["first_catalog"],
                "is_empty": False,
                "force": True,
            },
            {
                "unit_id": c3["unit_id"],
                "row": c3["row"],
                "col": c3["col"],
                "first_label": a["first_label"],
                "first_catalog": a["first_catalog"],
                "is_empty": False,
                "force": True,
            },
        ]
    return None


@pytest.mark.asyncio(loop_scope="session")
async def test_bulk_commit_rejects_scattered_labels(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax-216: POST /cubes/bulk must refuse a payload that scatters a label.

    This is the wizard's COMMIT path. Pre-fix it ran the phantom loop and went
    straight into the transaction — 200, scattered label persisted.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented")

    updates = await _scatter_payload(client, auth)
    if updates is None:
        pytest.skip("Fixture shelf has no 3+ cube unit with a repeated leading label")

    middle = updates[1]
    before = await _boundary(client, auth, middle["unit_id"], middle["row"], middle["col"])

    res = await client.post(
        "/api/admin/cubes/bulk",
        json={"updates": updates, "source": "wizard"},
        headers=_headers(auth),
    )
    assert res.status_code == 400, (
        "gruvax-216: a scattered-label bulk commit must be refused server-side; "
        f"got {res.status_code}: {res.text}"
    )
    assert res.json().get("type") == "contiguity_violation", res.text

    # ZERO partial state — the rejection happens before the transaction.
    after = await _boundary(client, auth, middle["unit_id"], middle["row"], middle["col"])
    assert after == before, f"a rejected bulk commit still wrote to the DB: {before} -> {after}"

    # Preview and commit now agree — that asymmetry was the reported symptom.
    preview = await client.post(
        "/api/admin/cubes/validate",
        json={"updates": [{k: v for k, v in u.items()} for u in updates]},
        headers=_headers(auth),
    )
    assert preview.status_code == 400, (
        "preview must reject exactly what commit rejects; "
        f"got {preview.status_code}: {preview.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_put_boundary_rejects_scattering_cut(client) -> None:  # type: ignore[no-untyped-def]
    """gruvax-216: PUT /{u}/{r}/{c}/boundary must refuse a scattering cut too.

    The per-cube editor had the same phantom-only gate as bulk.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented")

    updates = await _scatter_payload(client, auth)
    if updates is None:
        pytest.skip("Fixture shelf has no 3+ cube unit with a repeated leading label")

    middle = updates[1]
    before = await _boundary(client, auth, middle["unit_id"], middle["row"], middle["col"])

    res = await client.put(
        f"/api/admin/cubes/{middle['unit_id']}/{middle['row']}/{middle['col']}/boundary",
        json={
            "first_label": middle["first_label"],
            "first_catalog": middle["first_catalog"],
            "is_empty": False,
            "force": True,
        },
        headers=_headers(auth),
    )
    assert res.status_code == 400, (
        "gruvax-216: a scattering per-cube boundary write must be refused; "
        f"got {res.status_code}: {res.text}"
    )
    assert res.json().get("type") == "contiguity_violation", res.text

    after = await _boundary(client, auth, middle["unit_id"], middle["row"], middle["col"])
    assert after == before, f"a rejected boundary write still hit the DB: {before} -> {after}"


@pytest.mark.asyncio(loop_scope="session")
async def test_contiguous_bulk_commit_still_succeeds(client) -> None:  # type: ignore[no-untyped-def]
    """The new gate must not reject legal commits (no false positives).

    Re-committing a cube's own current cut point is a semantic no-op and has to
    keep working — otherwise the gate would have broken the wizard outright.
    """
    auth = await _login(client)
    if not auth:
        pytest.skip("Login not implemented")

    res = await client.get("/api/admin/cubes", headers=cookie_header(auth["cookies"]))
    cubes = [c for c in res.json()["cubes"] if not c["is_empty"]]
    if not cubes:
        pytest.skip("Fixture has no populated cubes")
    target = cubes[0]

    res = await client.post(
        "/api/admin/cubes/bulk",
        json={
            "updates": [
                {
                    "unit_id": target["unit_id"],
                    "row": target["row"],
                    "col": target["col"],
                    "first_label": target["first_label"],
                    "first_catalog": target["first_catalog"],
                    "is_empty": False,
                    "force": True,
                }
            ],
            "source": "wizard",
        },
        headers=_headers(auth),
    )
    assert res.status_code == 200, f"a contiguous commit must still succeed: {res.text}"

"""gruvax-xkc: an admin boundary write must refresh ITS OWN profile's caches.

``tests/integration/test_two_profile_isolation.py`` already proves the DB *rows*
are scoped correctly.  The defect this module pins is one layer up: every admin
write scoped its SQL to the resolved profile_id but then reloaded a cache taken
from ``Depends(get_boundary_cache)``, which reads ``app.state.boundary_cache`` —
an alias bound ONCE at startup to the DEFAULT profile's registry entry and never
re-pointed.  So a write bound to profile B committed B's row and then reloaded
profile A's cache: B's kiosk kept serving pre-edit boundaries from ``/api/locate``
until the next restart or nightly sync.

The assertions run against the registries directly, because that is exactly the
layer the bug lived in and the layer the HTTP surface cannot see.
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

# Profile B's own shelf: one cube whose cut point is a value that appears in NO
# other profile, so "which profile's rows are in this cache" is unambiguous.
_B_UNIT, _B_ROW, _B_COL = 1, 0, 0
_B_LABEL = "B-Only Label"
_B_CATALOG = "BONLY-001"
_B_NEW_CATALOG = "BONLY-002"


def _dsn() -> str:
    from gruvax.settings import settings

    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture(autouse=True)
def reset_login_rate_limit() -> None:  # type: ignore[return]
    """Reset the module-level login rate limiter between tests."""
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


@pytest.fixture(scope="module")
def profile_b() -> Any:
    """Create profile B with its own single-cube shelf; soft-delete it on teardown.

    Seeded synchronously so the row exists BEFORE ``create_app()`` runs its
    startup loop — otherwise B never gets a registry entry at all.
    """
    dsn = _dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.profiles (display_name, app_token_encrypted, app_token_revoked)"
            " VALUES ('CacheScopingB', %s::bytea, TRUE) RETURNING id::text",
            (b"",),
        )
        row = cur.fetchone()
        assert row is not None
        b_uuid: str = row[0]
        cur.execute(
            "INSERT INTO gruvax.cube_boundaries"
            " (profile_id, unit_id, row, col, first_label, first_catalog, is_empty)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, FALSE)"
            " ON CONFLICT (profile_id, unit_id, row, col) DO UPDATE"
            "   SET first_label = EXCLUDED.first_label,"
            "       first_catalog = EXCLUDED.first_catalog",
            (b_uuid, _B_UNIT, _B_ROW, _B_COL, _B_LABEL, _B_CATALOG),
        )
        conn.commit()

    yield b_uuid

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid", (b_uuid,))
        cur.execute("UPDATE gruvax.profiles SET deleted_at = now() WHERE id = %s::uuid", (b_uuid,))
        conn.commit()


@pytest_asyncio.fixture(scope="module")
async def app_and_client(db_pool, profile_b):  # type: ignore[no-untyped-def]
    """Yield ``(app, client)`` — the app object is needed to inspect the registries."""
    from gruvax.auth.pin import hash_pin
    from gruvax.db.seed_boundaries import load_boundaries

    await load_boundaries(_BOUNDARIES_YAML)

    with psycopg.connect(_dsn()) as conn, conn.cursor() as cur:
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
        yield app, ac


async def _login_bound_to(client: Any, profile_id: str) -> dict[str, Any]:
    """Log in as admin and bind the browse session to ``profile_id``."""
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    cookies = dict(res.cookies)
    cookies["gruvax_browse_binding"] = profile_id
    return {"cookies": cookies, "csrf_token": res.cookies.get("gruvax_csrf") or ""}


def _cut_of(app: Any, profile_id: str, unit: int, row: int, col: int) -> tuple[Any, Any] | None:
    """Read (first_label, first_catalog) for one cube straight out of the registry cache."""
    cache = app.state.boundary_cache_registry[profile_id]
    for b in cache.get_boundaries():
        if (b.unit_id, b.row, b.col) == (unit, row, col):
            return b.first_label, b.first_catalog
    return None


@pytest.mark.asyncio(loop_scope="session")
async def test_write_bound_to_b_refreshes_bs_cache(app_and_client, profile_b) -> None:  # type: ignore[no-untyped-def]
    """gruvax-xkc: a write bound to profile B must reload B's BoundaryCache.

    Pre-fix, all seven admin write sites called a bare ``cache.load(pool)`` on the
    DEFAULT profile's cache object, so B's registry entry was never refreshed and
    B's kiosk served pre-edit boundaries from /api/locate until a restart.
    """
    app, client = app_and_client
    auth = await _login_bound_to(client, profile_b)
    if not auth:
        pytest.skip("Login not implemented")

    assert _cut_of(app, profile_b, _B_UNIT, _B_ROW, _B_COL) == (_B_LABEL, _B_CATALOG), (
        "precondition: profile B's cache starts at its seeded cut point"
    )

    res = await client.put(
        f"/api/admin/cubes/{_B_UNIT}/{_B_ROW}/{_B_COL}/cut",
        json={"first_label": _B_LABEL, "first_catalog": _B_NEW_CATALOG, "force": True},
        headers={"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])},
    )
    assert res.status_code == 200, f"write bound to profile B failed: {res.text}"

    assert _cut_of(app, profile_b, _B_UNIT, _B_ROW, _B_COL) == (_B_LABEL, _B_NEW_CATALOG), (
        "gruvax-xkc: the write committed to profile B's row but B's own "
        "BoundaryCache was never reloaded — B's kiosk keeps serving stale "
        "boundaries until restart"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_write_bound_to_b_never_pollutes_the_default_cache(app_and_client, profile_b) -> None:  # type: ignore[no-untyped-def]
    """gruvax-xkc (fix-ordering hazard): B's rows must never land in A's cache.

    The naive half-fix — threading profile_id into ``load()`` while still using the
    injected default-profile cache object — would have turned benign staleness into
    cross-profile CORRUPTION: ``load(pool, profile_id=B)`` on the alias overwrites
    the live cache the default kiosk serves. This test fails on that half-fix.

    Profile B's shelf is a single cube; the default profile's is 32. So if A's
    cache ever gets loaded with B's rows the boundary count collapses, and the cut
    point at the shared coordinate becomes B's sentinel label.
    """
    app, client = app_and_client

    default_cache = app.state.boundary_cache_registry[_DEFAULT_PROFILE]
    before_count = len(list(default_cache.get_boundaries()))
    before_cut = _cut_of(app, _DEFAULT_PROFILE, _B_UNIT, _B_ROW, _B_COL)
    assert before_cut is not None and before_cut[0] != _B_LABEL, (
        "precondition: the default profile's shelf is not profile B's"
    )

    auth = await _login_bound_to(client, profile_b)
    if not auth:
        pytest.skip("Login not implemented")

    res = await client.put(
        f"/api/admin/cubes/{_B_UNIT}/{_B_ROW}/{_B_COL}/cut",
        json={"first_label": _B_LABEL, "first_catalog": _B_CATALOG, "force": True},
        headers={"X-CSRF-Token": auth["csrf_token"], **cookie_header(auth["cookies"])},
    )
    assert res.status_code == 200, f"write bound to profile B failed: {res.text}"

    assert len(list(default_cache.get_boundaries())) == before_count, (
        "gruvax-xkc: a write bound to profile B replaced the DEFAULT profile's "
        "live BoundaryCache — the kiosk is now serving another profile's shelf"
    )
    assert _cut_of(app, _DEFAULT_PROFILE, _B_UNIT, _B_ROW, _B_COL) == before_cut, (
        "gruvax-xkc: profile B's cut point leaked into the default profile's cache"
    )

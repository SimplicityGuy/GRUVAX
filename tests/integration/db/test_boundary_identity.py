"""Validation and diagnostics agree with the estimator's Unicode label identity."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from gruvax.db.queries import cube_exact_match, get_phantom_boundary_count
from gruvax.estimator.algorithm import locate_by_segment
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from tests.cookies import cookie_header


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def client(db_pool: Any, profile: str):  # type: ignore[no-untyped-def]
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        yield ac


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def profile(db_pool: Any):  # type: ignore[no-untyped-def]
    """Own every synthetic row; teardown never touches the default collection."""
    profile_id = str(uuid4())
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked)"
            " VALUES (%s::uuid, %s, %s, TRUE)",
            (profile_id, f"Boundary identity {profile_id}", b""),
        )
        await conn.commit()
    try:
        yield profile_id
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (profile_id,))
            await conn.commit()


async def clear_profile(db_pool: Any, profile: str) -> None:
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid", (profile,)
        )
        await conn.execute(
            "DELETE FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid", (profile,)
        )
        await conn.commit()


async def seed_pair(db_pool: Any, profile: str, label: str | None, catalog: str | None) -> None:
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profile_collection"
            " (profile_id, release_id, folder_id, label, catalog_number)"
            " VALUES (%s::uuid, 910001, 1, %s, %s)",
            (profile, label, catalog),
        )
        await conn.commit()


async def seed_boundary(db_pool: Any, profile: str, label: str, catalog: str) -> None:
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.cube_boundaries"
            " (profile_id, unit_id, row, col, first_label, first_catalog, is_empty)"
            " VALUES (%s::uuid, 1, 0, 0, %s, %s, FALSE)",
            (profile, label, catalog),
        )
        await conn.commit()


async def assert_estimator_resolves(db_pool: Any, profile: str, label: str, catalog: str) -> None:
    snapshot, boundaries, segments = CollectionSnapshot(), BoundaryCache(), SegmentCache()
    await snapshot.load(db_pool, profile)
    await boundaries.load(db_pool, profile)
    segments.derive(boundaries, snapshot, boundaries.overrides)
    result = locate_by_segment(
        release_id=910001,
        label=label,
        catalog_number=catalog,
        segment_cache=segments,
        snapshot=snapshot,
    )
    assert result.confidence > 0
    assert result.primary_cube is not None
    assert (result.primary_cube.unit_id, result.primary_cube.row, result.primary_cube.col) == (
        1,
        0,
        0,
    )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("stored", "proposed", "matches"),
    [
        ("Straße Records", "STRASSE RECORDS", True),
        ("Final ς", "FINAL Σ", True),
        ("ﬁ Records", "FI RECORDS", True),
        ("İtri Müzik", "İTRİ MÜZİK", False),
        ("İtri", "itri", False),
        ("Blue Note", "BLUE NOTE", True),
        ("A-B Records", "AB Records", False),
        ("Record Company", "RecordCompany", False),
    ],
)
async def test_unicode_label_identity_agrees_at_db_http_and_estimator(
    db_pool: Any,
    profile: str,
    client: AsyncClient,
    admin_session: dict[str, Any],
    stored: str,
    proposed: str,
    matches: bool,
) -> None:
    await clear_profile(db_pool, profile)
    await seed_pair(db_pool, profile, stored, "CAT 1")
    await seed_boundary(db_pool, profile, proposed, "CAT 1")
    assert await cube_exact_match(db_pool, proposed, "CAT 1", profile) is matches
    assert await get_phantom_boundary_count(db_pool, profile) == (0 if matches else 1)
    cookies = dict(admin_session["cookies"])
    cookies["gruvax_browse_binding"] = profile
    response = await client.post(
        "/api/admin/cubes/validate",
        headers={"X-CSRF-Token": admin_session["csrf_token"], **cookie_header(cookies)},
        json={
            "updates": [
                {
                    "unit_id": 1,
                    "row": 0,
                    "col": 0,
                    "first_label": proposed,
                    "first_catalog": "CAT 1",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is matches
    assert response.json()["results"][0]["valid"] is matches
    if matches:
        await assert_estimator_resolves(db_pool, profile, stored, "CAT 1")


@pytest.mark.asyncio(loop_scope="session")
async def test_identity_stays_profile_scoped(db_pool: Any, profile: str) -> None:
    await clear_profile(db_pool, profile)
    await seed_boundary(db_pool, profile, "Blue Note", "BLP 1000")
    # This pair exists in the default profile, but must not authorize this one.
    assert await cube_exact_match(db_pool, "Blue Note", "BLP 1000", profile) is False
    assert await get_phantom_boundary_count(db_pool, profile) == 1


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    ("stored", "proposed", "matches"),
    [
        ("BLP 4195", "blp-4195", True),
        ("\uff22\uff2c\uff30 \uff14\uff11\uff19\uff15", "BLP/4195", True),
        ("CAT 001", "cat1", True),
        ("CAT 1, EXTRA 2", "CAT.1", True),
        (None, "None", True),
        ("N/A", "?", True),
        ("Straße 1", "STRASSE 1", True),
        ("CAT 9999999999999", "CAT 10000000000000", True),
        ("CAT 10", "CAT 1", False),
        ("CAT 1", "OTHER 1", False),
    ],
)
async def test_catalog_identity_agrees_at_db_http_save_and_estimator(
    db_pool: Any,
    profile: str,
    client: AsyncClient,
    admin_session: dict[str, Any],
    stored: str | None,
    proposed: str,
    matches: bool,
) -> None:
    await clear_profile(db_pool, profile)
    await seed_pair(db_pool, profile, "Straße Records", stored)
    await seed_boundary(db_pool, profile, "STRASSE RECORDS", proposed)
    assert await cube_exact_match(db_pool, "STRASSE RECORDS", proposed, profile) is matches
    assert await get_phantom_boundary_count(db_pool, profile) == (0 if matches else 1)
    cookies = dict(admin_session["cookies"])
    cookies["gruvax_browse_binding"] = profile
    headers = {"X-CSRF-Token": admin_session["csrf_token"], **cookie_header(cookies)}
    edit = {
        "unit_id": 1,
        "row": 0,
        "col": 0,
        "first_label": "STRASSE RECORDS",
        "first_catalog": proposed,
    }
    response = await client.post(
        "/api/admin/cubes/validate", headers=headers, json={"updates": [edit]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is matches
    assert response.json()["results"][0]["valid"] is matches
    if matches:
        saved = await client.put(
            "/api/admin/cubes/1/0/0/boundary",
            headers=headers,
            json={"first_label": "STRASSE RECORDS", "first_catalog": proposed},
        )
        assert saved.status_code == 200, saved.text
        # Equality must not rewrite stored spelling: import G3's raw contract survives.
        assert saved.json()["first_catalog"] == proposed
        await assert_estimator_resolves(db_pool, profile, "Straße Records", stored or "")

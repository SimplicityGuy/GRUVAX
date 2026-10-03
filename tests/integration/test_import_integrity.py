"""Import rejection and replacement contracts against owned synthetic profiles."""

import copy
import uuid

from httpx import ASGITransport, AsyncClient
from psycopg import sql
import pytest
import pytest_asyncio
import yaml

from gruvax.app import create_app
from gruvax.auth.pin import hash_pin
from gruvax.db.queries import DEFAULT_PROFILE_UUID
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus
from tests.cookies import cookie_header


@pytest_asyncio.fixture(loop_scope="session")
async def import_api(db_pool):  # type: ignore[no-untyped-def]
    profiles = [str(uuid.uuid4()), str(uuid.uuid4())]
    app = create_app()
    app.state.db_pool = db_pool
    registries = [
        "boundary_cache_registry",
        "snapshot_registry",
        "segment_cache_registry",
        "event_bus_registry",
    ]
    for name in registries:
        setattr(app.state, name, {})
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (profile_id, key, value) VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb) ON CONFLICT (profile_id, key) DO UPDATE SET value = EXCLUDED.value",
            (DEFAULT_PROFILE_UUID, '"' + hash_pin("0000") + '"'),
        )
        for profile in profiles:
            await conn.execute(
                "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked) VALUES (%s::uuid, %s, %s, TRUE)",
                (profile, f"Import profile {profile}", b""),
            )
            for release, label, catalog in [
                (1, "Alpha", "A1"),
                (2, "Alpha", "A2"),
                (3, "Zulu", "Z1"),
                (4, "Zulu", "Z2"),
            ]:
                await conn.execute(
                    "INSERT INTO gruvax.profile_collection (profile_id, release_id, folder_id, artist, title, label, catalog_number, year) VALUES (%s::uuid, %s, 1, 'Synthetic artist', 'Synthetic title', %s, %s, 2000)",
                    (profile, release, label, catalog),
                )
            for col, label, catalog in [(0, "Alpha", "A1"), (1, "Zulu", "Z2")]:
                await conn.execute(
                    "INSERT INTO gruvax.cube_boundaries (profile_id, unit_id, row, col, first_label, first_catalog, is_empty) VALUES (%s::uuid, 1, 0, %s, %s, %s, FALSE)",
                    (profile, col, label, catalog),
                )
            await conn.execute(
                "INSERT INTO gruvax.segment_overrides (profile_id, unit_id, row, col, label, label_display, fraction) VALUES (%s::uuid, 1, 0, 0, 'alpha', 'Alpha', 0.25)",
                (profile,),
            )
        await conn.commit()
    queues = []
    for profile in profiles:
        boundary, snapshot, segment, bus = (
            BoundaryCache(),
            CollectionSnapshot(),
            SegmentCache(),
            EventBus(),
        )
        await boundary.load(db_pool, profile_id=profile)
        await snapshot.load(db_pool, profile_id=profile)
        segment.derive(boundary, snapshot, boundary.overrides)
        for name, value in zip(registries, [boundary, snapshot, segment, bus], strict=True):
            getattr(app.state, name)[profile] = value
        queues.append(bus.subscribe())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post("/api/admin/login", json={"pin": "0000"})
            assert login.status_code == 200, login.text
            headers = {
                "X-CSRF-Token": login.cookies["gruvax_csrf"],
                **cookie_header(login.cookies, {"gruvax_browse_binding": profiles[0]}),
            }
            yield client, headers, app, profiles, queues
    finally:
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.profiles WHERE id = ANY(%s::uuid[])", (profiles,)
            )
            await conn.commit()


async def import_state(db_pool, app, profiles):  # type: ignore[no-untyped-def]
    state = []
    async with db_pool.connection() as conn:
        for table in ["cube_boundaries", "segment_overrides", "boundary_history"]:
            state.append(
                await (
                    await conn.execute(
                        sql.SQL(
                            "SELECT * FROM gruvax.{} WHERE profile_id = ANY(%s::uuid[]) ORDER BY profile_id, unit_id, row, col"
                        ).format(sql.Identifier(table)),
                        (profiles,),
                    )
                ).fetchall()
            )
    caches = [
        (
            copy.deepcopy(app.state.boundary_cache_registry[p].get_boundaries()),
            copy.deepcopy(app.state.boundary_cache_registry[p].overrides),
            copy.deepcopy(app.state.segment_cache_registry[p]._bins),
        )
        for p in profiles
    ]
    return state, caches


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "cubes",
    [
        None,
        "nope",
        [42],
        [[1, 2]],
        [{"row": 0, "col": 0}],
        [{"unit_id": 1, "row": 0, "col": 0, "overrides": 5}],
    ],
)
async def test_malformed_yaml_rejected_without_any_import_mutation(import_api, db_pool, cubes):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    before = await import_state(db_pool, app, profiles)
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml.safe_dump({"version": "1", "cubes": cubes}),
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "parse_error"
    assert "cubes" in response.json()["detail"]["message"]
    assert await import_state(db_pool, app, profiles) == before
    assert all(queue.empty() for queue in queues)

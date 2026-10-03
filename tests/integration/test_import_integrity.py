"""Import rejection and replacement contracts against owned synthetic profiles."""

import asyncio
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
        await asyncio.gather(*getattr(app.state, "background_tasks", set()))
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


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("row", ["1,0,0,Alpha", "1,0,0,Alpha,A1,false,extra"])
async def test_ragged_csv_rejected_without_import_mutation(import_api, db_pool, row):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    before = await import_state(db_pool, app, profiles)
    response = await client.post(
        "/api/admin/import/boundaries",
        content="unit_id,row,col,first_label,first_catalog,is_empty\n" + row,
        headers={**headers, "Content-Type": "text/csv"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "parse_error"
    assert "CSV line 2" in response.json()["detail"]["message"]
    assert await import_state(db_pool, app, profiles) == before
    assert all(queue.empty() for queue in queues)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("override", [False, True])
@pytest.mark.parametrize("address", [(99, 0, 0), (1, 0, 2)])
async def test_outsider_rejected_before_any_fill_or_write(
    import_api, db_pool, dry_run, override, address
):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    exported = await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    assert exported.status_code == 200, exported.text
    document = yaml.safe_load(exported.content)
    unit, row, col = address
    outsider = {
        "unit_id": unit,
        "row": row,
        "col": col,
        "is_empty": False,
        "first_label": "Alpha",
        "first_catalog": "A1",
    }
    if override:
        outsider["overrides"] = {"Alpha": 0.5}
    document["cubes"].append(outsider)
    before = await import_state(db_pool, app, profiles)
    response = await client.post(
        f"/api/admin/import/boundaries?dry_run={str(dry_run).lower()}",
        content=yaml.safe_dump(document),
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "unknown_cube_addresses"
    assert response.json()["detail"]["addresses"] == [{"unit_id": unit, "row": row, "col": col}]
    assert await import_state(db_pool, app, profiles) == before
    assert all(queue.empty() for queue in queues)


@pytest.mark.asyncio(loop_scope="session")
async def test_raw_identity_import_and_valid_bootstrap_stay_supported(import_api, db_pool):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    exported = await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    assert exported.status_code == 200, exported.text
    preview = await client.post(
        "/api/admin/import/boundaries?dry_run=true",
        content=exported.content,
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["diff_preview"] == []
    committed = await client.post(
        "/api/admin/import/boundaries",
        content=exported.content,
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert committed.status_code == 200, committed.text
    assert committed.json()["applied"] == 2
    reexported = await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    assert reexported.status_code == 200
    assert reexported.content == exported.content
    assert not queues[0].empty()
    assert queues[1].empty()
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid", (profiles[0],)
        )
        await conn.commit()
    await app.state.boundary_cache_registry[profiles[0]].load(db_pool, profile_id=profiles[0])
    app.state.segment_cache_registry[profiles[0]].derive(
        app.state.boundary_cache_registry[profiles[0]], app.state.snapshot_registry[profiles[0]], {}
    )
    bootstrapped = await client.post(
        "/api/admin/import/boundaries",
        content=exported.content,
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert bootstrapped.status_code == 200, bootstrapped.text
    assert bootstrapped.json()["applied"] == 2
    assert (
        await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    ).content == exported.content


@pytest.mark.asyncio(loop_scope="session")
async def test_raw_identity_keeps_committed_phantom_catalog_spelling(import_api, db_pool):  # type: ignore[no-untyped-def]
    from gruvax.db.queries import cube_exact_match

    client, headers, app, profiles, queues = import_api
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.cube_boundaries SET first_catalog = 'A-000' WHERE profile_id = %s::uuid AND col = 0",
            (profiles[0],),
        )
        await conn.commit()
    assert not await cube_exact_match(db_pool, "Alpha", "A-000", profile_id=profiles[0])
    cache = app.state.boundary_cache_registry[profiles[0]]
    await cache.load(db_pool, profile_id=profiles[0])
    app.state.segment_cache_registry[profiles[0]].derive(
        cache, app.state.snapshot_registry[profiles[0]], cache.overrides
    )
    exported = await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    assert exported.status_code == 200
    assert b"A-000" in exported.content
    other_before = await import_state(db_pool, app, [profiles[1]])
    response = await client.post(
        "/api/admin/import/boundaries",
        content=exported.content,
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 200, response.text
    assert (
        await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    ).content == exported.content
    assert await import_state(db_pool, app, [profiles[1]]) == other_before
    assert not queues[0].empty()
    assert queues[1].empty()


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("address", [(99, 0, 0), (1, 99, 0), (1, 0, 99)])
async def test_bootstrap_rejects_unknown_unit_or_dimensions(import_api, db_pool, address):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid", (profiles[0],)
        )
        await conn.commit()
    before = await import_state(db_pool, app, profiles)
    unit, row, col = address
    response = await client.post(
        "/api/admin/import/boundaries",
        content=yaml.safe_dump(
            {"version": "1", "cubes": [{"unit_id": unit, "row": row, "col": col, "is_empty": True}]}
        ),
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "unknown_cube_addresses"
    assert await import_state(db_pool, app, profiles) == before
    assert all(queue.empty() for queue in queues)


@pytest.mark.asyncio(loop_scope="session")
async def test_emptied_overrides_do_not_resurrect_after_reimport_and_reload(import_api, db_pool):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    other_before = await import_state(db_pool, app, [profiles[1]])
    exported = await client.get("/api/admin/export/boundaries.yaml", headers=headers)
    assert exported.status_code == 200, exported.text
    initial = await client.get("/api/locate?release_id=2", headers=headers)
    assert initial.status_code == 200, initial.text
    emptied = await client.post(
        "/api/admin/import/boundaries",
        content='version: "1"\ncubes: []\n',
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert emptied.status_code == 200, emptied.text
    async with db_pool.connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT label, fraction FROM gruvax.segment_overrides WHERE profile_id = %s::uuid",
                (profiles[0],),
            )
        ).fetchall()
    assert rows == [], "An emptied cube must not keep a persistent override"
    assert app.state.boundary_cache_registry[profiles[0]].overrides == {}
    document = yaml.safe_load(exported.content)
    for cube in document["cubes"]:
        cube.pop("overrides", None)
    repopulated = await client.post(
        "/api/admin/import/boundaries",
        content=yaml.safe_dump(document),
        headers={**headers, "Content-Type": "application/x-yaml"},
    )
    assert repopulated.status_code == 200, repopulated.text
    live = await client.get("/api/locate?release_id=2", headers=headers)
    assert live.status_code == 200, live.text
    assert live.json()["sub_cube_interval"] != initial.json()["sub_cube_interval"]
    alpha = next(
        s
        for b in app.state.segment_cache_registry[profiles[0]]._bins
        for s in b.segments
        if s.label == "alpha"
    )
    assert not alpha.is_override
    assert alpha.applied_fraction == pytest.approx(2 / 3)
    fresh_boundary, fresh_snapshot, fresh_segment = (
        BoundaryCache(),
        CollectionSnapshot(),
        SegmentCache(),
    )
    await fresh_boundary.load(db_pool, profile_id=profiles[0])
    await fresh_snapshot.load(db_pool, profile_id=profiles[0])
    fresh_segment.derive(fresh_boundary, fresh_snapshot, fresh_boundary.overrides)
    assert fresh_boundary.overrides == {}
    app.state.boundary_cache_registry[profiles[0]] = fresh_boundary
    app.state.snapshot_registry[profiles[0]] = fresh_snapshot
    app.state.segment_cache_registry[profiles[0]] = fresh_segment
    reloaded = await client.get("/api/locate?release_id=2", headers=headers)
    assert reloaded.status_code == 200, reloaded.text
    for field in ["primary_cube", "label_span", "sub_cube_interval", "confidence"]:
        assert reloaded.json()[field] == live.json()[field]
    assert await import_state(db_pool, app, [profiles[1]]) == other_before
    assert not queues[0].empty()
    assert queues[1].empty()


@pytest.mark.asyncio(loop_scope="session")
async def test_csv_preserves_nonempty_overrides(import_api, db_pool):  # type: ignore[no-untyped-def]
    client, headers, app, profiles, queues = import_api
    response = await client.post(
        "/api/admin/import/boundaries",
        content="unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,Alpha,A1,false\n1,0,1,Zulu,Z2,false\n",
        headers={**headers, "Content-Type": "text/csv"},
    )
    assert response.status_code == 200, response.text
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT fraction FROM gruvax.segment_overrides WHERE profile_id = %s::uuid AND label = %s",
                (profiles[0], "alpha"),
            )
        ).fetchone()
    assert row == (0.25,)
    assert app.state.boundary_cache_registry[profiles[0]].overrides[(1, 0, 0, "alpha")] == 0.25
    assert not queues[0].empty()
    assert queues[1].empty()


@pytest.mark.asyncio(loop_scope="session")
async def test_late_sql_failure_rolls_back_empty_override_cleanup(import_api, db_pool, monkeypatch):  # type: ignore[no-untyped-def]
    from psycopg.errors import UniqueViolation

    from gruvax.api.admin import import_ as module

    client, headers, app, profiles, queues = import_api
    before = await import_state(db_pool, app, profiles)

    async def fail_after_cleanup(conn, _key, _response):  # type: ignore[no-untyped-def]
        await conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) SELECT id, display_name, app_token_encrypted FROM gruvax.profiles WHERE id = %s::uuid",
            (profiles[0],),
        )

    monkeypatch.setattr(module, "store_idempotency", fail_after_cleanup)
    with pytest.raises(UniqueViolation):
        await client.post(
            "/api/admin/import/boundaries",
            content='version: "1"\ncubes: []\n',
            headers={
                **headers,
                "Content-Type": "application/x-yaml",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
    assert await import_state(db_pool, app, profiles) == before
    assert all(queue.empty() for queue in queues)

"""Actual SQL staging abort retains the last committed collection and live caches."""

import datetime as dt
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio

from gruvax.discogsography.client import DiscogsographyClient
from gruvax.discogsography.errors import SnapshotMismatch
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
from tests.fixtures.migration_databases import (
    migration_db as migration_db,
    migration_pool as migration_pool,
)


DEFAULT = "00000000-0000-0000-0000-000000000001"
USER = "99999999-9999-9999-9999-999999999999"
GENERATION = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _seeded_profile_collection(migration_db):  # type: ignore[no-untyped-def]
    # Override inherited shared-parent seeding: this module owns its fresh child.
    import psycopg

    with psycopg.connect(migration_db[0]) as conn:
        assert (
            conn.execute("SELECT current_database()").fetchone()[0].startswith("gruvax_migration_")
        )


@pytest_asyncio.fixture(loop_scope="session")
async def db_pool(migration_pool):  # type: ignore[no-untyped-def]
    async with migration_pool.connection() as conn:
        assert (await (await conn.execute("SELECT current_database()")).fetchone())[0].startswith(
            "gruvax_migration_"
        )
    return migration_pool


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("failure", ["generation", "expired"])
async def test_staged_page_then_mismatch_preserves_sql_cache_pat_and_cleanup(
    db_pool, migration_db, monkeypatch, failure
):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(profile_sync.settings, "DATABASE_URL", migration_db[1])
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET app_token_encrypted=%s,app_token_revoked=false,last_sync_at=now()-INTERVAL '2 days',last_sync_status='ok',last_sync_item_count=1 WHERE id=%s",
            (encrypt_pat("dscg_synthetic_snapshot"), DEFAULT),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection(profile_id,release_id,folder_id,title,label,catalog_number) VALUES (%s,700,1,'Old committed record','Old Label','OLD')",
            (DEFAULT,),
        )
        before_rows = await (
            await conn.execute("SELECT * FROM gruvax.profile_collection ORDER BY release_id")
        ).fetchall()
        before_profile = await (
            await conn.execute(
                "SELECT to_jsonb(p)-'last_sync_status'-'last_sync_error' FROM gruvax.profiles p WHERE id=%s",
                (DEFAULT,),
            )
        ).fetchone()
    boundary, snapshot, segment = BoundaryCache(), CollectionSnapshot(), SegmentCache()
    await boundary.load(db_pool, profile_id=DEFAULT)
    await snapshot.load(db_pool, profile_id=DEFAULT)
    segment.derive(boundary, snapshot, boundary.overrides)
    before_cache = (dict(boundary.__dict__), dict(snapshot.__dict__), dict(segment.__dict__))
    bus = EventBus()
    queue = bus.subscribe()
    state = SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={DEFAULT: boundary},
        snapshot_registry={DEFAULT: snapshot},
        segment_cache_registry={DEFAULT: segment},
        event_bus_registry={DEFAULT: bus},
    )
    expiry = (
        (dt.datetime.now(dt.UTC) + dt.timedelta(minutes=10))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )
    requests: list[httpx.Request] = []
    written: list[tuple[Any, ...]] = []
    real_mapper = profile_sync._release_to_tuple

    def mapper(row):  # type: ignore[no-untyped-def]
        result = real_mapper(row)
        written.append(result)
        return result

    monkeypatch.setattr(profile_sync, "_release_to_tuple", mapper)

    def respond(request):  # type: ignore[no-untyped-def]
        requests.append(request)
        offset = int(request.url.params["offset"])
        if offset:
            assert len(written) == 200, "first page must have entered the actual COPY stream"
            if failure == "expired":
                return httpx.Response(410, json={"detail": {"code": "snapshot_expired"}})
        return httpx.Response(
            200,
            json={
                "user_id": USER,
                "releases": [
                    {"id": str(1000 + i), "title": "New row", "folder_id": 1}
                    for i in range(offset, min(offset + 200, 201))
                ],
                "total": 201,
                "limit": 200,
                "offset": offset,
                "has_more": offset == 0,
                "snapshot_token": "synthetic-opaque-pin",
                "snapshot_generation": GENERATION
                if not offset
                else "22222222-2222-2222-2222-222222222222",
                "snapshot_expires_at": expiry,
                "snapshot_source": "completed_collection_sync",
            },
        )

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic_snapshot")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), base_url="http://synthetic"
    )
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: client)
    try:
        with pytest.raises(SnapshotMismatch):
            await profile_sync.sync_profile(DEFAULT, state)
        assert len(requests) == 2 and len(written) == 200
        assert client._client.is_closed
        async with db_pool.connection() as conn:
            assert (
                await (
                    await conn.execute(
                        "SELECT * FROM gruvax.profile_collection ORDER BY release_id"
                    )
                ).fetchall()
                == before_rows
            )
            assert (
                await (
                    await conn.execute(
                        "SELECT to_jsonb(p)-'last_sync_status'-'last_sync_error' FROM gruvax.profiles p WHERE id=%s",
                        (DEFAULT,),
                    )
                ).fetchone()
                == before_profile
            )
            assert await (
                await conn.execute(
                    "SELECT last_sync_status,last_sync_error FROM gruvax.profiles WHERE id=%s",
                    (DEFAULT,),
                )
            ).fetchone() == ("failed", "snapshot_mismatch")
            assert await (
                await conn.execute(
                    "SELECT pg_try_advisory_lock(%s)", (profile_sync._lock_key(DEFAULT),)
                )
            ).fetchone() == (True,)
            await conn.execute("SELECT pg_advisory_unlock(%s)", (profile_sync._lock_key(DEFAULT),))
            assert await (
                await conn.execute(
                    "SELECT count(*) FROM pg_class WHERE relname='profile_collection_staging'"
                )
            ).fetchone() == (0,)
        assert (boundary.__dict__, snapshot.__dict__, segment.__dict__) == before_cache
        assert state.snapshot_registry[DEFAULT] is snapshot
        assert queue.empty()
    finally:
        bus.unsubscribe(queue)
        await client.aclose()


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("size", [0, 1, 201, "instances"])
async def test_successful_snapshot_swaps_and_counts_wire_instances_before_dedup(
    db_pool, migration_db, monkeypatch, size
):  # type: ignore[no-untyped-def]
    from gruvax._internal.fake_discogsography import create_fake_app

    monkeypatch.setattr(profile_sync.settings, "DATABASE_URL", migration_db[1])
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET app_token_encrypted=%s,app_token_revoked=false WHERE id=%s",
            (encrypt_pat("dscg_synthetic_snapshot"), DEFAULT),
        )
    if size == "instances":
        seed = [
            {"id": "42", "folder_id": 1, "instance_id": 1},
            {"id": "42", "folder_id": 1, "instance_id": 2},
            {"id": "43", "folder_id": 1, "instance_id": None},
        ]
        expected_ids = [42, 43]
    else:
        seed = [{"id": str(i + 1), "title": f"Synthetic {i}", "folder_id": 1} for i in range(size)]
        expected_ids = list(range(1, size + 1))
    app = create_fake_app(seed=seed, user_id=USER)
    client = DiscogsographyClient("http://fake", "dscg_synthetic_snapshot")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://fake",
        headers={"Authorization": "Bearer dscg_synthetic_snapshot"},
    )
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: client)
    boundary, snapshot, segment = BoundaryCache(), CollectionSnapshot(), SegmentCache()
    bus = EventBus()
    queue = bus.subscribe()
    state = SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={DEFAULT: boundary},
        snapshot_registry={DEFAULT: snapshot},
        segment_cache_registry={DEFAULT: segment},
        event_bus_registry={DEFAULT: bus},
    )
    try:
        result = await profile_sync.sync_profile(DEFAULT, state)
        assert result["item_count"] == len(expected_ids)
        async with db_pool.connection() as conn:
            ids = await (
                await conn.execute(
                    "SELECT release_id FROM gruvax.profile_collection ORDER BY release_id"
                )
            ).fetchall()
            assert ids == [(item,) for item in expected_ids]
            assert await (
                await conn.execute(
                    "SELECT last_sync_status,last_sync_error,last_sync_item_count,discogsography_user_id::text FROM gruvax.profiles WHERE id=%s",
                    (DEFAULT,),
                )
            ).fetchone() == ("ok", None, len(expected_ids), USER)
        assert client._client.is_closed
        assert state.snapshot_registry[DEFAULT] is snapshot
        assert not queue.empty()
        assert queue.get_nowait().name == "collection_changed"
    finally:
        bus.unsubscribe(queue)
        await client.aclose()

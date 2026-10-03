"""A pending admin writer still refreshes the live generation after sync finishes."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.api.admin.segments import router
from gruvax.api.deps import WriteContext, get_pool, get_write_context, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus
from gruvax.sync.profile_sync import _refresh_profile_caches


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("during_prepare", [False, True])
async def test_captured_writer_commits_after_sync_and_refreshes_live_cache(
    db_pool: Any,
    monkeypatch: pytest.MonkeyPatch,
    during_prepare: bool,
) -> None:
    profile_id = str(uuid4())
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id,display_name,app_token_encrypted,app_token_revoked)"
            " VALUES (%s,%s,%s,TRUE)",
            (profile_id, "Publication " + profile_id, b""),
        )
        for col, catalog in enumerate(("A 1", "A 4")):
            await conn.execute(
                "INSERT INTO gruvax.cube_boundaries"
                " (profile_id,unit_id,row,col,first_label,first_catalog,is_empty)"
                " VALUES (%s,1,0,%s,'AAA',%s,FALSE)",
                (profile_id, col, catalog),
            )
        for release in range(1, 7):
            await conn.execute(
                "INSERT INTO gruvax.profile_collection (profile_id,release_id,folder_id,label,catalog_number)"
                " VALUES (%s,%s,1,'AAA',%s)",
                (profile_id, release, f"A {release}"),
            )
    refresh_task = None
    release = asyncio.Event()
    try:
        boundary, snapshot, segment = BoundaryCache(), CollectionSnapshot(), SegmentCache()
        await boundary.load(db_pool, profile_id=profile_id)
        await snapshot.load(db_pool, profile_id=profile_id)
        segment.derive(boundary, snapshot, {})
        bus = EventBus()
        captured = WriteContext(profile_id, bus, boundary, segment, snapshot)
        state = SimpleNamespace(
            db_pool=db_pool,
            boundary_cache_registry={profile_id: boundary},
            snapshot_registry={profile_id: snapshot},
            segment_cache_registry={profile_id: segment},
            event_bus_registry={profile_id: bus},
        )
        # Pause the fresh snapshot read AFTER the fresh boundaries were loaded.
        # An actual admin transaction then commits a new cut into the live cache.
        if during_prepare:
            reached = asyncio.Event()
            original_load = CollectionSnapshot.load
            calls = 0

            async def delayed_snapshot(self: CollectionSnapshot, pool: Any, **kwargs: Any) -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    reached.set()
                    await release.wait()
                await original_load(self, pool, **kwargs)

            monkeypatch.setattr(CollectionSnapshot, "load", delayed_snapshot)
            refresh_task = asyncio.create_task(_refresh_profile_caches(profile_id, state))
            await asyncio.wait_for(reached.wait(), 5)
        else:
            await _refresh_profile_caches(profile_id, state)
        app = FastAPI()
        app.include_router(router, prefix="/api/admin")
        app.dependency_overrides[get_pool] = lambda: db_pool
        app.dependency_overrides[get_write_context] = lambda: captured
        app.dependency_overrides[require_admin] = lambda: {}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.put(
                "/api/admin/cubes/1/0/1/cut",
                json={
                    "first_label": "AAA",
                    "first_catalog": "A 5",
                },
            )
        release.set()
        if refresh_task is not None:
            await asyncio.wait_for(refresh_task, 5)
        assert response.status_code == 200, response.text
        async with db_pool.connection() as conn:
            cursor = await conn.execute(
                "SELECT first_catalog FROM gruvax.cube_boundaries"
                " WHERE profile_id=%s AND unit_id=1 AND row=0 AND col=1",
                (profile_id,),
            )
            assert await cursor.fetchone() == ("A 5",)
        live = state.boundary_cache_registry[profile_id]
        assert live.get_boundaries()[1].first_catalog == "A 5", (
            "Committed writer refreshed retired caches"
        )
        live_segments = state.segment_cache_registry[profile_id]
        assert live_segments.get_bin(1, 0, 0).segments[0].segment_count == 4
        assert live_segments.get_bin(1, 0, 1).segments[0].segment_count == 2
        assert live is captured.boundary_cache
        assert live_segments is captured.segment_cache
        if during_prepare:
            assert calls == 2, "Concurrent committed writer must trigger re-preparation"
    finally:
        if refresh_task is not None and not refresh_task.done():
            refresh_task.cancel()
            with suppress(asyncio.CancelledError):
                await refresh_task
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id=%s", (profile_id,))

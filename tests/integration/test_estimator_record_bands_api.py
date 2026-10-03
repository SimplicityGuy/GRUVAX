"""Actual locate routes serialize precise bands from isolated profile-owned data."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.api.locate import router
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache


def _record_shape(
    shape: str, base: int
) -> tuple[list[tuple[int, str, str]], list[tuple[int, str, str]]]:
    if shape == "mixed":
        return [(0, "LabelA", "A 001")], [
            (base + 1, "LabelA", "A 001"),
            (base + 2, "LabelA", "A 002"),
            (base + 3, "LabelB", "B 001"),
            (base + 4, "LabelB", "B 002"),
        ]
    if shape == "straddle":
        return [(0, "LabelS", "LS 001"), (1, "LabelS", "LS 007")], [
            (base + i, "LabelS", f"LS {i:03d}") for i in range(1, 13)
        ]
    return [(0, "Singleton", "SL 001")], [(base + 1, "Singleton", "SL 001")]


@pytest_asyncio.fixture(loop_scope="session")
async def estimator_app(db_pool: Any, request: pytest.FixtureRequest) -> Any:
    profile_id = str(uuid4())
    base = 500000 + uuid4().int % 100000000
    boundaries, records = _record_shape(request.param, base)
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id,display_name,app_token_encrypted,app_token_revoked)"
            " VALUES (%s,%s,%s,TRUE)",
            (profile_id, profile_id, b""),
        )
        for col, label, catalog in boundaries:
            await conn.execute(
                "INSERT INTO gruvax.cube_boundaries"
                " (profile_id,unit_id,row,col,first_label,first_catalog,is_empty)"
                " VALUES (%s,1,0,%s,%s,%s,FALSE)",
                (profile_id, col, label, catalog),
            )
        for release_id, label, catalog in records:
            await conn.execute(
                "INSERT INTO gruvax.profile_collection (profile_id,release_id,folder_id,label,catalog_number)"
                " VALUES (%s,%s,1,%s,%s)",
                (profile_id, release_id, label, catalog),
            )
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.db_pool = db_pool
    boundary, snapshot, segments = BoundaryCache(), CollectionSnapshot(), SegmentCache()
    await boundary.load(db_pool, profile_id=profile_id)
    await snapshot.load(db_pool, profile_id=profile_id)
    segments.derive(boundary, snapshot, {})
    app.state.snapshot_registry = {profile_id: snapshot}
    app.state.segment_cache_registry = {profile_id: segments}
    try:
        yield app, profile_id, base
    finally:
        await asyncio.gather(*getattr(app.state, "background_tasks", set()))
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id=%s", (profile_id,))
            await conn.execute(
                "DELETE FROM gruvax.record_stats WHERE release_id>%s AND release_id<=%s",
                (base, base + len(records)),
            )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("estimator_app", ["singleton"], indirect=True)
@pytest.mark.parametrize("missing", [None, "snapshot", "segment", "record"])
async def test_singleton_route_and_real_cube_only_controls(
    estimator_app: Any, missing: str | None
) -> None:
    app, profile_id, base = estimator_app
    if missing == "snapshot":
        app.state.snapshot_registry[profile_id] = CollectionSnapshot()
    elif missing == "segment":
        app.state.segment_cache_registry[profile_id] = SegmentCache()
    elif missing == "record":
        snapshot = CollectionSnapshot()
        from gruvax.estimator.collection_snapshot import RecordRow

        snapshot._load_snapshot({"singleton": [RecordRow(base + 99, "Singleton", "SL 099")]})
        app.state.snapshot_registry[profile_id] = snapshot
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"gruvax_browse_binding": profile_id},
    ) as client:
        response = await client.get("/api/locate", params={"release_id": base + 1})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {
        "release_id",
        "primary_cube",
        "label_span",
        "sub_cube_interval",
        "confidence",
        "generated_at",
        "estimator_version",
    }
    if missing is not None:
        assert body["sub_cube_interval"] is None
        assert body["estimator_version"] == "cube-only-v1"
        return
    assert body["primary_cube"] == {"unit_id": 1, "row": 0, "col": 0}
    assert body["label_span"] == [body["primary_cube"]]
    assert body["confidence"] == 0.30
    assert body["estimator_version"] == "segment-v1"
    assert body["sub_cube_interval"] == {
        "start": 0.0,
        "end": 1.0,
        "crosses_boundary": False,
        "next_cube": None,
    }


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("estimator_app", ["straddle"], indirect=True)
@pytest.mark.parametrize("index", [1, 5, 6, 7, 12])
async def test_straddle_route_crosses_only_for_edge_band(estimator_app: Any, index: int) -> None:
    app, profile_id, base = estimator_app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"gruvax_browse_binding": profile_id},
    ) as client:
        response = await client.get("/api/locate", params={"release_id": base + index})
    assert response.status_code == 200, response.text
    body = response.json()
    interval = body["sub_cube_interval"]
    assert set(interval) == {"start", "end", "crosses_boundary", "next_cube"}
    position = ((index - 1) % 6) / 5
    assert interval["start"] == pytest.approx(max(0, position - 0.05))
    assert interval["end"] == pytest.approx(min(1, position + 0.05))
    assert interval["crosses_boundary"] is (index == 6)
    assert interval["next_cube"] == ({"unit_id": 1, "row": 0, "col": 1} if index == 6 else None)


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("estimator_app", ["mixed"], indirect=True)
@pytest.mark.parametrize("index,position", [(1, 0.125), (2, 0.375), (3, 0.625), (4, 0.875)])
async def test_shared_bin_route_serializes_distinct_midpoints(
    estimator_app: Any, index: int, position: float
) -> None:
    app, profile_id, base = estimator_app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"gruvax_browse_binding": profile_id},
    ) as client:
        response = await client.get("/api/locate", params={"release_id": base + index})
    assert response.status_code == 200, response.text
    body = response.json()
    interval = body["sub_cube_interval"]
    assert set(interval) == {"start", "end", "crosses_boundary", "next_cube"}
    assert interval["start"] == pytest.approx(position - 0.05)
    assert interval["end"] == pytest.approx(position + 0.05)
    assert not interval["crosses_boundary"]
    assert interval["next_cube"] is None
    assert body["primary_cube"] == {"unit_id": 1, "row": 0, "col": 0}
    assert body["label_span"] == [body["primary_cube"]]
    assert body["estimator_version"] == "segment-v1"

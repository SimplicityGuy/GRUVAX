"""Insert-cut validates every affected unit before its atomic SQL change-set."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.api.admin.segments import router
from gruvax.api.deps import WriteContext, get_pool, get_write_context, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus


async def _stored(pool: Any, profile_id: str) -> tuple[Any, Any]:
    async with pool.connection() as conn:
        cursor = await conn.execute(
            "SELECT unit_id,row,col,first_label,first_catalog,is_empty"
            " FROM gruvax.cube_boundaries WHERE profile_id=%s ORDER BY unit_id,row,col",
            (profile_id,),
        )
        boundaries = await cursor.fetchall()
        cursor = await conn.execute(
            "SELECT count(*) FROM gruvax.boundary_history WHERE profile_id=%s", (profile_id,)
        )
        return boundaries, await cursor.fetchone()


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("scatter", [True, False])
async def test_insert_across_units_validates_second_unit(db_pool: Any, scatter: bool) -> None:
    """A later-unit scatter rolls back everything; legal cross-unit shifts still work."""
    profile_id = str(uuid4())
    rows = [(1, 0, 0, "Atlantic", "A 1", False), (1, 0, 1, "Verve", "A 1", False)]
    rows += [
        (2, 0, 0, "Atlantic" if scatter else "Verve", "A 1" if scatter else "A 3", False),
        (2, 0, 1, "Verve", "A 2" if scatter else "A 4", False),
        (2, 0, 2, None, None, True),
    ]
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id,display_name,app_token_encrypted,app_token_revoked)"
            " VALUES (%s,%s,%s,TRUE)",
            (profile_id, "Cascade " + profile_id, b""),
        )
        for row in rows:
            await conn.execute(
                "INSERT INTO gruvax.cube_boundaries"
                " (profile_id,unit_id,row,col,first_label,first_catalog,is_empty)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (profile_id, *row),
            )
    try:
        cache = BoundaryCache()
        await cache.load(db_pool, profile_id=profile_id)
        snapshot = CollectionSnapshot()
        snapshot._load_snapshot(
            {
                label.casefold(): [RecordRow(i * 100 + n, label, f"A {n}") for n in range(1, 9)]
                for i, label in enumerate(("Atlantic", "Verve"), 1)
            }
        )
        segments = SegmentCache()
        segments.derive(cache, snapshot, {})
        ctx = WriteContext(profile_id, EventBus(), cache, segments, snapshot)
        app = FastAPI()
        app.include_router(router, prefix="/api/admin")
        app.dependency_overrides[get_pool] = lambda: db_pool
        app.dependency_overrides[get_write_context] = lambda: ctx
        app.dependency_overrides[require_admin] = lambda: {}
        before = await _stored(db_pool, profile_id)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/admin/cubes/insert-cut",
                json={
                    "after_unit_id": 1,
                    "after_row": 0,
                    "after_col": 0,
                    "new_first_label": "Verve",
                    "new_first_catalog": "A 2",
                    "force": True,
                },
            )
        after = await _stored(db_pool, profile_id)
        if scatter:
            assert response.status_code == 400, response.text
            assert response.json()["type"] == "contiguity_error"
            assert "Verve" in response.json()["message"]
            assert after == before, "Rejected second-unit scatter wrote boundaries or history"
            assert [
                (b.unit_id, b.row, b.col, b.first_label, b.first_catalog, b.is_empty)
                for b in cache.get_boundaries()
            ] == before[0]
        else:
            assert response.status_code == 200, response.text
            assert response.json()["affected"] == 4
            assert [row[3] for row in after[0] if row[0] == 2] == ["Verve"] * 3
            assert after[1] == (4,)
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id=%s", (profile_id,))

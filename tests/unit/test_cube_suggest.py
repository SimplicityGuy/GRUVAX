"""Mounted suggestion endpoint chooses anchors that can split a populated bin."""

from __future__ import annotations

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.api.admin.cubes import router
from gruvax.api.deps import WriteContext, get_pool, get_write_context, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "count,next_label", [(2, "AAA"), (5, "AAA"), (1, "AAA"), (0, "AAA"), (5, None), (5, "BBB")]
)
async def test_suggest_splits_current_bin_or_returns_v1_null(
    count: int, next_label: str | None
) -> None:
    cache = BoundaryCache()
    rows = [BoundaryRow(1, 0, 0, "AAA" if count else None, "A 1" if count else None, not count)]
    if next_label:
        rows.append(
            BoundaryRow(
                1, 0, 1, next_label, f"A {count + 1}" if next_label == "AAA" else "B 1", False
            )
        )
    cache._load_rows(rows)
    snapshot = CollectionSnapshot()
    records = [RecordRow(100 + i, "AAA", f"A {i}") for i in range(1, count + 3)]
    snapshot._load_snapshot({"aaa": records, "bbb": [RecordRow(999, "BBB", "B 1")]})
    segments = SegmentCache()
    segments.derive(cache, snapshot, {})
    current = segments.get_bin(1, 0, 0)
    if count and next_label == "AAA":
        assert current is not None and sum(s.segment_count for s in current.segments) == count
    ctx = WriteContext(
        "00000000-0000-0000-0000-000000000001", EventBus(), cache, segments, snapshot
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/admin")
    app.dependency_overrides[get_pool] = lambda: None
    app.dependency_overrides[get_write_context] = lambda: ctx
    app.dependency_overrides[require_admin] = lambda: {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/admin/cubes/suggest", json={"unit_id": 1, "row": 0, "col": 0}
        )
    assert response.status_code == 200, response.text
    suggestion = response.json()["suggestion"]
    if count > 1 and next_label == "AAA":
        assert suggestion is not None, "Multi-record same-label bin must offer a real split"
        assert suggestion["release_id"] == records[count // 2].release_id
        assert suggestion["catalog_number"] == records[count // 2].catalog_number
        assert suggestion["label"] == "AAA"
        assert 100 + 1 < suggestion["release_id"] < 100 + count + 1
    else:
        assert suggestion is None

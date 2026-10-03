"""Cache refresh must tolerate actual registry eviction without publishing stale events."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from gruvax.api.admin.profiles import _evict_profile_registries
from gruvax.events.bus import EventBus
from gruvax.sync import profile_sync
from gruvax.sync.profile_sync import _refresh_profile_caches


PROFILE_ID = "00000000-0000-0000-0000-000000000002"
REGISTRIES = (
    "boundary_cache_registry",
    "snapshot_registry",
    "segment_cache_registry",
    "event_bus_registry",
)


@pytest.fixture
def state(monkeypatch):  # type: ignore[no-untyped-def]
    boundary = SimpleNamespace(
        invalidate=Mock(), load=AsyncMock(), overrides={}, publish_from=Mock(), generation=0
    )
    snapshot = SimpleNamespace(load=AsyncMock(), publish_from=Mock())
    segment = SimpleNamespace(derive=Mock(), publish_from=Mock())
    bus = EventBus()
    fresh_boundary = SimpleNamespace(load=AsyncMock(), overrides={})
    fresh_snapshot = SimpleNamespace(load=AsyncMock(), publish_from=Mock())
    fresh_segment = SimpleNamespace(derive=Mock(), publish_from=Mock())
    monkeypatch.setattr(profile_sync, "BoundaryCache", lambda: fresh_boundary)
    monkeypatch.setattr(profile_sync, "CollectionSnapshot", lambda: fresh_snapshot)
    monkeypatch.setattr(profile_sync, "SegmentCache", lambda: fresh_segment)
    return SimpleNamespace(
        fresh_boundary=fresh_boundary,
        fresh_snapshot=fresh_snapshot,
        fresh_segment=fresh_segment,
        db_pool=object(),
        boundary_cache_registry={PROFILE_ID: boundary},
        snapshot_registry={PROFILE_ID: snapshot},
        segment_cache_registry={PROFILE_ID: segment},
        event_bus_registry={PROFILE_ID: bus},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", REGISTRIES)
async def test_missing_cache_entry_skips_refresh_and_events(state, missing: str) -> None:  # type: ignore[no-untyped-def]
    boundary = state.boundary_cache_registry[PROFILE_ID]
    snapshot = state.snapshot_registry[PROFILE_ID]
    segment = state.segment_cache_registry[PROFILE_ID]
    bus = state.event_bus_registry[PROFILE_ID]
    queue = bus.subscribe()
    getattr(state, missing).pop(PROFILE_ID)
    await _refresh_profile_caches(PROFILE_ID, state)
    assert queue.empty()
    boundary.invalidate.assert_not_called()
    snapshot.load.assert_not_awaited()
    segment.derive.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["boundary", "snapshot"])
async def test_eviction_during_await_skips_remaining_refresh_and_publish(state, phase: str) -> None:  # type: ignore[no-untyped-def]
    boundary = state.fresh_boundary
    snapshot = state.fresh_snapshot
    segment = state.fresh_segment
    queue = state.event_bus_registry[PROFILE_ID].subscribe()

    async def evict(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        _evict_profile_registries(PROFILE_ID, state)

    target = boundary if phase == "boundary" else snapshot
    target.load.side_effect = evict
    await _refresh_profile_caches(PROFILE_ID, state)
    target.load.assert_awaited_once()
    assert all(PROFILE_ID not in getattr(state, name) for name in REGISTRIES)
    assert queue.empty()
    segment.derive.assert_not_called()
    if phase == "boundary":
        snapshot.load.assert_not_awaited()


@pytest.mark.asyncio
async def test_healthy_cache_refresh_publishes_actual_event_after_loads(state) -> None:  # type: ignore[no-untyped-def]
    order = []

    async def loaded_boundary(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        order.append("boundary")

    async def loaded_snapshot(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        order.append("snapshot")

    state.fresh_boundary.load.side_effect = loaded_boundary
    state.fresh_snapshot.load.side_effect = loaded_snapshot
    state.fresh_segment.derive.side_effect = lambda *_: order.append("segments")
    queue = state.event_bus_registry[PROFILE_ID].subscribe()
    await _refresh_profile_caches(PROFILE_ID, state, new_record_count=3, is_initial_import=True)
    assert order == ["boundary", "snapshot", "segments"]
    event = queue.get_nowait()
    assert event.name == "collection_changed"
    assert event.data == {
        "profile_id": PROFILE_ID,
        "new_record_count": 3,
        "is_initial_import": True,
    }
    assert queue.empty()

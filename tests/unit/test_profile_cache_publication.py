"""Controlled sync awaits expose only complete cache generations to real readers."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio

from gruvax.api.admin.cache_rebuild import rebuild_derived_caches
from gruvax.api.admin.profiles import _evict_profile_registries
from gruvax.api.deps import WriteContext
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus
from gruvax.sync.profile_sync import _refresh_profile_caches


PROFILE = "00000000-0000-0000-0000-000000000001"
REGISTRIES = (
    "boundary_cache_registry",
    "snapshot_registry",
    "segment_cache_registry",
    "event_bus_registry",
)


def _generation(first: int, last: int) -> tuple[BoundaryCache, CollectionSnapshot, SegmentCache]:
    boundary = BoundaryCache()
    boundary._load_rows([BoundaryRow(1, 0, 0, "AAA", f"A {first}", False)])
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot(
        {"aaa": [RecordRow(i, "AAA", f"A {i}") for i in range(first, last + 1)]}
    )
    segment = SegmentCache()
    segment.derive(boundary, snapshot, {})
    return boundary, snapshot, segment


def _read(state: Any) -> tuple[Any, ...]:
    """Real reader surfaces, not mocked method call counts."""
    boundary = state.boundary_cache_registry[PROFILE]
    snapshot = state.snapshot_registry[PROFILE]
    segment = state.segment_cache_registry[PROFILE]
    return (
        [b.first_catalog for b in boundary.get_boundaries()],
        [r.release_id for r in snapshot.get_label_records("AAA")],
        [
            (s.segment_count, s.first_rank_in_label, s.last_rank_in_label)
            for s in segment.get_bin(1, 0, 0).segments
        ],
    )


class ControlledRefresh:
    """Pause the first database reads; subsequent retry reads see current rows."""

    def __init__(self) -> None:
        self.old = _generation(1, 4)
        self.database = _generation(2, 6)
        self.database[0]._load_overrides({(1, 0, 0, "aaa"): 1.0})
        self.bus = EventBus()
        self.events = self.bus.subscribe()
        self.state = SimpleNamespace(
            db_pool=object(),
            **{
                name: {PROFILE: entry}
                for name, entry in zip(REGISTRIES, (*self.old, self.bus), strict=True)
            },
        )
        self.state.boundary_cache, self.state.collection_snapshot, self.state.segment_cache = (
            self.old
        )
        self.captured = WriteContext(PROFILE, self.bus, self.old[0], self.old[2], self.old[1])
        self.before = _read(self.state)
        self.reached: asyncio.Queue[str] = asyncio.Queue()
        self.resume: asyncio.Queue[None] = asyncio.Queue()
        self.boundary_reads = 0
        self.snapshot_reads = 0
        self.failure_phase: str | None = None
        self.task: asyncio.Task[None] | None = None

    async def pause(self, phase: str) -> None:
        await self.reached.put(phase)
        await self.resume.get()
        if self.failure_phase == phase:
            raise OSError(f"controlled {phase} read failure")

    async def load_boundary(self, cache: BoundaryCache, profile_id: str) -> None:
        assert profile_id == PROFILE
        # An admin writer's existing-context rebuild is independent of the
        # suspended off-registry preparation. Its real cache load is immediate.
        if cache is not self.old[0]:
            self.boundary_reads += 1
            if self.boundary_reads == 1:
                await self.pause("boundary")
        cache._load_rows(self.database[0].get_boundaries())
        cache._load_overrides(self.database[0].overrides)

    async def load_snapshot(self, snapshot: CollectionSnapshot, profile_id: str) -> None:
        assert profile_id == PROFILE
        self.snapshot_reads += 1
        if self.snapshot_reads == 1:
            await self.pause("snapshot")
        snapshot._load_snapshot({"aaa": self.database[1].get_label_records("AAA")})

    async def start_at(self, phase: str) -> None:
        self.task = asyncio.create_task(
            _refresh_profile_caches(PROFILE, self.state, new_record_count=1)
        )
        assert await asyncio.wait_for(self.reached.get(), 2) == "boundary"
        assert _read(self.state) == self.before, "Boundary await exposed empty/mixed caches"
        if phase == "snapshot":
            await self.resume.put(None)
            assert await asyncio.wait_for(self.reached.get(), 2) == "snapshot"
            assert _read(self.state) == self.before, "Snapshot await exposed premature boundaries"

    async def finish(self) -> None:
        assert self.task is not None
        await self.resume.put(None)
        await asyncio.wait_for(self.task, 2)

    async def commit_cut(self) -> None:
        self.database[0]._load_rows([BoundaryRow(1, 0, 0, "AAA", "A 3", False)])
        await rebuild_derived_caches(self.state.db_pool, self.captured)
        assert _read(self.state)[0] == ["A 3"]


@pytest_asyncio.fixture
async def refresh(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    control = ControlledRefresh()

    async def boundary(cache: BoundaryCache, _pool: Any, *, profile_id: str) -> None:
        await control.load_boundary(cache, profile_id)

    async def snapshot(cache: CollectionSnapshot, _pool: Any, *, profile_id: str) -> None:
        await control.load_snapshot(cache, profile_id)

    monkeypatch.setattr(BoundaryCache, "load", boundary)
    monkeypatch.setattr(CollectionSnapshot, "load", snapshot)
    try:
        yield control
    finally:
        if control.task is not None and not control.task.done():
            control.task.cancel()
            with suppress(asyncio.CancelledError):
                await control.task


@pytest.mark.asyncio
async def test_readers_observe_complete_publication_and_stable_aliases(
    refresh: ControlledRefresh,
) -> None:
    rows = refresh.old[0].get_boundaries()
    records = refresh.old[1].get_label_records("AAA")
    bin_ = refresh.old[2].get_bin(1, 0, 0)
    overrides = refresh.old[0].overrides
    await refresh.start_at("snapshot")
    await refresh.finish()
    assert _read(refresh.state) == (["A 2"], [2, 3, 4, 5, 6], [(5, 0, 4)])
    assert refresh.state.boundary_cache is refresh.old[0]
    assert refresh.state.collection_snapshot is refresh.old[1]
    assert refresh.state.segment_cache is refresh.old[2]
    assert refresh.state.boundary_cache.overrides == {(1, 0, 0, "aaa"): 1.0}
    assert rows[0].first_catalog == "A 1" and len(records) == 4
    assert bin_ is not None and bin_.segments[0].segment_count == 4
    assert overrides == {}
    event = refresh.events.get_nowait()
    assert event.name == "collection_changed" and event.data["new_record_count"] == 1
    assert refresh.events.empty()


@pytest.mark.asyncio
async def test_captured_writer_after_publication_refreshes_live_generation(
    refresh: ControlledRefresh,
) -> None:
    await refresh.start_at("snapshot")
    await refresh.finish()
    await refresh.commit_cut()
    assert _read(refresh.state) == (["A 3"], [2, 3, 4, 5, 6], [(4, 1, 4)])


@pytest.mark.asyncio
async def test_writer_during_preparation_triggers_retry_and_retains_commit(
    refresh: ControlledRefresh,
) -> None:
    await refresh.start_at("snapshot")
    await refresh.commit_cut()
    await refresh.finish()
    assert _read(refresh.state) == (["A 3"], [2, 3, 4, 5, 6], [(4, 1, 4)])
    assert refresh.boundary_reads == refresh.snapshot_reads == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["boundary", "snapshot"])
@pytest.mark.parametrize("action", ["evict", "replace"])
async def test_identity_change_during_reads_cannot_resurrect_or_overwrite(
    refresh: ControlledRefresh,
    action: str,
    phase: str,
) -> None:
    await refresh.start_at(phase)
    if action == "evict":
        _evict_profile_registries(PROFILE, refresh.state)
    else:
        for name, entry in zip(REGISTRIES, (*refresh.database, EventBus()), strict=True):
            getattr(refresh.state, name)[PROFILE] = entry
    await refresh.finish()
    if action == "evict":
        assert all(PROFILE not in getattr(refresh.state, name) for name in REGISTRIES)
    else:
        assert all(
            getattr(refresh.state, name)[PROFILE] is entry
            for name, entry in zip(REGISTRIES[:3], refresh.database, strict=True)
        )
    assert refresh.events.empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["boundary", "snapshot"])
async def test_read_failure_leaves_previous_state_and_sends_no_event(
    refresh: ControlledRefresh, phase: str
) -> None:
    refresh.failure_phase = phase
    await refresh.start_at(phase)
    with pytest.raises(OSError, match="controlled"):
        await refresh.finish()
    assert _read(refresh.state) == refresh.before
    assert refresh.events.empty()


@pytest.mark.asyncio
async def test_cancelled_read_leaves_previous_state_and_sends_no_event(
    refresh: ControlledRefresh,
) -> None:
    await refresh.start_at("snapshot")
    assert refresh.task is not None
    refresh.task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await refresh.task
    assert _read(refresh.state) == refresh.before
    assert refresh.events.empty()


@pytest.mark.asyncio
async def test_derive_failure_leaves_previous_state_and_sends_no_event(
    refresh: ControlledRefresh,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await refresh.start_at("snapshot")

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("controlled derive failure")

    monkeypatch.setattr(SegmentCache, "derive", fail)
    with pytest.raises(RuntimeError, match="controlled"):
        await refresh.finish()
    assert _read(refresh.state) == refresh.before
    assert refresh.events.empty()

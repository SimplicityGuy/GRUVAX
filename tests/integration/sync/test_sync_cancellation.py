"""Real PostgreSQL cancellation preserves ownership and durable sync state."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from gruvax.discogsography.errors import SyncInProgress
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus
from gruvax.sync import nightly, profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
from tests.fixtures.sync import add_page_iterator


@pytest_asyncio.fixture(loop_scope="session")
async def profile(db_pool):  # type: ignore[no-untyped-def]
    profile_id, user_id = str(uuid4()), str(uuid4())
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked, last_sync_status, last_sync_at) VALUES (%s::uuid, %s, %s, FALSE, 'ok', NOW() - INTERVAL '2 days')",
            (profile_id, f"Cancel probe {profile_id}", encrypt_pat("dscg_synthetic_cancel")),
        )
        await conn.execute(
            "INSERT INTO gruvax.profile_collection (profile_id, release_id, folder_id, title, label, catalog_number) VALUES (%s::uuid, 991103, 1, 'Old synthetic probe', 'Probe', 'P1')",
            (profile_id,),
        )
        await conn.commit()
    try:
        yield SimpleNamespace(id=profile_id, user_id=user_id)
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (profile_id,))
            await conn.commit()


def _page(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "has_more": False,
        "releases": [
            {
                "id": "991104",
                "title": "New synthetic probe",
                "artist": "Probe",
                "label": "Probe",
                "catalog_number": "P2",
                "year": 2000,
                "folder_id": 1,
            }
        ],
    }


def _state(pool):  # type: ignore[no-untyped-def]
    return SimpleNamespace(
        db_pool=pool,
        boundary_cache_registry={},
        snapshot_registry={},
        segment_cache_registry={},
        event_bus_registry={},
    )


async def _metadata(pool, profile_id):  # type: ignore[no-untyped-def]
    async with pool.connection() as conn:
        return await (
            await conn.execute(
                "SELECT last_sync_status, last_sync_error, last_sync_at, app_token_revoked, app_token_encrypted, deleted_at FROM gruvax.profiles WHERE id = %s::uuid",
                (profile_id,),
            )
        ).fetchone()


async def _collection(pool, profile_id):  # type: ignore[no-untyped-def]
    async with pool.connection() as conn:
        return await (
            await conn.execute(
                "SELECT release_id, title FROM gruvax.profile_collection WHERE profile_id = %s::uuid ORDER BY release_id",
                (profile_id,),
            )
        ).fetchall()


async def _assert_lock_released(pool, profile_id):  # type: ignore[no-untyped-def]
    async with pool.connection() as conn:
        key = profile_sync._lock_key(profile_id)
        acquired = await (await conn.execute("SELECT pg_try_advisory_lock(%s)", (key,))).fetchone()
        try:
            assert acquired == (True,)
        finally:
            await conn.execute("SELECT pg_advisory_unlock(%s)", (key,))


async def _cancel(task):  # type: ignore[no-untyped-def]
    task.cancel()
    [outcome] = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)
    assert isinstance(outcome, asyncio.CancelledError)


@pytest_asyncio.fixture(loop_scope="session")
async def blocked_sync(profile, db_pool, monkeypatch):  # type: ignore[no-untyped-def]
    fetching, finish = asyncio.Event(), asyncio.Event()

    async def page():  # type: ignore[no-untyped-def]
        fetching.set()
        await finish.wait()
        return _page(profile.user_id)

    upstream = SimpleNamespace(first_page=page, aclose=AsyncMock())
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: add_page_iterator(upstream))
    state = _state(db_pool)
    task = asyncio.create_task(profile_sync.sync_profile(profile.id, state))
    try:
        await asyncio.wait_for(fetching.wait(), timeout=5)
        yield SimpleNamespace(task=task, client=upstream, finish=finish, state=state)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio(loop_scope="session")
async def test_cancel_before_swap_is_retryable_and_next_real_sweep_selects_profile(
    profile, db_pool, blocked_sync, monkeypatch
):  # type: ignore[no-untyped-def]
    before = await _metadata(db_pool, profile.id)
    assert before is not None and before[0] == "in_progress"
    await _cancel(blocked_sync.task)
    after = await _metadata(db_pool, profile.id)
    assert after is not None and after[:2] == ("failed", None)
    assert after[2:] == before[2:], "cancellation must preserve completion time and token state"
    assert await _collection(db_pool, profile.id) == [(991103, "Old synthetic probe")]
    await _assert_lock_released(db_pool, profile.id)
    blocked_sync.client.aclose.assert_awaited_once()

    retry_client = SimpleNamespace(
        first_page=AsyncMock(return_value=_page(profile.user_id)), aclose=AsyncMock()
    )
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: add_page_iterator(retry_client))
    selected = []
    real_sync = nightly.sync_profile

    async def record_selected(profile_id, state):  # type: ignore[no-untyped-def]
        selected.append(profile_id)
        if profile_id == profile.id:
            return await real_sync(profile_id, state)

    monkeypatch.setattr(nightly, "sync_profile", record_selected)
    await nightly._startup_catchup_sweep(db_pool, blocked_sync.state, "24h")
    assert profile.id in selected
    assert await _collection(db_pool, profile.id) == [(991104, "New synthetic probe")]
    completed = await _metadata(db_pool, profile.id)
    assert completed is not None and completed[0] == "ok"
    retry_client.first_page.assert_awaited_once()
    retry_client.aclose.assert_awaited_once()


@pytest.mark.asyncio(loop_scope="session")
async def test_cancel_during_postcommit_cache_load_preserves_success(profile, db_pool, monkeypatch):  # type: ignore[no-untyped-def]
    loading = asyncio.Event()

    async def blocked_load(*_, **__):  # type: ignore[no-untyped-def]
        loading.set()
        await asyncio.Event().wait()

    cache = BoundaryCache()
    cache._load_rows([BoundaryRow(1, 0, 0, "Probe", "P1", False)])
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({"probe": [RecordRow(991103, "Probe", "P1")]})
    segments = SegmentCache()
    segments.derive(cache, snapshot, {})
    before_rows = list(cache.get_boundaries())
    before_records = list(snapshot.get_label_records("Probe"))
    before_bin = segments.get_bin(1, 0, 0)
    assert before_rows and before_records and before_bin is not None
    # Sync prepares a fresh off-registry instance. Block its actual read,
    # rather than the old live cache's method, to cancel AFTER SQL commit.
    monkeypatch.setattr(BoundaryCache, "load", blocked_load)
    bus = EventBus()
    queue = bus.subscribe()
    state = _state(db_pool)
    state.boundary_cache_registry[profile.id] = cache
    state.snapshot_registry[profile.id] = snapshot
    state.segment_cache_registry[profile.id] = segments
    state.event_bus_registry[profile.id] = bus
    upstream = SimpleNamespace(
        first_page=AsyncMock(return_value=_page(profile.user_id)), aclose=AsyncMock()
    )
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: add_page_iterator(upstream))
    task = asyncio.create_task(profile_sync.sync_profile(profile.id, state))
    try:
        await asyncio.wait_for(loading.wait(), timeout=5)
        committed = await _metadata(db_pool, profile.id)
        assert committed is not None and committed[0] == "ok"
        await _cancel(task)
        assert await _metadata(db_pool, profile.id) == committed
        assert await _collection(db_pool, profile.id) == [(991104, "New synthetic probe")]
        assert cache.get_boundaries() == before_rows
        assert snapshot.get_label_records("Probe") == before_records
        assert segments.get_bin(1, 0, 0) == before_bin
        assert queue.empty(), "cancelled cache refresh must not publish completion"
        upstream.aclose.assert_awaited_once()
        await _assert_lock_released(db_pool, profile.id)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        bus.unsubscribe(queue)


@pytest.mark.asyncio(loop_scope="session")
async def test_deleted_profile_is_untouched_by_cancellation(profile, db_pool, blocked_sync):  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET deleted_at = NOW() WHERE id = %s::uuid", (profile.id,)
        )
        await conn.commit()
    await nightly._purge_profile_collection(db_pool, profile.id)
    deleted = await _metadata(db_pool, profile.id)
    assert deleted is not None and deleted[-1] is not None
    await _cancel(blocked_sync.task)
    assert await _metadata(db_pool, profile.id) == deleted
    assert await _collection(db_pool, profile.id) == []
    assert not blocked_sync.state.snapshot_registry
    blocked_sync.client.aclose.assert_awaited_once()
    await _assert_lock_released(db_pool, profile.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_contended_manual_sync_does_not_finalize_live_owner(profile, db_pool, blocked_sync):  # type: ignore[no-untyped-def]
    owner_state = await _metadata(db_pool, profile.id)
    assert owner_state is not None and owner_state[0] == "in_progress"
    with pytest.raises(SyncInProgress, match="already running"):
        await profile_sync.sync_profile(profile.id, blocked_sync.state)
    assert await _metadata(db_pool, profile.id) == owner_state
    assert blocked_sync.client.aclose.await_count == 0
    blocked_sync.finish.set()
    result = await asyncio.wait_for(blocked_sync.task, timeout=5)
    assert result["status"] == "ok"
    assert await _collection(db_pool, profile.id) == [(991104, "New synthetic probe")]
    blocked_sync.client.aclose.assert_awaited_once()
    await _assert_lock_released(db_pool, profile.id)


@pytest.mark.asyncio(loop_scope="session")
async def test_status_write_failure_does_not_replace_cancellation(
    profile, db_pool, blocked_sync, monkeypatch, caplog
):  # type: ignore[no-untyped-def]
    from psycopg import OperationalError

    monkeypatch.setattr(
        profile_sync,
        "_record_cancellation",
        AsyncMock(side_effect=OperationalError("synthetic status-write failure")),
    )
    await _cancel(blocked_sync.task)
    blocked_sync.client.aclose.assert_awaited_once()
    await _assert_lock_released(db_pool, profile.id)
    assert "cancelled status could not be finalized" in caplog.text
    assert await _collection(db_pool, profile.id) == [(991103, "Old synthetic probe")]

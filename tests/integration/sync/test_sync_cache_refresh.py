"""Integration tests for sync_profile inline cache refresh — Plan 01-03 Task 2.

Behaviours under test (4 tests, mirrors PLAN.md Task 2):
  1. CollectionSnapshot reloaded after sync (snapshot record count grows from 0 to N).
  2. SegmentCache derived after snapshot reload (bins non-empty when boundaries
     match labels in the seed).
  3. BoundaryCache.load is awaited as part of the refresh sequence.
  4. Cache refresh failure does NOT undo the committed swap (DB has the new
     rows even though refresh raised; sync_profile re-raises).

D-14 / gruvax-58b: load fresh boundary and snapshot objects, derive a fresh
segment generation, then publish their values into stable instances without an await seam.

"""

from __future__ import annotations

import os
import types
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax._internal.fake_discogsography import create_fake_app
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
from gruvax.sync.profile_sync import sync_profile


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


DEFAULT_UUID = "00000000-0000-0000-0000-000000000001"
TEST_PAT = "dscg_test_pat_LEAK_DETECTOR_secret_aaa"


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_release(release_id: int, *, label: str = "Blue Note") -> dict:
    return {
        "id": str(release_id),
        "title": f"Title {release_id}",
        "year": 1960 + (release_id % 50),
        "catalog_number": f"BLP-{release_id:04d}",
        "artist": f"Artist {release_id}",
        "label": label,
        "folder_id": 1,
    }


def _conninfo() -> str:
    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


async def _seed_default_profile(db_pool) -> None:  # type: ignore[no-untyped-def]
    cipher = encrypt_pat(TEST_PAT)
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles "
            "SET app_token_encrypted = %s, app_token_revoked = FALSE, "
            "    last_sync_status = NULL, last_sync_error = NULL, "
            "    last_sync_at = NULL, last_sync_item_count = NULL, "
            "    discogsography_user_id = NULL "
            "WHERE id = %s::uuid",
            (cipher, DEFAULT_UUID),
        )
        await conn.commit()


async def _truncate_profile_collection(db_pool) -> None:  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        await conn.commit()


def _client_factory_for(app):  # type: ignore[no-untyped-def]
    def _factory(base_url: str, pat: str) -> DiscogsographyClient:
        client = DiscogsographyClient.__new__(DiscogsographyClient)
        client._client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://fake",
            headers={"Authorization": f"Bearer {pat}"},
        )
        return client

    return _factory


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _ensure_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        from cryptography.fernet import Fernet

        monkeypatch.setenv("GRUVAX_SECRET_KEY", Fernet.generate_key().decode())


@pytest_asyncio.fixture(loop_scope="session")
async def clean_db(db_pool) -> AsyncIterator[None]:  # type: ignore[no-untyped-def]
    await _seed_default_profile(db_pool)
    await _truncate_profile_collection(db_pool)
    yield


# ── tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_snapshot_reloaded_after_sync(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 1: CollectionSnapshot reloads from profile_collection post-sync.

    The actual scoped SQL snapshot read sees the committed collection. The
    previously returned record lists stay unchanged for captured readers.
    """
    snapshot = CollectionSnapshot()
    boundary = BoundaryCache()
    segment = SegmentCache()

    # Track that .load is called by wrapping the real method.
    load_calls: list[int] = []
    real_load = CollectionSnapshot.load

    async def _instrumented_load(self, pool, **kwargs):  # type: ignore[no-untyped-def]
        load_calls.append(1)
        await real_load(self, pool, **kwargs)

    monkeypatch.setattr(CollectionSnapshot, "load", _instrumented_load)

    seed = [_make_release(i) for i in range(1, 11)]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    from gruvax.events.bus import EventBus

    app_state = types.SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={DEFAULT_UUID: boundary},
        snapshot_registry={DEFAULT_UUID: snapshot},
        segment_cache_registry={DEFAULT_UUID: segment},
        event_bus_registry={DEFAULT_UUID: EventBus()},
    )

    # boundary_cache.load is real but the table is empty in this test → bins[]
    result = await sync_profile(DEFAULT_UUID, app_state)
    assert result["status"] == "ok"
    assert load_calls == [1], "snapshot.load was not awaited during cache refresh"
    refreshed = app_state.snapshot_registry[DEFAULT_UUID]
    assert refreshed is snapshot
    assert len(refreshed.get_label_records("Blue Note")) == 10
    assert len(snapshot.get_label_records("Blue Note")) == 10


@pytest.mark.asyncio(loop_scope="session")
async def test_segment_cache_derive_called_with_fresh_snapshot(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 2: segment_cache.derive is invoked with the refreshed snapshot."""
    snapshot = CollectionSnapshot()
    boundary = BoundaryCache()
    segment = SegmentCache()

    derive_calls: list[tuple] = []
    real_derive = SegmentCache.derive

    def _instrumented_derive(self, cache, snap, overrides):  # type: ignore[no-untyped-def]
        derive_calls.append((id(cache), id(snap), len(snap.get_label_records("Blue Note"))))
        real_derive(self, cache, snap, overrides)

    monkeypatch.setattr(SegmentCache, "derive", _instrumented_derive)

    seed = [_make_release(1)]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    from gruvax.events.bus import EventBus

    app_state = types.SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={DEFAULT_UUID: boundary},
        snapshot_registry={DEFAULT_UUID: snapshot},
        segment_cache_registry={DEFAULT_UUID: segment},
        event_bus_registry={DEFAULT_UUID: EventBus()},
    )

    await sync_profile(DEFAULT_UUID, app_state)
    assert len(derive_calls) == 1
    cache_id, snap_id, size = derive_calls[0]
    assert cache_id != id(app_state.boundary_cache_registry[DEFAULT_UUID]) == id(boundary)
    assert snap_id != id(app_state.snapshot_registry[DEFAULT_UUID]) == id(snapshot)
    assert size == 1
    assert app_state.segment_cache_registry[DEFAULT_UUID] is segment


@pytest.mark.asyncio(loop_scope="session")
async def test_boundary_cache_load_called(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 3: boundary_cache.load is awaited during _refresh_profile_caches."""
    from gruvax.events.bus import EventBus

    snapshot = CollectionSnapshot()
    boundary = BoundaryCache()
    segment = SegmentCache()

    loads = []
    real_load = BoundaryCache.load

    async def tracked_load(self, pool, **kwargs):  # type: ignore[no-untyped-def]
        loads.append(kwargs["profile_id"])
        await real_load(self, pool, **kwargs)

    monkeypatch.setattr(BoundaryCache, "load", tracked_load)

    seed = [_make_release(1)]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    app_state = types.SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={DEFAULT_UUID: boundary},
        snapshot_registry={DEFAULT_UUID: snapshot},
        segment_cache_registry={DEFAULT_UUID: segment},
        event_bus_registry={DEFAULT_UUID: EventBus()},
    )

    await sync_profile(DEFAULT_UUID, app_state)
    assert loads == [DEFAULT_UUID]
    assert app_state.boundary_cache_registry[DEFAULT_UUID] is boundary


@pytest.mark.asyncio(loop_scope="session")
async def test_cache_refresh_failure_preserves_committed_swap(  # type: ignore[no-untyped-def]
    db_pool, clean_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 4: if cache refresh raises, the DB swap is STILL committed."""
    from gruvax.events.bus import EventBus

    boundary = AsyncMock()
    boundary.invalidate = lambda: None
    boundary.load = AsyncMock(side_effect=RuntimeError("cache refresh blew up"))
    monkeypatch.setattr(
        BoundaryCache, "load", AsyncMock(side_effect=RuntimeError("cache refresh blew up"))
    )
    boundary.overrides = {}
    snapshot = AsyncMock()
    snapshot.invalidate = lambda: None
    segment = AsyncMock()
    segment.derive = lambda *a, **kw: None

    seed = [_make_release(i) for i in range(1, 51)]
    app = create_fake_app(seed=seed)
    monkeypatch.setattr(profile_sync, "_make_client", _client_factory_for(app))

    app_state = types.SimpleNamespace(
        db_pool=db_pool,
        boundary_cache_registry={DEFAULT_UUID: boundary},
        snapshot_registry={DEFAULT_UUID: snapshot},
        segment_cache_registry={DEFAULT_UUID: segment},
        event_bus_registry={DEFAULT_UUID: EventBus()},
    )

    with pytest.raises(RuntimeError, match="cache refresh blew up"):
        await sync_profile(DEFAULT_UUID, app_state)

    # The swap MUST have committed before the cache refresh ran.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (DEFAULT_UUID,),
        )
        assert (await cur.fetchone())[0] == 50

        await cur.execute(
            "SELECT last_sync_status, last_sync_item_count "
            "FROM gruvax.profiles WHERE id = %s::uuid",
            (DEFAULT_UUID,),
        )
        row = await cur.fetchone()
        # status='ok' was set inside the swap TX BEFORE refresh ran.
        assert row == ("ok", 50)

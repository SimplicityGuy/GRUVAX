"""Controlled real-DB interleavings for sync versus profile deletion."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.api.deps import require_admin
from gruvax.app import create_app
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat


@pytest_asyncio.fixture(loop_scope="session")
async def retention_client(db_pool):  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO gruvax.profiles (display_name, app_token_encrypted, app_token_revoked) VALUES ('Retention probe', %s, FALSE) RETURNING id::text",
                (encrypt_pat("dscg_synthetic_retention"),),
            )
        ).fetchone()
        await conn.commit()
    assert row is not None
    profile_id = row[0]
    app = create_app()
    app.dependency_overrides[require_admin] = lambda: {"role": "admin"}
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client,
    ):
        yield client, app, profile_id
    async with db_pool.connection() as conn:
        await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (profile_id,))
        await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_and_purge_during_fetch_cannot_resurrect_collection(
    db_pool, retention_client, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    client, app, profile_id = retention_client
    async with db_pool.connection() as conn:
        before = await (
            await conn.execute(
                "SELECT last_sync_at FROM gruvax.profiles WHERE id = %s::uuid", (profile_id,)
            )
        ).fetchone()
    assert before is not None
    fetching, finish_fetch = asyncio.Event(), asyncio.Event()
    bus = app.state.event_bus_registry[profile_id]
    publish = AsyncMock(wraps=bus.publish)
    monkeypatch.setattr(bus, "publish", publish)

    async def first_page():  # type: ignore[no-untyped-def]
        fetching.set()
        await finish_fetch.wait()
        return {
            "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "has_more": False,
            "releases": [
                {
                    "id": "991001",
                    "title": "Synthetic retention probe",
                    "artist": "Probe",
                    "label": "Probe",
                    "catalog_number": "P1",
                    "year": 2000,
                    "folder_id": 1,
                }
            ],
        }

    upstream = SimpleNamespace(first_page=first_page, aclose=AsyncMock())
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: upstream)
    task = asyncio.create_task(profile_sync.sync_profile(profile_id, app.state))
    try:
        await asyncio.wait_for(fetching.wait(), timeout=5)
        deleted = await client.delete(f"/api/admin/profiles/{profile_id}")
        assert deleted.status_code == 200, deleted.text
    finally:
        finish_fetch.set()
    [outcome] = await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), timeout=5)

    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
                (profile_id,),
            )
        ).fetchone()
        assert row == (0,), "sync must not restore collection rows after the DELETE's purge"
        status = await (
            await conn.execute(
                "SELECT deleted_at IS NOT NULL, last_sync_status, last_sync_at FROM gruvax.profiles WHERE id = %s::uuid",
                (profile_id,),
            )
        ).fetchone()
    assert status is not None and status[0] is True
    assert status[1] != "ok" and status[2] == before[0]
    assert isinstance(outcome, RuntimeError) and "deleted" in str(outcome).lower()
    assert profile_id not in app.state.snapshot_registry
    publish.assert_not_awaited()
    upstream.aclose.assert_awaited_once()


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_waits_for_protected_swap_then_purges(
    db_pool, retention_client, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    client, app, profile_id = retention_client
    locked, finish_swap = asyncio.Event(), asyncio.Event()
    original_lock = profile_sync._lock_profile_for_swap

    async def hold_profile_lock(conn, target):  # type: ignore[no-untyped-def]
        initial = await original_lock(conn, target)
        locked.set()
        await finish_swap.wait()
        return initial

    monkeypatch.setattr(profile_sync, "_lock_profile_for_swap", hold_profile_lock)
    upstream = SimpleNamespace(
        first_page=AsyncMock(
            return_value={
                "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "has_more": False,
                "releases": [
                    {
                        "id": "991002",
                        "title": "Protected swap probe",
                        "artist": "Probe",
                        "label": "Probe",
                        "catalog_number": "P2",
                        "year": 2000,
                        "folder_id": 1,
                    }
                ],
            }
        ),
        aclose=AsyncMock(),
    )
    monkeypatch.setattr(profile_sync, "_make_client", lambda *_: upstream)
    sync_task = asyncio.create_task(profile_sync.sync_profile(profile_id, app.state))
    delete_task = None
    try:
        await asyncio.wait_for(locked.wait(), timeout=5)
        delete_task = asyncio.create_task(client.delete(f"/api/admin/profiles/{profile_id}"))
        blocked = False
        for _ in range(100):
            async with db_pool.connection() as conn:
                row = await (
                    await conn.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE wait_event_type = 'Lock' AND query LIKE %s)",
                        ("UPDATE gruvax.profiles SET deleted_at%",),
                    )
                ).fetchone()
            if row == (True,):
                blocked = True
                break
            await asyncio.sleep(0.01)
        assert blocked, "the actual profile DELETE must wait on the swap's row lock"
        assert not delete_task.done()
    finally:
        finish_swap.set()
        tasks = [sync_task] + ([delete_task] if delete_task is not None else [])
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
    assert len(results) == 2
    assert not isinstance(results[0], BaseException), results[0]
    assert results[0]["status"] == "ok"
    assert results[1].status_code == 200, results[1].text
    async with db_pool.connection() as conn:
        count = await (
            await conn.execute(
                "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
                (profile_id,),
            )
        ).fetchone()
    assert count == (0,), "the later DELETE must purge the committed collection"
    assert profile_id not in app.state.snapshot_registry
    upstream.aclose.assert_awaited_once()

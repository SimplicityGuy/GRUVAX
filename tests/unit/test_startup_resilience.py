"""Startup failures must serve degraded health and release owned resources."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from psycopg.errors import UndefinedTable
import pytest

import gruvax.app as app_module


@pytest.fixture
def startup(monkeypatch):  # type: ignore[no-untyped-def]
    pool, conn, cursor = MagicMock(), MagicMock(), AsyncMock()
    pool.open, pool.close = AsyncMock(), AsyncMock()
    pool.connection.return_value.__aenter__.return_value = conn
    conn.cursor.return_value.__aenter__.return_value = cursor
    cursor.fetchall.return_value = []
    monkeypatch.setattr(app_module, "create_pool", lambda **_: pool)

    async def connect(app):  # type: ignore[no-untyped-def]
        app.state.mqtt = None
        app.state.mqtt_ok = False

    monkeypatch.setattr(app_module, "connect_mqtt", connect)
    disconnect = AsyncMock()
    monkeypatch.setattr(app_module, "disconnect_mqtt", disconnect)
    monkeypatch.setattr(app_module, "_read_sync_cadence", AsyncMock(return_value="off"))
    monkeypatch.setattr(app_module, "_startup_catchup_sweep", AsyncMock())
    monkeypatch.setattr(app_module, "_startup_purge_sweep", AsyncMock())

    async def parked(*_):  # type: ignore[no-untyped-def]
        await asyncio.Event().wait()

    monkeypatch.setattr(app_module, "_sync_loop", parked)
    return pool, cursor, disconnect


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["profiles", "cadence", "catchup", "purge"])
async def test_database_bootstrap_failure_serves_degraded_and_closes(
    startup, monkeypatch, fault: str
) -> None:  # type: ignore[no-untyped-def]
    pool, cursor, disconnect = startup
    if fault == "profiles":

        async def fail_profiles(query, *_):  # type: ignore[no-untyped-def]
            if "SELECT id FROM gruvax.profiles" in query:
                raise RuntimeError("synthetic missing profiles table")

        cursor.execute.side_effect = fail_profiles
    else:
        target = {
            "cadence": "_read_sync_cadence",
            "catchup": "_startup_catchup_sweep",
            "purge": "_startup_purge_sweep",
        }[fault]
        monkeypatch.setattr(
            app_module,
            target,
            AsyncMock(side_effect=UndefinedTable("synthetic missing startup table")),
        )
    app = app_module.create_app()
    async with (
        app_module.lifespan(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        if fault == "catchup":
            await asyncio.sleep(0)
        health = await client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["status"] == "degraded"
        assert app.state.profile_collection_ready is False
        response = await client.get("/api/search", params={"q": "synthetic"})
        assert response.status_code == 503
    pool.close.assert_awaited_once()
    disconnect.assert_awaited_once()
    assert not app.state.background_tasks


@pytest.mark.asyncio
async def test_unexpected_pre_yield_failure_always_closes_pool(startup, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    pool, _, disconnect = startup
    monkeypatch.setattr(
        app_module, "connect_mqtt", AsyncMock(side_effect=RuntimeError("synthetic connect failure"))
    )
    with pytest.raises(RuntimeError, match="synthetic connect failure"):
        async with app_module.lifespan(FastAPI()):
            raise AssertionError("the failed initializer must never yield")
    pool.close.assert_awaited_once()
    disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_shutdown_cancels_and_gathers_tasks_before_pool_close(startup) -> None:  # type: ignore[no-untyped-def]
    pool, _, _ = startup
    order = []

    async def worker():  # type: ignore[no-untyped-def]
        try:
            await asyncio.Event().wait()
        finally:
            order.append("task stopped")

    async def closed():  # type: ignore[no-untyped-def]
        order.append("pool closed")

    pool.close.side_effect = closed
    app = FastAPI()
    async with app_module.lifespan(app):
        task = asyncio.create_task(worker())
        app.state.background_tasks.add(task)
        await asyncio.sleep(0)
    assert task.done()
    assert order == ["task stopped", "pool closed"]


@pytest.mark.asyncio
async def test_slow_catchup_does_not_block_health_and_precedes_nightly(startup, monkeypatch):  # type: ignore[no-untyped-def]
    begun, finish, nightly = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def catchup(*_):  # type: ignore[no-untyped-def]
        begun.set()
        await finish.wait()

    async def loop(*_):  # type: ignore[no-untyped-def]
        nightly.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(app_module, "_startup_catchup_sweep", catchup)
    monkeypatch.setattr(app_module, "_sync_loop", loop)
    app = app_module.create_app()
    async with (
        asyncio.timeout(2),
        app_module.lifespan(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
    ):
        await begun.wait()
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert not nightly.is_set(), "nightly work must wait for catch-up, not readiness"
        finish.set()
        await nightly.wait()
    assert not app.state.background_tasks


@pytest.mark.asyncio
async def test_catchup_network_failure_keeps_loaded_database_available(startup, monkeypatch):  # type: ignore[no-untyped-def]
    pool, _, _ = startup
    nightly = asyncio.Event()

    async def loop(*_):  # type: ignore[no-untyped-def]
        nightly.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(
        app_module,
        "_startup_catchup_sweep",
        AsyncMock(side_effect=RuntimeError("synthetic upstream failure")),
    )
    monkeypatch.setattr(app_module, "_sync_loop", loop)
    app = app_module.create_app()
    async with app_module.lifespan(app):
        await asyncio.wait_for(nightly.wait(), timeout=2)
        assert app.state.db_pool is pool
        assert app.state.db_ok is True
        assert app.state.profile_collection_ready is True


@pytest.mark.asyncio
async def test_profile_bus_ready_for_subscribers_without_startup_replay(startup, monkeypatch):  # type: ignore[no-untyped-def]
    _pool, cursor, _disconnect = startup
    profile_id = "00000000-0000-0000-0000-000000000001"
    cursor.fetchall.return_value = [(profile_id,)]
    monkeypatch.setattr(app_module.BoundaryCache, "load", AsyncMock())
    monkeypatch.setattr(app_module.CollectionSnapshot, "load", AsyncMock())
    monkeypatch.setattr(app_module, "load_settings_cache", AsyncMock(return_value={}))
    app = app_module.create_app()
    async with app_module.lifespan(app):
        bus = app.state.event_bus_registry[profile_id]
        assert app.state.event_bus is bus
        queue = bus.subscribe()
        try:
            assert queue.empty()
            await bus.publish("boundary_changed", {"probe": "ready"})
            event = queue.get_nowait()
            assert event.name == "boundary_changed"
            assert event.data == {"probe": "ready"}
        finally:
            bus.unsubscribe(queue)

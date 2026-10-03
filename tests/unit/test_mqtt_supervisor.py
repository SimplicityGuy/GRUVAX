"""MQTT ownership, truthful publish failures and bounded startup retries."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import aiomqtt
from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.app import create_app
from gruvax.mqtt import client as mqtt_client
from gruvax.mqtt.publishers import safe_publish
from gruvax.settings import settings
from tests.unit.test_illuminate_endpoint import VALID_BODY


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_publish_failure_reports_only_its_live_client(
    monkeypatch: pytest.MonkeyPatch, stale: bool
) -> None:
    monkeypatch.setattr(settings, "MQTT_PORT", 1883)
    app = create_app()
    failed = asyncio.Event()
    client = mqtt_client._HealthReportingClient(app, failed)
    replacement = object()
    app.state.mqtt = replacement if stale else client
    app.state.mqtt_ok = True
    monkeypatch.setattr(
        aiomqtt.Client, "publish", AsyncMock(side_effect=TimeoutError("owned publish failure"))
    )
    assert await safe_publish(client, "owned/proof", b"proof") is False
    assert failed.is_set()
    assert app.state.mqtt_ok is stale
    assert app.state.mqtt is (replacement if stale else None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get("/api/health")).json()["mqtt"] == ("ok" if stale else "degraded")
        if not stale:
            response = await http.post("/api/illuminate", json=VALID_BODY)
            assert response.json()["accepted"] is False
            assert response.json()["published"] is False


@pytest.mark.asyncio
async def test_known_dead_client_is_not_accepted() -> None:
    app = create_app()
    app.state.mqtt = AsyncMock()
    app.state.mqtt_ok = False
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        response = await http.post("/api/illuminate", json=VALID_BODY)
    assert response.json()["accepted"] is False
    assert response.json()["published"] is False
    app.state.mqtt.publish.assert_not_awaited()


class OwnedClient:
    def __init__(self, phase: str | None) -> None:
        self.phase = phase
        self.exits = 0
        self.stopped = asyncio.Event()

    async def __aenter__(self) -> OwnedClient:
        if self.phase == "enter":
            raise aiomqtt.MqttError("synthetic unavailable broker")
        return self

    async def __aexit__(self, *_args: Any) -> None:
        self.exits += 1
        self.stopped.set()

    async def publish(self, *_args: Any, **_kwargs: Any) -> None:
        if self.phase == "hello":
            raise aiomqtt.MqttError("synthetic hello failure")

    async def monitor_messages(self) -> None:
        await self.stopped.wait()

    @property
    def messages(self) -> Any:
        async def stream():  # type: ignore[no-untyped-def]
            await self.stopped.wait()
            yield None

        return stream()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["constructor", "enter", "hello"])
async def test_initial_failure_retries_fresh_context_and_shutdown_awaits(
    monkeypatch: pytest.MonkeyPatch, phase: str
) -> None:
    app = create_app()
    clients: list[OwnedClient] = []
    attempts = 0

    def factory(*_args: Any) -> OwnedClient:
        nonlocal attempts
        attempts += 1
        if attempts == 1 and phase == "constructor":
            raise ValueError("synthetic bad port")
        result = OwnedClient(phase if attempts == 1 else None)
        clients.append(result)
        return result

    monkeypatch.setattr(mqtt_client, "_HealthReportingClient", factory)
    monkeypatch.setattr(mqtt_client, "_RECONNECT_SECONDS", 0.01)
    try:
        await mqtt_client.connect_mqtt(app)
        assert app.state.mqtt is None
        assert app.state.mqtt_ok is False
        async with asyncio.timeout(1):
            while not app.state.mqtt_ok:
                await asyncio.sleep(0.001)
        assert attempts == 2
        assert app.state.mqtt is clients[-1]
        if phase == "hello":
            assert clients[0].exits == 1
    finally:
        supervisor = app.state.mqtt_task
        await mqtt_client.disconnect_mqtt(app)
    assert supervisor.done()
    assert clients[-1].exits == 1
    assert clients[-1].stopped.is_set()
    assert app.state.mqtt_task is None
    assert app.state.mqtt is None
    assert app.state.mqtt_ok is False

"""The supervisor alone consumes native messages; diagnostic queues are scoped."""

from __future__ import annotations

import asyncio
from itertools import product
import logging
from typing import Any
from unittest.mock import AsyncMock

import aiomqtt
import pytest

from gruvax.app import create_app
from gruvax.mqtt.client import _HealthReportingClient, diagnostic_messages
from gruvax.mqtt.publishers import run_diagnostic
from gruvax.settings import settings
from tests.unit.test_led_admin_endpoints import SETTINGS_CACHE, _make_pool


def controlled_client(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_HealthReportingClient, asyncio.Queue[Any]]:
    incoming: asyncio.Queue[Any] = asyncio.Queue()

    async def stream():  # type: ignore[no-untyped-def]
        while True:
            message = await incoming.get()
            if isinstance(message, Exception):
                raise message
            yield message

    monkeypatch.setattr(settings, "MQTT_PORT", 1883)
    monkeypatch.setattr(aiomqtt.Client, "messages", property(lambda _self: stream()))
    return _HealthReportingClient(create_app(), asyncio.Event()), incoming


def message(topic: str, payload: bytes = b"proof") -> aiomqtt.Message:
    return aiomqtt.Message(topic, payload, 1, False, 1, None)


async def drain_input(incoming: asyncio.Queue[Any]) -> None:
    async with asyncio.timeout(1):
        while not incoming.empty():
            await asyncio.sleep(0)


def received_statuses(caplog: pytest.LogCaptureFixture) -> set[str]:
    return {
        record.args[1].decode()
        for record in caplog.records
        if "LED status from firmware" in record.message
    }


@pytest.mark.asyncio
async def test_diagnostic_preserves_full_five_unit_status_burst(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Five 4x4 units can reply to all five diagnostic states before draining."""
    client, incoming = controlled_client(monkeypatch)
    monkeypatch.setattr(settings, "MQTT_TOPIC_PREFIX", "owned")
    client.publish = AsyncMock()  # type: ignore[method-assign]
    client.unsubscribe = AsyncMock()  # type: ignore[method-assign]
    expected = {
        f"BURST_{unit}_{row}_{col}_{state}"
        for unit, row, col, state in product(range(5), range(4), range(4), range(5))
    }

    async def subscribe(_topic: str, **_kwargs: Any) -> None:
        for payload in expected:
            await incoming.put(message("owned/status/reply", payload.encode()))
        await drain_input(incoming)

    client.subscribe = subscribe  # type: ignore[method-assign]
    caplog.set_level(logging.INFO, logger="gruvax.mqtt.publishers")
    monitor = asyncio.create_task(client.monitor_messages())
    diagnostic = asyncio.create_task(
        run_diagnostic(
            client,
            _make_pool([(unit, 4, 4) for unit in range(5)]),
            {**SETTINGS_CACHE, "led_diagnostic.inter_cube_ms": "0"},
            "burst",
        )
    )
    try:
        async with asyncio.timeout(2):
            while len(received_statuses(caplog)) < 400:
                await asyncio.sleep(0)
        assert received_statuses(caplog) == expected
        assert not any("dropping status reply" in record.message for record in caplog.records)
    finally:
        diagnostic.cancel()
        await asyncio.gather(diagnostic, return_exceptions=True)
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)
    assert client._status_queue is None
    assert client._gruvax_diag_active is False  # type: ignore[attr-defined]
    client.unsubscribe.assert_awaited_once_with("owned/status/#")


@pytest.mark.asyncio
async def test_scoped_forwarding_has_no_idle_backlog_and_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, incoming = controlled_client(monkeypatch)
    monitor = asyncio.create_task(client.monitor_messages())
    try:
        await incoming.put(message("owned/status/before"))
        await drain_input(incoming)
        async with diagnostic_messages(client, "owned") as captured:
            queue = client._status_queue
            assert queue is not None and queue.empty()
            await incoming.put(message("other/status/ignored"))
            await incoming.put(message("owned/status/reply", b"actual forwarded reply"))
            async with asyncio.timeout(1):
                reply = await anext(captured)
            assert str(reply.topic) == "owned/status/reply"
            assert reply.payload == b"actual forwarded reply"
            with pytest.raises(RuntimeError, match="already owned"):
                async with diagnostic_messages(client, "owned"):
                    pytest.fail("second capture must not be admitted")
            for index in range(100):
                await incoming.put(message(f"owned/status/{index}"))
            await drain_input(incoming)
            assert queue.qsize() == 64
        assert client._status_queue is None
        assert client._status_prefix is None
    finally:
        monitor.cancel()
        await asyncio.gather(monitor, return_exceptions=True)


@pytest.mark.asyncio
async def test_disconnect_wakes_capture_and_disposes_waiters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, incoming = controlled_client(monkeypatch)
    monitor = asyncio.create_task(client.monitor_messages())
    try:
        async with diagnostic_messages(client, "owned") as captured:
            await incoming.put(aiomqtt.MqttError("controlled disconnect"))
            with pytest.raises(aiomqtt.MqttError, match="Disconnected during diagnostic"):
                async with asyncio.timeout(1):
                    await anext(captured)
        assert client._status_queue is None
    finally:
        monitor.cancel()
        result = await asyncio.gather(monitor, return_exceptions=True)
    assert isinstance(result[0], aiomqtt.MqttError)


@pytest.mark.asyncio
async def test_cancel_capture_disposes_waiters_without_stopping_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, incoming = controlled_client(monkeypatch)
    monitor = asyncio.create_task(client.monitor_messages())
    ready = asyncio.Event()

    async def capture() -> None:
        async with diagnostic_messages(client, "owned") as captured:
            ready.set()
            await anext(captured)

    diagnostic = asyncio.create_task(capture())
    try:
        await ready.wait()
        diagnostic.cancel()
        await asyncio.gather(diagnostic, return_exceptions=True)
        assert client._status_queue is None
        assert monitor.done() is False
        async with diagnostic_messages(client, "owned") as captured:
            await incoming.put(message("owned/status/new"))
            async with asyncio.timeout(1):
                assert str((await anext(captured)).topic) == "owned/status/new"
    finally:
        diagnostic.cancel()
        monitor.cancel()
        await asyncio.gather(diagnostic, monitor, return_exceptions=True)

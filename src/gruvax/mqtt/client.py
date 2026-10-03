"""Supervised MQTT 5 connection; broker failures remain noncritical to the API.

Every connection attempt owns a fresh client context. Health follows the live
connection and publish failures, and shutdown awaits the supervisor's cleanup.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
from typing import TYPE_CHECKING, Any

import aiomqtt
from aiomqtt import ProtocolVersion

from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from fastapi import FastAPI

logger = logging.getLogger(__name__)
_HELLO_TOPIC = "gruvax/v1/server/hello"
_HELLO_ALIVE = b'{"alive": true}'
_HELLO_DEAD = b'{"alive": false}'
_RECONNECT_SECONDS = 1.0


class _HealthReportingClient(aiomqtt.Client):
    """Report every failed publish, including failures swallowed by safe_publish."""

    def __init__(self, app: FastAPI, failed: asyncio.Event) -> None:
        self._app = app
        self._failed = failed
        self._status_queue: asyncio.Queue[aiomqtt.Message] | None = None
        self._status_prefix: str | None = None
        super().__init__(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            identifier="gruvax-api",
            protocol=ProtocolVersion.V5,
            will=aiomqtt.Will(topic=_HELLO_TOPIC, payload=_HELLO_DEAD, retain=True),
            keepalive=30,
            timeout=1.0,
        )

    async def publish(self, *args: Any, **kwargs: Any) -> None:
        try:
            await super().publish(*args, **kwargs)
        except Exception:
            # Old highlight tasks may still hold a prior client after reconnect.
            # A stale client's failure must never mark the new connection dead.
            if getattr(self._app.state, "mqtt", None) is self:
                self._app.state.mqtt = None
                self._app.state.mqtt_ok = False
            self._failed.set()
            raise

    async def monitor_messages(self) -> None:
        """Own the native public stream, forwarding only an active status capture."""
        try:
            async for message in super().messages:
                queue = self._status_queue
                prefix = self._status_prefix
                if queue is None or prefix is None or not str(message.topic).startswith(prefix):
                    continue
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    logger.warning("MQTT diagnostic capture full; dropping status reply")
        finally:
            self._failed.set()

    async def _next_status(self, queue: asyncio.Queue[aiomqtt.Message]) -> aiomqtt.Message:
        message = asyncio.create_task(queue.get())
        disconnected = asyncio.create_task(self._failed.wait())
        try:
            done, _ = await asyncio.wait(
                (message, disconnected), return_when=asyncio.FIRST_COMPLETED
            )
            if disconnected in done:
                raise aiomqtt.MqttError("Disconnected during diagnostic capture")
            return message.result()
        finally:
            message.cancel()
            disconnected.cancel()
            await asyncio.gather(message, disconnected, return_exceptions=True)

    async def _status_messages(
        self, queue: asyncio.Queue[aiomqtt.Message]
    ) -> AsyncGenerator[aiomqtt.Message]:
        while True:
            yield await self._next_status(queue)

    @asynccontextmanager
    async def capture_status(
        self, prefix: str, capacity: int = 64
    ) -> AsyncIterator[AsyncIterator[aiomqtt.Message]]:
        """Bounded per-diagnostic queue, disposed on completion or cancellation."""
        if self._status_queue is not None:
            raise RuntimeError("MQTT diagnostic status capture already owned")
        queue: asyncio.Queue[aiomqtt.Message] = asyncio.Queue(maxsize=max(1, capacity))
        self._status_queue = queue
        self._status_prefix = prefix + "/status/"
        messages = self._status_messages(queue)
        try:
            yield messages
        finally:
            await messages.aclose()
            self._status_queue = None
            self._status_prefix = None


@asynccontextmanager
async def diagnostic_messages(
    client: aiomqtt.Client, prefix: str, capacity: int = 64
) -> AsyncIterator[AsyncIterator[aiomqtt.Message]]:
    """Use supervisor forwarding, preserving plain-client diagnostic support."""
    if isinstance(client, _HealthReportingClient):
        async with client.capture_status(prefix, capacity) as messages:
            yield messages
    else:
        yield client.messages


async def _watch_connection(client: _HealthReportingClient, failed: asyncio.Event) -> None:
    watchers = [
        asyncio.create_task(client.monitor_messages()),
        asyncio.create_task(failed.wait()),
    ]
    try:
        done, _ = await asyncio.wait(watchers, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in watchers:
            task.cancel()
        await asyncio.gather(*watchers, return_exceptions=True)


async def _supervise_mqtt(app: FastAPI, first_attempt: asyncio.Event) -> None:
    while True:
        failed = asyncio.Event()
        try:
            async with _HealthReportingClient(app, failed) as client:
                await client.publish(_HELLO_TOPIC, payload=_HELLO_ALIVE, retain=True)
                app.state.mqtt = client
                app.state.mqtt_ok = True
                first_attempt.set()
                logger.info("MQTT connected to %s:%d", settings.MQTT_HOST, settings.MQTT_PORT)
                await _watch_connection(client, failed)
        except Exception as exc:
            logger.warning("MQTT unavailable; API continues in degraded mode; retrying: %s", exc)
        finally:
            app.state.mqtt = None
            app.state.mqtt_ok = False
            first_attempt.set()
        await asyncio.sleep(_RECONNECT_SECONDS)


async def connect_mqtt(app: FastAPI) -> None:
    """Complete one bounded best-effort attempt, then supervise reconnection.

    The first attempt retains the startup availability contract: callers can
    immediately use a healthy client when the broker is available. An unavailable
    broker never prevents startup; retries run in the app-owned background task.
    """
    app.state.mqtt = None
    app.state.mqtt_ok = False
    first_attempt = asyncio.Event()
    app.state.mqtt_task = asyncio.create_task(_supervise_mqtt(app, first_attempt))
    await first_attempt.wait()


async def disconnect_mqtt(app: FastAPI) -> None:
    """Cancel and await the supervisor, including the owned client context exit."""
    task: asyncio.Task[None] | None = getattr(app.state, "mqtt_task", None)
    if task is not None:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        app.state.mqtt_task = None
    app.state.mqtt = None
    app.state.mqtt_ok = False

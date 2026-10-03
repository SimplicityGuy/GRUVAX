"""Controlled overlapping publishes preserve highlight and reset ordering."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from gruvax.mqtt.lifecycle import (
    HighlightRegistry,
    cancel_and_revert_all,
    illuminate_with_lifecycle,
)
from tests.unit.test_led_lifecycle import SETTINGS_CACHE


class GatedPublisher:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.retained: dict[str, dict[str, Any]] = {}
        self.order: list[tuple[str, int]] = []

    async def publish(self, topic: str, payload: bytes, **kwargs: Any) -> None:
        data = json.loads(payload)
        if topic.endswith("/illuminate/1/0/0"):
            self.entered.set()
            await self.release.wait()
        self.order.append((topic, data["brightness"]))
        if kwargs.get("retain"):
            self.retained[topic] = data


def body(col: int) -> SimpleNamespace:
    return SimpleNamespace(
        release_id=col + 1,
        primary_cube={"unit_id": 1, "row": 0, "col": col},
        label_span=[],
        sub_cube_interval=None,
    )


async def never_revert(_seconds: float) -> None:
    await asyncio.Event().wait()


async def cleanup(registry: HighlightRegistry) -> None:
    tasks = [entry.task for entry in registry.values()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("retain", [False, True])
async def test_concurrent_illuminates_preserve_mode(retain: bool) -> None:
    registry = HighlightRegistry()
    client = GatedPublisher()
    settings = {**SETTINGS_CACHE, "led_highlight.retain_mode": retain}
    a = asyncio.create_task(
        illuminate_with_lifecycle(registry, client, settings, body(0), sleep=never_revert)
    )
    await client.entered.wait()
    b = asyncio.create_task(
        illuminate_with_lifecycle(registry, client, settings, body(1), sleep=never_revert)
    )
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        client.release.set()
        await asyncio.gather(a, b)
        assert len(registry) == (2 if retain else 1)
        states = {
            topic.rsplit("/", 1)[-1]: value["brightness"]
            for topic, value in client.retained.items()
        }
        assert states == {"0": 255 if retain else 40, "1": 255}
        if not retain:
            ambient_a = next(
                i
                for i, (topic, value) in enumerate(client.order)
                if topic.endswith("/state/1/0/0") and value == 40
            )
            highlight_b = next(
                i
                for i, (topic, value) in enumerate(client.order)
                if topic.endswith("/illuminate/1/0/1") and value == 255
            )
            assert ambient_a < highlight_b
    finally:
        client.release.set()
        await asyncio.gather(a, b, return_exceptions=True)
        await cleanup(registry)


@pytest.mark.asyncio
async def test_reset_waits_for_inflight_highlight_then_reverts() -> None:
    registry = HighlightRegistry()
    client = GatedPublisher()
    illuminate = asyncio.create_task(
        illuminate_with_lifecycle(registry, client, SETTINGS_CACHE, body(0), sleep=never_revert)
    )
    await client.entered.wait()
    reset = asyncio.create_task(cancel_and_revert_all(registry, client, SETTINGS_CACHE))
    try:
        for _ in range(10):
            await asyncio.sleep(0)
        client.release.set()
        await asyncio.gather(illuminate, reset)
        assert len(registry) == 0
        assert next(iter(client.retained.values()))["brightness"] == 40
    finally:
        client.release.set()
        await asyncio.gather(illuminate, reset, return_exceptions=True)
        await cleanup(registry)

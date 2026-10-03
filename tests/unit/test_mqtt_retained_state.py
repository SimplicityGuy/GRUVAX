"""Retained boot state preserves the primary tier when it also belongs to span."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from pydantic import TypeAdapter, ValidationError
import pytest

from gruvax.mqtt import publishers
from gruvax.mqtt.schemas import StatePayload
from gruvax.settings import settings
from tests.unit.test_mqtt_publishers import SETTINGS_CACHE


class RetainedBroker:
    def __init__(self) -> None:
        self.retained: dict[str, dict[str, Any]] = {}
        self.writes: dict[str, int] = {}
        self.commands: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, topic: str, payload: bytes, **kwargs: Any) -> None:
        value = json.loads(payload)
        if kwargs.get("retain"):
            self.retained[topic] = value
            self.writes[topic] = self.writes.get(topic, 0) + 1
            assert kwargs["qos"] == 1
            assert kwargs["properties"].MessageExpiryInterval > 0
        else:
            self.commands.append((topic, value))


@pytest.mark.asyncio
@pytest.mark.parametrize("primary_first", [True, False])
async def test_primary_retained_state_wins_and_span_command_is_unchanged(
    primary_first: bool,
) -> None:
    primary = {"unit_id": 0, "row": 2, "col": 3}
    companion = {"unit_id": 0, "row": 2, "col": 4}
    span = [primary, companion, companion] if primary_first else [companion, companion, primary]
    body = SimpleNamespace(primary_cube=primary, label_span=span, sub_cube_interval=None)
    broker = RetainedBroker()
    await publishers.fan_out_illuminate(broker, body, SETTINGS_CACHE)
    main = broker.retained[f"{settings.MQTT_TOPIC_PREFIX}/state/0/2/3"]
    other = broker.retained[f"{settings.MQTT_TOPIC_PREFIX}/state/0/2/4"]
    adapter = TypeAdapter(StatePayload)
    assert adapter.validate_python(main).schema_ == "gruvax.illuminate.v1"
    assert adapter.validate_python(other).schema_ == "gruvax.span.v1"
    with pytest.raises(ValidationError):
        adapter.validate_python({**main, "schema": "unknown.schema"})
    assert main["schema"] == "gruvax.illuminate.v1"
    assert main["color"] == {"r": 255, "g": 215, "b": 0}
    assert main["brightness"] == 255
    assert (main["unit_id"], main["row"], main["col"]) == (0, 2, 3)
    assert other["schema"] == "gruvax.span.v1"
    assert other["brightness"] == 128
    assert all(count == 1 for count in broker.writes.values())
    span_commands = [value for topic, value in broker.commands if "/span/" in topic]
    assert len(span_commands) == 1
    assert span_commands[0]["cubes"] == span

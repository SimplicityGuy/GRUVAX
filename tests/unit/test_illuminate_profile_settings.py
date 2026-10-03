"""Public illumination resolves configured profile colors and default fallback."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from httpx import ASGITransport, AsyncClient
import pytest

from gruvax.app import create_app
from tests.unit.test_illuminate_endpoint import VALID_BODY
from tests.unit.test_mqtt_publishers import SETTINGS_CACHE


PROFILE = "aabbccdd-1234-5678-9012-123456789012"


class PublishedColors:
    def __init__(self) -> None:
        self.primary: list[dict[str, Any]] = []

    async def publish(self, topic: str, payload: bytes, **_kwargs: Any) -> None:
        if "/illuminate/" in topic:
            self.primary.append(json.loads(payload))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("supplied", "expected"),
    [
        (PROFILE, {"r": 255, "g": 0, "b": 0}),
        (PROFILE.upper(), {"r": 255, "g": 0, "b": 0}),
        (PROFILE.replace("-", ""), {"r": 255, "g": 0, "b": 0}),
        ("urn:uuid:" + PROFILE, {"r": 255, "g": 0, "b": 0}),
        (None, {"r": 18, "g": 52, "b": 86}),
        ("ffffffff-ffff-ffff-ffff-ffffffffffff", {"r": 18, "g": 52, "b": 86}),
        ("unknown-profile", {"r": 18, "g": 52, "b": 86}),
    ],
)
async def test_profile_and_default_colors_reach_real_publisher(
    supplied: str | None, expected: dict[str, int]
) -> None:
    broker = PublishedColors()
    app = create_app()
    app.state.mqtt = broker
    app.state.mqtt_ok = True
    app.state.background_tasks = set()
    app.state.settings_cache = {**SETTINGS_CACHE, "led_color.position": '"#123456"'}
    app.state.settings_cache_registry = {
        PROFILE: {**SETTINGS_CACHE, "led_color.position": '"#FF0000"'}
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/illuminate",
            params={} if supplied is None else {"profile_id": supplied},
            json=VALID_BODY,
        )
    assert response.status_code == 200, response.text
    assert response.json()["accepted"] is True
    await asyncio.gather(*tuple(app.state.background_tasks))
    assert len(broker.primary) == 1
    assert broker.primary[0]["color"] == expected
    assert broker.primary[0]["brightness"] == 255

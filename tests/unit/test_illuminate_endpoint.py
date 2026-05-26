"""Unit tests for the POST /api/illuminate endpoint.

Nyquist Wave-0 scaffold — Phase 6: LED Contract over MQTT (Hardware Stubbed)

Covers: LED-09, D-01, SC5 — fire-and-forget publish, degraded mode (client=None),
input validation (422 on malformed body).

Tests use httpx AsyncClient against the app with app.state.mqtt as an AsyncMock
(and a separate case with app.state.mqtt=None).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ── shared body fixture ───────────────────────────────────────────────────────

VALID_BODY: dict[str, Any] = {
    "release_id": 42,
    "primary_cube": {"unit_id": 0, "row": 2, "col": 3},
    "label_span": [
        {"unit_id": 0, "row": 2, "col": 3},
        {"unit_id": 0, "row": 2, "col": 4},
    ],
    "sub_cube_interval": {
        "start": 0.2,
        "end": 0.7,
        "crosses_boundary": False,
        "next_cube": None,
    },
    "confidence": 0.75,
}


def _make_app_with_mqtt(mqtt_client: Any | None) -> Any:
    """Create a fresh app instance with the given MQTT client state.

    Uses the factory to get a clean app; overrides app.state after construction
    so the lifespan doesn't try to connect a real broker in tests.
    """
    from gruvax.app import create_app
    from gruvax.mqtt.lifecycle import HighlightRegistry

    app = create_app()
    # Patch lifespan-managed state directly so tests don't need a real DB/broker.
    app.state.mqtt = mqtt_client
    app.state.mqtt_ok = mqtt_client is not None
    # WR-06: ASGITransport does NOT run the lifespan, so highlight_registry is never
    # created automatically.  Set it explicitly so the illuminate endpoint takes the
    # REAL illuminate_with_lifecycle path (the shipping path) rather than the
    # registry-None fallback branch — otherwise test_fan_out_count covers only the
    # fallback, not the primary lifecycle code.
    app.state.highlight_registry = HighlightRegistry()
    app.state.settings_cache = {
        "led_color.position": '"#FFD700"',
        "led_color.label_span": '"#7C3AED"',
        "led_brightness.active": "255",
        "led_brightness.span": "128",
        "led_brightness.ambient": "40",
        "led_transition.position_style": '"pulse"',
        "led_transition.position_ms": "800",
        "led_transition.span_style": '"fade"',
        "led_transition.span_ms": "500",
    }
    return app


# ── LED-09: fan_out scheduled, 200 {"published": true} ──────────────────────


@pytest.mark.asyncio
async def test_fan_out_count() -> None:
    """POST /api/illuminate returns 200 {"published": true} with a connected broker.

    LED-09: The publisher fan-out must be scheduled via asyncio.create_task.
    """
    mqtt_mock = AsyncMock()
    mqtt_mock.publish = AsyncMock(return_value=None)

    app = _make_app_with_mqtt(mqtt_mock)

    # Patch asyncio.create_task to verify it's called (fire-and-forget)
    with patch("gruvax.api.illuminate.asyncio.create_task") as mock_create_task:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            res = await client.post("/api/illuminate", json=VALID_BODY)

    assert res.status_code == 200, f"Expected 200; got {res.status_code}: {res.text}"
    body = res.json()
    assert body["published"] is True, f"Expected published=true; got {body}"
    assert "accepted_at" in body
    mock_create_task.assert_called_once()


# ── D-01: degraded mode — returns 200 {"published": false} ───────────────────


@pytest.mark.asyncio
async def test_illuminate_degraded() -> None:
    """POST /api/illuminate with no broker returns 200 {"published": false} (D-01 / SC5).

    A broker hiccup or missing MQTT connection must never return an error.
    """
    app = _make_app_with_mqtt(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/illuminate", json=VALID_BODY)

    assert res.status_code == 200, f"Expected 200; got {res.status_code}: {res.text}"
    body = res.json()
    assert body["published"] is False, f"Expected published=false in degraded mode; got {body}"
    assert "accepted_at" in body


# ── input validation: malformed body → 422 ───────────────────────────────────


@pytest.mark.asyncio
async def test_illuminate_invalid_body() -> None:
    """POST /api/illuminate with missing required fields returns 422 (input validation).

    T-06-01: Pydantic IlluminateRequest validation must reject malformed bodies.
    """
    app = _make_app_with_mqtt(None)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Missing 'release_id' and other required fields
        res = await client.post("/api/illuminate", json={"bad_field": "value"})

    assert res.status_code == 422, (
        f"Expected 422 for malformed body; got {res.status_code}: {res.text}"
    )

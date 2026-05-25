"""Unit tests for MQTT publisher fan-out logic.

Nyquist Wave-0 scaffold — Phase 6: LED Contract over MQTT (Hardware Stubbed)

Covers: LED-01, LED-02, LED-03, LED-08, LED-09, LED-10 + D-01/D-02/D-12/D-13/D-14/D-24

Tests use a stub aiomqtt client (AsyncMock exposing publish, subscribe, unsubscribe
and recorded calls) to assert publish args without a live broker.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gruvax.mqtt import publishers, topics

# ── shared fixture helpers ────────────────────────────────────────────────────

TEST_PREFIX = "gruvax/v1/dev/leds"

SETTINGS_CACHE: dict[str, Any] = {
    "led_color.position": '"#FFD700"',
    "led_color.label_span": '"#7C3AED"',
    "led_brightness.active": "255",
    "led_brightness.span": "128",
    "led_brightness.ambient": "40",
    "led_transition.position_style": '"pulse"',
    "led_transition.position_ms": "800",
    "led_transition.span_style": '"fade"',
    "led_transition.span_ms": "500",
    "led_highlight.active_ttl_seconds": "180",
    "led_highlight.retain_mode": "false",
    "led_highlight.retain_ttl_seconds": "900",
}

LOCATE_RESULT_BODY = MagicMock(
    release_id=42,
    primary_cube={"unit_id": 0, "row": 2, "col": 3},
    label_span=[
        {"unit_id": 0, "row": 2, "col": 3},
        {"unit_id": 0, "row": 2, "col": 4},
    ],
    sub_cube_interval={"start": 0.2, "end": 0.7, "crosses_boundary": False, "next_cube": None},
    confidence=0.75,
)

LOCATE_RESULT_NO_SUB = MagicMock(
    release_id=7,
    primary_cube={"unit_id": 1, "row": 0, "col": 1},
    label_span=[{"unit_id": 1, "row": 0, "col": 1}],
    sub_cube_interval=None,
    confidence=0.30,
)


def _make_mqtt_client() -> AsyncMock:
    """Return an AsyncMock that mimics aiomqtt.Client.publish()."""
    client = AsyncMock()
    client.publish = AsyncMock(return_value=None)
    return client


# ── LED-01: illuminate payload shape ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_illuminate_payload() -> None:
    """fan_out_illuminate publishes IlluminatePayload-shaped JSON to illuminate/{u}/{r}/{c}.

    LED-01: payload has `schema` == "gruvax.illuminate.v1", color {r,g,b},
    brightness int, transition {style, duration_ms}.
    """
    client = _make_mqtt_client()
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    # Find the illuminate topic publish call
    illuminate_t = topics.illuminate_topic(TEST_PREFIX, 0, 2, 3)
    publish_calls = client.publish.call_args_list
    illuminate_call = next(
        (c for c in publish_calls if c[0][0] == illuminate_t),
        None,
    )
    assert illuminate_call is not None, (
        f"Expected a publish to {illuminate_t!r}; calls={[c[0][0] for c in publish_calls]}"
    )
    # Decode payload
    payload: dict[str, Any] = json.loads(illuminate_call[0][1])
    assert payload["schema"] == "gruvax.illuminate.v1", f"Wrong schema: {payload['schema']}"
    color = payload["color"]
    assert {"r", "g", "b"} <= set(color), f"color missing r/g/b: {color}"
    assert isinstance(payload["brightness"], int)
    transition = payload["transition"]
    assert "style" in transition and "duration_ms" in transition, (
        f"transition keys missing: {transition}"
    )


# ── LED-02: span payload lists all label_span cubes ──────────────────────────


@pytest.mark.asyncio
async def test_span_payload() -> None:
    """fan_out_illuminate publishes SpanPayload listing ALL label_span cubes.

    LED-02: span/{change_id} payload cubes list == [{unit_id,row,col},...] for
    every entry in label_span.
    """
    client = _make_mqtt_client()
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    publish_calls = client.publish.call_args_list
    span_call = next(
        (c for c in publish_calls if "/span/" in c[0][0] and TEST_PREFIX in c[0][0]),
        None,
    )
    assert span_call is not None, "Expected a publish to a span/... topic"
    payload = json.loads(span_call[0][1])
    assert payload["schema"] == "gruvax.span.v1"
    cubes = payload["cubes"]
    assert len(cubes) == 2, f"Expected 2 span cubes; got {cubes}"
    for cube in cubes:
        assert "unit_id" in cube and "row" in cube and "col" in cube


# ── LED-03: sub payload with normalized interval ──────────────────────────────


@pytest.mark.asyncio
async def test_sub_payload() -> None:
    """fan_out_illuminate publishes SubIntervalPayload to sub/{u}/{r}/{c}.

    LED-03: payload has interval {start,end} normalized 0..1,
    schema == "gruvax.sub_interval.v1".
    """
    client = _make_mqtt_client()
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    sub_t = topics.sub_topic(TEST_PREFIX, 0, 2, 3)
    publish_calls = client.publish.call_args_list
    sub_call = next(
        (c for c in publish_calls if c[0][0] == sub_t),
        None,
    )
    assert sub_call is not None, f"Expected publish to {sub_t!r}"
    payload = json.loads(sub_call[0][1])
    assert payload["schema"] == "gruvax.sub_interval.v1"
    interval = payload["interval"]
    assert 0.0 <= interval["start"] <= 1.0
    assert 0.0 <= interval["end"] <= 1.0


# ── LED-09: exact three command topics + retained state/* ────────────────────


@pytest.mark.asyncio
async def test_fan_out_topics() -> None:
    """One fan_out_illuminate call publishes exactly three command topics and retained state/*.

    LED-09, D-02, D-13: command topics (illuminate, span, sub) are non-retained;
    state/* topics are retain=True.
    """
    client = _make_mqtt_client()
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    calls = client.publish.call_args_list
    published_topics = [c[0][0] for c in calls]

    illuminate_t = topics.illuminate_topic(TEST_PREFIX, 0, 2, 3)
    span_ts = [t for t in published_topics if f"{TEST_PREFIX}/span/" in t]
    sub_t = topics.sub_topic(TEST_PREFIX, 0, 2, 3)
    state_ts = [t for t in published_topics if f"{TEST_PREFIX}/state/" in t]

    assert illuminate_t in published_topics, f"illuminate topic missing; got {published_topics}"
    assert len(span_ts) >= 1, "span topic missing"
    assert sub_t in published_topics, f"sub topic missing; got {published_topics}"
    assert len(state_ts) >= 1, "state/* retained topic missing"

    # Verify non-retained for command topics
    for c in calls:
        t = c[0][0]
        kwargs = c[1] if len(c) > 1 else {}
        if any(t == cmd for cmd in [illuminate_t, sub_t, *span_ts]):
            retain = kwargs.get("retain", False)
            assert retain is False, f"Command topic {t!r} must not be retained; got retain={retain}"


# ── D-12: state/* carries MessageExpiryInterval via paho Properties ──────────


@pytest.mark.asyncio
async def test_state_retained_has_expiry() -> None:
    """state/* publish calls carry paho Properties with MessageExpiryInterval == MQTT_STATE_EXPIRY_SECONDS.

    D-12: retained messages must have a TTL; no-expiry is rejected.
    qos=1, retain=True.
    """
    from paho.mqtt.properties import Properties

    client = _make_mqtt_client()
    expiry = 3600
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", expiry),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    calls = client.publish.call_args_list
    state_calls = [c for c in calls if f"{TEST_PREFIX}/state/" in c[0][0]]
    assert len(state_calls) >= 1, "No state/* publish calls found"
    for sc in state_calls:
        kwargs = sc[1] if len(sc) > 1 else {}
        assert kwargs.get("qos") == 1, f"state/* must use qos=1; got {kwargs.get('qos')}"
        assert kwargs.get("retain") is True, f"state/* must be retained; got {kwargs.get('retain')}"
        props = kwargs.get("properties")
        assert isinstance(props, Properties), (
            f"state/* must carry paho Properties; got {type(props)}"
        )
        assert props.MessageExpiryInterval == expiry, (
            f"MessageExpiryInterval {props.MessageExpiryInterval} != {expiry}"
        )


# ── D-14: topic prefix is applied ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_topic_prefix() -> None:
    """Topics are prefixed with MQTT_TOPIC_PREFIX (D-14 dev/prod isolation)."""
    client = _make_mqtt_client()
    custom_prefix = "gruvax/v1/dev/leds"
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", custom_prefix),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    for c in client.publish.call_args_list:
        topic = c[0][0]
        assert topic.startswith(custom_prefix), (
            f"Topic {topic!r} does not start with prefix {custom_prefix!r}"
        )

    illuminate_t = f"{custom_prefix}/illuminate/0/2/3"
    all_topics = [c[0][0] for c in client.publish.call_args_list]
    assert illuminate_t in all_topics, f"{illuminate_t!r} not in {all_topics}"


# ── D-24: span brightness uses led_brightness.span (NOT led_brightness.ambient) ─


@pytest.mark.asyncio
async def test_span_brightness_uses_span_tier() -> None:
    """SpanPayload brightness is clamped to led_brightness.span (NOT led_brightness.ambient).

    D-24: the span tier is led_brightness.span (~30-50%); the active/position tier
    is led_brightness.active (100%). The ambient tier is the idle baseline only.
    """
    cache = dict(SETTINGS_CACHE)
    cache["led_brightness.span"] = "90"  # label-span tier
    cache["led_brightness.active"] = "200"  # position tier
    cache["led_brightness.ambient"] = "10"  # idle baseline — NOT used for span

    client = _make_mqtt_client()
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, cache)

    calls = client.publish.call_args_list
    span_call = next(
        (c for c in calls if f"{TEST_PREFIX}/span/" in c[0][0]),
        None,
    )
    assert span_call is not None
    span_payload = json.loads(span_call[0][1])
    span_brightness = span_payload["brightness"]

    illuminate_t = topics.illuminate_topic(TEST_PREFIX, 0, 2, 3)
    ill_call = next((c for c in calls if c[0][0] == illuminate_t), None)
    assert ill_call is not None
    ill_payload = json.loads(ill_call[0][1])
    ill_brightness = ill_payload["brightness"]

    # span brightness must be from span tier (clamped to 90), NOT ambient (10)
    assert span_brightness == 90, f"Expected span brightness=90 (span tier); got {span_brightness}"
    # position brightness must be from active tier (clamped to 200)
    assert ill_brightness == 200, (
        f"Expected illuminate brightness=200 (active tier); got {ill_brightness}"
    )


# ── D-01: degraded mode — fan_out_illuminate with client=None does not raise ──


@pytest.mark.asyncio
async def test_degraded_mode_no_raise() -> None:
    """fan_out_illuminate with client=None returns without raising (D-01 / SC5).

    A broker hiccup must never block or crash the illuminate path.
    """
    # Should complete silently without any exception
    await publishers.fan_out_illuminate(None, LOCATE_RESULT_BODY, SETTINGS_CACHE)


# ── anti-pattern guard: command topics must NOT be retained ──────────────────


@pytest.mark.asyncio
async def test_no_retain_on_commands() -> None:
    """illuminate/span/sub publish calls must have retain=False (D-13 anti-pattern guard).

    Retained command topics create stale-command-replay footguns on firmware restart.
    Only state/* is retained.
    """
    client = _make_mqtt_client()
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publishers.fan_out_illuminate(client, LOCATE_RESULT_BODY, SETTINGS_CACHE)

    for c in client.publish.call_args_list:
        topic: str = c[0][0]
        kwargs = c[1] if len(c) > 1 else {}
        if any(segment in topic for segment in ["/illuminate/", "/span/", "/sub/"]):
            retain = kwargs.get("retain", False)
            assert retain is False, (
                f"Command topic {topic!r} must have retain=False; got retain={retain}"
            )

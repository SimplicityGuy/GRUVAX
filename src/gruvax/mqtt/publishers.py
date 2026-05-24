"""MQTT publish helpers for GRUVAX LED control.

Phase 6: LED Contract over MQTT (Hardware Stubbed)

Public surface:
  - hex_to_rgb(hex_str)          — parse "#RRGGBB" to (r, g, b) ints
  - clamp_brightness(val, ceil)  — clamp brightness to [0, ceil] (D-24)
  - _make_expiry_props(seconds)  — paho Properties with MessageExpiryInterval (D-12)
  - safe_publish(client, ...)    — fire-and-forget wrapper with native timeout (D-01)
  - fan_out_illuminate(client, body, settings_cache)  — main fan-out (LED-01/02/03)
  - publish_ambient(client, pool, settings_cache, *, cubes=None)  — ambient baseline (LED-11/D-20)

Degraded-mode posture (D-01, SC5):
  If ``client`` is None (broker unreachable at startup), every function that
  takes a client short-circuits with a warning log and returns immediately.
  A broker hiccup NEVER raises into the /api/illuminate request path.

Brightness-tier naming (D-24 — LOCKED):
  led_brightness.span    → label-span tier (~30-50%) — NOT the idle key
  led_brightness.active  → position/primary tier (100%)
  The idle/resting baseline key is NOT used by fan_out_illuminate for span brightness.

Topic architecture (ARCHITECTURE.md §"MQTT Topic Design" — LOCKED):
  Command topics (illuminate/span/sub): QoS 0, retain=False
  State topics (state/*): QoS 1, retain=True, message_expiry_interval (D-12)
  All topics prefixed by settings.MQTT_TOPIC_PREFIX (D-14)
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aiomqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.properties import Properties

from gruvax.mqtt import topics
from gruvax.mqtt.schemas import (
    IlluminatePayload,
    RGBColor,
    SpanPayload,
    SubIntervalPayload,
    TransitionSpec,
)
from gruvax.settings import settings

logger = logging.getLogger(__name__)


# ── Colour helpers ────────────────────────────────────────────────────────────


def hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    """Parse a "#RRGGBB" (or "RRGGBB") hex string to an (r, g, b) int tuple.

    T-06-02 mitigation: invalid hex raises ValueError at publish time rather
    than silently producing wrong colours.  Callers should pass validated values
    from settings_cache (seeded with known-good defaults).
    """
    h = hex_str.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# ── Brightness clamping ───────────────────────────────────────────────────────


def clamp_brightness(val: int, ceiling: int) -> int:
    """Clamp *val* to the range [0, ceiling].

    Satisfies the brightness invariant tested by test_led_brightness.py:
    the result is always within [0, ceiling] regardless of input.

    *ceiling* must itself be in [0, 255]; values outside that range are
    also clamped so callers from settings_cache never produce over-bright output.
    """
    safe_ceiling = max(0, min(ceiling, 255))
    return min(max(0, val), safe_ceiling)


# ── MQTT 5 Properties ─────────────────────────────────────────────────────────


def _make_expiry_props(seconds: int) -> Properties:
    """Build a paho MQTT 5 Properties object with MessageExpiryInterval.

    D-12: retained state/* publishes MUST carry an expiry so a broker restart
    does not permanently replay arbitrarily old LED state to firmware.
    "No expiry" (seconds=0 or omitted) is rejected by the retained-message
    hygiene rules in PITFALLS.md §3.
    """
    props = Properties(PacketTypes.PUBLISH)  # type: ignore[no-untyped-call]
    props.MessageExpiryInterval = seconds
    return props


# ── Low-level safe publish ────────────────────────────────────────────────────


async def safe_publish(
    client: aiomqtt.Client,
    topic: str,
    payload: bytes,
    *,
    qos: int = 0,
    retain: bool = False,
    properties: Properties | None = None,
    timeout: float = 0.25,
) -> bool:
    """Non-blocking publish that swallows timeout and MQTT errors.

    Uses the native aiomqtt ``timeout`` parameter instead of
    ``asyncio.wait_for`` (Pitfall F: do NOT use asyncio.wait_for around
    client.publish — aiomqtt 2.5.x has its own timeout kwarg).

    Returns True on success, False on any exception.  Callers may log or
    ignore the return value; the illuminate path is always fire-and-forget.

    D-01 / SC5: a broker hiccup must never block the API request path.
    """
    try:
        await client.publish(
            topic,
            payload,
            qos=qos,
            retain=retain,
            properties=properties,
            timeout=timeout,
        )
        return True
    except Exception as exc:
        logger.warning("MQTT publish failed (topic=%s): %s", topic, exc)
        return False


# ── Main fan-out ──────────────────────────────────────────────────────────────


async def fan_out_illuminate(
    client: aiomqtt.Client | None,
    body: Any,
    settings_cache: dict[str, Any],
) -> None:
    """Publish three command topics + retained state/* for a locate result.

    Command topics are published concurrently via asyncio.gather (QoS 0,
    retain=False) in one network round-trip.  State topics follow with
    QoS 1, retain=True, and a message_expiry_interval (D-12).

    D-01: if ``client`` is None (degraded mode), returns immediately without
    raising.  The caller (/api/illuminate) fires this via asyncio.create_task.

    Brightness-tier naming contract (D-24):
      led_brightness.span   → label-span cubes (SpanPayload)
      led_brightness.active → primary/position cube (IlluminatePayload)
    """
    if client is None:
        logger.warning(
            "MQTT not connected — illuminate request acknowledged but not published (degraded mode)"
        )
        return

    prefix = settings.MQTT_TOPIC_PREFIX
    expiry_seconds = settings.MQTT_STATE_EXPIRY_SECONDS
    now_iso = datetime.now(UTC).isoformat()

    # ── Resolve presentation settings ────────────────────────────────────────
    # .get() with hardcoded defaults per Shared Pattern "Settings Cache Access"
    pos_hex: str = str(settings_cache.get("led_color.position", '"#FFD700"')).strip('"')
    span_hex: str = str(settings_cache.get("led_color.label_span", '"#7C3AED"')).strip('"')

    # D-24: label-span tier uses led_brightness.span (the idle key is separate)
    brightness_active: int = clamp_brightness(
        int(settings_cache.get("led_brightness.active", "255")), 255
    )
    brightness_span: int = clamp_brightness(
        int(settings_cache.get("led_brightness.span", "128")), 128
    )

    pos_style: str = str(settings_cache.get("led_transition.position_style", '"pulse"')).strip('"')
    pos_ms: int = int(settings_cache.get("led_transition.position_ms", "800"))
    span_style: str = str(settings_cache.get("led_transition.span_style", '"fade"')).strip('"')
    span_ms: int = int(settings_cache.get("led_transition.span_ms", "500"))

    pos_r, pos_g, pos_b = hex_to_rgb(pos_hex)
    span_r, span_g, span_b = hex_to_rgb(span_hex)

    pos_color = RGBColor(r=pos_r, g=pos_g, b=pos_b)
    span_color = RGBColor(r=span_r, g=span_g, b=span_b)

    pos_transition = TransitionSpec(style=pos_style, duration_ms=pos_ms)
    span_transition = TransitionSpec(style=span_style, duration_ms=span_ms)

    primary = body.primary_cube  # dict or None
    label_span = body.label_span or []  # list[dict]
    sub_interval = body.sub_cube_interval  # dict or None

    # ── Build payloads ────────────────────────────────────────────────────────
    change_id = str(uuid.uuid4())

    publish_tasks = []
    state_publishes: list[tuple[str, bytes]] = []

    # Illuminate (primary cube) — LED-01
    if primary is not None:
        u, r, c = primary["unit_id"], primary["row"], primary["col"]

        ill_payload = IlluminatePayload(
            issued_at=now_iso,
            unit_id=u,
            row=r,
            col=c,
            color=pos_color,
            brightness=brightness_active,
            transition=pos_transition,
        )
        ill_bytes = ill_payload.model_dump_json(by_alias=True).encode()
        publish_tasks.append(
            safe_publish(
                client,
                topics.illuminate_topic(prefix, u, r, c),
                ill_bytes,
                qos=0,
                retain=False,
                timeout=0.25,
            )
        )

        # Retained state for primary cube
        state_publishes.append((
            topics.state_topic(prefix, u, r, c),
            ill_bytes,
        ))

    # Span (all label-span cubes) — LED-02
    if label_span:
        cubes_list = [
            {"unit_id": cube["unit_id"], "row": cube["row"], "col": cube["col"]}
            for cube in label_span
        ]
        span_payload = SpanPayload(
            issued_at=now_iso,
            change_id=change_id,
            cubes=cubes_list,
            color=span_color,
            brightness=brightness_span,
            transition=span_transition,
        )
        span_bytes = span_payload.model_dump_json(by_alias=True).encode()
        publish_tasks.append(
            safe_publish(
                client,
                topics.span_topic(prefix, change_id),
                span_bytes,
                qos=0,
                retain=False,
                timeout=0.25,
            )
        )

        # Retained state for each span cube
        for cube in label_span:
            su, sr, sc = cube["unit_id"], cube["row"], cube["col"]
            state_publishes.append((
                topics.state_topic(prefix, su, sr, sc),
                span_bytes,
            ))

    # Sub-interval — LED-03
    if sub_interval is not None and primary is not None:
        u, r, c = primary["unit_id"], primary["row"], primary["col"]
        # sub_cube_interval JSON has no `cube` field — use primary_cube's unit/row/col
        interval_dict = {
            "start": float(sub_interval.get("start", 0.0)),
            "end": float(sub_interval.get("end", 1.0)),
        }
        sub_payload = SubIntervalPayload(
            issued_at=now_iso,
            unit_id=u,
            row=r,
            col=c,
            interval=interval_dict,
            color=pos_color,
            brightness=brightness_active,
        )
        sub_bytes = sub_payload.model_dump_json(by_alias=True).encode()
        publish_tasks.append(
            safe_publish(
                client,
                topics.sub_topic(prefix, u, r, c),
                sub_bytes,
                qos=0,
                retain=False,
                timeout=0.25,
            )
        )

    # ── Publish command topics concurrently ───────────────────────────────────
    if publish_tasks:
        await asyncio.gather(*publish_tasks, return_exceptions=True)

    # ── Publish retained state/* topics (QoS 1, retain=True) ─────────────────
    expiry_props = _make_expiry_props(expiry_seconds)
    for state_t, state_payload in state_publishes:
        await safe_publish(
            client,
            state_t,
            state_payload,
            qos=1,
            retain=True,
            properties=expiry_props,
            timeout=0.5,
        )


# ── Ambient baseline publisher ────────────────────────────────────────────────


async def publish_ambient(
    client: aiomqtt.Client | None,
    pool: Any,
    settings_cache: dict[str, Any],
    *,
    cubes: list[dict[str, int]] | None = None,
) -> int:
    """Publish the retained idle/ambient state/* baseline.

    LED-11 / D-20: every cube should show the idle ambient colour and brightness
    (``led_color.ambient`` / ``led_brightness.ambient``) when no highlight is active.
    This function re-publishes the retained ``state/*`` baseline for the specified
    cubes (or ALL cubes when ``cubes`` is None).

    Brightness-tier naming (D-24 — LOCKED):
      Uses ``led_brightness.ambient`` (the idle key), NOT ``led_brightness.span``
      (the label-span tier used during active highlights).

    Args:
        client:         aiomqtt.Client, or None in degraded mode.
        pool:           psycopg AsyncConnectionPool used to enumerate units when
                        ``cubes`` is None.  Ignored when ``cubes`` is provided
                        (revert path passes specific cubes, no DB needed).
        settings_cache: The gruvax.settings key/value dict.
        cubes:          Optional explicit list of ``{unit_id, row, col}`` dicts.
                        When None: enumerate all cubes via a SHORT-LIVED DB
                        connection (close before publishing — no long-held conn).
                        When provided: publish only those cubes (revert path).

    Returns:
        Number of cubes for which ambient state/* was published.

    Degraded mode: if ``client`` is None, logs a warning and returns 0.
    """
    if client is None:
        logger.warning(
            "MQTT not connected — publish_ambient skipped (degraded mode)"
        )
        return 0

    prefix = settings.MQTT_TOPIC_PREFIX
    expiry_seconds = settings.MQTT_STATE_EXPIRY_SECONDS
    now_iso = json.dumps({"ts": "ambient"})  # placeholder — not needed for state/* payload

    # ── Resolve ambient settings ──────────────────────────────────────────────
    # D-24: use led_brightness.ambient (idle key), NOT led_brightness.span.
    ambient_hex: str = str(
        settings_cache.get("led_color.ambient", '"#0051A2"')
    ).strip('"')
    ambient_brightness: int = clamp_brightness(
        int(settings_cache.get("led_brightness.ambient", 40)), 255
    )
    r, g, b = hex_to_rgb(ambient_hex)

    from datetime import UTC, datetime
    now_iso = datetime.now(UTC).isoformat()

    # Build the ambient payload dict (minimal — firmware only needs color + brightness).
    # Re-use the IlluminatePayload schema shape for state/* compatibility.
    from gruvax.mqtt.schemas import IlluminatePayload, RGBColor, TransitionSpec

    def _make_ambient_bytes(unit_id: int, row: int, col: int) -> bytes:
        payload = IlluminatePayload(
            issued_at=now_iso,
            unit_id=unit_id,
            row=row,
            col=col,
            color=RGBColor(r=r, g=g, b=b),
            brightness=ambient_brightness,
            transition=TransitionSpec(style="instant", duration_ms=0),
        )
        return payload.model_dump_json(by_alias=True).encode()

    # ── Resolve cubes list ────────────────────────────────────────────────────
    cube_list: list[dict[str, int]]
    if cubes is not None:
        cube_list = cubes
    else:
        # Enumerate all cubes from the DB (short-lived connection, closed before publishing).
        if pool is None:
            logger.warning("publish_ambient: pool is None and no cubes provided; cannot enumerate")
            return 0
        sql = "SELECT id, rows, cols FROM gruvax.units ORDER BY ordering"
        cube_list = []
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql)
            unit_rows = await cur.fetchall()
        # Connection closed — no long-held conn during the publish loop.
        for (unit_id, row_count, col_count) in unit_rows:
            for row in range(row_count):
                for col in range(col_count):
                    cube_list.append({"unit_id": unit_id, "row": row, "col": col})

    if not cube_list:
        logger.warning("publish_ambient: no cubes to publish")
        return 0

    # ── Publish concurrently ──────────────────────────────────────────────────
    expiry_props = _make_expiry_props(expiry_seconds)

    async def _publish_one(unit_id: int, row: int, col: int) -> None:
        state_t = topics.state_topic(prefix, unit_id, row, col)
        payload_bytes = _make_ambient_bytes(unit_id, row, col)
        await safe_publish(
            client,
            state_t,
            payload_bytes,
            qos=1,
            retain=True,
            properties=expiry_props,
            timeout=0.5,
        )

    publish_coros = [
        _publish_one(cube["unit_id"], cube["row"], cube["col"])
        for cube in cube_list
    ]
    results = await asyncio.gather(*publish_coros, return_exceptions=True)

    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        logger.warning(
            "publish_ambient: %d of %d publishes failed: %s",
            len(errors),
            len(cube_list),
            errors[0],
        )

    count = len(cube_list) - len(errors)
    logger.info("publish_ambient: published ambient state/* for %d cubes", count)
    return count

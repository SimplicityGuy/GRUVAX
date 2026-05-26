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
from datetime import UTC, datetime
import json
import logging
from typing import TYPE_CHECKING, Any
import uuid

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


if TYPE_CHECKING:
    import aiomqtt


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
    # CR-02: clamp to the 8-bit hardware ceiling (255), NOT the tier default (128).
    # The admin slider exposes span brightness up to 255; using 128 as the ceiling
    # silently discarded any admin value above 128.  The default value remains 128.
    brightness_span: int = clamp_brightness(
        int(settings_cache.get("led_brightness.span", "128")), 255
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
        state_publishes.append(
            (
                topics.state_topic(prefix, u, r, c),
                ill_bytes,
            )
        )

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
            state_publishes.append(
                (
                    topics.state_topic(prefix, su, sr, sc),
                    span_bytes,
                )
            )

    # Sub-interval — LED-03
    if sub_interval is not None and primary is not None:
        u, r, c = primary["unit_id"], primary["row"], primary["col"]
        # sub_cube_interval JSON has no `cube` field — use primary_cube's unit/row/col
        #
        # WR-08: do NOT default missing start/end to [0.0, 1.0] (a full-cube span).
        # A partial interval (e.g. start present, end absent) previously produced a
        # misleading highlight covering the entire cube.  Require BOTH start and end
        # and validate 0 <= start <= end <= 1; skip the sub publish otherwise so a
        # malformed interval is a no-op rather than a wrong full-cube highlight.
        raw_start = sub_interval.get("start")
        raw_end = sub_interval.get("end")
        sub_ok = True
        if raw_start is None or raw_end is None:
            logger.warning(
                "illuminate: sub_cube_interval missing start/end (start=%r end=%r) — "
                "skipping sub publish for cube %s/%s/%s (WR-08)",
                raw_start,
                raw_end,
                u,
                r,
                c,
            )
            sub_ok = False
        else:
            try:
                start_f = float(raw_start)
                end_f = float(raw_end)
            except TypeError, ValueError:
                logger.warning(
                    "illuminate: non-numeric sub_cube_interval (start=%r end=%r) — "
                    "skipping sub publish for cube %s/%s/%s (WR-08)",
                    raw_start,
                    raw_end,
                    u,
                    r,
                    c,
                )
                sub_ok = False
            else:
                if not (0.0 <= start_f <= end_f <= 1.0):
                    logger.warning(
                        "illuminate: out-of-range sub_cube_interval (start=%s end=%s) — "
                        "skipping sub publish for cube %s/%s/%s (WR-08)",
                        start_f,
                        end_f,
                        u,
                        r,
                        c,
                    )
                    sub_ok = False

        if sub_ok:
            interval_dict = {"start": start_f, "end": end_f}
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
        logger.warning("MQTT not connected — publish_ambient skipped (degraded mode)")
        return 0

    prefix = settings.MQTT_TOPIC_PREFIX
    expiry_seconds = settings.MQTT_STATE_EXPIRY_SECONDS
    now_iso = json.dumps({"ts": "ambient"})  # placeholder — not needed for state/* payload

    # ── Resolve ambient settings ──────────────────────────────────────────────
    # D-24: use led_brightness.ambient (idle key), NOT led_brightness.span.
    ambient_hex: str = str(settings_cache.get("led_color.ambient", '"#0051A2"')).strip('"')
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
        # WR-05: this runs inside a detached asyncio task (scheduled at startup and
        # on the revert path).  A DB failure during enumeration must be logged and
        # turned into a no-op return — NOT allowed to raise into the detached task
        # where it would be lost.  Mirrors the try/except + return 0 posture used
        # elsewhere in the lifespan startup steps.
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(sql)
                unit_rows = await cur.fetchall()
        except Exception as exc:
            logger.warning(
                "publish_ambient: failed to enumerate cubes from gruvax.units (returning 0): %s",
                exc,
            )
            return 0
        # Connection closed — no long-held conn during the publish loop.
        for unit_id, row_count, col_count in unit_rows:
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

    publish_coros = [_publish_one(cube["unit_id"], cube["row"], cube["col"]) for cube in cube_list]
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


# ── All-off retained-clear publisher ─────────────────────────────────────────


async def publish_all_off(
    client: aiomqtt.Client | None,
    pool: Any,
    _settings_cache: dict[str, Any],
) -> int:
    """Publish an empty retained payload to every state/{unit_id}/{r}/{c} topic.

    LED-06 / D-11: An empty retained payload (payload=b'', retain=True) is the
    MQTT 3.1.1/5.0 protocol mechanism for deleting a retained message.  This
    is the authoritative retained-cleanup mechanism given Mosquitto's
    expiry-cleanup limitation (RESEARCH Pitfall B).

    Also publishes a non-retained command to ``all/off`` so firmware knows a
    global off was requested.

    Args:
        client:          aiomqtt.Client, or None in degraded mode.
        pool:            psycopg AsyncConnectionPool used to enumerate units.
        _settings_cache: The gruvax.settings key/value dict (unused in v1 but
                         kept for API symmetry with other publisher functions —
                         underscore-prefixed to signal intentional non-use).

    Returns:
        Number of cube state-clear publishes made (NOT counting the all/off command).

    Degraded mode: if ``client`` is None, logs a warning and returns 0.

    Idempotent: calling this function multiple times produces the same effect —
    retained messages are cleared (or were already cleared), no error raised.
    """
    if client is None:
        logger.warning("MQTT not connected — publish_all_off skipped (degraded mode)")
        return 0

    prefix = settings.MQTT_TOPIC_PREFIX

    # ── Enumerate all cubes (short-lived connection — close before publishing) ──
    sql = "SELECT id, rows, cols FROM gruvax.units ORDER BY ordering"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        unit_rows = await cur.fetchall()
    # Connection closed here — no long-held conn during the publish loop (Pitfall B).

    # ── Build a clear task per cube: empty payload, retain=True (D-11) ──────────
    clear_tasks = []
    cube_count = 0
    for unit_id, rows, cols in unit_rows:
        for r in range(rows):
            for c in range(cols):
                clear_tasks.append(
                    safe_publish(
                        client,
                        topics.state_topic(prefix, unit_id, r, c),
                        b"",
                        qos=1,
                        retain=True,
                        timeout=0.5,
                    )
                )
                cube_count += 1

    # Publish all state clears concurrently
    if clear_tasks:
        await asyncio.gather(*clear_tasks, return_exceptions=True)

    # ── Publish the all/off command topic (non-retained) ────────────────────────
    # QoS 1 so firmware that is online receives it reliably; retain=False so
    # firmware that boots AFTER the command is not replayed the off command
    # (it will see the cleared state/* retained messages instead).
    await safe_publish(
        client,
        topics.all_off_topic(prefix),
        b"{}",
        qos=1,
        retain=False,
        timeout=0.5,
    )

    logger.info("LED all-off: published %d clear-retained payloads", cube_count)
    return cube_count


# ── Diagnostic sequence publisher ────────────────────────────────────────────


async def run_diagnostic(
    client: aiomqtt.Client | None,
    pool: Any,
    settings_cache: dict[str, Any],
    run_id: str,
) -> None:
    """Cycle every cube through the configured state color sequence for diagnostics.

    LED-07 / D-08/09/10: Publishes a ``state/*`` payload per cube per state in
    the sequence: label-span → position → error → setup → off (5 states).
    After the cube loop, transiently subscribes to ``status/#`` for 5 s to log
    any firmware status responses (expected: nothing in v1 — wires the future
    hardware status seam).

    The background task runs asynchronously; the API endpoint returns a run_id
    immediately (D-08 — instant ack).

    Color sequence per cube (D-09):
      label-span  → led_color.label_span  / led_brightness.span   (span tier)
      position    → led_color.position    / led_brightness.active  (active tier)
      error       → led_color.error       / led_brightness.active  (active tier)
      setup       → led_color.setup       / led_brightness.active  (active tier)
      off         → #000000               / brightness=0

    D-24 brightness-tier correctness (LOCKED):
      Span state uses ``led_brightness.span``   (label-span tier, ~50%).
      All other active states use ``led_brightness.active`` (100%).
      The idle ``led_brightness.ambient`` key is NEVER used in this function.

    Args:
        client:         aiomqtt.Client, or None in degraded mode.
        pool:           psycopg AsyncConnectionPool.
        settings_cache: The gruvax.settings key/value dict.
        run_id:         Cosmetic run identifier (logged, returned to caller).

    Degraded mode: if ``client`` is None, logs a warning and returns.
    """
    if client is None:
        logger.warning(
            "MQTT not connected — run_diagnostic run_id=%s skipped (degraded mode)",
            run_id,
        )
        return

    # WR-07: guard against a missing pool (broker connected but DB unavailable).
    # Unlike publish_ambient this function unconditionally opens a connection to
    # enumerate cubes; without this guard a None pool raises AttributeError inside
    # the BackgroundTask, which FastAPI logs but never surfaces (the endpoint
    # already returned 200 {run_id}).
    if pool is None:
        logger.warning(
            "run_diagnostic run_id=%s: pool is None; cannot enumerate cubes — skipping",
            run_id,
        )
        return

    prefix = settings.MQTT_TOPIC_PREFIX
    expiry_seconds = settings.MQTT_STATE_EXPIRY_SECONDS

    # ── Read diagnostic parameters ────────────────────────────────────────────
    # WR-09: clamp inter-cube delay to a sane bounded range and tolerate a
    # non-numeric / hostile value.  Without this, a large or non-integer
    # led_diagnostic.inter_cube_ms makes the diagnostic loop sleep for an
    # arbitrary duration per cube (or raise ValueError) inside the BackgroundTask
    # while holding the status/# subscription open.
    try:
        inter_cube_ms = int(settings_cache.get("led_diagnostic.inter_cube_ms", 200))
    except TypeError, ValueError:
        logger.warning(
            "run_diagnostic run_id=%s: invalid led_diagnostic.inter_cube_ms %r; using 200ms",
            run_id,
            settings_cache.get("led_diagnostic.inter_cube_ms"),
        )
        inter_cube_ms = 200
    inter_cube_ms = min(max(inter_cube_ms, 0), 2000)  # clamp to [0, 2000] ms
    inter_cube_delay_s: float = inter_cube_ms / 1000.0

    # Resolve state colors (strip JSON string quotes — stored as '"#RRGGBB"')
    color_span: str = str(settings_cache.get("led_color.label_span", '"#7C3AED"')).strip('"')
    color_position: str = str(settings_cache.get("led_color.position", '"#FFD700"')).strip('"')
    color_error: str = str(settings_cache.get("led_color.error", '"#E63946"')).strip('"')
    color_setup: str = str(settings_cache.get("led_color.setup", '"#0077B6"')).strip('"')
    color_off: str = "#000000"

    # D-24: span state uses led_brightness.span; active states use led_brightness.active.
    # led_brightness.ambient is the IDLE key — never used here.
    # CR-02: clamp to the 8-bit hardware ceiling (255), NOT the tier default (128),
    # so the diagnostic honours an admin-configured span brightness above 128.
    brightness_span: int = clamp_brightness(
        int(settings_cache.get("led_brightness.span", 128)), 255
    )
    brightness_active: int = clamp_brightness(
        int(settings_cache.get("led_brightness.active", 255)), 255
    )
    # brightness_off is always 0
    brightness_off: int = 0

    # State sequence: (color_hex, brightness, state_label)
    state_sequence = [
        (color_span, brightness_span, "label-span"),
        (color_position, brightness_active, "position"),
        (color_error, brightness_active, "error"),
        (color_setup, brightness_active, "setup"),
        (color_off, brightness_off, "off"),
    ]

    # ── Enumerate all cubes (short-lived connection — close before loop) ──────
    sql = "SELECT id, rows, cols FROM gruvax.units ORDER BY ordering"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        unit_rows = await cur.fetchall()
    # Connection closed here — no long-held conn during the publish loop.

    now_iso = datetime.now(UTC).isoformat()
    expiry_props = _make_expiry_props(expiry_seconds)

    # ── Cube loop ─────────────────────────────────────────────────────────────
    for unit_id, rows, cols in unit_rows:
        for r in range(rows):
            for c in range(cols):
                state_t = topics.state_topic(prefix, unit_id, r, c)

                for color_hex, brightness, state_label in state_sequence:
                    if brightness == 0 or color_hex == "#000000":
                        # Off state: publish empty retained payload to clear state
                        payload_bytes = b""
                        await safe_publish(
                            client,
                            state_t,
                            payload_bytes,
                            qos=1,
                            retain=True,
                            timeout=0.5,
                        )
                    else:
                        r_val, g_val, b_val = hex_to_rgb(color_hex)
                        color_obj = RGBColor(r=r_val, g=g_val, b=b_val)
                        ill_payload = IlluminatePayload(
                            issued_at=now_iso,
                            unit_id=unit_id,
                            row=r,
                            col=c,
                            color=color_obj,
                            brightness=brightness,
                            transition=TransitionSpec(style="instant", duration_ms=0),
                        )
                        payload_bytes = ill_payload.model_dump_json(by_alias=True).encode()
                        await safe_publish(
                            client,
                            state_t,
                            payload_bytes,
                            qos=1,
                            retain=True,
                            properties=expiry_props,
                            timeout=0.5,
                        )
                    logger.info(
                        "LED diagnostic run_id=%s cube=%s/%d/%d state=%s brightness=%d",
                        run_id,
                        unit_id,
                        r,
                        c,
                        state_label,
                        brightness,
                    )

                # Yield the event loop between cubes (D-08 — don't block)
                await asyncio.sleep(inter_cube_delay_s)

    # ── Transient status subscribe (D-10) ─────────────────────────────────────
    # Subscribe to status/# for 5 s to capture any firmware status responses.
    # Expected result: nothing (no hardware in v1).  This wires the future seam.
    # Pitfall G: status/# is disjoint from illuminate/* — no cross-traffic risk.
    #
    # CR-03: ``client.messages`` is a SINGLE shared incoming-message iterator in
    # aiomqtt 2.5.x.  If two diagnostics ran concurrently they would BOTH iterate
    # it and race for inbound messages.  Guard with a flag on the client so only
    # one diagnostic owns ``client.messages`` at a time; a second concurrent
    # diagnostic skips the subscribe window entirely rather than fighting over the
    # shared queue.  The ``asyncio.timeout(5.0)`` bound already makes the window
    # finite and cancelable: at shutdown the surrounding task is cancelled, the
    # ``async with asyncio.timeout`` block propagates CancelledError, and the
    # ``finally`` still unsubscribes and clears the guard.
    # Use ``is True`` (not truthiness) so the guard only trips on the explicit
    # boolean flag we set below — never on an auto-created mock attribute or any
    # other truthy value that may live on the client object.
    if getattr(client, "_gruvax_diag_active", False) is True:
        logger.warning(
            "LED diagnostic run_id=%s: another diagnostic already owns status/#; "
            "skipping the status-subscribe window to avoid draining the shared "
            "message iterator (CR-03)",
            run_id,
        )
    else:
        status_topic = topics.status_wildcard(prefix)
        # Mark the client as the sole status/# consumer for this window.
        client._gruvax_diag_active = True  # type: ignore[attr-defined]
        await client.subscribe(status_topic, qos=1)
        try:
            async with asyncio.timeout(5.0):
                async for msg in client.messages:
                    logger.info(
                        "LED status from firmware: topic=%s payload=%s",
                        msg.topic,
                        msg.payload,
                    )
        except TimeoutError:
            pass  # expected — no hardware in v1
        finally:
            await client.unsubscribe(status_topic)
            client._gruvax_diag_active = False  # type: ignore[attr-defined]

    # ── Restore the idle ambient baseline (CR-04 / LED-11 / D-20) ──────────────
    # The diagnostic's final "off" frame deletes each cube's retained state/* via
    # an empty payload, which leaves every cube DARK after the sweep.  D-20 / LED-11
    # require every cube to show the idle ambient colour when no highlight is
    # active, so re-publish the ambient baseline as the last step.  This keeps the
    # post-diagnostic state consistent with startup ambient and the revert path,
    # rather than leaving the kiosk/firmware without an idle baseline until the
    # next search or restart.
    await publish_ambient(client, pool, settings_cache)

    logger.info("LED diagnostic run_id=%s complete; ambient baseline restored", run_id)

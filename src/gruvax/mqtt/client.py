"""MQTT client lifespan helper for GRUVAX.

Phase 1 stub: connects to the broker at startup and publishes a retained
``server/hello`` message with ``{"alive": true}``. The Last Will and Testament
(LWT) is configured so a broker-detected disconnect publishes ``{"alive": false}``.

DEP-01 constraint: The MQTT connection is **non-blocking**. If the broker is
unreachable (mosquitto may not be running in dev), startup continues with
``app.state.mqtt = None`` and ``app.state.mqtt_ok = False``.

Phase 6: upgraded to MQTT 5 (ProtocolVersion.V5) so that paho Properties
(MessageExpiryInterval) are wire-encoded on retained state/* publishes.
The publish spine lives in mqtt/publishers.py (Phase 6 — fan_out_illuminate).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiomqtt
from aiomqtt import ProtocolVersion

from gruvax.settings import settings


if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

_HELLO_TOPIC = "gruvax/v1/server/hello"
_HELLO_ALIVE = b'{"alive": true}'
_HELLO_DEAD = b'{"alive": false}'


async def connect_mqtt(app: FastAPI) -> None:
    """Attempt a best-effort MQTT connection at lifespan startup.

    On success: sets ``app.state.mqtt`` to the connected ``aiomqtt.Client``
    and ``app.state.mqtt_ok = True``. Publishes the retained hello message.

    On failure: logs a warning, sets ``app.state.mqtt = None`` and
    ``app.state.mqtt_ok = False``. The API continues serving; ``/api/health``
    will report ``mqtt: "degraded"``.

    DEP-01 / T-01-11: MQTT failure must never block API startup or requests.
    """
    try:
        client = aiomqtt.Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            identifier="gruvax-api",
            protocol=ProtocolVersion.V5,  # Phase 6: enables MQTT 5 Properties wire encoding (D-12)
            will=aiomqtt.Will(
                topic=_HELLO_TOPIC,
                payload=_HELLO_DEAD,
                retain=True,
            ),
            keepalive=30,
        )
        await client.__aenter__()
        await client.publish(_HELLO_TOPIC, payload=_HELLO_ALIVE, retain=True)
        app.state.mqtt = client
        app.state.mqtt_ok = True
        logger.info("MQTT connected to %s:%d", settings.MQTT_HOST, settings.MQTT_PORT)
    except Exception as exc:
        logger.warning(
            "MQTT connection failed (broker unreachable or misconfigured); "
            "API continues in degraded mode. Reason: %s",
            exc,
        )
        app.state.mqtt = None
        app.state.mqtt_ok = False


async def disconnect_mqtt(app: FastAPI) -> None:
    """Gracefully disconnect the MQTT client if connected."""
    client: aiomqtt.Client | None = getattr(app.state, "mqtt", None)
    if client is not None:
        try:
            await client.__aexit__(None, None, None)
            logger.info("MQTT disconnected cleanly")
        except Exception as exc:
            logger.warning("MQTT disconnect error (ignored): %s", exc)

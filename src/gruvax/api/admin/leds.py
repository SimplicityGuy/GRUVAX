"""Admin LED control endpoints for GRUVAX.

Endpoints:
  POST /api/admin/leds/off        — idempotent all-off: clears every retained
                                    state/* topic by publishing b'' with retain=True,
                                    then sends a non-retained all/off command.
  POST /api/admin/leds/diagnostic — start a diagnostic sweep in a background task;
                                    returns run_id + started_at immediately (D-08).

Both endpoints:
  - Require admin session + CSRF via Depends(require_admin) (T-06-12, STRIDE T-06-12).
  - Handle degraded mode (client=None) gracefully — return 200 without raising
    (DEP-03 / Pitfall C).
  - Live at /admin prefix + /api prefix from app.py; no new route (D-19).

Phase 6: LED Contract over MQTT (Hardware Stubbed)
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any

import aiomqtt
from fastapi import APIRouter, BackgroundTasks, Depends, Request

from gruvax.api.deps import get_pool, require_admin
from gruvax.mqtt import publishers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-leds"])


@router.post("/leds/off")
async def leds_all_off(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Idempotent all-off: clear every retained state/* topic.

    Publishes an empty retained payload (b'', retain=True) to every
    state/{unit_id}/{row}/{col} topic enumerated from gruvax.units.
    Also publishes a non-retained command to all/off.

    Safe to call repeatedly — clearing an already-cleared retained message
    is a no-op on the broker side (D-11, MQTT specification).

    Degraded mode (client=None): returns 200 {"published": 0} without raising.
    """
    client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
    settings_cache: dict[str, Any] = getattr(request.app.state, "settings_cache", {})

    published = await publishers.publish_all_off(client, pool, settings_cache)
    return {"published": published}


@router.post("/leds/diagnostic")
async def start_diagnostic(
    request: Request,
    background_tasks: BackgroundTasks,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Start a diagnostic sweep in a background task.

    Cycles every cube through the configured state color sequence (label-span →
    position → error → setup → off) with an inter-cube delay, then transiently
    subscribes to status/# for 5 s to log any firmware status responses
    (expected: nothing in v1 — wires the future hardware status seam, D-10).

    Returns run_id + started_at immediately (D-08 — instant ack; diagnostic runs
    in background, not blocking the response).

    Degraded mode (client=None): the background task short-circuits gracefully;
    the endpoint itself still returns 200 with the run_id.
    """
    run_id = str(_uuid.uuid4())
    client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
    settings_cache: dict[str, Any] = getattr(request.app.state, "settings_cache", {})

    background_tasks.add_task(
        publishers.run_diagnostic,
        client=client,
        pool=pool,
        settings_cache=settings_cache,
        run_id=run_id,
    )

    logger.info("LED diagnostic requested run_id=%s client_ok=%s", run_id, client is not None)
    return {
        "run_id": run_id,
        "started_at": datetime.now(UTC).isoformat(),
    }

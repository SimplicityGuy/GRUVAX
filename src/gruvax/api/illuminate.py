"""Public POST /api/illuminate endpoint — fire-and-forget LED fan-out.

Phase 6: LED Contract over MQTT (Hardware Stubbed)

D-03: This endpoint is PUBLIC — no require_admin guard. The kiosk browser
fires it directly after each locate result is selected, without needing an
admin session or CSRF token.  It is intentionally unauthenticated because:
  - The kiosk screen is in a controlled physical location (home LAN only).
  - Any client can POST a LocateResult they already received from /api/locate.
  - Worst-case impact: lights the wrong cube (cosmetic, not data loss).
  - T-06-01: Pydantic IlluminateRequest model rejects malformed bodies → 422.

D-01 / SC5: The publish is fire-and-forget via asyncio.create_task.
  - If the broker is connected: task is scheduled, returns immediately.
  - If the broker is None (degraded mode): returns {"published": false} without
    raising any exception.  The locate path is NEVER blocked.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime
from typing import Any

import aiomqtt
from fastapi import APIRouter, Request
from pydantic import BaseModel

from gruvax.mqtt import lifecycle, publishers

logger = logging.getLogger(__name__)

router = APIRouter(tags=["illuminate"])

# CR-01: module-scoped fallback strong-reference set for fire-and-forget tasks.
# The asyncio event loop holds only a WEAK reference to a task created via
# asyncio.create_task; a discarded task can be garbage-collected mid-execution,
# silently cancelling an in-flight publish.  Tasks are normally tracked on
# ``app.state.background_tasks`` (created in the lifespan), but this module-level
# set is used as a fallback for tests/early-startup paths that bypass the
# lifespan, so the strong-reference guarantee holds in every path.
_background_tasks: set[asyncio.Task[Any]] = set()


def _spawn(coro: Coroutine[Any, Any, Any], request: Request) -> None:
    """Schedule *coro* as a fire-and-forget task with a strong reference (CR-01).

    The task is added to ``request.app.state.background_tasks`` when that set
    exists (the production path, populated by the lifespan), otherwise to the
    module-level fallback set.  A done-callback discards the task from whichever
    set held it once it completes, so the set stays O(in-flight tasks).
    """
    task_set: set[asyncio.Task[Any]] = getattr(
        request.app.state, "background_tasks", _background_tasks
    )
    task = asyncio.create_task(coro)
    task_set.add(task)
    task.add_done_callback(task_set.discard)


class IlluminateRequest(BaseModel):
    """Request body for POST /api/illuminate.

    Mirrors the /api/locate JSON shape (the LocateResult the kiosk already holds).
    Extra fields are ignored so the kiosk can POST the full LocateResult without
    field filtering.

    T-06-01: Pydantic validates this model at request time — malformed bodies
    (missing required fields) return HTTP 422 automatically.
    """

    release_id: int
    primary_cube: dict[str, int] | None
    label_span: list[dict[str, int]]
    sub_cube_interval: dict[str, Any] | None
    confidence: float

    model_config = {"extra": "ignore"}


@router.post("/illuminate")
async def illuminate(
    request: Request,
    body: IlluminateRequest,
) -> dict[str, Any]:
    """Accept a LocateResult and schedule LED fan-out to the MQTT broker.

    Returns immediately with ``{"published": true, "accepted_at": ...}`` when
    the broker is connected, or ``{"published": false, "accepted_at": ...}``
    in degraded mode (broker unreachable).

    The MQTT publish is fire-and-forget: any broker hiccup surfaces only as a
    log warning and does not affect the HTTP response.

    LED-09: fans out to three locked command topics (illuminate/{u}/{r}/{c},
    span/{change_id}, sub/{u}/{r}/{c}) plus retained state/* topics.
    D-01: no blocking; asyncio.create_task schedules the coroutine.
    D-03: no require_admin — public endpoint.
    """
    client: aiomqtt.Client | None = getattr(request.app.state, "mqtt", None)
    settings_cache: dict[str, Any] = getattr(request.app.state, "settings_cache", {})
    registry = getattr(request.app.state, "highlight_registry", None)

    if client is not None and registry is not None:
        # CR-01: _spawn keeps a strong reference so the task is not GC-cancelled.
        _spawn(
            lifecycle.illuminate_with_lifecycle(registry, client, settings_cache, body),
            request,
        )
    elif client is not None:
        # Fallback: registry not initialised yet (very early startup edge case).
        # CR-01: _spawn keeps a strong reference so the task is not GC-cancelled.
        _spawn(
            publishers.fan_out_illuminate(client, body, settings_cache),
            request,
        )
        logger.warning(
            "highlight_registry not found on app.state — falling back to plain fan_out_illuminate "
            "for release_id=%s",
            body.release_id,
        )
    else:
        logger.warning(
            "MQTT not connected — illuminate for release_id=%s acknowledged but not published "
            "(degraded mode; D-01)",
            body.release_id,
        )

    return {
        "published": client is not None,
        "accepted_at": datetime.now(UTC).isoformat(),
    }

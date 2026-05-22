"""GET /api/events — Server-Sent Events stream for kiosk live updates.

Emits: boundary_changed, admin_editing, server_hello, server_shutdown.

Critical constraints (RESEARCH.md Pitfall 8 + 10):
  - Depends ONLY on get_event_bus — NEVER on get_pool (D-09, Pitfall 10).
  - Sets X-Accel-Buffering: no and Cache-Control: no-store (Pitfall 8).
  - ping=15 is the sse-starlette default — do NOT increase it (Pitfall 8).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from gruvax.api.deps import get_event_bus
from gruvax.events.bus import EventBus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.get("/events")
async def stream_events(
    request: Request,
    bus: EventBus = Depends(get_event_bus),  # NO get_pool — Pitfall 10
) -> EventSourceResponse:
    """SSE stream — no DB dependency (D-09, Pitfall 10).

    Each connected client gets its own asyncio.Queue subscriber.
    The generator unsubscribes on disconnect via the finally-block.
    ping=15 flushes nginx/reverse-proxy buffers (Pitfall 8).
    """

    async def generator() -> AsyncIterator[ServerSentEvent]:
        q = bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield ServerSentEvent(
                        event=event.name,
                        data=json.dumps(event.data),
                    )
                except asyncio.TimeoutError:
                    continue  # loop back; ping=15 handles keepalive
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(
        generator(),
        ping=15,  # Pitfall 8: flush proxy buffers; do NOT lengthen
        headers={
            "X-Accel-Buffering": "no",    # Pitfall 8: nginx/proxy buffering
            "Cache-Control": "no-store",   # Pitfall 8: no caching
        },
    )

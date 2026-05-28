"""GET /api/events/{profile_id} — per-profile SSE stream for kiosk live updates.

Emits: boundary_changed, admin_editing, server_hello, server_shutdown.

Critical constraints (RESEARCH.md Pitfall 8 + 10):
  - Depends ONLY on get_bus_for_profile — NEVER on get_pool (D-09, Pitfall 10).
  - Sets X-Accel-Buffering: no and Cache-Control: no-store (Pitfall 8).
  - ping=15 is the sse-starlette default — do NOT increase it (Pitfall 8).
  - path profile_id is validated against the gruvax_browse_binding cookie (D2-04).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from gruvax.api.deps import get_bus_for_profile


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from gruvax.events.bus import EventBus


logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])


@router.get("/events/{profile_id}")
async def stream_events(
    profile_id: str,
    request: Request,
    bus: EventBus = Depends(get_bus_for_profile),  # NO get_pool — Pitfall 10
) -> EventSourceResponse:
    """Per-profile SSE stream — no DB dependency (D-09, D2-04, Pitfall 10).

    The path profile_id is validated against the gruvax_browse_binding session
    cookie by get_bus_for_profile (400 unbound / 403 mismatch / 404 not found).
    Each connected client gets its own asyncio.Queue subscriber on the profile's bus.
    The generator unsubscribes on disconnect via the finally-block.
    ping=15 flushes nginx/reverse-proxy buffers (Pitfall 8).
    """

    async def generator() -> AsyncIterator[ServerSentEvent]:
        q = bus.subscribe()
        try:
            # Yield an SSE comment immediately so headers flush to the client
            # before the first real event arrives (Pitfall 8: proxy buffering).
            # sse-starlette forwards comment-only ServerSentEvent as ": ...\n\n".
            yield ServerSentEvent(comment="connected")
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield ServerSentEvent(
                        event=event.name,
                        data=json.dumps(event.data),
                    )
                except TimeoutError:
                    continue  # loop back; ping=15 handles keepalive
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(
        generator(),
        ping=15,  # Pitfall 8: flush proxy buffers; do NOT lengthen
        headers={
            "X-Accel-Buffering": "no",  # Pitfall 8: nginx/proxy buffering
            "Cache-Control": "no-store",  # Pitfall 8: no caching
        },
    )

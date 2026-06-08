"""GET /api/events/{profile_id} — per-profile SSE stream for kiosk live updates.

Emits: boundary_changed, admin_editing, server_hello, server_shutdown,
       device_revoked, device_reassigned.

Critical constraints (RESEARCH.md Pitfall 8 + 10):
  - Depends ONLY on get_bus_for_profile — NEVER on get_pool (D-09, Pitfall 10).
  - Sets X-Accel-Buffering: no and Cache-Control: no-store (Pitfall 8).
  - ping=15 is the sse-starlette default — do NOT increase it (Pitfall 8).
  - path profile_id is validated via resolve_profile_from_request in get_bus_for_profile
    (D2-04, D3-04): device binding + revoke guard run before streaming begins; the
    pool is acquired and released INSIDE the dep — generator body is pool-free.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
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
    """Per-profile SSE stream — no DB dependency in generator (D-09, D2-04, Pitfall 10).

    get_bus_for_profile (async dep) validates the request via resolve_profile_from_request:
    the device fingerprint + revoke guard check acquires + releases the pool BEFORE this
    handler runs (D3-04, D3-07).  The generator body reads ONLY the asyncio.Queue — zero
    pool interaction (Pitfall 10 / T-03-13 preserved).
    Error taxonomy: 400 session_unbound / 403 device_unknown / 403 device_revoked /
    403 profile_mismatch / 503 registry not ready / 404 profile_not_found.
    Each connected client gets its own asyncio.Queue subscriber on the profile's bus.
    The generator unsubscribes on disconnect via the finally-block.
    ping=15 flushes nginx/reverse-proxy buffers (Pitfall 8).
    """

    async def generator() -> AsyncIterator[ServerSentEvent]:
        q = bus.subscribe()
        try:
            # Yield comment + retry directive immediately so headers flush and
            # client gets its jittered reconnect interval before the first real event.
            # retry: field spreads reconnects over 2-8s window (PITFALLS 36 prevention).
            retry_ms = random.randint(2000, 8000)  # noqa: S311  # nosec B311 — jitter, not crypto
            yield ServerSentEvent(comment="connected", retry=retry_ms)
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

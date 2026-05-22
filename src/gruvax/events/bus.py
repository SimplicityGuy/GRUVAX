"""In-process asyncio.Queue event bus for GRUVAX SSE fan-out.

Instantiated once in the FastAPI lifespan (app.state.event_bus).
Any admin handler publishes; GET /api/events subscribers receive.

Phase 4 seam: bus.publish() is called after cache.invalidate() + cache.load()
in put_cube_boundary and bulk_write_cubes (Pitfall A ordering preserved).
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    """A single bus event — name + arbitrary JSON-serialisable data."""

    name: str
    data: dict[str, Any]


class EventBus:
    """In-process asyncio.Queue-per-subscriber fan-out.

    Usage::

        bus = EventBus()                        # called once in lifespan
        q = bus.subscribe()                     # called in SSE generator setup
        await bus.publish("boundary_changed", {...})
        bus.unsubscribe(q)                      # in SSE generator finally-block

    Backpressure: drop-oldest via ``put_nowait`` + ``QueueFull`` silence.
    A dropped event is handled by the client's resync-on-reconnect (D-11).
    ``maxsize=64`` holds ~1 min of 4-event/s bursts; typical traffic is one
    event every several minutes.
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()

    def subscribe(self) -> asyncio.Queue[Event]:
        """Return a per-connection Queue. Call in SSE generator setup.

        Phase 4: called once at the top of the ``stream_events`` generator.
        The queue is unsubscribed in the generator's finally-block on disconnect.
        """
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        """Remove subscriber queue. Call in the SSE generator finally-block.

        Uses ``discard`` — safe to call even if ``q`` is already removed (e.g.
        on a second disconnect signal for the same connection).
        """
        self._subscribers.discard(q)

    async def publish(self, name: str, data: dict[str, Any]) -> None:
        """Fan-out to all subscribers. Drop on QueueFull (slow client).

        The client will resync on reconnect (D-11). Never raises.
        Rule: call AFTER the DB transaction commits and AFTER cache.load(),
        same as cache.invalidate() — Pitfall A.
        """
        event = Event(name=name, data=data)
        for q in list(self._subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                # Slow subscriber; drop silently on QueueFull.
                # Client resyncs boundary-derived queries on next reconnect (D-11).
                # Disconnecting the slow client would be harsher and unnecessary.
                q.put_nowait(event)

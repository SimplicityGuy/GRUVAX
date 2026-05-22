"""Unit tests for EventBus (events/bus.py) — Phase 4 RTM-01, D-09.

Tests:
  - test_subscribe_receive_publish: subscribe → publish → assert round-trip; unsubscribe removes queue.
  - test_slow_subscriber_drops_silently: full queue does not raise on 65th publish.
  - test_sse_no_pool_dep: stream_events signature contains no pool/get_pool dep (D-09, Pitfall 10).
"""

from __future__ import annotations

import asyncio
import inspect

import pytest


@pytest.mark.asyncio
async def test_subscribe_receive_publish() -> None:
    """Subscribe, publish, and receive an event; unsubscribe removes the queue."""
    from gruvax.events.bus import EventBus

    bus = EventBus()
    q = bus.subscribe()

    await bus.publish("boundary_changed", {"cube_ids": [], "change_set_id": "x"})

    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event.name == "boundary_changed"
    assert event.data == {"cube_ids": [], "change_set_id": "x"}

    bus.unsubscribe(q)
    assert q not in bus._subscribers


@pytest.mark.asyncio
async def test_slow_subscriber_drops_silently() -> None:
    """Filling the queue to maxsize=64 then publishing once more must NOT raise.

    The 65th event is silently dropped (drop-oldest backpressure — D-11 resync
    handles the gap on reconnect). Queue stays full.
    """
    from gruvax.events.bus import EventBus

    bus = EventBus()
    q = bus.subscribe()

    # Fill the queue to maxsize (64)
    for i in range(64):
        await bus.publish(
            "boundary_changed",
            {"cube_ids": [{"unit": 1, "row": 0, "col": i % 4}], "change_set_id": str(i)},
        )

    # 65th publish must NOT raise even though the queue is full
    await bus.publish("boundary_changed", {"cube_ids": [], "change_set_id": "overflow"})

    # Queue must remain full (no exception, drop happened silently)
    assert q.full()


def test_sse_no_pool_dep() -> None:
    """Confirm stream_events signature contains no pool / get_pool dependency.

    Binds D-09 (SSE endpoint holds no DB connection) and Pitfall 10
    (pool exhaustion under concurrent SSE + search).
    """
    from gruvax.api.events import stream_events  # noqa: PLC0415

    sig = inspect.signature(stream_events)
    param_names = list(sig.parameters.keys())

    assert "pool" not in param_names, (
        f"stream_events must not depend on 'pool' — found params: {param_names}"
    )
    assert "get_pool" not in str(sig), (
        f"stream_events must not reference get_pool in its signature: {sig}"
    )

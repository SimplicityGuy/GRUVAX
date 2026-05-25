"""Unit tests for GRUVAX LED highlight lifecycle.

Nyquist Wave-0 scaffold — Phase 6 Plan 02: Highlight Lifecycle

Covers:
  LED-11 / D-20 — idle/ambient baseline (every cube held at led_color.ambient /
                   led_brightness.ambient as a retained state/* baseline)
  LED-12 / D-21,D-22 — server-scheduled TTL revert (injected delay) back to ambient
  LED-12 / D-22 — default mode: next search cancels prior highlight + reverts first
  LED-13 / D-23 — retain mode: accumulates highlights, each reverts independently

Tests use:
  - A stub aiomqtt client (AsyncMock recording publish calls) to assert which
    topics/payloads were published without a live broker.
  - A mocked DB pool returning one unit (id=1, rows=2, cols=2 → 4 cubes).
  - Injected near-zero delay everywhere a TTL would otherwise wait, so tests
    run without real 180s/900s waits (D-22 testability seam).

All tests MUST fail in RED until gruvax.mqtt.lifecycle is implemented (Task 2).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# This import is intentionally expected to fail RED until Task 2 creates lifecycle.py.
from gruvax.mqtt.lifecycle import (
    HighlightRegistry,
    cancel_and_revert_all,
    illuminate_with_lifecycle,
    schedule_revert,
)
from gruvax.mqtt.publishers import publish_ambient

# ── Shared fixture helpers ────────────────────────────────────────────────────

TEST_PREFIX = "gruvax/v1/dev/leds"

SETTINGS_CACHE: dict[str, Any] = {
    "led_color.ambient": '"#0051A2"',
    "led_brightness.ambient": "40",
    "led_color.position": '"#FFD700"',
    "led_color.label_span": '"#7C3AED"',
    "led_brightness.active": "255",
    "led_brightness.span": "128",
    "led_transition.position_style": '"pulse"',
    "led_transition.position_ms": "800",
    "led_transition.span_style": '"fade"',
    "led_transition.span_ms": "500",
    "led_highlight.active_ttl_seconds": "180",
    "led_highlight.retain_mode": "false",
    "led_highlight.retain_ttl_seconds": "900",
}

# A locate-result body describing primary cube (unit=1, row=0, col=0) with label span
# covering 2 cubes.
LOCATE_BODY_A = MagicMock(
    release_id=1,
    primary_cube={"unit_id": 1, "row": 0, "col": 0},
    label_span=[
        {"unit_id": 1, "row": 0, "col": 0},
        {"unit_id": 1, "row": 0, "col": 1},
    ],
    sub_cube_interval=None,
    confidence=0.80,
)

# A different locate result for "second search" tests.
LOCATE_BODY_B = MagicMock(
    release_id=2,
    primary_cube={"unit_id": 1, "row": 1, "col": 0},
    label_span=[{"unit_id": 1, "row": 1, "col": 0}],
    sub_cube_interval=None,
    confidence=0.70,
)


def _make_mqtt_client() -> AsyncMock:
    """Return an AsyncMock mimicking aiomqtt.Client.publish()."""
    client = AsyncMock()
    client.publish = AsyncMock(return_value=None)
    return client


def _make_pool_with_one_unit() -> AsyncMock:
    """Return an AsyncMock pool that returns one unit: id=1, rows=2, cols=2 (4 cubes).

    This gives publish_ambient 4 cubes to iterate over:
      (1,0,0), (1,0,1), (1,1,0), (1,1,1)
    """
    # Row returned by the DB cursor: (id, rows, cols)
    unit_row = (1, 2, 2)

    cursor_mock = AsyncMock()
    cursor_mock.fetchall = AsyncMock(return_value=[unit_row])
    cursor_mock.__aenter__ = AsyncMock(return_value=cursor_mock)
    cursor_mock.__aexit__ = AsyncMock(return_value=False)

    conn_mock = AsyncMock()
    conn_mock.cursor = MagicMock(return_value=cursor_mock)
    conn_mock.__aenter__ = AsyncMock(return_value=conn_mock)
    conn_mock.__aexit__ = AsyncMock(return_value=False)

    pool_mock = AsyncMock()
    pool_mock.connection = MagicMock(return_value=conn_mock)
    return pool_mock


# ── Ambient baseline (LED-11 / D-20) ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_ambient_writes_retained_state_for_every_cube() -> None:
    """publish_ambient publishes a retained state/* payload for every (unit,row,col).

    LED-11 / D-20: ambient baseline is published with qos=1, retain=True for
    every cube in the unit list. Color resolves from led_color.ambient (#0051A2)
    and brightness from led_brightness.ambient (40).
    """
    client = _make_mqtt_client()
    pool = _make_pool_with_one_unit()

    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        count = await publish_ambient(client, pool, SETTINGS_CACHE)

    # One unit, 2x2 = 4 cubes.
    assert count == 4, f"Expected 4 cubes published; got count={count}"

    publish_calls = client.publish.call_args_list
    state_calls = [c for c in publish_calls if f"{TEST_PREFIX}/state/" in c[0][0]]
    assert len(state_calls) == 4, (
        f"Expected 4 state/* retained calls; got {len(state_calls)} "
        f"(topics: {[c[0][0] for c in state_calls]})"
    )

    for sc in state_calls:
        kwargs = sc[1] if len(sc) > 1 else {}
        assert kwargs.get("retain") is True, f"state/* must be retain=True; got {kwargs}"
        assert kwargs.get("qos") == 1, f"state/* must use qos=1; got {kwargs}"
        payload = json.loads(sc[0][1])
        color = payload["color"]
        # #0051A2 → r=0, g=81, b=162
        assert color["r"] == 0, f"r channel should be 0 for #0051A2; got {color}"
        assert color["g"] == 81, f"g channel should be 81 for #0051A2; got {color}"
        assert color["b"] == 162, f"b channel should be 162 for #0051A2; got {color}"
        assert payload["brightness"] == 40, (
            f"brightness should be 40 (led_brightness.ambient); got {payload['brightness']}"
        )


@pytest.mark.asyncio
async def test_ambient_uses_ambient_keys_not_span() -> None:
    """publish_ambient uses led_brightness.ambient — NOT led_brightness.span (D-24 separation).

    The span tier (led_brightness.span=128) is for active label-span highlights.
    The ambient tier (led_brightness.ambient=40) is the idle baseline only.
    """
    client = _make_mqtt_client()
    pool = _make_pool_with_one_unit()

    # Deliberately different values so we can detect which key was read.
    cache = dict(SETTINGS_CACHE)
    cache["led_brightness.ambient"] = "30"
    cache["led_brightness.span"] = "200"  # should NOT appear in ambient publishes

    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await publish_ambient(client, pool, cache)

    publish_calls = client.publish.call_args_list
    state_calls = [c for c in publish_calls if f"{TEST_PREFIX}/state/" in c[0][0]]
    for sc in state_calls:
        payload = json.loads(sc[0][1])
        assert payload["brightness"] == 30, (
            f"Ambient publish must use led_brightness.ambient=30, not span=200; "
            f"got brightness={payload['brightness']}"
        )


# ── TTL revert (LED-12 / D-22) ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_illuminate_schedules_revert() -> None:
    """illuminate_with_lifecycle registers a revert task in the registry.

    LED-12 / D-22: after calling illuminate_with_lifecycle, the registry must
    contain exactly one entry (in default mode — prior is empty here) whose
    cubes include primary + span cubes from the body.
    """
    client = _make_mqtt_client()
    registry = HighlightRegistry()

    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await illuminate_with_lifecycle(
            registry, client, SETTINGS_CACHE, LOCATE_BODY_A, sleep=asyncio.sleep
        )

    assert len(registry) == 1, f"Expected 1 registered highlight; got {len(registry)}"


@pytest.mark.asyncio
async def test_revert_republishes_ambient_for_affected_cubes() -> None:
    """After the injected (near-zero) TTL elapses, the revert publishes ambient state/* for affected cubes.

    LED-12 / D-22: revert re-publishes retained ambient state/* for exactly the
    affected cubes (not all cubes) and removes its registry entry.

    The sleep is injected as asyncio.sleep with a near-zero (0) delay so the
    test completes without real 180s waits.
    """
    client = _make_mqtt_client()
    registry = HighlightRegistry()

    # The affected cubes from LOCATE_BODY_A: primary (1,0,0) + span (1,0,1)
    affected_cubes = [
        {"unit_id": 1, "row": 0, "col": 0},
        {"unit_id": 1, "row": 0, "col": 1},
    ]

    async def instant_sleep(_: float) -> None:
        # Yield control so the task actually runs, but don't wait.
        await asyncio.sleep(0)

    highlight_id = "test-revert-id"

    # Schedule a revert task with near-zero delay.
    task = asyncio.create_task(
        schedule_revert(
            registry,
            client,
            SETTINGS_CACHE,
            highlight_id=highlight_id,
            cubes=affected_cubes,
            delay_seconds=0,
            sleep=instant_sleep,
        )
    )
    registry.add(highlight_id, task, affected_cubes)

    # Let the revert task run.
    await asyncio.sleep(0)
    await task

    # Verify: registry entry was removed.
    assert len(registry) == 0, f"Registry should be empty after revert; got {len(registry)}"

    # Verify: ambient state/* was published for exactly the 2 affected cubes.
    publish_calls = client.publish.call_args_list
    state_calls = [c for c in publish_calls if f"{TEST_PREFIX}/state/" in c[0][0]]
    assert len(state_calls) == 2, (
        f"Expected 2 ambient state/* republishes for the 2 affected cubes; "
        f"got {len(state_calls)} (topics: {[c[0][0] for c in state_calls]})"
    )
    for sc in state_calls:
        kwargs = sc[1] if len(sc) > 1 else {}
        assert kwargs.get("retain") is True, "Ambient revert must be retain=True"


# ── Default-mode cancel-prior (LED-12 / D-22) ─────────────────────────────────


@pytest.mark.asyncio
async def test_default_mode_next_search_reverts_prior() -> None:
    """With retain_mode=false, a second illuminate cancels the first and reverts its cubes first.

    LED-12 / D-22: Default mode (retain_mode=false) — calling illuminate_with_lifecycle
    twice (different selections) must:
    1. Cancel the first highlight's pending revert task.
    2. Immediately revert the first selection's cubes to ambient (publish_ambient).
    3. Light the new selection.
    4. Leave exactly one highlight registered (the second one).
    """
    client = _make_mqtt_client()
    registry = HighlightRegistry()

    # Default mode — no retain.
    cache = dict(SETTINGS_CACHE)
    cache["led_highlight.retain_mode"] = "false"

    async def instant_sleep(_: float) -> None:
        """Never actually sleep — the revert should NOT fire while cancelled."""
        await asyncio.sleep(0)

    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        # First search.
        await illuminate_with_lifecycle(registry, client, cache, LOCATE_BODY_A, sleep=instant_sleep)
        assert len(registry) == 1, "After first illuminate, registry must have 1 entry"

        # Second search — must cancel first, revert first cubes, light new.
        await illuminate_with_lifecycle(registry, client, cache, LOCATE_BODY_B, sleep=instant_sleep)

    # After second illuminate, only the NEW highlight should remain.
    assert len(registry) == 1, (
        f"Default mode: after second search only 1 highlight should be registered; "
        f"got {len(registry)}"
    )

    # Verify ambient was re-published for the first selection's cubes before the new one lit.
    # LOCATE_BODY_A's cubes are: (1,0,0) and (1,0,1).
    publish_calls = client.publish.call_args_list
    state_topics = [c[0][0] for c in publish_calls if f"{TEST_PREFIX}/state/" in c[0][0]]
    # The first selection cubes should appear as state/* ambient publishes (the revert).
    first_cube_topic = f"{TEST_PREFIX}/state/1/0/0"
    assert first_cube_topic in state_topics, (
        f"Expected ambient revert for first selection cube {first_cube_topic!r}; "
        f"topics seen: {state_topics}"
    )


# ── Retain mode accumulate (LED-13 / D-23) ────────────────────────────────────


@pytest.mark.asyncio
async def test_retain_mode_accumulates() -> None:
    """With led_highlight.retain_mode=true, two illuminate calls leave TWO highlights registered.

    LED-13 / D-23: Retain mode — each search ADDS a lit location; no prior highlight
    is cancelled. Each schedules its own independent revert keyed retain_ttl_seconds.
    The second call does NOT revert the first's cubes.
    """
    client = _make_mqtt_client()
    registry = HighlightRegistry()

    cache = dict(SETTINGS_CACHE)
    cache["led_highlight.retain_mode"] = "true"
    cache["led_highlight.retain_ttl_seconds"] = "900"

    # Use a never-yielding sleep so revert tasks do not fire during this test.
    # The revert tasks are cancelled explicitly at the end.
    async def blocking_sleep(_: float) -> None:
        """Block without yielding — revert tasks will never fire on their own."""
        # Use Event.wait() so cancellation works properly.
        await asyncio.Event().wait()

    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await illuminate_with_lifecycle(
            registry, client, cache, LOCATE_BODY_A, sleep=blocking_sleep
        )
        await illuminate_with_lifecycle(
            registry, client, cache, LOCATE_BODY_B, sleep=blocking_sleep
        )

    # Both highlights must remain registered.
    assert len(registry) == 2, (
        f"Retain mode: both highlights must remain registered; got {len(registry)}"
    )

    # Verify: the first selection cubes must NOT have been reverted to ambient before the
    # second search (no premature revert of LOCATE_BODY_A's cubes).
    # Count ambient state/* publishes for the first cube — should have 0 (no revert yet).
    publish_calls = client.publish.call_args_list
    # Any state/* publish for (1,0,0) that is a revert (ambient brightness=40) should not exist.
    first_cube_state = f"{TEST_PREFIX}/state/1/0/0"
    first_cube_ambient_calls = [
        c
        for c in publish_calls
        if c[0][0] == first_cube_state
        and "brightness" in json.loads(c[0][1])
        and json.loads(c[0][1])["brightness"] == int(cache["led_brightness.ambient"])
    ]
    assert len(first_cube_ambient_calls) == 0, (
        f"Retain mode: first highlight's cubes must NOT be reverted before TTL; "
        f"found {len(first_cube_ambient_calls)} ambient reverts for {first_cube_state!r}"
    )

    # Cleanup: cancel the pending revert tasks to avoid asyncio warnings.
    for _, entry in registry.items():
        entry.task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await entry.task


# ── Registry leak guard (security) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_completed_revert_removes_registry_entry() -> None:
    """After a revert fires, the registry has no entry for that highlight_id.

    Security: the registry must be bounded and leak-free; each completed/cancelled
    revert task pops its own entry.
    """
    client = _make_mqtt_client()
    registry = HighlightRegistry()

    affected_cubes = [{"unit_id": 1, "row": 0, "col": 0}]
    highlight_id = "test-leak-guard"

    async def instant_sleep(_: float) -> None:
        await asyncio.sleep(0)

    task = asyncio.create_task(
        schedule_revert(
            registry,
            client,
            SETTINGS_CACHE,
            highlight_id=highlight_id,
            cubes=affected_cubes,
            delay_seconds=0,
            sleep=instant_sleep,
        )
    )
    registry.add(highlight_id, task, affected_cubes)

    assert len(registry) == 1, "Registry must have 1 entry before revert fires"

    await asyncio.sleep(0)
    await task

    assert len(registry) == 0, f"Registry must be empty after revert completes; got {len(registry)}"
    assert registry.pop(highlight_id) is None, "pop on missing id must return None (idempotent)"


@pytest.mark.asyncio
async def test_cancel_and_revert_all_clears_registry() -> None:
    """cancel_and_revert_all cancels every pending task and empties the registry.

    Security / shutdown leak guard: all pending revert tasks must be cancelled
    and the registry emptied on shutdown (D-22).
    """
    client = _make_mqtt_client()
    registry = HighlightRegistry()

    # Seed registry with two never-completing tasks (large delay).
    long_sleep_called = []

    async def long_sleep(seconds: float) -> None:
        long_sleep_called.append(seconds)
        # Actually wait forever — we expect cancellation.
        await asyncio.sleep(3600)

    # Add two highlight entries with long-running tasks.
    cubes_a = [{"unit_id": 1, "row": 0, "col": 0}]
    cubes_b = [{"unit_id": 1, "row": 1, "col": 1}]

    task_a = asyncio.create_task(
        schedule_revert(
            registry,
            client,
            SETTINGS_CACHE,
            highlight_id="id-a",
            cubes=cubes_a,
            delay_seconds=3600,
            sleep=long_sleep,
        )
    )
    registry.add("id-a", task_a, cubes_a)

    task_b = asyncio.create_task(
        schedule_revert(
            registry,
            client,
            SETTINGS_CACHE,
            highlight_id="id-b",
            cubes=cubes_b,
            delay_seconds=3600,
            sleep=long_sleep,
        )
    )
    registry.add("id-b", task_b, cubes_b)

    assert len(registry) == 2

    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await cancel_and_revert_all(registry, client, SETTINGS_CACHE)

    assert len(registry) == 0, (
        f"Registry must be empty after cancel_and_revert_all; got {len(registry)}"
    )
    assert task_a.cancelled() or task_a.done(), "Task A must be cancelled or done"
    assert task_b.cancelled() or task_b.done(), "Task B must be cancelled or done"


# ── Degraded mode ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifecycle_degraded_no_raise() -> None:
    """Every lifecycle function with client=None returns without raising.

    D-22 degraded posture: a broker hiccup must never crash the lifecycle.
    """
    registry = HighlightRegistry()
    cubes = [{"unit_id": 1, "row": 0, "col": 0}]

    async def instant_sleep(_: float) -> None:
        await asyncio.sleep(0)

    # publish_ambient with client=None
    pool = _make_pool_with_one_unit()
    result = await publish_ambient(None, pool, SETTINGS_CACHE)
    assert result == 0, f"publish_ambient(client=None) must return 0; got {result}"

    # illuminate_with_lifecycle with client=None
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await illuminate_with_lifecycle(
            registry, None, SETTINGS_CACHE, LOCATE_BODY_A, sleep=instant_sleep
        )

    # schedule_revert with client=None
    highlight_id = "degraded-test"
    task = asyncio.create_task(
        schedule_revert(
            registry,
            None,
            SETTINGS_CACHE,
            highlight_id=highlight_id,
            cubes=cubes,
            delay_seconds=0,
            sleep=instant_sleep,
        )
    )
    registry.add(highlight_id, task, cubes)
    await asyncio.sleep(0)
    await task  # must not raise

    # cancel_and_revert_all with client=None
    registry2 = HighlightRegistry()
    task2 = asyncio.create_task(asyncio.sleep(3600))
    registry2.add("x", task2, cubes)
    with (
        patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX),
        patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400),
    ):
        await cancel_and_revert_all(registry2, None, SETTINGS_CACHE)
    assert len(registry2) == 0, "cancel_and_revert_all(client=None) must empty registry"

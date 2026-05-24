"""Unit tests for LED admin endpoints and publisher functions.

Nyquist Wave-0 scaffold — Phase 6: LED Contract over MQTT (Hardware Stubbed)

Covers: LED-06 (all-off retained-clear, idempotency), LED-07 (diagnostic sequence,
status subscribe, correct brightness tiers), DEP-03 (degraded mode), T-06-12
(admin-gating on both endpoints).

Tests use a stub aiomqtt client (AsyncMock recording publish/subscribe/unsubscribe)
and a mocked pool returning a minimal units set (one unit: id=1, rows=2, cols=2 → 4 cubes).

Publisher-level tests call publishers.publish_all_off / publishers.run_diagnostic
directly with the stub; endpoint-level tests use httpx AsyncClient against the app.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── Shared test constants ─────────────────────────────────────────────────────

TEST_PREFIX = "gruvax/v1/dev/leds"

# Minimal unit set: one unit, 2×2 grid → 4 cubes
# Each row returned by `fetchall` is a 3-tuple: (id, rows, cols)
UNITS_ROWS = [(1, 2, 2)]  # unit_id=1, rows=2, cols=2

# Settings cache with all keys used by publish_all_off / run_diagnostic
SETTINGS_CACHE: dict[str, Any] = {
    # Colors (stored as JSON strings in DB; publishers strip quotes)
    "led_color.position": '"#FFD700"',
    "led_color.label_span": '"#7C3AED"',
    "led_color.error": '"#E63946"',
    "led_color.setup": '"#0077B6"',
    "led_color.all_off": '"#000000"',
    "led_color.ambient": '"#0051A2"',
    # Brightness tiers (D-24 naming)
    "led_brightness.span": "128",    # label-span tier
    "led_brightness.active": "255",  # position tier
    "led_brightness.ambient": "40",  # idle baseline — NOT used for active sequence
    # Diagnostic parameters
    "led_diagnostic.inter_cube_ms": "50",  # low for fast tests
}


# ── Pool mock factory ─────────────────────────────────────────────────────────


def _make_pool(units: list[tuple[int, int, int]] = UNITS_ROWS) -> Any:
    """Return a mock pool whose cursor returns `units` from fetchall.

    The pool supports the async context-manager pattern:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
    """
    mock_cursor = AsyncMock()
    mock_cursor.execute = AsyncMock(return_value=None)
    mock_cursor.fetchall = AsyncMock(return_value=units)
    mock_cursor.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor.__aexit__ = AsyncMock(return_value=None)

    mock_conn = AsyncMock()
    mock_conn.cursor = MagicMock(return_value=mock_cursor)
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=None)

    mock_pool = MagicMock()
    mock_pool.connection = MagicMock(return_value=mock_conn)
    return mock_pool


# ── MQTT client mock factory ──────────────────────────────────────────────────


def _make_mqtt_client() -> AsyncMock:
    """Return an AsyncMock that mimics aiomqtt.Client.publish/subscribe/unsubscribe."""
    client = AsyncMock()
    client.publish = AsyncMock(return_value=None)
    client.subscribe = AsyncMock(return_value=None)
    client.unsubscribe = AsyncMock(return_value=None)

    # messages is an async iterable that immediately StopAsyncIteration (no hardware)
    async def _empty_messages() -> Any:
        return
        yield  # make it an async generator

    client.messages = _empty_messages()
    return client


# ── Publisher-level tests: publish_all_off ────────────────────────────────────


@pytest.mark.asyncio
async def test_all_off() -> None:
    """publish_all_off publishes b'' with retain=True to every state/{id}/{r}/{c}
    topic plus one command on all/off (LED-06, D-11).

    For units=[(1, 2, 2)] → 4 state clears (state/1/0/0, state/1/0/1,
    state/1/1/0, state/1/1/1) + 1 all/off command = 5 total publishes.
    """
    from gruvax.mqtt import publishers, topics

    client = _make_mqtt_client()
    pool = _make_pool()

    with patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX), \
         patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400):
        count = await publishers.publish_all_off(client, pool, SETTINGS_CACHE)

    # 4 cubes → 4 state clears
    assert count == 4, f"Expected 4 published; got {count}"

    published_topics = [c[0][0] for c in client.publish.call_args_list]

    # Each state clear must use payload=b'' and retain=True
    for r in range(2):
        for c in range(2):
            t = topics.state_topic(TEST_PREFIX, 1, r, c)
            assert t in published_topics, f"Expected {t!r} in published topics"

    # Verify the state clears use b'' payload + retain=True
    state_calls = [
        c for c in client.publish.call_args_list
        if f"{TEST_PREFIX}/state/" in c[0][0]
    ]
    assert len(state_calls) == 4, f"Expected 4 state clear publishes; got {len(state_calls)}"
    for c in state_calls:
        payload = c[0][1]
        kwargs = c[1] if len(c) > 1 else {}
        assert payload == b'', f"State clear payload must be b''; got {payload!r}"
        assert kwargs.get("retain") is True, f"State clear must be retained; got retain={kwargs.get('retain')}"
        assert kwargs.get("qos") == 1, f"State clear must use qos=1; got qos={kwargs.get('qos')}"

    # Verify the all/off command topic is published (retain=False, not retained)
    all_off_t = topics.all_off_topic(TEST_PREFIX)
    assert all_off_t in published_topics, f"Expected {all_off_t!r} in {published_topics}"

    all_off_calls = [c for c in client.publish.call_args_list if c[0][0] == all_off_t]
    assert len(all_off_calls) == 1, f"Expected exactly 1 all/off command; got {len(all_off_calls)}"
    all_off_kwargs = all_off_calls[0][1] if len(all_off_calls[0]) > 1 else {}
    assert all_off_kwargs.get("retain") is not True, (
        f"all/off command must NOT be retained; got retain={all_off_kwargs.get('retain')}"
    )


@pytest.mark.asyncio
async def test_all_off_idempotent() -> None:
    """Calling publish_all_off twice produces the same set of clear publishes both
    times — no error raised, idempotent (D-11).
    """
    from gruvax.mqtt import publishers

    client = _make_mqtt_client()
    pool = _make_pool()

    with patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX), \
         patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400):
        count1 = await publishers.publish_all_off(client, pool, SETTINGS_CACHE)
        # Reset mock to count second call independently
        client.publish.reset_mock()
        # Re-set the mock pool for second call
        pool2 = _make_pool()
        count2 = await publishers.publish_all_off(client, pool2, SETTINGS_CACHE)

    assert count1 == count2, f"Idempotent: both calls must return same count; got {count1} vs {count2}"
    assert count2 == 4, f"Expected 4 on second call; got {count2}"


@pytest.mark.asyncio
async def test_all_off_uses_units_table() -> None:
    """publish_all_off fetches cubes from gruvax.units (no hardcoded N).

    Assert the SQL fetch hits gruvax.units — verified via the mocked cursor
    receiving the units SELECT.
    """
    from gruvax.mqtt import publishers

    client = _make_mqtt_client()
    pool = _make_pool()

    with patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX), \
         patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400):
        await publishers.publish_all_off(client, pool, SETTINGS_CACHE)

    # The mock cursor's execute must have been called with a SQL containing gruvax.units
    mock_conn = pool.connection.return_value
    mock_cursor = mock_conn.cursor.return_value
    execute_calls = mock_cursor.execute.call_args_list
    assert len(execute_calls) >= 1, "Expected at least one SQL execute call"
    sql_arg = execute_calls[0][0][0]
    assert "gruvax.units" in sql_arg, (
        f"SQL must query gruvax.units; got {sql_arg!r}"
    )


# ── Publisher-level tests: run_diagnostic ────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnostic_sequence() -> None:
    """run_diagnostic publishes the 5-state color sequence for each cube.

    For units=[(1, 2, 2)] → 4 cubes × 5 states = 20 state publishes.
    Plus 1 subscribe + 1 unsubscribe to status/# (LED-07, D-09).
    """
    from gruvax.mqtt import publishers

    client = _make_mqtt_client()
    pool = _make_pool()

    with patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX), \
         patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400):
        await publishers.run_diagnostic(client, pool, SETTINGS_CACHE, run_id="test-run-001")

    publish_calls = client.publish.call_args_list
    state_publishes = [c for c in publish_calls if f"{TEST_PREFIX}/state/" in c[0][0]]

    # 4 cubes × 5 states = 20 state publishes
    expected_publish_count = 4 * 5  # cubes × states
    assert len(state_publishes) == expected_publish_count, (
        f"Expected {expected_publish_count} state publishes; got {len(state_publishes)}"
    )


@pytest.mark.asyncio
async def test_diagnostic_uses_correct_brightness_tiers() -> None:
    """run_diagnostic's label-span state uses led_brightness.span and the position
    state uses led_brightness.active — never led_brightness.ambient (D-24).

    Uses distinct values so we can verify which tier is used per state.
    """
    from gruvax.mqtt import publishers
    import json as _json

    client = _make_mqtt_client()
    pool = _make_pool()

    # Distinct values for each tier so we can verify
    cache = dict(SETTINGS_CACHE)
    cache["led_brightness.span"] = "111"    # label-span tier — only used for span state
    cache["led_brightness.active"] = "222"  # position/active tier — used for position state
    cache["led_brightness.ambient"] = "9"   # idle baseline — must NOT appear in diagnostic

    with patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX), \
         patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400):
        await publishers.run_diagnostic(client, pool, cache, run_id="test-tier-001")

    publish_calls = client.publish.call_args_list
    state_publishes = [c for c in publish_calls if f"{TEST_PREFIX}/state/" in c[0][0]]

    brightnesses_seen: list[int] = []
    for c in state_publishes:
        payload_bytes = c[0][1]
        if not payload_bytes:
            continue  # off state has empty or brightness=0 payload
        try:
            payload = _json.loads(payload_bytes)
            b = payload.get("brightness", -1)
            brightnesses_seen.append(b)
        except Exception:
            pass

    # ambient tier value (9) must NOT appear in any diagnostic publish
    assert 9 not in brightnesses_seen, (
        f"D-24 violation: led_brightness.ambient (9) must not be used in diagnostic sequence; "
        f"brightnesses seen: {brightnesses_seen}"
    )

    # span tier (111) must appear (label-span state)
    assert 111 in brightnesses_seen, (
        f"D-24 violation: led_brightness.span (111) must appear in diagnostic sequence; "
        f"brightnesses seen: {brightnesses_seen}"
    )

    # active tier (222) must appear (position state)
    assert 222 in brightnesses_seen, (
        f"D-24 violation: led_brightness.active (222) must appear in diagnostic sequence; "
        f"brightnesses seen: {brightnesses_seen}"
    )


@pytest.mark.asyncio
async def test_diagnostic_status_subscribe() -> None:
    """run_diagnostic subscribes to status_wildcard and unsubscribes in finally,
    timing out gracefully with no status messages (D-10).
    """
    from gruvax.mqtt import publishers, topics

    client = _make_mqtt_client()
    pool = _make_pool()

    with patch("gruvax.settings.settings.MQTT_TOPIC_PREFIX", TEST_PREFIX), \
         patch("gruvax.settings.settings.MQTT_STATE_EXPIRY_SECONDS", 14400):
        await publishers.run_diagnostic(client, pool, SETTINGS_CACHE, run_id="test-sub-001")

    expected_wildcard = topics.status_wildcard(TEST_PREFIX)

    # Subscribe must have been called exactly once with the status wildcard
    client.subscribe.assert_called_once_with(expected_wildcard, qos=1)

    # Unsubscribe must have been called exactly once (in finally)
    client.unsubscribe.assert_called_once_with(expected_wildcard)


# ── Publisher-level tests: degraded mode ─────────────────────────────────────


@pytest.mark.asyncio
async def test_publishers_degraded() -> None:
    """publish_all_off / run_diagnostic with client=None return without raising (Pitfall C)."""
    from gruvax.mqtt import publishers

    pool = _make_pool()

    # publish_all_off with client=None — must return 0 without raising
    count = await publishers.publish_all_off(None, pool, SETTINGS_CACHE)
    assert count == 0, f"Expected 0 in degraded mode; got {count}"

    # run_diagnostic with client=None — must return without raising
    pool2 = _make_pool()
    await publishers.run_diagnostic(None, pool2, SETTINGS_CACHE, run_id="degraded-001")
    # No assertion needed — just must not raise


# ── App factory for endpoint tests ───────────────────────────────────────────

import os


async def _stub_require_admin() -> dict[str, str]:
    """FastAPI dependency override that bypasses authentication for endpoint tests."""
    return {"session_id": "test-session-id"}


def _make_app_with_mqtt(mqtt_client: Any | None) -> Any:
    """Create a fresh app instance with the given MQTT client on state.

    Uses FastAPI dependency_overrides (not patch) to bypass require_admin and
    get_pool — the canonical pattern from test_admin_led_settings.py.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.api.deps import get_pool, require_admin
    from gruvax.app import create_app

    app = create_app()
    app.state.mqtt = mqtt_client
    app.state.mqtt_ok = mqtt_client is not None
    app.state.settings_cache = dict(SETTINGS_CACHE)
    app.state.db_pool = _make_pool()

    # Override require_admin to skip session/CSRF verification
    app.dependency_overrides[require_admin] = _stub_require_admin

    # Override get_pool to return our mock pool
    mock_pool = _make_pool()

    async def _stub_get_pool() -> Any:
        return mock_pool

    app.dependency_overrides[get_pool] = _stub_get_pool

    return app


# ── Endpoint-level tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_off_endpoint_requires_admin() -> None:
    """POST /api/admin/leds/off without admin override returns 401 (T-06-12, access control).

    Uses a fresh app with NO dependency overrides so require_admin is real.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app

    app = create_app()
    app.state.mqtt = AsyncMock()
    app.state.mqtt_ok = True
    app.state.settings_cache = {}
    app.state.db_pool = _make_pool()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/admin/leds/off")

    assert res.status_code in (401, 403), (
        f"Expected 401/403 for unauthenticated leds/off; got {res.status_code}: {res.text}"
    )


@pytest.mark.asyncio
async def test_diagnostic_endpoint_returns_run_id() -> None:
    """POST /api/admin/leds/diagnostic (with admin session via override) returns 200 with
    {"run_id": ..., "started_at": ...} immediately (D-08 — instant ack).
    """
    from gruvax.mqtt import publishers

    app = _make_app_with_mqtt(AsyncMock())

    with patch.object(publishers, "run_diagnostic", new=AsyncMock(return_value=None)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            res = await client.post("/api/admin/leds/diagnostic")

    assert res.status_code == 200, (
        f"Expected 200; got {res.status_code}: {res.text}"
    )
    body = res.json()
    assert "run_id" in body, f"Response must contain run_id; got {body}"
    assert "started_at" in body, f"Response must contain started_at; got {body}"
    assert body["run_id"]  # non-empty


@pytest.mark.asyncio
async def test_off_endpoint_degraded() -> None:
    """With app.state.mqtt=None, POST /api/admin/leds/off returns 200 {"published": 0}
    without raising (Pitfall C, DEP-03).
    """
    app = _make_app_with_mqtt(None)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post("/api/admin/leds/off")

    assert res.status_code == 200, (
        f"Expected 200 in degraded mode; got {res.status_code}: {res.text}"
    )
    body = res.json()
    assert body.get("published") == 0, (
        f"Degraded mode must return published=0; got {body}"
    )

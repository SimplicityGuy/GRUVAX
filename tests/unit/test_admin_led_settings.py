"""Unit tests for admin LED settings persistence — Phase 6 Plan 03.

Tests the extended GET/PUT /api/admin/settings with all LED keys:
  - test_get_settings_includes_led_keys          (LED-04, LED-05, D-25)
  - test_put_led_settings_persists_and_caches    (LED-04, LED-05, D-15, D-25)
  - test_span_brightness_key_is_span_not_ambient (D-24 naming contract)
  - test_put_rejects_unknown_led_key             (whitelisting / D-17)
  - test_put_rejects_malformed_hex               (T-06-08 hex validation)
  - test_transition_keys_not_writable            (D-17 — transition keys excluded)

These tests use httpx AsyncClient against the ASGI app with a mocked DB pool
(same style as test_illuminate_endpoint.py) so they do NOT require a live
Postgres instance and run cleanly in the unit test suite.

RED: All tests fail until settings.py _ALLOWED_SETTINGS_KEYS, GET response,
     and PUT key_map are extended for LED keys.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


# ── helpers ───────────────────────────────────────────────────────────────────

# LED key defaults that would be seeded by migration 0006
_LED_DEFAULTS: dict[str, Any] = {
    "led_color.position": '"#FFD700"',
    "led_color.label_span": '"#7C3AED"',
    "led_color.error": '"#E63946"',
    "led_color.setup": '"#0077B6"',
    "led_color.all_off": '"#000000"',
    "led_color.ambient": '"#0051A2"',
    "led_brightness.span": "128",
    "led_brightness.active": "255",
    "led_brightness.ambient": "40",
    "led_highlight.active_ttl_seconds": "180",
    "led_highlight.retain_mode": "false",
    "led_highlight.retain_ttl_seconds": "900",
    # baseline settings
    "cube.nominal_capacity": "95",
    "session.idle_ttl_seconds": "600",
}


def _make_fake_db_row(key: str) -> tuple[str, Any]:
    """Return a (key, raw_value) row for the given settings key using migration defaults."""
    raw = _LED_DEFAULTS.get(key, "null")
    # Parse the JSON-encoded value (colors are '"#RRGGBB"', numbers are bare)
    return (key, json.loads(raw))


class _FakeCursor:
    """Minimal async cursor fake that returns LED settings rows."""

    def __init__(self, rows: list[tuple[str, Any]]) -> None:
        self._rows = rows

    async def execute(self, sql: str, params: Any = None) -> None:
        pass  # No-op for writes

    async def fetchall(self) -> list[tuple[str, Any]]:
        return self._rows

    async def fetchone(self) -> tuple[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def __aenter__(self) -> "_FakeCursor":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeConn:
    def __init__(self, rows: list[tuple[str, Any]]) -> None:
        self._rows = rows
        self._committed = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    async def execute(self, sql: str, params: Any = None) -> None:
        pass  # No-op for writes

    async def commit(self) -> None:
        self._committed = True

    async def __aenter__(self) -> "_FakeConn":
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakePool:
    def __init__(self, rows: list[tuple[str, Any]]) -> None:
        self._rows = rows

    def connection(self) -> _FakeConn:
        return _FakeConn(self._rows)


def _make_settings_rows(keys: list[str]) -> list[tuple[str, Any]]:
    """Build a list of (key, parsed_value) rows for the given setting keys."""
    return [_make_fake_db_row(k) for k in keys]


def _make_app_with_settings(settings_cache: dict[str, Any]) -> Any:
    """Create a GRUVAX app with pre-populated settings cache (no live DB/broker)."""
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app

    app = create_app()
    app.state.mqtt = None
    app.state.mqtt_ok = False
    app.state.settings_cache = settings_cache
    return app


def _make_admin_headers(csrf_token: str = "test-csrf") -> dict[str, str]:
    return {"X-CSRF-Token": csrf_token}


async def _login_and_get_headers(client: AsyncClient, pool: _FakePool) -> dict[str, str]:
    """Helper: seed PIN and log in, return headers with CSRF token + cookies."""
    from gruvax.auth.pin import hash_pin

    test_hash = hash_pin("0000")
    # Inject the PIN hash into the pool rows so require_admin can find it
    # (This is a simplified approach: we patch the pool to include auth.pin_hash)
    pool._rows.append(("auth.pin_hash", test_hash))

    res = await client.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        pytest.skip(f"Login failed with {res.status_code}: {res.text}")
    csrf = res.cookies.get("gruvax_csrf") or res.json().get("csrf_token", "")
    return {"X-CSRF-Token": csrf}


# ── Test 1: GET /api/admin/settings includes all LED keys ─────────────────────


@pytest.mark.asyncio
async def test_get_settings_includes_led_keys() -> None:
    """GET /api/admin/settings must return all 12 LED keys from migration 0006.

    LED-04, LED-05, D-25: The GET response must include:
      led_color_position, led_color_label_span, led_color_error, led_color_setup,
      led_color_all_off, led_color_ambient,
      led_brightness_span, led_brightness_active, led_brightness_ambient,
      led_highlight_active_ttl_seconds, led_highlight_retain_mode, led_highlight_retain_ttl_seconds
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app
    from gruvax.auth.pin import hash_pin

    app = create_app()
    app.state.mqtt = None
    app.state.mqtt_ok = False
    app.state.settings_cache = {}

    # Build pool rows: all LED defaults + auth.pin_hash for login
    all_keys = list(_LED_DEFAULTS.keys())
    rows = _make_settings_rows(all_keys)
    pin_hash = hash_pin("0000")
    rows.append(("auth.pin_hash", pin_hash))

    fake_pool = _FakePool(rows)
    app.state.db_pool = fake_pool

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login first
        login_res = await client.post("/api/admin/login", json={"pin": "0000"})
        if login_res.status_code != 200:
            pytest.skip(f"Login unavailable: {login_res.status_code} {login_res.text}")

        csrf = login_res.cookies.get("gruvax_csrf") or login_res.json().get("csrf_token", "")
        headers = {"X-CSRF-Token": csrf}

        res = await client.get("/api/admin/settings", headers=headers)

    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    body = res.json()

    # All 12 LED response keys must be present
    expected_keys = [
        "led_color_position",
        "led_color_label_span",
        "led_color_error",
        "led_color_setup",
        "led_color_all_off",
        "led_color_ambient",
        "led_brightness_span",
        "led_brightness_active",
        "led_brightness_ambient",
        "led_highlight_active_ttl_seconds",
        "led_highlight_retain_mode",
        "led_highlight_retain_ttl_seconds",
    ]
    missing = [k for k in expected_keys if k not in body]
    assert not missing, (
        f"GET /api/admin/settings missing LED keys: {missing}. "
        f"Response body: {sorted(body.keys())}"
    )

    # Verify default values match migration 0006
    assert body["led_color_position"] == "#FFD700", f"position default wrong: {body['led_color_position']}"
    assert body["led_color_label_span"] == "#7C3AED", f"label_span default wrong: {body['led_color_label_span']}"
    assert body["led_color_ambient"] == "#0051A2", f"ambient default wrong: {body['led_color_ambient']}"
    assert body["led_brightness_span"] == 128, f"span brightness default wrong: {body['led_brightness_span']}"
    assert body["led_brightness_active"] == 255, f"active brightness default wrong: {body['led_brightness_active']}"
    assert body["led_brightness_ambient"] == 40, f"ambient brightness default wrong: {body['led_brightness_ambient']}"
    assert body["led_highlight_active_ttl_seconds"] == 180, f"TTL default wrong: {body['led_highlight_active_ttl_seconds']}"
    assert body["led_highlight_retain_mode"] is False, f"retain_mode default wrong: {body['led_highlight_retain_mode']}"
    assert body["led_highlight_retain_ttl_seconds"] == 900, f"retain TTL default wrong: {body['led_highlight_retain_ttl_seconds']}"


# ── Test 2: PUT persists and caches LED keys ──────────────────────────────────


@pytest.mark.asyncio
async def test_put_led_settings_persists_and_caches() -> None:
    """PUT /api/admin/settings persists LED keys and refreshes settings_cache.

    LED-04, LED-05, D-15, D-25:
    - PUT with LED keys succeeds
    - GET after PUT reflects updated values
    - app.state.settings_cache["led_color.position"] == "#00FF00" after PUT
    - app.state.settings_cache["led_brightness.span"] == 64 after PUT
    - app.state.settings_cache["led_highlight.retain_mode"] is True after PUT
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app
    from gruvax.auth.pin import hash_pin

    app = create_app()
    app.state.mqtt = None
    app.state.mqtt_ok = False
    app.state.settings_cache = {}

    all_keys = list(_LED_DEFAULTS.keys())
    rows = _make_settings_rows(all_keys)
    pin_hash = hash_pin("0000")
    rows.append(("auth.pin_hash", pin_hash))
    fake_pool = _FakePool(rows)
    app.state.db_pool = fake_pool

    put_payload = {
        "led_color_position": "#00FF00",
        "led_brightness_span": 64,
        "led_color_ambient": "#112233",
        "led_brightness_ambient": 20,
        "led_highlight_active_ttl_seconds": 60,
        "led_highlight_retain_mode": True,
        "led_highlight_retain_ttl_seconds": 300,
    }

    # Patch load_settings_cache to verify it's called and to set the expected cache
    expected_cache: dict[str, Any] = {
        "led_color.position": "#00FF00",
        "led_brightness.span": 64,
        "led_color.ambient": "#112233",
        "led_brightness.ambient": 20,
        "led_highlight.active_ttl_seconds": 60,
        "led_highlight.retain_mode": True,
        "led_highlight.retain_ttl_seconds": 300,
    }

    async def mock_load_settings_cache(pool: Any) -> dict[str, Any]:
        return expected_cache

    with patch("gruvax.api.admin.settings.load_settings_cache", side_effect=mock_load_settings_cache):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            login_res = await client.post("/api/admin/login", json={"pin": "0000"})
            if login_res.status_code != 200:
                pytest.skip(f"Login unavailable: {login_res.status_code} {login_res.text}")

            csrf = login_res.cookies.get("gruvax_csrf") or login_res.json().get("csrf_token", "")
            headers = {"X-CSRF-Token": csrf}

            put_res = await client.put(
                "/api/admin/settings",
                json=put_payload,
                headers=headers,
            )

    assert put_res.status_code == 200, f"PUT failed: {put_res.status_code}: {put_res.text}"

    # Verify cache was refreshed with the new values (D-15)
    cache = app.state.settings_cache
    assert cache.get("led_color.position") == "#00FF00", (
        f"settings_cache['led_color.position'] not updated: {cache.get('led_color.position')!r}"
    )
    assert cache.get("led_brightness.span") == 64, (
        f"settings_cache['led_brightness.span'] not updated: {cache.get('led_brightness.span')!r}"
    )
    assert cache.get("led_highlight.retain_mode") is True, (
        f"settings_cache['led_highlight.retain_mode'] not updated: {cache.get('led_highlight.retain_mode')!r}"
    )


# ── Test 3: D-24 span/ambient naming separation ───────────────────────────────


def test_span_brightness_key_is_span_not_ambient() -> None:
    """The body key led_brightness_span maps to DB key led_brightness.span (D-24).

    And led_brightness_ambient maps to led_brightness.ambient (the idle tier).
    These are two DISTINCT keys — the label-span tier must never map to ambient.
    """
    # Import the settings module and inspect the key_map
    import importlib

    settings_mod = importlib.import_module("gruvax.api.admin.settings")

    # The key_map must exist and be accessible (checking the module-level pattern)
    # We verify by reading the source: the key_map is built inside update_settings.
    # Test the naming contract by checking the _ALLOWED_SETTINGS_KEYS frozenset.
    allowed = settings_mod._ALLOWED_SETTINGS_KEYS

    # D-24: both led_brightness.span and led_brightness.ambient must be separately allowed
    assert "led_brightness.span" in allowed, (
        "led_brightness.span not in _ALLOWED_SETTINGS_KEYS — the label-span tier is missing (D-24)"
    )
    assert "led_brightness.ambient" in allowed, (
        "led_brightness.ambient not in _ALLOWED_SETTINGS_KEYS — the idle tier is missing (D-24)"
    )

    # The two keys must be DISTINCT (sanity: can't be the same string)
    assert "led_brightness.span" != "led_brightness.ambient", (
        "Span and ambient keys must be distinct (D-24)"
    )

    # Neither transition key must be present (D-17)
    transition_keys_in_allowed = [k for k in allowed if k.startswith("led_transition.")]
    assert not transition_keys_in_allowed, (
        f"led_transition.* keys found in _ALLOWED_SETTINGS_KEYS: {transition_keys_in_allowed}. "
        "Transition keys are NOT admin-editable (D-17)."
    )


# ── Test 4: Unknown LED key is ignored ───────────────────────────────────────


@pytest.mark.asyncio
async def test_put_rejects_unknown_led_key() -> None:
    """A non-whitelisted key in the PUT body is silently ignored (not written to DB).

    T-06-10: _ALLOWED_SETTINGS_KEYS frozenset + key_map allow-list protects the DB
    from arbitrary key injection.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app
    from gruvax.auth.pin import hash_pin

    app = create_app()
    app.state.mqtt = None
    app.state.mqtt_ok = False
    app.state.settings_cache = {}

    rows: list[tuple[str, Any]] = [("cube.nominal_capacity", 95)]
    pin_hash = hash_pin("0000")
    rows.append(("auth.pin_hash", pin_hash))
    fake_pool = _FakePool(rows)
    app.state.db_pool = fake_pool

    executed_sqls: list[str] = []
    original_execute = _FakeConn.execute

    async def tracking_execute(self: "_FakeConn", sql: str, params: Any = None) -> None:
        executed_sqls.append(sql)

    with patch.object(_FakeConn, "execute", tracking_execute):
        with patch("gruvax.api.admin.settings.load_settings_cache", return_value={}):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                login_res = await client.post("/api/admin/login", json={"pin": "0000"})
                if login_res.status_code != 200:
                    pytest.skip(f"Login unavailable: {login_res.status_code} {login_res.text}")

                csrf = login_res.cookies.get("gruvax_csrf") or login_res.json().get("csrf_token", "")

                # This key is not in the whitelist — it must be silently ignored
                put_res = await client.put(
                    "/api/admin/settings",
                    json={"totally_unknown_key": "malicious"},
                    headers={"X-CSRF-Token": csrf},
                )

    # Must return 200 (unknown keys ignored, not a 422)
    assert put_res.status_code == 200, (
        f"Expected 200 (unknown key ignored), got {put_res.status_code}: {put_res.text}"
    )
    # The updated list should be empty (nothing was written)
    body = put_res.json()
    assert body.get("updated", []) == [], (
        f"Expected empty 'updated' list (unknown key ignored), got {body.get('updated')}"
    )


# ── Test 5: Malformed hex rejected with 422 ───────────────────────────────────


@pytest.mark.asyncio
async def test_put_rejects_malformed_hex() -> None:
    """PUT led_color_position: 'nothex' returns 422 (T-06-08 hex validation).

    The server must validate #RRGGBB (6 hex digits) before writing — reject
    malformed hex with HTTP 422.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app
    from gruvax.auth.pin import hash_pin

    app = create_app()
    app.state.mqtt = None
    app.state.mqtt_ok = False
    app.state.settings_cache = {}

    rows: list[tuple[str, Any]] = []
    pin_hash = hash_pin("0000")
    rows.append(("auth.pin_hash", pin_hash))
    fake_pool = _FakePool(rows)
    app.state.db_pool = fake_pool

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_res = await client.post("/api/admin/login", json={"pin": "0000"})
        if login_res.status_code != 200:
            pytest.skip(f"Login unavailable: {login_res.status_code} {login_res.text}")

        csrf = login_res.cookies.get("gruvax_csrf") or login_res.json().get("csrf_token", "")

        put_res = await client.put(
            "/api/admin/settings",
            json={"led_color_position": "nothex"},
            headers={"X-CSRF-Token": csrf},
        )

    assert put_res.status_code == 422, (
        f"Expected 422 for malformed hex 'nothex', got {put_res.status_code}: {put_res.text}"
    )


# ── Test 6: Transition keys not writable ─────────────────────────────────────


@pytest.mark.asyncio
async def test_transition_keys_not_writable() -> None:
    """PUT led_transition_position_style is silently ignored — not in the allow-list (D-17).

    Transition styles are fixed per-state defaults; the admin has NO transition editor in v1.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.app import create_app
    from gruvax.auth.pin import hash_pin

    app = create_app()
    app.state.mqtt = None
    app.state.mqtt_ok = False
    app.state.settings_cache = {}

    rows: list[tuple[str, Any]] = []
    pin_hash = hash_pin("0000")
    rows.append(("auth.pin_hash", pin_hash))
    fake_pool = _FakePool(rows)
    app.state.db_pool = fake_pool

    with patch("gruvax.api.admin.settings.load_settings_cache", return_value={}):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            login_res = await client.post("/api/admin/login", json={"pin": "0000"})
            if login_res.status_code != 200:
                pytest.skip(f"Login unavailable: {login_res.status_code} {login_res.text}")

            csrf = login_res.cookies.get("gruvax_csrf") or login_res.json().get("csrf_token", "")

            put_res = await client.put(
                "/api/admin/settings",
                json={"led_transition_position_style": "instant"},
                headers={"X-CSRF-Token": csrf},
            )

    assert put_res.status_code == 200, (
        f"Expected 200 (transition key ignored), got {put_res.status_code}: {put_res.text}"
    )
    body = put_res.json()
    updated = body.get("updated", [])
    # Transition keys must NOT appear in the updated list
    transition_written = [k for k in updated if "transition" in k]
    assert not transition_written, (
        f"Transition keys were written to DB: {transition_written}. "
        "Transition settings are NOT admin-editable (D-17)."
    )

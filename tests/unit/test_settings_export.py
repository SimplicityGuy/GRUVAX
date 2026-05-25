"""Unit tests for settings-export hard exclusion rules (D-14, BAK-02).

Tests the D-14 hard exclusion contract: auth.pin_hash must NEVER appear
in a serialized export payload (T-PIN-LEAK).

These tests are pure unit tests — they test the key-filtering logic
directly, without a live DB or HTTP client. Always runs GREEN on existing
code (the endpoint is not yet built but the _ALLOWED_SETTINGS_KEYS list
already exists and does not include auth.pin_hash).

Tests:
  - test_no_pin_in_export: 'auth.pin_hash' absent from _ALLOWED_SETTINGS_KEYS AND
    no key starts with 'auth.'
  - test_all_allowed_keys: all keys in _ALLOWED_SETTINGS_KEYS are present and
    representable (sanity check that the set was not accidentally emptied)
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio(loop_scope="session")
async def test_no_pin_in_export() -> None:
    """_ALLOWED_SETTINGS_KEYS must not contain auth.pin_hash or any auth.* key (D-14).

    This is the primary T-PIN-LEAK guard: the export endpoint uses only
    _ALLOWED_SETTINGS_KEYS to query the DB, so any key absent from the set
    is never serialized to a downloadable file.

    This test is always GREEN because _ALLOWED_SETTINGS_KEYS is pre-existing code
    (auth.pin_hash was never added to it). It acts as a regression guard.
    """
    from gruvax.api.admin.settings import _ALLOWED_SETTINGS_KEYS

    # Hard exclusion: auth.pin_hash must not be in the export allowlist
    assert "auth.pin_hash" not in _ALLOWED_SETTINGS_KEYS, (
        "SECURITY: auth.pin_hash must never appear in _ALLOWED_SETTINGS_KEYS (D-14, T-PIN-LEAK)"
    )

    # Broad exclusion: NO key starting with 'auth.' may be in the allowlist
    auth_keys = [k for k in _ALLOWED_SETTINGS_KEYS if k.startswith("auth.")]
    assert auth_keys == [], (
        f"SECURITY: No auth.* keys may be in _ALLOWED_SETTINGS_KEYS, found: {auth_keys}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_all_allowed_keys() -> None:
    """_ALLOWED_SETTINGS_KEYS contains all expected Phase 3 + Phase 6 keys.

    Verifies the allowlist is populated with the expected settings keys.
    Acts as a regression guard: if a key is accidentally removed from the set,
    export would silently omit it (breaking BAK-01 round-trip identity).
    """
    from gruvax.api.admin.settings import _ALLOWED_SETTINGS_KEYS

    # Phase 3 keys
    expected_phase3 = {
        "cube.nominal_capacity",
        "session.idle_ttl_seconds",
    }

    # Phase 6 LED color keys
    expected_led_colors = {
        "led_color.position",
        "led_color.label_span",
        "led_color.error",
        "led_color.setup",
        "led_color.all_off",
        "led_color.ambient",
    }

    # Phase 6 LED brightness/transition/highlight keys
    expected_led_lifecycle = {
        "led_brightness.span",
        "led_brightness.active",
        "led_brightness.ambient",
        "led_highlight.active_ttl_seconds",
        "led_highlight.retain_mode",
        "led_highlight.retain_ttl_seconds",
    }

    all_expected = expected_phase3 | expected_led_colors | expected_led_lifecycle

    missing = all_expected - _ALLOWED_SETTINGS_KEYS
    assert missing == set(), (
        f"Keys missing from _ALLOWED_SETTINGS_KEYS (BAK-01 regression guard): {missing}"
    )

    # Also assert the set is non-empty (guards against accidental clear())
    assert len(_ALLOWED_SETTINGS_KEYS) >= len(all_expected), (
        f"_ALLOWED_SETTINGS_KEYS has fewer keys than expected "
        f"(got {len(_ALLOWED_SETTINGS_KEYS)}, expected >= {len(all_expected)})"
    )

"""Admin settings endpoints for GRUVAX.

Endpoints:
  GET  /api/admin/settings      — return current settings (capacity, idle TTL, LED knobs)
  PUT  /api/admin/settings      — update whitelisted settings keys
  POST /api/admin/settings/pin  — change PIN (requires current PIN; revokes all other sessions)

Phase 3 scope: Change PIN + nominal capacity + idle timeout.
Phase 6 additions (LED-04, LED-05, D-15, D-24, D-25):
  LED color keys — per-state hex colors (position, label_span, error, setup, all_off, ambient)
  LED brightness keys — three distinct tiers (span, active, ambient; D-24 naming contract)
  LED highlight keys — active TTL, retain mode, retain timeout

Note (D-17): led_transition.* keys are NOT admin-editable; they are fixed per-state
defaults and excluded from _ALLOWED_SETTINGS_KEYS and the PUT key_map.

All SQL uses ``%s`` placeholders — no f-string interpolation (T-01-07).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from gruvax.api.deps import get_pool, require_admin
from gruvax.db.queries import load_settings_cache


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-settings"])

# Writable settings keys via PUT /settings.
# Phase 3: cube capacity + session TTL.
# Phase 6 (LED-04, LED-05, D-15, D-24, D-25): LED color / brightness / highlight keys.
# NOTE (D-17): led_transition.* keys are intentionally EXCLUDED — fixed per-state defaults.
_ALLOWED_SETTINGS_KEYS = frozenset(
    {
        # Phase 3 — capacity + session
        "cube.nominal_capacity",
        "session.idle_ttl_seconds",
        # Phase 6 — LED colors (all six states)
        "led_color.position",
        "led_color.label_span",
        "led_color.error",
        "led_color.setup",
        "led_color.all_off",
        "led_color.ambient",
        # Phase 6 — LED brightness tiers (D-24 naming contract — three DISTINCT tiers)
        "led_brightness.span",  # label-span tier (~50%) — NOT the idle baseline
        "led_brightness.active",  # position/primary tier (100%)
        "led_brightness.ambient",  # idle/resting baseline (low) — NOT the span tier
        # Phase 6 — LED highlight lifecycle (D-21, D-23, D-25)
        "led_highlight.active_ttl_seconds",
        "led_highlight.retain_mode",
        "led_highlight.retain_ttl_seconds",
    }
)

# Regex for valid #RRGGBB hex color (T-06-08 — reject malformed hex with 422)
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# DB keys that store color values (JSON strings "#RRGGBB"); remaining LED keys are
# integers or booleans stored as bare JSON.
_COLOR_KEYS = frozenset(
    {
        "led_color.position",
        "led_color.label_span",
        "led_color.error",
        "led_color.setup",
        "led_color.all_off",
        "led_color.ambient",
    }
)

# DB keys that store integers (brightness values, TTL seconds)
_INT_KEYS = frozenset(
    {
        "cube.nominal_capacity",
        "session.idle_ttl_seconds",
        "led_brightness.span",
        "led_brightness.active",
        "led_brightness.ambient",
        "led_highlight.active_ttl_seconds",
        "led_highlight.retain_ttl_seconds",
    }
)

# DB keys that store booleans
_BOOL_KEYS = frozenset(
    {
        "led_highlight.retain_mode",
    }
)

# WR-03: brightness keys must be within the 8-bit hardware range [0, 255].
# Without this, a value like 999 is persisted verbatim, echoed back by GET, and
# only clamped at publish time — the stored value and the published value disagree.
# Validate on the PUT path (422 on out-of-range) so the persisted value is always
# one the publisher will honour, consistent with the hex validation for colours.
_BRIGHTNESS_KEYS = frozenset(
    {
        "led_brightness.span",
        "led_brightness.active",
        "led_brightness.ambient",
    }
)


@router.get("/settings")
async def get_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Return admin settings: capacity, idle TTL, and all LED knobs.

    Phase 3: cube_nominal_capacity, session_idle_ttl_seconds.
    Phase 6: all LED color/brightness/highlight keys (LED-04, LED-05, D-25).

    Reads from ``gruvax.settings`` table.  Returns defaults if keys are absent.
    Colors returned as plain hex strings (stripped of JSON quotes).
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT key, value FROM gruvax.settings WHERE key = ANY(%s)",
            (list(_ALLOWED_SETTINGS_KEYS),),
        )
        rows = await cur.fetchall()

    settings_map: dict[str, Any] = {str(row[0]): row[1] for row in rows}

    def _get_color(key: str, default: str) -> str:
        """Get a color value, stripping JSON string quotes if present."""
        raw = settings_map.get(key, default)
        if isinstance(raw, str):
            return raw.strip('"')
        return default

    def _get_int(key: str, default: int) -> int:
        """Get an integer value."""
        raw = settings_map.get(key, default)
        try:
            return int(raw)
        except TypeError, ValueError:
            return default

    def _get_bool(key: str, default: bool) -> bool:
        """Get a boolean value."""
        raw = settings_map.get(key, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("true", "1")
        return bool(raw)

    return {
        # Phase 3 keys
        "cube_nominal_capacity": _get_int("cube.nominal_capacity", 95),
        "session_idle_ttl_seconds": _get_int("session.idle_ttl_seconds", 600),
        # Phase 6 — LED colors (LED-05)
        "led_color_position": _get_color("led_color.position", "#FFD700"),
        "led_color_label_span": _get_color("led_color.label_span", "#7C3AED"),
        "led_color_error": _get_color("led_color.error", "#E63946"),
        "led_color_setup": _get_color("led_color.setup", "#0077B6"),
        "led_color_all_off": _get_color("led_color.all_off", "#000000"),
        "led_color_ambient": _get_color("led_color.ambient", "#0051A2"),
        # Phase 6 — LED brightness tiers (LED-04, D-24)
        "led_brightness_span": _get_int("led_brightness.span", 128),
        "led_brightness_active": _get_int("led_brightness.active", 255),
        "led_brightness_ambient": _get_int("led_brightness.ambient", 40),
        # Phase 6 — LED highlight lifecycle (D-25)
        "led_highlight_active_ttl_seconds": _get_int("led_highlight.active_ttl_seconds", 180),
        "led_highlight_retain_mode": _get_bool("led_highlight.retain_mode", False),
        "led_highlight_retain_ttl_seconds": _get_int("led_highlight.retain_ttl_seconds", 900),
    }


@router.put("/settings")
async def update_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Update admin settings.

    Whitelisted keys: cube capacity, idle TTL, and all LED knobs (Phase 6).
    Unknown keys are silently ignored.
    Color values are validated against #RRGGBB — malformed hex returns 422 (T-06-08).
    led_transition.* keys are NOT accepted (D-17 — fixed per-state defaults).

    Body: any subset of the AdminSettingsPut shape (all fields optional).
    """
    body = await request.json()

    # Map JSON body keys → gruvax.settings DB keys
    # Order: Phase 3 first, then Phase 6 LED keys.
    # CRITICAL (D-24): led_brightness_span → led_brightness.span (NOT led_brightness.ambient)
    key_map: dict[str, str] = {
        # Phase 3
        "cube_nominal_capacity": "cube.nominal_capacity",
        "session_idle_ttl_seconds": "session.idle_ttl_seconds",
        # Phase 6 — LED colors (LED-05)
        "led_color_position": "led_color.position",
        "led_color_label_span": "led_color.label_span",
        "led_color_error": "led_color.error",
        "led_color_setup": "led_color.setup",
        "led_color_all_off": "led_color.all_off",
        "led_color_ambient": "led_color.ambient",
        # Phase 6 — LED brightness (LED-04, D-24 — three distinct tiers)
        "led_brightness_span": "led_brightness.span",  # label-span tier
        "led_brightness_active": "led_brightness.active",  # position/primary tier
        "led_brightness_ambient": "led_brightness.ambient",  # idle baseline
        # Phase 6 — LED highlight lifecycle (D-25)
        "led_highlight_active_ttl_seconds": "led_highlight.active_ttl_seconds",
        "led_highlight_retain_mode": "led_highlight.retain_mode",
        "led_highlight_retain_ttl_seconds": "led_highlight.retain_ttl_seconds",
    }

    # Validate color + brightness values before any writes (fail-fast, T-06-08 / WR-03)
    for body_key, db_key in key_map.items():
        if body_key not in body:
            continue
        if db_key in _COLOR_KEYS:
            value = body[body_key]
            if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_hex_color",
                        "field": body_key,
                        "message": (
                            f"Color value must be a valid #RRGGBB hex string. Got: {value!r}"
                        ),
                    },
                )
        elif db_key in _BRIGHTNESS_KEYS:
            # WR-03: brightness must be an integer in the 8-bit hardware range.
            value = body[body_key]
            try:
                int_value = int(value)
            except TypeError, ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_brightness",
                        "field": body_key,
                        "message": f"Brightness must be an integer in [0, 255]. Got: {value!r}",
                    },
                ) from None
            if not 0 <= int_value <= 255:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_brightness",
                        "field": body_key,
                        "message": f"Brightness must be in [0, 255]. Got: {int_value}",
                    },
                )

    updated: list[str] = []
    async with pool.connection() as conn:
        for body_key, db_key in key_map.items():
            if body_key not in body:
                continue
            value = body[body_key]

            if db_key in _COLOR_KEYS:
                # Store as JSON string: '"#FFD700"' (consistent with auth.pin_hash pattern)
                json_value = f'"{value}"'
            elif db_key in _INT_KEYS:
                # Store as bare integer JSON
                try:
                    int_val = int(value)
                except TypeError, ValueError:
                    logger.warning("Skipping invalid integer for %s: %r", db_key, value)
                    continue
                json_value = str(int_val)
            elif db_key in _BOOL_KEYS:
                # Store as bare boolean JSON (true/false)
                bool_val = bool(value)
                json_value = "true" if bool_val else "false"
            else:
                # Fallback: plain JSON encoding
                import json as _json

                json_value = _json.dumps(value)

            await conn.execute(
                "UPDATE gruvax.settings SET value = %s::jsonb, updated_at = now() WHERE key = %s",
                (json_value, db_key),
            )
            updated.append(db_key)
        await conn.commit()

    logger.info("Admin settings updated: %s", updated)

    # D-15 / WR-01: Refresh the in-process settings cache so the publisher (Plan 01)
    # and lifecycle (Plan 02) see new LED values immediately without a restart.
    #
    # WR-01: MUTATE the existing dict in place (clear + update) rather than REBINDING
    # the attribute to a fresh dict.  Fire-and-forget tasks (fan_out_illuminate,
    # illuminate_with_lifecycle, in-flight schedule_revert that runs 180-900s later)
    # capture the settings_cache dict REFERENCE at spawn time.  Rebinding the
    # attribute would leave those tasks reading the stale OLD dict; mutating the
    # same object in place means every holder of the reference sees the new values
    # immediately (D-15 "see new LED values immediately").
    try:
        fresh = await load_settings_cache(pool)
        existing = getattr(request.app.state, "settings_cache", None)
        if isinstance(existing, dict):
            existing.clear()
            existing.update(fresh)
        else:
            request.app.state.settings_cache = fresh
    except Exception as exc:
        logger.warning("Settings cache refresh failed after PUT /settings: %s", exc)
        # Non-fatal — the DB write succeeded; the cache will be stale until restart.

    return {"updated": updated}


@router.post("/settings/pin")
async def change_pin(
    request: Request,
    pool: Any = Depends(get_pool),
    admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Change the admin PIN (requires current PIN verification).

    Steps:
    1. Verify ``current_pin`` against stored ``auth.pin_hash``.
    2. Hash ``new_pin`` and write to ``gruvax.settings auth.pin_hash``.
    3. Revoke ALL other sessions (D-03b, T-03-08 session fixation mitigation).

    Body: ``{current_pin: str, new_pin: str}``

    Returns 401 if ``current_pin`` is wrong.  PIN is never logged (Pitfall 12).
    """
    from gruvax.auth.pin import hash_pin, verify_pin
    from gruvax.auth.sessions import revoke_all_sessions_except

    logger.info("Change-PIN attempt pin_attempt=redacted")

    body = await request.json()
    current_pin: str = str(body.get("current_pin", ""))
    new_pin: str = str(body.get("new_pin", ""))

    # Validate new PIN format (4 digits)
    if not new_pin.isdigit() or len(new_pin) != 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"type": "invalid_pin_format", "message": "PIN must be exactly 4 digits"},
        )

    # Fetch current hash
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT value FROM gruvax.settings WHERE key = %s",
            ("auth.pin_hash",),
        )
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "pin_not_configured"},
        )

    stored_hash: str = row[0] if isinstance(row[0], str) else str(row[0])

    # Verify current PIN — never log the raw value (Pitfall 12)
    if not verify_pin(current_pin, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "invalid_current_pin"},
        )

    # Hash the new PIN and upsert into gruvax.settings
    new_hash = hash_pin(new_pin)
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (key, value, description, updated_at)"
            " VALUES ('auth.pin_hash', %s::jsonb, 'Argon2id-hashed admin PIN', now())"
            " ON CONFLICT (key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (f'"{new_hash}"',),
        )
        # Revoke ALL other sessions (D-03b — lost device protection, T-03-08)
        current_session_id = admin["session_id"]
        await revoke_all_sessions_except(conn, current_session_id)
        await conn.commit()

    logger.info("PIN changed successfully; other sessions revoked")
    return {"message": "PIN changed; other sessions revoked"}

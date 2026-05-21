"""Admin settings endpoints for GRUVAX.

Endpoints:
  GET  /api/admin/settings      — return current cube.nominal_capacity + session.idle_ttl_seconds
  PUT  /api/admin/settings      — update whitelisted settings keys
  POST /api/admin/settings/pin  — change PIN (requires current PIN; revokes all other sessions)

Phase 3 scope (D-18): only Change PIN + nominal capacity + idle timeout.
LED color/brightness settings are deferred to Phase 5.

All SQL uses ``%s`` placeholders — no f-string interpolation (T-01-07).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status

from gruvax.api.deps import get_pool, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-settings"])

# Only Phase 3 keys are writable via PUT /settings (D-18)
_ALLOWED_SETTINGS_KEYS = frozenset({"cube.nominal_capacity", "session.idle_ttl_seconds"})


@router.get("/settings")
async def get_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Return Phase 3 admin settings (nominal capacity + idle TTL).

    Reads from ``gruvax.settings`` table.  Returns defaults if keys are absent.
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT key, value FROM gruvax.settings WHERE key = ANY(%s)",
            (list(_ALLOWED_SETTINGS_KEYS),),
        )
        rows = await cur.fetchall()

    settings_map = {str(row[0]): row[1] for row in rows}
    return {
        "cube_nominal_capacity": int(settings_map.get("cube.nominal_capacity", 95)),
        "session_idle_ttl_seconds": int(settings_map.get("session.idle_ttl_seconds", 600)),
    }


@router.put("/settings")
async def update_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Update Phase 3 admin settings.

    Only ``cube.nominal_capacity`` and ``session.idle_ttl_seconds`` are accepted
    (D-18 — LED settings deferred to Phase 5).  Unknown keys are silently ignored.

    Body: ``{cube_nominal_capacity?: int, session_idle_ttl_seconds?: int}``
    """
    body = await request.json()

    # Map the JSON body keys to gruvax.settings DB keys
    key_map = {
        "cube_nominal_capacity": "cube.nominal_capacity",
        "session_idle_ttl_seconds": "session.idle_ttl_seconds",
    }

    updated: list[str] = []
    async with pool.connection() as conn:
        for body_key, db_key in key_map.items():
            if body_key not in body:
                continue
            value = body[body_key]
            await conn.execute(
                "UPDATE gruvax.settings SET value = %s::jsonb, updated_at = now()"
                " WHERE key = %s",
                (str(value), db_key),
            )
            updated.append(db_key)
        await conn.commit()

    logger.info("Admin settings updated: %s", updated)
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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

"""Admin device lifecycle CRUD under /api/admin/devices/*.

Endpoints (all PIN-gated via Depends(require_admin)):
  POST   /devices/bind            — atomic PIN-gated code bind (rate-limited, first-wins)
  GET    /devices                 — list devices grouped by state (paired/pending/revoked)
  PATCH  /devices/{id}            — rename, change-profile, or unbind (profile_id=null)
  POST   /devices/{id}/revoke     — set revoked_at; publishes device_revoked SSE
  POST   /devices/{id}/reinstate  — clear revoked_at
  DELETE /devices/{id}            — hard-delete the device row

Security:
  - All mutations require Depends(require_admin) — PIN session + CSRF (T-03-07)
  - POST /devices/bind is rate-limited 10/5min per IP (T-03-05)
  - Bind uses atomic conditional UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW()
    RETURNING fingerprint (T-03-06: PostgreSQL row lock — first wins, second sees no row)
  - fingerprint is NEVER selected into or returned from any response payload (T-03-08)
  - fingerprint is NEVER logged (RESEARCH.md Pitfall 7)
  - SSE publish (D3-06) happens AFTER conn.commit(), never inside the transaction
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
import psycopg
from pydantic import BaseModel, field_validator

from gruvax.api.admin.limiter import _BIND_RATE, _rate_limiter
from gruvax.api.deps import get_pool, require_admin
from gruvax.db.queries import DEFAULT_PROFILE_UUID


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/devices", tags=["admin-devices"])


# ── Request models ────────────────────────────────────────────────────────────


class BindRequest(BaseModel):
    """Request body for POST /devices/bind."""

    code: str
    profile_id: str | None = None
    display_name: str | None = None

    @field_validator("code")
    @classmethod
    def code_must_be_4_digits(cls, v: str) -> str:
        """Server-side: code must be exactly 4 digits ('0000'..'9999')."""
        if not v.isdigit() or len(v) != 4:
            raise ValueError("code must be exactly 4 digits")
        return v


class RenameDeviceRequest(BaseModel):
    """Request body for PATCH /devices/{id} — rename."""

    display_name: str


class ChangeProfileRequest(BaseModel):
    """Request body for PATCH /devices/{id} — change profile or unbind."""

    profile_id: str | None = None


# ── SQL constants — parameterized %s, never f-strings (bandit B608) ──────────

# Atomic "first wins" bind: conditional UPDATE consumed_at only when the code
# has not been consumed AND has not expired. RETURNING fingerprint so we know
# which kiosk to bind. Under PostgreSQL READ COMMITTED, the first transaction
# acquires the row lock; the second re-evaluates WHERE and finds consumed_at IS NOT NULL
# — returns zero rows (RESEARCH.md Pattern 2 / T-03-06).
_BIND_CODE = (
    "UPDATE gruvax.pairing_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING fingerprint"
)

# The bind path uses an explicit three-step upsert below
# (_UPDATE_DEVICE_BY_FINGERPRINT → _UPDATE_DEVICE_BY_PROFILE → _INSERT_DEVICE),
# all within a single transaction (see bind_device). The fingerprint is only ever
# a query parameter — it is never returned in any response (T-03-08).

# Insert a new device row (re-pair / first pair). On conflict with the partial-unique
# active-device indexes, surfaces a UniqueViolation that bind_device maps to a clean 409.
_INSERT_DEVICE = (
    "INSERT INTO gruvax.devices (fingerprint, profile_id, display_name)"
    " VALUES (%s, %s::uuid, %s)"
    " RETURNING id, profile_id, display_name, revoked_at, last_seen_at, created_at"
)

_UPDATE_DEVICE_BY_FINGERPRINT = (
    "UPDATE gruvax.devices SET"
    "  profile_id = %s::uuid,"
    "  display_name = %s"
    " WHERE fingerprint = %s AND revoked_at IS NULL"
    " RETURNING id, profile_id, display_name, revoked_at, last_seen_at, created_at"
)

_UPDATE_DEVICE_BY_PROFILE = (
    "UPDATE gruvax.devices SET"
    "  fingerprint = %s,"
    "  display_name = %s"
    " WHERE profile_id = %s::uuid AND revoked_at IS NULL"
    " RETURNING id, profile_id, display_name, revoked_at, last_seen_at, created_at"
)

# List all devices — never select fingerprint (T-03-08).
_LIST_DEVICES = (
    "SELECT id, profile_id, display_name, revoked_at, last_seen_at, created_at"
    " FROM gruvax.devices"
    " ORDER BY created_at"
)

# Fetch a single device by id — never select fingerprint (T-03-08).
_SELECT_DEVICE_BY_ID = (
    "SELECT id, profile_id, display_name, revoked_at, last_seen_at, created_at"
    " FROM gruvax.devices WHERE id = %s::uuid"
)

_REVOKE_DEVICE = (
    "UPDATE gruvax.devices SET revoked_at = NOW()"
    " WHERE id = %s::uuid AND revoked_at IS NULL"
    " RETURNING id, profile_id"
)

_REINSTATE_DEVICE = (
    "UPDATE gruvax.devices SET revoked_at = NULL"
    " WHERE id = %s::uuid AND revoked_at IS NOT NULL"
    " RETURNING id, profile_id"
)

_DELETE_DEVICE = "DELETE FROM gruvax.devices WHERE id = %s::uuid RETURNING id"

_RENAME_DEVICE = (
    "UPDATE gruvax.devices SET display_name = %s WHERE id = %s::uuid RETURNING id, display_name"
)

_CHANGE_PROFILE = (
    "UPDATE gruvax.devices SET profile_id = %s::uuid WHERE id = %s::uuid RETURNING id, profile_id"
)

_UNBIND_DEVICE = (
    "UPDATE gruvax.devices SET profile_id = NULL WHERE id = %s::uuid RETURNING id, profile_id"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _parse_uuid(device_id: str) -> uuid.UUID:
    """Parse device_id as UUID, raising 400 on failure."""
    try:
        return uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_uuid", "message": "device_id must be a UUID"},
        ) from None


def _check_bind_rate_limit(request: Request) -> None:
    """Enforce the bind rate limit (10/5minutes per IP).

    Mirrors login.py's _check_login_rate_limit exactly, using the "device_bind"
    namespace key to avoid sharing the login counter (RESEARCH.md Pattern 3).

    Raises HTTPException(429) when the caller exceeds the limit.
    """
    client_ip: str = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_BIND_RATE, "device_bind", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "rate_limited",
                "message": "Too many attempts. Wait a moment and try again.",
            },
        )


def _device_state(profile_id: Any, revoked_at: Any) -> str:
    """Derive device state string from row fields."""
    if revoked_at is not None:
        return "revoked"
    if profile_id is None:
        return "pending"
    return "paired"


def _row_to_device(row: tuple[Any, ...]) -> dict[str, Any]:
    """Convert a DB row tuple to a device summary dict (no fingerprint — T-03-08)."""
    device_id, profile_id, display_name, revoked_at, last_seen_at, created_at = row
    return {
        "id": str(device_id),
        "profile_id": str(profile_id) if profile_id else None,
        "display_name": display_name,
        "state": _device_state(profile_id, revoked_at),
        "revoked_at": revoked_at.isoformat() if revoked_at else None,
        "last_seen_at": last_seen_at.isoformat() if last_seen_at else None,
        "created_at": created_at.isoformat() if created_at else None,
    }


async def _publish_device_event(
    request: Request,
    event_name: str,
    device_id: str,
    profile_id: str | None,
) -> None:
    """Publish a device lifecycle event on the profile's SSE channel (D3-06).

    Must be called AFTER conn.commit() — never inside a transaction.
    Only publishes when a bus exists for the given profile_id.
    """
    if not profile_id:
        return
    bus_registry: dict[str, Any] | None = getattr(request.app.state, "event_bus_registry", None)
    if not bus_registry:
        return
    bus = bus_registry.get(profile_id)
    if bus is None:
        return
    await bus.publish(event_name, {"device_id": device_id})


# ── POST /devices/bind ────────────────────────────────────────────────────────


@router.post("/bind")
async def bind_device(
    request: Request,
    body: BindRequest,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Atomic PIN-gated pairing-code bind (rate-limited, first-wins).

    Flow:
    1. Rate-limit check (10/5min per IP).
    2. Resolve profile_id (400 on bad UUID — BEFORE touching the DB so a client
       error never burns the code).
    3. In a SINGLE transaction: atomic UPDATE pairing_codes SET consumed_at=NOW()
       WHERE code=%s AND consumed_at IS NULL AND expires_at > NOW() RETURNING
       fingerprint (→ 404 code_not_found if no row), then UPSERT the devices row.
       Code consumption and the device upsert commit together — if the upsert
       fails, the consumed_at write rolls back and the code stays reusable (CR-02).
    4. Return 200 with device summary (NO fingerprint in response — T-03-08).
    """
    # Rate-limit check MUST be first line (T-03-05).
    _check_bind_rate_limit(request)

    # Resolve profile_id BEFORE consuming the code: use supplied profile_id if
    # provided, else default profile. A bad UUID must 400 without burning the code.
    # Defaulting to DEFAULT_PROFILE_UUID matches the single-profile deployment model.
    profile_id_str: str = DEFAULT_PROFILE_UUID
    if body.profile_id:
        try:
            profile_uuid = uuid.UUID(body.profile_id)
            profile_id_str = str(profile_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
            ) from None

    display_name: str = body.display_name or "Unnamed device"

    # Single transaction (CR-02): code consumption + device upsert commit together.
    # The "first wins" UPDATE takes a PostgreSQL row-level lock so concurrent binds
    # on the same code resolve to exactly one success (RESEARCH.md Pattern 2). If the
    # device upsert raises, the whole transaction rolls back — the code is NOT burned.
    # UPSERT priority:
    #   1. UPDATE an existing active row for this fingerprint (re-pairing).
    #   2. Else UPDATE the profile's existing active device to this fingerprint (rebind).
    #   3. Else INSERT a new row.
    # fingerprint is only ever a query parameter — never returned (T-03-08).
    device_row: tuple[Any, ...] | None = None
    try:
        async with pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_BIND_CODE, (body.code,))
            row = await cur.fetchone()
            if row is None:
                await conn.rollback()
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"type": "code_not_found"},
                )

            fingerprint: str = row[0]
            # fingerprint is NOT logged (Pitfall 7) and NOT returned to client.

            await cur.execute(
                _UPDATE_DEVICE_BY_FINGERPRINT, (profile_id_str, display_name, fingerprint)
            )
            device_row = await cur.fetchone()

            if device_row is None and profile_id_str:
                await cur.execute(
                    _UPDATE_DEVICE_BY_PROFILE, (fingerprint, display_name, profile_id_str)
                )
                device_row = await cur.fetchone()

            if device_row is None:
                await cur.execute(_INSERT_DEVICE, (fingerprint, profile_id_str, display_name))
                device_row = await cur.fetchone()

            await conn.commit()
    except psycopg.errors.UniqueViolation:
        # Partial-unique index collision (e.g. the profile already has a different
        # active device). The transaction rolls back automatically, so the code is
        # NOT consumed and the kiosk can retry. Report a clean 409 instead of a 500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"type": "profile_already_bound"},
        ) from None

    if device_row is None:
        logger.error("bind_device: UPSERT returned no row (unexpected)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "device_create_failed"},
        )

    device = _row_to_device(device_row)
    return JSONResponse(content=device)


# ── GET /devices ──────────────────────────────────────────────────────────────


@router.get("")
async def list_devices(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """List all devices grouped by state: {paired: [...], pending: [...], revoked: [...]}.

    Never includes the fingerprint field in any device record (T-03-08).
    Empty groups are included as empty lists.
    """
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_LIST_DEVICES)
        rows = await cur.fetchall()

    paired: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    revoked: list[dict[str, Any]] = []

    for row in rows:
        device = _row_to_device(row)
        state = device["state"]
        if state == "paired":
            paired.append(device)
        elif state == "pending":
            pending.append(device)
        else:
            revoked.append(device)

    return JSONResponse(content={"paired": paired, "pending": pending, "revoked": revoked})


# ── PATCH /devices/{id} ───────────────────────────────────────────────────────


@router.patch("/{device_id}")
async def patch_device(
    device_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Rename, change-profile, or unbind a device.

    Body fields (all optional):
      - display_name: str        → rename
      - profile_id: str | null   → change profile (if non-null) or unbind (if null)

    Publishes device_reassigned on the CURRENT (old) profile's SSE channel after
    a change-profile mutation (D3-06).
    """
    uid = _parse_uuid(device_id)

    # Parse the body manually to support both rename and profile change in one call.
    try:
        body_data = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_request", "message": "Request body must be valid JSON"},
        ) from exc

    if not isinstance(body_data, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_request", "message": "Request body must be a JSON object"},
        )

    # Track whether we need to publish SSE after commit.
    old_profile_id: str | None = None
    changed_profile = False

    async with pool.connection() as conn, conn.cursor() as cur:
        # Fetch current state to detect profile changes.
        await cur.execute(_SELECT_DEVICE_BY_ID, (str(uid),))
        current_row = await cur.fetchone()
        if current_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "device_not_found"},
            )
        old_profile_id = str(current_row[1]) if current_row[1] else None

        # Apply rename if display_name is in body.
        if "display_name" in body_data:
            display_name = str(body_data["display_name"])
            await cur.execute(_RENAME_DEVICE, (display_name, str(uid)))

        # Apply profile change if profile_id key is in body.
        if "profile_id" in body_data:
            new_profile_id_value = body_data["profile_id"]
            changed_profile = True

            if new_profile_id_value is None:
                # Unbind: set profile_id to NULL.
                await cur.execute(_UNBIND_DEVICE, (str(uid),))
            else:
                # Change profile.
                try:
                    new_profile_uuid = uuid.UUID(str(new_profile_id_value))
                except ValueError:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
                    ) from None
                await cur.execute(_CHANGE_PROFILE, (str(new_profile_uuid), str(uid)))

        # Fetch updated row (no fingerprint — T-03-08).
        await cur.execute(_SELECT_DEVICE_BY_ID, (str(uid),))
        updated_row = await cur.fetchone()
        await conn.commit()

    if updated_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "device_not_found"},
        )

    # Publish device_reassigned on the OLD profile's SSE channel AFTER commit (D3-06).
    if changed_profile and old_profile_id:
        await _publish_device_event(request, "device_reassigned", str(uid), old_profile_id)

    return JSONResponse(content=_row_to_device(updated_row))


# ── POST /devices/{id}/revoke ─────────────────────────────────────────────────


@router.post("/{device_id}/revoke")
async def revoke_device(
    device_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Revoke a device: set revoked_at to NOW().

    Publishes device_revoked on the device's current profile SSE channel
    AFTER the transaction commits (D3-06).
    """
    uid = _parse_uuid(device_id)

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_REVOKE_DEVICE, (str(uid),))
        row = await cur.fetchone()
        await conn.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "device_not_found"},
        )

    revoked_id, profile_id = row
    profile_id_str = str(profile_id) if profile_id else None

    # Publish device_revoked on the device's current profile channel (D3-06).
    # Must be AFTER commit — never inside the transaction.
    await _publish_device_event(request, "device_revoked", str(revoked_id), profile_id_str)

    return JSONResponse(content={"id": str(revoked_id), "status": "revoked"})


# ── POST /devices/{id}/reinstate ─────────────────────────────────────────────


@router.post("/{device_id}/reinstate")
async def reinstate_device(
    device_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Reinstate a revoked device: clear revoked_at."""
    uid = _parse_uuid(device_id)

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_REINSTATE_DEVICE, (str(uid),))
        row = await cur.fetchone()
        await conn.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "device_not_found"},
        )

    return JSONResponse(content={"id": str(row[0]), "status": "reinstated"})


# ── DELETE /devices/{id} ──────────────────────────────────────────────────────


@router.delete("/{device_id}")
async def delete_device(
    device_id: str,
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Hard-delete a device row."""
    uid = _parse_uuid(device_id)

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_DELETE_DEVICE, (str(uid),))
        row = await cur.fetchone()
        await conn.commit()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "device_not_found"},
        )

    return JSONResponse(content={"id": str(row[0]), "status": "deleted"})

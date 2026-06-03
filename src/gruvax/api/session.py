"""Session bootstrap + browse-binding API — Plan 02-04.

Implements the no-PIN browse-binding session layer (R7, D2-08, D2-10):

  GET  /api/session         — Bootstrap: returns {profile_count, bound_profile_id,
                              profiles[]}; auto-binds when exactly one active profile
                              exists and no binding cookie is present (D2-08).
  POST /api/session/bind    — Set browse-binding cookie for the given profile_id.
  DELETE /api/session/bind  — Clear the browse-binding cookie (Switch-profile, D2-07).

Security (T-02-04-02): none of these endpoints read or mutate the admin
``gruvax_session`` / ``gruvax_csrf`` cookies.  The browse-binding cookie
(``gruvax_browse_binding``) is entirely independent (D2-10).

CSRF (T-02-04-04): SameSite=Strict on both admin + browse cookies blocks
cross-site POST forging a bind; bind/unbind are reversible, non-destructive
operations. No additional CSRF token needed for this layer.

Threat model: T-02-04-01 (forged cookie) — server validates the bound profile_id
against active-profiles on every per-profile endpoint (D2-04); a forged id
resolving to no active profile → 404/403 in get_{cache,bus,...}_for_profile.
The GET /session and bind endpoints themselves also validate against the DB.
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.auth.sessions import (
    BROWSE_BINDING_COOKIE,
    clear_browse_binding_cookie,
    get_fingerprint,
    set_browse_binding_cookie,
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["session"])

# SQL — module-level constants (no f-strings, no concatenation — bandit B608).
# T-02-04-03: SELECT excludes app_token_encrypted + discogsography_user_id.
# Returns only the metadata the SPA needs for the picker / SSE URL.
_SELECT_ACTIVE_PROFILES = (
    "SELECT id, display_name, last_sync_at, last_sync_status,"
    " last_sync_item_count, app_token_revoked"
    " FROM gruvax.profiles"
    " WHERE deleted_at IS NULL"
    " ORDER BY created_at"
)

_SELECT_PROFILE_BY_ID = "SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL"

# Device lookup for GET /api/session bootstrap (D3-04 — device binding extension).
# Returns id, profile_id, revoked_at so we can:
#   - Override bound_profile_id when the device is paired (profile_id IS NOT NULL)
#   - Expose device_id (non-secret) in the session response (D3-05)
#   - Treat revoked devices as unpaired (no override) — T-03-14
#   - Never put the fingerprint value in the response (T-03-14)
_SELECT_DEVICE_BY_FINGERPRINT = (
    "SELECT id, profile_id, revoked_at FROM gruvax.devices WHERE fingerprint = %s"
)


class BindRequest(BaseModel):
    """Request body for POST /api/session/bind."""

    profile_id: str


@router.get("/session")
async def get_session(
    request: Request,
    # NO require_admin — browse-binding is PIN-free (R7 / D2-10).
) -> JSONResponse:
    """Bootstrap SPA routing — return active profiles + current binding.

    Returns ``{profile_count, bound_profile_id, profiles[]}``.

    Single-profile auto-bind (D2-08): when exactly one active profile exists
    and no browse-binding cookie is present, the server binds it automatically
    and sets the browse cookie on the response.  The kiosk never flashes the
    profile-picker screen in a single-profile deployment.

    Multi-profile, no cookie: ``bound_profile_id`` is ``null`` so the SPA
    routes to ``/select`` for the user to pick a profile.

    The ``profiles[]`` list contains only display metadata (T-02-04-03):
    ``id``, ``display_name``, ``last_sync_at``, ``last_sync_status``,
    ``last_sync_item_count``, ``app_token_revoked``.  No PAT or internal
    Discogs user IDs are exposed.
    """
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_SELECT_ACTIVE_PROFILES)
        rows = await cur.fetchall()

    profiles: list[dict[str, Any]] = [
        {
            "id": str(row[0]),
            "display_name": row[1],
            "last_sync_at": row[2].isoformat() if row[2] else None,
            "last_sync_status": row[3],
            "last_sync_item_count": row[4],
            "app_token_revoked": bool(row[5]),
        }
        for row in rows
    ]

    bound_profile_id: str | None = request.cookies.get(BROWSE_BINDING_COOKIE)

    # Device-binding extension (D3-04): check fingerprint cookie before constructing
    # the response.  If the fingerprint maps to a paired device, override
    # bound_profile_id (device binding wins over browse-binding, D3-05) and expose
    # device_id + is_device_paired.  Never put the fingerprint value in the response
    # (T-03-14 — fingerprint is a session-equivalent secret).
    device_id: str | None = None
    is_device_paired: bool = False

    fp = get_fingerprint(request)
    if fp:
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_SELECT_DEVICE_BY_FINGERPRINT, (fp,))
            device_row = await cur.fetchone()

        if device_row is not None:
            dev_id, dev_profile_id, dev_revoked_at = device_row
            device_id = str(dev_id)  # non-secret UUID — safe to expose (D3-05)

            # Override only for a LIVE paired device: not revoked AND has a profile.
            # Orphaned (profile soft-deleted → profile_id NULL) and revoked devices
            # both leave bound_profile_id as-is from the browse cookie (picker) and
            # is_device_paired False; device_id is still exposed so the SPA can show a
            # "revoked"/picker indicator.
            if dev_revoked_at is None and dev_profile_id is not None:
                # Paired device: device binding wins (D3-05)
                bound_profile_id = str(dev_profile_id)
                is_device_paired = True
                logger.debug(
                    "GET /session: device binding override → device_id=%s profile_id=%s",
                    device_id,
                    bound_profile_id,
                )

    # Single-profile auto-bind (D2-08) — only runs when device binding did NOT set a
    # bound_profile_id (i.e., no paired fingerprint is overriding).
    response_cookies: dict[str, Any] | None = None
    if len(profiles) == 1 and not bound_profile_id:
        bound_profile_id = profiles[0]["id"]
        response_cookies = {"profile_id": bound_profile_id}
        logger.debug("GET /session: single-profile auto-bind → profile_id=%s", bound_profile_id)

    # D4-08: Derive needs_reauth from the bound profile's app_token_revoked flag.
    # No new DB query — app_token_revoked is already fetched via _SELECT_ACTIVE_PROFILES.
    # Always present in the response (not just when True) so the kiosk can rely on it.
    # T-04-01-04: derived only from the BOUND profile; no cross-profile leakage.
    # T-04-01-05: derived from the live per-request profiles read, not an app.state cache.
    needs_reauth = False
    if bound_profile_id:
        bound_profile = next((p for p in profiles if str(p["id"]) == bound_profile_id), None)
        if bound_profile is not None:
            needs_reauth = bool(bound_profile.get("app_token_revoked", False))

    content: dict[str, Any] = {
        "profile_count": len(profiles),
        "bound_profile_id": bound_profile_id,
        "profiles": profiles,
        "device_id": device_id,
        "is_device_paired": is_device_paired,
        "needs_reauth": needs_reauth,  # D4-08
    }

    response = JSONResponse(content=content)
    if response_cookies is not None:
        set_browse_binding_cookie(response, response_cookies["profile_id"])

    return response


@router.post("/session/bind")
async def bind_session(
    request: Request,
    body: BindRequest,
    # NO require_admin — browse-binding is PIN-free (R7 / D2-10).
) -> JSONResponse:
    """Set the browse-binding cookie for the given profile_id.

    Validates that ``profile_id`` is a valid UUID (400) and resolves to an
    active (non-deleted) profile (404).  On success, sets the
    ``gruvax_browse_binding`` cookie and returns ``{status: "bound", profile_id}``.

    Does NOT read or mutate the admin ``gruvax_session`` cookie (D2-10).
    """
    # UUID parse — 400 on invalid format.
    try:
        uid = uuid.UUID(body.profile_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_uuid", "message": "profile_id must be a valid UUID"},
        ) from None

    profile_id_str = str(uid)

    # Validate against active profiles (T-02-04-01 — 404 if not found).
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_SELECT_PROFILE_BY_ID, (profile_id_str,))
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )

    response = JSONResponse(content={"status": "bound", "profile_id": profile_id_str})
    set_browse_binding_cookie(response, profile_id_str)
    return response


@router.delete("/session/bind")
async def unbind_session(
    # NO require_admin — browse-binding is PIN-free (R7 / D2-10).
) -> JSONResponse:
    """Clear the browse-binding cookie (Switch-profile flow, D2-07).

    Returns ``{status: "unbound"}``.  Does NOT read or mutate the admin
    ``gruvax_session`` cookie (D2-10).  The SPA should route to ``/select``
    after receiving this response.
    """
    response = JSONResponse(content={"status": "unbound"})
    clear_browse_binding_cookie(response)
    return response

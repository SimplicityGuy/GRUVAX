"""Kiosk device endpoints — pairing-code generation and device state polling.

Endpoints (no PIN required — kiosk-facing):
  POST /api/devices/pairing-codes — generate a 4-digit pairing code (5-min TTL);
                                     auto-issue HttpOnly fingerprint cookie on first request
  GET  /api/devices/me            — return device state for the current fingerprint cookie:
                                    {state: 'unpaired'|'pending'|'paired'|'revoked', profile_id?}

Security:
  - Fingerprint value is NEVER logged (RESEARCH.md Pitfall 7)
  - All SQL uses parameterized %s — no f-strings in query text (bandit B608)
  - Code uniqueness enforced via ON CONFLICT DO NOTHING + retry loop (RESEARCH.md Pattern 2)
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from gruvax.auth.sessions import get_fingerprint, issue_fingerprint_cookie


logger = logging.getLogger(__name__)

router = APIRouter(tags=["devices"])

# ── SQL constants — parameterized %s, never f-strings (bandit B608) ──────────

# INSERT a new pairing code; ON CONFLICT (code) DO NOTHING so that a collision
# on the CHAR(4) PK is silently discarded and the caller retries.
# RETURNING code confirms the insert succeeded (not just a conflict).
_INSERT_PAIRING_CODE = (
    "INSERT INTO gruvax.pairing_codes (code, fingerprint, expires_at)"
    " VALUES (%s, %s, NOW() + INTERVAL '5 minutes')"
    " ON CONFLICT (code) DO NOTHING"
    " RETURNING code, expires_at"
)

# SELECT device row by fingerprint — intentionally selects the raw fingerprint
# column to match the DB row, but fingerprint is NOT returned to clients.
_SELECT_DEVICE_BY_FINGERPRINT = (
    "SELECT id, profile_id, revoked_at"
    " FROM gruvax.devices WHERE fingerprint = %s"
)


# ── POST /api/devices/pairing-codes ──────────────────────────────────────────


@router.post("/devices/pairing-codes")
async def generate_pairing_code(
    request: Request,
    response: Response,
) -> JSONResponse:
    """Generate a 4-digit pairing code (5-min TTL) and auto-issue the fingerprint cookie.

    If no fingerprint cookie is present, one is issued via ``issue_fingerprint_cookie``
    and attached to the response.

    Returns:
        ``{code: "XXXX", expires_at: ISO-8601}``

    Security: fingerprint value is never logged (RESEARCH.md Pitfall 7).
    Code collisions are handled with up to 3 retries (RESEARCH.md Pattern 2 + Pitfall 6).
    """
    # Retrieve or issue the fingerprint cookie — auto-issue on first visit.
    fp = get_fingerprint(request)
    new_fp_issued = False
    if fp is None:
        fp = issue_fingerprint_cookie(response)
        new_fp_issued = True
    # fp is now guaranteed non-None; never log its value.

    db_pool = request.app.state.db_pool

    # Collision-retry loop: at household scale (<<100 pending codes) the
    # probability of 3 consecutive PK collisions is negligible (~(N/10000)^3).
    code: str | None = None
    expires_at_iso: str | None = None

    for _ in range(3):
        candidate = f"{secrets.randbelow(10000):04d}"  # '0000'..'9999' via OS CSPRNG
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_INSERT_PAIRING_CODE, (candidate, fp))
            row = await cur.fetchone()
            await conn.commit()
        if row is not None:
            code = row[0]
            expires_at = row[1]
            expires_at_iso = expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
            break

    if code is None:
        logger.error("generate_pairing_code: failed to generate unique code after 3 attempts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "code_generation_failed", "message": "Failed to generate unique pairing code"},
        )

    # Build the JSON response and attach the fingerprint cookie if it was
    # just issued (the cookie was already set on `response` via set_cookie,
    # but we need to propagate it on the JSONResponse object).
    content = {"code": code, "expires_at": expires_at_iso}

    if new_fp_issued:
        # The fingerprint cookie was set on the `response` FastAPI injects;
        # we must copy it to the JSONResponse we return so the Set-Cookie header
        # is present in the actual HTTP response (FastAPI merges headers from
        # both the injected Response and the returned Response).
        json_response = JSONResponse(content=content)
        # Re-issue the cookie on the JSON response directly so it's guaranteed
        # to appear in the response (FastAPI's background-response injection
        # copies headers from the injected Response).
        issue_fingerprint_cookie(json_response)
        return json_response

    return JSONResponse(content=content)


# ── GET /api/devices/me ───────────────────────────────────────────────────────


@router.get("/devices/me")
async def get_device_me(request: Request) -> JSONResponse:
    """Return device state for the current fingerprint cookie.

    States:
      - unpaired:  no fingerprint cookie present
      - pending:   fingerprint cookie present, device row exists but profile_id IS NULL
                   and not revoked (code generated, bind not yet completed)
      - paired:    device row exists, profile_id IS NOT NULL, revoked_at IS NULL
      - revoked:   device row exists, revoked_at IS NOT NULL

    Security: fingerprint value is never logged (RESEARCH.md Pitfall 7).
    """
    fp = get_fingerprint(request)
    if not fp:
        return JSONResponse(content={"state": "unpaired"})

    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_SELECT_DEVICE_BY_FINGERPRINT, (fp,))
        row = await cur.fetchone()

    if row is None:
        # Fingerprint cookie present but no device row yet (code generated but
        # device row not yet created — pending state).
        return JSONResponse(content={"state": "pending"})

    device_id, profile_id, revoked_at = row

    if revoked_at is not None:
        return JSONResponse(content={"state": "revoked"})

    if profile_id is None:
        # Device row exists but no profile bound (orphaned or pending bind).
        return JSONResponse(content={"state": "pending"})

    # Paired: non-null profile_id, not revoked.
    return JSONResponse(content={"state": "paired", "profile_id": str(profile_id)})

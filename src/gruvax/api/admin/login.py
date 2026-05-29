"""Admin login / logout / session endpoints for GRUVAX.

Endpoints:
  POST /api/admin/login   — rate-limited PIN verification; sets session + CSRF cookies
  POST /api/admin/logout  — revokes session row + clears cookies
  GET  /api/admin/session — returns current session expiry times (authenticated)

Security notes:
  - PIN is NEVER logged — logs ``pin_attempt=redacted`` at INFO (Pitfall 12, T-03-06).
  - Rate limit: 5 attempts per 5-minute window per IP → 429 (T-03-04, D-03a).
  - CSRF double-submit enforced by ``require_admin`` for mutating methods.
  - Session cookie: HttpOnly, SameSite=Strict (T-03-09, Pitfall 13).
  - CSRF cookie: NOT HttpOnly (SPA must read it to echo as X-CSRF-Token).

Rate-limiting implementation note:
  The rate limit is enforced using the public ``limits`` library (slowapi's own
  dependency) directly, via ``FixedWindowRateLimiter.hit()``.  This avoids any
  dependency on slowapi private attributes (``._limiter``, ``._key_prefix``,
  ``wrappers.Limit``), making the brute-force guard stable across slowapi upgrades.

  The limiter singleton's ``MemoryStorage`` and ``FixedWindowRateLimiter`` live in
  ``limiter.py`` so the counter is shared correctly across all requests in the same
  process.  On limit breach, ``HTTPException(429)`` is raised directly — no slowapi
  exception handler needed for this path.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from gruvax.api.admin.limiter import _LOGIN_RATE, _rate_limiter
from gruvax.api.deps import get_pool, require_admin
from gruvax.auth.pin import verify_pin
from gruvax.auth.sessions import (
    clear_session_cookies,
    create_session,
    get_session_id,
    revoke_session,
)
from gruvax.settings import settings


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-auth"])


def _check_login_rate_limit(request: Request) -> None:
    """Enforce the login rate limit inline (see module docstring for rationale).

    Raises ``HTTPException(429)`` when the caller has exceeded 5 attempts in the
    last 5 minutes.  Uses the shared ``FixedWindowRateLimiter`` singleton from
    ``limiter.py`` so the counter is shared across all requests in the same process.

    Rate-limit key: direct socket peer IP (``request.client.host``).  This is
    correct for GRUVAX's single-host home-LAN deployment with NO reverse proxy.
    If a proxy is introduced, configure trusted X-Forwarded-For / ProxyHeaders
    handling so the limit keys on the real client IP rather than the proxy.
    """
    # Direct socket peer IP — correct for no-proxy single-host home-LAN deployment.
    # See module docstring and limiter.py for proxy-awareness caveat (WR-05).
    client_ip: str = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_LOGIN_RATE, "login", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "rate_limited",
                "message": "Too many login attempts. Try again later.",
            },
        )


@router.post("/login")
async def login(
    request: Request,
    response: Response,
    pool: Any = Depends(get_pool),
) -> dict[str, Any]:
    """Authenticate with a 4-digit PIN and create an admin session.

    Returns 200 + session cookie + CSRF cookie on success.
    Returns 401 for a wrong PIN (PIN never logged — Pitfall 12).
    Returns 429 when the rate limit is exceeded (T-03-04, D-03a).

    The response body contains ``{csrf_token, expires_at, hard_cap_at}``
    so the SPA can seed the Zustand admin store without reading the HttpOnly
    session cookie.
    """
    # Rate-limit check (5/5minutes per IP) — must be first, before any DB or PIN work.
    _check_login_rate_limit(request)

    # PIN never logged — always log "redacted" (Pitfall 12, T-03-06)
    logger.info("Login attempt from %s pin_attempt=redacted", request.client)

    # WR-04: Wrap JSON decode to return 400 on malformed body (prevents 500)
    try:
        body = await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_request", "message": "Request body must be valid JSON"},
        ) from exc

    pin: str = str(body.get("pin", ""))

    # WR-04: Reject non-4-digit PINs before any DB/hash work — uniform 401
    # to avoid an oracle (same response for wrong PIN and malformed PIN).
    if not pin.isdigit() or len(pin) != 4:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "invalid_pin"},
        )

    # Fetch the stored PIN hash from gruvax.settings — global keys live under the
    # default profile UUID (composite PK = (profile_id, key)).
    _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT value FROM gruvax.settings WHERE profile_id = %s::uuid AND key = %s",
            (_DEFAULT_PROFILE_UUID, "auth.pin_hash"),
        )
        row = await cur.fetchone()

    if row is None:
        # No PIN has been set — bootstrap CLI not yet run
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "pin_not_configured"},
        )

    # The value column is JSONB — psycopg decodes it automatically.
    # If it's a string (JSON string `"<hash>"`), use it directly.
    # If psycopg returns a Python str, use it as-is.
    stored_hash: str = row[0] if isinstance(row[0], str) else str(row[0])

    if not verify_pin(pin, stored_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "invalid_pin"},
        )

    # Correct PIN — create server-side session row + set cookies
    async with pool.connection() as conn:
        csrf_token = await create_session(
            conn,
            response,
            settings.SESSION_SECRET,
            settings.SESSION_TTL_SECONDS,
        )

    # Return the CSRF token; let the client poll /session for expiry times.
    # session_id would be None here — cookie is on the RESPONSE not the request.
    return {
        "csrf_token": csrf_token,
        "message": "Login successful",
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, str]:
    """Revoke the current admin session and clear cookies (ADMN-08).

    Immediate logout — no confirmation required (ADMN-08 + UI-SPEC §Destructive
    action confirmations: "Logout — immediate, no confirm").
    """
    session_id = await get_session_id(request, settings.SESSION_SECRET)
    if session_id:
        async with pool.connection() as conn:
            await revoke_session(conn, session_id)

    clear_session_cookies(response)
    logger.info("Admin session logged out: session_id=%s", session_id)
    return {"message": "Logged out"}


@router.get("/session")
async def get_session(
    request: Request,
    pool: Any = Depends(get_pool),
    admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Return current session expiry info (authenticated).

    Called by the frontend countdown timer to keep the session state in sync
    with the server's sliding window (D-04).  The ``require_admin`` dependency
    already refreshes ``expires_at`` on each call.

    Returns:
        ``{expires_at: ISO-8601 string, hard_cap_at: ISO-8601 string}``
    """
    session_id = admin["session_id"]

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT expires_at, hard_expires_at FROM gruvax.admin_sessions WHERE id = %s",
            (session_id,),
        )
        row = await cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session not found",
        )

    expires_at, hard_expires_at = row
    return {
        "expires_at": expires_at.isoformat()
        if hasattr(expires_at, "isoformat")
        else str(expires_at),
        "hard_cap_at": hard_expires_at.isoformat()
        if hasattr(hard_expires_at, "isoformat")
        else str(hard_expires_at),
    }

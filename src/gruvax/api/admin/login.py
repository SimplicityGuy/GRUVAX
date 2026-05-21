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
  SlowAPI's ``@limiter.limit()`` decorator stores a ``_rate_limiting_complete`` flag
  on ``request.state`` to prevent double-checking when both middleware and decorator
  are used together.  When the app is tested via ``asgi-lifespan`` + httpx
  ``ASGITransport``, the ASGI scope's ``state`` dict is shared across requests in
  that process — so the flag leaks from request N to request N+1, causing the
  counter to stop accumulating after the first call.

  Fix: enforce the rate limit inline using ``limits`` directly.  This is a plain
  ``limits.strategies.FixedWindowRateLimiter.hit()`` call — no SlowAPI state flags,
  no decorator wrapper.  The limiter singleton's ``_storage`` and ``_limiter``
  attributes are reused so that the counter is shared correctly across requests.
  A ``RateLimitExceeded`` is raised on breach so the exception handler registered in
  ``app.py`` still produces the standard 429 response.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from limits import parse as parse_limit
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.wrappers import Limit

from gruvax.api.admin.limiter import limiter
from gruvax.api.deps import get_pool, require_admin
from gruvax.auth.sessions import (
    clear_session_cookies,
    create_session,
    get_session_id,
    revoke_session,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-auth"])

# Rate-limit spec: 5 login attempts per 5-minute window per IP (T-03-04, D-03a).
# Parsed once at module load so the limit item is not re-parsed on every request.
_LOGIN_LIMIT_STRING = "5/5minutes"
_LOGIN_LIMIT_ITEM = parse_limit(_LOGIN_LIMIT_STRING)


def _check_login_rate_limit(request: Request) -> None:
    """Enforce the login rate limit inline (see module docstring for rationale).

    Raises ``RateLimitExceeded`` (→ 429) when the caller has exceeded
    5 attempts in the last 5 minutes.  Uses the SlowAPI limiter singleton's
    underlying ``limits`` strategy so the counter is shared correctly across
    all requests in the same process.

    Also sets ``request.state.view_rate_limit`` which the SlowAPI exception
    handler reads to inject ``X-RateLimit-*`` response headers.
    """
    key = get_remote_address(request)
    scope = "/api/admin/login"
    args = [key, scope]
    if limiter._key_prefix:
        args = [limiter._key_prefix, *args]
    # Build a minimal Limit wrapper so RateLimitExceeded has the expected shape
    # for the exception handler registered in app.py and _inject_headers works.
    wrapped = Limit(
        _LOGIN_LIMIT_ITEM,
        key_func=lambda r: key,
        scope=None,
        per_method=False,
        methods=None,
        error_message=None,
        exempt_when=None,
        cost=1,
        override_defaults=True,
    )
    # view_rate_limit must be set before hit() so it's available whether the limit
    # is exceeded or not (header injection reads it on successful responses too).
    request.state.view_rate_limit = (_LOGIN_LIMIT_ITEM, args)
    if not limiter._limiter.hit(_LOGIN_LIMIT_ITEM, *args):
        raise RateLimitExceeded(wrapped)


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

    body = await request.json()
    pin: str = str(body.get("pin", ""))

    # Fetch the stored PIN hash from gruvax.settings
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT value FROM gruvax.settings WHERE key = %s",
            ("auth.pin_hash",),
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

    from gruvax.auth.pin import verify_pin
    from gruvax.settings import settings

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
    from gruvax.settings import settings

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
            "SELECT expires_at, hard_expires_at"
            " FROM gruvax.admin_sessions WHERE id = %s",
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
        "expires_at": expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at),
        "hard_cap_at": hard_expires_at.isoformat() if hasattr(hard_expires_at, "isoformat") else str(hard_expires_at),
    }

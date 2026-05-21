"""Server-side admin session management for GRUVAX.

Each login creates a row in ``gruvax.admin_sessions`` and sets two cookies:

  gruvax_session  — HttpOnly, SameSite=Strict.  Contains the itsdangerous-signed
                    session UUID.  NOT readable by JavaScript (XSS mitigation).
  gruvax_csrf     — NOT HttpOnly, SameSite=Strict.  Contains a random CSRF token
                    that the SPA echoes as ``X-CSRF-Token`` on every mutating
                    request (double-submit cookie pattern, Pitfall 13, T-03-05).

Session expiry model (D-04, Pitfall 23):
  - Sliding idle TTL: ``expires_at`` = now + SESSION_TTL_SECONDS (default 600 s).
    Refreshed on every authenticated request (sliding window).
  - Hard cap: ``hard_expires_at`` = now + 1800 s (30 min).
    Force re-PIN after a maximum lifetime regardless of activity.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Response
from itsdangerous import URLSafeSerializer

# Cookie name constants — imported by deps.py, login.py, tests/conftest.py
SESSION_COOKIE = "gruvax_session"
CSRF_COOKIE = "gruvax_csrf"

# Hard session cap (30 min) — override via function arg if needed (Pitfall 23)
HARD_CAP_SECONDS = 1800


def is_session_valid(
    *,
    expires_at: datetime,
    hard_expires_at: datetime,
    revoked_at: datetime | None,
) -> bool:
    """Pure helper: return True iff the session is currently valid.

    A session is invalid if ANY of these conditions hold:
    - ``revoked_at`` is set (explicit revocation via logout or Change-PIN)
    - ``expires_at`` is in the past (idle TTL expired, D-04)
    - ``hard_expires_at`` is in the past (hard cap, Pitfall 23)

    Args:
        expires_at:      Sliding idle TTL expiry (UTC).
        hard_expires_at: Hard session cap expiry (UTC).
        revoked_at:      Explicit revocation timestamp, or None if not revoked.

    Returns:
        True iff the session is valid; False otherwise.
    """
    if revoked_at is not None:
        return False
    now = datetime.now(UTC)
    return now <= expires_at and now <= hard_expires_at


def _make_signer(secret_key: str) -> URLSafeSerializer:
    """Build the itsdangerous signer used for the session cookie."""
    return URLSafeSerializer(secret_key, salt="session")


async def create_session(
    conn: Any,
    response: Response,
    secret_key: str,
    idle_ttl_seconds: int,
    hard_cap_seconds: int = HARD_CAP_SECONDS,
) -> str:
    """Insert a session row and set both session + CSRF cookies.

    Follows the ``%s`` placeholder + ``conn.execute`` + ``conn.commit`` pattern
    from ``src/gruvax/db/queries.py``.  The caller provides an already-open
    psycopg connection (released immediately after this function returns).

    Args:
        conn:             Open psycopg connection (caller owns lifecycle).
        response:         FastAPI ``Response`` to attach cookies to.
        secret_key:       ``settings.SESSION_SECRET`` for itsdangerous signing.
        idle_ttl_seconds: Sliding idle TTL (seconds).
        hard_cap_seconds: Hard session cap (seconds, default 30 min).

    Returns:
        The CSRF token string (also set as the ``gruvax_csrf`` cookie value).
    """
    session_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=idle_ttl_seconds)
    hard_expires_at = now + timedelta(seconds=hard_cap_seconds)

    await conn.execute(
        "INSERT INTO gruvax.admin_sessions"
        " (id, created_at, last_seen_at, expires_at, hard_expires_at)"
        " VALUES (%s, %s, %s, %s, %s)",
        (session_id, now, now, expires_at, hard_expires_at),
    )
    await conn.commit()

    # Sign the session UUID so an attacker cannot forge a valid cookie value
    signer = _make_signer(secret_key)
    signed_session_id = signer.dumps(session_id)

    # CSRF token: random hex, stored in a non-HttpOnly cookie so JS can read it
    csrf_token = secrets.token_hex(32)

    # Session cookie: HttpOnly=True — JavaScript cannot read it (XSS mitigation).
    # secure=False for home-LAN HTTP; set to True in production HTTPS.
    response.set_cookie(
        SESSION_COOKIE,
        signed_session_id,
        httponly=True,
        samesite="strict",
        secure=False,
    )
    # CSRF cookie: httponly=False — the SPA MUST read it to echo as X-CSRF-Token.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        samesite="strict",
        secure=False,
    )
    return csrf_token


async def get_session_id(request: Any, secret_key: str) -> str | None:
    """Extract and verify the session ID from the signed session cookie.

    Args:
        request:    FastAPI ``Request`` with cookies.
        secret_key: ``settings.SESSION_SECRET`` for signature verification.

    Returns:
        The session UUID string if the cookie is valid; ``None`` otherwise
        (missing cookie, invalid signature, or tampered value).
    """
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie:
        return None
    try:
        signer = _make_signer(secret_key)
        session_id: str = signer.loads(cookie)
        return session_id
    except Exception:
        return None


async def revoke_session(conn: Any, session_id: str) -> None:
    """Mark a single session as revoked (logout, D-03b).

    Sets ``revoked_at = now()`` on the session row so future requests with
    this session cookie receive 401.  The cookie is cleared by the logout
    handler separately.

    Args:
        conn:       Open psycopg connection (caller owns lifecycle).
        session_id: The UUID of the session to revoke.
    """
    now = datetime.now(UTC)
    await conn.execute(
        "UPDATE gruvax.admin_sessions SET revoked_at = %s WHERE id = %s",
        (now, session_id),
    )
    await conn.commit()


async def revoke_all_sessions_except(
    conn: Any,
    current_session_id: str,
) -> None:
    """Revoke ALL sessions EXCEPT the caller's current session (Change-PIN, D-03b).

    After a PIN change, all other sessions are invalidated so a stolen/lost
    device cannot continue using a cached session (T-03-07, T-03-08).

    Args:
        conn:               Open psycopg connection (caller owns lifecycle).
        current_session_id: The session ID to preserve (the one that changed the PIN).
    """
    now = datetime.now(UTC)
    await conn.execute(
        "UPDATE gruvax.admin_sessions"
        " SET revoked_at = %s"
        " WHERE revoked_at IS NULL AND id != %s",
        (now, current_session_id),
    )
    await conn.commit()


def clear_session_cookies(response: Response, secure: bool = False) -> None:
    """Clear both session cookies (set them as expired).

    Called by the logout handler after revoking the session row.

    The delete_cookie attributes MUST match the set_cookie attributes exactly
    (path, httponly, secure, samesite) so browsers remove the cookie (CR-04).
    The ``secure`` parameter must match what was used in create_session — pass
    ``True`` in production HTTPS environments.

    Args:
        response: FastAPI ``Response`` to modify.
        secure:   Whether the cookies were set with Secure=True (default False
                  for home-LAN HTTP). Set to True in production HTTPS.
    """
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )
    response.delete_cookie(
        CSRF_COOKIE,
        path="/",
        httponly=False,
        samesite="strict",
        secure=secure,
    )

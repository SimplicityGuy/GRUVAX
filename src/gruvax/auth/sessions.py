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

from datetime import UTC, datetime, timedelta
import secrets
from typing import TYPE_CHECKING, Any
import uuid

from itsdangerous import URLSafeSerializer


if TYPE_CHECKING:
    from fastapi import Request, Response


# Cookie name constants — imported by deps.py, login.py, tests/conftest.py
SESSION_COOKIE = "gruvax_session"
CSRF_COOKIE = "gruvax_csrf"

# Browse-binding cookie (D2-10 — INDEPENDENT of admin session cookie).
# httponly=False: SPA reads it to derive per-profile SSE URL.
# samesite=strict: home LAN same-site; secure=False for LAN HTTP.
# max_age=7 days: kiosk Chromium survives restarts without forcing /select.
# Value = plain UUID string — server validates against active-profiles set
# on every per-profile endpoint (D2-04, T-02-04-01); no signing needed on LAN.
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"

# Device fingerprint cookie (DEV-01 — INDEPENDENT of admin session + browse-binding).
# HttpOnly=True: JS must NEVER read the fingerprint — it is a session-equivalent
# secret (T-03-01). The SPA identifies the device by device_id (non-secret UUID)
# returned by GET /api/session; the fingerprint itself never reaches the DOM.
# max_age=30 days: Chromium only writes cookies to disk (user-data-dir) when
# max_age is explicitly set — session cookies are NOT persisted on browser exit
# (RESEARCH.md Pitfall 1, verified: Playwright issue #36139 upstream Chromium).
# Secure=False for home-LAN HTTP; set True when TLS lands (mirrors BROWSE_BINDING).
# The 30-day horizon outlives any reboot cycle; revocation is authoritative (D3-07).
FINGERPRINT_COOKIE = "gruvax_device_fp"
FINGERPRINT_MAX_AGE = 30 * 24 * 3600

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
        "UPDATE gruvax.admin_sessions SET revoked_at = %s WHERE revoked_at IS NULL AND id != %s",
        (now, current_session_id),
    )
    await conn.commit()


def set_browse_binding_cookie(
    response: Response,
    profile_id: str,
    secure: bool = False,
    max_age: int = 7 * 24 * 3600,
) -> None:
    """Set the browse-binding cookie (D2-10 — independent of admin session).

    httponly=False: the SPA must read the cookie to build the per-profile
    SSE URL (e.g., ``/api/events/{profile_id}``).
    samesite=strict: all GRUVAX requests are same-site on the home LAN;
    this blocks cross-site POST forging a bind (T-02-04-04).
    secure=False: home-LAN HTTP; set True in a future TLS deployment.
    max_age=7 days: kiosk Chromium survives a Pi reboot without returning
    to the profile-picker screen every morning.

    Value is the plain profile UUID string — the server validates it against
    the active-profiles registry on every per-profile endpoint (D2-04,
    T-02-04-01), so a forged / stale UUID resolves to 404/403.

    Args:
        response:   FastAPI ``Response`` to attach the cookie to.
        profile_id: UUID string of the profile to bind.
        secure:     Whether to set the ``Secure`` flag (default False).
        max_age:    Cookie max-age in seconds (default 7 days).
    """
    response.set_cookie(
        BROWSE_BINDING_COOKIE,
        profile_id,
        httponly=False,
        samesite="strict",
        secure=secure,
        max_age=max_age,
    )


def clear_browse_binding_cookie(response: Response, secure: bool = False) -> None:
    """Clear the browse-binding cookie (Switch-profile unbind, D2-07).

    The ``delete_cookie`` attributes MUST match the ``set_cookie`` attributes
    exactly (path, httponly, secure, samesite) so browsers actually remove the
    cookie (same constraint as ``clear_session_cookies``, CR-04).

    Args:
        response: FastAPI ``Response`` to modify.
        secure:   Whether the cookie was set with ``Secure=True`` (default False).
    """
    response.delete_cookie(
        BROWSE_BINDING_COOKIE,
        path="/",
        httponly=False,
        samesite="strict",
        secure=secure,
    )


def issue_fingerprint_cookie(response: Response, secure: bool = False) -> str:
    """Issue a new opaque HttpOnly fingerprint cookie and return the raw token.

    Generates a 32-byte CSPRNG token via ``secrets.token_urlsafe(32)`` (256 bits
    of entropy — RESEARCH.md Pattern 1; ASVS V6). Sets the cookie HttpOnly so JS
    can NEVER read it (fingerprint is a session-equivalent secret, T-03-01).

    max_age is required: Chromium does NOT persist session cookies (no max_age) to
    the user-data-dir SQLite store — they vanish on browser exit / Pi reboot.
    Setting max_age=FINGERPRINT_MAX_AGE (30 days) ensures disk persistence
    (RESEARCH.md Pitfall 1, D3-09).

    The raw token value is returned so the caller can persist it to gruvax.devices.
    NEVER log this value — treat with the same redaction discipline as the admin PIN
    (RESEARCH.md Pitfall 7, T-03-02).

    This cookie is INDEPENDENT of the admin session cookie (D3-04). Do not couple
    it to set_browse_binding_cookie — they serve different security domains.

    Args:
        response: FastAPI ``Response`` to attach the cookie to.
        secure:   Whether to set the ``Secure`` flag (default False for LAN HTTP;
                  set True when TLS lands in a future deployment).

    Returns:
        The raw fingerprint token string (do not log; store to DB as-is).
    """
    fp = secrets.token_urlsafe(32)  # 32 bytes → ~43 URL-safe chars, 256-bit CSPRNG
    set_fingerprint_cookie(response, fp, secure=secure)
    return fp


def set_fingerprint_cookie(response: Response, fp: str, secure: bool = False) -> None:
    """Attach the fingerprint cookie with a CALLER-SUPPLIED token value.

    Use when the token was already generated (or read) and must be set on a
    different ``Response`` object than the one it was first issued on — e.g. when
    an endpoint persists the fingerprint to the DB and then returns a fresh
    ``JSONResponse``. Calling ``issue_fingerprint_cookie`` twice would mint a
    SECOND, divergent token, desyncing the DB-stored fingerprint from the client
    cookie (the device would never resolve on subsequent requests). Always issue
    the token once, then propagate the same value with this helper.

    Attributes mirror ``issue_fingerprint_cookie`` exactly (HttpOnly, SameSite=Strict,
    max_age=30d) so the cookie persists across Pi reboots (RESEARCH.md Pitfall 1, D3-09).
    NEVER log ``fp`` — it is a session-equivalent secret (T-03-02).
    """
    response.set_cookie(
        FINGERPRINT_COOKIE,
        fp,
        httponly=True,
        samesite="strict",
        secure=secure,
        max_age=FINGERPRINT_MAX_AGE,
    )


def get_fingerprint(request: Request) -> str | None:
    """Extract the fingerprint from the HttpOnly cookie (None if absent).

    Returns the raw opaque token string, or None if the fingerprint cookie is not
    present in the request. Callers use this to identify devices on each request.

    NEVER log the returned value — it is a session-equivalent secret (T-03-02).

    Args:
        request: FastAPI ``Request`` with cookies.

    Returns:
        The fingerprint token string, or ``None`` if the cookie is absent.
    """
    return request.cookies.get(FINGERPRINT_COOKIE)


def clear_fingerprint_cookie(response: Response, secure: bool = False) -> None:
    """Clear the fingerprint cookie (device unbind / revoke, D3-07).

    The ``delete_cookie`` attributes MUST match the ``set_cookie`` attributes
    exactly (path, httponly, samesite, secure) so browsers actually remove the
    cookie. Mismatched attributes would be treated as a different cookie by the
    browser, leaving the old fingerprint alive — the CR-04 invariant enforced here
    mirrors ``clear_browse_binding_cookie`` (lines 248-268).

    Args:
        response: FastAPI ``Response`` to modify.
        secure:   Whether the cookie was set with ``Secure=True`` (default False).
    """
    response.delete_cookie(
        FINGERPRINT_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=secure,
    )


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

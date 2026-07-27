"""Kiosk device endpoints — pairing-code generation and device state polling.

Endpoints (no PIN required — kiosk-facing):
  POST /api/devices/pairing-codes — generate a 4-digit pairing code (5-min TTL);
                                     auto-issue HttpOnly fingerprint cookie on first request
  GET  /api/devices/me            — return device state for the current fingerprint cookie:
                                    {state: 'unpaired'|'pending'|'paired'|'revoked', profile_id?}

gruvax-6ip0 (clock skew): the pairing-codes response carries ``remaining_seconds``,
a server-computed DURATION (``EXTRACT(EPOCH FROM (expires_at - NOW()))``), alongside
``expires_at``. The kiosk countdown (PairView.tsx) counts down from that duration
using its own monotonic clock rather than repeatedly diffing the client's wall clock
against the server's absolute ``expires_at`` — so a Pi that cold-boots with its clock
still behind (no RTC battery fitted, fake-hwclock restores time from last shutdown
until systemd-timesyncd catches up) still gets a correct 5:00 countdown instead of a
bogus one, or worse, a code that renders already-expired.

gruvax-8fp (namespace exhaustion): the CHAR(4) code PK is a 10,000-value
namespace with no cleanup — every reroll (a kiosk parked on /pair auto-rerolls
every 5 minutes, ~288/day) permanently consumed a slot (ON CONFLICT ... DO
NOTHING never reclaims an expired/consumed row), so an idle kiosk alone
exhausted the namespace within ~5 weeks, and any unauthenticated LAN client
could exhaust it in seconds (no auth, no rate limit on this endpoint).
generate_pairing_code now (1) sweeps expired-or-consumed rows once per
generation request, before the insert-retry loop (cheap — assisted by
idx_pairing_codes_expires — and keeps
the live table bounded to roughly one 5-minute window's worth of codes
regardless of how long the deployment has been running) and (2) rate-limits
generation per IP (see limiter.py) so brute-force exhaustion can't happen in
seconds even from a single unauthenticated client.

Security:
  - Fingerprint value is NEVER logged (RESEARCH.md Pitfall 7)
  - All SQL uses parameterized %s — no f-strings in query text (bandit B608)
  - Code uniqueness enforced via ON CONFLICT DO NOTHING + retry loop (RESEARCH.md Pattern 2)
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from gruvax.api.admin.limiter import _PAIRING_GENERATE_RATE, _rate_limiter
from gruvax.auth.sessions import get_fingerprint, set_fingerprint_cookie


logger = logging.getLogger(__name__)

router = APIRouter(tags=["devices"])

# ── SQL constants — parameterized %s, never f-strings (bandit B608) ──────────

# gruvax-8fp: sweep expired-or-consumed rows before every generation attempt.
# Assisted by idx_pairing_codes_expires (migration 0011). Run once per request
# (not once per retry iteration below) — cheap, and keeps the live table
# bounded to roughly one 5-minute window's worth of codes regardless of
# deployment age, which is what actually prevents the 10,000-code CHAR(4)
# namespace from ever filling up.
_SWEEP_EXPIRED_CODES = (
    "DELETE FROM gruvax.pairing_codes WHERE expires_at < NOW() OR consumed_at IS NOT NULL"
)

# INSERT a new pairing code; ON CONFLICT (code) DO NOTHING so that a collision
# on the CHAR(4) PK is silently discarded and the caller retries.
# RETURNING code confirms the insert succeeded (not just a conflict).
_INSERT_PAIRING_CODE = (
    "INSERT INTO gruvax.pairing_codes (code, fingerprint, expires_at)"
    " VALUES (%s, %s, NOW() + INTERVAL '5 minutes')"
    " ON CONFLICT (code) DO NOTHING"
    " RETURNING code, expires_at,"
    " EXTRACT(EPOCH FROM (expires_at - NOW()))::int AS remaining_seconds"
)

# SELECT device row by fingerprint — intentionally selects the raw fingerprint
# column to match the DB row, but fingerprint is NOT returned to clients.
#
# gruvax-gqe: idx_devices_fingerprint_active (migration 0011) only enforces
# uniqueness among ACTIVE rows, so a revoked row can coexist with an active one
# for the same fingerprint. Without an ORDER BY, fetchone() is nondeterministic —
# prefer the active row, tie-break on the most recently created row.
_SELECT_DEVICE_BY_FINGERPRINT = (
    "SELECT id, profile_id, revoked_at FROM gruvax.devices WHERE fingerprint = %s"
    " ORDER BY revoked_at IS NULL DESC, created_at DESC"
    " LIMIT 1"
)


# ── POST /api/devices/pairing-codes ──────────────────────────────────────────


def _check_pairing_generate_rate_limit(request: Request) -> None:
    """Enforce the pairing-code generation rate limit (gruvax-8fp).

    This endpoint is intentionally unauthenticated (a kiosk hasn't paired
    yet), so without a rate limit any LAN client could loop this endpoint and
    exhaust the 10,000-code namespace in seconds. 30/5min per IP comfortably
    covers a legitimate kiosk's steady-state 1-per-5-min auto-reroll (plus the
    occasional gruvax-7j5 failure-retry burst) while still bounding
    worst-case abuse.

    Rate-limit key: direct socket peer IP — see login.py's identical caveat
    (correct for GRUVAX's single-host home-LAN deployment with no reverse
    proxy).
    """
    client_ip: str = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_PAIRING_GENERATE_RATE, "pairing_generate", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "rate_limited",
                "message": "Too many pairing-code requests. Try again later.",
            },
        )


@router.post("/devices/pairing-codes")
async def generate_pairing_code(
    request: Request,
) -> JSONResponse:
    """Generate a 4-digit pairing code (5-min TTL) and auto-issue the fingerprint cookie.

    If no fingerprint cookie is present, one is issued via ``issue_fingerprint_cookie``
    and attached to the response.

    Returns:
        ``{code: "XXXX", expires_at: ISO-8601, remaining_seconds: int}``

    ``remaining_seconds`` (gruvax-6ip0) is a server-computed DURATION, not a
    timestamp — the kiosk counts down from it locally instead of repeatedly
    diffing its own (possibly skewed, e.g. pre-NTP-sync on a cold Pi boot)
    wall clock against the server-absolute ``expires_at``.

    Security: fingerprint value is never logged (RESEARCH.md Pitfall 7).
    Code collisions are handled with up to 3 retries (RESEARCH.md Pattern 2 + Pitfall 6).
    Rate-limited per IP (gruvax-8fp) — 429 ``{type: "rate_limited"}`` past the limit.
    """
    # gruvax-8fp: rate-limit check must be first, before any DB or fingerprint work.
    _check_pairing_generate_rate_limit(request)

    # Retrieve or issue the fingerprint cookie — auto-issue on first visit.
    # Generate the token ONCE here so the exact same value is both stored in
    # gruvax.pairing_codes (below) AND set on the response cookie. Calling
    # issue_fingerprint_cookie twice (once per Response object) would mint two
    # divergent CSPRNG tokens — the DB would hold one, the kiosk the other, and
    # the device would never resolve on GET /api/session (D3-04 desync bug).
    fp = get_fingerprint(request)
    new_fp_issued = fp is None
    if fp is None:
        fp = secrets.token_urlsafe(32)  # 256-bit CSPRNG — matches issue_fingerprint_cookie
    # fp is now guaranteed non-None; never log its value.

    db_pool = request.app.state.db_pool

    # gruvax-8fp: sweep expired/consumed rows BEFORE attempting an insert —
    # once per request, not once per retry iteration below. This is what
    # actually prevents the 10,000-code namespace from ever filling up,
    # regardless of how long the deployment has been running.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_SWEEP_EXPIRED_CODES)
        await conn.commit()

    # Collision-retry loop: at household scale (<<100 pending codes) the
    # probability of 3 consecutive PK collisions is negligible (~(N/10000)^3).
    code: str | None = None
    expires_at_iso: str | None = None
    remaining_seconds: int = 0

    for _ in range(3):
        candidate = f"{secrets.randbelow(10000):04d}"  # '0000'..'9999' via OS CSPRNG
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_INSERT_PAIRING_CODE, (candidate, fp))
            row = await cur.fetchone()
            await conn.commit()
        if row is not None:
            code = row[0]
            expires_at = row[1]
            expires_at_iso = (
                expires_at.isoformat() if hasattr(expires_at, "isoformat") else str(expires_at)
            )
            # gruvax-6ip0: server-computed duration, immune to client clock skew.
            remaining_seconds = int(row[2]) if row[2] is not None else 0
            break

    if code is None:
        logger.error("generate_pairing_code: failed to generate unique code after 3 attempts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "type": "code_generation_failed",
                "message": "Failed to generate unique pairing code",
            },
        )

    # Build the JSON response and attach the fingerprint cookie (with the SAME
    # token that was just stored in pairing_codes) only if it was freshly issued.
    json_response = JSONResponse(
        content={
            "code": code,
            "expires_at": expires_at_iso,
            "remaining_seconds": remaining_seconds,
        }
    )
    if new_fp_issued:
        set_fingerprint_cookie(json_response, fp)
    return json_response


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

    _device_id, profile_id, revoked_at = row

    if revoked_at is not None:
        return JSONResponse(content={"state": "revoked"})

    if profile_id is None:
        # Device row exists but no profile bound (orphaned or pending bind).
        return JSONResponse(content={"state": "pending"})

    # Paired: non-null profile_id, not revoked.
    return JSONResponse(content={"state": "paired", "profile_id": str(profile_id)})

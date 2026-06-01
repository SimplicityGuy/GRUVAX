"""Invite-code endpoints for member self-connect PAT flow (AUTH-02).

Two routers are exposed:

owner_router — PIN-gated, registered under /api/admin by create_admin_router():
  POST /profiles/{id}/invite  — generate a 1-hour single-use invite link (D-01, D-09)

public_router — NO PIN required, registered directly on the main app before StaticFiles:
  GET  /invite-codes/{code}        — validate code, return profile display_name (D-03)
  POST /invite-codes/{code}/redeem — accept member PAT, validate, encrypt, store, auto-sync

Security contract (threat register §T-07-05 through §T-07-12):
  - UUID4 code = 122-bit entropy; per-IP rate limit 5/10min on redeem (T-07-05).
  - Atomic UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id
    makes the consume single-use and race-safe under PostgreSQL READ COMMITTED (T-07-06).
  - Redeem returns only {status, profile_id}; PAT is never echoed (T-07-07).
  - No error/detail/log string is constructed from body.pat (T-07-08).
  - encrypt_pat() (Fernet) before the bytea write (T-07-09).
  - All negative invite cases return uniform 404 invite_not_found (T-07-10).
  - _run_test_sync runs with NO pool slot held (pool-isolation discipline, T-07-11).
  - Redeem onto a profile with an existing token OVERWRITES it (D-10, T-07-12 accept).

Pool-isolation discipline (mirrors profiles.py connect_pat, Pitfall 1 / Pitfall 6):
  Step 1 — consume invite (pool acquired → released).
  Step 2 — validate PAT via _run_test_sync (HTTP call, NO pool slot held).
  Step 3 — collision check (pool acquired → released).
  Step 4 — store encrypted PAT (pool acquired → released).
  Step 5 — add background sync task.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.api.admin.limiter import _REDEEM_RATE, _rate_limiter
from gruvax.api.admin.profile_sync import _run_sync_background
from gruvax.api.deps import get_pool, require_admin
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
)
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat


logger = logging.getLogger(__name__)

# ── Router definitions ─────────────────────────────────────────────────────────

# Owner-side router: generate endpoint (PIN-gated via Depends(require_admin)).
# Registered under /api/admin by create_admin_router().
owner_router = APIRouter(tags=["invite-owner"])

# Public router: validate + redeem endpoints (NO require_admin — Pitfall 8 / D-03).
# Registered directly on the main app before StaticFiles.
public_router = APIRouter(tags=["invite-public"])


# ── SQL constants (no f-strings — bandit B608) ────────────────────────────────

# Void any prior unredeemed/unexpired invite for the profile (D-09 one-active rule).
# Runs in the same transaction as _INSERT_INVITE so void + insert are atomic.
_VOID_PRIOR_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE profile_id = %s::uuid"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
)

# Insert a new invite code with a 1-hour TTL (D-01).
# gen_random_uuid() produces a UUID4 (122-bit entropy, T-07-05).
_INSERT_INVITE = (
    "INSERT INTO gruvax.profile_invite_codes (code, profile_id, expires_at)"
    " VALUES (gen_random_uuid(), %s::uuid, NOW() + INTERVAL '1 hour')"
    " RETURNING code::text, expires_at"
)

# Atomic "first wins" single-use consume (T-07-06).
# Under PostgreSQL READ COMMITTED the first transaction acquires the row lock;
# the second re-evaluates WHERE and finds consumed_at IS NOT NULL → zero rows.
# Uniform: expired / consumed / non-existent all return no row (Pitfall 2 / T-07-10).
_CONSUME_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s::uuid"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING profile_id"
)

# Public GET: validate a code without consuming it.
# Returns display_name + expires_at only when the code is valid and not consumed.
_SELECT_INVITE = (
    "SELECT p.display_name, pic.expires_at"
    " FROM gruvax.profile_invite_codes pic"
    " JOIN gruvax.profiles p ON p.id = pic.profile_id"
    " WHERE pic.code = %s::uuid"
    "   AND pic.consumed_at IS NULL"
    "   AND pic.expires_at > NOW()"
    "   AND p.deleted_at IS NULL"
)


# ── Request model ──────────────────────────────────────────────────────────────


class RedeemRequest(BaseModel):
    """Request body for POST /invite-codes/{code}/redeem."""

    pat: str


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_invite_uuid(code: str) -> uuid.UUID:
    """Parse code as UUID, raising uniform 404 on failure (Pitfall 2 / T-07-10).

    Never echo the code back in any error detail — no oracle surface.
    """
    try:
        return uuid.UUID(code)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "invite_not_found"},
        ) from None


def _check_redeem_rate_limit(request: Request) -> None:
    """Enforce per-IP rate limit on the public redeem endpoint (T-07-05).

    Uses the shared _rate_limiter singleton with namespace "invite_redeem" so it
    does not share the login or device_bind counter.
    Raises HTTPException(429) when the caller exceeds 5 requests per 10 minutes.
    """
    client_ip: str = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_REDEEM_RATE, "invite_redeem", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "type": "rate_limited",
                "message": "Too many attempts. Wait a moment and try again.",
            },
        )


async def _run_test_sync(pat: str) -> str:
    """Run a per_page=1 test-sync against discogsography; return user_id.

    Duplicated from profiles.py to avoid importing a private function across modules.
    Uses profile_sync._make_client so tests can monkeypatch the factory.
    Raises PATRejected (401), RateLimitExhausted (503), ServerError / NetworkError (503).
    """
    client = profile_sync._make_client(settings.DISCOGSOGRAPHY_BASE_URL, pat)
    try:
        page = await client._get_page(limit=1, offset=0)
        user_id = str(page["user_id"])
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()
    return user_id


# ── Owner-side: POST /profiles/{id}/invite ────────────────────────────────────


@owner_router.post("/profiles/{profile_id}/invite")
async def generate_invite(
    profile_id: str,
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Generate a 1-hour single-use invite link for a profile (PIN-gated).

    Voids any prior unredeemed/unexpired invite for the same profile (D-09) and
    inserts a new UUID code with a 1-hour TTL (D-01) — both in one transaction.
    Returns {code, url, expires_at}.

    The url is constructed from request.base_url so it is correct across
    environments (RESEARCH Open Question 3 — base_url is authoritative).
    """
    try:
        uid = uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        ) from None

    db_pool = request.app.state.db_pool

    # Guard existence before the FK insert: a soft-deleted or unknown profile_id
    # would otherwise surface the profile_invite_codes FK violation as an
    # unhandled 500. Mirror the _require_profile() preflight used by every other
    # mutating profile endpoint (WR-03). Tight pool checkout, released immediately.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
            (str(uid),),
        )
        if await cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "profile_not_found"},
            )

    async with db_pool.connection() as conn, conn.cursor() as cur:
        # D-09: void prior unredeemed invite before inserting the new one (atomic).
        await cur.execute(_VOID_PRIOR_INVITE, (str(uid),))
        await cur.execute(_INSERT_INVITE, (str(uid),))
        row = await cur.fetchone()
        await conn.commit()

    if row is None:
        # INSERT ... RETURNING should always return a row; guard against edge case.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"type": "invite_generation_failed"},
        )

    code_str, expires_at = row
    url = str(request.base_url) + f"redeem/{code_str}"

    return JSONResponse(
        content={
            "code": code_str,
            "url": url,
            "expires_at": expires_at.isoformat(),
        }
    )


# ── Public: GET /invite-codes/{code} ─────────────────────────────────────────


@public_router.get("/invite-codes/{code}")
async def get_invite(
    code: str,
    pool: Any = Depends(get_pool),
) -> JSONResponse:
    """Public: validate a code and return the profile display_name.

    Returns 404 for all negative cases — expired, consumed, invalid-UUID, or
    non-existent codes all return the same uniform 404 invite_not_found (Pitfall 2
    / T-07-10). Never echoes the code in any error response.
    """
    code_uuid = _parse_invite_uuid(code)

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_SELECT_INVITE, (str(code_uuid),))
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "invite_not_found"},
        )

    display_name, expires_at = row
    return JSONResponse(
        content={
            "display_name": display_name,
            "expires_at": expires_at.isoformat(),
        }
    )


# ── Public: POST /invite-codes/{code}/redeem ──────────────────────────────────


@public_router.post("/invite-codes/{code}/redeem")
async def redeem_invite(
    code: str,
    request: Request,
    body: RedeemRequest,
    background_tasks: BackgroundTasks,
    pool: Any = Depends(get_pool),
) -> JSONResponse:
    """Public: consume invite, validate PAT, store encrypted, auto-sync.

    Pool-isolation discipline (Pitfall 1 — no pool slot held during HTTP call):
      1. Consume invite atomically (pool acquired + released).
      2. Validate PAT via _run_test_sync (HTTP call — NO pool slot held).
      3. Collision check (pool acquired + released).
      4. Store Fernet-encrypted PAT + clear revoked flag (pool acquired + released).
      5. Add background sync task (D-04 auto-sync mirrors connect_pat).

    Error taxonomy (all negative invite cases → uniform 404, no oracle — T-07-10):
      404 invite_not_found  — expired, consumed, non-existent, or invalid UUID
      401 pat_rejected      — discogsography returned 401/403
      409 user_id_collision — user_id already on another active profile
      503 upstream_unavailable — discogsography rate-limited or server error
      429 rate_limited      — per-IP redeem rate limit exceeded (T-07-05)

    Security: body.pat is NEVER included in any log line or error detail (T-07-08).
    D-10: redeeming onto a profile with an existing token OVERWRITES it (no guard).
    """
    # Rate-limit check FIRST (T-07-05).
    _check_redeem_rate_limit(request)

    # Uniform 404 on invalid UUID (Pitfall 2 / T-07-10 — no oracle).
    code_uuid = _parse_invite_uuid(code)

    # Step 1: atomic consume (pool acquired + released BEFORE the HTTP call — Pitfall 1).
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_CONSUME_INVITE, (str(code_uuid),))
        row = await cur.fetchone()
        await conn.commit()

    if row is None:
        # Code expired, already consumed, or non-existent — uniform 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "invite_not_found"},
        )

    profile_id: str = str(row[0])

    # Step 2: validate PAT — NO pool slot held during this HTTP call (Pitfall 1 / T-07-11).
    # body.pat must NOT appear in any log message or error detail string (T-07-08).
    try:
        new_user_id = await _run_test_sync(body.pat)
    except PATRejected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "pat_rejected", "message": "PAT rejected by discogsography (401/403)"},
        ) from None
    except RateLimitExhausted as exc:
        # T-07-08 (WR-02): never forward upstream (discogsography) error text into
        # the public response body — use a fixed, generic message. The original
        # exception is still chained (`from exc`) for server-side logs.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "upstream_unavailable", "message": "Discogs is temporarily unavailable. Please try again shortly."},
        ) from exc
    except (ServerError, NetworkError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "upstream_unavailable", "message": "Discogs is temporarily unavailable. Please try again shortly."},
        ) from exc

    # Step 3: D-09 strict user_id collision check (mirrors connect_pat lines 476-497).
    # Another ACTIVE profile must not already hold this discogsography_user_id.
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles"
            " WHERE discogsography_user_id = %s::uuid"
            "   AND id != %s::uuid"
            "   AND deleted_at IS NULL",
            (new_user_id, profile_id),
        )
        collision_row = await cur.fetchone()

    if collision_row is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"type": "user_id_collision"},
        )

    # Step 4: store Fernet-encrypted PAT + flip revoked=FALSE (T-07-09 / D-10).
    # D-10: no guard on existing token — COALESCE preserves the existing user_id if set.
    ciphertext = encrypt_pat(body.pat)
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET"
            "    app_token_encrypted = %s::bytea,"
            "    app_token_revoked = FALSE,"
            "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid),"
            "    last_sync_status = NULL,"
            "    last_sync_error = NULL"
            " WHERE id = %s::uuid AND deleted_at IS NULL",
            (ciphertext, new_user_id, profile_id),
        )
        await conn.commit()

    # Step 5: kick background sync (D-04 auto-sync mirrors connect_pat lines 514-519).
    background_tasks.add_task(
        _run_sync_background,
        profile_id=profile_id,
        app_state=request.app.state,
    )

    return JSONResponse(content={"status": "connected", "profile_id": profile_id})

"""POST /api/admin/profiles/{profile_id}/sync — manually trigger a profile sync (D-10).

Endpoint:
  POST /api/admin/profiles/{profile_id}/sync

Auth (per PATTERNS §Shared Patterns "Authentication"):
  - Session cookie + CSRF double-submit gated by ``require_admin``.
  - Same protection as every other admin write.

Response taxonomy:
  - 200: ``{"status":"ok","item_count":N,"took_ms":T,"user_id":U}`` (D-14 — caches
    refreshed inline before returning).
  - 400: ``{"type":"invalid_uuid"}`` — path param is not a UUID.
  - 401: missing/invalid session cookie (from ``require_admin``).
  - 401: ``{"type":"pat_rejected"}`` — discogsography returned 401/403.
  - 403: ``{"type":"csrf_check_failed"}`` (from ``require_admin``).
  - 404: ``{"type":"profile_not_found"}`` — UUID resolved but profile missing
    or soft-deleted.
  - 409: ``{"type":"already_in_progress"}`` — pg advisory lock held by a
    concurrent sync (raised as ``SyncInProgress`` by ``sync_profile``).
  - 503: ``{"type":"rate_limited_upstream"}`` — ``RateLimitExhausted``.
  - 503: ``{"type":"upstream_unavailable"}`` — ``ServerError`` / ``NetworkError``.

Pitfall 6 — handler MUST NOT inject the connection pool via the standard
admin-handler dependency:
  The standard admin handler analog (``editing.py``) injects the pool
  through the ``get_pool`` FastAPI dependency. That keeps the pool slot
  attached for the request lifetime — fine for a heartbeat, fatal for a
  multi-second sync. If this handler held a slot, a small pool would be
  starved by a single in-flight sync, blocking concurrent admin requests
  (PATTERNS §Shared Patterns "Authentication — EXCEPTION FOR LONG-RUNNING
  OPERATIONS").

  Correct pattern (used below):
    1. Accept ``request: Request`` and read ``request.app.state.db_pool``.
    2. Open a tight ``async with db_pool.connection() as conn`` block for
       the 404 pre-flight check.
    3. CLOSE the block before awaiting ``sync_profile`` — the pool slot is
       returned to the pool BEFORE the long-running call starts.
    4. ``sync_profile`` itself acquires a dedicated ``psycopg.AsyncConnection``
       for the sync body (Plan 03 mitigation); the pool stays free.

  Static grep gate (Plan 04 Task 1 Test 10): the source must contain ZERO
  occurrences of the literal pool-dependency-injection token; the assert
  message in the test names the exact pattern.
"""

from __future__ import annotations

import logging
import time
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from gruvax.api.deps import require_admin
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
    SyncInProgress,
)
from gruvax.sync.profile_sync import sync_profile


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-profile-sync"])


@router.post("/profiles/{profile_id}/sync")
async def trigger_sync(
    profile_id: str,
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
    # NO pool injection here — see module docstring. The handler reaches into
    # request.app.state.db_pool directly so the pool slot is only held for the
    # short-lived 404 pre-flight, not the full sync.
) -> JSONResponse:
    """Manually trigger a profile sync. PIN + CSRF gated.

    The handler does three things, in order:

    1. Validate ``profile_id`` is a UUID (400 on parse failure).
    2. Pre-flight check: SELECT 1 inside a tight ``async with`` block to
       confirm the profile exists and is not soft-deleted; the pool slot
       is released BEFORE step 3.
    3. ``await sync_profile(profile_id, request.app.state)`` — runs on a
       dedicated psycopg connection acquired by ``sync_profile`` itself
       (Pitfall 6 mitigation, Plan 03).

    All terminal sync_profile exceptions are translated to structured
    HTTPException responses with a ``detail.type`` discriminator.
    """
    try:
        uid = uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
        ) from None

    # 404 pre-flight check on a short-lived pool checkout.
    db_pool = request.app.state.db_pool
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
    # async-with block CLOSED here — pool slot RETURNED before await sync_profile.

    t0 = time.perf_counter()
    try:
        result = await sync_profile(str(uid), request.app.state)
    except SyncInProgress as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"type": "already_in_progress", "message": str(e)},
        ) from e
    except PATRejected as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "pat_rejected", "message": str(e)},
        ) from e
    except RateLimitExhausted as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "rate_limited_upstream", "message": str(e)},
        ) from e
    except (ServerError, NetworkError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"type": "upstream_unavailable", "message": str(e)},
        ) from e

    took_ms = (time.perf_counter() - t0) * 1000.0
    # sync_profile already returns took_ms; overwrite with the handler-measured
    # value so the response reflects total endpoint time (including the 404
    # pre-flight + result serialization), not just the inner sync_profile body.
    body: dict[str, Any] = {**result, "took_ms": round(took_ms, 2)}
    logger.info(
        "profile sync ok: profile=%s item_count=%d took_ms=%.2f",
        profile_id,
        body.get("item_count", -1),
        body["took_ms"],
    )
    return JSONResponse(content=body)

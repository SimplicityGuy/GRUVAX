"""POST /api/admin/profiles/{profile_id}/sync — manually trigger a profile sync (D-10).

Poller contract (02-08):
  The frontend poller (ProfileDrawer.tsx refetchInterval) keeps polling
  GET /api/admin/profiles/{id} until a TERMINAL status ('ok' | 'failed') is
  observed — it does NOT stop on 'in_progress' or null. The backend MUST
  therefore never expose a non-terminal, non-'in_progress' status during an
  active sync window.

  Audit result — the only observable last_sync_status transitions during a
  sync are:

    ① null / prior terminal (before trigger_sync)
    ② 'in_progress'  — written synchronously by trigger_sync before 202 returns
    ③ 'ok'           — written atomically with last_sync_item_count inside
                       sync.profile_sync._swap_inside_tx (one conn.transaction())
       OR
       'failed'       — written by sync.profile_sync._record_failure on any error

  There is NO intermediate write that sets status to null or any other
  non-terminal, non-'in_progress' value once a sync is in flight. The
  'item_count + terminal status' flip is a single UPDATE inside one
  transaction, so no observer can see a split state (item_count updated
  but status still 'in_progress', or vice versa).

  See: src/gruvax/sync/profile_sync.py::_swap_inside_tx

Endpoint:
  POST /api/admin/profiles/{profile_id}/sync

Auth (per PATTERNS §Shared Patterns "Authentication"):
  - Session cookie + CSRF double-submit gated by ``require_admin``.
  - Same protection as every other admin write.

Response taxonomy:
  - 202: ``{"status":"accepted","profile_id":U}`` — sync queued as a background task.
    Poll GET /api/admin/profiles/{id} for last_sync_status transitions
    (in_progress → ok | failed) to determine completion (D2-13).
  - 400: ``{"type":"invalid_uuid"}`` — path param is not a UUID.
  - 401: missing/invalid session cookie (from ``require_admin``).
  - 403: ``{"type":"csrf_check_failed"}`` (from ``require_admin``).
  - 404: ``{"type":"profile_not_found"}`` — UUID resolved but profile missing
    or soft-deleted.

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
    2. Open a tight ``async with`` block for the 404 pre-flight check.
    3. CLOSE the block before calling add_task — the pool slot is
       returned to the pool BEFORE the long-running sync starts.
    4. ``sync_profile`` itself acquires a dedicated ``psycopg.AsyncConnection``
       for the sync body (Plan 03 mitigation); the pool stays free.

  Static grep gate (Plan 04 Task 1 Test 10): the source must contain ZERO
  occurrences of the literal pool-dependency-injection token; the assert
  message in the test names the exact pattern.

Pitfall 3 — background task exception swallowing:
  FastAPI exception handlers do NOT fire for background tasks (fastapi/fastapi#3589).
  The ``_run_sync_background`` wrapper catches ALL exceptions via bare ``except Exception``
  and logs them with ``logger.exception``. The sync failure is surfaced through the
  DB row's ``last_sync_status='failed'`` which the polling GET /api/admin/profiles/{id}
  returns.
"""

from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from gruvax.api.deps import require_admin
from gruvax.sync.profile_sync import sync_profile


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-profile-sync"])


@router.post("/profiles/{profile_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    profile_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    _admin: dict[str, Any] = Depends(require_admin),
    # NO pool injection here — see module docstring. The handler reaches into
    # request.app.state.db_pool directly so the pool slot is only held for the
    # short-lived 404 pre-flight + in_progress update, not the full sync.
) -> JSONResponse:
    """Manually trigger a profile sync (D2-13). PIN + CSRF gated.

    Returns 202 immediately and runs the sync in a background task.
    The caller must poll GET /api/admin/profiles/{id} to observe
    last_sync_status transitions (in_progress → ok | failed).

    The handler does three things, in order:

    1. Validate ``profile_id`` is a UUID (400 on parse failure).
    2. Pre-flight check: SELECT 1 inside a tight ``async with`` block to
       confirm the profile exists and is not soft-deleted; the pool slot
       is released BEFORE step 3.
    3. Set last_sync_status='in_progress' synchronously so the poller sees
       it immediately, then add ``_run_sync_background`` to background_tasks
       and return 202.
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
    # async-with block CLOSED here — pool slot RETURNED before setting in_progress.

    # Set in_progress synchronously so the poller sees it immediately (D2-13).
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET last_sync_status = 'in_progress', "
            "last_sync_error = NULL WHERE id = %s::uuid",
            (str(uid),),
        )
        await conn.commit()
    # Pool slot RETURNED before add_task.

    background_tasks.add_task(
        _run_sync_background,
        profile_id=str(uid),
        app_state=request.app.state,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={"status": "accepted", "profile_id": str(uid)},
    )


async def _run_sync_background(profile_id: str, app_state: Any) -> None:
    """Background task wrapper — catches ALL exceptions (Pitfall 3).

    FastAPI exception handlers do NOT fire for background tasks
    (fastapi/fastapi#3589). Must catch + log here directly.

    ``sync_profile`` handles: commit → per-profile cache reload → bus.publish
    (Pitfall A ordering preserved inside sync_profile). On failure, sync_profile's
    _record_failure chain already sets last_sync_status='failed' and
    last_sync_error=<tag> — no double-write needed here.
    """
    try:
        await sync_profile(profile_id, app_state)
    except Exception as exc:
        logger.exception(
            "background sync failed for profile=%s: %s", profile_id, exc
        )
        # last_sync_status is already 'failed' via _record_failure inside
        # sync_profile's except chain — no double-write needed here.

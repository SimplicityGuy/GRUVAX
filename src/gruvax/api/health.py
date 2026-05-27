"""GET /api/health — subsystem status for GRUVAX.

Reports:
  - ``db``:                       "ok" | "error:<msg>"
  - ``discogsography_api_check``: "ok" | "failed" | "stale"   (D-13 rename + widening)
  - ``mqtt``:                     "ok" | "degraded"
  - ``status``:                   "ok" | "degraded"
  - ``version``:                  git SHA baked at Docker build time (OBS-04/OBS-01)
  - ``started_at``:               ISO-8601 UTC timestamp of app startup
  - ``sync_age_seconds``:         seconds since last discogsography sync (OBS-06),
                                  float or null. Post-P1 D-13 source: derived from
                                  ``app.state.default_profile_last_sync_at`` (NOT
                                  ``max(v_collection.synced_at)`` — the v_collection
                                  view has been dropped).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse


try:
    from gruvax._version import GIT_SHA
except ImportError:
    GIT_SHA = "dev"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


# D-13 staleness threshold — sync data older than this is considered stale even
# if last_sync_status is 'ok'. Matches the threshold spelled out in CONTEXT D-13
# and the UI-SPEC /api/health state mapping table.
_STALE_THRESHOLD = timedelta(hours=24)


@router.get("/health")
async def get_health(request: Request) -> JSONResponse:
    """Return subsystem health status.

    Does NOT perform a live DB probe on every call (that would add latency
    and hammer Postgres). Instead it reflects the state captured during
    lifespan startup, which is updated by the boundary cache reload (Phase 4)
    and (P1) by the 60-second default-profile-state background refresh
    populating ``app.state.default_profile_*`` attributes.

    Returns HTTP 200 with ``status: "degraded"`` when any subsystem is unhealthy.
    Callers should inspect individual fields, not just the status string.
    """
    db_ok: bool = getattr(request.app.state, "db_ok", False)
    mqtt_ok: bool = getattr(request.app.state, "mqtt_ok", False)
    started_at: datetime = getattr(request.app.state, "started_at", datetime.now(UTC))

    # D-13 three-state derivation per CONTEXT.md + UI-SPEC §/api/health state mapping
    # table + Warning #4 RESOLUTION (in_progress → 'ok' — an active sync is healthy
    # state; the 5-min watchdog in Plan 03 flips hung syncs to 'failed').
    last_sync_at: datetime | None = getattr(request.app.state, "default_profile_last_sync_at", None)
    last_sync_status: str | None = getattr(
        request.app.state, "default_profile_last_sync_status", None
    )
    token_revoked: bool = bool(
        getattr(request.app.state, "default_profile_app_token_revoked", True)
    )
    now = datetime.now(UTC)

    # Precedence per D-13:  failed > stale > ok
    # NB: in_progress maps to 'ok' (active sync == healthy state). NEVER invent a
    # 'stale' fallback for in_progress — Plan 03's watchdog owns the failure flip.
    if last_sync_status == "failed" or token_revoked:
        api_check = "failed"
    elif last_sync_status == "in_progress":
        api_check = "ok"
    elif last_sync_at is None or (now - last_sync_at) > _STALE_THRESHOLD:
        api_check = "stale"
    else:  # last_sync_status == 'ok' (or None with a fresh last_sync_at)
        api_check = "ok"

    db_status = "ok" if db_ok else "error"
    mqtt_status = "ok" if mqtt_ok else "degraded"
    # Overall status: degraded when db is down OR api_check is not 'ok'. MQTT
    # degraded does NOT degrade overall (DEP-01 — MQTT is non-critical).
    overall = "ok" if (db_ok and api_check == "ok") else "degraded"

    sync_age_seconds: float | None = getattr(request.app.state, "sync_age_seconds", None)

    body: dict[str, Any] = {
        "status": overall,
        "db": db_status,
        "discogsography_api_check": api_check,
        "mqtt": mqtt_status,
        "version": GIT_SHA,
        "started_at": started_at.isoformat(),
        "sync_age_seconds": sync_age_seconds,
    }
    # Always HTTP 200 — callers inspect individual fields for degraded subsystems.
    return JSONResponse(content=body, status_code=200)

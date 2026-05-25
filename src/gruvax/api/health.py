"""GET /api/health — subsystem status for GRUVAX.

Reports:
  - ``db``:                     "ok" | "error:<msg>"
  - ``discogsography_view_check``: "ok" | "failed"
  - ``mqtt``:                   "ok" | "degraded"
  - ``status``:                 "ok" | "degraded"
  - ``version``:                git SHA baked at Docker build time (OBS-04/OBS-01)
  - ``started_at``:             ISO-8601 UTC timestamp of app startup
  - ``sync_age_seconds``:       seconds since last discogsography sync (OBS-06), float or null
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

try:
    from gruvax._version import GIT_SHA
except ImportError:
    GIT_SHA = "dev"

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def get_health(request: Request) -> JSONResponse:
    """Return subsystem health status.

    Does NOT perform a live DB probe on every call (that would add latency
    and hammer Postgres). Instead it reflects the state captured during
    lifespan startup, which is updated by the boundary cache reload (Phase 4).

    Returns HTTP 200 with ``status: "degraded"`` when any subsystem is unhealthy.
    Callers should inspect individual fields, not just the status string.
    """
    db_ok: bool = getattr(request.app.state, "db_ok", False)
    view_ok: bool = getattr(request.app.state, "discogsography_view_ok", False)
    mqtt_ok: bool = getattr(request.app.state, "mqtt_ok", False)
    started_at: datetime = getattr(request.app.state, "started_at", datetime.now(UTC))

    db_status = "ok" if db_ok else "error"
    view_status = "ok" if view_ok else "failed"
    mqtt_status = "ok" if mqtt_ok else "degraded"
    overall = "ok" if (db_ok and view_ok) else "degraded"

    sync_age_seconds: float | None = getattr(request.app.state, "sync_age_seconds", None)

    body: dict[str, Any] = {
        "status": overall,
        "db": db_status,
        "discogsography_view_check": view_status,
        "mqtt": mqtt_status,
        "version": GIT_SHA,
        "started_at": started_at.isoformat(),
        "sync_age_seconds": sync_age_seconds,
    }
    # Always HTTP 200 — callers inspect individual fields for degraded subsystems.
    return JSONResponse(content=body, status_code=200)

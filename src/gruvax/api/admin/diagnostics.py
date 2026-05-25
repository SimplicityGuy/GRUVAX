"""Admin diagnostics endpoints for GRUVAX.

Endpoints:
  GET  /api/admin/diagnostics            — return the 7 SC#2 rows:
                                            sync_age_seconds, top_searched,
                                            slow_queries, mqtt, pool,
                                            phantom_boundary_count, recent_logs.
  POST /api/admin/diagnostics/reset-stats — truncate gruvax.record_stats (D-06).

Both endpoints:
  - Require admin session + CSRF via Depends(require_admin) (T-08-13).
  - Never expose: connection strings, env vars, PIN, or raw query text.
  - Live at /admin prefix + /api prefix from app.py.

Phase 8: Observability + Deployment Hardening (OBS-05, OBS-06, OBS-07)
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from fastapi import APIRouter, Depends, Request
from psycopg_pool import AsyncConnectionPool

from gruvax.api.deps import get_pool, require_admin
from gruvax.db.queries import (
    get_phantom_boundary_count,
    get_sync_staleness_seconds,
    get_top_searched,
    reset_record_stats,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-diagnostics"])


@router.get("/diagnostics")
async def get_diagnostics(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Return the 7 SC#2 diagnostic rows for the admin diagnostics page.

    Reads from app.state ring buffers (non-blocking) and runs async DB queries
    for staleness, top-searched, and phantom boundary count.

    Security (T-08-14, T-08-15):
    - Admin-gated: unauthenticated requests are rejected by require_admin (401).
    - Body excludes: session_secret, database_url, pin, raw query text.
    - top_searched rows carry release_id + display fields only (title/primary_artist).
    - recent_logs carry pre-formatted messages from the ring buffer (counts/timing).

    Returns:
        Dict with keys: sync_age_seconds, top_searched, slow_queries, mqtt,
        pool, phantom_boundary_count, recent_logs.
    """
    # ── Ring buffer reads (from app.state, set by Plan 01/03 lifespan) ──────
    slow_ring: deque[dict[str, Any]] = getattr(
        request.app.state, "slow_query_ring", deque()
    )
    log_ring: deque[dict[str, Any]] = getattr(
        request.app.state, "log_ring_buffer", deque()
    )

    # ── sync_age_seconds ────────────────────────────────────────────────────
    # Prefer the cached value on app.state (set by background task, Plan 01).
    # Fall back to a live DB query when the cache is not populated.
    sync_age: float | None = getattr(request.app.state, "sync_age_seconds", None)
    if sync_age is None:
        sync_age = await get_sync_staleness_seconds(pool)

    # ── Pool stats ──────────────────────────────────────────────────────────
    # get_stats() is synchronous and non-blocking (psycopg_pool implementation).
    db_pool: AsyncConnectionPool = request.app.state.db_pool
    pool_stats: dict[str, Any] = db_pool.get_stats()
    pool_size: int = pool_stats.get("pool_size", 0)
    pool_available: int = pool_stats.get("pool_available", 0)
    pool_min: int = pool_stats.get("pool_min", 0)
    size_used = max(0, pool_size - pool_available)

    # ── MQTT status ─────────────────────────────────────────────────────────
    mqtt_ok: bool = getattr(request.app.state, "mqtt_ok", False)

    # ── DB queries ──────────────────────────────────────────────────────────
    top_searched = await get_top_searched(pool, 10)
    phantom_count = await get_phantom_boundary_count(pool)

    # ── Recent logs — last 20, newest-first (D-12) ─────────────────────────
    recent_logs_raw = list(log_ring)
    recent_logs = list(reversed(recent_logs_raw[-20:]))

    # ── Slow queries — newest-first ─────────────────────────────────────────
    slow_queries_raw = list(slow_ring)
    slow_queries = list(reversed(slow_queries_raw))

    return {
        "sync_age_seconds": sync_age,
        "top_searched": top_searched,
        "slow_queries": slow_queries,
        "mqtt": "connected" if mqtt_ok else "disconnected",
        "pool": {"size_used": size_used, "size_min": pool_min},
        "phantom_boundary_count": phantom_count,
        "recent_logs": recent_logs,
    }


@router.post("/diagnostics/reset-stats")
async def reset_stats(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Truncate gruvax.record_stats — backs the PIN-gated Reset stats action (D-06).

    CSRF is enforced by require_admin on this POST (V4 access control, T-08-13).
    The admin session already covers authentication; no extra PIN re-prompt.

    Security (T-08-13):
    - Requires admin session + CSRF double-submit (enforced by require_admin).
    - Unauthenticated requests are rejected (401/403).

    Returns:
        {"reset": True} on success.
    """
    await reset_record_stats(pool)
    logger.info("record_stats truncated by admin")
    return {"reset": True}

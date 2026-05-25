"""Slow-query timing helper for GRUVAX (OBS-05, D-07/08/09).

Per RESEARCH.md Open Question 5 (A5) and Pitfall 3, the chosen approach is
**inline instrumentation** rather than ``BaseHTTPMiddleware``.

``BaseHTTPMiddleware`` adds ~0.5-1 ms overhead per request due to response
streaming buffering — unacceptable for the 50 ms ``/api/locate`` SLO.  The
inline helper approach records slow requests with zero middleware overhead;
route handlers call ``record_slow_query`` directly after measuring timing.

Provides:
  - ``SLO_THRESHOLDS_MS`` — per-endpoint SLO thresholds in milliseconds (D-09).
  - ``record_slow_query`` — helper that appends a slow-request entry to
    ``app.state.slow_query_ring`` when ``total_ms`` exceeds the threshold.

Usage in route handlers (search.py, locate.py — Plan 03)::

    from gruvax.middleware.timing import record_slow_query

    # After the route computes total_ms and db_ms:
    record_slow_query(request.app, "/api/search", total_ms=took_total, db_ms=took_db)
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

# Per-endpoint SLO thresholds in milliseconds (D-09).
# /api/search: page total (framework + DB) must be < 200 ms
# /api/locate: CPU-only estimate must be < 50 ms (POS-03)
SLO_THRESHOLDS_MS: dict[str, float] = {
    "/api/search": 200.0,
    "/api/locate": 50.0,
}


def record_slow_query(
    app: Any,
    path: str,
    total_ms: float,
    db_ms: float,
) -> None:
    """Append a slow-request entry to ``app.state.slow_query_ring`` if over threshold.

    Does nothing when:
      - ``path`` is not in ``SLO_THRESHOLDS_MS`` (unknown endpoint).
      - ``total_ms`` is at or below the threshold (fast request).
      - ``app.state.slow_query_ring`` is absent (startup incomplete or tests).

    Args:
        app: The FastAPI application instance (provides ``app.state``).
        path: The request path, e.g. ``"/api/search"`` or ``"/api/locate"``.
        total_ms: End-to-end request time in milliseconds.
        db_ms: Database time component in milliseconds (0.0 for CPU-only endpoints).
    """
    threshold = SLO_THRESHOLDS_MS.get(path)
    if threshold is None or total_ms <= threshold:
        return

    ring: deque[dict[str, Any]] = getattr(app.state, "slow_query_ring", deque())
    ring.append(
        {
            "path": path,
            "total_ms": round(total_ms, 1),
            "db_ms": round(db_ms, 1),
            "threshold_ms": threshold,
            "ts": time.time(),
        }
    )

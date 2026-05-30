"""GET /api/search — FTS + catalog-number union search (SRCH-01, SRCH-02, SRCH-04).

Query parameters:
  - ``q``:          Search query. ``min_length=1``, ``max_length=200`` (T-01-10).
  - ``limit``:      Max results. Default 20, ``ge=1``, ``le=50`` (T-01-08).
  - ``profile_id``: Profile UUID; optional — defaults to the bound profile from the
                    gruvax_browse_binding cookie (D2-04, B-02).  When supplied,
                    validated against the cookie (403 profile_mismatch on mismatch).

Response:
  ``{items: [{release_id, collection_item_id, title, primary_artist,
              label, catalog_number, format, year, rank}],
     took_ms,
     did_you_mean: string | null}``

SRCH-04: ``q=zzznomatch`` → HTTP 200 with ``{items: []}``.
SRCH-07: ``did_you_mean`` is a trigram-similarity suggestion returned only
         when FTS finds nothing strong; ``null`` otherwise or when pg_trgm
         is unavailable (Pitfall E graceful degradation).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from starlette import status

from gruvax.api.deps import get_pool, get_snapshot_for_profile, resolve_profile_from_request
from gruvax.db.queries import increment_search_count, search_collection
from gruvax.middleware.timing import record_slow_query


logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    profile_id: str | None = Query(default=None),
    pool: Any = Depends(get_pool),
) -> dict[str, Any]:
    """Search the collection via FTS and catalog-number prefix matching.

    The profile_id query parameter is optional; defaults to the bound profile from the
    gruvax_browse_binding cookie (D2-04, B-02).  When omitted, the authoritative profile
    is resolved via resolve_profile_from_request (cookie/device authoritative): 400 if
    unbound, 403 if device_unknown/device_revoked.  When supplied, the resolved profile
    must match the supplied value (403 profile_mismatch on mismatch).

    Args:
        q:          Search query (1-200 characters, T-01-10).
        limit:      Maximum results (1-50, default 20, T-01-08).
        profile_id: Profile UUID (optional; defaults to cookie-bound profile, D2-04/B-02).

    Returns:
        ``{items: [SearchRow, ...], took_ms: float, did_you_mean: str | None}``
        Items are ordered by relevance (highest rank first).
        Returns ``{items: []}`` on no match (SRCH-04).
        ``did_you_mean`` is non-null only when items is empty and pg_trgm
        finds a high-similarity candidate (SRCH-07/D-11).
    """
    # B-02: resolve the authoritative profile from the request (cookie/device wins).
    # resolve_profile_from_request raises 400 session_unbound or 403 device_unknown/
    # device_revoked automatically — these propagate as HTTP errors.
    resolved_profile_id, _ = await resolve_profile_from_request(request, pool)

    if profile_id is None:
        # Omitted-param path (B-02): use the cookie-authoritative resolved profile.
        effective_profile_id = resolved_profile_id
    else:
        # Supplied-param path: preserve D2-04 mismatch check exactly.
        if resolved_profile_id != profile_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"type": "profile_mismatch"},
            )
        effective_profile_id = profile_id

    # Validate the effective profile against the snapshot registry (503/404 taxonomy).
    # Calling the dep directly with the resolved UUID — its internal mismatch check
    # passes because effective_profile_id == resolved_profile_id.
    await get_snapshot_for_profile(effective_profile_id, request, pool)

    rows, took_ms, did_you_mean = await search_collection(pool, q, limit, effective_profile_id)

    # OBS-05: record in slow-query ring when request exceeds the /api/search SLO (200 ms).
    # For search, took_ms is both request-total and DB time (Pitfall 3 — inline approach).
    record_slow_query(request.app, "/api/search", took_ms, took_ms)

    # OBS-07/D-04: fire-and-forget counter increment for the top result only.
    # PRIVACY: only the int release_id is passed — never q, did_you_mean, or label text.
    # CR-01: strong-reference via app.state.background_tasks so GC cannot cancel mid-flight.
    if rows:
        top_id: int = rows[0]["release_id"]
        task = asyncio.create_task(increment_search_count(pool, top_id))
        # CR-01 fix: never fall back to a throwaway set() — that would drop the only
        # strong reference and let the GC cancel the task. Persist the set on app.state
        # if the lifespan did not seed it (e.g. tests without a full lifespan).
        bg: set[asyncio.Task[None]] | None = getattr(request.app.state, "background_tasks", None)
        if bg is None:
            bg = set()
            request.app.state.background_tasks = bg
        bg.add(task)
        task.add_done_callback(bg.discard)

        # Pitfall 2: log exceptions from fire-and-forget tasks; never crash the response.
        def _log_exc(t: asyncio.Task[None]) -> None:
            if not t.cancelled() and t.exception() is not None:
                logger.warning(
                    "increment_search_count failed for release_id=%s: %s",
                    top_id,
                    t.exception(),
                )

        task.add_done_callback(_log_exc)

    return {
        "items": rows,
        "took_ms": round(took_ms, 2),
        "did_you_mean": did_you_mean,
    }

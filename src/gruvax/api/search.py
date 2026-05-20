"""GET /api/search — FTS + catalog-number union search (SRCH-01, SRCH-02, SRCH-04).

Query parameters:
  - ``q``:     Search query. ``min_length=1``, ``max_length=200`` (T-01-10).
  - ``limit``: Max results. Default 20, ``ge=1``, ``le=50`` (T-01-08).

Response:
  ``{items: [{release_id, collection_item_id, title, primary_artist,
              label, catalog_number, format, year, rank}], took_ms}``

SRCH-04: ``q=zzznomatch`` → HTTP 200 with ``{items: []}``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from gruvax.api.deps import get_pool
from gruvax.db.queries import search_collection

logger = logging.getLogger(__name__)

router = APIRouter(tags=["search"])


@router.get("/search")
async def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    pool: Any = Depends(get_pool),
) -> dict[str, Any]:
    """Search the collection via FTS and catalog-number prefix matching.

    Returns a ranked list of collection items matching the query string.
    FTS matches on artist name, title, and label; catalog-path matches on
    separator-normalized catalog number prefix (e.g. ``blp4195`` hits ``BLP 4195``).

    Args:
        q:     Search query (1-200 characters, T-01-10).
        limit: Maximum results (1-50, default 20, T-01-08).

    Returns:
        ``{items: [SearchRow, ...], took_ms: float}``
        Items are ordered by relevance (highest rank first).
        Returns ``{items: []}`` on no match (SRCH-04).
    """
    rows, took_ms = await search_collection(pool, q, limit)

    return {
        "items": rows,
        "took_ms": round(took_ms, 2),
    }

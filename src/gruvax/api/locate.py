"""GET /api/locate — position estimate for a collection release (POS-02).

Query parameter:
  - ``release_id``: Integer Discogs release ID (T-01-09: typed param, 422 on non-int).

Response (HTTP 200): Locked LocateResult JSON contract (D-10/D-11/D-12):
  ``{release_id, primary_cube, label_span, sub_cube_interval, confidence,
     generated_at, estimator_version}``

The ``sub_cube_interval`` field (Phase 2) shape (UI-SPEC §TypeScript Type Extension):
  ``{start, end, crosses_boundary, next_cube}``
  NOTE: the ``cube`` field of the SubInterval dataclass is NOT emitted — the frontend
  derives the cube from context (primary_cube / label_span).

Error semantics:
  - HTTP 404: release_id not in gruvax.v_collection
    → ``{type: "release_not_in_collection", release_id: <id>}``
  - HTTP 200 with confidence 0.0 / primary_cube null / label_span []:
    release IS in collection but no cube boundary covers its label (D-12).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from gruvax.api.deps import get_boundary_cache, get_collection_snapshot, get_pool
from gruvax.db.queries import get_release_for_locate
from gruvax.estimator.algorithm import locate
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.contract import CubeRef, SubInterval

logger = logging.getLogger(__name__)

router = APIRouter(tags=["locate"])


def _cube_ref_to_dict(cube: CubeRef) -> dict[str, int]:
    """Serialize a CubeRef dataclass to a JSON-safe dict."""
    return {"unit_id": cube.unit_id, "row": cube.row, "col": cube.col}


def _sub_interval_to_dict(si: SubInterval) -> dict[str, Any]:
    """Serialize a SubInterval dataclass to a JSON-safe dict.

    Emits ``{start, end, crosses_boundary, next_cube}`` — the ``cube`` field is
    intentionally omitted (UI-SPEC §TypeScript Type Extension; the frontend derives
    the cube from primary_cube / label_span context).
    """
    return {
        "start": si.start,
        "end": si.end,
        "crosses_boundary": si.crosses_boundary,
        "next_cube": _cube_ref_to_dict(si.next_cube) if si.next_cube else None,
    }


@router.get("/locate")
async def locate_endpoint(
    request: Request,
    release_id: int,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
) -> JSONResponse:
    """Return the locked LocateResult for a release.

    Looks up the release in ``gruvax.v_collection``, runs the position estimator
    dispatcher (§4.1 index-based primary, §4.8 cube-only fallback), and returns
    the JSON result.

    Args:
        release_id: Discogs release ID (integer; 422 on non-integer T-01-09).

    Returns:
        HTTP 200 with the LocateResult JSON on success (including no-boundary case).
        HTTP 404 with ``{type: "release_not_in_collection"}`` if not in collection.

    The JSON shape (Phase 2 extension of the Phase 1 contract):
      ``{release_id, primary_cube, label_span, sub_cube_interval,
         confidence, generated_at, estimator_version}``
    where ``sub_cube_interval`` is ``{start, end, crosses_boundary, next_cube}``
    when the estimator produces a sub-cube estimate, or ``null`` for the cube-only fallback.
    """
    record = await get_release_for_locate(pool, release_id)

    if record is None:
        raise HTTPException(
            status_code=404,
            detail={
                "type": "release_not_in_collection",
                "release_id": release_id,
            },
        )

    label: str = record.get("label") or ""
    catalog_number: str = record.get("catalog_number") or ""

    result = locate(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        cache=cache,
        snapshot=snapshot,
    )

    # Serialize LocateResult to JSON-compatible dict.
    # Dataclasses are not JSON-serializable by default; JSONResponse handles dicts.
    body: dict[str, Any] = {
        "release_id": result.release_id,
        "primary_cube": _cube_ref_to_dict(result.primary_cube) if result.primary_cube else None,
        "label_span": [_cube_ref_to_dict(c) for c in result.label_span],
        "sub_cube_interval": (
            _sub_interval_to_dict(result.sub_cube_interval)
            if result.sub_cube_interval is not None
            else None
        ),
        "confidence": result.confidence,
        "generated_at": result.generated_at.isoformat(),
        "estimator_version": result.estimator_version,
    }

    return JSONResponse(content=body, status_code=200)

"""GET /api/units, GET /api/cubes (bulk), and GET /api/cubes/{unit_id}/{row}/{col}.

Endpoints:
  - ``GET /api/units``:
      Returns all configured shelving units (``id``, ``display_name``,
      ``rows``, ``cols``, ``ordering``). The NxNx4 grid is driven by this
      data. N is the number of units.

  - ``GET /api/cubes``:
      Returns all cube boundary rows as ``{cubes: [{unit_id,row,col,is_empty}, …]}``.
      Used by the kiosk SPA to render the CUBE-05 empty state for cubes flagged
      ``is_empty=true``. Row/col are 0-based.

  - ``GET /api/cubes/{unit_id}/{row}/{col}``:
      Returns one cube's boundary metadata (first_label, first_catalog,
      is_empty) PLUS fill_level, total_count, and sample_records computed
      from the in-memory SegmentCache and snapshot (no DB during compute, D-13/D-14).
      Typed int path params; FastAPI returns 422 on non-int.
      Public endpoint — no admin auth required (D-15).

Phase 5 changes:
  - last_label/last_catalog removed from DB SELECT and BoundaryRow construction (SEG-01).
  - fill_level/count computed via SegmentCache.get_bin + count_records_in_bin (no last_*).
  - sample_records computed via get_records_in_bin(bin_, snapshot) + sample_records().
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from gruvax.api.deps import (
    get_boundary_cache,
    get_collection_snapshot,
    get_pool,
    get_segment_cache,
)
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.boundary_math import count_records_in_bin, get_records_in_bin, sample_records
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["units"])


@router.get("/units")
async def get_units(
    request: Request,
    pool: Any = Depends(get_pool),
) -> dict[str, Any]:
    """Return all configured shelving units.

    Response: ``{units: [{id, display_name, rows, cols, ordering}, ...]}``

    The grid renders N units in ``ordering`` sequence; each unit is a
    ``rows x cols`` grid of cubes. Phase 1: N=2, 4x4 each = 32 cubes.
    """
    sql = """
SELECT id, display_name, rows, cols, ordering
FROM gruvax.units
ORDER BY ordering
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    units = [dict(zip(cols_meta, row, strict=True)) for row in rows_raw]
    return {"units": units}


@router.get("/cubes")
async def get_cubes_bulk(
    request: Request,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    segment_cache: SegmentCache = Depends(get_segment_cache),
) -> dict[str, Any]:
    """Return all cube boundary rows with their empty-state flag and fill level.

    Response: ``{cubes: [{unit_id, row, col, is_empty, fill_level}, ...]}``

    Row and col are 0-based, matching the API convention used by
    ``/api/locate`` and ``/api/cubes/{unit_id}/{row}/{col}``.
    The kiosk SPA uses this endpoint to render:
      - CUBE-05 empty state for cubes flagged ``is_empty=true``
      - CUBE-07 fill bars (fill_level 0.0-1.0+) from the in-memory segment cache

    ``fill_level`` is computed from the in-memory SegmentCache (no extra DB calls
    during compute, D-13 / T-03-12). Phase 5: uses count_records_in_bin(SegmentBin).
    """
    # Phase 5: fetch only cut-point columns (last_* dropped in SEG-01 migration 0005)
    sql = """
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
ORDER BY unit_id, row, col
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    nominal_capacity: int = int(
        getattr(request.app.state, "settings_cache", {}).get("cube.nominal_capacity", 95)
    )

    cubes = []
    for raw in rows_raw:
        row_dict = dict(zip(cols_meta, raw, strict=True))
        unit_id = row_dict["unit_id"]
        row = row_dict["row"]
        col = row_dict["col"]

        # Phase 5: compute fill_level via SegmentCache (no last_* needed)
        seg_bin = segment_cache.get_bin(unit_id, row, col)
        count = count_records_in_bin(seg_bin) if seg_bin else 0
        fill_level = count / max(nominal_capacity, 1)

        cubes.append(
            {
                "unit_id": unit_id,
                "row": row,
                "col": col,
                "is_empty": row_dict["is_empty"],
                "fill_level": fill_level,
            }
        )

    return {"cubes": cubes}


@router.get("/cubes/{unit_id}/{row}/{col}")
async def get_cube(
    request: Request,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    segment_cache: SegmentCache = Depends(get_segment_cache),
) -> dict[str, Any]:
    """Return one cube's boundary metadata plus fill level, count, and sample records.

    Public endpoint — no admin auth required (D-15). Visiting friends can browse
    cube contents on the kiosk without logging in.

    Args:
        unit_id: Unit ID (integer ≥ 1). FastAPI returns 422 on non-int.
        row:     Row index (0-indexed). FastAPI returns 422 on non-int.
        col:     Column index (0-indexed). FastAPI returns 422 on non-int.

    Returns:
        ``{unit_id, row, col, first_label, first_catalog, is_empty,
           total_count, fill_level, sample_records}``

        Note: last_label and last_catalog are dropped (Phase 5 / SEG-01 migration 0005).
        ``fill_level`` is total_count / nominal_capacity (may exceed 1.0 for
        overstuffed cubes). Computed from in-memory SegmentCache — no DB during compute
        (D-13, T-03-12).

        ``sample_records`` is a list of up to 7 evenly-spaced records from the range
        (D-14), each with {release_id, label, catalog_number}.

    HTTP 404 if no cube boundary row exists for the given coordinates (T-03-11).
    """
    # Phase 5: fetch only cut-point columns (last_* dropped in SEG-01 migration 0005)
    sql = """
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE unit_id = %s AND row = %s AND col = %s
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (unit_id, row, col))
        row_raw = await cur.fetchone()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    if row_raw is None:
        raise HTTPException(
            status_code=404,
            detail={"type": "cube_not_found", "unit_id": unit_id, "row": row, "col": col},
        )

    result = dict(zip(cols_meta, row_raw, strict=True))

    # Phase 5: Build BoundaryRow without last_* (dropped in SEG-01 migration 0005).
    # Used only for type compatibility; fill/count/sample computed via SegmentCache below.
    boundary = BoundaryRow(
        unit_id=result["unit_id"],
        row=result["row"],
        col=result["col"],
        first_label=result["first_label"],
        first_catalog=result["first_catalog"],
        is_empty=result["is_empty"],
    )

    # Nominal capacity from settings cache (admin-configurable, D-13).
    # Default 95 records per Kallax cube (typical LP density).
    nominal_capacity: int = int(
        getattr(request.app.state, "settings_cache", {}).get("cube.nominal_capacity", 95)
    )

    # Phase 5: Compute fill level and sample from SegmentCache + snapshot (no DB during compute,
    # O(records-per-label) — negligible at ~50 worst case, T-03-12 / RESEARCH.md A5).
    seg_bin = segment_cache.get_bin(boundary.unit_id, boundary.row, boundary.col)
    if seg_bin is not None:
        total_count = count_records_in_bin(seg_bin)
        records_in_range = get_records_in_bin(seg_bin, snapshot)
    else:
        total_count = 0
        records_in_range = []

    fill_level = total_count / max(nominal_capacity, 1)
    sampled = sample_records(records_in_range, n=7)

    result["total_count"] = total_count
    result["fill_level"] = fill_level
    result["sample_records"] = [
        {
            "release_id": r.release_id,
            "label": r.label,
            "catalog_number": r.catalog_number,
        }
        for r in sampled
    ]

    return result

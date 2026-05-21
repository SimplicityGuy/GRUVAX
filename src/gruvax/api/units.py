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
      Returns one cube's boundary metadata (first/last label+catalog,
      is_empty) PLUS fill_level, total_count, and sample_records computed
      from the in-memory snapshot (no DB during compute, D-13/D-14).
      Typed int path params; FastAPI returns 422 on non-int.
      Public endpoint — no admin auth required (D-15).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from gruvax.api.deps import get_boundary_cache, get_collection_snapshot, get_pool
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.boundary_math import get_records_in_boundary, sample_records
from gruvax.estimator.collection_snapshot import CollectionSnapshot

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
) -> dict[str, Any]:
    """Return all cube boundary rows with their empty-state flag and fill level.

    Response: ``{cubes: [{unit_id, row, col, is_empty, fill_level}, ...]}``

    Row and col are 0-based, matching the API convention used by
    ``/api/locate`` and ``/api/cubes/{unit_id}/{row}/{col}``.
    The kiosk SPA uses this endpoint to render:
      - CUBE-05 empty state for cubes flagged ``is_empty=true``
      - CUBE-07 fill bars (fill_level 0.0-1.0+) from the in-memory snapshot

    ``fill_level`` is computed from the in-memory snapshot (no extra DB calls
    during compute, D-13 / T-03-12). The full boundary fields (first_label etc.)
    are also fetched so they can be used to build BoundaryRow objects for compute.
    """
    sql = """
SELECT unit_id, row, col, first_label, first_catalog, last_label, last_catalog, is_empty
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
        boundary = BoundaryRow(
            unit_id=row_dict["unit_id"],
            row=row_dict["row"],
            col=row_dict["col"],
            first_label=row_dict["first_label"],
            first_catalog=row_dict["first_catalog"],
            last_label=row_dict["last_label"],
            last_catalog=row_dict["last_catalog"],
            is_empty=row_dict["is_empty"],
        )
        records_in_range = get_records_in_boundary(boundary, snapshot)
        fill_level = len(records_in_range) / max(nominal_capacity, 1)
        cubes.append({
            "unit_id": row_dict["unit_id"],
            "row": row_dict["row"],
            "col": row_dict["col"],
            "is_empty": row_dict["is_empty"],
            "fill_level": fill_level,
        })

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
) -> dict[str, Any]:
    """Return one cube's boundary metadata plus fill level, count, and sample records.

    Public endpoint — no admin auth required (D-15). Visiting friends can browse
    cube contents on the kiosk without logging in.

    Args:
        unit_id: Unit ID (integer ≥ 1). FastAPI returns 422 on non-int.
        row:     Row index (0-indexed). FastAPI returns 422 on non-int.
        col:     Column index (0-indexed). FastAPI returns 422 on non-int.

    Returns:
        ``{unit_id, row, col, first_label, first_catalog, last_label, last_catalog,
           is_empty, total_count, fill_level, sample_records}``

        ``fill_level`` is total_count / nominal_capacity (may exceed 1.0 for
        overstuffed cubes). Computed from in-memory snapshot — no DB during compute
        (D-13, T-03-12).

        ``sample_records`` is a list of up to 7 evenly-spaced records from the range
        (D-14), each with {release_id, label, catalog_number}.

    HTTP 404 if no cube boundary row exists for the given coordinates (T-03-11).
    """
    sql = """
SELECT unit_id, row, col, first_label, first_catalog, last_label, last_catalog, is_empty
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

    # Build a BoundaryRow from the DB result to feed the in-memory compute helpers.
    # This avoids a second DB query — the boundary cache may lag slightly after an
    # admin commit, but the DB result is always authoritative (T-03-12).
    boundary = BoundaryRow(
        unit_id=result["unit_id"],
        row=result["row"],
        col=result["col"],
        first_label=result["first_label"],
        first_catalog=result["first_catalog"],
        last_label=result["last_label"],
        last_catalog=result["last_catalog"],
        is_empty=result["is_empty"],
    )

    # Nominal capacity from settings cache (admin-configurable, D-13).
    # Default 95 records per Kallax cube (typical LP density).
    nominal_capacity: int = int(
        getattr(request.app.state, "settings_cache", {}).get("cube.nominal_capacity", 95)
    )

    # Compute fill level and sample from the in-memory snapshot (no DB during compute,
    # O(records-per-label) — negligible at ~50 worst case, T-03-12 / RESEARCH.md A5).
    records_in_range = get_records_in_boundary(boundary, snapshot)
    total_count = len(records_in_range)
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

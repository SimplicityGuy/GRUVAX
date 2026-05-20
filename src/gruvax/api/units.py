"""GET /api/units and GET /api/cubes/{unit_id}/{row}/{col} (CUBE-01).

Endpoints:
  - ``GET /api/units``:
      Returns all configured shelving units (``id``, ``display_name``,
      ``rows``, ``cols``, ``ordering``). The NxNx4 grid is driven by this
      data. N is the number of units.

  - ``GET /api/cubes/{unit_id}/{row}/{col}``:
      Returns one cube's boundary metadata (first/last label+catalog,
      is_empty). Typed int path params; FastAPI returns 422 on non-int.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from gruvax.api.deps import get_pool

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


@router.get("/cubes/{unit_id}/{row}/{col}")
async def get_cube(
    request: Request,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
) -> dict[str, Any]:
    """Return one cube's boundary metadata.

    Args:
        unit_id: Unit ID (integer ≥ 1).
        row:     Row index (0-indexed).
        col:     Column index (0-indexed).

    Returns:
        ``{unit_id, row, col, first_label, first_catalog, last_label, last_catalog,
           is_empty}``

    HTTP 404 if no cube exists for the given coordinates.
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

    return dict(zip(cols_meta, row_raw, strict=True))

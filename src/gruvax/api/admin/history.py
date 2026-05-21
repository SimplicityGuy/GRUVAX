"""Admin boundary history endpoints — list change-sets and conflict-aware revert.

Endpoints:
  - ``GET /admin/history``:
      Returns all change-sets from boundary_history grouped by change_set_id,
      newest-first.  Each row includes source, changed_at, cube_count.
      Requires admin session (require_admin).

  - ``POST /admin/history/{change_set_id}/revert``:
      Conflict-aware revert of a change-set (D-11, D-12).
      For each cube in the target change-set:
        - If a newer boundary_history row exists for that (unit, row, col)
          → SKIP and add to skipped report (no silent clobber — T-03-21).
        - Else → restore prev_* values to cube_boundaries and write a new
          boundary_history row with source='revert' under a new change_set_id.
      The inverse change-set is atomic for the non-conflicting cubes.
      A revert is itself recorded in history — it is undoable (D-11).
      After commit, invalidates + reloads the boundary cache (Pitfall A).
      Requires admin session + CSRF.

Security:
  - Both handlers depend on require_admin (T-03-18).
  - All SQL uses %s placeholders, zero f-string interpolation (T-03-24).
  - Conflict detection via has_newer_changes prevents silent clobber (T-03-21).
  - Cache invalidated only after successful commit — a failed revert does NOT
    empty the live cache (T-03-22).
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse

from gruvax.api.deps import get_boundary_cache, get_pool, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-history"])


@router.get("/history")
async def get_history(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Return all change-sets from boundary_history, newest-first.

    Groups rows by change_set_id and returns one entry per change-set with
    source, MAX(changed_at), and cube_count.

    Response: ``{history: [{change_set_id, source, changed_at, cube_count}, ...]}``
    """
    from gruvax.db.queries import list_change_sets

    change_sets = await list_change_sets(pool)
    return {"history": change_sets}


@router.post("/history/{change_set_id}/revert")
async def revert_change_set(
    request: Request,
    change_set_id: str = Path(description="UUID of the change-set to revert"),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Conflict-aware revert of a change-set (D-11, D-12, ADMN-09).

    For each cube in the target change-set, checks whether a newer
    boundary_history row exists for that (unit, row, col) via
    has_newer_changes().  If so, skips that cube and adds it to the skipped
    report.  Non-conflicting cubes are restored atomically.

    The inverse change-set is itself written to boundary_history with
    source='revert' so it can be undone by reverting it (D-11).

    AFTER the transaction commits, invalidates + reloads the boundary cache
    (Pitfall A — never inside the transaction).

    Response:
      ``{change_set_id: str, reverted: [...], skipped: [...]}``
      where ``reverted`` lists ``{unit_id, row, col}`` dicts for cubes that
      were successfully reverted, and ``skipped`` lists the same for cubes
      that had newer changes and were not touched.

    HTTP 404 if the change_set_id is not found in boundary_history.
    """
    from gruvax.db.queries import (
        fetch_change_set_rows,
        has_newer_changes,
        write_boundary,
        write_history_row,
    )

    # Fetch all history rows for this change-set
    rows = await fetch_change_set_rows(pool, change_set_id)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "change_set_not_found", "change_set_id": change_set_id},
        )

    new_change_set_id = str(_uuid.uuid4())
    reverted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    async with pool.connection() as conn, conn.transaction():
        for hist in rows:
            unit_id = int(hist["unit_id"])
            row_idx = int(hist["row"])
            col_idx = int(hist["col"])
            original_changed_at = hist["changed_at"]

            # Conflict check: is there a newer history row for this cube?
            conflict = await has_newer_changes(
                conn, unit_id, row_idx, col_idx, original_changed_at
            )
            if conflict:
                skipped.append({
                    "unit_id": unit_id,
                    "row": row_idx,
                    "col": col_idx,
                })
                continue

            # Restore prev_* values to cube_boundaries
            prev_first_label = hist.get("prev_first_label")
            prev_first_catalog = hist.get("prev_first_catalog")
            prev_last_label = hist.get("prev_last_label")
            prev_last_catalog = hist.get("prev_last_catalog")
            prev_is_empty = bool(hist.get("prev_is_empty", True))

            await write_boundary(
                conn,
                unit_id, row_idx, col_idx,
                prev_first_label, prev_first_catalog,
                prev_last_label, prev_last_catalog,
                prev_is_empty,
            )

            # Record the inverse change in history (source='revert')
            # The "prev" for this revert row is the *current* (new_*) values
            prev_for_revert: dict[str, Any] = {
                "first_label": hist.get("new_first_label"),
                "first_catalog": hist.get("new_first_catalog"),
                "last_label": hist.get("new_last_label"),
                "last_catalog": hist.get("new_last_catalog"),
                "is_empty": bool(hist.get("new_is_empty", True)),
            }
            await write_history_row(
                conn,
                new_change_set_id,
                unit_id, row_idx, col_idx,
                prev_for_revert,
                prev_first_label, prev_first_catalog,
                prev_last_label, prev_last_catalog,
                prev_is_empty,
                source="revert",
            )

            reverted.append({
                "unit_id": unit_id,
                "row": row_idx,
                "col": col_idx,
            })

    if not reverted and not skipped:
        # This can happen if the change-set was already fully reverted or had 0 cubes
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "change_set_not_found", "change_set_id": change_set_id},
        )

    # ── Invalidate + reload cache AFTER transaction commit (Pitfall A) ───────
    # Only reload if at least one cube was actually changed
    if reverted:
        cache.invalidate()
        await cache.load(pool)

    return JSONResponse(
        content={
            "change_set_id": new_change_set_id,
            "reverted": reverted,
            "skipped": skipped,
        }
    )

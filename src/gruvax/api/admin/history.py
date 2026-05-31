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
      After commit, invalidates + reloads BoundaryCache, re-derives SegmentCache
      from all current overrides in gruvax.segment_overrides, and publishes a
      boundary_changed SSE event with the reverted cube_ids (Pitfall A).
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
from typing import TYPE_CHECKING, Any
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse

from gruvax.api.deps import (
    get_boundary_cache,
    get_collection_snapshot,
    get_pool,
    get_segment_cache,
    get_write_target,
    require_admin,
)
from gruvax.db.queries import (
    fetch_change_set_rows,
    has_newer_changes,
    list_change_sets,
    write_boundary,
    write_history_row,
)


if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryCache
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-history"])


@router.get("/history")
async def get_history(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> dict[str, Any]:
    """Return all change-sets from boundary_history, newest-first.

    Groups rows by change_set_id and returns one entry per change-set with
    source, MAX(changed_at), and cube_count.

    WR-02 (Phase 6 CR fix): scoped to the resolved profile_id so history from
    other profiles is not mixed in.

    Response: ``{history: [{change_set_id, source, changed_at, cube_count}, ...]}``
    """
    profile_id, _ = _write_target
    change_sets = await list_change_sets(pool, profile_id=profile_id)
    return {"history": change_sets}


@router.post("/history/{change_set_id}/revert")
async def revert_change_set(
    request: Request,
    change_set_id: str = Path(description="UUID of the change-set to revert"),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> JSONResponse:
    """Conflict-aware revert of a change-set (D-11, D-12, ADMN-09).

    For each cube in the target change-set, checks whether a newer
    boundary_history row exists for that (unit, row, col) via
    has_newer_changes().  If so, skips that cube and adds it to the skipped
    report.  Non-conflicting cubes are restored atomically.

    The inverse change-set is itself written to boundary_history with
    source='revert' so it can be undone by reverting it (D-11).

    AFTER the transaction commits, invalidates + reloads BoundaryCache, re-reads
    all overrides from gruvax.segment_overrides, re-derives SegmentCache, and
    publishes a boundary_changed SSE event with the reverted cube_ids (Pitfall A —
    cache mutations never inside the transaction).

    Response:
      ``{change_set_id: str, reverted: [...], skipped: [...]}``
      where ``reverted`` lists ``{unit_id, row, col}`` dicts for cubes that
      were successfully reverted, and ``skipped`` lists the same for cubes
      that had newer changes and were not touched.

    HTTP 404 if the change_set_id is not found in boundary_history.
    """
    profile_id, bus = _write_target

    # Fetch all history rows for this change-set — scoped to resolved profile (WR-02).
    rows = await fetch_change_set_rows(pool, change_set_id, profile_id=profile_id)
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

            # Conflict check: scoped to resolved profile (WR-02 — prevents cross-profile
            # false conflicts where a newer edit on a different profile triggers a skip).
            conflict = await has_newer_changes(
                conn, unit_id, row_idx, col_idx, original_changed_at, profile_id=profile_id
            )
            if conflict:
                skipped.append(
                    {
                        "unit_id": unit_id,
                        "row": row_idx,
                        "col": col_idx,
                    }
                )
                continue

            # Restore prev_* values to cube_boundaries.
            # Phase 5 (SEG-01): cube_boundaries no longer has last_* columns.
            # Revert restores only first_label, first_catalog, and is_empty.
            # The prev_last_* columns in boundary_history are nullable audit
            # artifacts (A1) — they may be NULL for rows from 0005 onwards.
            prev_first_label = hist.get("prev_first_label")
            prev_first_catalog = hist.get("prev_first_catalog")
            # WR-07 (updated for cut-point model): coerce is_empty=True if
            # first_* columns are NULL — the old empty_or_complete/last_* check
            # no longer applies; only first_* completeness matters now.
            prev_is_empty_raw = bool(hist.get("prev_is_empty", True))
            has_cut_point = bool(prev_first_label and prev_first_catalog)
            prev_is_empty = prev_is_empty_raw or not has_cut_point

            rows_affected = await write_boundary(
                conn,
                unit_id,
                row_idx,
                col_idx,
                prev_first_label,
                prev_first_catalog,
                prev_is_empty,
                profile_id=profile_id,
            )
            # D-10: 0-row write means the cube doesn't exist for this profile.
            # Inside the transaction — aborts the whole revert atomically (D-11).
            if rows_affected == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "type": "boundary_not_found",
                        "unit_id": unit_id,
                        "row": row_idx,
                        "col": col_idx,
                    },
                )

            # Record the inverse change in history (source='revert').
            # The "prev" for this revert row is the *current* (new_*) values.
            # last_* fields are omitted from the prev dict (not in cube_boundaries).
            prev_for_revert: dict[str, Any] = {
                "first_label": hist.get("new_first_label"),
                "first_catalog": hist.get("new_first_catalog"),
                "is_empty": bool(hist.get("new_is_empty", True)),
            }
            await write_history_row(
                conn,
                new_change_set_id,
                unit_id,
                row_idx,
                col_idx,
                prev_for_revert,
                prev_first_label,
                prev_first_catalog,
                prev_is_empty,
                source="revert",
                profile_id=profile_id,
            )

            reverted.append(
                {
                    "unit_id": unit_id,
                    "row": row_idx,
                    "col": col_idx,
                }
            )

    # WR-11: Removed the dead `not reverted and not skipped` 404 branch.
    # `fetch_change_set_rows` returned non-empty rows (otherwise we 404'd above),
    # and the loop always appends each cube to reverted or skipped, so this branch
    # was unreachable. Returning {reverted:[], skipped:[...]} is the meaningful
    # signal for a fully-conflicted revert — not 404.

    # ── Invalidate + reload BoundaryCache + re-derive SegmentCache AFTER commit ─
    # (Pitfall A: cache mutations must run AFTER the transaction block exits.)
    # Only execute if at least one cube was actually changed.
    if reverted:
        cache.invalidate()
        try:
            await cache.load(pool)
            # Re-read ALL overrides from the DB before re-deriving SegmentCache.
            # A revert may touch multiple bins, and admin-set width overrides must
            # be preserved.  Re-reading from gruvax.segment_overrides is the same
            # approach used by segments.py::set_bin_overrides and insert_cut.
            # CR-02: scoped to the resolved profile_id to prevent cross-profile
            # override contamination.
            overrides: dict[tuple[int, int, int, str], float] = {}
            async with pool.connection() as conn2, conn2.cursor() as cur2:
                await cur2.execute(
                    "SELECT unit_id, row, col, label, fraction"
                    " FROM gruvax.segment_overrides"
                    " WHERE profile_id = %s::uuid",
                    (profile_id,),
                )
                override_rows = await cur2.fetchall()
            for uid_o, r_o, c_o, lbl_o, frac_o in override_rows:
                overrides[(int(uid_o), int(r_o), int(c_o), str(lbl_o))] = float(frac_o)
            segment_cache.invalidate()
            segment_cache.derive(cache, snapshot, overrides)
        finally:
            # Publish boundary_changed even if cache.load() raised — the kiosk must
            # be notified that a revert occurred.  cube_ids uses key "unit" (not
            # "unit_id") to match the ShimmerCube contract (Pitfall 1).
            await bus.publish(
                "boundary_changed",
                {
                    "cube_ids": [
                        {"unit": r["unit_id"], "row": r["row"], "col": r["col"]} for r in reverted
                    ],
                    "change_set_id": new_change_set_id,
                },
            )

    return JSONResponse(
        content={
            "change_set_id": new_change_set_id,
            "reverted": reverted,
            "skipped": skipped,
        }
    )

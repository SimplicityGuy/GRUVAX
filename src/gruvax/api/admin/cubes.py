"""Admin cube boundary endpoints — read, dry-run validate, suggest-midpoint, and bulk write.

Endpoints:
  - ``GET /admin/cubes``:
      Returns all cubes with their fill levels (count / nominal_capacity).
      Requires admin session (require_admin).

  - ``GET /admin/cubes/{unit_id}/{row}/{col}/boundary``:
      Returns one cube's current boundary values.
      Requires admin session. HTTP 404 for missing cube.

  - ``POST /admin/cubes/validate``:
      Dry-run diff — validates a proposed boundary without writing to the DB.
      Checks:
        1. Phantom check (cube_exact_match): unless force=true, rejects (label, catalog)
           pairs absent from v_collection and returns trigram near-misses.
        2. Contiguity check (validate_contiguity): rejects non-adjacent label scatter.
        3. Movement counts: computed from the in-memory SegmentCache + snapshot.
      Requires admin session + CSRF.

  - ``POST /admin/cubes/suggest``:
      Returns an index-space midpoint suggestion from suggest_midpoint.
      The suggestion is always a real owned record from v_collection — never
      a synthesized catalog string (Pitfall 22, D-08).
      Requires admin session + CSRF.

Security:
  - Every handler depends on require_admin (session cookie + CSRF, ASVS V4 — T-03-13).
  - All SQL uses %s placeholders, zero f-string interpolation (T-03-16).
  - validate endpoint performs NO INSERT/UPDATE/DELETE (T-03-14).

Phase 5 changes (05-04):
  - BoundaryEdit drops last_label / last_catalog (SEG-01 / migration 0005).
  - _compute_movement_counts uses SegmentCache + count_records_in_bin.
  - suggest_cube_midpoint derives the last-record anchor from SegmentCache rank info.
  - Both write paths (put_cube_boundary + bulk_write_cubes) invalidate + re-derive
    SegmentCache after BoundaryCache reload (Pitfall A: AFTER transaction commit).
  - validate endpoint adds validate_contiguity check after phantom check.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.api.admin.validation import validate_contiguity
from gruvax.api.deps import (
    get_boundary_cache,
    get_collection_snapshot,
    get_pool,
    get_segment_cache,
    get_write_target,
    require_admin,
)
from gruvax.db.queries import (
    check_idempotency,
    cleanup_idempotency,
    cube_exact_match,
    fetch_current_boundary,
    find_boundary_near_misses,
    store_idempotency,
    write_boundary,
    write_history_row,
)
from gruvax.estimator.boundary_math import count_records_in_bin, suggest_midpoint
from gruvax.estimator.normalize import parse_key


if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryCache
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-cubes"])

# ── Request / Response models ──────────────────────────────────────────────────


class BoundaryEdit(BaseModel):
    """One cube boundary proposal — the shape used for validate and suggest.

    Phase 5 (05-04): last_label / last_catalog removed (SEG-01, migration 0005).
    The cut-point model stores only first_label / first_catalog as the cut point.
    """

    unit_id: int
    row: int
    col: int
    first_label: str | None = None
    first_catalog: str | None = None
    is_empty: bool = False
    force: bool = False  # True: skip phantom check


class PerCubeBoundaryEdit(BaseModel):
    """Body for PUT /admin/cubes/{u}/{r}/{c}/boundary — no path params repeated.

    Phase 5 (05-04): last_label / last_catalog removed (SEG-01, migration 0005).
    """

    first_label: str | None = None
    first_catalog: str | None = None
    is_empty: bool = False
    force: bool = False  # True: skip phantom check


class ValidateRequest(BaseModel):
    """Body for POST /admin/cubes/validate."""

    updates: list[BoundaryEdit]


class SuggestRequest(BaseModel):
    """Body for POST /admin/cubes/suggest."""

    unit_id: int
    row: int
    col: int


class BulkWriteRequest(BaseModel):
    """Body for POST /admin/cubes/bulk — atomic multi-cube commit (D-10).

    All updates share a single change_set_id in boundary_history.
    The Idempotency-Key header must be provided by the caller;
    a replay with the same key returns the cached response without re-writing.

    Phase 5 (05-04): BoundaryEdit no longer carries last_label / last_catalog.
    Phase 7 (07-01): source field added so wizard/import commits are legible in
    History (D-04, Pitfall 1). Default 'bulk' preserves all existing callers.
    The DB CHECK constraint (migration 0007) is the value allowlist (T-07-01).
    """

    updates: list[BoundaryEdit]
    source: str = "bulk"  # 'bulk' | 'wizard' | 'reshuffle' | 'csv' | 'yaml'


# ── Helper ────────────────────────────────────────────────────────────────────


def _get_nominal_capacity(request: Request) -> int:
    """Read nominal cube capacity from the settings cache (default 95)."""
    settings_cache: dict[str, Any] = getattr(request.app.state, "settings_cache", {})
    raw = settings_cache.get("cube.nominal_capacity", 95)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        logger.warning(
            "cube.nominal_capacity=%r is not a valid int; falling back to 95",
            raw,
        )
        return 95


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/cubes")
async def get_admin_cubes(
    request: Request,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> dict[str, Any]:
    """Return all cubes with fill levels.

    Phase 5: fill_level = count_records_in_bin(SegmentBin) / nominal_capacity.
    Uses SegmentCache to count records per bin (no last_* range needed).
    Values > 1.0 mean overstuffed.  0 for is_empty cubes.

    Phase 6 (CR-03): scoped to the resolved profile_id from get_write_target so
    only the requesting admin's cubes are returned (no cross-profile row leakage).

    Response: ``{cubes: [{unit_id, row, col, is_empty, fill_level,
                           first_label, first_catalog}, ...]}``
    """
    profile_id, _ = _write_target
    nominal_capacity = _get_nominal_capacity(request)

    sql = """
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE profile_id = %s::uuid
ORDER BY unit_id, row, col
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id,))
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    cubes: list[dict[str, Any]] = []
    for row_raw in rows_raw:
        cube = dict(zip(cols_meta, row_raw, strict=True))

        # Use SegmentCache to get record count for this bin (no last_* needed)
        seg_bin = segment_cache.get_bin(cube["unit_id"], cube["row"], cube["col"])
        if seg_bin is not None and not cube.get("is_empty"):
            count = count_records_in_bin(seg_bin)
            cube["fill_level"] = count / nominal_capacity
            cube["record_count"] = count
        else:
            cube["fill_level"] = 0.0
            cube["record_count"] = 0

        cubes.append(cube)

    return {"cubes": cubes}


@router.get("/cubes/{unit_id}/{row}/{col}/boundary")
async def get_cube_boundary(
    request: Request,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> dict[str, Any]:
    """Return one cube's current boundary values.

    Phase 5: returns only cut-point columns (first_label, first_catalog, is_empty).
    last_label / last_catalog are no longer stored in cube_boundaries (SEG-01).

    Phase 6 (CR-03): scoped to the resolved profile_id from get_write_target so
    the admin sees only their profile's row, not another profile's row at the same
    physical coordinate.

    Response: ``{unit_id, row, col, first_label, first_catalog, is_empty}``

    HTTP 404 if no cube exists for the given coordinates.
    """
    profile_id, _ = _write_target
    sql = """
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (profile_id, unit_id, row, col))
        row_raw = await cur.fetchone()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    if row_raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "cube_not_found", "unit_id": unit_id, "row": row, "col": col},
        )

    return dict(zip(cols_meta, row_raw, strict=True))


@router.put("/cubes/{unit_id}/{row}/{col}/boundary")
async def put_cube_boundary(
    request: Request,
    body: PerCubeBoundaryEdit,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> JSONResponse:
    """Validate and (when valid) update a cube boundary.

    Phase 5 validation order (T-03-14, D-07):
      1. Phantom check (unless force=True): rejects values absent from v_collection;
         returns near_misses for tappable suggestions.
      2. On success: writes to cube_boundaries (cut-point only), logs to boundary_history,
         invalidates + reloads BoundaryCache, then re-derives SegmentCache (Pitfall A).

    NOTE: last_label / last_catalog removed from BoundaryEdit in Phase 5 (SEG-01).
    The cut-point model stores only first_label / first_catalog.

    Returns 400 with flat JSON (phantom/near_misses/message as top-level keys)
    so the frontend can distinguish phantom errors without unwrapping a nested
    ``detail`` object.
    """
    profile_id, bus = _write_target
    first_label = body.first_label or ""
    first_catalog = body.first_catalog or ""

    # ── Step 1: Phantom check (skipped when force=True) ──────────────────────
    # CR-01: pass resolved profile_id so validation targets the same profile
    # as the write, not the default profile.
    if not body.is_empty and not body.force:
        first_exists = await cube_exact_match(
            pool, first_label, first_catalog, profile_id=profile_id
        )

        if not first_exists:
            near_misses = await find_boundary_near_misses(
                pool, first_label, first_catalog, profile_id=profile_id
            )
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "type": "phantom_boundary",
                    "phantom": True,
                    "message": "No match in collection. Did you mean one of these?",
                    "near_misses": near_misses,
                    "unit_id": unit_id,
                    "row": row,
                    "col": col,
                },
            )

    # ── Step 2: DB write (boundary update + history log) ─────────────────────
    change_set_id = str(uuid.uuid4())
    new_first_label = first_label or None
    new_first_catalog = first_catalog or None

    async with pool.connection() as conn, conn.transaction():
        # Capture prev_* before overwriting (history audit) — scoped to resolved profile.
        prev = await fetch_current_boundary(conn, unit_id, row, col, profile_id=profile_id)
        if prev is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "cube_not_found", "unit_id": unit_id, "row": row, "col": col},
            )

        # Write new boundary scoped to resolved profile (T-06-01; DATA-01).
        rows_affected = await write_boundary(
            conn,
            unit_id,
            row,
            col,
            new_first_label,
            new_first_catalog,
            body.is_empty,
            profile_id=profile_id,
        )
        # 0-row write means the cube doesn't exist for this profile (D-10).
        if rows_affected == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "boundary_not_found", "unit_id": unit_id, "row": row, "col": col},
            )

        # Fetch the updated row for the response (scoped to resolved profile).
        write_sql = """
SELECT unit_id, row, col, first_label, first_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s
"""
        async with conn.cursor() as cur:
            await cur.execute(write_sql, (profile_id, unit_id, row, col))
            updated = await cur.fetchone()
            cols_meta = [desc[0] for desc in (cur.description or [])]

        # Append to boundary_history with the shared change_set_id and resolved profile.
        await write_history_row(
            conn,
            change_set_id,
            unit_id,
            row,
            col,
            prev,
            new_first_label,
            new_first_catalog,
            body.is_empty,
            source="manual",
            profile_id=profile_id,
        )
    # transaction commits atomically on exiting the conn.transaction() context.

    # Invalidate + reload BoundaryCache AFTER transaction commit (Pitfall A).
    # Then re-derive SegmentCache from the updated BoundaryCache (Phase 5 / 05-04).
    cache.invalidate()
    try:
        await cache.load(pool)
        # Re-derive SegmentCache from the refreshed BoundaryCache (D-07 / SEG-08).
        # Must use the same overrides that were in effect before invalidation.
        overrides: dict[tuple[int, int, int, str], float] = {}
        seg_bin_old = segment_cache.get_bin(unit_id, row, col)
        if seg_bin_old is not None:
            for seg in seg_bin_old.segments:
                if seg.is_override:
                    overrides[(unit_id, row, col, seg.label)] = seg.applied_fraction
        segment_cache.invalidate()
        segment_cache.derive(cache, snapshot, overrides)
    finally:
        await bus.publish(
            "boundary_changed",
            {
                "cube_ids": [{"unit": unit_id, "row": row, "col": col}],
                "change_set_id": change_set_id,
            },
        )

    return JSONResponse(
        status_code=200,
        content=dict(zip(cols_meta, updated, strict=True)),
    )


@router.post("/cubes/validate", response_model=None)
async def validate_boundary(
    request: Request,
    body: ValidateRequest,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> JSONResponse:
    """Dry-run boundary validation — NO DB write.

    For each proposed update, this endpoint:
    1. Checks phantom (cube_exact_match against v_collection): if not found AND force
       is False, returns phantom=True + near_misses.
    2. Calls validate_contiguity across all proposed updates.
    3. Computes movement_counts from the in-memory SegmentCache (diff preview).

    Returns HTTP 400 on phantom (when force=False) or contiguity violation.
    Returns HTTP 200 with valid=True + movement_counts when all checks pass.

    This endpoint performs NO INSERT/UPDATE/DELETE (T-03-14, ADMN-07).

    WR-01 (Phase 6 CR fix): profile_id resolved via get_write_target so phantom
    checks and near-miss lookups are scoped to the same profile as the matching
    commit path — preview and commit now agree.
    """
    profile_id, _ = _write_target
    nominal_capacity = _get_nominal_capacity(request)

    results: list[dict[str, Any]] = []

    for edit in body.updates:
        # is_empty short-circuit: no validation needed for is_empty cubes
        if edit.is_empty:
            results.append(
                {
                    "unit_id": edit.unit_id,
                    "row": edit.row,
                    "col": edit.col,
                    "valid": True,
                    "movement_counts": _compute_movement_counts(
                        edit,
                        segment_cache,
                        nominal_capacity,
                    ),
                }
            )
            continue

        first_label = edit.first_label or ""
        first_catalog = edit.first_catalog or ""

        # ── Step 1: Phantom check (skipped when force=True) ──────────────────
        # WR-01: pass resolved profile_id so preview and commit share one scope.
        if not edit.force:
            first_exists = await cube_exact_match(
                pool, first_label, first_catalog, profile_id=profile_id
            )

            if not first_exists:
                near_misses = await find_boundary_near_misses(
                    pool, first_label, first_catalog, profile_id=profile_id
                )
                results.append(
                    {
                        "unit_id": edit.unit_id,
                        "row": edit.row,
                        "col": edit.col,
                        "valid": False,
                        "phantom": True,
                        "phantom_field": "first",
                        "message": "No match in collection. Did you mean one of these?",
                        "near_misses": near_misses,
                        "movement_counts": [],
                    }
                )
                continue

        # ── Step 2: Movement counts from SegmentCache (no DB) ────────────────
        movement_counts = _compute_movement_counts(
            edit,
            segment_cache,
            nominal_capacity,
        )

        results.append(
            {
                "unit_id": edit.unit_id,
                "row": edit.row,
                "col": edit.col,
                "valid": True,
                "movement_counts": movement_counts,
            }
        )

    # ── Step 3: Contiguity check across ALL proposed updates ──────────────────
    if results and all(r.get("valid", False) for r in results):
        updates_as_dicts: list[dict[str, object]] = [
            {
                "unit_id": e.unit_id,
                "row": e.row,
                "col": e.col,
                "first_label": e.first_label,
                "first_catalog": e.first_catalog,
                "is_empty": e.is_empty,
            }
            for e in body.updates
        ]
        contiguity_error = validate_contiguity(updates_as_dicts, segment_cache)
        if contiguity_error is not None:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "type": "contiguity_violation",
                    "message": contiguity_error,
                    "results": results,
                },
            )

    # WR-09: Use bool(results) so an empty updates list is not vacuously "valid"
    all_valid = bool(results) and all(r.get("valid", False) for r in results)
    return JSONResponse(
        status_code=200,
        content={
            "valid": all_valid,
            "results": results,
            "movement_counts": results[0]["movement_counts"] if len(results) == 1 else None,
        },
    )


def _compute_movement_counts(
    edit: BoundaryEdit,
    segment_cache: SegmentCache,
    nominal_capacity: int,
) -> list[dict[str, Any]]:
    """Compute before/after record-movement counts for a proposed edit.

    Phase 5 (05-04): uses SegmentCache + count_records_in_bin instead of the
    retired count_records_in_boundary + BoundaryRow(last_*=...) approach.

    Reads the current bin from SegmentCache (before) and returns the count.
    The "after" count requires re-deriving the SegmentCache with the new cut
    point; since this is a dry-run diff endpoint, we return the current count
    as both before and after (the caller uses the live SegmentCache). For a
    full diff, the caller should re-derive after the proposed edit is committed.

    Returns a list with one dict describing the movement for the edited cube.
    """
    seg_bin = segment_cache.get_bin(edit.unit_id, edit.row, edit.col)
    records_before = count_records_in_bin(seg_bin) if seg_bin is not None else 0

    # For the proposed (after) state: we cannot re-derive without writing to DB
    # (Pitfall A), so we use the current count as an approximation.
    # The actual post-commit count will be computed by the live SegmentCache.
    records_after = records_before  # approximation; real diff computed post-commit

    return [
        {
            "unit_id": edit.unit_id,
            "row": edit.row,
            "col": edit.col,
            "records_before": records_before,
            "records_after": records_after,
            "delta": records_after - records_before,
            "fill_level_before": records_before / nominal_capacity,
            "fill_level_after": records_after / nominal_capacity,
        }
    ]


@router.post("/cubes/suggest")
async def suggest_cube_midpoint(
    request: Request,
    body: SuggestRequest,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Suggest an index-space midpoint between this cube and the next populated cube.

    Phase 5 (05-04): Derives the last record of the current bin from SegmentCache
    instead of reading current.last_label / last_catalog (which no longer exist).

    Walks collection-INDEX space (Pitfall 22, D-08) — never catalog-string space.
    Returns a real owned record from the snapshot or null if no midpoint exists.

    Response on success: ``{suggestion: {release_id, label, catalog_number}}``
    Response when no midpoint: ``{suggestion: null}``
    """
    # Get the SegmentBin for the requested cube
    current_bin = segment_cache.get_bin(body.unit_id, body.row, body.col)
    if current_bin is None or not current_bin.segments:
        return {"suggestion": None}

    # Derive the "last record" of this bin using SegmentCache rank info.
    # The last record is the one at the highest rank in the bin's last segment
    # (by label casefold order, the last segment's last_rank_in_label).
    last_seg = current_bin.segments[-1]
    last_label = last_seg.label

    # Retrieve the last record in this segment from the snapshot
    label_records = sorted(
        snapshot.get_label_records(last_label),
        key=lambda r: parse_key(r.catalog_number),
    )
    if last_seg.last_rank_in_label >= len(label_records):
        return {"suggestion": None}

    last_record = label_records[last_seg.last_rank_in_label]
    first_anchor_id = last_record.release_id

    # Find the next non-empty cube in shelf order
    boundary_index: dict[tuple[int, int, int], Any] = {
        (b.unit_id, b.row, b.col): b for b in cache.get_boundaries()
    }
    next_cube = _find_next_populated_cube(body.unit_id, body.row, body.col, cache, boundary_index)
    if next_cube is None:
        return {"suggestion": None}

    # Get the next cube's SegmentBin; the first record is the second anchor
    next_bin = segment_cache.get_bin(next_cube["unit_id"], next_cube["row"], next_cube["col"])
    if next_bin is None or not next_bin.segments:
        return {"suggestion": None}

    first_seg = next_bin.segments[0]
    next_label = first_seg.label

    # Both anchors must be in the same label for index-space midpoint (D-08)
    if last_label.casefold() != next_label.casefold():
        # Cross-label boundary — suggest from the next cube's label via adjacent index
        # For now, return None (cross-label midpoint is out of scope for v1)
        return {"suggestion": None}

    # Retrieve the first record of the next bin's first segment
    next_label_records = sorted(
        snapshot.get_label_records(next_label),
        key=lambda r: parse_key(r.catalog_number),
    )
    if first_seg.first_rank_in_label >= len(next_label_records):
        return {"suggestion": None}

    last_anchor_record = next_label_records[first_seg.first_rank_in_label]
    last_anchor_id = last_anchor_record.release_id

    mid_record = suggest_midpoint(
        label=last_label,
        first_anchor_release_id=first_anchor_id,
        last_anchor_release_id=last_anchor_id,
        snapshot=snapshot,
    )

    if mid_record is None:
        return {"suggestion": None}

    return {
        "suggestion": {
            "release_id": mid_record.release_id,
            "label": mid_record.label,
            "catalog_number": mid_record.catalog_number,
        }
    }


def _find_next_populated_cube(
    unit_id: int,
    row: int,
    col: int,
    cache: BoundaryCache,
    boundary_index: dict[tuple[int, int, int], Any],
) -> dict[str, int] | None:
    """Find the next non-empty cube after (unit_id, row, col) in shelf order.

    Iterates cubes in (unit_id, row, col) order.
    Returns the coordinate dict of the first populated (non is_empty) cube found.
    Returns None if no populated cube follows.
    """
    all_boundaries = sorted(
        cache.get_boundaries(),
        key=lambda b: (b.unit_id, b.row, b.col),
    )

    found_current = False
    for boundary in all_boundaries:
        if boundary.unit_id == unit_id and boundary.row == row and boundary.col == col:
            found_current = True
            continue
        if found_current and not boundary.is_empty:
            return {
                "unit_id": boundary.unit_id,
                "row": boundary.row,
                "col": boundary.col,
            }

    return None


@router.post("/cubes/bulk")
async def bulk_write_cubes(
    request: Request,
    body: BulkWriteRequest,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> JSONResponse:
    """Atomic bulk commit of all pending cube boundary edits (D-10, ADMN-09).

    Phase 5 (05-04): BoundaryEdit no longer carries last_label / last_catalog.
    After the transaction commits, invalidates BoundaryCache + reloads, then
    re-derives SegmentCache (Pitfall A — NEVER inside the transaction).

    All updates are validated (phantom check) before ANY write.
    Writes all cubes in a single DB transaction sharing one change_set_id.
    AFTER the transaction commits, invalidates + reloads the boundary cache
    and re-derives SegmentCache (Pitfall A — cache.invalidate() is NEVER
    called inside the transaction).

    Idempotency-Key header (D-10, Pitfall 7):
      - If the key was seen before, returns the cached response immediately.
      - If new, stores the key + response inside the transaction.
      - Old keys (>24h) are pruned on each bulk (Pitfall E).

    Security:
      - require_admin enforces session cookie + CSRF (T-03-18).
      - All SQL uses %s placeholders (T-03-24).
      - A failed transaction NEVER empties the live cache (T-03-22).

    Returns:
      ``{change_set_id: str, applied: int}``
    """
    profile_id, bus = _write_target

    # ── Idempotency short-circuit (Pitfall 7) ────────────────────────────────
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        cached = await check_idempotency(pool, idempotency_key)
        if cached is not None:
            return JSONResponse(content=cached)

    # ── Validate ALL cubes before any write (Pitfall 11 / T-03-19) ──────────
    for edit in body.updates:
        if edit.is_empty:
            continue
        first_label = edit.first_label or ""
        first_catalog = edit.first_catalog or ""

        # Phantom check (skipped when force=True)
        # CR-01: pass resolved profile_id so validation targets the same profile
        # as the write, not the default profile.
        if not edit.force:
            first_exists = await cube_exact_match(
                pool, first_label, first_catalog, profile_id=profile_id
            )

            if not first_exists:
                near_misses = await find_boundary_near_misses(
                    pool, first_label, first_catalog, profile_id=profile_id
                )
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={
                        "type": "phantom_boundary",
                        "phantom": True,
                        "message": "No match in collection. Did you mean one of these?",
                        "near_misses": near_misses,
                        "unit_id": edit.unit_id,
                        "row": edit.row,
                        "col": edit.col,
                    },
                )

    # ── Single atomic transaction: write boundary + history for all cubes ────
    change_set_id = str(uuid.uuid4())
    response_body: dict[str, Any] = {
        "change_set_id": change_set_id,
        "applied": len(body.updates),
    }

    async with pool.connection() as conn, conn.transaction():
        for edit in body.updates:
            # Capture prev_* before overwriting (history audit) — scoped to resolved profile.
            prev = await fetch_current_boundary(
                conn, edit.unit_id, edit.row, edit.col, profile_id=profile_id
            )

            # Write new boundary values (cut-point shape: first_* + is_empty only)
            new_first_label = edit.first_label if not edit.is_empty else None
            new_first_catalog = edit.first_catalog if not edit.is_empty else None

            rows_affected = await write_boundary(
                conn,
                edit.unit_id,
                edit.row,
                edit.col,
                new_first_label,
                new_first_catalog,
                edit.is_empty,
                profile_id=profile_id,
            )
            # D-11: if any cube affects 0 rows, raise INSIDE the transaction to abort all.
            if rows_affected == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={
                        "type": "boundary_not_found",
                        "unit_id": edit.unit_id,
                        "row": edit.row,
                        "col": edit.col,
                    },
                )

            # Append to boundary_history with shared change_set_id + resolved profile.
            await write_history_row(
                conn,
                change_set_id,
                edit.unit_id,
                edit.row,
                edit.col,
                prev,
                new_first_label,
                new_first_catalog,
                edit.is_empty,
                source=body.source,  # Phase 7: use caller-supplied source (D-15, T-07-01)
                profile_id=profile_id,
            )

        # Store idempotency key inside transaction (atomic with writes)
        if idempotency_key:
            await store_idempotency(conn, idempotency_key, response_body)

        # Prune old idempotency keys (Pitfall E)
        await cleanup_idempotency(conn)

    # ── Invalidate + reload BoundaryCache AFTER transaction commit (Pitfall A) ─
    # CR review CR-01: publish in `finally` so a transient cache.load() failure
    # never strands SSE subscribers on stale data (the bulk write already committed).
    cache.invalidate()
    try:
        await cache.load(pool)
        # Re-derive SegmentCache from the refreshed BoundaryCache (Phase 5 / 05-04).
        # Collect overrides from the current (pre-invalidation) SegmentCache state.
        overrides: dict[tuple[int, int, int, str], float] = {}
        for edit in body.updates:
            seg_bin = segment_cache.get_bin(edit.unit_id, edit.row, edit.col)
            if seg_bin is not None:
                for seg in seg_bin.segments:
                    if seg.is_override:
                        key = (edit.unit_id, edit.row, edit.col, seg.label)
                        overrides[key] = seg.applied_fraction
        segment_cache.invalidate()
        segment_cache.derive(cache, snapshot, overrides)
    finally:
        await bus.publish(
            "boundary_changed",
            {
                "cube_ids": [{"unit": e.unit_id, "row": e.row, "col": e.col} for e in body.updates],
                "change_set_id": response_body["change_set_id"],
            },
        )

    return JSONResponse(content=response_body)

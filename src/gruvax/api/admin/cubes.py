"""Admin cube boundary endpoints — read, dry-run validate, and suggest-midpoint.

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
        1. POS-01 comparator (parse_key): rejects first > last (always, even with force).
        2. Phantom check (cube_exact_match): unless force=true, rejects (label, catalog)
           pairs absent from v_collection and returns trigram near-misses.
        3. Movement counts: computed from the in-memory collection snapshot.
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
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.api.deps import get_boundary_cache, get_collection_snapshot, get_pool, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.boundary_math import count_records_in_boundary, suggest_midpoint
from gruvax.estimator.collection_snapshot import CollectionSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-cubes"])

# ── Request / Response models ──────────────────────────────────────────────────


class BoundaryEdit(BaseModel):
    """One cube boundary proposal — the shape used for validate and suggest."""

    unit_id: int
    row: int
    col: int
    first_label: str | None = None
    first_catalog: str | None = None
    last_label: str | None = None
    last_catalog: str | None = None
    is_empty: bool = False
    force: bool = False  # True: skip phantom check (still runs comparator)


class PerCubeBoundaryEdit(BaseModel):
    """Body for PUT /admin/cubes/{u}/{r}/{c}/boundary — no path params repeated."""

    first_label: str | None = None
    first_catalog: str | None = None
    last_label: str | None = None
    last_catalog: str | None = None
    is_empty: bool = False
    force: bool = False  # True: skip phantom check (still runs comparator)


class ValidateRequest(BaseModel):
    """Body for POST /admin/cubes/validate."""

    updates: list[BoundaryEdit]


class SuggestRequest(BaseModel):
    """Body for POST /admin/cubes/suggest."""

    unit_id: int
    row: int
    col: int


# ── Helper ────────────────────────────────────────────────────────────────────


def _get_nominal_capacity(request: Request) -> int:
    """Read nominal cube capacity from the settings cache (default 95)."""
    settings_cache: dict[str, Any] = getattr(request.app.state, "settings_cache", {})
    raw = settings_cache.get("cube.nominal_capacity", 95)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return 95


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/cubes")
async def get_admin_cubes(
    request: Request,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Return all cubes with fill levels.

    fill_level = count_records_in_boundary / nominal_capacity.
    Values > 1.0 mean overstuffed.  0 for is_empty cubes.

    Response: ``{cubes: [{unit_id, row, col, is_empty, fill_level,
                           first_label, first_catalog, last_label, last_catalog}, ...]}``
    """
    nominal_capacity = _get_nominal_capacity(request)

    sql = """
SELECT unit_id, row, col, first_label, first_catalog,
       last_label, last_catalog, is_empty
FROM gruvax.cube_boundaries
ORDER BY unit_id, row, col
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql)
        rows_raw = await cur.fetchall()
        cols_meta = [desc[0] for desc in (cur.description or [])]

    # Build a lookup from (unit_id, row, col) → BoundaryRow for fill-level calc
    boundary_index: dict[tuple[int, int, int], Any] = {
        (b.unit_id, b.row, b.col): b for b in cache.get_boundaries()
    }

    cubes: list[dict[str, Any]] = []
    for row_raw in rows_raw:
        cube = dict(zip(cols_meta, row_raw, strict=True))

        # Look up the BoundaryRow from the cache for fill-level calculation
        boundary_row = boundary_index.get((cube["unit_id"], cube["row"], cube["col"]))
        if boundary_row is not None:
            count = count_records_in_boundary(boundary_row, snapshot)
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
) -> dict[str, Any]:
    """Return one cube's current boundary values.

    Response: ``{unit_id, row, col, first_label, first_catalog,
                 last_label, last_catalog, is_empty}``

    HTTP 404 if no cube exists for the given coordinates.
    """
    sql = """
SELECT unit_id, row, col, first_label, first_catalog,
       last_label, last_catalog, is_empty
FROM gruvax.cube_boundaries
WHERE unit_id = %s AND row = %s AND col = %s
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(sql, (unit_id, row, col))
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
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Validate and (when valid) update a cube boundary.

    Validation order (T-03-14, D-07):
      1. POS-01 comparator: rejects first > last always, even with force=True.
      2. Phantom check (unless force=True): rejects values absent from v_collection;
         returns near_misses for tappable suggestions.
      3. On success: writes to cube_boundaries, logs to boundary_history,
         invalidates + reloads the boundary cache.

    NOTE: In plan 04, this endpoint drives the boundary editor. Plan 05 will
    add the bulk-write endpoint for multi-cube commits via pendingChangeSet.

    Returns 400 with flat JSON (phantom/near_misses/message as top-level keys)
    so the frontend can distinguish phantom errors from comparator errors without
    unwrapping a nested ``detail`` object.
    """
    from gruvax.api.admin.validation import validate_boundary_order
    from gruvax.db.queries import cube_exact_match, find_boundary_near_misses

    first_label = body.first_label or ""
    first_catalog = body.first_catalog or ""
    last_label = body.last_label or ""
    last_catalog = body.last_catalog or ""

    # ── Step 1: POS-01 comparator (always, even force=True) ─────────────────
    if not body.is_empty and not validate_boundary_order(
        first_label, first_catalog, last_label, last_catalog
    ):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "type": "boundary_order_error",
                "message": "First record comes after last record. Check the order.",
                "unit_id": unit_id,
                "row": row,
                "col": col,
            },
        )

    # ── Step 2: Phantom check (skipped when force=True) ──────────────────────
    if not body.is_empty and not body.force:
        first_exists = await cube_exact_match(pool, first_label, first_catalog)
        if first_label == last_label and first_catalog == last_catalog:
            last_exists = first_exists
        else:
            last_exists = await cube_exact_match(pool, last_label, last_catalog)

        if not first_exists or not last_exists:
            phantom_label = first_label if not first_exists else last_label
            phantom_catalog = first_catalog if not first_exists else last_catalog
            near_misses = await find_boundary_near_misses(pool, phantom_label, phantom_catalog)
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

    # ── Step 3: DB write (boundary update + history log) ─────────────────────
    # Note: In plan 05, multi-cube edits go through POST /cubes/bulk.
    # This endpoint handles single-cube edits from the per-cube editor.
    write_sql = """
UPDATE gruvax.cube_boundaries
SET first_label = %s, first_catalog = %s,
    last_label = %s, last_catalog = %s,
    is_empty = %s
WHERE unit_id = %s AND row = %s AND col = %s
RETURNING unit_id, row, col, first_label, first_catalog, last_label, last_catalog, is_empty
"""
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            write_sql,
            (
                first_label or None,
                first_catalog or None,
                last_label or None,
                last_catalog or None,
                body.is_empty,
                unit_id,
                row,
                col,
            ),
        )
        updated = await cur.fetchone()
        cols_meta = [desc[0] for desc in (cur.description or [])]
        await conn.commit()

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "cube_not_found", "unit_id": unit_id, "row": row, "col": col},
        )

    # Invalidate + reload the boundary cache after commit (Pitfall A)
    cache.invalidate()
    await cache.load(pool)

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
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Dry-run boundary validation — NO DB write.

    For each proposed update, this endpoint:
    1. Runs the POS-01 comparator (parse_key): rejects first > last even with force.
    2. Checks phantom (cube_exact_match against v_collection): if not found AND force
       is False, returns phantom=True + near_misses.
    3. Computes movement_counts from the in-memory snapshot (diff preview).

    Returns HTTP 400 on comparator failure or phantom (when force=False).
    Returns HTTP 200 with valid=True + movement_counts when all checks pass.

    This endpoint performs NO INSERT/UPDATE/DELETE (T-03-14, ADMN-07).
    """
    from gruvax.api.admin.validation import validate_boundary_order
    from gruvax.db.queries import cube_exact_match, find_boundary_near_misses

    nominal_capacity = _get_nominal_capacity(request)

    results: list[dict[str, Any]] = []

    for edit in body.updates:
        # is_empty short-circuit: no validation needed for is_empty cubes
        if edit.is_empty:
            results.append({
                "unit_id": edit.unit_id,
                "row": edit.row,
                "col": edit.col,
                "valid": True,
                "movement_counts": _compute_movement_counts(
                    edit, cache, snapshot, nominal_capacity,
                ),
            })
            continue

        first_label = edit.first_label or ""
        first_catalog = edit.first_catalog or ""
        last_label = edit.last_label or ""
        last_catalog = edit.last_catalog or ""

        # ── Step 1: POS-01 comparator — always runs, even with force ────────
        if not validate_boundary_order(first_label, first_catalog, last_label, last_catalog):
            results.append({
                "unit_id": edit.unit_id,
                "row": edit.row,
                "col": edit.col,
                "valid": False,
                "error": "boundary_order_error",
                "message": "First record comes after last record. Check the order.",
                "movement_counts": [],
            })
            continue

        # ── Step 2: Phantom check (skipped when force=True) ──────────────────
        if not edit.force:
            # Check first boundary
            first_exists = await cube_exact_match(pool, first_label, first_catalog)
            # Check last boundary (only if different from first)
            if first_label == last_label and first_catalog == last_catalog:
                last_exists = first_exists
            else:
                last_exists = await cube_exact_match(pool, last_label, last_catalog)

            if not first_exists or not last_exists:
                # Find near-misses for whichever boundary is phantom
                phantom_label = first_label if not first_exists else last_label
                phantom_catalog = first_catalog if not first_exists else last_catalog
                near_misses = await find_boundary_near_misses(
                    pool, phantom_label, phantom_catalog
                )
                results.append({
                    "unit_id": edit.unit_id,
                    "row": edit.row,
                    "col": edit.col,
                    "valid": False,
                    "phantom": True,
                    "message": "No match in collection. Did you mean one of these?",
                    "near_misses": near_misses,
                    "movement_counts": [],
                })
                continue

        # ── Step 3: Movement counts from snapshot (no DB) ────────────────────
        movement_counts = _compute_movement_counts(
            edit, cache, snapshot, nominal_capacity,
        )

        results.append({
            "unit_id": edit.unit_id,
            "row": edit.row,
            "col": edit.col,
            "valid": True,
            "movement_counts": movement_counts,
        })

    all_valid = all(r.get("valid", False) for r in results)
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
    cache: BoundaryCache,
    snapshot: CollectionSnapshot,
    nominal_capacity: int,
) -> list[dict[str, Any]]:
    """Compute before/after record-movement counts for a proposed edit.

    Reads the current boundary from the cache (before) and computes the
    record count that would be in the proposed boundary (after) using
    count_records_in_boundary over the in-memory snapshot.  No DB access.

    Returns a list with one dict describing the movement for the edited cube.
    """
    from gruvax.estimator.boundary_cache import BoundaryRow

    boundary_index: dict[tuple[int, int, int], Any] = {
        (b.unit_id, b.row, b.col): b for b in cache.get_boundaries()
    }
    current = boundary_index.get((edit.unit_id, edit.row, edit.col))
    records_before = count_records_in_boundary(current, snapshot) if current else 0

    # Construct a synthetic BoundaryRow for the proposed values
    proposed = BoundaryRow(
        unit_id=edit.unit_id,
        row=edit.row,
        col=edit.col,
        first_label=edit.first_label,
        first_catalog=edit.first_catalog,
        last_label=edit.last_label,
        last_catalog=edit.last_catalog,
        is_empty=edit.is_empty,
    )
    records_after = count_records_in_boundary(proposed, snapshot)

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
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Suggest an index-space midpoint between this cube and the next populated cube.

    Walks collection-INDEX space (Pitfall 22, D-08) — never catalog-string space.
    Returns a real owned record from the snapshot or null if no midpoint exists.

    Response on success: ``{suggestion: {release_id, label, catalog_number}}``
    Response when no midpoint: ``{suggestion: null}``
    """
    from gruvax.db.queries import get_catalogs_for_label

    boundary_index: dict[tuple[int, int, int], Any] = {
        (b.unit_id, b.row, b.col): b for b in cache.get_boundaries()
    }
    current = boundary_index.get((body.unit_id, body.row, body.col))
    if current is None:
        return {"suggestion": None}

    # Find the label shared by the adjacent cube boundary
    # Use the last record of the current cube as the first anchor,
    # and the first record of the next populated cube as the second anchor.
    if not current.last_label or not current.last_catalog:
        return {"suggestion": None}

    # Look up the release_id for the current cube's last record from v_collection
    last_records = await get_catalogs_for_label(pool, current.last_label)
    first_anchor_id: int | None = None
    for rec in last_records:
        if rec["catalog_number"] == current.last_catalog:
            first_anchor_id = rec["release_id"]
            break

    if first_anchor_id is None:
        return {"suggestion": None}

    # Find the next cube (same unit: next col; if at end of row, next row; etc.)
    next_cube = _find_next_populated_cube(body.unit_id, body.row, body.col, cache, boundary_index)
    if next_cube is None:
        return {"suggestion": None}

    # The next cube's first record is the second anchor
    next_boundary = boundary_index.get((next_cube["unit_id"], next_cube["row"], next_cube["col"]))
    if (
        next_boundary is None
        or next_boundary.first_label is None
        or next_boundary.first_catalog is None
    ):
        return {"suggestion": None}

    # Both anchors must be in the same label for index-space midpoint (D-08)
    if current.last_label.casefold() != next_boundary.first_label.casefold():
        # Cross-label boundary — suggest from the next cube's label using adjacent index
        # For now, return None (cross-label midpoint is out of scope for v1)
        return {"suggestion": None}

    # Look up the release_id for the next cube's first record
    next_records = await get_catalogs_for_label(pool, next_boundary.first_label)
    last_anchor_id: int | None = None
    for rec in next_records:
        if rec["catalog_number"] == next_boundary.first_catalog:
            last_anchor_id = rec["release_id"]
            break

    if last_anchor_id is None:
        return {"suggestion": None}

    mid_record = suggest_midpoint(
        label=current.last_label,
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

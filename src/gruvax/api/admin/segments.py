"""Admin segment endpoints — view derived segments, edit cut points, manage overrides, insert cut.

Endpoints:
  - ``GET /admin/cubes/{unit_id}/{row}/{col}/segments``:
      Returns derived segment data for a bin from SegmentCache (no DB read).
      HTTP 404 if no bin exists at the given coordinates.
      Requires admin session (require_admin).

  - ``PUT /admin/cubes/{unit_id}/{row}/{col}/cut``:
      Update the cut point for a bin (first_label + first_catalog).
      Runs phantom check (unless force=True), writes via cube_boundaries,
      then invalidates + re-derives SegmentCache, publishes boundary_changed.
      Requires admin session + CSRF.

  - ``POST /admin/cubes/{unit_id}/{row}/{col}/overrides``:
      Set per-label physical-width overrides for a bin.
      Null fraction clears the override.  Rejects labels absent from the bin's
      derived segments (phantom override injection guard — T-05-04-02).
      Upserts into gruvax.segment_overrides; honors Idempotency-Key.
      Invalidates + re-derives SegmentCache, publishes boundary_changed.
      Requires admin session + CSRF.

  - ``POST /admin/cubes/insert-cut``:
      Insert a new cut point after a given (unit_id, row, col), cascading all
      subsequent cut points by one position.  Runs phantom check + shelf overflow +
      empty-bin validation before writing.  Writes all affected cubes as ONE
      change-set (source='cut_insert') so the cut is undoable via /history revert.
      Invalidates + re-derives SegmentCache, publishes boundary_changed.
      Requires admin session + CSRF.

Security:
  - Every handler depends on require_admin (T-05-04-01, ASVS V4 carry-forward).
  - Fraction bounds validated by Pydantic (0 < fraction <= 1.0) + DB CHECK (T-05-04-03).
  - Phantom override injection rejected server-side (T-05-04-02).
  - Shelf overflow guarded by validate_shelf_overflow before insert (T-05-04-04).
  - Idempotency-Key dedup: check → execute → store in one transaction (T-05-04-05, Pitfall 7).
  - All SQL uses %s placeholders, zero f-string interpolation (T-05-04-06, T-03-24).

Phase 5 (05-04 / SEG-08):
  - SegmentCache invalidated + re-derived on every write (Pitfall A: AFTER commit).
  - insert-cut uses source='cut_insert' (boundary_history CHECK extended in migration 0005).
  - Override writes use gruvax.segment_overrides (SEG-04 table from migration 0005).
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gruvax.api.deps import (
    get_boundary_cache,
    get_collection_snapshot,
    get_event_bus,
    get_pool,
    get_segment_cache,
    require_admin,
)
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache
from gruvax.events.bus import EventBus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-segments"])


# ── Request / Response models ──────────────────────────────────────────────────


class CutEditBody(BaseModel):
    """Body for PUT /admin/cubes/{u}/{r}/{c}/cut.

    Phase 5 (SEG-08): cut-point model stores only first_label + first_catalog.
    """

    first_label: str
    first_catalog: str
    force: bool = False  # True: skip phantom check


class LabelOverride(BaseModel):
    """One label override entry within a POST /overrides body.

    fraction=None clears the override for this label.
    Fraction must be strictly positive and at most 1.0 (T-05-04-03):
    - fraction=0.0 would erase the segment (forbidden by DB CHECK)
    - fraction>1.0 is geometrically impossible (sub-cube band > full cube)
    """

    label: str
    fraction: float | None = Field(default=None, gt=0.0, le=1.0)


class OverridesBody(BaseModel):
    """Body for POST /admin/cubes/{u}/{r}/{c}/overrides."""

    overrides: list[LabelOverride]


class InsertCutBody(BaseModel):
    """Body for POST /admin/cubes/insert-cut.

    Inserts a new cut point immediately AFTER (after_unit_id, after_row, after_col),
    cascading all subsequent cubes by one position.
    """

    after_unit_id: int
    after_row: int
    after_col: int
    new_first_label: str
    new_first_catalog: str
    force: bool = False  # True: skip phantom check


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/cubes/{unit_id}/{row}/{col}/segments")
async def get_bin_segments(
    request: Request,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    _admin: dict[str, Any] = Depends(require_admin),
) -> dict[str, Any]:
    """Return derived segment data for a bin (no DB access — from SegmentCache).

    Response:
    ``{segments: [{label, fraction, is_override, auto_fraction, continues,
                   segment_count, first_rank_in_label, last_rank_in_label}]}``

    HTTP 404 if no bin exists at the given coordinates.
    """
    seg_bin = segment_cache.get_bin(unit_id, row, col)
    if seg_bin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "type": "bin_not_found",
                "unit_id": unit_id,
                "row": row,
                "col": col,
            },
        )

    segments = [
        {
            "label": seg.label,
            "fraction": seg.applied_fraction,
            "auto_fraction": seg.auto_fraction,
            "is_override": seg.is_override,
            "continues": seg.continues,
            "segment_count": seg.segment_count,
            "first_rank_in_label": seg.first_rank_in_label,
            "last_rank_in_label": seg.last_rank_in_label,
        }
        for seg in seg_bin.segments
    ]
    return {"segments": segments, "unit_id": unit_id, "row": row, "col": col}


@router.put("/cubes/{unit_id}/{row}/{col}/cut")
async def put_bin_cut(
    request: Request,
    body: CutEditBody,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    bus: EventBus = Depends(get_event_bus),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Update the cut point for a bin.

    Phantom check (unless force=True): rejects (first_label, first_catalog) pairs
    not in gruvax.v_collection.  On success: writes to cube_boundaries, logs to
    boundary_history (source='manual'), then invalidates + re-derives SegmentCache
    and publishes boundary_changed (Pitfall A: after transaction commit).

    Returns 400 with phantom/near_misses on phantom rejection, 200 on success.
    """
    from gruvax.db.queries import (
        cube_exact_match,
        fetch_current_boundary,
        find_boundary_near_misses,
        write_boundary,
        write_history_row,
    )

    first_label = body.first_label.strip()
    first_catalog = body.first_catalog.strip()

    # ── Phantom check (skipped when force=True) ──────────────────────────────
    if not body.force:
        first_exists = await cube_exact_match(pool, first_label, first_catalog)
        if not first_exists:
            near_misses = await find_boundary_near_misses(pool, first_label, first_catalog)
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

    # ── Contiguity check (SEG-05 / D-09 — Direction A) ───────────────────────
    # Enforce label contiguity on the live write path BEFORE the DB transaction
    # so a scatter-inducing cut is never committed.  Direction A (enforce here,
    # not via the orphaned DiffPreviewSheet/preview route) is the lowest-risk
    # fix: one validate_contiguity call per direct write path instead of
    # re-wiring the whole editor through the two-step validate→preview→commit
    # flow that the owner accepted dropping (05-UAT.md test 5 note).
    from gruvax.api.admin.validation import build_proposed_cuts, validate_contiguity

    proposed = build_proposed_cuts(cache, replace=(unit_id, row, col, first_label, first_catalog))
    contiguity_error = validate_contiguity(proposed, segment_cache)
    if contiguity_error is not None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "type": "contiguity_error",
                "message": contiguity_error,
                "unit_id": unit_id,
                "row": row,
                "col": col,
            },
        )

    # ── DB write ──────────────────────────────────────────────────────────────
    # Note: validate_no_empty_bin is NOT called here — PUT /cut REPLACES the
    # existing cut point (not inserts a new one), so there's no risk of an
    # empty leading bin.  validate_no_empty_bin is used in POST /insert-cut.
    change_set_id = str(_uuid.uuid4())

    async with pool.connection() as conn, conn.transaction():
        prev = await fetch_current_boundary(conn, unit_id, row, col)
        if prev is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "cube_not_found", "unit_id": unit_id, "row": row, "col": col},
            )

        await write_boundary(conn, unit_id, row, col, first_label, first_catalog, is_empty=False)

        await write_history_row(
            conn,
            change_set_id,
            unit_id,
            row,
            col,
            prev,
            first_label,
            first_catalog,
            new_is_empty=False,
            source="manual",
        )

    # ── Invalidate + re-derive SegmentCache AFTER commit (Pitfall A) ─────────
    cache.invalidate()
    try:
        await cache.load(pool)
        # Collect overrides from pre-invalidation state to preserve admin fractions
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
                "type": "boundary_changed",
                "change_set_id": change_set_id,
                "cubes": [{"unit_id": unit_id, "row": row, "col": col}],
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "change_set_id": change_set_id,
            "unit_id": unit_id,
            "row": row,
            "col": col,
            "first_label": first_label,
            "first_catalog": first_catalog,
        },
    )


@router.post("/cubes/{unit_id}/{row}/{col}/overrides")
async def set_bin_overrides(
    request: Request,
    body: OverridesBody,
    unit_id: int = Path(ge=1),
    row: int = Path(ge=0),
    col: int = Path(ge=0),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    bus: EventBus = Depends(get_event_bus),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Set per-label physical-width overrides for a bin.

    Phantom override injection guard (T-05-04-02): rejects any override whose
    label is not present in the bin's derived segments.  Null fraction clears the
    override for that label (DELETE from segment_overrides).  Non-null fraction is
    upserted into gruvax.segment_overrides.

    Idempotency-Key supported: a replay with the same key returns the cached
    response without re-writing (Pitfall 7).

    After commit: invalidates + re-derives SegmentCache; publishes boundary_changed.

    Response: ``{applied: int, cleared: int}`` (counts of upserted / deleted rows).
    """
    from gruvax.db.queries import check_idempotency, cleanup_idempotency, store_idempotency

    idempotency_key: str | None = request.headers.get("Idempotency-Key")

    # ── Idempotency replay check ──────────────────────────────────────────────
    if idempotency_key:
        cached = await check_idempotency(pool, idempotency_key)
        if cached is not None:
            return JSONResponse(status_code=200, content=cached)

    # ── Validate bin exists ───────────────────────────────────────────────────
    seg_bin = segment_cache.get_bin(unit_id, row, col)
    if seg_bin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "bin_not_found", "unit_id": unit_id, "row": row, "col": col},
        )

    # ── Phantom override injection guard (T-05-04-02) ─────────────────────────
    # Build the set of labels currently derived in this bin (casefold comparison)
    bin_labels = {seg.label.casefold() for seg in seg_bin.segments}

    phantom_labels = [ov.label for ov in body.overrides if ov.label.casefold() not in bin_labels]
    if phantom_labels:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "type": "phantom_override",
                "message": "Cannot set override for labels not present in this bin.",
                "phantom_labels": phantom_labels,
            },
        )

    # ── DB write (upsert/delete in one transaction) ───────────────────────────
    applied = 0
    cleared = 0

    async with pool.connection() as conn, conn.transaction():
        for ov in body.overrides:
            if ov.fraction is None:
                # Clear the override for this label (DELETE)
                sql_del = """
DELETE FROM gruvax.segment_overrides
WHERE unit_id = %s AND row = %s AND col = %s AND lower(label) = lower(%s)
"""
                result = await conn.execute(sql_del, (unit_id, row, col, ov.label))
                if result.rowcount and result.rowcount > 0:
                    cleared += 1
            else:
                # Upsert the override fraction (INSERT ON CONFLICT DO UPDATE)
                sql_upsert = """
INSERT INTO gruvax.segment_overrides (unit_id, row, col, label, fraction, updated_at)
VALUES (%s, %s, %s, %s, %s, now())
ON CONFLICT (unit_id, row, col, label)
DO UPDATE SET fraction = EXCLUDED.fraction, updated_at = now()
"""
                await conn.execute(sql_upsert, (unit_id, row, col, ov.label, ov.fraction))
                applied += 1

        response_body = {
            "unit_id": unit_id,
            "row": row,
            "col": col,
            "applied": applied,
            "cleared": cleared,
        }

        if idempotency_key:
            await store_idempotency(conn, idempotency_key, response_body)
        await cleanup_idempotency(conn)

    # ── Invalidate + re-derive SegmentCache AFTER commit (Pitfall A) ─────────
    # Reload overrides from segment_overrides table for this bin (and others)
    # We approximate by keeping existing overrides + merging the new ones.
    cache.invalidate()
    try:
        await cache.load(pool)
        # Build overrides dict from the segment_overrides table for this re-derive
        # (the table is the authoritative source; we re-read for correctness)
        new_overrides: dict[tuple[int, int, int, str], float] = {}
        async with pool.connection() as conn2:
            sql_overrides = """
SELECT unit_id, row, col, label, fraction
FROM gruvax.segment_overrides
"""
            async with conn2.cursor() as cur:
                await cur.execute(sql_overrides)
                override_rows = await cur.fetchall()
        for uid, r, c, lbl, frac in override_rows:
            new_overrides[(int(uid), int(r), int(c), str(lbl))] = float(frac)
        segment_cache.invalidate()
        segment_cache.derive(cache, snapshot, new_overrides)
    finally:
        await bus.publish(
            "boundary_changed",
            {
                "type": "boundary_changed",
                "change_set_id": None,
                "cubes": [{"unit_id": unit_id, "row": row, "col": col}],
            },
        )

    return JSONResponse(status_code=200, content=response_body)


@router.post("/cubes/insert-cut")
async def insert_cut(
    request: Request,
    body: InsertCutBody,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    bus: EventBus = Depends(get_event_bus),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Insert a new cut point after (after_unit_id, after_row, after_col).

    Cascades all subsequent cut points by one position to make room.  The cascade
    is one atomic change-set (source='cut_insert') so it is undoable via history
    revert.

    Validation order:
    1. Phantom check (unless force=True)
    2. Shelf overflow guard (validate_shelf_overflow)
    3. Empty-bin guard (validate_no_empty_bin)

    After commit: invalidates + re-derives SegmentCache, publishes boundary_changed.

    Returns 400 with specific error types on each failure condition.
    HTTP 404 if (after_unit_id, after_row, after_col) is not a known cube.
    """
    from gruvax.api.admin.validation import (
        build_proposed_cuts,
        validate_contiguity,
        validate_no_empty_bin,
        validate_shelf_overflow,
    )
    from gruvax.db.queries import (
        cube_exact_match,
        fetch_current_boundary,
        find_boundary_near_misses,
        write_boundary,
        write_history_row,
    )

    new_first_label = body.new_first_label.strip()
    new_first_catalog = body.new_first_catalog.strip()
    after_uid = body.after_unit_id
    after_row = body.after_row
    after_col = body.after_col

    # ── Phantom check ─────────────────────────────────────────────────────────
    if not body.force:
        first_exists = await cube_exact_match(pool, new_first_label, new_first_catalog)
        if not first_exists:
            near_misses = await find_boundary_near_misses(pool, new_first_label, new_first_catalog)
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "type": "phantom_boundary",
                    "phantom": True,
                    "message": "No match in collection. Did you mean one of these?",
                    "near_misses": near_misses,
                },
            )

    # ── Shelf overflow check (T-05-04-04) ─────────────────────────────────────
    overflow_error = validate_shelf_overflow(
        boundary_cache=cache,
        after_unit_id=after_uid,
        after_row=after_row,
        after_col=after_col,
    )
    if overflow_error is not None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "shelf_overflow", "message": overflow_error},
        )

    # ── Empty-bin check ───────────────────────────────────────────────────────
    no_empty_error = validate_no_empty_bin(
        proposed_first_label=new_first_label,
        proposed_first_catalog=new_first_catalog,
        segment_cache=segment_cache,
        unit_id=after_uid,
        row=after_row,
        col=after_col,
    )
    if no_empty_error is not None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "empty_bin", "message": no_empty_error},
        )

    # ── Load all boundaries sorted to find the cascade target ─────────────────
    # Get the sorted boundary list from the cache
    boundaries = sorted(
        cache.get_boundaries(),
        key=lambda b: (b.unit_id, b.row, b.col),
    )

    # Find the insertion index (the cube AFTER which we insert)
    insert_after_idx: int | None = None
    for i, b in enumerate(boundaries):
        if b.unit_id == after_uid and b.row == after_row and b.col == after_col:
            insert_after_idx = i
            break

    if insert_after_idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "type": "cube_not_found",
                "unit_id": after_uid,
                "row": after_row,
                "col": after_col,
            },
        )

    # ── Build cascade plan ────────────────────────────────────────────────────
    # Cubes after the insertion point shift their cut points "right" by one position.
    # The new cube at (insert_after_idx + 1) gets the new cut point.
    # Each subsequent cube gets the cut point from the cube immediately before it.
    #
    # Concretely:
    #   Old:  [A][B][C][D][E]
    #   Insert new cut N after A:
    #   New:  [A][N][B][C][D]  — E becomes the new trailing empty cube
    #
    # All affected cubes (the new one + every cube shifted) are written in ONE
    # change-set so the whole insert is undoable.
    #
    # The cascade stops at the first empty cube (it absorbs the shift).
    cascade_cubes: list[tuple[int, int, int, str | None, str | None, bool]] = []
    # The new cut: assigned to the cube immediately after the insertion point
    next_cube = boundaries[insert_after_idx + 1]  # overflow check guarantees this exists
    cascade_cubes.append(
        (
            next_cube.unit_id,
            next_cube.row,
            next_cube.col,
            new_first_label,
            new_first_catalog,
            False,
        )
    )

    # Shift each subsequent cube's cut point right by one, reading ORIGINAL values
    # from `boundaries`. The first empty cube absorbs the shift: it receives the
    # last real cut point, and the cascade stops there.
    #
    # The stop condition MUST fire as soon as we FILL the empty cube (nxt.is_empty),
    # NOT one step later when that cube would become the source. Breaking on
    # `curr.is_empty` copied the empty cube's blank value onto the following real
    # bin before stopping — silently dropping that record (e.g. inserting in row 0
    # wiped Columbia at (3,0), the bin just past the empty (2,3) absorber).
    #
    # If next_cube was itself empty it already absorbed the insert above, so there
    # is nothing left to shift.
    if not next_cube.is_empty:
        for i in range(insert_after_idx + 1, len(boundaries) - 1):
            curr = boundaries[i]
            nxt = boundaries[i + 1]
            # nxt receives curr's ORIGINAL (real) cut point — always non-empty.
            cascade_cubes.append(
                (
                    nxt.unit_id,
                    nxt.row,
                    nxt.col,
                    curr.first_label,
                    curr.first_catalog,
                    False,
                )
            )
            if nxt.is_empty:
                # nxt was the first empty cube — it absorbed the shift. Stop so the
                # next (real) bin is left untouched.
                break

    # ── Contiguity check (SEG-05 / D-09 — Direction A) ───────────────────────
    # Enforce label contiguity on the live write path BEFORE the DB transaction
    # so a scatter-inducing insert is never committed.  The cascade_cubes list
    # already encodes the full post-insert cut-point set for the affected cubes;
    # build_proposed_cuts merges it with the remaining (unaffected) live cuts.
    proposed_insert = build_proposed_cuts(cache, cascade=cascade_cubes)
    insert_contiguity_error = validate_contiguity(proposed_insert, segment_cache)
    if insert_contiguity_error is not None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"type": "contiguity_error", "message": insert_contiguity_error},
        )

    change_set_id = str(_uuid.uuid4())
    affected_cubes: list[dict[str, int]] = []

    async with pool.connection() as conn, conn.transaction():
        for uid, r, c, fl, fc, ie in cascade_cubes:
            prev = await fetch_current_boundary(conn, uid, r, c)
            await write_boundary(conn, uid, r, c, fl, fc, ie)
            await write_history_row(
                conn,
                change_set_id,
                uid,
                r,
                c,
                prev,
                fl,
                fc,
                new_is_empty=ie,
                source="cut_insert",
            )
            affected_cubes.append({"unit_id": uid, "row": r, "col": c})

    # ── Invalidate + re-derive SegmentCache AFTER commit (Pitfall A) ─────────
    cache.invalidate()
    try:
        await cache.load(pool)
        # Reload overrides from segment_overrides for accurate re-derive
        new_overrides: dict[tuple[int, int, int, str], float] = {}
        async with pool.connection() as conn2:
            sql_overrides = """
SELECT unit_id, row, col, label, fraction
FROM gruvax.segment_overrides
"""
            async with conn2.cursor() as cur:
                await cur.execute(sql_overrides)
                override_rows = await cur.fetchall()
        for uid_o, r_o, c_o, lbl_o, frac_o in override_rows:
            new_overrides[(int(uid_o), int(r_o), int(c_o), str(lbl_o))] = float(frac_o)
        segment_cache.invalidate()
        segment_cache.derive(cache, snapshot, new_overrides)
    finally:
        await bus.publish(
            "boundary_changed",
            {
                "type": "boundary_changed",
                "change_set_id": change_set_id,
                "cubes": affected_cubes,
            },
        )

    return JSONResponse(
        status_code=200,
        content={
            "change_set_id": change_set_id,
            "inserted_after": {"unit_id": after_uid, "row": after_row, "col": after_col},
            "new_cut": {"first_label": new_first_label, "first_catalog": new_first_catalog},
            "affected": len(affected_cubes),
        },
    )

"""Admin import endpoints for GRUVAX.

Endpoints:
  POST /api/admin/import/boundaries — atomic CSV/YAML boundary import, with optional
    dry_run preview (ADMN-05, D-09, D-11, BAK-01)
  POST /api/admin/import/settings   — validated settings import (BAK-02, D-13, D-14)

Both endpoints accept raw request body bytes. The format is determined from
the Content-Type request header (text/csv, application/x-yaml, text/yaml) or
from the Content-Disposition filename extension (.csv, .yaml, .yml).

Security:
  T-07-YAML-BOMB: yaml.safe_load ONLY — never yaml.load (would allow arbitrary code execution).
  T-07-YAML-BOMB: 100 KB upload size cap enforced before parse (→ 413 on oversize).
    The size cap runs BEFORE dry_run branching — it applies to both paths equally.
  T-07-PARTIAL: ALL edits are validated BEFORE any DB write. A single phantom or contiguity
    error returns 400 with ZERO partial state (Pitfall 7). The DB is unchanged on error.
  T-07-DRYRUN-WRITE: dry_run performs NO INSERT/UPDATE/DELETE, DOES NOT invalidate caches or
    publish on the bus, and DOES NOT mint or consume an Idempotency-Key. The preview shares the
    same parse + validation code path as the commit so it is byte-for-byte equivalent.
  T-07-CSRF: require_admin enforces session + double-submit CSRF for POST endpoints; dry_run is
    still a POST through require_admin (a GET would drop CSRF and allow cross-site reads of diff).
  T-07-IDENTITY-BYPASS: phantom check is SKIPPED only for rows byte-equal to the current
    committed cut point (G3 decision — Pitfall 22). New/changed rows keep full phantom + near-miss;
    contiguity always runs across ALL rows. test_phantom_row_rejected + test_contiguity_violation
    guard against over-broad skip.
  T-07-SETTINGS-KEY: auth.* keys are rejected with 422 before any settings write (D-14).
    Unknown keys (not in _ALLOWED_SETTINGS_KEYS) are also rejected with 422.
    The entire file is rejected on first bad key — no partial settings write.
  T-07-DOUBLE-COMMIT: Idempotency-Key header deduplication (same pattern as cubes/bulk).

All SQL uses ``%s`` placeholders — no f-string interpolation.

dry_run preview contract (POST /api/admin/import/boundaries?dry_run=true):
  - Runs the identical parse + fill + validation pipeline (steps 1-6) with NO DB write.
  - On validation pass → 200 preview body:
      {
        "total_cubes":    <int — count of all addresses in cube_boundaries>,
        "file_cube_count": <int — cubes present in the uploaded file>,
        "diff_preview":   [
          {unit_id, row, col, delta, will_be_empty},
          ...  (only cubes that DIFFER from committed state — empty list for identity re-import)
        ]
      }
  - On validation error → same 400 bodies as the commit path (phantom_boundary /
    contiguity_violation), so the gated COMMIT button logic is unaffected.
  - W5: cubes EQUAL to the current committed state are OMITTED entirely from diff_preview
    (NOT carried as delta 0). An identity re-import therefore has diff_preview == [].
  - Idempotency-Key is IGNORED in dry_run (no change_set_id minted; no key stored).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
import yaml

from gruvax.api.admin.cubes import (
    BoundaryEdit,
    _compute_movement_counts,
    _get_nominal_capacity,
)
from gruvax.api.admin.settings import (
    _ALLOWED_SETTINGS_KEYS,
    _BOOL_KEYS,
    _BRIGHTNESS_KEYS,
    _COLOR_KEYS,
    _HEX_COLOR_RE,
    _INT_KEYS,
)
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
    load_settings_cache,
    store_idempotency,
    write_boundary,
    write_history_row,
)
from gruvax.io.boundary_csv import parse_csv_boundaries
from gruvax.io.boundary_yaml import parse_yaml_boundaries


if TYPE_CHECKING:
    from gruvax.estimator.boundary_cache import BoundaryCache
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-import"])

# Upload size limit: 100 KB. Files larger than this are rejected before parsing.
_MAX_UPLOAD_BYTES = 100_000


def _detect_format(request: Request) -> str | None:
    """Detect the file format from Content-Type or Content-Disposition headers.

    Returns:
        'yaml', 'csv', or None if format cannot be determined.
    """
    content_type = request.headers.get("content-type", "").lower().split(";")[0].strip()
    if "yaml" in content_type or "yml" in content_type:
        return "yaml"
    if "csv" in content_type:
        return "csv"

    # Try Content-Disposition filename extension as fallback
    cd = request.headers.get("content-disposition", "")
    if cd:
        if ".yaml" in cd.lower() or ".yml" in cd.lower():
            return "yaml"
        if ".csv" in cd.lower():
            return "csv"

    return None


def _normalize_label_or_catalog(value: str | None) -> str:
    """Normalize a label or catalog string for committed-state comparison.

    Empty-cube rows store None in the DB; import entries may supply "" or None.
    Treat None and "" as equivalent empty (the write_boundary path stores None
    for empty cubes — Pitfall 22 / G3 identity-skip normalization).
    """
    if value is None:
        return ""
    return value


@router.post("/import/boundaries")
async def import_boundaries(
    request: Request,
    dry_run: bool = Query(default=False, description="Preview import without writing to DB"),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    _admin: dict[str, str] = Depends(require_admin),
    _write_target: tuple[str, Any] = Depends(get_write_target),
) -> JSONResponse:
    """Atomic CSV/YAML boundary import with optional dry_run preview (ADMN-05, D-09, D-11, BAK-01).

    Accepts raw request body. Format detected from Content-Type header or
    Content-Disposition filename. Supports CSV (text/csv) and YAML
    (application/x-yaml, text/yaml).

    dry_run=false (default) — ALL-or-nothing commit:
      1. Read and size-cap the upload.
      2. Detect format from Content-Type / Content-Disposition.
      3. Parse (parse_yaml_boundaries or parse_csv_boundaries).
      4. Map CutPointEntry list → BoundaryEdit list.
      5. FULL ADDRESS SPACE fill (D-09 replace-all): any cube in cube_boundaries but
         absent from the file is added as is_empty=True.
      6. Validate ALL edits BEFORE any write:
         - Build current_index from committed state (one SELECT — no per-row query).
         - Per non-empty edit: SKIP phantom check if the row equals the current committed
           cut point (G3 decision — Pitfall 22: stored catalog-string state is authoritative
           for an unchanged committed row). New/changed rows get full phantom + near-miss.
         - On phantom miss: collect near_misses, return 400 (ZERO writes).
         - After all phantom checks pass: contiguity check via validate_contiguity.
         - On contiguity violation: return 400 (ZERO writes).
      7. Commit atomically: one change_set_id, one DB transaction for all edits
         + segment_overrides upsert + idempotency store.
      8. AFTER transaction commit: cache.invalidate(), cache.load(), segment_cache
         re-derive, bus.publish (Pitfall A — NEVER inside the transaction).
    Returns: JSON ``{change_set_id, applied, source}``

    dry_run=true — NO-write preview (T-07-DRYRUN-WRITE):
      Runs steps 1-6 identically (same parse + fill + validation), then:
      - Returns 400 on any validation error (same bodies as commit path).
      - On validation pass, returns 200 preview:
          {total_cubes, file_cube_count, diff_preview: [{unit_id, row, col, delta, will_be_empty}]}
      - diff_preview contains ONLY cubes that differ from the current committed state
        (W5: equal cubes omitted entirely — identity re-import yields diff_preview==[]).
      - Performs NO INSERT/UPDATE/DELETE. Does NOT invalidate caches or publish on the bus.
      - Does NOT mint or consume an Idempotency-Key (preview has no change_set_id).

    Idempotency-Key header (commit path only): same semantics as cubes/bulk.
    """
    profile_id, bus = _write_target

    # ── 1. Read + size cap (runs before dry_run branching — both paths capped) ─
    content = await request.body()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"type": "file_too_large", "limit_bytes": _MAX_UPLOAD_BYTES},
        )

    # ── 2. Detect format ──────────────────────────────────────────────────────
    fmt = _detect_format(request)
    if fmt is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "type": "unsupported_format",
                "message": (
                    "Cannot determine file format. Set Content-Type to text/csv or "
                    "application/x-yaml, or include filename in Content-Disposition."
                ),
            },
        )

    # ── 3. Parse ──────────────────────────────────────────────────────────────
    source: str
    if fmt == "yaml":
        # parse_yaml_boundaries uses yaml.safe_load internally (T-07-YAML-BOMB)
        try:
            entries = parse_yaml_boundaries(content)
        except (ValueError, yaml.YAMLError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"type": "parse_error", "message": str(exc)},
            ) from exc
        source = "yaml"
    else:  # fmt == "csv"
        try:
            entries = parse_csv_boundaries(content.decode("utf-8", errors="replace"))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"type": "parse_error", "message": str(exc)},
            ) from exc
        source = "csv"

    # ── 4+5. Build edit list + full address space fill (D-09 replace-all) ─────
    # Also fetch the committed cut-point state in the SAME query for current_index
    # (G3 identity-skip: one SELECT — no per-row query). keyed by (unit_id, row, col).
    file_index: dict[tuple[int, int, int], Any] = {(e.unit_id, e.row, e.col): e for e in entries}

    # Fetch full address space + committed cut-point columns in one SELECT.
    # current_index is used for both the G3 phantom skip (step 6) and the
    # dry_run diff-preview (W5: omit unchanged cubes from diff_preview).
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT unit_id, row, col, first_label, first_catalog, is_empty"
            " FROM gruvax.cube_boundaries"
            " ORDER BY unit_id, row, col"
        )
        all_addresses_raw = await cur.fetchall()

    # Build the committed-state index: (unit_id, row, col) → {first_label, first_catalog, is_empty}
    current_index: dict[tuple[int, int, int], dict[str, Any]] = {}
    for addr_row in all_addresses_raw:
        key = (addr_row[0], addr_row[1], addr_row[2])
        current_index[key] = {
            "first_label": addr_row[3],
            "first_catalog": addr_row[4],
            "is_empty": addr_row[5],
        }

    all_edits: list[BoundaryEdit] = []
    for addr_row in all_addresses_raw:
        addr = (addr_row[0], addr_row[1], addr_row[2])
        if addr in file_index:
            entry = file_index[addr]
            all_edits.append(
                BoundaryEdit(
                    unit_id=entry.unit_id,
                    row=entry.row,
                    col=entry.col,
                    first_label=entry.first_label,
                    first_catalog=entry.first_catalog,
                    is_empty=entry.is_empty,
                    force=False,
                )
            )
        else:
            # Absent from file → fill as is_empty (D-09 full replace-all)
            all_edits.append(
                BoundaryEdit(
                    unit_id=addr[0],
                    row=addr[1],
                    col=addr[2],
                    first_label=None,
                    first_catalog=None,
                    is_empty=True,
                    force=False,
                )
            )

    # If no DB addresses exist yet (empty setup), just use file entries directly
    if not all_addresses_raw:
        all_edits = [
            BoundaryEdit(
                unit_id=e.unit_id,
                row=e.row,
                col=e.col,
                first_label=e.first_label,
                first_catalog=e.first_catalog,
                is_empty=e.is_empty,
                force=False,
            )
            for e in entries
        ]

    # ── Idempotency short-circuit (commit path only — dry_run skips entirely) ──
    idempotency_key: str | None = None
    if not dry_run:
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key:
            cached = await check_idempotency(pool, idempotency_key)
            if cached is not None:
                return JSONResponse(content=cached)

    # ── 6. Validate ALL edits BEFORE any write (Pitfall 7, D-11) ─────────────
    #
    # G3 identity-skip (BAK-01, SC4, Pitfall 22):
    # A row that EQUALS the current committed cut point is SKIPPED from phantom
    # re-validation. This guarantees export → re-import = identity even when a cube
    # stores a (label, catalog) pair that no longer matches v_collection (the
    # asymmetry root cause: write/force paths can persist such state, but naive
    # import always re-validated it). New/changed rows still get full phantom +
    # near-miss collection. contiguity always runs across ALL rows.
    #
    # SKIP condition: all of (first_label, first_catalog, is_empty) equal the
    # current committed row (None and "" treated as equal-empty per _normalize_*).
    phantom_errors: list[dict[str, Any]] = []

    for edit in all_edits:
        if edit.is_empty:
            continue  # empty cubes need no phantom check

        # G3: check if this row equals the current committed cut point.
        addr_key = (edit.unit_id, edit.row, edit.col)
        committed = current_index.get(addr_key)
        if committed is not None:
            committed_label = _normalize_label_or_catalog(committed["first_label"])
            committed_catalog = _normalize_label_or_catalog(committed["first_catalog"])
            committed_empty = bool(committed["is_empty"])
            proposed_label = _normalize_label_or_catalog(edit.first_label)
            proposed_catalog = _normalize_label_or_catalog(edit.first_catalog)
            proposed_empty = bool(edit.is_empty)
            if (
                proposed_label == committed_label
                and proposed_catalog == committed_catalog
                and proposed_empty == committed_empty
            ):
                # Row equals the current committed cut point — skip phantom re-validation.
                # (G3 decision, Pitfall 22: stored catalog-string state is authoritative
                # for an unchanged committed row; re-validating it is the bug that broke
                # export → re-import identity.)
                continue

        first_label = edit.first_label or ""
        first_catalog = edit.first_catalog or ""

        # Phantom check (force is always False for imports — no user override)
        first_exists = await cube_exact_match(pool, first_label, first_catalog)
        if not first_exists:
            near_misses = await find_boundary_near_misses(pool, first_label, first_catalog)
            phantom_errors.append(
                {
                    "unit_id": edit.unit_id,
                    "row": edit.row,
                    "col": edit.col,
                    "first_label": first_label,
                    "first_catalog": first_catalog,
                    "near_misses": near_misses,
                }
            )

    if phantom_errors:
        # Return 400 with the first phantom error (all checks run, first reported)
        first_err = phantom_errors[0]
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "type": "phantom_boundary",
                "phantom": True,
                "message": "No match in collection. Did you mean one of these?",
                "near_misses": first_err["near_misses"],
                "unit_id": first_err["unit_id"],
                "row": first_err["row"],
                "col": first_err["col"],
                "errors": phantom_errors,
            },
        )

    # Contiguity check across ALL proposed edits (D-11, SEG-05).
    # Runs regardless of the G3 identity-skip — contiguity is a cross-cube invariant
    # that must hold on the FULL resulting set (not just changed rows).
    updates_as_dicts: list[dict[str, object]] = [
        {
            "unit_id": e.unit_id,
            "row": e.row,
            "col": e.col,
            "first_label": e.first_label,
            "first_catalog": e.first_catalog,
            "is_empty": e.is_empty,
        }
        for e in all_edits
    ]
    contiguity_error = validate_contiguity(updates_as_dicts, segment_cache)
    if contiguity_error is not None:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "type": "contiguity_violation",
                "message": contiguity_error,
            },
        )

    # ── dry_run: return preview, NO DB write (T-07-DRYRUN-WRITE) ─────────────
    if dry_run:
        nominal_capacity = 95  # default; no request.app.state access needed here
        try:
            nominal_capacity = _get_nominal_capacity(request)
        except Exception:  # nosec B110 - best-effort lookup; default is fine for preview delta
            # Log at debug — this is a best-effort lookup with a sane default.
            logger.debug(
                "import: nominal_capacity lookup failed; using default 95",
                exc_info=True,
            )

        total_cubes = len(all_addresses_raw)
        file_cube_count = len(file_index)

        # W5: include ONLY cubes that differ from the current committed state.
        # Cubes equal to committed state are OMITTED entirely (not delta 0).
        # An identity re-import yields diff_preview == [].
        diff_preview: list[dict[str, Any]] = []
        for edit in all_edits:
            addr_key = (edit.unit_id, edit.row, edit.col)
            committed = current_index.get(addr_key)
            if committed is not None:
                committed_label = _normalize_label_or_catalog(committed["first_label"])
                committed_catalog = _normalize_label_or_catalog(committed["first_catalog"])
                committed_empty = bool(committed["is_empty"])
                proposed_label = _normalize_label_or_catalog(edit.first_label)
                proposed_catalog = _normalize_label_or_catalog(edit.first_catalog)
                proposed_empty = bool(edit.is_empty)
                if (
                    proposed_label == committed_label
                    and proposed_catalog == committed_catalog
                    and proposed_empty == committed_empty
                ):
                    # Equal to committed state — omit from diff_preview (W5)
                    continue

            # Cube differs (or is new) — compute approximate delta
            movement = _compute_movement_counts(edit, segment_cache, nominal_capacity)
            delta = movement[0]["delta"] if movement else 0
            will_be_empty = bool(edit.is_empty) and (
                committed is None or not bool(committed.get("is_empty"))
            )
            diff_preview.append(
                {
                    "unit_id": edit.unit_id,
                    "row": edit.row,
                    "col": edit.col,
                    "delta": delta,
                    "will_be_empty": will_be_empty,
                }
            )

        logger.info(
            "Admin boundaries dry_run preview: total_cubes=%d, file_cube_count=%d, diff=%d",
            total_cubes,
            file_cube_count,
            len(diff_preview),
        )
        return JSONResponse(
            content={
                "total_cubes": total_cubes,
                "file_cube_count": file_cube_count,
                "diff_preview": diff_preview,
            }
        )

    # ── 7. Atomic DB transaction: write all boundaries + history + overrides ──
    change_set_id = str(_uuid.uuid4())
    response_body: dict[str, Any] = {
        "change_set_id": change_set_id,
        "applied": len(all_edits),
        "source": source,
    }

    async with pool.connection() as conn, conn.transaction():
        for edit in all_edits:
            # Capture previous boundary for history audit — scoped to resolved profile.
            prev = await fetch_current_boundary(
                conn, edit.unit_id, edit.row, edit.col, profile_id=profile_id
            )

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
            # D-11: 0-row write inside transaction aborts the whole change-set.
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
                source=source,  # 'csv' or 'yaml' (D-04, T-07-01)
                profile_id=profile_id,
            )

        # Upsert segment_overrides for entries with overrides (Pitfall 4 — inside txn).
        # Admin import operates on the default profile (P1-compat path; composite PK).
        _IMPORT_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
        for entry in entries:
            if entry.overrides and not entry.is_empty:
                for label, fraction in entry.overrides.items():
                    await conn.execute(
                        "INSERT INTO gruvax.segment_overrides"
                        " (profile_id, unit_id, row, col, label, fraction, updated_at)"
                        " VALUES (%s::uuid, %s, %s, %s, %s, %s, now())"
                        " ON CONFLICT (profile_id, unit_id, row, col, label)"
                        " DO UPDATE SET fraction = EXCLUDED.fraction, updated_at = now()",
                        (
                            _IMPORT_DEFAULT_PROFILE_UUID,
                            entry.unit_id,
                            entry.row,
                            entry.col,
                            label,
                            fraction,
                        ),
                    )

        # Idempotency: store response + prune old keys inside the same transaction
        if idempotency_key:
            await store_idempotency(conn, idempotency_key, response_body)
        await cleanup_idempotency(conn)

    # ── 8. Cache invalidate AFTER transaction commit (Pitfall A) ─────────────
    cache.invalidate()
    try:
        await cache.load(pool)
        # Collect overrides for segment_cache re-derive
        overrides: dict[tuple[int, int, int, str], float] = {}
        for edit in all_edits:
            seg_bin = segment_cache.get_bin(edit.unit_id, edit.row, edit.col)
            if seg_bin is not None:
                for seg in seg_bin.segments:
                    if seg.is_override:
                        override_key: tuple[int, int, int, str] = (
                            edit.unit_id,
                            edit.row,
                            edit.col,
                            str(seg.label),
                        )
                        overrides[override_key] = seg.applied_fraction
        # Also include any overrides from the imported file entries
        for entry in entries:
            if entry.overrides and not entry.is_empty:
                for label, fraction in entry.overrides.items():
                    overrides[(entry.unit_id, entry.row, entry.col, str(label))] = fraction
        segment_cache.invalidate()
        segment_cache.derive(cache, snapshot, overrides)
    finally:
        await bus.publish(
            "boundary_changed",
            {
                "cube_ids": [{"unit": e.unit_id, "row": e.row, "col": e.col} for e in all_edits],
                "change_set_id": change_set_id,
            },
        )

    logger.info(
        "Admin boundaries imported: change_set_id=%s, applied=%d, source=%s",
        change_set_id,
        len(all_edits),
        source,
    )
    return JSONResponse(content=response_body)


@router.post("/import/settings")
async def import_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> dict[str, Any]:
    """Validated settings import (BAK-02, D-13, D-14).

    Accepts raw request body bytes (YAML format).

    Protocol (whole-file-reject, never partial write):
      1. Read and size-cap the upload.
      2. Parse YAML with yaml.safe_load (T-07-YAML-BOMB).
      3. Flatten nested YAML keys (e.g. led_color.position → "led_color.position").
      4. For each key:
         - If key starts with "auth." → 422 auth_key_rejected (D-14, T-07-SETTINGS-KEY).
         - If key not in _ALLOWED_SETTINGS_KEYS → 422 unknown_key (T-07-SETTINGS-KEY).
         (Reject on first bad key — never write partial settings.)
      5. Validate value types (colors, brightness values).
      6. Apply via the existing validated write path (mirror update_settings).

    Settings import is SEPARATE from boundaries — no boundary_history / change-set
    involvement (D-13). Settings values are written to gruvax.settings only.

    Returns:
        JSON ``{updated: [<db-key>, ...]}``
    """
    # ── 1. Read + size cap ────────────────────────────────────────────────────
    content = await request.body()
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"type": "file_too_large", "limit_bytes": _MAX_UPLOAD_BYTES},
        )

    # ── 2. Parse YAML (safe_load only — T-07-YAML-BOMB) ──────────────────────
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"type": "parse_error", "message": str(exc)},
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"type": "parse_error", "message": "Settings YAML must be a mapping"},
        )

    # ── 3. Flatten nested YAML to dotted keys ─────────────────────────────────
    flat_keys: dict[str, Any] = _flatten_yaml(data)

    # ── 4. Validate all keys BEFORE any write (whole-file reject) ─────────────
    for dotted_key in flat_keys:
        if dotted_key == "version":
            continue  # skip the top-level version field if present
        if dotted_key.startswith("auth."):
            # D-14 hard exclusion: auth.* keys are never accepted via import
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "type": "auth_key_rejected",
                    "key": dotted_key,
                    "message": (
                        "Keys under 'auth.' are not permitted in settings imports (D-14)."
                        " The admin PIN can only be changed via the change-PIN endpoint."
                    ),
                },
            )
        if dotted_key not in _ALLOWED_SETTINGS_KEYS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "type": "unknown_key",
                    "key": dotted_key,
                    "message": f"Key '{dotted_key}' is not an allowed settings key.",
                },
            )

    # ── 5. Validate value types (mirror settings.py validation, fail-fast) ─────
    for dotted_key, value in flat_keys.items():
        if dotted_key == "version":
            continue
        if dotted_key in _COLOR_KEYS:
            if not isinstance(value, str) or not _HEX_COLOR_RE.match(value):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_hex_color",
                        "field": dotted_key,
                        "message": (
                            f"Color value must be a valid #RRGGBB hex string. Got: {value!r}"
                        ),
                    },
                )
        elif dotted_key in _BRIGHTNESS_KEYS:
            try:
                int_value = int(value)
            except TypeError, ValueError:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_brightness",
                        "field": dotted_key,
                        "message": (f"Brightness must be an integer in [0, 255]. Got: {value!r}"),
                    },
                ) from None
            if not 0 <= int_value <= 255:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_brightness",
                        "field": dotted_key,
                        "message": f"Brightness must be in [0, 255]. Got: {int_value}",
                    },
                )

    # ── 6. Write settings via validated path (same as update_settings) ────────
    # Global settings live under the default profile UUID (composite PK = (profile_id, key)).
    _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
    updated: list[str] = []
    # Explicit transaction so the whole-file-reject guarantee is structural, not
    # reliant on implicit rollback-on-release (matches the boundaries import path).
    async with pool.connection() as conn, conn.transaction():
        for dotted_key, value in flat_keys.items():
            if dotted_key == "version":
                continue

            if dotted_key in _COLOR_KEYS:
                json_value = f'"{value}"'
            elif dotted_key in _INT_KEYS:
                try:
                    int_val = int(value)
                except TypeError, ValueError:
                    logger.warning("Skipping invalid integer for %s", dotted_key)
                    continue
                json_value = str(int_val)
            elif dotted_key in _BOOL_KEYS:
                bool_val = bool(value)
                json_value = "true" if bool_val else "false"
            else:
                json_value = json.dumps(value)

            await conn.execute(
                "UPDATE gruvax.settings SET value = %s::jsonb, updated_at = now()"
                " WHERE profile_id = %s::uuid AND key = %s",
                (json_value, _DEFAULT_PROFILE_UUID, dotted_key),
            )
            updated.append(dotted_key)

    logger.info("Admin settings imported: %s", updated)

    # D-15 / WR-01: refresh in-process settings cache (same as update_settings)
    try:
        fresh = await load_settings_cache(pool, profile_id=_DEFAULT_PROFILE_UUID)
        existing = getattr(request.app.state, "settings_cache", None)
        if isinstance(existing, dict):
            existing.clear()
            existing.update(fresh)
        else:
            request.app.state.settings_cache = fresh
    except Exception as exc:
        logger.warning("Settings cache refresh failed after POST /import/settings: %s", exc)

    return {"updated": updated}


# ── Private helpers ───────────────────────────────────────────────────────────


def _flatten_yaml(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    """Flatten a nested YAML dict to dotted keys.

    Example:
      {"led_color": {"position": "#FFD700"}} → {"led_color.position": "#FFD700"}
      {"version": "1", "cube": {"nominal_capacity": 95}} →
        {"version": "1", "cube.nominal_capacity": 95}

    Only two levels of nesting are expected for the GRUVAX settings schema.
    Deeper nesting is flattened recursively.

    Args:
        data:   Dict (possibly nested) to flatten.
        prefix: Key prefix accumulated during recursion.

    Returns:
        Dict with dotted key paths as keys.
    """
    result: dict[str, Any] = {}
    for k, v in data.items():
        full_key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            result.update(_flatten_yaml(v, prefix=full_key))
        else:
            result[full_key] = v
    return result

"""Admin import endpoints for GRUVAX.

Endpoints:
  POST /api/admin/import/boundaries — atomic CSV/YAML boundary import (ADMN-05, D-09, D-11)
  POST /api/admin/import/settings   — validated settings import (BAK-02, D-13, D-14)

Both endpoints accept raw request body bytes. The format is determined from
the Content-Type request header (text/csv, application/x-yaml, text/yaml) or
from the Content-Disposition filename extension (.csv, .yaml, .yml).

Security:
  T-07-YAML-BOMB: yaml.safe_load ONLY — never yaml.load (would allow arbitrary code execution).
  T-07-YAML-BOMB: 100 KB upload size cap enforced before parse (→ 413 on oversize).
  T-07-PARTIAL: ALL edits are validated BEFORE any DB write. A single phantom or contiguity
    error returns 400 with ZERO partial state (Pitfall 7). The DB is unchanged on error.
  T-07-SETTINGS-KEY: auth.* keys are rejected with 422 before any settings write (D-14).
    Unknown keys (not in _ALLOWED_SETTINGS_KEYS) are also rejected with 422.
    The entire file is rejected on first bad key — no partial settings write.
  T-07-CSRF: require_admin enforces session + double-submit CSRF for POST endpoints.
  T-07-DOUBLE-COMMIT: Idempotency-Key header deduplication (same pattern as cubes/bulk).

All SQL uses ``%s`` placeholders — no f-string interpolation.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

import yaml

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

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


@router.post("/import/boundaries")
async def import_boundaries(
    request: Request,
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    segment_cache: SegmentCache = Depends(get_segment_cache),
    snapshot: CollectionSnapshot = Depends(get_collection_snapshot),
    bus: EventBus = Depends(get_event_bus),
    _admin: dict[str, str] = Depends(require_admin),
) -> JSONResponse:
    """Atomic CSV/YAML boundary import (ADMN-05, D-09, D-11, Pitfall 7).

    Accepts raw request body. Format detected from Content-Type header or
    Content-Disposition filename. Supports CSV (text/csv) and YAML
    (application/x-yaml, text/yaml).

    Protocol (ALL-or-nothing, zero partial state):
      1. Read and size-cap the upload.
      2. Detect format from Content-Type / Content-Disposition.
      3. Parse (parse_yaml_boundaries or parse_csv_boundaries).
      4. Map CutPointEntry list → BoundaryEdit list.
      5. FULL ADDRESS SPACE fill (D-09 replace-all): any cube in cube_boundaries but
         absent from the file is added as is_empty=True.
      6. Validate ALL edits BEFORE any write:
         - Per non-empty, non-force edit: phantom check via cube_exact_match.
         - On phantom miss: collect near_misses, return 400 (ZERO writes).
         - After all phantom checks pass: contiguity check via validate_contiguity.
         - On contiguity violation: return 400 (ZERO writes).
      7. Commit atomically: one change_set_id, one DB transaction for all edits
         + segment_overrides upsert + idempotency store.
      8. AFTER transaction commit: cache.invalidate(), cache.load(), segment_cache
         re-derive, bus.publish (Pitfall A — NEVER inside the transaction).

    Idempotency-Key header: same semantics as cubes/bulk (replay returns cached response).

    Returns:
        JSON ``{change_set_id, applied, source}``
    """
    from gruvax.api.admin.validation import validate_contiguity
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
    from gruvax.io.boundary_csv import parse_csv_boundaries
    from gruvax.io.boundary_yaml import parse_yaml_boundaries

    # ── 1. Read + size cap ────────────────────────────────────────────────────
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

    # ── 4+5. Build edit list + full address space fill (D-09 replace-all) ────
    file_index: dict[tuple[int, int, int], Any] = {
        (e.unit_id, e.row, e.col): e for e in entries
    }

    # Get the full address space from DB (replace-all requires all cubes to be written)
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT unit_id, row, col FROM gruvax.cube_boundaries ORDER BY unit_id, row, col"
        )
        all_addresses = await cur.fetchall()

    from gruvax.api.admin.cubes import BoundaryEdit

    all_edits: list[BoundaryEdit] = []
    for addr_row in all_addresses:
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
    if not all_addresses:
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

    # ── Idempotency short-circuit ─────────────────────────────────────────────
    idempotency_key = request.headers.get("Idempotency-Key")
    if idempotency_key:
        cached = await check_idempotency(pool, idempotency_key)
        if cached is not None:
            return JSONResponse(content=cached)

    # ── 6. Validate ALL edits BEFORE any write (Pitfall 7, D-11) ─────────────
    phantom_errors: list[dict[str, Any]] = []

    for edit in all_edits:
        if edit.is_empty:
            continue  # empty cubes need no phantom check
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

    # Contiguity check across ALL proposed edits (D-11, SEG-05)
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

    # ── 7. Atomic DB transaction: write all boundaries + history + overrides ──
    change_set_id = str(_uuid.uuid4())
    response_body: dict[str, Any] = {
        "change_set_id": change_set_id,
        "applied": len(all_edits),
        "source": source,
    }

    async with pool.connection() as conn, conn.transaction():
        for edit in all_edits:
            # Capture previous boundary for history audit
            prev = await fetch_current_boundary(conn, edit.unit_id, edit.row, edit.col)

            new_first_label = edit.first_label if not edit.is_empty else None
            new_first_catalog = edit.first_catalog if not edit.is_empty else None

            await write_boundary(
                conn,
                edit.unit_id,
                edit.row,
                edit.col,
                new_first_label,
                new_first_catalog,
                edit.is_empty,
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
            )

        # Upsert segment_overrides for entries with overrides (Pitfall 4 — inside txn)
        for entry in entries:
            if entry.overrides and not entry.is_empty:
                for label, fraction in entry.overrides.items():
                    await conn.execute(
                        "INSERT INTO gruvax.segment_overrides"
                        " (unit_id, row, col, label, fraction, updated_at)"
                        " VALUES (%s, %s, %s, %s, %s, now())"
                        " ON CONFLICT (unit_id, row, col, label)"
                        " DO UPDATE SET fraction = EXCLUDED.fraction, updated_at = now()",
                        (entry.unit_id, entry.row, entry.col, label, fraction),
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
                        key = (edit.unit_id, edit.row, edit.col, seg.label)
                        overrides[key] = seg.applied_fraction
        # Also include any overrides from the imported file entries
        for entry in entries:
            if entry.overrides and not entry.is_empty:
                for label, fraction in entry.overrides.items():
                    overrides[(entry.unit_id, entry.row, entry.col, label)] = fraction
        segment_cache.invalidate()
        segment_cache.derive(cache, snapshot, overrides)
    finally:
        await bus.publish(
            "boundary_changed",
            {
                "cube_ids": [
                    {"unit": e.unit_id, "row": e.row, "col": e.col} for e in all_edits
                ],
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
    from gruvax.api.admin.settings import (
        _ALLOWED_SETTINGS_KEYS,
        _BOOL_KEYS,
        _BRIGHTNESS_KEYS,
        _COLOR_KEYS,
        _HEX_COLOR_RE,
        _INT_KEYS,
    )

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
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "type": "invalid_brightness",
                        "field": dotted_key,
                        "message": (
                            f"Brightness must be an integer in [0, 255]. Got: {value!r}"
                        ),
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
    import json as _json

    updated: list[str] = []
    async with pool.connection() as conn:
        for dotted_key, value in flat_keys.items():
            if dotted_key == "version":
                continue

            if dotted_key in _COLOR_KEYS:
                json_value = f'"{value}"'
            elif dotted_key in _INT_KEYS:
                try:
                    int_val = int(value)
                except (TypeError, ValueError):
                    logger.warning("Skipping invalid integer for %s", dotted_key)
                    continue
                json_value = str(int_val)
            elif dotted_key in _BOOL_KEYS:
                bool_val = bool(value)
                json_value = "true" if bool_val else "false"
            else:
                json_value = _json.dumps(value)

            await conn.execute(
                "UPDATE gruvax.settings"
                " SET value = %s::jsonb, updated_at = now()"
                " WHERE key = %s",
                (json_value, dotted_key),
            )
            updated.append(dotted_key)

        await conn.commit()

    logger.info("Admin settings imported: %s", updated)

    # D-15 / WR-01: refresh in-process settings cache (same as update_settings)
    try:
        from gruvax.db.queries import load_settings_cache

        fresh = await load_settings_cache(pool)
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

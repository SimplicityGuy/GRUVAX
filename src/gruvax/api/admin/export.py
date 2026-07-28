"""Admin export endpoints for GRUVAX.

Endpoints:
  GET /api/admin/export/boundaries.yaml — export full boundary + overrides as YAML (BAK-01)
  GET /api/admin/export/settings.yaml   — export allowed settings as YAML (BAK-02, D-14)

Security (D-14, T-07-PIN-LEAK):
  Settings export uses an ALLOWLIST query: SELECT WHERE key = ANY(_ALLOWED_SETTINGS_KEYS).
  auth.pin_hash is intentionally absent from _ALLOWED_SETTINGS_KEYS and is therefore
  NEVER selected, never serialized, and NEVER present in a downloaded settings.yaml.
  This is an allowlist (not a denylist) — adding new keys requires explicit inclusion
  in _ALLOWED_SETTINGS_KEYS.

Both endpoints require an active admin session (require_admin). Export GETs are
read-only — no CSRF check is needed beyond session validation.

All SQL uses ``%s`` placeholders — no f-string interpolation (T-07-SC).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
import yaml

from gruvax.api.admin.settings import _ALLOWED_SETTINGS_KEYS
from gruvax.api.deps import (
    boundary_cache_for_profile,
    get_pool,
    get_read_profile_id,
    require_admin,
)
from gruvax.io.boundary_yaml import CutPointEntry, serialize_boundaries_yaml


logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-export"])


@router.get("/export/boundaries.yaml")
async def export_boundaries(
    request: Request,
    pool: Any = Depends(get_pool),
    profile_id: str = Depends(get_read_profile_id),
    _admin: dict[str, str] = Depends(require_admin),
) -> Response:
    """Export the bound profile's live boundary set (+ per-label overrides) as YAML (BAK-01).

    The YAML document conforms to the ``version: "1"`` boundary schema understood
    by ``parse_yaml_boundaries`` (SC4 round-trip identity). Each non-empty cube
    includes ``first_label``, ``first_catalog``, and (when present) ``overrides``.

    Empty cubes serialize as ``{is_empty: true}`` with no first_* fields.

    gruvax-0ge — this export used to mix profiles two different ways:
      - the segment_overrides SELECT had no WHERE profile_id (the last unscoped
        segment_overrides query in the codebase) and overrides_index was keyed on
        coordinates alone, so with two profiles overriding the same cube whichever
        row Postgres returned LAST silently won;
      - the cut points came from Depends(get_boundary_cache) = the DEFAULT
        profile's cache, so an admin bound to B downloaded A's cut points.
    Re-importing such a file (import IS correctly scoped) wrote a foreign
    profile's boundaries into the importing profile, breaking BAK-01's
    export -> re-import identity guarantee across profiles. The settings export one
    function down always scoped explicitly; :63 was an oversight, not a design
    choice.

    Returns:
        YAML file download with Content-Disposition attachment.
    """
    # Load THIS profile's per-label segment overrides, keyed by
    # (unit_id, row, col) → {label: fraction}.
    # gruvax-rn7l.3: export label_display (original case), NEVER the casefolded
    # `label` storage key — a round-tripped export/import must not silently
    # relabel every override to lowercase.
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT unit_id, row, col, label_display, fraction"
            " FROM gruvax.segment_overrides"
            " WHERE profile_id = %s::uuid"
            " ORDER BY unit_id, row, col, label",
            (profile_id,),
        )
        override_rows = await cur.fetchall()

    overrides_index: dict[tuple[int, int, int], dict[str, float]] = {}
    for uid, r, c, lbl, frac in override_rows:
        overrides_index.setdefault((uid, r, c), {})[str(lbl)] = float(frac)

    # Build CutPointEntry list from the CALLER's live boundary cache (gruvax-0ge)
    cache = boundary_cache_for_profile(request, profile_id)
    entries: list[CutPointEntry] = []
    for b in sorted(cache.get_boundaries(), key=lambda b: (b.unit_id, b.row, b.col)):
        ovr = overrides_index.get((b.unit_id, b.row, b.col), {})
        entries.append(
            CutPointEntry(
                unit_id=b.unit_id,
                row=b.row,
                col=b.col,
                first_label=b.first_label,
                first_catalog=b.first_catalog,
                is_empty=b.is_empty,
                overrides=ovr,
            )
        )

    payload = serialize_boundaries_yaml(entries)
    logger.info("Admin boundaries export: %d cubes", len(entries))

    return Response(
        content=payload,
        media_type="application/x-yaml",
        headers={"Content-Disposition": 'attachment; filename="boundaries.yaml"'},
    )


@router.get("/export/settings.yaml")
async def export_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> Response:
    """Export allowed settings as a YAML file (BAK-02, D-14).

    Reads ONLY keys in _ALLOWED_SETTINGS_KEYS from the DB.
    auth.pin_hash is absent from _ALLOWED_SETTINGS_KEYS and is therefore
    provably excluded from this export (T-07-PIN-LEAK, D-14 hard exclusion).

    Returns a nested YAML dict (e.g. led_color.position → led_color: {position: ...})
    under a top-level ``version: "1"`` key.

    Returns:
        YAML file download with Content-Disposition attachment.
    """
    # D-14 hard exclusion: the WHERE clause IS the guard — auth.pin_hash is never
    # in _ALLOWED_SETTINGS_KEYS, so it is never SELECTed and never serialized.
    # Global settings live under the default profile UUID (composite PK = (profile_id, key)).
    _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT key, value FROM gruvax.settings WHERE profile_id = %s::uuid AND key = ANY(%s)",
            (_DEFAULT_PROFILE_UUID, list(_ALLOWED_SETTINGS_KEYS)),
        )
        rows = await cur.fetchall()

    # Build a nested dict from flat dotted keys:
    # "led_color.position" → {"led_color": {"position": <value>}}
    nested: dict[str, Any] = {}
    for key, raw_value in rows:
        key_str = str(key)
        # Decode stored JSON values (colors are stored as '"#RRGGBB"', integers as "255", etc.)
        value = _decode_settings_value(raw_value)
        parts = key_str.split(".", 1)
        if len(parts) == 2:
            section, subkey = parts
            nested.setdefault(section, {})[subkey] = value
        else:
            nested[key_str] = value

    export_doc: dict[str, Any] = {"version": "1", **nested}

    payload = yaml.dump(
        export_doc,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )

    logger.info("Admin settings export: %d keys", len(rows))

    return Response(
        content=payload,
        media_type="application/x-yaml",
        headers={"Content-Disposition": 'attachment; filename="settings.yaml"'},
    )


def _decode_settings_value(raw: Any) -> Any:
    """Decode a stored settings value from its JSON-string DB representation.

    Settings are stored as JSON in the ``gruvax.settings.value`` column:
    - Color strings: ``'"#FFD700"'`` → ``"#FFD700"``
    - Integers: ``'255'`` → ``255``
    - Booleans: ``'true'`` / ``'false'`` → ``True`` / ``False``
    - Anything else: returned as-is.

    Args:
        raw: Raw value from the ``value`` column (may be str or already decoded).

    Returns:
        Python value decoded from the JSON-string representation.
    """
    if isinstance(raw, str):
        stripped = raw.strip()
        # JSON string: starts and ends with double quotes → strip them
        if stripped.startswith('"') and stripped.endswith('"'):
            return stripped[1:-1]
        # JSON boolean
        if stripped == "true":
            return True
        if stripped == "false":
            return False
        # JSON integer
        try:
            return int(stripped)
        except ValueError, TypeError:
            pass
        # JSON float
        try:
            return float(stripped)
        except ValueError, TypeError:
            pass
    return raw

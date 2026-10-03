"""YAML parse and serialize for GRUVAX boundary cut-point data.

Security: This module uses yaml.safe_load ONLY. Never use yaml.load without
a Loader argument — it can construct arbitrary Python objects from untrusted
input (T-07-YAML-BOMB / YAML-bomb / RCE vector). safe_load restricts
deserialization to standard YAML types only.

Functions:
  parse_yaml_boundaries(content)    — parse YAML bytes/str → list[CutPointEntry]
  serialize_boundaries_yaml(entries) — serialize list[CutPointEntry] → YAML str

The round-trip identity property (SC4) holds: for any list of CutPointEntry
values, parse_yaml_boundaries(serialize_boundaries_yaml(entries)) produces
the same entry set (modulo sort order).

All SQL interaction is outside this module — pure transform only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

import yaml


@dataclass
class CutPointEntry:
    """Internal model for a single cube boundary cut-point.

    Fields:
      unit_id       — IKEA Kallax unit number (1-based)
      row           — row index within the unit (0-based)
      col           — column index within the unit (0-based)
      first_label   — record label at the start of this cube (None when is_empty)
      first_catalog — catalog number at the start of this cube (None when is_empty)
      is_empty      — True when the cube holds no records
      overrides     — per-label segment fraction overrides; label → fraction in (0.0, 1.0]
                      Empty dict when no overrides are set.
                      DB CHECK enforces 0 < fraction <= 1.0 at write time.

    Note: overrides are present in YAML but omitted from flat CSV (D-10, D-12).
    """

    unit_id: int
    row: int
    col: int
    first_label: str | None
    first_catalog: str | None
    is_empty: bool
    overrides: dict[str, float] = field(default_factory=dict)


def parse_yaml_boundaries(content: bytes | str) -> list[CutPointEntry]:
    """Parse a YAML boundary document into a list of CutPointEntry values.

    Uses yaml.safe_load only — never yaml.load (security requirement T-07-YAML-BOMB).

    Args:
        content: Raw YAML bytes or string (from file upload or export roundtrip).

    Returns:
        List of CutPointEntry instances.

    Raises:
        ValueError: If the document is missing a valid ``version: "1"`` field.
        yaml.YAMLError: If the content is not valid YAML (propagated from safe_load).
    """
    data = yaml.safe_load(content)
    if not isinstance(data, dict) or data.get("version") != "1":
        raise ValueError(
            "Missing or unsupported version field — "
            "YAML boundary documents must contain version: '1'"
        )

    cubes = data.get("cubes", [])
    if not isinstance(cubes, list):
        raise ValueError("cubes must be a list")
    return [_parse_cube(cube, index) for index, cube in enumerate(cubes, start=1)]


def _address_value(cube: dict[str, Any], key: str, context: str) -> int:
    value = cube.get(key)
    if value is None:
        raise ValueError(f"{context}.{key} is required")
    try:
        if isinstance(value, bool) or (isinstance(value, float) and not value.is_integer()):
            raise ValueError("not an integer")
        parsed = int(value)
    except TypeError, ValueError, OverflowError:
        raise ValueError(f"{context}.{key} must be an integer") from None
    minimum = 1 if key == "unit_id" else 0
    if parsed < minimum:
        raise ValueError(f"{context}.{key} must be at least {minimum}")
    return parsed


def _optional_text(cube: dict[str, Any], key: str, context: str) -> str | None:
    value = cube.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{context}.{key} must be text or null")
    return value


def _parse_overrides(value: Any, context: str) -> dict[str, float]:
    if not isinstance(value, dict):
        raise ValueError(f"{context}.overrides must be a mapping")
    overrides = {}
    for label, raw in value.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"{context}.overrides labels must be nonempty text")
        try:
            if isinstance(raw, bool):
                raise ValueError("not a fraction")
            fraction = float(raw)
        except TypeError, ValueError, OverflowError:
            raise ValueError(f"{context}.overrides[{label!r}] must be a fraction") from None
        if not math.isfinite(fraction) or not 0 < fraction <= 1:
            raise ValueError(f"{context}.overrides[{label!r}] must be in (0, 1]")
        overrides[label] = fraction
    return overrides


def _parse_cube(cube: Any, index: int) -> CutPointEntry:
    context = f"cubes[{index}]"
    if not isinstance(cube, dict):
        raise ValueError(f"{context} must be a mapping")
    is_empty = cube.get("is_empty", False)
    if not isinstance(is_empty, bool):
        raise ValueError(f"{context}.is_empty must be a boolean")
    return CutPointEntry(
        unit_id=_address_value(cube, "unit_id", context),
        row=_address_value(cube, "row", context),
        col=_address_value(cube, "col", context),
        first_label=_optional_text(cube, "first_label", context),
        first_catalog=_optional_text(cube, "first_catalog", context),
        is_empty=is_empty,
        overrides=_parse_overrides(cube.get("overrides", {}), context),
    )


def serialize_boundaries_yaml(entries: list[CutPointEntry]) -> str:
    """Serialize a list of CutPointEntry values to a YAML string.

    Output is deterministic and round-trip stable (SC4):
      - Cubes are sorted by (unit_id, row, col)
      - Override keys within each cube are sorted alphabetically
      - yaml.dump is called with sort_keys=True, default_flow_style=False,
        allow_unicode=True for reproducible output

    Empty cubes (is_empty=True) omit first_label, first_catalog, and overrides
    from the serialized document.

    Args:
        entries: List of CutPointEntry instances.

    Returns:
        YAML string with version: "1" header.
    """
    cubes = []
    for e in sorted(entries, key=lambda x: (x.unit_id, x.row, x.col)):
        cube: dict[str, object] = {
            "unit_id": e.unit_id,
            "row": e.row,
            "col": e.col,
            "is_empty": e.is_empty,
        }
        if not e.is_empty:
            cube["first_label"] = e.first_label
            cube["first_catalog"] = e.first_catalog
            if e.overrides:
                cube["overrides"] = dict(sorted(e.overrides.items()))
        cubes.append(cube)

    return yaml.dump(
        {"version": "1", "cubes": cubes},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )

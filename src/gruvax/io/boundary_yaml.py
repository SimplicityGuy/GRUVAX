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

    entries: list[CutPointEntry] = []
    for cube in data.get("cubes", []):
        overrides: dict[str, float] = {
            str(k): float(v)
            for k, v in cube.get("overrides", {}).items()
        }
        entries.append(
            CutPointEntry(
                unit_id=int(cube["unit_id"]),
                row=int(cube["row"]),
                col=int(cube["col"]),
                first_label=cube.get("first_label"),
                first_catalog=cube.get("first_catalog"),
                is_empty=bool(cube.get("is_empty", False)),
                overrides=overrides,
            )
        )
    return entries


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

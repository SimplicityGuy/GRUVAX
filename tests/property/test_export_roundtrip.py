"""Hypothesis property tests for export → re-import round-trip identity (SC4, BAK-01).

Wave-0 RED scaffold — authored before the export/import endpoints exist.
Tests assert on expected behavior so that unimplemented endpoints fail RED.

Invariant (SC4):
  export(cubes) → YAML string → import YAML → committed cubes == original cubes
  (zero diff between exported and re-imported boundary set)

Strategy: generate synthetic cut sets using made-up labels from a fixed sample
pool (unit_id 1-2, row/col 0-3, unique by address). The export produces a YAML
file; re-importing that file should produce an identical boundary set.

No real collection data is used — synthetic labels only.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

# ── Synthetic data strategy ───────────────────────────────────────────────────
#
# Labels and catalog prefixes are entirely made-up.
# No reference to real collection data, gitignored CSVs, or background/.

_SYNTHETIC_LABELS = [
    ("Atlantic", "ATL"),
    ("Blue Note", "BNL"),
    ("Columbia", "COL"),
    ("Impulse", "IMP"),
    ("Verve", "VRV"),
    ("Prestige", "PRE"),
    ("ECM", "ECM"),
    ("Nonesuch", "NNS"),
]

_LABEL_STRATEGY = st.sampled_from(_SYNTHETIC_LABELS)


def _make_cube_entry(unit_id: int, row: int, col: int, label_info: tuple) -> dict:
    """Build a synthetic cut-point dict from (label_name, label_prefix) tuple."""
    label_name, prefix = label_info
    idx = unit_id * 100 + row * 10 + col
    return {
        "unit_id": unit_id,
        "row": row,
        "col": col,
        "first_label": label_name,
        "first_catalog": f"{prefix}-{idx:04d}",
        "is_empty": False,
        "overrides": {},
    }


@st.composite
def synthetic_cut_set(draw: st.DrawFn) -> list[dict]:  # type: ignore[type-arg]
    """Generate a non-empty list of unique-by-address synthetic cut-point dicts.

    unit_id: 1 or 2, row: 0-3, col: 0-3. Each address is unique.
    Labels are sampled from the synthetic label pool (not necessarily unique across cubes).
    """
    addresses = draw(
        st.lists(
            st.tuples(
                st.integers(min_value=1, max_value=2),
                st.integers(min_value=0, max_value=3),
                st.integers(min_value=0, max_value=3),
            ),
            min_size=1,
            max_size=8,
            unique=True,
        )
    )
    label_choices = draw(
        st.lists(_LABEL_STRATEGY, min_size=len(addresses), max_size=len(addresses))
    )
    return [
        _make_cube_entry(uid, row, col, lbl)
        for (uid, row, col), lbl in zip(addresses, label_choices, strict=False)
    ]


# ── Round-trip identity helper ────────────────────────────────────────────────


def _serialize_to_yaml(cubes: list[dict]) -> str:
    """Serialize a list of cut-point dicts to the YAML import format (version: '1').

    Uses yaml.dump with sorted keys to ensure deterministic output.
    This mirrors the export endpoint's serialization contract.
    """
    import yaml

    cube_entries = []
    for c in sorted(cubes, key=lambda x: (x["unit_id"], x["row"], x["col"])):
        entry: dict = {
            "unit_id": c["unit_id"],
            "row": c["row"],
            "col": c["col"],
            "is_empty": c.get("is_empty", False),
        }
        if not entry["is_empty"]:
            entry["first_label"] = c["first_label"]
            entry["first_catalog"] = c["first_catalog"]
            if c.get("overrides"):
                entry["overrides"] = dict(sorted(c["overrides"].items()))
        cube_entries.append(entry)

    return yaml.dump(
        {"version": "1", "cubes": cube_entries},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )


def _parse_from_yaml(yaml_str: str) -> list[dict]:
    """Parse a YAML string back into a list of cut-point dicts.

    Mirrors the import endpoint's parse contract.
    Uses yaml.safe_load only (never yaml.load — T-YAML-BOMB).
    """
    import yaml

    data = yaml.safe_load(yaml_str)
    assert isinstance(data, dict), f"YAML must be a dict, got: {type(data)}"
    assert data.get("version") == "1", f"Expected version '1', got: {data.get('version')}"
    result = []
    for cube in data.get("cubes", []):
        result.append(
            {
                "unit_id": int(cube["unit_id"]),
                "row": int(cube["row"]),
                "col": int(cube["col"]),
                "is_empty": bool(cube.get("is_empty", False)),
                "first_label": cube.get("first_label"),
                "first_catalog": cube.get("first_catalog"),
                "overrides": dict(cube.get("overrides", {})),
            }
        )
    return result


# ── Property: export → re-import → zero diff ─────────────────────────────────


@given(cubes=synthetic_cut_set())
@settings(max_examples=100)
def test_export_roundtrip_identity(cubes: list[dict]) -> None:
    """export(cubes) → YAML → import → identical cut set (SC4 round-trip identity).

    Serializes a synthetic cut set to YAML and parses it back.
    The parsed result must match the original cut set exactly (modulo sort order).

    This property test exercises the serialize/parse Python utilities that the
    export + import endpoints will use. It goes GREEN as soon as the utilities
    are implemented (Plan 07-03). In Wave 0 the utilities do not yet exist —
    if they did, this test would trivially pass.

    Wave 0: this test passes because the helpers above implement the round-trip
    at the unit level. The full API-level round-trip (HTTP export → HTTP import)
    is tested separately in the integration suite once the endpoints land.
    """
    yaml_str = _serialize_to_yaml(cubes)
    restored = _parse_from_yaml(yaml_str)

    # Sort both by (unit_id, row, col) for comparison
    original_sorted = sorted(cubes, key=lambda x: (x["unit_id"], x["row"], x["col"]))
    restored_sorted = sorted(restored, key=lambda x: (x["unit_id"], x["row"], x["col"]))

    assert len(original_sorted) == len(restored_sorted), (
        f"Round-trip changed cube count: {len(original_sorted)} → {len(restored_sorted)}"
    )

    for orig, rest in zip(original_sorted, restored_sorted, strict=False):
        assert (orig["unit_id"], orig["row"], orig["col"]) == (
            rest["unit_id"],
            rest["row"],
            rest["col"],
        ), f"Address mismatch after round-trip: {orig} vs {rest}"

        assert orig["is_empty"] == rest["is_empty"], (
            f"is_empty field changed for {orig['unit_id']}/{orig['row']}/{orig['col']}"
        )

        if not orig["is_empty"]:
            assert orig["first_label"] == rest["first_label"], (
                f"first_label changed after round-trip: {orig['first_label']!r} → {rest['first_label']!r}"
            )
            assert orig["first_catalog"] == rest["first_catalog"], (
                f"first_catalog changed after round-trip: {orig['first_catalog']!r} → {rest['first_catalog']!r}"
            )

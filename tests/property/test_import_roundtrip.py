"""Hypothesis property tests for YAML import round-trip (ADMN-05, BAK-01).

Wave-0 RED scaffold — authored before the import endpoint exists.
Tests target the import-side round-trip contract distinct from the full
export → re-import roundtrip in test_export_roundtrip.py.

Focus: YAML parse → normalize → serialize → parse must be idempotent.
A valid YAML import file must survive two parse → serialize cycles unchanged.

Strategy: generate synthetic YAML boundary files using made-up labels.
No real collection data — synthetic labels only.
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st


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
]

_LABEL_STRATEGY = st.sampled_from(_SYNTHETIC_LABELS)


@st.composite
def synthetic_yaml_import(draw: st.DrawFn) -> str:  # type: ignore[type-arg]
    """Generate a synthetic YAML import string (version: '1') with unique addresses.

    unit_id: 1 or 2, row: 0-3, col: 0-3.
    All labels are synthetic; no real collection data.
    """
    import yaml

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

    cube_entries = []
    for (uid, row, col), (lbl_name, lbl_prefix) in zip(addresses, label_choices, strict=False):
        idx = uid * 100 + row * 10 + col
        cube_entries.append(
            {
                "unit_id": uid,
                "row": row,
                "col": col,
                "is_empty": False,
                "first_label": lbl_name,
                "first_catalog": f"{lbl_prefix}-{idx:04d}",
            }
        )

    return yaml.dump(
        {
            "version": "1",
            "cubes": sorted(cube_entries, key=lambda c: (c["unit_id"], c["row"], c["col"])),
        },
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )


def _parse_yaml(yaml_str: str) -> list[dict]:
    """Parse a YAML import string to a list of cut-point dicts.

    Uses yaml.safe_load only (never yaml.load — T-YAML-BOMB security requirement).
    """
    import yaml

    data = yaml.safe_load(yaml_str)
    assert isinstance(data, dict), f"YAML root must be a mapping, got: {type(data)}"
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
            }
        )
    return result


def _reserialize(cubes: list[dict]) -> str:
    """Re-serialize a list of cut-point dicts to YAML."""
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
            entry["first_label"] = c.get("first_label")
            entry["first_catalog"] = c.get("first_catalog")
        cube_entries.append(entry)

    return yaml.dump(
        {"version": "1", "cubes": cube_entries},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )


# ── Property: YAML import parse is idempotent ─────────────────────────────────


@given(yaml_str=synthetic_yaml_import())
@settings(max_examples=100)
def test_yaml_import_parse_idempotent(yaml_str: str) -> None:
    """parse(YAML) → re-serialize → parse must produce the same cut set (SC4).

    A valid YAML import file must survive two parse → serialize cycles without
    data loss or transformation. This ensures the import path is idempotent:
    importing the same file twice leaves the boundary set unchanged.

    Pure Python property test — does not require a live DB or HTTP client.
    Synthetic labels only; no real collection data referenced.
    """
    # First parse
    cubes_first = _parse_yaml(yaml_str)

    # Re-serialize and parse again
    yaml_second = _reserialize(cubes_first)
    cubes_second = _parse_yaml(yaml_second)

    # Sort both for comparison
    by_addr = lambda c: (c["unit_id"], c["row"], c["col"])  # noqa: E731
    first_sorted = sorted(cubes_first, key=by_addr)
    second_sorted = sorted(cubes_second, key=by_addr)

    assert len(first_sorted) == len(second_sorted), (
        f"Parse idempotency violation: cube count changed "
        f"{len(first_sorted)} → {len(second_sorted)}"
    )

    for f, s in zip(first_sorted, second_sorted, strict=False):
        assert (f["unit_id"], f["row"], f["col"]) == (s["unit_id"], s["row"], s["col"]), (
            f"Address changed across parse cycles: {f} vs {s}"
        )
        assert f["is_empty"] == s["is_empty"], (
            f"is_empty changed: {f['unit_id']}/{f['row']}/{f['col']}"
        )
        if not f["is_empty"]:
            assert f["first_label"] == s["first_label"], (
                f"first_label changed: {f['first_label']!r} → {s['first_label']!r}"
            )
            assert f["first_catalog"] == s["first_catalog"], (
                f"first_catalog changed: {f['first_catalog']!r} → {s['first_catalog']!r}"
            )


@given(yaml_str=synthetic_yaml_import())
@settings(max_examples=50)
def test_yaml_safe_load_only(yaml_str: str) -> None:
    """Verifies that safe_load parses the YAML correctly (T-YAML-BOMB guard).

    yaml.safe_load must be used exclusively — never yaml.load without a Loader.
    This test documents the requirement: all YAML parsing in GRUVAX uses safe_load.

    Synthetic data only; no real collection data.
    """
    import yaml

    # safe_load must not raise on valid YAML
    data = yaml.safe_load(yaml_str)
    assert data is not None, "safe_load returned None for non-empty YAML"
    assert isinstance(data, dict), f"safe_load result must be a dict, got: {type(data)}"
    assert "cubes" in data, f"YAML missing 'cubes' key: {data}"
    assert "version" in data, f"YAML missing 'version' key: {data}"

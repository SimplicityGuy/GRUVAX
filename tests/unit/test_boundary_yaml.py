"""Unit + property tests for YAML parse/serialize (boundary_yaml.py).

Tests:
  - parse_yaml_boundaries parses a known document correctly
  - round-trip identity with overrides
  - is_empty entries omit first_label/first_catalog/overrides in serialized YAML
  - missing or wrong version field raises ValueError
  - yaml.safe_load is used (rejects !!python/object tags without executing them)
"""

from __future__ import annotations

import textwrap

import pytest
import yaml

from gruvax.io.boundary_yaml import CutPointEntry, parse_yaml_boundaries, serialize_boundaries_yaml


# ── Fixture data ──────────────────────────────────────────────────────────────

VALID_YAML = textwrap.dedent("""\
    version: '1'
    cubes:
      - unit_id: 1
        row: 0
        col: 2
        first_label: Blue Note
        first_catalog: BLP-1500
        is_empty: false
        overrides:
          Atlantic: 0.45
          Blue Note: 0.55
      - unit_id: 1
        row: 1
        col: 0
        is_empty: true
""")


# ── Parse correctness tests ───────────────────────────────────────────────────


def test_parse_known_document() -> None:
    """parse_yaml_boundaries returns CutPointEntry list with correct types."""
    entries = parse_yaml_boundaries(VALID_YAML)
    assert len(entries) == 2

    non_empty = next(e for e in entries if not e.is_empty)
    assert non_empty.unit_id == 1
    assert non_empty.row == 0
    assert non_empty.col == 2
    assert non_empty.first_label == "Blue Note"
    assert non_empty.first_catalog == "BLP-1500"
    assert non_empty.is_empty is False
    assert non_empty.overrides == {"Atlantic": 0.45, "Blue Note": 0.55}

    empty = next(e for e in entries if e.is_empty)
    assert empty.unit_id == 1
    assert empty.row == 1
    assert empty.col == 0
    assert empty.is_empty is True
    assert empty.first_label is None
    assert empty.first_catalog is None
    assert empty.overrides == {}


def test_parse_accepts_bytes() -> None:
    """parse_yaml_boundaries accepts bytes input."""
    entries = parse_yaml_boundaries(VALID_YAML.encode())
    assert len(entries) == 2


def test_parse_missing_version_raises() -> None:
    """Missing version field raises ValueError."""
    doc = yaml.dump({"cubes": []})
    with pytest.raises(ValueError, match="Missing or unsupported version"):
        parse_yaml_boundaries(doc)


def test_parse_wrong_version_raises() -> None:
    """Wrong version value raises ValueError."""
    doc = yaml.dump({"version": "2", "cubes": []})
    with pytest.raises(ValueError, match="Missing or unsupported version"):
        parse_yaml_boundaries(doc)


def test_parse_not_a_dict_raises() -> None:
    """Non-dict YAML document raises ValueError."""
    with pytest.raises(ValueError, match="Missing or unsupported version"):
        parse_yaml_boundaries("- item1\n- item2\n")


def test_parse_empty_cubes_list() -> None:
    """Empty cubes list parses to empty list."""
    doc = yaml.dump({"version": "1", "cubes": []})
    entries = parse_yaml_boundaries(doc)
    assert entries == []


# ── Serialize correctness tests ───────────────────────────────────────────────


def test_serialize_produces_valid_yaml() -> None:
    """serialize_boundaries_yaml output is valid YAML with version field."""
    entries = [
        CutPointEntry(
            unit_id=1,
            row=0,
            col=0,
            first_label="ECM",
            first_catalog="ECM 1001",
            is_empty=False,
            overrides={},
        ),
    ]
    result = serialize_boundaries_yaml(entries)
    data = yaml.safe_load(result)
    assert data["version"] == "1"
    assert len(data["cubes"]) == 1


def test_serialize_empty_entry_omits_label_catalog_overrides() -> None:
    """is_empty=True entries omit first_label, first_catalog, overrides in YAML."""
    entries = [
        CutPointEntry(
            unit_id=1,
            row=0,
            col=0,
            first_label=None,
            first_catalog=None,
            is_empty=True,
            overrides={},
        ),
    ]
    result = serialize_boundaries_yaml(entries)
    data = yaml.safe_load(result)
    cube = data["cubes"][0]
    assert cube["is_empty"] is True
    assert "first_label" not in cube
    assert "first_catalog" not in cube
    assert "overrides" not in cube


def test_serialize_sorts_by_unit_row_col() -> None:
    """Serialized cubes are sorted by (unit_id, row, col)."""
    entries = [
        CutPointEntry(
            unit_id=2,
            row=1,
            col=0,
            first_label="A",
            first_catalog="A-001",
            is_empty=False,
            overrides={},
        ),
        CutPointEntry(
            unit_id=1,
            row=0,
            col=3,
            first_label="B",
            first_catalog="B-001",
            is_empty=False,
            overrides={},
        ),
        CutPointEntry(
            unit_id=1,
            row=0,
            col=1,
            first_label="C",
            first_catalog="C-001",
            is_empty=False,
            overrides={},
        ),
    ]
    result = serialize_boundaries_yaml(entries)
    data = yaml.safe_load(result)
    keys = [(c["unit_id"], c["row"], c["col"]) for c in data["cubes"]]
    assert keys == sorted(keys)


def test_overrides_survive_roundtrip() -> None:
    """Overrides {"Atlantic": 0.45, "Blue Note": 0.55} survive serialize → parse."""
    entry = CutPointEntry(
        unit_id=1,
        row=0,
        col=0,
        first_label="Atlantic",
        first_catalog="SD 8001",
        is_empty=False,
        overrides={"Atlantic": 0.45, "Blue Note": 0.55},
    )
    result = serialize_boundaries_yaml([entry])
    reparsed = parse_yaml_boundaries(result)
    assert len(reparsed) == 1
    assert reparsed[0].overrides == {"Atlantic": 0.45, "Blue Note": 0.55}


# ── Security test (yaml.safe_load rejects arbitrary tags) ────────────────────


def test_safe_load_rejects_python_object_tag() -> None:
    """YAML with !!python/object tag is rejected (safe_load does not execute it)."""
    malicious = textwrap.dedent("""\
        version: '1'
        cubes:
          - !!python/object:subprocess.Popen
            args: ["echo", "pwned"]
    """)
    # yaml.safe_load raises yaml.constructor.ConstructorError for arbitrary tags.
    # parse_yaml_boundaries propagates that error (does not catch it).
    with pytest.raises(yaml.constructor.ConstructorError):
        parse_yaml_boundaries(malicious)

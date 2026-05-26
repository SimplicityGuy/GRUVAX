"""Unit tests for boundary_csv.py flat CSV parser (Task 2).

Tests:
  - parse_csv_boundaries of a 5-row flat CSV → list[CutPointEntry] with overrides=={}
  - is_empty column truthiness: "true"/"1"/"yes" (any case) → True; blank/"false" → False
  - is_empty=true rows yield first_label=None/first_catalog=None when cells are blank
  - CSV missing a required header → ValueError naming the expected header set
  - Leading/trailing whitespace stripped; empty string → None for first_label/first_catalog
  - BOM-prefixed CSV parses correctly (csv.DictReader with utf-8-sig handles BOM)
"""

from __future__ import annotations

import pytest

from gruvax.io.boundary_csv import REQUIRED_HEADERS, parse_csv_boundaries
from gruvax.io.boundary_yaml import CutPointEntry


# ── Fixture CSV data ──────────────────────────────────────────────────────────

FIVE_ROW_CSV = (
    "unit_id,row,col,first_label,first_catalog,is_empty\n"
    "1,0,0,Blue Note,BLP-1500,false\n"
    "1,0,1,Atlantic,SD 8001,false\n"
    "1,0,2,ECM,ECM 1001,false\n"
    "1,0,3,,, true\n"  # empty cube — note trailing whitespace on is_empty
    "2,0,0,Verve,V-8427,false\n"
)


# ── Basic parse tests ─────────────────────────────────────────────────────────


def test_parse_five_rows() -> None:
    """Five-row CSV produces five CutPointEntry values, all with overrides=={}."""
    entries = parse_csv_boundaries(FIVE_ROW_CSV)
    assert len(entries) == 5
    for e in entries:
        assert e.overrides == {}, f"Expected empty overrides, got {e.overrides}"


def test_parse_correct_types() -> None:
    """Fields are coerced to correct types."""
    entries = parse_csv_boundaries(FIVE_ROW_CSV)
    first = next(e for e in entries if e.first_label == "Blue Note")
    assert first.unit_id == 1
    assert first.row == 0
    assert first.col == 0
    assert first.first_catalog == "BLP-1500"
    assert first.is_empty is False


def test_parse_all_entries_have_empty_overrides() -> None:
    """Every parsed entry has overrides=={} (flat CSV carries no overrides)."""
    entries = parse_csv_boundaries(FIVE_ROW_CSV)
    assert all(e.overrides == {} for e in entries)


# ── is_empty truthiness tests ─────────────────────────────────────────────────


def test_is_empty_true_values() -> None:
    """'true', '1', 'yes' (any case) parse as is_empty=True."""
    truthy_values = ["true", "TRUE", "True", "1", "yes", "YES", "Yes"]
    for val in truthy_values:
        csv_data = f"unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,,,{val}\n"
        entries = parse_csv_boundaries(csv_data)
        assert len(entries) == 1
        assert entries[0].is_empty is True, f"Expected is_empty=True for '{val}'"


def test_is_empty_false_values() -> None:
    """Blank and 'false' parse as is_empty=False."""
    falsy_values = ["false", "FALSE", "False", "0", ""]
    for val in falsy_values:
        csv_data = (
            f"unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,Blue Note,BLP-1500,{val}\n"
        )
        entries = parse_csv_boundaries(csv_data)
        assert len(entries) == 1
        assert entries[0].is_empty is False, f"Expected is_empty=False for '{val}'"


def test_is_empty_true_gives_none_label_catalog() -> None:
    """is_empty=true rows yield first_label=None and first_catalog=None when cells blank."""
    csv_data = "unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,,,true\n"
    entries = parse_csv_boundaries(csv_data)
    assert len(entries) == 1
    e = entries[0]
    assert e.is_empty is True
    assert e.first_label is None
    assert e.first_catalog is None


# ── Missing header tests ──────────────────────────────────────────────────────


def test_missing_required_header_raises_value_error() -> None:
    """CSV missing any required header raises ValueError."""
    csv_missing_is_empty = "unit_id,row,col,first_label,first_catalog\n1,0,0,A,B\n"
    with pytest.raises(ValueError) as exc_info:
        parse_csv_boundaries(csv_missing_is_empty)
    # Error message should name the expected headers
    error_msg = str(exc_info.value)
    assert (
        "is_empty" in error_msg
        or str(REQUIRED_HEADERS) in error_msg
        or "required" in error_msg.lower()
    )


def test_missing_unit_id_header_raises() -> None:
    """CSV missing unit_id header raises ValueError."""
    csv_data = "row,col,first_label,first_catalog,is_empty\n0,0,A,B,false\n"
    with pytest.raises(ValueError):
        parse_csv_boundaries(csv_data)


def test_empty_csv_with_correct_headers_returns_empty_list() -> None:
    """CSV with correct headers but no data rows returns empty list."""
    csv_data = "unit_id,row,col,first_label,first_catalog,is_empty\n"
    entries = parse_csv_boundaries(csv_data)
    assert entries == []


# ── Whitespace stripping tests ────────────────────────────────────────────────


def test_whitespace_stripped_from_cells() -> None:
    """Leading/trailing whitespace in cells is stripped."""
    csv_data = "unit_id,row,col,first_label,first_catalog,is_empty\n  1 ,  0 ,  0 ,  Blue Note  ,  BLP-1500  ,  false  \n"
    entries = parse_csv_boundaries(csv_data)
    assert len(entries) == 1
    e = entries[0]
    assert e.unit_id == 1
    assert e.first_label == "Blue Note"
    assert e.first_catalog == "BLP-1500"
    assert e.is_empty is False


def test_empty_string_yields_none_for_label_catalog() -> None:
    """Empty string (or whitespace-only) in first_label/first_catalog → None."""
    csv_data = "unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,   ,   ,false\n"
    entries = parse_csv_boundaries(csv_data)
    assert len(entries) == 1
    e = entries[0]
    assert e.first_label is None
    assert e.first_catalog is None


# ── BOM test ──────────────────────────────────────────────────────────────────


def test_bom_prefixed_csv_parses_correctly() -> None:
    """BOM-prefixed UTF-8 CSV parses without errors (DictReader handles BOM)."""
    # UTF-8 BOM is the byte sequence \xef\xbb\xbf; as a string it is the
    # Unicode BOM character U+FEFF. csv.DictReader opened with the utf-8-sig
    # encoding (or passed a StringIO with the BOM already decoded) handles it.
    bom = "﻿"
    csv_data = (
        f"{bom}unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,ECM,ECM 1001,false\n"
    )
    entries = parse_csv_boundaries(csv_data)
    assert len(entries) == 1
    assert entries[0].first_label == "ECM"
    assert entries[0].first_catalog == "ECM 1001"


# ── Import consistency ────────────────────────────────────────────────────────


def test_returns_cut_point_entry_instances() -> None:
    """parse_csv_boundaries returns CutPointEntry instances."""
    csv_data = "unit_id,row,col,first_label,first_catalog,is_empty\n1,0,0,A,B,false\n"
    entries = parse_csv_boundaries(csv_data)
    assert all(isinstance(e, CutPointEntry) for e in entries)

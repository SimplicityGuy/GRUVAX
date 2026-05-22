"""Unit tests for boundary validation — POS-01 comparator check (ADMN-03).

Validates that the boundary validator (implemented in Plan 02/04 as the
``validate_boundary`` helper) rejects boundaries where first > last.

All catalog comparisons must go through ``parse_key`` (POS-01, T-03-03, Pitfall C).
Labels are compared with ``.casefold()`` only — never ``normalize_catalog()``.

Analog: tests/unit/test_normalize.py (pure-function pattern).
"""

from __future__ import annotations


def test_first_gt_last() -> None:
    """A boundary where parse_key(first_catalog) > parse_key(last_catalog) is rejected.

    POS-01 / ADMN-03: the save validator must call parse_key (not raw string compare)
    to detect inverted boundaries. Example: "BLP 10" > "BLP 9" under raw string
    compare, but parse_key("BLP 9") < parse_key("BLP 10") (numeric-aware).
    """
    from gruvax.api.admin.validation import validate_boundary_order

    # Catalog-inverted boundary: "BLP 20" is numerically greater than "BLP 10"
    result = validate_boundary_order(
        first_label="Blue Note",
        first_catalog="BLP 20",
        last_label="Blue Note",
        last_catalog="BLP 10",
    )
    assert not result, (
        "validate_boundary_order must return False for inverted catalog range"
        " (first_catalog > last_catalog per parse_key)"
    )


def test_valid_same_label_boundary() -> None:
    """A boundary where first_catalog < last_catalog (same label) is valid."""
    from gruvax.api.admin.validation import validate_boundary_order

    result = validate_boundary_order(
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="Blue Note",
        last_catalog="BLP 4195",
    )
    assert result, "Valid same-label boundary must pass validation"


def test_valid_multi_label_boundary() -> None:
    """A boundary spanning two labels is valid when first_label < last_label (casefold)."""
    from gruvax.api.admin.validation import validate_boundary_order

    result = validate_boundary_order(
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="ECM",
        last_catalog="ECM 1050",
    )
    assert result, "Multi-label boundary with first_label < last_label must be valid"


def test_label_first_gt_last_rejected() -> None:
    """A boundary where first_label.casefold() > last_label.casefold() is rejected.

    Labels are compared with .casefold() — never normalize_catalog() (Pitfall C).
    """
    from gruvax.api.admin.validation import validate_boundary_order

    result = validate_boundary_order(
        first_label="ECM",
        first_catalog="ECM 1001",
        last_label="Blue Note",
        last_catalog="BLP 4195",
    )
    assert not result, (
        "validate_boundary_order must return False when first_label > last_label (casefold)"
    )


def test_numeric_sort_awareness() -> None:
    """Catalog comparison must be numeric-aware via parse_key.

    Raw string: "BLP 9" > "BLP 10" (because "9" > "1").
    parse_key: BLP 9 < BLP 10 (numeric-aware — 9 < 10).
    This test ensures the validator uses parse_key, not raw comparison.
    """
    from gruvax.api.admin.validation import validate_boundary_order

    # Numerically: BLP 9 < BLP 10, so this is a valid boundary
    result = validate_boundary_order(
        first_label="Blue Note",
        first_catalog="BLP 9",
        last_label="Blue Note",
        last_catalog="BLP 10",
    )
    assert result, "BLP 9 < BLP 10 numerically — boundary must be valid (parse_key-aware)"

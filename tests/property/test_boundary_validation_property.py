"""Hypothesis property tests for boundary validation (ADMN-03).

Invariants:
  1. Any boundary where parse_key(first_catalog) > parse_key(last_catalog) is rejected
  2. Any boundary where first_label.casefold() > last_label.casefold() is rejected
  3. A valid boundary (first <= last in both dimensions) is accepted

These tests target ``gruvax.api.admin.validation.validate_boundary_order``
(implemented in Plan 02/04). Authored RED in Wave-0; goes GREEN when Plan 02 ships.

Analog: tests/property/test_parser_props.py (Hypothesis @given + @settings pattern).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from gruvax.estimator.normalize import parse_key

# ── Strategy helpers ──────────────────────────────────────────────────────────

_LABEL_STRATEGY = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    min_size=1,
    max_size=15,
)

_CATALOG_N_STRATEGY = st.integers(min_value=1, max_value=9999)


# ── Property 1: inverted catalog range is rejected ────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    n_first=_CATALOG_N_STRATEGY,
    n_last=_CATALOG_N_STRATEGY,
)
@settings(max_examples=300)
def test_inverted_catalog_rejected(label: str, n_first: int, n_last: int) -> None:
    """Any boundary where parse_key(first) > parse_key(last) is rejected (ADMN-03).

    This is the POS-01 comparator check: labels and catalogs must be in order.
    Uses parse_key for numeric-aware comparison (not raw string).
    """
    from gruvax.api.admin.validation import validate_boundary_order

    first_cat = f"CAT {n_first}"
    last_cat = f"CAT {n_last}"

    expected_valid = parse_key(first_cat) <= parse_key(last_cat)
    result = validate_boundary_order(
        first_label=label,
        first_catalog=first_cat,
        last_label=label,
        last_catalog=last_cat,
    )
    assert result == expected_valid, (
        f"validate_boundary_order({label!r}, {first_cat!r}, {label!r}, {last_cat!r})"
        f" should be {expected_valid} (parse_key-aware), got {result}"
    )


# ── Property 2: inverted label range is rejected ──────────────────────────────


@given(
    label_first=_LABEL_STRATEGY,
    label_last=_LABEL_STRATEGY,
    n=_CATALOG_N_STRATEGY,
)
@settings(max_examples=300)
def test_inverted_label_rejected(label_first: str, label_last: str, n: int) -> None:
    """Any boundary where first_label.casefold() > last_label.casefold() is rejected.

    Labels are compared with .casefold() — never normalize_catalog() (Pitfall C).
    When both labels are equal and catalogs are in valid order, boundary is accepted.
    """
    from gruvax.api.admin.validation import validate_boundary_order

    label_first_lower = label_first.casefold()
    label_last_lower = label_last.casefold()

    # For simplicity, use the same catalog number so catalog comparison is always valid
    first_cat = f"CAT {n}"
    last_cat = f"CAT {n}"  # same catalog → always valid catalog range

    # The result depends only on label ordering (catalog range is valid)
    expected_valid = label_first_lower <= label_last_lower
    result = validate_boundary_order(
        first_label=label_first,
        first_catalog=first_cat,
        last_label=label_last,
        last_catalog=last_cat,
    )
    assert result == expected_valid, (
        f"validate_boundary_order with labels ({label_first!r}, {label_last!r})"
        f" should be {expected_valid} (casefold comparison), got {result}"
    )


# ── Property 3: valid boundaries are accepted ─────────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    n_first=_CATALOG_N_STRATEGY,
    extra=st.integers(min_value=0, max_value=999),
)
@settings(max_examples=300)
def test_valid_boundary_accepted(label: str, n_first: int, extra: int) -> None:
    """A boundary where first <= last in both catalog and label dimensions is accepted."""
    from gruvax.api.admin.validation import validate_boundary_order

    # Ensure first_catalog <= last_catalog (same prefix, non-decreasing numeric)
    first_cat = f"CAT {n_first}"
    last_cat = f"CAT {n_first + extra}"

    result = validate_boundary_order(
        first_label=label,
        first_catalog=first_cat,
        last_label=label,
        last_catalog=last_cat,
    )
    assert result is True, (
        f"Valid boundary (first={first_cat!r} <= last={last_cat!r}, same label) "
        f"must be accepted, got {result}"
    )

"""Hypothesis property tests for fill-level computation (CUBE-07).

Invariants:
  1. count_records_in_boundary >= 0 for any valid boundary (non-negative count)
  2. count is monotone: a wider catalog range produces >= count as a narrower one
  3. label comparison uses .casefold(), NEVER normalize_catalog() (Pitfall C, T-03-03)
  4. is_empty=True always yields count == 0

These tests target ``gruvax.estimator.boundary_math.count_records_in_boundary``.
Authored RED in Plan 01 Task 2; goes GREEN when Task 3 implements boundary_math.py.

Analog: tests/property/test_parser_props.py (Hypothesis @given + @settings pattern).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from gruvax.estimator.boundary_cache import BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow

# ── Strategy helpers ──────────────────────────────────────────────────────────

# Valid 4-character ASCII alpha catalog prefix (e.g. "BLP ", "ECM ", "VERV")
_LABEL_STRATEGY = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz ",
    min_size=2,
    max_size=20,
).filter(lambda s: s.strip())

_CATALOG_N_STRATEGY = st.integers(min_value=1, max_value=9999)


def _make_snapshot_from_records(records: list[RecordRow]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from a flat list of records (no DB)."""
    by_label: dict[str, list[RecordRow]] = {}
    for r in records:
        key = r.label.casefold()
        if key not in by_label:
            by_label[key] = []
        by_label[key].append(r)
    snap = CollectionSnapshot()
    snap._load_snapshot(by_label)
    return snap


def _make_boundary(
    label: str,
    first_n: int,
    last_n: int,
    is_empty: bool = False,
) -> BoundaryRow:
    return BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label=label if not is_empty else None,
        first_catalog=f"CAT {first_n}" if not is_empty else None,
        last_label=label if not is_empty else None,
        last_catalog=f"CAT {last_n}" if not is_empty else None,
        is_empty=is_empty,
    )


# ── Property 1: count is always non-negative ──────────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    first_n=_CATALOG_N_STRATEGY,
    last_n=_CATALOG_N_STRATEGY,
    record_count=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=200)
def test_fill_count_nonnegative(
    label: str,
    first_n: int,
    last_n: int,
    record_count: int,
) -> None:
    """count_records_in_boundary >= 0 for any valid (non-empty) boundary."""
    from gruvax.estimator.boundary_math import count_records_in_boundary

    label = label.strip() or "TestLabel"
    records = [
        RecordRow(
            release_id=i,
            label=label,
            catalog_number=f"CAT {i}",
        )
        for i in range(1, record_count + 1)
    ]
    snapshot = _make_snapshot_from_records(records)

    first_cat = min(first_n, last_n)
    last_cat = max(first_n, last_n)
    boundary = _make_boundary(label, first_cat, last_cat)
    count = count_records_in_boundary(boundary, snapshot)
    assert count >= 0, f"count_records_in_boundary must be non-negative, got {count}"


# ── Property 2: empty boundary always yields 0 ───────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    record_count=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200)
def test_empty_boundary_zero(label: str, record_count: int) -> None:
    """count_records_in_boundary returns 0 for is_empty=True boundaries."""
    from gruvax.estimator.boundary_math import count_records_in_boundary

    label = label.strip() or "TestLabel"
    records = [
        RecordRow(release_id=i, label=label, catalog_number=f"CAT {i}")
        for i in range(1, record_count + 1)
    ]
    snapshot = _make_snapshot_from_records(records)
    boundary = _make_boundary(label, 1, record_count, is_empty=True)
    count = count_records_in_boundary(boundary, snapshot)
    assert count == 0, (
        f"count_records_in_boundary must return 0 for is_empty boundary, got {count}"
    )


# ── Property 3: casefold label lookup (Pitfall C / T-03-03) ──────────────────


@given(
    base_label=st.text(
        alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        min_size=3,
        max_size=15,
    ),
    n=st.integers(min_value=1, max_value=20),
)
@settings(max_examples=200)
def test_label_casefold_not_normalize_catalog(base_label: str, n: int) -> None:
    """Labels are compared via .casefold() — count must be same for upper/lower variants.

    Pitfall C (T-03-03): labels must NEVER go through normalize_catalog().
    normalize_catalog() collapses separators and treats labels like catalog numbers,
    which would produce wrong results (e.g., "Blue Note" → "bluenote").
    """
    from gruvax.estimator.boundary_math import count_records_in_boundary

    # Records stored with mixed-case label
    mixed_label = base_label.capitalize()
    records = [
        RecordRow(release_id=i, label=mixed_label, catalog_number=f"CAT {i}")
        for i in range(1, n + 1)
    ]
    snapshot = _make_snapshot_from_records(records)

    # Boundary with uppercase label — must find same records via casefold
    upper_boundary = _make_boundary(base_label.upper(), 1, n)
    lower_boundary = _make_boundary(base_label.lower(), 1, n)

    count_upper = count_records_in_boundary(upper_boundary, snapshot)
    count_lower = count_records_in_boundary(lower_boundary, snapshot)

    assert count_upper == count_lower, (
        f"Label case must not affect count: "
        f"upper={count_upper}, lower={count_lower} for label={base_label!r}"
    )


# ── Property 4: monotone in range width ──────────────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    n=st.integers(min_value=5, max_value=50),
    cut=st.integers(min_value=1, max_value=4),
)
@settings(max_examples=200)
def test_fill_count_monotone_in_range(label: str, n: int, cut: int) -> None:
    """A wider catalog range produces >= count than a narrower one (monotonicity).

    If boundary A covers records 1–n and boundary B covers 1–(n-cut),
    then count(A) >= count(B).
    """
    from gruvax.estimator.boundary_math import count_records_in_boundary

    label = label.strip() or "TestLabel"
    records = [
        RecordRow(release_id=i, label=label, catalog_number=f"CAT {i}")
        for i in range(1, n + 1)
    ]
    snapshot = _make_snapshot_from_records(records)

    narrow_last = max(1, n - cut)
    wider_boundary = _make_boundary(label, 1, n)
    narrow_boundary = _make_boundary(label, 1, narrow_last)

    count_wider = count_records_in_boundary(wider_boundary, snapshot)
    count_narrow = count_records_in_boundary(narrow_boundary, snapshot)

    assert count_wider >= count_narrow, (
        f"Wider range must produce >= count than narrower: "
        f"wider={count_wider}, narrow={count_narrow}"
    )

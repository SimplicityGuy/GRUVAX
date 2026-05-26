"""Hypothesis property tests for fill-level computation (CUBE-07).

Phase 5 rewrite (Plan 05-03): count_records_in_boundary is a deprecated compat
shim returning 0. These property tests now target ``count_records_in_bin`` from
``gruvax.estimator.boundary_math``, which is the Phase 5 production function.

The tests build a BoundaryCache + CollectionSnapshot, derive a SegmentCache,
then call get_bin() to obtain the SegmentBin for count_records_in_bin.

Invariants:
  1. count_records_in_bin >= 0 for any valid SegmentBin
  2. is_empty=True boundary always yields an empty bin (count == 0)
  3. Single-label single-cube bin count == number of records in snapshot

Analog: tests/property/test_parser_props.py (Hypothesis @given + @settings pattern).
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentBin, SegmentCache


# ── Strategy helpers ──────────────────────────────────────────────────────────

# Valid ASCII alpha label (must not be empty after strip)
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


def _make_single_cube_cache(label: str, first_cat: str) -> BoundaryCache:
    """Build a BoundaryCache with a single cut-point cube (Phase 5 — no last_*)."""
    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label=label,
            first_catalog=first_cat,
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)
    return cache


def _make_empty_cache() -> BoundaryCache:
    """Build a BoundaryCache with a single cube marked is_empty=True."""
    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label=None,
            first_catalog=None,
            is_empty=True,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)
    return cache


def _derive_get_bin(
    cache: BoundaryCache,
    snapshot: CollectionSnapshot,
) -> SegmentBin | None:
    """Derive a SegmentCache and return the single bin at (1,0,0)."""
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})
    return sc.get_bin(1, 0, 0)


# ── Property 1: count is always non-negative ──────────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    record_count=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=200)
def test_fill_count_nonnegative(
    label: str,
    record_count: int,
) -> None:
    """count_records_in_bin >= 0 for any valid SegmentBin."""
    from gruvax.estimator.boundary_math import count_records_in_bin

    label = label.strip() or "TestLabel"
    records = [
        RecordRow(
            release_id=i,
            label=label,
            catalog_number=f"CAT {i:04d}",
        )
        for i in range(1, record_count + 1)
    ]
    snapshot = _make_snapshot_from_records(records)
    first_cat = "CAT 0001" if record_count == 0 else f"CAT {1:04d}"
    cache = _make_single_cube_cache(label, first_cat)
    seg_bin = _derive_get_bin(cache, snapshot)
    assert seg_bin is not None, "Expected a SegmentBin"
    count = count_records_in_bin(seg_bin)
    assert count >= 0, f"count_records_in_bin must be non-negative, got {count}"


# ── Property 2: empty boundary always yields 0 ───────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    record_count=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200)
def test_empty_boundary_zero(label: str, record_count: int) -> None:
    """count_records_in_bin returns 0 for is_empty=True boundaries (empty segments tuple)."""
    from gruvax.estimator.boundary_math import count_records_in_bin

    label = label.strip() or "TestLabel"
    records = [
        RecordRow(release_id=i, label=label, catalog_number=f"CAT {i:04d}")
        for i in range(1, record_count + 1)
    ]
    snapshot = _make_snapshot_from_records(records)
    cache = _make_empty_cache()
    seg_bin = _derive_get_bin(cache, snapshot)
    assert seg_bin is not None, "Expected a SegmentBin even for empty boundary"
    count = count_records_in_bin(seg_bin)
    assert count == 0, f"count_records_in_bin must return 0 for is_empty boundary, got {count}"


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

    Both upper and lower boundary cuts resolve to the same label via casefold,
    so count_records_in_bin must return the same count for both.
    """
    from gruvax.estimator.boundary_math import count_records_in_bin

    # Records stored with mixed-case label
    mixed_label = base_label.capitalize()
    records = [
        RecordRow(release_id=i, label=mixed_label, catalog_number=f"CAT {i:04d}")
        for i in range(1, n + 1)
    ]
    snapshot = _make_snapshot_from_records(records)

    # Build two caches with upper / lower first_label — both should map to same label
    first_cat = "CAT 0001"
    cache_upper = _make_single_cube_cache(base_label.upper(), first_cat)
    cache_lower = _make_single_cube_cache(base_label.lower(), first_cat)

    bin_upper = _derive_get_bin(cache_upper, snapshot)
    bin_lower = _derive_get_bin(cache_lower, snapshot)

    assert bin_upper is not None and bin_lower is not None, "Expected SegmentBins for both"

    count_upper = count_records_in_bin(bin_upper)
    count_lower = count_records_in_bin(bin_lower)

    assert count_upper == count_lower, (
        f"Label case must not affect count: "
        f"upper={count_upper}, lower={count_lower} for label={base_label!r}"
    )


# ── Property 4: single-cube single-label count matches snapshot ───────────────


@given(
    label=_LABEL_STRATEGY,
    n=st.integers(min_value=1, max_value=50),
)
@settings(max_examples=200)
def test_fill_count_matches_snapshot_size(label: str, n: int) -> None:
    """A single-label single-cube bin count equals the number of records in the snapshot.

    When one label fully occupies a single cube, count_records_in_bin must return
    exactly the number of records in the snapshot for that label.
    """
    from gruvax.estimator.boundary_math import count_records_in_bin

    label = label.strip() or "TestLabel"
    records = [
        RecordRow(release_id=i, label=label, catalog_number=f"CAT {i:04d}") for i in range(1, n + 1)
    ]
    snapshot = _make_snapshot_from_records(records)
    cache = _make_single_cube_cache(label, "CAT 0001")
    seg_bin = _derive_get_bin(cache, snapshot)
    assert seg_bin is not None, "Expected a SegmentBin"
    count = count_records_in_bin(seg_bin)
    assert count == n, f"Expected count == n={n} for single-label single-cube bin, got {count}"

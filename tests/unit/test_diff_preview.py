"""Unit tests for diff-preview record-movement counts (ADMN-07).

Tests that record-movement counts are correctly computed from the in-memory
SegmentCache when a boundary changes — no DB hit (D-09).

Phase 5 update: uses SegmentCache + count_records_in_bin instead of the
retired count_records_in_boundary + BoundaryRow(last_*=...) approach.

Analog: tests/unit/test_algorithm.py (snapshot fixture + pure computation).
"""

from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentCache


def _make_snapshot(records_by_label: dict[str, list[RecordRow]]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from pre-grouped records (no DB)."""
    snap = CollectionSnapshot()
    snap._load_snapshot({k.casefold(): v for k, v in records_by_label.items()})
    return snap


def _make_cache_single_boundary(
    unit_id: int,
    row: int,
    col: int,
    first_label: str,
    first_catalog: str,
) -> BoundaryCache:
    """Build a BoundaryCache with a single cut-point boundary (no last_*)."""
    cache = BoundaryCache()
    cache._load_rows(
        [
            BoundaryRow(
                unit_id=unit_id,
                row=row,
                col=col,
                first_label=first_label,
                first_catalog=first_catalog,
                is_empty=False,
            )
        ]
    )
    return cache


def _make_cache_two_boundaries(
    unit_id: int,
    row_a: int,
    col_a: int,
    first_label_a: str,
    first_catalog_a: str,
    row_b: int,
    col_b: int,
    first_label_b: str,
    first_catalog_b: str,
) -> BoundaryCache:
    """Build a BoundaryCache with two cut-point boundaries."""
    cache = BoundaryCache()
    cache._load_rows(
        [
            BoundaryRow(
                unit_id=unit_id,
                row=row_a,
                col=col_a,
                first_label=first_label_a,
                first_catalog=first_catalog_a,
                is_empty=False,
            ),
            BoundaryRow(
                unit_id=unit_id,
                row=row_b,
                col=col_b,
                first_label=first_label_b,
                first_catalog=first_catalog_b,
                is_empty=False,
            ),
        ]
    )
    return cache


def test_movement_counts() -> None:
    """Record-movement count is correct for a known boundary change.

    Scenario (cut-point model, Phase 5):
      - Cube A (1,0,0) has cut_point "Blue Note / BLP 4001" → first 50 records
      - Cube B (1,0,1) has cut_point "Blue Note / BLP 4051" → next 50 records
      - Both have 100 Blue Note records total (BLP 4001-4100)

    Under the cut-point model, count_records_in_bin counts are derived from
    SegmentCache.derive() which assigns records to bins by global sort order.

    Before: Cube A = 50 records (BLP 4001-4050), Cube B = 50 records (BLP 4051-4100)
    After moving cut point: Cube A = 75 records (BLP 4001-4075), Cube B = 25 records

    The delta for Cube A = +25 records.
    """
    from gruvax.estimator.boundary_math import count_records_in_bin

    # Build a synthetic label with 100 records: BLP 4001-4100
    records_bn = [
        RecordRow(
            release_id=i,
            label="Blue Note",
            catalog_number=f"BLP {4000 + i}",
        )
        for i in range(1, 101)
    ]
    snapshot = _make_snapshot({"Blue Note": records_bn})

    # --- Before: two cuts, Cube A covers BLP 4001-4050, Cube B covers BLP 4051-4100
    cache_before = _make_cache_two_boundaries(
        unit_id=1,
        row_a=0, col_a=0, first_label_a="Blue Note", first_catalog_a="BLP 4001",
        row_b=0, col_b=1, first_label_b="Blue Note", first_catalog_b="BLP 4051",
    )
    sc_before = SegmentCache()
    sc_before.derive(cache_before, snapshot, {})

    bin_a_before = sc_before.get_bin(1, 0, 0)
    assert bin_a_before is not None, "Cube A bin must exist in before-state"
    count_before = count_records_in_bin(bin_a_before)

    # --- After: Cube A's cut covers BLP 4001-4075, Cube B's cut covers BLP 4076-4100
    cache_after = _make_cache_two_boundaries(
        unit_id=1,
        row_a=0, col_a=0, first_label_a="Blue Note", first_catalog_a="BLP 4001",
        row_b=0, col_b=1, first_label_b="Blue Note", first_catalog_b="BLP 4076",
    )
    sc_after = SegmentCache()
    sc_after.derive(cache_after, snapshot, {})

    bin_a_after = sc_after.get_bin(1, 0, 0)
    assert bin_a_after is not None, "Cube A bin must exist in after-state"
    count_after = count_records_in_bin(bin_a_after)

    # 25 records moved into Cube A (from 50 → 75)
    assert count_after - count_before == 25, (
        f"Expected movement of 25 records, got {count_after - count_before}"
    )
    assert count_before == 50, f"Expected 50 records in original boundary, got {count_before}"
    assert count_after == 75, f"Expected 75 records in new boundary, got {count_after}"

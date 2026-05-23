"""Unit tests for fill-level computation (CUBE-07).

Phase 5 rewrite (Plan 05-03): count_records_in_boundary is a deprecated compat
shim returning 0. Tests now target ``count_records_in_bin`` from
``gruvax.estimator.boundary_math``, which is the Phase 5 production function.

Fill level = count_records_in_bin(seg_bin) / nominal_capacity (D-13).
count_records_in_bin returns the integer record count; the caller divides.

The tests build a BoundaryCache + CollectionSnapshot, derive a SegmentCache,
then call get_bin() to obtain the SegmentBin for count_records_in_bin.

Analog: tests/unit/test_collection_snapshot.py (snapshot fixture pattern).
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


def _derive_segment_cache(cache: BoundaryCache, snapshot: CollectionSnapshot) -> SegmentCache:
    """Derive a SegmentCache from a BoundaryCache + snapshot with no overrides."""
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})
    return sc


def test_empty_cube() -> None:
    """count_records_in_bin returns 0 for an is_empty=True boundary (CUBE-07).

    An empty cube has no records regardless of the snapshot contents.
    """
    from gruvax.estimator.boundary_math import count_records_in_bin

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    # Empty cube: SegmentBin will have no segments (empty tuple).
    cache = _make_empty_cache()
    sc = _derive_segment_cache(cache, snapshot)
    seg_bin = sc.get_bin(1, 0, 0)
    assert seg_bin is not None, "Expected a SegmentBin for the empty cube"
    count = count_records_in_bin(seg_bin)
    assert count == 0, f"Expected 0 for empty boundary, got {count}"


def test_overstuffed() -> None:
    """count_records_in_bin can return a count exceeding nominal capacity.

    Fill level > 1.0 is possible for overstuffed cubes — count/capacity may exceed 1.0.
    The boundary math returns an integer count; the divide-by-capacity is the caller's job.
    """
    from gruvax.estimator.boundary_math import count_records_in_bin

    # 200 records all within the boundary range; nominal capacity is typically 95
    records = [
        RecordRow(
            release_id=i,
            label="Blue Note",
            catalog_number=f"BLP {4000 + i}",
        )
        for i in range(1, 201)
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    cache = _make_single_cube_cache("Blue Note", "BLP 4001")
    sc = _derive_segment_cache(cache, snapshot)
    seg_bin = sc.get_bin(1, 0, 0)
    assert seg_bin is not None, "Expected a SegmentBin"
    count = count_records_in_bin(seg_bin)
    assert count == 200, f"Expected 200 records, got {count}"
    # As a fill level: 200 / 95 > 1.0 — this is expected and valid
    assert count / 95 > 1.0, "Overstuffed cube must yield fill_level > 1.0"


def test_same_label_boundary() -> None:
    """count_records_in_bin counts all records in the bin for the label."""
    from gruvax.estimator.boundary_math import count_records_in_bin

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
        RecordRow(release_id=2, label="Blue Note", catalog_number="BLP 4050"),
        RecordRow(release_id=3, label="Blue Note", catalog_number="BLP 4200"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    # Single-cube cache: all 3 records belong to this bin
    cache = _make_single_cube_cache("Blue Note", "BLP 4001")
    sc = _derive_segment_cache(cache, snapshot)
    seg_bin = sc.get_bin(1, 0, 0)
    assert seg_bin is not None, "Expected a SegmentBin"
    count = count_records_in_bin(seg_bin)
    # All 3 records are in this bin (single-cube, single-label)
    assert count == 3, f"Expected 3 records in bin, got {count}"


def test_empty_snapshot() -> None:
    """count_records_in_bin returns 0 for a bin with no matching records."""
    from gruvax.estimator.boundary_math import count_records_in_bin

    snapshot = _make_snapshot({})  # empty snapshot

    # Cache has a cut point, but the snapshot has no records for it
    cache = _make_single_cube_cache("Blue Note", "BLP 4001")
    sc = _derive_segment_cache(cache, snapshot)
    seg_bin = sc.get_bin(1, 0, 0)
    assert seg_bin is not None, "Expected a SegmentBin"
    count = count_records_in_bin(seg_bin)
    assert count == 0, f"Expected 0 for empty snapshot, got {count}"

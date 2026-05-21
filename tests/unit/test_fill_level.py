"""Unit tests for fill-level computation (CUBE-07).

Tests ``count_records_in_boundary`` from ``gruvax.estimator.boundary_math``.
Authored RED in Plan 01 Task 2 (Wave-0 scaffold); goes GREEN when Task 3
implements ``boundary_math.py``.

Fill level = records_in_range / nominal_capacity (D-13).
count_records_in_boundary returns the integer record count; the caller divides.

Analog: tests/unit/test_collection_snapshot.py (snapshot fixture pattern).
"""

from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow


def _make_snapshot(records_by_label: dict[str, list[RecordRow]]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from pre-grouped records (no DB)."""
    snap = CollectionSnapshot()
    snap._load_snapshot({k.casefold(): v for k, v in records_by_label.items()})
    return snap


def _empty_boundary(unit_id: int = 1) -> BoundaryRow:
    """Return a BoundaryRow marked is_empty=True."""
    return BoundaryRow(
        unit_id=unit_id,
        row=0,
        col=0,
        first_label=None,
        first_catalog=None,
        last_label=None,
        last_catalog=None,
        is_empty=True,
    )


def test_empty_cube() -> None:
    """count_records_in_boundary returns 0 for an is_empty=True boundary (CUBE-07).

    An empty cube has no records regardless of the snapshot contents.
    """
    from gruvax.estimator.boundary_math import count_records_in_boundary

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    boundary = _empty_boundary()
    count = count_records_in_boundary(boundary, snapshot)
    assert count == 0, f"Expected 0 for empty boundary, got {count}"


def test_overstuffed() -> None:
    """count_records_in_boundary can return a count exceeding nominal capacity.

    Fill level > 1.0 is possible for overstuffed cubes — count/capacity may exceed 1.0.
    The boundary math returns an integer count; the divide-by-capacity is the caller's job.
    """
    from gruvax.estimator.boundary_math import count_records_in_boundary

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

    boundary = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="Blue Note",
        last_catalog="BLP 4200",
        is_empty=False,
    )
    count = count_records_in_boundary(boundary, snapshot)
    assert count == 200, f"Expected 200 records, got {count}"
    # As a fill level: 200 / 95 > 1.0 — this is expected and valid
    assert count / 95 > 1.0, "Overstuffed cube must yield fill_level > 1.0"


def test_same_label_boundary() -> None:
    """count_records_in_boundary counts records within catalog range for same-label boundary."""
    from gruvax.estimator.boundary_math import count_records_in_boundary

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
        RecordRow(release_id=2, label="Blue Note", catalog_number="BLP 4050"),
        RecordRow(release_id=3, label="Blue Note", catalog_number="BLP 4200"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    boundary = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="Blue Note",
        last_catalog="BLP 4100",
        is_empty=False,
    )
    count = count_records_in_boundary(boundary, snapshot)
    # BLP 4001 and BLP 4050 are within range; BLP 4200 is not
    assert count == 2, f"Expected 2 records in range, got {count}"


def test_empty_snapshot() -> None:
    """count_records_in_boundary returns 0 for a non-empty boundary with no matching records."""
    from gruvax.estimator.boundary_math import count_records_in_boundary

    snapshot = _make_snapshot({})  # empty snapshot

    boundary = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="Blue Note",
        last_catalog="BLP 4195",
        is_empty=False,
    )
    count = count_records_in_boundary(boundary, snapshot)
    assert count == 0, f"Expected 0 for empty snapshot, got {count}"

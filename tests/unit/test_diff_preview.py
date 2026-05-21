"""Unit tests for diff-preview record-movement counts (ADMN-07).

Tests that record-movement counts are correctly computed from the in-memory
collection snapshot when a boundary changes — no DB hit (D-09).

Targets ``gruvax.estimator.boundary_math.count_records_in_boundary``
(implemented in Plan 01 Task 3) and the diff helper (Plan 04/05).

Analog: tests/unit/test_algorithm.py (snapshot fixture + pure computation).
"""

from __future__ import annotations

from gruvax.estimator.boundary_cache import BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow


def _make_snapshot(records_by_label: dict[str, list[RecordRow]]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from pre-grouped records (no DB)."""
    snap = CollectionSnapshot()
    snap._load_snapshot({k.casefold(): v for k, v in records_by_label.items()})
    return snap


def test_movement_counts() -> None:
    """Record-movement count is correct for a known boundary change.

    Scenario:
      - Cube A: Blue Note BLP 4001 – BLP 4100 (has 50 records)
      - Cube B: Blue Note BLP 4101 – BLP 4200 (has 50 records)
      - Change: Cube A's last_catalog moves from BLP 4100 to BLP 4150
        → 50 records move from Cube B to Cube A

    count_records_in_boundary must reflect the new range correctly.
    """
    from gruvax.estimator.boundary_math import count_records_in_boundary

    # Build a synthetic label with 100 records: BLP 4001 – BLP 4100
    records_a = [
        RecordRow(
            release_id=i,
            label="Blue Note",
            catalog_number=f"BLP {4000 + i}",
        )
        for i in range(1, 101)
    ]
    snapshot = _make_snapshot({"Blue Note": records_a})

    # Cube A: original boundary covers BLP 4001 – BLP 4050 (first 50 records)
    cube_a_original = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="Blue Note",
        last_catalog="BLP 4050",
        is_empty=False,
    )
    count_before = count_records_in_boundary(cube_a_original, snapshot)

    # Cube A: new boundary covers BLP 4001 – BLP 4075 (first 75 records)
    cube_a_new = BoundaryRow(
        unit_id=1,
        row=0,
        col=0,
        first_label="Blue Note",
        first_catalog="BLP 4001",
        last_label="Blue Note",
        last_catalog="BLP 4075",
        is_empty=False,
    )
    count_after = count_records_in_boundary(cube_a_new, snapshot)

    # 25 records moved into Cube A (from 50 → 75)
    assert count_after - count_before == 25, (
        f"Expected movement of 25 records, got {count_after - count_before}"
    )
    assert count_before == 50, f"Expected 50 records in original boundary, got {count_before}"
    assert count_after == 75, f"Expected 75 records in new boundary, got {count_after}"

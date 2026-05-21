"""Unit tests for index-space midpoint suggestion (ADMN-12).

Tests ``suggest_midpoint`` from ``gruvax.estimator.boundary_math``.
Authored RED in Plan 01 Task 2 (Wave-0 scaffold); goes GREEN when Task 3
implements ``boundary_math.py``.

Midpoint contract (D-08, Pitfall 22):
  - Walks collection-INDEX space, NOT catalog-string space
  - Returns a RecordRow that is strictly between the two anchor records by index
  - Returns None when no record lies strictly between the two anchors
  - The returned record is always a real owned record from the snapshot

Analog: tests/unit/test_algorithm.py (snapshot fixture + pure computation).
"""

from __future__ import annotations

from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow


def _make_snapshot(records_by_label: dict[str, list[RecordRow]]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from pre-grouped records (no DB)."""
    snap = CollectionSnapshot()
    snap._load_snapshot({k.casefold(): v for k, v in records_by_label.items()})
    return snap


def test_midpoint_is_real_record() -> None:
    """suggest_midpoint returns a record strictly between the two anchor indices.

    Scenario: 5 records sorted by parse_key. Anchors are index 0 and index 4.
    Midpoint index = (0 + 4) // 2 = 2 → records[2].
    """
    from gruvax.estimator.boundary_math import suggest_midpoint

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
        RecordRow(release_id=2, label="Blue Note", catalog_number="BLP 4050"),
        RecordRow(release_id=3, label="Blue Note", catalog_number="BLP 4100"),
        RecordRow(release_id=4, label="Blue Note", catalog_number="BLP 4150"),
        RecordRow(release_id=5, label="Blue Note", catalog_number="BLP 4200"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    result = suggest_midpoint(
        label="Blue Note",
        first_anchor_release_id=1,   # BLP 4001 → index 0 after sort
        last_anchor_release_id=5,    # BLP 4200 → index 4 after sort
        snapshot=snapshot,
    )
    assert result is not None, "suggest_midpoint must return a record when midpoint exists"
    # The returned record must be one of the real owned records
    record_ids = {r.release_id for r in records}
    assert result.release_id in record_ids, (
        f"Midpoint record {result.release_id} must be a real owned record"
    )
    # And strictly between the anchors (not the anchors themselves)
    assert result.release_id not in {1, 5}, (
        "Midpoint must be strictly between anchors, not an anchor itself"
    )
    # The midpoint release_id should be 3 (index 2 of the sorted list)
    assert result.release_id == 3, f"Expected release_id=3 (index 2), got {result.release_id}"


def test_midpoint_empty_range() -> None:
    """suggest_midpoint returns None when no record lies strictly between anchors.

    Scenario: only 2 records — anchor A at index 0, anchor B at index 1.
    mid = (0 + 1) // 2 = 0; not strictly between (0 < 0 < 1 is False).
    """
    from gruvax.estimator.boundary_math import suggest_midpoint

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
        RecordRow(release_id=2, label="Blue Note", catalog_number="BLP 4002"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    result = suggest_midpoint(
        label="Blue Note",
        first_anchor_release_id=1,
        last_anchor_release_id=2,
        snapshot=snapshot,
    )
    assert result is None, (
        "suggest_midpoint must return None when no record lies strictly between anchors"
    )


def test_midpoint_missing_anchor() -> None:
    """suggest_midpoint returns None when an anchor release_id is not in the snapshot."""
    from gruvax.estimator.boundary_math import suggest_midpoint

    records = [
        RecordRow(release_id=1, label="Blue Note", catalog_number="BLP 4001"),
        RecordRow(release_id=3, label="Blue Note", catalog_number="BLP 4100"),
        RecordRow(release_id=5, label="Blue Note", catalog_number="BLP 4200"),
    ]
    snapshot = _make_snapshot({"Blue Note": records})

    # release_id=999 does not exist in snapshot
    result = suggest_midpoint(
        label="Blue Note",
        first_anchor_release_id=1,
        last_anchor_release_id=999,
        snapshot=snapshot,
    )
    assert result is None, "suggest_midpoint must return None when an anchor is missing"


def test_midpoint_three_records_middle() -> None:
    """suggest_midpoint with exactly 3 records returns the middle one."""
    from gruvax.estimator.boundary_math import suggest_midpoint

    records = [
        RecordRow(release_id=10, label="ECM", catalog_number="ECM 1001"),
        RecordRow(release_id=20, label="ECM", catalog_number="ECM 1010"),
        RecordRow(release_id=30, label="ECM", catalog_number="ECM 1020"),
    ]
    snapshot = _make_snapshot({"ECM": records})

    result = suggest_midpoint(
        label="ECM",
        first_anchor_release_id=10,  # index 0
        last_anchor_release_id=30,   # index 2
        snapshot=snapshot,
    )
    assert result is not None
    # mid = (0 + 2) // 2 = 1 → release_id 20
    assert result.release_id == 20, f"Expected release_id=20 (middle), got {result.release_id}"

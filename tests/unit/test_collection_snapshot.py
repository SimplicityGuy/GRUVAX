"""Unit tests for CollectionSnapshot.

Tests the behavior described in Plan 02-01 §Task 1 <behavior>:
  - _load_snapshot() groups records by label correctly
  - get_label_records() is case-insensitive (casefold — Pitfall C)
  - get_label_records() returns [] for unknown labels
  - invalidate() empties the snapshot (Phase 4 seam)
  - CollectionSnapshot.load(pool) groups records by label from live DB
"""

from __future__ import annotations

import pytest

from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow


# ── Helper ───────────────────────────────────────────────────────────────────


def _make_snapshot(records: list[dict]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from a list of dicts (bypasses DB for unit tests)."""
    snapshot = CollectionSnapshot()
    by_label: dict[str, list[RecordRow]] = {}
    for r in records:
        key = (r.get("label") or "").casefold()
        row = RecordRow(
            release_id=r["release_id"],
            label=r.get("label") or "",
            catalog_number=r.get("catalog_number") or "",
        )
        if key not in by_label:
            by_label[key] = []
        by_label[key].append(row)
    snapshot._load_snapshot(by_label)
    return snapshot


# ── Test 1: grouping by label ─────────────────────────────────────────────────


def test_snapshot_load_groups_by_label() -> None:
    """After _load_snapshot, get_label_records returns exactly the records for that label."""
    records = [
        {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4001"},
        {"release_id": 2, "label": "Blue Note", "catalog_number": "BLP 4002"},
        {"release_id": 3, "label": "ECM", "catalog_number": "ECM 1001"},
    ]
    snapshot = _make_snapshot(records)

    bn_records = snapshot.get_label_records("Blue Note")
    assert len(bn_records) == 2, f"Expected 2 Blue Note records, got {len(bn_records)}"
    release_ids = {r.release_id for r in bn_records}
    assert release_ids == {1, 2}, f"Expected release_ids {{1, 2}}, got {release_ids}"

    ecm_records = snapshot.get_label_records("ECM")
    assert len(ecm_records) == 1
    assert ecm_records[0].release_id == 3


# ── Test 2: case-folded lookup (Pitfall C) ────────────────────────────────────


def test_snapshot_label_case_folded() -> None:
    """get_label_records('BLUE NOTE') == get_label_records('blue note') (Pitfall C).

    Labels must NEVER go through normalize_catalog() — casefold only.
    """
    records = [
        {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4001"},
        {"release_id": 2, "label": "Blue Note", "catalog_number": "BLP 4002"},
    ]
    snapshot = _make_snapshot(records)

    upper_result = snapshot.get_label_records("BLUE NOTE")
    lower_result = snapshot.get_label_records("blue note")
    canonical_result = snapshot.get_label_records("Blue Note")

    assert upper_result == canonical_result == lower_result, (
        "get_label_records must be case-insensitive (casefold)"
    )
    assert len(upper_result) == 2


# ── Test 3: unknown label returns empty ───────────────────────────────────────


def test_snapshot_unknown_label_returns_empty() -> None:
    """get_label_records('NONEXISTENT') returns [] — no KeyError."""
    records = [
        {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4001"},
    ]
    snapshot = _make_snapshot(records)

    result = snapshot.get_label_records("NONEXISTENT")
    assert result == [], f"Expected [], got {result}"


# ── Test 4: invalidate empties the snapshot ───────────────────────────────────


def test_snapshot_invalidate_empties() -> None:
    """After invalidate(), every get_label_records(...) returns [] (Phase 4 SSE seam)."""
    records = [
        {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4001"},
        {"release_id": 2, "label": "ECM", "catalog_number": "ECM 1001"},
    ]
    snapshot = _make_snapshot(records)

    # Verify data is present before invalidation
    assert len(snapshot.get_label_records("Blue Note")) == 1
    assert len(snapshot.get_label_records("ECM")) == 1

    snapshot.invalidate()

    # After invalidation all queries must return []
    assert snapshot.get_label_records("Blue Note") == [], (
        "After invalidate(), Blue Note records must be empty"
    )
    assert snapshot.get_label_records("ECM") == [], (
        "After invalidate(), ECM records must be empty"
    )
    assert snapshot.get_label_records("NONEXISTENT") == []


# ── Test 5: live DB load ──────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_snapshot_load_from_db(db_pool: object) -> None:  # type: ignore[type-arg]
    """CollectionSnapshot.load(pool) must populate records from the seeded DB.

    Uses loop_scope="session" so this test shares the same event loop as the
    session-scoped db_pool fixture (required by pytest-asyncio 1.x).

    Verifies that at least one known label from the seed data resolves to >= 1 record.
    """
    snapshot = CollectionSnapshot()
    await snapshot.load(db_pool)  # type: ignore[arg-type]

    # Blue Note BLP series is seeded in fixtures/synth_collection.sql
    blue_note_records = snapshot.get_label_records("Blue Note")
    assert len(blue_note_records) >= 1, (
        f"Expected at least 1 Blue Note record from DB, got {len(blue_note_records)}"
    )

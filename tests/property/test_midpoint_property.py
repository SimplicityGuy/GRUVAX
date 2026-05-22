"""Hypothesis property tests for the midpoint suggestion algorithm (ADMN-12).

Invariants:
  1. When suggest_midpoint returns a record, it is an element of the label's records
     in the snapshot (always a real owned record — Pitfall 22)
  2. When suggest_midpoint returns a record, its index is strictly between the
     indices of the two anchor records (after parse_key sort)
  3. suggest_midpoint returns None when fewer than 3 records exist in the label

These tests target ``gruvax.estimator.boundary_math.suggest_midpoint``.
Authored RED in Plan 01 Task 2; goes GREEN when Task 3 implements boundary_math.py.

Analog: tests/property/test_parser_props.py (Hypothesis @given + @settings pattern).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow

# ── Strategy helpers ──────────────────────────────────────────────────────────

_CATALOG_N_STRATEGY = st.integers(min_value=1, max_value=500)

_LABEL_STRATEGY = st.text(
    alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    min_size=2,
    max_size=10,
)


def _make_snapshot_from_label(label: str, records: list[RecordRow]) -> CollectionSnapshot:
    """Build a CollectionSnapshot with one label group."""
    snap = CollectionSnapshot()
    snap._load_snapshot({label.casefold(): records})
    return snap


# ── Property 1: midpoint is a real owned record ───────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    record_nums=st.lists(
        _CATALOG_N_STRATEGY,
        min_size=3,
        max_size=30,
        unique=True,
    ).map(sorted),
)
@settings(max_examples=200)
def test_midpoint_is_real_record_property(label: str, record_nums: list[int]) -> None:
    """When suggest_midpoint returns a record, it must be a real record in the snapshot.

    The returned record's release_id must match one of the records in the label's group.
    This prevents Pitfall 22: midpoint must never be a synthesized phantom string.
    """
    from gruvax.estimator.boundary_math import suggest_midpoint

    records = [
        RecordRow(
            release_id=n,
            label=label,
            catalog_number=f"CAT {n}",
        )
        for n in record_nums
    ]
    snapshot = _make_snapshot_from_label(label, records)

    first_anchor_id = records[0].release_id
    last_anchor_id = records[-1].release_id

    result = suggest_midpoint(
        label=label,
        first_anchor_release_id=first_anchor_id,
        last_anchor_release_id=last_anchor_id,
        snapshot=snapshot,
    )

    if result is not None:
        record_ids = {r.release_id for r in records}
        assert result.release_id in record_ids, (
            f"Midpoint record {result.release_id!r} must be a real owned record"
            f" (Pitfall 22: never a phantom)"
        )


# ── Property 2: midpoint index is strictly between anchors ────────────────────


@given(
    label=_LABEL_STRATEGY,
    record_nums=st.lists(
        _CATALOG_N_STRATEGY,
        min_size=3,
        max_size=30,
        unique=True,
    ).map(sorted),
)
@settings(max_examples=200)
def test_midpoint_index_strictly_between(label: str, record_nums: list[int]) -> None:
    """When suggest_midpoint returns a record, its sort-order index is strictly between anchors.

    After sorting by parse_key, the midpoint's index must satisfy i_a < mid < i_b.
    """
    from gruvax.estimator.boundary_math import suggest_midpoint
    from gruvax.estimator.normalize import parse_key

    records = [
        RecordRow(
            release_id=n,
            label=label,
            catalog_number=f"CAT {n}",
        )
        for n in record_nums
    ]
    snapshot = _make_snapshot_from_label(label, records)

    first_anchor_id = records[0].release_id
    last_anchor_id = records[-1].release_id

    result = suggest_midpoint(
        label=label,
        first_anchor_release_id=first_anchor_id,
        last_anchor_release_id=last_anchor_id,
        snapshot=snapshot,
    )

    if result is None:
        return  # None is valid when no record lies strictly between anchors

    # Sort the records by parse_key to find indices
    sorted_records = sorted(records, key=lambda r: parse_key(r.catalog_number))
    ids = [r.release_id for r in sorted_records]

    i_a = ids.index(first_anchor_id) if first_anchor_id in ids else None
    i_b = ids.index(last_anchor_id) if last_anchor_id in ids else None
    i_mid = ids.index(result.release_id) if result.release_id in ids else None

    if i_a is None or i_b is None or i_mid is None:
        return  # Anchor not found — suggest_midpoint correctly returned None

    assert i_a < i_mid < i_b, (
        f"Midpoint index {i_mid} must be strictly between anchor indices "
        f"{i_a} and {i_b} (D-08, index-space walk)"
    )


# ── Property 3: None when fewer than 3 records ────────────────────────────────


@given(
    label=_LABEL_STRATEGY,
    record_nums=st.lists(
        _CATALOG_N_STRATEGY,
        min_size=2,
        max_size=2,
        unique=True,
    ).map(sorted),
)
@settings(max_examples=100)
def test_midpoint_none_for_two_records(label: str, record_nums: list[int]) -> None:
    """suggest_midpoint returns None when only 2 records exist (no room for a midpoint).

    With exactly 2 records (index 0 and 1), mid=(0+1)//2=0 which is NOT strictly
    between 0 and 1, so the function returns None.
    """
    from gruvax.estimator.boundary_math import suggest_midpoint

    records = [
        RecordRow(
            release_id=n,
            label=label,
            catalog_number=f"CAT {n}",
        )
        for n in record_nums
    ]
    snapshot = _make_snapshot_from_label(label, records)

    result = suggest_midpoint(
        label=label,
        first_anchor_release_id=records[0].release_id,
        last_anchor_release_id=records[1].release_id,
        snapshot=snapshot,
    )
    assert result is None, (
        "suggest_midpoint must return None when only 2 records exist "
        "(no record strictly between anchors at index 0 and 1)"
    )

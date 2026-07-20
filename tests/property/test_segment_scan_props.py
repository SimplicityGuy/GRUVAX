"""Hypothesis property tests for SegmentCache's record→bin scan (gruvax-trl).

The cut-key scan must be robust to two invariant breaks that previously caused
silent misfiling on the shipped dev fixture:

  M1 — empty (null-cut) bins interspersed mid-shelf must never capture records.
  M2 — the physical (unit, row, col) walk order need not match global cut-key
       order; a later physical cube may carry an alphabetically-earlier cut. Every
       record must still land in the cube whose cut point it actually follows.

Core invariants asserted for any single-label-per-cube layout, regardless of how
the cubes are permuted across physical positions and how many empty cubes are
interspersed:

  * Conservation — no record is dropped: the summed segment counts equal the
    number of input records.
  * Correct cube — each label's records resolve to exactly the one cube whose cut
    point is that label, with the full record count.
  * Empty cubes stay empty.
"""

from __future__ import annotations

import string

from hypothesis import given, settings, strategies as st

from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.segment_cache import SegmentCache


@st.composite
def _shelf_layouts(draw):  # type: ignore[no-untyped-def]
    """Draw a shelf: distinct single-letter labels + interspersed empty cubes.

    Each label owns one cube whose cut point is that label's first (smallest-key)
    record. The cubes are then placed at physical coordinates in a DRAWN
    permutation, so cut-key order and physical-walk order are decoupled — exactly
    the M2 condition. ``n_empty`` empty cubes are mixed in to exercise M1.
    """
    letters = draw(
        st.lists(st.sampled_from(string.ascii_uppercase), min_size=1, max_size=6, unique=True)
    )
    label_records: dict[str, list[RecordRow]] = {}
    rid = 1
    for letter in letters:
        k = draw(st.integers(min_value=1, max_value=5))
        label_records[letter.casefold()] = [
            RecordRow(release_id=rid + i, label=letter, catalog_number=f"{letter} {i:04d}")
            for i in range(k)
        ]
        rid += k

    n_empty = draw(st.integers(min_value=0, max_value=3))

    # Cube specs: (first_label, first_catalog, is_empty)
    cubes: list[tuple[str | None, str | None, bool]] = [
        (letter, f"{letter} 0000", False) for letter in letters
    ]
    cubes += [(None, None, True) for _ in range(n_empty)]

    order = draw(st.permutations(list(range(len(cubes)))))
    return letters, label_records, cubes, order


@given(layout=_shelf_layouts())
@settings(max_examples=150, deadline=None)
def test_scan_robust_to_physical_disorder_and_empty_bins(layout) -> None:  # type: ignore[no-untyped-def]
    """gruvax-trl: assignment is correct under arbitrary physical order + empties."""
    letters, label_records, cubes, order = layout

    # Place cube ``cubes[order[slot]]`` at physical slot ``slot`` (unit 1, 4x4 grid;
    # at most 6 + 3 = 9 cubes, so a single unit's 16 slots always suffice).
    rows: list[BoundaryRow] = []
    for slot, cube_idx in enumerate(order):
        first_label, first_catalog, is_empty = cubes[cube_idx]
        rows.append(
            BoundaryRow(
                unit_id=1,
                row=slot // 4,
                col=slot % 4,
                first_label=first_label,
                first_catalog=first_catalog,
                is_empty=is_empty,
            )
        )

    cache = BoundaryCache()
    cache._load_rows(rows)
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot(label_records)

    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    total_input = sum(len(recs) for recs in label_records.values())

    # Conservation: no record dropped.
    total_assigned = sum(seg.segment_count for b in sc._bins for seg in b.segments)
    assert total_assigned == total_input, (
        f"records dropped: assigned {total_assigned} of {total_input}"
    )

    # Correct cube: each label resolves to exactly its own cube with full count.
    for letter in letters:
        key = letter.casefold()
        bins = sc.get_bins_for_label(letter)
        assert len(bins) == 1, f"label {letter!r} must occupy exactly one cube, got {len(bins)}"
        cut = bins[0].cut_label
        assert cut is not None and cut.casefold() == key, (
            f"label {letter!r} landed in a cube cut by {cut!r}"
        )
        seg = next(s for s in bins[0].segments if s.label.casefold() == key)
        assert seg.segment_count == len(label_records[key])

    # Empty cubes stay empty.
    for b in sc._bins:
        if b.cut_label is None:
            assert b.segments == (), "an empty cube derived non-empty segments"


@given(layout=_shelf_layouts())
@settings(max_examples=100, deadline=None)
def test_per_bin_fractions_sum_to_one_under_disorder(layout) -> None:  # type: ignore[no-untyped-def]
    """Every non-empty derived bin's applied_fractions still sum to 1.0 (SEG-04)."""
    _letters, label_records, cubes, order = layout

    rows: list[BoundaryRow] = []
    for slot, cube_idx in enumerate(order):
        first_label, first_catalog, is_empty = cubes[cube_idx]
        rows.append(
            BoundaryRow(
                unit_id=1,
                row=slot // 4,
                col=slot % 4,
                first_label=first_label,
                first_catalog=first_catalog,
                is_empty=is_empty,
            )
        )

    cache = BoundaryCache()
    cache._load_rows(rows)
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot(label_records)

    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    for b in sc._bins:
        if b.segments:
            total = sum(seg.applied_fraction for seg in b.segments)
            assert abs(total - 1.0) < 1e-6, (
                f"bin ({b.unit_id},{b.row},{b.col}) fractions sum to {total}"
            )

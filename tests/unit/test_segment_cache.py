"""Unit tests for SegmentCache (SEG-02, SEG-03, SEG-04, SEG-05).

SEG-02: SegmentCache.derive() produces correct ordered per-label segments
SEG-03: Counts from row-counting v_collection, not catalog arithmetic
SEG-04: Override wins over count-derived fraction; widths sum to 100%
SEG-05: Contiguity validator rejects non-adjacent scatter (Wave 4 — 05-04)

Per-Requirement coverage:
  SEG-02: test_segment_cache_derive_single_label + test_segment_cache_segments_ordered
  SEG-03: test_row_count_not_arithmetic
  SEG-04: test_override_applied + test_override_renormalization_sums_to_one
  SEG-05: test_contiguity_validation (SKIPPED — Plan 05-04)

Test names referenced in 05-VALIDATION.md § Per-Requirement Verification Map.
"""

from __future__ import annotations

import pytest

from fixtures.synth_collection import make_multi_label_bin, make_straddle
from gruvax.estimator.collection_snapshot import RecordRow


# ── Session-scoped synth fixtures ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def multi_label_bin_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped multi-label bin cache + segment_cache + snapshot (no DB)."""
    return make_multi_label_bin()


@pytest.fixture(scope="session")
def straddle_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped straddle (one label, two bins) cache + segment_cache + snapshot."""
    return make_straddle()


# ── SEG-02: SegmentCache.derive() produces correct segments ───────────────────


def test_segment_cache_derive_single_label(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-02: SegmentCache.derive() produces ordered per-label segments for each bin.

    Requirement: SEG-02 — derive per-bin ordered per-label segments from cut points
    via row-counting v_collection, zero additional manual input.

    Pitfall 5 discipline: assert SegmentCache state (bin count, segment count,
    label membership) before asserting derived values.
    """
    from gruvax.estimator.segment_cache import SegmentCache

    cache, _, snapshot = multi_label_bin_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    # Pitfall 5: pre-check SegmentCache structure before asserting values
    assert len(sc._bins) == 1, f"Expected 1 bin, got {len(sc._bins)}"
    bin_ = sc._bins[0]
    assert bin_.unit_id == 1 and bin_.row == 0 and bin_.col == 0, (
        f"Bin coordinates mismatch: {bin_.unit_id},{bin_.row},{bin_.col}"
    )

    # All bins with cut points should have at least one segment
    for bin_ in sc._bins:
        assert len(bin_.segments) >= 1, (
            f"Bin ({bin_.unit_id},{bin_.row},{bin_.col}) has no segments"
        )

    # The single bin should have exactly 2 segments (LabelA and LabelB)
    bin_ = sc._bins[0]
    assert len(bin_.segments) == 2, f"Expected 2 segments in bin (1,0,0), got {len(bin_.segments)}"


def test_segment_cache_segments_ordered(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-02: Segments within a bin are ordered by global (label casefold, parse_key).

    Requirement: SEG-02 — ordered per-label segments.

    Pitfall 5: assert bin exists and has segments before asserting order.
    """
    from gruvax.estimator.segment_cache import SegmentCache

    cache, _, snapshot = multi_label_bin_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    # Pitfall 5: pre-check bin exists with segments
    assert len(sc._bins) >= 1, "Expected at least one bin"
    bin_ = sc._bins[0]
    assert len(bin_.segments) >= 2, f"Expected at least 2 segments, got {len(bin_.segments)}"

    # Assert first segment is LabelA (casefold "labela" < "labelb")
    first_label = bin_.segments[0].label.casefold()
    second_label = bin_.segments[1].label.casefold()
    assert first_label == "labela", f"First segment should be labela, got {first_label}"
    assert second_label == "labelb", f"Second segment should be labelb, got {second_label}"

    # Assert general ordering invariant: segments are sorted by label casefold
    for bin_ in sc._bins:
        labels = [seg.label.casefold() for seg in bin_.segments]
        assert labels == sorted(labels), (
            f"Segments not ordered by label in bin ({bin_.unit_id},{bin_.row},{bin_.col})"
        )


# ── SEG-03: Row-count not arithmetic ─────────────────────────────────────────


def test_row_count_not_arithmetic(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-03: Counts from v_collection row-counts — NOT catalog arithmetic.

    Requirement: SEG-03 — per-segment counts computed by row-counting v_collection
    including dupes + variants (LB 003, LB 003 duplicate copy, LB 003-r), never
    catalog arithmetic.

    The multi_label_bin factory includes:
    - LabelB: "LB 003" appears twice (duplicate owned copy)
    - LabelB: "LB 003-r" (remix variant)
    These 3 records must be counted as 3 (not 1 unique catalog).
    Total LabelB count = 6.

    Pitfall 5: assert segment exists and SegmentCache state before asserting count.
    """
    from gruvax.estimator.segment_cache import SegmentCache

    cache, _, snapshot = multi_label_bin_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    # Pitfall 5: assert bin and segment structure first
    assert len(sc._bins) == 1, f"Expected 1 bin, got {len(sc._bins)}"
    bin_ = sc._bins[0]
    assert len(bin_.segments) == 2, f"Expected 2 segments, got {len(bin_.segments)}"

    # Find LabelB's segment in the bin
    label_b_segs = [
        seg for bin_ in sc._bins for seg in bin_.segments if seg.label.casefold() == "labelb"
    ]
    assert len(label_b_segs) == 1, f"Expected 1 LabelB segment, got {len(label_b_segs)}"
    seg = label_b_segs[0]

    # Assert the pre-state: first_rank should be 0 (LabelB starts at rank 0 in its sorted list)
    assert seg.first_rank_in_label == 0, (
        f"LabelB first_rank_in_label should be 0, got {seg.first_rank_in_label}"
    )

    # Core assertion: LabelB has 6 records (including duplicate "LB 003" and "LB 003-r")
    # This would fail if counting used parse_key subtraction (which would give ~5 unique keys)
    assert seg.segment_count == 6, (
        f"LabelB segment_count should be 6 (row-count including dupes+variants), got {seg.segment_count}"
    )

    # Verify LabelA also has correct count (8 records, no duplicates)
    label_a_segs = [
        seg for bin_ in sc._bins for seg in bin_.segments if seg.label.casefold() == "labela"
    ]
    assert len(label_a_segs) == 1, f"Expected 1 LabelA segment, got {len(label_a_segs)}"
    assert label_a_segs[0].segment_count == 8, (
        f"LabelA segment_count should be 8, got {label_a_segs[0].segment_count}"
    )


# ── SEG-04: Override wins; widths sum to 1.0 ─────────────────────────────────


def test_override_applied(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-04: Admin physical-width override wins over count-derived fraction.

    Requirement: SEG-04 — optional admin physical-width override per label-segment
    takes precedence over count-derived auto_fraction.

    Pitfall 5: assert SegmentCache structure and auto_fraction before asserting
    override application.
    """
    from gruvax.estimator.segment_cache import SegmentCache

    cache, _, snapshot = multi_label_bin_fixture

    # Inject a physical-width override for LabelA at (1,0,0)
    overrides = {(1, 0, 0, "LabelA"): 0.6}

    sc = SegmentCache()
    sc.derive(cache, snapshot, overrides)

    # Pitfall 5: pre-check SegmentCache structure before asserting override
    assert len(sc._bins) == 1, "Expected 1 bin"
    bin_ = sc._bins[0]
    assert len(bin_.segments) == 2, "Expected 2 segments"

    # Find LabelA's segment in the bin at (1,0,0)
    label_a_segs = [
        seg
        for bin_ in sc._bins
        if bin_.unit_id == 1 and bin_.row == 0 and bin_.col == 0
        for seg in bin_.segments
        if seg.label.casefold() == "labela"
    ]
    assert len(label_a_segs) == 1, "Expected exactly one LabelA segment in bin (1,0,0)"
    seg = label_a_segs[0]

    # Pre-check: auto_fraction should be 8/14 ≈ 0.5714 (before override)
    expected_auto = 8 / 14
    assert abs(seg.auto_fraction - expected_auto) < 1e-6, (
        f"LabelA auto_fraction should be {expected_auto:.6f}, got {seg.auto_fraction:.6f}"
    )

    # Core assertions: override wins
    assert seg.is_override, "LabelA segment should be marked is_override=True"
    assert abs(seg.applied_fraction - 0.6) < 1e-6, (
        f"LabelA applied_fraction should be 0.6 (override), got {seg.applied_fraction}"
    )


def test_override_renormalization_sums_to_one(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-04: Per-bin applied_fractions always sum to 1.0 even with overrides.

    Pitfall 2: When one segment is overridden, remaining non-overridden segments
    must be renormalized to fill the remaining space. Sum must still equal 1.0
    within 1e-6.

    Pitfall 5: assert SegmentCache state before asserting sum.
    """
    from gruvax.estimator.segment_cache import SegmentCache

    cache, _, snapshot = multi_label_bin_fixture

    # Override LabelA at 60% — LabelB auto should get the remaining 40%
    overrides = {(1, 0, 0, "LabelA"): 0.6}

    sc = SegmentCache()
    sc.derive(cache, snapshot, overrides)

    # Pitfall 5: pre-check structure before asserting sum
    assert len(sc._bins) >= 1, "Expected at least one bin"
    for bin_ in sc._bins:
        assert len(bin_.segments) >= 1, (
            f"Bin ({bin_.unit_id},{bin_.row},{bin_.col}) has no segments"
        )

    # Core assertion: per-bin applied_fractions sum to 1.0 with override active
    for bin_ in sc._bins:
        total = sum(seg.applied_fraction for seg in bin_.segments)
        assert abs(total - 1.0) < 1e-6, (
            f"Bin ({bin_.unit_id},{bin_.row},{bin_.col}) fractions sum to {total} (should be 1.0 within 1e-6)"
        )

    # Also verify LabelB was renormalized correctly (should get remaining 0.4)
    label_b_segs = [
        seg for bin_ in sc._bins for seg in bin_.segments if seg.label.casefold() == "labelb"
    ]
    assert len(label_b_segs) == 1
    seg_b = label_b_segs[0]
    assert not seg_b.is_override, "LabelB should NOT be marked is_override"
    assert abs(seg_b.applied_fraction - 0.4) < 1e-6, (
        f"LabelB applied_fraction should be 0.4 (renormalized), got {seg_b.applied_fraction}"
    )


# ── SEG-05: Contiguity invariant ──────────────────────────────────────────────


def test_contiguity_validation() -> None:
    """SEG-05: Contiguity validator rejects cuts scattering a label across non-adjacent bins.

    Requirement: SEG-05 — label-contiguity invariant enforced by save-validator;
    non-adjacent scatter is hard-rejected; adjacent multi-bin spans are valid (D-09).

    Two cases tested:

    Case 1 — Non-adjacent scatter (rejected):
      Proposing: (1,0,0)=Blue Note, (1,0,1)=ECM, (1,0,2)=Blue Note
      Blue Note would be split across non-adjacent bins (ECM between them) → rejected.

    Case 2 — Adjacent multi-bin span (accepted):
      Proposing: (1,0,0)=Blue Note, (1,0,1)=Blue Note
      Blue Note occupies adjacent bins (no other label between them) → accepted.

    Note: Simply not including a bin in proposed_updates (e.g. proposing only bins 0
    and 2) is NOT a scatter if the omitted bin (1,0,1) retains its current Blue Note
    cut point — the label is still contiguous.  A real scatter requires a DIFFERENT
    label to appear between two Blue Note bins in the proposed cut sequence.
    """
    from gruvax.api.admin.validation import validate_contiguity
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
    from gruvax.estimator.segment_cache import SegmentCache

    # Build a 3-bin BoundaryCache with 3 different labels
    cache = BoundaryCache()
    cache._load_rows(
        [
            BoundaryRow(
                unit_id=1,
                row=0,
                col=0,
                first_label="Blue Note",
                first_catalog="BLP 4001",
                is_empty=False,
            ),
            BoundaryRow(
                unit_id=1, row=0, col=1, first_label="ECM", first_catalog="ECM 1001", is_empty=False
            ),
            BoundaryRow(
                unit_id=1,
                row=0,
                col=2,
                first_label="Blue Note",
                first_catalog="BLP 4011",
                is_empty=False,
            ),
        ]
    )

    # Synthetic records for each label
    records_bn_1 = [
        RecordRow(release_id=i, label="Blue Note", catalog_number=f"BLP {4000 + i}")
        for i in range(1, 11)
    ]
    records_ecm = [
        RecordRow(release_id=100 + i, label="ECM", catalog_number=f"ECM {1000 + i}")
        for i in range(1, 11)
    ]
    records_bn_2 = [
        RecordRow(release_id=200 + i, label="Blue Note", catalog_number=f"BLP {4010 + i}")
        for i in range(1, 11)
    ]
    snap = CollectionSnapshot()
    snap._load_snapshot(
        {
            "blue note": records_bn_1 + records_bn_2,
            "ecm": records_ecm,
        }
    )

    sc = SegmentCache()
    sc.derive(cache, snap, {})

    # Case 1: Non-adjacent scatter — Blue Note in (1,0,0) and (1,0,2) with ECM at (1,0,1)
    proposed_non_adjacent: list[dict[str, object]] = [
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": "Blue Note",
            "first_catalog": "BLP 4001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 1,
            "first_label": "ECM",
            "first_catalog": "ECM 1001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 2,
            "first_label": "Blue Note",
            "first_catalog": "BLP 4011",
            "is_empty": False,
        },
    ]
    result_non_adjacent = validate_contiguity(proposed_non_adjacent, sc)
    assert result_non_adjacent is not None, (
        "validate_contiguity must reject non-adjacent label scatter (SEG-05): "
        "Blue Note at bins 0+2 with ECM at bin 1 should be rejected"
    )
    assert (
        "non-adjacent" in result_non_adjacent.lower() or "split" in result_non_adjacent.lower()
    ), f"Error message must reference the contiguity problem: {result_non_adjacent}"

    # Case 2: Adjacent span — Blue Note in adjacent bins (1,0,0) and (1,0,1) — valid
    proposed_adjacent: list[dict[str, object]] = [
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": "Blue Note",
            "first_catalog": "BLP 4001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 1,
            "first_label": "Blue Note",
            "first_catalog": "BLP 4011",
            "is_empty": False,
        },
    ]
    result_adjacent = validate_contiguity(proposed_adjacent, sc)
    assert result_adjacent is None, (
        f"validate_contiguity must accept adjacent multi-bin spans (SEG-05 D-09), got: {result_adjacent}"
    )


# ── gruvax-trl: cut-key scan robustness (empty bins + physical disorder) ──────


def _derive(rows, records):  # type: ignore[no-untyped-def]
    """Helper: build a SegmentCache from raw BoundaryRow + label→records inputs."""
    from gruvax.estimator.boundary_cache import BoundaryCache
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache

    cache = BoundaryCache()
    cache._load_rows(rows)
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot(records)
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})
    return sc


def test_empty_bin_does_not_swallow_preceding_cube() -> None:
    """gruvax-trl M1: a mid-shelf empty bin must not capture (and drop) records.

    Before the fix, ``_cut_key`` returned the global-minimum sentinel
    ``("", ((-1, 0),))`` for an empty bin, so it satisfied ``cut_key <= rec_key``
    for every record and — being later in the physical walk — won assignment; the
    build loop then dropped those records as empty. The preceding non-empty cube
    derived ZERO records. The empty bin is placed BETWEEN two occupied cubes,
    exactly the deliberate mid-shelf empty layout in fixtures/boundaries.yaml.
    """
    from gruvax.estimator.boundary_cache import BoundaryRow

    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label="Riverside",
            first_catalog="RLP 1000",
            is_empty=False,
        ),
        BoundaryRow(unit_id=1, row=0, col=1, first_label=None, first_catalog=None, is_empty=True),
        BoundaryRow(
            unit_id=1, row=0, col=2, first_label="Verve", first_catalog="MGV 1000", is_empty=False
        ),
    ]
    records = {
        "riverside": [
            RecordRow(release_id=i, label="Riverside", catalog_number=f"RLP {1000 + i}")
            for i in range(1, 6)
        ],
        "verve": [
            RecordRow(release_id=10 + i, label="Verve", catalog_number=f"MGV {1000 + i}")
            for i in range(1, 4)
        ],
    }
    sc = _derive(rows, records)

    riverside_bin = sc.get_bin(1, 0, 0)
    assert riverside_bin is not None
    assert len(riverside_bin.segments) == 1, "Riverside cube must keep its single segment"
    assert riverside_bin.segments[0].segment_count == 5, (
        "the mid-shelf empty bin swallowed the preceding cube's records (M1 regression)"
    )

    empty_bin = sc.get_bin(1, 0, 1)
    assert empty_bin is not None
    assert empty_bin.segments == (), "empty cube must stay empty"

    verve_bin = sc.get_bin(1, 0, 2)
    assert verve_bin is not None
    assert verve_bin.segments[0].segment_count == 3

    # Conservation: no record dropped.
    total = sum(seg.segment_count for b in sc._bins for seg in b.segments)
    assert total == 8, f"records were dropped by the scan: got {total}, expected 8"


def test_cross_unit_disorder_assigns_correct_cube_and_warns(caplog) -> None:  # type: ignore[no-untyped-def]
    """gruvax-trl M2: an alphabetically-earlier cut in a later physical unit.

    Unit 2's "Padding" cut sorts BEFORE unit 1's later "Riverside"/"Verve" cuts.
    The old physical-order scan stopped at the first cut greater than the record
    and misfiled Padding into an earlier unit-1 cube at high confidence. Records
    must instead land in the cube whose cut point they actually follow — here
    unit 2 (2,0,0) — and the disorder must be surfaced with a loud warning rather
    than a silent misfile.
    """
    import logging

    from gruvax.estimator.boundary_cache import BoundaryRow

    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label="Riverside",
            first_catalog="RLP 1000",
            is_empty=False,
        ),
        BoundaryRow(
            unit_id=1, row=0, col=1, first_label="Verve", first_catalog="MGV 1000", is_empty=False
        ),
        BoundaryRow(
            unit_id=2, row=0, col=0, first_label="Padding", first_catalog="PAD 0001", is_empty=False
        ),
    ]
    records = {
        "riverside": [
            RecordRow(release_id=i, label="Riverside", catalog_number=f"RLP {1000 + i}")
            for i in range(1, 4)
        ],
        "verve": [
            RecordRow(release_id=10 + i, label="Verve", catalog_number=f"MGV {1000 + i}")
            for i in range(1, 4)
        ],
        "padding": [
            RecordRow(release_id=20 + i, label="Padding", catalog_number=f"PAD {i:04d}")
            for i in range(1, 4)
        ],
    }

    with caplog.at_level(logging.WARNING, logger="gruvax.estimator.segment_cache"):
        sc = _derive(rows, records)

    # Padding lands in its own physically-later cube, NOT an earlier unit-1 cube.
    padding_bins = sc.get_bins_for_label("Padding")
    assert [(b.unit_id, b.row, b.col) for b in padding_bins] == [(2, 0, 0)], (
        "Padding records misfiled into the wrong unit (M2 regression)"
    )
    padding_bin = sc.get_bin(2, 0, 0)
    assert padding_bin is not None and padding_bin.segments[0].segment_count == 3

    # Unit-1 cubes keep exactly their own records — no Padding contamination.
    assert sc.get_bin(1, 0, 0).segments[0].label == "riverside"  # type: ignore[union-attr]
    assert sc.get_bin(1, 0, 1).segments[0].label == "verve"  # type: ignore[union-attr]

    # Conservation across all cubes.
    total = sum(seg.segment_count for b in sc._bins for seg in b.segments)
    assert total == 9

    # The physical disorder was surfaced loudly.
    assert any("not monotonically non-decreasing" in rec.message for rec in caplog.records), (
        "cross-unit disorder must emit a loud warning, not misfile silently"
    )


def test_monotonic_layout_emits_no_warning(caplog) -> None:  # type: ignore[no-untyped-def]
    """A well-ordered shelf (with a trailing empty) derives cleanly and silently."""
    import logging

    from gruvax.estimator.boundary_cache import BoundaryRow

    rows = [
        BoundaryRow(
            unit_id=1, row=0, col=0, first_label="Alpha", first_catalog="A 001", is_empty=False
        ),
        BoundaryRow(
            unit_id=1, row=0, col=1, first_label="Bravo", first_catalog="B 001", is_empty=False
        ),
        BoundaryRow(unit_id=1, row=0, col=2, first_label=None, first_catalog=None, is_empty=True),
    ]
    records = {
        "alpha": [
            RecordRow(release_id=i, label="Alpha", catalog_number=f"A {i:03d}") for i in range(1, 4)
        ],
        "bravo": [
            RecordRow(release_id=10 + i, label="Bravo", catalog_number=f"B {i:03d}")
            for i in range(1, 4)
        ],
    }
    with caplog.at_level(logging.WARNING, logger="gruvax.estimator.segment_cache"):
        sc = _derive(rows, records)

    assert not any("not monotonically non-decreasing" in rec.message for rec in caplog.records), (
        "a monotonic layout must not warn"
    )
    total = sum(seg.segment_count for b in sc._bins for seg in b.segments)
    assert total == 6

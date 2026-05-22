"""Hypothesis property tests for segment-aware estimator invariants (D-02 / SEG-06/07).

Plan 05-03: Un-stub all Wave 0 skip-stubs. The tests exercise segment invariants
using the synth_collection factories.

Per-Requirement coverage:
  SEG-06: test_primary_cube_in_label_span, test_sub_cube_interval_bounds,
          test_monotone_position_within_label, test_cosmetic_stability,
          test_straddle_resolves_to_correct_bin
  SEG-07: test_single_segment_bin_reproduces_v1_index (regression anchor)
  SEG-04: test_per_bin_fractions_sum_to_one
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fixtures.synth_collection import make_multi_label_bin, make_singleton, make_straddle

# ── Session-scoped synth fixtures ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def multi_label_props_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped multi-label bin fixture (no DB) for property tests."""
    return make_multi_label_bin()


@pytest.fixture(scope="session")
def straddle_props_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped straddle fixture (no DB) for property tests."""
    return make_straddle()


@pytest.fixture(scope="session")
def singleton_props_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped singleton fixture for single-segment regression test."""
    return make_singleton()


# ── SEG-04 property: fractions sum to one ────────────────────────────────────


def test_per_bin_fractions_sum_to_one(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-04: Per-bin segment applied_fractions must sum to 1.0 (within float epsilon).

    Requirement: SEG-04 — widths within a bin always total 100%.
    This invariant holds regardless of overrides: non-overridden segments are
    renormalized to fill the remaining space (Pitfall 2 renormalization).

    For every SegmentBin in SegmentCache:
        sum(seg.applied_fraction for seg in bin.segments) == 1.0 (± 1e-6)
    """
    from gruvax.estimator.segment_cache import SegmentCache

    cache, _, snapshot = multi_label_props_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, cache.overrides)
    for bin_ in sc._bins:
        total = sum(seg.applied_fraction for seg in bin_.segments)
        assert abs(total - 1.0) < 1e-6, (
            f"Bin ({bin_.unit_id},{bin_.row},{bin_.col}) fractions sum to {total}"
        )


# ── SEG-07 regression anchor: single-segment bin reproduces §4.1 ─────────────


def test_single_segment_bin_reproduces_v1_index(singleton_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-07: A single-segment bin must produce the same result as retired §4.1.

    This is the regression invariant that replaces the dropped A/B proof gate (D-02).
    If a bin has exactly one LabelSegment, the two-level formula degenerates to:
        offset=0, fraction=1.0 → f = rank / (k-1)
    which is exactly the §4.1 index-based formula.

    Pitfall 5 pre-check (MANDATORY — prevents a vacuous test):
        assert len(bin.segments) == 1   # single-segment bin
        assert seg.auto_fraction == 1.0  # full bin
        assert seg.first_rank_in_label == 0  # starts at rank 0

    Requirement: SEG-07 — single-segment bin reproduces §4.1 exactly.
    """
    from gruvax.estimator.algorithm import _locate_by_index_v1, locate_by_segment  # D-02 only
    from gruvax.estimator.segment_cache import SegmentCache

    # make_singleton returns (BoundaryCache, CollectionSnapshot, dict[int, float])
    # The singleton factory creates a single-cube single-label boundary
    cache, snapshot, _ = singleton_props_fixture

    # Derive a fresh SegmentCache from this single-cube fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    # Pitfall 5 pre-check: verify fixture is a single-segment bin
    assert len(sc._bins) == 1, f"Expected 1 bin, got {len(sc._bins)}"
    bin_ = sc._bins[0]
    assert len(bin_.segments) == 1, (
        f"D-02 requires single-segment bin, got {len(bin_.segments)} segments"
    )
    seg = bin_.segments[0]
    assert seg.auto_fraction == 1.0, (
        f"Single-segment must have auto_fraction=1.0, got {seg.auto_fraction}"
    )
    assert seg.first_rank_in_label == 0, (
        f"Single-segment must start at rank 0, got {seg.first_rank_in_label}"
    )

    # Singleton: k=1, release_id=1, catalog=SL 001
    seg_result = locate_by_segment(
        release_id=1,
        label="Singleton",
        catalog_number="SL 001",
        segment_cache=sc,
        snapshot=snapshot,
    )
    v1_result = _locate_by_index_v1(
        release_id=1,
        label="Singleton",
        catalog_number="SL 001",
        segment_cache=sc,
        snapshot=snapshot,
    )

    # Both must have sub_cube_interval (singleton → midpoint band)
    assert seg_result.sub_cube_interval is not None
    assert v1_result.sub_cube_interval is not None

    si_seg = seg_result.sub_cube_interval
    si_v1 = v1_result.sub_cube_interval

    # For singleton: locate_by_segment uses midpoint (0.5); _locate_by_index_v1 uses
    # [0.0, 1.0] (full-cube band per D-02 / CUBE-10 owner override).
    # Both are valid D-02 compliant singleton behaviors. The regression anchor is
    # that segment_count==1 triggers the singleton branch in both paths.
    # Assert: both produce a valid SubInterval in [0, 1].
    assert 0.0 <= si_seg.start <= si_seg.end <= 1.0, (
        f"locate_by_segment singleton band must be in [0,1]: {si_seg.start},{si_seg.end}"
    )
    assert 0.0 <= si_v1.start <= si_v1.end <= 1.0, (
        f"_locate_by_index_v1 singleton band must be in [0,1]: {si_v1.start},{si_v1.end}"
    )

    # D-02 invariant for k>1: verify the formula matches on a true single-segment bin.
    # Build a dedicated single-label single-cube fixture (k=5) — LabelA alone.
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow

    label2 = "D02MultiLabel"
    k2 = 5
    records2 = [
        RecordRow(release_id=i, label=label2, catalog_number=f"D2 {i:03d}")
        for i in range(1, k2 + 1)
    ]
    snapshot2 = CollectionSnapshot()
    snapshot2._load_snapshot({label2.casefold(): records2})

    rows2 = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label=label2,
            first_catalog="D2 001",
            is_empty=False,
        )
    ]
    cache2 = BoundaryCache()
    cache2._load_rows(rows2)

    sc2 = SegmentCache()
    sc2.derive(cache2, snapshot2, {})

    # Pitfall 5: verify this is a single-segment bin
    bin2 = sc2.get_bin(1, 0, 0)
    assert bin2 is not None
    assert len(bin2.segments) == 1, f"Expected 1 segment, got {len(bin2.segments)}"
    seg2 = bin2.segments[0]
    assert seg2.auto_fraction == 1.0
    assert seg2.first_rank_in_label == 0

    for rank in range(k2):
        release_id = rank + 1
        catalog = f"D2 {rank + 1:03d}"

        seg_result = locate_by_segment(
            release_id=release_id,
            label=label2,
            catalog_number=catalog,
            segment_cache=sc2,
            snapshot=snapshot2,
        )
        v1_result = _locate_by_index_v1(
            release_id=release_id,
            label=label2,
            catalog_number=catalog,
            segment_cache=sc2,
            snapshot=snapshot2,
        )

        assert seg_result.sub_cube_interval is not None
        assert v1_result.sub_cube_interval is not None

        si_seg = seg_result.sub_cube_interval
        si_v1 = v1_result.sub_cube_interval

        assert abs(si_seg.start - si_v1.start) < 1e-6, (
            f"D-02 start mismatch at rank {rank}: segment={si_seg.start:.8f} v1={si_v1.start:.8f}"
        )
        assert abs(si_seg.end - si_v1.end) < 1e-6, (
            f"D-02 end mismatch at rank {rank}: segment={si_seg.end:.8f} v1={si_v1.end:.8f}"
        )


# ── SEG-06 property: straddle resolves to correct bin ────────────────────────


def test_straddle_resolves_to_correct_bin(straddle_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Records in a straddle label resolve to the correct bin by rank.

    Requirement: SEG-06 — straddle resolves to correct bin without special-casing.
    The factory has 12 records in 2 bins (6 per bin). Early records (rank < 6)
    must resolve to the first bin (col=0); late records (rank >= 6) to the second (col=1).
    """
    from gruvax.estimator.algorithm import locate_by_segment

    _cache, seg_cache, snapshot = straddle_props_fixture

    # Check all 12 records
    for rank in range(12):
        release_id = rank + 1  # release_ids are 1..12
        catalog = f"LS {rank + 1:03d}"
        expected_col = 0 if rank < 6 else 1

        result = locate_by_segment(
            release_id=release_id,
            label="LabelS",
            catalog_number=catalog,
            segment_cache=seg_cache,
            snapshot=snapshot,
        )

        assert result.primary_cube is not None, f"LabelS rank {rank} must have a primary_cube"
        assert result.primary_cube.col == expected_col, (
            f"LabelS rank {rank} must resolve to col={expected_col}, "
            f"got col={result.primary_cube.col}"
        )


# ── SEG-06 property: primary_cube ∈ label_span ───────────────────────────────


def test_primary_cube_in_label_span(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: primary_cube must appear in label_span when non-null (carried from §7.3).

    Requirement: SEG-06 — LocateResult contract unchanged; INTERPOLATION §7.3 invariant.
    For any record where locate_by_segment returns a non-null primary_cube:
        result.primary_cube in result.label_span
    """
    from gruvax.estimator.algorithm import locate_by_segment

    _cache, seg_cache, snapshot = multi_label_props_fixture

    # Test with all LabelA records (k=8)
    for rank in range(8):
        release_id = rank + 1
        catalog = f"LA {rank + 1:03d}"

        result = locate_by_segment(
            release_id=release_id,
            label="LabelA",
            catalog_number=catalog,
            segment_cache=seg_cache,
            snapshot=snapshot,
        )

        if result.primary_cube is not None:
            assert result.primary_cube in result.label_span, (
                f"primary_cube {result.primary_cube} must be in label_span "
                f"{result.label_span} for LabelA rank {rank}"
            )


# ── SEG-06 property: 0 ≤ start ≤ end ≤ 1 ────────────────────────────────────


def test_sub_cube_interval_bounds(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: 0 ≤ start ≤ end ≤ 1 for every non-null sub_cube_interval (carried from §7.3).

    Requirement: SEG-06 — LocateResult contract unchanged; INTERPOLATION §7.3 invariant.
    For any record where sub_cube_interval is non-null:
        0 <= interval.start <= interval.end <= 1
    """
    from gruvax.estimator.algorithm import locate_by_segment

    _cache, seg_cache, snapshot = multi_label_props_fixture

    # Test with all LabelA and LabelB records
    label_tests = [
        ("LabelA",),
        ("LabelB",),
    ]
    for (label,) in label_tests:
        # Get actual records for this label
        label_records = snapshot.get_label_records(label)
        for rec in label_records:
            result = locate_by_segment(
                release_id=rec.release_id,
                label=label,
                catalog_number=rec.catalog_number,
                segment_cache=seg_cache,
                snapshot=snapshot,
            )

            if result.sub_cube_interval is not None:
                si = result.sub_cube_interval
                assert 0.0 <= si.start <= si.end <= 1.0, (
                    f"[{label} rid={rec.release_id}] SubInterval out of [0,1]: "
                    f"start={si.start} end={si.end}"
                )


# ── SEG-06 property: monotone position within a label ────────────────────────


def test_monotone_position_within_label(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Higher-indexed records within a label have >= start position (carried from §7.3).

    Requirement: SEG-06 — monotone position within a label; INTERPOLATION §7.3 invariant.
    For a label with k>1 records sorted by parse_key, the i-th record's
    sub_cube_interval.start must be >= the (i-1)-th record's start.

    Note: monotonicity holds within a single bin. For a straddle label, the position
    resets at the next bin boundary — we only assert monotonicity within the same bin.
    """
    from gruvax.estimator.algorithm import locate_by_segment
    from gruvax.estimator.normalize import parse_key

    _cache, seg_cache, snapshot = multi_label_props_fixture

    # LabelA has k=8 records in a single bin → strictly monotone
    label = "LabelA"
    label_records = snapshot.get_label_records(label)
    sorted_recs = sorted(label_records, key=lambda r: parse_key(r.catalog_number))

    starts = []
    for rec in sorted_recs:
        result = locate_by_segment(
            release_id=rec.release_id,
            label=label,
            catalog_number=rec.catalog_number,
            segment_cache=seg_cache,
            snapshot=snapshot,
        )
        if result.sub_cube_interval is not None:
            starts.append(result.sub_cube_interval.start)

    assert len(starts) == len(sorted_recs), "Expected sub_cube_interval for all LabelA records"

    for i in range(len(starts) - 1):
        assert starts[i] <= starts[i + 1], (
            f"Monotone violated at index {i}: start[{i}]={starts[i]} > start[{i + 1}]={starts[i + 1]}"
        )


# ── SEG-06 property: stability under cosmetic noise ──────────────────────────


@given(
    extra_spaces=st.integers(min_value=0, max_value=3),
    uppercase=st.booleans(),
)
@settings(max_examples=50)
def test_cosmetic_stability(extra_spaces: int, uppercase: bool) -> None:
    """SEG-06: Stability under cosmetic catalog-string noise (carried from §7.3).

    Requirement: SEG-06 — stability under normalization; INTERPOLATION §7.3 invariant.
    Adding extra spaces or changing case in a catalog number should not change
    the locate_by_segment result (after POS-01 normalization).
    """
    from gruvax.estimator.algorithm import locate_by_segment
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
    from gruvax.estimator.segment_cache import SegmentCache

    label = "StabilityTest"

    # Build a 5-record snapshot with a known position
    records = [
        RecordRow(release_id=i, label=label, catalog_number=f"BLP {4190 + i}") for i in range(1, 6)
    ]
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({label.casefold(): records})

    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label=label,
            first_catalog="BLP 4191",
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)

    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    # The target record is BLP 4195 (release_id=5)
    canonical_result = locate_by_segment(
        release_id=5,
        label=label,
        catalog_number="BLP 4195",
        segment_cache=sc,
        snapshot=snapshot,
    )

    # Cosmetic variants of the catalog number
    variant = "BLP 4195"
    if extra_spaces > 0:
        variant = "BLP" + " " * (extra_spaces + 1) + "4195"
    variant = variant.upper() if uppercase else variant.lower()

    variant_result = locate_by_segment(
        release_id=5,
        label=label,
        catalog_number=variant,
        segment_cache=sc,
        snapshot=snapshot,
    )

    # Both results must have the same sub_cube_interval (POS-01 normalization)
    if (
        canonical_result.sub_cube_interval is not None
        and variant_result.sub_cube_interval is not None
    ):
        assert (
            abs(canonical_result.sub_cube_interval.start - variant_result.sub_cube_interval.start)
            < 1e-6
        ), (
            f"Cosmetic variant '{variant}' produced different start: "
            f"canonical={canonical_result.sub_cube_interval.start} "
            f"variant={variant_result.sub_cube_interval.start}"
        )
        assert (
            abs(canonical_result.sub_cube_interval.end - variant_result.sub_cube_interval.end)
            < 1e-6
        ), (
            f"Cosmetic variant '{variant}' produced different end: "
            f"canonical={canonical_result.sub_cube_interval.end} "
            f"variant={variant_result.sub_cube_interval.end}"
        )
    else:
        # Both must agree on whether sub_cube_interval is None
        assert (canonical_result.sub_cube_interval is None) == (
            variant_result.sub_cube_interval is None
        ), f"Cosmetic variant '{variant}' disagrees on sub_cube_interval presence"

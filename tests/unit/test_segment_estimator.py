"""Unit tests for segment-aware two-level interpolation estimator (SEG-06/SEG-07).

Plan 05-03: Un-stub all Wave 0 skip-stubs. The tests exercise locate_by_segment()
and the locate() dispatcher using the synth_collection factories.

Per-Requirement coverage:
  SEG-06: locate_by_segment() two-level interpolation + straddle fallback path
  SEG-07: estimator_version = "segment-v1"; §4.8 cube-only fallback retained
"""

from __future__ import annotations

import pytest

from fixtures.synth_collection import make_multi_label_bin, make_straddle

# ── Session-scoped synth fixtures ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def multi_label_estimator_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped multi-label bin fixture for estimator tests."""
    return make_multi_label_bin()


@pytest.fixture(scope="session")
def straddle_estimator_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped straddle fixture for estimator tests."""
    return make_straddle()


# ── SEG-06: Two-level interpolation ──────────────────────────────────────────


def test_locate_by_segment_basic(multi_label_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: locate_by_segment() returns a valid LocateResult with sub_cube_interval.

    Requirement: SEG-06 — /api/locate returns sub-cube interval from two-level
    interpolation behind unchanged LocateResult contract.
    """
    from gruvax.estimator.algorithm import locate_by_segment
    from gruvax.estimator.constants import SEGMENT_ESTIMATOR_VERSION

    _cache, seg_cache, snapshot = multi_label_estimator_fixture

    # LabelA has 8 records; pick the 4th (rank=3 in 0-based)
    label_a_records = snapshot.get_label_records("LabelA")
    assert len(label_a_records) >= 4, "Expected at least 4 LabelA records"

    # release_id=4 is LA 004 (4th record in make_multi_label_bin)
    result = locate_by_segment(
        release_id=4,
        label="LabelA",
        catalog_number="LA 004",
        segment_cache=seg_cache,
        snapshot=snapshot,
    )

    # Contract shape assertions
    assert result.release_id == 4
    assert result.primary_cube is not None, "Expected non-null primary_cube"
    assert result.label_span, "Expected non-empty label_span"
    assert result.sub_cube_interval is not None, (
        "SEG-06: locate_by_segment must return a non-null sub_cube_interval"
    )
    si = result.sub_cube_interval
    assert 0.0 <= si.start <= si.end <= 1.0, (
        f"sub_cube_interval must be in [0,1]: start={si.start} end={si.end}"
    )
    assert result.estimator_version == SEGMENT_ESTIMATOR_VERSION == "segment-v1"


def test_locate_by_segment_two_level_formula(multi_label_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Two-level interpolation formula: f = offset + (rank_in_seg / (count-1)) * fraction.

    Requirement: SEG-06 — two-level interpolation within a segment (bin+segment → offset).

    For a single-label single-segment bin:
      offset=0.0, fraction=1.0 → f = 0 + (rank / (k-1)) * 1.0 = rank/(k-1)
    which is exactly §4.1's formula (D-02 regression anchor).

    LabelA in make_multi_label_bin has k=8 records.
    For rank=3 (4th record): f = 3/7 ≈ 0.4286
    Expected: start = max(0, 0.4286 - 0.05), end = min(1, 0.4286 + 0.05)
    """
    from gruvax.estimator.algorithm import locate_by_segment
    from gruvax.estimator.constants import POSITION_HALF_WIDTH
    from gruvax.estimator.segment_cache import SegmentCache

    cache_for_derive, _, snapshot = multi_label_estimator_fixture

    # Re-derive a SegmentCache to inspect the segment structure
    sc = SegmentCache()
    sc.derive(cache_for_derive, snapshot, {})

    # Get the bin and find LabelA's segment
    bin_ = sc.get_bin(1, 0, 0)
    assert bin_ is not None, "Expected a SegmentBin at (1,0,0)"

    # Find LabelA segment (casefold match)
    label_a_seg = next(
        (s for s in bin_.segments if s.label.casefold() == "labela"),
        None,
    )
    assert label_a_seg is not None, "Expected LabelA segment in the bin"

    # LabelA has k=8 records, rank=3 (release_id=4 is LA 004)
    rank = 3
    rank_in_seg = rank - label_a_seg.first_rank_in_label
    expected_f = (
        label_a_seg.offset_in_bin
        + (rank_in_seg / (label_a_seg.segment_count - 1)) * label_a_seg.applied_fraction
    )
    expected_start = max(0.0, expected_f - POSITION_HALF_WIDTH)
    expected_end = min(1.0, expected_f + POSITION_HALF_WIDTH)

    result = locate_by_segment(
        release_id=4,
        label="LabelA",
        catalog_number="LA 004",
        segment_cache=sc,
        snapshot=snapshot,
    )

    assert result.sub_cube_interval is not None
    si = result.sub_cube_interval
    assert abs(si.start - expected_start) < 1e-9, (
        f"start={si.start:.8f} expected {expected_start:.8f}"
    )
    assert abs(si.end - expected_end) < 1e-9, f"end={si.end:.8f} expected {expected_end:.8f}"


def test_locate_by_segment_straddle_resolves_correct_bin(straddle_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Records in the straddle resolve to correct bin without special-casing.

    Requirement: SEG-06 — straddle resolves to correct bin without special-casing
    (D-08: generic for N adjacent bins per label).
    Early records (rank < 6) → first bin (col=0); late records (rank >= 6) → second bin (col=1).

    make_straddle: LabelS has k=12 records. LS 001..LS 006 → bin (1,0,0);
    LS 007..LS 012 → bin (1,0,1).
    """
    from gruvax.estimator.algorithm import locate_by_segment

    _cache, seg_cache, snapshot = straddle_estimator_fixture

    # Early record (rank=2, LS 003 → should be in bin col=0)
    result_early = locate_by_segment(
        release_id=3,  # LS 003 (release_id=3 per _build_snapshot)
        label="LabelS",
        catalog_number="LS 003",
        segment_cache=seg_cache,
        snapshot=snapshot,
    )
    assert result_early.primary_cube is not None
    assert result_early.primary_cube.col == 0, (
        f"LS 003 (rank<6) must resolve to bin col=0, got col={result_early.primary_cube.col}"
    )
    assert result_early.sub_cube_interval is not None

    # Late record (rank=8, LS 009 → should be in bin col=1)
    result_late = locate_by_segment(
        release_id=9,  # LS 009 (release_id=9 per _build_snapshot)
        label="LabelS",
        catalog_number="LS 009",
        segment_cache=seg_cache,
        snapshot=snapshot,
    )
    assert result_late.primary_cube is not None
    assert result_late.primary_cube.col == 1, (
        f"LS 009 (rank>=6) must resolve to bin col=1, got col={result_late.primary_cube.col}"
    )
    assert result_late.sub_cube_interval is not None


def test_locate_by_segment_fallback_to_cube_only() -> None:
    """SEG-06: §4.8 cube-only fallback coverage path (no snapshot → cube-only result).

    Requirement: SEG-06 — §4.8 cube-only retained as timeout/low-confidence fallback.
    When no collection snapshot records exist for a label, locate() falls back to
    locate_cube_only() which returns a cube-only result with cube-only-v1 version.
    """
    from gruvax.estimator.algorithm import locate
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache

    # Build a cache with a cut point for "GhostLabel"
    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label="GhostLabel",
            first_catalog="GL 001",
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)

    # Empty snapshot — no records for "GhostLabel"
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({})

    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    result = locate(
        release_id=999,
        label="GhostLabel",
        catalog_number="GL 005",
        segment_cache=sc,
        snapshot=snapshot,
    )

    # §4.8 fallback: sub_cube_interval=None, estimator_version=cube-only-v1
    assert result.sub_cube_interval is None, (
        f"Expected sub_cube_interval=None for §4.8 fallback, got {result.sub_cube_interval}"
    )
    assert result.estimator_version == "cube-only-v1", (
        f"Expected 'cube-only-v1', got {result.estimator_version!r}"
    )


# ── SEG-07: estimator_version + §4.8 fallback retained ───────────────────────


def test_segment_estimator_version_in_result(multi_label_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-07: locate_by_segment() emits estimator_version='segment-v1' in LocateResult.

    Requirement: SEG-07 — estimator_version reflects the new algorithm.
    """
    from gruvax.estimator.algorithm import locate_by_segment
    from gruvax.estimator.constants import SEGMENT_ESTIMATOR_VERSION

    _cache, seg_cache, snapshot = multi_label_estimator_fixture

    # k=8 for LabelA → compute_confidence(8) > CUBE_ONLY_CONFIDENCE (0.30)
    result = locate_by_segment(
        release_id=5,
        label="LabelA",
        catalog_number="LA 005",
        segment_cache=seg_cache,
        snapshot=snapshot,
    )

    assert result.estimator_version == SEGMENT_ESTIMATOR_VERSION, (
        f"Expected estimator_version='{SEGMENT_ESTIMATOR_VERSION}', "
        f"got {result.estimator_version!r}"
    )
    assert result.estimator_version == "segment-v1"


def test_cube_only_fallback_version_string() -> None:
    """SEG-07: §4.8 cube-only fallback returns estimator_version='cube-only-v1'.

    Requirement: SEG-07 — §4.8 cube-only stays the timeout/low-confidence fallback.
    The fallback path must still emit 'cube-only-v1', not 'segment-v1'.
    """
    from gruvax.estimator.algorithm import locate
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache

    # Snapshot with 1 record for the label → k=1 → compute_confidence(1) == CUBE_ONLY_CONFIDENCE
    # → locate() dispatcher strips sub_cube_interval and returns cube-only-v1
    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label="FallbackLabel",
            first_catalog="FL 001",
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)

    snapshot = CollectionSnapshot()
    snapshot._load_snapshot(
        {
            "fallbacklabel": [
                __import__(
                    "gruvax.estimator.collection_snapshot", fromlist=["RecordRow"]
                ).RecordRow(release_id=1, label="FallbackLabel", catalog_number="FL 001")
            ]
        }
    )

    sc = SegmentCache()
    sc.derive(cache, snapshot, {})

    result = locate(
        release_id=1,
        label="FallbackLabel",
        catalog_number="FL 001",
        segment_cache=sc,
        snapshot=snapshot,
    )

    # k=1 → confidence==CUBE_ONLY_CONFIDENCE → dispatcher returns cube-only-v1
    assert result.estimator_version == "cube-only-v1", (
        f"Expected 'cube-only-v1' for singleton fallback, got {result.estimator_version!r}"
    )
    assert result.sub_cube_interval is None, "§4.8 fallback must set sub_cube_interval=None"

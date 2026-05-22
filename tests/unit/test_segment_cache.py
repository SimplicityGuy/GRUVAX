"""Wave 0 test stubs for SegmentCache unit tests (SEG-02, SEG-03, SEG-04, SEG-05).

These tests are created in Plan 05-01 Task 3 as Wave 0 scaffolds so downstream
plans (05-02: SegmentCache derivation) can fill them in without creating new test
files. Each test is marked skip until its production code lands in Plan 05-02.

Per-Requirement coverage:
  SEG-02: SegmentCache.derive() produces correct ordered per-label segments
  SEG-03: Counts from row-counting v_collection, not catalog arithmetic
  SEG-04: Override wins over count-derived fraction; widths sum to 100%
  SEG-05: Contiguity validator rejects non-adjacent scatter

Test names referenced in 05-VALIDATION.md § Per-Requirement Verification Map.
"""

from __future__ import annotations

import pytest

from fixtures.synth_collection import make_multi_label_bin, make_straddle


# ── Session-scoped synth fixtures ─────────────────────────────────────────────


@pytest.fixture(scope="session")
def multi_label_bin_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped multi-label bin cache + segment cache stub + snapshot."""
    return make_multi_label_bin()


@pytest.fixture(scope="session")
def straddle_fixture():  # type: ignore[no-untyped-def]
    """Session-scoped straddle (one label, two bins) cache + segment cache stub + snapshot."""
    return make_straddle()


# ── SEG-02: SegmentCache.derive() produces correct segments ───────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-02 (SegmentCache.derive())")
def test_segment_cache_derive_single_label(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-02: SegmentCache.derive() produces ordered per-label segments for each bin.

    Requirement: SEG-02 — derive per-bin ordered per-label segments from cut points
    via row-counting v_collection, zero additional manual input.
    """
    from gruvax.estimator.segment_cache import SegmentCache
    cache, _, snapshot = multi_label_bin_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, cache.overrides)
    # All bins with cut points should have at least one segment
    for bin_ in sc._bins:
        assert len(bin_.segments) >= 1, f"Bin ({bin_.unit_id},{bin_.row},{bin_.col}) has no segments"


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-02 (SegmentCache.derive())")
def test_segment_cache_segments_ordered(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-02: Segments within a bin are ordered by global (label casefold, parse_key).

    Requirement: SEG-02 — ordered per-label segments.
    """
    from gruvax.estimator.segment_cache import SegmentCache
    cache, _, snapshot = multi_label_bin_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, cache.overrides)
    for bin_ in sc._bins:
        labels = [seg.label.casefold() for seg in bin_.segments]
        assert labels == sorted(labels), f"Segments not ordered by label in bin ({bin_.unit_id},{bin_.row},{bin_.col})"


# ── SEG-03: Row-count not arithmetic ─────────────────────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-02 (row-count derivation)")
def test_row_count_not_arithmetic(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-03: Counts from v_collection row-counts — NOT catalog arithmetic.

    Requirement: SEG-03 — per-segment counts computed by row-counting v_collection
    including dupes + variants (AS 78, AS 78 2nd copy, AS 78-r), never catalog arithmetic.

    The multi_label_bin factory includes:
    - LabelB: "LB 003" appears twice (duplicate owned copy)
    - LabelB: "LB 003-r" (remix variant)
    These 3 records must be counted as 3 (not 1 unique catalog).
    """
    from gruvax.estimator.segment_cache import SegmentCache
    cache, _, snapshot = multi_label_bin_fixture
    sc = SegmentCache()
    sc.derive(cache, snapshot, cache.overrides)
    # Find LabelB's segment in the bin
    label_b_segs = [
        seg
        for bin_ in sc._bins
        for seg in bin_.segments
        if seg.label.casefold() == "labelb"
    ]
    assert len(label_b_segs) == 1, f"Expected 1 LabelB segment, got {len(label_b_segs)}"
    seg = label_b_segs[0]
    # LabelB has 6 records (including duplicate "LB 003" and "LB 003-r")
    assert seg.segment_count == 6, (
        f"LabelB segment_count should be 6 (row-count including dupes+variants), got {seg.segment_count}"
    )


# ── SEG-04: Override wins; widths sum to 1.0 ─────────────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-02 (override application)")
def test_override_applied(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-04: Admin physical-width override wins over count-derived fraction.

    Requirement: SEG-04 — optional admin physical-width override per label-segment
    takes precedence over count-derived auto_fraction.
    """
    from gruvax.estimator.segment_cache import SegmentCache
    cache, _, snapshot = multi_label_bin_fixture

    # Inject a physical-width override for LabelA at (1,0,0)
    overrides = {(1, 0, 0, "LabelA"): 0.6}
    cache._load_overrides(overrides)

    sc = SegmentCache()
    sc.derive(cache, snapshot, cache.overrides)

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
    assert seg.is_override, "LabelA segment should be marked is_override=True"
    assert abs(seg.applied_fraction - 0.6) < 1e-6, (
        f"LabelA applied_fraction should be 0.6 (override), got {seg.applied_fraction}"
    )


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-02 (fraction renormalization)")
def test_override_renormalization_sums_to_one(multi_label_bin_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-04: Per-bin applied_fractions always sum to 1.0 even with overrides.

    Pitfall 2: When one segment is overridden, remaining non-overridden segments
    must be renormalized to fill the remaining space. Sum must still equal 1.0.
    """
    from gruvax.estimator.segment_cache import SegmentCache
    cache, _, snapshot = multi_label_bin_fixture

    # Override LabelA at 60% — LabelB auto should get the remaining 40%
    cache._load_overrides({(1, 0, 0, "LabelA"): 0.6})

    sc = SegmentCache()
    sc.derive(cache, snapshot, cache.overrides)

    for bin_ in sc._bins:
        total = sum(seg.applied_fraction for seg in bin_.segments)
        assert abs(total - 1.0) < 1e-6, (
            f"Bin ({bin_.unit_id},{bin_.row},{bin_.col}) fractions sum to {total} (should be 1.0)"
        )


# ── SEG-05: Contiguity invariant ──────────────────────────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (contiguity validator)")
def test_contiguity_validation() -> None:
    """SEG-05: Contiguity validator rejects cuts scattering a label across non-adjacent bins.

    Requirement: SEG-05 — label-contiguity invariant enforced by save-validator;
    non-adjacent scatter is hard-rejected; adjacent multi-bin spans are valid (D-09).
    """
    from gruvax.api.admin.validation import validate_contiguity  # noqa: F401
    # Wave 0 stub — validate_contiguity doesn't exist yet (Plan 05-03)
    # Test: a label in bins [0,0] and [0,2] (skipping [0,1]) must be rejected
    # Test: a label in bins [0,0] and [0,1] (adjacent) must be accepted
    pytest.skip("Wave 0 stub — validate_contiguity implemented in Plan 05-03")

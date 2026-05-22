"""Wave 0 Hypothesis property test stubs for segment-aware estimator invariants (D-02).

These are the Extended Hypothesis Invariants from 05-VALIDATION.md (D-02).
Created in Plan 05-01 Task 3 as Wave 0 scaffolds; downstream plans (05-02/03)
will fill in the production code so these tests can pass.

All invariants are skip-stubbed until production code lands. The test bodies
are structured so the implementer cannot write vacuous tests — each stub
documents the exact preconditions (Pitfall 5 pre-check for test_single_segment_bin_reproduces_v1_index).

Per-Requirement coverage:
  SEG-06: test_primary_cube_in_label_span, test_sub_cube_interval_bounds,
          test_monotone_position_within_label, test_cosmetic_stability,
          test_straddle_resolves_to_correct_bin
  SEG-07: test_single_segment_bin_reproduces_v1_index (regression anchor)
  SEG-04: test_per_bin_fractions_sum_to_one

Extended invariants table (05-VALIDATION.md):
  test_per_bin_fractions_sum_to_one
  test_single_segment_bin_reproduces_v1_index
  test_straddle_resolves_to_correct_bin
  test_primary_cube_in_label_span
  test_sub_cube_interval_bounds
  test_monotone_position_within_label
  test_cosmetic_stability
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


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-02 (SegmentCache.derive())")
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


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_single_segment_bin_reproduces_v1_index(singleton_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-07: A single-segment bin must produce the same result as retired §4.1.

    This is the regression invariant that replaces the dropped A/B proof gate (D-02).
    If a bin has exactly one LabelSegment, the two-level formula degenerates to:
        offset=0, fraction=1.0 → f = rank / (k-1)
    which is exactly the §4.1 index-based formula.

    Pitfall 5 pre-check (MANDATORY — implementer must not write a vacuous test):
    BEFORE the estimator equality assertion, verify:
        assert len(bin.segments) == 1   # single-segment bin
        assert seg.auto_fraction == 1.0  # full bin
        assert seg.first_rank_in_label == 0  # starts at rank 0
    These three checks prevent a vacuous test where the fixture doesn't exercise
    the single-segment degeneracy.

    Requirement: SEG-07 — single-segment bin reproduces §4.1 exactly.
    """
    # Pitfall 5 pre-check: verify fixture is a single-segment bin
    # (these assertions must happen BEFORE the estimator equality assertion)
    # assert len(bin.segments) == 1   # single-segment bin invariant
    # assert seg.auto_fraction == 1.0  # full bin for single-segment
    # assert seg.first_rank_in_label == 0  # starts at rank 0
    pytest.skip("Wave 0 stub — single-segment regression anchor tested in Plan 05-03")


# ── SEG-06 property: straddle resolves to correct bin ────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_straddle_resolves_to_correct_bin(straddle_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Records in a straddle label resolve to the correct bin by rank.

    Requirement: SEG-06 — straddle resolves to correct bin without special-casing.
    The factory has 12 records in 2 bins (6 per bin). Early records (rank < 6)
    must resolve to the first bin; late records (rank >= 6) to the second.
    """
    pytest.skip("Wave 0 stub — straddle resolution property tested in Plan 05-03")


# ── SEG-06 property: primary_cube ∈ label_span ───────────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_primary_cube_in_label_span(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: primary_cube must appear in label_span when non-null (carried from §7.3).

    Requirement: SEG-06 — LocateResult contract unchanged; INTERPOLATION §7.3 invariant.
    For any record where locate_by_segment returns a non-null primary_cube:
        result.primary_cube in result.label_span
    """
    pytest.skip("Wave 0 stub — primary_cube ∈ label_span tested in Plan 05-03")


# ── SEG-06 property: 0 ≤ start ≤ end ≤ 1 ────────────────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_sub_cube_interval_bounds(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: 0 ≤ start ≤ end ≤ 1 for every non-null sub_cube_interval (carried from §7.3).

    Requirement: SEG-06 — LocateResult contract unchanged; INTERPOLATION §7.3 invariant.
    For any record where sub_cube_interval is non-null:
        0 <= interval.start <= interval.end <= 1
    """
    pytest.skip("Wave 0 stub — interval bounds tested in Plan 05-03")


# ── SEG-06 property: monotone position within a label ────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_monotone_position_within_label(multi_label_props_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Higher-indexed records within a label have >= start position (carried from §7.3).

    Requirement: SEG-06 — monotone position within a label; INTERPOLATION §7.3 invariant.
    For a label with k>1 records sorted by parse_key, the i-th record's
    sub_cube_interval.start must be >= the (i-1)-th record's start.
    """
    pytest.skip("Wave 0 stub — monotone position within label tested in Plan 05-03")


# ── SEG-06 property: stability under cosmetic noise ──────────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
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
    pytest.skip("Wave 0 stub — cosmetic stability tested in Plan 05-03")

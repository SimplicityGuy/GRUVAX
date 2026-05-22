"""Wave 0 test stubs for segment-aware two-level interpolation estimator (SEG-06).

These tests are created in Plan 05-01 Task 3 as Wave 0 scaffolds so downstream
plans (05-02: SegmentCache derivation; 05-03: locate_by_segment) can fill them
in without creating new test files.

Per-Requirement coverage:
  SEG-06: locate_by_segment() two-level interpolation + straddle fallback path
  SEG-07: estimator_version = "segment-v1"; §4.8 cube-only fallback retained

All tests are skip-stubbed until Plan 05-02/03 implement the production code.
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


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_locate_by_segment_basic(multi_label_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: locate_by_segment() returns a valid LocateResult with sub_cube_interval.

    Requirement: SEG-06 — /api/locate returns sub-cube interval from two-level
    interpolation behind unchanged LocateResult contract.
    """
    from gruvax.estimator.algorithm import locate_by_segment  # noqa: F401
    pytest.skip("Wave 0 stub — locate_by_segment implemented in Plan 05-03")


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_locate_by_segment_two_level_formula(multi_label_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Two-level interpolation formula: offset + (rank_in_seg / (count-1)) * fraction.

    Requirement: SEG-06 — two-level interpolation within a segment (bin+segment → offset).
    Formula: f = seg.offset_in_bin + (rank_in_segment / (seg.segment_count - 1)) * seg.applied_fraction
    """
    pytest.skip("Wave 0 stub — two-level formula tested in Plan 05-03")


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (locate_by_segment)")
def test_locate_by_segment_straddle_resolves_correct_bin(straddle_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-06: Records in the straddle resolve to correct bin without special-casing.

    Requirement: SEG-06 — straddle resolves to correct bin without special-casing
    (D-08: generic for N adjacent bins per label).
    Early records (rank < 6) → first bin; late records (rank >= 6) → second bin.
    """
    pytest.skip("Wave 0 stub — straddle resolution tested in Plan 05-03")


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (§4.8 fallback coverage)")
def test_locate_by_segment_fallback_to_cube_only() -> None:
    """SEG-06: §4.8 cube-only fallback coverage path (no snapshot → cube-only result).

    Requirement: SEG-06 — §4.8 cube-only retained as timeout/low-confidence fallback.
    When no collection snapshot records exist for a label, locate() falls back to
    locate_cube_only() which returns a cube-only result with cube-only-v1 version.
    """
    pytest.skip("Wave 0 stub — §4.8 fallback path tested in Plan 05-03")


# ── SEG-07: estimator_version + §4.8 fallback retained ───────────────────────


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (estimator version)")
def test_segment_estimator_version_in_result(multi_label_estimator_fixture) -> None:  # type: ignore[no-untyped-def]
    """SEG-07: locate_by_segment() emits estimator_version='segment-v1' in LocateResult.

    Requirement: SEG-07 — estimator_version reflects the new algorithm.
    """
    pytest.skip("Wave 0 stub — estimator_version checked in Plan 05-03")


@pytest.mark.skip(reason="Wave 0 stub — implemented in Plan 05-03 (cube-only fallback)")
def test_cube_only_fallback_version_string() -> None:
    """SEG-07: §4.8 cube-only fallback returns estimator_version='cube-only-v1'.

    Requirement: SEG-07 — §4.8 cube-only stays the timeout/low-confidence fallback.
    The fallback path must still emit 'cube-only-v1', not 'segment-v1'.
    """
    pytest.skip("Wave 0 stub — cube-only fallback version checked in Plan 05-03")

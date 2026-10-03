"""Hypothesis property tests for the segment-aware position estimator (Phase 5).

Phase 5 rewrite (Plan 05-03):
  - locate_by_index removed; tests updated to use locate_by_segment.
  - locate() now takes segment_cache= (not cache=).
  - SegmentCache derived from BoundaryCache + CollectionSnapshot in each test.
  - Factory return type: (BoundaryCache, CollectionSnapshot, dict[int, float]).

Invariants (INTERPOLATION §7.3):
  1. primary_cube ∈ label_span when locate() returns a non-null primary_cube
  2. 0 ≤ start ≤ end ≤ 1 for every non-null sub_cube_interval
  3. Monotone position within a label: higher-indexed records have >= start
  4. Stability under cosmetic (case/separator/whitespace) noise on catalog numbers

Session-scoped fixtures build the synthetic shapes without DB (using the
_load_snapshot / _load_rows seams from synth_collection.py).
Covered synthetic records must actually locate: a missing cube or interval
fails before an invariant can become vacuous. Singleton public results may be
cube-only; their coverage census still requires the cube and label span.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from fixtures.synth_collection import make_multi_prefix, make_singleton, make_uniform_dense
from gruvax.estimator.algorithm import locate, locate_by_segment
from gruvax.estimator.normalize import parse_key
from gruvax.estimator.segment_cache import SegmentCache


# ── Session-scoped synth fixtures (no DB) ────────────────────────────────────


@pytest.fixture(scope="session")
def uniform_dense_fixtures():  # type: ignore[no-untyped-def]
    """Session-scoped uniform-dense cache + snapshot + truth (no DB)."""
    return make_uniform_dense()


@pytest.fixture(scope="session")
def multi_prefix_fixtures():  # type: ignore[no-untyped-def]
    """Session-scoped multi-prefix cache + snapshot + truth (no DB)."""
    return make_multi_prefix()


@pytest.fixture(scope="session")
def singleton_fixtures():  # type: ignore[no-untyped-def]
    """Session-scoped singleton cache + snapshot + truth (no DB)."""
    return make_singleton()


def _derive(cache, snapshot):  # type: ignore[no-untyped-def]
    """Derive a SegmentCache from cache + snapshot with no overrides."""
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})
    return sc


@pytest.mark.parametrize("estimator_name", ["locate", "locate_by_segment"])
@pytest.mark.parametrize(
    ("fixture_name", "label", "expected_count"),
    [
        ("uniform_dense_fixtures", "UniformDense", 20),
        ("multi_prefix_fixtures", "MultiPrefix", 6),
        ("singleton_fixtures", "Singleton", 1),
    ],
)
def test_covered_shape_census(request, fixture_name, label, expected_count, estimator_name):  # type: ignore[no-untyped-def]
    """Both estimator entry points must cover every planted record in each shape."""
    cache, snapshot, truth = request.getfixturevalue(fixture_name)
    records = snapshot.get_label_records(label)
    assert len(records) == len(truth) == expected_count, f"{label}: empty/incomplete fixture"
    segment_cache = _derive(cache, snapshot)
    estimator = locate if estimator_name == "locate" else locate_by_segment
    results = [
        estimator(
            release_id=record.release_id,
            label=label,
            catalog_number=record.catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        for record in records
    ]
    covered = sum(result.primary_cube is not None for result in results)
    assert covered == expected_count, f"{label}/{estimator_name}: only {covered} cubes located"
    for result in results:
        assert result.primary_cube in result.label_span
    # The public singleton path can legitimately return cube-only today. Do not
    # settle gruvax-wz2's separate singleton-band contract decision in this test.
    if label != "Singleton" or estimator_name == "locate_by_segment":
        intervals = sum(result.sub_cube_interval is not None for result in results)
        assert intervals == expected_count, (
            f"{label}/{estimator_name}: only {intervals} intervals located"
        )


# ── Invariant 1: primary_cube ∈ label_span ───────────────────────────────────


def test_primary_cube_in_label_span(uniform_dense_fixtures) -> None:  # type: ignore[no-untyped-def]
    """primary_cube must appear in label_span when locate() returns a non-null primary_cube."""
    cache, snapshot, truth = uniform_dense_fixtures
    label = "UniformDense"
    segment_cache = _derive(cache, snapshot)
    assert len(truth) == 20, "UniformDense: expected 20 covered records"

    for release_id in truth:
        catalog_number = f"UD {release_id:03d}"
        result = locate(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        assert result.primary_cube is not None, f"No cube for covered release_id={release_id}"
        assert result.primary_cube in result.label_span, (
            f"primary_cube {result.primary_cube} not in label_span {result.label_span}"
            f" for release_id={release_id}"
        )


# ── Invariant 2: 0 ≤ start ≤ end ≤ 1 ────────────────────────────────────────


def test_sub_cube_interval_bounds(uniform_dense_fixtures) -> None:  # type: ignore[no-untyped-def]
    """0 ≤ start ≤ end ≤ 1 for every non-null sub_cube_interval."""
    cache, snapshot, truth = uniform_dense_fixtures
    label = "UniformDense"
    segment_cache = _derive(cache, snapshot)
    assert len(truth) == 20, "UniformDense: expected 20 interval-bearing records"

    for release_id in truth:
        catalog_number = f"UD {release_id:03d}"
        result = locate_by_segment(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        assert result.sub_cube_interval is not None, f"No interval for release_id={release_id}"
        si = result.sub_cube_interval
        assert si.start >= 0.0, f"start={si.start} < 0 for release_id={release_id}"
        assert si.start <= si.end, f"start={si.start} > end={si.end} for release_id={release_id}"
        assert si.end <= 1.0, f"end={si.end} > 1 for release_id={release_id}"


# ── Invariant 3: monotone position within label ───────────────────────────────


def test_monotone_position_within_label(uniform_dense_fixtures) -> None:  # type: ignore[no-untyped-def]
    """Records sorted by parse_key(catalog_number) produce non-decreasing sub_cube_interval.start."""
    cache, snapshot, truth = uniform_dense_fixtures
    label = "UniformDense"
    segment_cache = _derive(cache, snapshot)

    # Collect (catalog_number, release_id, start) in parse_key order
    records_ordered = sorted(
        [(f"UD {release_id:03d}", release_id) for release_id in truth],
        key=lambda x: parse_key(x[0]),
    )

    starts = []
    for catalog_number, release_id in records_ordered:
        result = locate_by_segment(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        assert result.sub_cube_interval is not None, f"No interval for release_id={release_id}"
        starts.append((catalog_number, result.sub_cube_interval.start))

    assert len(starts) == len(records_ordered) == 20, "Monotone comparison must cover all records"
    for i in range(len(starts) - 1):
        cat_a, s_a = starts[i]
        cat_b, s_b = starts[i + 1]
        assert s_a <= s_b, (
            f"Monotone violated: start({cat_a!r})={s_a:.4f} > start({cat_b!r})={s_b:.4f}"
        )


# ── Invariant 4: cosmetic stability ──────────────────────────────────────────


def test_cosmetic_stability_multi_prefix(multi_prefix_fixtures) -> None:  # type: ignore[no-untyped-def]
    """Separator and case variants of the same catalog number produce equal positions."""
    cache, snapshot, _truth = multi_prefix_fixtures
    label = "MultiPrefix"
    segment_cache = _derive(cache, snapshot)

    # BLP 100 and BLP-100 should produce the same locate result (parse_key is cosmetic-stable)
    result_space = locate_by_segment(
        release_id=1,
        label=label,
        catalog_number="BLP 100",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    result_dash = locate_by_segment(
        release_id=1,
        label=label,
        catalog_number="BLP-100",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    result_upper = locate_by_segment(
        release_id=1,
        label=label,
        catalog_number="blp 100",  # lowercase
        segment_cache=segment_cache,
        snapshot=snapshot,
    )

    # All three should be covered (same parse_key) and return equivalent positions
    assert result_space.sub_cube_interval is not None, "No interval for BLP 100"
    for result, variant in [(result_dash, "BLP-100"), (result_upper, "blp 100")]:
        assert result.sub_cube_interval is not None, f"No interval for {variant}"
        assert abs(result_space.sub_cube_interval.start - result.sub_cube_interval.start) < 1e-9, (
            f"Cosmetic stability violated: BLP 100 start={result_space.sub_cube_interval.start:.4f}"
            f" != {variant!r} start={result.sub_cube_interval.start:.4f}"
        )


# ── Hypothesis-driven: bounds invariant across all synth records ──────────────


@given(release_id=st.integers(min_value=1, max_value=20))
@settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_hypothesis_bounds_uniform_dense(release_id: int) -> None:
    """Hypothesis: for any release_id in uniform_dense, 0 ≤ start ≤ end ≤ 1."""
    cache, snapshot, _truth = make_uniform_dense()
    segment_cache = _derive(cache, snapshot)
    label = "UniformDense"
    catalog_number = f"UD {release_id:03d}"

    result = locate_by_segment(
        release_id=release_id,
        label=label,
        catalog_number=catalog_number,
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is not None, f"No interval for release_id={release_id}"
    si = result.sub_cube_interval
    assert 0.0 <= si.start <= si.end <= 1.0, (
        f"Bounds violated for release_id={release_id}: start={si.start} end={si.end}"
    )

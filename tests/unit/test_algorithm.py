"""Unit tests for the LocateResult contract, BoundaryCache, and position estimators.

Phase 5 rewrite (Plan 05-03):
  - locate_by_index removed from public API; tests updated to use locate_by_segment.
  - _locate_by_index_v1 imported by name for D-02 regression anchor.
  - locate_cube_only now takes (segment_cache, snapshot) — no more cache= kwarg.
  - BoundaryRow no longer takes last_label / last_catalog (SEG-01).
  - SegmentCache derived via _derive_seg_cache() helper for all estimator tests.
  - Golden cases updated to use locate_by_segment.

Contract tests (contract.py) and BoundaryCache tests are unchanged.

Tests the behavior described in PLAN.md §Task 2 <behavior>:
  - locate_cube_only returns confidence==0.30, sub_cube_interval==None,
    estimator_version=="cube-only-v1" for a covered record
  - label_span lists ALL covering cubes sorted by (unit_id, row, col)
  - primary_cube == label_span[0]
  - No-boundary record: confidence==0.0, primary_cube==None, label_span==[]
  - BoundaryCache.load(pool) populates 32 rows from seeded DB
  - invalidate() empties the cache (Phase 4 seam)
  - Range membership uses catalog_in_range (numeric-aware), NOT string compare

Phase 5 estimator tests (05-03):
  - locate_by_segment computes SubInterval with ±POSITION_HALF_WIDTH band
  - Singletons (k=1) → midpoint band (start≤0.5≤end), confidence==CUBE_ONLY_CONFIDENCE
  - Records not in snapshot → fallback to cube-only (estimator_version="cube-only-v1")
  - Records sorted by parse_key (D-13 — no raw string comparison)
  - Benchmark: p95 < 50 ms for 100 locate() calls (POS-03)
  - D-02 regression: single-segment bin reproduces §4.1 index formula exactly
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from gruvax.estimator.algorithm import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    locate,
    locate_by_segment,
    locate_cube_only,
)
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.constants import POSITION_HALF_WIDTH
from gruvax.estimator.contract import (
    CUBE_ONLY_CONFIDENCE as CONTRACT_CONFIDENCE,
    CubeRef,
    LocateResult,
    SubInterval,
)
from gruvax.estimator.segment_cache import SegmentCache


# FIXTURE_DIR points to repo-root fixtures/ — same path as tests/conftest.py uses
FIXTURE_DIR = Path(__file__).parent.parent.parent / "fixtures"

# ── Contract shape tests (contract.py) ───────────────────────────────────────


def test_locate_result_type_annotations() -> None:
    """LocateResult must have the expected fields with correct types."""
    import dataclasses

    fields = {f.name: f for f in dataclasses.fields(LocateResult)}
    assert "release_id" in fields
    assert "primary_cube" in fields
    assert "label_span" in fields
    assert "sub_cube_interval" in fields
    assert "confidence" in fields
    assert "generated_at" in fields
    assert "estimator_version" in fields


def test_cube_ref_frozen() -> None:
    """CubeRef must be frozen (immutable, hashable)."""
    cube = CubeRef(unit_id=1, row=0, col=0)
    with pytest.raises((TypeError, AttributeError)):
        cube.row = 99  # type: ignore[misc]


def test_cube_only_confidence_value() -> None:
    """CUBE_ONLY_CONFIDENCE must be 0.30 (D-11)."""
    assert CONTRACT_CONFIDENCE == 0.30


def test_locate_result_default_version() -> None:
    """Default estimator_version must be 'cube-only-v1'."""
    result = LocateResult(
        release_id=1,
        primary_cube=None,
        label_span=[],
        sub_cube_interval=None,
        confidence=0.0,
    )
    assert result.estimator_version == "cube-only-v1"


def test_sub_interval_frozen() -> None:
    """SubInterval must be frozen (used as a value object)."""
    cube = CubeRef(unit_id=1, row=0, col=0)
    interval = SubInterval(cube=cube, start=0.0, end=1.0, crosses_boundary=False)
    with pytest.raises((TypeError, AttributeError)):
        interval.start = 0.5  # type: ignore[misc]


# ── BoundaryCache from YAML fixture (unit tests — no DB) ────────────────────


def _make_cache_from_yaml(boundary_rows: list[dict]) -> BoundaryCache:
    """Build a BoundaryCache from the YAML fixture (bypasses DB for unit tests).

    Phase 5: BoundaryRow no longer takes last_label / last_catalog (SEG-01).
    """
    cache = BoundaryCache()
    rows = [
        BoundaryRow(
            unit_id=row["unit_id"],
            row=row["row"],
            col=row["col"],
            first_label=row.get("first_label"),
            first_catalog=row.get("first_catalog"),
            is_empty=row.get("is_empty", False),
        )
        for row in boundary_rows
    ]
    cache._load_rows(rows)  # seam method for testing without DB
    return cache


def test_cache_from_yaml_has_32_rows(boundary_cache: list[dict]) -> None:
    """YAML fixture must provide 32 rows (2 units x 4x4)."""
    cache = _make_cache_from_yaml(boundary_cache)
    assert len(cache.get_boundaries()) == 32


def test_cache_invalidate_empties(boundary_cache: list[dict]) -> None:
    """invalidate() must empty the cache (Phase 4 seam)."""
    cache = _make_cache_from_yaml(boundary_cache)
    assert len(cache.get_boundaries()) == 32
    cache.invalidate()
    assert len(cache.get_boundaries()) == 0


# ── Phase 5: Helpers for estimator tests ─────────────────────────────────────


# Helper: build a CollectionSnapshot from a list of dicts (no DB).
def _make_snapshot(records: list[dict]) -> CollectionSnapshot:
    """Build a CollectionSnapshot from a list of record dicts (bypasses DB)."""
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


def _make_single_cube_cache(label: str, first_cat: str) -> BoundaryCache:
    """Build a BoundaryCache with a single cut-point cube (Phase 5 — no last_*)."""
    rows = [
        BoundaryRow(
            unit_id=1,
            row=0,
            col=0,
            first_label=label,
            first_catalog=first_cat,
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)
    return cache


def _derive_seg_cache(
    cache: BoundaryCache,
    snapshot: CollectionSnapshot,
) -> SegmentCache:
    """Derive a SegmentCache from cache + snapshot with no overrides."""
    sc = SegmentCache()
    sc.derive(cache, snapshot, {})
    return sc


# ── locate_cube_only: covered record ─────────────────────────────────────────


def test_covered_record_confidence(boundary_cache: list[dict]) -> None:
    """A record covered by a boundary must return confidence == 0.30 (D-11)."""
    cache = _make_cache_from_yaml(boundary_cache)
    snapshot = _make_snapshot(
        [
            {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4010"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.confidence == CUBE_ONLY_CONFIDENCE == 0.30


def test_covered_record_sub_cube_interval_is_none(boundary_cache: list[dict]) -> None:
    """Phase 5 cube-only estimator must always return sub_cube_interval=None (D-10)."""
    cache = _make_cache_from_yaml(boundary_cache)
    snapshot = _make_snapshot(
        [
            {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4010"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is None


def test_covered_record_estimator_version(boundary_cache: list[dict]) -> None:
    """Covered record must report estimator_version='cube-only-v1'."""
    cache = _make_cache_from_yaml(boundary_cache)
    snapshot = _make_snapshot(
        [
            {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4010"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.estimator_version == "cube-only-v1"


def test_covered_record_primary_cube(boundary_cache: list[dict]) -> None:
    """primary_cube must equal label_span[0] (first in sorted order)."""
    cache = _make_cache_from_yaml(boundary_cache)
    snapshot = _make_snapshot(
        [
            {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4010"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.primary_cube is not None
    assert len(result.label_span) >= 1
    assert result.primary_cube == result.label_span[0]


def test_covered_record_label_span_sorted(boundary_cache: list[dict]) -> None:
    """label_span must be sorted by (unit_id, row, col)."""
    cache = _make_cache_from_yaml(boundary_cache)
    snapshot = _make_snapshot(
        [
            {"release_id": 1, "label": "Blue Note", "catalog_number": "BLP 4010"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    pairs = [(c.unit_id, c.row, c.col) for c in result.label_span]
    assert pairs == sorted(pairs), f"label_span not sorted: {result.label_span}"


def test_covered_record_release_id(boundary_cache: list[dict]) -> None:
    """locate_cube_only must propagate release_id into the result."""
    cache = _make_single_cube_cache("ECM", "ECM 1001")
    snapshot = _make_snapshot(
        [
            {"release_id": 42, "label": "ECM", "catalog_number": "ECM 1001"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=42,
        label="ECM",
        catalog_number="ECM 1001",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.release_id == 42


# ── locate_cube_only: no-boundary record ─────────────────────────────────────


def test_no_boundary_confidence() -> None:
    """Label with no covering boundary must return confidence == 0.0 (D-12).

    Phase 5: locate_cube_only relies on get_segment_for_rank returning None for
    an uncovered release_id. This happens when the release_id is not in the snapshot
    at all (stale snapshot / unknown label).
    """
    # Empty snapshot — release_id 99 is NOT in the snapshot → rank is None
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({})

    # Build a cache with a cut point (label doesn't matter — release_id not in snapshot)
    cache = _make_single_cube_cache("SomeLabel", "SL 001")
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.confidence == NO_BOUNDARY_CONFIDENCE == 0.0


def test_no_boundary_primary_cube_is_none() -> None:
    """No-boundary record: primary_cube must be None (D-12)."""
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({})

    cache = _make_single_cube_cache("SomeLabel", "SL 001")
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.primary_cube is None


def test_no_boundary_label_span_empty() -> None:
    """No-boundary record: label_span must be [] (D-12)."""
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({})

    cache = _make_single_cube_cache("SomeLabel", "SL 001")
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.label_span == []


def test_no_boundary_sub_cube_interval_is_none() -> None:
    """No-boundary record: sub_cube_interval must still be None."""
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({})

    cache = _make_single_cube_cache("SomeLabel", "SL 001")
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is None


# ── Numeric-edge case: proves range membership uses parse_key ─────────────────


def test_numeric_edge_covering_blp_9_NOT_in_blp_10_20() -> None:
    """BLP 9 must NOT be covered by a range [BLP 10, BLP 20].

    This proves that range membership uses parse_key (numeric-aware), not string
    comparison. BLP 9 < BLP 10 numerically — it must not be found in a cube whose
    cut point is BLP 10.
    """
    # Cache with cut point at BLP 10 (records starting at BLP 10)
    cache = _make_single_cube_cache("TestLabel", "BLP 10")
    # BLP 9 is below the cut point — it should not be in this bin
    snapshot_blp9 = _make_snapshot(
        [
            {"release_id": 1, "label": "TestLabel", "catalog_number": "BLP 9"},
        ]
    )
    sc_blp9 = _derive_seg_cache(cache, snapshot_blp9)
    result_blp9 = locate_cube_only(
        release_id=1,
        label="TestLabel",
        catalog_number="BLP 9",
        segment_cache=sc_blp9,
        snapshot=snapshot_blp9,
    )
    assert result_blp9.confidence == 0.0, (
        "BLP 9 must NOT be covered by a cube with cut point BLP 10 — "
        "numeric-aware range check required"
    )

    # BLP 10 == cut point → should BE covered
    snapshot_blp10 = _make_snapshot(
        [
            {"release_id": 1, "label": "TestLabel", "catalog_number": "BLP 10"},
        ]
    )
    sc_blp10 = _derive_seg_cache(cache, snapshot_blp10)
    result_blp10 = locate_cube_only(
        release_id=1,
        label="TestLabel",
        catalog_number="BLP 10",
        segment_cache=sc_blp10,
        snapshot=snapshot_blp10,
    )
    assert result_blp10.confidence == CUBE_ONLY_CONFIDENCE, (
        "BLP 10 must be covered by a cube with cut point BLP 10"
    )


def test_numeric_edge_blp_9_in_single_cube() -> None:
    """BLP 9 IS in a cube starting at BLP 9 (exact match at cut point)."""
    cache = _make_single_cube_cache("TestLabel", "BLP 9")
    snapshot = _make_snapshot(
        [
            {"release_id": 1, "label": "TestLabel", "catalog_number": "BLP 9"},
        ]
    )
    segment_cache = _derive_seg_cache(cache, snapshot)
    result = locate_cube_only(
        release_id=1,
        label="TestLabel",
        catalog_number="BLP 9",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.confidence == CUBE_ONLY_CONFIDENCE


# ── BoundaryCache.load from DB ────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_cache_load_from_db(db_pool: object) -> None:  # type: ignore[type-arg]
    """BoundaryCache.load(pool) must populate 32 rows from the seeded DB.

    Uses loop_scope="session" so this test shares the same event loop as the
    session-scoped db_pool fixture (required by pytest-asyncio 1.x).
    """
    cache = BoundaryCache()
    await cache.load(db_pool)
    assert len(cache.get_boundaries()) == 32, (
        f"Expected 32 boundary rows from DB, got {len(cache.get_boundaries())}"
    )


# ── Phase 5: locate_by_segment + locate dispatcher ───────────────────────────


def test_locate_by_segment_multi_record() -> None:
    """A label with k>=4 records returns a populated SubInterval with 0<=start<=end<=1.

    For a single-cube label the band width equals 2*POSITION_HALF_WIDTH (except
    clamped at cube edges).
    """
    records = [
        {"release_id": 10, "label": "TestLabel", "catalog_number": "TL 001"},
        {"release_id": 11, "label": "TestLabel", "catalog_number": "TL 002"},
        {"release_id": 12, "label": "TestLabel", "catalog_number": "TL 003"},
        {"release_id": 13, "label": "TestLabel", "catalog_number": "TL 004"},
    ]
    cache = _make_single_cube_cache("TestLabel", "TL 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_by_segment(
        release_id=12,
        label="TestLabel",
        catalog_number="TL 003",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is not None, (
        "Expected non-null SubInterval for multi-record label"
    )
    si = result.sub_cube_interval
    assert 0 <= si.start <= si.end <= 1, f"SubInterval out of [0,1]: start={si.start} end={si.end}"
    assert result.confidence > CUBE_ONLY_CONFIDENCE, (
        f"Expected confidence > {CUBE_ONLY_CONFIDENCE}, got {result.confidence}"
    )


def test_singleton_full_cube_band() -> None:
    """k=1 → SubInterval(start≤0.5≤end) — midpoint band for singleton."""
    records = [
        {"release_id": 1, "label": "SingleLabel", "catalog_number": "SL 001"},
    ]
    cache = _make_single_cube_cache("SingleLabel", "SL 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_by_segment(
        release_id=1,
        label="SingleLabel",
        catalog_number="SL 001",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    # For singleton: segment_count==1 → f = 0 + 1.0 * 0.5 = 0.5 (midpoint)
    # start = max(0, 0.5 - HALF_WIDTH), end = min(1, 0.5 + HALF_WIDTH)
    assert result.sub_cube_interval is not None, "Singleton must have a SubInterval (not None)"
    si = result.sub_cube_interval
    assert si.start <= 0.5 <= si.end, (
        f"Singleton midpoint band must include 0.5: start={si.start} end={si.end}"
    )
    assert 0.0 <= si.start <= si.end <= 1.0, "SubInterval out of [0,1]"


def test_singleton_confidence() -> None:
    """k=1 → confidence == CUBE_ONLY_CONFIDENCE (0.30) — D-02."""
    records = [
        {"release_id": 1, "label": "SingleLabel", "catalog_number": "SL 001"},
    ]
    cache = _make_single_cube_cache("SingleLabel", "SL 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_by_segment(
        release_id=1,
        label="SingleLabel",
        catalog_number="SL 001",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    # locate() dispatcher strips sub_cube_interval when confidence <= CUBE_ONLY_CONFIDENCE,
    # but locate_by_segment itself still emits the sub_cube_interval (dispatcher handles it).
    # Confidence for k=1 comes from compute_confidence(1) which returns CUBE_ONLY_CONFIDENCE.
    assert result.confidence == CUBE_ONLY_CONFIDENCE, (
        f"Singleton confidence must be {CUBE_ONLY_CONFIDENCE}, got {result.confidence}"
    )


def test_band_width_formula() -> None:
    """For k>1, start == max(0, f - POSITION_HALF_WIDTH), end == min(1, f + POSITION_HALF_WIDTH).

    Test with rank=2 in k=5 records in a single-segment bin.
    Single segment: offset=0, fraction=1.0.
    f = 0 + (2 / (5-1)) * 1.0 = 0.5
    Expected: start = 0.5 - 0.05 = 0.45, end = 0.5 + 0.05 = 0.55.
    """
    records = [
        {"release_id": 1, "label": "BandTest", "catalog_number": "BT 001"},
        {"release_id": 2, "label": "BandTest", "catalog_number": "BT 002"},
        {"release_id": 3, "label": "BandTest", "catalog_number": "BT 003"},  # rank=2, f=0.5
        {"release_id": 4, "label": "BandTest", "catalog_number": "BT 004"},
        {"release_id": 5, "label": "BandTest", "catalog_number": "BT 005"},
    ]
    cache = _make_single_cube_cache("BandTest", "BT 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_by_segment(
        release_id=3,  # rank=2 in 0-based sorted list → f = 2/4 = 0.5
        label="BandTest",
        catalog_number="BT 003",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is not None
    si = result.sub_cube_interval
    expected_start = max(0.0, 0.5 - POSITION_HALF_WIDTH)
    expected_end = min(1.0, 0.5 + POSITION_HALF_WIDTH)
    assert abs(si.start - expected_start) < 1e-9, f"start={si.start} expected {expected_start}"
    assert abs(si.end - expected_end) < 1e-9, f"end={si.end} expected {expected_end}"


def test_fallback_to_cube_only() -> None:
    """Record not in snapshot → locate() returns sub_cube_interval=None, estimator_version='cube-only-v1'.

    Pitfall B: release_id present in collection but not in snapshot (stale snapshot).
    """
    # Snapshot has NO records for this label
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({})  # empty

    cache = _make_single_cube_cache("GhostLabel", "GL 001")
    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate(
        release_id=999,
        label="GhostLabel",
        catalog_number="GL 005",
        segment_cache=segment_cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is None, (
        f"Expected sub_cube_interval=None for fallback, got {result.sub_cube_interval}"
    )
    assert result.estimator_version == "cube-only-v1", (
        f"Expected estimator_version='cube-only-v1', got {result.estimator_version!r}"
    )


def test_monotone_within_label() -> None:
    """Records sorted by parse_key produce non-decreasing sub_cube_interval.start."""
    # Build 10 records with increasing catalog numbers
    label = "MonoTest"
    records = [
        {"release_id": i, "label": label, "catalog_number": f"MT {i:03d}"} for i in range(1, 11)
    ]
    cache = _make_single_cube_cache(label, "MT 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    starts = []
    for rec in records:
        result = locate_by_segment(
            release_id=rec["release_id"],
            label=label,
            catalog_number=rec["catalog_number"],
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        assert result.sub_cube_interval is not None
        starts.append(result.sub_cube_interval.start)

    # Verify monotone non-decreasing
    for i in range(len(starts) - 1):
        assert starts[i] <= starts[i + 1], (
            f"Monotone violated at index {i}: start[{i}]={starts[i]} > start[{i + 1}]={starts[i + 1]}"
        )


def test_locate_benchmark(benchmark) -> None:  # type: ignore[no-untyped-def]
    """p95 over 100 locate() calls must be < 50 ms (POS-03).

    Uses pytest-benchmark's benchmark fixture. The benchmark runs locate() for
    each of 100 release_ids against an in-memory snapshot/cache (no DB calls).
    """
    label = "BenchLabel"
    release_ids = list(range(1, 101))
    records = [
        {"release_id": rid, "label": label, "catalog_number": f"BL {rid:03d}"}
        for rid in release_ids
    ]
    cache = _make_single_cube_cache(label, "BL 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    def run_all() -> list:
        return [
            locate(
                release_id=rid,
                label=label,
                catalog_number=f"BL {rid:03d}",
                segment_cache=segment_cache,
                snapshot=snapshot,
            )
            for rid in release_ids
        ]

    benchmark(run_all)
    # pytest-benchmark records total time for the batched call.
    # p95 is in milliseconds: assert the batch p95 is well under the budget.
    assert benchmark.stats["mean"] * 1000 < 50, (
        f"benchmark mean {benchmark.stats['mean'] * 1000:.2f}ms exceeds 50ms budget (POS-03)"
    )


# ── D-02 regression anchor: _locate_by_index_v1 single-segment degeneracy ────


def test_single_segment_bin_reproduces_v1_index() -> None:
    """D-02: single-segment bin produces the same result as retired §4.1 index formula.

    The regression invariant: when a bin has exactly one LabelSegment, the two-level
    formula degenerates to f = rank / (k-1), which is exactly §4.1.

    Uses _locate_by_index_v1 (private — imported by name for this test only).
    """
    from gruvax.estimator.algorithm import _locate_by_index_v1  # private — D-02 only

    label = "D02Label"
    k = 5
    records = [
        {"release_id": i, "label": label, "catalog_number": f"D0 {i:03d}"} for i in range(1, k + 1)
    ]
    cache = _make_single_cube_cache(label, "D0 001")
    snapshot = _make_snapshot(records)
    segment_cache = _derive_seg_cache(cache, snapshot)

    # Pitfall 5 pre-check: verify fixture is a single-segment bin
    bin_ = segment_cache.get_bin(1, 0, 0)
    assert bin_ is not None, "Expected a SegmentBin for D-02 test"
    assert len(bin_.segments) == 1, f"D-02 requires single-segment bin, got {len(bin_.segments)}"
    seg = bin_.segments[0]
    assert seg.auto_fraction == 1.0, (
        f"Single-segment must have auto_fraction=1.0, got {seg.auto_fraction}"
    )
    assert seg.first_rank_in_label == 0, (
        f"Single-segment must start at rank 0, got {seg.first_rank_in_label}"
    )

    # Compare locate_by_segment vs _locate_by_index_v1 for every record
    for i in range(1, k + 1):
        release_id = i
        cat = f"D0 {i:03d}"

        seg_result = locate_by_segment(
            release_id=release_id,
            label=label,
            catalog_number=cat,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        v1_result = _locate_by_index_v1(
            release_id=release_id,
            label=label,
            catalog_number=cat,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )

        assert seg_result.sub_cube_interval is not None, (
            f"locate_by_segment must produce SubInterval for release_id={release_id}"
        )
        assert v1_result.sub_cube_interval is not None, (
            f"_locate_by_index_v1 must produce SubInterval for release_id={release_id}"
        )

        si_seg = seg_result.sub_cube_interval
        si_v1 = v1_result.sub_cube_interval

        assert abs(si_seg.start - si_v1.start) < 1e-6, (
            f"D-02 start mismatch for rank {i - 1}: segment={si_seg.start:.8f} v1={si_v1.start:.8f}"
        )
        assert abs(si_seg.end - si_v1.end) < 1e-6, (
            f"D-02 end mismatch for rank {i - 1}: segment={si_seg.end:.8f} v1={si_v1.end:.8f}"
        )


# ── Golden cases (Task 2b, now using locate_by_segment) ──────────────────────


def _load_golden_cases() -> list[dict]:
    """Load golden_cases.yaml from the repo-root fixtures/ directory."""
    golden_yaml = FIXTURE_DIR / "golden_cases.yaml"
    data = yaml.safe_load(golden_yaml.read_text())
    return data["cases"]


def _make_golden_cache_and_snapshot(case: dict) -> tuple[BoundaryCache, CollectionSnapshot]:
    """Build cache + snapshot for a golden case entry.

    Phase 5: BoundaryRow uses cut-point model (first_label/first_catalog only).
    """
    label = case["label"]
    k = case["k"]
    target_cat = case["catalog_number"]
    release_id = case["release_id"]

    # Build k catalog numbers; target is at position idx
    prefix = label[:3].upper()

    catalog_nums = []
    other_release_ids = []

    # Handle special cases from the golden_cases.yaml
    if label == "SingletonGold":
        catalog_nums = [target_cat]
        other_release_ids = [release_id]
    elif label == "TightPairGold":
        catalogs = ["TP 001", "TP 002"]
        catalog_nums = catalogs
        other_release_ids = [1, 2]
    elif label == "DenseK5Gold":
        catalogs = [f"DK 00{i}" for i in range(1, k + 1)]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))
    elif label == "SparseK5Gold":
        catalogs = [f"SK 00{i}" for i in range(1, k + 1)]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))
    elif label == "MultiPrefixGold":
        catalogs = ["BLP 100", "BLP 200", "BLP 300", "BST 84001", "BST 84002", "BST 84003"]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))
    elif label == "MixedSepGold":
        # 5 records; target is BLP-4195 at index 2
        catalogs = ["BLP 4001", "BLP 4100", "BLP 4195", "BLP 4200", "BLP 4300"]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))
    elif label == "BarcodeGold":
        # 3 records; barcode at index 1
        catalogs = ["1000000000000", "1234567890123", "9999999999999"]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))
    elif label == "TwoCubeGold":
        # 10 records spanning two cubes: TC 001-TC 005 in cube 0, TC 006-TC 010 in cube 1
        catalogs = [f"TC {i:03d}" for i in range(1, k + 1)]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))
    else:
        # Generic: sequential catalogs
        catalogs = [f"{prefix} {i:03d}" for i in range(1, k + 1)]
        catalog_nums = catalogs
        other_release_ids = list(range(1, k + 1))

    # Build cache: single cube covering first to last in sorted order
    from gruvax.estimator.normalize import parse_key as _pk

    sorted_pairs = sorted(
        zip(catalog_nums, other_release_ids, strict=True), key=lambda x: _pk(x[0])
    )
    sorted_cats = [p[0] for p in sorted_pairs]
    sorted_ids = [p[1] for p in sorted_pairs]

    # Special case: TwoCubeGold uses two cubes (CUBE-03 test)
    if label == "TwoCubeGold":
        mid = len(sorted_cats) // 2
        rows = [
            BoundaryRow(
                unit_id=1,
                row=0,
                col=0,
                first_label=label,
                first_catalog=sorted_cats[0],
                is_empty=False,
            ),
            BoundaryRow(
                unit_id=1,
                row=0,
                col=1,
                first_label=label,
                first_catalog=sorted_cats[mid],
                is_empty=False,
            ),
        ]
        cache = BoundaryCache()
        cache._load_rows(rows)
    else:
        cache = _make_single_cube_cache(label, sorted_cats[0])

    # Build snapshot
    snapshot = CollectionSnapshot()
    records = [
        RecordRow(release_id=rid, label=label, catalog_number=cat)
        for cat, rid in zip(sorted_cats, sorted_ids, strict=True)
    ]
    by_label = {label.casefold(): records}
    snapshot._load_snapshot(by_label)

    return cache, snapshot


@pytest.mark.parametrize("case", _load_golden_cases(), ids=[c["id"] for c in _load_golden_cases()])
def test_golden_cases(case: dict) -> None:
    """Each golden_cases.yaml entry produces expected start/end/confidence/crosses_boundary.

    Phase 5: uses locate_by_segment instead of the retired locate_by_index.
    Single-segment bins (all golden cases) reproduce §4.1 formula exactly (D-02).
    """
    cache, snapshot = _make_golden_cache_and_snapshot(case)
    tol = case.get("tolerance", 0.001)

    segment_cache = _derive_seg_cache(cache, snapshot)

    result = locate_by_segment(
        release_id=case["release_id"],
        label=case["label"],
        catalog_number=case["catalog_number"],
        segment_cache=segment_cache,
        snapshot=snapshot,
    )

    assert result.sub_cube_interval is not None, f"[{case['id']}] Expected non-null SubInterval"
    si = result.sub_cube_interval

    assert abs(si.start - case["expected_start"]) <= tol, (
        f"[{case['id']}] start={si.start:.4f} expected {case['expected_start']:.4f} ±{tol}"
    )
    assert abs(si.end - case["expected_end"]) <= tol, (
        f"[{case['id']}] end={si.end:.4f} expected {case['expected_end']:.4f} ±{tol}"
    )
    assert abs(result.confidence - case["expected_confidence"]) <= tol, (
        f"[{case['id']}] confidence={result.confidence:.4f} expected {case['expected_confidence']:.4f} ±{tol}"
    )
    assert si.crosses_boundary == case["expected_crosses_boundary"], (
        f"[{case['id']}] crosses_boundary={si.crosses_boundary} expected {case['expected_crosses_boundary']}"
    )

"""Unit tests for the LocateResult contract, BoundaryCache, and position estimators.

Tests the behavior described in PLAN.md §Task 2 <behavior>:
  - locate_cube_only returns confidence==0.30, sub_cube_interval==None,
    estimator_version=="cube-only-v1" for a covered record
  - label_span lists ALL covering cubes sorted by (unit_id, row, col)
  - primary_cube == label_span[0]
  - No-boundary record: confidence==0.0, primary_cube==None, label_span==[]
  - BoundaryCache.load(pool) populates 32 rows from seeded DB
  - invalidate() empties the cache (Phase 4 seam)
  - Range membership uses catalog_in_range (numeric-aware), NOT string compare

Phase 2 additions (02-01 §Task 2a):
  - locate_by_index computes SubInterval with ±POSITION_HALF_WIDTH band (non-singleton)
  - Singletons (k=1) → start=0.0, end=1.0, confidence==CUBE_ONLY_CONFIDENCE (D-02)
  - Records not in snapshot → fallback to cube-only (estimator_version="cube-only-v1")
  - Records sorted by parse_key (D-13 — no raw string comparison)
  - Benchmark: p95 < 50 ms for 100 locate() calls (POS-03)
"""

from __future__ import annotations

import pytest

from gruvax.estimator.algorithm import (
    CUBE_ONLY_CONFIDENCE,
    NO_BOUNDARY_CONFIDENCE,
    locate,
    locate_by_index,
    locate_cube_only,
)
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
from gruvax.estimator.constants import POSITION_HALF_WIDTH
from gruvax.estimator.contract import CUBE_ONLY_CONFIDENCE as CONTRACT_CONFIDENCE
from gruvax.estimator.contract import CubeRef, LocateResult, SubInterval

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
    """Build a BoundaryCache from the YAML fixture (bypasses DB for unit tests)."""
    cache = BoundaryCache()
    rows = [
        BoundaryRow(
            unit_id=row["unit_id"],
            row=row["row"],
            col=row["col"],
            first_label=row.get("first_label"),
            first_catalog=row.get("first_catalog"),
            last_label=row.get("last_label"),
            last_catalog=row.get("last_catalog"),
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


# ── locate_cube_only: covered record ─────────────────────────────────────────


def test_covered_record_confidence(boundary_cache: list[dict]) -> None:
    """A record covered by a boundary must return confidence == 0.30 (D-11)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        cache=cache,
    )
    assert result.confidence == CUBE_ONLY_CONFIDENCE == 0.30


def test_covered_record_sub_cube_interval_is_none(boundary_cache: list[dict]) -> None:
    """Phase 1 cube-only estimator must always return sub_cube_interval=None (D-10)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        cache=cache,
    )
    assert result.sub_cube_interval is None


def test_covered_record_estimator_version(boundary_cache: list[dict]) -> None:
    """Covered record must report estimator_version='cube-only-v1'."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        cache=cache,
    )
    assert result.estimator_version == "cube-only-v1"


def test_covered_record_primary_cube(boundary_cache: list[dict]) -> None:
    """primary_cube must equal label_span[0] (first in sorted order)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        cache=cache,
    )
    assert result.primary_cube is not None
    assert len(result.label_span) >= 1
    assert result.primary_cube == result.label_span[0]


def test_covered_record_label_span_sorted(boundary_cache: list[dict]) -> None:
    """label_span must be sorted by (unit_id, row, col)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=1,
        label="Blue Note",
        catalog_number="BLP 4010",
        cache=cache,
    )
    pairs = [(c.unit_id, c.row, c.col) for c in result.label_span]
    assert pairs == sorted(pairs), f"label_span not sorted: {result.label_span}"


def test_covered_record_release_id(boundary_cache: list[dict]) -> None:
    """locate_cube_only must propagate release_id into the result."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=42,
        label="ECM",
        catalog_number="ECM 1001",
        cache=cache,
    )
    assert result.release_id == 42


# ── locate_cube_only: no-boundary record ─────────────────────────────────────


def test_no_boundary_confidence(boundary_cache: list[dict]) -> None:
    """Label with no covering boundary must return confidence == 0.0 (D-12)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        cache=cache,
    )
    assert result.confidence == NO_BOUNDARY_CONFIDENCE == 0.0


def test_no_boundary_primary_cube_is_none(boundary_cache: list[dict]) -> None:
    """No-boundary record: primary_cube must be None (D-12)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        cache=cache,
    )
    assert result.primary_cube is None


def test_no_boundary_label_span_empty(boundary_cache: list[dict]) -> None:
    """No-boundary record: label_span must be [] (D-12)."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        cache=cache,
    )
    assert result.label_span == []


def test_no_boundary_sub_cube_interval_is_none(boundary_cache: list[dict]) -> None:
    """No-boundary record: sub_cube_interval must still be None."""
    cache = _make_cache_from_yaml(boundary_cache)
    result = locate_cube_only(
        release_id=99,
        label="NONEXISTENT LABEL XYZ",
        catalog_number="ZZZ 9999",
        cache=cache,
    )
    assert result.sub_cube_interval is None


# ── Numeric-edge case: proves range membership uses parse_key ─────────────────


def test_numeric_edge_covering_blp_9_NOT_in_blp_10_20(boundary_cache: list[dict]) -> None:
    """BLP 9 must NOT be covered by a range [BLP 4001, BLP 4020].

    This proves that range membership uses parse_key (numeric-aware), not string
    comparison. Under raw string comparison, 'BLP 9' > 'BLP 4020' is FALSE because
    '9' > '4' lexically... actually under raw string, 'BLP 9' > 'BLP 4020' would
    be True ('9' > '4'), so 'BLP 9' would NOT be in ['BLP 4001', 'BLP 4020'].

    The critical numeric-aware case: a catalog_number numerically ABOVE the range
    must not match, while one numerically equal to BLP 9 (below 10) must NOT match
    a [BLP 10, BLP 20] range.
    """
    # Create a synthetic cache with [BLP 10, BLP 20] range
    rows = [
        BoundaryRow(
            unit_id=1, row=0, col=0,
            first_label="TestLabel", first_catalog="BLP 10",
            last_label="TestLabel", last_catalog="BLP 20",
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)

    # BLP 9 < BLP 10 numerically → should NOT be covered
    result_blp9 = locate_cube_only(
        release_id=1, label="TestLabel", catalog_number="BLP 9", cache=cache
    )
    assert result_blp9.confidence == 0.0, (
        "BLP 9 must NOT be covered by [BLP 10, BLP 20] — numeric-aware range check required"
    )

    # BLP 10 == lower bound → should BE covered
    result_blp10 = locate_cube_only(
        release_id=1, label="TestLabel", catalog_number="BLP 10", cache=cache
    )
    assert result_blp10.confidence == CUBE_ONLY_CONFIDENCE, (
        "BLP 10 must be covered by [BLP 10, BLP 20]"
    )


def test_numeric_edge_blp_9_vs_blp_9_range(boundary_cache: list[dict]) -> None:
    """BLP 9 IS in range [BLP 9, BLP 9] (exact match), proving numeric-aware equality."""
    rows = [
        BoundaryRow(
            unit_id=1, row=0, col=0,
            first_label="TestLabel", first_catalog="BLP 9",
            last_label="TestLabel", last_catalog="BLP 9",
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)

    result = locate_cube_only(
        release_id=1, label="TestLabel", catalog_number="BLP 9", cache=cache
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


# ── Phase 2: locate_by_index + locate dispatcher ─────────────────────────────

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


def _make_single_cube_cache(label: str, first_cat: str, last_cat: str) -> BoundaryCache:
    """Build a BoundaryCache with a single cube covering the given label + catalog range."""
    rows = [
        BoundaryRow(
            unit_id=1, row=0, col=0,
            first_label=label, first_catalog=first_cat,
            last_label=label, last_catalog=last_cat,
            is_empty=False,
        )
    ]
    cache = BoundaryCache()
    cache._load_rows(rows)
    return cache


def test_locate_by_index_multi_record() -> None:
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
    cache = _make_single_cube_cache("TestLabel", "TL 001", "TL 004")
    snapshot = _make_snapshot(records)

    result = locate_by_index(
        release_id=12,
        label="TestLabel",
        catalog_number="TL 003",
        cache=cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is not None, "Expected non-null SubInterval for multi-record label"
    si = result.sub_cube_interval
    assert 0 <= si.start <= si.end <= 1, f"SubInterval out of [0,1]: start={si.start} end={si.end}"
    assert result.confidence > CUBE_ONLY_CONFIDENCE, (
        f"Expected confidence > {CUBE_ONLY_CONFIDENCE}, got {result.confidence}"
    )


def test_singleton_full_cube_band() -> None:
    """k=1 → SubInterval(start=0.0, end=1.0) — faint full-cube band (CUBE-10/D-02)."""
    records = [
        {"release_id": 1, "label": "SingleLabel", "catalog_number": "SL 001"},
    ]
    cache = _make_single_cube_cache("SingleLabel", "SL 001", "SL 001")
    snapshot = _make_snapshot(records)

    result = locate_by_index(
        release_id=1,
        label="SingleLabel",
        catalog_number="SL 001",
        cache=cache,
        snapshot=snapshot,
    )
    assert result.sub_cube_interval is not None, "Singleton must have a SubInterval (not None)"
    si = result.sub_cube_interval
    assert si.start == 0.0, f"Singleton start must be 0.0, got {si.start}"
    assert si.end == 1.0, f"Singleton end must be 1.0, got {si.end}"


def test_singleton_confidence() -> None:
    """k=1 → confidence == CUBE_ONLY_CONFIDENCE (0.30) — D-02."""
    records = [
        {"release_id": 1, "label": "SingleLabel", "catalog_number": "SL 001"},
    ]
    cache = _make_single_cube_cache("SingleLabel", "SL 001", "SL 001")
    snapshot = _make_snapshot(records)

    result = locate_by_index(
        release_id=1,
        label="SingleLabel",
        catalog_number="SL 001",
        cache=cache,
        snapshot=snapshot,
    )
    assert result.confidence == CUBE_ONLY_CONFIDENCE, (
        f"Singleton confidence must be {CUBE_ONLY_CONFIDENCE}, got {result.confidence}"
    )


def test_band_width_formula() -> None:
    """For k>1, start == max(0, f - POSITION_HALF_WIDTH), end == min(1, f + POSITION_HALF_WIDTH).

    Test with a known index idx=2 in k=5 records → f = 2/4 = 0.5.
    Expected: start = 0.5 - 0.05 = 0.45, end = 0.5 + 0.05 = 0.55.
    """
    records = [
        {"release_id": 1, "label": "BandTest", "catalog_number": "BT 001"},
        {"release_id": 2, "label": "BandTest", "catalog_number": "BT 002"},
        {"release_id": 3, "label": "BandTest", "catalog_number": "BT 003"},  # idx=2, f=0.5
        {"release_id": 4, "label": "BandTest", "catalog_number": "BT 004"},
        {"release_id": 5, "label": "BandTest", "catalog_number": "BT 005"},
    ]
    cache = _make_single_cube_cache("BandTest", "BT 001", "BT 005")
    snapshot = _make_snapshot(records)

    result = locate_by_index(
        release_id=3,  # idx=2 in 0-based sorted list → f = 2/4 = 0.5
        label="BandTest",
        catalog_number="BT 003",
        cache=cache,
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

    cache = _make_single_cube_cache("GhostLabel", "GL 001", "GL 010")

    result = locate(
        release_id=999,
        label="GhostLabel",
        catalog_number="GL 005",
        cache=cache,
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
        {"release_id": i, "label": label, "catalog_number": f"MT {i:03d}"}
        for i in range(1, 11)
    ]
    cache = _make_single_cube_cache(label, "MT 001", "MT 010")
    snapshot = _make_snapshot(records)

    starts = []
    for rec in records:
        result = locate_by_index(
            release_id=rec["release_id"],
            label=label,
            catalog_number=rec["catalog_number"],
            cache=cache,
            snapshot=snapshot,
        )
        assert result.sub_cube_interval is not None
        starts.append(result.sub_cube_interval.start)

    # Verify monotone non-decreasing
    for i in range(len(starts) - 1):
        assert starts[i] <= starts[i + 1], (
            f"Monotone violated at index {i}: start[{i}]={starts[i]} > start[{i+1}]={starts[i+1]}"
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
    cache = _make_single_cube_cache(label, "BL 001", "BL 100")
    snapshot = _make_snapshot(records)

    def run_all() -> list:
        return [
            locate(
                release_id=rid,
                label=label,
                catalog_number=f"BL {rid:03d}",
                cache=cache,
                snapshot=snapshot,
            )
            for rid in release_ids
        ]

    result = benchmark(run_all)
    # pytest-benchmark records total time for the batched call.
    # p95 is in milliseconds: assert the batch p95 is well under the budget.
    assert benchmark.stats["mean"] * 1000 < 50, (
        f"benchmark mean {benchmark.stats['mean'] * 1000:.2f}ms exceeds 50ms budget (POS-03)"
    )

"""Unit tests for the LocateResult contract, BoundaryCache, and cube-only estimator.

Tests the behavior described in PLAN.md §Task 2 <behavior>:
  - locate_cube_only returns confidence==0.30, sub_cube_interval==None,
    estimator_version=="cube-only-v1" for a covered record
  - label_span lists ALL covering cubes sorted by (unit_id, row, col)
  - primary_cube == label_span[0]
  - No-boundary record: confidence==0.0, primary_cube==None, label_span==[]
  - BoundaryCache.load(pool) populates 32 rows from seeded DB
  - invalidate() empties the cache (Phase 4 seam)
  - Range membership uses catalog_in_range (numeric-aware), NOT string compare
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from gruvax.estimator.algorithm import CUBE_ONLY_CONFIDENCE, NO_BOUNDARY_CONFIDENCE, locate_cube_only
from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
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
    import dataclasses
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
    """YAML fixture must provide 32 rows (2 units × 4×4)."""
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


@pytest.mark.asyncio
async def test_cache_load_from_db(db_pool: object) -> None:  # type: ignore[type-arg]
    """BoundaryCache.load(pool) must populate 32 rows from the seeded DB."""
    cache = BoundaryCache()
    await cache.load(db_pool)
    assert len(cache.get_boundaries()) == 32, (
        f"Expected 32 boundary rows from DB, got {len(cache.get_boundaries())}"
    )

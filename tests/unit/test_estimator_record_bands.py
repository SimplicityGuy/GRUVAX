"""Exact public record bands honor crossing and singleton contracts."""

from __future__ import annotations

from typing import Any

import pytest

from fixtures.synth_collection import make_straddle
from gruvax.estimator.algorithm import locate, locate_by_segment
from gruvax.estimator.contract import CubeRef


@pytest.mark.parametrize("estimator", [locate, locate_by_segment])
@pytest.mark.parametrize("release_id", range(1, 13))
def test_continuing_segment_only_crosses_for_edge_record(estimator: Any, release_id: int) -> None:
    _, segments, snapshot = make_straddle()
    result = estimator(
        release_id=release_id,
        label="LabelS",
        catalog_number=f"LS {release_id:03d}",
        segment_cache=segments,
        snapshot=snapshot,
    )
    interval = result.sub_cube_interval
    assert interval is not None
    local_rank = (release_id - 1) % 6
    position = local_rank / 5
    assert interval.start == pytest.approx(max(0, position - 0.05))
    assert interval.end == pytest.approx(min(1, position + 0.05))
    assert result.primary_cube == CubeRef(1, 0, (release_id - 1) // 6)
    crosses = release_id == 6
    assert interval.crosses_boundary is crosses, (
        "Crossing describes this record's band, not its whole segment"
    )
    assert interval.next_cube == (CubeRef(1, 0, 1) if crosses else None)


@pytest.mark.parametrize("estimator", [locate, locate_by_segment])
def test_global_singleton_has_exact_full_cube_band(estimator: Any) -> None:
    from fixtures.synth_collection import make_singleton
    from gruvax.estimator.segment_cache import SegmentCache

    boundary, snapshot, _ = make_singleton()
    segments = SegmentCache()
    segments.derive(boundary, snapshot, {})
    result = estimator(1, "Singleton", "SL 001", segments, snapshot)
    interval = result.sub_cube_interval
    assert interval is not None, "Known singleton coverage must not become cube-only"
    assert (interval.start, interval.end) == (0.0, 1.0)
    assert interval.crosses_boundary is False
    assert interval.next_cube is None
    assert result.confidence == 0.30
    assert result.estimator_version == "segment-v1"


@pytest.mark.parametrize("estimator", [locate, locate_by_segment])
@pytest.mark.parametrize("missing", ["snapshot", "record", "segment"])
def test_genuine_missing_coverage_keeps_cube_only(estimator: Any, missing: str) -> None:
    from fixtures.synth_collection import make_singleton
    from gruvax.estimator.collection_snapshot import CollectionSnapshot
    from gruvax.estimator.segment_cache import SegmentCache

    boundary, snapshot, _ = make_singleton()
    segments = SegmentCache()
    segments.derive(boundary, snapshot, {})
    release_id = 1
    if missing == "snapshot":
        snapshot = CollectionSnapshot()
    elif missing == "record":
        release_id = 999
    else:
        segments = SegmentCache()
    result = estimator(release_id, "Singleton", "SL 001", segments, snapshot)
    assert result.sub_cube_interval is None
    assert result.estimator_version == "cube-only-v1"


def _mixed_bin(count_a: int = 2, count_b: int = 2) -> tuple[Any, Any]:
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
    from gruvax.estimator.segment_cache import SegmentCache

    boundary = BoundaryCache()
    boundary._load_rows([BoundaryRow(1, 0, 0, "LabelA", "A 001", False)])
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot(
        {
            "labela": [RecordRow(i + 1, "LabelA", f"A {i + 1:03d}") for i in range(count_a)],
            "labelb": [
                RecordRow(count_a + i + 1, "LabelB", f"B {i + 1:03d}") for i in range(count_b)
            ],
        }
    )
    segments = SegmentCache()
    segments.derive(boundary, snapshot, {})
    return segments, snapshot


@pytest.mark.parametrize("estimator", [locate, locate_by_segment])
@pytest.mark.parametrize("release_id,position", [(1, 0.125), (2, 0.375), (3, 0.625), (4, 0.875)])
def test_mixed_labels_have_distinct_record_midpoints(
    estimator: Any, release_id: int, position: float
) -> None:
    segments, snapshot = _mixed_bin()
    label = "LabelA" if release_id <= 2 else "LabelB"
    catalog = f"{'A' if release_id <= 2 else 'B'} {(release_id - 1) % 2 + 1:03d}"
    result = estimator(release_id, label, catalog, segments, snapshot)
    interval = result.sub_cube_interval
    assert interval is not None
    assert interval.start == pytest.approx(position - 0.05)
    assert interval.end == pytest.approx(position + 0.05)
    assert not interval.crosses_boundary
    assert interval.next_cube is None


@pytest.mark.parametrize("estimator", [locate, locate_by_segment])
def test_global_singleton_in_mixed_bin_keeps_full_cube_contract(estimator: Any) -> None:
    segments, snapshot = _mixed_bin(1, 2)
    result = estimator(1, "LabelA", "A 001", segments, snapshot)
    assert len(segments.get_bin(1, 0, 0).segments) == 2
    assert len(snapshot.get_label_records("LabelA")) == 1
    interval = result.sub_cube_interval
    assert interval is not None
    assert (interval.start, interval.end) == (0.0, 1.0)
    assert result.confidence == 0.30


@pytest.mark.parametrize("estimator", [locate, locate_by_segment])
def test_single_record_segment_of_larger_label_keeps_local_midpoint(estimator: Any) -> None:
    from gruvax.estimator.boundary_cache import BoundaryCache, BoundaryRow
    from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow
    from gruvax.estimator.segment_cache import SegmentCache

    boundary = BoundaryCache()
    boundary._load_rows(
        [BoundaryRow(1, 0, col, "LabelA", f"A {col + 1:03d}", False) for col in range(2)]
    )
    snapshot = CollectionSnapshot()
    snapshot._load_snapshot({"labela": [RecordRow(i, "LabelA", f"A {i:03d}") for i in (1, 2)]})
    segments = SegmentCache()
    segments.derive(boundary, snapshot, {})
    for release in (1, 2):
        result = estimator(release, "LabelA", f"A {release:03d}", segments, snapshot)
        interval = result.sub_cube_interval
        assert interval is not None
        assert (interval.start, interval.end) == pytest.approx((0.45, 0.55))
        assert result.primary_cube == CubeRef(1, 0, release - 1)
        assert not interval.crosses_boundary
        assert interval.next_cube is None

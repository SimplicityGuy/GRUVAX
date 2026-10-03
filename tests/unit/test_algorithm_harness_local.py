"""Exercise the optional developer CSV path using only owned synthetic files."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from fixtures.synth_collection import all_shapes
from gruvax.estimator.collection_snapshot import RecordRow
from scripts.run_all_algorithms import _load_local_boundaries, _p95, _run_local_csv, _score_shape


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def local_collection(tmp_path: Path) -> Path:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    shutil.copyfile("fixtures/boundaries.yaml", fixtures / "boundaries.yaml")
    (tmp_path / "RWlodarczyk-collection-synthetic.csv").write_text(
        "Label,Catalog#\n" + "".join(f"Blue Note,BLP {1000 + i}\n" for i in range(8))
    )
    return tmp_path


def test_local_nested_boundaries_produce_real_estimates(local_collection: Path) -> None:
    metrics = _run_local_csv(local_collection)
    assert metrics is not None
    # With zero loaded boundaries the original implementation confidently returned 0.
    assert metrics["local_csv"]["cube_only"]["confidence_mean"] > 0.0
    assert metrics["local_csv"]["index"]["confidence_mean"] > 0.0


def test_nested_fixture_retains_all_cubes_and_parent_unit_ids(local_collection: Path) -> None:
    rows = _load_local_boundaries(local_collection / "fixtures/boundaries.yaml").get_boundaries()
    assert len(rows) == 32
    assert {row.unit_id for row in rows} == {1, 2}
    assert sum(row.unit_id == 1 for row in rows) == 16
    assert sum(row.unit_id == 2 for row in rows) == 16


@pytest.mark.parametrize("yaml_text", ["units: []\n", "boundaries: []\n", "- invalid\n"])
def test_present_csv_invalid_or_empty_boundaries_fail(
    local_collection: Path, yaml_text: str
) -> None:
    (local_collection / "fixtures/boundaries.yaml").write_text(yaml_text)
    with pytest.raises(RuntimeError, match="Local CSV path failed"):
        _run_local_csv(local_collection)


def test_present_csv_missing_boundaries_fail(local_collection: Path) -> None:
    (local_collection / "fixtures/boundaries.yaml").unlink()
    with pytest.raises(RuntimeError, match="Local CSV path failed"):
        _run_local_csv(local_collection)


def test_present_csv_empty_collection_fails(local_collection: Path) -> None:
    (local_collection / "RWlodarczyk-collection-synthetic.csv").write_text("Label,Catalog#\n")
    with pytest.raises(RuntimeError, match="Local CSV path failed"):
        _run_local_csv(local_collection)


def test_absent_optional_csv_remains_absent(tmp_path: Path) -> None:
    assert _run_local_csv(tmp_path) is None


def test_empty_timing_census_is_zero() -> None:
    assert _p95([]) == 0.0


@pytest.mark.parametrize(
    "count,rank", [(2, 2), (3, 3), (5, 5), (10, 10), (20, 19), (21, 20), (100, 95)]
)
@pytest.mark.parametrize("scorer", ["synthetic", "local_csv"])
def test_both_scorers_report_nearest_rank_p95(
    local_collection: Path, monkeypatch: pytest.MonkeyPatch, count: int, rank: int, scorer: str
) -> None:
    ticks = iter(t for i in range(1, count + 1) for t in (0.0, i / 1000, 0.0, (100 + i) / 1000))
    monkeypatch.setattr("scripts.run_all_algorithms.time.perf_counter", lambda: next(ticks))
    if scorer == "local_csv":
        (local_collection / "RWlodarczyk-collection-synthetic.csv").write_text(
            "Label,Catalog#\n" + "".join(f"Blue Note,BLP {1000 + i}\n" for i in range(count))
        )
        results = _run_local_csv(local_collection)
        assert results is not None
        metrics = results["local_csv"]
    else:
        cache, snapshot, _ = all_shapes()["uniform_dense"]()
        label = "UniformDense"
        snapshot._load_snapshot(
            {label.casefold(): [RecordRow(i, label, f"UD {i:03d}") for i in range(1, count + 1)]}
        )
        selected_truth = {i: (i - 1) / (count - 1) for i in range(1, count + 1)}
        metrics = _score_shape(cache, snapshot, selected_truth, label)
    assert metrics["index"]["p95_ms"] == pytest.approx(rank)
    assert metrics["cube_only"]["p95_ms"] == pytest.approx(100 + rank)

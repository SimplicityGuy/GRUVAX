"""SLO checking must reject absent coverage and tail-latency regressions."""

import json

import pytest

from scripts.check_benchmark import _check


@pytest.mark.parametrize(
    ("benchmarks", "required", "expected"),
    [
        ([], (), False),
        ([{"name": "unknown", "stats": {"data": [0.001]}}], (), False),
        (
            [{"name": "test_search_slo_benchmark", "stats": {"data": [0.01]}}],
            ("test_locate_slo_benchmark",),
            False,
        ),
        ([{"name": "test_search_slo_benchmark", "stats": {"mean": 0.001}}], (), False),
        (
            [
                {
                    "name": "test_search_slo_benchmark",
                    "stats": {"data": [0.001] * 18 + [0.5, 0.5], "mean": 0.051},
                }
            ],
            (),
            False,
        ),
        ([{"name": "test_locate_slo_benchmark", "stats": {"data": [0.051]}}], (), False),
        (
            [
                {"name": "test_search_slo_benchmark", "stats": {"data": [0.2]}},
                {"name": "test_locate_slo_benchmark", "stats": {"data": [0.05]}},
            ],
            ("test_search_slo_benchmark", "test_locate_slo_benchmark"),
            True,
        ),
    ],
)
def test_slo_gate_characterizes_p95_and_required_coverage(
    tmp_path, benchmarks, required, expected
) -> None:  # type: ignore[no-untyped-def]
    report = tmp_path / "benchmarks.json"
    report.write_text(json.dumps({"benchmarks": benchmarks}))
    assert _check(str(report), required) is expected

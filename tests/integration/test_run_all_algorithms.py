"""CI assertion tests for the §4.1 vs §4.8 A/B harness.

POS-06: Proves that §4.1 (index-based estimator) MAE <= §4.8 (cube-only) MAE
on every synthetic planted-truth collection shape, and that the aggregate
compute stays under the POS-03 50 ms p95 budget.

These tests import run_all_algorithms(ci=True) — the synthetic-only path — so
they never read or require the gitignored owner collection CSV.

Import resolution: `from scripts.run_all_algorithms import run_all_algorithms`
works via `pythonpath = ["."]` in [tool.pytest.ini_options] (pyproject.toml,
established in Plan 02-01 Task 2b) combined with `scripts/__init__.py`
(added in Plan 02-04 Task 1).
"""

from __future__ import annotations

import pytest

from scripts.run_all_algorithms import P95_BUDGET_MS, run_all_algorithms


# ── Shared fixture: run harness once per session ──────────────────────────────


@pytest.fixture(scope="session")
def harness_results() -> dict[str, dict[str, dict[str, float]]]:
    """Run the A/B harness in CI mode (synthetic shapes only) once per session.

    ci=True ensures the local CSV is never read (repo hygiene — CSV is gitignored).
    """
    return run_all_algorithms(ci=True)


# ── Synthetic shape names expected from all_shapes() ─────────────────────────

EXPECTED_SHAPES = ["uniform_dense", "sparse_gappy", "multi_prefix", "singleton"]


# ── §4.1 MAE <= §4.8 MAE on every planted-truth shape (D-07 / D-08) ─────────


def test_index_beats_or_ties_cube_only_on_all_shapes(
    harness_results: dict[str, dict[str, dict[str, float]]],
) -> None:
    """§4.1 MAE <= §4.8 MAE on every synthetic planted-truth shape.

    D-08 reframed: "prove §4.1 >= §4.8 on planted-truth shapes" means the
    index-based estimator must produce equal or lower mean absolute error than
    the cube-only (worst-case-0.5) baseline on every shape.

    Pitfall F is avoided: sparse_gappy planted truth is gap-weighted (NOT idx/(k-1))
    so §4.1 shows non-zero MAE — the harness genuinely differentiates the algorithms.
    """
    for shape in EXPECTED_SHAPES:
        assert shape in harness_results, (
            f"Shape '{shape}' missing from harness results. "
            f"Got keys: {list(harness_results.keys())}"
        )
        shape_metrics = harness_results[shape]

        index_mae = shape_metrics["index"]["mae"]
        cube_mae = shape_metrics["cube_only"]["mae"]

        # Use a small float tolerance for the singleton case where both MAEs
        # are exactly 0.0 — floating-point rounding can cause minor deviations.
        tolerance = 1e-9
        assert index_mae <= cube_mae + tolerance, (
            f"Shape '{shape}': §4.1 MAE ({index_mae:.6f}) > §4.8 MAE ({cube_mae:.6f}). "
            "Expected §4.1 to be equal or better than §4.8 on every planted-truth shape."
        )


# ── Aggregate p95 timing under POS-03 budget ─────────────────────────────────


def test_harness_aggregate_under_budget(
    harness_results: dict[str, dict[str, dict[str, float]]],
) -> None:
    """Aggregate p95 across all shapes and both estimators is < 50 ms (POS-03).

    Verifies the estimator compute stays within the 50 ms round-trip budget when
    run against the synthetic collection. Real-collection timing is validated
    separately (local CSV path, never run in CI).
    """
    all_p95_values: list[float] = []

    for shape in EXPECTED_SHAPES:
        if shape not in harness_results:
            continue
        shape_metrics = harness_results[shape]
        all_p95_values.append(shape_metrics["index"]["p95_ms"])
        all_p95_values.append(shape_metrics["cube_only"]["p95_ms"])

    assert all_p95_values, "No p95 timing values collected — harness may have failed."

    aggregate_p95 = max(all_p95_values)
    assert aggregate_p95 < P95_BUDGET_MS, (
        f"Aggregate p95 {aggregate_p95:.2f} ms exceeds POS-03 budget of {P95_BUDGET_MS:.0f} ms."
    )


# ── Shape presence check ──────────────────────────────────────────────────────


def test_all_shapes_present(
    harness_results: dict[str, dict[str, dict[str, float]]],
) -> None:
    """Harness returns results for all four expected synthetic shapes."""
    for shape in EXPECTED_SHAPES:
        assert shape in harness_results, (
            f"Expected shape '{shape}' in harness_results. Got: {list(harness_results.keys())}"
        )
        assert "index" in harness_results[shape], f"Missing 'index' key for shape '{shape}'"
        assert "cube_only" in harness_results[shape], f"Missing 'cube_only' key for shape '{shape}'"


# ── Local CSV is never accessed in CI tests ───────────────────────────────────


def test_local_csv_not_in_ci_results(
    harness_results: dict[str, dict[str, dict[str, float]]],
) -> None:
    """run_all_algorithms(ci=True) must not include 'local_csv' in results.

    Verifies that the --ci guard is respected: the gitignored owner collection
    CSV is never read or required when running under CI mode.
    """
    assert "local_csv" not in harness_results, (
        "ci=True run should not include 'local_csv' key in results. "
        "The gitignored CSV must never be read in CI."
    )

"""GRUVAX developer A/B harness — §4.1 (index-based dispatcher via locate) vs §4.8 (cube-only).

POS-06: Runs both estimators against synthetic planted-truth collection shapes
and (optionally) the gitignored local CSV, emitting per-distribution-shape MAE,
p95 timing, and confidence metrics.

Phase 5 changes:
  - ``locate()`` now takes ``segment_cache`` instead of ``cache``. The harness
    constructs a SegmentCache via derive() from the existing cache/snapshot.
  - BoundaryRow no longer has last_label/last_catalog (SEG-01 / Phase 5).
  - Per D-01: the harness is NOT extended with the segment estimator as a new
    compared algorithm. The ``locate`` dispatcher already calls ``locate_by_segment``
    internally; the harness output structure ("index" / "cube_only") is unchanged.
  - The "index" key in results now reflects the segment-aware locate() output
    (estimator_version = "segment-v1"), not the retired §4.1 index-based version.
    This is correct: the harness validates that the new estimator beats cube-only on MAE.

Standalone run (developer):
    uv run python scripts/run_all_algorithms.py

CI run (synthetic shapes only, CSV not required):
    uv run python scripts/run_all_algorithms.py --ci

Imported by:
    tests/integration/test_run_all_algorithms.py (via `from scripts.run_all_algorithms import
    run_all_algorithms`)

Import-path strategy (single source of truth, Plan 02-01 §Task 2b):
  - pytest resolves imports via `pythonpath = ["."]` in pyproject.toml, so
    `from scripts.run_all_algorithms import ...` works in tests.
  - For standalone `uv run python scripts/run_all_algorithms.py`, sys.path[0] is
    `scripts/`, NOT the repo root, so we insert the repo root explicitly below.
    This is the ONLY place this shim lives — do not replicate it in tests.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time


# ── Standalone-run import shim ────────────────────────────────────────────────
# Must appear BEFORE any `from fixtures.*` or `from gruvax.*` imports.
# pytest uses pythonpath=["."] (pyproject.toml); standalone script sys.path[0]
# is scripts/, not the repo root. Insert the repo root if not already present.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# ─────────────────────────────────────────────────────────────────────────────

from fixtures.synth_collection import all_shapes  # noqa: E402
from gruvax.estimator.algorithm import locate, locate_cube_only  # noqa: E402
from gruvax.estimator.boundary_cache import BoundaryCache  # noqa: E402
from gruvax.estimator.collection_snapshot import CollectionSnapshot, RecordRow  # noqa: E402
from gruvax.estimator.segment_cache import SegmentCache  # noqa: E402


# POS-03 budget: aggregate p95 per shape must stay under this threshold.
P95_BUDGET_MS: float = 50.0

# §4.8 null-interval worst-case: midpoint of cube = 0.5
CUBE_ONLY_NULL_MIDPOINT: float = 0.5


# ── Per-shape metrics ─────────────────────────────────────────────────────────


def _midpoint(start: float, end: float) -> float:
    """Return the midpoint of a [start, end] interval."""
    return (start + end) / 2.0


def _score_shape(
    cache: BoundaryCache,
    snapshot: CollectionSnapshot,
    truth: dict[int, float],
    label: str,
) -> dict[str, dict[str, float]]:
    """Run locate() and locate_cube_only() on every planted-truth release and return per-shape metrics.

    Phase 5: locate() dispatcher calls locate_by_segment() internally (segment-v1 estimator).
    The harness output structure ("index" / "cube_only") is unchanged per D-01.
    SegmentCache is derived from cache + snapshot here.

    Args:
        cache: BoundaryCache for this shape.
        snapshot: CollectionSnapshot for this shape.
        truth: dict[release_id → planted shelf position in [0, 1]].
        label: The label name used for all records in this shape.

    Returns:
        {
            "index":    {"mae": float, "p95_ms": float, "confidence_mean": float},
            "cube_only":{"mae": float, "p95_ms": float, "confidence_mean": float},
        }
    """
    # Phase 5: derive SegmentCache from cache + snapshot (no overrides in harness)
    segment_cache = SegmentCache()
    segment_cache.derive(cache, snapshot, cache.overrides)

    index_errors: list[float] = []
    index_timings_ms: list[float] = []
    index_confidences: list[float] = []

    cube_only_errors: list[float] = []
    cube_only_timings_ms: list[float] = []
    cube_only_confidences: list[float] = []

    # Derive catalog_number for each release_id from the snapshot.
    # _build_snapshot assigns release_id = i+1 (1-indexed) for catalogs in order.
    label_records: list[RecordRow] = snapshot.get_label_records(label)
    release_to_catalog: dict[int, str] = {r.release_id: r.catalog_number for r in label_records}

    for release_id, planted_pos in truth.items():
        catalog_number = release_to_catalog.get(release_id, "")

        # Phase 5: locate() dispatcher calls locate_by_segment() internally (segment-v1).
        # Per D-01: harness output key stays "index" (not renamed to "segment").
        t0 = time.perf_counter()
        index_result = locate(
            release_id=release_id,
            label=label,
            catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        index_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if index_result.sub_cube_interval is not None:
            si = index_result.sub_cube_interval
            predicted = _midpoint(si.start, si.end)
        else:
            # locate() fell back to cube-only (singleton confidence gate): worst-case 0.5
            predicted = CUBE_ONLY_NULL_MIDPOINT

        index_errors.append(abs(predicted - planted_pos))
        index_timings_ms.append(index_elapsed_ms)
        index_confidences.append(index_result.confidence)

        # §4.8 cube-only estimator (always null sub_cube_interval → worst-case 0.5)
        t0 = time.perf_counter()
        cube_result = locate_cube_only(
            release_id=release_id,
            label=label,
            _catalog_number=catalog_number,
            segment_cache=segment_cache,
            snapshot=snapshot,
        )
        cube_elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # §4.8 always returns null sub_cube_interval → score as 0.5 center-of-cube
        cube_predicted = CUBE_ONLY_NULL_MIDPOINT
        cube_only_errors.append(abs(cube_predicted - planted_pos))
        cube_only_timings_ms.append(cube_elapsed_ms)
        cube_only_confidences.append(cube_result.confidence)

    def _mae(errors: list[float]) -> float:
        return sum(errors) / len(errors) if errors else 0.0

    def _p95(timings: list[float]) -> float:
        if not timings:
            return 0.0
        sorted_t = sorted(timings)
        idx = max(0, int(len(sorted_t) * 0.95) - 1)
        return sorted_t[idx]

    def _mean(vals: list[float]) -> float:
        return sum(vals) / len(vals) if vals else 0.0

    return {
        "index": {
            "mae": _mae(index_errors),
            "p95_ms": _p95(index_timings_ms),
            "confidence_mean": _mean(index_confidences),
        },
        "cube_only": {
            "mae": _mae(cube_only_errors),
            "p95_ms": _p95(cube_only_timings_ms),
            "confidence_mean": _mean(cube_only_confidences),
        },
    }


# ── Local CSV path (developer-only, gitignored) ───────────────────────────────


def _find_local_csv(repo_root: Path) -> Path | None:
    """Find the gitignored owner collection CSV in the repo root.

    Returns None if absent (expected in CI and fresh developer checkouts).
    Guard: never fails — gracefully returns None when absent.
    """
    matches = sorted(repo_root.glob("RWlodarczyk-collection-*.csv"))
    return matches[0] if matches else None


def _run_local_csv(repo_root: Path) -> dict[str, dict[str, float]] | None:
    """Run locate() and locate_cube_only() against the local collection CSV + boundaries.yaml.

    Returns None when the CSV is absent or any loading step fails.
    This path is silently skipped under --ci.

    Phase 5: BoundaryRow no longer has last_label/last_catalog (dropped in SEG-01).
    SegmentCache is derived from cache + snapshot for the locate() calls.
    """
    csv_path = _find_local_csv(repo_root)
    if csv_path is None or not csv_path.exists():
        return None

    try:
        import csv as csv_mod

        import yaml

        boundaries_path = repo_root / "fixtures" / "boundaries.yaml"
        if not boundaries_path.exists():
            print(f"  [skip] fixtures/boundaries.yaml not found at {boundaries_path}")
            return None

        # Load boundaries — Phase 5: cut-point model (no last_*)
        from gruvax.estimator.boundary_cache import BoundaryRow

        with boundaries_path.open() as f:
            raw = yaml.safe_load(f)

        boundary_rows: list[BoundaryRow] = []
        for item in raw.get("boundaries", []):
            boundary_rows.append(
                BoundaryRow(
                    unit_id=item["unit_id"],
                    row=item["row"],
                    col=item["col"],
                    first_label=item.get("first_label"),
                    first_catalog=item.get("first_catalog"),
                    # last_label and last_catalog dropped in Phase 5 (SEG-01)
                    is_empty=item.get("is_empty", False),
                )
            )
        cache = BoundaryCache()
        cache._load_rows(boundary_rows)

        # Load collection CSV
        records_by_label: dict[str, list[RecordRow]] = {}
        with csv_path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv_mod.DictReader(f)
            release_id = 0
            for row in reader:
                release_id += 1
                label = (row.get("Label") or row.get("label") or "").strip()
                catalog = (row.get("Catalog#") or row.get("catalog_number") or "").strip()
                if not label:
                    continue
                key = label.casefold()
                if key not in records_by_label:
                    records_by_label[key] = []
                records_by_label[key].append(
                    RecordRow(release_id=release_id, label=label, catalog_number=catalog)
                )

        snapshot = CollectionSnapshot()
        snapshot._load_snapshot(records_by_label)

        # Phase 5: derive SegmentCache from loaded cache + snapshot
        segment_cache = SegmentCache()
        segment_cache.derive(cache, snapshot, cache.overrides)

        # Compute aggregate metrics across all labels
        total_index_errors: list[float] = []
        total_index_ms: list[float] = []
        total_index_conf: list[float] = []
        total_cube_errors: list[float] = []
        total_cube_ms: list[float] = []
        total_cube_conf: list[float] = []

        all_records_flat: list[RecordRow] = []
        for recs in records_by_label.values():
            all_records_flat.extend(recs)

        for rec in all_records_flat:
            t0 = time.perf_counter()
            res = locate(
                release_id=rec.release_id,
                label=rec.label,
                catalog_number=rec.catalog_number,
                segment_cache=segment_cache,
                snapshot=snapshot,
            )
            elapsed = (time.perf_counter() - t0) * 1000.0
            total_index_ms.append(elapsed)
            total_index_conf.append(res.confidence)
            # No planted truth for real CSV — we only report timing + confidence
            total_index_errors.append(0.0)

            t0 = time.perf_counter()
            cres = locate_cube_only(
                release_id=rec.release_id,
                label=rec.label,
                _catalog_number=rec.catalog_number,
                segment_cache=segment_cache,
                snapshot=snapshot,
            )
            celapsed = (time.perf_counter() - t0) * 1000.0
            total_cube_ms.append(celapsed)
            total_cube_conf.append(cres.confidence)
            total_cube_errors.append(0.0)

        def _p95(ts: list[float]) -> float:
            if not ts:
                return 0.0
            s = sorted(ts)
            idx = max(0, int(len(s) * 0.95) - 1)
            return s[idx]

        def _mean(vs: list[float]) -> float:
            return sum(vs) / len(vs) if vs else 0.0

        print(f"\n  Local CSV: {csv_path.name} — {len(all_records_flat)} records loaded")
        print(
            f"  locate()  — p95={_p95(total_index_ms):.2f} ms"
            f"  conf_mean={_mean(total_index_conf):.3f}"
        )
        print(
            f"  §4.8 cube   — p95={_p95(total_cube_ms):.2f} ms"
            f"  conf_mean={_mean(total_cube_conf):.3f}"
        )
        print(
            "  (No planted truth for real CSV — MAE not meaningful; timing + confidence shown only)"
        )
        return {
            "local_csv": {
                "index": {
                    "mae": float("nan"),
                    "p95_ms": _p95(total_index_ms),
                    "confidence_mean": _mean(total_index_conf),
                },
                "cube_only": {
                    "mae": float("nan"),
                    "p95_ms": _p95(total_cube_ms),
                    "confidence_mean": _mean(total_cube_conf),
                },
            }
        }

    except Exception as exc:
        print(f"  [skip] Local CSV path failed: {exc}")
        return None


# ── Main harness function ─────────────────────────────────────────────────────


def run_all_algorithms(ci: bool = False) -> dict[str, dict[str, dict[str, float]]]:
    """Run locate() and locate_cube_only() against all synthetic planted-truth shapes.

    Phase 5: locate() internally calls locate_by_segment() (segment-v1 estimator).
    Per D-01: the harness output structure ("index" / "cube_only") is unchanged;
    the segment estimator is NOT added as a new third algorithm in the harness.

    Args:
        ci: When True, skip the local CSV path (CI mode — CSV is gitignored).
            When False (developer run), also run against the local CSV if present.

    Returns:
        Per-shape results dict:
        {
            shape_name: {
                "index":     {"mae": float, "p95_ms": float, "confidence_mean": float},
                "cube_only": {"mae": float, "p95_ms": float, "confidence_mean": float},
            },
            ...
        }
        Shape names: "uniform_dense", "sparse_gappy", "multi_prefix", "singleton".
        Under --ci the "local_csv" key is absent.
    """
    shapes = all_shapes()
    results: dict[str, dict[str, dict[str, float]]] = {}

    print("\n=== GRUVAX A/B Harness: locate() [segment-v1] vs §4.8 cube-only ===")
    print(f"{'Shape':<18} {'Estimator':<12} {'MAE':>8} {'p95 ms':>9} {'conf':>7}")
    print("-" * 60)

    aggregate_p95_ms: list[float] = []

    for shape_name, factory in shapes.items():
        cache, snapshot, truth = factory()

        # Derive label from the first record group in the snapshot (via _by_label)
        label_groups = list(snapshot._by_label.values())
        label = label_groups[0][0].label if label_groups and label_groups[0] else shape_name

        metrics = _score_shape(cache, snapshot, truth, label)
        results[shape_name] = metrics

        idx = metrics["index"]
        co = metrics["cube_only"]

        print(
            f"  {shape_name:<16} locate()     MAE={idx['mae']:.4f}"
            f"  p95={idx['p95_ms']:.2f}ms  conf={idx['confidence_mean']:.3f}"
        )
        print(
            f"  {'':<16} §4.8 cube    MAE={co['mae']:.4f}"
            f"  p95={co['p95_ms']:.2f}ms  conf={co['confidence_mean']:.3f}"
        )

        better = (
            "=" if abs(idx["mae"] - co["mae"]) < 1e-9 else ("<" if idx["mae"] < co["mae"] else ">")
        )
        print(
            f"  {'':<16} locate() MAE {better} §4.8 MAE {'[PASS]' if better in ('<', '=') else '[FAIL]'}"
        )
        print()

        aggregate_p95_ms.extend([idx["p95_ms"], co["p95_ms"]])

    # Aggregate timing check (POS-03 budget)
    agg_p95 = max(aggregate_p95_ms) if aggregate_p95_ms else 0.0
    budget_ok = agg_p95 < P95_BUDGET_MS
    print(
        f"Aggregate p95 timing: {agg_p95:.2f} ms (budget: {P95_BUDGET_MS:.0f} ms) "
        f"{'[OK]' if budget_ok else '[OVER BUDGET]'}"
    )

    # Local CSV path (developer only — skipped under --ci or when CSV absent)
    if not ci:
        local_results = _run_local_csv(_REPO_ROOT)
        if local_results:
            results.update(local_results)
    else:
        print("\n[--ci] Local CSV path skipped (synthetic shapes only)")

    return results


# ── CLI entry point ───────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "GRUVAX A/B harness: compare locate() [segment-v1] vs §4.8 (cube-only) "
            "position estimators across synthetic planted-truth collection shapes."
        )
    )
    parser.add_argument(
        "--ci",
        action="store_true",
        help="CI mode: run synthetic shapes only; skip the gitignored local CSV.",
    )
    args = parser.parse_args()
    run_all_algorithms(ci=args.ci)


if __name__ == "__main__":
    main()

"""Benchmark SLO gate — checks pytest-benchmark JSON output for p95 regressions.

Usage:
    uv run python scripts/check_benchmark.py benchmark.json

Exits 0 if all benchmarks are within their SLO budgets.
Exits 1 with a clear message if any benchmark exceeds its budget.

SLO budgets (v1 acceptance criteria, SC#5):
  - /api/search  (test_search_slo_benchmark) : p95 <= 200 ms
  - locate algo  (test_locate_benchmark)     : p95 <=  50 ms

SC#5 specifies p95, not mean. pytest-benchmark's JSON does not emit a p95 field,
but it does include raw per-round samples under stats["data"]. We compute
the nearest-rank 95th percentile and fail if samples are absent or invalid.
Use --require to reject missing expected benchmarks even when another passes.

This script is stdlib-only (json + math + sys) — no third-party imports required.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys


def _p95_ms(stats: dict[str, object]) -> tuple[float, str]:
    """Return (value_ms, metric_label) — p95 from raw samples, or a failing sentinel."""
    data = stats.get("data")
    if not isinstance(data, list) or not data:
        return float("inf"), "missing-p95-samples"
    try:
        samples = sorted(float(x) for x in data)
    except TypeError, ValueError:
        return float("inf"), "invalid-p95-samples"
    if any(not math.isfinite(x) or x < 0 for x in samples):
        return float("inf"), "invalid-p95-samples"
    rank = math.ceil(0.95 * len(samples)) - 1
    return samples[rank] * 1000.0, "p95"


# SLO budgets in milliseconds (seconds * 1000 conversion is applied below)
_BUDGETS: dict[str, float] = {
    "test_search_slo_benchmark": 200.0,
    "test_locate_benchmark": 50.0,
    "test_locate_slo_benchmark": 50.0,
}


def _check(path: str, required: tuple[str, ...] = ()) -> bool:
    """Parse benchmark JSON and check each known benchmark against its budget.

    Returns True if all budgets pass, False if any breach is found.
    """
    try:
        with Path(path).open() as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: benchmark file not found: {path}", file=sys.stderr)
        return False
    except json.JSONDecodeError as exc:
        print(f"ERROR: benchmark file is not valid JSON: {exc}", file=sys.stderr)
        return False

    if not isinstance(data, dict):
        print("ERROR: benchmark JSON must be an object", file=sys.stderr)
        return False
    benchmarks = data.get("benchmarks", [])
    if not benchmarks:
        print("ERROR: no benchmarks found in JSON file", file=sys.stderr)
        return False

    passed = True
    checked: set[str] = set()

    for bench in benchmarks:
        name: str = bench.get("name", "")
        # Match by the function name portion (after '::' separator if present)
        short_name = name.rsplit("::", maxsplit=1)[-1] if "::" in name else name

        for budget_key, budget_ms in _BUDGETS.items():
            if budget_key != short_name.split("[", 1)[0]:
                continue

            stats = bench.get("stats", {})
            value_ms, metric = _p95_ms(stats)
            checked.add(budget_key)

            if value_ms <= budget_ms:
                print(f"PASS  {short_name}: {metric}={value_ms:.2f}ms <= {budget_ms:.0f}ms")
            else:
                print(
                    f"FAIL  {short_name}: {metric}={value_ms:.2f}ms > {budget_ms:.0f}ms  "
                    f"(SLO breach: +{value_ms - budget_ms:.2f}ms over budget)",
                    file=sys.stderr,
                )
                passed = False

    if not checked:
        print("ERROR: no known SLO benchmarks were checked", file=sys.stderr)
        passed = False
    missing = set(required) - checked
    if missing:
        print(
            f"ERROR: required SLO benchmarks missing: {', '.join(sorted(missing))}", file=sys.stderr
        )
        passed = False

    return passed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path")
    parser.add_argument("--require", nargs="+", choices=sorted(_BUDGETS), default=[])
    args = parser.parse_args()
    ok = _check(args.path, tuple(args.require))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

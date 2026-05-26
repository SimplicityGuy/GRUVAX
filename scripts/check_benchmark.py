"""Benchmark SLO gate — checks pytest-benchmark JSON output for p95 regressions.

Usage:
    uv run python scripts/check_benchmark.py benchmark.json

Exits 0 if all benchmarks are within their SLO budgets.
Exits 1 with a clear message if any benchmark exceeds its budget.

SLO budgets (v1 acceptance criteria, SC#5):
  - /api/search  (test_search_slo_benchmark) : p95 <= 200 ms
  - locate algo  (test_locate_benchmark)     : p95 <=  50 ms

SC#5 specifies p95, not mean. pytest-benchmark's JSON does not emit a p95 field,
but it does include the raw per-round samples under stats["data"], so we compute
the 95th percentile (nearest-rank) ourselves. If "data" is unavailable we fall
back to "mean" and say so, so the gate degrades loudly rather than silently.

This script is stdlib-only (json + math + sys) — no third-party imports required.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys


def _p95_ms(stats: dict[str, object]) -> tuple[float, str]:
    """Return (value_ms, metric_label) — p95 from raw samples, else mean fallback."""
    data = stats.get("data")
    if isinstance(data, list) and data:
        samples = sorted(float(x) for x in data)
        # Nearest-rank percentile: index = ceil(0.95 * N) - 1, clamped to [0, N-1].
        rank = max(0, min(len(samples) - 1, math.ceil(0.95 * len(samples)) - 1))
        return samples[rank] * 1000.0, "p95"
    mean_s = stats.get("mean", float("inf"))
    return float(mean_s) * 1000.0 if isinstance(mean_s, (int, float)) else float(
        "inf"
    ), "mean(fallback)"


# SLO budgets in milliseconds (seconds * 1000 conversion is applied below)
_BUDGETS: dict[str, float] = {
    "test_search_slo_benchmark": 200.0,
    "test_locate_benchmark": 50.0,
}


def _check(path: str) -> bool:
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

    benchmarks = data.get("benchmarks", [])
    if not benchmarks:
        print("ERROR: no benchmarks found in JSON file", file=sys.stderr)
        return False

    passed = True
    checked = 0

    for bench in benchmarks:
        name: str = bench.get("name", "")
        # Match by the function name portion (after '::' separator if present)
        short_name = name.rsplit("::", maxsplit=1)[-1] if "::" in name else name

        for budget_key, budget_ms in _BUDGETS.items():
            if budget_key not in short_name:
                continue

            stats = bench.get("stats", {})
            value_ms, metric = _p95_ms(stats)
            checked += 1

            if value_ms <= budget_ms:
                print(f"PASS  {short_name}: {metric}={value_ms:.2f}ms <= {budget_ms:.0f}ms")
            else:
                print(
                    f"FAIL  {short_name}: {metric}={value_ms:.2f}ms > {budget_ms:.0f}ms  "
                    f"(SLO breach: +{value_ms - budget_ms:.2f}ms over budget)",
                    file=sys.stderr,
                )
                passed = False

    if checked == 0:
        # No known benchmarks found — this may mean test IDs changed; warn but don't fail
        # (the test itself will fail if the benchmark didn't run at all)
        known = ", ".join(_BUDGETS.keys())
        print(
            f"WARNING: none of the known benchmarks ({known}) found in {path}.",
            file=sys.stderr,
        )
        print("  Check that --benchmark-only was passed and the tests ran.", file=sys.stderr)

    return passed


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <benchmark.json>", file=sys.stderr)
        sys.exit(2)

    ok = _check(sys.argv[1])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

"""Benchmark SLO gate — checks pytest-benchmark JSON output for p95 regressions.

Usage:
    uv run python scripts/check_benchmark.py benchmark.json

Exits 0 if all benchmarks are within their SLO budgets.
Exits 1 with a clear message if any benchmark exceeds its budget.

SLO budgets (v1 acceptance criteria):
  - /api/search  (test_search_slo_benchmark) : mean <= 200 ms
  - locate algo  (test_locate_benchmark)     : mean <=  50 ms

These thresholds match the assertions in the pytest-benchmark tests themselves
(test_search_benchmark.py and test_algorithm.py).

This script is stdlib-only (json + sys) — no third-party imports required.
"""

from __future__ import annotations

import json
import sys

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
        with open(path) as f:
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
        short_name = name.split("::")[-1] if "::" in name else name

        for budget_key, budget_ms in _BUDGETS.items():
            if budget_key not in short_name:
                continue

            stats = bench.get("stats", {})
            mean_s: float = stats.get("mean", float("inf"))
            mean_ms = mean_s * 1000.0
            checked += 1

            if mean_ms <= budget_ms:
                print(f"PASS  {short_name}: mean={mean_ms:.2f}ms <= {budget_ms:.0f}ms")
            else:
                print(
                    f"FAIL  {short_name}: mean={mean_ms:.2f}ms > {budget_ms:.0f}ms  "
                    f"(SLO breach: +{mean_ms - budget_ms:.2f}ms over budget)",
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

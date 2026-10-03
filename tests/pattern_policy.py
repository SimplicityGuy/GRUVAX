"""A missing feature or fixture must fail its test, never silently skip it."""

from __future__ import annotations

import pytest


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):  # type: ignore[no-untyped-def]
    report = yield
    if report.skipped:
        marker = item.get_closest_marker("skip") or item.get_closest_marker("skipif")
        explicit_platform = marker and "platform" in str(marker.kwargs.get("reason", "")).lower()
        reason = str(report.longrepr)
        benchmark = "Skipping benchmark (--benchmark-skip active)." in reason
        if not explicit_platform and not benchmark:
            report.outcome = "failed"
            report.longrepr = f"Unexpected runtime skip in {item.nodeid}: {reason}. Assert the implemented behavior or repair its fixture."
    return report

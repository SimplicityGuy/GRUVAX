"""Unit tests for src/gruvax/middleware/timing.py.

Tests:
  - SLO_THRESHOLDS_MS == {"/api/search": 200.0, "/api/locate": 50.0}
  - record_slow_query() appends an entry only when total_ms > threshold.
  - Entry dict has keys: path, total_ms, db_ms, threshold_ms, ts.
  - Fast request (below threshold) appends nothing.
  - total_ms and db_ms are rounded to 1 decimal place.
  - ts is a float (Unix timestamp).
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any
from unittest.mock import MagicMock

from gruvax.middleware.timing import SLO_THRESHOLDS_MS, record_slow_query


class TestSloThresholds:
    """Tests for SLO_THRESHOLDS_MS constant."""

    def test_search_threshold(self) -> None:
        """Search SLO threshold is 200.0 ms."""
        assert SLO_THRESHOLDS_MS["/api/search"] == 200.0

    def test_locate_threshold(self) -> None:
        """Locate SLO threshold is 50.0 ms."""
        assert SLO_THRESHOLDS_MS["/api/locate"] == 50.0

    def test_exact_dict_shape(self) -> None:
        """SLO_THRESHOLDS_MS has exactly the two expected keys."""
        assert SLO_THRESHOLDS_MS == {"/api/search": 200.0, "/api/locate": 50.0}

    def test_values_are_floats(self) -> None:
        """Threshold values are floats, not ints."""
        for value in SLO_THRESHOLDS_MS.values():
            assert isinstance(value, float)


class TestRecordSlowQuery:
    """Tests for the record_slow_query() helper."""

    def _make_app_with_ring(self, maxlen: int = 50) -> Any:
        """Return a mock 'app' object with app.state.slow_query_ring set."""
        ring: deque[dict[str, Any]] = deque(maxlen=maxlen)
        app = MagicMock()
        app.state.slow_query_ring = ring
        return app, ring

    def test_appends_when_above_search_threshold(self) -> None:
        """Appends entry when /api/search total_ms > 200.0."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=250.0, db_ms=200.0)
        assert len(ring) == 1

    def test_appends_when_above_locate_threshold(self) -> None:
        """Appends entry when /api/locate total_ms > 50.0."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/locate", total_ms=75.5, db_ms=0.0)
        assert len(ring) == 1

    def test_does_not_append_when_fast_search(self) -> None:
        """Fast /api/search (below 200 ms) appends nothing."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=150.0, db_ms=100.0)
        assert len(ring) == 0

    def test_does_not_append_when_fast_locate(self) -> None:
        """Fast /api/locate (below 50 ms) appends nothing."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/locate", total_ms=30.0, db_ms=0.0)
        assert len(ring) == 0

    def test_does_not_append_at_exact_threshold(self) -> None:
        """Request at exactly the threshold (== 200.0) is NOT slow (must be >)."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=200.0, db_ms=150.0)
        assert len(ring) == 0

    def test_does_not_append_for_unknown_path(self) -> None:
        """Paths not in SLO_THRESHOLDS_MS are silently ignored."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/health", total_ms=9999.0, db_ms=0.0)
        assert len(ring) == 0

    def test_entry_has_required_keys(self) -> None:
        """Appended entry dict has path, total_ms, db_ms, threshold_ms, ts."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=300.0, db_ms=250.0)
        entry = ring[0]
        assert "path" in entry
        assert "total_ms" in entry
        assert "db_ms" in entry
        assert "threshold_ms" in entry
        assert "ts" in entry

    def test_entry_path_correct(self) -> None:
        """path key matches the passed path argument."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=300.0, db_ms=0.0)
        assert ring[0]["path"] == "/api/search"

    def test_entry_threshold_ms_correct(self) -> None:
        """threshold_ms key matches the SLO for the endpoint."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=300.0, db_ms=0.0)
        assert ring[0]["threshold_ms"] == 200.0

    def test_entry_total_ms_rounded(self) -> None:
        """total_ms is rounded to 1 decimal place."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=201.234567, db_ms=0.0)
        entry = ring[0]
        # Should be round(201.234567, 1) == 201.2
        assert entry["total_ms"] == round(201.234567, 1)

    def test_entry_db_ms_rounded(self) -> None:
        """db_ms is rounded to 1 decimal place."""
        app, ring = self._make_app_with_ring()
        record_slow_query(app, "/api/search", total_ms=300.0, db_ms=199.876)
        entry = ring[0]
        assert entry["db_ms"] == round(199.876, 1)

    def test_entry_ts_is_float(self) -> None:
        """ts is a float (Unix timestamp)."""
        app, ring = self._make_app_with_ring()
        before = time.time()
        record_slow_query(app, "/api/search", total_ms=300.0, db_ms=0.0)
        after = time.time()
        ts = ring[0]["ts"]
        assert isinstance(ts, float)
        assert before <= ts <= after

    def test_ring_evicts_when_full(self) -> None:
        """Ring buffer evicts oldest entries when maxlen is exceeded."""
        app, ring = self._make_app_with_ring(maxlen=3)
        for _ in range(5):
            record_slow_query(app, "/api/search", total_ms=300.0, db_ms=0.0)
        assert len(ring) == 3

    def test_no_app_state_ring_does_not_crash(self) -> None:
        """If app.state.slow_query_ring is absent, record_slow_query is a no-op."""
        app = MagicMock()
        # Return a fresh empty deque when getattr is called (fallback)
        type(app.state).slow_query_ring = MagicMock(
            side_effect=AttributeError("no slow_query_ring")
        )
        # Should not raise
        record_slow_query(app, "/api/search", total_ms=300.0, db_ms=0.0)

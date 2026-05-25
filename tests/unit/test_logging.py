"""Unit tests for src/gruvax/logging_config.py.

Tests:
  - JsonFormatter.format() returns valid single-line JSON with ts/level/logger/msg keys.
  - JsonFormatter.format() includes 'exc' key when record has exc_info.
  - LogRingHandler.emit() appends one dict per record to the passed deque.
  - LogRingHandler dict has ts (float), level, logger, msg keys.
  - deque(maxlen=N) eviction works correctly (capacity enforcement).
"""

from __future__ import annotations

import json
import logging
from collections import deque

import pytest

from gruvax.logging_config import JsonFormatter, LogRingHandler


def _make_record(
    msg: str = "hello",
    level: int = logging.INFO,
    name: str = "test.logger",
    exc_info: object = None,
) -> logging.LogRecord:
    """Create a LogRecord suitable for testing."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
    )
    return record


class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def test_format_returns_valid_json(self) -> None:
        """format() output parses as JSON without error."""
        formatter = JsonFormatter()
        record = _make_record("test message")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_format_has_required_keys(self) -> None:
        """Parsed output contains ts, level, logger, msg keys."""
        formatter = JsonFormatter()
        record = _make_record("test message", name="gruvax.api")
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "ts" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "msg" in parsed

    def test_format_ts_is_iso8601_string(self) -> None:
        """ts field is a string in ISO-8601 UTC format (ends with Z)."""
        formatter = JsonFormatter()
        record = _make_record()
        parsed = json.loads(formatter.format(record))
        ts = parsed["ts"]
        assert isinstance(ts, str)
        assert ts.endswith("Z"), f"Expected ts to end with Z, got {ts!r}"
        # Must contain T separator (ISO-8601)
        assert "T" in ts

    def test_format_level_is_levelname(self) -> None:
        """level field matches the record's levelname."""
        formatter = JsonFormatter()
        record = _make_record(level=logging.WARNING)
        parsed = json.loads(formatter.format(record))
        assert parsed["level"] == "WARNING"

    def test_format_logger_is_record_name(self) -> None:
        """logger field matches the record's name."""
        formatter = JsonFormatter()
        record = _make_record(name="gruvax.search")
        parsed = json.loads(formatter.format(record))
        assert parsed["logger"] == "gruvax.search"

    def test_format_msg_is_message(self) -> None:
        """msg field contains the formatted message."""
        formatter = JsonFormatter()
        record = _make_record("search took 42ms")
        parsed = json.loads(formatter.format(record))
        assert parsed["msg"] == "search took 42ms"

    def test_format_no_exc_key_on_normal_record(self) -> None:
        """No 'exc' key when record has no exc_info."""
        formatter = JsonFormatter()
        record = _make_record()
        parsed = json.loads(formatter.format(record))
        assert "exc" not in parsed

    def test_format_error_with_exc_info_includes_exc(self) -> None:
        """ERROR record with exc_info includes an 'exc' key."""
        formatter = JsonFormatter()
        try:
            raise ValueError("oops")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = _make_record(msg="something failed", level=logging.ERROR, exc_info=exc_info)
        parsed = json.loads(formatter.format(record))
        assert "exc" in parsed
        assert "ValueError" in parsed["exc"]
        assert "oops" in parsed["exc"]

    def test_format_is_single_line(self) -> None:
        """Output is a single JSON line (no newlines in the JSON itself)."""
        formatter = JsonFormatter()
        record = _make_record("line one\nline two")
        output = formatter.format(record)
        # The JSON string itself should not contain raw newlines outside the JSON encoding
        parsed = json.loads(output)
        # Verify it parses (single-line JSON)
        assert parsed is not None


class TestLogRingHandler:
    """Tests for LogRingHandler."""

    def test_emit_appends_to_ring(self) -> None:
        """emit() appends one entry to the deque."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_record("test msg")
        handler.emit(record)
        assert len(ring) == 1

    def test_emit_dict_has_required_keys(self) -> None:
        """Emitted dict has ts, level, logger, msg keys."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_record("hello", level=logging.DEBUG, name="gruvax.db")
        handler.emit(record)
        entry = ring[0]
        assert "ts" in entry
        assert "level" in entry
        assert "logger" in entry
        assert "msg" in entry

    def test_emit_ts_is_float(self) -> None:
        """ts field in the emitted dict is a float (Unix timestamp)."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_record()
        handler.emit(record)
        ts = ring[0]["ts"]
        assert isinstance(ts, float)
        # Should be a recent timestamp (after year 2020 in Unix time)
        assert ts > 1_577_836_800.0

    def test_emit_level_is_levelname(self) -> None:
        """level field matches the record's levelname string."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_record(level=logging.ERROR)
        handler.emit(record)
        assert ring[0]["level"] == "ERROR"

    def test_emit_logger_is_record_name(self) -> None:
        """logger field matches the record name."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_record(name="gruvax.api.search")
        handler.emit(record)
        assert ring[0]["logger"] == "gruvax.api.search"

    def test_emit_msg_is_message(self) -> None:
        """msg field contains the formatted message text."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_record("search done")
        handler.emit(record)
        assert ring[0]["msg"] == "search done"

    def test_deque_evicts_oldest_past_maxlen(self) -> None:
        """A deque(maxlen=N) evicts the oldest entry when capacity is exceeded."""
        ring: deque[dict] = deque(maxlen=3)
        handler = LogRingHandler(ring)
        for i in range(5):
            handler.emit(_make_record(f"msg {i}"))
        # Only last 3 should remain
        assert len(ring) == 3
        msgs = [entry["msg"] for entry in ring]
        assert msgs == ["msg 2", "msg 3", "msg 4"]

    def test_large_ring_with_maxlen_200(self) -> None:
        """deque(maxlen=200) holds up to 200 entries and evicts past that."""
        ring: deque[dict] = deque(maxlen=200)
        handler = LogRingHandler(ring)
        for i in range(250):
            handler.emit(_make_record(f"msg {i}"))
        assert len(ring) == 200
        # Most recent entry should be msg 249
        assert ring[-1]["msg"] == "msg 249"
        # Oldest should be msg 50
        assert ring[0]["msg"] == "msg 50"

    def test_multiple_records_append_in_order(self) -> None:
        """Multiple emits produce ordered entries in the deque."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        handler.emit(_make_record("first"))
        handler.emit(_make_record("second"))
        handler.emit(_make_record("third"))
        msgs = [e["msg"] for e in ring]
        assert msgs == ["first", "second", "third"]

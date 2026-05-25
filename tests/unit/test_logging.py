"""Unit tests for src/gruvax/logging_config.py (post-structlog migration).

Tests:
  - LogRingHandler.emit() appends one dict per record to the passed deque.
  - LogRingHandler dict has ts (float), level (str), logger (str), msg (str) keys.
  - LogRingHandler handles structlog-native records (record.msg is a dict).
  - LogRingHandler handles stdlib foreign records (record.msg is a string).
  - deque(maxlen=N) eviction works correctly (capacity enforcement).
"""

from __future__ import annotations

import logging
from collections import deque

from gruvax.logging_config import LogRingHandler


def _make_string_record(
    msg: str = "hello",
    level: int = logging.INFO,
    name: str = "test.logger",
) -> logging.LogRecord:
    """Create a stdlib-style LogRecord with a plain string msg."""
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    return record


def _make_dict_record(
    event: str = "hello",
    level: int = logging.INFO,
    name: str = "gruvax.api",
) -> logging.LogRecord:
    """Create a structlog-native LogRecord where msg is the event dict.

    structlog wraps its log calls into stdlib LogRecords with record.msg set to
    the event dict (a Python dict) before ProcessorFormatter renders it to JSON
    for stdout.  LogRingHandler.emit() fires on this unmodified record.
    """
    record = logging.LogRecord(
        name=name,
        level=level,
        pathname="test.py",
        lineno=1,
        msg={"event": event, "level": "info"},
        args=(),
        exc_info=None,
    )
    return record


class TestLogRingHandler:
    """Tests for LogRingHandler."""

    def test_emit_appends_to_ring(self) -> None:
        """emit() appends one entry to the deque."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_string_record("test msg")
        handler.emit(record)
        assert len(ring) == 1

    def test_emit_dict_has_required_keys(self) -> None:
        """Emitted dict has ts, level, logger, msg keys."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_string_record("hello", level=logging.DEBUG, name="gruvax.db")
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
        record = _make_string_record()
        handler.emit(record)
        ts = ring[0]["ts"]
        assert isinstance(ts, float)
        # Should be a recent timestamp (after year 2020 in Unix time)
        assert ts > 1_577_836_800.0

    def test_emit_level_is_levelname(self) -> None:
        """level field matches the record's levelname string."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_string_record(level=logging.ERROR)
        handler.emit(record)
        assert ring[0]["level"] == "ERROR"

    def test_emit_logger_is_record_name(self) -> None:
        """logger field matches the record name."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_string_record(name="gruvax.api.search")
        handler.emit(record)
        assert ring[0]["logger"] == "gruvax.api.search"

    def test_emit_msg_stdlib_string_record(self) -> None:
        """msg field contains getMessage() text for stdlib foreign records."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_string_record("search done")
        handler.emit(record)
        assert ring[0]["msg"] == "search done"

    def test_emit_msg_structlog_dict_record(self) -> None:
        """msg field extracts 'event' key for structlog-native records (record.msg is dict)."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = _make_dict_record("boundary cache loaded")
        handler.emit(record)
        assert ring[0]["msg"] == "boundary cache loaded"

    def test_emit_msg_structlog_dict_missing_event(self) -> None:
        """Structlog-native dict without 'event' key produces empty string msg."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        record = logging.LogRecord(
            name="gruvax.test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg={"level": "info"},  # no 'event' key
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert ring[0]["msg"] == ""

    def test_emit_structlog_does_not_mutate_record(self) -> None:
        """emit() must not modify record.msg (ProcessorFormatter needs it intact)."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        original_msg = {"event": "startup complete", "level": "info"}
        record = _make_dict_record("startup complete")
        # Capture the original dict id
        original_id = id(record.msg)
        handler.emit(record)
        # record.msg must still be the same dict object, unmodified
        assert id(record.msg) == original_id
        assert record.msg == original_msg

    def test_deque_evicts_oldest_past_maxlen(self) -> None:
        """A deque(maxlen=N) evicts the oldest entry when capacity is exceeded."""
        ring: deque[dict] = deque(maxlen=3)
        handler = LogRingHandler(ring)
        for i in range(5):
            handler.emit(_make_string_record(f"msg {i}"))
        # Only last 3 should remain
        assert len(ring) == 3
        msgs = [entry["msg"] for entry in ring]
        assert msgs == ["msg 2", "msg 3", "msg 4"]

    def test_large_ring_with_maxlen_200(self) -> None:
        """deque(maxlen=200) holds up to 200 entries and evicts past that."""
        ring: deque[dict] = deque(maxlen=200)
        handler = LogRingHandler(ring)
        for i in range(250):
            handler.emit(_make_string_record(f"msg {i}"))
        assert len(ring) == 200
        # Most recent entry should be msg 249
        assert ring[-1]["msg"] == "msg 249"
        # Oldest should be msg 50
        assert ring[0]["msg"] == "msg 50"

    def test_multiple_records_append_in_order(self) -> None:
        """Multiple emits produce ordered entries in the deque."""
        ring: deque[dict] = deque()
        handler = LogRingHandler(ring)
        handler.emit(_make_string_record("first"))
        handler.emit(_make_string_record("second"))
        handler.emit(_make_string_record("third"))
        msgs = [e["msg"] for e in ring]
        assert msgs == ["first", "second", "third"]

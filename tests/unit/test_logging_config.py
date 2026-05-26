"""Unit tests for configure_logging() in src/gruvax/logging_config.py.

Wave-0 regression: verify that LOG_LEVEL env-variable plumbing raises (or lowers)
the effective level on the gruvax logger as expected.

Design decisions:
  - Each test case snapshots and restores the root logger handlers/level AND the gruvax
    logger handlers/level so the suite stays order-independent (project memory:
    suite must stay order-independent per commit a26252d).
  - configure_logging() uses logging.basicConfig(force=True) internally, so it is safe
    to call multiple times within a process; the fixture restores the prior state.
  - structlog.configure() is also reset between tests via a fixture to prevent
    cache_logger_on_first_use from carrying state across test cases.
"""

from __future__ import annotations

from collections import deque
import logging
from typing import Any

import pytest
import structlog

from gruvax.logging_config import configure_logging


@pytest.fixture(autouse=True)
def restore_logging_state() -> Any:
    """Snapshot and restore Python logging + structlog state around each test.

    Ensures test cases are completely isolated from each other's configure_logging()
    calls.  Restores:
    - Root logger level and handlers (configure_logging calls basicConfig(force=True))
    - gruvax logger level and handlers
    - structlog configuration (reset to defaults to clear cache_logger_on_first_use)
    """
    # ── Snapshot ─────────────────────────────────────────────────────────────
    root = logging.getLogger()
    root_level_before = root.level
    root_handlers_before = list(root.handlers)

    gruvax_logger = logging.getLogger("gruvax")
    gruvax_level_before = gruvax_logger.level
    gruvax_handlers_before = list(gruvax_logger.handlers)
    gruvax_propagate_before = gruvax_logger.propagate

    yield

    # ── Restore ──────────────────────────────────────────────────────────────
    # Remove any handlers added by the test (close them to release file/stream resources).
    for h in root.handlers:
        if h not in root_handlers_before:
            h.close()
    root.handlers = root_handlers_before
    root.setLevel(root_level_before)

    for h in gruvax_logger.handlers:
        if h not in gruvax_handlers_before:
            h.close()
    gruvax_logger.handlers = gruvax_handlers_before
    gruvax_logger.setLevel(gruvax_level_before)
    gruvax_logger.propagate = gruvax_propagate_before

    # Reset structlog to clear cached bound loggers from cache_logger_on_first_use.
    structlog.reset_defaults()


def test_configure_logging_debug_enables_debug() -> None:
    """configure_logging("DEBUG", ring) makes the gruvax logger effective-level-enabled for DEBUG."""
    ring: deque[dict[str, Any]] = deque()
    configure_logging("DEBUG", ring)
    gruvax_logger = logging.getLogger("gruvax")
    assert gruvax_logger.isEnabledFor(logging.DEBUG), (
        "After configure_logging('DEBUG'), logging.getLogger('gruvax').isEnabledFor(DEBUG) "
        "must be True.  Check that configure_logging() sets basicConfig(level=DEBUG, force=True)."
    )


def test_configure_logging_warning_disables_debug() -> None:
    """configure_logging("WARNING", ring) makes the gruvax logger NOT effective-level-enabled for DEBUG."""
    ring: deque[dict[str, Any]] = deque()
    configure_logging("WARNING", ring)
    gruvax_logger = logging.getLogger("gruvax")
    assert not gruvax_logger.isEnabledFor(logging.DEBUG), (
        "After configure_logging('WARNING'), logging.getLogger('gruvax').isEnabledFor(DEBUG) "
        "must be False.  The effective level should be WARNING (30), not DEBUG (10)."
    )


def test_configure_logging_warning_enables_warning() -> None:
    """configure_logging("WARNING", ring) enables WARNING level on gruvax logger."""
    ring: deque[dict[str, Any]] = deque()
    configure_logging("WARNING", ring)
    gruvax_logger = logging.getLogger("gruvax")
    assert gruvax_logger.isEnabledFor(logging.WARNING), (
        "After configure_logging('WARNING'), logging.getLogger('gruvax').isEnabledFor(WARNING) "
        "must be True."
    )


def test_configure_logging_info_is_default() -> None:
    """configure_logging("INFO", ring) enables INFO level."""
    ring: deque[dict[str, Any]] = deque()
    configure_logging("INFO", ring)
    gruvax_logger = logging.getLogger("gruvax")
    assert gruvax_logger.isEnabledFor(logging.INFO)
    assert not gruvax_logger.isEnabledFor(logging.DEBUG)


def test_configure_logging_invalid_level_falls_back_to_info() -> None:
    """configure_logging() falls back to INFO for unrecognised level strings."""
    ring: deque[dict[str, Any]] = deque()
    configure_logging("NOTAVALIDLEVEL", ring)
    root = logging.getLogger()
    # Should default to INFO (20), not DEBUG (10) or WARNING (30).
    assert root.level == logging.INFO, (
        f"Expected root logger level INFO (20) for invalid log_level string, got {root.level}"
    )


def test_configure_logging_attaches_ring_handler_to_gruvax_logger() -> None:
    """configure_logging() attaches LogRingHandler to the gruvax logger, not root."""
    from gruvax.logging_config import LogRingHandler

    ring: deque[dict[str, Any]] = deque()
    configure_logging("INFO", ring)

    gruvax_logger = logging.getLogger("gruvax")
    ring_handlers = [h for h in gruvax_logger.handlers if isinstance(h, LogRingHandler)]
    assert len(ring_handlers) >= 1, (
        "configure_logging() must attach LogRingHandler to logging.getLogger('gruvax'), "
        f"but found no LogRingHandler.  Handlers: {gruvax_logger.handlers!r}"
    )

    # Root logger must NOT have a LogRingHandler (T-9-IL: secret-leak guard).
    root = logging.getLogger()
    root_ring_handlers = [h for h in root.handlers if isinstance(h, LogRingHandler)]
    assert len(root_ring_handlers) == 0, (
        "configure_logging() must NOT attach LogRingHandler to the root logger. "
        "Third-party loggers (psycopg/uvicorn) propagate to root; attaching the ring "
        "there would leak secrets to the admin UI (T-9-IL).  "
        f"Root handlers: {root.handlers!r}"
    )


def test_configure_logging_ring_receives_gruvax_records() -> None:
    """Records from the gruvax logger appear in the ring after configure_logging()."""
    ring: deque[dict[str, Any]] = deque(maxlen=50)
    configure_logging("INFO", ring)

    test_logger = logging.getLogger("gruvax.test.ring_receives")
    test_logger.info("test ring record")

    assert len(ring) >= 1, "Ring must contain at least one entry after an INFO log on gruvax.*"
    msgs = [e["msg"] for e in ring]
    assert any("test ring record" in m for m in msgs), (
        f"Expected 'test ring record' in ring msgs but got: {msgs!r}"
    )


def test_configure_logging_ring_excludes_third_party_records() -> None:
    """Records from non-gruvax loggers do NOT appear in the ring (T-9-IL)."""
    ring: deque[dict[str, Any]] = deque(maxlen=50)
    configure_logging("INFO", ring)
    ring.clear()  # clear any startup noise

    logging.getLogger("psycopg").info("DSN=postgresql://secret:password@host/db")
    logging.getLogger("sqlalchemy.engine").info("some engine message")

    logger_names = [e["logger"] for e in ring]
    for name in logger_names:
        assert name.startswith("gruvax"), (
            f"Non-gruvax logger {name!r} appeared in the ring — T-9-IL secret-leak guard failed."
        )


def test_configure_logging_is_order_independent() -> None:
    """Two sequential configure_logging calls with different levels each set the correct level.

    Verifies the restore_logging_state fixture + basicConfig(force=True) combine to make
    configure_logging() repeatable within and across tests.
    """
    ring1: deque[dict[str, Any]] = deque()
    configure_logging("DEBUG", ring1)
    assert logging.getLogger("gruvax").isEnabledFor(logging.DEBUG)

    ring2: deque[dict[str, Any]] = deque()
    configure_logging("WARNING", ring2)
    gruvax_logger = logging.getLogger("gruvax")
    assert not gruvax_logger.isEnabledFor(logging.DEBUG), (
        "After the second configure_logging('WARNING') call, DEBUG must no longer be enabled."
    )
    assert gruvax_logger.isEnabledFor(logging.WARNING)


def test_configure_logging_no_duplicate_ring_handlers() -> None:
    """Calling configure_logging() twice must not duplicate ring entries (WR-02 regression).

    Each log record must appear exactly once in the ring, not N times for N configure_logging calls.
    """
    from gruvax.logging_config import LogRingHandler

    ring1: deque[dict[str, Any]] = deque(maxlen=50)
    configure_logging("INFO", ring1)

    ring2: deque[dict[str, Any]] = deque(maxlen=50)
    configure_logging("INFO", ring2)

    # After the second call there must be exactly ONE LogRingHandler on the gruvax logger.
    gruvax_logger = logging.getLogger("gruvax")
    ring_handlers = [h for h in gruvax_logger.handlers if isinstance(h, LogRingHandler)]
    assert len(ring_handlers) == 1, (
        f"Expected exactly 1 LogRingHandler after two configure_logging() calls, "
        f"got {len(ring_handlers)}.  Duplicate handlers cause each record to be "
        f"written to the ring buffer multiple times (WR-02)."
    )

    # Emit one record and verify ring2 receives it exactly once.
    ring2.clear()
    logging.getLogger("gruvax.test.dedup").info("dedup-marker")
    dedup_entries = [e for e in ring2 if "dedup-marker" in e.get("msg", "")]
    assert len(dedup_entries) == 1, (
        f"Expected exactly 1 ring entry for 'dedup-marker', got {len(dedup_entries)}.  "
        f"Duplicate LogRingHandler entries indicate WR-02 regression."
    )

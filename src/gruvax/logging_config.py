"""Structured-JSON logging for GRUVAX (OBS-02, D-12).

Provides:
  - ``configure_logging(log_level, ring)`` — one-call setup that wires structlog's
    processor chain for stdout JSON emission and attaches a ``LogRingHandler`` to the
    ``gruvax`` logger only.  Call once at lifespan startup, before any log calls.
  - ``LogRingHandler`` — a ``logging.Handler`` that appends one dict per emitted record
    to a caller-supplied ``deque``.  Understands both structlog-native records (where
    ``record.msg`` is the event dict) and stdlib foreign records (where ``record.msg``
    is a plain string), producing the same ``{ts, level, logger, msg}`` shape in both
    cases.

Stdout format (per record)::

    {"event": "search took 42ms", "level": "info", "logger": "gruvax.api.search",
     "timestamp": "2026-05-25T02:00:00.000000Z"}

Ring buffer shape (consumed by ``GET /api/admin/diagnostics``)::

    {"ts": 1716602400.0, "level": "INFO", "logger": "gruvax.api.search",
     "msg": "search took 42ms"}

Security note: ``LogRingHandler`` is attached **only** to ``logging.getLogger("gruvax")``,
never to the root logger.  This prevents third-party log records — which may stringify
secrets such as a DSN in a psycopg connection-failure message — from reaching the admin UI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import orjson
import structlog


if TYPE_CHECKING:
    from collections import deque


def _orjson_serializer(obj: Any, **_kw: Any) -> str:
    """orjson-backed JSON serializer for structlog's JSONRenderer.

    Returns a UTF-8 decoded string so structlog can write it to the stream handler.
    orjson is 3-5x faster than stdlib json and handles datetime/UUID/numpy out of the box.
    """
    return orjson.dumps(obj).decode()


class LogRingHandler(logging.Handler):
    """Append ``{ts, level, logger, msg}`` dicts to an in-memory ring buffer (D-12).

    The ring is stored on ``app.state.log_ring_buffer`` so the admin diagnostics
    endpoint can tail it without coupling to journald or the container runtime.

    Structlog-native vs. stdlib foreign records
    -------------------------------------------
    When structlog processes a log call, it wraps the event dict into a stdlib
    ``logging.LogRecord`` with ``record.msg`` set to the event dict (a Python ``dict``).
    ``ProcessorFormatter.format()`` later renders that dict to a JSON string for the
    stdout handler, but ``LogRingHandler.emit()`` fires on the original, unmodified
    record.  By checking ``isinstance(record.msg, dict)`` we extract the human-readable
    ``event`` key directly — avoiding a double-serialised JSON blob in the ``msg`` field.

    For stdlib foreign records (psycopg, uvicorn, etc.) ``record.msg`` is the format
    string and ``record.getMessage()`` returns the fully interpolated text, same as before.

    NEVER modify the record in this handler — ProcessorFormatter needs it intact for
    its own stdout rendering pass (anti-pattern documented in RESEARCH.md Pitfall 1).

    ``ts`` is stored as a float (``record.created``, seconds since epoch) so the
    diagnostics layer can sort or filter without parsing ISO strings.

    Thread-safety: ``logging.Handler.emit()`` acquires ``self.acquire()`` /
    ``self.release()`` around the call, so concurrent appends are serialised at the
    handler level.
    """

    def __init__(self, ring: deque[dict[str, Any]], level: int = logging.INFO) -> None:
        super().__init__(level)
        self._ring = ring

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # structlog-native path: record.msg is the event dict before rendering.
            # Extract the 'event' key to get the human-readable message string.
            # stdlib foreign path: record.msg is a format string; getMessage() interpolates.
            if isinstance(record.msg, dict):
                msg: str = record.msg.get("event", "")
            else:
                msg = record.getMessage()
            self._ring.append(
                {
                    "ts": record.created,  # float — unchanged from pre-migration shape
                    "level": record.levelname,  # str — unchanged
                    "logger": record.name,  # str — unchanged
                    "msg": msg,  # str — unchanged
                }
            )
        except Exception:
            self.handleError(record)


def configure_logging(log_level: str, ring: deque[dict[str, Any]]) -> None:
    """Configure structlog + stdlib logging for GRUVAX.

    Sets up the shared processor chain for both structlog-native and stdlib foreign
    records, wires the stdout JSON handler via ``ProcessorFormatter``, and attaches the
    in-memory ring handler to the ``gruvax`` logger only (security constraint: no root
    attachment, per RESEARCH.md Pitfall 2).

    Call once at lifespan startup::

        from collections import deque
        from gruvax.logging_config import configure_logging

        ring: deque[dict] = deque(maxlen=200)
        configure_logging(settings.LOG_LEVEL, ring)
        app.state.log_ring_buffer = ring

    Args:
        log_level: Log level name (e.g. ``"INFO"``, ``"DEBUG"``).  Case-insensitive.
                   Falls back to ``INFO`` for unrecognised values.
        ring:      Pre-created ``deque`` to which the handler appends ring entries.
                   Typically ``deque(maxlen=200)`` as per the diagnostics contract.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)

    # Processors applied to BOTH structlog-native and stdlib foreign records.
    # Order matches discogsography's common/config.py right-sized for GRUVAX
    # (no multi-service context binding or Neo4j/pika suppression needed here).
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(serializer=_orjson_serializer),
            ],
        )
    )

    # Replace any default handlers; force=True handles re-configuration in tests.
    logging.basicConfig(level=level, handlers=[console_handler], force=True)

    # Ring buffer: scoped to the gruvax logger ONLY — NEVER the root logger.
    # Third-party loggers (psycopg, uvicorn, etc.) may stringify a DSN or secret
    # in an error message; attaching to root would leak those records to the admin UI
    # via /api/admin/diagnostics.  This preserves the pre-Phase-9 security control.
    #
    # Remove any existing LogRingHandlers before adding the new one, so that
    # configure_logging() is idempotent and safe to call multiple times (tests,
    # --reload).  Without this guard, each call appends a new handler and every
    # log record is written to the ring buffer N times.
    gruvax_logger = logging.getLogger("gruvax")
    for h in list(gruvax_logger.handlers):
        if isinstance(h, LogRingHandler):
            gruvax_logger.removeHandler(h)
    gruvax_logger.addHandler(LogRingHandler(ring, level=logging.INFO))

    # Suppress noisy access-log chatter (same suppression as the pre-migration setup).
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

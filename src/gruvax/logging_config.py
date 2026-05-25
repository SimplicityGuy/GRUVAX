"""Structured-JSON logging for GRUVAX (OBS-02, D-12).

Provides:
  - ``JsonFormatter`` — emits each log record as a single-line JSON object
    with keys ``ts`` (ISO-8601 UTC string), ``level``, ``logger``, ``msg``,
    and ``exc`` (only when ``exc_info`` is present on the record).
  - ``LogRingHandler`` — a ``logging.Handler`` that appends one dict per
    emitted record to a caller-supplied ``deque``.  The dict stores ``ts``
    as a float (``record.created``, seconds since epoch) so the diagnostics
    endpoint can sort or filter by timestamp without parsing strings.

Usage in ``app.py`` lifespan::

    from collections import deque
    from gruvax.logging_config import JsonFormatter, LogRingHandler

    ring: deque[dict] = deque(maxlen=200)
    root = logging.getLogger()
    root.handlers = [logging.StreamHandler()]
    root.handlers[0].setFormatter(JsonFormatter())
    # Ring buffer is scoped to the `gruvax` logger (not root) so third-party log
    # records — which may stringify secrets like a DSN — never reach the admin UI.
    logging.getLogger("gruvax").addHandler(LogRingHandler(ring))
    app.state.log_ring_buffer = ring
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from typing import Any


class JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object.

    Output format::

        {"ts": "2026-05-25T02:00:00Z", "level": "INFO", "logger": "gruvax.api.search", "msg": "..."}

    When ``record.exc_info`` is set, an additional ``exc`` key contains the
    formatted traceback string (from ``self.formatException``).
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


class LogRingHandler(logging.Handler):
    """Append formatted records to an in-memory deque (D-12).

    The deque is stored on ``app.state.log_ring_buffer`` so the admin
    diagnostics endpoint can tail it without coupling to journald or the
    container runtime.

    ``ts`` is stored as a float (``record.created``) — the same value
    used by Python's logging system — so the diagnostics layer can sort or
    filter without parsing ISO strings.

    Thread-safety: ``logging.Handler.emit()`` holds ``self.acquire()`` /
    ``self.release()`` around the call, so concurrent appends to the deque
    are serialised at the handler level.
    """

    def __init__(self, ring: deque[dict[str, Any]], level: int = logging.INFO) -> None:
        super().__init__(level)
        self._ring = ring

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ring.append(
                {
                    "ts": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
            )
        except Exception:
            self.handleError(record)

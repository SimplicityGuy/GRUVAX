"""Shared log processor masking PATs and opaque collection snapshot tokens.

The regex deliberately covers both ``Bearer dscg_<base64url>`` AND bare
``dscg_<base64url>`` substrings (no Bearer prefix). This broader form catches
PATs that leak into exception strings — e.g. when ``httpx.HTTPStatusError`` or
a downstream library stringifies the request including the Authorization
header. Per Plan 02 Task 1's Open Q4 RESOLVED in RESEARCH.md.

The processor is inserted into ``configure_logging``'s ``shared_processors``
list AFTER ``structlog.processors.format_exc_info``. ``format_exc_info`` is
what turns the ``exc_info`` bool/tuple into the rendered ``exception`` string
in the first place — running the redactor any earlier means ``exc_info`` is
still a bool or a ``(type, value, traceback)`` tuple (neither a ``str`` nor a
``dict``), so the walk below would skip it entirely and any secret embedded
in the traceback text would flow to stdout unmasked.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote


# Compiled once at module-import time — avoids per-call regex compilation.
# Alphabet covers base64url (a-z, A-Z, 0-9, _, -) so embedded tokens inside
# HTTP exception strings are captured even when surrounded by other text.
# Snapshot query keys are percent-decoded independently, including duplicates.
_DSCG_PATTERN = re.compile(r"(?:Bearer\s+)?dscg_[A-Za-z0-9_-]+")

_REDACTED = "[REDACTED]"
_QUERY_PARAMETER = re.compile(r"([?&])([^&#\s=]+)=([^&#\s\"'<>]*)")


def _redact_query_parameter(match: re.Match[str]) -> str:
    key = match[2]
    try:
        malformed = re.search(r"%(?![0-9a-fA-F]{2})", key) is not None
        sensitive = unquote(key, errors="strict") == "snapshot"
    except UnicodeError:
        malformed, sensitive = True, False
    value = _REDACTED if sensitive or malformed else match[3]
    return f"{match[1]}{key}={value}"


def _redact_value(val: Any) -> Any:
    """Recursively mask PATs, snapshot fields and decoded URL query values.

    Handles the shapes that can appear in a structlog event_dict: plain
    strings, nested dicts (e.g. a ``request``/``response`` blob), and nested
    lists/tuples (e.g. ``structlog.processors.dict_tracebacks`` frame lists,
    or a list of header strings). Any other type is returned unchanged.
    """
    if isinstance(val, str):
        return _QUERY_PARAMETER.sub(_redact_query_parameter, _DSCG_PATTERN.sub(_REDACTED, val))
    if isinstance(val, dict):
        return {
            k: _REDACTED
            if isinstance(k, str) and unquote(k) in {"snapshot", "snapshot_token"}
            else _redact_value(v)
            for k, v in val.items()
        }
    if isinstance(val, list):
        return [_redact_value(v) for v in val]
    if isinstance(val, tuple):
        return tuple(_redact_value(v) for v in val)
    return val


def redact_dscg_tokens(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Mask PAT substrings and snapshot tokens without discarding other context.

    Three-arg structlog processor signature. Walks ``event_dict`` values
    recursively into nested dicts, lists, and tuples — including the
    rendered ``exception`` field that ``format_exc_info`` produces, and the
    frame-list shape ``dict_tracebacks`` would produce if it were ever
    activated — so secrets buried anywhere in the payload are scrubbed.

    Args:
        _logger:      structlog logger (unused — processor signature requirement).
        _method_name: log method name (unused — processor signature requirement).
        event_dict:   the event payload structlog will render.

    Returns:
        ``event_dict`` with PATs and opaque snapshot values replaced by ``[REDACTED]``.
    """
    for key, val in list(event_dict.items()):
        event_dict[key] = (
            _REDACTED if unquote(key) in {"snapshot", "snapshot_token"} else _redact_value(val)
        )
    return event_dict

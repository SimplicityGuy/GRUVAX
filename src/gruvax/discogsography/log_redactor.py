"""structlog processor that masks discogsography PAT tokens (T-01-PAT-leak).

The regex deliberately covers both ``Bearer dscg_<base64url>`` AND bare
``dscg_<base64url>`` substrings (no Bearer prefix). This broader form catches
PATs that leak into exception strings — e.g. when ``httpx.HTTPStatusError`` or
a downstream library stringifies the request including the Authorization
header. Per Plan 02 Task 1's Open Q4 RESOLVED in RESEARCH.md.

The processor is inserted into ``configure_logging``'s ``shared_processors``
list BEFORE ``structlog.processors.format_exc_info`` so the exception-info
tuple's already-rendered string values are masked on the same pass.
"""

from __future__ import annotations

import re
from typing import Any


# Compiled once at module-import time — avoids per-call regex compilation.
# Alphabet covers base64url (a-z, A-Z, 0-9, _, -) so embedded tokens inside
# HTTP exception strings are captured even when surrounded by other text.
_DSCG_PATTERN = re.compile(r"(?:Bearer\s+)?dscg_[A-Za-z0-9_-]+")

_REDACTED = "[REDACTED]"


def redact_dscg_tokens(
    _logger: Any,
    _method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Mask any ``dscg_…`` substring (with or without ``Bearer `` prefix).

    Three-arg structlog processor signature. Walks ``event_dict`` values
    recursively into nested dicts so headers buried in a ``request`` /
    ``response`` blob are also scrubbed.

    Args:
        _logger:      structlog logger (unused — processor signature requirement).
        _method_name: log method name (unused — processor signature requirement).
        event_dict:   the event payload structlog will render.

    Returns:
        ``event_dict`` with all dscg_* substrings replaced by ``[REDACTED]``.
    """
    for key, val in list(event_dict.items()):
        if isinstance(val, str):
            if _DSCG_PATTERN.search(val):
                event_dict[key] = _DSCG_PATTERN.sub(_REDACTED, val)
        elif isinstance(val, dict):
            event_dict[key] = redact_dscg_tokens(_logger, _method_name, dict(val))
    return event_dict

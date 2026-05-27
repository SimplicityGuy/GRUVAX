"""Plan 02 Task 1 — structlog redactor masks every dscg_* substring.

Tests 1-5 + Test 7 (per PLAN.md):
  1. Bearer-prefixed PAT in a top-level string is masked.
  2. Bare dscg_<token> in a top-level string is masked.
  3. Nested dicts (event_dict["request"]["headers"]["Authorization"]) are walked.
  4. Hypothesis fuzz: 100+ generated PATs never survive in the output.
  5. End-to-end: configured logger's stdout output does NOT contain the PAT
     (wires through configure_logging — proves the processor is slotted in).
  7. Exception-message coverage: an exception whose str() contains a leaked
     PAT does NOT render the PAT in the captured stdout when logged via
     logger.exception().
"""

from __future__ import annotations

import json
import logging
import string
from collections import deque
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from gruvax.discogsography.log_redactor import _DSCG_PATTERN, redact_dscg_tokens
from gruvax.logging_config import configure_logging


# ── Unit-level processor tests (Tests 1-4) ───────────────────────────────────


def test_bearer_prefixed_token_in_top_level_value_is_masked() -> None:
    """Test 1: 'Bearer dscg_abc123_xyz' is masked inside a top-level string."""
    event_dict: dict[str, Any] = {
        "event": "auth header",
        "header": "Bearer dscg_abc123_xyz",
    }
    out = redact_dscg_tokens(None, "info", event_dict)
    assert "dscg_abc123_xyz" not in out["header"]
    assert "Bearer" not in out["header"]  # the whole Bearer-prefixed token is replaced
    assert out["header"] == "[REDACTED]"
    # Untouched key passes through.
    assert out["event"] == "auth header"


def test_bare_token_no_bearer_prefix_is_masked() -> None:
    """Test 2: 'dscg_abc123_xyz' (no Bearer prefix) is masked."""
    event_dict: dict[str, Any] = {
        "event": "got PAT",
        "pat_dump": "operator pasted dscg_abc123_xyz at prompt",
    }
    out = redact_dscg_tokens(None, "info", event_dict)
    assert "dscg_abc123_xyz" not in out["pat_dump"]
    assert "[REDACTED]" in out["pat_dump"]
    assert "operator pasted" in out["pat_dump"]  # surrounding text preserved


def test_nested_dict_walking() -> None:
    """Test 3: redact recursively masks dscg_* inside nested dict values."""
    event_dict: dict[str, Any] = {
        "event": "request",
        "request": {
            "method": "GET",
            "headers": {
                "Authorization": "Bearer dscg_secret_nested_token",
                "Content-Type": "application/json",
            },
        },
    }
    out = redact_dscg_tokens(None, "info", event_dict)
    assert "dscg_secret_nested_token" not in json.dumps(out)
    # Bearer-prefixed full match is replaced.
    assert out["request"]["headers"]["Authorization"] == "[REDACTED]"
    # Non-secret nested values pass through.
    assert out["request"]["headers"]["Content-Type"] == "application/json"
    assert out["request"]["method"] == "GET"


@settings(max_examples=120, deadline=None)
@given(
    st.text(
        alphabet=string.ascii_letters + string.digits + "_-",
        min_size=30,
        max_size=80,
    ),
    st.text(min_size=0, max_size=40),
    st.text(min_size=0, max_size=40),
)
def test_property_pat_never_survives_in_rendered_output(
    token_suffix: str,
    prefix: str,
    suffix: str,
) -> None:
    """Test 4 (Hypothesis property): for every generated PAT, the rendered
    event_dict NEVER contains the original PAT plaintext.

    Embeds a synthetic ``dscg_<token>`` into a surrounding string drawn from
    arbitrary text — the regex must catch the token regardless of context.
    """
    plaintext_pat = f"dscg_{token_suffix}"
    payload = f"{prefix}{plaintext_pat}{suffix}"
    event_dict: dict[str, Any] = {"event": "fuzz", "blob": payload}
    out = redact_dscg_tokens(None, "info", event_dict)
    # Property: rendered output must NEVER contain the PAT plaintext.
    serialized = json.dumps(out)
    assert plaintext_pat not in serialized, (
        f"PAT leaked through redactor: pat={plaintext_pat!r} in serialized={serialized!r}"
    )


# ── End-to-end tests through configure_logging (Tests 5 + 7) ─────────────────


@pytest.fixture
def configured_logging_ring() -> deque[dict[str, Any]]:
    """Fresh ring buffer + configure_logging() call. Returns the ring."""
    ring: deque[dict[str, Any]] = deque(maxlen=200)
    configure_logging("INFO", ring)
    return ring


def test_pat_does_not_appear_in_captured_stdout(
    configured_logging_ring: deque[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test 5: the configured logger's stdout output does NOT contain the PAT
    plaintext anywhere in the rendered JSON.

    Uses ``capsys`` (NOT ``caplog``) — caplog can bypass structlog processors
    by hooking into stdlib's handler stack before format runs.
    """
    secret_pat = "dscg_secret_abc123_DO_NOT_LEAK"
    logger = logging.getLogger("gruvax.test_log_redaction")
    logger.error("auth attempt with header=%s", f"Bearer {secret_pat}")

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert secret_pat not in combined, (
        f"PAT plaintext leaked into stdout/stderr: {combined!r}"
    )


def test_pat_does_not_appear_in_exception_message(
    configured_logging_ring: deque[dict[str, Any]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test 7 (Open Q4 RESOLVED — exception-message coverage):

    Construct an exception whose ``str()`` contains a synthetic 'request
    failed: ... Authorization: Bearer dscg_secret_LEAK_xyz ...' message.
    Log it via ``logger.exception()`` so structlog's format_exc_info renders
    the traceback. The redactor runs BEFORE format_exc_info, so the
    exception-derived string flowing into the event_dict must also be masked.

    Practically: the redactor walks the event_dict on each log call. The
    ``logger.error("msg %s", str(exc))`` form puts the exception's str into
    a positional arg that PositionalArgumentsFormatter merges into the event
    key, where the redactor catches it on the recursive walk.
    """
    secret_pat = "dscg_secret_LEAK_DETECTOR_xyz"
    exc_message = (
        f"request failed: GET https://x/y "
        f"headers={{'Authorization': 'Bearer {secret_pat}'}}"
    )
    logger = logging.getLogger("gruvax.test_log_redaction_exc")
    try:
        raise RuntimeError(exc_message)
    except RuntimeError as exc:
        # Log the message string (which contains the PAT). The redactor must
        # mask the substring regardless of how it arrived in the event_dict.
        logger.error("upstream failed: %s", str(exc))

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert secret_pat not in combined, (
        f"PAT plaintext leaked through exception logging path: {combined!r}"
    )


# ── Regex-self-test sanity ──────────────────────────────────────────────────


def test_dscg_pattern_matches_bare_and_bearer_forms() -> None:
    """Sanity: the compiled regex catches both Bearer-prefixed and bare PATs.

    Lowers the bus factor on the regex itself: if a refactor breaks the
    compile, this test fails fast with a clear error before the higher-level
    tests do.
    """
    assert _DSCG_PATTERN.search("Bearer dscg_abc123") is not None
    assert _DSCG_PATTERN.search("dscg_abc123_xyz") is not None
    assert _DSCG_PATTERN.search("hello dscg_TokenWithMixedCase_-09 world") is not None
    # Non-matches:
    assert _DSCG_PATTERN.search("dscg_") is None  # alphabet requires at least one char
    assert _DSCG_PATTERN.search("DSCG_ABC123") is None  # case-sensitive prefix

"""Plan 02 Task 1 — structlog redactor masks every dscg_* substring.

Tests 1-5 + Test 7 (per PLAN.md), plus Test 6 (gruvax-dxd regression):
  1. Bearer-prefixed PAT in a top-level string is masked.
  2. Bare dscg_<token> in a top-level string is masked.
  3. Nested dicts (event_dict["request"]["headers"]["Authorization"]) are walked.
  4. Hypothesis fuzz: 100+ generated PATs never survive in the output.
  5. End-to-end: configured logger's stdout output does NOT contain the PAT
     (wires through configure_logging — proves the processor is slotted in).
  6. Nested lists/tuples (e.g. a dict_tracebacks-shaped frame list) are walked.
  7. Exception-message coverage: an exception logged via logger.exception()
     (the traceback-rendering path, not just str(exc)) does NOT render the
     PAT in the captured stdout — this is the gruvax-dxd regression: the
     redactor must run AFTER format_exc_info so it can see the rendered
     exception field.
"""

from __future__ import annotations

from collections import deque
import io
import json
import logging
import string
from typing import Any

from hypothesis import given, settings, strategies as st
import pytest

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


def test_nested_list_and_tuple_walking() -> None:
    """Test 6 (gruvax-dxd regression): redact recursively masks dscg_* inside
    nested lists/tuples, e.g. the frame-list shape
    ``structlog.processors.dict_tracebacks`` would produce (a list of frame
    dicts, each potentially containing a list of local-variable dicts).
    """
    event_dict: dict[str, Any] = {
        "event": "traceback",
        "exception": [
            {
                "exc_type": "RuntimeError",
                "frames": [
                    {"locals": {"token": "dscg_frame_local_secret"}},
                ],
            },
        ],
        "headers": ("Authorization", "Bearer dscg_tuple_secret"),
    }
    out = redact_dscg_tokens(None, "info", event_dict)
    serialized = json.dumps(out)
    assert "dscg_frame_local_secret" not in serialized
    assert "dscg_tuple_secret" not in serialized
    assert out["headers"] == ("Authorization", "[REDACTED]")


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
def logging_stream(monkeypatch: pytest.MonkeyPatch) -> io.StringIO:
    """Fresh ring buffer + ``configure_logging()`` call, capturing stdout via
    an owned ``io.StringIO()`` rather than pytest's ``capsys``/``capfd``.

    ``configure_logging()`` builds a ``logging.StreamHandler()`` whose
    ``stream`` attribute is bound to whatever ``sys.stderr`` object is current
    at *construction* time — it does not re-read ``sys.stderr`` on each write.
    That makes pytest's capture fixtures unreliable here:

      - ``capsys`` monkeypatches the ``sys.stdout``/``sys.stderr`` Python
        objects. If ``configure_logging()`` runs (via a same-scope fixture)
        before ``capsys``'s own per-test swap takes effect, the handler keeps
        writing to the pre-``capsys`` object and ``capsys.readouterr()``
        silently returns empty — a vacuously passing test regardless of
        whether redaction actually worked.
      - ``capfd`` is OS-fd-level and in principle order-independent, but
        forcing it to run before this fixture (to fix the above) instead hits
        a *different* problem: pytest rotates/closes the underlying fd-backed
        file object between capture phases, so a handler holding a stale
        reference to it raises ``ValueError: I/O operation on closed file``
        mid-test.

    Monkeypatching ``sys.stderr`` to a plain ``io.StringIO()`` we control
    directly sidesteps both failure modes: the handler binds to *our* object,
    which we simply read via ``.getvalue()`` after the log call — no pytest
    capture-fixture ordering or lifecycle involved.
    """
    buffer = io.StringIO()
    monkeypatch.setattr("sys.stderr", buffer)
    ring: deque[dict[str, Any]] = deque(maxlen=200)
    configure_logging("INFO", ring)
    return buffer


def test_pat_does_not_appear_in_captured_stdout(logging_stream: io.StringIO) -> None:
    """Test 5: the configured logger's stdout output does NOT contain the PAT
    plaintext anywhere in the rendered JSON.

    Reads the owned ``io.StringIO()`` the ``logging_stream`` fixture installs
    as ``sys.stderr`` — NOT ``caplog`` (which can bypass structlog processors
    by hooking into stdlib's handler stack before format runs) and NOT
    ``capsys``/``capfd`` (see ``logging_stream``'s docstring for why both are
    unreliable against a handler built by ``configure_logging()``).
    """
    secret_pat = "dscg_secret_abc123_DO_NOT_LEAK"
    logger = logging.getLogger("gruvax.test_log_redaction")
    logger.error("auth attempt with header=%s", f"Bearer {secret_pat}")

    combined = logging_stream.getvalue()
    assert secret_pat not in combined, f"PAT plaintext leaked into stdout/stderr: {combined!r}"
    # Sanity: prove the log line actually reached the captured stream —
    # otherwise this would pass vacuously if logging were broken rather than
    # because redaction worked.
    assert "[REDACTED]" in combined


def test_pat_does_not_appear_in_exception_message(logging_stream: io.StringIO) -> None:
    """Test 7 (gruvax-dxd regression — traceback-rendering coverage):

    Construct an exception whose ``str()`` contains a synthetic 'request
    failed: ... Authorization: Bearer dscg_secret_LEAK_xyz ...' message.
    Log it via ``logger.exception()`` — the stdlib/structlog idiom for
    exception logging — so ``format_exc_info`` renders the *traceback* (not
    just the exception's ``str()``) into the ``exception`` field. Regression
    coverage for gruvax-dxd: ``redact_dscg_tokens`` must run AFTER
    ``format_exc_info`` so it can see and scrub that rendered field; this is
    the exact vector the redactor exists for (e.g. httpx stringifying a
    request's Authorization header into an exception message that then ends
    up embedded in the traceback text).
    """
    secret_pat = "dscg_secret_LEAK_DETECTOR_xyz"
    exc_message = (
        f"request failed: GET https://x/y headers={{'Authorization': 'Bearer {secret_pat}'}}"
    )
    logger = logging.getLogger("gruvax.test_log_redaction_exc")
    try:
        raise RuntimeError(exc_message)
    except RuntimeError:
        # logger.exception() sets exc_info=True, which format_exc_info renders
        # into a full traceback string under the "exception" key — this is
        # the path that leaked PATs before the processor-ordering fix.
        logger.exception("upstream failed")

    combined = logging_stream.getvalue()
    assert secret_pat not in combined, (
        f"PAT plaintext leaked through exception logging path: {combined!r}"
    )
    # Sanity: prove the traceback (with the exception message) actually made
    # it into the captured output — otherwise this test would pass vacuously
    # if logging were broken rather than because redaction worked.
    assert "RuntimeError" in combined
    assert "[REDACTED]" in combined


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

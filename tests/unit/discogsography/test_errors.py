"""Plan 02 Task 1 — typed exception classes for DiscogsographyClient.

Test 6 (per PLAN.md):
  - errors.py exports the six exception classes.
  - PATRejected inherits from DiscogsographyError.
  - PATRejected.__str__ does NOT echo any PAT plaintext (defensive — the
    constructor must only accept operator-safe messages).
"""

from __future__ import annotations

import pytest

from gruvax.discogsography.errors import (
    DiscogsographyError,
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
    SyncInProgress,
)


def test_six_exception_classes_exported() -> None:
    """All six typed exceptions are importable from the errors module."""
    for cls in (
        DiscogsographyError,
        PATRejected,
        RateLimitExhausted,
        ServerError,
        NetworkError,
        SyncInProgress,
    ):
        assert issubclass(cls, Exception), f"{cls.__name__} must subclass Exception"


def test_specialised_errors_subclass_base() -> None:
    """Every specialised error inherits from DiscogsographyError so callers
    can ``except DiscogsographyError`` and catch all of them.
    """
    for cls in (PATRejected, RateLimitExhausted, ServerError, NetworkError, SyncInProgress):
        assert issubclass(cls, DiscogsographyError), (
            f"{cls.__name__} must subclass DiscogsographyError"
        )


def test_pat_rejected_is_raisable_and_catchable() -> None:
    """Smoke test: PATRejected behaves like a normal exception."""
    with pytest.raises(PATRejected):
        raise PATRejected("PAT rejected by discogsography (401/403)")

    with pytest.raises(DiscogsographyError):
        raise PATRejected("PAT rejected by discogsography (401/403)")


def test_pat_rejected_str_does_not_echo_plaintext() -> None:
    """Constructor only accepts operator-safe messages; if a caller passes the
    plaintext PAT (defensive check), the message string must not be the PAT.

    The class itself cannot enforce "never contains dscg_*" — the constructor
    accepts whatever string the caller hands it. The invariant is that the
    *production code path* in client.py NEVER passes the PAT. This test
    asserts the standard operator-safe message has no PAT substring.
    """
    err = PATRejected("PAT rejected by discogsography (401/403)")
    assert "dscg_" not in str(err)
    # Sanity: __str__ should match what the caller passed.
    assert "PAT rejected by discogsography" in str(err)

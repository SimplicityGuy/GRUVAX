"""Unit tests for admin session expiry logic (ADMN-02).

These tests target pure expiry-logic helpers in ``gruvax.auth.sessions``
(implemented in Plan 02). They go RED in Wave-0 (module doesn't exist yet)
and GREEN when Plan 02 ships the session module.

Analog: tests/unit/test_algorithm.py (pure-function tests without DB).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta


def _now() -> datetime:
    return datetime.now(UTC)


def test_hard_cap_expired() -> None:
    """A session whose hard_expires_at is in the past is considered expired.

    The hard cap is independent of sliding idle TTL (D-03d, Pitfall 23):
    even if last_seen_at is recent, a session beyond hard_expires_at must
    be treated as expired.
    """
    from gruvax.auth.sessions import is_session_valid

    now = _now()
    # Session created 2 hours ago; hard cap is 30 minutes → expired
    hard_expires_at = now - timedelta(hours=1)
    expires_at = now + timedelta(minutes=5)  # sliding TTL would still be valid
    assert not is_session_valid(
        expires_at=expires_at,
        hard_expires_at=hard_expires_at,
        revoked_at=None,
    ), "Session beyond hard_expires_at must be expired even if idle TTL is valid"


def test_idle_expired() -> None:
    """A session whose expires_at (idle TTL) is in the past is considered expired.

    Sliding window: if no requests arrive within SESSION_TTL_SECONDS, the session
    expires (D-04).
    """
    from gruvax.auth.sessions import is_session_valid

    now = _now()
    # Idle TTL expired 5 minutes ago
    expires_at = now - timedelta(minutes=5)
    hard_expires_at = now + timedelta(hours=1)  # hard cap would still be valid
    assert not is_session_valid(
        expires_at=expires_at,
        hard_expires_at=hard_expires_at,
        revoked_at=None,
    ), "Session beyond idle expires_at must be expired"


def test_active_session_valid() -> None:
    """A session with future expires_at and future hard_expires_at is valid."""
    from gruvax.auth.sessions import is_session_valid

    now = _now()
    expires_at = now + timedelta(minutes=5)
    hard_expires_at = now + timedelta(hours=1)
    assert is_session_valid(
        expires_at=expires_at,
        hard_expires_at=hard_expires_at,
        revoked_at=None,
    ), "A session with future expiry times must be valid"


def test_revoked_session_invalid() -> None:
    """A session with revoked_at set is invalid regardless of expiry times (D-03b)."""
    from gruvax.auth.sessions import is_session_valid

    now = _now()
    expires_at = now + timedelta(minutes=5)
    hard_expires_at = now + timedelta(hours=1)
    revoked_at = now - timedelta(seconds=10)  # revoked 10 seconds ago
    assert not is_session_valid(
        expires_at=expires_at,
        hard_expires_at=hard_expires_at,
        revoked_at=revoked_at,
    ), "A revoked session must be invalid"

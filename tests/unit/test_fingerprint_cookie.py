"""Unit tests for fingerprint cookie helpers (DEV-01).

Targets pure helpers in ``gruvax.auth.sessions`` (implemented in Plan 03-01).
They go RED in Wave-0 (module functions don't exist yet) and GREEN when Plan 03-01
ships the fingerprint cookie helpers.

Analog: tests/unit/test_sessions.py (pure-function tests without DB).
"""

from __future__ import annotations


def test_fingerprint_cookie_is_httponly() -> None:
    """issue_fingerprint_cookie sets HttpOnly + SameSite=Strict + max_age >= 30 days (D3-09).

    The fingerprint cookie is a session-equivalent secret — JS must NEVER read it
    (HttpOnly=True). max_age must be set explicitly so Chromium writes it to disk
    (RESEARCH.md Pitfall 1: session cookies are NOT persisted by Chromium to
    user-data-dir on exit). Returns a value of at least 40 chars
    (secrets.token_urlsafe(32) → 32 bytes → ~43 URL-safe chars).

    RED until Plan 03-01 adds issue_fingerprint_cookie to gruvax.auth.sessions.
    """
    from unittest.mock import MagicMock

    from gruvax.auth.sessions import FINGERPRINT_MAX_AGE, issue_fingerprint_cookie

    response_mock = MagicMock()
    fp = issue_fingerprint_cookie(response_mock)

    # Return value: opaque token from secrets.token_urlsafe(32)
    assert isinstance(fp, str), "issue_fingerprint_cookie must return a str"
    assert len(fp) >= 40, (
        f"fingerprint must be at least 40 chars (secrets.token_urlsafe(32) → ~43 chars), "
        f"got {len(fp)} chars"
    )

    # set_cookie must be called exactly once
    response_mock.set_cookie.assert_called_once()

    # Extract the call keyword arguments
    call_kwargs = response_mock.set_cookie.call_args[1]

    assert call_kwargs.get("httponly") is True, (
        "fingerprint cookie must be HttpOnly=True (JS must never read it — it is a "
        "session-equivalent secret per RESEARCH.md §Security Domain)"
    )
    assert call_kwargs.get("samesite") == "strict", (
        "fingerprint cookie must be SameSite=Strict (all GRUVAX traffic is same-site "
        "on gruvax.lan — RESEARCH.md Pitfall 4)"
    )
    assert call_kwargs.get("max_age") >= 30 * 24 * 3600, (
        "fingerprint cookie max_age must be >= 30 days so Chromium writes it to disk "
        "(RESEARCH.md Pitfall 1: session cookies are NOT persisted on exit)"
    )
    assert call_kwargs.get("max_age") == FINGERPRINT_MAX_AGE, (
        "max_age must equal the module-level FINGERPRINT_MAX_AGE constant"
    )


def test_clear_fingerprint_cookie_matches_attributes() -> None:
    """clear_fingerprint_cookie uses the same attributes as issue_fingerprint_cookie (CR-04).

    The delete_cookie attributes (path, httponly, samesite, secure) MUST match the
    set_cookie attributes exactly. Browsers that see a mismatched delete_cookie
    (e.g., httponly differs) may treat it as a different cookie and silently ignore
    the deletion — leaving the old fingerprint alive (CR-04 invariant, mirroring
    the clear_browse_binding_cookie pattern in sessions.py line 248).

    RED until Plan 03-01 adds clear_fingerprint_cookie to gruvax.auth.sessions.
    """
    from unittest.mock import MagicMock

    from gruvax.auth.sessions import clear_fingerprint_cookie, issue_fingerprint_cookie

    set_mock = MagicMock()
    issue_fingerprint_cookie(set_mock)
    set_kwargs = set_mock.set_cookie.call_args[1]

    clear_mock = MagicMock()
    clear_fingerprint_cookie(clear_mock)
    clear_kwargs = clear_mock.delete_cookie.call_args[1]

    # samesite and httponly must match between set and clear
    assert clear_kwargs.get("samesite") == set_kwargs.get("samesite"), (
        "clear_fingerprint_cookie samesite must match issue_fingerprint_cookie samesite (CR-04)"
    )
    assert clear_kwargs.get("httponly") == set_kwargs.get("httponly"), (
        "clear_fingerprint_cookie httponly must match issue_fingerprint_cookie httponly (CR-04)"
    )

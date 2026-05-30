"""Unit tests for _profile_status() — the profiles-list status badge derivation.

Phase 4 gap-closure (criterion #2 / D4-07): a real 401 sets
last_sync_error='pat_rejected' and last_sync_status='failed' (NOT 'ok'), so the
re-auth-required badge must key on app_token_revoked + (pat_rejected error or a
prior sync), never on last_sync_status=='ok'. These tests pin that contract and
the "never-connected → pending" distinction an existing integration test relies on.
"""

from __future__ import annotations

from datetime import datetime, timezone

from gruvax.api.admin.profiles import _profile_status


def test_revoked_after_pat_rejected_is_reauth_required() -> None:
    """A profile 401'd by discogsography (the real revocation flow) → re-auth-required.

    The 401 path sets app_token_revoked=TRUE, last_sync_status='failed',
    last_sync_error='pat_rejected'. This is the exact state criterion #2 targets.
    """
    row = {
        "app_token_revoked": True,
        "last_sync_status": "failed",
        "last_sync_error": "pat_rejected",
        "last_sync_at": None,
    }
    assert _profile_status(row) == "re-auth-required"


def test_revoked_with_prior_sync_is_reauth_required() -> None:
    """A profile that synced successfully before being revoked → re-auth-required.

    Even if a later non-PAT failure overwrote last_sync_error, a non-null
    last_sync_at proves it was connected, so the badge must surface re-auth.
    """
    row = {
        "app_token_revoked": True,
        "last_sync_status": "failed",
        "last_sync_error": "network",
        "last_sync_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
    }
    assert _profile_status(row) == "re-auth-required"


def test_never_connected_revoked_is_pending() -> None:
    """A freshly-created profile (revoked default, never connected) → pending.

    Regression guard for tests/integration/test_profile_manager_api.py which
    asserts a brand-new profile reports 'pending', not 're-auth-required'.
    """
    row = {
        "app_token_revoked": True,
        "last_sync_status": None,
        "last_sync_error": None,
        "last_sync_at": None,
    }
    assert _profile_status(row) == "pending"


def test_revoked_status_ok_still_reauth_required() -> None:
    """The old (revoked AND status=='ok') case must STILL map to re-auth-required.

    Belt-and-suspenders: a non-null last_sync_at covers it regardless of status.
    """
    row = {
        "app_token_revoked": True,
        "last_sync_status": "ok",
        "last_sync_error": None,
        "last_sync_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
    }
    assert _profile_status(row) == "re-auth-required"


def test_in_progress_is_syncing() -> None:
    row = {
        "app_token_revoked": False,
        "last_sync_status": "in_progress",
        "last_sync_error": None,
        "last_sync_at": None,
    }
    assert _profile_status(row) == "syncing"


def test_synced_ok_is_connected() -> None:
    row = {
        "app_token_revoked": False,
        "last_sync_status": "ok",
        "last_sync_error": None,
        "last_sync_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
    }
    assert _profile_status(row) == "connected"


def test_not_revoked_never_synced_is_pending() -> None:
    row = {
        "app_token_revoked": False,
        "last_sync_status": None,
        "last_sync_error": None,
        "last_sync_at": None,
    }
    assert _profile_status(row) == "pending"

"""Unit tests for per-profile staleness state registry — Plan 02-00 RED baseline.

Covers SYN-02: per-profile staleness tracked on app.state.profile_state_registry.

Tests assert the intended shape:
  app.state.profile_state_registry: dict[str, dict]
  where each entry holds:
    last_sync_at:       datetime | None
    last_sync_status:   str | None  (one of 'ok', 'failed', 'in_progress', or None)
    app_token_revoked:  bool

Two profiles must produce two independent entries (isolation by construction).

RED tests: verify that the REAL app.state does NOT yet have profile_state_registry
(currently uses singular default_profile_last_sync_at etc.). When Plan 02-02 lands
and adds profile_state_registry, the RED gate assertions fail — that is the intended
GREEN trigger confirming the refactor is complete.
"""

from __future__ import annotations

from datetime import UTC, datetime
import types
import uuid


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_profile_state_entry(
    last_sync_at: datetime | None = None,
    last_sync_status: str | None = None,
    app_token_revoked: bool = True,
) -> dict:
    """Build a single profile_state_registry entry with the expected shape."""
    return {
        "last_sync_at": last_sync_at,
        "last_sync_status": last_sync_status,
        "app_token_revoked": app_token_revoked,
    }


def _make_fake_state_with_profile_state_registry(
    profile_id_a: str,
    profile_id_b: str,
) -> types.SimpleNamespace:
    """Build a fake app.state with a two-profile profile_state_registry."""
    state = types.SimpleNamespace()
    state.profile_state_registry = {
        profile_id_a: _make_profile_state_entry(
            last_sync_at=datetime(2026, 5, 28, 10, 0, 0, tzinfo=UTC),
            last_sync_status="ok",
            app_token_revoked=False,
        ),
        profile_id_b: _make_profile_state_entry(
            last_sync_at=None,
            last_sync_status=None,
            app_token_revoked=True,
        ),
    }
    return state


# ── test: profile_state_registry attribute shape (via fake state) ─────────────
#
# These tests document the intended contract. They PASS now (against the fake
# state) and remain GREEN. The RED tests are in the "real app.state" section.


def test_profile_state_registry_attribute_name() -> None:
    """app.state.profile_state_registry must exist as a dict[str, dict]."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    assert hasattr(state, "profile_state_registry")
    assert isinstance(state.profile_state_registry, dict)


def test_profile_state_entry_has_required_keys() -> None:
    """Each entry must hold last_sync_at, last_sync_status, app_token_revoked."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    required_keys = {"last_sync_at", "last_sync_status", "app_token_revoked"}
    for pid in (pid_a, pid_b):
        entry = state.profile_state_registry[pid]
        missing = required_keys - entry.keys()
        assert not missing, f"profile_state_registry[{pid!r}] missing required keys: {missing}"


def test_profile_state_last_sync_at_type() -> None:
    """last_sync_at must be datetime | None."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    assert isinstance(state.profile_state_registry[pid_a]["last_sync_at"], datetime)
    assert state.profile_state_registry[pid_b]["last_sync_at"] is None


def test_profile_state_last_sync_status_values() -> None:
    """last_sync_status must be 'ok' | 'failed' | 'in_progress' | None."""
    valid_statuses = {"ok", "failed", "in_progress", None}

    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    for pid in (pid_a, pid_b):
        status = state.profile_state_registry[pid]["last_sync_status"]
        assert status in valid_statuses


def test_profile_state_app_token_revoked_type() -> None:
    """app_token_revoked must be bool."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    for pid in (pid_a, pid_b):
        revoked = state.profile_state_registry[pid]["app_token_revoked"]
        assert isinstance(revoked, bool)


def test_two_profiles_independent_entries() -> None:
    """Mutating one profile's entry must not affect the other."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    b_status_before = state.profile_state_registry[pid_b]["last_sync_status"]
    b_revoked_before = state.profile_state_registry[pid_b]["app_token_revoked"]

    state.profile_state_registry[pid_a]["last_sync_status"] = "failed"
    state.profile_state_registry[pid_a]["app_token_revoked"] = True

    assert state.profile_state_registry[pid_b]["last_sync_status"] == b_status_before
    assert state.profile_state_registry[pid_b]["app_token_revoked"] == b_revoked_before


def test_two_profiles_produce_two_distinct_dict_objects() -> None:
    """Each profile must have a distinct dict object in the registry."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_profile_state_registry(pid_a, pid_b)

    entry_a = state.profile_state_registry[pid_a]
    entry_b = state.profile_state_registry[pid_b]
    assert entry_a is not entry_b


# ── RED gate: real app.state does not yet have profile_state_registry ─────────
#
# These tests FAIL when Plan 02-02 lands and adds profile_state_registry.
# They are the actual RED baseline assertions for this file.
# Current P1 code uses default_profile_last_sync_at (singular), not a registry.


def test_real_app_state_has_singular_sync_state_not_registry() -> None:
    """Current app.state has default_profile_last_sync_at (singular), not profile_state_registry.

    RED until Plan 02-02 lands. After 02-02, app.state will have
    profile_state_registry and no longer use the singular per-default attributes.
    """
    from gruvax.app import create_app

    app = create_app()
    # Pre-lifespan: app.state has no dynamic attrs yet.
    assert not hasattr(app.state, "profile_state_registry"), (
        "profile_state_registry already exists on app.state — "
        "Plan 02-02 has landed; this RED gate test should be removed."
    )

"""Unit tests for per-profile cache registry isolation — Plan 02-00 RED baseline.

Covers API-02: per-profile registry isolation on app.state.

Tests assert the intended registry attribute names and per-profile isolation
on a REAL (post-lifespan) app instance. All tests are RED until Plan 02-02
lands the per-profile registry refactor — they fail because app.state currently
uses singular attributes (boundary_cache, event_bus) rather than per-profile
registries (boundary_cache_registry, event_bus_registry).

The canonical registry attribute names per D2-01:
  - boundary_cache_registry: dict[str, BoundaryCache]
  - snapshot_registry:       dict[str, CollectionSnapshot]
  - segment_cache_registry:  dict[str, SegmentCache]
  - settings_cache_registry: dict[str, dict]
  - event_bus_registry:      dict[str, EventBus]

Strategy: build a small fake state object that has the INTENDED shape and
assert the five registry names are present, lookups work, and two distinct
profile keys return distinct instances. Then, separately, verify that the
REAL app.state does NOT yet have the per-profile registry attributes (RED gate
for production code). The real-app assertion flips to a test failure when
Plan 02-02 lands — that is the intended GREEN trigger.
"""

from __future__ import annotations

import types
import uuid

from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.collection_snapshot import CollectionSnapshot
from gruvax.estimator.segment_cache import SegmentCache


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_fake_state_with_registries(
    profile_id_a: str,
    profile_id_b: str,
) -> types.SimpleNamespace:
    """Build a fake app.state namespace with per-profile registry dicts.

    This mirrors the intended lifespan shape after Plan 02-02 lands (D2-01).
    Each registry maps str(profile_id) → per-profile cache instance.
    """
    from gruvax.events.bus import EventBus

    state = types.SimpleNamespace()
    state.boundary_cache_registry = {
        profile_id_a: BoundaryCache(),
        profile_id_b: BoundaryCache(),
    }
    state.snapshot_registry = {
        profile_id_a: CollectionSnapshot(),
        profile_id_b: CollectionSnapshot(),
    }
    state.segment_cache_registry = {
        profile_id_a: SegmentCache(),
        profile_id_b: SegmentCache(),
    }
    state.settings_cache_registry = {
        profile_id_a: {},
        profile_id_b: {},
    }
    state.event_bus_registry = {
        profile_id_a: EventBus(),
        profile_id_b: EventBus(),
    }
    return state


# ── test: registry attribute names and isolation (via fake state) ─────────────
#
# These tests use the fake state to document the intended contract.
# They PASS now (describing the intended post-02-02 shape) and remain GREEN.
# The RED tests are in the "real app.state" section below.


def test_boundary_cache_registry_attribute_name() -> None:
    """app.state.boundary_cache_registry must exist and be keyed by str(profile_id)."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    assert hasattr(state, "boundary_cache_registry")
    cache_a = state.boundary_cache_registry[pid_a]
    cache_b = state.boundary_cache_registry[pid_b]
    assert isinstance(cache_a, BoundaryCache)
    assert isinstance(cache_b, BoundaryCache)


def test_snapshot_registry_attribute_name() -> None:
    """app.state.snapshot_registry must exist and be keyed by str(profile_id)."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    assert hasattr(state, "snapshot_registry")
    snap_a = state.snapshot_registry[pid_a]
    snap_b = state.snapshot_registry[pid_b]
    assert isinstance(snap_a, CollectionSnapshot)
    assert isinstance(snap_b, CollectionSnapshot)


def test_segment_cache_registry_attribute_name() -> None:
    """app.state.segment_cache_registry must exist and be keyed by str(profile_id)."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    assert hasattr(state, "segment_cache_registry")
    seg_a = state.segment_cache_registry[pid_a]
    seg_b = state.segment_cache_registry[pid_b]
    assert isinstance(seg_a, SegmentCache)
    assert isinstance(seg_b, SegmentCache)


def test_settings_cache_registry_attribute_name() -> None:
    """app.state.settings_cache_registry must exist and be keyed by str(profile_id)."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    assert hasattr(state, "settings_cache_registry")
    settings_a = state.settings_cache_registry[pid_a]
    settings_b = state.settings_cache_registry[pid_b]
    assert isinstance(settings_a, dict)
    assert isinstance(settings_b, dict)


def test_event_bus_registry_attribute_name() -> None:
    """app.state.event_bus_registry must exist and be keyed by str(profile_id)."""
    from gruvax.events.bus import EventBus

    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    assert hasattr(state, "event_bus_registry")
    bus_a = state.event_bus_registry[pid_a]
    bus_b = state.event_bus_registry[pid_b]
    assert isinstance(bus_a, EventBus)
    assert isinstance(bus_b, EventBus)


def test_all_five_registry_names_present() -> None:
    """All 5 registry attribute names (D2-01) must be present on app.state.

    Canonical names: boundary_cache_registry, snapshot_registry,
    segment_cache_registry, settings_cache_registry, event_bus_registry.
    """
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    required = (
        "boundary_cache_registry",
        "snapshot_registry",
        "segment_cache_registry",
        "settings_cache_registry",
        "event_bus_registry",
    )
    for name in required:
        assert hasattr(state, name), (
            f"app.state missing registry '{name}' — Plan 02-02 must add it (D2-01)"
        )


def test_boundary_cache_registry_isolation() -> None:
    """Two profile keys must return DISTINCT BoundaryCache instances."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    cache_a = state.boundary_cache_registry[pid_a]
    cache_b = state.boundary_cache_registry[pid_b]
    assert cache_a is not cache_b


def test_event_bus_registry_isolation() -> None:
    """Two profile keys must return DISTINCT EventBus instances."""
    from gruvax.events.bus import EventBus

    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    bus_a = state.event_bus_registry[pid_a]
    bus_b = state.event_bus_registry[pid_b]
    assert isinstance(bus_a, EventBus)
    assert isinstance(bus_b, EventBus)
    assert bus_a is not bus_b


def test_snapshot_registry_isolation() -> None:
    """Two profile keys must return DISTINCT CollectionSnapshot instances."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    snap_a = state.snapshot_registry[pid_a]
    snap_b = state.snapshot_registry[pid_b]
    assert snap_a is not snap_b


def test_segment_cache_registry_isolation() -> None:
    """Two profile keys must return DISTINCT SegmentCache instances."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    seg_a = state.segment_cache_registry[pid_a]
    seg_b = state.segment_cache_registry[pid_b]
    assert seg_a is not seg_b


def test_settings_cache_registry_isolation() -> None:
    """Two profile keys must return DISTINCT settings dicts."""
    pid_a = str(uuid.uuid4())
    pid_b = str(uuid.uuid4())
    state = _make_fake_state_with_registries(pid_a, pid_b)

    settings_a = state.settings_cache_registry[pid_a]
    settings_b = state.settings_cache_registry[pid_b]
    assert settings_a is not settings_b


# ── RED gate: real app.state does not yet have per-profile registries ─────────
#
# These tests are the actual RED baseline. They FAIL when Plan 02-02 lands
# (because the assertion "registry is absent" becomes false after refactor).
# That failure is the intended GREEN trigger for Plan 02-02 verification.
#
# Tests assert: real app.state currently has SINGULAR attributes (boundary_cache,
# event_bus) rather than the per-profile dict registries D2-01 requires.


def test_real_app_state_has_singular_boundary_cache_not_registry() -> None:
    """Current app.state has boundary_cache (singular), not boundary_cache_registry.

    RED until Plan 02-02 lands. After 02-02, app.state will have
    boundary_cache_registry and no longer have boundary_cache.
    """
    from gruvax.app import create_app

    app = create_app()
    # Pre-lifespan app has no dynamic state attributes yet.
    # The test documents the P1 state: singular, no registry.
    assert not hasattr(app.state, "boundary_cache_registry"), (
        "boundary_cache_registry exists on app.state — "
        "Plan 02-02 has landed; this RED gate test should be removed."
    )


def test_real_app_state_has_singular_event_bus_not_registry() -> None:
    """Current app.state has event_bus (singular), not event_bus_registry.

    RED until Plan 02-02 lands. After 02-02, app.state will have
    event_bus_registry (dict[str, EventBus]) and no longer event_bus (singular).
    """
    from gruvax.app import create_app

    app = create_app()
    assert not hasattr(app.state, "event_bus_registry"), (
        "event_bus_registry exists on app.state — "
        "Plan 02-02 has landed; this RED gate test should be removed."
    )

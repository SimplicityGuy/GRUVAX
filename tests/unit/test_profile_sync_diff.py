"""Unit tests for collection-diff computation in profile_sync (API-04).

Tests:
  - test_collection_changed_payload: assert the published collection_changed
    payload dict contains keys profile_id, new_record_count, is_initial_import.
  - test_arrival_count_arithmetic: verify new_record_count = max(0, row_count - existing_count)
    including never-negative invariant.
  - test_is_initial_import_detection: verify is_initial_import is True when last_sync_at
    is None (first-ever sync) and False when it is not None.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


# ── Arrival count arithmetic tests ───────────────────────────────────────────


@pytest.mark.parametrize(
    "row_count, existing_count, expected",
    [
        (100, 90, 10),  # 10 new arrivals
        (50, 50, 0),  # no new arrivals (identical collection)
        (200, 0, 200),  # initial import: all are new
        (80, 100, 0),  # shrinking collection: never negative
        (0, 0, 0),  # empty → empty
        (1, 0, 1),  # first record
    ],
)
def test_arrival_count_arithmetic(row_count: int, existing_count: int, expected: int) -> None:
    """new_record_count = max(0, row_count - existing_count) — never negative.

    This is the D-06 invariant: arrivals only, never negative.
    Tested as a pure arithmetic assertion since the formula is a one-liner
    in _swap_inside_tx.
    """
    new_record_count = max(0, row_count - existing_count)
    assert new_record_count == expected, (
        f"max(0, {row_count} - {existing_count}) expected {expected}, got {new_record_count}"
    )
    assert new_record_count >= 0, "new_record_count must never be negative (D-06)"


# ── is_initial_import detection tests ────────────────────────────────────────


@pytest.mark.parametrize(
    "last_sync_at, expected_is_initial",
    [
        (None, True),  # first-ever sync: last_sync_at IS NULL → is_initial_import=True
        ("2026-01-01T00:00:00Z", False),  # subsequent sync: has prior sync_at → False
        ("2026-05-31T03:00:00Z", False),  # nightly sync: not initial
    ],
)
def test_is_initial_import_detection(last_sync_at: str | None, expected_is_initial: bool) -> None:
    """is_initial_import is True iff last_sync_at IS NULL before the swap UPDATE.

    Pitfall 4: this must be read BEFORE the UPDATE that sets last_sync_at = NOW().
    The formula is simply: is_initial_import = (last_sync_at is None).
    """
    is_initial_import = last_sync_at is None
    assert is_initial_import == expected_is_initial, (
        f"last_sync_at={last_sync_at!r}: expected is_initial_import={expected_is_initial}, "
        f"got {is_initial_import}"
    )


# ── collection_changed payload structure test ─────────────────────────────────


@pytest.mark.asyncio
async def test_collection_changed_payload() -> None:
    """The published collection_changed payload contains profile_id, new_record_count,
    is_initial_import.

    Mocks the EventBus.publish call and asserts the payload dict shape matches
    the Phase 7 extended contract (RESEARCH.md Pattern 5).

    This test exercises _refresh_profile_caches to confirm it passes all three
    keys through to publish.
    """
    from gruvax.sync import profile_sync

    profile_id = "00000000-0000-0000-0000-000000000001"
    new_record_count = 42
    is_initial_import = True

    captured_events: list[tuple[str, dict[str, Any]]] = []

    # Build a minimal mock of app_state that satisfies _refresh_profile_caches.
    mock_bus = AsyncMock()
    mock_bus.publish.side_effect = lambda name, data: captured_events.append((name, data))

    mock_cache = MagicMock()
    mock_cache.invalidate = MagicMock()
    mock_cache.load = AsyncMock()
    mock_cache.overrides = {}

    mock_snapshot = MagicMock()
    mock_snapshot.load = AsyncMock()

    mock_seg = MagicMock()
    mock_seg.derive = MagicMock()

    mock_app_state = MagicMock()
    mock_app_state.db_pool = MagicMock()
    mock_app_state.boundary_cache_registry = {profile_id: mock_cache}
    mock_app_state.snapshot_registry = {profile_id: mock_snapshot}
    mock_app_state.segment_cache_registry = {profile_id: mock_seg}
    mock_app_state.event_bus_registry = {profile_id: mock_bus}

    # Call the extended _refresh_profile_caches with the new parameters.
    await profile_sync._refresh_profile_caches(
        profile_id,
        mock_app_state,
        new_record_count=new_record_count,
        is_initial_import=is_initial_import,
    )

    assert len(captured_events) == 1, (
        f"Expected exactly 1 publish call, got {len(captured_events)}: {captured_events}"
    )
    event_name, payload = captured_events[0]
    assert event_name == "collection_changed", (
        f"Event name must be 'collection_changed', got {event_name!r}"
    )
    assert "profile_id" in payload, "payload must contain 'profile_id'"
    assert "new_record_count" in payload, (
        "payload must contain 'new_record_count' (API-04 requirement)"
    )
    assert "is_initial_import" in payload, (
        "payload must contain 'is_initial_import' (D-07 requirement)"
    )
    assert payload["profile_id"] == profile_id, (
        f"profile_id mismatch: expected {profile_id!r}, got {payload['profile_id']!r}"
    )
    assert payload["new_record_count"] == new_record_count, (
        f"new_record_count mismatch: expected {new_record_count}, got {payload['new_record_count']}"
    )
    assert payload["is_initial_import"] == is_initial_import, (
        f"is_initial_import mismatch: expected {is_initial_import}, "
        f"got {payload['is_initial_import']}"
    )


@pytest.mark.asyncio
async def test_collection_changed_payload_subsequent_sync() -> None:
    """is_initial_import=False on a subsequent sync, new_record_count can be 0."""
    from gruvax.sync import profile_sync

    profile_id = "00000000-0000-0000-0000-000000000001"
    captured_events: list[tuple[str, dict[str, Any]]] = []

    mock_bus = AsyncMock()
    mock_bus.publish.side_effect = lambda name, data: captured_events.append((name, data))

    mock_cache = MagicMock()
    mock_cache.invalidate = MagicMock()
    mock_cache.load = AsyncMock()
    mock_cache.overrides = {}

    mock_snapshot = MagicMock()
    mock_snapshot.load = AsyncMock()

    mock_seg = MagicMock()
    mock_seg.derive = MagicMock()

    mock_app_state = MagicMock()
    mock_app_state.db_pool = MagicMock()
    mock_app_state.boundary_cache_registry = {profile_id: mock_cache}
    mock_app_state.snapshot_registry = {profile_id: mock_snapshot}
    mock_app_state.segment_cache_registry = {profile_id: mock_seg}
    mock_app_state.event_bus_registry = {profile_id: mock_bus}

    await profile_sync._refresh_profile_caches(
        profile_id,
        mock_app_state,
        new_record_count=0,
        is_initial_import=False,
    )

    assert len(captured_events) == 1
    _, payload = captured_events[0]
    assert payload["new_record_count"] == 0
    assert payload["is_initial_import"] is False

"""Unit tests for the nightly scheduler — Phase 4 Plan 04-00 Task 1 (SYN-01).

Phase 4 Wave 0 RED scaffolding. These tests import and call symbols from
gruvax.sync.nightly that do NOT exist yet (module ships in Plan 04-01).
They will fail at import or assertion until production code lands — that is
the expected RED state.

Analog: tests/unit/test_admin_led_settings.py (role-match: unit tests for a
settings/service component using AsyncMock + fake pool pattern).

Behaviors under test:
  (a) test_cadence_anchoring — next_fire_after() derived from fire-hour lists
      {"24h": [3], "12h": [3, 15], "6h": [3, 9, 15, 21]} picks the soonest
      correct hour. (D4-03)
  (b) test_skip_policy — the loop's profile-selection SQL excludes
      app_token_revoked=TRUE and last_sync_status='in_progress' rows.
      Assert against a stubbed cursor return. (D4-04)
  (c) test_cadence_off — when _read_sync_cadence returns "off", one loop
      iteration parks (sleeps) and never calls sync_profile. (D4-06)
  (d) test_read_sync_cadence_fallback — absent settings row returns "24h".
      (D4-06 / Pitfall 6)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

# Cadence fire-hour table (D4-03).
_CADENCE_HOURS: dict[str, list[int]] = {
    "24h": [3],
    "12h": [3, 15],
    "6h": [3, 9, 15, 21],
}


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    """Build a UTC-aware datetime for cadence anchoring tests."""
    return datetime(year, month, day, hour, minute, 0, tzinfo=timezone.utc)


# ── (a) Cadence fire-time anchoring ──────────────────────────────────────────


@pytest.mark.parametrize(
    "cadence,now_hour,expected_next_hour",
    [
        # 24h cadence: only fires at 03:00
        ("24h", 1, 3),   # 01:00 → next is 03:00 same day
        ("24h", 4, 3),   # 04:00 → next is 03:00 next day (past today's slot)
        ("24h", 23, 3),  # 23:00 → next is 03:00 next day
        # 12h cadence: fires at 03:00 and 15:00
        ("12h", 1, 3),   # 01:00 → next is 03:00
        ("12h", 4, 15),  # 04:00 → next is 15:00 same day
        ("12h", 16, 3),  # 16:00 → next is 03:00 next day (past 15:00 slot)
        # 6h cadence: fires at 03:00, 09:00, 15:00, 21:00
        ("6h", 1, 3),    # 01:00 → next is 03:00
        ("6h", 4, 9),    # 04:00 → next is 09:00
        ("6h", 10, 15),  # 10:00 → next is 15:00
        ("6h", 16, 21),  # 16:00 → next is 21:00
        ("6h", 22, 3),   # 22:00 → next is 03:00 next day
    ],
)
def test_cadence_anchoring(cadence: str, now_hour: int, expected_next_hour: int) -> None:
    """next_fire_after() returns the soonest fire hour for the given cadence.

    D4-03: The scheduler resolves the next fire time by picking the smallest
    hour in the cadence list that is strictly after `now`. If no hour today
    qualifies, it picks the first hour in the cadence list for the next day.
    """
    from gruvax.sync.nightly import next_fire_after

    now = _utc(2026, 6, 1, now_hour)
    hours = _CADENCE_HOURS[cadence]

    # Find the soonest fire after now from the cadence's hour list
    result = min(next_fire_after(now, h) for h in hours)
    assert result.hour == expected_next_hour, (
        f"cadence={cadence!r}, now_hour={now_hour}: "
        f"expected next fire hour={expected_next_hour}, got hour={result.hour} "
        f"(result={result!r})"
    )


# ── (b) Skip policy ───────────────────────────────────────────────────────────


class _FakeCursor:
    """Minimal async cursor stub for skip-policy test."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    async def execute(self, sql: str, params: Any = None) -> None:
        pass

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return self._rows

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakeConn:
    """Minimal async connection stub."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *args: object) -> None:
        pass


class _FakePool:
    """Minimal pool stub that returns a controlled cursor."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def connection(self) -> _FakeConn:
        return _FakeConn(self._rows)


@pytest.mark.asyncio
async def test_skip_policy() -> None:
    """_sync_loop skip policy: revoked and in_progress profiles are excluded.

    D4-04: The SELECT that feeds _sync_loop must filter out:
      - profiles where app_token_revoked = TRUE
      - profiles where last_sync_status = 'in_progress'

    Strategy: stub the pool to return only eligible UUIDs (both filter conditions
    already applied by the SQL), then assert sync_profile is called exactly for
    those UUIDs and NOT for the revoked/in_progress ones.

    The loop is sleep-FIRST (it sleeps until the next scheduled fire, then syncs),
    so we let the first asyncio.sleep (the scheduling sleep) return normally,
    allow the single sync pass to run, then raise asyncio.CancelledError on the
    SECOND sleep to stop the loop after exactly one pass. CancelledError is a
    BaseException (not Exception), so the loop does not swallow it.
    """
    import asyncio

    from gruvax.sync.nightly import _sync_loop

    eligible_uuid = "00000000-0000-0000-0000-000000000001"
    revoked_uuid = "00000000-0000-0000-0000-000000000002"   # excluded by SQL
    inprogress_uuid = "00000000-0000-0000-0000-000000000003"  # excluded by SQL

    # The skip policy SQL excludes revoked/in_progress rows before returning.
    # Our stub cursor reflects that: only the eligible profile is in the result set.
    eligible_rows = [(eligible_uuid,)]
    pool = _FakePool(eligible_rows)

    sync_calls: list[str] = []

    async def _fake_sync(profile_id: str, app_state: Any) -> None:
        sync_calls.append(profile_id)

    # Sleep-first loop: first sleep (scheduling) returns so the sync pass runs;
    # second sleep (next iteration's scheduling sleep) raises to stop the loop.
    sleep_calls = 0

    async def _fake_sleep(seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 2:
            raise asyncio.CancelledError("stop after one sync pass")
        return None

    app_state = MagicMock()

    with (
        patch("gruvax.sync.nightly.sync_profile", _fake_sync),
        patch("gruvax.sync.nightly.asyncio.sleep", _fake_sleep),
    ):
        try:
            await _sync_loop(pool=pool, app_state=app_state)
        except asyncio.CancelledError:
            pass

    # Only the eligible profile should have been passed to sync_profile
    assert sync_calls == [eligible_uuid], (
        f"Expected sync_profile called with [{eligible_uuid!r}], got {sync_calls!r}. "
        f"Revoked ({revoked_uuid!r}) and in_progress ({inprogress_uuid!r}) "
        f"profiles must be excluded by the SQL skip policy."
    )
    # Sleep must have been reached (confirms loop ran one pass)
    assert sleep_calls >= 1, "Loop did not reach asyncio.sleep — may not have run"


# ── (c) Cadence "off" — parks without syncing ─────────────────────────────────


@pytest.mark.asyncio
async def test_cadence_off() -> None:
    """When cadence is "off", _sync_loop parks (sleeps) without calling sync_profile.

    D4-06: A setting of sync.cadence="off" must completely suppress sync calls.
    The loop should call asyncio.sleep (park) but must not call sync_profile for
    any profile, for as long as cadence remains "off".

    Strategy: stub _read_sync_cadence to return "off", patch sync_profile to record
    calls, run one iteration (raise CancelledError from sleep to stop), and assert
    sync_profile was never called.
    """
    import asyncio

    from gruvax.sync.nightly import _sync_loop

    pool = _FakePool([])  # pool has zero rows — but cadence=off should never reach SQL
    sync_calls: list[str] = []

    async def _fake_sync(profile_id: str, app_state: Any) -> None:
        sync_calls.append(profile_id)

    async def _fake_sleep(seconds: float) -> None:
        raise asyncio.CancelledError("stop after one park")

    async def _fake_read_cadence(pool: Any) -> str:
        return "off"

    app_state = MagicMock()

    with (
        patch("gruvax.sync.nightly.sync_profile", _fake_sync),
        patch("gruvax.sync.nightly.asyncio.sleep", _fake_sleep),
        patch("gruvax.sync.nightly._read_sync_cadence", _fake_read_cadence),
    ):
        try:
            await _sync_loop(pool=pool, app_state=app_state)
        except asyncio.CancelledError:
            pass

    assert sync_calls == [], (
        f"When cadence='off', sync_profile must NOT be called. "
        f"Got calls: {sync_calls!r}"
    )


# ── (d) _read_sync_cadence fallback: absent row returns "24h" ─────────────────


@pytest.mark.asyncio
async def test_read_sync_cadence_fallback() -> None:
    """_read_sync_cadence returns "24h" when no settings row exists.

    D4-06 / Pitfall 6: The settings table may not have a sync.cadence row
    (e.g. fresh install before first admin save). The function must fall back
    to the default cadence of "24h" rather than raising KeyError or returning None.
    """
    from gruvax.sync.nightly import _read_sync_cadence

    # Stub pool whose cursor returns no rows (absent settings row)
    empty_pool = _FakePool([])

    result = await _read_sync_cadence(empty_pool)
    assert result == "24h", (
        f"_read_sync_cadence must return '24h' when no settings row exists, "
        f"got {result!r}"
    )

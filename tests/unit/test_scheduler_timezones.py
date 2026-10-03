"""Pinned timezone transitions prove elapsed scheduling, independent of host TZ."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from gruvax.sync import nightly


@pytest.mark.parametrize(
    "zone,date,hours",
    [
        ("America/Los_Angeles", (2026, 3, 7), 23),
        ("America/Los_Angeles", (2026, 10, 31), 25),
        ("Australia/Lord_Howe", (2026, 10, 3), 23.5),
        ("Australia/Lord_Howe", (2026, 4, 4), 24.5),
    ],
)
@pytest.mark.asyncio
async def test_loop_sleeps_actual_elapsed_time_across_dst(monkeypatch, zone, date, hours):  # type: ignore[no-untyped-def]
    now = datetime(*date, 3, tzinfo=ZoneInfo(zone))
    sleeps = []

    async def sleep(seconds):  # type: ignore[no-untyped-def]
        sleeps.append(seconds)
        raise asyncio.CancelledError

    monkeypatch.setattr(nightly, "now_local", lambda: now)
    monkeypatch.setattr(nightly, "_read_sync_cadence", AsyncMock(return_value="24h"))
    monkeypatch.setattr(nightly.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await nightly._sync_loop(None, None)
    assert sleeps == [hours * 3600]


def test_now_local_keeps_configured_transition_rules(monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        nightly, "settings", SimpleNamespace(TZ="America/Los_Angeles"), raising=False
    )
    result = nightly.now_local()
    assert isinstance(result.tzinfo, ZoneInfo)
    assert result.tzinfo.key == "America/Los_Angeles"


def test_fall_back_uses_second_fold_if_it_is_still_future() -> None:
    zone = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    result = nightly.next_fire_after(now, 1)
    assert result == datetime(2026, 11, 1, 1, tzinfo=zone, fold=1)
    assert result.fold == 1
    assert (result.astimezone(UTC) - now.astimezone(UTC)).total_seconds() == 1800


def test_nonexistent_spring_hour_moves_forward_to_valid_wall_time() -> None:
    zone = ZoneInfo("America/Los_Angeles")
    now = datetime(2026, 3, 8, 1, 30, tzinfo=zone)
    result = nightly.next_fire_after(now, 2)
    assert result == datetime(2026, 3, 8, 3, tzinfo=zone)
    assert result.astimezone(UTC).astimezone(zone) == result


def test_config_rejects_unknown_timezone() -> None:
    from pydantic import ValidationError

    from gruvax.settings import Settings

    with pytest.raises(ValidationError, match="TZ must name an available IANA timezone"):
        Settings(TZ="Synthetic/Unknown")


def test_half_hour_spring_gap_resolves_to_valid_local_time() -> None:
    zone = ZoneInfo("Australia/Lord_Howe")
    now = datetime(2026, 10, 4, 1, 45, tzinfo=zone)
    result = nightly.next_fire_after(now, 2)
    assert result == datetime(2026, 10, 4, 2, 30, tzinfo=zone)
    assert result.astimezone(UTC).astimezone(zone) == result

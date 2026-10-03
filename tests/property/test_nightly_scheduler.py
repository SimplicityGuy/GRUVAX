"""Timezone-pinned scheduler properties compare real UTC instants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from hypothesis import given, settings, strategies as st

from gruvax.sync.nightly import next_fire_after


# ── Invariant 1: next_fire_after() is always strictly in the future ───────────


@given(
    # Generate a datetime in 2025-2027 to cover DST transitions
    epoch_seconds=st.integers(
        min_value=int(datetime(2025, 1, 1, tzinfo=UTC).timestamp()),
        max_value=int(datetime(2027, 12, 31, tzinfo=UTC).timestamp()),
    ),
    hour=st.integers(min_value=0, max_value=23),
    zone=st.sampled_from(
        [
            "America/New_York",
            "America/Los_Angeles",
            "Europe/London",
            "Australia/Sydney",
            "Australia/Lord_Howe",
        ]
    ),
)
@settings(max_examples=500)
def test_next_fire_always_future(epoch_seconds: int, hour: int, zone: str) -> None:
    """next_fire_after() always returns a time strictly after now.

    D4-01: The scheduler must never schedule a fire time in the past.
    Verified across the full 2025-2027 range (covers DST transitions in
    US/Eastern, US/Pacific, Europe/London, Australia/Sydney, etc.).
    """
    now = datetime.fromtimestamp(epoch_seconds, UTC).astimezone(ZoneInfo(zone))
    result = next_fire_after(now, hour)
    assert result.astimezone(UTC) > now.astimezone(UTC), (
        f"next_fire_after({now!r}, hour={hour}) returned {result!r} which is not strictly after now"
    )


# ── Invariant 2: successive 03:00 firings are 22-26h apart ──────────────────


@given(
    epoch_seconds=st.integers(
        min_value=int(datetime(2025, 1, 1, tzinfo=UTC).timestamp()),
        max_value=int(datetime(2027, 12, 31, tzinfo=UTC).timestamp()),
    ),
    zone=st.sampled_from(
        [
            "America/New_York",
            "America/Los_Angeles",
            "Europe/London",
            "Australia/Sydney",
            "Australia/Lord_Howe",
        ]
    ),
)
@settings(max_examples=500)
def test_next_fire_interval_in_22_26h_window(epoch_seconds: int, zone: str) -> None:
    """Successive 03:00 firings are always 22-26 elapsed hours apart.

    D4-01: DST transitions can shift the elapsed gap by ±1h from 24h.
    The invariant [22h, 26h] is intentionally wide to pass through both
    spring-forward (23h gap) and fall-back (25h gap) transitions safely.
    A gap outside [22, 26] would indicate a bug in the fold/tzinfo handling.
    """
    now = datetime.fromtimestamp(epoch_seconds, UTC).astimezone(ZoneInfo(zone))
    t1 = next_fire_after(now, 3)
    t2 = next_fire_after(t1 + timedelta(seconds=1), 3)
    delta_h = (t2.astimezone(UTC) - t1.astimezone(UTC)).total_seconds() / 3600
    assert 22 <= delta_h <= 26, (
        f"interval {delta_h:.2f}h between successive 03:00 firings is outside "
        f"the expected [22, 26] window. t1={t1!r}, t2={t2!r}"
    )

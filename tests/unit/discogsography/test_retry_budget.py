"""Exercise real stamina attempt limits without waiting for upstream delays."""

from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
import stamina._core
import tenacity

from gruvax.discogsography.client import DiscogsographyClient, _parse_retry_after
from gruvax.discogsography.errors import NetworkError, RateLimitExhausted


@pytest.mark.parametrize(
    "header,seconds",
    [
        ("1000000000", 300),
        ("inf", 1),
        ("nan", 1),
        ("-5", 1),
        (None, 1),
        ("Wed, 21 Oct 2015 07:28:00 GMT", 1),
    ],
)
def test_retry_after_is_finite_and_bounded(header, seconds):  # type: ignore[no-untyped-def]
    assert _parse_retry_after(header) == timedelta(seconds=seconds)


@pytest.mark.asyncio
@pytest.mark.parametrize("network", [False, True])
async def test_large_delays_do_not_truncate_attempt_budget(monkeypatch, network: bool) -> None:
    clock = [0.0]
    waits = []

    async def sleep(delay: float) -> None:
        waits.append(delay)
        clock[0] += delay

    monkeypatch.setattr(tenacity, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(stamina._core, "_smart_sleep", sleep)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if network:
            # A slow failed request must still receive its promised second attempt.
            clock[0] += 60
            raise httpx.ReadTimeout("synthetic slow request", request=request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    client = DiscogsographyClient("http://synthetic", "dscg_synthetic_retry")
    await client._client.aclose()
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://synthetic"
    )
    try:
        with pytest.raises(NetworkError if network else RateLimitExhausted):
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert len(calls) == (2 if network else 4)
    assert len(waits) == (1 if network else 3)
    if not network:
        assert waits == [60, 60, 60]

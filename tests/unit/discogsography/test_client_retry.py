"""Plan 02 Task 3 — DiscogsographyClient retry semantics (CONTEXT.md §specifics LOCKED).

Tests 1-11 (per PLAN.md):
  1.  401 → PATRejected, NO retry (call counter == 1).
  2.  403 → PATRejected, NO retry.
  3.  429 → honor Retry-After then exp backoff; succeed on 3rd attempt;
      wall-clock between first/second call ≥ 1s.
  4.  429 exhausts → RateLimitExhausted after 4 total calls (3 retries).
  5.  5xx (500) → exp backoff; succeed on 3rd attempt.
  6.  5xx exhausts → ServerError after 4 total calls (3 retries).
  7.  Network error (ConnectError twice) → NetworkError after 2 total calls.
  8.  iter_collection pagination over 450 rows yields exactly 450 releases.
  9.  first_page returns dict with user_id, releases, has_more.
  10. Retry-After HTTP-date defense — predicate defaults to 1s; no crash.
  11. PAT plaintext NEVER in exception message (LEAK_DETECTOR sentinel).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response
import pytest


if TYPE_CHECKING:
    from collections.abc import Callable

from gruvax._internal.fake_discogsography import create_fake_app
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _client_with_transport(transport: Any, pat: str = "dscg_test") -> DiscogsographyClient:
    """Build a DiscogsographyClient whose underlying httpx client uses a
    user-provided transport. PATTERNS §4 "test access" note — _client is
    deliberately single-underscored so tests may substitute it.
    """
    client = DiscogsographyClient(base_url="http://fake", pat=pat)
    # Substitute transport WITHOUT changing the Bearer header that __init__ set.
    client._client = AsyncClient(
        transport=transport,
        base_url="http://fake",
        headers={"Authorization": f"Bearer {pat}"},
        timeout=httpx.Timeout(5.0),
    )
    return client


def _sequence_transport(
    responses: list[Callable[[Request], Response] | Response],
    counter: dict[str, int] | None = None,
) -> MockTransport:
    """Build a MockTransport that returns the i-th response on the i-th call.

    If ``counter`` is provided, the dict's ``"n"`` key is updated to track the
    number of times the transport was invoked — used by tests that need to
    assert "no retry was made" (Test 1) or "exactly N total calls" (Test 4).
    """
    if counter is None:
        counter = {"n": 0}
    responses_list = list(responses)

    def handler(request: Request) -> Response:
        idx = counter["n"]
        counter["n"] = idx + 1
        # Defensive — last response repeats if a test under-specifies.
        entry = responses_list[-1] if idx >= len(responses_list) else responses_list[idx]
        if callable(entry):
            return entry(request)
        return entry

    return MockTransport(handler)


# ── Test 1: 401 → PATRejected, NO retry ──────────────────────────────────────


async def test_401_raises_pat_rejected_no_retry() -> None:
    counter: dict[str, int] = {"n": 0}
    transport = _sequence_transport(
        [Response(401, json={"detail": "Missing or invalid token"})],
        counter=counter,
    )
    client = _client_with_transport(transport)
    try:
        with pytest.raises(PATRejected):
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert counter["n"] == 1, f"401 must NOT trigger a retry — got {counter['n']} calls, expected 1"


# ── Test 2: 403 → PATRejected, NO retry ──────────────────────────────────────


async def test_403_raises_pat_rejected_no_retry() -> None:
    counter: dict[str, int] = {"n": 0}
    transport = _sequence_transport(
        [Response(403, json={"detail": "Missing collection:read scope"})],
        counter=counter,
    )
    client = _client_with_transport(transport)
    try:
        with pytest.raises(PATRejected):
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert counter["n"] == 1, f"403 must NOT trigger a retry — got {counter['n']} calls, expected 1"


# ── Test 3: 429 honors Retry-After then succeeds ─────────────────────────────


async def test_429_retries_with_retry_after_then_succeeds() -> None:
    """Two 429+Retry-After:1 responses, then 200. Wall-clock between first
    and second call ≥ 1s (Retry-After honored).
    """
    counter: dict[str, int] = {"n": 0}
    call_times: list[float] = []

    def handler_429_then_ok(request: Request) -> Response:
        call_times.append(time.monotonic())
        idx = counter["n"]
        counter["n"] = idx + 1
        if idx < 2:
            return Response(429, headers={"Retry-After": "1"}, json={"detail": "rate limited"})
        return Response(
            200,
            json={
                "user_id": "11111111-2222-3333-4444-555555555555",
                "releases": [],
                "total": 0,
                "offset": 0,
                "limit": 1,
                "has_more": False,
            },
        )

    transport = MockTransport(handler_429_then_ok)
    client = _client_with_transport(transport)
    try:
        page = await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()

    assert counter["n"] == 3, f"expected 3 total calls (2x429 + 1x200), got {counter['n']}"
    assert page["user_id"] == "11111111-2222-3333-4444-555555555555"
    # Wall-clock between call #1 and call #2 should be ≥ 1s (Retry-After:1).
    # Allow a small floor (0.95s) for clock-resolution slop.
    assert call_times[1] - call_times[0] >= 0.95, (
        f"Retry-After:1 not honored — delta was {call_times[1] - call_times[0]:.3f}s"
    )


# ── Test 4: 429 exhausts → RateLimitExhausted ────────────────────────────────


async def test_429_exhausts_raises_rate_limit_exhausted() -> None:
    """4 consecutive 429s → RateLimitExhausted after exactly 4 total calls."""
    counter: dict[str, int] = {"n": 0}
    transport = _sequence_transport(
        [Response(429, headers={"Retry-After": "1"}, json={"detail": "rate limited"})] * 6,
        counter=counter,
    )
    client = _client_with_transport(transport)
    try:
        with pytest.raises(RateLimitExhausted):
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert counter["n"] == 4, (
        f"expected exactly 4 total calls (1 initial + 3 retries), got {counter['n']}"
    )


# ── Test 5: 5xx exp-backoff then succeed ─────────────────────────────────────


async def test_5xx_retries_then_succeeds() -> None:
    counter: dict[str, int] = {"n": 0}
    success_body = {
        "user_id": "22222222-3333-4444-5555-666666666666",
        "releases": [],
        "total": 0,
        "offset": 0,
        "limit": 1,
        "has_more": False,
    }

    def handler_500_then_ok(request: Request) -> Response:
        idx = counter["n"]
        counter["n"] = idx + 1
        if idx < 2:
            return Response(500, json={"detail": "server error"})
        return Response(200, json=success_body)

    transport = MockTransport(handler_500_then_ok)
    client = _client_with_transport(transport)
    try:
        page = await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert counter["n"] == 3, f"expected 3 total calls (2x500 + 1x200), got {counter['n']}"
    assert page["user_id"] == "22222222-3333-4444-5555-666666666666"


# ── Test 6: 5xx exhausts → ServerError ───────────────────────────────────────


async def test_5xx_exhausts_raises_server_error() -> None:
    counter: dict[str, int] = {"n": 0}
    transport = _sequence_transport(
        [Response(500, json={"detail": "server error"})] * 6,
        counter=counter,
    )
    client = _client_with_transport(transport)
    try:
        with pytest.raises(ServerError):
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert counter["n"] == 4, (
        f"expected exactly 4 total calls (1 initial + 3 retries), got {counter['n']}"
    )


# ── Test 7: network error → 1 retry then NetworkError ────────────────────────


async def test_network_error_one_retry_then_network_error() -> None:
    """ConnectError twice in a row → NetworkError after exactly 2 total calls."""
    counter: dict[str, int] = {"n": 0}

    def handler_connect_error(request: Request) -> Response:
        counter["n"] += 1
        raise httpx.ConnectError("simulated connect refused", request=request)

    transport = MockTransport(handler_connect_error)
    client = _client_with_transport(transport)
    try:
        with pytest.raises((NetworkError, httpx.ConnectError)):
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert counter["n"] == 2, (
        f"network error must retry exactly once — got {counter['n']} calls, expected 2"
    )


# ── Test 8: iter_collection pagination over 450 rows ─────────────────────────


async def test_iter_collection_pages_all_releases() -> None:
    """450-row seed via the canonical fake → iter_collection yields all 450."""
    seed = [{"id": str(i), "title": f"r{i}"} for i in range(450)]
    app = create_fake_app(seed=seed)
    transport = ASGITransport(app=app)
    client = _client_with_transport(transport)
    try:
        collected: list[dict[str, Any]] = []
        async for release in client.iter_collection(page_size=200):
            collected.append(release)
    finally:
        await client.aclose()
    assert len(collected) == 450, f"expected 450 releases, got {len(collected)}"
    assert {r["id"] for r in collected} == {str(i) for i in range(450)}


# ── Test 9: first_page returns envelope with user_id ─────────────────────────


async def test_first_page_returns_envelope_with_user_id() -> None:
    seed = [{"id": "1", "title": "Solo"}]
    custom_user_id = "abcdef00-0000-0000-0000-fedcba000001"
    app = create_fake_app(seed=seed, user_id=custom_user_id)
    transport = ASGITransport(app=app)
    client = _client_with_transport(transport)
    try:
        page = await client.first_page()
    finally:
        await client.aclose()
    assert isinstance(page, dict)
    assert "user_id" in page
    assert "releases" in page
    assert "has_more" in page
    assert page["user_id"] == custom_user_id


# ── Test 10: Retry-After HTTP-date defense (Pitfall 4) ───────────────────────


async def test_retry_after_http_date_does_not_crash() -> None:
    """``Retry-After: Wed, 21 Oct 2026 07:28:00 GMT`` must not crash the
    predicate — it defaults to 1s and proceeds.
    """
    counter: dict[str, int] = {"n": 0}

    def handler(request: Request) -> Response:
        idx = counter["n"]
        counter["n"] = idx + 1
        if idx == 0:
            # First call: 429 with an HTTP-date Retry-After (not seconds).
            return Response(
                429,
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                json={"detail": "rate limited"},
            )
        # Subsequent call: 200.
        return Response(
            200,
            json={
                "user_id": "33333333-4444-5555-6666-777777777777",
                "releases": [],
                "total": 0,
                "offset": 0,
                "limit": 1,
                "has_more": False,
            },
        )

    transport = MockTransport(handler)
    client = _client_with_transport(transport)
    try:
        page = await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    # Did not crash and recovered on the 2nd attempt.
    assert counter["n"] == 2
    assert page["user_id"] == "33333333-4444-5555-6666-777777777777"


# ── Test 11: PAT plaintext NEVER in client error message ─────────────────────


async def test_pat_plaintext_never_in_client_error_message() -> None:
    """Trigger PATRejected. Assert the LEAK_DETECTOR sentinel is NOT present
    in str(exc).
    """
    leak_detector_pat = "dscg_test_pat_secret_LEAK_DETECTOR_12345"
    transport = _sequence_transport(
        [Response(401, json={"detail": "Missing or invalid token"})],
    )
    client = _client_with_transport(transport, pat=leak_detector_pat)
    try:
        with pytest.raises(PATRejected) as exc_info:
            await client._get_page(limit=1, offset=0)
    finally:
        await client.aclose()
    assert "LEAK_DETECTOR" not in str(exc_info.value), (
        f"PAT plaintext substring 'LEAK_DETECTOR' leaked into PATRejected "
        f"message: {exc_info.value!r}"
    )
    # Also verify the full message is operator-safe.
    assert "dscg_" not in str(exc_info.value)
    assert "401" in str(exc_info.value) or "rejected" in str(exc_info.value).lower()

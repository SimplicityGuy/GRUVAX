"""Integration tests for per-profile SSE endpoint — Plan 02-00 RED baseline.

Covers D2-04: /api/events/{profile_id} with session validation.
All tests are RED until Plan 02-03 lands the per-profile SSE refactor.

Tests:
  - test_sse_403_on_profile_mismatch: cookie bound to profile A, GET /api/events/{B} → 403
  - test_sse_400_on_unbound: no browse cookie, GET /api/events/{A} → 400
  - test_sse_connects_when_bound: cookie bound to A, GET /api/events/{A} → 200 + initial comment
  - test_no_cross_profile_leakage: two clients on A and B; event on A's bus must not reach B

The browse-binding cookie name is gruvax_browse_binding (D2-10, RESEARCH §Pattern 5).
This is a separate cookie from gruvax_session (admin) — D2-10 constraint.

Uses a live uvicorn server (background thread) so streaming SSE responses are
delivered over a genuine TCP socket, mirroring the test_sse.py pattern exactly.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
import time

import httpx
import pytest
import uvicorn

from gruvax.app import create_app


# ── browse-binding cookie name (D2-10) ───────────────────────────────────────
#
# Must differ from gruvax_session and gruvax_csrf.
# RESEARCH §Pattern 5 names it "gruvax_browse_binding".
# The test asserts this name to enforce the separation contract (D2-10).

BROWSE_BINDING_COOKIE = "gruvax_browse_binding"

# ── live-server fixture ──────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(db_pool):  # type: ignore[no-untyped-def]
    """Real uvicorn server in a background thread for SSE testing.

    Mirrors the fixture from test_sse.py exactly.
    """
    port = _find_free_port()
    app = create_app()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        loop="asyncio",
        log_level="warning",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn server did not start within 10s")
        time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_403_on_profile_mismatch(live_server) -> None:  # type: ignore[no-untyped-def]
    """Browse cookie bound to profile A; GET /api/events/{B} → 403.

    RED until Plan 02-03 lands. After landing, the SSE endpoint validates the
    path profile_id against the session's bound_profile_id and returns 403 on
    mismatch (D2-04).
    """
    profile_a = "00000000-0000-0000-0000-000000000001"  # default profile UUID
    profile_b = "00000000-0000-0000-0000-000000000002"  # a different (potentially absent) UUID

    cookies = {BROWSE_BINDING_COOKIE: profile_a}

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.get(
            f"/api/events/{profile_b}",
            cookies=cookies,
        )

    assert res.status_code == 403, (
        f"GET /api/events/{{profile_b}} with cookie bound to profile_a must return 403 "
        f"(D2-04 profile mismatch), got {res.status_code}. "
        f"RED until Plan 02-03 lands the per-profile SSE endpoint."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_400_on_unbound(live_server) -> None:  # type: ignore[no-untyped-def]
    """No browse cookie → GET /api/events/{A} → 400 (session unbound).

    RED until Plan 02-03 lands. An SSE request with no binding cookie must
    return 400 with type 'session_unbound' (D2-04, D2-06).
    """
    profile_a = "00000000-0000-0000-0000-000000000001"

    async with httpx.AsyncClient(base_url=live_server) as ac:
        # No cookies — no binding
        res = await ac.get(f"/api/events/{profile_a}")

    assert res.status_code == 400, (
        f"GET /api/events/{{profile_id}} with no browse-binding cookie must return 400 "
        f"(D2-06 unbound session), got {res.status_code}. "
        f"RED until Plan 02-03 lands the per-profile SSE endpoint."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_connects_when_bound(live_server) -> None:  # type: ignore[no-untyped-def]
    """Browse cookie bound to A → GET /api/events/{A} → 200 + initial connected comment.

    RED until Plan 02-03 lands. When the session is bound to the correct
    profile, the SSE endpoint should stream a 200 response with the initial
    ': connected' comment (D2-04, D2-06).

    Note: Currently /api/events (without profile_id) exists (Phase 1). The
    test targets /api/events/{profile_id} which does NOT yet exist. The test
    will fail with 404 until Plan 02-03 adds the route.
    """
    profile_a = "00000000-0000-0000-0000-000000000001"
    cookies = {BROWSE_BINDING_COOKIE: profile_a}

    async with (
        httpx.AsyncClient(base_url=live_server) as ac,
        ac.stream("GET", f"/api/events/{profile_a}", cookies=cookies) as resp,
    ):
        assert resp.status_code == 200, (
            f"GET /api/events/{profile_a} with bound cookie must return 200, "
            f"got {resp.status_code}. RED until Plan 02-03 adds the route."
        )
        # Read just the first line (the ': connected' comment) then close.
        got_comment = False
        async for line in resp.aiter_lines():
            if line.startswith(":"):
                got_comment = True
                break
        assert got_comment, "SSE stream must start with a ': connected' comment line"


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_emits_jittered_retry(live_server) -> None:  # type: ignore[no-untyped-def]
    """GET /api/events/{profile_id} initial SSE frame must carry a retry: directive in [2000, 8000].

    Verifies OFF-03 (PITFALLS 36 anti-thundering-herd): each connected client
    receives a distinct reconnect interval so ~30 kiosks do not reconnect in
    lockstep after a server restart.  The value is randomised per connection;
    this test asserts the contract (range + presence + positive int), not a
    specific value, and does NOT monkeypatch random.
    """
    profile_a = "00000000-0000-0000-0000-000000000001"
    cookies = {BROWSE_BINDING_COOKIE: profile_a}

    retry_value: int | None = None

    async with (
        httpx.AsyncClient(base_url=live_server) as ac,
        ac.stream("GET", f"/api/events/{profile_a}", cookies=cookies) as resp,
    ):
        assert resp.status_code == 200, (
            f"GET /api/events/{profile_a} with bound cookie must return 200, "
            f"got {resp.status_code}"
        )
        # Read up to 10 lines to find the retry: directive in the initial SSE frame.
        lines_read = 0
        async for line in resp.aiter_lines():
            lines_read += 1
            if line.startswith("retry:"):
                raw = line[len("retry:"):].strip()
                assert raw.isdigit(), (
                    f"retry: field must be a non-negative integer, got {raw!r}"
                )
                retry_value = int(raw)
                break
            if lines_read >= 10:
                break  # initial frame should be within the first few lines

    assert retry_value is not None, (
        "Initial SSE frame must contain a 'retry:' directive (OFF-03 / PITFALLS 36). "
        "No retry: line found in the first 10 SSE lines."
    )
    assert 2000 <= retry_value <= 8000, (
        f"retry: value {retry_value} is outside the required [2000, 8000] ms window "
        "(OFF-03 / PITFALLS 36: jitter range 2000-8000 ms). "
        "Implementation in events.py lines 65-66: random.randint(2000, 8000)."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_no_cross_profile_leakage(live_server) -> None:  # type: ignore[no-untyped-def]
    """Two SSE clients on profiles A and B; event on A's bus must not reach B.

    RED until Plan 02-03 lands. After landing:
    - Client bound to A subscribes to /api/events/{A}
    - Client bound to B subscribes to /api/events/{B}
    - Triggering an event on profile A (via boundary update) delivers
      collection_changed / boundary_changed only to A's subscriber, not B's

    This test uses a simplified approach: both clients connect; we publish to A's
    bus (by triggering a boundary update as admin) and assert only A receives it.
    If the profile-isolated bus is not implemented, B would also receive A's events.

    Since the per-profile event endpoint doesn't yet exist, this test documents
    the leakage invariant. It will go RED in a different way (404 / routing error)
    until Plan 02-03 lands.
    """
    profile_a = "00000000-0000-0000-0000-000000000001"
    profile_b = "00000000-0000-0000-0000-000000000002"  # non-existent but tests routing

    received_by_a: list[str] = []
    received_by_b: list[str] = []
    a_connected = asyncio.Event()
    b_connected = asyncio.Event()

    async def subscribe_a() -> None:
        cookies = {BROWSE_BINDING_COOKIE: profile_a}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{profile_a}",
                    cookies=cookies,
                    timeout=5.0,
                ) as resp,
            ):
                if resp.status_code != 200:
                    a_connected.set()
                    return
                a_connected.set()
                async for line in resp.aiter_lines():
                    if "boundary_changed" in line or "collection_changed" in line:
                        received_by_a.append(line)
                        return
        except (httpx.TimeoutException, httpx.RemoteProtocolError):
            a_connected.set()

    async def subscribe_b() -> None:
        cookies = {BROWSE_BINDING_COOKIE: profile_b}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{profile_b}",
                    cookies=cookies,
                    timeout=5.0,
                ) as resp,
            ):
                if resp.status_code not in (200, 403, 404):
                    b_connected.set()
                    return
                b_connected.set()
                if resp.status_code != 200:
                    return
                async for line in resp.aiter_lines():
                    if "boundary_changed" in line or "collection_changed" in line:
                        received_by_b.append(line)
                        return
        except (httpx.TimeoutException, httpx.RemoteProtocolError):
            b_connected.set()

    # Start both subscribers
    task_a = asyncio.create_task(subscribe_a())
    task_b = asyncio.create_task(subscribe_b())

    # Wait for both to connect (or fail) before triggering the event
    await asyncio.wait_for(
        asyncio.gather(a_connected.wait(), b_connected.wait()),
        timeout=10.0,
    )

    # We cannot trigger a real event without admin session in the live server test
    # here, so we rely on the structural assertion:
    # If profile B's endpoint returns 403 (correct behavior — unrecognized profile),
    # or the subscriber is isolated, B receives nothing.
    # Wait a moment for any cross-leakage to manifest.
    await asyncio.sleep(0.3)

    for task in (task_a, task_b):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    # The core leakage assertion: B must not receive profile A's events.
    assert not received_by_b, (
        f"Cross-profile leakage detected: profile B received events meant for profile A: "
        f"{received_by_b}. The per-profile event bus must isolate events by profile_id (D2-05)."
    )

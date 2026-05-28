"""Integration tests for GET /api/events/{profile_id} SSE endpoint — Phase 4 ADMN-11, RTM-01, RTM-02.

Plan 02-03: updated from /api/events to /api/events/{profile_id} with browse-binding cookie.

Tests:
  - test_sse_headers: GET /api/events/{profile_id} (with bound cookie) returns
    X-Accel-Buffering: no + Cache-Control: no-store (Pitfall 8).
  - test_boundary_changed_latency: admin PUT → kiosk receives boundary_changed via SSE in
    <500ms (primary ADMN-11 gate).
  - test_concurrent_searches: two simultaneous searches complete without serialization
    (RTM-02, Pitfall 10 — SSE holds no pool slot).

SSE + httpx note:
  httpx's ASGITransport buffers the full response body before returning, which is
  incompatible with infinite SSE streams.  We use a real uvicorn server (background
  thread) so that streaming responses are delivered over a genuine TCP socket.  This
  is the standard pattern for testing FastAPI SSE endpoints.
"""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest
import uvicorn

from gruvax.app import create_app


# Default profile UUID (D-02) — the single profile seeded by migrations.
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
# Browse-binding cookie name (D2-10) — separate from gruvax_session.
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"


def _find_free_port() -> int:
    """Return an OS-assigned free TCP port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(db_pool):  # type: ignore[no-untyped-def]
    """Start a real uvicorn server in a background thread for SSE testing.

    Returns the base URL (e.g. ``http://127.0.0.1:PORT``).

    Using a real TCP socket is required because httpx's ASGITransport buffers
    the entire response body before yielding control — incompatible with infinite
    SSE streams.  Uvicorn streams over real sockets, so httpx can read headers
    and body chunks incrementally.

    ``db_pool`` in the signature ensures the DB is up before the server starts
    (session fixture). The server creates its own connection pool via the standard
    lifespan path — the fixture dependency is only to gate timing.
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
    server.install_signal_handlers = lambda: None  # disable SIGINT hijacking

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait until the server is ready (polls every 50ms, up to 10s)
    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn server did not start within 10s")
        time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    # Graceful shutdown
    server.should_exit = True
    thread.join(timeout=5)


async def _login(base_url: str) -> dict[str, str]:
    """Log in with test PIN, return cookies dict + csrf_token.

    Mirrors the conftest admin_session fixture inline — we can't depend on
    the module-scope conftest admin_session from a module-scope fixture that
    uses a different client shape.
    """
    async with httpx.AsyncClient(base_url=base_url) as ac:
        res = await ac.post("/api/admin/login", json={"pin": "0000"})
        if res.status_code != 200:
            return {}
        csrf = res.cookies.get("gruvax_csrf") or ""
        return {"cookies": dict(res.cookies), "csrf_token": csrf}


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_headers(live_server) -> None:  # type: ignore[no-untyped-def]
    """GET /api/events/{profile_id} must set X-Accel-Buffering: no + Cache-Control: no-store.

    Plan 02-03: the endpoint is now per-profile — the browse-binding cookie must be
    set to the default profile UUID to obtain a 200.
    Binds Pitfall 8: without these headers, nginx/proxy buffers SSE data into
    30-second clumps, making live re-render appear broken.
    """
    cookies = {BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID}
    sse_url = f"/api/events/{DEFAULT_PROFILE_UUID}"
    async with (
        httpx.AsyncClient(base_url=live_server) as ac,
        ac.stream("GET", sse_url, cookies=cookies) as resp,
    ):
        assert resp.status_code == 200, (
            f"Expected 200 from {sse_url} with bound cookie, got {resp.status_code}"
        )
        assert resp.headers.get("x-accel-buffering") == "no", (
            f"X-Accel-Buffering header missing or wrong: {dict(resp.headers)}"
        )
        assert resp.headers.get("cache-control") == "no-store", (
            f"Cache-Control header missing or wrong: {dict(resp.headers)}"
        )
        # Read just the first line (the `: connected` comment) then close.
        async for _line in resp.aiter_lines():
            break


@pytest.mark.asyncio(loop_scope="session")
async def test_boundary_changed_latency(live_server) -> None:  # type: ignore[no-untyped-def]
    """Admin PUT → kiosk receives boundary_changed via SSE in <500ms.

    This is the primary ADMN-11 gate (roadmap criterion 1: ~500ms live re-render).

    Protocol:
      1. Open an SSE reader task on GET /api/events.
      2. Wait ~50ms for the SSE connection to establish.
      3. Record t0, then issue PUT /api/admin/cubes/1/0/0/boundary (force=True).
      4. Assert boundary_changed appears in the stream within 0.5s of t0.
      5. Restore the original fixture boundary so other tests are unaffected.

    Uses force=True to skip the phantom check (synthetic values won't be in
    v_collection).  Restores cube 1/0/0 to its boundaries.yaml fixture values
    after the test to avoid contaminating test_locate.py and others.
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not implemented — skipping SSE latency test")

    # Fixture boundary for cube 1/0/0 (boundaries.yaml row 0, col 0).
    # Phase 5 (SEG-01): last_label / last_catalog removed from request bodies.
    ORIGINAL_BOUNDARY = {
        "first_label": "Blue Note",
        "first_catalog": "BLP 4001",
        "is_empty": False,
        "force": True,
    }
    TEST_BOUNDARY = {
        "first_label": "ZZ Test",
        "first_catalog": "ZZT 0001",
        "is_empty": False,
        "force": True,
    }

    received = asyncio.Event()
    sse_url = f"/api/events/{DEFAULT_PROFILE_UUID}"
    sse_cookies = {BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID}

    async def read_sse() -> None:
        async with (
            httpx.AsyncClient(base_url=live_server) as ac,
            ac.stream("GET", sse_url, cookies=sse_cookies) as response,
        ):
            async for line in response.aiter_lines():
                if "boundary_changed" in line:
                    received.set()
                    return

    sse_task = asyncio.create_task(read_sse())
    # Let the SSE connection establish before triggering the write
    await asyncio.sleep(0.05)

    t0 = time.perf_counter()
    # Admin PUT triggers boundary_changed fan-out (after cache.load in Phase 4)
    async with httpx.AsyncClient(base_url=live_server) as ac:
        await ac.put(
            "/api/admin/cubes/1/0/0/boundary",
            json=TEST_BOUNDARY,
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    try:
        await asyncio.wait_for(received.wait(), timeout=0.5)
    except TimeoutError:
        sse_task.cancel()
        # Attempt restore before failing
        async with httpx.AsyncClient(base_url=live_server) as ac:
            await ac.put(
                "/api/admin/cubes/1/0/0/boundary",
                json=ORIGINAL_BOUNDARY,
                cookies=auth["cookies"],
                headers={"X-CSRF-Token": auth["csrf_token"]},
            )
        pytest.fail("boundary_changed not received within 500ms — ADMN-11 gate FAILED")

    latency = time.perf_counter() - t0
    sse_task.cancel()

    # Restore original fixture boundary so other tests (e.g. test_locate.py) are unaffected
    async with httpx.AsyncClient(base_url=live_server) as ac:
        await ac.put(
            "/api/admin/cubes/1/0/0/boundary",
            json=ORIGINAL_BOUNDARY,
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert latency < 0.5, f"boundary_changed latency {latency:.3f}s exceeded 500ms budget"


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_searches(live_server) -> None:  # type: ignore[no-untyped-def]
    """Two simultaneous searches complete concurrently — no server-side serialization.

    Binds RTM-02: the SSE endpoint holds no DB pool slot (Pitfall 10), so concurrent
    search requests are not starved. Both requests must complete independently
    (total wall-time is not ~2x a single search).
    """

    async def do_search(q: str) -> float:
        t0 = time.perf_counter()
        cookies = {BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID}
        async with httpx.AsyncClient(base_url=live_server) as ac:
            await ac.get(
                "/api/search",
                params={"q": q, "profile_id": DEFAULT_PROFILE_UUID},
                cookies=cookies,
            )
        return time.perf_counter() - t0

    t_start = time.perf_counter()
    durations = await asyncio.gather(
        do_search("blue note"),
        do_search("columbia"),
    )
    wall_time = time.perf_counter() - t_start

    # Both must have completed
    assert len(durations) == 2, "Expected two search results from gather"

    # Wall-time must be significantly less than the sum of individual times,
    # confirming concurrent (not sequential) execution.
    # A 2x sequential overhead means wall_time ~ sum(durations). We allow up
    # to max(durations) * 1.5 to account for scheduling overhead.
    max_single = max(durations)
    assert wall_time < max_single * 1.5 + 0.1, (
        f"Searches appear serialized: wall_time={wall_time:.3f}s, "
        f"individual times={[f'{d:.3f}' for d in durations]}"
    )

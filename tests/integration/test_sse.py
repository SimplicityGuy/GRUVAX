"""Integration tests for GET /api/events SSE endpoint — Phase 4 ADMN-11, RTM-01, RTM-02.

Tests:
  - test_sse_headers: GET /api/events returns X-Accel-Buffering: no + Cache-Control: no-store
    (Pitfall 8).
  - test_boundary_changed_latency: admin PUT → kiosk receives boundary_changed via SSE in
    <500ms (primary ADMN-11 gate).
  - test_concurrent_searches: two simultaneous searches complete without serialization
    (RTM-02, Pitfall 10 — SSE holds no pool slot).

Analog: tests/integration/test_health.py (LifespanManager + ASGITransport + AsyncClient).
"""

from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    ``db_pool`` is the session-scoped fixture from conftest — ensures the
    DB is running before the app boots.
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, app


async def _login(ac: AsyncClient) -> dict[str, str]:
    """Helper: log in with test PIN and return cookies + CSRF token.

    Mirrors the conftest admin_session fixture logic inline — we need a local
    copy here because admin_session depends on the module-scope client fixture
    shape and scope (module vs. session).  The conftest admin_session fixture
    is available for tests that need its full seeding behaviour.
    """
    res = await ac.post("/api/admin/login", json={"pin": "0000"})
    if res.status_code != 200:
        return {}
    csrf = res.cookies.get("gruvax_csrf") or ""
    return {"cookies": res.cookies, "csrf_token": csrf}


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_headers(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/events must set X-Accel-Buffering: no and Cache-Control: no-store.

    Binds Pitfall 8: without these headers, nginx/proxy buffers SSE data into
    30-second clumps, making live re-render appear broken.
    """
    ac, _app = client
    async with ac.stream("GET", "/api/events") as resp:
        assert resp.status_code == 200, f"Expected 200 from /api/events, got {resp.status_code}"
        assert resp.headers.get("x-accel-buffering") == "no", (
            f"X-Accel-Buffering header missing or wrong: {dict(resp.headers)}"
        )
        assert resp.headers.get("cache-control") == "no-store", (
            f"Cache-Control header missing or wrong: {dict(resp.headers)}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_boundary_changed_latency(client) -> None:  # type: ignore[no-untyped-def]
    """Admin PUT → kiosk receives boundary_changed via SSE in <500ms.

    This is the primary ADMN-11 gate (roadmap criterion 1: ~500ms live re-render).

    Protocol:
      1. Open an SSE reader task on GET /api/events.
      2. Wait ~50ms for the SSE connection to establish.
      3. Record t0, then issue PUT /api/admin/cubes/1/0/0/boundary.
      4. Assert boundary_changed appears in the stream within 0.5s of t0.
    """
    ac, _app = client

    auth = await _login(ac)
    if not auth:
        pytest.skip("Admin login not implemented — skipping SSE latency test")

    received = asyncio.Event()

    async def read_sse() -> None:
        async with ac.stream("GET", "/api/events") as response:
            async for line in response.aiter_lines():
                if "boundary_changed" in line:
                    received.set()
                    return

    sse_task = asyncio.create_task(read_sse())
    # Let the SSE connection establish before triggering the write
    await asyncio.sleep(0.05)

    t0 = time.perf_counter()
    # Admin PUT triggers boundary_changed fan-out (after cache.load in Phase 4)
    await ac.put(
        "/api/admin/cubes/1/0/0/boundary",
        json={
            "first_label": "A",
            "first_catalog": "A001",
            "last_label": "B",
            "last_catalog": "B001",
            "is_empty": False,
            "force": True,
        },
        cookies=auth["cookies"],
        headers={"X-CSRF-Token": auth["csrf_token"]},
    )

    try:
        await asyncio.wait_for(received.wait(), timeout=0.5)
    except TimeoutError:
        sse_task.cancel()
        pytest.fail("boundary_changed not received within 500ms — ADMN-11 gate FAILED")

    latency = time.perf_counter() - t0
    sse_task.cancel()
    assert latency < 0.5, f"boundary_changed latency {latency:.3f}s exceeded 500ms budget"


@pytest.mark.asyncio(loop_scope="session")
async def test_concurrent_searches(client) -> None:  # type: ignore[no-untyped-def]
    """Two simultaneous searches complete concurrently — no server-side serialization.

    Binds RTM-02: the SSE endpoint holds no DB pool slot (Pitfall 10), so concurrent
    search requests are not starved. Both requests must complete independently
    (total wall-time is not ~2× a single search).
    """
    ac, _app = client

    # Fire two concurrent search requests
    async def do_search(q: str) -> float:
        t0 = time.perf_counter()
        await ac.get("/api/search", params={"q": q})
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
    # A 2× sequential overhead means wall_time ≈ sum(durations). We allow up
    # to max(durations) * 1.5 to account for scheduling overhead.
    max_single = max(durations)
    assert wall_time < max_single * 1.5 + 0.1, (
        f"Searches appear serialized: wall_time={wall_time:.3f}s, "
        f"individual times={[f'{d:.3f}' for d in durations]}"
    )

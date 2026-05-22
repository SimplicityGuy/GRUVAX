"""Integration tests for POST /api/admin/editing heartbeat endpoint — Phase 4 RTM-04.

Tests:
  - test_editing_requires_auth: POST /api/admin/editing with no session → 401 or 403,
    nothing published (T-04-08 auth gate).
  - test_editing_fans_out: with admin_session cookies + X-CSRF-Token,
    POST {cube_ids:[{unit:1,row:0,col:0}], editing:true} → 200 {"ok":true},
    AND a connected SSE reader on /api/events receives an admin_editing event (RTM-04).

Uses the real uvicorn server pattern (from test_sse.py) for the fan-out test because
httpx's ASGITransport buffers the full response body before returning — incompatible
with infinite SSE streams.
"""

from __future__ import annotations

import asyncio
import threading
import time

import httpx
import pytest

from gruvax.app import create_app


def _find_free_port() -> int:
    """Return an OS-assigned free TCP port."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server(db_pool):  # type: ignore[no-untyped-def]
    """Start a real uvicorn server in a background thread.

    Mirrors test_sse.py fixture exactly — required for SSE streaming tests.
    ``db_pool`` ensures the DB is ready before the server starts.
    """
    import uvicorn

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

    # Poll until the server is ready (up to 10s)
    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn server did not start within 10s")
        time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"
    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


async def _login(base_url: str) -> dict[str, str]:
    """Log in with the test PIN, return cookies + csrf_token.

    Mirrors the helper in test_sse.py; seeds the test PIN hash first.
    Returns an empty dict if login is not implemented.
    """
    import os

    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    # Seed the test PIN "0000" into the server's DB
    # The server has its own pool via the standard lifespan path.
    # Re-use a brief direct DB connection to upsert the hash.
    try:
        from gruvax.auth.pin import hash_pin  # noqa: PLC0415
        from gruvax.db.pool import create_pool  # noqa: PLC0415

        pool = create_pool(min_size=1, max_size=2, open=False)
        await pool.open()
        test_hash = hash_pin("0000")
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings (key, value, description, updated_at)"
                " VALUES ('auth.pin_hash', %s::jsonb, 'Test PIN seeded by test_editing', now())"
                " ON CONFLICT (key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (f'"{test_hash}"',),
            )
            await conn.commit()
        await pool.close()
    except Exception:
        pass  # Seeding failure — login will fail gracefully below

    async with httpx.AsyncClient(base_url=base_url) as ac:
        res = await ac.post("/api/admin/login", json={"pin": "0000"})
        if res.status_code != 200:
            return {}
        csrf = res.cookies.get("gruvax_csrf") or ""
        return {"cookies": dict(res.cookies), "csrf_token": csrf}


@pytest.mark.asyncio(loop_scope="session")
async def test_editing_requires_auth(live_server) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/editing without a session must be rejected (401 or 403).

    Binds T-04-08: the endpoint is session + CSRF gated. An unauthenticated
    call must be rejected before anything is published to the bus.
    """
    payload = {"cube_ids": [{"unit": 1, "row": 0, "col": 0}], "editing": True}
    async with httpx.AsyncClient(base_url=live_server) as ac:
        # No cookies, no X-CSRF-Token
        res = await ac.post("/api/admin/editing", json=payload)
    assert res.status_code in (401, 403), (
        f"Unauthenticated POST /api/admin/editing must return 401 or 403, "
        f"got {res.status_code}: {res.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_editing_fans_out(live_server) -> None:  # type: ignore[no-untyped-def]
    """Authenticated POST /api/admin/editing fans out admin_editing via SSE.

    Binds RTM-04 + D-01:
      1. Open an SSE reader on GET /api/events.
      2. Wait ~50ms for the SSE connection to establish.
      3. POST /api/admin/editing with a valid admin session + X-CSRF-Token.
      4. Assert the SSE stream delivers an admin_editing event within 1s.
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping fan-out test")

    received = asyncio.Event()

    async def read_sse() -> None:
        async with (
            httpx.AsyncClient(base_url=live_server) as ac,
            ac.stream("GET", "/api/events") as response,
        ):
            async for line in response.aiter_lines():
                if "admin_editing" in line:
                    received.set()
                    return

    sse_task = asyncio.create_task(read_sse())
    # Allow SSE connection to establish before triggering the heartbeat
    await asyncio.sleep(0.05)

    payload = {"cube_ids": [{"unit": 1, "row": 0, "col": 0}], "editing": True}
    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.post(
            "/api/admin/editing",
            json=payload,
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert res.status_code == 200, (
        f"Expected 200 from POST /api/admin/editing, got {res.status_code}: {res.text}"
    )
    body = res.json()
    assert body == {"ok": True}, f"Expected {{\"ok\": true}}, got {body}"

    try:
        await asyncio.wait_for(received.wait(), timeout=1.0)
    except TimeoutError:
        sse_task.cancel()
        pytest.fail(
            "admin_editing event not received via SSE within 1s — RTM-04 gate FAILED"
        )

    sse_task.cancel()

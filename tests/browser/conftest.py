"""pytest fixtures for browser (Playwright) tests.

Provides:
  - ``live_server_url`` — a real uvicorn server in a background thread, yielding
    ``http://127.0.0.1:{port}``. Copied verbatim from the pattern in
    tests/integration/test_sse_per_profile.py and tests/integration/test_devices.py.

    The browser tests need a genuine TCP socket (not ASGI transport) because
    Playwright makes real HTTP requests and cannot use httpx ASGI transport.
"""

from __future__ import annotations

import os
import socket
import threading
import time

import pytest
import uvicorn

from gruvax.app import create_app


_TEST_PIN = "0000"
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server_url(db_pool):  # type: ignore[no-untyped-def]
    """Real uvicorn server in a background thread for Playwright tests.

    Seeds the test PIN hash ("0000") into gruvax.settings so that admin-gated
    bind tests can log in via the API inside the Playwright context.

    Mirrors the live_server fixture from test_sse_per_profile.py and
    test_devices.py (uvicorn-in-thread pattern). Yields ``http://127.0.0.1:{port}``.

    Module-scoped: one server instance shared across all browser tests in this
    module (starts once, stops after the module's last test).
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

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
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10.0
    while not server.started:
        if time.monotonic() > deadline:
            pytest.fail("uvicorn live_server did not start within 10s")
        time.sleep(0.05)

    base_url = f"http://127.0.0.1:{port}"

    # Seed the test PIN hash so admin bind works inside the Playwright context.
    # The server is running so we can reach app.state directly.
    _seed_test_pin(app, _DEFAULT_PROFILE_UUID, _TEST_PIN)

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


def _seed_test_pin(app: object, profile_uuid: str, pin: str) -> None:
    """Synchronously seed the test PIN hash into gruvax.settings.

    Runs a short asyncio loop to execute the async DB write. This is safe
    because it runs before tests start using the server (the uvicorn server
    runs its own event loop on the daemon thread; this uses a separate loop
    for the one-time seed operation).
    """
    import asyncio

    from gruvax.auth.pin import hash_pin

    test_hash = hash_pin(pin)

    async def _insert() -> None:
        pool = getattr(getattr(app, "state", None), "db_pool", None)
        if pool is None:
            return
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings"
                " (profile_id, key, value, description, updated_at)"
                " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb,"
                "   'Test PIN seeded by browser conftest', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (profile_uuid, f'"{test_hash}"'),
            )
            await conn.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_insert())
    finally:
        loop.close()

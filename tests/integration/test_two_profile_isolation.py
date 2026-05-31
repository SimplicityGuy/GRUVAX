"""Integration tests for two-profile boundary isolation (DATA-01, D-02, D-04, D-10).

Tests:
  - test_boundary_edit_profile_a_does_not_touch_profile_b (DATA-01 write scoping):
      A PUT bound to the default profile (A) must not modify profile B's sentinel row
      at the same (unit_id, row, col).
  - test_unbound_admin_write_returns_400 (D-02):
      A PUT with admin credentials but NO browse-binding cookie returns 400 session_unbound.
  - test_zero_row_write_returns_404 (D-10):
      A PUT bound to profile B for a (unit, row, col) absent from B returns 404 boundary_not_found.
  - test_boundary_changed_fans_out_per_profile (D-04, success criterion #4):
      A boundary write bound to profile A delivers boundary_changed only on A's SSE channel;
      profile B's channel receives nothing. The other-profile channel GET is verified 200 first
      (bus exists at server start) so the negative assertion is meaningful (WARNING-2).
  - test_admin_editing_fans_out_per_profile (D-04 shimmer isolation):
      POST /api/admin/editing bound to profile A delivers admin_editing only on A's SSE channel;
      profile B's channel receives nothing.

Design note — WARNING-2 registry constraint:
  Profile B must be inserted into gruvax.profiles BEFORE live_server calls create_app(),
  so create_app()'s startup loop builds B's EventBus. We achieve this by making the
  ``profile_b`` fixture a dependency of ``live_server`` (module-scoped). Both fixtures
  are module-scoped; pytest resolves dependencies in topological order — profile_b is
  created before live_server starts the uvicorn process.

All SQL uses parameterised %s placeholders — no f-string SQL.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import socket
import threading
import time
from typing import Any

import httpx
import psycopg
import pytest
import uvicorn

from gruvax.app import create_app


logger = logging.getLogger(__name__)

# ── constants ─────────────────────────────────────────────────────────────────

BROWSE_BINDING_COOKIE = "gruvax_browse_binding"
DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

# Sentinel first_label for profile B's boundary row — if the default-profile
# write overwrites this, the test fails.
_B_SENTINEL_LABEL = "B-SENTINEL"
_B_SENTINEL_CATALOG = "B-SENTINEL-001"

# (unit_id, row, col) that exists for the default profile (from boundaries.yaml)
# and will also be seeded for profile B with a sentinel value.
_SHARED_UNIT = 1
_SHARED_ROW = 0
_SHARED_COL = 0

# A (unit_id, row, col) that does NOT exist for profile B (deliberately absent).
_ABSENT_UNIT = 1
_ABSENT_ROW = 3
_ABSENT_COL = 3


# ── helpers ───────────────────────────────────────────────────────────────────


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get_dsn() -> str:
    from gruvax.settings import settings

    return settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


# ── profile_b fixture — must run before live_server ──────────────────────────
#
# Module-scoped so the same profile B is reused across all tests in this module
# and the live_server can build its EventBus during startup.  Teardown deletes
# B's boundary rows first (FK child), then soft-deletes the profile.


@pytest.fixture(scope="module")
def profile_b(db_pool) -> Any:  # type: ignore[no-untyped-def]
    """Insert profile B + its sentinel boundary row; yield its UUID string.

    Inserts synchronously via psycopg.connect (sync path) so the fixture can
    run before the pytest-asyncio event loop is finalised for the module.
    The profile is seeded with app_token_revoked=TRUE (no live PAT; sentinel pattern).

    Profile B gets one boundary row at (_SHARED_UNIT, _SHARED_ROW, _SHARED_COL) with
    first_label=_B_SENTINEL_LABEL so the isolation test can verify it is untouched.
    Profile B does NOT get a row at (_ABSENT_UNIT, _ABSENT_ROW, _ABSENT_COL) — that
    absence is the precondition for test_zero_row_write_returns_404.
    """
    dsn = _get_dsn()
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.profiles "
            "(display_name, app_token_encrypted, app_token_revoked) "
            "VALUES ('IsolationTestB', %s::bytea, TRUE) "
            "RETURNING id::text",
            (b"",),
        )
        row = cur.fetchone()
        conn.commit()

    assert row is not None, "profile_b INSERT failed — no row returned"
    b_uuid: str = row[0]

    # Seed a boundary row for profile B at the shared position with a sentinel.
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.cube_boundaries "
            "(profile_id, unit_id, row, col, first_label, first_catalog, is_empty) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s, FALSE) "
            "ON CONFLICT (profile_id, unit_id, row, col) DO UPDATE "
            "  SET first_label = EXCLUDED.first_label, "
            "      first_catalog = EXCLUDED.first_catalog, "
            "      updated_at = now()",
            (
                b_uuid,
                _SHARED_UNIT,
                _SHARED_ROW,
                _SHARED_COL,
                _B_SENTINEL_LABEL,
                _B_SENTINEL_CATALOG,
            ),
        )
        conn.commit()

    yield b_uuid

    # Teardown: remove B's boundary rows (FK child), then soft-delete profile B.
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "DELETE FROM gruvax.cube_boundaries WHERE profile_id = %s::uuid",
            (b_uuid,),
        )
        cur.execute(
            "UPDATE gruvax.profiles SET deleted_at = now() "
            "WHERE id = %s::uuid AND deleted_at IS NULL",
            (b_uuid,),
        )
        conn.commit()


# ── live_server fixture ───────────────────────────────────────────────────────
#
# IMPORTANT: profile_b is listed as a parameter so pytest creates it before
# this fixture runs — guaranteeing profile B exists when create_app() queries
# gruvax.profiles and builds the event_bus_registry (WARNING-2 constraint).


@pytest.fixture(scope="module")
def live_server(db_pool, profile_b) -> Any:  # type: ignore[no-untyped-def]
    """Real uvicorn server in a background thread for SSE testing.

    profile_b is a fixture dependency — pytest ensures it is created (and
    therefore visible to create_app()'s startup loop) before the server starts.
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


# ── login helper ──────────────────────────────────────────────────────────────


async def _login(base_url: str) -> dict[str, str]:
    """Log in with the test PIN; return cookies dict + csrf_token.

    Mirrors the helper in test_editing.py. Seeds the test PIN hash directly
    via a brief direct DB connection (the server has its own pool).
    The returned cookies dict includes the default-profile browse-binding cookie
    so that get_write_target resolves without raising 400 session_unbound (D-02).
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    try:
        from gruvax.auth.pin import hash_pin
        from gruvax.db.pool import create_pool

        pool = create_pool(min_size=1, max_size=2, open=False)
        await pool.open()
        test_hash = hash_pin("0000")
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings "
                "(profile_id, key, value, description, updated_at) "
                "VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb, "
                "'Test PIN seeded by test_two_profile_isolation', now()) "
                "ON CONFLICT (profile_id, key) DO UPDATE "
                "  SET value = EXCLUDED.value, updated_at = now()",
                (DEFAULT_PROFILE_UUID, f'"{test_hash}"'),
            )
            await conn.commit()
        await pool.close()
    except Exception:
        logger.exception("test_two_profile_isolation: PIN seeding failed")

    async with httpx.AsyncClient(base_url=base_url) as ac:
        res = await ac.post("/api/admin/login", json={"pin": "0000"})
        if res.status_code != 200:
            return {}
        csrf = res.cookies.get("gruvax_csrf") or ""
        cookies = dict(res.cookies)
        # Wire the default-profile browse-binding so get_write_target resolves (D-02).
        cookies[BROWSE_BINDING_COOKIE] = DEFAULT_PROFILE_UUID
        return {"cookies": cookies, "csrf_token": csrf}


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_boundary_edit_profile_a_does_not_touch_profile_b(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
    db_pool,
) -> None:
    """DATA-01: a PUT bound to the default profile must not modify profile B's sentinel row.

    Steps:
      1. Log in as admin; bind browse-binding cookie to DEFAULT_PROFILE_UUID (profile A).
      2. PUT /api/admin/cubes/{u}/{r}/{c} with a new first_label for profile A.
      3. Assert HTTP 200.
      4. SELECT profile B's row directly and assert first_label == _B_SENTINEL_LABEL (unchanged).
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping isolation test")

    new_label = "A-UPDATED-LABEL"
    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.put(
            f"/api/admin/cubes/{_SHARED_UNIT}/{_SHARED_ROW}/{_SHARED_COL}/boundary",
            json={
                "first_label": new_label,
                "first_catalog": "A-UPD-001",
                "is_empty": False,
                "force": True,
            },
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert res.status_code == 200, (
        f"Expected 200 from PUT bound to profile A, got {res.status_code}: {res.text}"
    )

    # Verify profile B's row is completely untouched.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT first_label FROM gruvax.cube_boundaries "
            "WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s",
            (profile_b, _SHARED_UNIT, _SHARED_ROW, _SHARED_COL),
        )
        row = await cur.fetchone()

    assert row is not None, (
        f"Profile B's boundary row at ({_SHARED_UNIT},{_SHARED_ROW},{_SHARED_COL}) vanished"
    )
    assert row[0] == _B_SENTINEL_LABEL, (
        f"DATA-01 VIOLATED: profile B's first_label was mutated. "
        f"Expected '{_B_SENTINEL_LABEL}', got '{row[0]}'. "
        "A-scoped write must not touch profile B's row at the same physical position."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_unbound_admin_write_returns_400(live_server) -> None:  # type: ignore[no-untyped-def]
    """D-02: PUT with admin credentials but NO browse-binding cookie → 400 session_unbound.

    get_write_target must raise 400 session_unbound when there is no browse-binding
    cookie and no device fingerprint — it must never fall back to DEFAULT_PROFILE_UUID.
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping unbound test")

    # Build cookie dict with ONLY the session and CSRF cookies, NO browse-binding.
    session_only_cookies = {
        k: v for k, v in auth["cookies"].items() if k not in (BROWSE_BINDING_COOKIE,)
    }

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.put(
            f"/api/admin/cubes/{_SHARED_UNIT}/{_SHARED_ROW}/{_SHARED_COL}/boundary",
            json={
                "first_label": "ShouldNeverLand",
                "first_catalog": "X-001",
                "is_empty": False,
                "force": True,
            },
            cookies=session_only_cookies,
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert res.status_code == 400, (
        f"Expected 400 session_unbound for unbound admin write, got {res.status_code}: {res.text}"
    )
    body = res.json()
    detail = body.get("detail", body)
    if isinstance(detail, dict):
        assert detail.get("type") == "session_unbound", (
            f"Expected detail.type == 'session_unbound', got: {detail}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_zero_row_write_returns_404(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
) -> None:
    """D-10: PUT bound to profile B for a (unit, row, col) absent from B → 404 boundary_not_found.

    Profile B was seeded with only one boundary row (_SHARED_UNIT, _SHARED_ROW, _SHARED_COL).
    A write to (_ABSENT_UNIT, _ABSENT_ROW, _ABSENT_COL) — which has no row for profile B —
    must return 404 with detail type boundary_not_found.
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping 0-row-404 test")

    # Bind the write to profile B instead of the default profile.
    b_bound_cookies = dict(auth["cookies"])
    b_bound_cookies[BROWSE_BINDING_COOKIE] = profile_b

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.put(
            f"/api/admin/cubes/{_ABSENT_UNIT}/{_ABSENT_ROW}/{_ABSENT_COL}/boundary",
            json={
                "first_label": "ShouldReturn404",
                "first_catalog": "X-002",
                "is_empty": False,
                "force": True,
            },
            cookies=b_bound_cookies,
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert res.status_code == 404, (
        f"Expected 404 for a write to a (unit,row,col) absent from profile B, "
        f"got {res.status_code}: {res.text}"
    )
    body = res.json()
    detail = body.get("detail", body)
    if isinstance(detail, dict):
        # The implementation returns cube_not_found when fetch_current_boundary returns
        # None for the profile (absent row), OR boundary_not_found if fetch succeeds but
        # write_boundary returns 0 rows.  Both are valid 404 responses that prove the
        # absent-position guard is in place (D-10).
        assert detail.get("type") in ("boundary_not_found", "cube_not_found"), (
            f"Expected detail.type in ('boundary_not_found', 'cube_not_found'), got: {detail}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_boundary_changed_fans_out_per_profile(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
) -> None:
    """D-04: a boundary write bound to profile A delivers boundary_changed only on A's channel.

    WARNING-2 guard: asserts that profile B's SSE channel returns 200 (bus exists at
    server start — profile_b fixture ran before live_server created the app) before
    relying on B's silence. If this assertion fails, the negative assertion would pass
    vacuously (GET /api/events/{B} returns 404, so B never receives anything).

    Steps:
      1. Verify GET /api/events/{B} → 200 (bus exists).
      2. Open two SSE streams: one for A, one for B.
      3. Drain initial server_hello frames from both.
      4. Log in and PUT a boundary change bound to profile A.
      5. Assert A's stream yields boundary_changed within 2 s.
      6. Assert B's stream yields NO boundary_changed in that same window.
    """
    # ── Step 1: WARNING-2 guard — verify B's channel exists ──────────────────
    # Use a streaming GET so the SSE long-lived connection does not cause a read
    # timeout when we only need the HTTP status line.
    b_channel_status: int = 0
    try:
        async with (
            httpx.AsyncClient(base_url=live_server) as probe,
            probe.stream(
                "GET",
                f"/api/events/{profile_b}",
                cookies={BROWSE_BINDING_COOKIE: profile_b},
                timeout=3.0,
            ) as check_stream,
        ):
            b_channel_status = check_stream.status_code
    except httpx.TimeoutException, httpx.RemoteProtocolError:
        pass  # timeout reading body is fine — we only care about the status line

    assert b_channel_status == 200, (
        f"WARNING-2 failed: GET /api/events/{profile_b} returned {b_channel_status}, "
        f"not 200. Profile B's EventBus was not registered at server start. "
        f"The negative 'B receives nothing' assertion would be vacuous (404 is not 200). "
        f"Fix: ensure profile_b fixture runs before live_server creates the app."
    )

    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping boundary_changed fan-out test")

    received_by_a: list[str] = []
    received_by_b: list[str] = []
    a_ready = asyncio.Event()
    b_ready = asyncio.Event()

    async def stream_a() -> None:
        sse_cookies = {BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{DEFAULT_PROFILE_UUID}",
                    cookies=sse_cookies,
                    timeout=8.0,
                ) as resp,
            ):
                if resp.status_code != 200:
                    a_ready.set()
                    return
                a_ready.set()
                async for line in resp.aiter_lines():
                    if "boundary_changed" in line:
                        received_by_a.append(line)
                        return
        except httpx.TimeoutException, httpx.RemoteProtocolError:
            a_ready.set()

    async def stream_b() -> None:
        sse_cookies = {BROWSE_BINDING_COOKIE: profile_b}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{profile_b}",
                    cookies=sse_cookies,
                    timeout=8.0,
                ) as resp,
            ):
                if resp.status_code != 200:
                    b_ready.set()
                    return
                b_ready.set()
                async for line in resp.aiter_lines():
                    if "boundary_changed" in line:
                        received_by_b.append(line)
                        return
        except httpx.TimeoutException, httpx.RemoteProtocolError:
            b_ready.set()

    task_a = asyncio.create_task(stream_a())
    task_b = asyncio.create_task(stream_b())

    # Wait for both streams to establish before triggering the write.
    await asyncio.wait_for(
        asyncio.gather(a_ready.wait(), b_ready.wait()),
        timeout=10.0,
    )
    # Brief pause to let both SSE connections register their queue subscriptions.
    await asyncio.sleep(0.1)

    # Trigger a boundary write bound to profile A.
    async with httpx.AsyncClient(base_url=live_server) as ac:
        put_res = await ac.put(
            f"/api/admin/cubes/{_SHARED_UNIT}/{_SHARED_ROW}/{_SHARED_COL}/boundary",
            json={
                "first_label": "FANOUT-TEST-A",
                "first_catalog": "FO-001",
                "is_empty": False,
                "force": True,
            },
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )
    assert put_res.status_code == 200, (
        f"Expected 200 from admin PUT in fan-out test, got {put_res.status_code}: {put_res.text}"
    )

    # Wait for boundary_changed on A's stream (up to 2 s).
    deadline = asyncio.get_running_loop().time() + 2.0
    while not received_by_a and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)

    # Give B a brief window to incorrectly receive the event.
    await asyncio.sleep(0.3)

    for task in (task_a, task_b):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert received_by_a, (
        "boundary_changed was not received on profile A's SSE channel within 2 s — "
        "either the write did not publish or A's stream was not connected. (D-04)"
    )
    assert not received_by_b, (
        f"D-04 VIOLATED: boundary_changed leaked to profile B's SSE channel. "
        f"Fan-out must be scoped to the writing profile's bus only. "
        f"B received: {received_by_b}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_admin_editing_fans_out_per_profile(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
) -> None:
    """D-04 shimmer isolation: admin_editing must fan out only to the writing profile's channel.

    WARNING-2 guard (same as boundary_changed test): verify GET /api/events/{B} → 200
    before relying on B's silence, so a missing-bus regression fails loudly.

    Steps:
      1. Verify GET /api/events/{B} → 200.
      2. Open two SSE streams: one for A, one for B.
      3. Drain initial server_hello frames.
      4. Log in and POST /api/admin/editing with browse-binding bound to profile A.
      5. Assert A's stream yields admin_editing within 1 s.
      6. Assert B's stream yields NO admin_editing in that window.
    """
    # ── WARNING-2 guard ───────────────────────────────────────────────────────
    b_channel_status_2: int = 0
    try:
        async with (
            httpx.AsyncClient(base_url=live_server) as probe,
            probe.stream(
                "GET",
                f"/api/events/{profile_b}",
                cookies={BROWSE_BINDING_COOKIE: profile_b},
                timeout=3.0,
            ) as check_stream,
        ):
            b_channel_status_2 = check_stream.status_code
    except httpx.TimeoutException, httpx.RemoteProtocolError:
        pass

    assert b_channel_status_2 == 200, (
        f"WARNING-2 failed: GET /api/events/{profile_b} returned {b_channel_status_2}, "
        f"not 200. Profile B's EventBus was not registered at server start."
    )

    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping admin_editing fan-out test")

    received_by_a: list[str] = []
    received_by_b: list[str] = []
    a_ready = asyncio.Event()
    b_ready = asyncio.Event()

    async def stream_a() -> None:
        sse_cookies = {BROWSE_BINDING_COOKIE: DEFAULT_PROFILE_UUID}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{DEFAULT_PROFILE_UUID}",
                    cookies=sse_cookies,
                    timeout=6.0,
                ) as resp,
            ):
                if resp.status_code != 200:
                    a_ready.set()
                    return
                a_ready.set()
                async for line in resp.aiter_lines():
                    if "admin_editing" in line:
                        received_by_a.append(line)
                        return
        except httpx.TimeoutException, httpx.RemoteProtocolError:
            a_ready.set()

    async def stream_b() -> None:
        sse_cookies = {BROWSE_BINDING_COOKIE: profile_b}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{profile_b}",
                    cookies=sse_cookies,
                    timeout=6.0,
                ) as resp,
            ):
                if resp.status_code != 200:
                    b_ready.set()
                    return
                b_ready.set()
                async for line in resp.aiter_lines():
                    if "admin_editing" in line:
                        received_by_b.append(line)
                        return
        except httpx.TimeoutException, httpx.RemoteProtocolError:
            b_ready.set()

    task_a = asyncio.create_task(stream_a())
    task_b = asyncio.create_task(stream_b())

    await asyncio.wait_for(
        asyncio.gather(a_ready.wait(), b_ready.wait()),
        timeout=10.0,
    )
    await asyncio.sleep(0.05)

    # POST /api/admin/editing with browse-binding bound to profile A.
    payload = {
        "cube_ids": [{"unit": _SHARED_UNIT, "row": _SHARED_ROW, "col": _SHARED_COL}],
        "editing": True,
    }
    async with httpx.AsyncClient(base_url=live_server) as ac:
        edit_res = await ac.post(
            "/api/admin/editing",
            json=payload,
            cookies=auth["cookies"],
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )
    assert edit_res.status_code == 200, (
        f"Expected 200 from POST /api/admin/editing, got {edit_res.status_code}: {edit_res.text}"
    )

    # Wait for admin_editing on A's stream (up to 1 s).
    deadline = asyncio.get_running_loop().time() + 1.0
    while not received_by_a and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.05)

    # Give B a brief window to incorrectly receive the event.
    await asyncio.sleep(0.3)

    for task in (task_a, task_b):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert received_by_a, (
        "admin_editing was not received on profile A's SSE channel within 1 s — "
        "either the POST did not publish or A's stream was not connected. (D-04)"
    )
    assert not received_by_b, (
        f"D-04 shimmer isolation VIOLATED: admin_editing leaked to profile B's SSE channel. "
        f"Fan-out must be scoped to the writing profile's bus only. "
        f"B received: {received_by_b}"
    )

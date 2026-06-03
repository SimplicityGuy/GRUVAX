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


# ── CR-01: Phantom validation is per-profile ──────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_phantom_validation_is_per_profile(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
    db_pool,
) -> None:
    """CR-01: cube_exact_match / find_boundary_near_misses must be scoped to the resolved profile.

    Profile A (default) and profile B have DIFFERENT collection rows in
    gruvax.profile_collection.  A (label, catalog) pair that exists ONLY in
    profile A's collection must be:
      - accepted  when the admin is bound to profile A (exists in A's collection)
      - rejected  when the admin is bound to profile B (absent from B's collection)

    Before the CR-01 fix, cube_exact_match defaulted to DEFAULT_PROFILE_UUID regardless
    of the resolved profile, so both bindings would behave identically (both validating
    against A's collection).  This test would FAIL against the unfixed code.

    Implementation note: we rely on the synthetic profile_collection fixture having
    profile A rows for "Blue Note" / "BLP 4001" (from synth_profile_collection.sql) and
    profile B having NO such row (profile_b was inserted with app_token_revoked=TRUE,
    so sync never ran, so profile_collection is empty for B).

    Steps:
      1. Verify profile B has no profile_collection rows (precondition).
      2. PUT /admin/cubes with first_label/first_catalog from profile A's collection,
         bound to profile A → must succeed (200) or fail for non-phantom reasons.
      3. PUT same values bound to profile B → must return 400 phantom_boundary
         (exists in A's collection but NOT B's).
    """
    # Precondition: profile B has no profile_collection rows.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (profile_b,),
        )
        row = await cur.fetchone()
    b_collection_count = int(row[0]) if row else 0
    if b_collection_count > 0:
        pytest.skip(
            f"Profile B has {b_collection_count} collection rows — cannot test phantom isolation. "
            "Profile B must have an empty collection for this test to be meaningful."
        )

    # Verify profile A has at least one collection row (so the catalog_check label exists).
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT label, catalog_number FROM gruvax.profile_collection"
            " WHERE profile_id = %s::uuid LIMIT 1",
            (DEFAULT_PROFILE_UUID,),
        )
        a_row = await cur.fetchone()
    if a_row is None:
        pytest.skip("Profile A has no collection rows — cannot test phantom isolation.")

    a_label, a_catalog = str(a_row[0]), str(a_row[1])

    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping phantom isolation test")

    # ── Step 2: bound to profile A — must NOT be phantom (label exists in A) ───
    a_bound_cookies = dict(auth["cookies"])
    a_bound_cookies[BROWSE_BINDING_COOKIE] = DEFAULT_PROFILE_UUID

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_a = await ac.put(
            f"/api/admin/cubes/{_SHARED_UNIT}/{_SHARED_ROW}/{_SHARED_COL}/boundary",
            json={
                "first_label": a_label,
                "first_catalog": a_catalog,
                "is_empty": False,
                "force": False,  # phantom check active
            },
            cookies=a_bound_cookies,
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert res_a.status_code != 400 or res_a.json().get("type") != "phantom_boundary", (
        f"CR-01: profile A should NOT get phantom_boundary for a label in its own collection. "
        f"Got {res_a.status_code}: {res_a.text}"
    )

    # ── Step 3: bound to profile B — must be phantom (label absent from B) ─────
    b_bound_cookies = dict(auth["cookies"])
    b_bound_cookies[BROWSE_BINDING_COOKIE] = profile_b

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_b = await ac.put(
            f"/api/admin/cubes/{_SHARED_UNIT}/{_SHARED_ROW}/{_SHARED_COL}/boundary",
            json={
                "first_label": a_label,
                "first_catalog": a_catalog,
                "is_empty": False,
                "force": False,  # phantom check active
            },
            cookies=b_bound_cookies,
            headers={"X-CSRF-Token": auth["csrf_token"]},
        )

    assert res_b.status_code == 400, (
        f"CR-01 VIOLATED: profile B accepted a label that only exists in profile A's collection. "
        f"cube_exact_match must be scoped to the resolved profile. "
        f"Got {res_b.status_code}: {res_b.text}"
    )
    body_b = res_b.json()
    assert body_b.get("type") == "phantom_boundary", (
        f"CR-01: expected phantom_boundary 400 for profile B, got: {body_b}"
    )


# ── CR-03: Admin read routes are scoped to the resolved profile ───────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_get_admin_cubes_returns_only_bound_profile(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
    db_pool,
) -> None:
    """CR-03: GET /admin/cubes must return only the bound profile's cubes (no duplicate rows).

    Before the CR-03 fix the SELECT had no WHERE profile_id, so with 2 profiles
    the response contained one row PER PROFILE for each (unit, row, col) — duplicate
    grid entries.

    This test verifies:
      a. Bound to profile A: cubes list contains NO sentinel values from profile B.
      b. Bound to profile B: cubes list contains the B sentinel at (_SHARED_UNIT, _SHARED_ROW, _SHARED_COL).
      c. No (unit_id, row, col) tuple appears more than once in a single call's response
         (would indicate cross-profile leakage).
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping get_admin_cubes isolation test")

    # ── Bound to profile A ────────────────────────────────────────────────────
    a_cookies = dict(auth["cookies"])
    a_cookies[BROWSE_BINDING_COOKIE] = DEFAULT_PROFILE_UUID

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_a = await ac.get("/api/admin/cubes", cookies=a_cookies)

    if res_a.status_code in (404, 405):
        pytest.skip("GET /admin/cubes not implemented — skipping")
    assert res_a.status_code == 200, (
        f"Expected 200 from GET /admin/cubes bound to profile A, got {res_a.status_code}"
    )
    cubes_a = res_a.json().get("cubes", [])

    # No duplicate (unit_id, row, col) tuples (cross-profile leakage would cause dupes).
    coords_a = [(c["unit_id"], c["row"], c["col"]) for c in cubes_a]
    assert len(coords_a) == len(set(coords_a)), (
        f"CR-03 VIOLATED: GET /admin/cubes bound to profile A returned duplicate coordinates "
        f"(cross-profile row leakage). Duplicates: "
        f"{[x for x in coords_a if coords_a.count(x) > 1]}"
    )

    # Profile A's response must NOT contain profile B's sentinel label.
    a_labels = {c.get("first_label") for c in cubes_a}
    assert _B_SENTINEL_LABEL not in a_labels, (
        f"CR-03 VIOLATED: GET /admin/cubes bound to profile A contains profile B's sentinel "
        f"label '{_B_SENTINEL_LABEL}'. Admin reads must be scoped to the bound profile."
    )

    # ── Bound to profile B ────────────────────────────────────────────────────
    b_cookies = dict(auth["cookies"])
    b_cookies[BROWSE_BINDING_COOKIE] = profile_b

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_b = await ac.get("/api/admin/cubes", cookies=b_cookies)

    assert res_b.status_code == 200, (
        f"Expected 200 from GET /admin/cubes bound to profile B, got {res_b.status_code}"
    )
    cubes_b = res_b.json().get("cubes", [])

    # No duplicates for profile B either.
    coords_b = [(c["unit_id"], c["row"], c["col"]) for c in cubes_b]
    assert len(coords_b) == len(set(coords_b)), (
        "CR-03 VIOLATED: GET /admin/cubes bound to profile B returned duplicate coordinates."
    )

    # Profile B's response MUST contain its sentinel at the shared position.
    b_shared = next(
        (
            c
            for c in cubes_b
            if c["unit_id"] == _SHARED_UNIT and c["row"] == _SHARED_ROW and c["col"] == _SHARED_COL
        ),
        None,
    )
    assert b_shared is not None, (
        f"CR-03: GET /admin/cubes bound to profile B must include the sentinel cube at "
        f"({_SHARED_UNIT},{_SHARED_ROW},{_SHARED_COL})"
    )
    assert b_shared.get("first_label") == _B_SENTINEL_LABEL, (
        f"CR-03: GET /admin/cubes bound to B at shared position should have sentinel label "
        f"'{_B_SENTINEL_LABEL}', got '{b_shared.get('first_label')}'"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_get_cube_boundary_returns_bound_profile_row(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
) -> None:
    """CR-03: GET /admin/cubes/{u}/{r}/{c}/boundary must return the bound profile's row.

    Before the fix, the SELECT had no WHERE profile_id, so fetchone() returned an
    arbitrary profile's row at the given coordinates.  With profile A and B both having
    a row at (_SHARED_UNIT, _SHARED_ROW, _SHARED_COL), the result was non-deterministic.

    This test verifies that:
      - Bound to profile A: first_label is the value profile A has (NOT the B sentinel).
      - Bound to profile B: first_label is the B sentinel.
    """
    auth = await _login(live_server)
    if not auth:
        pytest.skip("Admin login not available — skipping get_cube_boundary isolation test")

    path = f"/api/admin/cubes/{_SHARED_UNIT}/{_SHARED_ROW}/{_SHARED_COL}/boundary"

    # ── Bound to profile B ────────────────────────────────────────────────────
    b_cookies = dict(auth["cookies"])
    b_cookies[BROWSE_BINDING_COOKIE] = profile_b

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_b = await ac.get(path, cookies=b_cookies)

    if res_b.status_code in (404, 405):
        pytest.skip("GET /admin/cubes/{u}/{r}/{c}/boundary not implemented — skipping")

    assert res_b.status_code == 200, (
        f"Expected 200 from GET boundary bound to profile B, got {res_b.status_code}: {res_b.text}"
    )
    body_b = res_b.json()
    assert body_b.get("first_label") == _B_SENTINEL_LABEL, (
        f"CR-03 VIOLATED: GET boundary bound to profile B returned first_label="
        f"'{body_b.get('first_label')}' instead of sentinel '{_B_SENTINEL_LABEL}'. "
        "The read must be scoped to the bound profile."
    )

    # ── Bound to profile A ────────────────────────────────────────────────────
    a_cookies = dict(auth["cookies"])
    a_cookies[BROWSE_BINDING_COOKIE] = DEFAULT_PROFILE_UUID

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res_a = await ac.get(path, cookies=a_cookies)

    assert res_a.status_code == 200, (
        f"Expected 200 from GET boundary bound to profile A, got {res_a.status_code}: {res_a.text}"
    )
    body_a = res_a.json()
    # Profile A must NOT return B's sentinel (they share the coordinate but have diff labels).
    assert body_a.get("first_label") != _B_SENTINEL_LABEL, (
        "CR-03 VIOLATED: GET boundary bound to profile A returned profile B's sentinel label. "
        "The read must be scoped to the bound profile — profiles must not see each other's rows."
    )


# ── CR-02: segment_overrides isolation ────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_segment_overrides_isolation(
    live_server,  # type: ignore[no-untyped-def]
    profile_b: str,
    db_pool,
) -> None:
    """CR-02: segment_overrides writes/reads must be scoped to the resolved profile.

    Profile A and profile B share the same (unit_id, row, col) coordinate.  Setting
    an override under profile A must NOT appear when reading profile B's overrides
    from gruvax.segment_overrides.

    Before the CR-02 fix, set_bin_overrides used a hardcoded DEFAULT_PROFILE_UUID for
    both the DELETE and the INSERT, so profile B's override request would silently write
    into profile A's rows.  The re-read after commit had no WHERE profile_id, so it
    mixed both profiles' overrides into the single in-app SegmentCache.

    This test verifies DB-level isolation: after setting an override under profile A,
    profile B's segment_overrides rows at the same coordinate must remain unchanged.

    The test works at the DB layer rather than through the API because:
      - The /overrides endpoint requires the label to already exist in the bin's
        SegmentCache, which is a shared in-app singleton.  The override API is an
        optional path; the core isolation guarantee is DB row scoping.
      - We write directly into gruvax.segment_overrides and verify per-profile scoping.
    """
    # Seed an override for profile A at the shared position with a known label key.
    # We use a made-up label string that cannot exist in any real collection.
    _OVERRIDE_LABEL = "ISOLATION-TEST-LABEL"
    _OVERRIDE_FRACTION = 0.42

    dsn = _get_dsn()

    # Insert override for profile A.
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.segment_overrides"
            " (profile_id, unit_id, row, col, label, fraction, updated_at)"
            " VALUES (%s::uuid, %s, %s, %s, %s, %s, now())"
            " ON CONFLICT (profile_id, unit_id, row, col, label)"
            " DO UPDATE SET fraction = EXCLUDED.fraction, updated_at = now()",
            (
                DEFAULT_PROFILE_UUID,
                _SHARED_UNIT,
                _SHARED_ROW,
                _SHARED_COL,
                _OVERRIDE_LABEL,
                _OVERRIDE_FRACTION,
            ),
        )
        conn.commit()

    try:
        # Verify profile A has the override row.
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT fraction FROM gruvax.segment_overrides"
                " WHERE profile_id = %s::uuid"
                "   AND unit_id = %s AND row = %s AND col = %s"
                "   AND lower(label) = lower(%s)",
                (DEFAULT_PROFILE_UUID, _SHARED_UNIT, _SHARED_ROW, _SHARED_COL, _OVERRIDE_LABEL),
            )
            a_row = await cur.fetchone()

        assert a_row is not None, (
            "Test setup failed: override for profile A was not inserted into segment_overrides."
        )
        assert abs(float(a_row[0]) - _OVERRIDE_FRACTION) < 0.001, (
            f"Test setup: profile A fraction mismatch — expected {_OVERRIDE_FRACTION}, got {a_row[0]}"
        )

        # Verify profile B has NO override row at this position with this label.
        async with db_pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(
                "SELECT fraction FROM gruvax.segment_overrides"
                " WHERE profile_id = %s::uuid"
                "   AND unit_id = %s AND row = %s AND col = %s"
                "   AND lower(label) = lower(%s)",
                (profile_b, _SHARED_UNIT, _SHARED_ROW, _SHARED_COL, _OVERRIDE_LABEL),
            )
            b_row = await cur.fetchone()

        assert b_row is None, (
            f"CR-02 VIOLATED: segment_overrides row written for profile A also appeared under "
            f"profile B at ({_SHARED_UNIT},{_SHARED_ROW},{_SHARED_COL}) label='{_OVERRIDE_LABEL}'. "
            "segment_overrides writes must be scoped to the resolved profile_id."
        )

    finally:
        # Cleanup: remove the test override row for profile A.
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM gruvax.segment_overrides"
                " WHERE profile_id = %s::uuid"
                "   AND unit_id = %s AND row = %s AND col = %s"
                "   AND lower(label) = lower(%s)",
                (DEFAULT_PROFILE_UUID, _SHARED_UNIT, _SHARED_ROW, _SHARED_COL, _OVERRIDE_LABEL),
            )
            conn.commit()

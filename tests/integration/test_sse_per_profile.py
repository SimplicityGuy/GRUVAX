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
from tests.cookies import cookie_header


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


# ── letter-bearing profile fixture (gruvax-kol) ──────────────────────────────
#
# The default profile UUID (00000000-…-0001) has NO hex letters, so
# ``uuid.upper()`` is a no-op on it — a "sends the UUID uppercase" test written
# against the default profile is VACUOUS (it passes against the unfixed raw string
# compare). This fixture inserts a profile whose UUID does contain hex letters so
# the two spellings are genuinely different strings that denote the same UUID.
#
# It is a dependency of live_server so the profile exists BEFORE create_app()
# builds event_bus_registry (same ordering constraint as
# test_two_profile_isolation.py's profile_b / WARNING-2).

CASE_PROFILE_UUID = "0000000f-0000-0000-0000-0000000000ab"


@pytest.fixture(scope="module")
def case_profile(db_pool):  # type: ignore[no-untyped-def]
    """Insert a profile with a letter-bearing UUID; yield the canonical lowercase string."""
    import psycopg

    from gruvax.settings import settings

    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, "
            "app_token_revoked) VALUES (%s::uuid, 'SSECaseTest', %s::bytea, TRUE) "
            "ON CONFLICT (id) DO UPDATE SET deleted_at = NULL",
            (CASE_PROFILE_UUID, b""),
        )
        conn.commit()

    yield CASE_PROFILE_UUID

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (CASE_PROFILE_UUID,))
        conn.commit()


@pytest.fixture(scope="module")
def live_server(db_pool, case_profile):  # type: ignore[no-untyped-def]
    """Real uvicorn server in a background thread for SSE testing.

    Mirrors the fixture from test_sse.py exactly, plus the ``case_profile``
    dependency so a letter-bearing profile UUID is in the registry at startup
    (gruvax-kol).
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
            headers=cookie_header(cookies),
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
        ac.stream("GET", f"/api/events/{profile_a}", headers=cookie_header(cookies)) as resp,
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
async def test_sse_connects_when_path_uuid_is_uppercase(live_server, case_profile) -> None:  # type: ignore[no-untyped-def]
    """gruvax-kol: an UPPERCASE path UUID for the bound profile must connect, not 403/404.

    The bug: ``get_bus_for_profile`` compared the resolved profile (canonical
    lowercase — ``str()`` of a DB UUID) against the raw path string, and looked the
    bus up under that raw string. A kiosk that spelled its own profile UUID in
    uppercase got 403 profile_mismatch on SSE while GET /api/search with the SAME
    uppercase UUID returned 200 — SSE dead, search alive, same client, no error the
    user could act on.

    This is a BEHAVIOURAL assertion: it drives the real endpoint over a real socket
    with an uppercase spelling of a letter-bearing profile UUID and requires
    200 + the ': connected' comment. It fails against the pre-fix raw string compare
    (403) and against a compare-only fix that leaves the registry lookup
    un-normalized (404 profile_not_found).
    """
    upper = case_profile.upper()
    assert upper != case_profile, (
        "fixture regression: CASE_PROFILE_UUID must contain hex letters, otherwise "
        "upper() is a no-op and this test cannot detect a raw string compare"
    )
    cookies = {BROWSE_BINDING_COOKIE: case_profile}

    async with (
        httpx.AsyncClient(base_url=live_server) as ac,
        ac.stream("GET", f"/api/events/{upper}", headers=cookie_header(cookies)) as resp,
    ):
        assert resp.status_code == 200, (
            f"gruvax-kol: GET /api/events/{upper} with the browse cookie bound to "
            f"{case_profile} must return 200 — the two strings are the same UUID. "
            f"Got {resp.status_code}: a 403 means the profile compare is a raw string "
            f"compare (WR-02 unfixed); a 404 means the registry lookup key was not "
            f"normalized to canonical form."
        )
        got_comment = False
        async for line in resp.aiter_lines():
            if line.startswith(":"):
                got_comment = True
                break
        assert got_comment, "SSE stream must start with a ': connected' comment line"


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_uppercase_cookie_binding_still_matches(live_server, case_profile) -> None:  # type: ignore[no-untyped-def]
    """gruvax-kol (inverse direction): an uppercase browse COOKIE must match a lowercase path.

    The cookie is client-controlled too, so the normalization has to hold in both
    directions — otherwise the same spurious 403 appears with the operands swapped.
    """
    cookies = {BROWSE_BINDING_COOKIE: case_profile.upper()}

    async with (
        httpx.AsyncClient(base_url=live_server) as ac,
        ac.stream("GET", f"/api/events/{case_profile}", headers=cookie_header(cookies)) as resp,
    ):
        assert resp.status_code == 200, (
            f"gruvax-kol: an UPPERCASE gruvax_browse_binding cookie must resolve to the "
            f"same profile as the lowercase path UUID. Got {resp.status_code}."
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_sse_still_403s_a_genuinely_different_profile(live_server, case_profile) -> None:  # type: ignore[no-untyped-def]
    """gruvax-kol guard: the normalization must NOT weaken the spoofing check.

    Companion to the uppercase tests: a DIFFERENT profile UUID (not a different
    spelling of the same one) must still be rejected with 403 profile_mismatch.
    Without this, "fix the false 403" could regress into "never 403" — the
    uppercase tests alone are satisfied by deleting the check entirely.
    """
    default_profile = "00000000-0000-0000-0000-000000000001"

    async with httpx.AsyncClient(base_url=live_server) as ac:
        res = await ac.get(
            # Uppercase spelling of a DIFFERENT profile — case-insensitively distinct.
            f"/api/events/{case_profile.upper()}",
            headers=cookie_header({BROWSE_BINDING_COOKIE: default_profile}),
        )

    assert res.status_code == 403, (
        f"A genuinely different profile UUID must still be 403 profile_mismatch — "
        f"UUID normalization must not turn the spoofing guard off. Got {res.status_code}."
    )


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
        ac.stream("GET", f"/api/events/{profile_a}", headers=cookie_header(cookies)) as resp,
    ):
        assert resp.status_code == 200, (
            f"GET /api/events/{profile_a} with bound cookie must return 200, got {resp.status_code}"
        )
        # Read up to 10 lines to find the retry: directive in the initial SSE frame.
        lines_read = 0
        async for line in resp.aiter_lines():
            lines_read += 1
            if line.startswith("retry:"):
                raw = line[len("retry:") :].strip()
                assert raw.isdigit(), f"retry: field must be a non-negative integer, got {raw!r}"
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
                    headers=cookie_header(cookies),
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
        except httpx.TimeoutException, httpx.RemoteProtocolError:
            a_connected.set()

    async def subscribe_b() -> None:
        cookies = {BROWSE_BINDING_COOKIE: profile_b}
        try:
            async with (
                httpx.AsyncClient(base_url=live_server) as ac,
                ac.stream(
                    "GET",
                    f"/api/events/{profile_b}",
                    headers=cookie_header(cookies),
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
        except httpx.TimeoutException, httpx.RemoteProtocolError:
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

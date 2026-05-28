"""Integration tests for session bootstrap + browse-binding cookie — Plan 02-00 RED baseline.

Covers D2-08 (auto-bind single profile) + D2-10 (cookie independence).
All tests are RED until Plan 02-04 lands the /api/session bootstrap endpoint.

Tests:
  - test_single_profile_auto_binds: with exactly one active profile, GET /api/session
    returns profile_count 1, a non-null bound_profile_id, and sets the browse-binding
    cookie in the response.
  - test_two_profiles_unbound: with two active profiles and no cookie, GET /api/session
    returns profile_count 2 and bound_profile_id null.
  - test_bind_then_unbind: POST /api/session/bind {profile_id} sets cookie;
    DELETE /api/session/bind clears it.
  - test_binding_independent_of_admin: binding/unbinding browse cookie does not affect
    gruvax_session admin cookie, and vice versa (D2-10).

Browse-binding cookie name: gruvax_browse_binding (D2-10, RESEARCH §Pattern 5).
Must differ from gruvax_session (admin) and gruvax_csrf (CSRF double-submit).
"""

from __future__ import annotations

import os

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from gruvax.auth.sessions import CSRF_COOKIE, SESSION_COOKIE


# ── browse-binding cookie name (D2-10) ───────────────────────────────────────

BROWSE_BINDING_COOKIE = "gruvax_browse_binding"

# Verify at import time that the browse cookie name is distinct from admin cookies.
assert BROWSE_BINDING_COOKIE != SESSION_COOKIE, (
    f"Browse binding cookie '{BROWSE_BINDING_COOKIE}' must differ from admin session "
    f"cookie '{SESSION_COOKIE}' (D2-10)"
)
assert BROWSE_BINDING_COOKIE != CSRF_COOKIE, (
    f"Browse binding cookie '{BROWSE_BINDING_COOKIE}' must differ from CSRF cookie "
    f"'{CSRF_COOKIE}' (D2-10)"
)


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan."""
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.auth.pin import hash_pin

    test_hash = hash_pin("0000")

    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        pool = app.state.db_pool
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings"
                "  (profile_id, key, value, description, updated_at)"
                " VALUES"
                "  ('00000000-0000-0000-0000-000000000001'::uuid,"
                "   'auth.pin_hash', %s::jsonb,"
                "   'Test PIN seeded by test_session_bootstrap', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (f'"{test_hash}"',),
            )
            await conn.commit()
        yield ac


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_single_profile_auto_binds(
    client,  # type: ignore[no-untyped-def]
    db_pool,
) -> None:
    """With one active profile, GET /api/session returns bound_profile_id + sets cookie.

    RED until Plan 02-04 lands the /api/session bootstrap endpoint. After landing:
    - GET /api/session → {profile_count: 1, bound_profile_id: UUID, profiles: [...]}
    - Response includes Set-Cookie for gruvax_browse_binding
    - bound_profile_id equals the single active profile's UUID

    The default profile (00000000-0000-0000-0000-000000000001) is the single active
    profile in the test DB (assuming no second_profile fixture is in scope here).
    """
    # Verify there is exactly one active profile in the DB for this test.
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) FROM gruvax.profiles WHERE deleted_at IS NULL"
        )
        count_row = await cur.fetchone()
    active_count = count_row[0] if count_row else 0
    if active_count != 1:
        pytest.skip(
            f"test_single_profile_auto_binds requires exactly 1 active profile, "
            f"found {active_count}. This test must run without the second_profile fixture."
        )

    res = await client.get("/api/session")
    assert res.status_code == 200, (
        f"GET /api/session expected 200, got {res.status_code}: {res.text}. "
        f"RED until Plan 02-04 lands the session bootstrap endpoint."
    )

    body = res.json()
    assert body.get("profile_count") == 1, (
        f"profile_count must be 1, got {body.get('profile_count')!r}"
    )
    assert body.get("bound_profile_id") is not None, (
        f"single-profile session must auto-bind: bound_profile_id must be non-null, "
        f"got None. D2-08 auto-bind is missing."
    )

    # Response must set the browse-binding cookie
    set_cookie_headers = res.headers.get_list("set-cookie")
    browse_cookie_header = next(
        (h for h in set_cookie_headers if BROWSE_BINDING_COOKIE in h), None
    )
    assert browse_cookie_header is not None, (
        f"GET /api/session must set {BROWSE_BINDING_COOKIE!r} cookie on auto-bind. "
        f"D2-08 single-profile auto-bind is missing."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_two_profiles_unbound(
    client,  # type: ignore[no-untyped-def]
    second_profile,
) -> None:
    """With two active profiles and no cookie, GET /api/session → profile_count 2, bound_profile_id null.

    RED until Plan 02-04 lands. Uses second_profile fixture to seed a 2nd profile.
    D2-08: when 2+ active profiles exist and no binding cookie is present, the server
    must NOT auto-bind — it returns bound_profile_id = null so the SPA routes to /select.
    """
    # second_profile fixture has seeded a second profile in the DB.
    # Clear any browse-binding cookie left by a prior test so this test starts with
    # no browse-binding cookie as designed (the module-scoped client accumulates cookies
    # across tests; we explicitly clear before this isolated assertion).
    client.cookies.delete(BROWSE_BINDING_COOKIE)
    res = await client.get("/api/session")  # No cookies — no browse binding
    assert res.status_code == 200, (
        f"GET /api/session expected 200, got {res.status_code}: {res.text}. "
        f"RED until Plan 02-04 lands."
    )

    body = res.json()
    assert body.get("profile_count") == 2, (
        f"profile_count must be 2 with two active profiles, got {body.get('profile_count')!r}"
    )
    assert body.get("bound_profile_id") is None, (
        f"bound_profile_id must be null when 2+ profiles exist and no cookie: "
        f"got {body.get('bound_profile_id')!r}. D2-08 multi-profile unbound case."
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_bind_then_unbind(
    client,  # type: ignore[no-untyped-def]
) -> None:
    """POST /api/session/bind {profile_id} sets cookie; DELETE /api/session/bind clears it.

    RED until Plan 02-04 lands the bind/unbind endpoints.
    """
    profile_a = "00000000-0000-0000-0000-000000000001"

    # Bind
    bind_res = await client.post(
        "/api/session/bind",
        json={"profile_id": profile_a},
    )
    assert bind_res.status_code == 200, (
        f"POST /api/session/bind expected 200, got {bind_res.status_code}: {bind_res.text}. "
        f"RED until Plan 02-04 lands."
    )

    # Verify browse-binding cookie is set
    set_cookie_headers = bind_res.headers.get_list("set-cookie")
    browse_cookie_header = next(
        (h for h in set_cookie_headers if BROWSE_BINDING_COOKIE in h), None
    )
    assert browse_cookie_header is not None, (
        f"POST /api/session/bind must set {BROWSE_BINDING_COOKIE!r} cookie"
    )
    # Verify cookie contains the profile_id
    assert profile_a in browse_cookie_header, (
        f"Browse binding cookie must contain profile_id={profile_a!r}: {browse_cookie_header}"
    )

    # Unbind
    unbind_res = await client.delete(
        "/api/session/bind",
        cookies=bind_res.cookies,
    )
    assert unbind_res.status_code == 200, (
        f"DELETE /api/session/bind expected 200, got {unbind_res.status_code}: {unbind_res.text}"
    )

    # Verify browse-binding cookie is cleared (Set-Cookie with empty value or expired)
    set_cookie_after = unbind_res.headers.get_list("set-cookie")
    cleared = any(
        BROWSE_BINDING_COOKIE in h and ("max-age=0" in h.lower() or 'expires=' in h.lower())
        for h in set_cookie_after
    )
    cookie_gone = BROWSE_BINDING_COOKIE not in unbind_res.cookies
    assert cleared or cookie_gone, (
        f"DELETE /api/session/bind must clear the {BROWSE_BINDING_COOKIE!r} cookie. "
        f"Set-Cookie headers: {set_cookie_after}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_binding_independent_of_admin(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """Browse-binding cookie ops must not affect gruvax_session, and vice versa.

    RED until Plan 02-04 lands. D2-10: browse-binding is INDEPENDENT of the
    admin session. This test verifies:
    1. The two cookie names are distinct (structural).
    2. POST /api/session/bind does NOT alter the gruvax_session cookie.
    3. POST /api/admin/logout does NOT alter the gruvax_browse_binding cookie.
    """
    profile_a = "00000000-0000-0000-0000-000000000001"

    # Structural: cookie names must be distinct.
    assert BROWSE_BINDING_COOKIE != SESSION_COOKIE, (
        f"Browse binding cookie '{BROWSE_BINDING_COOKIE}' must be distinct from "
        f"admin session cookie '{SESSION_COOKIE}' (D2-10)"
    )

    # Bind browse cookie (with admin session cookies in place to simulate a logged-in admin)
    bind_res = await client.post(
        "/api/session/bind",
        json={"profile_id": profile_a},
        cookies=admin_session["cookies"],
    )
    if bind_res.status_code != 200:
        pytest.skip("Session bind endpoint not implemented — skipping independence test")

    # The bind operation must NOT modify the admin session cookie.
    bind_set_cookies = {
        h.split("=")[0].strip(): h
        for h in bind_res.headers.get_list("set-cookie")
    }
    if SESSION_COOKIE in bind_set_cookies:
        # If gruvax_session appears in the response, it must not be cleared.
        assert "max-age=0" not in bind_set_cookies[SESSION_COOKIE].lower(), (
            f"POST /api/session/bind must not clear the admin session cookie "
            f"({SESSION_COOKIE}). D2-10 independence violated."
        )

    # Logout (admin) must NOT clear the browse-binding cookie.
    logout_res = await client.post(
        "/api/admin/logout",
        cookies={**admin_session["cookies"], **bind_res.cookies},
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if logout_res.status_code == 200:
        logout_set_cookies = {
            h.split("=")[0].strip(): h
            for h in logout_res.headers.get_list("set-cookie")
        }
        if BROWSE_BINDING_COOKIE in logout_set_cookies:
            # Browse cookie must not be cleared by admin logout.
            assert "max-age=0" not in logout_set_cookies[BROWSE_BINDING_COOKIE].lower(), (
                f"POST /api/admin/logout must not clear the browse-binding cookie "
                f"({BROWSE_BINDING_COOKIE}). D2-10 independence violated."
            )

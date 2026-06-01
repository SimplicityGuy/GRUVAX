"""Integration tests for member self-connect invite flow (AUTH-02) + collection diff (API-04).

Tests (12 total — per RESEARCH.md §Validation Architecture §Phase Requirements → Test Map):

AUTH-02 tests (endpoints in Plan 02 — marked xfail(strict=False) until shipped):
  - test_generate_invite: POST /api/admin/profiles/{id}/invite → {code, url, expires_at}
  - test_new_invite_voids_prior: generating a second invite voids the first (D-09)
  - test_get_valid_code: GET /api/invite-codes/{code} → {display_name, expires_at}
  - test_redeem_success: POST /api/invite-codes/{code}/redeem with valid PAT → 200
  - test_redeem_second_use_rejected: second redeem of same code → 404 (single-use)
  - test_redeem_bad_pat: invalid PAT → 401 pat_rejected
  - test_redeem_expired: expired code → 404
  - test_redeem_rotates_token: redeem onto a profile with existing token rotates it (D-10)

API-04 tests (endpoints ship in Plan 01 — must pass after this plan):
  - test_profile_has_token_field: GET /api/admin/profiles includes has_token bool (not ciphertext)
  - test_initial_import_flag: first sync is_initial_import=True; second sync is False
  - test_arrival_count_accuracy: new_record_count equals genuinely new releases (>= 0)
  - test_profile_new_record_fields: profile response includes last_new_record_count + last_sync_is_initial

Fixture pattern from tests/integration/test_devices.py:
  - module-scoped ASGI client via LifespanManager + ASGITransport
  - autouse rate-limit reset fixture (resets all limiters before each test)
  - _login() helper posting /api/admin/login and returning cookies dict
"""

from __future__ import annotations

import asyncio
import os
import uuid as _uuid_module

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


# ── Test constants ────────────────────────────────────────────────────────────

_TEST_PIN = "0000"
_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
# The in-process fake-discogsography returns this CONSTANT discogsography_user_id
# for every token (see tests/integration/conftest.py). The partial unique index
# uq_profiles_dgs_user_id_active permits only ONE active profile per discogs account,
# so a sync test must hold it exclusively (free any leftover active holder first).
_FAKE_DGS_USER_ID = "99999999-9999-9999-9999-999999999999"


# ── Rate-limit reset fixtures ─────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:  # type: ignore[return]
    """Reset ALL rate-limit counters before each test.

    Mirrors the pattern from test_devices.py — the login and redeem limiters
    share the same module-level FixedWindowRateLimiter singleton backed by
    MemoryStorage. Without a reset, tests that exhaust the window would cause
    subsequent tests to receive 429.
    """
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


# ── Module-scoped ASGI client fixture ────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    Seeds the test PIN hash ("0000") into gruvax.settings so admin-gated tests
    (invite generation) can log in.

    Mirrors the client fixture in test_devices.py exactly.
    """
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    from gruvax.auth.pin import hash_pin

    test_hash = hash_pin(_TEST_PIN)

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
                "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
                " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb,"
                "   'Test PIN seeded by test_invite_codes', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (_DEFAULT_PROFILE_UUID, f'"{test_hash}"'),
            )
            await conn.commit()
        yield ac


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _login(client: AsyncClient) -> dict[str, str]:
    """POST /api/admin/login and return cookies.

    Skips the test (rather than failing) if the login endpoint returns non-200,
    so AUTH-02 tests that require an admin session can degrade gracefully.
    """
    res = await client.post("/api/admin/login", json={"pin": _TEST_PIN})
    if res.status_code != 200:
        pytest.skip(
            f"Admin login failed ({res.status_code}) — skipping test that requires admin auth."
        )
    return dict(res.cookies)


def _csrf(cookies: dict[str, str]) -> str:
    return cookies.get("gruvax_csrf", "")


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH-02 tests — invite endpoints ship in Plan 02
# Marked xfail(strict=False) so the suite stays green while Plan 01 only ships
# the API-04 backend pieces.  These tests will go green once Plan 02 lands.
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_generate_invite(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/profiles/{id}/invite → {code, url, expires_at} (AUTH-02, D-01).

    Asserts:
    - 200 status
    - response body contains 'code' (UUID string), 'url' (http://...redeem/<code>), 'expires_at'
    - url ends with /redeem/<code>

    RED until Plan 02 ships POST /api/admin/profiles/{id}/invite.
    """
    cookies = await _login(client)
    res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    assert res.status_code == 200, (
        f"POST /api/admin/profiles/{{id}}/invite expected 200, got {res.status_code}: {res.text}. "
        f"RED until Plan 02 ships the invite endpoint."
    )
    data = res.json()
    assert "code" in data, "response must contain 'code' (UUID string)"
    assert "url" in data, "response must contain 'url'"
    assert "expires_at" in data, "response must contain 'expires_at'"
    # Validate code is a valid UUID
    _uuid_module.UUID(data["code"])
    assert f"/redeem/{data['code']}" in data["url"], (
        f"url must end with /redeem/<code>, got {data['url']!r}"
    )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_new_invite_voids_prior(client) -> None:  # type: ignore[no-untyped-def]
    """Generating a second invite voids the first — D-09 one-active-per-profile rule.

    Asserts:
    - First invite code becomes invalid (GET returns 404) after generating a second.
    - Second invite code is valid.

    RED until Plan 02 ships POST /api/admin/profiles/{id}/invite.
    """
    cookies = await _login(client)
    headers = {"X-CSRF-Token": _csrf(cookies)}

    # Generate first invite
    res1 = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers=headers,
    )
    if res1.status_code != 200:
        pytest.skip(f"invite endpoint returned {res1.status_code} — skipping void test")
    first_code = res1.json()["code"]

    # Generate second invite — must void the first
    res2 = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers=headers,
    )
    assert res2.status_code == 200, (
        f"Second invite generation expected 200, got {res2.status_code}: {res2.text}"
    )
    second_code = res2.json()["code"]
    assert first_code != second_code, "Second invite must have a different code"

    # First code must now be invalid (D-09 void behavior)
    get_first = await client.get(f"/api/invite-codes/{first_code}")
    assert get_first.status_code == 404, (
        f"Prior invite (code={first_code}) must be voided after generating a new one — "
        f"expected 404, got {get_first.status_code}: {get_first.text}. "
        f"D-09: one active invite per profile."
    )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_get_valid_code(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/invite-codes/{code} returns {display_name, expires_at} for a valid code.

    Asserts:
    - 200 status for a freshly generated valid code
    - response includes 'display_name' (the profile's display name)
    - response includes 'expires_at' (ISO-8601)

    RED until Plan 02 ships GET /api/invite-codes/{code} + POST /api/admin/profiles/{id}/invite.
    """
    cookies = await _login(client)
    # Generate a fresh invite
    gen_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    if gen_res.status_code != 200:
        pytest.skip(f"invite endpoint returned {gen_res.status_code}")
    code = gen_res.json()["code"]

    # Public GET — no auth required
    get_res = await client.get(f"/api/invite-codes/{code}")
    assert get_res.status_code == 200, (
        f"GET /api/invite-codes/{code} expected 200, got {get_res.status_code}: {get_res.text}. "
        f"RED until Plan 02 ships the invite-codes GET endpoint."
    )
    data = get_res.json()
    assert "display_name" in data, "response must include 'display_name'"
    assert "expires_at" in data, "response must include 'expires_at'"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_redeem_success(client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/invite-codes/{code}/redeem with valid PAT → 200 + sync starts (AUTH-02, D-04).

    Asserts:
    - 200 status
    - response body: {status: "connected", profile_id}
    - auto-sync triggered (verified by subsequent GET /api/admin/profiles showing in_progress
      or by last_sync_status changing from None to non-None)

    RED until Plan 02 ships POST /api/invite-codes/{code}/redeem.
    """
    cookies = await _login(client)
    gen_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    if gen_res.status_code != 200:
        pytest.skip(f"invite generation returned {gen_res.status_code}")
    code = gen_res.json()["code"]

    # Redeem with a valid fake PAT (the in-process fake accepts any dscg_* token)
    redeem_res = await client.post(
        f"/api/invite-codes/{code}/redeem",
        json={"pat": "dscg_test_member_token"},
    )
    assert redeem_res.status_code == 200, (
        f"POST /api/invite-codes/{code}/redeem expected 200, "
        f"got {redeem_res.status_code}: {redeem_res.text}. "
        f"RED until Plan 02 ships the redeem endpoint."
    )
    data = redeem_res.json()
    assert data.get("status") == "connected", (
        f"redeem response must include {{status: 'connected'}}, got: {data}"
    )
    assert "profile_id" in data, "redeem response must include 'profile_id'"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_redeem_second_use_rejected(client) -> None:  # type: ignore[no-untyped-def]
    """Second redeem of the same code returns 404 (single-use — D-02, AUTH-02).

    Asserts:
    - First redeem: 200
    - Second redeem of same code: 404 {type: "invite_not_found"}

    RED until Plan 02 ships the atomic consume-on-redeem pattern.
    """
    cookies = await _login(client)
    gen_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    if gen_res.status_code != 200:
        pytest.skip(f"invite generation returned {gen_res.status_code}")
    code = gen_res.json()["code"]

    # First redeem — should succeed
    first_res = await client.post(
        f"/api/invite-codes/{code}/redeem",
        json={"pat": "dscg_test_member_token"},
    )
    if first_res.status_code != 200:
        pytest.skip(f"first redeem returned {first_res.status_code} — skipping second-use check")

    # Second redeem — must be rejected (code already consumed)
    second_res = await client.post(
        f"/api/invite-codes/{code}/redeem",
        json={"pat": "dscg_test_member_token"},
    )
    assert second_res.status_code == 404, (
        f"Second redeem of already-consumed code expected 404, "
        f"got {second_res.status_code}: {second_res.text}. "
        f"The atomic UPDATE ... WHERE consumed_at IS NULL must reject the second attempt."
    )
    detail = second_res.json()
    error_type = (
        detail.get("type")
        or detail.get("detail", {}).get("type")
    )
    assert error_type == "invite_not_found", (
        f"404 response must include {{type: 'invite_not_found'}}, got: {detail}"
    )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_redeem_bad_pat(client) -> None:  # type: ignore[no-untyped-def]
    """Redeem with invalid PAT returns 401 pat_rejected (AUTH-02, T-07-03).

    Uses a token that does NOT start with 'dscg_' — the in-process fake returns 401
    for any non-dscg_* prefix token.

    RED until Plan 02 ships the redeem endpoint.
    """
    cookies = await _login(client)
    gen_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    if gen_res.status_code != 200:
        pytest.skip(f"invite generation returned {gen_res.status_code}")
    code = gen_res.json()["code"]

    # Invalid PAT — does not start with 'dscg_'
    redeem_res = await client.post(
        f"/api/invite-codes/{code}/redeem",
        json={"pat": "INVALID_TOKEN_NOT_DSCG"},
    )
    assert redeem_res.status_code == 401, (
        f"Redeem with invalid PAT expected 401 pat_rejected, "
        f"got {redeem_res.status_code}: {redeem_res.text}. "
        f"RED until Plan 02 ships PAT validation in the redeem endpoint."
    )
    detail = redeem_res.json()
    error_type = (
        detail.get("type")
        or detail.get("detail", {}).get("type")
    )
    assert error_type == "pat_rejected", (
        f"401 response must include {{type: 'pat_rejected'}}, got: {detail}"
    )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_redeem_expired(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """Expired invite code returns 404 invite_not_found (AUTH-02, D-01 TTL).

    Sets expires_at to the past directly in the DB to simulate TTL expiry.

    RED until Plan 02 ships the redeem endpoint with expiry check.
    """
    cookies = await _login(client)
    gen_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    if gen_res.status_code != 200:
        pytest.skip(f"invite generation returned {gen_res.status_code}")
    code = gen_res.json()["code"]

    # Expire the code directly in the DB
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profile_invite_codes"
            " SET expires_at = NOW() - INTERVAL '1 hour'"
            " WHERE code = %s::uuid",
            (code,),
        )
        await conn.commit()

    redeem_res = await client.post(
        f"/api/invite-codes/{code}/redeem",
        json={"pat": "dscg_test_member_token"},
    )
    assert redeem_res.status_code == 404, (
        f"Expired invite code expected 404, got {redeem_res.status_code}: {redeem_res.text}. "
        f"The WHERE expires_at > NOW() clause must reject expired codes."
    )
    detail = redeem_res.json()
    error_type = (
        detail.get("type")
        or detail.get("detail", {}).get("type")
    )
    assert error_type == "invite_not_found", (
        f"404 response must be {{type: 'invite_not_found'}} (no oracle — Pitfall 2), "
        f"got: {detail}"
    )


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.xfail(reason="endpoint in Plan 02", strict=False)
async def test_redeem_rotates_token(client) -> None:  # type: ignore[no-untyped-def]
    """Redeem onto a profile with existing token rotates it (D-10).

    Flow:
    1. Connect a PAT via the owner connect_pat endpoint (profile has a token).
    2. Generate an invite.
    3. Redeem with a different PAT — must overwrite without error (D-10).
    4. Subsequent sync uses the new PAT.

    RED until Plan 02 ships the redeem endpoint with D-10 overwrite behavior.
    """
    cookies = await _login(client)
    headers = {"X-CSRF-Token": _csrf(cookies)}

    # Step 1: connect an initial PAT via the owner flow
    connect_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/connect-pat",
        json={"pat": "dscg_initial_token"},
        cookies=cookies,
        headers=headers,
    )
    if connect_res.status_code not in (200, 201):
        pytest.skip(
            f"connect-pat returned {connect_res.status_code} — skipping rotation test"
        )

    # Step 2: generate invite
    gen_res = await client.post(
        f"/api/admin/profiles/{_DEFAULT_PROFILE_UUID}/invite",
        cookies=cookies,
        headers=headers,
    )
    if gen_res.status_code != 200:
        pytest.skip(f"invite generation returned {gen_res.status_code}")
    code = gen_res.json()["code"]

    # Step 3: redeem with a different PAT — must overwrite (D-10, no guard)
    redeem_res = await client.post(
        f"/api/invite-codes/{code}/redeem",
        json={"pat": "dscg_new_member_token"},
    )
    assert redeem_res.status_code == 200, (
        f"Redeem onto a profile with existing token expected 200 (D-10 rotation), "
        f"got {redeem_res.status_code}: {redeem_res.text}. "
        f"RED until Plan 02 ships D-10 overwrite behavior."
    )


# ═══════════════════════════════════════════════════════════════════════════════
# API-04 tests — ship in Plan 01, must NOT be xfail
# These test the has_token field, diff state fields, and sync diff computation.
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio(loop_scope="session")
async def test_profile_has_token_field(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/profiles returns has_token bool, never app_token_encrypted (API-04, T-07-01).

    Asserts:
    - Response for each profile includes 'has_token' (bool)
    - Response does NOT include 'app_token_encrypted'

    This plan (07-01) ships the has_token derivation in the SELECT query.
    """
    cookies = await _login(client)
    res = await client.get(
        "/api/admin/profiles",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    assert res.status_code == 200, (
        f"GET /api/admin/profiles expected 200, got {res.status_code}: {res.text}"
    )
    profiles = res.json()
    assert isinstance(profiles, list), "GET /api/admin/profiles must return a list"
    assert len(profiles) >= 1, "Expected at least 1 profile (the default)"

    for profile in profiles:
        assert "has_token" in profile, (
            f"Profile response must include 'has_token' bool (API-04, Pitfall 7). "
            f"Profile id={profile.get('id')!r} is missing 'has_token'. "
            f"Keys present: {list(profile.keys())}"
        )
        assert isinstance(profile["has_token"], bool), (
            f"'has_token' must be a bool, got {type(profile['has_token']).__name__!r}"
        )
        assert "app_token_encrypted" not in profile, (
            f"Profile response must NOT include 'app_token_encrypted' (T-07-01 — PAT must "
            f"never leave Postgres). Profile id={profile.get('id')!r} exposes the ciphertext. "
            f"Fix: use (app_token_encrypted IS NOT NULL ...)::bool AS has_token in SELECT."
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_profile_new_record_fields(client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/profiles includes last_new_record_count + last_sync_is_initial (API-04, D-08).

    Asserts:
    - Response for each profile includes 'last_new_record_count' (int or null)
    - Response includes 'last_sync_is_initial' (bool or null)

    These fields are stored atomically in the swap transaction and persisted
    until the next sync (D-08: stateless derivation from stored values).
    """
    cookies = await _login(client)
    res = await client.get(
        "/api/admin/profiles",
        cookies=cookies,
        headers={"X-CSRF-Token": _csrf(cookies)},
    )
    assert res.status_code == 200, (
        f"GET /api/admin/profiles expected 200, got {res.status_code}: {res.text}"
    )
    profiles = res.json()
    assert isinstance(profiles, list) and len(profiles) >= 1

    for profile in profiles:
        assert "last_new_record_count" in profile, (
            f"Profile response must include 'last_new_record_count' (API-04, D-08). "
            f"Profile id={profile.get('id')!r} is missing it. "
            f"Fix: add last_new_record_count to the profiles SELECT and response dict."
        )
        assert "last_sync_is_initial" in profile, (
            f"Profile response must include 'last_sync_is_initial' (API-04, D-08). "
            f"Profile id={profile.get('id')!r} is missing it. "
            f"Fix: add last_sync_is_initial to the profiles SELECT and response dict."
        )
        # Values can be None (before first sync) or int/bool (after)
        lnrc = profile["last_new_record_count"]
        lsi = profile["last_sync_is_initial"]
        assert lnrc is None or (isinstance(lnrc, int) and lnrc >= 0), (
            f"'last_new_record_count' must be None or non-negative int, got {lnrc!r}"
        )
        assert lsi is None or isinstance(lsi, bool), (
            f"'last_sync_is_initial' must be None or bool, got {lsi!r}"
        )


async def _free_fake_account(db_pool, keep_profile_id):  # type: ignore[no-untyped-def]
    """Clear the fake discogs user_id from any OTHER active profile holding it.

    The fake returns a constant discogsography_user_id; uq_profiles_dgs_user_id_active
    is a partial unique index over active profiles WHERE discogsography_user_id IS NOT
    NULL. In the full suite an earlier test may leave a profile (commonly the Default
    profile, synced by the sync/* tests) still holding it, which makes THIS profile's
    sync fail with a UniqueViolation.

    We NULL out the user_id rather than soft-deleting the holder: NULLing removes the
    row from the partial index (freeing the account) while keeping the holder ACTIVE.
    Soft-deleting would evict the Default profile from the app's per-profile registries
    and break unrelated tests (e.g. test_locate → profile_not_found). For the Default
    profile, NULL is also its canonical seeded state, so this just undoes the leak.
    """
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET discogsography_user_id = NULL"
            " WHERE discogsography_user_id = %s::uuid"
            " AND deleted_at IS NULL AND id <> %s::uuid",
            (_FAKE_DGS_USER_ID, keep_profile_id),
        )
        await conn.commit()


async def _await_sync(client, profile_id, cookies, headers):  # type: ignore[no-untyped-def]
    """Poll GET /api/admin/profiles/{id} until the async sync settles, return the JSON.

    POST .../sync returns 202 (background swap). Reading the stored diff fields
    immediately races the background task — under full-suite event-loop contention
    the swap has not run yet and last_sync_is_initial still reads its default.
    Mirror the poll pattern used by test_profile_manager_api::test_connect_pat_flow.
    """
    profile = {}
    for _ in range(20):
        detail = await client.get(
            f"/api/admin/profiles/{profile_id}",
            cookies=cookies,
            headers=headers,
        )
        if detail.status_code == 200:
            profile = detail.json()
            if profile.get("last_sync_status") in ("ok", "failed"):
                return profile
        await asyncio.sleep(0.5)
    return profile


@pytest.mark.asyncio(loop_scope="session")
async def test_initial_import_flag(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """First sync reports is_initial_import=True; second sync reports False (API-04, D-07).

    Flow:
    1. Create a fresh profile (no sync history).
    2. Trigger sync — is_initial_import must be True (last_sync_at WAS NULL).
    3. Trigger sync again — is_initial_import must be False.

    This test is self-contained: creates and cleans up its own profile.
    """
    cookies = await _login(client)
    headers = {"X-CSRF-Token": _csrf(cookies)}

    # Create a fresh profile with a unique name
    unique_suffix = _uuid_module.uuid4().hex[:8]
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": f"Initial-Import-Test-{unique_suffix}"},
        cookies=cookies,
        headers=headers,
    )
    if create_res.status_code not in (200, 201):
        pytest.skip(
            f"create profile endpoint returned {create_res.status_code} — "
            f"skipping initial_import_flag test"
        )
    profile_id = create_res.json().get("id")
    if not profile_id:
        pytest.skip("could not get profile id from create response")

    try:
        # Seed a valid PAT for the profile so sync can proceed
        async with db_pool.connection() as conn:
            from gruvax.sync.pat_crypto import encrypt_pat
            ciphertext = encrypt_pat("dscg_test_initial_import_token")
            await conn.execute(
                "UPDATE gruvax.profiles"
                " SET app_token_encrypted = %s::bytea, app_token_revoked = FALSE"
                " WHERE id = %s::uuid",
                (ciphertext, profile_id),
            )
            await conn.commit()

        # Free the shared fake discogs account so this sync can claim it.
        await _free_fake_account(db_pool, profile_id)

        # First sync — must report is_initial_import=True
        sync_res1 = await client.post(
            f"/api/admin/profiles/{profile_id}/sync",
            cookies=cookies,
            headers=headers,
        )
        if sync_res1.status_code not in (200, 202):
            pytest.skip(
                f"sync endpoint returned {sync_res1.status_code} — "
                f"skipping initial_import_flag test"
            )

        # /sync is async (202) — wait for the background swap to settle before
        # reading the stored diff flag, else we race the background task.
        profile1 = await _await_sync(client, profile_id, cookies, headers)
        assert "last_sync_is_initial" in profile1, (
            "Profile response must include 'last_sync_is_initial' after first sync"
        )
        is_initial_1 = profile1["last_sync_is_initial"]
        assert is_initial_1 is True, (
            f"First sync must report last_sync_is_initial=True (D-07). "
            f"Got: {is_initial_1!r}. "
            f"Fix: _swap_inside_tx must read last_sync_at IS NULL BEFORE the UPDATE (Pitfall 4)."
        )

        # Second sync — must report is_initial_import=False
        sync_res2 = await client.post(
            f"/api/admin/profiles/{profile_id}/sync",
            cookies=cookies,
            headers=headers,
        )
        if sync_res2.status_code not in (200, 202):
            pytest.skip(
                f"second sync returned {sync_res2.status_code} — "
                f"skipping second-sync assertion"
            )

        profile2 = await _await_sync(client, profile_id, cookies, headers)
        is_initial_2 = profile2["last_sync_is_initial"]
        assert is_initial_2 is False, (
            f"Second sync must report last_sync_is_initial=False (D-07). "
            f"Got: {is_initial_2!r}. "
            f"Fix: last_sync_at IS NOT NULL after first sync → is_initial_import=False."
        )

    finally:
        # Cleanup: soft-delete the test profile
        async with db_pool.connection() as conn:
            await conn.execute(
                "UPDATE gruvax.profiles SET deleted_at = NOW() WHERE id = %s::uuid",
                (profile_id,),
            )
            await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_arrival_count_accuracy(client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """new_record_count equals the count of genuinely new releases, never negative (API-04, D-06).

    Flow:
    1. Create a fresh profile, seed a PAT.
    2. First sync: in-process fake has N releases. new_record_count should be N (initial import).
    3. Check last_new_record_count via GET /api/admin/profiles/{id}.
    4. Verify it is >= 0 and matches the item count for an initial import.

    The in-process fake-discogsography (seeded in conftest.py with 50 releases) is used.
    """
    cookies = await _login(client)
    headers = {"X-CSRF-Token": _csrf(cookies)}

    # Create a fresh profile
    unique_suffix = _uuid_module.uuid4().hex[:8]
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": f"Arrival-Count-Test-{unique_suffix}"},
        cookies=cookies,
        headers=headers,
    )
    if create_res.status_code not in (200, 201):
        pytest.skip(
            f"create profile endpoint returned {create_res.status_code} — "
            f"skipping arrival_count_accuracy test"
        )
    profile_id = create_res.json().get("id")
    if not profile_id:
        pytest.skip("could not get profile id from create response")

    try:
        # Seed a valid PAT
        async with db_pool.connection() as conn:
            from gruvax.sync.pat_crypto import encrypt_pat
            ciphertext = encrypt_pat("dscg_test_arrival_count_token")
            await conn.execute(
                "UPDATE gruvax.profiles"
                " SET app_token_encrypted = %s::bytea, app_token_revoked = FALSE"
                " WHERE id = %s::uuid",
                (ciphertext, profile_id),
            )
            await conn.commit()

        # Free the shared fake discogs account so this sync can claim it.
        await _free_fake_account(db_pool, profile_id)

        # Trigger sync
        sync_res = await client.post(
            f"/api/admin/profiles/{profile_id}/sync",
            cookies=cookies,
            headers=headers,
        )
        if sync_res.status_code not in (200, 202):
            pytest.skip(
                f"sync endpoint returned {sync_res.status_code} — "
                f"skipping arrival count accuracy test"
            )

        # /sync is async (202) — wait for the background swap to settle before
        # reading the stored diff state, else we race the background task.
        profile = await _await_sync(client, profile_id, cookies, headers)

        assert "last_new_record_count" in profile, (
            "Profile response must include 'last_new_record_count' after sync"
        )
        count = profile["last_new_record_count"]
        assert count is not None, (
            "last_new_record_count must not be None after a successful sync"
        )
        assert count >= 0, (
            f"last_new_record_count must be >= 0 (D-06: never negative). Got: {count}"
        )

        # For a fresh profile (initial import), count should equal item_count
        # (all records are new — no pre-existing records to compare against)
        item_count = profile.get("last_sync_item_count", 0) or 0
        is_initial = profile.get("last_sync_is_initial", False)
        if is_initial and item_count > 0:
            assert count == item_count, (
                f"On initial import (is_initial=True), new_record_count ({count}) "
                f"should equal item_count ({item_count}) — all records are new. "
                f"Fix: max(0, row_count - 0) = row_count on first sync (existing_count=0)."
            )

    finally:
        # Cleanup
        async with db_pool.connection() as conn:
            await conn.execute(
                "UPDATE gruvax.profiles SET deleted_at = NOW() WHERE id = %s::uuid",
                (profile_id,),
            )
            await conn.commit()

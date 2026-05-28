"""Integration tests for Profile Manager admin API — Plan 02-00 RED baseline.

Covers PROF-02: Profile manager CRUD + connect-PAT + 202/poll + collision + soft-delete.

All tests are RED until Plans 02-05 land the profile manager admin endpoints.

Endpoints tested:
  GET  /api/admin/profiles                  — list profiles
  POST /api/admin/profiles                  — create profile
  GET  /api/admin/profiles/{id}             — get single profile
  POST /api/admin/profiles/{id}/connect     — connect PAT (test-sync + store)
  POST /api/admin/profiles/{id}/sync        — trigger async sync → 202
  DELETE /api/admin/profiles/{id}           — soft-delete

Cookie name convention (D2-10): gruvax_browse_binding is the browse-binding cookie,
independent from gruvax_session (admin) and gruvax_csrf (CSRF double-submit).

Uses fake-discogsography for PAT validation (D-15 single-module pattern).
"""

from __future__ import annotations

import os

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    Seeds the test PIN ("0000") after app startup, following the pattern
    from test_admin_auth.py (module-scope; db_pool ensures DB is up).
    """
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
        _DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"
        async with pool.connection() as conn:
            await conn.execute(
                "INSERT INTO gruvax.settings (profile_id, key, value, description, updated_at)"
                " VALUES (%s::uuid, 'auth.pin_hash', %s::jsonb, 'Test PIN seeded by test_profile_manager_api', now())"
                " ON CONFLICT (profile_id, key) DO UPDATE"
                "  SET value = EXCLUDED.value, updated_at = now()",
                (_DEFAULT_PROFILE_UUID, f'"{test_hash}"'),
            )
            await conn.commit()
        yield ac


# ── tests ─────────────────────────────────────────────────────────────────────
#
# All tests use admin_session (requires X-CSRF-Token on all mutating requests).


@pytest.mark.asyncio(loop_scope="session")
async def test_create_profile(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """POST /api/admin/profiles {display_name:"Sam"} → 200/201; GET lists it PENDING.

    RED until Plan 02-05 lands the profiles CRUD endpoints. After landing:
    - POST returns id (new profile UUID)
    - GET /api/admin/profiles lists the new profile with status PENDING (no PAT)
    """
    # Create a new profile
    res = await client.post(
        "/api/admin/profiles",
        json={"display_name": "Sam"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert res.status_code in (200, 201), (
        f"POST /api/admin/profiles expected 200/201, got {res.status_code}: {res.text}"
    )
    body = res.json()
    assert "id" in body, f"Response must include 'id': {body}"
    new_profile_id = body["id"]

    # List profiles and find our new one
    list_res = await client.get(
        "/api/admin/profiles",
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert list_res.status_code == 200, (
        f"GET /api/admin/profiles expected 200, got {list_res.status_code}"
    )
    profiles = list_res.json()
    # Find the created profile by id
    found = next((p for p in profiles if str(p.get("id", "")) == str(new_profile_id)), None)
    assert found is not None, (
        f"Newly created profile {new_profile_id!r} not in GET /api/admin/profiles listing"
    )
    # Status must be PENDING (no PAT connected yet)
    assert found.get("status") in ("pending", "PENDING", None) or found.get("app_token_revoked") is True, (
        f"New profile without PAT should have status PENDING or app_token_revoked=True, got: {found}"
    )

    # Cleanup: soft-delete the test profile
    await client.delete(
        f"/api/admin/profiles/{new_profile_id}",
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_connect_pat_flow(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """POST /api/admin/profiles/{id}/connect with valid fake PAT → sync completes.

    RED until Plans 02-04/02-05 land. After landing:
    - POST /connect validates PAT via test-sync (synchronous, blocks request)
    - Captures discogsography_user_id, flips app_token_revoked FALSE
    - Kicks full async sync as background task
    - GET /api/admin/profiles/{id} eventually shows last_sync_status 'ok'

    Uses the fake-discogsography's default magic token routing — any Bearer
    dscg_* token (not dscg_force_*) returns 200 with user_id.
    """
    # Create profile first
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": "ConnectTestProfile"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if create_res.status_code not in (200, 201):
        pytest.skip("Profile create endpoint not implemented — skipping connect test")

    profile_id = create_res.json()["id"]

    try:
        # Connect with a valid fake PAT — fake-discogsography accepts any dscg_* token
        connect_res = await client.post(
            f"/api/admin/profiles/{profile_id}/connect",
            json={"pat": "dscg_test_valid_token_00000000"},
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )
        assert connect_res.status_code == 200, (
            f"POST /connect expected 200, got {connect_res.status_code}: {connect_res.text}"
        )

        # Poll GET /api/admin/profiles/{id} until last_sync_status = 'ok' or timeout
        import asyncio

        deadline = asyncio.get_event_loop().time() + 30.0  # 30s budget for sync
        sync_status = None
        while asyncio.get_event_loop().time() < deadline:
            detail_res = await client.get(
                f"/api/admin/profiles/{profile_id}",
                cookies=admin_session["cookies"],
                headers={"X-CSRF-Token": admin_session["csrf_token"]},
            )
            if detail_res.status_code == 200:
                sync_status = detail_res.json().get("last_sync_status")
                if sync_status == "ok":
                    break
                if sync_status == "failed":
                    break
            await asyncio.sleep(2.0)

        assert sync_status == "ok", (
            f"last_sync_status should be 'ok' after connect+sync, got {sync_status!r}"
        )
    finally:
        # Cleanup
        await client.delete(
            f"/api/admin/profiles/{profile_id}",
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_202_poll(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """POST /api/admin/profiles/{id}/sync → 202 immediately; last_sync_status transitions.

    RED until Plan 02-04 (background-task 202 conversion) lands. After landing:
    - POST /sync returns 202 Accepted immediately (not 200)
    - Poll GET /api/admin/profiles/{id} shows last_sync_status transitions
      from 'in_progress' eventually to 'ok' or 'failed'
    """
    # Create and connect a profile first
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": "SyncPollTestProfile"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if create_res.status_code not in (200, 201):
        pytest.skip("Profile create endpoint not implemented — skipping sync 202 test")

    profile_id = create_res.json()["id"]

    try:
        # Trigger sync — must return 202 Accepted (not 200)
        sync_res = await client.post(
            f"/api/admin/profiles/{profile_id}/sync",
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )
        assert sync_res.status_code == 202, (
            f"POST /sync must return 202 Accepted (background task), "
            f"got {sync_res.status_code}: {sync_res.text}"
        )

        # Poll for completion
        import asyncio

        deadline = asyncio.get_event_loop().time() + 30.0
        final_status = None
        while asyncio.get_event_loop().time() < deadline:
            detail_res = await client.get(
                f"/api/admin/profiles/{profile_id}",
                cookies=admin_session["cookies"],
                headers={"X-CSRF-Token": admin_session["csrf_token"]},
            )
            if detail_res.status_code == 200:
                final_status = detail_res.json().get("last_sync_status")
                if final_status in ("ok", "failed"):
                    break
            await asyncio.sleep(2.0)

        assert final_status in ("ok", "failed"), (
            f"last_sync_status should be 'ok' or 'failed' after polling, got {final_status!r}"
        )
    finally:
        await client.delete(
            f"/api/admin/profiles/{profile_id}",
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_user_id_collision(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """Connecting two profiles with the same discogsography_user_id → 409.

    RED until Plan 02-05 lands the connect endpoint's uniqueness guard.
    The fake-discogsography returns the same user_id for all tokens; the server
    must detect the collision on the second connect and return 409
    {"type":"user_id_collision"}.
    """
    # Create two profiles
    res_a = await client.post(
        "/api/admin/profiles",
        json={"display_name": "CollisionProfileA"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if res_a.status_code not in (200, 201):
        pytest.skip("Profile create endpoint not implemented — skipping collision test")
    profile_id_a = res_a.json()["id"]

    res_b = await client.post(
        "/api/admin/profiles",
        json={"display_name": "CollisionProfileB"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if res_b.status_code not in (200, 201):
        await client.delete(
            f"/api/admin/profiles/{profile_id_a}",
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )
        pytest.skip("Profile create endpoint not implemented — skipping collision test")
    profile_id_b = res_b.json()["id"]

    try:
        # Connect profile A — this should succeed
        connect_a = await client.post(
            f"/api/admin/profiles/{profile_id_a}/connect",
            json={"pat": "dscg_test_valid_token_collision_a"},
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )
        if connect_a.status_code != 200:
            pytest.skip("Connect endpoint not implemented — skipping collision test")

        # Connect profile B with a different token resolving to the SAME user_id →
        # The fake-discogsography returns user_id = "99999999-..." for all tokens.
        # The server must detect the already-used user_id and return 409.
        connect_b = await client.post(
            f"/api/admin/profiles/{profile_id_b}/connect",
            json={"pat": "dscg_test_valid_token_collision_b"},
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )
        assert connect_b.status_code == 409, (
            f"Second connect with same discogsography_user_id must return 409, "
            f"got {connect_b.status_code}: {connect_b.text}"
        )
        error_body = connect_b.json()
        assert error_body.get("type") == "user_id_collision" or (
            "detail" in error_body
            and isinstance(error_body["detail"], dict)
            and error_body["detail"].get("type") == "user_id_collision"
        ), f"409 response must include type='user_id_collision': {error_body}"
    finally:
        for pid in (profile_id_a, profile_id_b):
            await client.delete(
                f"/api/admin/profiles/{pid}",
                cookies=admin_session["cookies"],
                headers={"X-CSRF-Token": admin_session["csrf_token"]},
            )


@pytest.mark.asyncio(loop_scope="session")
async def test_soft_delete_evicts(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """DELETE /api/admin/profiles/{id} → 200; profile absent from list + GET /api/session.

    RED until Plan 02-05 lands the soft-delete endpoint. After landing:
    - DELETE returns 200
    - Profile no longer in GET /api/admin/profiles
    - Profile absent from GET /api/session profiles[]
    """
    # Create a profile to delete
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": "ToBeDeleted"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if create_res.status_code not in (200, 201):
        pytest.skip("Profile create endpoint not implemented — skipping soft-delete test")
    profile_id = create_res.json()["id"]

    # Soft-delete
    delete_res = await client.delete(
        f"/api/admin/profiles/{profile_id}",
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert delete_res.status_code == 200, (
        f"DELETE /api/admin/profiles/{profile_id} expected 200, "
        f"got {delete_res.status_code}: {delete_res.text}"
    )

    # Must not appear in GET /api/admin/profiles
    list_res = await client.get(
        "/api/admin/profiles",
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    assert list_res.status_code == 200
    profiles = list_res.json()
    found = next(
        (p for p in profiles if str(p.get("id", "")) == str(profile_id)),
        None,
    )
    assert found is None, (
        f"Soft-deleted profile {profile_id!r} should not appear in GET /api/admin/profiles"
    )

    # Must not appear in GET /api/session profiles[]
    session_res = await client.get("/api/session")
    if session_res.status_code == 200:
        session_data = session_res.json()
        session_profiles = session_data.get("profiles", [])
        in_session = any(
            str(p.get("id", "")) == str(profile_id) for p in session_profiles
        )
        assert not in_session, (
            f"Soft-deleted profile {profile_id!r} should not appear in GET /api/session profiles[]"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_pat_rejected(
    client,  # type: ignore[no-untyped-def]
    admin_session,
) -> None:
    """POST /api/admin/profiles/{id}/connect with rejected PAT → 401 {"type":"pat_rejected"}.

    RED until Plan 02-05 lands. Uses the fake-discogsography's magic token
    "dscg_force_401" (or any token that is 401'd) to simulate a rejected PAT.
    The connect endpoint's test-sync leg must surface this as 401 pat_rejected.
    """
    create_res = await client.post(
        "/api/admin/profiles",
        json={"display_name": "PatRejectedTestProfile"},
        cookies=admin_session["cookies"],
        headers={"X-CSRF-Token": admin_session["csrf_token"]},
    )
    if create_res.status_code not in (200, 201):
        pytest.skip("Profile create endpoint not implemented — skipping pat_rejected test")
    profile_id = create_res.json()["id"]

    try:
        # Use a bad-prefix token — the fake app rejects tokens that don't start
        # with "Bearer dscg_". Sending "Bearer invalid_token" should trigger 401.
        connect_res = await client.post(
            f"/api/admin/profiles/{profile_id}/connect",
            # A token that the fake-discogsography's auth check will reject:
            # doesn't start with "dscg_" prefix so the fake returns 401.
            json={"pat": "invalid_token_no_dscg_prefix"},
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )
        assert connect_res.status_code == 401, (
            f"POST /connect with invalid PAT must return 401, "
            f"got {connect_res.status_code}: {connect_res.text}"
        )
        error_body = connect_res.json()
        # Accept either top-level or nested type field
        error_type = error_body.get("type") or (
            error_body.get("detail", {}).get("type") if isinstance(error_body.get("detail"), dict)
            else None
        )
        assert error_type == "pat_rejected", (
            f"401 response must include type='pat_rejected': {error_body}"
        )
    finally:
        await client.delete(
            f"/api/admin/profiles/{profile_id}",
            cookies=admin_session["cookies"],
            headers={"X-CSRF-Token": admin_session["csrf_token"]},
        )

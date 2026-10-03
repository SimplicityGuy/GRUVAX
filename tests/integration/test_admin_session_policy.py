"""Actual global settings writes control login and refresh, never profile selection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from itsdangerous import URLSafeSerializer
from psycopg.types.json import Jsonb
import pytest
import pytest_asyncio

from gruvax.api.admin.login import router as login_router
from gruvax.api.admin.settings import router as settings_router
from gruvax.auth.pin import hash_pin
from gruvax.db.queries import DEFAULT_PROFILE_UUID, load_settings_cache
from gruvax.settings import settings


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

KEYS = ["auth.pin_hash", "session.idle_ttl_seconds", "session.hard_cap_seconds"]


@pytest_asyncio.fixture(loop_scope="session")
async def policy_client(db_pool: Any) -> AsyncIterator[Any]:
    async with db_pool.connection() as conn:
        cur = await conn.execute(
            "SELECT key,value,description,updated_at FROM gruvax.settings"
            " WHERE profile_id=%s AND key=ANY(%s)",
            (DEFAULT_PROFILE_UUID, KEYS),
        )
        previous = await cur.fetchall()
        for key, value in zip(KEYS, [hash_pin("0000"), 600, 1800], strict=True):
            await conn.execute(
                "INSERT INTO gruvax.settings(profile_id,key,value,description) VALUES(%s,%s,%s,'Policy test')"
                " ON CONFLICT(profile_id,key) DO UPDATE SET value=EXCLUDED.value",
                (DEFAULT_PROFILE_UUID, key, Jsonb(value)),
            )
    app = FastAPI()
    app.state.db_pool = db_pool
    app.state.settings_cache = await load_settings_cache(db_pool, profile_id=DEFAULT_PROFILE_UUID)
    app.state.settings_cache_registry = {str(uuid4()): {"session.idle_ttl_seconds": 9999}}
    app.include_router(login_router, prefix="/api/admin")
    app.include_router(settings_router, prefix="/api/admin")
    session_ids: list[str] = []
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, db_pool, app, session_ids
    finally:
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.admin_sessions WHERE id=ANY(%s::uuid[])", (session_ids,)
            )
            await conn.execute(
                "DELETE FROM gruvax.settings WHERE profile_id=%s AND key=ANY(%s)",
                (DEFAULT_PROFILE_UUID, KEYS),
            )
            for key, value, description, updated_at in previous:
                await conn.execute(
                    "INSERT INTO gruvax.settings(profile_id,key,value,description,updated_at) VALUES(%s,%s,%s,%s,%s)",
                    (DEFAULT_PROFILE_UUID, key, Jsonb(value), description, updated_at),
                )


async def login(ctx: Any) -> tuple[str, str]:
    client, _, _, ids = ctx
    result = await client.post("/api/admin/login", json={"pin": "0000"})
    assert result.status_code == 200
    sid = URLSafeSerializer(settings.SESSION_SECRET, salt="session").loads(
        client.cookies["gruvax_session"]
    )
    ids.append(sid)
    return sid, result.json()["csrf_token"]


async def put(ctx: Any, csrf: str, **values: Any) -> Any:
    return await ctx[0].put("/api/admin/settings", json=values, headers={"X-CSRF-Token": csrf})


async def row(ctx: Any, sid: str) -> Any:
    async with ctx[1].connection() as conn:
        cur = await conn.execute(
            "SELECT created_at,last_seen_at,expires_at,hard_expires_at FROM gruvax.admin_sessions WHERE id=%s",
            (sid,),
        )
        return await cur.fetchone()


@pytest.mark.asyncio(loop_scope="session")
async def test_absent_policy_get_and_login_share_environment_fallback(
    policy_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, pool, app, _ = policy_client
    await login(policy_client)
    monkeypatch.setattr(settings, "SESSION_TTL_SECONDS", 47)
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.settings WHERE profile_id=%s AND key=ANY(%s)",
            (DEFAULT_PROFILE_UUID, KEYS[1:]),
        )
    app.state.settings_cache = await load_settings_cache(pool, profile_id=DEFAULT_PROFILE_UUID)
    displayed = await client.get("/api/admin/settings")
    assert displayed.status_code == 200
    assert displayed.json()["session_idle_ttl_seconds"] == 47
    assert displayed.json()["session_hard_cap_seconds"] == 1800
    sid, _ = await login(policy_client)
    created, _, expires, hard = await row(policy_client, sid)
    assert (expires - created).total_seconds() == 47
    assert (hard - created).total_seconds() == 1800


@pytest.mark.asyncio(loop_scope="session")
async def test_put_policy_controls_login_and_refresh_globally(policy_client: Any) -> None:
    client, _, app, _ = policy_client
    _, csrf = await login(policy_client)
    assert (
        await put(policy_client, csrf, session_idle_ttl_seconds=60, session_hard_cap_seconds=120)
    ).status_code == 200
    # Browse selection and per-profile overrides do not change global PIN authority.
    client.cookies.set("gruvax_browse_binding", next(iter(app.state.settings_cache_registry)))
    sid, csrf = await login(policy_client)
    created, _, expires, hard = await row(policy_client, sid)
    assert (expires - created).total_seconds() == 60
    assert (hard - created).total_seconds() == 120
    settings_result = await client.get("/api/admin/settings")
    assert settings_result.json()["session_hard_cap_seconds"] == 120
    assert (await put(policy_client, csrf, session_idle_ttl_seconds=90)).status_code == 200
    assert (await client.get("/api/admin/session")).status_code == 200
    _, seen, expires, hard_after = await row(policy_client, sid)
    assert (expires - seen).total_seconds() == 90
    assert hard_after == hard


@pytest.mark.asyncio(loop_scope="session")
async def test_new_caps_apply_to_login_existing_caps_remain_immutable(policy_client: Any) -> None:
    _, csrf = await login(policy_client)
    assert (
        await put(policy_client, csrf, session_idle_ttl_seconds=120, session_hard_cap_seconds=60)
    ).status_code == 200
    sid, csrf = await login(policy_client)
    created, _, expires, hard = await row(policy_client, sid)
    assert expires == hard and (hard - created).total_seconds() == 60
    assert (await put(policy_client, csrf, session_hard_cap_seconds=3600)).status_code == 200
    assert (await policy_client[0].get("/api/admin/session")).status_code == 200
    assert (await row(policy_client, sid))[2:] == (hard, hard)
    new_sid, csrf = await login(policy_client)
    new_created, _, _, new_hard = await row(policy_client, new_sid)
    assert (new_hard - new_created).total_seconds() == 3600
    assert (await put(policy_client, csrf, session_hard_cap_seconds=15)).status_code == 200
    final_sid, _ = await login(policy_client)
    final_created, _, final_expires, final_hard = await row(policy_client, final_sid)
    assert final_expires == final_hard and (final_hard - final_created).total_seconds() == 15


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("field", ["session_idle_ttl_seconds", "session_hard_cap_seconds"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "60"])
async def test_invalid_policy_write_rejected(policy_client: Any, field: str, value: Any) -> None:
    _, csrf = await login(policy_client)
    result = await put(policy_client, csrf, **{field: value})
    assert result.status_code == 422
    assert result.json()["detail"]["type"] == "invalid_session_duration"
    current = await policy_client[0].get("/api/admin/settings")
    assert current.json()[field] == (600 if field == "session_idle_ttl_seconds" else 1800)

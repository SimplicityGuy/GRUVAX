"""Cadence import parity uses real HTTP, SQL and in-process cache state."""

from copy import deepcopy

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
import yaml

from gruvax.app import create_app
from gruvax.auth.pin import hash_pin
from gruvax.db.queries import load_settings_cache
from tests.cookies import cookie_header


PROFILE = "00000000-0000-0000-0000-000000000001"
KEYS = ["sync.cadence", "led_brightness.active", "auth.pin_hash"]


async def settings_rows(pool):  # type: ignore[no-untyped-def]
    async with pool.connection() as conn:
        return await (
            await conn.execute(
                "SELECT key, value, updated_at FROM gruvax.settings WHERE profile_id = %s::uuid AND key = ANY(%s) ORDER BY key",
                (PROFILE, KEYS),
            )
        ).fetchall()


@pytest_asyncio.fixture(loop_scope="session")
async def settings_api(db_pool):  # type: ignore[no-untyped-def]
    original = await settings_rows(db_pool)
    async with db_pool.connection() as conn:
        for key, value in [
            ("sync.cadence", '"24h"'),
            ("led_brightness.active", "255"),
            ("auth.pin_hash", '"' + hash_pin("0000") + '"'),
        ]:
            await conn.execute(
                "INSERT INTO gruvax.settings (profile_id, key, value) VALUES (%s::uuid, %s, %s::jsonb) ON CONFLICT (profile_id, key) DO UPDATE SET value = EXCLUDED.value",
                (PROFILE, key, value),
            )
        await conn.commit()
    app = create_app()
    app.state.db_pool = db_pool
    app.state.settings_cache = await load_settings_cache(db_pool, profile_id=PROFILE)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            login = await client.post("/api/admin/login", json={"pin": "0000"})
            assert login.status_code == 200, login.text
            headers = {"X-CSRF-Token": login.cookies["gruvax_csrf"], **cookie_header(login.cookies)}
            yield client, headers, app
    finally:
        from psycopg.types.json import Jsonb

        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.settings WHERE profile_id = %s::uuid AND key = ANY(%s)",
                (PROFILE, KEYS),
            )
            for row in original:
                await conn.execute(
                    "INSERT INTO gruvax.settings (profile_id, key, value, updated_at) VALUES (%s::uuid, %s, %s, %s)",
                    (PROFILE, row[0], Jsonb(row[1]), row[2]),
                )
            await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "cadence", ["bogus", 24, True, None, [], ["24h"], {}, {"unexpected": "24h"}]
)
async def test_invalid_import_cadence_rejects_entire_file(settings_api, db_pool, cadence):  # type: ignore[no-untyped-def]
    client, headers, app = settings_api
    before = await settings_rows(db_pool)
    cache = deepcopy(app.state.settings_cache)
    response = await client.post(
        "/api/admin/import/settings",
        content=yaml.safe_dump({"led_brightness": {"active": 17}, "sync": {"cadence": cadence}}),
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "invalid_cadence"
    assert await settings_rows(db_pool) == before
    assert app.state.settings_cache == cache


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("cadence", ["24h", "12h", "6h", "off"])
async def test_valid_import_cadence_matches_sql_cache_and_get(settings_api, db_pool, cadence):  # type: ignore[no-untyped-def]
    client, headers, app = settings_api
    response = await client.post(
        "/api/admin/import/settings",
        content=yaml.safe_dump({"sync": {"cadence": cadence}}),
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["updated"] == ["sync.cadence"]
    rows = await settings_rows(db_pool)
    assert next(row[1] for row in rows if row[0] == "sync.cadence") == cadence
    assert app.state.settings_cache["sync.cadence"] == cadence
    fetched = await client.get("/api/admin/settings", headers=headers)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["sync_cadence"] == cadence


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("cadence", [["24h"], {"unexpected": "24h"}])
async def test_put_cadence_container_rejects_entire_payload(settings_api, db_pool, cadence):  # type: ignore[no-untyped-def]
    client, headers, app = settings_api
    before = await settings_rows(db_pool)
    cache = deepcopy(app.state.settings_cache)
    response = await client.put(
        "/api/admin/settings",
        json={"led_brightness_active": 17, "sync_cadence": cadence},
        headers=headers,
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["type"] == "invalid_cadence"
    assert await settings_rows(db_pool) == before
    assert app.state.settings_cache == cache

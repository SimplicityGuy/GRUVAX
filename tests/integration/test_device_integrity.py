"""Real PostgreSQL/HTTP profile assignment contracts for admin devices."""

import uuid

from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app
from gruvax.auth.pin import hash_pin
from gruvax.db.queries import DEFAULT_PROFILE_UUID
from tests.cookies import cookie_header


@pytest_asyncio.fixture(loop_scope="session")
async def device_api(db_pool):  # type: ignore[no-untyped-def]
    app = create_app()
    app.state.db_pool = db_pool
    async with db_pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (value, profile_id, key) VALUES (%s::jsonb, %s::uuid, 'auth.pin_hash') ON CONFLICT (profile_id, key) DO UPDATE SET value = EXCLUDED.value",
            ('"' + hash_pin("0000") + '"', DEFAULT_PROFILE_UUID),
        )
        await conn.commit()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        login = await client.post("/api/admin/login", json={"pin": "0000"})
        assert login.status_code == 200, login.text
        headers = {"X-CSRF-Token": login.cookies["gruvax_csrf"], **cookie_header(login.cookies)}
        yield client, headers


@pytest_asyncio.fixture(loop_scope="session")
async def device_rows(db_pool):  # type: ignore[no-untyped-def]
    profiles = [str(uuid.uuid4()) for _ in range(3)]
    devices = [str(uuid.uuid4()) for _ in range(2)]
    async with db_pool.connection() as conn:
        for i, profile in enumerate(profiles):
            await conn.execute(
                "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked, deleted_at) VALUES (%s::uuid, %s, %s, TRUE, CASE WHEN %s THEN NOW() ELSE NULL END)",
                (profile, f"Device profile {profile}", b"", i == 2),
            )
        for device, profile in zip(devices, profiles, strict=False):
            await conn.execute(
                "INSERT INTO gruvax.devices (id, fingerprint, profile_id, display_name) VALUES (%s::uuid, %s, %s::uuid, 'Original name')",
                (device, str(uuid.uuid4()), profile),
            )
        await conn.commit()
    try:
        yield profiles, devices
    finally:
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.devices WHERE id = ANY(%s::uuid[])", (devices,))
            await conn.execute(
                "DELETE FROM gruvax.profiles WHERE id = ANY(%s::uuid[])", (profiles,)
            )
            await conn.commit()


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize(
    "target,expected,error",
    [
        ("missing", 404, "profile_not_found"),
        ("deleted", 404, "profile_not_found"),
        ("occupied", 409, "profile_already_bound"),
    ],
)
async def test_patch_profile_rejection_rolls_back_rename(
    device_api, device_rows, db_pool, target, expected, error
):  # type: ignore[no-untyped-def]
    client, headers = device_api
    profiles, devices = device_rows
    profile = {"missing": str(uuid.uuid4()), "deleted": profiles[2], "occupied": profiles[1]}[
        target
    ]
    response = await client.patch(
        f"/api/admin/devices/{devices[0]}",
        json={"profile_id": profile, "display_name": "Must roll back"},
        headers=headers,
    )
    assert response.status_code == expected, response.text
    assert response.json()["detail"]["type"] == error
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT profile_id::text, display_name FROM gruvax.devices WHERE id = %s::uuid",
                (devices[0],),
            )
        ).fetchone()
    assert row == (profiles[0], "Original name")


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("target", ["missing", "deleted", "occupied"])
async def test_bind_profile_rejection_preserves_generated_code(
    device_api, device_rows, db_pool, target
):  # type: ignore[no-untyped-def]
    client, headers = device_api
    profiles, devices = device_rows
    async with db_pool.connection() as conn:
        fingerprint = await (
            await conn.execute(
                "SELECT fingerprint FROM gruvax.devices WHERE id = %s::uuid", (devices[0],)
            )
        ).fetchone()
    assert fingerprint is not None
    client.cookies.set("gruvax_device_fp", fingerprint[0])
    generated = await client.post("/api/devices/pairing-codes")
    assert generated.status_code == 200, generated.text
    code = generated.json()["code"]
    profile = {"missing": str(uuid.uuid4()), "deleted": profiles[2], "occupied": profiles[1]}[
        target
    ]
    rejected = await client.post(
        "/api/admin/devices/bind",
        json={"code": code, "profile_id": profile, "display_name": "Must roll back"},
        headers=headers,
    )
    assert rejected.status_code == (409 if target == "occupied" else 404), rejected.text
    assert rejected.json()["detail"]["type"] == (
        "profile_already_bound" if target == "occupied" else "profile_not_found"
    )
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT consumed_at FROM gruvax.pairing_codes WHERE code = %s", (code,)
            )
        ).fetchone()
        device = await (
            await conn.execute(
                "SELECT profile_id::text, display_name FROM gruvax.devices WHERE id = %s::uuid",
                (devices[0],),
            )
        ).fetchone()
    assert row == (None,)
    assert device == (profiles[0], "Original name")
    retry = await client.post(
        "/api/admin/devices/bind", json={"code": code, "profile_id": profiles[0]}, headers=headers
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["id"] == devices[0]


@pytest.mark.asyncio(loop_scope="session")
async def test_patch_maps_actual_foreign_key_race(device_api, device_rows, db_pool, monkeypatch):  # type: ignore[no-untyped-def]
    from gruvax.api.admin import devices as module

    client, headers = device_api
    profiles, devices = device_rows

    async def disappearing_preflight(cur, profile_id):  # type: ignore[no-untyped-def]
        # Inject physical deletion in the preflight seam to exercise the real
        # SQL constraint fallback independently of the normal profile row lock.
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (profile_id,))
            await conn.commit()

    monkeypatch.setattr(module, "_require_active_profile", disappearing_preflight)
    response = await client.patch(
        f"/api/admin/devices/{devices[0]}",
        json={"profile_id": profiles[1], "display_name": "Must roll back"},
        headers=headers,
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"]["type"] == "profile_not_found"
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "SELECT profile_id::text, display_name FROM gruvax.devices WHERE id = %s::uuid",
                (devices[0],),
            )
        ).fetchone()
    assert row == (profiles[0], "Original name")

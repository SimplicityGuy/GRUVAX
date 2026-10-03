"""Historical off colors round-trip only through backups, never live controls."""

from __future__ import annotations

import pytest
import yaml

from tests.integration.test_import_settings_cadence import settings_api as _settings_api


settings_api = _settings_api


@pytest.mark.asyncio(loop_scope="session")
async def test_live_settings_exclude_off_color(settings_api) -> None:  # type: ignore[no-untyped-def]
    client, headers, _app = settings_api
    current = await client.get("/api/admin/settings", headers=headers)
    assert current.status_code == 200
    assert "led_color_position" in current.json()
    assert "led_color_all_off" not in current.json()


@pytest.mark.asyncio(loop_scope="session")
async def test_live_settings_reject_off_color_without_writing(settings_api) -> None:  # type: ignore[no-untyped-def]
    client, headers, _app = settings_api
    before = await client.get("/api/admin/export/settings.yaml", headers=headers)
    assert before.status_code == 200
    rejected = await client.put(
        "/api/admin/settings",
        json={"led_color_all_off": "#112233", "led_color_position": "#AABBCC"},
        headers=headers,
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["type"] == "unsupported_setting"
    after = await client.get("/api/admin/export/settings.yaml", headers=headers)
    assert after.status_code == 200
    assert yaml.safe_load(after.text) == yaml.safe_load(before.text)


@pytest.mark.asyncio(loop_scope="session")
async def test_live_position_color_remains_writable(settings_api) -> None:  # type: ignore[no-untyped-def]
    client, headers, _app = settings_api
    original = await client.get("/api/admin/export/settings.yaml", headers=headers)
    assert original.status_code == 200
    try:
        written = await client.put(
            "/api/admin/settings",
            headers=headers,
            json={"led_color_position": "#123456"},
        )
        assert written.status_code == 200
        assert written.json()["updated"] == ["led_color.position"]
        current = await client.get("/api/admin/settings", headers=headers)
        assert current.status_code == 200
        assert current.json()["led_color_position"] == "#123456"
        exported = await client.get("/api/admin/export/settings.yaml", headers=headers)
        assert exported.status_code == 200
        assert (
            yaml.safe_load(exported.text)["led_color"]["all_off"]
            == yaml.safe_load(original.text)["led_color"]["all_off"]
        )
    finally:
        restored = await client.post(
            "/api/admin/import/settings",
            headers=headers,
            content=original.content,
        )
        assert restored.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_historical_off_color_export_reimport_identity(settings_api) -> None:  # type: ignore[no-untyped-def]
    client, headers, _app = settings_api
    original = await client.get("/api/admin/export/settings.yaml", headers=headers)
    assert original.status_code == 200
    assert "all_off" in yaml.safe_load(original.text)["led_color"]
    try:
        imported = await client.post(
            "/api/admin/import/settings",
            headers=headers,
            content=b'led_color:\n  all_off: "#123456"\n',
        )
        assert imported.status_code == 200
        assert imported.json()["updated"] == ["led_color.all_off"]
        exported = await client.get("/api/admin/export/settings.yaml", headers=headers)
        assert exported.status_code == 200
        backup = yaml.safe_load(exported.text)
        assert backup["led_color"]["all_off"] == "#123456"
        assert "auth" not in backup
        altered = await client.post(
            "/api/admin/import/settings",
            headers=headers,
            content=b'led_color:\n  all_off: "#ABCDEF"\n',
        )
        assert altered.status_code == 200
        restored = await client.post(
            "/api/admin/import/settings",
            headers=headers,
            content=exported.content,
        )
        assert restored.status_code == 200
        again = await client.get("/api/admin/export/settings.yaml", headers=headers)
        assert again.status_code == 200
        assert yaml.safe_load(again.text) == backup
    finally:
        restored = await client.post(
            "/api/admin/import/settings",
            headers=headers,
            content=original.content,
        )
        assert restored.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_invalid_legacy_color_rejects_whole_backup(settings_api) -> None:  # type: ignore[no-untyped-def]
    client, headers, _app = settings_api
    before = await client.get("/api/admin/export/settings.yaml", headers=headers)
    assert before.status_code == 200
    rejected = await client.post(
        "/api/admin/import/settings",
        headers=headers,
        content=b'led_color:\n  position: "#AABBCC"\n  all_off: "not-a-color"\n',
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["type"] == "invalid_hex_color"
    after = await client.get("/api/admin/export/settings.yaml", headers=headers)
    assert after.status_code == 200
    assert yaml.safe_load(after.text) == yaml.safe_load(before.text)

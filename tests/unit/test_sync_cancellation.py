"""Deleted-profile cancellation is not reported as a failed sync by its callers."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from gruvax.api.admin import profile_sync as admin_sync
from gruvax.sync import nightly
from gruvax.sync.profile_sync import ProfileDeletedDuringSync


@pytest.mark.asyncio
async def test_admin_background_handles_deleted_profile_as_cancellation(
    monkeypatch, caplog
) -> None:  # type: ignore[no-untyped-def]
    sync = AsyncMock(side_effect=ProfileDeletedDuringSync("deleted"))
    monkeypatch.setattr(admin_sync, "sync_profile", sync)
    with caplog.at_level(logging.INFO, logger=admin_sync.__name__):
        await admin_sync._run_sync_background("deleted-profile", object())
    sync.assert_awaited_once()
    assert "cancelled for deleted profile" in caplog.text
    assert "background sync failed" not in caplog.text


@pytest.mark.asyncio
async def test_startup_catchup_continues_after_deleted_profile(monkeypatch, caplog) -> None:  # type: ignore[no-untyped-def]
    pool, conn, cursor = MagicMock(), MagicMock(), AsyncMock()
    pool.connection.return_value.__aenter__.return_value = conn
    conn.cursor.return_value.__aenter__.return_value = cursor
    cursor.fetchall.return_value = [("deleted-profile",), ("active-profile",)]
    sync = AsyncMock(side_effect=[ProfileDeletedDuringSync("deleted"), {}])
    monkeypatch.setattr(nightly, "sync_profile", sync)
    with caplog.at_level(logging.INFO, logger=nightly.__name__):
        await nightly._startup_catchup_sweep(pool, object(), "24h")
    assert [call.args[0] for call in sync.await_args_list] == ["deleted-profile", "active-profile"]
    assert "cancelled after deletion" in caplog.text
    assert "FAILED" not in caplog.text

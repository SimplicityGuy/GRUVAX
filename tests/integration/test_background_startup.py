"""Real startup catch-up sync may finish or cancel without delaying readiness."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
import pytest

import gruvax.app as app_module
from gruvax.discogsography.errors import NetworkError
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.parametrize("cancel", [False, True])
async def test_real_catchup_serves_while_fetching_and_finishes_safely(db_pool, monkeypatch, cancel):  # type: ignore[no-untyped-def]
    async with db_pool.connection() as conn:
        row = await (
            await conn.execute(
                "INSERT INTO gruvax.profiles (display_name, app_token_encrypted, app_token_revoked) VALUES ('Startup probe', %s, FALSE) RETURNING id::text",
                (encrypt_pat("dscg_synthetic_startup"),),
            )
        ).fetchone()
        await conn.commit()
    assert row is not None
    profile_id = row[0]
    fetching, finish, stopped, nightly = (asyncio.Event() for _ in range(4))

    async def first_page():  # type: ignore[no-untyped-def]
        fetching.set()
        try:
            await finish.wait()
            return {
                "user_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "has_more": False,
                "releases": [
                    {
                        "id": "991002",
                        "title": "Synthetic startup probe",
                        "artist": "Probe",
                        "label": "Probe",
                        "catalog_number": "P2",
                        "year": 2000,
                        "folder_id": 1,
                    }
                ],
            }
        finally:
            stopped.set()

    upstream = SimpleNamespace(first_page=first_page, aclose=AsyncMock())

    def synthetic_client(_base_url, pat):  # type: ignore[no-untyped-def]
        if pat == "dscg_synthetic_startup":
            return upstream
        # Other fixtures may leave eligible profiles. Give each an independent
        # synthetic failure client rather than sharing the probe's data/closure.
        return SimpleNamespace(
            first_page=AsyncMock(
                side_effect=NetworkError("synthetic unrelated upstream unavailable")
            ),
            aclose=AsyncMock(),
        )

    monkeypatch.setattr(profile_sync, "_make_client", synthetic_client)
    monkeypatch.setattr(app_module, "_read_sync_cadence", AsyncMock(return_value="24h"))

    async def loop(*_):  # type: ignore[no-untyped-def]
        nightly.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(app_module, "_sync_loop", loop)
    app = app_module.create_app()
    try:
        async with (
            asyncio.timeout(10),
            app_module.lifespan(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            pool = app.state.db_pool
            await fetching.wait()
            health = await client.get("/api/health")
            assert health.status_code == 200
            assert pool.closed is False
            assert not nightly.is_set()
            if not cancel:
                finish.set()
                await nightly.wait()
                async with db_pool.connection() as conn:
                    collection = await (
                        await conn.execute(
                            "SELECT title FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
                            (profile_id,),
                        )
                    ).fetchall()
                assert collection == [("Synthetic startup probe",)]
                assert app.state.snapshot_registry[profile_id]._by_label
        assert pool.closed
        assert stopped.is_set()
        assert not app.state.background_tasks
        upstream.aclose.assert_awaited_once()
        assert nightly.is_set() is (not cancel)
    finally:
        finish.set()
        async with db_pool.connection() as conn:
            await conn.execute("DELETE FROM gruvax.profiles WHERE id = %s::uuid", (profile_id,))
            await conn.commit()

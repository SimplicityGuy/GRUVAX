"""A real unmigrated database must not prevent the HTTP listener starting."""

import asyncio
from uuid import uuid4

from httpx import ASGITransport, AsyncClient
from psycopg import AsyncConnection, sql
import pytest

import gruvax.app as app_module
from gruvax.db.pool import _conninfo
from gruvax.settings import settings


@pytest.mark.asyncio
async def test_unmigrated_database_serves_degraded_then_closes_pool(monkeypatch):  # type: ignore[no-untyped-def]
    name = f"startup_probe_{uuid4().hex}"
    conninfo = _conninfo(settings.DATABASE_URL)
    admin = await AsyncConnection.connect(conninfo, autocommit=True)
    original_factory = app_module.create_pool
    pools = []

    def own_pool(**kwargs):  # type: ignore[no-untyped-def]
        pool = original_factory(**kwargs)
        pools.append(pool)
        return pool

    try:
        await admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        monkeypatch.setattr(
            settings, "DATABASE_URL", settings.DATABASE_URL.rsplit("/", 1)[0] + "/" + name
        )
        monkeypatch.setattr(app_module, "create_pool", own_pool)
        app = app_module.create_app()
        async with (
            asyncio.timeout(10),
            app_module.lifespan(app),
            AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client,
        ):
            health = await client.get("/api/health")
            assert health.status_code == 200
            assert health.json()["status"] == "degraded"
            search = await client.get("/api/search", params={"q": "synthetic"})
            locate = await client.get("/api/locate", params={"label": "Synthetic", "catno": "P1"})
            assert search.status_code == 503
            assert locate.status_code == 503
        assert len(pools) == 1 and pools[0].closed
        assert not app.state.background_tasks
    finally:
        await admin.execute(
            sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
        )
        await admin.close()

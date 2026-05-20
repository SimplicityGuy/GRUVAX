"""Integration tests for GET /api/health.

Tests:
  - test_view_probe: health endpoint returns 200 with all expected keys
    and discogsography_view_check == "ok" against the seeded Postgres.
  - test_health_keys: all required keys present in response.
  - test_degraded_view_path: simulate a failed v_collection probe by
    directly patching app.state.discogsography_view_ok = False and
    confirming status becomes "degraded".
  - test_mqtt_degraded_is_ok: mqtt degraded does not change overall status.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.app import create_app


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    ``asgi_lifespan.LifespanManager`` correctly triggers the FastAPI
    lifespan (DB pool, v_collection probe, boundary cache load, MQTT stub)
    before yielding the client.

    ``db_pool`` is the session-scoped fixture from conftest — ensures the
    DB is running before the app boots.
    """
    app = create_app()
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac:
            yield ac, app


@pytest.mark.asyncio(loop_scope="session")
async def test_view_probe(client) -> None:  # type: ignore[no-untyped-def]
    """Startup probe reaches gruvax.v_collection; health reports view OK."""
    ac, _app = client
    response = await ac.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["discogsography_view_check"] == "ok", (
        f"Expected view probe OK but got: {body}"
    )
    assert body["db"] == "ok"
    assert body["status"] == "ok"


@pytest.mark.asyncio(loop_scope="session")
async def test_health_keys(client) -> None:  # type: ignore[no-untyped-def]
    """All required keys are present in the health response."""
    ac, _app = client
    response = await ac.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    required_keys = {"status", "db", "discogsography_view_check", "mqtt", "started_at", "version"}
    assert required_keys.issubset(body.keys()), (
        f"Missing keys: {required_keys - body.keys()}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_started_at_is_iso8601(client) -> None:  # type: ignore[no-untyped-def]
    """started_at is a non-empty ISO-8601 string."""
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    started_at = body.get("started_at", "")
    assert started_at, "started_at must be non-empty"
    assert "T" in started_at, f"started_at not ISO-8601: {started_at!r}"


@pytest.mark.asyncio(loop_scope="session")
async def test_degraded_view_path(client) -> None:  # type: ignore[no-untyped-def]
    """When discogsography_view_ok is False, status == 'degraded'."""
    ac, app = client
    original = app.state.discogsography_view_ok
    try:
        app.state.discogsography_view_ok = False
        response = await ac.get("/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "degraded"
        assert body["discogsography_view_check"] == "failed"
    finally:
        app.state.discogsography_view_ok = original


@pytest.mark.asyncio(loop_scope="session")
async def test_mqtt_degraded_is_overall_ok(client) -> None:  # type: ignore[no-untyped-def]
    """MQTT degraded alone does NOT degrade the overall status.

    MQTT is non-critical (DEP-01) — db + view_ok determines overall status.
    """
    ac, app = client
    original = app.state.mqtt_ok
    try:
        app.state.mqtt_ok = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["mqtt"] == "degraded"
        if app.state.db_ok and app.state.discogsography_view_ok:
            assert body["status"] == "ok"
    finally:
        app.state.mqtt_ok = original

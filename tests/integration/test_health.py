"""Integration tests for GET /api/health.

Tests:
  - test_view_probe: health endpoint returns 200 with all expected keys
    and discogsography_view_check == "ok" against the seeded Postgres.
  - test_health_keys: all required keys present in response (including
    sync_age_seconds added in Plan 03, OBS-06).
  - test_version_is_git_sha: version field equals GIT_SHA from _version.py
    (not the hardcoded "0.1.0" string) — OBS-01/OBS-04.
  - test_sync_age_seconds_type: sync_age_seconds is a float or null.
  - test_no_secrets_in_health: health body contains no session_secret,
    database_url, or pin keys (T-08-09 mitigation).
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

try:
    from gruvax._version import GIT_SHA as _GIT_SHA
except ImportError:
    _GIT_SHA = "dev"


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
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, app


@pytest.mark.asyncio(loop_scope="session")
async def test_view_probe(client) -> None:  # type: ignore[no-untyped-def]
    """Startup probe reaches gruvax.v_collection; health reports view OK."""
    ac, _app = client
    response = await ac.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["discogsography_view_check"] == "ok", f"Expected view probe OK but got: {body}"
    assert body["db"] == "ok"
    assert body["status"] == "ok"


@pytest.mark.asyncio(loop_scope="session")
async def test_index_html_no_store(client) -> None:  # type: ignore[no-untyped-def]
    """index.html is served with Cache-Control: no-store (T-01-13).

    Skips when the SPA bundle has not been built into ``static/`` in this
    environment (the StaticFiles mount is then absent and ``/`` 404s).
    """
    ac, _app = client
    response = await ac.get("/")
    if response.status_code == 404:
        pytest.skip("SPA static/ not built — StaticFiles mount absent")
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("text/html")
    assert response.headers.get("cache-control") == "no-store"


@pytest.mark.asyncio(loop_scope="session")
async def test_health_keys(client) -> None:  # type: ignore[no-untyped-def]
    """All required keys are present in the health response (OBS-06 adds sync_age_seconds)."""
    ac, _app = client
    response = await ac.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    required_keys = {
        "status",
        "db",
        "discogsography_view_check",
        "mqtt",
        "started_at",
        "version",
        "sync_age_seconds",
    }
    assert required_keys.issubset(body.keys()), f"Missing keys: {required_keys - body.keys()}"


@pytest.mark.asyncio(loop_scope="session")
async def test_version_is_git_sha(client) -> None:  # type: ignore[no-untyped-def]
    """version field equals GIT_SHA from _version.py — NOT the hardcoded "0.1.0" string.

    In dev the placeholder is "dev"; in Docker builds it is the actual git SHA.
    The critical invariant is that the hardcode is gone (OBS-01/OBS-04).
    """
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    assert body["version"] == _GIT_SHA, (
        f"version should match _version.GIT_SHA ({_GIT_SHA!r}) but got {body['version']!r}"
    )
    assert body["version"] != "0.1.0", "version must not be the hardcoded '0.1.0' fallback"


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_age_seconds_type(client) -> None:  # type: ignore[no-untyped-def]
    """sync_age_seconds is a float (seconds since last sync) or null (OBS-06).

    It may be null when the background staleness task has not yet run,
    or when v_collection is empty. Both are valid states.
    """
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    value = body.get("sync_age_seconds")
    assert value is None or isinstance(value, (int, float)), (
        f"sync_age_seconds must be float or null but got {type(value).__name__!r}: {value!r}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_no_secrets_in_health(client) -> None:  # type: ignore[no-untyped-def]
    """Health body contains no session_secret, database_url, or pin keys (T-08-09)."""
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    forbidden = {"session_secret", "database_url", "pin"}
    leaked = forbidden & body.keys()
    assert not leaked, f"Health response leaks secret keys: {leaked}"


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

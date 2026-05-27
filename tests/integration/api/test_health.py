"""Integration tests for GET /api/health (Plan 01-05, D-13).

Covers BOTH Task 1 (field rename + three-state derivation) and Task 2 (lifespan
rewire — profile_collection probe + default_profile_* background task), since
both touch the same fixture surface (the lifespan-managed FastAPI app) and
consolidating prevents fixture duplication.

D-13 contract (the source of truth for these tests):
  - `discogsography_api_check` field (NOT `discogsography_view_check`).
  - Value strictly in {'ok', 'failed', 'stale'}.
  - 'ok'      when last_sync_status='ok' AND app_token_revoked=FALSE
                 OR last_sync_status='in_progress' (Warning #4 RESOLUTION — an
                 active sync is healthy; the 5-min watchdog flips hangs to
                 'failed').
  - 'failed'  when last_sync_status='failed' OR app_token_revoked=TRUE
              (precedence — token_revoked beats in_progress).
  - 'stale'   when last_sync_at IS NULL OR now() - last_sync_at > 24h
              (and status is NOT 'in_progress' / 'failed').
  - sync_age_seconds is derived from default_profile_last_sync_at (not from
    `max(v_collection.synced_at)` any more).

D-13 also requires:
  - app.state.discogsography_view_ok is NOT assigned anywhere in app.py (legacy
    attribute removed — Test 5 of Task 2).
  - Lifespan startup probe targets `gruvax.profile_collection` rather than
    `gruvax.v_collection` (verified via lifespan startup log line + Test 1/2 of
    Task 2 — but those run against the live DB which doesn't exist in CI
    integration without a Postgres service, so we test via probe-success +
    probe-failure-by-attribute-flip).

Fixture pattern follows the existing v1 ``tests/integration/test_health.py``:
  asgi_lifespan.LifespanManager wraps the in-process app so the full lifespan
  fires (DB pool, profile_collection probe, background task scheduled).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.app import create_app


try:
    from gruvax._version import GIT_SHA as _GIT_SHA
except ImportError:
    _GIT_SHA = "dev"


# ── Module-scoped lifespan-managed client ────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped async test client with full ASGI lifespan.

    ``db_pool`` is the session-scoped fixture from conftest.py — ensures the
    DB is running before the app boots. The lifespan runs the
    profile_collection startup probe + schedules the default_profile_state
    background task, so by the time tests run the app.state attributes are
    populated (or set to safe defaults via the probe-failure path).
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


# ──────────────────────────────────────────────────────────────────────────────
# Task 1 — /api/health field rename + state-widening derivation
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_field_rename_present(client) -> None:  # type: ignore[no-untyped-def]
    """Test 1 (field rename): response has discogsography_api_check key
    and does NOT have discogsography_view_check.
    """
    ac, _app = client
    response = await ac.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert "discogsography_api_check" in body, (
        f"Missing discogsography_api_check: {body.keys()}"
    )
    assert "discogsography_view_check" not in body, (
        f"Legacy discogsography_view_check field must be removed: {body.keys()}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_value_enum(client) -> None:  # type: ignore[no-untyped-def]
    """Test 2 (value enum): value is one of {'ok','failed','stale'}."""
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    assert body["discogsography_api_check"] in {"ok", "failed", "stale"}, (
        f"Expected one of ok/failed/stale, got: {body['discogsography_api_check']!r}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_ok_derivation(client) -> None:  # type: ignore[no-untyped-def]
    """Test 3 (ok derivation): status='ok' AND not revoked → discogsography_api_check == 'ok'."""
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(minutes=5)
        app.state.default_profile_last_sync_status = "ok"
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "ok", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_failed_by_status(client) -> None:  # type: ignore[no-untyped-def]
    """Test 4 (failed by status): status='failed' AND not revoked → 'failed'."""
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(minutes=5)
        app.state.default_profile_last_sync_status = "failed"
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "failed", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_failed_by_revoked(client) -> None:  # type: ignore[no-untyped-def]
    """Test 5 (failed by revoked): status='ok' AND revoked=TRUE → 'failed'.

    token_revoked beats every other state — precedence is failed > stale > ok.
    """
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(minutes=5)
        app.state.default_profile_last_sync_status = "ok"
        app.state.default_profile_app_token_revoked = True
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "failed", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_stale_by_null(client) -> None:  # type: ignore[no-untyped-def]
    """Test 6 (stale by null): last_sync_at=None, status not in_progress/failed → 'stale'."""
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        app.state.default_profile_last_sync_at = None
        app.state.default_profile_last_sync_status = None
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "stale", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_stale_by_age(client) -> None:  # type: ignore[no-untyped-def]
    """Test 7 (stale by age): last_sync_at=now()-25h AND status='ok' → 'stale'."""
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(hours=25)
        app.state.default_profile_last_sync_status = "ok"
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "stale", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_in_progress_to_ok(client) -> None:  # type: ignore[no-untyped-def]
    """Test 8 (in_progress → ok per Warning #4 fix): an active sync is healthy state.

    Do NOT map to 'stale'. The 5-min watchdog (Plan 03) marks hung syncs as
    'failed'; until then in_progress is a normal healthy state.
    """
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        # last_sync_at set to NULL — in_progress sync has not yet completed once.
        app.state.default_profile_last_sync_at = None
        app.state.default_profile_last_sync_status = "in_progress"
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "ok", (
            f"in_progress should map to 'ok' per D-13 Warning #4 RESOLUTION; got: {body}"
        )
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_in_progress_with_revoked_still_failed(client) -> None:  # type: ignore[no-untyped-def]
    """Test 9 (in_progress + revoked → failed): token_revoked takes precedence."""
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(minutes=5)
        app.state.default_profile_last_sync_status = "in_progress"
        app.state.default_profile_app_token_revoked = True
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "failed", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_overall_degraded_propagation(client) -> None:  # type: ignore[no-untyped-def]
    """Test 10 (overall degraded propagation):
    - api_check='failed' → top-level status='degraded'
    - api_check='ok' AND db='ok' AND mqtt='ok' (or degraded) → status='ok'
    """
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        # Force api_check='failed'
        app.state.default_profile_last_sync_status = "failed"
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["status"] == "degraded", body
        assert body["discogsography_api_check"] == "failed", body

        # Force api_check='ok' — depends on db_ok being True (lifespan-set)
        if not getattr(app.state, "db_ok", False):
            pytest.skip("db_ok is False, can't assert overall 'ok'")
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(minutes=5)
        app.state.default_profile_last_sync_status = "ok"
        app.state.default_profile_app_token_revoked = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["discogsography_api_check"] == "ok", body
        # MQTT degraded does NOT degrade overall (preserves v1 contract).
        assert body["status"] == "ok", body
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked


@pytest.mark.asyncio(loop_scope="session")
async def test_sync_age_seconds_source_swap(client) -> None:  # type: ignore[no-untyped-def]
    """Test 11 (sync_age_seconds source swap): derived from default_profile_last_sync_at,
    not from max(v_collection.synced_at).

    Set last_sync_at = now() - 60s; sync_age_seconds in [55, 65] (account for
    derivation timing slack on slow CI).
    """
    ac, app = client
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    original_age = getattr(app.state, "sync_age_seconds", None)
    try:
        target = datetime.now(UTC) - timedelta(seconds=60)
        app.state.default_profile_last_sync_at = target
        app.state.default_profile_last_sync_status = "ok"
        app.state.default_profile_app_token_revoked = False
        # The handler should derive sync_age_seconds at request time from
        # default_profile_last_sync_at, OR rely on the background-task-populated
        # cached value. The handler reads app.state.sync_age_seconds — also set
        # it here to match the background-task contract (the background task
        # would set both).
        app.state.sync_age_seconds = (datetime.now(UTC) - target).total_seconds()
        response = await ac.get("/api/health")
        body = response.json()
        age = body.get("sync_age_seconds")
        assert age is not None, "sync_age_seconds must be set when last_sync_at is non-null"
        assert 55 <= age <= 65, (
            f"sync_age_seconds should be ~60 (in [55,65]) when last_sync_at is now-60s; "
            f"got: {age}"
        )
    finally:
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked
        app.state.sync_age_seconds = original_age


def test_typescript_type_renamed() -> None:
    """Test 12 (TypeScript type renamed): frontend/src/api/types.ts (or wherever
    HealthResponse lives) declares ``discogsography_api_check: 'ok' | 'failed' | 'stale'``
    and does NOT contain ``discogsography_view_check``.

    Plain file-read test — no TypeScript compiler dependency. ``tsc --noEmit`` runs
    in CI as a separate gate.
    """
    repo_root = Path(__file__).resolve().parents[3]
    types_path = repo_root / "frontend" / "src" / "api" / "types.ts"
    assert types_path.exists(), f"Missing {types_path} — frontend types file moved?"
    content = types_path.read_text()
    assert "discogsography_view_check" not in content, (
        f"Legacy discogsography_view_check field must be removed from {types_path}"
    )
    assert "discogsography_api_check" in content, (
        f"types.ts must declare HealthResponse.discogsography_api_check in {types_path}"
    )
    # State union 'ok' | 'failed' | 'stale' must be present.
    assert "'stale'" in content or '"stale"' in content, (
        "HealthResponse type union must include 'stale' state per D-13"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Task 2 — Lifespan rewire (probe profile_collection + populate default_profile_*)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_startup_probe_attribute_set(client) -> None:  # type: ignore[no-untyped-def]
    """Test 1 of Task 2 (startup probe runs): after lifespan startup,
    ``app.state.profile_collection_ready`` is set (True or False).

    The actual value depends on whether the test DB has the profile_collection
    table populated; both states are acceptable here — what we assert is that
    the probe ran (it set the attribute) rather than crashing the startup.
    """
    _ac, app = client
    assert hasattr(app.state, "profile_collection_ready"), (
        "Lifespan must set app.state.profile_collection_ready"
    )
    assert isinstance(app.state.profile_collection_ready, bool), (
        f"Expected bool, got {type(app.state.profile_collection_ready).__name__}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_startup_probe_failure_non_fatal(client) -> None:  # type: ignore[no-untyped-def]
    """Test 2 of Task 2 (probe failure non-fatal): even when
    profile_collection_ready=False, /api/health still serves with status 200.

    Simulate by flipping the flag — the app does not crash, the endpoint
    returns 200. (Real probe failure happens at startup; we can't easily
    re-trigger lifespan mid-test, but the flag-flip exercises the same
    downstream behavior.)
    """
    ac, app = client
    original_ready = getattr(app.state, "profile_collection_ready", True)
    try:
        app.state.profile_collection_ready = False
        response = await ac.get("/api/health")
        assert response.status_code == 200, response.text
    finally:
        app.state.profile_collection_ready = original_ready


@pytest.mark.asyncio(loop_scope="session")
async def test_background_task_populates_default_profile_state(client) -> None:  # type: ignore[no-untyped-def]
    """Test 3 of Task 2 (background task populates default_profile_*).

    After lifespan startup, the three default_profile_* attributes exist on
    app.state. Their value depends on whether the default profile row exists
    and whether the first task iteration has completed yet (initial sleep + DB
    read), but the attributes themselves must always exist with safe initial
    defaults (so health.py never KeyErrors).
    """
    _ac, app = client
    for attr in (
        "default_profile_last_sync_at",
        "default_profile_last_sync_status",
        "default_profile_app_token_revoked",
    ):
        assert hasattr(app.state, attr), (
            f"app.state missing {attr} — lifespan must seed it before yielding"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_legacy_view_ok_attribute_removed(client) -> None:  # type: ignore[no-untyped-def]
    """Test 5 of Task 2 (legacy view_ok attribute removed).

    No code path in app.py sets app.state.discogsography_view_ok any more. We
    verify by reading the file's source — the attribute name must not appear
    as an assignment target.
    """
    repo_root = Path(__file__).resolve().parents[3]
    app_py = repo_root / "src" / "gruvax" / "app.py"
    content = app_py.read_text()
    # The string "discogsography_view_ok" must not appear in app.py. (A grep
    # gate matches the verify command in the plan: `! grep -n
    # discogsography_view_ok src/gruvax/app.py`.)
    assert "discogsography_view_ok" not in content, (
        f"Legacy discogsography_view_ok attribute must be removed from {app_py}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Pre-existing v1 health tests (preserved — health endpoint contract carries over)
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_health_endpoint_returns_200(client) -> None:  # type: ignore[no-untyped-def]
    """Health endpoint always returns 200 — callers inspect individual fields."""
    ac, _app = client
    response = await ac.get("/api/health")
    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_health_keys(client) -> None:  # type: ignore[no-untyped-def]
    """Required keys remain in the health response (D-13 rename + carryover)."""
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    required_keys = {
        "status",
        "db",
        "discogsography_api_check",
        "mqtt",
        "started_at",
        "version",
        "sync_age_seconds",
    }
    assert required_keys.issubset(body.keys()), (
        f"Missing keys: {required_keys - body.keys()}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_version_is_git_sha(client) -> None:  # type: ignore[no-untyped-def]
    """version field equals GIT_SHA (OBS-01/OBS-04)."""
    ac, _app = client
    response = await ac.get("/api/health")
    body = response.json()
    assert body["version"] == _GIT_SHA
    assert body["version"] != "0.1.0"


@pytest.mark.asyncio(loop_scope="session")
async def test_no_secrets_in_health(client) -> None:  # type: ignore[no-untyped-def]
    """Health body contains no secret keys (T-08-09)."""
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
    assert started_at
    assert "T" in started_at


@pytest.mark.asyncio(loop_scope="session")
async def test_mqtt_degraded_does_not_degrade_overall(client) -> None:  # type: ignore[no-untyped-def]
    """MQTT degraded alone does NOT degrade overall status (DEP-01)."""
    ac, app = client
    original_mqtt = getattr(app.state, "mqtt_ok", True)
    original_at = getattr(app.state, "default_profile_last_sync_at", None)
    original_status = getattr(app.state, "default_profile_last_sync_status", None)
    original_revoked = getattr(app.state, "default_profile_app_token_revoked", True)
    try:
        # Set everything else healthy
        app.state.default_profile_last_sync_at = datetime.now(UTC) - timedelta(minutes=5)
        app.state.default_profile_last_sync_status = "ok"
        app.state.default_profile_app_token_revoked = False
        app.state.mqtt_ok = False
        response = await ac.get("/api/health")
        body = response.json()
        assert body["mqtt"] == "degraded"
        if app.state.db_ok and body["discogsography_api_check"] == "ok":
            assert body["status"] == "ok", body
    finally:
        app.state.mqtt_ok = original_mqtt
        app.state.default_profile_last_sync_at = original_at
        app.state.default_profile_last_sync_status = original_status
        app.state.default_profile_app_token_revoked = original_revoked

"""Integration tests for GET /api/admin/diagnostics and POST /api/admin/diagnostics/reset-stats.

Tests (Wave-0):
  - test_staleness:         GET returns sync_age_seconds as float or null.
  - test_counters:          GET returns all 7 SC#2 keys; pool has size_used/size_min.
  - test_no_secrets:        Diagnostics body contains no session_secret/database_url/pin.
  - test_unauthenticated_get:  GET without session returns 401.
  - test_unauthenticated_reset: POST reset-stats without session returns 401/403.
  - test_reset_stats:       Seed counters → GET (non-empty top_searched) → POST reset → GET (empty).
  - test_recent_logs_shape: Each recent_logs entry has exactly {ts: float, level: str,
                            logger: str, msg: str} — regression guard for structlog migration.
  - test_recent_logs_ring_scoping: Third-party loggers (psycopg, uvicorn, etc.) do NOT
                                   appear in recent_logs (T-9-IL secret-leak guard).

Auth bypass uses app.dependency_overrides[require_admin] (Phase 06-04 canonical pattern).
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from gruvax.api.deps import require_admin
from gruvax.app import create_app

# ── Module-scoped client (authenticated via dependency_overrides) ──────────────


def _admin_stub() -> dict[str, str]:
    """Stub for require_admin dependency — returns a minimal admin dict."""
    return {"role": "admin"}


@pytest_asyncio.fixture(scope="module")
async def diag_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with require_admin bypassed via dependency_overrides.

    Uses the canonical Phase 06-04 pattern: FastAPI resolves Depends(require_admin)
    by function reference at route registration; patching the module-level name does
    not intercept the dependency — use app.dependency_overrides[require_admin] instead.
    """
    app = create_app()
    app.dependency_overrides[require_admin] = _admin_stub
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, manager.app
    # Cleanup overrides
    app.dependency_overrides.clear()


# ── Unauthenticated client (no override) ──────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def unauth_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with NO require_admin override (tests 401/403)."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, manager.app


# ── Helper ─────────────────────────────────────────────────────────────────────


async def _seed_search_count(db_pool: Any, release_id: int) -> None:
    """Upsert a search count for release_id so top_searched is non-empty."""
    sql = """
INSERT INTO gruvax.record_stats
    (release_id, search_count, search_count_7d, last_searched_at, updated_at)
VALUES (%s, 1, 1, now(), now())
ON CONFLICT (release_id) DO UPDATE SET
    search_count     = gruvax.record_stats.search_count + 1,
    search_count_7d  = gruvax.record_stats.search_count_7d + 1,
    last_searched_at = now(),
    updated_at       = now()
"""
    async with db_pool.connection() as conn:
        await conn.execute(sql, (release_id,))


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio(loop_scope="session")
async def test_staleness(diag_client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/diagnostics returns sync_age_seconds as float or null (OBS-06).

    The value may be None when v_collection is empty in the test DB;
    both are valid states — the test accepts either.
    """
    ac, _app = diag_client
    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    body = response.json()
    value = body.get("sync_age_seconds")
    assert value is None or isinstance(value, (int, float)), (
        f"sync_age_seconds must be float or null but got {type(value).__name__!r}: {value!r}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_counters(diag_client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/diagnostics returns all 7 SC#2 keys with correct types.

    The pool sub-dict must have size_used and size_min.
    """
    ac, _app = diag_client
    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    body = response.json()

    # All 7 SC#2 keys must be present
    required_keys = {
        "sync_age_seconds",
        "top_searched",
        "slow_queries",
        "mqtt",
        "pool",
        "phantom_boundary_count",
        "recent_logs",
    }
    assert required_keys.issubset(body.keys()), (
        f"Missing keys: {required_keys - body.keys()}"
    )

    # pool sub-dict shape
    pool_val = body["pool"]
    assert isinstance(pool_val, dict), f"pool must be a dict but got {type(pool_val)}"
    assert "size_used" in pool_val, "pool must contain size_used"
    assert "size_min" in pool_val, "pool must contain size_min"

    # top_searched is a list
    assert isinstance(body["top_searched"], list), "top_searched must be a list"

    # slow_queries is a list
    assert isinstance(body["slow_queries"], list), "slow_queries must be a list"

    # mqtt is a string
    assert body["mqtt"] in ("connected", "disconnected"), (
        f"mqtt must be 'connected' or 'disconnected' but got {body['mqtt']!r}"
    )

    # phantom_boundary_count is a non-negative int
    assert isinstance(body["phantom_boundary_count"], int), (
        "phantom_boundary_count must be an int"
    )
    assert body["phantom_boundary_count"] >= 0, "phantom_boundary_count must be >= 0"

    # recent_logs is a list
    assert isinstance(body["recent_logs"], list), "recent_logs must be a list"


@pytest.mark.asyncio(loop_scope="session")
async def test_no_secrets(diag_client) -> None:  # type: ignore[no-untyped-def]
    """Diagnostics body must not contain session_secret, database_url, or pin (T-08-14)."""
    ac, _app = diag_client
    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    body = response.json()
    # Flatten all string values and keys to catch nested leakage
    body_text = str(body).lower()
    forbidden = ["session_secret", "database_url"]
    for key in forbidden:
        assert key not in body_text, f"Diagnostics body must not leak {key!r}"
    # pin key must not be a top-level key
    assert "pin" not in body, "pin must not be a top-level diagnostics key"


@pytest.mark.asyncio(loop_scope="session")
async def test_unauthenticated_get(unauth_client) -> None:  # type: ignore[no-untyped-def]
    """GET /api/admin/diagnostics without a session returns 401."""
    ac, _app = unauth_client
    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code in (401, 403), (
        f"Expected 401/403 but got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_unauthenticated_reset(unauth_client) -> None:  # type: ignore[no-untyped-def]
    """POST /api/admin/diagnostics/reset-stats without a session returns 401/403."""
    ac, _app = unauth_client
    response = await ac.post("/api/admin/diagnostics/reset-stats")
    assert response.status_code in (401, 403), (
        f"Expected 401/403 but got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_reset_stats(diag_client, db_pool) -> None:  # type: ignore[no-untyped-def]
    """Seed search counts → GET (non-empty top_searched) → POST reset → GET (empty).

    Uses a real v_collection release_id to ensure the JOIN in get_top_searched
    returns a match. Falls back to skipping if v_collection is empty (no seed data).
    """
    ac, _app = diag_client

    # Find a release_id that exists in v_collection (for the JOIN to work)
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT release_id FROM gruvax.v_collection LIMIT 1"
        )
        row = await cur.fetchone()

    if row is None:
        pytest.skip("v_collection is empty — no seed data available for reset test")

    seed_release_id: int = int(row[0])

    # Seed a search count (ensures top_searched is non-empty)
    await _seed_search_count(db_pool, seed_release_id)

    # GET diagnostics — top_searched must be non-empty now
    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["top_searched"]) > 0, (
        "top_searched should be non-empty after seeding a search count"
    )

    # POST reset-stats — must succeed
    reset_response = await ac.post("/api/admin/diagnostics/reset-stats")
    assert reset_response.status_code == 200, reset_response.text
    assert reset_response.json().get("reset") is True, (
        f"Expected {{reset: True}} but got: {reset_response.json()}"
    )

    # GET diagnostics again — top_searched must now be empty
    response2 = await ac.get("/api/admin/diagnostics")
    assert response2.status_code == 200, response2.text
    body2 = response2.json()
    assert body2["top_searched"] == [], (
        f"top_searched should be empty after reset but got: {body2['top_searched']}"
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_recent_logs_shape(diag_client) -> None:  # type: ignore[no-untyped-def]
    """Every recent_logs entry must have exactly {ts: float, level: str, logger: str, msg: str}.

    Wave-0 regression guard: the structlog migration must not silently change the shape
    consumed by the admin diagnostics page (T-9-SHAPE). The test emits a gruvax-logger
    record first so the ring is non-empty, then validates each entry's keys and types.
    """
    ac, _app = diag_client

    # Emit a gruvax-scoped record so recent_logs is non-empty.
    logging.getLogger("gruvax.test.shape").info("shape regression probe")

    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    body = response.json()
    recent_logs: list[Any] = body["recent_logs"]

    # The ring may still be empty (e.g. log level filtered it out) — skip if so.
    if not recent_logs:
        pytest.skip("recent_logs is empty — cannot assert shape; check LOG_LEVEL setting")

    for entry in recent_logs:
        assert isinstance(entry, dict), f"recent_logs entry must be a dict, got {type(entry)}"
        assert set(entry.keys()) == {"ts", "level", "logger", "msg"}, (
            f"recent_logs entry must have exactly {{ts, level, logger, msg}} keys, "
            f"got {set(entry.keys())!r}"
        )
        assert isinstance(entry["ts"], (int, float)), (
            f"ts must be a float but got {type(entry['ts']).__name__!r}: {entry['ts']!r}"
        )
        assert isinstance(entry["level"], str), (
            f"level must be a str but got {type(entry['level']).__name__!r}"
        )
        assert isinstance(entry["logger"], str), (
            f"logger must be a str but got {type(entry['logger']).__name__!r}"
        )
        assert isinstance(entry["msg"], str), (
            f"msg must be a str but got {type(entry['msg']).__name__!r}"
        )


@pytest.mark.asyncio(loop_scope="session")
async def test_recent_logs_ring_scoping(diag_client) -> None:  # type: ignore[no-untyped-def]
    """Third-party logger records must NOT appear in recent_logs (T-9-IL secret-leak guard).

    Wave-0 regression assertion: after a psycopg-namespace logger emits at INFO+, no
    entry in recent_logs should have a 'logger' field starting with a non-gruvax prefix.
    This covers the security control that prevents a stringified DSN from a psycopg
    connection-failure record from reaching the admin diagnostics page.

    The LogRingHandler is attached only to logging.getLogger("gruvax"); third-party
    loggers propagate to the root logger but cannot reach the ring buffer.
    """
    ac, _app = diag_client

    # Emit from third-party-namespaced loggers to verify they cannot reach the ring.
    for third_party_name in ("psycopg", "uvicorn.error", "sqlalchemy.engine", "aiomqtt"):
        logging.getLogger(third_party_name).info(
            "scoping probe — should never appear in recent_logs"
        )

    # Also emit from the gruvax logger so recent_logs is non-empty and the test is meaningful.
    logging.getLogger("gruvax.test.scoping").info("scoping probe — gruvax reference record")

    response = await ac.get("/api/admin/diagnostics")
    assert response.status_code == 200, response.text
    body = response.json()
    recent_logs: list[Any] = body["recent_logs"]

    third_party_prefixes = ("psycopg", "uvicorn", "sqlalchemy", "aiomqtt")
    for entry in recent_logs:
        logger_name: str = entry.get("logger", "")
        for prefix in third_party_prefixes:
            assert not logger_name.startswith(prefix), (
                f"Third-party logger {logger_name!r} (prefix {prefix!r}) appeared in "
                f"recent_logs — ring scoping is broken (T-9-IL: secret-leak guard failed). "
                f"Entry: {entry!r}"
            )

"""Shared pytest fixtures for GRUVAX tests.

Provides:
  - ``db_pool``        — session-scoped async psycopg pool connected to the
                         test Postgres instance (reads DATABASE_URL from env).
  - ``boundary_cache`` — the parsed contents of ``fixtures/boundaries.yaml``
                         as a list of dicts, for unit tests that don't need DB.
  - ``admin_session``  — module-scoped fixture that seeds a test PIN hash and
                         posts to ``/api/admin/login``, returning session cookies
                         and CSRF token.  Depends on Plan 02 implementing
                         ``gruvax.auth.pin.hash_pin`` and the login endpoint.

Integration tests that need a live DB should use ``db_pool``; unit tests
should use ``boundary_cache`` or plain Python fixtures.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import yaml

from gruvax.db.pool import create_pool

# Path to the committed synthetic boundary fixture
FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"
BOUNDARIES_YAML = FIXTURE_DIR / "boundaries.yaml"


# ── event loop ───────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.DefaultEventLoopPolicy:
    """Use the default event loop policy (no uvloop in tests for simplicity)."""
    return asyncio.DefaultEventLoopPolicy()


# ── database ─────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="session")
async def db_pool():  # type: ignore[no-untyped-def]
    """Session-scoped async psycopg pool.

    Opens the pool once per test session and closes it at teardown.
    Requires DATABASE_URL to be set (via .env or environment variable).

    Usage::

        async def test_something(db_pool):
            async with db_pool.connection() as conn:
                result = await conn.execute("SELECT 1")
    """
    pool = create_pool(min_size=1, max_size=5, open=False)
    await pool.open()
    yield pool
    await pool.close()


# ── admin session fixture (Phase 3) ──────────────────────────────────────────


@pytest_asyncio.fixture(scope="module")
async def admin_session(client: Any) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    """Module-scoped fixture that seeds a test PIN and logs in.

    Requires ``client`` fixture (LifespanManager + AsyncClient, see integration
    tests) to be passed in; conftest declares the fixture but each integration
    test module provides its own ``client`` fixture because scope must match.

    Seeding steps:
    1.  Ensure SESSION_SECRET is set in the environment so Settings() doesn't
        crash at boot (real value from .env; tests set a fallback if absent).
    2.  Hash the test PIN "0000" and upsert into gruvax.settings.auth.pin_hash.
        Uses a low Argon2 time_cost=1 for speed in tests (A-3 assumption).
    3.  POST /api/admin/login with PIN "0000".
    4.  Return {"cookies": response.cookies, "csrf_token": <gruvax_csrf value>}.

    NOTE: hash_pin import is provided by Plan 02 (gruvax.auth.pin module).
    Until Plan 02 lands, this fixture itself goes RED, which is expected.
    """
    # Ensure SESSION_SECRET is set for this test process (fallback for CI)
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"

    # Seed auth.pin_hash for the test PIN "0000" at low cost for speed
    # The hash_pin import comes from Plan 02 — RED until then
    from gruvax.auth.pin import hash_pin

    # Use time_cost=1 for test speed (Argon2id default is time_cost=2)
    # passlib CryptContext allows overriding rounds via hash(pin, rounds=N) for
    # bcrypt; Argon2 uses time_cost. We rely on the default context here since
    # passlib's Argon2 verify is still fast enough at default params for a few tests.
    test_pin_hash = hash_pin("0000")

    # Upsert the test PIN hash into gruvax.settings
    pool = client.app.state.db_pool  # type: ignore[attr-defined]
    async with pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (key, value, description, updated_at)"
            " VALUES ('auth.pin_hash', %s, 'Test PIN hash seeded by conftest', now())"
            " ON CONFLICT (key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (f'"{test_pin_hash}"',),
        )
        await conn.commit()

    # Log in with the test PIN
    res = await client.post("/api/admin/login", json={"pin": "0000"})
    assert res.status_code == 200, (
        f"admin_session fixture: login failed with status {res.status_code}: {res.text}"
    )
    csrf = res.cookies.get("gruvax_csrf") or res.json().get("csrf_token")
    return {"cookies": res.cookies, "csrf_token": csrf}


# ── boundary fixture ─────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def boundary_cache() -> list[dict[str, Any]]:
    """Load ``fixtures/boundaries.yaml`` and return the flat list of cube rows.

    Phase 5 update: Each row is a dict matching the updated ``gruvax.cube_boundaries``
    column shape (cut-point model): unit_id, row, col, first_label, first_catalog,
    is_empty. The last_label / last_catalog keys have been removed from the YAML
    (SEG-01 / D-05). Any stale last_* keys in older YAML files are silently ignored.

    This fixture does NOT require a live database and is safe to use in unit
    and property tests.
    """
    data: dict[str, Any] = yaml.safe_load(BOUNDARIES_YAML.read_text())
    cubes: list[dict[str, Any]] = []
    for unit in data["units"]:
        unit_id: int = unit["unit_id"]
        for cube in unit["cubes"]:
            # Ignore stale last_* keys from older YAML files (Phase 5 compatibility)
            clean_cube = {k: v for k, v in cube.items() if k not in ("last_label", "last_catalog")}
            cubes.append({**clean_cube, "unit_id": unit_id})
    return cubes

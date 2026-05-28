"""Shared pytest fixtures for GRUVAX tests.

Provides:
  - ``db_pool``             — session-scoped async psycopg pool connected to the
                              test Postgres instance (reads DATABASE_URL from env).
  - ``boundary_cache``      — the parsed contents of ``fixtures/boundaries.yaml``
                              as a list of dicts, for unit tests that don't need DB.
  - ``admin_session``       — module-scoped fixture that seeds a test PIN hash and
                              posts to ``/api/admin/login``, returning session cookies
                              and CSRF token.  Depends on Plan 02 implementing
                              ``gruvax.auth.pin.hash_pin`` and the login endpoint.
  - ``four_cube_boundaries`` — Phase 7: synthetic 4-cube cut-point list (unit 1, row 0,
                              cols 0-3) using made-up labels only.  No real collection CSV.
  - ``thirty_two_cube_boundaries`` — Phase 7: synthetic 32-cube cut-point list (units 1 + 2,
                              4x4 each) using made-up labels only. No real collection CSV.

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


# ── login rate-limit reset (global) ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_login_rate_limit_global() -> None:  # type: ignore[return]
    """Reset the process-global login rate-limit counter before EVERY test.

    The login endpoint enforces a 5-attempts-per-5-minute limit via a
    module-level singleton ``FixedWindowRateLimiter`` backed by ``MemoryStorage``
    (see ``gruvax.api.admin.limiter``).  The key is the socket peer IP, which is
    constant for all in-process test requests, so the counter is shared across
    the ENTIRE test session — every test module's per-test ``_login()`` helper
    draws from the same 5-attempt bucket.  After 5 logins the rest of the session
    receives 429 and every auth-gated test fails at the login step.

    ``test_admin_auth`` already resets the limiter per-test, but only for its own
    module.  Promoting the reset to an autouse fixture in the root conftest makes
    every module start with a clean budget.  The reset only clears an in-memory
    counter (no DB), so it is safe and cheap for unit and property tests too.
    """
    from gruvax.api.admin.limiter import limiter

    limiter.reset()


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


# ── Phase 7 synthetic cut-point fixtures ─────────────────────────────────────
#
# These fixtures use ONLY made-up labels and catalog numbers.
# They NEVER reference the real collection CSV, background/, or any real data.
# Labels chosen: "Atlantic", "Blue Note", "Columbia", "Impulse"
# Catalog formats: short alphabetic prefix + numeric suffix (purely fictional).
#
# Usage in tests: pass as `force=True` to /api/admin/cubes/bulk so the phantom
# check is bypassed (these labels do not exist in the dev v_collection).


@pytest.fixture(scope="session")
def four_cube_boundaries() -> list[dict[str, Any]]:
    """4 synthetic cut-point rows - unit_id=1, row=0, cols 0-3.

    Covers one shelf row with four distinct made-up labels.
    Synthetic catalog numbers: A-001 … A-004 (purely fictional).
    Used in wizard/reshuffle tests that need a small, fast commit target.
    """
    return [
        {
            "unit_id": 1,
            "row": 0,
            "col": 0,
            "first_label": "Atlantic",
            "first_catalog": "ATL-001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 1,
            "first_label": "Blue Note",
            "first_catalog": "BNL-001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 2,
            "first_label": "Columbia",
            "first_catalog": "COL-001",
            "is_empty": False,
        },
        {
            "unit_id": 1,
            "row": 0,
            "col": 3,
            "first_label": "Impulse",
            "first_catalog": "IMP-001",
            "is_empty": False,
        },
    ]


@pytest.fixture(scope="session")
def thirty_two_cube_boundaries() -> list[dict[str, Any]]:
    """32 synthetic cut-point rows - units 1 and 2, each 4x4 (rows 0-3, cols 0-3).

    Covers a full 2-unit Kallax setup.
    Labels cycle through the four synthetic label families.
    Catalog numbers increment per cube (row*4 + col + 1, prefixed by label code).
    Synthetic data only — no real collection records referenced.
    """
    _LABELS = [
        ("Atlantic", "ATL"),
        ("Blue Note", "BNL"),
        ("Columbia", "COL"),
        ("Impulse", "IMP"),
    ]
    cubes: list[dict[str, Any]] = []
    for unit_id in (1, 2):
        for row in range(4):
            for col in range(4):
                idx = (unit_id - 1) * 16 + row * 4 + col
                label_name, label_prefix = _LABELS[idx % 4]
                catalog = f"{label_prefix}-{idx + 1:03d}"
                cubes.append(
                    {
                        "unit_id": unit_id,
                        "row": row,
                        "col": col,
                        "first_label": label_name,
                        "first_catalog": catalog,
                        "is_empty": False,
                    }
                )
    return cubes


# ── P1 Wave 0 fixtures (added by plan 01-00) ─────────────────────────────────
#
# These fixtures back Plans 02-06 of Phase 1:
#   - ``default_profile_uuid``       — the single-profile UUID constant (D-02).
#   - ``fake_discogsography_app``    — empty-seed canonical fake app (D-15 single-module).
#   - ``fake_discogsography_client`` — httpx.AsyncClient bound to the fake via ASGITransport.
#
# Plan 02 tests that want a non-empty seed call ``create_fake_app(seed=[...])``
# directly; the ``fake_discogsography_app`` fixture is the "empty default" used by
# tests that only need the app surface to exist.

from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest.fixture
def default_profile_uuid() -> str:
    """Single-profile UUID (D-02). Constant across the entire test suite."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def fake_discogsography_app():  # type: ignore[no-untyped-def]
    """Canonical fake-discogsography FastAPI app with an empty seed.

    Resolves to ``gruvax._internal.fake_discogsography.create_fake_app`` (D-15).
    """
    from gruvax._internal.fake_discogsography import create_fake_app

    return create_fake_app(seed=[])


@pytest_asyncio.fixture
async def fake_discogsography_client(fake_discogsography_app):  # type: ignore[no-untyped-def]
    """httpx.AsyncClient bound to the canonical fake-discogsography via ASGITransport."""
    transport = ASGITransport(app=fake_discogsography_app)
    async with AsyncClient(transport=transport, base_url="http://fake") as client:
        yield client


# ── P2 Wave 0 fixtures (added by plan 02-00) ─────────────────────────────────
#
# ``second_profile`` — two-profile DB fixture for SLO benchmark + SSE-leakage tests.
#   Seeds a second non-deleted profile row into gruvax.profiles via db_pool,
#   yields its UUID string; teardown soft-deletes the row so the suite stays
#   order-independent (T-02-00-01 mitigation).
#
# Usage: pass ``second_profile`` as a fixture parameter in tests that need two
# active profiles (e.g. test_sse_per_profile.py, test_session_bootstrap.py).


@pytest_asyncio.fixture
async def second_profile(db_pool) -> Any:  # type: ignore[no-untyped-def]
    """Seed a second non-deleted profile into gruvax.profiles; yield its UUID string.

    Profile attributes:
      - display_name:          'Sam'
      - id:                    gen_random_uuid() (captured into the fixture return)
      - app_token_encrypted:   b'' (Fernet placeholder — not a real PAT)
      - app_token_revoked:     TRUE (no live token; D-02 sentinel pattern)
      - last_sync_status:      NULL (never synced)

    Teardown: sets deleted_at = now() (soft-delete) so the row is excluded from
    all "active profiles" queries without hard-deleting related FK rows.

    Parameterized SQL only — no f-strings or string interpolation (project convention).

    Scope: function (each test gets a fresh profile row; avoids order-dependency).
    """
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO gruvax.profiles "
            "(display_name, app_token_encrypted, app_token_revoked, last_sync_status) "
            "VALUES ('Sam', %s::bytea, TRUE, NULL) "
            "RETURNING id::text",
            (b"",),
        )
        row = await cur.fetchone()
        await conn.commit()

    assert row is not None, "second_profile INSERT failed — no row returned"
    profile_uuid: str = row[0]

    yield profile_uuid

    # Teardown: soft-delete the second profile so subsequent tests see only 1 active
    # profile. Use UPDATE … SET deleted_at rather than DELETE to preserve FK constraints
    # on related tables (T-02-00-01 — order-independent suite).
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "UPDATE gruvax.profiles SET deleted_at = now() "
            "WHERE id = %s::uuid AND deleted_at IS NULL",
            (profile_uuid,),
        )
        await conn.commit()

"""Integration-test conftest: module-scoped autouse seed for gruvax.profile_collection.

Closes Gap #1 (BLOCKER) and Gap #3 (WARNING cascade) from
01-VERIFICATION.md by re-applying ``tests/fixtures/synth_profile_collection.sql``
before every integration test module runs. Lifts the proven sync-psycopg pattern
from ``tests/integration/test_search_benchmark.py`` (Plan 01-06) to apply
suite-wide, so a fresh checkout reaches green without manual
``psql < tests/fixtures/synth_profile_collection.sql``.

Uses ``psycopg.connect()`` (NOT the session-scoped async ``db_pool``) — the
async-pool path deadlocks here per the PoolTimeout debugging note in
01-06-SUMMARY.md (Rule 1 fix). pytest auto-loads both ``tests/conftest.py``
(root) and this file (integration-only); fixtures here add to, not replace,
the root-conftest fixtures.

P2 addition: ``_patch_make_client_with_in_process_fake`` — session-scoped autouse
fixture that patches ``gruvax.sync.profile_sync._make_client`` with a factory that
routes DiscogsographyClient through the in-process fake-discogsography app. This
allows integration tests (e.g. test_profile_manager_api.py) that test the connect/
sync flows to work without requiring the ``fake-discogsography`` hostname to resolve.

Tests that explicitly monkeypatch ``profile_sync._make_client`` per-test (e.g.
test_admin_sync_endpoint.py) use function-scoped monkeypatch which takes precedence
over this session-scoped mock. Those tests are unaffected.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
import psycopg
import pytest

from gruvax._internal.fake_discogsography import create_fake_app
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.settings import settings


# ── In-process fake-discogsography for profile manager tests ─────────────────
# The fake app serves the dev seed with a fixed user_id. All dscg_* tokens are
# accepted; tokens not starting with "Bearer dscg_" return 401 (pat_rejected
# path for test_pat_rejected).
_FAKE_APP = create_fake_app(
    seed=[
        {
            "id": str(i),
            "title": f"Test Title {i}",
            "year": 1970 + (i % 30),
            "catalog_number": f"TEST-{i:04d}",
            "artist": f"Artist {i}",
            "label": "Test Label",
            "folder_id": 1,
        }
        for i in range(1, 51)
    ],
    user_id="99999999-9999-9999-9999-999999999999",
)


def _in_process_client_factory(base_url: str, pat: str) -> DiscogsographyClient:
    """Factory that routes DiscogsographyClient through the in-process fake app.

    Replaces the real HTTP transport with an ASGITransport bound to the in-process
    fake-discogsography app. The PAT is passed as the Authorization header so the
    fake's token-routing logic (401 for non-dscg_ tokens) applies correctly.
    """
    client = DiscogsographyClient.__new__(DiscogsographyClient)
    client._client = AsyncClient(
        transport=ASGITransport(app=_FAKE_APP),
        base_url="http://fake-in-process",
        headers={"Authorization": f"Bearer {pat}"},
    )
    return client


@pytest.fixture(scope="session", autouse=True)
def _ensure_gruvax_secret_key() -> None:
    """Ensure GRUVAX_SECRET_KEY is set in os.environ for the integration test session.

    ``gruvax.sync.pat_crypto`` reads ``GRUVAX_SECRET_KEY`` directly from
    ``os.environ`` (not from pydantic-settings), so pydantic loading the .env
    file into ``settings`` is not sufficient. This fixture guarantees the env var
    is present so PAT encrypt/decrypt tests can run.

    If the key is already set (e.g. from a real .env export), the existing value
    is preserved. Otherwise a fresh Fernet key is generated for the test session.
    """
    if not os.environ.get("GRUVAX_SECRET_KEY"):
        # Try reading from pydantic-settings (loaded from .env)
        try:
            key_val = settings.GRUVAX_SECRET_KEY.get_secret_value()  # type: ignore[attr-defined]
            if key_val:
                os.environ["GRUVAX_SECRET_KEY"] = key_val
        except AttributeError, Exception:
            # Fall back to generating a fresh key for the session.
            os.environ["GRUVAX_SECRET_KEY"] = Fernet.generate_key().decode()
    yield  # type: ignore[misc]


@pytest.fixture(scope="session", autouse=True)
def _patch_make_client_with_in_process_fake() -> None:
    """Session-scoped autouse: route _make_client through the in-process fake.

    Activated for the entire test session so any integration test that calls
    DiscogsographyClient (via sync_profile or the connect endpoint) uses the
    in-process fake instead of attempting to reach http://fake-discogsography:8004.

    Per-test monkeypatches (function-scoped) override this session mock during the
    individual test and restore it afterward — existing tests are unaffected.
    """
    with patch("gruvax.sync.profile_sync._make_client", _in_process_client_factory):
        yield


# Resolve from tests/integration/conftest.py → tests/ → tests/fixtures/synth_profile_collection.sql
_SYNTH_SQL_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "synth_profile_collection.sql"
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BOUNDARIES_YAML_PATH = _REPO_ROOT / "fixtures" / "boundaries.yaml"

_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"


def _schema_at_head(cur: psycopg.Cursor) -> bool:
    """Return True iff gruvax.profiles exists (the head-marker table from migration 0009)."""
    cur.execute("SELECT to_regclass('gruvax.profiles')")
    return cur.fetchone()[0] is not None


def _alembic_upgrade_head() -> None:
    """Run ``alembic upgrade head`` via subprocess (no event-loop conflict)."""
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
    )


def _seed_cube_boundaries(conn: psycopg.Connection) -> None:
    """Seed gruvax.cube_boundaries from fixtures/boundaries.yaml.

    Only runs when cube_boundaries is empty — idempotent seed to restore data
    after a migration roundtrip test empties the DB.

    Uses the composite PK (profile_id, unit_id, row, col) from migration 0010.
    Boundaries belong to the default profile.
    """
    import yaml

    if not _BOUNDARIES_YAML_PATH.is_file():
        return  # no fixture to seed — skip gracefully

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM gruvax.cube_boundaries")
        count = cur.fetchone()[0]
        if count and count > 0:
            return  # already seeded — skip

    data = yaml.safe_load(_BOUNDARIES_YAML_PATH.read_text())
    with conn.cursor() as cur:
        for unit in data.get("units", []):
            unit_id = unit["unit_id"]
            # Ensure unit row exists (FK constraint)
            cur.execute(
                "INSERT INTO gruvax.units (id, display_name, rows, cols, ordering)"
                " VALUES (%s, %s, %s, %s, %s)"
                " ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name,"
                "   rows = EXCLUDED.rows, cols = EXCLUDED.cols, ordering = EXCLUDED.ordering,"
                "   updated_at = now()",
                (
                    unit_id,
                    unit.get("display_name", f"Unit {unit_id}"),
                    unit.get("rows", 4),
                    unit.get("cols", 4),
                    unit.get("ordering", unit_id),
                ),
            )
            for cube in unit.get("cubes", []):
                cur.execute(
                    "INSERT INTO gruvax.cube_boundaries"
                    " (profile_id, unit_id, row, col, first_label, first_catalog, is_empty)"
                    " VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)"
                    " ON CONFLICT (profile_id, unit_id, row, col) DO UPDATE"
                    "   SET first_label = EXCLUDED.first_label,"
                    "       first_catalog = EXCLUDED.first_catalog,"
                    "       is_empty = EXCLUDED.is_empty,"
                    "       updated_at = now()",
                    (
                        _DEFAULT_PROFILE_UUID,
                        unit_id,
                        cube["row"],
                        cube["col"],
                        cube.get("first_label"),
                        cube.get("first_catalog"),
                        cube.get("is_empty", False),
                    ),
                )
    conn.commit()


@pytest.fixture(scope="module", autouse=True)
def _seeded_profile_collection() -> None:
    """Idempotently seed gruvax.profile_collection for every integration test module.

    Closes Gap #1 (BLOCKER) and Gap #3 (WARNING cascade) from 01-VERIFICATION.md.

    Self-healing — if a prior test (e.g. ``test_migrate_0009::test_alembic_round_trip_is_clean``)
    left the dev DB at a non-head revision, this fixture restores it via
    ``alembic upgrade head`` before seeding. Required because the integration suite
    shares a single dev Postgres (no isolated test DB; see integration_test_harness
    project memory) and migration tests are destructive by design.

    Also re-seeds cube_boundaries if empty (migration roundtrip tests clear all data).

    Reads DATABASE_URL via pydantic-settings (NOT os.environ) — pydantic-settings
    loads .env directly without populating the OS environment.

    Uses a fresh sync psycopg connection (NOT the session-scoped async ``db_pool``)
    because the synchronous fixture runs in pytest's collection phase, before
    pytest-asyncio constructs the event loop the async pool needs.

    Idempotent: ``synth_profile_collection.sql`` starts with
    ``TRUNCATE gruvax.profile_collection RESTART IDENTITY CASCADE``, so calling
    once per module is safe across the whole suite.
    """
    assert _SYNTH_SQL_PATH.is_file(), f"synth fixture missing at {_SYNTH_SQL_PATH}"
    dsn = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        if not _schema_at_head(cur):
            # Migration test (or aborted run) left DB at a lower revision — restore it.
            _alembic_upgrade_head()
        sql = _SYNTH_SQL_PATH.read_text()
        cur.execute(sql)
        conn.commit()
    # Reseed cube_boundaries if empty (migration roundtrip tests destroy all data).
    with psycopg.connect(dsn) as conn:
        _seed_cube_boundaries(conn)
    yield
    # No teardown — the table stays seeded for subsequent modules.

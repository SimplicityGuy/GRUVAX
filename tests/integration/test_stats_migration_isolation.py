"""Old revision roundtrips must never consume recent parent activity history."""

import os
from pathlib import Path
import subprocess
import sys

import psycopg
import pytest

from tests.fixtures.migration_databases import migration_db as migration_db
from tests.integration.test_migration_safety import database_state


@pytest.mark.parametrize("revision", ["0011", "0015", "0016"])
def test_migration_modules_preserve_active_parent_database(migration_db, revision):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as parent:
        parent.execute(
            "INSERT INTO gruvax.record_stats(profile_id,release_id,search_count) VALUES ('00000000-0000-0000-0000-000000000001',991800,1)"
        )
        parent.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind) VALUES ('00000000-0000-0000-0000-000000000001',991800,'search')"
        )
        before = database_state(parent)
        result = subprocess.run(  # noqa: S603
            [
                sys.executable,
                "-m",
                "pytest",
                f"tests/integration/test_migrate_{revision}.py",
                "-q",
                "-ra",
            ],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "DATABASE_URL": url},
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SKIPPED" not in result.stdout
        assert database_state(parent) == before

"""New snapshot status refuses downgrade before DDL rather than rewriting user state."""

import os
from pathlib import Path
import subprocess
import sys
import time

from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
import pytest

from tests.fixtures.migration_databases import migrate, migration_db as migration_db
from tests.integration.test_migration_safety import database_state


ROOT = Path(__file__).resolve().parents[2]
DEFAULT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
SCRIPT = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
CROSSING = f"-{len(list(SCRIPT.iterate_revisions(SCRIPT.get_current_head(), '0018')))}"


@pytest.fixture(autouse=True)
def _seeded_profile_collection(migration_db):  # type: ignore[no-untyped-def]
    with psycopg.connect(migration_db[0]) as conn:
        assert (
            conn.execute("SELECT current_database()").fetchone()[0].startswith("gruvax_migration_")
        )


@pytest.mark.parametrize("owner", [DEFAULT, OTHER])
@pytest.mark.parametrize("target", ["0018", "base", CROSSING])
def test_snapshot_error_refuses_before_any_downgrade_ddl(migration_db, owner, target):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        if owner == OTHER:
            conn.execute(
                "INSERT INTO gruvax.profiles(id,display_name,app_token_encrypted,deleted_at) VALUES (%s,'Deleted error owner',%s,now())",
                (OTHER, b""),
            )
        conn.execute(
            "UPDATE gruvax.profiles SET last_sync_status='failed',last_sync_error='snapshot_mismatch' WHERE id=%s",
            (owner,),
        )
        before = database_state(conn)
        result = migrate(url, "downgrade", target)
        assert result.returncode != 0
        assert "snapshot mismatch status" in result.stderr
        assert "Running downgrade" not in result.stderr
        assert database_state(conn) == before


def test_clean_error_constraint_roundtrip_retains_prior_values(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "UPDATE gruvax.profiles SET last_sync_error='shrink_guard',last_sync_status='failed' WHERE id=%s",
            (DEFAULT,),
        )
        before = conn.execute("SELECT to_jsonb(p) FROM gruvax.profiles p ORDER BY id").fetchall()
        down = migrate(url, "downgrade", "0018")
        assert down.returncode == 0, down.stderr
        assert (
            conn.execute("SELECT to_jsonb(p) FROM gruvax.profiles p ORDER BY id").fetchall()
            == before
        )
        up = migrate(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        assert (
            conn.execute("SELECT to_jsonb(p) FROM gruvax.profiles p ORDER BY id").fetchall()
            == before
        )
        conn.execute(
            "UPDATE gruvax.profiles SET last_sync_error='snapshot_mismatch' WHERE id=%s", (DEFAULT,)
        )


def test_emitted_direct_sql_refuses_without_schema_or_value_changes(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    emitted = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0019:0018", "--sql"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert emitted.returncode == 0, emitted.stderr
    assert emitted.stdout.index("LOCK TABLE gruvax.profiles") < emitted.stdout.index(
        "ALTER TABLE gruvax.profiles"
    )
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "UPDATE gruvax.profiles SET last_sync_error='snapshot_mismatch' WHERE id=%s", (DEFAULT,)
        )
        before = database_state(conn)
        with pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState):
            conn.execute(emitted.stdout)
        conn.rollback()
        assert database_state(conn) == before


def test_downgrade_waits_for_profile_writer_then_refuses(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with (
        psycopg.connect(conninfo) as writer,
        psycopg.connect(conninfo, autocommit=True) as observer,
    ):
        writer.execute(
            "UPDATE gruvax.profiles SET last_sync_error='snapshot_mismatch' WHERE id=%s", (DEFAULT,)
        )
        process = subprocess.Popen(
            [sys.executable, "-m", "alembic", "downgrade", "0018"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            blocked = False
            while time.monotonic() < deadline:
                blocked = observer.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid() AND wait_event_type='Lock' AND query LIKE '%LOCK TABLE gruvax.profiles%')"
                ).fetchone()[0]
                if blocked:
                    break
                time.sleep(0.05)
            assert blocked, "migration must wait for the actual profile writer"
            writer.commit()
            before = database_state(observer)
            out, err = process.communicate(timeout=20)
            assert process.returncode != 0 and "snapshot mismatch status" in err, out + err
            assert "Running downgrade" not in err
            assert database_state(observer) == before
        finally:
            writer.rollback()
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

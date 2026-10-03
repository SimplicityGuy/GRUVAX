"""Recent activity refusal before DDL, safe expiry rollback, and actual writer locks."""

import os
from pathlib import Path
import subprocess
import sys
import time

from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg.errors import ObjectNotInPrerequisiteState
import pytest

from tests.fixtures.migration_databases import migrate, migration_db as migration_db
from tests.integration.test_migration_safety import database_state


ROOT = Path(__file__).resolve().parents[2]
DEFAULT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
SCRIPT = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
CROSSING = f"-{len(list(SCRIPT.iterate_revisions(SCRIPT.get_current_head(), '0017')))}"


@pytest.mark.parametrize("owner", [DEFAULT, OTHER])
@pytest.mark.parametrize("target", ["0017", "base", CROSSING])
def test_recent_history_refuses_before_any_downgrade_ddl(migration_db, owner, target):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        if owner == OTHER:
            conn.execute(
                "INSERT INTO gruvax.profiles(id,display_name,app_token_encrypted) VALUES (%s,'Recent history owner',%s)",
                (OTHER, b""),
            )
        conn.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind) VALUES (%s,42,'search')",
            (owner,),
        )
        before = database_state(conn)
        result = migrate(url, "downgrade", target)
        assert result.returncode != 0
        assert "Cannot downgrade" in result.stderr
        if target != "base" or owner == DEFAULT:
            assert "recent record activity" in result.stderr
        assert "Running downgrade" not in result.stderr
        assert database_state(conn) == before


def test_expired_only_roundtrip_preserves_lifetime_totals(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.record_stats(profile_id,release_id,search_count,selection_count,last_searched_at,last_selected_at) VALUES (%s,42,31,12,now()-INTERVAL '8 days',now()-INTERVAL '9 days')",
            (DEFAULT,),
        )
        conn.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind,occurred_at) VALUES (%s,42,'search',now()-INTERVAL '8 days')",
            (DEFAULT,),
        )
        before = conn.execute(
            "SELECT search_count,selection_count,last_searched_at,last_selected_at FROM gruvax.record_stats"
        ).fetchall()
        down = migrate(url, "downgrade", "0017")
        assert down.returncode == 0, down.stderr
        assert (
            conn.execute(
                "SELECT search_count,selection_count,last_searched_at,last_selected_at FROM gruvax.record_stats"
            ).fetchall()
            == before
        )
        up = migrate(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        assert (
            conn.execute(
                "SELECT search_count,selection_count,last_searched_at,last_selected_at FROM gruvax.record_stats"
            ).fetchall()
            == before
        )
        assert conn.execute("SELECT count(*) FROM gruvax.record_activity").fetchone() == (0,)
        assert conn.execute(
            "SELECT search_count_7d,selection_count_7d FROM gruvax.record_stats"
        ).fetchone() == (0, 0)


def test_upgrade_does_not_invent_events_from_legacy_counters(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    down = migrate(url, "downgrade", "0017")
    assert down.returncode == 0, down.stderr
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.record_stats(profile_id,release_id,search_count,search_count_7d,selection_count,selection_count_7d,last_searched_at) VALUES (%s,42,100,100,20,20,now())",
            (DEFAULT,),
        )
        before = conn.execute(
            "SELECT search_count,selection_count,last_searched_at FROM gruvax.record_stats"
        ).fetchall()
        up = migrate(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        assert (
            conn.execute(
                "SELECT search_count,selection_count,last_searched_at FROM gruvax.record_stats"
            ).fetchall()
            == before
        )
        assert conn.execute(
            "SELECT search_count_7d,selection_count_7d FROM gruvax.record_stats"
        ).fetchone() == (0, 0)
        assert conn.execute("SELECT count(*) FROM gruvax.record_activity").fetchone() == (0,)


def test_downgrade_waits_for_stats_writer_then_refuses_history(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with (
        psycopg.connect(conninfo) as writer,
        psycopg.connect(conninfo, autocommit=True) as observer,
    ):
        writer.execute(
            "INSERT INTO gruvax.record_stats(profile_id,release_id,search_count) VALUES (%s,42,1)",
            (DEFAULT,),
        )
        writer.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind) VALUES (%s,42,'search')",
            (DEFAULT,),
        )
        expected = database_state(writer)
        process = subprocess.Popen(
            [sys.executable, "-m", "alembic", "downgrade", "0017"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            blocked = False
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and process.poll() is None:
                blocked = observer.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND query LIKE '%%LOCK TABLE gruvax.record_stats%%')"
                ).fetchone()[0]
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked, "Downgrade must wait for the actual lifetime/event writer"
            writer.commit()
            _, error = process.communicate(timeout=30)
            assert process.returncode != 0
            assert "recent record activity" in error
            assert "Running downgrade" not in error
            assert database_state(observer) == expected
        finally:
            writer.rollback()
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


def test_emitted_downgrade_also_refuses_recent_history(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    emitted = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0018:0017", "--sql"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        check=False,
    )
    assert emitted.returncode == 0, emitted.stderr
    assert emitted.stdout.index("LOCK TABLE") < emitted.stdout.index(
        "DROP TABLE gruvax.record_activity"
    )
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind) VALUES (%s,42,'search')",
            (DEFAULT,),
        )
        before = database_state(conn)
        with pytest.raises(ObjectNotInPrerequisiteState, match="recent record activity"):
            conn.execute(emitted.stdout)
        conn.execute("ROLLBACK")
        assert database_state(conn) == before

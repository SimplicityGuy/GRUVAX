"""Migration refusal and shared-extension ownership on disposable databases."""

import os
from pathlib import Path
import subprocess
import sys
import uuid

from alembic.config import Config
from alembic.script import ScriptDirectory
import psycopg
from psycopg import sql
import pytest

from gruvax.settings import settings
from tests.fixtures.migration_databases import (
    disposable_migration_database,
    migrate,
    migration_db as migration_db,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"
SCRIPT = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
HEAD_REVISION = SCRIPT.get_current_head()
HEAD_PREDECESSOR = SCRIPT.get_revision(HEAD_REVISION).down_revision
PROFILE_CROSSING = f"-{len(list(SCRIPT.iterate_revisions(HEAD_REVISION, '0009')))}"


def database_state(conn):  # type: ignore[no-untyped-def]
    revision = conn.execute(
        "SELECT version_num FROM public.alembic_version ORDER BY version_num"
    ).fetchall()
    columns = conn.execute(
        "SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns WHERE table_schema = 'gruvax' ORDER BY table_name, ordinal_position"
    ).fetchall()
    constraints = conn.execute(
        "SELECT c.relname, con.conname, pg_get_constraintdef(con.oid) FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'gruvax' ORDER BY c.relname, con.conname"
    ).fetchall()
    indexes = conn.execute(
        "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = 'gruvax' ORDER BY tablename, indexname"
    ).fetchall()
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'gruvax' ORDER BY tablename"
    ).fetchall()
    data = {}
    for (table,) in tables:
        data[table] = conn.execute(
            sql.SQL("SELECT to_jsonb(t) FROM gruvax.{} t ORDER BY to_jsonb(t)::text").format(
                sql.Identifier(table)
            )
        ).fetchall()
    return revision, columns, constraints, indexes, data


@pytest.mark.parametrize(
    "payload", ["metadata", "settings", "boundaries", "stats", "overrides", "collection"]
)
def test_downgrade_refuses_nondefault_data_before_any_mutation(migration_db, payload):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s::uuid, 'Synthetic retained profile', %s)",
            (OTHER, b"synthetic-encrypted-pat"),
        )
        if payload == "settings":
            conn.execute(
                "INSERT INTO gruvax.settings (profile_id, key, value) VALUES (%s::uuid, 'sync.cadence', '\"off\"'::jsonb)",
                (OTHER,),
            )
        elif payload in {"boundaries", "overrides"}:
            conn.execute(
                "INSERT INTO gruvax.units (id, display_name, rows, cols, ordering) VALUES (1, 'Synthetic unit', 1, 1, 0)"
            )
            conn.execute(
                "INSERT INTO gruvax.cube_boundaries (profile_id, unit_id, row, col, first_label, first_catalog, is_empty) VALUES (%s::uuid, 1, 0, 0, 'Default synthetic', 'D1', FALSE)",
                (DEFAULT,),
            )
            conn.execute(
                "INSERT INTO gruvax.cube_boundaries (profile_id, unit_id, row, col, first_label, first_catalog, is_empty) VALUES (%s::uuid, 1, 0, 0, 'Synthetic', 'S1', FALSE)",
                (OTHER,),
            )
            if payload == "overrides":
                conn.execute(
                    "INSERT INTO gruvax.segment_overrides (profile_id, unit_id, row, col, label, label_display, fraction) VALUES (%s::uuid, 1, 0, 0, 'synthetic', 'Synthetic', 0.25)",
                    (DEFAULT,),
                )
                conn.execute(
                    "INSERT INTO gruvax.segment_overrides (profile_id, unit_id, row, col, label, label_display, fraction) VALUES (%s::uuid, 1, 0, 0, 'synthetic', 'Synthetic', 0.5)",
                    (OTHER,),
                )
        elif payload == "stats":
            conn.execute(
                "INSERT INTO gruvax.record_stats (profile_id, release_id) VALUES (%s::uuid, 99)",
                (DEFAULT,),
            )
            conn.execute(
                "INSERT INTO gruvax.record_stats (profile_id, release_id) VALUES (%s::uuid, 99)",
                (OTHER,),
            )
        elif payload == "collection":
            conn.execute(
                "INSERT INTO gruvax.profile_collection (profile_id, release_id, folder_id) VALUES (%s::uuid, 99, 1)",
                (OTHER,),
            )
        before = database_state(conn)
        result = migrate(url, "downgrade", "base")
        assert result.returncode != 0, "Downgrade must refuse loss of non-default profile data"
        assert "non-default profile data" in result.stderr
        assert "Running downgrade" not in result.stderr
        assert database_state(conn) == before


def test_default_only_roundtrip_remains_supported(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    down = migrate(url, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    up = migrate(url, "upgrade", "head")
    assert up.returncode == 0, up.stderr
    with psycopg.connect(conninfo) as conn:
        assert conn.execute("SELECT id::text FROM gruvax.profiles").fetchall() == [(DEFAULT,)]
        assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
            HEAD_REVISION,
        )


@pytest.mark.parametrize("target", ["0009", "0010"])
def test_profile_downgrade_boundary(migration_db, target):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s::uuid, 'Boundary retained profile', %s)",
            (OTHER, b"synthetic-pat"),
        )
        before = database_state(conn)
        result = migrate(url, "downgrade", target)
        if target == "0009":
            assert result.returncode != 0, result.stderr
            assert "non-default profile data" in result.stderr
            assert "Running downgrade" not in result.stderr
            assert database_state(conn) == before
        else:
            assert result.returncode == 0, result.stderr
            assert conn.execute(
                "SELECT id::text, display_name, app_token_encrypted FROM gruvax.profiles WHERE id = %s::uuid",
                (OTHER,),
            ).fetchone() == (OTHER, "Boundary retained profile", b"synthetic-pat")
            assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
                "0010",
            )


def test_direct_0009_downgrade_preserves_profile(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    assert migrate(url, "downgrade", "0009").returncode == 0
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s::uuid, 'Direct retained profile', %s)",
            (OTHER, b"synthetic-pat"),
        )
        before = database_state(conn)
        result = migrate(url, "downgrade", "base")
        assert result.returncode != 0, result.stderr
        assert "non-default profile data" in result.stderr
        assert "Running downgrade" not in result.stderr
        assert database_state(conn) == before


def test_late_downgrade_failure_rolls_back_entire_chain(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "CREATE TABLE public.profile_sentinel (profile_id UUID REFERENCES gruvax.profiles(id))"
        )
        conn.execute("INSERT INTO public.profile_sentinel VALUES (%s::uuid)", (DEFAULT,))
        conn.execute(
            "INSERT INTO gruvax.record_activity(profile_id,release_id,event_kind,occurred_at) VALUES (%s,99,'search',now()-INTERVAL '8 days')",
            (DEFAULT,),
        )
        before = database_state(conn)
        result = migrate(url, "downgrade", "base")
        assert result.returncode != 0
        assert "profile_sentinel" in result.stderr
        assert f"Running downgrade {HEAD_REVISION}" in result.stderr
        assert database_state(conn) == before
        assert conn.execute("SELECT profile_id::text FROM public.profile_sentinel").fetchall() == [
            (DEFAULT,)
        ]


def test_downgrade_waits_for_live_writer_then_refuses_its_profile(migration_db):  # type: ignore[no-untyped-def]
    import time

    conninfo, url = migration_db
    with (
        psycopg.connect(conninfo) as writer,
        psycopg.connect(conninfo, autocommit=True) as observer,
    ):
        writer.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s::uuid, 'Concurrent retained profile', %s)",
            (OTHER, b"synthetic-pat"),
        )
        expected = database_state(writer)
        process = subprocess.Popen(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=ROOT,
            env={**os.environ, "DATABASE_URL": url},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 10
            blocked = False
            while time.monotonic() < deadline and process.poll() is None:
                blocked = observer.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE '%%LOCK TABLE gruvax.profiles%%')"
                ).fetchone()[0]
                if blocked:
                    break
                time.sleep(0.02)
            assert blocked, "Downgrade must wait for the actual uncommitted profile writer"
            writer.commit()
            _, error = process.communicate(timeout=30)
            assert process.returncode != 0
            assert "non-default profile data" in error
            assert database_state(observer) == expected
        finally:
            writer.rollback()
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=10)


@pytest.mark.parametrize("target", ["-1", PROFILE_CROSSING])
def test_relative_downgrade_preserves_revision_boundary(migration_db, target):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s::uuid, 'Relative retained profile', %s)",
            (OTHER, b"synthetic-pat"),
        )
        before = database_state(conn)
        result = migrate(url, "downgrade", target)
        if target == "-1":
            assert result.returncode == 0, result.stderr
            assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
                HEAD_PREDECESSOR,
            )
            assert conn.execute(
                "SELECT display_name, app_token_encrypted FROM gruvax.profiles WHERE id = %s::uuid",
                (OTHER,),
            ).fetchone() == ("Relative retained profile", b"synthetic-pat")
        else:
            assert result.returncode != 0
            assert "non-default profile data" in result.stderr
            assert "Running downgrade" not in result.stderr
            assert database_state(conn) == before


@pytest.mark.parametrize("start", ["0010", "0009"])
def test_emitted_sql_refuses_before_its_first_mutation(migration_db, start):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    assert migrate(url, "downgrade", start).returncode == 0
    target = "0010:0009" if start == "0010" else "0009:0008"
    # Both revision ranges are fixed test literals and no shell is involved.
    emitted = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "downgrade", target, "--sql"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert emitted.returncode == 0, emitted.stderr
    assert emitted.stdout.index("LOCK TABLE") < emitted.stdout.index("ALTER TABLE")
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s::uuid, 'Emitted retained profile', %s)",
            (OTHER, b"synthetic-pat"),
        )
        before = database_state(conn)
        with pytest.raises(
            psycopg.errors.ObjectNotInPrerequisiteState, match="non-default profile data"
        ):
            conn.execute(emitted.stdout)
        conn.execute("ROLLBACK")
        assert database_state(conn) == before


def test_disposable_migrations_preserve_parent_profile_sentinel():
    parent = settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)
    sentinel = uuid.uuid4()
    with psycopg.connect(parent, autocommit=True) as shared:
        shared.execute(
            "INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted) VALUES (%s, %s, %s)",
            (sentinel, f"Migration parent sentinel {sentinel}", b"synthetic-parent-pat"),
        )
        try:
            before = shared.execute(
                "SELECT to_jsonb(p) FROM gruvax.profiles p WHERE id = %s", (sentinel,)
            ).fetchone()
            assert before is not None
            with disposable_migration_database() as (_conninfo, url):
                down = migrate(url, "downgrade", "base")
                assert down.returncode == 0, down.stderr
                up = migrate(url, "upgrade", "head")
                assert up.returncode == 0, up.stderr
            assert (
                shared.execute(
                    "SELECT to_jsonb(p) FROM gruvax.profiles p WHERE id = %s", (sentinel,)
                ).fetchone()
                == before
            )
        finally:
            shared.execute("DELETE FROM gruvax.profiles WHERE id = %s", (sentinel,))


def test_fresh_v1_rows_are_backfilled_on_every_profile_aware_table(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    down = migrate(url, "downgrade", "0008")
    assert down.returncode == 0, down.stderr
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO gruvax.units (id, display_name, rows, cols, ordering) VALUES (1, 'Backfill unit', 1, 1, 0)"
        )
        conn.execute(
            "INSERT INTO gruvax.cube_boundaries (unit_id, row, col, first_label, first_catalog, is_empty) VALUES (1, 0, 0, 'Synthetic', 'S1', FALSE)"
        )
        conn.execute(
            "INSERT INTO gruvax.segment_overrides (unit_id, row, col, label, fraction) VALUES (1, 0, 0, 'Synthetic', 0.5)"
        )
        conn.execute("INSERT INTO gruvax.record_stats (release_id) VALUES (99)")
        conn.execute(
            "INSERT INTO gruvax.settings (key, value) VALUES ('migration.sentinel', '17'::jsonb)"
        )
        conn.execute(
            "INSERT INTO gruvax.admin_sessions (id, expires_at, hard_expires_at) VALUES (gen_random_uuid(), now() + interval '1 hour', now() + interval '2 hours')"
        )
        conn.execute(
            "INSERT INTO gruvax.idempotency_keys (key, response_json) VALUES ('migration-backfill', '{}'::jsonb)"
        )
        conn.execute(
            "INSERT INTO gruvax.boundary_history (change_set_id, unit_id, row, col, prev_is_empty, new_is_empty, source) VALUES (gen_random_uuid(), 1, 0, 0, TRUE, TRUE, 'manual')"
        )
        up = migrate(url, "upgrade", "head")
        assert up.returncode == 0, up.stderr
        for table in [
            "cube_boundaries",
            "segment_overrides",
            "record_stats",
            "settings",
            "admin_sessions",
            "idempotency_keys",
            "boundary_history",
        ]:
            rows = conn.execute(
                sql.SQL("SELECT profile_id::text FROM gruvax.{}").format(sql.Identifier(table))
            ).fetchall()
            assert rows, f"{table} must contain an actual pre-profile row"
            assert all(row == (DEFAULT,) for row in rows), table

"""Shared pgcrypto belongs to the database operator, not GRUVAX rollback."""

import uuid

import psycopg

from tests.integration.test_migration_safety import migrate, migration_db as migration_db


def test_shared_extension_and_dependent_view_survive_downgrade(migration_db):  # type: ignore[no-untyped-def]
    conninfo, url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public")
        conn.execute(
            "CREATE VIEW public.crypto_sentinel AS SELECT public.digest('synthetic sentinel', 'sha256') AS digest"
        )
        extension = conn.execute(
            "SELECT oid FROM pg_extension WHERE extname = 'pgcrypto'"
        ).fetchone()
        sentinel = conn.execute("SELECT digest FROM public.crypto_sentinel").fetchone()
        assert extension is not None
        assert sentinel is not None and len(sentinel[0]) == 32
        result = migrate(url, "downgrade", "0008")
        assert result.returncode == 0, result.stderr
        assert (
            conn.execute("SELECT oid FROM pg_extension WHERE extname = 'pgcrypto'").fetchone()
            == extension
        )
        assert conn.execute("SELECT digest FROM public.crypto_sentinel").fetchone() == sentinel
        assert conn.execute("SELECT version_num FROM public.alembic_version").fetchone() == (
            "0008",
        )
        restored = migrate(url, "upgrade", "head")
        assert restored.returncode == 0, restored.stderr
        assert conn.execute("SELECT digest FROM public.crypto_sentinel").fetchone() == sentinel


def test_core_uuid_and_profile_default_work_without_pgcrypto(migration_db):  # type: ignore[no-untyped-def]
    conninfo, _url = migration_db
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("DROP EXTENSION pgcrypto")
        assert (
            conn.execute("SELECT oid FROM pg_extension WHERE extname = 'pgcrypto'").fetchone()
            is None
        )
        generated = conn.execute("SELECT pg_catalog.gen_random_uuid()").fetchone()
        assert generated is not None and isinstance(generated[0], uuid.UUID)
        profile = conn.execute(
            "INSERT INTO gruvax.profiles (display_name, app_token_encrypted) VALUES ('Synthetic core UUID', %s) RETURNING id",
            (b"synthetic",),
        ).fetchone()
        assert profile is not None and isinstance(profile[0], uuid.UUID)
        conn.execute("DELETE FROM gruvax.profiles WHERE id = %s", (profile[0],))

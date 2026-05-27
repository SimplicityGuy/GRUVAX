#!/bin/sh
# GRUVAX container entrypoint script.
# Uses 'python -m <module>' invocations to avoid hardcoded shebang paths
# that arise when the venv is built in one directory and copied to another.
set -e

PYTHON="/app/.venv/bin/python"

# Wait for Postgres to accept connections before migrating — a cold
# `docker compose up` starts the DB and the API concurrently, so without this
# `alembic upgrade head` would fail and crash-loop the container (WR-04).
echo "Waiting for database to become available..."
i=0
until "$PYTHON" - <<'PY' 2>/dev/null
import os, psycopg
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
psycopg.connect(dsn, connect_timeout=3).close()
PY
do
    i=$((i + 1))
    if [ "$i" -ge 30 ]; then
        echo "Database not reachable after 30 attempts — aborting." >&2
        exit 1
    fi
    sleep 2
done
echo "Database is up."

# Plan 01-10: dev-only gruvax_dev stub schema bootstrap.
#
# WHY: Migration 0002 (CREATE VIEW gruvax.v_collection AS SELECT ... FROM
# collection_items / releases / artists — see migrations/versions/0002_v_collection_view.py)
# uses UNQUALIFIED table names. The runtime pool's search_path is `gruvax, public`
# (D-12), so unqualified references resolve via the public-search-path fallback
# to gruvax_dev in dev/CI (or to discogsography in production). On a virgin
# compose `postgres:18` volume the gruvax_dev schema does NOT exist, so 0002
# crashes the `alembic upgrade head` step and the api container crash-loops
# BEFORE migration 0009 (which DROPs the view per D-19) gets a chance to run.
#
# WHAT: This block creates empty STUB tables (collection_items, releases, artists)
# under gruvax_dev so 0002 parses cleanly. The stubs become dead weight once 0009
# drops the view — that is the intended end state for compose-only scope. The
# stubs MUST NEVER be seeded with real data; their only purpose is to let the
# alembic chain reach 0009. The synth-seed block farther down (lines 36-64 of
# this script before this insert; renumbered after) populates the real
# gruvax.profile_collection AFTER alembic completes, against the v2 schema.
#
# PRODUCTION SAFETY: The GRUVAX_ENV=development guard mirrors the existing
# synth-seed guard verbatim (search for `GRUVAX_ENV:-production` to find both
# gates). Production deployments target the real `discogsography` schema per
# D-12 and MUST NOT run this bootstrap.
#
# IDEMPOTENCY: `CREATE SCHEMA IF NOT EXISTS` + `CREATE TABLE IF NOT EXISTS`
# make this a no-op on dev databases that already contain the discogsography-mock
# tables from `tests/fixtures/legacy/synth_collection.sql` (per the
# integration_test_harness memory note: "shared dev Postgres … gruvax_dev
# populated by hand-managed seed scripts"). The richer columns/constraints on
# any pre-existing tables are preserved unchanged.
#
# Reference: .planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-10-PLAN.md
# Reference: 01-HUMAN-UAT.md `## Gaps` second entry (migration-0002 sub-blocker).
if [ "${GRUVAX_ENV:-production}" = "development" ]; then
    echo "Ensuring gruvax_dev stub schema for migration 0002 (dev-only)..."
    "$PYTHON" - <<'PY'
import os, psycopg
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn, conn.cursor() as cur:
    cur.execute("""
        CREATE SCHEMA IF NOT EXISTS gruvax_dev;
        CREATE TABLE IF NOT EXISTS gruvax_dev.artists (
            id   BIGINT PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE IF NOT EXISTS gruvax_dev.releases (
            id                BIGINT PRIMARY KEY,
            title             TEXT,
            label             TEXT,
            catalog_number    TEXT,
            format            TEXT,
            year              INT,
            fts_vector        TSVECTOR,
            primary_artist_id BIGINT
        );
        CREATE TABLE IF NOT EXISTS gruvax_dev.collection_items (
            id         BIGINT PRIMARY KEY,
            release_id BIGINT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    """)
    conn.commit()
print("gruvax_dev stub tables ensured (idempotent; required for migration 0002 v_collection view).")
PY
fi

# Run Alembic migrations
"$PYTHON" -m alembic upgrade head

# Plan 01-06: dev-only synthetic profile_collection seed.
# Initdb cannot seed v2 schema (it runs BEFORE alembic), so the api container
# seeds after migration. Idempotent — only runs when GRUVAX_ENV=development AND
# profile_collection is empty for the default profile. In production the init-sync
# one-shot does a real sync against discogsography (see compose.yaml).
SYNTH_SQL=/app/tests/fixtures/synth_profile_collection.sql
if [ "${GRUVAX_ENV:-production}" = "development" ] && [ -f "$SYNTH_SQL" ]; then
    PSQL_DSN=$("$PYTHON" -c 'import os; print(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://"))')
    COUNT=$(PGPASSWORD=$(echo "$PSQL_DSN" | sed -E 's|.*://[^:]+:([^@]+)@.*|\1|') \
        "$PYTHON" - <<PY
import os, psycopg
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(dsn) as conn, conn.cursor() as cur:
    cur.execute("SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = '00000000-0000-0000-0000-000000000001'::uuid")
    print(cur.fetchone()[0])
PY
)
    if [ "$COUNT" = "0" ]; then
        echo "Seeding synthetic profile_collection from $SYNTH_SQL ($COUNT rows present)..."
        "$PYTHON" - <<PY
import os, psycopg
dsn = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")
with open("$SYNTH_SQL", "r") as f:
    sql = f.read()
with psycopg.connect(dsn) as conn, conn.cursor() as cur:
    cur.execute(sql)
    conn.commit()
PY
        echo "Synthetic profile_collection seed complete."
    else
        echo "profile_collection already populated ($COUNT rows); skipping synthetic seed."
    fi
fi

# Seed cube boundaries (idempotent upsert on (unit_id, row, col)) so the kiosk
# grid and /api/locate work on a fresh database. Safe to run on every start.
# Skipped automatically if the fixtures file is absent (e.g. a future slim image).
if [ -f fixtures/boundaries.yaml ]; then
    echo "Seeding cube boundaries from fixtures/boundaries.yaml..."
    "$PYTHON" -m gruvax.db.seed_boundaries fixtures/boundaries.yaml
fi

# Start the FastAPI app
exec "$PYTHON" -m uvicorn gruvax.app:app --host 0.0.0.0 --port 8000

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

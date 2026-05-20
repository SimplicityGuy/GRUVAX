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

# Start the FastAPI app
exec "$PYTHON" -m uvicorn gruvax.app:app --host 0.0.0.0 --port 8000

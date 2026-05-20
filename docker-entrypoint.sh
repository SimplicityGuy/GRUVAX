#!/bin/sh
# GRUVAX container entrypoint script.
# Uses 'python -m <module>' invocations to avoid hardcoded shebang paths
# that arise when the venv is built in one directory and copied to another.
set -e

PYTHON="/app/.venv/bin/python"

# Run Alembic migrations
"$PYTHON" -m alembic upgrade head

# Start the FastAPI app
exec "$PYTHON" -m uvicorn gruvax.app:app --host 0.0.0.0 --port 8000

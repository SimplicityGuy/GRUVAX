# GRUVAX task runner — https://just.systems
# Usage: just <recipe>

# ── default ──────────────────────────────────────────────────────────────────
_default:
    @just --list

# ── development ──────────────────────────────────────────────────────────────

# Run the full test suite (requires running Postgres)
test:
    uv run pytest tests/ -q --tb=short

# Run unit + property tests only (no Postgres needed)
test-unit:
    uv run pytest tests/unit/ tests/property/ -x -q

# Run the linter
lint:
    uv run ruff check src/ tests/
    uv run ruff format --check src/ tests/

# Apply ruff autofix + format in place
lint-fix:
    uv run ruff check --fix src/ tests/
    uv run ruff format src/ tests/

# Run mypy strict type check on application source
typecheck:
    uv run mypy --strict src/gruvax/

# ── database ─────────────────────────────────────────────────────────────────

# Apply all pending Alembic migrations
migrate:
    uv run alembic upgrade head

# Roll back all migrations to base
migrate-down:
    uv run alembic downgrade base

# Round-trip migration check (upgrade → downgrade → upgrade)
migrate-roundtrip:
    uv run alembic upgrade head
    uv run alembic downgrade base
    uv run alembic upgrade head

# Seed the dev database: apply migrations + synthetic data
#
# Order is significant:
#   1. migration 0001 — creates gruvax schema, units, cube_boundaries
#   2. synth_collection.sql — creates gruvax_dev schema + source tables
#      (must exist before migration 0002 so the v_collection view body
#       can resolve the unqualified table names at DDL validation time)
#   3. migration 0002 — creates gruvax.v_collection over gruvax_dev
#   4. boundary loader — INSERTs fixtures/boundaries.yaml into cube_boundaries
seed-dev:
    uv run alembic upgrade 0001
    docker exec -i gruvax-dev-pg psql -U gruvax -d gruvax < fixtures/synth_collection.sql
    uv run alembic upgrade head
    uv run python -m gruvax.db.seed_boundaries fixtures/boundaries.yaml

# ── provisioning ─────────────────────────────────────────────────────────────

# Provision DB roles and grants (run once by operator; never by application)
# This prints the SQL to stdout for review; pipe to psql when ready.
provision-db:
    @echo "-- Run the following SQL as a superuser on the shared Postgres instance:"
    @echo "-- GRANT USAGE ON SCHEMA discogsography TO gruvax;"
    @echo "-- GRANT SELECT ON discogsography.releases, discogsography.artists,"
    @echo "--                  discogsography.collection_items TO gruvax;"
    @echo "-- (No INSERT / UPDATE / DELETE granted.)"

# ── frontend ─────────────────────────────────────────────────────────────────

# Build the React SPA and emit dist into ./static/ (served by FastAPI StaticFiles)
build-spa:
    npm --prefix frontend run build

# Run the Vite dev server (proxies /api → localhost:8000)
dev-spa:
    npm --prefix frontend run dev

# Install frontend dependencies (required before first build)
install-spa:
    npm --prefix frontend install

# ── docker ───────────────────────────────────────────────────────────────────

# Start the full Docker Compose stack (builds if needed)
up:
    docker compose up --build

# Start in detached mode
up-d:
    docker compose up --build -d

# Stop and remove containers (NEVER use -v — that wipes mosquitto-data volume)
down:
    docker compose down

# Build the Docker image only (passes version metadata as build-args)
build:
    docker compose build \
      --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
      --build-arg BUILD_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ") \
      --build-arg GRUVAX_ENV=production

# Generate src/gruvax/_version.py from current git state (for local dev outside Docker)
build-version:
    #!/usr/bin/env bash
    set -euo pipefail
    sha=$(git rev-parse --short HEAD)
    ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    printf 'GIT_SHA = "%s"\nBUILD_TIMESTAMP = "%s"\nENVIRONMENT = "development"\n' "$sha" "$ts" > src/gruvax/_version.py
    echo "Wrote src/gruvax/_version.py (GIT_SHA=$sha)"

# Core Value smoke test: docker compose up → search → locate → assert SLO (SC5)
demo:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "=== GRUVAX Core Value smoke test ==="
    docker compose up --build -d
    echo "Waiting for api to be healthy..."
    until curl -sf http://localhost:8000/api/health | python3 -c \
      "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['status']=='ok' else 1)"; do
        sleep 2
    done
    RESULT=$(curl -sf "http://localhost:8000/api/search?q=Miles+Davis&limit=1")
    TOOK_MS=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['took_ms'])")
    echo "Search took: ${TOOK_MS}ms"
    python3 -c "ms=float('$TOOK_MS'); assert ms < 200, f'Search SLO FAILED: {ms:.1f}ms > 200ms'; print(f'Search SLO: PASS ({ms:.1f}ms)')"
    RELEASE_ID=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['items'][0]['release_id'])")
    LOC_RESULT=$(curl -sf "http://localhost:8000/api/locate?release_id=${RELEASE_ID}")
    echo "Locate result: $(echo $LOC_RESULT | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["primary_cube"])')"
    echo "=== PASS ==="

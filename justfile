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
    @echo "-- GRANT USAGE ON SCHEMA discogsography TO gruvax_app;"
    @echo "-- GRANT SELECT ON discogsography.releases, discogsography.artists,"
    @echo "--                  discogsography.collection_items TO gruvax_app;"
    @echo "-- (No INSERT / UPDATE / DELETE granted.)"

# ── docker ───────────────────────────────────────────────────────────────────

# Start the full Docker Compose stack (builds if needed)
up:
    docker compose up --build

# Stop and remove containers
down:
    docker compose down

# Build the Docker image only
build:
    docker compose build

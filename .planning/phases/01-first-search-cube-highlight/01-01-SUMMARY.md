---
phase: 01-first-search-cube-highlight
plan: 01
subsystem: backend/db
tags: [scaffold, alembic, migrations, psycopg, sqlalchemy, seeds, fixtures]
dependency_graph:
  requires: []
  provides:
    - "gruvax Python 3.13 uv project with all backend deps locked"
    - "gruvax schema + units + cube_boundaries + v_collection via Alembic"
    - "search_path mechanism routing v_collection to gruvax_dev (dev) or discogsography (prod)"
    - "32-cube YAML boundary fixture and 152-row synthetic gruvax_dev collection"
    - "Wave 0 pytest infrastructure: conftest db_pool + boundary_cache fixtures"
  affects:
    - "All Phase 1 plans (depend on the schema and test infrastructure)"
    - "gruvax.v_collection is the sole read surface for discogsography across all plans"
tech_stack:
  added:
    - "psycopg 3.x AsyncConnectionPool with autocommit-wrapped configure callback"
    - "SQLAlchemy 2.0 async + greenlet (sqlalchemy[asyncio])"
    - "Alembic 1.18 async env with SQLAlchemy connect event for search_path"
    - "pydantic-settings 2.x BaseSettings with DATABASE_URL + OBSERVED_DISCOGSOGRAPHY_SCHEMA"
    - "psycopg3 direct bootstrap connection (bypasses SQLAlchemy for schema creation)"
  patterns:
    - "Engine-level connect event listener sets search_path before autobegin — avoids _in_external_transaction=True"
    - "version_table_schema=public ensures alembic_version survives DROP SCHEMA gruvax"
    - "Pool configure callback wraps set_config in set_autocommit(True/False) to satisfy psycopg_pool IDLE invariant"
key_files:
  created:
    - pyproject.toml
    - uv.lock
    - justfile
    - Dockerfile
    - alembic.ini
    - migrations/env.py
    - migrations/versions/0001_create_schema.py
    - migrations/versions/0002_v_collection_view.py
    - fixtures/synth_collection.sql
    - fixtures/boundaries.yaml
    - src/gruvax/__init__.py
    - src/gruvax/settings.py
    - src/gruvax/db/__init__.py
    - src/gruvax/db/pool.py
    - src/gruvax/db/seed_boundaries.py
    - tests/__init__.py
    - tests/conftest.py
  modified:
    - .gitignore
decisions:
  - "search_path set via SQLAlchemy engine connect event (not execute before configure) to preserve Alembic transaction ownership"
  - "alembic_version pinned to public schema (version_table_schema=public) to survive DROP SCHEMA gruvax on downgrade"
  - "psycopg_pool configure callback uses set_autocommit(True/False) to leave connection in IDLE state"
  - "Bootstrap schema creation uses direct psycopg.AsyncConnection with autocommit=True, bypassing SQLAlchemy event"
metrics:
  duration: "~4h (includes 3 auto-fix iterations on transaction management)"
  completed: "2026-05-19"
  tasks_completed: 3
  files_created: 17
  files_modified: 1
---

# Phase 1 Plan 1: Walking Skeleton — uv Project, Alembic Migrations, Synthetic Seeds Summary

Async Alembic migrations establishing gruvax schema with units/cube_boundaries/v_collection, psycopg3 pool with search_path routing, and 152-row synthetic collection + 32-cube YAML boundary fixture.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Scaffold uv project + Wave 0 pytest infrastructure | 13a991c | pyproject.toml, src/gruvax/*, tests/*, justfile, Dockerfile |
| 2 | Alembic async migrations — gruvax schema + v_collection | 8264299 | alembic.ini, migrations/env.py, 0001_create_schema.py, 0002_v_collection_view.py, pool.py |
| 3 | Synthetic seeds — gruvax_dev collection + YAML boundaries | a59d0e1 | fixtures/synth_collection.sql, fixtures/boundaries.yaml, seed_boundaries.py |

## Verification Results

- `alembic upgrade head && alembic downgrade base && alembic upgrade head` exits 0
- `just seed-dev` produces 32 cube boundaries + 152 v_collection rows from clean state
- `alembic_version` lands in `public` schema (verified: `SELECT schemaname FROM pg_tables WHERE tablename='alembic_version'` → `public`)
- `ruff check src/ migrations/` passes
- `uv run python -c "import gruvax.settings"` exits 0
- Repo hygiene: no CSV or background/ files staged

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Alembic migrations executed but never committed**
- **Found during:** Task 2
- **Issue:** `connection.execute(text("SELECT pg_catalog.set_config(...)"))` before `context.configure()` triggered SQLAlchemy's autobegin. Alembic detects `_in_external_transaction = True` and `begin_transaction()` returns `nullcontext()`. Alembic never calls COMMIT. The outer `async with connection:` exit calls rollback on close.
- **Root cause discovery path:** Traced via psycopg `AsyncConnection.commit/rollback` patching — found 3 rollback calls from `engine.close()` with zero commits. SQL was executing correctly (verified via `DefaultDialect.do_execute` patch), but rolling back on connection close.
- **Fix:** Moved search_path setup to a SQLAlchemy engine-level `connect` event listener (`@event.listens_for(connectable.sync_engine, "connect")`). The connect event fires on the raw DBAPI connection before any autobegin, so `_in_external_transaction` stays False and Alembic retains full transaction ownership.
- **Files modified:** `migrations/env.py`
- **Commits:** 8264299

**2. [Rule 2 - Correctness] alembic_version table created in gruvax schema, not public**
- **Found during:** Task 2 (after fix #1)
- **Issue:** With search_path `gruvax, gruvax_dev, public`, unqualified `CREATE TABLE alembic_version` lands in `gruvax`. The downgrade's `DROP SCHEMA gruvax` (without CASCADE) would fail if alembic_version is there. CASCADE would delete it before Alembic's bookkeeping runs.
- **Fix:** Added `version_table_schema="public"` to `context.configure()`. Alembic uses an explicit `public.alembic_version` schema-qualified reference for all version table operations.
- **Files modified:** `migrations/env.py`
- **Commits:** 8264299

**3. [Rule 1 - Bug] psycopg_pool configure callback left connection in INTRANS status**
- **Found during:** Task 3
- **Issue:** `await conn.execute("SELECT pg_catalog.set_config(...)")` in `_configure_connection` starts an implicit transaction (psycopg3 autobegin). psycopg_pool checks `conn.pgconn.transaction_status` after configure and requires `IDLE`; `INTRANS` causes the connection to be discarded. All pool.connection() attempts time out.
- **Fix:** Wrapped the execute in `await conn.set_autocommit(True)` / `await conn.set_autocommit(False)` so no implicit transaction is started.
- **Files modified:** `src/gruvax/db/pool.py`
- **Commits:** 8264299

**4. [Rule 1 - Bug] Bootstrap schema creation failed when engine bootstrap connection got search_path event**
- **Found during:** Task 2
- **Issue:** After adding the connect event listener, the bootstrap connection for `CREATE SCHEMA gruvax` was also subject to the event. The event called `cursor.execute()` (starting a transaction), then `execution_options(isolation_level="AUTOCOMMIT")` failed with `ProgrammingError: can't change 'autocommit' now: connection in transaction status INTRANS`.
- **Fix:** Bootstrap schema creation uses a direct `psycopg.AsyncConnection.connect(url, autocommit=True)` bypassing SQLAlchemy entirely. The connect event only fires for SQLAlchemy-managed connections.
- **Files modified:** `migrations/env.py`
- **Commits:** 8264299

### Version Reconciliations (tracked from plan)

- `aiomqtt` is 2.5.x (no 3.x exists on PyPI)
- `sse-starlette` is 3.4.x (not 2.x as in STACK.md)
- Vite is 8.x (not 7.x as in STACK.md/CLAUDE.md) — frontend not yet set up

## Known Stubs

- `Dockerfile` line 47: `# TODO(plan-04): COPY frontend/dist/ ./static/` — intentional stub, will be resolved in plan 04 when the frontend is built.

## Threat Surface Scan

No new network endpoints, auth paths, or external schema changes introduced. The `v_collection` view is the bounded read surface over discogsography as designed (T-01-01 mitigated: only SELECT granted). T-01-02 mitigated: only synthetic PII-free fixtures committed (verified clean git status).

## Self-Check: PASSED

Files verified present:
- migrations/env.py: FOUND
- migrations/versions/0001_create_schema.py: FOUND
- migrations/versions/0002_v_collection_view.py: FOUND
- fixtures/synth_collection.sql: FOUND
- fixtures/boundaries.yaml: FOUND
- src/gruvax/db/pool.py: FOUND
- src/gruvax/db/seed_boundaries.py: FOUND
- tests/conftest.py: FOUND

Commits verified:
- 13a991c (Task 1): FOUND
- 8264299 (Task 2): FOUND
- a59d0e1 (Task 3): FOUND

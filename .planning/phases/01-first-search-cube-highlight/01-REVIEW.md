---
phase: 01-first-search-cube-highlight
reviewed: 2026-05-20T00:00:00Z
resolution: partial — Phase-1 subset fixed (commit 56bc819); MQTT/security deferred to Phase 5
depth: standard
files_reviewed: 54
files_reviewed_list:
  - alembic.ini
  - compose.yaml
  - docker-entrypoint.sh
  - Dockerfile
  - fixtures/boundaries.yaml
  - fixtures/synth_collection.sql
  - frontend/index.html
  - frontend/package.json
  - frontend/src/api/client.ts
  - frontend/src/api/types.ts
  - frontend/src/App.tsx
  - frontend/src/main.tsx
  - frontend/src/routes/kiosk/Cube.tsx
  - frontend/src/routes/kiosk/kiosk.css
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/NoResultsRow.tsx
  - frontend/src/routes/kiosk/ResultRow.tsx
  - frontend/src/routes/kiosk/ResultsList.tsx
  - frontend/src/routes/kiosk/SearchBox.tsx
  - frontend/src/routes/kiosk/ShelfGrid.test.tsx
  - frontend/src/routes/kiosk/ShelfGrid.tsx
  - frontend/src/routes/kiosk/ShelfLabel.tsx
  - frontend/src/state/store.ts
  - frontend/src/test-setup.ts
  - frontend/vite.config.ts
  - justfile
  - migrations/env.py
  - migrations/versions/0001_create_schema.py
  - migrations/versions/0002_v_collection_view.py
  - mosquitto/mosquitto.conf
  - pyproject.toml
  - src/gruvax/api/deps.py
  - src/gruvax/api/health.py
  - src/gruvax/api/locate.py
  - src/gruvax/api/search.py
  - src/gruvax/api/units.py
  - src/gruvax/app.py
  - src/gruvax/db/pool.py
  - src/gruvax/db/queries.py
  - src/gruvax/db/seed_boundaries.py
  - src/gruvax/estimator/algorithm.py
  - src/gruvax/estimator/boundary_cache.py
  - src/gruvax/estimator/contract.py
  - src/gruvax/estimator/normalize.py
  - src/gruvax/mqtt/client.py
  - src/gruvax/settings.py
  - tests/conftest.py
  - tests/integration/test_cubes_bulk.py
  - tests/integration/test_health.py
  - tests/integration/test_locate.py
  - tests/integration/test_search.py
  - tests/property/test_parser_props.py
  - tests/unit/test_algorithm.py
  - tests/unit/test_normalize.py
findings:
  critical: 5
  warning: 9
  info: 4
  total: 18
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-05-20T00:00:00Z
**Depth:** standard
**Files Reviewed:** 54
**Status:** issues_found

## Resolution (2026-05-20, commit `56bc819`)

**Fixed (Phase-1 correctness/reliability subset):**
- **CR-04** — `/api/search` dedup rewritten as `UNION ALL` + `DISTINCT ON` (was the fragile 8-column `FULL OUTER JOIN`). Verified live: broad query 30 rows / 30 unique, no duplicates.
- **CR-05** — `deps.get_pool`/`get_boundary_cache` now return HTTP 503 instead of `AttributeError`/500 when `app.state` isn't ready.
- **WR-01** — `websearch_to_tsquery` computed once via `CROSS JOIN`.
- **WR-02** — `ResultsList` auto-highlight effect keys on the top result's `release_id`, not the array identity (no more redundant `/api/locate` calls).
- **WR-04** — `docker-entrypoint.sh` waits for Postgres before `alembic upgrade` (no cold-start crash-loop). Verified: stack healthy in ~3s after rebuild.
- **WR-09** — `pool._configure_connection` restores `autocommit=False` in a `finally`.
- **RUF002** — ambiguous `×` → `x` in `test_cubes_bulk.py`.

**Deferred to Phase 5 (LED/MQTT milestone) — MQTT is a no-publish stub in Phase 1:**
- **CR-01** (aiomqtt `__aenter__` lifecycle leak), **CR-02** (default MQTT creds), **CR-03** (mosquitto `allow_anonymous true`). Mosquitto has no exposed host ports in v1.

**Backlog (low-priority warnings/info):** WR-03, WR-05 (`:latest` pin per always-latest directive), WR-06, WR-07, WR-08, IN-01..04, and the `asyncio.DefaultEventLoopPolicy` deprecation (Python 3.16).

Post-fix gates: `ruff` + `mypy --strict` + `pytest` (104) green; deployed stack re-verified end-to-end (search→highlight, 404, no-results, 6 empty cubes).

## Summary

Reviewed the complete Phase 1 walking skeleton: FastAPI backend (Python 3.14), psycopg3 async pool, SQLAlchemy/Alembic migrations, Mosquitto MQTT stub, and a React 19/Vite/Zustand frontend. The core application logic (catalog normalizer, cube-only estimator, SQL parameterization) is well-structured and the test coverage is meaningful. However, five critical issues were found that can cause silent data loss, security exposure, or incorrect behavior in production.

Key concerns:
- The MQTT client is opened via `__aenter__` but the `aiomqtt.Client` context manager starts an internal reconnect loop that is never properly managed — correct disconnect requires `__aexit__` but the error path leaks the underlying connection.
- Default MQTT credentials are hardcoded as plaintext in `settings.py` and echoed verbatim into `compose.yaml`.
- Mosquitto runs `allow_anonymous true` with no password file, exposing the internal broker to any process in the Docker network.
- The SQL query in `queries.py` uses a `DISTINCT ON (release_id)` combined with `ORDER BY release_id, rank DESC` — this is incorrect PostgreSQL syntax for `DISTINCT ON`; the first `ORDER BY` key must match the `DISTINCT ON` key but additional sort criteria can follow. The current query orders by `release_id` first which forces all results for the same `release_id` to be kept by lowest `release_id` value, not by highest `rank` — the Python re-sort compensates but the SQL intent comment is misleading, and there is a subtle correctness issue in the `FULL OUTER JOIN` combination path.
- `app.state.db_pool` is accessed without a guard in `deps.py`; if called during lifespan before the pool is assigned (e.g., a startup probe race) or during shutdown teardown, it raises `AttributeError` crashing the request instead of returning a meaningful error.

---

## Critical Issues

### CR-01: MQTT client lifecycle misuse — `__aenter__`/`__aexit__` called manually on a context-manager-only API

**File:** `src/gruvax/mqtt/client.py:60-61`
**Issue:** `aiomqtt.Client` is documented as an async context manager only. The implementation calls `await client.__aenter__()` directly to enter, which starts the aiomqtt internal network task and reconnect loop. On disconnect, `disconnect_mqtt` calls `await client.__aexit__(None, None, None)`. This pattern is fragile: if `connect_mqtt` fails after `__aenter__` succeeds but before `app.state.mqtt` is set (e.g., the `publish` call raises), `__aexit__` is never called and the internal task leaks for the lifetime of the process. Additionally, aiomqtt v2.x's `__aexit__` is not guaranteed to be re-entrant or safe when called outside its own `async with` block — the library explicitly warns against this in its docs. The correct pattern is `async with aiomqtt.Client(...) as client:` held in a background task, or using the context manager as designed.

**Fix:**
```python
# Wrap the MQTT session in a long-lived task so the context manager
# is used as designed.  The task runs until cancelled at shutdown.
import asyncio

async def _mqtt_session(app: FastAPI) -> None:
    try:
        async with aiomqtt.Client(
            hostname=settings.MQTT_HOST,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            identifier="gruvax-api",
            will=aiomqtt.Will(topic=_HELLO_TOPIC, payload=_HELLO_DEAD, retain=True),
            keepalive=30,
        ) as client:
            await client.publish(_HELLO_TOPIC, payload=_HELLO_ALIVE, retain=True)
            app.state.mqtt = client
            app.state.mqtt_ok = True
            await asyncio.Event().wait()  # hold open until task is cancelled
    except Exception as exc:
        logger.warning("MQTT session ended: %s", exc)
        app.state.mqtt = None
        app.state.mqtt_ok = False

async def connect_mqtt(app: FastAPI) -> None:
    app.state.mqtt = None
    app.state.mqtt_ok = False
    task = asyncio.create_task(_mqtt_session(app))
    app.state.mqtt_task = task
    # Give the connection a moment to establish before continuing lifespan
    await asyncio.sleep(0)

async def disconnect_mqtt(app: FastAPI) -> None:
    task = getattr(app.state, "mqtt_task", None)
    if task is not None:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
```

---

### CR-02: Hardcoded MQTT credentials in settings.py and compose.yaml

**File:** `src/gruvax/settings.py:30-31`, `compose.yaml:47`
**Issue:** `MQTT_USERNAME` defaults to `"gruvax"` and `MQTT_PASSWORD` defaults to `"gruvax"` — plaintext in source code. Even on a home LAN, hardcoded credentials committed to git defeat the purpose of using authentication at all. The compose file also allows `MQTT_PASSWORD` to fall back to an empty string (`${MQTT_PASSWORD:-}`), meaning if the operator does not set the env var, the API connects with no password while Mosquitto accepts anonymous connections — so no auth is enforced end-to-end.

**Fix:**
```python
# settings.py — require credentials to be set explicitly; no insecure default
MQTT_USERNAME: str  # no default — must be set in .env or environment
MQTT_PASSWORD: str  # no default — must be set in .env or environment
```
```yaml
# compose.yaml — no fallback to empty
MQTT_PASSWORD: "${MQTT_PASSWORD}"   # will fail at startup if unset (correct behavior)
```
Also remove the `MQTT_USERNAME: gruvax` default from the `Settings` class.

---

### CR-03: Mosquitto `allow_anonymous true` with no password file — broker accepts unauthenticated connections from any container on the internal network

**File:** `mosquitto/mosquitto.conf:18`
**Issue:** `allow_anonymous true` is set as the active configuration. The password file lines are commented out. The comment in the file correctly notes this is "for initial dev," but the shipped configuration provides no authentication. Any process in the `internal` Docker network (now or after future service additions) can publish or subscribe to any topic, including `gruvax/v1/server/hello`. For a Phase 1 stub this is low risk in isolation, but the LED milestone in Phase 5 will add real retained payloads for physical hardware — if the anonymous config ships as-is into that phase, the broker is fully open. The project's own CLAUDE.md constraint calls for "Username/password auth even on internal network."

**Fix:** Require a passwd file at container start; provide a `make-mosquitto-passwd` recipe in the justfile. At minimum, set a non-empty default password in the Compose environment and document the operator step clearly:
```
# mosquitto.conf — REQUIRED: generate passwd with mosquitto_passwd before first run
password_file /mosquitto/config/passwd
allow_anonymous false
```
Gate the compose `up` on a check that `mosquitto/passwd` exists, or provide a `just init-mqtt` recipe that generates it.

---

### CR-04: `DISTINCT ON (release_id) ORDER BY release_id, rank DESC` is semantically incorrect — the Python re-sort is a band-aid that masks a deeper query bug

**File:** `src/gruvax/db/queries.py:112-124`
**Issue:** PostgreSQL `DISTINCT ON (expr)` keeps the *first row in each group* as determined by the `ORDER BY` clause. The `ORDER BY` here is `release_id, rank DESC`. This means: sort the combined rows by `release_id` ascending, then by `rank` descending within that. `DISTINCT ON` will keep the first row per `release_id`, which is the highest `rank` for that `release_id` — so the deduplication is actually correct for the per-`release_id` selection. However, the final `ORDER BY release_id, rank DESC` sorts the *deduplicated* output by `release_id`, not by `rank`. The kiosk needs results ordered by relevance, not by Discogs ID. The Python `rows.sort(key=lambda r: r.get("rank", 0) or 0, reverse=True)` at line 138 re-sorts to work around this, but the SQL is misleading and the workaround adds O(n log n) Python overhead after every DB round-trip.

More critically: the `FULL OUTER JOIN ... USING (release_id, collection_item_id, title, primary_artist, label, catalog_number, format, year)` at lines 107-110 joins on **all eight columns**. This means a record that appears in both FTS and catalog paths but with even a single column differing (e.g., trailing whitespace in a denormalized label) will produce **two separate rows** in `combined` instead of being merged. Such a record will then appear twice in the final result even after `DISTINCT ON (release_id)` — because `DISTINCT ON` only deduplicates if `release_id` repeats in the `ORDER BY` group, but if the two rows have different `collection_item_id` values they will both survive.

**Fix:** Change the `ORDER BY` inside the outer `SELECT DISTINCT ON` to sort by `rank DESC` so the SQL intent matches reality, and drop the Python re-sort:
```sql
SELECT DISTINCT ON (release_id)
    release_id, collection_item_id, title, primary_artist,
    label, catalog_number, format, year, rank
FROM combined
ORDER BY release_id, rank DESC
LIMIT %s
```
This is already almost correct — the fix is to also return results ordered by rank in the Python caller, or to wrap in a final `ORDER BY rank DESC` using a CTE. For the `FULL OUTER JOIN` issue, join on `release_id` only and use `COALESCE` for all other columns:
```sql
FULL OUTER JOIN cat USING (release_id)
```
(taking `COALESCE` for all non-key columns as already done).

---

### CR-05: `app.state.db_pool` accessed in `deps.py` without guard — `AttributeError` during shutdown or race conditions crashes requests rather than returning a structured error

**File:** `src/gruvax/api/deps.py:25`, `src/gruvax/app.py:44-47`
**Issue:** `get_pool` returns `request.app.state.db_pool` directly. If any request arrives before the lifespan fully completes `app.state.db_pool = pool` (line 46 of `app.py`) — possible under load or when running tests that bypass the lifespan — or if a request is still in flight during the `await pool.close()` teardown, this raises an `AttributeError` that propagates as an unhandled 500. The same issue applies to `get_boundary_cache` for `app.state.boundary_cache`. FastAPI does not catch `AttributeError` in dependencies and will return a bare 500 with a stack trace.

**Fix:**
```python
def get_pool(request: Request) -> AsyncConnectionPool:
    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Database pool not ready")
    return pool

def get_boundary_cache(request: Request) -> BoundaryCache:
    cache = getattr(request.app.state, "boundary_cache", None)
    if cache is None:
        raise HTTPException(status_code=503, detail="Boundary cache not ready")
    return cache
```

---

## Warnings

### WR-01: `search_collection` passes `q` three times but comment says "q appears 3 times" — FTS `WHERE` and `ts_rank_cd` both consume a copy, but `websearch_to_tsquery` is evaluated twice

**File:** `src/gruvax/db/queries.py:71-73`, `129`
**Issue:** The FTS CTE calls `websearch_to_tsquery('english', %s)` twice — once in the `WHERE` clause and once in `ts_rank_cd`. Postgres will evaluate this function twice per row, which is wasteful. More importantly, the query binds `(q, q, q, limit)` but the SQL text has `%s` at positions: FTS-rank, FTS-WHERE, catalog-LIKE, and LIMIT — four positions. The comment at line 128 says "q appears 3 times" which matches the four `%s` bindings (rank, WHERE, LIKE, LIMIT). This is actually fine — `limit` is the fourth — but the mismatch in the comment is a maintenance hazard. A future edit that adds or removes a `%s` will cause a `ProgrammingError` at runtime if it mismatches the 4-tuple.

**Fix:** Use a CTE or a lateral query to compute `websearch_to_tsquery` once, and update the comment to say "q appears 3 times, limit is the 4th binding":
```sql
WITH q_tsq AS (
    SELECT websearch_to_tsquery('english', %s) AS tsq
),
fts AS (
    SELECT ..., ts_rank_cd(fts_vector, (SELECT tsq FROM q_tsq), 4) AS score
    FROM gruvax.v_collection, q_tsq
    WHERE fts_vector @@ (SELECT tsq FROM q_tsq)
    ...
)
```
Bindings become `(q, q, limit)`.

---

### WR-02: `ResultsList` fires `locateRelease` on every `items` array reference change, not on actual top-result change — can trigger redundant locate calls

**File:** `frontend/src/routes/kiosk/ResultsList.tsx:35-50`
**Issue:** The `useEffect` that auto-selects the top result depends on `[items]`. The `items` prop is `searchData?.items ?? []` — a new array reference is created on every render (the `?? []` fallback creates a new `[]` each render). If `KioskView` re-renders for any reason while the search data is cached (e.g., mouse movement causing a state update), a new `[]` array is passed, the effect fires, `items.length === 0` so nothing happens — but if `items` is non-empty, a locate call is fired again for the already-selected top result. TanStack Query deduplicates the locate fetch if it is in-flight, but `setHighlightCube` is still called on every effect invocation unnecessarily.

The `eslint-disable-next-line react-hooks/exhaustive-deps` comment at line 49 suppresses the warning that `setSelectedResult`, `setSelectedReleaseId`, and `setHighlightCube` are missing from the dependency array — these are Zustand setters and are stable references, so their absence is intentional, but the comment hides the real issue: `items` itself is an unstable reference.

**Fix:** Memoize `searchResults` in `KioskView` so the reference is stable when content is unchanged:
```tsx
// KioskView.tsx
const searchResults = useMemo(
  () => searchData?.items ?? [],
  [searchData]
)
```
Then `items` reference changes only when `searchData` changes, not on every render.

---

### WR-03: `catalog_in_range` returns `True` when both `first_catalog` and `catalog` are sentinels (None / "none" / etc.) — a cube with `first_catalog=None` would incorrectly match a record with `catalog_number=None`

**File:** `src/gruvax/estimator/normalize.py:154-170`, `src/gruvax/estimator/algorithm.py:73`
**Issue:** `parse_key(None)` returns `_SENTINEL = ((-1, 0),)`. `catalog_in_range(None, None, None)` evaluates `_SENTINEL <= _SENTINEL <= _SENTINEL` which is `True`. The algorithm at line 73 of `algorithm.py` guards against empty cubes with `b.is_empty or b.first_label is None or b.last_label is None`, but does NOT guard against `b.first_catalog is None` and `b.last_catalog is None` together. The `is_empty` flag is the intended guard for this case; however, if a boundary row is inserted with `is_empty=False` but `first_catalog=None` and `last_catalog=None` (which the DB `empty_or_complete` CHECK constraint prevents, but which the Python test helper `_make_cache_from_yaml` does not enforce), the `catalog_in_range` check would return `True` for any null-catalog record against that row. The DB constraint makes this safe in production, but the algorithm has a latent correctness gap.

**Fix:** Add an explicit guard in `locate_cube_only`:
```python
if b.is_empty or b.first_label is None or b.last_label is None \
        or b.first_catalog is None or b.last_catalog is None:
    continue
```

---

### WR-04: `docker-entrypoint.sh` runs `alembic upgrade head` without a retry or database-ready check — container will crash-loop if Postgres is not yet accepting connections

**File:** `docker-entrypoint.sh:10`
**Issue:** The entrypoint runs `alembic upgrade head` as the first command. If the Postgres container (whether host-based via `host.docker.internal` or via the `discogsography_default` network) is not yet ready to accept connections, alembic exits non-zero and Docker restarts the container (`restart: unless-stopped`). Docker Compose does not have a `depends_on` for the external Postgres host, so under concurrent `docker compose up` or after a host restart, repeated crash-loops are expected before the API becomes healthy. There is no `mosquitto` dependency issue here (it has a `healthcheck`), only Postgres.

**Fix:** Add a wait loop before the alembic call:
```sh
#!/bin/sh
set -e
PYTHON="/app/.venv/bin/python"

# Wait for Postgres to accept connections (max 60s)
until "$PYTHON" -c "
import psycopg, os, sys
try:
    psycopg.connect(os.environ['DATABASE_URL'].replace('postgresql+psycopg://', 'postgresql://', 1)).close()
    sys.exit(0)
except Exception:
    sys.exit(1)
"; do
    echo "Waiting for Postgres..."
    sleep 2
done

"$PYTHON" -m alembic upgrade head
exec "$PYTHON" -m uvicorn gruvax.app:app --host 0.0.0.0 --port 8000
```

---

### WR-05: `compose.yaml` uses `eclipse-mosquitto:latest` — unpinned image tag will silently break on broker API changes

**File:** `compose.yaml:75`
**Issue:** The Mosquitto service uses `eclipse-mosquitto:latest`. The CLAUDE.md stack recommendation specifies `eclipse-mosquitto:2.1-alpine`. Using `latest` means a future `docker compose pull` or `docker compose up --build` on a fresh machine can pull Mosquitto 3.x or later, which may have breaking config syntax changes. This has already diverged from the stated constraint.

**Fix:**
```yaml
mosquitto:
  image: eclipse-mosquitto:2.1-alpine
```

---

### WR-06: `migrations/env.py` builds `search_path_value` via f-string interpolation of `OBSERVED_DISCOGSOGRAPHY_SCHEMA` in the `set_search_path` event callback, then executes it via a cursor — partial SQL injection risk from the schema name

**File:** `migrations/env.py:96`, `src/gruvax/db/pool.py:61`
**Issue:** Both `env.py` and `pool.py` build `search_path_value = f"gruvax, {schema}, public"` and then pass this as a **parameter value** to `pg_catalog.set_config(...)` — which is safe because `set_config` receives it as a typed string, not as SQL syntax. However, in `env.py` the value comes from `settings.OBSERVED_DISCOGSOGRAPHY_SCHEMA` which is a plain `str` field with no format validation. A value like `gruvax; DROP SCHEMA gruvax;` would be passed as the `search_path` string value to `set_config`, which Postgres would reject as an invalid search path, not execute as SQL — so this is NOT a SQL injection vector in practice. But it is a misconfiguration risk: an attacker who can set an env var could cause `alembic upgrade head` to fail with a confusing error.

More concretely: `pool.py` does the same thing (line 61) and comments "pg_catalog.set_config ... fully parameterises the value" which is correct. The `env.py` version (lines 119-120) uses the exact same pattern, which is also correct. The warning here is that `OBSERVED_DISCOGSOGRAPHY_SCHEMA` has no regex validation to ensure it is a valid schema identifier. A typo or injection attempt silently degrades into a Postgres error.

**Fix:** Add a validator to `settings.py`:
```python
from pydantic import field_validator
import re

@field_validator("OBSERVED_DISCOGSOGRAPHY_SCHEMA")
@classmethod
def validate_schema_name(cls, v: str) -> str:
    if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", v):
        raise ValueError(f"Invalid schema name: {v!r}")
    return v
```

---

### WR-07: `KioskView` hardcodes `SHELF_NAMES = ['SHELF A', 'SHELF B', 'SHELF C', 'SHELF D']` and uses `idx` to index it — silently falls back to `SHELF ${idx+1}` for units beyond index 3, but the fallback placeholder grid also uses the same hardcoded list

**File:** `frontend/src/routes/kiosk/KioskView.tsx:11`, `frontend/src/routes/kiosk/KioskView.tsx:136`, `frontend/src/routes/kiosk/KioskView.tsx:151`
**Issue:** `SHELF_NAMES[idx] ?? \`SHELF ${idx + 1}\`` at line 136 is safe for up to 4 units. The fallback placeholder grid at lines 149-160 hard-codes `[0, 1].map(...)` — always renders exactly 2 placeholder shelves, regardless of how many units the API eventually returns. If the API data is slow to load and the user sees the placeholder, then 3+ units load, there is a jarring layout shift. More importantly, the `display_name` field from the units API is ignored — the UI always uses `SHELF A/B/C/D`, so if an operator renames a unit in the DB, the kiosk ignores it.

**Fix:** Use `unit.display_name` from the API response as the shelf label (falling back to `SHELF_NAMES[idx]` only when `display_name` is empty). Remove the hardcoded `[0, 1]` in the placeholder path; instead, derive the placeholder count from a config constant.

---

### WR-08: `locateRelease` in `client.ts` discards the 404 error message — `throw new Error('release_not_in_collection')` replaces the structured API body with a plain string

**File:** `frontend/src/api/client.ts:28-30`
**Issue:** When the server returns HTTP 404 with `{"detail": {"type": "release_not_in_collection", "release_id": ...}}`, the client discards all structured information and throws `Error('release_not_in_collection')`. `ResultsList.tsx` catches this in `.catch(() => { setHighlightCube(null) })` — the error is silently swallowed. There is no path to surface the structured error to the user. While this is acceptable for Phase 1 (the locate call happens on a record that was just returned by search, so 404 should be impossible in normal flow), a release that exists in the search index but is deleted before the locate call returns will silently clear the highlight with no feedback.

**Fix:** Preserve the structured error or at minimum throw a typed error:
```typescript
if (res.status === 404) {
  const body = await res.json().catch(() => ({}))
  throw Object.assign(new Error('release_not_in_collection'), { detail: body.detail })
}
```

---

### WR-09: `_configure_connection` in `pool.py` toggles `autocommit` around `set_config` but does not restore it if `set_config` raises — leaves the connection in autocommit mode

**File:** `src/gruvax/db/pool.py:62-67`
**Issue:** The configure callback does:
```python
await conn.set_autocommit(True)
await conn.execute("SELECT pg_catalog.set_config(...)", ...)
await conn.set_autocommit(False)
```
If the `execute` call raises (e.g., Postgres rejects the search path value), `set_autocommit(False)` is never called. `psycopg_pool` requires the connection to be in `IDLE` transaction status after the configure callback; a connection stuck in autocommit mode will likely be discarded by the pool, which is the correct behavior — but psycopg3 autocommit mode is a connection-level flag, not a transaction state. The real issue: if the `execute` raises and the connection is returned to the pool in autocommit mode, subsequent callers that rely on transaction semantics (e.g., `conn.transaction()`) will behave incorrectly.

**Fix:**
```python
async def _configure_connection(conn: AsyncConnection) -> None:
    schema = settings.OBSERVED_DISCOGSOGRAPHY_SCHEMA
    search_path_value = f"gruvax, {schema}, public"
    await conn.set_autocommit(True)
    try:
        await conn.execute(
            "SELECT pg_catalog.set_config('search_path', %s, false)",
            (search_path_value,),
        )
    finally:
        await conn.set_autocommit(False)
```

---

## Info

### IN-01: `SearchResult` TypeScript interface is missing `collection_item_id` — present in the API response but absent from the frontend type

**File:** `frontend/src/api/types.ts:9-18`
**Issue:** The backend `search_collection` query returns `collection_item_id` in every row (confirmed in `queries.py` lines 64-65 and the `test_response_shape` test at line 175 of `test_search.py`). The `SearchResult` TypeScript interface omits it. This means calling code cannot access `collection_item_id` from search results in a type-safe manner. The field is in the runtime payload but invisible to TypeScript.

**Fix:**
```typescript
export interface SearchResult {
  release_id: number
  collection_item_id: number  // add this field
  title: string
  primary_artist: string
  label: string
  catalog_number: string
  format: string
  year: number | null
  rank: number
}
```

---

### IN-02: `alembic.ini` contains a real database URL as the default `sqlalchemy.url` — a developer running `alembic` without setting `DATABASE_URL` will silently connect to `localhost:5432`

**File:** `alembic.ini:91`
**Issue:** `sqlalchemy.url = postgresql+psycopg://gruvax:gruvax@localhost:5432/gruvax` is the fallback. `env.py` overrides this at runtime via `config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)` — but only if `Settings()` can be instantiated (i.e., `DATABASE_URL` is in the environment). If `DATABASE_URL` is not set, `Settings()` raises a `ValidationError` at import time, which means alembic's `env.py` fails before it can override the ini value. So the ini default never actually takes effect as a connection fallback — but it still documents real credentials and a real host, which is a hygiene issue.

**Fix:** Replace with a clearly invalid placeholder:
```ini
sqlalchemy.url = postgresql+psycopg://REPLACE_VIA_ENV@localhost/gruvax
```

---

### IN-03: `pyproject.toml` comment acknowledges `aiomqtt` version mismatch — constraint says "3.x" but installed is `>=2.5`

**File:** `pyproject.toml:98-100`
**Issue:** The comment at the bottom of `pyproject.toml` correctly notes that aiomqtt "3.x" referenced in CLAUDE.md and STACK.md does not exist on PyPI (latest is 2.5.1). The `mqtt/client.py` code is compatible with 2.x but the documented constraint is wrong. This is a documentation debt that will cause confusion when a future developer reads CLAUDE.md and tries to install "aiomqtt 3.x".

**Fix:** Update CLAUDE.md's stack table to reflect the actual installed version (`aiomqtt>=2.5`). This is documentation-only but materially affects developer onboarding.

---

### IN-04: `ShelfGrid.tsx` uses `React.ReactNode[]` as the cells array type but `React` is not imported

**File:** `frontend/src/routes/kiosk/ShelfGrid.tsx:32`
**Issue:** `const cells: React.ReactNode[] = []` references `React.ReactNode` but the file does not import `React`. This works in React 17+ with the new JSX transform and TypeScript because `React` is globally available in the JSX namespace — but it is a style inconsistency that may cause `noImplicitAny` or `noUnusedLocals` warnings in stricter TS configs, and is confusing to readers.

**Fix:** Either add `import type { ReactNode } from 'react'` and use `ReactNode[]`, or use the JSX-native `JSX.Element[]` type:
```tsx
import type { ReactNode } from 'react'
// ...
const cells: ReactNode[] = []
```

---

_Reviewed: 2026-05-20T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

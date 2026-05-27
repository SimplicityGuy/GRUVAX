# Phase 1: Walking skeleton — API client + single-profile sync - Pattern Map

**Mapped:** 2026-05-26
**Files analyzed:** 22 (14 new, 8 modified)
**Analogs found:** 22 / 22 (every new file has a strong intra-repo analog)

> Read this with CONTEXT.md `<code_context>` and RESEARCH.md §Architecture Patterns open. Excerpts below are lifted from real files — copy them, then adapt the names. Line numbers cited are accurate as of 2026-05-26 (HEAD `4bbd086`).

---

## File Classification

### New files

| File | Role | Data Flow | Closest Analog | Match |
|------|------|-----------|----------------|-------|
| `src/gruvax/discogsography/__init__.py` | package-init | n/a | `src/gruvax/auth/__init__.py` | exact (trivial — empty/marker) |
| `src/gruvax/discogsography/client.py` | service (HTTP client) | request-response (paged egress, retry) | `src/gruvax/mqtt/client.py` (only existing external-network client) | role-match (lifespan-owned, app.state-bound) |
| `src/gruvax/discogsography/errors.py` | utility (exception classes) | n/a | `src/gruvax/auth/sessions.py` (typed-error consumers); psycopg-shaped errors in `db/queries.py` | role-match |
| `src/gruvax/discogsography/log_redactor.py` | utility (structlog processor) | event-driven (in-process) | `src/gruvax/logging_config.py::_orjson_serializer` + `shared_processors` chain | role-match |
| `src/gruvax/sync/__init__.py` | package-init | n/a | `src/gruvax/auth/__init__.py` | exact |
| `src/gruvax/sync/pat_crypto.py` | utility (crypto helpers) | transform | `src/gruvax/auth/pin.py` | exact (same shape: top-level `_ctx`, hash/verify pair) |
| `src/gruvax/sync/profile_sync.py` | service (orchestration) | batch (COPY-staging-swap + advisory lock) | `src/gruvax/api/admin/editing.py` + `db/queries.py::write_boundary/write_history_row` (transaction patterns) | role-match (no existing staging-swap to copy verbatim) |
| `src/gruvax/api/admin/profile_sync.py` | api-route | request-response | `src/gruvax/api/admin/editing.py` (smallest admin POST endpoint w/ require_admin) | exact |
| `src/gruvax/cli/set_pat.py` | cli | request-response (one-shot) | `src/gruvax/cli/set_pin.py` | exact (same scaffold, different secret type) |
| `src/gruvax/cli/sync_cli.py` | cli | request-response (HTTP) | `src/gruvax/cli/set_pin.py` (entry-point scaffold) + `tests/integration/test_search_benchmark.py` (httpx client construction) | role-match |
| `migrations/versions/0009_v2_profiles_and_collection_cache.py` | migration | DDL | `migrations/versions/0002_v_collection_view.py` (view DROP/recreate + GRANT comments) + `0008_record_stats.py` (CREATE TABLE + INDEX shape) | exact |
| `tests/fixtures/__init__.py` | test-fixture (package marker) | n/a | `tests/integration/__init__.py` | exact |
| `tests/fixtures/fake_discogsography.py` | test-fixture (in-memory FastAPI) | event-driven | `src/gruvax/app.py::create_app` (FastAPI factory) + `tests/integration/test_search_benchmark.py::search_client` (ASGITransport client wiring) | role-match |
| `tests/fixtures/synth_profile_collection.sql` | test-fixture (SQL seed) | DDL/DML | `fixtures/synth_collection.sql` | exact (rewrite of) |
| `tests/fixtures/synth_profile_collection_seed.yaml` | test-fixture (data seed) | data | `fixtures/boundaries.yaml` (YAML loaded by tests) | role-match |
| `services/fake-discogsography/Dockerfile` + compose entry | infra | n/a | `compose.yaml` `api:` + `mosquitto:` service blocks; root `Dockerfile` for the multi-stage uv build | role-match |

### Modified files (existing — analog IS the file itself; patterns to preserve)

| File | Modification | What to preserve |
|------|--------------|------------------|
| `src/gruvax/settings.py` | Add `DISCOGSOGRAPHY_BASE_URL` (str, no default), `GRUVAX_SECRET_KEY` (SecretStr + validator). Remove `OBSERVED_DISCOGSOGRAPHY_SCHEMA`. | Pydantic-settings boot-fail convention; ASCII section headers; "No default" comment above hard-required vars (mirrors `DATABASE_URL` line 21 + `SESSION_SECRET` line 45). |
| `src/gruvax/db/pool.py` | Simplify `_configure_connection` — drop `OBSERVED_DISCOGSOGRAPHY_SCHEMA` branch; set `search_path = "gruvax, public"`. | Keep the autocommit/autocommit-restore pattern (lines 68-77); keep `pg_catalog.set_config('search_path', %s, false)` parameterization. |
| `src/gruvax/db/queries.py` | Rewire `search_collection`, `get_release_for_locate`, `did_you_mean_query`, `get_distinct_labels`, `get_catalogs_for_label`, `cube_exact_match`, `get_phantom_boundary_count`, `get_top_searched`, `get_sync_staleness_seconds` from `gruvax.v_collection` to `gruvax.profile_collection WHERE profile_id = %s::uuid`. | `%s` placeholder convention (T-01-07); module docstring listing every function; `async with pool.connection() as conn, conn.cursor() as cur` idiom. |
| `src/gruvax/estimator/collection_snapshot.py` | `load()` query swap; query targets `profile_collection` with `WHERE profile_id = %s::uuid`. | Existing `invalidate()` seam (lines 109-121); `_load_snapshot` test seam (lines 86-94); Pitfall C label-casefold rule (lines 73-74). |
| `src/gruvax/app.py` | Step 2 probe targets `profile_collection`; step 1c `_refresh_sync_age` reads `profiles.last_sync_at` instead of `max(v_collection.synced_at)`; add `DiscogsographyClient` lifecycle (optional — RESEARCH §Open Q3 says per-sync is fine for P1). | Lifespan numbered-section comments; CR-01 strong-reference pattern for background tasks (lines 204-211); `try/except + logger.error + proceed` (steps 3, 3b, 3c, 3e). |
| `src/gruvax/api/health.py` | Rename `discogsography_view_check` → `discogsography_api_check`; widen union to `'ok' \| 'failed' \| 'stale'`; derive from `app.state.profile_sync_state` populated by `_refresh_sync_age`. | "No live probe" rule (docstring lines 35-43); always HTTP 200 + JSON envelope. |
| `src/gruvax/api/admin/router.py` | Register the new `profile_sync_router`. | Module-top import order; alphabetic-ish include_router calls. |
| `pyproject.toml` | Add `cryptography>=48`, `stamina>=26`, `pytest-httpx>=0.36` (dev); add `gruvax-set-pat`, `gruvax-sync` entry points. | The `[project.scripts]` block at line 33; the existing `gruvax-set-pin = "gruvax.cli.set_pin:main"` line shows exact format. |
| `compose.yaml` | Remove `OBSERVED_DISCOGSOGRAPHY_SCHEMA` env line; add `DISCOGSOGRAPHY_BASE_URL`, `GRUVAX_SECRET_KEY`; add `fake-discogsography` sibling service block. | The `${VAR:-default}` substitution pattern; `depends_on: condition: service_healthy` block; explicit `networks: - internal`; multi-line `healthcheck` array. |

---

## Pattern Assignments

### 1. `src/gruvax/cli/set_pat.py` (cli, request-response one-shot)

**Analog:** `src/gruvax/cli/set_pin.py` (entire file — 57 lines; copy the scaffold verbatim).

**Imports & docstring header** (set_pin.py:1-29):
```python
"""Bootstrap CLI to provision or rotate the admin PIN hash in ``gruvax.settings``.

Usage::

    uv run gruvax-set-pin
[...security notes prose...]
Requires DATABASE_URL and SESSION_SECRET in environment / .env.
"""

from __future__ import annotations

import asyncio
import getpass
import sys

from gruvax.auth.pin import hash_pin
from gruvax.db.pool import get_pool_context
```

**Async body + commit pattern** (set_pin.py:31-46):
```python
async def _set_pin(pin: str) -> None:
    """Hash the PIN and upsert into gruvax.settings."""
    if not pin.isdigit() or len(pin) != 4:
        sys.exit("PIN must be exactly 4 numeric digits (e.g. 1234)")

    h = hash_pin(pin)

    async with get_pool_context() as pool, pool.connection() as conn:
        await conn.execute(
            "INSERT INTO gruvax.settings (key, value, description, updated_at)"
            " VALUES ('auth.pin_hash', %s::jsonb, 'Argon2id-hashed admin PIN', now())"
            " ON CONFLICT (key) DO UPDATE"
            "  SET value = EXCLUDED.value, updated_at = now()",
            (f'"{h}"',),
        )
        await conn.commit()
```

**Entry-point shape** (set_pin.py:49-56):
```python
def main() -> None:
    """Entry point for ``gruvax-set-pin`` CLI script."""
    pin = getpass.getpass("Enter new PIN (4 digits): ")
    asyncio.run(_set_pin(pin))


if __name__ == "__main__":
    main()
```

**Conventions to copy verbatim:**
- `from __future__ import annotations` (project-wide).
- `async def _<verb>(...)` private worker + thin sync `main()` calling `asyncio.run(_worker(...))`.
- `async with get_pool_context() as pool, pool.connection() as conn:` — one chained context manager, never the longer 2-line form.
- `await conn.commit()` explicit (autocommit is OFF in the pool; never elide).
- Failure mode: `sys.exit("plain English error message")` — no logging, no exceptions, no traceback.
- Docstring uses RST `::` literal blocks for usage examples.

**What to do differently (vs set_pin.py):**
- **Secret type is Fernet ciphertext, not Argon2id.** Hash via `gruvax.sync.pat_crypto.encrypt_pat(pat)` (returns `bytes`), not `hash_pin(pin)` (returns `str`).
- **Stdin-only, never `getpass.getpass()` unconditionally.** Per D-07 the contract is: `if sys.stdin.isatty(): getpass.getpass("Paste PAT (input hidden): ")` else `sys.stdin.read().strip()`. set_pin.py is keyboard-only because admins always type the PIN; PAT is owner-pasted, often piped.
- **Two-step write: inline test-sync, then DB write (D-08).** set_pin.py is one-shot DB write; set_pat.py must first construct `DiscogsographyClient`, call `_get_page(limit=1, offset=0)`, validate `releases[0].catalog_number` is present, capture `user_id`, then proceed to encrypt + UPDATE. On PATRejected: `sys.exit("PAT rejected by discogsography (401/403). Not stored.")` — leaving the row untouched.
- **Strict rotation check (D-09).** Before UPDATE, `SELECT discogsography_user_id FROM gruvax.profiles WHERE display_name = %s AND deleted_at IS NULL`. If non-NULL and `!= new_user_id`, refuse with the exact wording from D-09: `"PAT belongs to a different discogsography user (was <old>, got <new>). Soft-delete the profile first if you really intend to switch."`
- **`--profile` argparse flag** (set_pin.py has no args; set_pat.py needs `--profile default`).
- **Add a `--profile` arg via `argparse.ArgumentParser` at module top of `main()`** — keeps the scaffold close to set_pin.py while adding the one needed flag.

**Data flow:**
```
operator (stdin) → main() → _set_pat(profile, pat)
  → DiscogsographyClient(base_url=settings.DISCOGSOGRAPHY_BASE_URL, pat=pat)
    → GET /api/user/collection?limit=1 (in-process test sync)
  → encrypt_pat(pat) (Fernet ciphertext, bytes)
  → UPDATE gruvax.profiles SET app_token_encrypted=%s, ..., discogsography_user_id=COALESCE(...)
  → exit 0 + print "Run gruvax-sync --profile default to perform the full sync."
```

---

### 2. `src/gruvax/cli/sync_cli.py` (cli, request-response over HTTP)

**Analog:** `src/gruvax/cli/set_pin.py` (scaffold) + `tests/integration/test_search_benchmark.py:31-43` (httpx async client construction).

**Differences from set_pin scaffold:**
- Replace `get_pool_context()` + `conn.execute(...)` body with `httpx.AsyncClient(base_url=GRUVAX_BASE_URL)` doing `POST /api/admin/login` then `POST /api/admin/profiles/{profile_id}/sync`.
- PIN prompt via `getpass.getpass("Enter admin PIN (4 digits): ")`.
- Stream response lines to stdout as plain text (per RESEARCH §Open Q2 recommendation: plain text on stdout, not structlog-JSON).
- `--profile default` argparse flag (same as set_pat.py).
- Exit code 0 on `{"status": "ok"}`, non-zero with stderr on any error.

**PIN flow recommendation** (per RESEARCH §Open Q1, Option (a) — reuse v1 admin flow verbatim, see `src/gruvax/api/admin/login.py:77-158` for the contract):
```python
# Pseudocode skeleton (full impl follows set_pin.py scaffold)
async def _run_sync(profile_id: str, pin: str) -> None:
    base_url = os.environ.get("GRUVAX_BASE_URL", "http://localhost:8000")
    async with httpx.AsyncClient(base_url=base_url, cookies=httpx.Cookies()) as client:
        # 1. Login — captures session cookie + CSRF in the response body
        login_resp = await client.post("/api/admin/login", json={"pin": pin})
        if login_resp.status_code != 200:
            sys.exit(f"Admin login failed: HTTP {login_resp.status_code}")
        csrf_token = login_resp.json()["csrf_token"]
        # 2. Trigger sync — cookies auto-carried; CSRF must be echoed in header
        sync_resp = await client.post(
            f"/api/admin/profiles/{profile_id}/sync",
            headers={"X-CSRF-Token": csrf_token},
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0),  # sync can take ~tens of seconds
        )
        if sync_resp.status_code != 200:
            sys.exit(f"Sync failed: HTTP {sync_resp.status_code}: {sync_resp.text}")
        print(sync_resp.json())
```

**Conventions to copy verbatim:**
- `from __future__ import annotations` + `async def _run_sync(...) → None` + sync `main()` wrapper.
- `sys.exit("plain message")` on every failure path.
- `argparse.ArgumentParser` with `--profile` required.

**What to do differently:**
- No `get_pool_context()` — this CLI never touches the DB. It's a thin HTTP client that POSTs into the running FastAPI process.
- Generous `httpx.Timeout(read=120.0)` because the sync runs in-process and the response only returns after staging-swap + cache refresh complete (~tens of seconds for ~3000 rows).

---

### 3. `src/gruvax/api/admin/profile_sync.py` (api-route, request-response)

**Analog:** `src/gruvax/api/admin/editing.py` (78 lines — the smallest existing admin POST endpoint w/ `require_admin`).

**Module docstring + imports** (editing.py:1-23):
```python
"""POST /api/admin/editing — admin_editing heartbeat (D-01, D-03).
[...prose explaining what + why...]
Security:
  - Session + CSRF gated via ``require_admin`` (same as every admin write).
  - Body validated by Pydantic ``EditingPayload`` (typed cube_ids ints + editing bool).
  - ``model_dump()`` emits only validated fields onto the bus — no raw client strings.
  (T-04-08, T-04-11)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from gruvax.api.deps import get_event_bus, require_admin
```

**Router declaration** (editing.py:30-32):
```python
logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-editing"])
```

**Handler shape** (editing.py:60-78):
```python
@router.post("/editing")
async def signal_editing(
    body: EditingPayload,
    bus: EventBus = Depends(get_event_bus),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Fan-out admin_editing event — no DB write, no state stored.
    [...]
    """
    await bus.publish("admin_editing", body.model_dump())
    logger.debug(...)
    return JSONResponse(content={"ok": True})
```

**Conventions to copy verbatim:**
- Tag prefix `tags=["admin-<topic>"]` (here: `tags=["admin-profile-sync"]`).
- Underscore-prefixed deps that the handler doesn't reference: `_admin: dict[str, Any] = Depends(require_admin)`.
- Pydantic request body `model_config = {"extra": "forbid"}` (editing.py:39) — copy this verbatim to reject unknown fields.
- Module docstring header lists endpoints + Security section with `require_admin` mention.

**What to do differently:**
- **Path is `POST /profiles/{profile_id}/sync` not `/editing`.** Use FastAPI's `profile_id: str` path param; validate as UUID inside the handler (`uuid.UUID(profile_id)` — raises `ValueError` → return 400).
- **Holds a DB pool slot for the duration of the sync** — per Pitfall 6 in RESEARCH.md, take a dedicated standalone connection (`await psycopg.AsyncConnection.connect(_conninfo(settings.DATABASE_URL))`) so the pool isn't starved during the ~tens-of-seconds sync. Reuse `gruvax.db.pool._conninfo` (already exported via `from gruvax.db.pool import _conninfo` is acceptable; or factor out to a public helper in the same plan).
- **Response is `{"status": "ok", "item_count": N, "took_ms": T}` not `{"ok": True}`.**
- **Handler body delegates to `sync_profile(profile_id, app_state)` in `gruvax.sync.profile_sync`** — the route is a thin wrapper. All staging/swap/cache-refresh logic lives in `sync_profile`.
- **Register in `src/gruvax/api/admin/router.py`** alongside `diagnostics_router` (router.py:48-49 shows the pattern — one `router.include_router(...)` line per sub-router).

---

### 4. `src/gruvax/discogsography/client.py` (service, request-response with retry)

**Analog:** No existing httpx client in the repo — `src/gruvax/mqtt/client.py` is the closest external-network client (different protocol, but the same "lifespan-owned, app.state-bound, typed errors" shape applies).

**Primary template:** RESEARCH.md §Pattern 1 lines 188-288 (the full client skeleton — copy that into `client.py` directly, then adapt names). The skeleton has been crafted to match the project conventions; no separate analog excerpt is needed.

**Companion file `errors.py`** — analog: `src/gruvax/auth/sessions.py` (project's pattern for typed error sentinels consumed by callers). Define:
```python
class DiscogsographyError(Exception):
    """Base for all DiscogsographyClient errors. Plain Python exceptions — no Pydantic."""

class PATRejected(DiscogsographyError):
    """401/403 from discogsography — terminal, no retry. Caller sets app_token_revoked=TRUE."""

class RateLimitExhausted(DiscogsographyError):
    """429 retried max times — propagates `last_sync_error = 'rate_limited'`."""

class ServerError(DiscogsographyError):
    """5xx retried max times — propagates `last_sync_error = 'server_error'`."""

class NetworkError(DiscogsographyError):
    """Connect/Read/WriteTimeout retried once then failed — `'network'`."""

class SyncInProgress(DiscogsographyError):
    """pg_try_advisory_lock returned FALSE — another sync is already running for this profile."""
```

**Conventions to copy verbatim from elsewhere in the repo:**
- Module docstring lists every public name (mirrors `db/queries.py:1-26`).
- `from __future__ import annotations` + `if TYPE_CHECKING:` blocks for `psycopg`/`AsyncConnectionPool`-only imports (see `db/pool.py:14-25` for the exact idiom).
- Single long-lived `httpx.AsyncClient` constructed in `__init__`, closed by `aclose()` — never per-request. The shape mirrors how `src/gruvax/app.py:114-116` owns the `AsyncConnectionPool`.

**What to do differently from RESEARCH §Pattern 1:**
- **Pull `user_id` out of the first page once** rather than parsing it on every page. RESEARCH §Pattern 2 already does this in `_ingest_into_staging`; keep `iter_collection` for "just give me the rows" and add a separate `fetch_first_page() → dict` if the caller needs the envelope. Don't reach into `client._get_page(...)` directly from `sync_profile` — give it a public API (e.g., `iter_collection_with_envelope() → AsyncIterator[tuple[dict, dict]]` yielding `(envelope, release)` pairs, or simpler: `async def first_page() → dict` + `async def iter_collection() → AsyncIterator[dict]`).
- **Test access:** unit tests will substitute the `_client` field with an `AsyncClient(transport=ASGITransport(app=fake_app))`. RESEARCH §Pattern 4 already shows this. Make the attribute name `_client` (single underscore) so test access reads "we know we're poking the private API for testing."

**Data flow:**
```
sync_profile() / set_pat.py → DiscogsographyClient(base_url, pat)
  → self._client.get("/api/user/collection?limit=200&offset=N")
    → stamina retry: 429 → Retry-After; 5xx → exp backoff; 401/403 → raise PATRejected
  → AsyncIterator[dict] of releases
```

---

### 5. `src/gruvax/sync/pat_crypto.py` (utility, transform)

**Analog:** `src/gruvax/auth/pin.py` (entire file — 58 lines).

**Module-level singleton + helper pair pattern** (pin.py:18-37):
```python
# Argon2id context — memory-hard, GPU-resistant (T-03-04).
# ``deprecated="auto"`` ensures older hash schemes are upgraded on next verify.
_ctx = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_pin(pin: str) -> str:
    """Hash a 4-digit PIN using Argon2id.

    Each call produces a unique hash (random salt) even for the same PIN.
    Store the result in ``gruvax.settings`` key ``auth.pin_hash`` — never in
    an environment variable, config file, or source code.
    """
    return _ctx.hash(pin)
```

**Verify pair with try/except → False** (pin.py:39-57):
```python
def verify_pin(pin: str, hashed: str) -> bool:
    """Constant-time verify a PIN against its Argon2id hash.

    Returns ``False`` (not raises) on mismatch, empty input, or any error.
    NEVER compare ``hash_pin(pin) == hashed`` — use this function exclusively
    (Pitfall G).
    """
    try:
        return bool(_ctx.verify(pin, hashed))
    except Exception:
        return False
```

**Conventions to copy verbatim:**
- Top-of-file "Security rules (non-negotiable)" bullet list in the module docstring.
- `_ctx` (or `_fernet()` in our case) as a module-level singleton — initialized once, reused everywhere.
- Pair shape: `<verb>_pat(plaintext) → bytes` + `decrypt_pat(ciphertext) → str`.

**What to do differently:**
- **Construct Fernet lazily inside `_fernet()` helper** rather than as a module-import-time singleton — `settings.GRUVAX_SECRET_KEY` validation must complete first, and the migration also imports `pat_crypto` (for the seed-row placeholder), so eager construction would order-dep on settings load. The RESEARCH §Pattern 5 excerpt has the right shape:
  ```python
  def _fernet() -> Fernet:
      return Fernet(settings.GRUVAX_SECRET_KEY.get_secret_value().encode())
  ```
  Note `.get_secret_value()` because `GRUVAX_SECRET_KEY: SecretStr` (per RESEARCH §Common operation 1).
- **`decrypt_pat` MUST NOT silently return on `InvalidToken`** — re-raise so the caller (sync_profile) can mark `last_sync_status='failed'` + `last_sync_error='pat_rejected'`. This differs from `verify_pin`'s "return False on any error" pattern because Fernet rotation orphaning a profile is an operator-actionable signal, not a wrong-PIN-try-again.

---

### 6. `src/gruvax/discogsography/log_redactor.py` (utility, structlog processor)

**Analog:** `src/gruvax/logging_config.py` (entire file — especially the `shared_processors` list lines 132-140).

**Existing processor chain to extend** (logging_config.py:132-140):
```python
shared_processors: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]
```

**New processor signature contract** (matches structlog's stdlib processor API):
```python
# src/gruvax/discogsography/log_redactor.py
def redact_dscg_tokens(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Mask any 'dscg_<base64url>' substring (with or without 'Bearer ') in event values.

    Inserted BEFORE structlog.processors.format_exc_info in the shared_processors chain
    (logging_config.py:139) so exception strings carrying the Authorization header
    are also redacted before being JSON-rendered.
    """
    # Full impl per RESEARCH §Pattern 6 (lines 519-530) — copy verbatim.
```

**Wiring point in `logging_config.py:configure_logging`:**

Insert into `shared_processors` (line 132-140) BEFORE `structlog.processors.format_exc_info` (line 139) so exception messages are also scrubbed:
```python
shared_processors: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.StackInfoRenderer(),
    redact_dscg_tokens,                       # ← NEW (P1)
    structlog.processors.format_exc_info,
]
```

**Conventions to copy verbatim:**
- Three-arg signature `(_logger, _method_name, event_dict) → event_dict` — standard structlog processor shape.
- Underscore-prefix unused args (project linter would otherwise flag).
- Recursive walk into nested dicts (RESEARCH §Pattern 6 shows the `elif isinstance(val, dict)` branch).

**What to do differently:**
- **Compile the regex at module scope** (`_DSCG_PATTERN = re.compile(...)`), not inside the function. RESEARCH §Pattern 6 does this correctly — preserve it.
- **Test with a fuzz corpus.** RESEARCH §Open Q4 calls for a Hypothesis property test asserting `dscg_*` is never in the rendered output. Place under `tests/unit/test_log_redactor.py`.

---

### 7. `src/gruvax/sync/profile_sync.py` (service, batch / staging-swap orchestration)

**Analog:** No staging-swap pattern exists in the repo — closest analog is `src/gruvax/db/queries.py:write_boundary` + `write_history_row` + `store_idempotency` (transaction-bundled writes, all called inside the same outer `async with conn.transaction()`).

**Primary template:** RESEARCH.md §Pattern 2 (lines 290-355) for the COPY-from-STDIN staging-ingest, §Pattern 3 (lines 358-395) for the advisory lock, §Pattern 7 (lines 534-552) for the inline cache refresh. Copy those skeletons.

**Conventions to copy from `db/queries.py`:**
- Module docstring lists every public function (queries.py:1-26).
- `%s` placeholders everywhere; never f-string interpolation (queries.py:91, 130, 949+ all preserve this).
- `async with conn.cursor() as cur` for parameterized queries; `await conn.execute(...)` for fire-and-forget (no fetch).
- Connection lifecycle: explicit `await conn.commit()` after the final write of a transaction (mirrors `set_pin.py:46`).

**What to do differently:**
- **Use a dedicated connection, not the pool** — per Pitfall 6 (RESEARCH.md line 626). Acquire via `await psycopg.AsyncConnection.connect(conninfo)` for the entire sync; the pool's request connection is freed immediately. The cache refresh at end-of-sync DOES need pool access briefly (snapshot.load takes a pool, not a connection — see `collection_snapshot.py:56-67`).
- **Wrap the swap in `async with conn.transaction()`** — per Pitfall 3 (RESEARCH.md line 607). The staging-load loop runs OUTSIDE the transaction (the TEMP table is `ON COMMIT DROP`, but the COPY itself doesn't need an outer TX); the DELETE/INSERT/UPDATE atomic swap runs INSIDE one.
- **session-scoped `pg_try_advisory_lock`, not `_xact_lock`** — RESEARCH §Pattern 3 + Anti-Patterns lines 556-557. Held across BOTH the staging-load and swap TXes; released in `finally`.
- **Defensive Pitfall 1 guard:** if `pg_try_advisory_lock` returns FALSE AND `profiles.last_sync_status = 'in_progress'` AND `last_sync_at < now() - INTERVAL '5 minutes'`, surface a clear error message rather than 409-ing forever.
- **Cache refresh inline at end (D-14):** call `snapshot.invalidate()`, `await snapshot.load(pool)`, `await boundary_cache.load(pool)`, `segment_cache.derive(boundary_cache, snapshot, boundary_cache.overrides)` — uses the same call sequence as `app.py:142-172`. The app_state object is passed in by the caller (HTTP handler in `api/admin/profile_sync.py`).

**Data flow:**
```
POST /api/admin/profiles/{id}/sync handler
  → sync_profile(profile_id, app_state)
    → acquire dedicated psycopg.AsyncConnection
    → pg_try_advisory_lock(hash(profile_id)) — abort if held
    → UPDATE profiles SET last_sync_status='in_progress'
    → CREATE TEMP TABLE profile_collection_staging ON COMMIT DROP
    → async for release in client.iter_collection():
        → COPY ... FROM STDIN write_row
    → BEGIN TX
      DELETE FROM profile_collection WHERE profile_id=:id
      INSERT INTO profile_collection SELECT ... FROM staging
      UPDATE profiles SET last_sync_at=NOW(), ..., app_token_revoked=FALSE
      COMMIT
    → pg_advisory_unlock (always in finally)
    → snapshot.invalidate() + load(pool) + segment_cache.derive(...)
    → return {"status":"ok", "item_count": N, "took_ms": T}
```

---

### 8. `migrations/versions/0009_v2_profiles_and_collection_cache.py` (migration, DDL)

**Analog:** `migrations/versions/0002_v_collection_view.py` (for DROP VIEW + GRANT comments + the downgrade-recreates pattern) and `migrations/versions/0008_record_stats.py` (for CREATE TABLE + INDEX shape).

**File header convention** (0008_record_stats.py:1-26):
```python
"""Create gruvax.record_stats — durable search/selection counters (D-04/D-05/D-06).

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-24

Phase 8: Adds the record_stats table for OBS-07 (most-searched diagnostics).
Counters are release_id-keyed aggregates; no query text is ever stored (OBS-07).

Conventions (carried from 0001-0007):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() fully reverses upgrade().
- alembic_version in public; search_path via connect listener (env.py).
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None
```

**DDL-as-module-string + upgrade/downgrade pair** (0008_record_stats.py:28-54):
```python
_CREATE_TABLE = """
CREATE TABLE gruvax.record_stats (
    release_id          BIGINT        PRIMARY KEY,
    ...
)
"""

_CREATE_IDX = "CREATE INDEX ix_record_stats_search_count ON gruvax.record_stats (search_count DESC)"

_DROP_IDX = "DROP INDEX IF EXISTS gruvax.ix_record_stats_search_count"
_DROP_TABLE = "DROP TABLE IF EXISTS gruvax.record_stats"


def upgrade() -> None:
    op.execute(_CREATE_TABLE)
    op.execute(_CREATE_IDX)


def downgrade() -> None:
    op.execute(_DROP_IDX)
    op.execute(_DROP_TABLE)
```

**GRANT-as-prose comment for operator** (0002_v_collection_view.py:16-23):
```python
"""...
GRANT NOTE (for operator, never run by application code):
    GRANT USAGE ON SCHEMA discogsography TO gruvax;
    GRANT SELECT ON discogsography.releases,
                    discogsography.artists,
                    discogsography.collection_items TO gruvax;
    -- No INSERT / UPDATE / DELETE granted.
    -- See `just provision-db` for the full provisioning script.
"""
```

For 0009, the inverse comment goes in the docstring (REVOKE on upgrade, GRANT on downgrade):
```python
"""...
GRANT NOTE (for operator, after upgrading to this revision):
    REVOKE SELECT ON discogsography.releases,
                     discogsography.artists,
                     discogsography.collection_items FROM gruvax;
    REVOKE USAGE ON SCHEMA discogsography FROM gruvax;
    -- See `just provision-db-revoke-discogsography-grant` for the cleanup recipe.
"""
```

**Conventions to copy verbatim:**
- Module-level `_VERB_NOUN = """..."""` strings, then `op.execute(_VERB_NOUN)` in `upgrade()`/`downgrade()` — never inline triple-quoted strings inside functions.
- Revision IDs are 4-digit zero-padded strings (`"0009"`, `"0008"`).
- Named indexes (`ix_<table>_<columns>`, `uq_<table>_<columns>`) — never anonymous.
- `IF NOT EXISTS` / `IF EXISTS` everywhere for idempotency (0001's `CREATE SCHEMA IF NOT EXISTS gruvax`).
- Downgrade drops indexes BEFORE the table.

**What to do differently:**
- **Full primary template lives in RESEARCH §Common operation 2** (lines 681-829). Copy that body verbatim — it already follows all the conventions above.
- **Downgrade must `SET LOCAL search_path = gruvax, gruvax_dev, public` before CREATE VIEW** (Pitfall 5, RESEARCH lines 619-623). The pool's simplified search_path won't include `gruvax_dev` post-upgrade; the downgrade body explicitly widens it.
- **Seed the default profile** in upgrade (D-02) with a sentinel `'\x'::bytea` placeholder and `app_token_revoked = TRUE` — the CLI rewrites both on first `gruvax-set-pat`. Per RESEARCH lines 770-777.
- **`CREATE EXTENSION IF NOT EXISTS pgcrypto`** at top of upgrade — needed for `gen_random_uuid()` default on `profiles.id`. RESEARCH line 761.
- **Loop over `_V1_TABLES`** to ADD COLUMN + UPDATE backfill (D-11). RESEARCH lines 785-788.

---

### 9. `tests/fixtures/fake_discogsography.py` (test-fixture, in-memory FastAPI)

**Analog:** `src/gruvax/app.py::create_app` for the FastAPI factory shape + `tests/integration/test_search_benchmark.py:31-43` for the ASGITransport client construction.

**Factory pattern** — copy from RESEARCH.md §Pattern 4 (lines 404-453). The skeleton is the canonical form; project conventions are baked in.

**Test-side wiring** (test_search_benchmark.py:31-43):
```python
@pytest_asyncio.fixture(scope="module")
async def search_client(db_pool):  # type: ignore[no-untyped-def]
    """Module-scoped ASGI client with full lifespan for benchmark tests."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac
```

For the **fake-discogsography fixture itself**, NO `LifespanManager` is needed (no DB pool, no startup tasks) — just `AsyncClient(transport=ASGITransport(app=fake_app))`.

**Conventions to copy verbatim:**
- Three-line `async with (...):` block formatting — preserve the comma-separated context managers inside parentheses.
- `# type: ignore[no-untyped-def]` on pytest fixture defs (project convention; conftest.py:32 + test_search_benchmark.py:32 both use it).
- `scope="module"` for fixtures that should persist across multiple tests in one file.

**What to do differently:**
- **No DB dependency** — the fake is purely in-memory. Skip the `db_pool` fixture parameter.
- **Magic-token error injection** — RESEARCH §Pattern 4 lines 439-442 show the `Bearer dscg_force_429` / `Bearer dscg_force_500` triggers. Keep these as the test-only error contract.
- **Token routing by prefix** — fail with 401 if the Authorization header doesn't start with `Bearer dscg_`. RESEARCH §Pattern 4 lines 436-437.
- **Pagination math:** `has_more = offset + len(page) < len(seed)` (line 450) — verify this against the discogsography contract envelope shape (`{user_id, releases, total, offset, limit, has_more}`).

---

### 10. `tests/fixtures/synth_profile_collection.sql` (test-fixture, SQL seed)

**Analog:** `fixtures/synth_collection.sql` (existing — entire file is the template to rewrite).

**Existing file shape** (synth_collection.sql:1-50):
```sql
-- Synthetic dev collection seed (committed; PII-free).
--
-- Creates gruvax_dev schema with minimal discogsography-shaped tables and
-- inserts ~200 synthetic records covering all catalog-number format shapes
-- documented in INTERPOLATION.md §2.3.
--
-- Shape variety required (per plan acceptance criteria):
--   - alpha-prefix + digits: BLP 4001..4020, ECM 1001..1015
--   - multi-prefix within one label: "Blue Note" has BLP + BST prefixes
--   - mixed separators within one label: KC 32731 and KC-32732
--   - pure numeric: 32731..32740
--   - multi-value catalog (comma): BLP-100, BST-200
--   - placeholder: none
--   - ~50 singleton labels
[...]
CREATE SCHEMA IF NOT EXISTS gruvax_dev;
CREATE TABLE IF NOT EXISTS gruvax_dev.releases (...);
CREATE TABLE IF NOT EXISTS gruvax_dev.collection_items (...);
TRUNCATE gruvax_dev.collection_items RESTART IDENTITY CASCADE;
INSERT INTO gruvax_dev.artists (name) VALUES ('Miles Davis'), ...;
```

**Conventions to copy verbatim:**
- Top header comment describing the shape-variety contract (catalog-number formats) — preserve this exact list; the search tests depend on it.
- `IF NOT EXISTS` / `IF EXISTS` guards.
- `TRUNCATE ... RESTART IDENTITY CASCADE` before INSERT for idempotent re-seed.
- INSERT row layout with column-aligned comments (`('Miles Davis'),  -- 1`).

**What to do differently:**
- **Target `gruvax.profile_collection` directly, not the discogsography-shaped staging tables.** Schema is `gruvax`, not `gruvax_dev`. Foreign-key column `profile_id` is the default UUID `'00000000-0000-0000-0000-000000000001'::uuid` (D-02).
- **No `releases` / `collection_items` / `artists` tables** — profile_collection is denormalized (artist/title/label/catalog_number all in one row).
- **No `fts_vector` INSERT** — the column is `GENERATED ALWAYS AS (...) STORED` per the 0009 migration (RESEARCH lines 739-743).
- **Schema preamble** must INSERT a `gruvax.profiles` default row first (or use `ON CONFLICT DO NOTHING` against the migration-seeded one) — `INSERT INTO gruvax.profiles (id, display_name, app_token_encrypted, app_token_revoked) VALUES ('00000000-...0001', 'Default', '\x'::bytea, TRUE) ON CONFLICT (id) DO NOTHING`.
- **Per the dev-DB-schema-is-gruvax_dev MEMORY:** the dev Postgres has `search_path` via 0009 simplified to `gruvax, public`. The SQL fixture should be runnable via `psql ... -f tests/fixtures/synth_profile_collection.sql` against the migrated dev DB — no schema-branch logic needed.

---

### 11. `services/fake-discogsography/Dockerfile` + compose entry (infra)

**Analog:** `compose.yaml` `mosquitto:` block (sibling sidecar service pattern) + root `Dockerfile` (multi-stage uv build).

**Compose entry — copy `mosquitto:` block shape from `compose.yaml`** (the mosquitto block has the right size and conventions). New entry should be:
- `image:` with a local-built tag (`gruvax/fake-discogsography:dev`) and `build: { context: ./services/fake-discogsography }`.
- `networks: - internal` (so `api:` can reach it via Compose DNS as `fake-discogsography`).
- `healthcheck:` polling `GET /api/user/collection?limit=1` with a valid `Authorization: Bearer dscg_dev_seed` token.
- `depends_on:` block on `api:` should add `fake-discogsography: condition: service_healthy`.
- `environment:` `DISCOGSOGRAPHY_BASE_URL` on the `api:` service should be `http://fake-discogsography:8004`.

**Init-sync sidecar (D-16)** — separate compose service `init-sync` (one-shot) that runs:
```yaml
init-sync:
  image: gruvax/api:latest  # reuses the main image
  depends_on:
    api: { condition: service_healthy }
    fake-discogsography: { condition: service_healthy }
  command: ["uv", "run", "gruvax-sync", "--profile", "default"]
  environment:
    GRUVAX_BASE_URL: "http://api:8000"
  restart: "no"
  networks: [internal]
```

**Conventions to copy verbatim:**
- `${VAR:-default}` env substitution everywhere.
- Multi-line `healthcheck` arrays with `test: ["CMD", ...]`.
- `depends_on` blocks use the `{ condition: service_healthy }` long form, never the short list form.
- Project comment style: section headers in DEPLOYMENT comments at top of file.

**What to do differently:**
- **The fake-discogsography Dockerfile should be MINIMAL** — single stage, `python:3.13-slim` base, `uv pip install fastapi uvicorn`, COPY `tests/fixtures/fake_discogsography.py` + `tests/fixtures/synth_profile_collection_seed.yaml`, `CMD ["uvicorn", "fake_discogsography:create_fake_app", "--factory", "--host", "0.0.0.0", "--port", "8004"]`. Don't reuse the main Dockerfile — it's overkill.

---

### 12. `src/gruvax/api/health.py` (modified — rename + state widening)

**Self-analog:** Current 67-line file is its own template. Preserve everything except the field/state derivation.

**Current shape** (health.py:34-66):
```python
@router.get("/health")
async def get_health(request: Request) -> JSONResponse:
    """Return subsystem health status.
    [...]
    """
    db_ok: bool = getattr(request.app.state, "db_ok", False)
    view_ok: bool = getattr(request.app.state, "discogsography_view_ok", False)
    mqtt_ok: bool = getattr(request.app.state, "mqtt_ok", False)
    started_at: datetime = getattr(request.app.state, "started_at", datetime.now(UTC))

    db_status = "ok" if db_ok else "error"
    view_status = "ok" if view_ok else "failed"
    [...]
    body: dict[str, Any] = {
        "status": overall,
        "db": db_status,
        "discogsography_view_check": view_status,
        [...]
    }
    return JSONResponse(content=body, status_code=200)
```

**What to do differently:**
- **Replace `discogsography_view_ok: bool` reads with `discogsography_api_check: str` derived from `request.app.state.profile_sync_state`** — a dict populated by the background task (or directly read from `profiles.last_sync_at` via a cached value):
  ```python
  # Derivation per D-13 (UI-SPEC line 95-105):
  last_sync_at = getattr(request.app.state, "default_profile_last_sync_at", None)  # datetime | None
  last_sync_status = getattr(request.app.state, "default_profile_last_sync_status", None)  # 'ok' | 'failed' | 'in_progress' | None
  token_revoked = getattr(request.app.state, "default_profile_app_token_revoked", True)
  now = datetime.now(UTC)

  if last_sync_status == 'ok' and not token_revoked:
      api_check = 'ok'
  elif last_sync_status == 'failed' or token_revoked:
      api_check = 'failed'
  elif last_sync_at is None or (now - last_sync_at) > timedelta(hours=24):
      api_check = 'stale'
  else:
      api_check = 'ok'
  ```
- **Rename `view_check` → `api_check`** in the response body.
- **Overall status:** `degraded` if `db_ok=False` OR `api_check != 'ok'`.
- **No live HTTP probe** — preserve the docstring rule (lines 35-43). The background task in `app.py` refreshes `app.state.default_profile_*` every 60s.

---

## Shared Patterns

### Authentication (admin endpoint)
**Source:** `src/gruvax/api/deps.py:require_admin` (lines 137-224).
**Apply to:** `src/gruvax/api/admin/profile_sync.py`.
**Standard excerpt (short-lived handlers — e.g., editing.py heartbeat):**
```python
# Already-existing dependency — just import and use.
from gruvax.api.deps import get_pool, require_admin

@router.post("/editing")
async def signal_editing(
    body: EditingPayload,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),
) -> JSONResponse:
    ...
```
The dependency enforces: signed-cookie session + CSRF double-submit + sliding TTL + hard cap. Same protection as every other admin write. No new auth path to test.

**EXCEPTION FOR LONG-RUNNING OPERATIONS (added 2026-05-27 per Plan 03 Pitfall 6):**
Handlers that call `await sync_profile(...)` or any similar tens-of-seconds operation MUST NOT use `Depends(get_pool)` injection. `Depends(get_pool)` keeps the pool slot attached for the request lifetime, defeating Plan 03's dedicated-connection design and causing concurrent admin requests to block on pool slots.

Correct pattern for long-running handlers (used by `profile_sync.py`):
```python
@router.post("/profiles/{profile_id}/sync")
async def trigger_sync(
    profile_id: str,
    request: Request,                                       # capture request to reach app.state
    _admin: dict[str, Any] = Depends(require_admin),        # auth still injected
    # NO pool: Any = Depends(get_pool) — see note above
) -> JSONResponse:
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        # short-lived pre-flight check (e.g., 404 lookup) — pool slot held only briefly
        await cur.execute("SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL", (str(uid),))
        if await cur.fetchone() is None:
            raise HTTPException(404, detail={"type":"profile_not_found"})
    # async with block CLOSED here — pool slot RETURNED to the pool BEFORE awaiting sync_profile
    result = await sync_profile(str(uid), request.app.state)
    return JSONResponse(content=result)
```
Plan 04 Task 1's grep gate (`grep "Depends(get_pool)" src/gruvax/api/admin/profile_sync.py` returns 0) and the observable concurrent-checkout test (Plan 03 Task 2 Test 7 + Plan 04 Task 1 Test 10) enforce this invariant.

### Error handling (typed exceptions → HTTP responses)
**Source:** `src/gruvax/api/admin/login.py:68-74` (HTTPException with structured detail).
**Apply to:** `src/gruvax/api/admin/profile_sync.py`.
**Excerpt:**
```python
raise HTTPException(
    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
    detail={
        "type": "rate_limited",
        "message": "Too many login attempts. Try again later.",
    },
)
```
For profile_sync endpoint, catch `SyncInProgress` → 409 + `{"type":"already_in_progress"}`; `PATRejected` → 401 + `{"type":"pat_rejected"}`; `RateLimitExhausted` → 503 + `{"type":"rate_limited_upstream"}`; `ServerError`/`NetworkError` → 502 + `{"type":"upstream_unavailable"}`.

### SQL parameterization (T-01-07 / T-08-06)
**Source:** Every function in `src/gruvax/db/queries.py`.
**Apply to:** All new queries in `sync/profile_sync.py`, 0009 migration body, set_pat.py UPDATE, profile_collection rewires in queries.py.
**Excerpt:**
```python
# CORRECT (queries.py:121, 308-311, 392-393):
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(sql, (q, q, limit))   # %s placeholders; tuple of values

# WRONG (never):
sql = f"SELECT ... WHERE label = '{user_input}'"   # T-01-07 violation
```
The migration's UPDATE backfill is the only place where a literal UUID is interpolated into a string — that's safe because it's the constant `DEFAULT_PROFILE_UUID`, not user input (RESEARCH lines 786-788 demonstrate the convention with `f"... '{DEFAULT_PROFILE_UUID}'::uuid"`).

### Cache invalidation seam (D-14)
**Source:** `src/gruvax/estimator/collection_snapshot.py:109-121` + `src/gruvax/app.py:142-172` (the lifespan-startup load sequence to mirror).
**Apply to:** `src/gruvax/sync/profile_sync.py` (end of `sync_profile`).
**Excerpt — lifespan-startup load sequence (app.py):**
```python
# Order: boundary_cache.load → snapshot.load → segment_cache.derive(both)
cache = BoundaryCache()
await cache.load(pool)
app.state.boundary_cache = cache

snapshot = CollectionSnapshot()
await snapshot.load(pool)
app.state.collection_snapshot = snapshot

segment_cache = SegmentCache()
segment_cache.derive(cache, snapshot, cache.overrides)
app.state.segment_cache = segment_cache
```
End-of-sync refresh must replay this exact sequence (per RESEARCH §Pattern 7). The order matters: `segment_cache.derive` reads both `boundary_cache` and `snapshot`, so it goes last.

### Lifespan-startup probe + try/except + proceed
**Source:** `src/gruvax/app.py:127-139` (v_collection probe).
**Apply to:** `src/gruvax/app.py` step 2 modification (probe `profile_collection` instead) + new `DiscogsographyClient` reachability check.
**Excerpt:**
```python
try:
    async with pool.connection() as conn:
        await conn.execute("SELECT 1 FROM gruvax.v_collection LIMIT 1")
    app.state.discogsography_view_ok = True
    logger.info("v_collection probe: OK")
except Exception as exc:
    app.state.discogsography_view_ok = False
    logger.error(
        "v_collection probe FAILED — search will return 503 until resolved. "
        "Upstream schema change? Details: %s",
        exc,
    )
```
The "never crash on startup, log + flip flag + continue" pattern carries over. For P1, the probe becomes a `SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = %s::uuid` against the default UUID.

### Background-task lifecycle (CR-01 strong reference)
**Source:** `src/gruvax/app.py:204-238` (sync_age background task with `background_tasks` set).
**Apply to:** Any new background task in app.py lifespan (especially the per-60s refresh of `app.state.default_profile_last_sync_at`).
**Excerpt:**
```python
async def _refresh_default_profile_state() -> None:
    while True:
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT last_sync_at, last_sync_status, app_token_revoked "
                    "FROM gruvax.profiles WHERE id = %s::uuid",
                    (DEFAULT_PROFILE_UUID,),
                )
                row = await cur.fetchone()
            if row:
                app.state.default_profile_last_sync_at = row[0]
                app.state.default_profile_last_sync_status = row[1]
                app.state.default_profile_app_token_revoked = bool(row[2])
        except Exception as exc:
            logger.warning("default profile state refresh failed: %s", exc)
        await asyncio.sleep(60)

_task = asyncio.create_task(_refresh_default_profile_state())
app.state.background_tasks.add(_task)
_task.add_done_callback(app.state.background_tasks.discard)
_task.add_done_callback(_log_task_exc)  # log unexpected exits
```

### Pool checkout idiom
**Source:** Every async DB function in the codebase.
**Apply to:** Every new query.
**Excerpt:**
```python
# Read with fetch:
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(sql, params)
    row = await cur.fetchone()

# Write without fetch:
async with pool.connection() as conn:
    await conn.execute(sql, params)
    await conn.commit()  # explicit; autocommit is OFF
```

### Pydantic model_config for HTTP bodies
**Source:** `src/gruvax/api/admin/editing.py:39` (`model_config = {"extra": "forbid"}`).
**Apply to:** Any new request-body Pydantic model in `api/admin/profile_sync.py` (e.g., if a `{"force": bool}` body is added).
**Excerpt:**
```python
class CubeId(BaseModel):
    """A single cube address. Typed so the heartbeat can't smuggle arbitrary keys."""
    model_config = {"extra": "forbid"}
    unit: int
    row: int
    col: int
```

---

## No Analog Found

None. Every new file in P1 maps to a strong intra-repo analog. The closest "weak" matches are:

| File | Why it's "weak" but still has an analog |
|------|------------------------------------------|
| `src/gruvax/discogsography/client.py` | No existing httpx client in repo, but RESEARCH §Pattern 1 is a project-conventions-aware template; `src/gruvax/mqtt/client.py` shows the lifespan-owned external-client shape. |
| `src/gruvax/sync/profile_sync.py` | No existing staging-swap, but `db/queries.py` write functions + RESEARCH §§Patterns 2, 3, 7 cover every primitive used. |
| `services/fake-discogsography/Dockerfile` | No existing sibling-service Dockerfile, but the root `Dockerfile` (multi-stage uv) + `compose.yaml` `mosquitto:` block cover both ends. |

---

## Metadata

**Analog search scope:**
- `src/gruvax/**/*.py` (66 modules across 12 subpackages)
- `migrations/versions/*.py` (8 prior migrations)
- `tests/**/*.py` (54 test modules; conftest.py read in full)
- `compose.yaml`, `pyproject.toml`, `fixtures/`
- Cross-referenced with RESEARCH.md §§Patterns 1-7 and §Common Operations 1-4 (the planner's drop-in templates).

**Files read in full:** `cli/set_pin.py`, `settings.py`, `db/pool.py`, `db/queries.py` (full but excerpts only), `api/health.py`, `api/admin/login.py`, `api/admin/editing.py`, `api/admin/router.py`, `api/deps.py`, `auth/pin.py`, `app.py`, `logging_config.py`, `estimator/collection_snapshot.py`, `migrations/versions/0001_create_schema.py` (partial), `0002_v_collection_view.py`, `0008_record_stats.py`, `migrations/env.py` (partial), `tests/conftest.py` (partial), `tests/integration/test_search_benchmark.py`, `compose.yaml` (partial), `fixtures/synth_collection.sql` (partial), `api/admin/diagnostics.py` (partial).

**Pattern extraction date:** 2026-05-26.

**Closing note for the planner:** All RESEARCH.md §Pattern N and §Common Operation N excerpts are project-conventions-aware and ready to drop into the corresponding files. Treat them as the **canonical** templates for new code; the analog excerpts in this PATTERNS.md are the **anchoring** templates for any conventions the planner needs to double-check against the live codebase.

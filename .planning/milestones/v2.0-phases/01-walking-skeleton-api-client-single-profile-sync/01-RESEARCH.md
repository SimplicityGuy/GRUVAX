# Phase 1: Walking skeleton — API client + single-profile sync — Research

**Researched:** 2026-05-27
**Domain:** Backend integration (HTTP API client + per-profile cache + Fernet-encrypted secret + Alembic round-trip migration) replacing v1.0 cross-schema DB view as the discogsography contact surface.
**Confidence:** HIGH

## Summary

Phase 1 is a backend-heavy walking skeleton. It retires the v1.0 `gruvax.v_collection` cross-schema view (the only contact surface with discogsography per DEP-02), replaces it with a paged HTTP client + per-profile local cache table (`profile_collection`), and rebuilds positioning/search/locate off the cache for a single deterministic default profile. The migration must round-trip cleanly (`upgrade head → downgrade base → upgrade head`) — a v1.0 CI invariant.

Three new capabilities land: (1) a `DiscogsographyClient` httpx async wrapper with locked retry semantics (401/403 immediate, 429 with `Retry-After` + ≤3 backoff, 5xx ≤3 backoff, network 1-retry); (2) a `sync_profile()` staging-swap routine using a pg session-level advisory lock keyed on `profile_id`, a TEMP table for COPY streaming, and a single-transaction `DELETE; INSERT SELECT; UPDATE profiles` swap with inline cache invalidation; (3) two new CLIs (`gruvax-set-pat` stdin-only with inline `limit=1` test sync; `gruvax-sync` calling a new PIN-gated `POST /api/admin/profiles/{id}/sync`).

The contract is locked at the cross-repo artifact `/Users/Robert/Code/public/discogsography/docs/specs/v2-gruvax-integration.md` v1 (`limit/offset` paging max 200, top-level `user_id`, `releases[]`, `has_more`, no `instance_id`, `id` is string-→-BIGINT, 60/min + 600/hour rate limits, `dscg_` token prefix, 401 identical-shape across missing/wrong-prefix/unknown/revoked). 19 implementation decisions in CONTEXT.md (D-01..D-19) further pin the schema, sync state machine, CLI UX, and cleanup boundaries.

**Primary recommendation:** Use `stamina>=26.1.0` as the retry decorator (it's an opinionated wrapper around `tenacity` with first-class `Retry-After` support and clean async ergonomics), psycopg3 `cur.copy("COPY ... FROM STDIN") + write_row()` for staging ingestion, `pg_try_advisory_lock(bigint)` (session-scoped) keyed on `hashtext('profile:' || profile_id::text)::bigint`, `cryptography.fernet.Fernet` for PAT-at-rest, and a single Alembic 0009 migration that creates `profiles` + `profile_collection`, adds nullable `profile_id` to the 7 v1 tables, drops `v_collection`, and has a downgrade that re-creates the v_collection body verbatim from migration 0002. Reuse the existing `httpx.AsyncClient + ASGITransport + asgi-lifespan.LifespanManager` test pattern (already used in `tests/integration/test_search_benchmark.py`) for the fake-discogsography in-process FastAPI fixture.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Paged HTTP fetch of discogsography collection | API / Backend (`DiscogsographyClient`) | — | Auth + retry + rate-limit semantics are server-side concerns; client never runs in the browser tier. |
| PAT-at-rest encryption (Fernet) | API / Backend | Database (`profiles.app_token_encrypted BYTEA`) | Encryption key (`GRUVAX_SECRET_KEY`) lives in process env; DB stores ciphertext only. |
| Staging-swap of `profile_collection` (~3000 rows) | Database / Storage (single TX) | API / Backend (orchestration) | Atomic visibility requires DB transaction; psycopg `COPY ... FROM STDIN` is the data-plane primitive. |
| Per-profile sync serialization | Database / Storage (`pg_try_advisory_lock`) | API / Backend (lock probe) | PG advisory lock is the correct primitive — no Redis, no in-process mutex (process restart loses it). |
| In-process cache refresh (BoundaryCache, CollectionSnapshot, SegmentCache) | API / Backend (lifespan-shared code path) | — | Caches are process-local; D-14 explicitly reuses the v1.0 Phase 4 invalidate/load seam. |
| Search / locate against `profile_collection` | Database / Storage (FTS on `fts_vector`) | API / Backend (router) | Identical to v1.0 model; only the table source changes. |
| `/api/health.discogsography_api_check` derivation | API / Backend (read of `profiles.last_sync_at`) | — | D-13 explicitly disallows live HTTP probe per request; field is derived from cached state. |
| `gruvax-set-pat` / `gruvax-sync` CLI entry points | API / Backend (Python package console_scripts) | — | Same pattern as existing `gruvax-set-pin`; entry points in pyproject.toml. |
| Kiosk staleness banner | Frontend / Client (existing v1.0 component) | API / Backend (`sync_age_seconds` field) | UI is unchanged per UI-SPEC; only the field's server-side derivation source changes. |

## Standard Stack

> All package versions verified against PyPI on 2026-05-27. Discovery sources: Context7 fallback (ctx7 absent — used WebFetch on canonical project URLs + `python3 -m pip index versions` for registry confirmation). All packages passed `slopcheck scan` clean.

### Core (already in pyproject.toml — no install needed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `httpx` | 0.28.1 [VERIFIED: PyPI] | Async HTTP client for `DiscogsographyClient` | Already in dev deps for tests; promote to runtime dep. `AsyncClient` + `ASGITransport` is the de-facto FastAPI test pattern (already used in `test_search_benchmark.py`). [CITED: python-httpx.org/advanced/transports/] |
| `fastapi` | 0.136.1 [VERIFIED: PyPI, already pinned] | Routes for `POST /api/admin/profiles/{id}/sync` | Existing; reuses `Depends(require_admin)` from `src/gruvax/api/deps.py:137`. |
| `psycopg[binary,pool]` | 3.2 [VERIFIED: PyPI, already pinned] | Async COPY + advisory lock + queries | `cursor.copy("COPY ... FROM STDIN")` + `await copy.write_row(...)` is the idiomatic streaming pattern. [CITED: psycopg.org/articles/2020/11/15/psycopg3-copy/] |
| `pydantic-settings` | 2.14 [VERIFIED: PyPI, already pinned] | Validates `DISCOGSOGRAPHY_BASE_URL` + `GRUVAX_SECRET_KEY` at boot | Existing pattern (`DATABASE_URL`, `SESSION_SECRET` already use no-default → boot-fail). |
| `alembic` | 1.18.4 [VERIFIED: PyPI, already pinned] | Migration 0009 (round-trippable) | Existing 8 migrations show the project's `op.execute()` + named-constraint pattern. |
| `sqlalchemy[asyncio]` | 2.0.49 [VERIFIED: PyPI, already pinned] | Used by Alembic; not used for runtime queries (project uses raw `psycopg`) | Existing; no new ORM models needed for P1 (the project does raw SQL via `psycopg`). |
| `structlog` | 25.5.0 [VERIFIED: PyPI, already pinned] | PAT redaction processor | Existing chain at `src/gruvax/logging_config.py`; new processor slots in via `shared_processors` list. |
| `pytest-asyncio` | 1.3.0 [VERIFIED: PyPI, already pinned] | Async test runner | Existing. |
| `pytest-benchmark` | 5.2.3 [VERIFIED: PyPI, already pinned] | p95 SLO gate preservation | Existing; `tests/integration/test_search_benchmark.py` already exists and must keep passing. |
| `hypothesis` | 6.152.9 [VERIFIED: PyPI, already pinned] | Property tests for client retry semantics + envelope parsing | Existing. |

### Supporting (NEW — must be added to pyproject.toml)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `cryptography` | 48.0.0 [VERIFIED: PyPI, slopcheck OK] | `Fernet` for PAT-at-rest encryption | Required by D-01 (`app_token_encrypted BYTEA`). Standard library for Fernet; thread-safe per [CITED: cryptography.io/en/latest/fernet/]. |
| `stamina` | 26.1.0 [VERIFIED: PyPI, slopcheck OK] | Retry decorator for `DiscogsographyClient` | Opinionated wrapper over `tenacity` (same author as `attrs`, `structlog`); first-class `Retry-After` support via custom on-predicate returning `timedelta`. [CITED: stamina.hynek.me/en/latest/tutorial.html] |
| `pytest-httpx` | 0.36.2 [VERIFIED: PyPI, slopcheck OK] | Optional — for tests that mock httpx WITHOUT an ASGI fake | Use sparingly; the fake-discogsography FastAPI fixture is the primary test surface (D-15). pytest-httpx is for narrow per-test assertions like "client raised PATRejected on 401" without needing the full fake. |

> **Note on `tenacity` vs `stamina`:** Both verified clean on PyPI. Recommendation is `stamina` because: (1) the retry semantics in CONTEXT.md §specifics map 1:1 to stamina's documented patterns (per-exception backoff predicate that returns `timedelta(seconds=int(Retry-After))`), (2) stamina is from the `attrs`/`structlog` author and matches the project's existing structlog stack ergonomically, (3) the boilerplate is ~½ that of bare tenacity. If the planner prefers a pure-tenacity approach (no extra dep), the patterns map directly — tenacity provides `wait_exponential`, `wait_random_exponential`, `retry_if_exception_type`, and `before_sleep` hooks.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `stamina` | bare `tenacity` 9.1.4 | Tenacity is the engine stamina wraps; pick tenacity if avoiding wrapper dep matters more than ergonomics. Same retry capabilities, more lines of code. |
| `stamina` | hand-rolled `asyncio.sleep` loop | Saves a dep but reinvents jitter, exponential backoff curve, and `Retry-After` parsing — exactly the things stamina has tested. Not recommended. |
| `pytest-httpx` | `respx` 0.23.1 | Both clean on PyPI. pytest-httpx is more fixture-idiomatic; respx is more route-pattern-rich. Either works for narrow assertion tests; primary test surface is the FastAPI fake (D-15) which uses neither. |
| psycopg `COPY ... FROM STDIN` for staging | `executemany INSERT ON CONFLICT` | COPY is ~10x faster (3,300 rows/s vs 300/s) and handles ~3000 rows in <1s. INSERT-many is only justified if the rows need per-row server-side defaults that COPY can't supply — not the case here. |
| `pg_try_advisory_lock(bigint)` (session-scoped) | `pg_try_advisory_xact_lock(bigint)` (transaction-scoped) | xact_lock auto-releases at COMMIT, but the sync flow has TWO transactions (the staging-load TX and the swap TX) — session lock spans both naturally. Use session lock with explicit `pg_advisory_unlock` in a `try/finally`. |
| Fernet (symmetric) | RSA-OAEP / age (asymmetric) | Asymmetric needed only when encryptor ≠ decryptor (which doesn't apply here — same server encrypts and decrypts). Fernet is the right primitive. |

**Installation (additions only):**
```bash
uv add cryptography stamina pytest-httpx
```

The planner should also add the two new entry points to `pyproject.toml`:
```toml
[project.scripts]
gruvax = "gruvax:main"
gruvax-set-pin = "gruvax.cli.set_pin:main"
gruvax-set-pat = "gruvax.cli.set_pat:main"          # NEW
gruvax-sync    = "gruvax.cli.sync:main"             # NEW
```

## Package Legitimacy Audit

> Slopcheck (v0.6.1) was available and ran cleanly. All three new packages verified.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `cryptography` | PyPI 48.0.0 [VERIFIED] | 12 yrs (since 2014) | ~280M/month [CITED: pepy.tech] | github.com/pyca/cryptography | [OK] | Approved (PyCA project; canonical Fernet implementation) |
| `stamina` | PyPI 26.1.0 [VERIFIED] | 4 yrs (since 2022) | ~3M/month | github.com/hynek/stamina | [OK] | Approved (Hynek Schlawack — `attrs`, `structlog`, `argon2-cffi` author) |
| `pytest-httpx` | PyPI 0.36.2 [VERIFIED] | 5 yrs (since 2020) | ~10M/month | github.com/Colin-b/pytest_httpx | [OK] | Approved (active maintainer, lockstep with httpx releases) |
| `tenacity` (alternative, not adopted) | PyPI 9.1.4 [VERIFIED] | 10 yrs | ~80M/month | github.com/jd/tenacity | [OK] | Approved if planner prefers over stamina |
| `respx` (alternative, not adopted) | PyPI 0.23.1 [VERIFIED] | 5 yrs | ~5M/month | github.com/lundberg/respx | [OK] | Approved if planner prefers over pytest-httpx |

**Packages removed due to slopcheck [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```mermaid
sequenceDiagram
    actor Owner
    participant CLI as gruvax-sync<br/>(CLI)
    participant API as FastAPI app<br/>(in-process)
    participant Sync as sync_profile()
    participant PG as Postgres<br/>(gruvax schema)
    participant DGS as discogsography<br/>HTTP API

    Owner->>CLI: PIN from stdin + profile=default
    CLI->>API: POST /api/admin/profiles/{id}/sync<br/>Cookie: gruvax_session, X-CSRF-Token
    API->>API: require_admin (session+CSRF)
    API->>Sync: sync_profile("00000...001")
    Sync->>PG: SELECT pg_try_advisory_lock(hash(profile_id))
    alt lock not acquired
        Sync-->>API: 409 already_in_progress
    end
    Sync->>PG: UPDATE profiles SET last_sync_status='in_progress'
    Sync->>PG: CREATE TEMP TABLE profile_collection_staging (...) ON COMMIT DROP
    loop until has_more=false
        Sync->>DGS: GET /api/user/collection?limit=200&offset=N<br/>Authorization: Bearer dscg_*
        DGS-->>Sync: 200 {user_id, releases, has_more, ...}
        Note over Sync: stamina retry: 429→Retry-After,<br/>5xx→exp backoff, 401/403→raise PATRejected
        Sync->>PG: COPY profile_collection_staging FROM STDIN<br/>(stream write_row per release)
    end
    Sync->>PG: BEGIN; DELETE FROM profile_collection WHERE profile_id=...;<br/>INSERT INTO profile_collection SELECT ... FROM staging;<br/>UPDATE profiles SET last_sync_at=NOW(), ...; COMMIT
    Sync->>PG: SELECT pg_advisory_unlock(hash(profile_id))
    Sync->>API: in-process: snapshot.invalidate() + load(pool) +<br/>segment_cache.invalidate() + boundary_cache.reload()
    API-->>CLI: 200 {status:"ok", item_count: N, took_ms: T}
    CLI-->>Owner: progress lines + final status
```

### Recommended Project Structure

```
src/gruvax/
├── discogsography/                     # NEW
│   ├── __init__.py
│   ├── client.py                       # DiscogsographyClient (httpx + stamina)
│   ├── errors.py                       # PATRejected, RateLimitExhausted, etc.
│   └── log_redactor.py                 # structlog processor (masks dscg_* in event values)
├── sync/                               # NEW
│   ├── __init__.py
│   ├── profile_sync.py                 # sync_profile(profile_id) staging-swap routine
│   └── pat_crypto.py                   # encrypt_pat / decrypt_pat (Fernet)
├── api/
│   └── admin/
│       └── profiles.py                 # NEW — POST /api/admin/profiles/{id}/sync
├── cli/
│   ├── set_pin.py                      # existing
│   ├── set_pat.py                      # NEW — gruvax-set-pat
│   └── sync.py                         # NEW — gruvax-sync
├── settings.py                         # MODIFIED — add DISCOGSOGRAPHY_BASE_URL, GRUVAX_SECRET_KEY; drop OBSERVED_DISCOGSOGRAPHY_SCHEMA
├── db/
│   ├── pool.py                         # MODIFIED — _configure_connection sets search_path = "gruvax, public" (drop schema branch)
│   └── queries.py                      # MODIFIED — rewire to profile_collection WHERE profile_id=:default
├── estimator/
│   └── collection_snapshot.py          # MODIFIED — load() query targets profile_collection
├── app.py                              # MODIFIED — startup probe + sync_age background task
└── api/health.py                       # MODIFIED — field rename (D-13)

migrations/versions/
└── 0009_v2_profiles_and_collection_cache.py   # NEW — single atomic migration

tests/
├── fixtures/                           # NEW directory
│   ├── __init__.py
│   ├── fake_discogsography.py          # In-memory FastAPI app implementing 3 contract endpoints
│   ├── synth_profile_collection.sql    # Rewrite of fixtures/synth_collection.sql for new schema
│   └── synth_profile_collection_seed.yaml  # ~3000-row YAML for fake-discogsography service
├── unit/
│   ├── test_discogsography_client.py   # NEW — retry semantics, envelope parsing, PATRejected
│   ├── test_pat_crypto.py              # NEW — Fernet round-trip + InvalidToken
│   └── test_log_redactor.py            # NEW — assert dscg_* never appears in captured logs
└── integration/
    ├── test_profile_sync.py            # NEW — full staging-swap against fake + real PG
    ├── test_set_pat_cli.py             # NEW — stdin + test sync + user_id strict match
    └── test_sync_cli.py                # NEW — end-to-end via PIN-gated endpoint

docker/
└── fake-discogsography/                # NEW
    └── Dockerfile + entrypoint         # serves tests/fixtures/fake_discogsography.py app
```

### Pattern 1: `DiscogsographyClient` with stamina retry

**What:** Async httpx client that pages a discogsography collection endpoint and raises typed exceptions on terminal errors.
**When to use:** All HTTP calls to discogsography. Never instantiate `httpx.AsyncClient` directly elsewhere in P1.

```python
# Source: pattern verified against [CITED: stamina.hynek.me/en/latest/tutorial.html]
#         and [CITED: python-httpx.org/advanced/transports/]
from __future__ import annotations

import datetime as dt
from collections.abc import AsyncIterator

import httpx
import stamina

from gruvax.discogsography.errors import (
    PATRejected,
    RateLimitExhausted,
    ServerError,
    NetworkError,
)


def _should_retry(exc: BaseException) -> bool | dt.timedelta:
    """Stamina retry predicate matching CONTEXT.md §specifics retry semantics.

    Returns:
      False        — do NOT retry (raise the exception out of the retry loop)
      True         — retry with default exponential backoff
      timedelta    — retry after exactly this wait (used for 429 Retry-After)
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        # 401/403: PAT rejected — no retry. Caller will set app_token_revoked=TRUE.
        if code in (401, 403):
            return False
        # 429: honour Retry-After (seconds), THEN exponential backoff for subsequent attempts.
        if code == 429:
            retry_after_raw = exc.response.headers.get("Retry-After", "1")
            try:
                return dt.timedelta(seconds=max(1, int(float(retry_after_raw))))
            except (TypeError, ValueError):
                return dt.timedelta(seconds=1)
        # 5xx: exponential backoff.
        if 500 <= code < 600:
            return True
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout)):
        return True
    return False


class DiscogsographyClient:
    """Async client for discogsography v2 integration contract v1.

    One instance per process (FastAPI app lifespan). Long-lived AsyncClient
    is the documented httpx best practice; per-request instantiation would
    re-establish the TCP connection and defeat the keep-alive pool.
    """

    def __init__(self, base_url: str, pat: str, *, timeout: float = 10.0) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {pat}"},
            timeout=httpx.Timeout(timeout),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @stamina.retry(on=_should_retry, attempts=3)
    async def _get_page(self, *, limit: int, offset: int) -> dict[str, object]:
        resp = await self._client.get(
            "/api/user/collection",
            params={"limit": limit, "offset": offset},
        )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 403):
                # No retry — raise out as PATRejected (terminal).
                raise PATRejected("PAT rejected by discogsography") from e
            raise
        return resp.json()

    async def iter_collection(self, *, page_size: int = 200) -> AsyncIterator[dict]:
        """Paged iteration. Yields one release dict at a time."""
        offset = 0
        while True:
            page = await self._get_page(limit=page_size, offset=offset)
            for release in page["releases"]:
                yield release
            if not page.get("has_more"):
                break
            offset += page_size

    async def fetch_user_id(self) -> str:
        """Test-sync helper: GET /api/user/collection?limit=1, return user_id."""
        page = await self._get_page(limit=1, offset=0)
        return str(page["user_id"])
```

### Pattern 2: psycopg3 async COPY + staging-swap

**What:** Stream paged API responses into a `TEMP TABLE` via `COPY ... FROM STDIN`, then atomically swap the target table contents in a single transaction.
**When to use:** Inside `sync_profile(profile_id)`. Never use `INSERT ... VALUES` for the row-loading path.

```python
# Source: pattern verified against [CITED: psycopg.org/articles/2020/11/15/psycopg3-copy/]
#         and [CITED: jacopofarina.eu/posts/ingest-data-into-postgres-fast/]
# Confirmed: ~3,300 rows/s for plain COPY; matches our ~3,000-row payload budget.
async def _ingest_into_staging(conn, client, profile_id):
    """Stream all rows into profile_collection_staging via COPY.

    The staging table is TEMP + ON COMMIT DROP so it disappears when the
    swap transaction commits, regardless of how the function exits.
    """
    async with conn.cursor() as cur:
        await cur.execute("""
            CREATE TEMP TABLE profile_collection_staging (
                release_id     BIGINT NOT NULL,
                folder_id      INT,
                artist         TEXT,
                title          TEXT,
                label          TEXT,
                catalog_number TEXT,
                year           INT
            ) ON COMMIT DROP
        """)

    user_id: str | None = None
    async with conn.cursor() as cur, cur.copy(
        "COPY profile_collection_staging "
        "(release_id, folder_id, artist, title, label, catalog_number, year) "
        "FROM STDIN"
    ) as copy:
        # First, get user_id from the initial page so caller can use it later.
        first_page = await client._get_page(limit=200, offset=0)
        user_id = str(first_page["user_id"])
        for release in first_page["releases"]:
            await copy.write_row(_release_to_tuple(release))
        offset = 200
        has_more = first_page.get("has_more", False)
        while has_more:
            page = await client._get_page(limit=200, offset=offset)
            for release in page["releases"]:
                await copy.write_row(_release_to_tuple(release))
            offset += 200
            has_more = page.get("has_more", False)

    return user_id  # caller will UPDATE profiles.discogsography_user_id


def _release_to_tuple(rel: dict) -> tuple:
    """Map a discogsography v1 collection-item envelope row to the COPY tuple.

    Contract: `id` is a STRING (parse to BIGINT). No `instance_id`. `label` and
    `catalog_number` are nullable. See discogsography contract §4.4.
    """
    return (
        int(rel["id"]),                            # release_id — parse string → BIGINT (D-04)
        rel.get("folder_id"),                      # folder_id — nullable INT
        rel.get("artist"),
        rel.get("title"),
        rel.get("label"),
        rel.get("catalog_number"),
        rel.get("year"),
    )
```

### Pattern 3: pg_try_advisory_lock keyed on profile_id

**What:** Session-scoped PG advisory lock that prevents two concurrent syncs of the same profile.
**When to use:** As the first step of `sync_profile()`, before any state mutation.

```python
# Source: pattern verified against
#         [CITED: postgresql.org/docs/current/functions-admin.html §pg_try_advisory_lock]
import hashlib

def _profile_lock_key(profile_id: str) -> int:
    """Map profile_id (UUID string) → signed 64-bit integer for pg advisory lock.

    PG's advisory-lock key space is BIGINT (signed 64-bit). Take the first 8
    bytes of SHA-256(profile_id) and reinterpret as signed int64. Collision
    probability over the home-LAN profile count (<10) is effectively zero.
    """
    h = hashlib.sha256(f"gruvax:profile_sync:{profile_id}".encode()).digest()[:8]
    return int.from_bytes(h, byteorder="big", signed=True)


async def sync_profile(pool, profile_id: str):
    lock_key = _profile_lock_key(profile_id)
    async with pool.connection() as conn:
        # Session-scoped lock (D-12 / spec): held across the staging-load TX
        # and the swap TX. Released in finally, even if either TX rolls back.
        async with conn.cursor() as cur:
            await cur.execute("SELECT pg_try_advisory_lock(%s)", (lock_key,))
            row = await cur.fetchone()
            acquired = bool(row[0])
        if not acquired:
            raise SyncInProgress("Another sync for this profile is already running")
        try:
            await _do_sync(conn, profile_id)
        finally:
            async with conn.cursor() as cur:
                await cur.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))
```

> **Choice rationale:** Session-scoped `pg_try_advisory_lock` chosen over `pg_try_advisory_xact_lock` because the sync runs across two transactions (staging-load + atomic swap). xact_lock auto-releases on COMMIT, which would drop the lock between the two TXs and admit a concurrent sync. Session lock with explicit `pg_advisory_unlock` in a `finally` block is the textbook pattern for "multi-transaction critical section."

### Pattern 4: Fake-discogsography FastAPI fixture (D-15)

**What:** An in-process `FastAPI` app implementing the three contract endpoints, backed by an in-memory store. Used by httpx via `ASGITransport` (no network).
**When to use:** Every `DiscogsographyClient` test that doesn't strictly need pytest-httpx-style assertion granularity.

```python
# Source: pattern from existing tests/integration/test_search_benchmark.py
#         + [CITED: python-httpx.org/advanced/transports/]
# tests/fixtures/fake_discogsography.py
from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

class _Release(BaseModel):
    id: str
    title: str
    year: int | None = None
    catalog_number: str | None = None
    artist: str | None = None
    label: str | None = None
    genres: list[str] = []
    styles: list[str] = []
    rating: int = 0
    date_added: str | None = None
    folder_id: int | None = None


def create_fake_app(*, seed: list[dict], user_id: str = "99999999-9999-9999-9999-999999999999"):
    """Factory: each test gets a fresh app + in-memory seed."""
    app = FastAPI()

    @app.get("/api/user/collection")
    async def get_collection(
        authorization: str | None = Header(default=None),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ):
        # Token routing (mirrors discogsography contract §3.2)
        if not authorization or not authorization.startswith("Bearer dscg_"):
            raise HTTPException(401, detail="Missing/invalid token")
        # Magic tokens for forced error paths (test-only)
        if authorization == "Bearer dscg_force_429":
            raise HTTPException(429, headers={"Retry-After": "1"})
        if authorization == "Bearer dscg_force_500":
            raise HTTPException(500)
        page = seed[offset : offset + limit]
        return {
            "user_id": user_id,
            "releases": page,
            "total": len(seed),
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(page) < len(seed),
        }

    return app
```

```python
# Usage in tests/unit/test_discogsography_client.py
import pytest
from httpx import ASGITransport, AsyncClient
from gruvax.discogsography.client import DiscogsographyClient
from tests.fixtures.fake_discogsography import create_fake_app

@pytest.fixture
def fake_client():
    app = create_fake_app(seed=[{"id": str(i), "title": f"r{i}"} for i in range(250)])
    transport = ASGITransport(app=app)
    client = DiscogsographyClient(base_url="http://fake", pat="dscg_test")
    client._client = AsyncClient(
        transport=transport,
        base_url="http://fake",
        headers={"Authorization": "Bearer dscg_test"},
    )
    return client
```

### Pattern 5: Fernet PAT-at-rest

**What:** Encrypt the PAT with a process-level `GRUVAX_SECRET_KEY`; store the ciphertext as `BYTEA`; decrypt on read.
**When to use:** Every write to `profiles.app_token_encrypted` and every read where the plaintext is needed (i.e., before constructing a `DiscogsographyClient`).

```python
# Source: [CITED: cryptography.io/en/latest/fernet/]
from cryptography.fernet import Fernet, InvalidToken
from gruvax.settings import settings


def _fernet() -> Fernet:
    """Returns a Fernet instance from the validated GRUVAX_SECRET_KEY.

    Key format: URL-safe base64-encoded 32 random bytes. Generate once per
    deployment with: python -c "from cryptography.fernet import Fernet;
    print(Fernet.generate_key().decode())".
    """
    return Fernet(settings.GRUVAX_SECRET_KEY.encode())


def encrypt_pat(plaintext: str) -> bytes:
    """Encrypt a plaintext PAT. Returns BYTEA-friendly bytes."""
    return _fernet().encrypt(plaintext.encode())


def decrypt_pat(ciphertext: bytes) -> str:
    """Decrypt. Raises InvalidToken if ciphertext was encrypted with a different
    GRUVAX_SECRET_KEY (operator rotated the key without re-encrypting profiles)."""
    return _fernet().decrypt(ciphertext).decode()
```

### Pattern 6: structlog redaction processor for `dscg_*`

**What:** A structlog processor that walks the event dict and replaces any string value matching `Bearer dscg_*` (or bare `dscg_*`) with `[REDACTED]`. Inserted into the existing `shared_processors` chain.
**When to use:** Inserted ONCE in `configure_logging()`. Tested with a dedicated test that asserts the plaintext never appears in `caplog` even when the PAT is on a failing request.

```python
# Source: pattern from [CITED: structlog.org/en/stable/processors.html]
# src/gruvax/discogsography/log_redactor.py
import re
from typing import Any

_DSCG_PATTERN = re.compile(r"(?:Bearer\s+)?dscg_[A-Za-z0-9_-]+")


def redact_dscg_tokens(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Mask any 'dscg_…' substring (with or without 'Bearer ' prefix) in event values."""
    for key, val in list(event_dict.items()):
        if isinstance(val, str) and _DSCG_PATTERN.search(val):
            event_dict[key] = _DSCG_PATTERN.sub("[REDACTED]", val)
        elif isinstance(val, dict):
            event_dict[key] = redact_dscg_tokens(_logger, _method_name, dict(val))
    return event_dict
```

Insert into `logging_config.py:configure_logging()`'s `shared_processors`, **before** `structlog.processors.format_exc_info` (so exception strings carrying the header are also redacted).

### Pattern 7: Reusing the v1 cache-invalidation seam

**What:** `sync_profile()` ends by calling the same code paths the v1 lifespan uses to populate caches.
**When to use:** After the swap TX commits and the advisory lock is released (D-14).

```python
# In src/gruvax/sync/profile_sync.py, end of sync_profile():
async def _refresh_app_caches(app_state) -> None:
    """D-14: inline cache refresh. P2 replaces with SSE publish."""
    snapshot = app_state.collection_snapshot
    boundary_cache = app_state.boundary_cache
    segment_cache = app_state.segment_cache
    pool = app_state.db_pool

    snapshot.invalidate()
    await snapshot.load(pool)                          # query now hits profile_collection
    await boundary_cache.load(pool)                    # boundary cache is unaffected by sync but reload for parity with lifespan
    segment_cache.derive(boundary_cache, snapshot, boundary_cache.overrides)
```

### Anti-Patterns to Avoid

- **Don't instantiate a new `httpx.AsyncClient` per request.** httpx best practice: single long-lived client. P1 puts the client on `app.state` (constructed in lifespan after `profiles.app_token_encrypted` is decrypted).
- **Don't use `pg_try_advisory_xact_lock` for the sync.** Auto-releases on COMMIT; sync needs the lock across the staging-load TX and the swap TX. Use session-scoped + explicit unlock.
- **Don't read PAT plaintext into a long-lived variable that the logger might capture.** Decrypt inside the function that constructs the `DiscogsographyClient`, pass into the constructor, and let the local go out of scope.
- **Don't log `event_dict["request"]["headers"]["Authorization"]` without the redactor wired.** Even DEBUG logs must mask `dscg_*`.
- **Don't use `op.add_column` for the `profile_id` fanout** if there's a faster `op.execute("ALTER TABLE ... ADD COLUMN profile_id UUID NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE")` — actually `op.add_column` is fine and matches project convention. Stay consistent with existing migrations (see `0008_record_stats.py`).
- **Don't store the PAT in an env var.** Per D-07 it's stdin-only into `gruvax-set-pat`; no env-var fallback.
- **Don't call `gruvax-sync` from outside the API process** — the CLI is just an HTTP client. The actual sync runs in-process so `app.state` caches refresh inline (D-14).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP retry with backoff + Retry-After | A `while attempts < 3: await asyncio.sleep(2**i)` loop | `stamina.retry` with custom on-predicate | Stamina handles jitter, max-attempts, exception filtering, `Retry-After`-as-timedelta in one decorator. [CITED: stamina.hynek.me] |
| Encrypt PAT at rest | XOR / your own AES wrapper / a "simple" Fernet alternative | `cryptography.fernet.Fernet` | Fernet IS the well-tested PyCA AES-128-CBC + HMAC primitive. Hand-rolling means re-implementing the IV + MAC + base64 envelope. |
| Per-profile sync mutex | In-process `asyncio.Lock` | `pg_try_advisory_lock(bigint)` | In-process locks don't survive process restart and don't coordinate across container replicas. PG advisory locks do both. |
| Bulk row load (~3000 rows) | `executemany INSERT ... VALUES` | psycopg3 `cur.copy("COPY ... FROM STDIN") + write_row` | ~10× faster, stream-friendly, avoids 3000 round-trips. [CITED: jacopofarina.eu] |
| HTTP pagination | A hand-rolled `for page in itertools.count(): ...` | An `async def iter_collection() -> AsyncIterator[dict]` generator on `DiscogsographyClient` | Generator composes cleanly with `async for` inside the COPY loop; consumer doesn't need to know pagination details. |
| Test mocking of httpx | `monkeypatch.setattr(httpx, "AsyncClient", ...)` | `httpx.ASGITransport(app=fake_app)` + pytest-httpx for narrow assertions | ASGITransport is the documented httpx test pattern. Monkey-patching `AsyncClient` is brittle and breaks any code path that constructs its own client. [CITED: python-httpx.org/advanced/transports/] |
| FastAPI lifespan in tests | A bare `httpx.AsyncClient(app=...)` (old shim) | `asgi_lifespan.LifespanManager` wrapping `create_app()` | Lifespan startup/shutdown is REQUIRED for the cache fixtures to populate. Existing test `test_search_benchmark.py` shows the pattern. |
| Time-since-last-sync field | `now() - max(profile_collection.synced_at)` query per `/api/health` request | Background task refreshing a `app.state.sync_age_seconds` float every 60s, read from `profiles.last_sync_at` | D-13 explicitly forbids live DB probes on `/api/health`. Mirrors existing v1 OBS-06 pattern. |

**Key insight:** Every item in this table corresponds to a published, well-tested library that has solved the edge cases the project does NOT have time to re-discover. Stamina alone replaces ~80 lines of careful retry/backoff logic. Fernet replaces ~120 lines of careful crypto-primitive composition. `COPY ... FROM STDIN` replaces a 3,000-iteration loop with a single stream.

## Runtime State Inventory

> Phase 1 is a SCHEMA MIGRATION + STATE CUTOVER, not a pure rename — but the inventory still applies to "what existing state needs migration vs. what's pure schema."

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | (a) `gruvax.cube_boundaries`, `gruvax.segments`, `gruvax.change_log`, `gruvax.change_sets`, `gruvax.settings`, `gruvax.record_stats`, `gruvax.ambient_baseline` (7 v1 tables) — exist with v1 data; need nullable `profile_id` added + backfill to default UUID. (b) `gruvax.v_collection` view + its read-only grant — must be DROPPED in P1 migration and re-created in downgrade. (c) `gruvax_dev` (dev) and `discogsography` (prod) external schemas — GRUVAX no longer reads from them after P1; the grant on the prod side must be revoked separately via an operator runbook entry. | (a) Data migration: `ALTER TABLE ... ADD COLUMN profile_id UUID NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE; UPDATE ... SET profile_id = '00000000-0000-0000-0000-000000000001'`. (b) Schema migration: `DROP VIEW`. (c) Code edit + runbook: planner should add a `just provision-db-revoke-discogsography-grant` recipe and document the grant removal in the migration's docstring. The `GRANT NOTE` in `0002_v_collection_view.py:16-23` is the existing precedent. |
| Live service config | None applicable. No external services (n8n, Datadog, Tailscale, Cloudflare) hold "v_collection" or related strings. discogsography itself does not depend on GRUVAX's view — the dependency is unidirectional. | None. |
| OS-registered state | None applicable. No Windows Task Scheduler / pm2 / systemd / launchd registrations reference GRUVAX schema names. The single `systemd --user` unit on the Pi runs Chromium against `gruvax-api.local`; no GRUVAX-side change. | None. |
| Secrets/env vars | (a) `OBSERVED_DISCOGSOGRAPHY_SCHEMA` — env var consumed by `settings.py`, set in `compose.yaml:69` (`gruvax_dev` default) and prod via env override. Will be REMOVED from `settings.py` (D-12); compose.yaml line must be deleted; any `.env` files documenting it stop having effect. (b) NEW env vars: `DISCOGSOGRAPHY_BASE_URL` (boot-fail), `GRUVAX_SECRET_KEY` (boot-fail; Fernet key, 32 url-safe base64 bytes). Existing pattern at `settings.py:21` (DATABASE_URL) and `settings.py:45` (SESSION_SECRET) is the template. | Update `compose.yaml`: remove `OBSERVED_DISCOGSOGRAPHY_SCHEMA` env, add `DISCOGSOGRAPHY_BASE_URL` + `GRUVAX_SECRET_KEY`. Add `gruvax-set-pat`-friendly bootstrap line to README. Document `GRUVAX_SECRET_KEY` generation: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| Build artifacts / installed packages | (a) Two new console_scripts entry points (`gruvax-set-pat`, `gruvax-sync`) — won't exist until `uv sync` reinstalls the package after pyproject.toml updates. Standard `uv sync --frozen` will pick them up. (b) Docker image needs the new `cryptography`, `stamina`, optionally `pytest-httpx` (dev-only) — uv lockfile regeneration. (c) `_version.py` is generated; unaffected. | After pyproject.toml edits: `uv sync` regenerates entry points + lockfile. CI workflow `build.yml` rebuilds the image automatically. |

**Nothing found in category:** All five categories enumerated above; OS-registered state and live service config both verified empty by code review (no grep hits in the repo for the strings).

## Common Pitfalls

### Pitfall 1: Lock-not-released-on-exception leaves the profile permanently in `in_progress`
**What goes wrong:** The session-scoped advisory lock is held until `pg_advisory_unlock` OR session close. If the sync raises an exception between `UPDATE profiles SET last_sync_status='in_progress'` and the `try/finally` unlock, AND the connection is somehow returned to the pool without closing, the lock survives and every subsequent `gruvax-sync` returns 409.
**Why it happens:** `psycopg_pool` recycles connections; advisory locks persist on the same backend across recycles unless explicitly released.
**How to avoid:** (a) Always use `try/finally pg_advisory_unlock` around the sync body. (b) Defensively set `last_sync_status` back to `'failed'` in the same finally block when an exception fired before the swap. (c) Add an idempotency guard: if `pg_try_advisory_lock` returns FALSE AND `profiles.last_sync_status = 'in_progress'` AND `last_sync_at < now() - INTERVAL '5 minutes'`, surface a clear error message ("stale in-progress sync detected — run `gruvax-sync --force-clear-lock`").
**Warning signs:** First sync after a crash returns 409 immediately. `pg_locks` view shows a granted advisory lock with no active query.

### Pitfall 2: 401 response on `gruvax-set-pat` test-sync sets `app_token_revoked = TRUE` BEFORE the row is written
**What goes wrong:** CLI hits `GET /api/user/collection?limit=1`, gets 401, raises `PATRejected`. If the CLI then tries to write the PAT row with `app_token_revoked = FALSE`, we're claiming a known-bad PAT works. If we write with `revoked=TRUE`, we've silently broken a previously working PAT (in the rotation case).
**Why it happens:** The CLI MUST atomically: (1) decide whether to commit the new PAT, (2) decide whether to leave the existing row alone, based on the test-sync outcome. D-09 already handles the rotation case (user_id mismatch). The 401 case needs the same care.
**How to avoid:** D-08 already covers this: "On failure: exits non-zero, leaves the existing row untouched." Implement as a strict pre-write probe — call `client.fetch_user_id()` first; only on success does the CLI proceed to encrypt + write the new PAT. Never blanket-write `revoked=TRUE` from the CLI.
**Warning signs:** Test `test_set_pat_cli_401_leaves_row_unchanged` should fail if this regresses.

### Pitfall 3: `COPY ... FROM STDIN` inside a connection that was used for an earlier query without explicit COMMIT
**What goes wrong:** psycopg starts an implicit transaction on the first query of a connection. COPY inside that transaction is fine, but if the connection's `autocommit` mode is on (as in the pool's `_configure_connection` callback for SET search_path), the COPY can race with the staging-load + swap.
**Why it happens:** Project's `_configure_connection` toggles autocommit ON for the `SET search_path` call and back OFF after — this is correct. But a developer might leave a connection in autocommit unexpectedly.
**How to avoid:** Inside `sync_profile`, explicitly `async with conn.transaction()` around the swap. The staging-load loop can be outside `transaction()` since the temp table is `ON COMMIT DROP` — fall-through to the swap TX is desired. Add a test that asserts `conn.transaction_status` is `IDLE` before sync starts.
**Warning signs:** Intermittent test failures where staging table is empty at swap time, or psycopg raises "cannot run command inside a transaction block" on the CREATE TEMP TABLE.

### Pitfall 4: `Retry-After` header is a HTTP-date, not seconds
**What goes wrong:** HTTP spec allows `Retry-After: <seconds>` OR `Retry-After: <HTTP-date>`. discogsography's contract says "Retry-After: <seconds>" but a future upstream library bump could send a date and our `int(float(...))` parser crashes silently.
**Why it happens:** Defensive coding against contract violations.
**How to avoid:** Wrap the parse in `try/except ValueError`; on failure, default to 1 second and emit a `WARNING` log. The discogsography contract is fixed for v1 but defending against drift is cheap.
**Warning signs:** `ValueError: could not convert string to float: 'Wed, 21 Oct 2026 07:28:00 GMT'` in production logs.

### Pitfall 5: Alembic downgrade fails to re-create `v_collection` because the `gruvax_dev` schema is missing in CI
**What goes wrong:** v_collection's body references unqualified `collection_items`, `releases`, `artists`. Downgrade re-runs the `CREATE VIEW` from migration 0002. But by then, the search_path no longer includes `gruvax_dev` (D-12 simplifies it to `gruvax, public`). The CREATE VIEW fails with "relation does not exist."
**Why it happens:** The downgrade's runtime context has the NEW pool's search_path, not the OLD one.
**How to avoid:** In migration 0009's downgrade, set `search_path = gruvax, gruvax_dev, public` for the connection performing the CREATE VIEW. The existing `migrations/env.py` connect-event listener uses `settings.OBSERVED_DISCOGSOGRAPHY_SCHEMA` — keep that setting alive ONLY for downgrade compatibility, OR re-add it in env.py's listener IF the alembic context is in offline/downgrade mode. Simplest fix: have migration 0009's downgrade explicitly run `SET LOCAL search_path = gruvax, gruvax_dev, public` before the CREATE VIEW. Add a CI test that runs the full round-trip.
**Warning signs:** `just migrate-roundtrip` fails on the downgrade step with `relation "collection_items" does not exist`.

### Pitfall 6: Inline cache refresh inside an HTTP handler holds a pool connection for the entire sync (~tens of seconds)
**What goes wrong:** `POST /api/admin/profiles/{id}/sync` runs `sync_profile()` synchronously inside the request handler. Holds a pool slot for the whole sync. Pool exhaustion if a second admin request races with the sync.
**Why it happens:** D-10 + D-14 explicitly require the sync to run in-process and the cache refresh to happen inline before the HTTP response.
**How to avoid:** Use a dedicated long-lived connection (not from the pool's request slot) for the sync. Acquire a new connection via `await psycopg.AsyncConnection.connect(conninfo, ...)`, run the sync on that, then close it. The pool's request connection is freed immediately. The cache refresh at end-of-sync DOES need a pool connection but only briefly.
**Warning signs:** Concurrent requests during sync return 503 / pool-exhausted; new test `test_concurrent_admin_endpoint_during_sync` would catch this.

### Pitfall 7: `discogsography_user_id` partial-unique index can't be enforced if it's NOT NULL UNIQUE on a single-row table
**What goes wrong:** P1 inserts a single default profile with `discogsography_user_id = NULL` (no PAT yet). Partial-unique index `WHERE deleted_at IS NULL` is correct, but a buggy migration could add `UNIQUE(discogsography_user_id)` outright — that NULL never violates uniqueness in PG, so no problem; but if the migration adds `NOT NULL UNIQUE(discogsography_user_id)`, the seed insert fails.
**Why it happens:** Confusion between "PG NULL is unique" semantics and the partial-index requirement.
**How to avoid:** Use the EXACT D-01 spec: `CREATE UNIQUE INDEX ... ON gruvax.profiles (LOWER(display_name)) WHERE deleted_at IS NULL` and `... (discogsography_user_id) WHERE deleted_at IS NULL`. Never add `UNIQUE` as a column-level constraint. The migration test `test_migrate_0009_seed_default_profile` should assert both indexes exist + the default row is present.
**Warning signs:** Migration upgrade fails at the seed-INSERT step with a unique-violation error.

### Pitfall 8: `Fernet.encrypt(b"")` writing an empty placeholder still produces a valid token (~100 bytes)
**What goes wrong:** D-02 says seed the default profile with `app_token_encrypted = Fernet('') of an empty placeholder`. A test that decrypts the seed row should get `b""`. If subsequent code does `if pat: client = DiscogsographyClient(...)`, the empty string is falsy and the sync is skipped — which is correct. But a test that does `if pat is None` would never see None — it gets `""`.
**Why it happens:** Sentinel-choice ambiguity.
**How to avoid:** Always check `app_token_revoked = TRUE` first (which the seed sets) before attempting to decrypt or use. The `revoked` flag is the source of truth for "this PAT is unusable"; the encrypted blob is a secondary signal.
**Warning signs:** Test `test_default_profile_seed_revoked` should assert `app_token_revoked = TRUE` AND `decrypt(app_token_encrypted) == ""`.

## Code Examples

### Common operation 1: Settings additions (boot-fail-if-missing)

```python
# Source: pattern from existing src/gruvax/settings.py (SESSION_SECRET — line 45)
# src/gruvax/settings.py — ADDITIONS

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ... existing fields ...

    # ── discogsography integration (P1, D-18) ────────────────────────────────
    # No default — missing value crashes boot (mirrors DATABASE_URL convention).
    DISCOGSOGRAPHY_BASE_URL: str

    # ── Fernet encryption for PAT-at-rest (P1, D-01) ────────────────────────
    # URL-safe base64-encoded 32 random bytes. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    GRUVAX_SECRET_KEY: SecretStr  # SecretStr prevents accidental logging/repr

    @field_validator("GRUVAX_SECRET_KEY")
    @classmethod
    def _validate_fernet_key(cls, v: SecretStr) -> SecretStr:
        from cryptography.fernet import Fernet
        # Construct Fernet(v) — raises ValueError if key is malformed.
        # This means the boot crash will include the precise error message.
        Fernet(v.get_secret_value().encode())
        return v

    # ── OBSOLETE — REMOVE in P1 (D-12) ───────────────────────────────────────
    # OBSERVED_DISCOGSOGRAPHY_SCHEMA: str = "gruvax_dev"  ← deleted
```

### Common operation 2: Alembic migration 0009 (single round-trippable migration)

```python
# Source: pattern from existing migrations/versions/0008_record_stats.py
#         and 0002_v_collection_view.py
# migrations/versions/0009_v2_profiles_and_collection_cache.py
"""Create profiles + profile_collection; add profile_id to 7 v1 tables; drop v_collection.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-27
"""
from __future__ import annotations
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None

DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"

_CREATE_PROFILES = """
CREATE TABLE gruvax.profiles (
    id                          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name                TEXT         NOT NULL,
    discogs_username            TEXT,
    discogsography_user_id      UUID,
    app_token_encrypted         BYTEA        NOT NULL,
    app_token_revoked           BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_sync_at                TIMESTAMPTZ,
    last_sync_status            TEXT         CHECK (last_sync_status IN ('ok','failed','in_progress')),
    last_sync_error             TEXT         CHECK (last_sync_error  IN ('pat_rejected','network','rate_limited','server_error','cancelled') OR last_sync_error IS NULL),
    last_sync_item_count        BIGINT,
    deleted_at                  TIMESTAMPTZ
)
"""
_IDX_PROFILES_DISPLAY_NAME = """
CREATE UNIQUE INDEX uq_profiles_display_name_active
    ON gruvax.profiles (LOWER(display_name))
    WHERE deleted_at IS NULL
"""
_IDX_PROFILES_DGS_USER = """
CREATE UNIQUE INDEX uq_profiles_dgs_user_id_active
    ON gruvax.profiles (discogsography_user_id)
    WHERE deleted_at IS NULL AND discogsography_user_id IS NOT NULL
"""

_CREATE_PROFILE_COLLECTION = """
CREATE TABLE gruvax.profile_collection (
    profile_id      UUID         NOT NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE,
    release_id      BIGINT       NOT NULL,
    folder_id       INT,
    artist          TEXT,
    title           TEXT,
    label           TEXT,
    catalog_number  TEXT,
    year            INT,
    fts_vector      TSVECTOR     GENERATED ALWAYS AS (
                       setweight(to_tsvector('english', coalesce(catalog_number,'')), 'A')
                    || setweight(to_tsvector('english', coalesce(title,'')),          'B')
                    || setweight(to_tsvector('english', coalesce(artist,'') || ' ' || coalesce(label,'')), 'C')
                    ) STORED,
    synced_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (profile_id, release_id, folder_id)
)
"""
_IDX_PC_FTS    = "CREATE INDEX ix_profile_collection_fts ON gruvax.profile_collection USING GIN (fts_vector)"
_IDX_PC_LABEL  = "CREATE INDEX ix_profile_collection_label_catalog ON gruvax.profile_collection (profile_id, label, catalog_number)"
_IDX_PC_ARTIST = "CREATE INDEX ix_profile_collection_artist_trgm ON gruvax.profile_collection USING GIN (artist gin_trgm_ops)"
_IDX_PC_TITLE  = "CREATE INDEX ix_profile_collection_title_trgm  ON gruvax.profile_collection USING GIN (title  gin_trgm_ops)"

# 7 v1 tables — all get nullable profile_id (D-11; NOT NULL in P2).
_V1_TABLES = ["cube_boundaries", "segments", "change_log", "change_sets", "settings", "record_stats", "ambient_baseline"]

_DROP_V_COLLECTION = "DROP VIEW IF EXISTS gruvax.v_collection"


def upgrade() -> None:
    # Make Fernet's gen_random_uuid() available
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(_CREATE_PROFILES)
    op.execute(_IDX_PROFILES_DISPLAY_NAME)
    op.execute(_IDX_PROFILES_DGS_USER)

    # Seed default profile with empty Fernet-encrypted placeholder (D-02).
    # The placeholder is a literal empty-string ciphertext rendered by Python at migration
    # time. We can't call Fernet here without GRUVAX_SECRET_KEY at migration time, so insert
    # a sentinel bytes blob and let the CLI rewrite it on first set_pat. Since
    # app_token_revoked=TRUE, no code path uses it before the rewrite.
    op.execute(f"""
        INSERT INTO gruvax.profiles
            (id, display_name, app_token_encrypted, app_token_revoked, last_sync_status)
        VALUES
            ('{DEFAULT_PROFILE_UUID}'::uuid, 'Default', '\\x'::bytea, TRUE, NULL)
    """)

    op.execute(_CREATE_PROFILE_COLLECTION)
    op.execute(_IDX_PC_FTS)
    op.execute(_IDX_PC_LABEL)
    op.execute(_IDX_PC_ARTIST)
    op.execute(_IDX_PC_TITLE)

    # Add nullable profile_id to all 7 v1 tables + backfill (D-11).
    for tbl in _V1_TABLES:
        op.execute(f"ALTER TABLE gruvax.{tbl} ADD COLUMN profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE CASCADE")
        op.execute(f"UPDATE gruvax.{tbl} SET profile_id = '{DEFAULT_PROFILE_UUID}'::uuid WHERE profile_id IS NULL")

    # Retire v_collection (D-07 + D-12).
    op.execute(_DROP_V_COLLECTION)


def downgrade() -> None:
    # Re-create v_collection from migration 0002 verbatim. Requires search_path to include
    # the source schema; CI runs with OBSERVED_DISCOGSOGRAPHY_SCHEMA=gruvax_dev in env, so
    # set it explicitly here to defend against the simplified pool config.
    op.execute("SET LOCAL search_path = gruvax, gruvax_dev, public")
    op.execute("""
        CREATE VIEW gruvax.v_collection AS
        SELECT
            ci.id                 AS collection_item_id,
            ci.release_id,
            r.title,
            r.label,
            r.catalog_number,
            r.format,
            r.year,
            r.fts_vector,
            a.name                AS primary_artist,
            ci.updated_at         AS synced_at
        FROM collection_items  ci
        JOIN releases          r  ON r.id = ci.release_id
        LEFT JOIN artists      a  ON a.id = r.primary_artist_id
    """)

    # Drop nullable profile_id from 7 v1 tables.
    for tbl in reversed(_V1_TABLES):
        op.execute(f"ALTER TABLE gruvax.{tbl} DROP COLUMN IF EXISTS profile_id")

    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_title_trgm")
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_artist_trgm")
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_label_catalog")
    op.execute("DROP INDEX IF EXISTS gruvax.ix_profile_collection_fts")
    op.execute("DROP TABLE IF EXISTS gruvax.profile_collection")
    op.execute("DROP INDEX IF EXISTS gruvax.uq_profiles_dgs_user_id_active")
    op.execute("DROP INDEX IF EXISTS gruvax.uq_profiles_display_name_active")
    op.execute("DROP TABLE IF EXISTS gruvax.profiles")
```

### Common operation 3: gruvax-set-pat CLI scaffold

```python
# Source: pattern from existing src/gruvax/cli/set_pin.py
# src/gruvax/cli/set_pat.py
"""Owner-paste PAT into a profile + inline test sync (D-07, D-08, D-09).

Usage::

    echo "$PAT" | uv run gruvax-set-pat --profile default
    # OR interactively (PAT not echoed, paste at prompt):
    uv run gruvax-set-pat --profile default
"""
from __future__ import annotations
import argparse
import asyncio
import getpass
import sys
import uuid

from gruvax.db.pool import get_pool_context
from gruvax.discogsography.client import DiscogsographyClient
from gruvax.discogsography.errors import PATRejected
from gruvax.settings import settings
from gruvax.sync.pat_crypto import encrypt_pat


DEFAULT_PROFILE_UUID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _set_pat(profile_name: str, pat: str) -> None:
    if not pat.startswith("dscg_") or len(pat) < 50:
        sys.exit("PAT must start with 'dscg_' and be at least 50 chars total")
    # D-08: inline test sync — captures user_id, validates catalog_number on sample.
    client = DiscogsographyClient(base_url=settings.DISCOGSOGRAPHY_BASE_URL, pat=pat)
    try:
        page = await client._get_page(limit=1, offset=0)
    except PATRejected:
        sys.exit("PAT rejected by discogsography (401/403). Not stored.")
    finally:
        await client.aclose()

    new_user_id = str(page["user_id"])
    releases = page.get("releases", [])
    if not releases or "catalog_number" not in releases[0]:
        sys.exit("PAT works but discogsography sample release has no catalog_number — refusing.")

    async with get_pool_context() as pool, pool.connection() as conn:
        # D-09: strict rotation — if discogsography_user_id is already set, must match.
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT discogsography_user_id FROM gruvax.profiles WHERE display_name = %s AND deleted_at IS NULL",
                (profile_name,),
            )
            row = await cur.fetchone()
        if row is None:
            sys.exit(f"No profile named {profile_name!r}")
        existing_dgs_user_id = row[0]
        if existing_dgs_user_id is not None and str(existing_dgs_user_id) != new_user_id:
            sys.exit(
                f"PAT belongs to a different discogsography user (was {existing_dgs_user_id}, "
                f"got {new_user_id}). Soft-delete the profile first if you really intend to switch."
            )
        ciphertext = encrypt_pat(pat)
        await conn.execute(
            "UPDATE gruvax.profiles "
            "SET app_token_encrypted = %s, app_token_revoked = FALSE, "
            "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid) "
            "WHERE display_name = %s AND deleted_at IS NULL",
            (ciphertext, new_user_id, profile_name),
        )
        await conn.commit()
    print(f"PAT stored for profile {profile_name!r} (user_id={new_user_id}). "
          "Run `gruvax-sync --profile default` to perform the full sync.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set or rotate a profile's discogsography PAT")
    parser.add_argument("--profile", required=True, help="Profile display_name (e.g. 'default')")
    args = parser.parse_args()

    # D-07: stdin only — env-var fallback explicitly forbidden.
    if sys.stdin.isatty():
        pat = getpass.getpass("Paste PAT (input hidden): ").strip()
    else:
        pat = sys.stdin.read().strip()
    if not pat:
        sys.exit("No PAT provided on stdin")
    asyncio.run(_set_pat(args.profile, pat))


if __name__ == "__main__":
    main()
```

### Common operation 4: Reusing the existing ASGI/lifespan test pattern

```python
# Source: copied from existing tests/integration/test_search_benchmark.py:30-43
# tests/integration/test_profile_sync.py
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from gruvax.app import create_app


@pytest_asyncio.fixture(scope="module")
async def admin_client(db_pool):
    """Real GRUVAX app + lifespan, exposed via in-process httpx client."""
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac,
    ):
        yield ac
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `gruvax.v_collection` cross-schema view | Local `profile_collection` table populated via httpx | P1 (2026-05-27 onwards) | Decouples GRUVAX from discogsography's DB layout; enables multi-profile (P2) + cross-host deployment. |
| `OBSERVED_DISCOGSOGRAPHY_SCHEMA` env var + dual search_path | `search_path = gruvax, public` (single, simple) | P1 (D-12) | Removes the dev/prod schema branch entirely. |
| Synchronous direct-DB probe in `/api/health` | Cached `app.state.sync_age_seconds` from background task | v1 Phase 8 already (CARRIES OVER) | D-13 preserves the "no live probe" rule, replaces source from `v_collection.synced_at` to `profiles.last_sync_at`. |
| `paho-mqtt` (sync) | `aiomqtt 2.5+` (async) | v1 Phase 6 (NOT CHANGED IN P1) | Mentioned for completeness; P1 does not touch MQTT. |
| `synced_at = max(v_collection.synced_at)` | `synced_at = profiles.last_sync_at` (per-profile) | P1 (CON-staleness-redefinition) | Banner trigger is per-profile from P2 onwards; P1 has single profile so behaviour is identical. |
| FastAPI `TestClient` (sync) | `AsyncClient(transport=ASGITransport(app))` + `asgi-lifespan.LifespanManager` | v1 (already in use) | The async-first test stack matches the async server. P1 adds the fake-discogsography app on the same primitive. |

**Deprecated/outdated:**
- The `_configure_connection` callback's two-schema search_path branch — deleted in P1 per D-12. The bootstrap connection in `migrations/env.py` still sets the dual path during downgrade (intentionally, to let `v_collection` resolve).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `aiomqtt 2.5.1` is the latest stable as of P1 start; P1 does not exercise MQTT so this is informational only. | State of the Art | Low. P1 doesn't ship new MQTT code. |
| A2 | `cryptography.fernet.Fernet` is async-safe for `encrypt`/`decrypt` calls (no docs assertion but the PyCA spec implies it). | Pattern 5 (Fernet) | Low. Worst case: serialize via a single-threaded lock in `pat_crypto.py`. |
| A3 | discogsography's `Retry-After` header is always integer seconds (per contract §7), not HTTP-date. | Pitfall 4 | Low. Defensive parser falls back to 1s on parse failure. |
| A4 | The migration's `INSERT INTO gruvax.profiles ... VALUES ('\x'::bytea, ...)` (empty bytes) is acceptable for the seed because the FOLLOWING field `app_token_revoked = TRUE` blocks all code paths from using it. | Pitfall 8 | Low. Test asserts both invariants. |
| A5 | `pg_try_advisory_lock(bigint)` accepts a signed 64-bit integer derived from `int.from_bytes(sha256(...)[:8], "big", signed=True)`. PG's BIGINT range covers all int64 values. | Pattern 3 | Low. Pattern is textbook PG advisory lock. |
| A6 | The fake-discogsography sibling Compose service (D-16) and the test-time in-process fake (D-15) can share the same `create_fake_app(seed=...)` factory; the Compose one mounts the YAML seed file at container start. | Pattern 4 | Low. Saves duplicating the FastAPI handlers. |
| A7 | `cryptography>=46` is the right floor (current is 48.0.0). The Fernet API has been stable since `cryptography` 0.6 (2014), so any `>=44` would also work. Recommendation pins `>=46` for conservative defaults. | Standard Stack table | Low. Wider compatibility range. |
| A8 | The CLI `gruvax-sync` should prompt for the PIN via `getpass` once per invocation, then send it as the `X-Admin-PIN` header (or whatever v1's admin flow uses). Need to confirm the v1 admin flow header name — the existing `set_pin.py` CLI doesn't help here because it talks to the DB directly. Planner discretion (per CONTEXT.md). | Pattern 1 + Pattern 7 | Medium. Planner reads `src/gruvax/api/admin/` to confirm whether PIN gates by session cookie (post-login) or by direct header. **[OPEN QUESTION]** for the planner: does the CLI need to first POST to `/api/admin/login` to get a session cookie, then POST to `/api/admin/profiles/{id}/sync` with that cookie + CSRF, or is there a simpler PIN-header path? |
| A9 | `pyproject.toml` should pin `cryptography>=46`, `stamina>=26`, `pytest-httpx>=0.36` to lock in current API. Looser pins are fine for the home-LAN deploy story. | Installation block | Low. |

## Open Questions (RESOLVED)

> All four open questions are resolved in the planning artifacts. Decisions are inlined below with pointers to where each choice is implemented.

1. **PIN flow for `gruvax-sync` CLI** — **RESOLVED:** cookie-based session via the existing `/api/admin/login` endpoint. The CLI uses `httpx.AsyncClient` with a cookie jar; POST `/api/admin/login` with `{"pin": ...}` captures the session cookie + CSRF token, then POST `/api/admin/profiles/{id}/sync` with `X-CSRF-Token` header. Reuses the entire `require_admin` enforcement path (sliding TTL, hard cap, CSRF). No new auth path to test. **See Plan 04 Task 3.**

2. **`gruvax-sync` progress reporting format** — **RESOLVED:** plain text on stdout (operator-facing). Server-side logs remain JSON via structlog. The CLI is intended for compose-exec ergonomics; not log-aggregator-facing. **See Plan 04 Task 3.**

3. **Where does the `DiscogsographyClient` instance live across the sync?** — **RESOLVED:** construct-per-sync in Plan 03. The client is bound to a single profile's PAT, decrypted at sync start and discarded at sync end. P2 may revisit when multiple profiles + infrequent syncs change the calculus. **See Plan 03 Task 1.**

4. **Should the `dscg_*` log redactor also catch `Authorization: Bearer dscg_...` in raw exception messages?** — **RESOLVED:** yes — the broader regex `(?:Bearer\s+)?dscg_[A-Za-z0-9_-]+` is applied to every event_dict value (including nested dict values and exception strings rendered by `format_exc_info`). A Hypothesis property test asserts plaintext never survives on a 100+-example fuzz corpus; an additional test wraps a logger.exception call to assert the exception path is also masked. **See Plan 02 Task 1.**

## Environment Availability

> P1 has external service dependencies but the only NEW one is the discogsography API base URL. The fake-discogsography sibling Compose service satisfies the dev/test cases.

| Dependency | Required By | Available (dev) | Version | Fallback |
|------------|------------|-----------------|---------|----------|
| Postgres 18 | All DB ops | ✓ (gruvax-dev-pg compose service) | 18 | — |
| Mosquitto 2.1.2-alpine | MQTT (NOT used in P1) | ✓ | 2.1.2 | — |
| Python 3.14+ | Runtime | ✓ (system: 3.14.5) | 3.14 | — |
| `uv` | Dep mgmt | ✓ (assumed; project uses it) | latest | — |
| discogsography production API | Production runs only | ✗ in dev | — | dev uses `fake-discogsography` compose service (D-16) seeded with synthetic YAML |
| `cryptography` 48.0.0 | Fernet | needs `uv add` | 48.0.0 | — |
| `stamina` 26.1.0 | Retry decorator | needs `uv add` | 26.1.0 | hand-rolled retry loop (NOT recommended) |
| `pytest-httpx` 0.36.2 | Optional narrow tests | needs `uv add --dev` | 0.36.2 | rely entirely on fake-discogsography FastAPI fixture |
| `slopcheck` (CI optional) | Slopcheck for future deps | ✓ (already installed system-wide) | 0.6.1 | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `pytest-httpx` (the FastAPI fake covers most test cases; planner may skip adding pytest-httpx if scope is tight).

## Validation Architecture

> Phase 1's validation is mostly automated. The new sync path needs unit + integration coverage; the existing benchmark gate must remain green; a new Alembic round-trip test must be added (the v1 invariant carries over and gets a new migration to cover).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest 9.0.3` + `pytest-asyncio 1.3.0` (existing) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` (`asyncio_mode = "auto"`, `addopts = "-q --tb=short --benchmark-skip"`, `pythonpath = ["."]`) |
| Quick run command | `uv run pytest tests/unit/ tests/property/ -x -q` (no DB; `just test-unit`) |
| Full suite command | `uv run pytest tests/ -q --tb=short` (requires Postgres; `just test`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | `DiscogsographyClient` raises `PATRejected` on 401/403 (no retry) | unit | `pytest tests/unit/test_discogsography_client.py::test_401_raises_pat_rejected -x` | ❌ Wave 0 |
| API-01 | `DiscogsographyClient` retries 429 with `Retry-After` honored | unit | `pytest tests/unit/test_discogsography_client.py::test_429_retries_with_retry_after -x` | ❌ Wave 0 |
| API-01 | `DiscogsographyClient` retries 5xx ≤3 times, then raises `ServerError` | unit | `pytest tests/unit/test_discogsography_client.py::test_5xx_exhausts_retries -x` | ❌ Wave 0 |
| API-01 | `DiscogsographyClient.iter_collection` correctly pages until `has_more=false` | unit (against fake) | `pytest tests/unit/test_discogsography_client.py::test_iter_collection_pages_through -x` | ❌ Wave 0 |
| API-02 | `/api/search` p95 ≤ 200 ms against `profile_collection` | benchmark | `uv run pytest tests/integration/test_search_benchmark.py --benchmark-only` | ✅ existing (must keep passing after table rewire) |
| API-02 | `/api/locate` p95 ≤ 50 ms (existing v1 gate) | benchmark | (existing benchmark) | ✅ existing |
| API-02 | `search_collection` returns rows from `profile_collection` for the default profile | integration | `pytest tests/integration/test_search.py -x` | ✅ existing (must keep passing) |
| API-03 | Alembic `upgrade head → downgrade base → upgrade head` round-trip clean (with new 0009 migration) | integration | `just migrate-roundtrip` + `pytest tests/integration/test_migrate_0009.py -x` | ❌ Wave 0 |
| API-03 | `gruvax.v_collection` does NOT exist after `alembic upgrade head` | integration | `pytest tests/integration/test_migrate_0009.py::test_v_collection_dropped -x` | ❌ Wave 0 |
| SYN-02 | `now() - profiles.last_sync_at` drives `sync_age_seconds` | integration | `pytest tests/integration/test_health.py::test_sync_age_from_profiles_last_sync_at -x` | ❌ Wave 0 (extend existing `test_health.py`) |
| SYN-02 | `discogsography_api_check` returns `'stale'` when `last_sync_at IS NULL` | integration | `pytest tests/integration/test_health.py::test_api_check_stale_when_null -x` | ❌ Wave 0 |
| PROF-03 | Default profile UUID = `00000000-0000-0000-0000-000000000001` exists after migration | integration | `pytest tests/integration/test_migrate_0009.py::test_default_profile_seeded -x` | ❌ Wave 0 |
| PROF-03 | `cube_boundaries.profile_id` backfilled to default UUID for existing rows | integration | `pytest tests/integration/test_migrate_0009.py::test_v1_tables_backfilled -x` | ❌ Wave 0 |
| (D-15) | Fake-discogsography fixture returns the contract envelope shape | unit | `pytest tests/unit/test_fake_discogsography.py -x` | ❌ Wave 0 |
| (D-08) | `gruvax-set-pat` writes the profile row on test-sync success | integration | `pytest tests/integration/test_set_pat_cli.py::test_success_writes_row -x` | ❌ Wave 0 |
| (D-08) | `gruvax-set-pat` exits non-zero on 401 and leaves row unchanged | integration | `pytest tests/integration/test_set_pat_cli.py::test_401_leaves_row_unchanged -x` | ❌ Wave 0 |
| (D-09) | `gruvax-set-pat` rejects PAT belonging to different user_id | integration | `pytest tests/integration/test_set_pat_cli.py::test_user_id_mismatch_refuses -x` | ❌ Wave 0 |
| (D-10) | `POST /api/admin/profiles/{id}/sync` calls `sync_profile` and refreshes caches inline | integration | `pytest tests/integration/test_sync_endpoint.py -x` | ❌ Wave 0 |
| (D-14) | Cache refresh inline at end of sync (snapshot, segment, boundary) | integration | `pytest tests/integration/test_profile_sync.py::test_caches_refreshed_post_swap -x` | ❌ Wave 0 |
| (Pitfall 1) | Stale `in_progress` sync state can be cleared (advisory-lock recovery) | integration | `pytest tests/integration/test_profile_sync.py::test_stale_in_progress_recovery -x` | ❌ Wave 0 |
| (specifics) | Plaintext PAT NEVER appears in captured logs across all severities | unit | `pytest tests/unit/test_log_redactor.py -x` | ❌ Wave 0 |
| (D-04) | `profile_collection` PK is `(profile_id, release_id, folder_id)` | integration | `pytest tests/integration/test_migrate_0009.py::test_profile_collection_pk -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ tests/property/ -x -q` (fast; no DB)
- **Per wave merge:** `uv run pytest tests/ -q` (full suite incl. integration) + `just migrate-roundtrip`
- **Phase gate:** Full suite green + `--benchmark-only` benchmark gate green + `just migrate-roundtrip` clean before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/fixtures/__init__.py` — package marker for new fixtures dir
- [ ] `tests/fixtures/fake_discogsography.py` — FastAPI in-memory fake (Pattern 4)
- [ ] `tests/fixtures/synth_profile_collection.sql` — rewrite of existing `fixtures/synth_collection.sql` targeting `gruvax.profile_collection` for default profile UUID
- [ ] `tests/fixtures/synth_profile_collection_seed.yaml` — ~3000-row synthetic seed for the Compose `fake-discogsography` sibling
- [ ] `tests/unit/test_discogsography_client.py` — all client retry/pagination/error tests
- [ ] `tests/unit/test_pat_crypto.py` — Fernet round-trip + InvalidToken + boot validation
- [ ] `tests/unit/test_log_redactor.py` — dscg_* masking property test
- [ ] `tests/unit/test_fake_discogsography.py` — fixture self-test
- [ ] `tests/integration/test_migrate_0009.py` — full migration round-trip + default profile seed + 7-table backfill
- [ ] `tests/integration/test_profile_sync.py` — end-to-end staging-swap (fake → real PG) + cache refresh
- [ ] `tests/integration/test_set_pat_cli.py` — CLI behavior tests
- [ ] `tests/integration/test_sync_endpoint.py` — PIN-gated POST sync end-to-end
- [ ] Extend `tests/integration/test_health.py` with the new `discogsography_api_check` cases
- [ ] No framework install needed — pytest + pytest-asyncio + httpx + asgi-lifespan all already present.

## Security Domain

> `security_enforcement` is not explicitly disabled in `.planning/config.json`; included.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Bearer PAT against discogsography (handled by their `require_app_token` dep); admin PIN against GRUVAX (existing v1 `require_admin` reused for new endpoint) |
| V3 Session Management | yes | Existing Starlette `SessionMiddleware` + `gruvax.admin_sessions` table; new endpoint inherits |
| V4 Access Control | yes | Existing `require_admin` (session + CSRF double-submit) for new `POST /api/admin/profiles/{id}/sync` |
| V5 Input Validation | yes | Pydantic models on the new endpoint; CLI validates PAT prefix + length before sending |
| V6 Cryptography | yes | `cryptography.fernet.Fernet` for PAT-at-rest; **never hand-roll** |
| V7 Errors & Logging | yes | structlog redactor masks `dscg_*`; PATRejected error never includes the plaintext PAT in its message |
| V8 Data Protection | yes | PAT stored as Fernet ciphertext; `GRUVAX_SECRET_KEY` validated at boot (`SecretStr` + `field_validator`) |
| V9 Communications | partial | LAN-only deploy; TLS deferred (OOS-06). HTTP traffic between GRUVAX and discogsography goes through the LAN; PAT in `Authorization` header is plaintext-on-wire. Acceptable per project constraints. |
| V13 API & Web Service | yes | New endpoint follows v1 admin endpoint conventions; CSRF; OpenAPI shape derives from FastAPI |

### Known Threat Patterns for {stack}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PAT plaintext leaks via logs | Information Disclosure | structlog `redact_dscg_tokens` processor wired in `shared_processors`; test asserts |
| PAT plaintext leaks via process listing (`ps`, journald) | Information Disclosure | stdin-only CLI (D-07); no env var fallback; no `--pat` flag |
| PAT plaintext leaks via shell history | Information Disclosure | `getpass`-driven prompt when stdin is a TTY; pipe-based when not |
| PAT rotation across discogsography users | Tampering / Privilege Escalation | D-09 strict user_id match; refuses cross-user PAT |
| Concurrent sync race causing torn writes | Tampering | `pg_try_advisory_lock` keyed on profile_id |
| `GRUVAX_SECRET_KEY` rotation orphans existing profiles | Denial of Service | Out of scope for P1 (deferred to v4 utility); documented in CONTEXT.md §specifics. |
| 401 reflection oracle (different shapes for "missing" vs "revoked" PAT) | Information Disclosure | discogsography contract §6 guarantees identical 401 shape for all four cases; GRUVAX just surfaces the result |
| Rate-limit DoS via runaway sync triggering | Denial of Service | Single profile in P1; 60/min cap is 10× the budget. P2+ concern. |
| CSRF on `POST /api/admin/profiles/{id}/sync` | Tampering | `require_admin` enforces double-submit (existing v1 pattern) |
| SQL injection via profile name | Tampering | All queries use `%s` placeholders; T-01-07 invariant carries over |
| Migration partial-failure leaves DB in mixed state | Tampering | Alembic `transaction_per_migration=True` (existing `env.py` config); round-trip CI gate catches |
| Fernet ciphertext re-binding to different key | Tampering | `InvalidToken` raised on decrypt; profile sync fails fast with `last_sync_status='failed'` + `last_sync_error='pat_rejected'` (caller treats as PAT problem; operator regenerates) |

## Sources

### Primary (HIGH confidence)
- **discogsography v2 integration contract v1** — `/Users/Robert/Code/public/discogsography/docs/specs/v2-gruvax-integration.md` — endpoint shape, auth, rate limits, OpenAPI fragment, error semantics. Authoritative.
- **GRUVAX CONTEXT.md** — `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-CONTEXT.md` — 19 locked decisions D-01..D-19 + specifics.
- **GRUVAX UI-SPEC.md** — `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-UI-SPEC.md` — `/api/health` field rename, kiosk banner data-source swap.
- **Project intel pack** — `.planning/intel/decisions.md`, `constraints.md`, `context.md`, `requirements.md`, `SYNTHESIS.md`.
- **Existing GRUVAX source** — `src/gruvax/db/pool.py`, `src/gruvax/settings.py`, `src/gruvax/db/queries.py`, `src/gruvax/estimator/collection_snapshot.py`, `src/gruvax/app.py`, `src/gruvax/api/health.py`, `src/gruvax/cli/set_pin.py`, `src/gruvax/logging_config.py`, `src/gruvax/api/deps.py`, `migrations/versions/0001_create_schema.py` through `0008_record_stats.py`, `migrations/env.py`, `tests/integration/test_search_benchmark.py`, `tests/conftest.py`, `compose.yaml`, `pyproject.toml`.
- **PostgreSQL functions-admin docs** — https://www.postgresql.org/docs/current/functions-admin.html — `pg_try_advisory_lock`, `pg_advisory_unlock`, transaction vs session scope.
- **cryptography.io Fernet docs** — https://cryptography.io/en/latest/fernet/ — key format, encrypt/decrypt, thread-safety.
- **stamina tutorial** — https://stamina.hynek.me/en/latest/tutorial.html — retry decorator, exception predicate, Retry-After-as-timedelta pattern.
- **httpx Transports docs** — https://www.python-httpx.org/advanced/transports/ — ASGITransport pattern.
- **PyPI versions** — verified via `python3 -m pip index versions` 2026-05-27 for cryptography (48.0.0), stamina (26.1.0), pytest-httpx (0.36.2), httpx (0.28.1), tenacity (9.1.4), respx (0.23.1).
- **slopcheck verification** — all five candidate packages clean.

### Secondary (MEDIUM confidence)
- **psycopg3 COPY benchmark blog** — https://jacopofarina.eu/posts/ingest-data-into-postgres-fast/ — ~3,300 rows/s figure; matches Postgres official COPY docs (which we couldn't fetch due to 403).
- **FastAPI async tests discussion** — https://github.com/fastapi/fastapi/discussions/11785 — confirms ASGITransport + LifespanManager pattern.
- **stamina GitHub** — https://github.com/hynek/stamina — version 26.1.0, maintainer (Hynek Schlawack), MIT.
- **pytest-httpx README** — https://github.com/Colin-b/pytest_httpx — fixture pattern, latest 0.36.2.
- **Starlette middleware docs** — https://www.starlette.io/middleware/ — `SessionMiddleware` `max_age`.

### Tertiary (LOW confidence — none used in load-bearing assertions)
- General WebSearch results for "structlog custom processor redact bearer token" — used only as a generality; the actual processor we wrote is straightforward enough to not need a third-party citation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries verified on PyPI registry on 2026-05-27, slopcheck clean, project-author pedigree where it matters (stamina/cryptography).
- Architecture: HIGH — pattern is "wrap httpx in a class, page, COPY, swap, refresh caches" — verified against existing project patterns (`test_search_benchmark.py` is the template for ASGI tests; `0008_record_stats.py` is the template for migrations; `set_pin.py` is the template for CLIs).
- Pitfalls: MEDIUM — Pitfalls 1, 3, 4, 5, 8 are based on direct reasoning about the spec + existing project mechanics. Pitfall 6 (pool exhaustion during sync) is a derived risk that needs the planner to confirm whether `sync_profile` uses a dedicated connection or a pool slot.
- Validation: HIGH — leverages existing pytest + pytest-asyncio + asgi-lifespan + pytest-benchmark stack already proven by 10 v1 phases.

**Research date:** 2026-05-27
**Valid until:** 2026-06-27 (30 days; stable contract, no fast-moving dependencies).

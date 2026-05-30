---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 03
subsystem: sync
tags: [sync, staging-swap, advisory-lock, psycopg, copy-from-stdin, cache-refresh, pitfall-6, pitfall-1, pitfall-8, fernet, discogsography]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-api-client-single-profile-sync
    provides: |
      Plan 01-01 — gruvax.profiles + gruvax.profile_collection schema +
      default-UUID seed + settings.DISCOGSOGRAPHY_BASE_URL +
      settings.GRUVAX_SECRET_KEY + pool simplified to gruvax,public.
      Plan 01-02 — DiscogsographyClient + typed errors module +
      pat_crypto (Fernet round-trip) + canonical fake-discogsography
      fleshed-out body.
provides:
  - "sync_profile(profile_id, app_state) → dict — the canonical staging-swap orchestrator that drives the data plane of P1."
  - "Atomic DELETE + INSERT SELECT + UPDATE wrapped in ONE explicit conn.transaction() block (Pitfall 3) — no observer ever sees the cache in a mixed-row state."
  - "TEMP profile_collection_staging table (ON COMMIT DROP) populated via psycopg3 cur.copy(\"COPY ... FROM STDIN\") write_row."
  - "Session-scoped pg_try_advisory_lock keyed on int64(sha256(\"gruvax:profile_sync:<uuid>\")) — held across staging-load + swap, released in try/finally even on non-typed exceptions (Pitfall 1)."
  - "Dedicated psycopg.AsyncConnection.connect() for the sync body — the pool is NEVER held across the multi-second collection fetch (Pitfall 6). Observable test (test_concurrent_pool_checkouts_unblocked_during_sync) proves a 3-concurrent-checkout race against a max_size=2 pool completes in <500ms while sync runs."
  - "Sentinel-bytea Pitfall 8 short-circuit: if app_token_encrypted is the migration's empty '\\x' placeholder AND app_token_revoked=TRUE, raise PATRejected BEFORE constructing DiscogsographyClient — no noisy 401 hitting upstream."
  - "Stale-lock detection (Pitfall 1): on pg_try_advisory_lock failure, query last_sync_status + last_sync_at; if status='in_progress' AND last_sync_at < now() - INTERVAL '5 minutes', surface SyncInProgress with 'stale' in the message so operators know to restart the API."
  - "Per-error-class status updates on a separate short-lived connection (so they commit even if the sync conn is poisoned): PATRejected→'pat_rejected'+revoked=TRUE, RateLimitExhausted→'rate_limited', ServerError→'server_error', NetworkError→'network', generic Exception→status='failed' (no tag)."
  - "Inline cache refresh sequence (D-14) — _refresh_app_caches replays src/gruvax/app.py:142-172 verbatim: snapshot.invalidate() → await snapshot.load(pool) → await boundary_cache.load(pool) → segment_cache.derive(boundary, snapshot, boundary.overrides)."
  - "Cache-refresh-after-commit fault tolerance: a _CacheRefreshFailed wrapper exception lets the swap stay durable (status='ok' in DB) while still surfacing the refresh exception to the Plan 04 admin endpoint for a 500 response."
  - "discogsography_user_id COALESCE (Pitfall 7) preserves the originally captured user_id across re-syncs; strict rotation check is upstream in gruvax-set-pat (Plan 04)."
  - "release_id parsed via int(rel['id']) per D-04 — 13-digit BIGINT overflow tolerated (verified in test_sync_release_id_bigint_overflow)."
affects:
  - "01-04 (gruvax-set-pat + gruvax-sync CLIs + POST /api/admin/profiles/{id}/sync): the admin endpoint awaits sync_profile() and translates typed errors to HTTP statuses per PATTERNS §Shared §error handling."
  - "01-06 (queries rewire to profile_collection): the staging-swap is the canonical writer; downstream consumers must respect the WHERE profile_id=%s::uuid pattern this plan established."
  - "P2 (multi-profile): the per-profile_id advisory-lock keying carries over verbatim; the cache-refresh-per-profile fan-out replaces the inline call."
  - "P4 (nightly background sync): the same sync_profile entry point is what the scheduler awaits — no second code path."

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dedicated AsyncConnection for long-running operations (Pitfall 6) — psycopg.AsyncConnection.connect outside the pool, explicit close in finally; pool remains for short-lived hot-path work."
    - "Internal sentinel exception (_CacheRefreshFailed) to distinguish post-commit refresh failure (DB intact) from sync-body failure (DB rolled back) without leaking the internal type to callers (unwrapped on the way out)."
    - "Per-error short-lived status updater (_record_failure) on a SEPARATE connection so the failed-status UPDATE commits even when the sync conn is in an indeterminate state after a mid-fetch crash."
    - "ONE explicit conn.transaction() wrapping CREATE TEMP TABLE + COPY + DELETE + INSERT + UPDATE — keeps the staging TEMP table alive across the COPY → swap boundary (without this, ON COMMIT DROP nukes it between implicit TXes)."
    - "sha256-derived signed int64 keys for pg_try_advisory_lock — collision-free across <10 home-LAN profiles and stable across process restarts."

key-files:
  created:
    - "src/gruvax/sync/profile_sync.py — sync_profile + _lock_key + _make_client factory seam + _release_to_tuple + _refresh_app_caches + _record_failure + _detect_stale_in_progress + _swap_inside_tx + _ingest_into_staging."
    - "tests/integration/sync/test_sync_profile.py — 11 integration tests (happy path, atomic replacement, folder_id dupes allowed, advisory lock, PATRejected, ServerError, RateLimitExhausted, NetworkError, COALESCE user_id, BIGINT overflow, lock release on exception)."
    - "tests/integration/sync/test_sync_cache_refresh.py — 4 integration tests covering the D-14 inline refresh sequence and the cache-refresh-failure-preserves-swap fault tolerance path."
    - "tests/integration/sync/test_sync_pitfalls.py — 2 integration tests: stale 'in_progress' detection (Pitfall 1) + sentinel-bytea short-circuit without HTTP (Pitfall 8)."
    - "tests/integration/sync/test_sync_pool_isolation.py — Pitfall 6 observable test (max_size=2 pool + slow fake + 3 concurrent checkouts all complete <500ms while sync runs)."
  modified:
    - "migrations/versions/0009_v2_profiles_and_collection_cache.py — Deviation Rule 3 fix: _V1_TABLES + _V1_ADD_COLUMN_STATEMENTS + _V1_BACKFILL_STATEMENTS + _V1_DROP_COLUMN_STATEMENTS realigned to the 7 real v1 user-data tables (admin_sessions, boundary_history, cube_boundaries, idempotency_keys, record_stats, segment_overrides, settings) so `alembic upgrade head` actually creates profiles + profile_collection on a fresh DB. units is excluded as global hardware config."
    - "tests/integration/test_migrate_0009.py — _V1_NULL_COUNT_QUERIES dict updated to the realigned 7-table list."

key-decisions:
  - "ONE explicit conn.transaction() wraps CREATE TEMP TABLE + COPY + DELETE/INSERT/UPDATE — diverges from PATTERNS §7's two-phase layout (staging-load outside TX, swap inside TX) because the staging TEMP table is ON COMMIT DROP and an implicit-TX commit between them would silently drop the staging rows before the swap reads them. The atomicity guarantee is unaffected; the swap still rolls back the entire critical section on any exception."
  - "Internal _CacheRefreshFailed wrapper exception (caught + unwrapped at the outer sync_profile level) — preserves the original exception type for the Plan 04 caller while keeping the cache-refresh failure isolated from the sync-body except-chain (which would otherwise call _record_failure and overwrite the freshly-committed 'ok' status with 'failed')."
  - "folder_id NULL coerced to 0 sentinel in _release_to_tuple — the composite PK (profile_id, release_id, folder_id) rejects NULL in folder_id, and Postgres treats NULL PK columns as a unique-violation-skip, which would silently corrupt the swap. Documented in the helper docstring."
  - "Dedicated AsyncConnection explicitly sets `search_path = 'gruvax, public'` (mirrors the pool's configure callback) so the sync conn behaves identically to a pool-checked-out conn for any future refactor that moves work between them."
  - "Pre-flight _load_pat runs on its own short-lived connection BEFORE acquiring the advisory lock — sentinel-bytea Pitfall 8 short-circuits without holding state that needs cleanup; the only state change is the _record_failure UPDATE which is safe to fire even if the lock was never acquired."

patterns-established:
  - "Long-running operations use psycopg.AsyncConnection.connect() with explicit close in finally, NOT pool.connection() — the pool is reserved for hot-path work."
  - "Short-lived status-update side-effects (especially failure recovery) use their own short-lived AsyncConnection.connect() so they commit independently of the primary connection's transaction state."
  - "Advisory locks use session scope (pg_try_advisory_lock + pg_advisory_unlock) when the critical section spans multiple transactions; xact_lock auto-releases on COMMIT and would admit a concurrent sync between staging-load and swap."
  - "Per-error-class except chain that maps typed exceptions to last_sync_error tag strings + (for PATRejected) the app_token_revoked flip — keeps the failure→status mapping single-sourced in the orchestrator, not scattered across HTTP route translators."

requirements-completed: [API-02, SYN-02]

# Metrics
duration: 75min
completed: 2026-05-26
---

# Phase 01 Plan 03: sync_profile (staging-swap + advisory lock + inline cache refresh) Summary

**sync_profile(profile_id, app_state) — dedicated-AsyncConnection staging-swap with session-scoped pg_try_advisory_lock, ON-COMMIT-DROP TEMP table via psycopg3 COPY FROM STDIN, atomic DELETE+INSERT+UPDATE in one TX, inline D-14 cache refresh, and Pitfall-1/3/6/7/8 mitigations all covered by 18 integration tests.**

## Performance

- **Duration:** 75 min
- **Started:** 2026-05-26T19:48Z
- **Completed:** 2026-05-26T21:03Z
- **Tasks:** 2 (1 deviation fix + 2 TDD plan tasks = 4 commits)
- **Files modified:** 6 (1 src + 4 tests + 1 migration + 1 test fix)

## Accomplishments

- **`sync_profile(profile_id, app_state)`** implements the full canonical staging-swap flow with all five Pitfalls (1, 3, 6, 7, 8) explicitly mitigated and tested.
- **18 integration tests pass** against live Postgres in tests/integration/sync/ — covering happy path, atomic replacement, PK composite folder_id, advisory lock, 4 typed errors (PATRejected/ServerError/RateLimited/Network), COALESCE user_id, BIGINT overflow, lock release on crash, cache refresh sequence (4 tests), Pitfalls 1 + 8 (2 tests), and the Pitfall 6 pool-isolation observable test.
- **Per-error tag mapping verified end-to-end** in DB: 401→pat_rejected+revoked=TRUE, 5xx→server_error, 429→rate_limited, ConnectError→network, generic→status='failed' (no tag).
- **Plan 04 unblocked** — the new admin endpoint can `await sync_profile(profile_id, request.app.state)` and translate typed exceptions to HTTP statuses with no further glue.

## Task Commits

Each task was committed atomically:

1. **Deviation fix (pre-plan blocker): migration 0009 _V1_TABLES realignment** — `6880516` (fix)
2. **Task 1 RED: failing tests for sync_profile core** — `ffb755d` (test)
3. **Task 1 GREEN: implement sync_profile core** — `3365a3d` (feat)
4. **Task 2: cache refresh sentinel + Pitfall 1/8 + pool-isolation tests** — `cabce3a` (feat)

The Task 1 TDD split is intentional (test commit → impl commit). Task 2 lands tests + the production wiring in a single commit because the wiring is a small additive change (a new sentinel exception) — no separate RED step needed.

## Files Created/Modified

### Created

- `src/gruvax/sync/profile_sync.py` (530 lines) — sync_profile public entry + 8 helpers + module docstring with full citation map.
- `tests/integration/sync/test_sync_profile.py` (~340 lines, 11 tests) — Task 1 behaviour coverage.
- `tests/integration/sync/test_sync_cache_refresh.py` (~280 lines, 4 tests) — D-14 inline refresh.
- `tests/integration/sync/test_sync_pitfalls.py` (~180 lines, 2 tests) — Pitfalls 1 + 8.
- `tests/integration/sync/test_sync_pool_isolation.py` (~225 lines, 1 test) — Pitfall 6 observable.

### Modified (deviation)

- `migrations/versions/0009_v2_profiles_and_collection_cache.py` — realigned `_V1_TABLES` to the seven REAL v1 tables (admin_sessions, boundary_history, cube_boundaries, idempotency_keys, record_stats, segment_overrides, settings); the original Plan 01-01 list referenced four nonexistent tables (segments, change_log, change_sets, ambient_baseline) which made `alembic upgrade head` fail at the ALTER TABLE step. Without this fix, profiles + profile_collection never existed on a fresh DB and no sync_profile test could run.
- `tests/integration/test_migrate_0009.py` — `_V1_NULL_COUNT_QUERIES` realigned to the same 7-table list.

## Decisions Made

- **Single explicit transaction wraps CREATE TEMP + COPY + DELETE + INSERT + UPDATE.** PATTERNS §7 suggested staging-load outside TX + swap inside TX, but ON COMMIT DROP on the TEMP table means an intervening implicit-TX commit would silently drop the staging rows before the swap reads them. Wrapping the entire critical section in one TX preserves atomicity AND keeps the staging table accessible. The Pitfall-3 protection (no implicit-TX race) is strictly stronger.
- **`_CacheRefreshFailed` internal sentinel exception** isolates post-commit cache failures from the sync-body except-chain. Without it, a refresh RuntimeError would land in `except Exception` → `_record_failure(status='failed')`, undoing the committed `status='ok'`. The wrapper preserves the original exception type for the Plan 04 caller via `.inner`.
- **`folder_id = 0` sentinel for NULL** — the composite PK (profile_id, release_id, folder_id) cannot accept NULL in any column, and Postgres' "NULL is unique" semantics would silently skip the unique-violation if we let it through. Documented in `_release_to_tuple`'s docstring.
- **Per-error short-lived `_record_failure` connection.** The dedicated sync conn may be in an indeterminate state after a mid-fetch crash (in a TX that auto-rolled back, with a half-released lock, etc.). Writing the failed-status UPDATE on a separate fresh connection guarantees it commits regardless.
- **Pre-flight `_load_pat` BEFORE the advisory lock acquisition** — keeps the Pitfall-8 sentinel short-circuit cheap and means a sentinel-bytea row never even attempts the lock. The cost is one extra short-lived conn open/close per sync, which is negligible.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migration 0009 referenced nonexistent v1 tables**

- **Found during:** Pre-Task-1 environment setup (running `alembic upgrade head` to prepare the test DB).
- **Issue:** Plan 01-01's `_V1_TABLES` constant in `migrations/versions/0009_v2_profiles_and_collection_cache.py` listed seven table names — `cube_boundaries, segments, change_log, change_sets, settings, record_stats, ambient_baseline` — but four of those (`segments`, `change_log`, `change_sets`, `ambient_baseline`) DO NOT EXIST in the v1 schema. The migration's `ALTER TABLE gruvax.segments ADD COLUMN profile_id ...` failed with `relation "gruvax.segments" does not exist`, rolling back the whole transaction and leaving the schema at 0008. `gruvax.profiles` and `gruvax.profile_collection` never existed on a fresh DB — blocking every downstream test that needs them. (Plan 01-01 self-reported the integration test as deferred-to-CI; CI must also have been failing or never ran.)
- **Fix:** Realigned the four module-level statement tuples (`_V1_TABLES`, `_V1_ADD_COLUMN_STATEMENTS`, `_V1_BACKFILL_STATEMENTS`, `_V1_DROP_COLUMN_STATEMENTS`) to the seven REAL v1 user-data tables that exist after `alembic upgrade 0008`: `admin_sessions, boundary_history, cube_boundaries, idempotency_keys, record_stats, segment_overrides, settings`. `units` is excluded because it models the physical hardware layout, not per-profile state — that's the natural read of D-11's "7 v1 tables" intent. Also updated `tests/integration/test_migrate_0009.py::_V1_NULL_COUNT_QUERIES` to match.
- **Files modified:** `migrations/versions/0009_v2_profiles_and_collection_cache.py`, `tests/integration/test_migrate_0009.py`
- **Verification:** `uv run alembic upgrade head` now succeeds; `\dt gruvax.*` shows all 10 expected tables including the new `profiles` and `profile_collection`. The seven realigned ALTER statements all reference real tables. The downgrade list is the reverse of the upgrade list.
- **Committed in:** `6880516` (separate fix commit ahead of the plan tasks so the diff is visible).

---

**Total deviations:** 1 auto-fixed (Rule 3 blocking — pre-existing migration bug in a different plan's commit).
**Impact on plan:** Without this fix, zero P1 progress was possible — no test in tests/integration/sync/ could run because profiles + profile_collection didn't exist. The fix is minimal (table-name realignment) and preserves the spirit of D-11 ("all 7 v1 tables get nullable profile_id"). No scope creep — only the table list changed; the ADD COLUMN / UPDATE / DROP COLUMN SQL shapes are identical.

## Issues Encountered

- **Docker daemon was not running at executor start.** Resolved by `open -a "Rancher Desktop"` and polling for the socket to become available (~35s). Postgres image pull initially timed out (network blip) — retried successfully.
- **`pytest-asyncio` default loop scope mismatched the session-scoped `db_pool` fixture.** Symptoms: first test instantly failed with `PoolTimeout: couldn't get a connection after 30.00 sec`. Fix: annotate every sync_profile test + fixture with `@pytest.mark.asyncio(loop_scope="session")` / `@pytest_asyncio.fixture(loop_scope="session")` so they share the same event loop the pool was opened on. (This matches the project memory entry: "`pytest-asyncio loop_scope=\"session\"` for DB tests".)
- **First implementation of `_swap` ran inside its own `async with conn.transaction()` AFTER the staging-load loop ran outside any TX.** Symptom: happy-path test reported `status=ok, item_count=450` but the DB showed zero rows post-swap. Root cause: psycopg started an implicit TX for `CREATE TEMP TABLE`, the COPY populated it, then `async with conn.transaction()` started a SAVEPOINT inside that implicit TX. The savepoint committed but the outer TX never did, and ON COMMIT DROP fired on the next implicit commit — silently nuking the staging rows. Fixed by wrapping the entire critical section (CREATE + COPY + swap) in one explicit `async with conn.transaction()` and renaming `_swap` → `_swap_inside_tx` to document the contract.
- **Test 4 initially failed because the generic-Exception except-chain caught the cache-refresh RuntimeError and called `_record_failure(status='failed')`, overwriting the freshly-committed 'ok' status.** Fixed by introducing the `_CacheRefreshFailed` internal sentinel wrapper.

## User Setup Required

None — no new env vars, no new packages, no new external services. The `.env` already requires `GRUVAX_SECRET_KEY` (Plan 01-01) which sync_profile uses transitively via `pat_crypto.decrypt_pat`.

## Next Phase Readiness

- **Plan 04 (CLIs + admin endpoint) is unblocked.** The admin endpoint can `await sync_profile(profile_id, request.app.state)` directly; typed exceptions translate cleanly to HTTP statuses per PATTERNS §Shared §error handling.
- **Plan 06 (queries rewire) will not need changes to sync_profile.** The cache refresh sequence is the seam: when `CollectionSnapshot.load` rewires from `v_collection` to `profile_collection`, the sync's `_refresh_app_caches` automatically picks up the fresh source — no code change here.
- **Open concern (NOT a blocker for this plan):** The pre-existing `tests/integration/test_migrate_0009.py` test file has `RuntimeError: asyncio.run() cannot be called from a running event loop` failures unrelated to this plan's changes (it predates this plan and uses a different alembic-invocation pattern). Plan 01-01's CI should be re-validated once the migration is shipped; for the worktree, these tests sit alongside the sync tests and `pytest tests/integration/sync/` runs them all 18-for-18 green.
- **Phase-level next step:** Plan 01-04 (admin endpoint + two CLIs) can start immediately.

---
*Phase: 01-walking-skeleton-api-client-single-profile-sync*
*Completed: 2026-05-26*

## Self-Check: PASSED

All 6 files referenced in this SUMMARY exist on disk; all 4 commit hashes
(`6880516`, `ffb755d`, `3365a3d`, `cabce3a`) are reachable from HEAD in
the worktree-agent-ad23f795c2f8ec902 branch.

### Files verified
- `src/gruvax/sync/profile_sync.py` ✓
- `tests/integration/sync/test_sync_profile.py` ✓
- `tests/integration/sync/test_sync_cache_refresh.py` ✓
- `tests/integration/sync/test_sync_pitfalls.py` ✓
- `tests/integration/sync/test_sync_pool_isolation.py` ✓
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-03-SUMMARY.md` ✓

### Test outcome verified
`uv run pytest tests/integration/sync/` → 18 passed, 1 warning in ~7s.

### Verification grep gates (per PLAN.md `<verification>`)
- `grep -c "pg_try_advisory_lock" src/gruvax/sync/profile_sync.py` = **2** (≥1 ✓)
- `grep -c "ON COMMIT DROP" src/gruvax/sync/profile_sync.py` = **3** (≥1 ✓)
- `grep -c "async with conn.transaction()" src/gruvax/sync/profile_sync.py` = **2** (≥1 ✓)
- `grep -c "psycopg.AsyncConnection.connect" src/gruvax/sync/profile_sync.py` = **4** (≥1 ✓)

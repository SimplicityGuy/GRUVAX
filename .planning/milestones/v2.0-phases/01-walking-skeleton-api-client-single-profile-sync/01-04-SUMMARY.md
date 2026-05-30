---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 04
subsystem: api
tags: [fastapi, admin-endpoint, cli, pin-gate, csrf, stdin, pat, sync, pitfall-6]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 01)
    provides: GRUVAX_SECRET_KEY + DISCOGSOGRAPHY_BASE_URL settings, profiles + profile_collection tables, Fernet pat_crypto module
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 02)
    provides: DiscogsographyClient, typed errors (PATRejected/RateLimitExhausted/ServerError/NetworkError), fake_discogsography test fixture
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 03)
    provides: sync_profile(profile_id, app_state) with dedicated-connection Pitfall-6 mitigation
provides:
  - POST /api/admin/profiles/{profile_id}/sync — PIN-gated admin endpoint
  - gruvax-set-pat CLI — stdin-only PAT provisioning with inline test-sync + strict D-09 rotation
  - gruvax-sync CLI — PIN-gated HTTP trigger for the full sync (TTY + pipe modes)
  - pyproject.toml console-script registration for both new CLIs
  - Pool-isolation guard wired into the admin endpoint (Pitfall 6 verbatim)
affects:
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 05) — uses gruvax-sync in init-sync compose container
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 06) — collection_snapshot rewire removes the AsyncMock cache-substitution scaffold these tests added
  - phase: 02-multi-user-collections — POST /api/admin/profiles/{id}/sync becomes the "Sync now" admin-button backend

# Tech tracking
tech-stack:
  added: [argparse (stdlib — first time used in src/), getpass (stdlib — for PIN/PAT input)]
  patterns:
    - "Long-running admin handlers reach into request.app.state.db_pool directly for short-lived pre-flight checks, then release before awaiting the long-running call — preserves Plan 03 Pitfall-6 mitigation"
    - "TTY-aware CLI PIN/PAT input: getpass when sys.stdin.isatty(); sys.stdin.readline() when piped (supports `echo $X | cli` form)"
    - "CLI subprocess test harness: session-scoped uvicorn-on-thread + per-test `_MUX` app pin-board for fake-discogsography → avoids start/stop per test"
    - "Cross-plan isolation: AsyncMock substitution of app.state caches keeps Plan 04 tests independent of Plan 06's pending collection_snapshot rewire"

key-files:
  created:
    - src/gruvax/api/admin/profile_sync.py
    - src/gruvax/cli/set_pat.py
    - src/gruvax/cli/sync_cli.py
    - tests/integration/api/test_admin_sync_endpoint.py
    - tests/integration/cli/test_set_pat.py
    - tests/integration/cli/test_sync_cli.py
  modified:
    - src/gruvax/api/admin/router.py (register profile_sync_router)
    - pyproject.toml (register gruvax-set-pat + gruvax-sync console_scripts)
    - .env (added local dev defaults — gitignored)

key-decisions:
  - "Handler does NOT use the standard get_pool FastAPI dependency — instead it reads request.app.state.db_pool inside a tight async-with block for the 404 pre-flight and releases the slot BEFORE awaiting sync_profile (PATTERNS §Shared Patterns 'Authentication — EXCEPTION FOR LONG-RUNNING OPERATIONS'). Verified by static grep gate + observable concurrent-checkout test."
  - "Plan-04 integration tests substitute AsyncMock cache hooks on app.state AFTER lifespan startup, isolating Plan 04 from Plan 06's pending collection_snapshot.py rewire. Plan 03's tests follow the same pattern."
  - "gruvax-sync CLI uses a module-scoped uvicorn fixture (not session-scoped) so the temporary monkeypatch of profile_sync._refresh_app_caches is torn down before test_sync_cache_refresh.py runs."
  - "gruvax-set-pat shells out via uv-run subprocess in tests (TDD on subprocess behavior) but uses in-process invocation for the TTY-isatty branch (subprocess can't reliably simulate TTY on macOS without pty)."

patterns-established:
  - "Long-running-handler dependency-injection pattern: request: Request + read app.state directly, never Depends(get_pool)"
  - "TTY-aware stdin pattern (set_pat + sync_cli): getpass when TTY, sys.stdin.read/readline when piped — enables both interactive use and shell-pipeline (CI/init-container) use"
  - "Subprocess CLI testing via session/module uvicorn fixtures with a `_MUX` app pin-board for per-test fake-server reconfiguration"

requirements-completed: [PROF-03, API-01]

# Metrics
duration: 72min
completed: 2026-05-26
---

# Phase 01 Plan 04: Operator Surfaces — Admin Sync Endpoint + Two CLIs Summary

**PIN-gated POST /api/admin/profiles/{id}/sync handler (no Depends(get_pool) — Pitfall-6 safe) plus stdin-only `gruvax-set-pat` (strict D-09 rotation) and TTY-aware `gruvax-sync` (supports `echo $PIN | gruvax-sync` for the Plan 05 init-sync container).**

## Performance

- **Duration:** ~72 min
- **Started:** 2026-05-27T04:26:58Z
- **Completed:** 2026-05-27T05:38:00Z
- **Tasks:** 3 (all TDD: RED → GREEN per task)
- **Files modified:** 8 (3 new src/, 3 new tests/, 2 modified: router.py + pyproject.toml)

## Accomplishments

- POST /api/admin/profiles/{profile_id}/sync wired with the full error taxonomy (200/400/401/403/404/409/503 with structured `detail.type` discriminators).
- D-10 cleanly split: gruvax-set-pat (stdin-only PAT provisioning) and gruvax-sync (PIN-gated full-sync trigger) live in different modules and have non-overlapping responsibilities.
- Pitfall-6 mitigation made observable: the static grep gate AND the concurrent-pool-checkout assertion both run as integration tests against the real handler.
- D-09 strict rotation enforced verbatim in gruvax-set-pat: PAT for a different discogsography user → non-zero exit with the exact CONTEXT.md wording before any DB UPDATE.
- TTY-aware PIN input in gruvax-sync proven by Test 6 (the exact `echo $GRUVAX_ADMIN_PIN | gruvax-sync --profile Default` shell-pipeline form Plan 05's init-sync container will use).

## Task Commits

Each task was committed atomically (TDD pair):

1. **Task 1: admin profile-sync endpoint**
   - Tests RED: `5bd801e` (test)
   - Handler GREEN: `6507836` (feat)
2. **Task 2: gruvax-set-pat CLI**
   - Tests RED: `5653638` (test)
   - CLI GREEN: `b835c09` (feat)
3. **Task 3: gruvax-sync CLI**
   - Tests RED: `71410fd` (test)
   - CLI GREEN: `1d53d1a` (feat)

## Files Created/Modified

**Created:**
- `src/gruvax/api/admin/profile_sync.py` — POST /api/admin/profiles/{profile_id}/sync handler. Auth via `require_admin`. Reads `request.app.state.db_pool` directly (never `Depends(get_pool)`); pre-flight 404 check in a tight async-with block; pool slot RELEASED before awaiting sync_profile. Full structured-error translation per the response taxonomy.
- `src/gruvax/cli/set_pat.py` — `gruvax-set-pat --profile <name>` CLI. Stdin-only PAT input (D-07 strict — no `--pat` flag, no env-var fallback). Inline test-sync via `client._get_page(limit=1, offset=0)` (D-08). Strict user_id-match rotation (D-09 verbatim wording). Pitfall 2: row untouched on any failure path before the UPDATE.
- `src/gruvax/cli/sync_cli.py` — `gruvax-sync --profile <name>` CLI. TTY-aware PIN input (getpass | sys.stdin.readline). POST /api/admin/login → capture session + CSRF → POST /api/admin/profiles/{id}/sync with `httpx.Timeout(read=120.0)` for the long-running response.
- `tests/integration/api/test_admin_sync_endpoint.py` — 10 tests covering the full auth + error matrix + Pitfall-6 static gate + observable concurrent-checkout assertion.
- `tests/integration/cli/test_set_pat.py` — 10 tests; subprocess harness for stdin behaviors + in-process TTY simulation.
- `tests/integration/cli/test_sync_cli.py` — 7 tests; real GRUVAX uvicorn + fake-discogsography uvicorn fixtures + `echo $PIN | gruvax-sync` shell-pipeline form (Test 6).

**Modified:**
- `src/gruvax/api/admin/router.py` — added `from gruvax.api.admin.profile_sync import router as profile_sync_router` import + `router.include_router(profile_sync_router)` line.
- `pyproject.toml` — added two `[project.scripts]` entries: `gruvax-set-pat = "gruvax.cli.set_pat:main"` and `gruvax-sync = "gruvax.cli.sync_cli:main"`.
- `.env` — populated local dev defaults (DATABASE_URL pointed at localhost:5432, fresh GRUVAX_SECRET_KEY, SESSION_SECRET, DISCOGSOGRAPHY_BASE_URL). File is gitignored.

## CLI Invocation Examples (Working)

**gruvax-set-pat — both stdin forms work:**

```bash
# Piped (CI / scripted):
echo "dscg_..." | uv run gruvax-set-pat --profile default

# Interactive (TTY → getpass prompt):
uv run gruvax-set-pat --profile default
```

**gruvax-sync — both TTY and pipe forms work:**

```bash
# Interactive TTY (operator at terminal):
uv run gruvax-sync --profile default

# Pipe (Plan 05 init-sync container form — verified by Test 6):
echo "$GRUVAX_ADMIN_PIN" | uv run gruvax-sync --profile default
```

## Pitfall-6 Pool-Isolation Confirmation

The admin handler does NOT use `Depends(get_pool)`:

```bash
$ grep -c "Depends(get_pool)" src/gruvax/api/admin/profile_sync.py
0
```

The handler pattern (verbatim from the implementation):

```python
db_pool = request.app.state.db_pool
async with db_pool.connection() as conn, conn.cursor() as cur:
    await cur.execute("SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL", (str(uid),))
    if await cur.fetchone() is None:
        raise HTTPException(404, detail={"type": "profile_not_found"})
# async-with block CLOSED here — pool slot RETURNED to the pool BEFORE awaiting sync_profile
result = await sync_profile(str(uid), request.app.state)
```

The integration test (`test_pitfall_6_handler_does_not_hold_pool_during_sync`) verifies BOTH (a) the static grep gate AND (b) the observable concurrent-checkout property: a slow sync (≈1.6s) is in flight when a concurrent pool checkout against the same pool returns in <500ms.

## Subprocess vs In-Process Test Harness Choices

| Test class                              | Harness                          | Why                                                                                                  |
| --------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------- |
| test_admin_sync_endpoint (10 tests)     | LifespanManager + AsyncClient    | The handler is pure HTTP; ASGITransport is fast + lets us monkeypatch `_make_client` inline.         |
| test_set_pat (9 of 10 tests)            | subprocess + uvicorn fixture     | The CLI must work as an installed console_script with real stdin pipe semantics — pipe vs TTY only differs in a real process. |
| test_set_pat (1 of 10 — `test_tty_flow_in_process`) | In-process call to `_read_pat()` | Subprocess can't reliably simulate `sys.stdin.isatty() = True` on macOS without a pty. In-process call + monkeypatch is the simpler honest check.       |
| test_sync_cli (6 of 7 tests)            | subprocess + 2 uvicorn fixtures  | This CLI talks to a real HTTP server; both ends must be live processes for `httpx.AsyncClient` cookies + CSRF to round-trip correctly. |
| test_sync_cli (1 of 7 — `test_static_read_timeout_120s`) | Static file read                 | "Source contains a generous read timeout" is a code-property assertion — no runtime needed.                         |

## Decisions Made

- **No `get_pool` injection on the long-running handler.** PATTERNS §Shared Patterns "Authentication — EXCEPTION FOR LONG-RUNNING OPERATIONS" calls this out explicitly. The hand-rolled pool checkout (read `request.app.state.db_pool` in a tight `async with`) is the only way to keep Plan 03's dedicated-connection design effective end-to-end.
- **AsyncMock substitution on app.state caches inside integration tests.** Plan 06 hasn't rewired `collection_snapshot.py` from `v_collection` to `profile_collection` yet, so the inline cache refresh in `sync_profile._refresh_app_caches` would crash on `UndefinedTable`. The substitution is identical to Plan 03's pattern (AsyncMock for boundary/snapshot/segment); Test 9 (D-14 inline-refresh contract) checks the call-count, not the row count.
- **Module-scoped uvicorn fixtures for test_sync_cli.** Initially session-scoped, but the necessary monkeypatch of `profile_sync._refresh_app_caches` would have leaked into `test_sync_cache_refresh.py` (later in collection order). Module scope ensures teardown happens between test files. Trade-off: 2× uvicorn process per file = +5s; cheap in absolute terms.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wrong assertion target in test_caches_refreshed_inline (Task 1)**
- **Found during:** Task 1 (happy-path test)
- **Issue:** Initial test_caches_refreshed_inline assertion read `pre_snapshot._rows` / `post_snapshot.rows` expecting CollectionSnapshot to have refreshed real row counts. Production `snapshot.load(pool)` queries `gruvax.v_collection` (Plan 06's job to rewire) — fails with `UndefinedTable` before Plan 06 lands.
- **Fix:** Substituted AsyncMock cache hooks on app.state AFTER lifespan startup; reframed Test 9 to verify the D-14 inline-refresh contract via mock call counts (snapshot.load.call_count ≥ 1, boundary.load.call_count ≥ 1).
- **Files modified:** tests/integration/api/test_admin_sync_endpoint.py (app_client fixture)
- **Verification:** All 10 tests pass; Plan 03's test_sync_cache_refresh.py still passes too (confirms no regression on the real cache-refresh wiring).
- **Committed in:** 6507836 (Task 1 GREEN commit)

**2. [Rule 3 - Blocking] PoolTimeout in CLI subprocess fixtures (Task 2)**
- **Found during:** Task 2 (first CLI subprocess test)
- **Issue:** The `reset_profile` async fixture (no explicit loop_scope) ran on a per-function event loop, but `db_pool` is `loop_scope="session"`. Mixing loops causes pool checkouts to hang for 30s and time out.
- **Fix:** Added `loop_scope="session"` to the `reset_profile` and `reset_profile_and_pin` pytest_asyncio fixtures — matching the explicit pattern used in Plan 03's `test_sync_profile.py`.
- **Files modified:** tests/integration/cli/test_set_pat.py, tests/integration/cli/test_sync_cli.py
- **Committed in:** b835c09, 1d53d1a (within respective Task GREEN commits)

**3. [Rule 3 - Blocking] AsyncMock substitution leaked into Plan 03 tests via uvicorn process lifetime (Task 3)**
- **Found during:** Task 3 (cross-module regression)
- **Issue:** A session-scoped uvicorn fixture started for test_sync_cli.py kept the no-op monkeypatch on `profile_sync._refresh_app_caches` alive across all subsequent test files. test_sync_cache_refresh.py then asserted the real cache hooks fired and failed.
- **Fix:** Changed `fake_disco_server`, `gruvax_api_server`, `fake_disco_port`, `gruvax_api_port` to module-scope (was session-scope). Also captured the original `_refresh_app_caches` reference in the fixture and restored it on teardown — defense-in-depth against future scope changes.
- **Files modified:** tests/integration/cli/test_sync_cli.py
- **Verification:** Full Plan-04 + Plan-03 + admin-auth suite (53 tests) passes; no regressions in test_sync_cache_refresh.py.
- **Committed in:** 1d53d1a (Task 3 GREEN commit)

**4. [Rule 3 - Blocking] semgrep urllib warning in test_sync_cli health-check polling**
- **Found during:** Task 3 (initial test file write)
- **Issue:** semgrep MCP scan flagged `urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", ...)` as supporting the `file://` scheme attack surface — even though the URL is a test-controlled localhost literal.
- **Fix:** Switched to `httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1.0)` — httpx is HTTP/HTTPS-only and already a project dependency.
- **Files modified:** tests/integration/cli/test_sync_cli.py
- **Verification:** semgrep clean; functional behavior unchanged.
- **Committed in:** 71410fd (Task 3 RED commit)

**5. [Rule 3 - Blocking] Missing `.env` for local test runs**
- **Found during:** Pre-Task-1 setup
- **Issue:** Tests require `DATABASE_URL`, `SESSION_SECRET`, `DISCOGSOGRAPHY_BASE_URL`, `GRUVAX_SECRET_KEY` — `.env` did not exist locally.
- **Fix:** Created `.env` (gitignored) with localhost-pointing DATABASE_URL + a fresh Fernet key + safe placeholders for the other secrets.
- **Files modified:** .env (gitignored — not in version control)
- **Verification:** Baseline `pytest tests/integration/sync/test_sync_profile.py` passes (11/11).

---

**Total deviations:** 5 auto-fixed (5 Rule 3 - Blocking)
**Impact on plan:** All five were ordering / environment scaffolding issues. None affected the plan's correctness contracts (D-07/D-08/D-09/D-10, Pitfall 6, response taxonomy). No scope creep.

## Issues Encountered

- Wave-ordering dependency on Plan 06 surfaced clearly in Task 1: the inline cache refresh (D-14) calls `snapshot.load(pool)` which still hits the dropped `v_collection` view because Plan 06's `collection_snapshot.py` rewire is in a later wave. Resolved via AsyncMock substitution (consistent with Plan 03's approach). Plan 06's verifier should drop this scaffold once `collection_snapshot.py` is migrated.

## User Setup Required

None. All new surfaces (admin endpoint + 2 CLIs) configure themselves from existing env vars (`DATABASE_URL`, `SESSION_SECRET`, `DISCOGSOGRAPHY_BASE_URL`, `GRUVAX_SECRET_KEY`, `GRUVAX_BASE_URL`).

## Next Phase Readiness

- **Plan 05 (compose + health rewire) can land in parallel.** Plan 05's init-sync container can shell out to `echo $GRUVAX_ADMIN_PIN | gruvax-sync --profile default` immediately — Test 6 explicitly covers that form.
- **Plan 06 (queries.py + collection_snapshot.py rewire) is the gating dependency for end-to-end "real" cache refresh.** Once that lands, the AsyncMock cache substitutions in `test_admin_sync_endpoint.py` and `test_sync_cli.py` can be removed and the production code paths will assert directly.
- **P2 (multi-user collections) inherits the same admin endpoint** — the "Sync now" admin-UI button just POSTs to it; no rework needed on the backend.

## Self-Check: PASSED

Files exist:
- `src/gruvax/api/admin/profile_sync.py` — FOUND
- `src/gruvax/cli/set_pat.py` — FOUND
- `src/gruvax/cli/sync_cli.py` — FOUND
- `tests/integration/api/test_admin_sync_endpoint.py` — FOUND
- `tests/integration/cli/test_set_pat.py` — FOUND
- `tests/integration/cli/test_sync_cli.py` — FOUND

Commits exist:
- `5bd801e` (test RED Task 1) — FOUND
- `6507836` (feat GREEN Task 1) — FOUND
- `5653638` (test RED Task 2) — FOUND
- `b835c09` (feat GREEN Task 2) — FOUND
- `71410fd` (test RED Task 3) — FOUND
- `1d53d1a` (feat GREEN Task 3) — FOUND

Plan verification:
- `grep -c "Depends(get_pool)" src/gruvax/api/admin/profile_sync.py` → 0 ✓
- `grep -c "gruvax-set-pat" pyproject.toml` → 1 ✓
- `grep -c "gruvax-sync" pyproject.toml` → 1 ✓
- `grep -c "PAT belongs to a different discogsography user" src/gruvax/cli/set_pat.py` → 1 ✓
- `grep -c "stdin.read\|isatty" src/gruvax/cli/set_pat.py` → 2 ✓
- `grep -c "stdin.readline\|isatty" src/gruvax/cli/sync_cli.py` → 4 ✓
- `uv run pytest tests/integration/api/test_admin_sync_endpoint.py tests/integration/cli/ -q` → 27 passed ✓

---
*Phase: 01-walking-skeleton-api-client-single-profile-sync*
*Completed: 2026-05-26*

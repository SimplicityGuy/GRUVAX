---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 05
subsystem: api
tags: [health, lifespan, compose, fake-discogsography, init-sync, fastapi, docker]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 01-03)
    provides: profile_collection table, profiles.last_sync_at, sync_profile + advisory lock
  - phase: 01-walking-skeleton-api-client-single-profile-sync (plan 01-00)
    provides: src/gruvax/_internal/fake_discogsography.py canonical module, services/fake-discogsography/seed.yaml (~3000 releases)
provides:
  - /api/health discogsography_api_check three-state field per D-13 (ok|failed|stale)
  - Lifespan profile_collection startup probe (replaces v_collection)
  - 60s default_profile_state background task reading gruvax.profiles.last_sync_at
  - Compose fake-discogsography sibling service (importing the canonical module — D-15)
  - Compose init-sync one-shot with D-16 idempotency precheck
  - just compose-smoke recipe + CI gate
  - HealthResponse TypeScript type for the frontend
affects:
  - 01-06 (queries.py + collection_snapshot.py rewire — final v_collection → profile_collection sweep)
  - 02 (multi-profile fanout — base health/lifespan/compose shape carries forward)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "No-live-probe /api/health (cached app.state attributes refreshed by 60s background task)"
    - "Three-state staleness derivation (failed > stale > ok; in_progress maps to ok per D-13 Warning #4)"
    - "Lifespan startup probe pattern carries over from v1 (try/except + flip flag + continue)"
    - "Compose init-sync idempotency via psql precheck — never re-syncs unnecessarily (D-16)"
    - "D-15 canonical-module single-source — services/ import the in-repo module, no copies"

key-files:
  created:
    - services/fake-discogsography/Dockerfile
    - services/fake-discogsography/server.py
    - tests/integration/api/test_health.py
    - tests/integration/test_compose_smoke.py
    - .planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-05-SUMMARY.md
  modified:
    - src/gruvax/api/health.py
    - src/gruvax/app.py
    - frontend/src/api/types.ts
    - compose.yaml
    - justfile
    - .github/workflows/build.yml
  deleted:
    - tests/integration/test_health.py  # replaced by tests/integration/api/test_health.py (D-13 contract)

key-decisions:
  - "Frontend HealthResponse type was missing from v1 types.ts — added in this plan (zero-consumer rename means no other frontend file changes were needed)"
  - "Plan 01-04 owns pyproject.toml changes per the executor concurrency note; this plan installs the gruvax package as-is (fastapi/pyyaml/pydantic/uvicorn already in core deps, no [fake] extra needed)"
  - "init-sync uses PSQL_DSN (libpq form) for the precheck + DATABASE_URL (SQLAlchemy form) for app code paths — psql doesn't understand postgresql+psycopg:// schemes"
  - "Compose `command:` uses YAML block-literal so embedded $$ Compose-escapes survive into the container shell (verified via `docker compose config`)"
  - "Replaced the legacy `tests/integration/test_health.py` outright (its assertions reference the dropped `discogsography_view_check` field and would block CI)"

patterns-established:
  - "Pattern 1: lifespan-startup probe targets profile_collection — set ready flag, log error, continue (never crash)"
  - "Pattern 2: 60s background task reads `gruvax.profiles WHERE id = DEFAULT_PROFILE_UUID` and caches default_profile_last_sync_at/last_sync_status/app_token_revoked on app.state"
  - "Pattern 3: /api/health derives discogsography_api_check from cached app.state attributes (zero DB hits per request)"
  - "Pattern 4: D-15 services/ entry script imports canonical module — `from gruvax._internal.fake_discogsography import create_fake_app`"
  - "Pattern 5: init-sync command shell-block performs psql precheck on a sentinel COUNT(*) gate before any side-effect (D-16 idempotent contract)"

requirements-completed: [SYN-02]

# Metrics
duration: ~21min
completed: 2026-05-27
---

# Phase 1 Plan 5: /api/health rewire + compose fake-discogsography + init-sync + compose-smoke gate Summary

**Wire-side completion of the v_collection → profile_collection swap: /api/health field renamed and three-state derivation landed per D-13 (in_progress → ok per Warning #4); lifespan probe + 60s background task rewired to profile_collection / profiles.last_sync_at; Compose stack now boots a fake-discogsography sibling and a one-shot idempotent init-sync container so `docker compose up` runs a real end-to-end sync the first time and a no-op on subsequent boots.**

## Performance

- **Duration:** ~21 min
- **Started:** 2026-05-27T04:33:50Z (test commit c4d040d)
- **Completed:** 2026-05-27T04:54:58Z
- **Tasks:** 3 (all auto-tdd)
- **Files modified:** 11 (5 created, 6 modified, 1 deleted)

## Accomplishments

- `/api/health` now returns `discogsography_api_check` (renamed from `discogsography_view_check`) with the D-13 three-state union {`ok`, `failed`, `stale`} — derived from cached `app.state.default_profile_*` attributes, NO live DB probe per request. Warning #4 RESOLUTION baked in: `in_progress` maps to `ok` (active sync is healthy state; Plan 03's watchdog owns the failure flip after 5 min).
- Lifespan startup probe targets `gruvax.profile_collection WHERE profile_id = DEFAULT_PROFILE_UUID` — the v_collection probe is gone (the view was dropped in migration 0009). Same "log + flip flag + continue" pattern as v1 — startup never crashes on probe failure.
- Replaced `_refresh_sync_age` with `_refresh_default_profile_state` — reads `last_sync_at`, `last_sync_status`, and `app_token_revoked` from `gruvax.profiles` for the default profile every 60s. `sync_age_seconds` is now derived from `default_profile_last_sync_at` (NOT `max(v_collection.synced_at)`).
- Legacy `app.state.discogsography_view_ok` is gone — verified by `! grep discogsography_view_ok src/gruvax/app.py`.
- Frontend `HealthResponse` TypeScript interface added to `frontend/src/api/types.ts` with the new field shape per D-13. (The v1 types.ts had no HealthResponse interface — zero consumers means the rename was strictly type-only.)
- Compose `fake-discogsography` sibling service: builds a minimal `python:3.14-slim` image that installs the gruvax package and imports the canonical module at `gruvax._internal.fake_discogsography` (D-15 single-source). Non-root user, internal-only network (no host port mapping — T-01-fake-svc-exposure mitigation), healthcheck against `/api/user/collection?limit=1`.
- Compose `init-sync` one-shot service: implements D-16 verbatim — `psql ... SELECT COUNT(*) FROM gruvax.profile_collection WHERE profile_id = '00000000-0000-0000-0000-000000000001'` precheck; if > 0 logs `"profile_collection already populated for default profile; skipping initial sync"` and exits 0; if == 0 runs `echo $$GRUVAX_ADMIN_PIN | gruvax-sync --profile default`. `GRUVAX_ADMIN_PIN` uses `${VAR:?...}` substitution so compose-up fails clearly when unset (T-01-init-sync-pin mitigation).
- `just compose-smoke` recipe added (Blocker #2 RESOLUTION) — brings up `api + fake-discogsography + init-sync`, waits ≤60s for init-sync to exit, asserts exit code 0, verifies fake-discogsography serves rows, tears down with `docker compose down -v`. CI step added to `.github/workflows/build.yml` runs it with test-only env values.

## Task Commits

Each task was committed atomically (TDD pattern — RED then GREEN):

1. **Task 1 + 2 RED: failing tests for /api/health D-13 + lifespan rewire** — `c4d040d` (test)
2. **Task 1 + 2 GREEN: health.py + app.py + types.ts implementation** — `3d119a0` (feat)
3. **Task 3 RED: failing structural tests for compose + init-sync** — `3538558` (test)
4. **Task 3 GREEN: Dockerfile + server.py + compose.yaml + justfile + CI gate** — `4dc644a` (feat)

_Tasks 1 + 2 were consolidated into a single RED commit (and a single GREEN commit) because they share the same test file (per Task 2 action: "Extend or write tests in `tests/integration/api/test_health.py` (Task 1's file)... they overlap heavily with Task 1's testing surface and consolidating prevents fixture duplication.") and the same lifespan-managed FastAPI fixture surface._

## Files Created/Modified

### Created
- `services/fake-discogsography/Dockerfile` — single-stage minimal `python:3.14-slim` image; installs the gruvax package via `uv pip install --system .`; non-root `fake` user (CWE-250 mitigation); HEALTHCHECK hits `/api/user/collection?limit=1` with `Bearer dscg_dev_seed`; `CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8004"]`.
- `services/fake-discogsography/server.py` — imports `create_fake_app` from the canonical `gruvax._internal.fake_discogsography` (D-15); loads seed from sibling `seed.yaml` (Plan 01-00 generated; 3000 releases verified); exposes module-level `app` for uvicorn.
- `tests/integration/api/test_health.py` — 22 tests covering Tasks 1 + 2 (12 health-derivation + 4 lifespan + 6 v1 contract carry-over).
- `tests/integration/test_compose_smoke.py` — 10 fast structural tests asserting compose.yaml service blocks, services/fake-discogsography/ shape (D-15 grep gates), and justfile recipe.
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-05-SUMMARY.md` — this file.

### Modified
- `src/gruvax/api/health.py` — field rename + 3-state derivation per D-13; `_STALE_THRESHOLD = timedelta(hours=24)` module constant; in_progress → ok (Warning #4 RESOLUTION code comment); overall status derivation cites api_check.
- `src/gruvax/app.py` — `DEFAULT_PROFILE_UUID` module-top constant; lifespan step 2 probe targets `gruvax.profile_collection`; step 1c `_refresh_default_profile_state` background task; legacy `discogsography_view_ok` assignments removed.
- `frontend/src/api/types.ts` — added `HealthResponse` interface (was missing in v1) with the new D-13 field shape.
- `compose.yaml` — added `fake-discogsography` + `init-sync` service blocks; api.depends_on adds `fake-discogsography: condition: service_healthy`.
- `justfile` — added `compose-smoke` recipe.
- `.github/workflows/build.yml` — added "Compose smoke gate" step in the build job that runs `just compose-smoke`.

### Deleted
- `tests/integration/test_health.py` — replaced by `tests/integration/api/test_health.py`. The deleted file referenced the dropped `discogsography_view_check` field and `app.state.discogsography_view_ok` attribute; its assertions would block CI post-rewire.

## Decisions Made

- **Test file location:** moved health tests from `tests/integration/test_health.py` to `tests/integration/api/test_health.py` per the plan's per-task validation row (`01-05-01`). Old file deleted in the same commit as the new file.
- **Tasks 1 + 2 consolidated:** per plan Task 2 action ("Extend or write tests in `tests/integration/api/test_health.py` (Task 1's file)... overlap heavily with Task 1's testing surface"), I produced one RED commit + one GREEN commit covering both — single fixture surface, no duplication.
- **No pyproject.toml `[fake]` extra:** sibling Plan 01-04 owns pyproject.toml; the canonical fake module only needs `fastapi`, `pydantic`, `pyyaml`, `uvicorn` — all already in the gruvax core dep set. `uv pip install --system .` resolves everything without needing an optional extra.
- **init-sync DSN split:** psql understands `postgresql://` (libpq) but not `postgresql+psycopg://` (SQLAlchemy form). The compose env declares `PSQL_DSN` (libpq) for the precheck and keeps `DATABASE_URL` (SQLAlchemy form) for any in-process app code path the gruvax image might import.
- **Compose `command:` block-literal style:** YAML block literal `>` was tried first but the embedded `$$` escapes for `$$COUNT`, `$$PSQL_DSN`, `$$GRUVAX_ADMIN_PIN` are easier to read in `|` block-literal form. `docker compose config` verified the rendered command has the right `$$` → `$` Compose escapes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Non-root user in fake-discogsography Dockerfile (CWE-250)**

- **Found during:** Task 3 (Dockerfile creation)
- **Issue:** First-pass Dockerfile ran the container as root by default. Semgrep PreToolUse hook blocked the Write call, flagging CWE-250 (Execution with Unnecessary Privileges).
- **Fix:** Added a non-root `fake` user (groupadd + useradd `--no-create-home --shell /usr/sbin/nologin`), `chown` of `/app`, and `USER fake` before the EXPOSE / HEALTHCHECK / CMD lines. Mirrors the main Dockerfile's `gruvax` user convention.
- **Files modified:** `services/fake-discogsography/Dockerfile`
- **Verification:** semgrep hook re-runs clean; container image will run as `fake` user.
- **Committed in:** `4dc644a`

**2. [Rule 3 - Blocking] Ruff lint + format cleanup on Task 3 commit**

- **Found during:** Task 3 final verification (`uv run ruff check` + `ruff format --check`)
- **Issue:** Initial test_compose_smoke.py used `if/else` for the command-string flattening (SIM108 lint error) and one f-string had no placeholders; also ruff format reflowed health.py + app.py + test_health.py (the existing format width was different from what the project's ruff config now expects).
- **Fix:** Replaced the if/else with a ternary (SIM108), then ran `ruff format` on all five touched files; the format reflow on the previously-committed health.py + app.py + test_health.py is pure cosmetic (no logic change).
- **Files modified:** `tests/integration/test_compose_smoke.py` + ruff-format reflow on `src/gruvax/api/health.py`, `src/gruvax/app.py`, `tests/integration/api/test_health.py`
- **Verification:** `uv run ruff check ... && uv run ruff format --check ...` both clean.
- **Committed in:** `4dc644a` (included in the Task 3 GREEN commit since it was a side-effect of the same edit session)

---

**Total deviations:** 2 auto-fixed (1 missing critical security mitigation, 1 blocking lint)
**Impact on plan:** Both deviations were necessary for correctness — the Dockerfile non-root user is a CWE-250 mitigation flagged by the semgrep hook, and the lint cleanup was required to pass the code-quality gate. No scope creep.

## Issues Encountered

- **Background test ran very slowly (>2 min) on first try** — the `uv run pytest` command with the LifespanManager fixture took longer than expected to spin up. Killed the stuck processes and re-ran with `--override-ini="addopts="` to bypass the project-level `-q` flag (which suppresses tracebacks). Once that was set, all 32 tests finish in ~1.3 s.
- **`addopts = "-q --tb=short"` in pyproject.toml mangled traceback visibility** — initial test runs returned only `F` characters with no traceback even with `-v --tb=long` because the `-q` short-form was overriding. Workaround: pass `--override-ini="addopts="` when needing full output for debugging. (Not a code change — diagnostic note for future runs.)
- **Compose env-file resolution surprise** — `docker compose config` rendered the init-sync command with `$$COUNT` (Compose-escaped `$`), which is exactly what's needed inside the container shell. The `|` block-literal form preserves the `$$` literally; the `>` folded form would collapse newlines. Verified by inspecting the rendered output.

## User Setup Required

None — no external service configuration required. The init-sync container's `GRUVAX_ADMIN_PIN` requirement is enforced by compose `${VAR:?...}` substitution at compose-up time, so missing values produce a clear error message rather than silent boot. Local dev sets `GRUVAX_ADMIN_PIN` in `.env`; CI sets it as an inline env var on the `just compose-smoke` step.

## Concurrency / Sibling Plan Note

This plan ran in parallel with sibling Plan 01-04 (`admin endpoint + 2 CLIs`). Per the executor concurrency note, `pyproject.toml` was NOT modified here — 01-04 owns the `[project.scripts]` additions for `gruvax-set-pat` and `gruvax-sync`. The compose `init-sync` command relies on `gruvax-sync` being installed as a CLI entry-point inside the gruvax image — that entry-point lands when sibling Plan 01-04's commits merge with this plan's commits. No other shared files modified.

## D-15 Single-Module Compliance Confirmation

- `services/fake-discogsography/server.py` imports `from gruvax._internal.fake_discogsography import create_fake_app` — verified (grep gate test_compose_smoke.py::test_fake_discogsography_server_imports_canonical_module passes).
- NO `services/fake-discogsography/fake_discogsography.py` file — verified (grep gate test_compose_smoke.py::test_no_duplicate_fake_module_in_services_dir passes; `! test -f services/fake-discogsography/fake_discogsography.py`).
- NO `just sync-fake` recipe in justfile — verified (`grep sync-fake justfile` returns nothing).
- Dockerfile installs the gruvax package itself (`uv pip install --system .`) so the canonical module is importable at runtime.

## Sample /api/health Response (Post-Rewire)

```json
{
  "status": "ok",
  "db": "ok",
  "discogsography_api_check": "ok",
  "mqtt": "ok",
  "version": "dev",
  "started_at": "2026-05-27T04:53:12.123456+00:00",
  "sync_age_seconds": 42.7
}
```

State transitions per D-13:
- `discogsography_api_check = "ok"` — last_sync_status='ok' AND app_token_revoked=FALSE (or in_progress)
- `discogsography_api_check = "failed"` — last_sync_status='failed' OR app_token_revoked=TRUE
- `discogsography_api_check = "stale"` — last_sync_at IS NULL OR now() - last_sync_at > 24h
- `status = "degraded"` whenever `db_ok=FALSE` OR `discogsography_api_check != "ok"`

## Sample Lifespan Startup Log Lines

```
INFO  profile_collection probe: OK
INFO  Boundary cache loaded (32 rows)
INFO  Collection snapshot loaded (...labels)
INFO  SegmentCache derived (...bins)
INFO  Settings cache loaded (...keys)
INFO  EventBus ready; server_hello published
INFO  default_profile_state background refresh task scheduled (60s cadence)
INFO  Ambient baseline publish task scheduled at startup (LED-11/D-20)
```

## Self-Check: PASSED

- [x] `src/gruvax/api/health.py` — exists, contains `discogsography_api_check`
- [x] `src/gruvax/app.py` — exists, no longer references `discogsography_view_ok`
- [x] `frontend/src/api/types.ts` — exists, contains HealthResponse with 3-state union
- [x] `services/fake-discogsography/Dockerfile` — exists, non-root user
- [x] `services/fake-discogsography/server.py` — exists, imports canonical module
- [x] `services/fake-discogsography/seed.yaml` — exists (Wave 0 generated), 3000 releases
- [x] `compose.yaml` — fake-discogsography + init-sync blocks present; api.depends_on updated
- [x] `justfile` — `compose-smoke` recipe present
- [x] `.github/workflows/build.yml` — Compose smoke gate step present
- [x] `tests/integration/api/test_health.py` — exists, 22 tests pass
- [x] `tests/integration/test_compose_smoke.py` — exists, 10 tests pass
- [x] `tests/integration/test_health.py` — deleted (legacy v1 file)
- [x] Commits — c4d040d (RED), 3d119a0 (GREEN), 3538558 (RED), 4dc644a (GREEN) all in `git log`

## Threat Surface Scan

No new threat surface introduced beyond the plan's `<threat_model>`. The init-sync container processes the admin PIN via stdin pipe per the plan's contract (T-01-init-sync-pin already mitigated via `${VAR:?...}`); the fake-discogsography service is bound internal-only per T-01-fake-svc-exposure; the canonical-module import gate prevents the T-01-fake-drift threat.

## Next Phase Readiness

Plan 01-06 (Wave 4 — queries.py + collection_snapshot.py rewire) is unblocked. The wire-side rewire is complete; what remains for plan 06 is the heavy read-path rewire (search_collection, get_release_for_locate, get_sync_staleness_seconds, get_phantom_boundary_count, snapshot.load) that touches the hot path of the kiosk search/locate API. The SLO benchmark gate (`just slo`) in plan 06 will validate that the new `profile_collection` source preserves the v1.0 p95 ≤ 200 ms search invariant.

Sibling plan 01-04 (admin endpoint + 2 CLIs) commits will merge with this plan's commits; the init-sync container's `gruvax-sync` invocation relies on the `[project.scripts]` entry-point that 01-04 adds.

---
*Phase: 01-walking-skeleton-api-client-single-profile-sync*
*Plan: 05*
*Completed: 2026-05-27*

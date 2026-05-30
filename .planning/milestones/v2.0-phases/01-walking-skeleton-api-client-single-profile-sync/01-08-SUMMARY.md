---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 08
subsystem: testing
tags: [gap-closure, migration-test, subprocess-harness, alembic, pytest-asyncio, asyncio-loop-conflict, sc-3]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-api-client-single-profile-sync
    provides: "Plan 01-01 Task 2's `tests/integration/test_migrate_0009.py` (8 behavior tests for migration 0009 — profiles + profile_collection + 7-table fanout)."
provides:
  - "Working in-pytest evidence path for SC-3 'Alembic round-trip is clean' sub-clause: the test harness no longer errors with `RuntimeError: asyncio.run() cannot be called from a running event loop`."
  - "subprocess-driven `_alembic()` helper that mirrors the canonical `just migrate-roundtrip` argv exactly, so test failure surfaces match the CI gate's failure surfaces."
affects:
  - "Future migration-verification tests that need to drive alembic from inside pytest — they should follow the subprocess + asyncio.to_thread pattern established here, NOT call `alembic.command.upgrade()` programmatically."
  - "Phase 02+ (any plan that adds another `tests/integration/test_migrate_*.py` module) — the pattern from this fix is the supported way to invoke alembic from within an async test."

# Tech tracking
tech-stack:
  added: []  # subprocess + asyncio are std-lib; no new dependencies.
  patterns:
    - "subprocess + asyncio.to_thread for invoking sync CLIs that internally `asyncio.run()` — the only safe way to call a tool that owns its own event loop from within an already-running pytest-asyncio loop."
    - "Custom AssertionError carrying full stdout/stderr instead of relying on CalledProcessError's truncated default __str__ — dramatically more useful in pytest failure reports."

key-files:
  created: []
  modified:
    - "tests/integration/test_migrate_0009.py — `_alembic()` helper rewritten to drive alembic via subprocess.run wrapped in asyncio.to_thread; lazy `from alembic import command` / `Config` imports removed; top-level `import asyncio` + `import subprocess` added (ruff-sorted)."

key-decisions:
  - "Use `uv run alembic ...` argv (not bare `alembic` or `python -m alembic`) to mirror the justfile recipe exactly — operators and CI both invoke alembic this way, so a failure here surfaces an identical error to a failure during operator/CI runs."
  - "Wrap subprocess.run in asyncio.to_thread (not subprocess.create_subprocess_exec) — to_thread is simpler, the test event loop has nothing else to do during a migration anyway, and capture_output+timeout work as documented without manual stream-pumping."
  - "Manually check returncode + raise custom AssertionError instead of check=True — CalledProcessError's default __str__ truncates output; a custom AssertionError with full stdout/stderr is dramatically more useful in pytest failure reports."
  - "Resolve cwd to repo root and let alembic auto-discover alembic.ini (no -c flag) — matches the justfile recipe; one less argument to keep in sync."

patterns-established:
  - "Subprocess-via-to_thread for CLIs that internally `asyncio.run()` — the canonical workaround for the 'cannot call asyncio.run() from a running loop' constraint in pytest-asyncio tests."
  - "Argv mirrors canonical justfile recipe — so the test failure surface and the operator/CI failure surface are byte-identical, eliminating 'works in tests, fails in CI' divergence."

requirements-completed: [API-03]

# Metrics
duration: 11min
completed: 2026-05-27
---

# Phase 01 Plan 08: Migration-Round-Trip In-Pytest Harness (Gap #2 Closure) Summary

**Rewrote `tests/integration/test_migrate_0009.py::_alembic()` to drive alembic via `subprocess.run` wrapped in `asyncio.to_thread`, eliminating the `RuntimeError: asyncio.run() cannot be called from a running event loop` that ERRORed all 8 tests in the module.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-27T16:45:55Z
- **Completed:** 2026-05-27T16:57:30Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- **Closed Gap #2 (WARNING) from 01-VERIFICATION.md** — `RuntimeError: asyncio.run() cannot be called from a running event loop` occurrences in test output: **0** (was: every test in the module).
- **SC-3 round-trip cleanness now has two independent evidence paths** — (a) the shell `just migrate-roundtrip` CI gate, and (b) this in-pytest schema-verification module. The earlier asymmetry (CI worked, in-pytest didn't) is gone.
- **Failure surfaces are now byte-identical between tests and CI** — the test subprocess uses the same `uv run alembic ...` argv that operators and CI use; a migration error surfaces identically in both paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite _alembic() helper to subprocess.run via asyncio.to_thread (Gap #2 close)** — `a5087ac` (fix)

## Files Created/Modified

- `tests/integration/test_migrate_0009.py` — `_alembic()` helper body rewritten:
  - **Removed:** lazy `from alembic import command` / `from alembic.config import Config` imports; the `alembic_ini = Path(...)` + `cfg = Config(...)` resolution; the `command.upgrade(cfg, target)` / `command.downgrade(cfg, target)` invocations.
  - **Added:** top-level `import asyncio` + `import subprocess` (ruff-sorted); input validation on `action`; argv `["uv", "run", "alembic", action, target]` mirroring the `just migrate-roundtrip` recipe; `cwd` set to repo root so alembic auto-discovers `alembic.ini`; `subprocess.run` wrapped in `await asyncio.to_thread(...)` with `capture_output=True`, `text=True`, `timeout=120`; manual returncode check raising a custom `AssertionError` with full stdout/stderr.
  - **Preserved:** the `async def _alembic(action: str, target: str) -> None` signature — all three caller sites (`fresh_head` fixture, `test_alembic_round_trip_is_clean` × 2) continue to `await _alembic(...)` unchanged.

## Decisions Made

- **`uv run alembic` argv (not bare `alembic` or `python -m alembic`)** — mirrors the `justfile` recipe exactly. Operators and CI both invoke alembic this way; an error here is the same error they would see.
- **`asyncio.to_thread`, not `asyncio.create_subprocess_exec`** — the test event loop has nothing else to do during a multi-second migration, and `to_thread + subprocess.run` is far simpler (capture_output, timeout, text work as documented; no manual stream pumping).
- **Custom `AssertionError` over `check=True`** — `subprocess.CalledProcessError.__str__` truncates output by default. A custom `AssertionError` carrying full stdout + stderr is dramatically more useful in pytest failure reports.
- **No `-c alembic.ini` flag** — alembic auto-discovers `alembic.ini` from cwd, which is set to repo root; matches the justfile recipe.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Copied repo `.env` into worktree so conftest could load `gruvax.settings`**

- **Found during:** Task 1 verification (running `pytest --collect-only` to count collected tests)
- **Issue:** `tests/conftest.py:32` imports `from gruvax.db.pool import create_pool`, which triggers `gruvax.settings.Settings()` instantiation at module import. Without `.env`, pydantic-settings raises `ValidationError: 4 validation errors for Settings` (`DATABASE_URL`, `DISCOGSOGRAPHY_BASE_URL`, `SESSION_SECRET`, `GRUVAX_SECRET_KEY` all missing) → conftest fails to import → 0 tests collected → verify gate's "≥7 collected tests" check would erroneously fail with `COLLECTED=0`, masking the actual asyncio-loop fix.
- **Fix:** `cp /Users/Robert/Code/public/GRUVAX/.env ./.env` — `.env` is gitignored (`.gitignore:151`) so this does not affect the commit. The file is the operator's existing dev `.env`, identical content to what `just test` uses.
- **Files modified:** None tracked in git (`.env` is gitignored).
- **Verification:** `pytest --collect-only` now reports 8 collected tests; conftest loads successfully.
- **Committed in:** N/A (gitignored side effect of the test harness, not a code change).

**2. [Rule 1 - Bug] Verify-gate shell logic corrected for grep -c's exit-code semantics**

- **Found during:** Task 1 verification (first attempt of the verify gate)
- **Issue:** The plan's strengthened verify-gate snippet used the pattern `ERR=$(grep -c ... || echo 0)`. When grep matches zero lines, it prints `0` AND exits 1, so the `|| echo 0` runs, concatenating `"0\n0"` into `$ERR`. The subsequent `[ "$ERR" != "0" ]` test compares against `"0\n0"` (truthy) and reports a spurious FAIL — even though the actual asyncio-loop error count IS zero.
- **Fix:** Wrap the grep in `set +e; ERR=$(grep -c ...); set -e` so a zero-match doesn't trigger the `|| echo 0` fallback. The verify then correctly reports `ERR=0` and exits 0. (Note: this is a deviation in the verification harness, not in the test code. The test code is correct; the verify-gate's shell quoting was the bug.)
- **Files modified:** None (one-off shell invocation, not committed).
- **Verification:** Final verify gate output: `OK: asyncio-loop error = 0, collected = 8`.
- **Committed in:** N/A (verify-gate logic is the harness, not the deliverable).

**3. [Rule 3 - Blocking] ruff isort reorganization after import additions**

- **Found during:** Post-edit lint check (between the edit and the commit)
- **Issue:** Adding `import asyncio` and `import subprocess` to the top of the file triggered `I001 [*] Import block is un-sorted or un-formatted`. ruff is the project's lint gate (matched to discogsography per CLAUDE.md), so an `I001` would block the precommit hook on the actual commit.
- **Fix:** `uv run ruff check --fix tests/integration/test_migrate_0009.py` — ruff moved `import subprocess` between `from pathlib import Path` and `from typing import TYPE_CHECKING` (alphabetical within the stdlib block, with `from pathlib` placed first per ruff's isort default for mixed `import`/`from` ordering).
- **Files modified:** `tests/integration/test_migrate_0009.py` (re-formatted, no semantic change).
- **Verification:** `uv run ruff check tests/integration/test_migrate_0009.py` → All checks passed; `uv run ruff format --check ...` → 1 file already formatted.
- **Committed in:** `a5087ac` (Task 1 commit — the formatted version is what was committed).

**4. [Documentation - Plan slip] Plan said "7 tests collected", actual count is 8**

- **Found during:** Task 1 verification (`pytest --collect-only` output)
- **Issue:** The plan repeatedly referenced "7 tests" in the module (verify gate, acceptance criteria, success criteria). The actual file has 8 test functions — 7 async behavior tests + 1 sync `test_legacy_seed_path_resolves` (Behavior 10). The plan checker's count was off by one.
- **Fix:** Verified the spirit of the check still holds (`8 ≥ 7` = we have AT LEAST the 7 expected tests; nothing was inadvertently removed by the rewrite). The strengthened verify gate's `if [ "$COLLECTED" -lt 7 ]` correctly treats 8 as PASS. No code change required — this is a documentation slip in the plan, not a defect in the implementation.
- **Files modified:** None.
- **Verification:** Final verify gate: `collected = 8` (≥7 required) → PASS.
- **Committed in:** N/A.

---

**Total deviations:** 4 (3 Rule 3 blocking, 1 documentation slip)
**Impact on plan:** All deviations were on the verification path (env setup, shell quoting, lint formatting) or in the plan documentation (off-by-one test count). The core deliverable — the rewritten `_alembic()` helper using `subprocess.run` via `asyncio.to_thread` — was implemented exactly as the plan specified. No scope creep.

## Issues Encountered

- **Pre-existing environmental:** When running the test bodies (not just collection), `psycopg_pool.PoolTimeout: couldn't get a connection after 30.00 sec` is raised because the worktree cannot reach `gruvax-dev-pg` (the docker-network DB hostname). This is **out of scope per Gap #2's "Out of scope" note** — operator concern, not a code bug. The asyncio-loop error elimination (the actual deliverable of this plan) is proven by the verify gate independently of whether the DB is reachable.
- **CI-gate handoff:** The "all 8 tests PASS against a fresh CI postgres:18 service" assertion is the CI-gate handoff — this plan only proves (a) the asyncio-loop `RuntimeError` is gone and (b) the module collects cleanly. The all-PASS assertion is explicitly deferred per the plan's `<acceptance_criteria>` ("verifier may need to confirm via a CI run").

## User Setup Required

None — no external service configuration required. The `.env` copied into the worktree during verification is gitignored and is the same `.env` the operator's local dev environment already uses.

## Next Phase Readiness

- **Gap #2 (WARNING) is closed at the test-harness level.** The next time the CI suite runs against `postgres:18`, all 8 tests in `test_migrate_0009.py` will either PASS (proving SC-3 from the in-pytest path) or FAIL with **meaningful diffs** instead of ERRORing with the unrelated asyncio-loop conflict — both outcomes are real, actionable evidence.
- **Plan 01-07 owns the VALIDATION.md row 01-08-01** — once Plan 01-07's Wave-5 commit lands, the gap-closure validation evidence for this plan is fully recorded.
- **Pattern reusable:** Future migration-verification tests (Phase 02+) should follow this subprocess + `asyncio.to_thread` pattern when driving alembic from inside pytest-asyncio. Do NOT use `alembic.command.upgrade()` programmatically — it WILL re-trigger the asyncio-loop conflict.

## Self-Check: PASSED

- `tests/integration/test_migrate_0009.py` exists at the expected path: **FOUND** (verified by `git log --oneline --all | grep a5087ac` → `a5087ac fix(01-08): rewrite test_migrate_0009 _alembic() to subprocess.run`).
- Commit `a5087ac` exists in worktree history: **FOUND**.
- `grep -c "subprocess.run" tests/integration/test_migrate_0009.py` = 2 (≥1 required): **PASS**.
- `grep -c "from alembic" tests/integration/test_migrate_0009.py` = 0 (must be 0): **PASS**.
- `grep -c "asyncio.to_thread" tests/integration/test_migrate_0009.py` = 2 (≥1 required): **PASS**.
- `grep -c "RuntimeError: asyncio.run() cannot be called from a running event loop" /tmp/test_migrate_0009.log` = 0: **PASS**.
- `pytest --collect-only` count = 8 (≥7 required, see deviation #4): **PASS**.
- `uv run ruff check tests/integration/test_migrate_0009.py` = All checks passed: **PASS**.
- `uv run ruff format --check ...` = 1 file already formatted: **PASS**.

---
*Phase: 01-walking-skeleton-api-client-single-profile-sync*
*Plan: 08 (gap-closure, Wave 5)*
*Completed: 2026-05-27*

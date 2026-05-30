---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 00
subsystem: testing
tags: [wave-zero, scaffolding, fixtures, test-harness, fake-discogsography, synthetic-data]

# Dependency graph
requires:
  - phase: 00-discovery
    provides: "Phase 1 plan, research, validation, patterns artifacts"
provides:
  - "11 test-package __init__.py markers (tests/fixtures/{,discogsography/,sync/,cli/,legacy/}, tests/unit/discogsography/, tests/integration/{sync/,cli/,db/,api/}, src/gruvax/_internal/)"
  - "Canonical fake-discogsography SHELL module at src/gruvax/_internal/fake_discogsography.py (D-15 single-module)"
  - "Thin re-export shim at tests/fixtures/fake_discogsography.py (backward-compat test imports)"
  - "Single canonical synthetic-data generator at tests/fixtures/generate_synth_data.py (deterministic seed=42, 3000 rows, emits YAML + SQL from one source)"
  - "Pre-moved legacy v1.0 seed at tests/fixtures/legacy/synth_collection.sql (resolves Plan 01 ↔ Plan 06 cross-wave path collision)"
  - "Scaffold + generator-populated tests/fixtures/synth_profile_collection.sql (3000 INSERTs targeting gruvax.profile_collection)"
  - "Committed services/fake-discogsography/seed.yaml (3000-release canonical seed for Plan 05 sibling service)"
  - "tests/conftest.py fixtures: default_profile_uuid, fake_discogsography_app, fake_discogsography_client"
  - "justfile `regen-synth-data` recipe + updated `seed-dev` path"
  - "tests/fixtures/test_generator_consistency.py (4 regression tests: row-count equality, determinism, shape-variety, shim identity)"
affects: [01-01, 01-02, 01-03, 01-04, 01-05, 01-06]

# Tech tracking
tech-stack:
  added: [pyyaml (already present, now used by generator)]
  patterns:
    - "Single-source-of-truth for fake-discogsography (D-15): one module imported by both test code and Compose sibling service — no `just sync-fake` drift guard needed"
    - "Single-source-of-truth for synthetic data (D-17): one generator emits YAML (Plan 05) AND SQL (Plan 06) from the same in-memory list — row-count equality enforced by regression test"
    - "Wave-0 scaffolding gate (Nyquist): wave_0_complete: true flips before any Wave 1 plan runs"

key-files:
  created:
    - "src/gruvax/_internal/__init__.py"
    - "src/gruvax/_internal/fake_discogsography.py (canonical SHELL — Plan 02 Task 2 fleshes out routes)"
    - "tests/fixtures/__init__.py"
    - "tests/fixtures/discogsography/__init__.py"
    - "tests/fixtures/sync/__init__.py"
    - "tests/fixtures/cli/__init__.py"
    - "tests/fixtures/legacy/__init__.py"
    - "tests/fixtures/legacy/synth_collection.sql (renamed from fixtures/synth_collection.sql; byte-identical)"
    - "tests/fixtures/fake_discogsography.py (thin re-export)"
    - "tests/fixtures/generate_synth_data.py (single canonical generator)"
    - "tests/fixtures/synth_profile_collection.sql (scaffold + generator-populated, 3000 INSERTs)"
    - "tests/fixtures/test_generator_consistency.py (4 regression tests)"
    - "tests/unit/discogsography/__init__.py"
    - "tests/integration/sync/__init__.py"
    - "tests/integration/cli/__init__.py"
    - "tests/integration/db/__init__.py"
    - "tests/integration/api/__init__.py"
    - "services/fake-discogsography/seed.yaml (committed canonical seed, 3000 releases)"
  modified:
    - "tests/conftest.py (adds default_profile_uuid, fake_discogsography_app, fake_discogsography_client fixtures)"
    - "justfile (adds regen-synth-data recipe; fixes seed-dev path to tests/fixtures/legacy/)"
    - ".planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-VALIDATION.md (flips 01-00-* rows to ✅ green)"

key-decisions:
  - "D-15 single-module fake-discogsography lives at src/gruvax/_internal/ (internal package marker disclaims public API). Plan 02 Task 2 fleshes routes; Plan 05 Task 3 imports same module for Compose sibling."
  - "D-17 single-generator emits YAML + SQL from one in-memory list. Regression test test_yaml_and_sql_row_count_agree enforces row-count equality on every CI run (T-00-fixture-drift mitigation)."
  - "Pre-move legacy seed to tests/fixtures/legacy/ in Wave 0 (was scheduled for Plan 06) so Plan 01-01 Task 2's downgrade test reference and Plan 06's later move do not collide (T-00-legacy-collision mitigation)."
  - "Generator is a Wave-0-committed SQL file (3000 INSERTs), not generated on-the-fly during CI, so SLO/integration tests can seed gruvax.profile_collection via `psql -f` without invoking the generator."

patterns-established:
  - "Single canonical module rule: when two consumers need the same artifact, put it in ONE module and have both import directly — avoids sync-guards entirely."
  - "Single canonical generator rule: when two outputs must agree (YAML seed + SQL seed), one function call → both emitters consume the same list → regression test asserts equality."
  - "Wave-0 scaffolding gate rule: every test-package __init__.py + cross-wave shared artifact lands BEFORE any implementation plan runs, so Wave 1+ plans never scavenger-hunt for shared imports."

requirements-completed: [API-01, API-02, API-03, PROF-03, SYN-02]

# Metrics
duration: 18 min
completed: 2026-05-26
---

# Phase 01 Plan 00: Wave 0 Scaffolding Gate Summary

**Canonical fake-discogsography SHELL module + single synthetic-data generator (YAML + SQL from one source) + test-package scaffolding + pre-moved legacy seed — Wave 0 gate flipped before any Wave 1 plan runs.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-27T02:48:00Z
- **Completed:** 2026-05-27T03:06:00Z
- **Tasks:** 3
- **Files modified:** 17 created, 3 modified (1 of which was a rename)

## Accomplishments

- Established the D-15 single-source-of-truth for the fake-discogsography app — `src/gruvax/_internal/fake_discogsography.py` is the canonical SHELL; both test code (via the `tests/fixtures/fake_discogsography.py` shim) and Plan 05's Compose sibling service will import from the same module. No `just sync-fake` drift guard is needed.
- Established the D-17 single-source-of-truth for the synthetic dataset — `tests/fixtures/generate_synth_data.py` emits BOTH the YAML seed (consumed by Plan 05 `services/fake-discogsography/seed.yaml`) AND the SQL fixture (consumed by Plan 06 `tests/fixtures/synth_profile_collection.sql`) from one deterministic in-memory list (seed=42, 3000 rows). The regression test `test_yaml_and_sql_row_count_agree` enforces row-count equality on every CI run, mitigating the T-00-fixture-drift threat by construction.
- Pre-moved the legacy v1.0 seed from `fixtures/synth_collection.sql` to `tests/fixtures/legacy/synth_collection.sql` (byte-identical; git detected 100% rename) — resolves the T-00-legacy-collision threat (Plan 01-01 Task 2's downgrade-test reference and Plan 06's later move would otherwise both touch the file).
- Landed all 11 test-package `__init__.py` markers and the 4 conftest fixtures Wave 1 plans depend on — Plans 01-01 (Wave 1, migration + settings) and 01-02 (Wave 1, primitives + fake) BOTH `depends_on: [01-00]` so the test scaffolding is in place BEFORE either runs.
- Materialized the committed `services/fake-discogsography/seed.yaml` (3000 releases) and populated `tests/fixtures/synth_profile_collection.sql` with 3000 INSERTs via `just regen-synth-data`. Plan 05 Task 3 will surround the YAML with a Dockerfile + server.py; Plan 06 Task 1 re-runs `just regen-synth-data` as a final post-rewire sweep.
- Flipped `VALIDATION.md` `wave_0_complete: true` (was already set during planning revision) and marked both 01-00-* Per-Task Verification Map rows as `✅ green`.

## Task Commits

1. **Task 1: package markers + legacy seed move + SQL fixture scaffold** — `545fb45` (feat)
2. **Task 2: canonical fake-discogsography shell + single synthetic-data generator** — `5455457` (feat)
3. **Task 3: mark Wave 0 tasks green in VALIDATION.md** — `57c539a` (docs)

**Plan metadata:** _committed in this SUMMARY commit_

## Files Created/Modified

### Created (17)

- `src/gruvax/_internal/__init__.py` — internal-package marker (disclaims public API)
- `src/gruvax/_internal/fake_discogsography.py` — canonical fake-discogsography SHELL (no routes mounted; Plan 02 Task 2 fleshes out)
- `tests/fixtures/__init__.py` — shared-fixtures package marker
- `tests/fixtures/discogsography/__init__.py` — discogsography-client-fixture marker
- `tests/fixtures/sync/__init__.py` — sync-routine-fixture marker
- `tests/fixtures/cli/__init__.py` — CLI-fixture marker
- `tests/fixtures/legacy/__init__.py` — retired-v1.0-fixtures marker
- `tests/fixtures/legacy/synth_collection.sql` — pre-moved from `fixtures/synth_collection.sql` (byte-identical, git rename detected at 100%)
- `tests/fixtures/fake_discogsography.py` — thin re-export of canonical module (backward-compat test imports)
- `tests/fixtures/generate_synth_data.py` — single canonical synthetic-data generator (YAML + SQL emitters; deterministic seed=42; 3000 rows)
- `tests/fixtures/synth_profile_collection.sql` — scaffold + generator-populated (3000 INSERTs into `gruvax.profile_collection`)
- `tests/fixtures/test_generator_consistency.py` — 4 regression tests: row-count equality, determinism, shape-variety contract, shim identity
- `tests/unit/discogsography/__init__.py` — unit-test package marker for DiscogsographyClient + Fernet + log-redactor specs (Plan 02 will populate)
- `tests/integration/sync/__init__.py` — integration test package marker for `sync_profile` (Plan 03 will populate)
- `tests/integration/cli/__init__.py` — integration test package marker for the two new CLIs (Plan 04 will populate)
- `tests/integration/db/__init__.py` — integration test package marker for DB query rewires (Plan 06 will populate)
- `tests/integration/api/__init__.py` — integration test package marker for admin endpoints (Plan 04/05 will populate)
- `services/fake-discogsography/seed.yaml` — committed canonical seed (3000 releases); Plan 05 Task 3 adds the surrounding Dockerfile + server.py

### Modified (3)

- `tests/conftest.py` — appends `default_profile_uuid` fixture (returns the D-02 single-profile UUID constant), `fake_discogsography_app` fixture (returns `create_fake_app(seed=[])`), and `fake_discogsography_client` fixture (yields `httpx.AsyncClient(transport=ASGITransport(app=fake_discogsography_app))`).
- `justfile` — adds `regen-synth-data` recipe; updates `seed-dev` path from `fixtures/synth_collection.sql` to `tests/fixtures/legacy/synth_collection.sql` per the Task 1 pre-move (deviation Rule 3).
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-VALIDATION.md` — flips Per-Task Verification Map rows 01-00-01 and 01-00-02 Status from `⬜ pending` to `✅ green`.

### Renamed (git-detected, 100% similarity)

- `fixtures/synth_collection.sql` → `tests/fixtures/legacy/synth_collection.sql`

## Decisions Made

- **`# noqa: S311` on `random.Random(seed)`** in the generator — this is a deterministic test fixture, not cryptographic randomness. The whole point is byte-for-byte reproducibility across runs, which is the opposite of what `secrets`-grade randomness would provide.
- **`# noqa: S608` on the SQL-string-construction loop** in `emit_sql` — values come from `generate_releases` (deterministic, synthesized, no untrusted input); string values are quoted via `q()` which doubles embedded single quotes per SQL convention; output is a committed test fixture, never executed against a live DB with attacker-controllable input.
- **Committed `services/fake-discogsography/seed.yaml` to git** (616 KB) — the generator is deterministic so the YAML is reproducible, but committing it means Plan 05 Task 3 can land the Compose sibling without depending on an Operator-runs-the-generator step on first boot. Trade-off accepted per the plan's explicit guidance ("services/fake-discogsography/ directory does NOT exist in Wave 0… The committed seed.yaml is OK to land in Wave 0").
- **Updated `just seed-dev` path** as part of Task 2 even though the plan didn't explicitly call for it — Task 1's pre-move broke the `seed-dev` recipe's `psql … < fixtures/synth_collection.sql` reference. Treated as Rule 3 (blocking issue auto-fix).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated `just seed-dev` path to reflect the legacy seed move**

- **Found during:** Task 2 (justfile edit)
- **Issue:** The `seed-dev` recipe references `fixtures/synth_collection.sql`. Task 1 deleted that file (it moved to `tests/fixtures/legacy/synth_collection.sql`), so `just seed-dev` would have failed with `No such file or directory` for any developer setting up the dev DB.
- **Fix:** Updated the recipe to read from `tests/fixtures/legacy/synth_collection.sql` and added a comment noting the v1.0 location moved post-Plan-01-00.
- **Files modified:** `justfile`
- **Verification:** Visual review of the updated recipe; full `seed-dev` flow is gated on a running `gruvax-dev-pg` container so not exercisable in CI here.
- **Commit:** `5455457` (folded into the Task 2 commit since the path change is logically paired with the seed-move it depends on).

**2. [Rule 1 - Bug] Generic-type annotation on `seed: list[dict]`**

- **Found during:** Task 2 (mypy strict run)
- **Issue:** `mypy --strict src/gruvax/_internal/` flagged `seed: list[dict]` as `Missing type arguments for generic type "dict"`.
- **Fix:** Changed signature to `seed: list[dict[str, Any]]` (with `from typing import Any` import).
- **Files modified:** `src/gruvax/_internal/fake_discogsography.py`
- **Verification:** `uv run mypy --strict src/gruvax/_internal/` returns "Success: no issues found in 2 source files".
- **Commit:** `5455457` (Task 2 commit).

**3. [Rule 3 - Blocking] Ruff `# noqa: S311` + `# noqa: S608` on fixture generator**

- **Found during:** Task 2 (ruff check)
- **Issue:** Default ruff config raises S311 on `random.Random(seed)` and S608 on string-construction of `INSERT INTO …` SQL.
- **Fix:** Added narrow `# noqa: S311` and `# noqa: S608` with multi-line rationale comments explaining (a) this is a deterministic test fixture not cryptographic randomness, and (b) values come from `generate_releases` (deterministic, synthesized, no untrusted input) with `q()` quoting and the output is a committed test fixture.
- **Files modified:** `tests/fixtures/generate_synth_data.py`
- **Verification:** `uv run ruff check` returns "All checks passed!".
- **Commit:** `5455457` (Task 2 commit).

---

**Total deviations:** 3 auto-fixed (2 Rule 3 blocking, 1 Rule 1 bug)
**Impact on plan:** All three auto-fixes were necessary for the plan's verification commands to succeed. No scope creep — every fix was on a file already touched by the plan.

## Issues Encountered

- **`pytest --collect-only` requires `DATABASE_URL` and `SESSION_SECRET` env vars.** Pre-existing constraint of `src/gruvax/settings.py` (`SESSION_SECRET` / `DATABASE_URL` are no-default boot-fail fields). The plan's verification commands implicitly assume these are set; in CI they will be (via `.env` / GHA secrets), and in the worktree I set them to placeholder values for the verification round. Not a blocker — flagged here so Wave 1 plans don't trip on the same.

## Authentication Gates

None — no external services were called during this plan.

## Known Stubs

The canonical `create_fake_app(seed=[…])` is intentionally a SHELL with no routes mounted. This is **NOT** a leak-stub — it is the explicit Wave 0 deliverable per the plan's `<behavior>` section ("Plan 02 Task 2 adds the contract routes"). The shell exists so Wave 1 import paths resolve and so the single-source-of-truth contract (D-15) is locked from this plan forward.

`tests/fixtures/synth_profile_collection.sql` was Task-1-scaffolded with 0 rows and Task-2-populated with 3000 rows. Plan 06 Task 1 will regenerate as a final post-rewire sweep. Both states are expected and load-bearing for the dependent plans.

## Threat Flags

None — Plan 01-00 ships only test-harness scaffolding and a deterministic generator. No new application network endpoints, no new auth paths, no new schema changes at trust boundaries. The `<threat_model>` register's `T-00-fixture-drift`, `T-00-fake-module-drift`, and `T-00-legacy-collision` threats are all directly mitigated by the artifacts shipped in this plan (see Decisions Made).

## User Setup Required

None — this plan ships test-harness scaffolding only. No environment variables to add, no dashboard configuration, no external services to connect.

## Next Phase Readiness

- **Wave 1 (Plans 01-01 + 01-02) is unblocked.** Both `depends_on: [01-00]`; the test-package markers, conftest fixtures, canonical fake module, and legacy seed are all in their final paths.
- **VALIDATION.md `wave_0_complete: true`** is set, so the Nyquist Wave-0 gate has passed.
- **Plan 02 Task 2 will replace the SHELL.** The canonical `create_fake_app(seed=[…])` shell will gain the `/api/user/collection` route with pagination, token routing, and magic-token error injection. The `seed` and `user_id` parameters are already wired through `app.state` so route bodies can read them.
- **Plan 05 Task 3 will surround `services/fake-discogsography/seed.yaml`** with a Dockerfile + `server.py` that imports `create_fake_app` from `gruvax._internal.fake_discogsography` and loads the seed YAML.
- **Plan 06 Task 1 will re-run `just regen-synth-data`** as a final post-rewire sweep against the migrated `gruvax.profile_collection` schema.

## Self-Check: PASSED

- `[ -f tests/fixtures/legacy/synth_collection.sql ]` → FOUND
- `[ ! -f fixtures/synth_collection.sql ]` → DELETED (as required)
- `[ -f src/gruvax/_internal/fake_discogsography.py ]` → FOUND
- `[ -f tests/fixtures/generate_synth_data.py ]` → FOUND
- `[ -f tests/fixtures/test_generator_consistency.py ]` → FOUND
- `[ -f tests/fixtures/synth_profile_collection.sql ]` → FOUND (3000 INSERTs)
- `[ -f services/fake-discogsography/seed.yaml ]` → FOUND (3000 releases)
- All 11 `__init__.py` package markers → FOUND
- `git log --grep "feat(01-00)"` → returns 2 commits (`545fb45`, `5455457`)
- `git log --grep "docs(01-00)"` → returns 1 commit (`57c539a`)
- `grep -q "wave_0_complete: true" .planning/phases/01-…/01-VALIDATION.md` → MATCH
- `uv run pytest tests/fixtures/test_generator_consistency.py -x -q` → 4 passed
- `uv run pytest --collect-only` → 473 tests collected, no ImportError
- `uv run ruff check` on new files → All checks passed
- `uv run ruff format --check` on new files → 6 files already formatted
- `uv run mypy --strict src/gruvax/_internal/` → Success: no issues found

---
*Phase: 01-walking-skeleton-api-client-single-profile-sync*
*Completed: 2026-05-26*

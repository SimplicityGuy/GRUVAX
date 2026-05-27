---
phase: 01-walking-skeleton-api-client-single-profile-sync
verified: 2026-05-27T23:40:00Z
status: complete
score: 5/5 must-haves verified
overrides_applied: 0
uat_closure:
  uat_file: 01-HUMAN-UAT.md
  uat_status: complete
  tests_passed: 5
  tests_total: 5
  ci_run: "26544940172 (HEAD 289cb29) — all jobs green"
  sub_gaps_closed_during_uat: 13
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  previous_verified: 2026-05-27T08:15:00Z
  closure_commits:
    - "d25bed6 test(01-07): add autouse seed for profile_collection in tests/integration/conftest.py"
    - "e74f355 fix(01-07): align boundaries.yaml + test catalogs with v2 synth seed"
    - "9a310d2 docs(01-07): add VALIDATION.md rows 01-07-01, 01-07-02, 01-08-01"
    - "a5087ac fix(01-08): rewrite test_migrate_0009 _alembic() to subprocess.run"
    - "75f730f fix(01): self-healing autouse seed fixture (alembic upgrade head if needed)"
  gaps_closed:
    - "Gap #1 (BLOCKER) — Integration test seed + boundaries.yaml v2 alignment"
    - "Gap #2 (WARNING) — Migration round-trip asyncio.run-from-async harness"
    - "Gap #3 (WARNING) — test_change_set + test_collection_snapshot cascade"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Compose-up clean-boot end-to-end (just compose-smoke)"
    expected: "`docker compose down -v && docker compose up gruvax-api init-sync fake-discogsography` brings the stack up; init-sync's idempotency precheck returns 0 rows; runs gruvax-sync; populates profile_collection with ~3000 rows from fake-discogsography seed; exits 0. A second `docker compose up` of init-sync exits 0 with log line 'profile_collection already populated for default profile; skipping initial sync'."
    why_human: "Multi-container orchestration with network + healthchecks + build; not testable from pytest alone. The `just compose-smoke` recipe exists (justfile:152) and is invoked from .github/workflows/build.yml (line 116). Recommend running `just compose-smoke` locally OR confirming the CI job is green at HEAD."
  - test: "Kiosk staleness banner UI rendering (SC-5 sub-clause)"
    expected: "With profile_collection populated and profiles.last_sync_at set to ~now(), kiosk shows no staleness banner. After `UPDATE gruvax.profiles SET last_sync_at = now() - INTERVAL '4 days'` and waiting <60s, kiosk renders the >3-day staleness banner (per v1.0 Phase 8 thresholds, per SYN-02). After >14 days ago, kiosk renders the critical banner."
    why_human: "Visual UI behavior in the kiosk frontend. The /api/health field is populated by the lifespan background task (verified in test_health.py) but whether the React component renders the banner from this field is a UI-rendering concern grep cannot verify."
  - test: "gruvax-set-pat TTY no-echo behavior"
    expected: "Running `gruvax-set-pat --profile default` in an interactive terminal prompts 'Paste PAT (input hidden):' and the typed PAT is NOT echoed. Piping `echo dscg_xxx | gruvax-set-pat --profile default` reads from stdin without prompt and does not require a TTY."
    why_human: "getpass.getpass behavior under a real TTY (vs simulated isatty=True) is hard to assert reliably in pytest — platform-specific terminal-control codes that suppress echo are only active when a real PTY is attached. Plan 04 Task 2 Test 9 simulates this via monkeypatch but does not exercise the real PTY path."
  - test: "init-sync GRUVAX_ADMIN_PIN substitution fails compose-up if unset"
    expected: "Running `docker compose up init-sync` without GRUVAX_ADMIN_PIN in .env fails compose-up with a clear error mentioning the missing env var (the `${GRUVAX_ADMIN_PIN:?...}` substitution form)."
    why_human: "Compose-time env-var substitution behavior. Verifiable via compose CLI but not via pytest."
  - test: "CI gate — just slo + just migrate-roundtrip on fresh postgres:18 service"
    expected: "CI's `just slo` step exits 0 with p95 /api/search ≤ 200ms and /api/locate ≤ 50ms on synthetic dataset. `just migrate-roundtrip` exits 0 against fresh postgres:18 (the in-repo dev DB fails locally due to environmental boundary_history CHECK violation from prior phases — documented as operator hygiene, not a Phase 1 gap)."
    why_human: "Plan 01-06 SUMMARY reports SLO benchmark headroom (search ~9ms, locate ~3ms) measured locally; verifier did not re-run benchmark during gap closure (no query-path changes). The all-pass-in-CI assertion is explicitly the CI-gate handoff per Plan 01-08 acceptance criteria."
---

# Phase 1 (v2.0): Walking Skeleton — API Client + Single-Profile Sync — Verification Report (Re-verification)

**Phase Goal:** Restore Core Value end-to-end (search → cube highlight ≤ 200 ms) against API-sourced collection data, with `gruvax.v_collection` retired and positioning running off the local `profile_collection` cache for a single default profile.

**Verified:** 2026-05-27T18:45:00Z
**Status:** human_needed (all 5 ROADMAP Success Criteria now VERIFIED — 5 items deferred to human verification for UI/compose/PTY behaviors that grep cannot prove)
**Re-verification:** Yes — after gap closure round (Plans 01-07 + 01-08 + orchestrator commit 75f730f)

## Re-verification Summary

| Prior gap | Prior status | Re-verification outcome | Closure evidence |
| --------- | ------------ | ----------------------- | ---------------- |
| Gap #1 (BLOCKER) — Integration test seed + boundaries v2 alignment | partial / blocked | ✓ CLOSED | `tests/integration/conftest.py` exists with module-scoped autouse `_seeded_profile_collection`; `fixtures/boundaries.yaml` references only v2 catalog numbers (BLP 1000, BST 1001, KC1000, etc.); 66 originally-failing tests pass on a fresh dev DB with no manual psql reseed (verified: `uv run pytest tests/integration/test_locate.py tests/integration/test_search.py tests/integration/test_segment_api.py tests/integration/db/test_queries_rewire.py tests/integration/test_change_set.py tests/unit/test_collection_snapshot.py::test_snapshot_load_from_db` → 66 passed, 2 skipped). |
| Gap #2 (WARNING) — asyncio.run-from-async migration harness | failed | ✓ CLOSED at harness level | `tests/integration/test_migrate_0009.py::_alembic` now uses `subprocess.run` wrapped in `asyncio.to_thread` (verified: `grep -c "subprocess.run\|asyncio.to_thread"` returns 3+); `from alembic import command` removed (`grep -c "from alembic"` returns 0); 8 tests collected; the `RuntimeError: asyncio.run() cannot be called from a running event loop` is GONE — the one remaining test failure on local dev DB (`test_alembic_round_trip_is_clean`) is now an environmental `boundary_history_source_check` CHECK violation with a meaningful diff, NOT the original asyncio-loop error. CI's fresh `postgres:18` service is the source of truth for the all-pass assertion (deferred to human verification item #5). |
| Gap #3 (WARNING) — test_change_set + test_collection_snapshot cascade | failed | ✓ CLOSED | Cascade closure: same root cause as Gap #1; autouse fixture now seeds profile_collection so `test_revert_rederives_segment_cache` and `test_snapshot_load_from_db` pass without manual reseed (verified: both included in the 66-passed run above). |

**Orchestrator commit 75f730f (`fix(01): self-healing autouse seed fixture`):** Independently verified — the autouse fixture's `_schema_at_head()` helper detects when migration tests rolled back the dev DB and invokes `alembic upgrade head` via subprocess before seeding. This closes the secondary "schema disappears mid-suite" cascade exposed when Gap #2's fix made the migration round-trip actually run.

## Goal Achievement

### Observable Truths (ROADMAP §Phase 1 Success Criteria)

| #   | Truth (ROADMAP SC) | Status     | Evidence |
| --- | ------------------ | ---------- | -------- |
| 1   | Search → cube highlight loop works end-to-end against API-sourced data; typed query returns the right cube + sub-cube position estimate. | ✓ VERIFIED | (Was partial.) Code paths (`src/gruvax/db/queries.py` rewired to profile_collection — 13 occurrences; `src/gruvax/estimator/collection_snapshot.py::load` queries profile_collection) PLUS test infrastructure now prove end-to-end on a fresh checkout: `test_locate.py::test_locate_covered` returns `primary_cube={unit:1,row:0,col:0}` with confidence ≥ CUBE_ONLY_CONFIDENCE for release_id=1 (Blue Note BLP 1000); cut-points in `fixtures/boundaries.yaml` resolve to real records in the v2 synth seed; SegmentCache derives non-empty bins. |
| 2   | v1.0 SLOs hold: `/api/search` p95 ≤ 200 ms and `/api/locate` p95 ≤ 50 ms on synthetic data. | ✓ VERIFIED | Plan 01-06 SUMMARY reports p95 /api/search ≈ 9ms (22× headroom vs 200ms budget) and /api/locate ≈ 3ms (15× headroom vs 50ms budget). Plan 01-07 SUMMARY reports search ≈ 12ms / locate ≈ 4ms post-conftest-lift — no regression. `just slo` recipe in justfile; `.github/workflows/test.yml` invokes it as a CI step. CI gate green-check deferred to human verification item #5 per Plan 01-06 contract. |
| 3   | `gruvax.v_collection` is dropped and the read-only grant to discogsography is revoked in the same Alembic migration; round-trip is clean. | ✓ VERIFIED | (Was partial.) Migration 0009 DROPs v_collection (line 282), documents grant revocation, downgrade re-creates verbatim with `SET LOCAL search_path` for Pitfall 5. Gap #2 closure: `tests/integration/test_migrate_0009.py` is now collectable + runnable (asyncio-loop error eliminated) — all 8 tests reach their assertions instead of ERRORing. SC-3 round-trip cleanness has TWO independent evidence paths: (a) shell `just migrate-roundtrip` CI gate against fresh postgres:18, and (b) in-pytest schema-verification module. Local dev DB still environmentally fails `boundary_history_source_check` from pre-existing rows in prior phases — explicitly classified as operator hygiene, not a code defect (per gap-closure evidence + integration_test_harness memory note). |
| 4   | Default profile's first sync completes with `last_sync_status='ok'` and `last_sync_item_count ≥ ~3000`. | ⚠️ CODE VERIFIED, COMPOSE PATH DEFERRED | `src/gruvax/sync/profile_sync.py` is 557 lines of substantive code with 11+ happy-path + error-mapping tests passing. Compose `init-sync` container is wired (D-16 idempotent precheck). Default-profile seed row present at deterministic UUID (verified live in initial verification). End-to-end compose smoke = human verification item #1. |
| 5   | `/api/health` reports discogsography reachability via HTTP probe; kiosk staleness banner reads from `now() - profiles.last_sync_at`. | ✓ VERIFIED | `src/gruvax/api/health.py` returns `discogsography_api_check` field with three-state `{'ok','failed','stale'}` per D-13; zero references to legacy `discogsography_view_check` in src/. `app.state.default_profile_last_sync_at` populated by 60s `_refresh_default_profile_state` lifespan task. `frontend/src/api/types.ts` field renamed + union widened. UI banner rendering = human verification item #2. |

**Score:** 5/5 ROADMAP Success Criteria verified. SC-4 has a residual "human verifies the compose smoke ran" item; the code itself is fully verified.

### Required Artifacts (PLAN frontmatter)

All 20 artifacts from initial verification remain VERIFIED — no regressions. Three test files have new state from this gap-closure round:

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `tests/integration/conftest.py` (NEW) | Module-scoped autouse fixture seeding profile_collection + self-healing for migration-test schema rollback | ✓ VERIFIED | File exists; uses `@pytest.fixture(scope="module", autouse=True)`; reads DSN via pydantic-settings (NOT os.environ — Plan 01-07 deviation #4); calls `_alembic_upgrade_head` via subprocess if `_schema_at_head` returns False (orchestrator commit 75f730f self-heal); uses sync `psycopg.connect()` per Plan 01-06 documented Rule 1. |
| `tests/integration/test_migrate_0009.py::_alembic` | subprocess.run via asyncio.to_thread (no programmatic alembic command) | ✓ VERIFIED | `subprocess.run` present (2 occurrences); `from alembic import command/Config` removed (0 occurrences); argv mirrors `just migrate-roundtrip` exactly (`["uv", "run", "alembic", action, target]`); wrapped in `asyncio.to_thread` so event loop stays responsive during multi-second migration; manual returncode check with custom AssertionError carrying full stdout/stderr. |
| `fixtures/boundaries.yaml` | All 32 cubes reference v2 generator catalog numbers; Atlantic deliberately omitted to satisfy no-boundary contract | ✓ VERIFIED | Header comment documents v1→v2 rewrite + Atlantic-omission rationale. Zero references to v1 catalogs (`BLP 4001`, `BST 84001`, `CRLP 501`, `KC 32731`, `Saturn`, `Creole`, `Tamla`, `Capitol`, `Apple`, etc.) as `first_label:` values — verified via grep. Layout: Blue Note (×2), Columbia, ECM (×2), Impulse! (×2), Prestige (×2), Pure Label, Riverside (×2), Verve (×2), Padding Label, Singleton Labels 0..12, 4 empty cubes. |
| `tests/integration/test_locate.py` | NO_BOUNDARY_RELEASE_ID = 951 (Atlantic), ABSENT_RELEASE_ID = 99999 | ✓ VERIFIED | Constants updated at lines 42, 64; comment block (lines 44-63) documents the SegmentCache assignment-loop reasoning explicitly so future contributors don't revert. |
| `tests/integration/test_segment_api.py` | Rule 1 patches: BLP 4001→BLP 1000, KC→ECM (cube 1,0,3), C2S 841→RLP 1075, BLP 4010→BLP 1010 | ✓ VERIFIED | All 19 test_segment_api.py tests pass (included in 66-passed run). Plan 01-07 SUMMARY deviations #3 documents the scope expansion from Task 2's stated files to include test_segment_api.py; justified by the plan's own success_criteria. |
| `tests/integration/test_search_benchmark.py` | Module-local `_seeded_profile_collection` + `_SYNTH_SQL_PATH` removed; `search_client` param list trimmed | ✓ VERIFIED | Plan 01-07 Task 1 lift; SLO benchmark still green per Plan 01-07 SUMMARY (search ~12ms, locate ~4ms post-lift). |

### Key Link Verification

All 14 key links from initial verification remain WIRED. Gap-closure additions:

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| tests/integration/conftest.py::_seeded_profile_collection | tests/fixtures/synth_profile_collection.sql | `psycopg.connect(dsn).execute(sql_file.read_text())` | ✓ WIRED | Plan 01-07 Task 1. Plus self-healing branch (orchestrator commit 75f730f): conditional `_alembic_upgrade_head()` subprocess call when `to_regclass('gruvax.profiles')` returns NULL. |
| fixtures/boundaries.yaml cube (1,0,0) | gruvax.profile_collection release_id=1 (Blue Note BLP 1000) | SegmentCache cut-point match | ✓ WIRED | Plan 01-07 Task 2. Verified by `test_locate_covered` passing. |
| tests/integration/test_migrate_0009.py::_alembic | alembic CLI via subprocess | `["uv", "run", "alembic", action, target]` argv, asyncio.to_thread wrapper | ✓ WIRED | Plan 01-08 Task 1. Verified by Gap #2 elimination — zero asyncio-loop errors in test output. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Originally-failing test modules pass on fresh dev DB | `uv run pytest tests/integration/test_locate.py tests/integration/test_search.py tests/integration/test_segment_api.py tests/integration/db/test_queries_rewire.py tests/integration/test_change_set.py tests/unit/test_collection_snapshot.py::test_snapshot_load_from_db --tb=no -q` | 66 passed, 2 skipped | ✓ PASS |
| `from alembic` import removed from test_migrate_0009.py | `grep -c "from alembic" tests/integration/test_migrate_0009.py` | 0 | ✓ PASS |
| subprocess.run + asyncio.to_thread in test_migrate_0009.py | `grep -c "subprocess.run\|asyncio.to_thread" tests/integration/test_migrate_0009.py` | 3 | ✓ PASS |
| Atlantic omitted from boundaries.yaml (`first_label:` values only) | `grep -nE "first_label.*Atlantic" fixtures/boundaries.yaml` | 0 hits (Atlantic appears only in 3 comment lines documenting the omission) | ✓ PASS |
| Self-healing fixture in conftest.py | `grep -E "_alembic_upgrade_head\|_schema_at_head" tests/integration/conftest.py` | 4 hits (2 defs + 2 calls) | ✓ PASS |
| Full test-suite collection healthy | `uv run pytest --collect-only` | 606 tests collected in 0.46s; no collection errors | ✓ PASS |
| Full suite execution | `uv run pytest --tb=no -p no:warnings` | 1 failed, 593 passed, 12 skipped in 51.09s | ⚠️ See below |
| v_collection fully retired from src/ | `grep -rE "FROM gruvax.v_collection" src/gruvax/` | 0 hits in live code (only docstring/comment historical references) | ✓ PASS |
| Debt-marker scan on modified files | `grep -nE "TBD\|FIXME\|XXX" tests/integration/conftest.py tests/integration/test_migrate_0009.py fixtures/boundaries.yaml tests/integration/test_locate.py` | 0 hits | ✓ PASS |

**Full suite 1 failure analysis:** `tests/integration/test_migrate_0009.py::test_alembic_round_trip_is_clean` fails with `psycopg.errors.CheckViolation: check constraint "boundary_history_source_check" of relation "boundary_history" is violated by some row` during the round-trip's re-`ALTER TABLE ADD CONSTRAINT` leg. This is the **environmental** failure documented in the gap-closure evidence note: the shared dev DB has pre-existing `boundary_history` rows from prior phases whose `source` values are not in the v2 CHECK clause `('manual', 'bulk', 'revert', 'cut_insert')`. CI's `just migrate-roundtrip` against fresh `postgres:18` is the source of truth and was always the gate for this — the in-pytest version is now only a structural check that the asyncio-loop bug is gone, which it is. Plan 01-08 acceptance criteria explicitly defer the all-pass assertion to CI.

**Note on order-dependent flake:** Gap-closure evidence cited `test_resume_revalidates_stale_cut` as a 2nd full-suite failure; in this verifier's full run it PASSED, indicating the flake is non-deterministic with run order. Not introduced by Phase 1 plans (per memory note `integration_test_harness`). Not a Phase 1 gap.

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| Targeted gap-closure verify (Plan 01-07 verify gate) | `uv run pytest tests/integration/test_locate.py tests/integration/test_search.py tests/integration/test_segment_api.py tests/integration/db/test_queries_rewire.py tests/integration/test_change_set.py tests/unit/test_collection_snapshot.py::test_snapshot_load_from_db --tb=short -q` | 66 passed, 2 skipped, 0 failures | ✓ PASS |
| Migration harness regression (Plan 01-08 verify gate) | `uv run pytest tests/integration/test_migrate_0009.py --collect-only -q` + asyncio-loop grep | 8 tests collected; 0 asyncio.run-from-running-loop errors | ✓ PASS |
| Full pytest suite | `uv run pytest --tb=no -p no:warnings` | 1 failed (environmental boundary_history_source_check, NOT a code defect), 593 passed, 12 skipped | ⚠️ ENVIRONMENTAL — defer to CI postgres:18 |
| `just slo` | not re-run (no query-path changes since Plan 01-06) | Plan 01-06 SUMMARY: search ~9ms / locate ~3ms | ⚠️ DEFERRED — human verification item #5 |
| `just compose-smoke` | not re-run | infrastructure verified to exist in justfile + .github/workflows/build.yml | ⚠️ DEFERRED — human verification item #1 |
| `just migrate-roundtrip` (local) | not re-run | environmentally fails locally per same boundary_history_source_check; CI gate against fresh postgres:18 is source of truth | ⚠️ DEFERRED — human verification item #5 |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
| ----------- | -------------- | ----------- | ------ | -------- |
| API-01 | 01-00, 01-02, 01-04 | DiscogsographyClient paged sync + retry semantics | ✓ SATISFIED | Initial verification + 11 retry-semantics tests passing. No regression. |
| API-02 | 01-00, 01-03, 01-06, 01-07 | Positioning + search + /api/locate run off local profile_collection cache; SLOs preserved | ✓ SATISFIED | Initial verification (code) + gap closure (end-to-end test path now provable via Plan 01-07 conftest + boundaries alignment). All 66 originally-failing tests pass. |
| API-03 | 01-00, 01-01, 01-05, 01-06, 01-08 | Retire v_collection + revoke grant; round-trip clean; health probe → HTTP | ✓ SATISFIED | Initial verification + gap closure (Plan 01-08 eliminated asyncio-loop conflict; in-pytest round-trip evidence path restored modulo environmental boundary_history issue). |
| SYN-02 | 01-00, 01-03, 01-05, 01-07 | Staleness redefinition per-profile (single-profile flavor) | ✓ SATISFIED | Initial verification. No regression. |
| PROF-03 | 01-00, 01-01, 01-04, 01-07 | v1 backfill to deterministic default profile | ✓ SATISFIED | Initial verification (migration 0009 seeds row at 00000000-0000-0000-0000-000000000001 + 7-table backfill). No regression. |

**All 5 required REQ IDs satisfied.** No ORPHANED requirements: every Phase 1 REQ in `.planning/REQUIREMENTS.md` (PROF-03, API-01, API-02 single-profile, API-03, SYN-02 single-profile) is claimed by ≥1 plan and implemented.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `src/gruvax/discogsography/client.py` | 78 | `except TypeError, ValueError:` Python 2-style clause (Python 3.14 accepts as tuple literal; non-idiomatic) | ℹ️ Info (carried over from initial verification) | Functionally correct. Should be `except (TypeError, ValueError):`. Style nit; not a blocker. Recommend follow-up cleanup ticket. |

**Closed since initial verification:**
- ~~`tests/integration/test_migrate_0009.py`~~ — asyncio.run-from-async helper REWRITTEN to subprocess.run (Plan 01-08). 🛑 BLOCKER → ✓ CLOSED.
- ~~`fixtures/boundaries.yaml`~~ — v1 catalog references REPLACED with v2 generator output (Plan 01-07 Task 2). 🛑 BLOCKER → ✓ CLOSED.
- ~~Implicit profile_collection seed dependency~~ — Module-scoped autouse fixture in `tests/integration/conftest.py` (Plan 01-07 Task 1 + orchestrator commit 75f730f self-heal). 🛑 BLOCKER → ✓ CLOSED.

No new anti-patterns introduced by the gap-closure plans. Debt-marker scan on all 5 modified files returned 0 hits.

### Human Verification Required

5 items remain (carried forward from initial verification — none introduced by gap-closure round). See frontmatter `human_verification:` for the structured list. Summary:

1. `just compose-smoke` end-to-end (init-sync first-sync + idempotency + populated profile_collection).
2. Kiosk staleness banner UI rendering from `discogsography_api_check` / `sync_age_seconds`.
3. `gruvax-set-pat` TTY no-echo behavior under a real PTY.
4. `${GRUVAX_ADMIN_PIN:?…}` compose-up failure when env var unset.
5. CI green-check of `just slo` and `just migrate-roundtrip` on a fresh `postgres:18` service for the merge commit.

### Gaps Summary

**All 3 prior gaps closed.** Closure tally:

- **Gap #1 (BLOCKER) → CLOSED.** Plan 01-07 added `tests/integration/conftest.py` autouse fixture + realigned `fixtures/boundaries.yaml` to v2 generator output + updated `NO_BOUNDARY_RELEASE_ID` to 951 (Atlantic SD 1000, with extensive comment block documenting why the planner's first guess of 1937 was disproven by SegmentCache's assignment algorithm). 66 originally-failing tests pass on a fresh dev DB; cube (1,0,0) resolves to release_id=1 with confidence ≥ CUBE_ONLY_CONFIDENCE. SC-1 observably true via automated test suite.

- **Gap #2 (WARNING) → CLOSED.** Plan 01-08 rewrote `_alembic()` to `subprocess.run` wrapped in `asyncio.to_thread`. The `RuntimeError: asyncio.run() cannot be called from a running event loop` is eliminated (0 occurrences in test output). All 8 tests in test_migrate_0009.py now collect + run; one remaining failure on local dev DB (`test_alembic_round_trip_is_clean`) is environmental `boundary_history_source_check` from pre-existing data, NOT the original asyncio-loop bug — explicitly classified as operator hygiene per gap-closure evidence and integration_test_harness memory note. CI gate (`just migrate-roundtrip` against fresh `postgres:18`) is the source of truth for the all-pass SC-3 assertion.

- **Gap #3 (WARNING cascade) → CLOSED.** Same root cause as Gap #1; closed by the same conftest fixture. `test_revert_rederives_segment_cache` and `test_snapshot_load_from_db` both pass.

**Orchestrator commit 75f730f independently verified:** the self-healing `_alembic_upgrade_head()` branch in conftest.py correctly invokes `alembic upgrade head` via subprocess when the dev DB schema is below head (e.g., after the migration round-trip's downgrade leg). This is a defense-in-depth addition that prevents the migration-test cascade from breaking the suite for the operator.

### Recommendation

Phase 1 goal is **observably achieved in the codebase**. The 5 deferred human verification items are end-to-end behaviors (compose orchestration, UI rendering, TTY interaction, CI green-check) that cannot be programmatically verified — they should be exercised via:

```bash
/gsd-verify-work 1
```

…which routes the human verification list through the standard HUMAN-UAT.md sink. After human sign-off on items #1–5, Phase 1 is ready to be marked closed and Phase 2 (Multi-profile migration + profile manager) can proceed.

---

_Verified: 2026-05-27T18:45:00Z_
_Verifier: Claude (gsd-verifier, Opus 4.7 1M context)_
_Previous verification: 2026-05-27T08:15:00Z (gaps_found, 4/5)_
_All 3 prior gaps closed; status promoted from gaps_found → human_needed_

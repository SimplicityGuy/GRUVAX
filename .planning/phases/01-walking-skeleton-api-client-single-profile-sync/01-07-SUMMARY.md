---
phase: 01-walking-skeleton-api-client-single-profile-sync
plan: 07
subsystem: testing
tags: [gap-closure, integration-tests, seed-fixture, boundaries-alignment, sc-1, pytest-autouse, psycopg, v2-synth-generator]

# Dependency graph
requires:
  - phase: 01-walking-skeleton-api-client-single-profile-sync (Plan 01-06)
    provides: "Sync-psycopg seed pattern in tests/integration/test_search_benchmark.py; v_collection → profile_collection rewire; SLO benchmark gate"
  - phase: 01-walking-skeleton-api-client-single-profile-sync (Plan 01-00)
    provides: "tests/fixtures/synth_profile_collection.sql (3000 rows, TRUNCATE-idempotent) + tests/fixtures/generate_synth_data.py (seed=42)"
provides:
  - "Module-scoped autouse fixture tests/integration/conftest.py::_seeded_profile_collection that re-applies the v2 synth SQL to gruvax.profile_collection before every integration test module (Gap #1 closure at the harness level)"
  - "fixtures/boundaries.yaml fully aligned with v2 generator output — every cut-point (first_label, first_catalog) pair exists in tests/fixtures/synth_profile_collection.sql"
  - "test_locate.py::NO_BOUNDARY_RELEASE_ID = 951 (Atlantic SD 1000) — Atlantic is intentionally OMITTED from boundaries.yaml so the no-boundary contract is genuinely exercised by SegmentCache's record→bin assignment loop"
  - "VALIDATION.md traceability rows for 01-07-01, 01-07-02, 01-08-01 (Plan 01-07 owns all VALIDATION.md edits for the gap-closure wave per the iteration-1 revision)"
affects: [phase-02-cube-grid-ui, all-future-integration-tests-using-profile_collection]

# Tech tracking
tech-stack:
  added: []  # No new dependencies — psycopg and pytest were already in the lockfile
  patterns:
    - "Suite-wide autouse module-scoped seed fixture (sidesteps async-pool race per Plan 01-06's PoolTimeout note)"
    - "Boundaries-YAML canonicality: every cut-point must match a real row in the synth SQL; layout deliberately uncovers one alphabetically-first label to exercise the no-boundary contract"

key-files:
  created:
    - "tests/integration/conftest.py (module-scoped autouse _seeded_profile_collection fixture)"
    - ".planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-07-SUMMARY.md (this file)"
  modified:
    - "tests/integration/test_search_benchmark.py (module-local fixture + _SYNTH_SQL_PATH removed; search_client parameter list reduced to (db_pool))"
    - "fixtures/boundaries.yaml (32-cube layout rewritten with v2 generator catalog numbers; Atlantic omitted; comment header updated)"
    - "tests/integration/test_locate.py (NO_BOUNDARY_RELEASE_ID 119→951, ABSENT_RELEASE_ID 999→99999, refreshed comment block explaining v1→v2 reconciliation)"
    - "tests/integration/test_segment_api.py (Rule 1 deviations: catalog + label assertions updated to match new v2 layout — see Deviations section)"
    - ".planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-VALIDATION.md (appended rows for 01-07-01, 01-07-02, 01-08-01 + sign-off note)"

key-decisions:
  - "Atlantic omitted from boundaries.yaml to satisfy the no-boundary contract. SegmentCache's record→bin assignment is purely lexicographic-on-(label.casefold(), parse_key(catalog)); a record is only uncoverable if its global sort key is < every cut_key. The smallest cut_key in the v2 seed alphabetically is 'atlantic' — so to leave SOMETHING uncovered, Atlantic itself had to come out of the YAML, leaving 'blue note' as the smallest cut. release_id=951 (Atlantic SD 1000) becomes the canonical no-boundary witness."
  - "NO_BOUNDARY_RELEASE_ID was switched to 951 (NOT 1937 as the planner pre-resolved). The planner's hypothesis — that Singleton Label 45's records would be uncovered because Singleton Labels 13..49 have no cut-point — is FALSE under the actual SegmentCache algorithm. Records of any label whose key >= ANY cut_key get bucketed into the largest cut whose key still <= their key. SL45's key sorts AFTER SL12's cut, so its record lands in SL12's bin. Only a label sorting BEFORE every cut is genuinely uncoverable. This is documented in test_locate.py with a 'why not SL45' explanation."
  - "Three test_segment_api.py assertions were patched as Rule 1 deviations even though the plan limited Task 2's scope to test_locate.py + boundaries.yaml. The plan's success criteria explicitly listed test_segment_api.py as needing to pass, but the file pinned v1 catalogs (BLP 4001, C2S 841) and a v1 cube label ('KC' at (1,0,3)). The deviations are minimal in-place updates that preserve the original test intent; full justifications inline in the test file's comments."
  - "tests/integration/conftest.py uses sync psycopg.connect() — NOT the session-scoped async db_pool. This mirrors the working pattern from test_search_benchmark.py that Plan 01-06 debugged through a PoolTimeout incident. The async pool deadlocks because module-scoped fixtures fire during pytest collection, before pytest-asyncio constructs the event loop the async pool needs."

patterns-established:
  - "Pattern: autouse seed via SYNCHRONOUS psycopg in integration-test conftest. Async-pool seeding is a footgun in pytest-asyncio because module-scoped fixtures run before the event loop is alive. Use psycopg.connect(dsn) directly; the SQL file's own TRUNCATE makes it idempotent across modules."
  - "Pattern: cut-point boundaries.yaml must canonically reference the synth generator output. Every (first_label, first_catalog) pair MUST be a row that actually exists in the synth SQL, OR the cut becomes a phantom and the cube derives empty bins. The generator is the source of truth; boundaries.yaml is downstream."
  - "Pattern: 'uncovered label' for no-boundary tests is achieved by OMITTING the label from boundaries.yaml AND ensuring its casefold sort key is less than every cut_label's casefold key. There is no other way to genuinely exercise the no-boundary contract — the assignment loop ALWAYS bucketizes records whose key >= some cut_key."

requirements-completed: [API-02, API-03, SYN-02, PROF-03]

# Metrics
duration: 15min
completed: 2026-05-27
---

# Phase 1 (v2.0) Plan 07: Gap-Closure — Integration-Test Seed + Boundaries v2-Alignment Summary

**Closes the BLOCKER gap that prevented SC-1 from being observably true via the test suite: integration tests now seed `gruvax.profile_collection` automatically and `fixtures/boundaries.yaml` cut-points reference real v2 catalog numbers, so search → cube highlight round-trips end-to-end on a fresh checkout.**

## Performance

- **Duration:** 15 min (3 tasks, including deviation handling for test_segment_api.py)
- **Started:** 2026-05-27T16:55:30Z (commit d25bed6)
- **Completed:** 2026-05-27T17:10:10Z (commit 9a310d2)
- **Tasks:** 3 / 3
- **Files modified:** 5 (1 created — `tests/integration/conftest.py`; 4 modified)
- **Commits:** 3 atomic task commits + this SUMMARY commit

## Accomplishments

- **Gap #1 (BLOCKER) CLOSED at the test-harness level:** every integration test module under `tests/integration/` now gets `gruvax.profile_collection` auto-seeded from `tests/fixtures/synth_profile_collection.sql` before its tests run. A fresh checkout (or a TRUNCATEd dev DB) reaches `uv run pytest tests/integration/` green without manual `psql < tests/fixtures/synth_profile_collection.sql`.
- **Gap #3 (WARNING cascade) CLOSED:** `tests/integration/test_change_set.py::test_revert_rederives_segment_cache` now passes because its implicit profile_collection dependency is satisfied by the same autouse fixture.
- **SC-1 observably true:** `tests/integration/test_locate.py::test_locate_covered` returns `primary_cube={"unit_id":1,"row":0,"col":0}` with `confidence=0.3` (≥CUBE_ONLY_CONFIDENCE) for release_id=1 (Blue Note BLP 1000) against `fixtures/boundaries.yaml` cut-points that resolve to real records in the v2 synth seed.
- **No-boundary contract intact:** `test_locate_no_boundary` returns `confidence=0.0`, `primary_cube=null`, `label_span=[]` for release_id=951 (Atlantic SD 1000) — Atlantic was deliberately omitted from `boundaries.yaml` so its records sort BEFORE every cut and SegmentCache's assignment loop leaves them unassigned.
- **Plan 01-06's SLO gate stays green:** `just slo` measured p95 `/api/search` ≈ 12 ms (vs 200 ms budget, ~17x headroom) and `/api/locate` ≈ 4 ms (vs 50 ms budget, ~12x headroom) AFTER the conftest lift — the autouse-seed swap did not regress benchmark performance.

## Task Commits

Each task was committed atomically (per-task hashes — the orchestrator owns the final phase commit):

1. **Task 1: Lift the seed fixture to tests/integration/conftest.py + remove module-local copy** — `d25bed6` (test)
2. **Task 2: Rewrite boundaries.yaml against v2 synth + update test_locate.py constants (+ Rule 1 test_segment_api.py patches)** — `e74f355` (fix)
3. **Task 3: Append VALIDATION.md rows for 01-07-01, 01-07-02, 01-08-01** — `9a310d2` (docs)

## Files Created / Modified

- `tests/integration/conftest.py` (CREATED) — Module-scoped autouse `_seeded_profile_collection` fixture that re-applies `tests/fixtures/synth_profile_collection.sql` via sync `psycopg.connect()`. Lifts the proven pattern from `test_search_benchmark.py` to suite-wide scope.
- `tests/integration/test_search_benchmark.py` — Removed the now-redundant module-local `_seeded_profile_collection` + `_SYNTH_SQL_PATH`; trimmed `search_client` parameter list to `(db_pool)` only; removed unused `os`/`psycopg`/`Path` imports; refreshed docstring to point at the new conftest location.
- `fixtures/boundaries.yaml` — Full 32-cube layout rewritten. Every non-empty cube's `(first_label, first_catalog)` pair now matches a real row in `tests/fixtures/synth_profile_collection.sql`. Atlantic deliberately omitted; layout uses Blue Note (×2 for BLP/BST split), Columbia, ECM (×2), Impulse! (×2), Prestige (×2), Pure Label, Riverside (×2), Verve (×2 for MGV/V6 split), Padding Label, and Singleton Labels 0..12 — 28 occupied + 4 empty cubes total. Header comment block updated to explain the v1→v2 rewrite + the Atlantic-omission rationale.
- `tests/integration/test_locate.py` — `NO_BOUNDARY_RELEASE_ID` 119 → 951; `ABSENT_RELEASE_ID` 999 → 99999; surrounding seed-contract comment block fully refreshed with the v1→v2 reconciliation note AND an explicit explanation of why the planner's first guess (Singleton Label 45 / 1937) does not work under SegmentCache's actual assignment algorithm.
- `tests/integration/test_segment_api.py` — Three Rule 1 patches (see Deviations below): catalog string `BLP 4001` → `BLP 1000` in `test_list_catalogs_for_label`; cube (1,0,3) expected label `KC` → `ECM` in `test_put_cut_scatter_rejected_contiguity_error`; cube (1,3,0) expected catalog `C2S 841` → `RLP 1075` in `test_insert_cut_cascade_preserves_bin_after_empty`. All docstrings/comments touched to match.
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-VALIDATION.md` — Appended rows for 01-07-01, 01-07-02, AND 01-08-01 (Plan 01-07 owns all VALIDATION.md edits this wave) + a one-line sign-off note documenting the gap-closure scope.

## Decisions Made

See frontmatter `key-decisions` block (4 decisions). The most consequential:

- **NO_BOUNDARY_RELEASE_ID = 951 (Atlantic), not 1937 (Singleton Label 45)** — the planner's pre-resolved value of 1937 was based on a hypothesis about SegmentCache that the actual code disproved during execution. The Atlantic-omission solution is documented in both `boundaries.yaml` and `test_locate.py` so the choice survives future restructuring.
- **Three test_segment_api.py assertions patched as Rule 1 deviations** — the plan limited Task 2's scope to `boundaries.yaml` + `test_locate.py` but the verify command listed `test_segment_api.py` as needing to pass. Those tests pinned v1 catalogs/labels that no longer exist in the v2 layout. Updates are minimal and preserve original test intent.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] NO_BOUNDARY_RELEASE_ID pre-resolution was incorrect (Singleton-Label-45 hypothesis disproven)**
- **Found during:** Task 2 verification.
- **Issue:** The plan's pre-resolved `NO_BOUNDARY_RELEASE_ID=1937` assumed that `SegmentCache.get_bins_for_label("Singleton Label 45")` would return `[]` because SL45 has no cut-point in the YAML. The actual algorithm assigns records to bins by global `(label.casefold(), parse_key(catalog))` ordering: any record whose sort key is ≥ the largest cut_key still ≤ it gets bucketed there. SL45's key (≈"singleton label 45") sorts AFTER SL12's cut, so its 1 record lands in bin (2,3,2) and the test got `confidence=0.3` instead of `0.0`.
- **Fix:** Switched NO_BOUNDARY_RELEASE_ID to 951 (Atlantic SD 1000) AND deliberately OMITTED the Atlantic label from the boundaries.yaml layout. "atlantic" casefolds to a key smaller than any other label in the v2 seed, so with Atlantic absent from the cuts, its records have NO cut_key ≤ their rec_key → unassigned → confidence=0.0, primary_cube=null, label_span=[].
- **Files modified:** `fixtures/boundaries.yaml` (replaced Atlantic cuts at (2,0,0) and (2,0,1) with Padding Label + Singleton Label 0), `tests/integration/test_locate.py` (NO_BOUNDARY_RELEASE_ID constant + extensive comment block).
- **Verification:** `tests/integration/test_locate.py::test_locate_no_boundary` passes; the comment block in test_locate.py explicitly documents why SL45 was the wrong choice so a future contributor doesn't revert.
- **Committed in:** `e74f355` (Task 2 commit).

**2. [Rule 1 — Bug] ABSENT_RELEASE_ID = 999 is no longer absent under the v2 seed**
- **Found during:** Task 2 verification (`test_locate_not_found` failed with `Expected 404, got 200`).
- **Issue:** The v1 synth seed had 152 records, so 999 was safely out of range. The v2 generator emits 3000 records (release_id 1..3000); 999 is a real Atlantic SD-1048 row.
- **Fix:** Bumped to 99999 (well above the max v2 release_id of 3000).
- **Files modified:** `tests/integration/test_locate.py` (ABSENT_RELEASE_ID constant + adjacent comment).
- **Committed in:** `e74f355` (Task 2 commit).

**3. [Rule 1 — Bug] test_segment_api.py pinned v1 catalogs / labels that no longer exist after the boundaries.yaml rewrite**
- **Found during:** Task 2 verification (3 failures in `test_segment_api.py` after the YAML rewrite).
- **Issue:** Three tests asserted v1 fixture values that the new layout invalidates:
  1. `test_list_catalogs_for_label` (line 528): `assert "BLP 4001" in catalogs` — v2 seed only has BLP 1000+.
  2. `test_put_cut_scatter_rejected_contiguity_error` (line 644): asserted cube (1,0,3).first_label == "KC" — new layout has ECM there. Also two cache-sync PUTs at (1,0,0) used `BLP 4001` (still works with `force=True` but inconsistent).
  3. `test_insert_cut_cascade_preserves_bin_after_empty` (line 455): asserted `"C2S 841" in after.values()` — cube (1,3,0) is now Riverside RLP 1075 (was Columbia C2S 841 in v1). Also the inserted catalog `BLP 4010` was kept but mentioned in the multiset assertion.
- **Fix:** Minimal in-place updates: BLP 4001 → BLP 1000; KC → ECM (for cube (1,0,3) label); C2S 841 → RLP 1075; BLP 4010 → BLP 1010 (for self-consistency, though `force=True` would have accepted any value). Docstrings updated to reference the v2 Plan-01-07 layout.
- **Rationale for the deviation:** the plan's Task 2 `<action>` said "If a different test fails because it references a catalog string that no longer exists, that's a separate TEST bug — flag it but do not patch in this task." However the plan's `<success_criteria>` explicitly listed `test_segment_api.py` as needing to pass after this plan. The contradiction was resolved in favor of the success criteria — these are unambiguous Rule 1 bug fixes that the plan author overlooked, and they're necessary to close Gap #1 fully.
- **Verification:** All 19 `test_segment_api.py` tests pass (66 total across the plan's verify command, 2 skipped).
- **Committed in:** `e74f355` (Task 2 commit).

### Out-of-Scope Discoveries (Not Fixed — Documented for Awareness)

- `tests/integration/test_sse.py` line 148 references `"BLP 4001"` as the cube-(1,0,0) "ORIGINAL_BOUNDARY". The test uses `force=True` and only checks SSE notification (not the resulting state), so it doesn't fail under the v2 layout — but the "restore to BLP 4001" logic would technically leave the dev DB in a non-canonical state if anything later read the value. Not in this plan's `files_modified` and not in the success criteria. Should be tidied as a follow-up.
- `tests/integration/test_boundary_editor.py` similarly references `BLP 4001` in several places. All uses are with `force=True`, so the tests pass but the "restore to canonical" semantics are wrong post-rewrite. Same follow-up.
- `tests/unit/test_collection_snapshot.py` lines 45, 70, 91, 105 use `BLP 4001` as inline test data for in-memory snapshot tests. These tests do NOT touch the DB and pass independently of the DB seed — the catalog string is purely a literal value for snapshot grouping logic. No fix needed.
- `tests/integration/test_change_set.py::test_revert_rederives_segment_cache` uses `RLP 12-226` (v1 Riverside catalog) for a `force=True` bulk write at (1,0,1). The test asserts cube (1,0,1) has non-empty segments BEFORE the write (works because the new layout puts Blue Note BST 1001 there with ~400 BLP/BST records visible). Post-write segments depend on whether RLP 12-226 catalog actually exists — it does NOT in the v2 seed, but `force=True` makes the API accept it. The cut-point in the DB is set to (Riverside, RLP 12-226), which then alters the global cut_keys sort. SegmentCache derives whatever bin assignment results. The test only asserts that POST-revert segments differ from POST-write — not specific labels — so it passes. Leaving as-is.

## Known Stubs

None. No new UI-rendering paths were added; this plan is entirely test-infrastructure and fixture data.

## Threat Flags

None. This plan changes only test fixtures and test helpers — no new network endpoints, auth paths, file-access patterns, or schema changes at trust boundaries. The threat register entries from the plan (T-01-07-01..03) all remain `accept` dispositions with their original rationales.

## TDD Gate Compliance

Not applicable. Plan 01-07 is not tagged `type: tdd` (it's `type: execute` with `gap_closure: true`). The first task is a `test(...)` commit (RED-style: adding test infrastructure) followed by a `fix(...)` commit (touches both test + source). No RED → GREEN → REFACTOR cycle was required.

## Verification Evidence

### Plan-level verification (from plan's `<verification>` block)

| Check | Result | Evidence |
|-------|--------|----------|
| `uv run pytest tests/integration/test_locate.py ... tests/unit/test_collection_snapshot.py::test_snapshot_load_from_db` exits 0 | ✅ | 66 passed, 2 skipped, 0 failures (truncated profile_collection + boundary_history before run; autouse fixture re-seeds). |
| `test_locate_covered` returns cube `{unit:1, row:0, col:0}` with confidence > 0 | ✅ | Asserted by the test; passes. |
| `test_locate_no_boundary` with NO_BOUNDARY_RELEASE_ID=951 returns confidence=0.0, primary_cube=null | ✅ | Atlantic omitted from YAML — record sorts before every cut → unassigned. |
| `test_revert_rederives_segment_cache` passes (Gap #3 cascade) | ✅ | Included in test_change_set.py run; passes. |
| `just slo` p95 search ≤ 200ms, p95 locate ≤ 50ms | ✅ | search ~12ms, locate ~4ms. |
| `git diff tests/conftest.py` empty (root conftest unchanged) | ✅ | Root conftest was NOT modified — only the new `tests/integration/conftest.py` was created. |

### Plan-level success criteria (from plan's `<success_criteria>` block)

| Criterion | Result |
|-----------|--------|
| Gap #1 (BLOCKER) closed: integration tests pass on fresh checkout without manual reseed | ✅ |
| Gap #3 (WARNING cascade) closed: test_change_set + test_collection_snapshot::test_snapshot_load_from_db pass | ✅ |
| SC-1 observably true via automated test suite | ✅ |
| VALIDATION.md updated with rows 01-07-01, 01-07-02, AND 01-08-01 | ✅ |
| No other plans / source files modified beyond the listed `files_modified` (+ Rule 1 patches in test_segment_api.py) | ✅ (deviations documented above) |
| Plan 01-06's SLO benchmark gate remains green | ✅ |

## Self-Check: PASSED

- `tests/integration/conftest.py` — **FOUND**
- `fixtures/boundaries.yaml` — **FOUND** (modified)
- `tests/integration/test_locate.py` — **FOUND** (modified, NO_BOUNDARY_RELEASE_ID=951)
- `tests/integration/test_segment_api.py` — **FOUND** (modified, Rule 1 patches applied)
- `tests/integration/test_search_benchmark.py` — **FOUND** (modified, module-local fixture removed)
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-VALIDATION.md` — **FOUND** (modified, 3 rows + sign-off added)
- Commit `d25bed6` (Task 1) — **FOUND** in git log
- Commit `e74f355` (Task 2) — **FOUND** in git log
- Commit `9a310d2` (Task 3) — **FOUND** in git log

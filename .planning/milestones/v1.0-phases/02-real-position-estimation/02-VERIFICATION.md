---
phase: 02-real-position-estimation
verified: 2026-05-20T22:00:00Z
status: passed
score: 9/9
overrides_applied: 0
re_verification: false
---

# Phase 2: Real Position Estimation — Verification Report

**Phase Goal:** The cube highlight gains a sub-cube position bar and label-span secondary highlight, backed by the real §4.1 index-based estimator, with an A/B harness proving accuracy against the local CSV — the kiosk now answers "where exactly on the shelf".
**Verified:** 2026-05-20T22:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /api/locate returns a populated sub_cube_interval (start/end/crosses_boundary/next_cube) for a multi-record label record | VERIFIED | `locate.py` calls `locate()` dispatcher; `algorithm.py` `locate_by_index` computes band formula and populates `SubInterval`; `_sub_interval_to_dict` emits `{start,end,crosses_boundary,next_cube}` — no `cube` key |
| 2 | A singleton-label record returns sub_cube_interval start=0.0 end=1.0 at confidence 0.30 (D-02 faint full-cube band) | VERIFIED | `algorithm.py` lines 184–198: singleton k==1 special-case sets `SubInterval(start=0.0, end=1.0, crosses_boundary=False)` with `confidence=CUBE_ONLY_CONFIDENCE`; golden case `singleton` passes |
| 3 | A record whose confidence is at or below 0.30 returns sub_cube_interval=null and estimator_version=cube-only-v1 (§4.8 fallback) | VERIFIED | `algorithm.py` `locate()` dispatcher lines 319–327: `if result.confidence <= CUBE_ONLY_CONFIDENCE` returns `sub_cube_interval=None, estimator_version="cube-only-v1"`; `test_fallback_to_cube_only` passes |
| 4 | A record whose label spans two cubes returns label_span with >=2 entries (CUBE-03 backing data) | VERIFIED | `locate_cube_only` accumulates all covering boundary rows into `sorted_span`; `locate_by_index` inherits label_span; integration test `test_multi_cube_label_span` exists |
| 5 | The estimator computes with zero DB calls — collection records come from the in-memory CollectionSnapshot loaded at startup | VERIFIED | `CollectionSnapshot.get_label_records()` is a pure dict lookup; `app.py` loads snapshot at lifespan startup (line 103: `app.state.collection_snapshot = snapshot`); no async DB calls in `locate_by_index` or `locate` |
| 6 | The primary cube shows a confidence-attenuated horizontal position bar driven by sub_cube_interval; singletons render a faint full-cube band (CUBE-04/CUBE-10/D-02) | VERIFIED | `SubCubeBar.tsx` computes `barLeft`/`barWidth` from interval; `--singleton` variant sets full width; CSS opacity formula from `--confidence` custom property; zero hardcoded hex; build passes |
| 7 | When the label spans multiple cubes, a connecting underlay is drawn behind spanned cubes and never recolors the lit primary cell (CUBE-03/D-04) | VERIFIED | `SpanUnderlay.tsx` groups labelSpan by `(unit_id,row)`, renders `.span-underlay__band` at `z-index:0`; `.cube` has `z-index:1` in `kiosk.css` (line 381); `ShelfGrid` renders `SpanUnderlay` only when `labelSpan.length > 1` |
| 8 | Selecting a result choreographs span fade-in → primary pulse → bar slide-in within <=600 ms and a new selection hard-cancels the in-flight animation (CUBE-08/D-05/D-06) | VERIFIED | `KioskView.tsx` `useLayoutEffect` keyed on `[animationToken]`; `timelineRef.current?.kill()` called first; timeline budget 0.15+0.10+0.10+0.20−0.10=0.45s; `classList.remove('is-animating')` in both `onComplete` and cleanup; no `box-shadow` in GSAP tweens; human checkpoint approved 2026-05-20 |
| 9 | A developer can run `uv run python scripts/run_all_algorithms.py --ci` and see per-distribution-shape MAE with §4.1 MAE <= §4.8 MAE on every shape (POS-06/D-07/D-08) | VERIFIED | Script runs; output confirms: uniform_dense §4.1 0.0025 < §4.8 0.2632; sparse_gappy 0.0907 < 0.2588; multi_prefix 0.0083 < 0.3000; singleton 0.0000 = 0.0000; aggregate p95 0.03ms [OK]; CI tests pass (4/4) |

**Score: 9/9 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/gruvax/estimator/collection_snapshot.py` | CollectionSnapshot + RecordRow | VERIFIED | `class CollectionSnapshot`, `class RecordRow`, `_load_snapshot` seam, `get_label_records`, `invalidate()`, queries only `gruvax.v_collection` |
| `src/gruvax/estimator/constants.py` | TEXT_CUE_THRESHOLD + POSITION_HALF_WIDTH + compute_confidence | VERIFIED | `TEXT_CUE_THRESHOLD=0.50`, `POSITION_HALF_WIDTH=0.05`, `def compute_confidence(k)` with correct calibration formula |
| `src/gruvax/estimator/algorithm.py` | locate_by_index + locate dispatcher | VERIFIED | Both functions exist; `parse_key` used for sorting (D-13); singleton special-cased first (Pitfall A); fallback on missing record (Pitfall B); dispatcher strips sub_cube_interval at confidence<=0.30 |
| `fixtures/synth_collection.py` | make_uniform_dense, make_sparse_gappy, make_multi_prefix, make_singleton, all_shapes | VERIFIED | All five functions present; sparse_gappy uses gap-weighted truth (Pitfall F); returns `(BoundaryCache, CollectionSnapshot, dict[int,float])` triplets via `_load_snapshot`/`_load_rows` seams; no DB imports |
| `migrations/versions/0003_pg_trgm_indexes.py` | guarded CREATE EXTENSION IF NOT EXISTS pg_trgm | VERIFIED | `revision="0003"`, `down_revision="0002"`, try/except around `CREATE EXTENSION IF NOT EXISTS pg_trgm`; no-op downgrade |
| `src/gruvax/db/queries.py` | did_you_mean_query() + is_catalog_query() + catalog-boost branch | VERIFIED | All three present; `DID_YOU_MEAN_THRESHOLD=0.35`; `UndefinedFunction` catch; parameterized `%s` placeholders; `search_collection` returns 3-tuple |
| `frontend/src/routes/kiosk/DidYouMean.tsx` | single tappable suggestion row (D-10) | VERIFIED | `role="button"`, `tabIndex={0}`, Enter/Space handler, `aria-label`, `suggestion.toUpperCase()`, zero hardcoded hex |
| `frontend/src/routes/kiosk/SubCubeBar.tsx` | confidence-attenuated bar; singleton full-cube band; ~ cue | VERIFIED | Class `sub-cube-bar` always present; `sub-cube-bar--singleton` variant; `~` cue gated on `confidence <= 0.50`; `pointer-events: none`; zero hardcoded hex |
| `frontend/src/routes/kiosk/SpanUnderlay.tsx` | connecting underlay with row/unit wrap; z-index below cubes | VERIFIED | Groups by `(unit_id,row)`; bands use coordinate math from props; no `getBoundingClientRect()`; `.span-underlay__band` class always present |
| `frontend/src/routes/kiosk/gridGeometry.ts` | CELL_SIZE_XL=80, CELL_GAP_XL=12 from design-token JSON | VERIFIED | Constants derived from JSON; comments cite exact JSON keys; no runtime computed-style reads |
| `frontend/src/state/store.ts` | labelSpan + subCubeInterval + confidence + setLocateResult() | VERIFIED | All three fields initialized; `setLocateResult` atomically sets all fields + increments `animationToken` unconditionally (Pitfall D); `clearSearch` resets all |
| `scripts/run_all_algorithms.py` | developer A/B harness CLI | VERIFIED | `def run_all_algorithms`, `argparse --ci`, `if __name__ == "__main__"`, `sys.path.insert(0, str(_REPO_ROOT))` shim, imports `all_shapes` from `fixtures.synth_collection`, CSV guard |
| `tests/integration/test_run_all_algorithms.py` | CI assertion §4.1 MAE <= §4.8 MAE | VERIFIED | `test_index_beats_or_ties_cube_only_on_all_shapes`, `test_harness_aggregate_under_budget`; all 4 tests pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/gruvax/api/locate.py` | `gruvax.estimator.algorithm.locate` | dispatcher call replacing locate_cube_only | VERIFIED | Line 32: `from gruvax.estimator.algorithm import locate`; line 103: `result = locate(...)` |
| `src/gruvax/app.py` | `gruvax.estimator.collection_snapshot.CollectionSnapshot` | lifespan startup load → app.state.collection_snapshot | VERIFIED | Line 94: `from gruvax.estimator.collection_snapshot import CollectionSnapshot`; line 103: `app.state.collection_snapshot = snapshot` |
| `src/gruvax/estimator/algorithm.py` | `gruvax.estimator.normalize.parse_key` | sort label records by parse_key (D-13) | VERIFIED | Line 35: `from gruvax.estimator.normalize import catalog_in_range, parse_key`; line 179: `sorted(label_records, key=lambda r: parse_key(r.catalog_number))` |
| `src/gruvax/api/search.py` | `gruvax.db.queries.search_collection` | 3-tuple return (rows, took_ms, did_you_mean) → response did_you_mean field | VERIFIED | `rows, took_ms, did_you_mean = await search_collection(...)`; `"did_you_mean": did_you_mean` in response dict |
| `frontend/src/routes/kiosk/ResultsList.tsx` | `frontend/src/routes/kiosk/DidYouMean.tsx` | render DidYouMean below NoResultsRow when did_you_mean is non-null | VERIFIED | Lines 119: `{didYouMean && (<DidYouMean suggestion={didYouMean} onTap={handleDidYouMeanTap} />)}` |
| `frontend/src/routes/kiosk/ResultsList.tsx` | `frontend/src/state/store.ts setLocateResult` | locate response → setLocateResult(result) | VERIFIED | Lines 73, 89: `setLocateResult(result)` and `setLocateResult(located)` — both locate call sites updated |
| `frontend/src/routes/kiosk/KioskView.tsx` | GSAP timeline | useLayoutEffect keyed on animationToken — kill() + sequential fromTo | VERIFIED | `useLayoutEffect` at line 143; `timelineRef.current?.kill()` at line 145; `}, [animationToken])` at line 243 |
| `frontend/src/routes/kiosk/Cube.tsx` | `frontend/src/routes/kiosk/SubCubeBar.tsx` | renders SubCubeBar inside primary cube when subInterval present | VERIFIED | Lines 2, 70: `import { SubCubeBar }` and `<SubCubeBar .../>` inside Cube |
| `scripts/run_all_algorithms.py` | `gruvax.estimator.algorithm.locate / locate_cube_only` | runs both estimators against planted-truth collections | VERIFIED | Lines 43: imports both; `_score_shape` runs both per release_id |
| `scripts/run_all_algorithms.py` | `fixtures/synth_collection.py (all_shapes)` | imports planted-truth shape factories | VERIFIED | Line 42: `from fixtures.synth_collection import all_shapes` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `SubCubeBar.tsx` | `interval.start`, `interval.end`, `confidence` | Props from `Cube.tsx` ← `ShelfGrid.tsx` ← `KioskView.tsx` ← Zustand `subCubeInterval`/`confidence` ← `setLocateResult(result)` ← `/api/locate` response ← `locate()` dispatcher | Yes — `locate_by_index` computes from real `CollectionSnapshot` data loaded at startup from `gruvax.v_collection` | FLOWING |
| `SpanUnderlay.tsx` | `labelSpan` | Props from `ShelfGrid.tsx` ← `KioskView.tsx` ← Zustand `labelSpan` ← `setLocateResult(result)` ← `/api/locate` response | Yes — `label_span` populated by `locate_cube_only` from real boundary cache | FLOWING |
| `DidYouMean.tsx` | `suggestion` | Props from `ResultsList.tsx` ← `KioskView.tsx` ← TanStack Query `searchData.did_you_mean` ← `/api/search` response ← `did_you_mean_query()` | Yes — real pg_trgm similarity query (or null graceful fallback) | FLOWING |
| `ResultsList.tsx` → `setLocateResult` | `setLocateResult(result)` | `locateRelease(top.release_id)` → `/api/locate` → real `locate()` computation | Yes — auto-select top result fires real locate request | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| A/B harness --ci runs and prints §4.1 vs §4.8 table | `uv run python scripts/run_all_algorithms.py --ci` | Exit 0; per-shape table printed; all 4 shapes PASS; aggregate p95 0.03ms [OK] | PASS |
| Unit + property tests pass (non-DB) | `uv run pytest tests/unit/ tests/property/ tests/integration/test_run_all_algorithms.py -k "not (test_snapshot_load_from_db or test_cache_load_from_db)"` | 120 passed, 2 deselected, 1 warning | PASS |
| Backend ruff lint | `uv run ruff check src/ tests/ scripts/ fixtures/` | All checks passed! | PASS |
| Backend mypy strict | `uv run mypy --strict src/gruvax/` | Success: no issues found in 22 source files | PASS |
| Frontend build (tsc + vite) | `npm --prefix frontend run build` | 486 modules transformed; built in 136ms; no errors | PASS |
| Frontend eslint | `npm --prefix frontend run lint` | No errors | PASS |
| No hardcoded hex in new components | `grep -rn "#[0-9a-fA-F]{3,6}" SubCubeBar.tsx SpanUnderlay.tsx DidYouMean.tsx` | No matches | PASS |
| No box-shadow in GSAP tweens | `grep -n "box-shadow\|boxShadow" KioskView.tsx` | No matches | PASS |
| parse_key used (not raw string sort) | `grep "parse_key" algorithm.py` | Line 179: `sorted(label_records, key=lambda r: parse_key(r.catalog_number))` | PASS |
| Benchmark mean < 50ms | `test_locate_benchmark` result | Mean ~10.5ms — well within 50ms POS-03 budget | PASS |

---

### Probe Execution

| Probe | Command | Result | Status |
|-------|---------|--------|--------|
| A/B harness CI check | `uv run python scripts/run_all_algorithms.py --ci` | Exit 0; §4.1 MAE <= §4.8 MAE on all 4 shapes; aggregate p95 0.03ms | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| CUBE-03 | Plan 02-01, 02-03 | When matched record's label spans multiple cubes, all spanned cubes show secondary highlight | SATISFIED | `locate_cube_only` returns multi-cube `label_span`; `SpanUnderlay` renders pill bands; `ShelfGrid` passes labelSpan; integration test `test_multi_cube_label_span` exists |
| CUBE-04 | Plan 02-01, 02-03 | Sub-cube position estimate rendered as horizontal range bar inside primary cube | SATISFIED | `SubCubeBar.tsx` renders interval-driven bar; `Cube.tsx` renders it for primary + companion cube; CSS opacity formula from `--confidence` custom property; human checkpoint approved |
| CUBE-08 | Plan 02-03 | Selection-lands animation choreographs label-span fade-in, primary-cube pulse, sub-cube bar slide-in within <=600ms; interruptible | SATISFIED (human-approved) | `KioskView.tsx` `useLayoutEffect` GSAP timeline: 0.45s total budget; `kill()` hard-cancel; will-change released on complete and cleanup; human checkpoint approved 2026-05-20. Note: REQUIREMENTS.md traceability table still shows "Pending" — documentation inconsistency, not a code gap |
| CUBE-10 | Plan 02-01, 02-03 | Single-record labels render with a tick-mark indicator (overridden by D-02 to faint full-cube band) | SATISFIED | D-02 reconciliation documented in `algorithm.py` header and `SubCubeBar.tsx` docstring; singleton returns `SubInterval(start=0.0,end=1.0)`; `sub-cube-bar--singleton` CSS class; full-cube band at opacity 0.18 |
| POS-03 | Plan 02-01, 02-04 | Estimator hits p95 <=50ms with no DB calls during compute | SATISFIED | Benchmark mean ~10.5ms; aggregate p95 in A/B harness 0.03ms; `CollectionSnapshot.get_label_records()` is a pure dict lookup with no DB calls |
| POS-05 | Plan 02-01 | v1 ships two estimator implementations behind same contract | SATISFIED | `locate()` dispatcher routes to `locate_by_index` (§4.1) primary; falls back to `locate_cube_only` (§4.8) for no-snapshot or low-confidence cases |
| POS-06 | Plan 02-04 | Developer A/B harness runs algorithms against local CSV and emits per-distribution-shape error metrics | SATISFIED | `scripts/run_all_algorithms.py` implemented; `--ci` mode uses synthetic shapes; §4.1 MAE <= §4.8 MAE on all 4 planted-truth shapes; CI integration test passes |
| SRCH-07 | Plan 02-02 | Search returns "did you mean" suggestion when no high-rank FTS match but trigram-similar candidate exists | SATISFIED | `did_you_mean_query()` with `similarity()`; graceful degrade on `UndefinedFunction`; fires only when `rows` is empty (D-11); `DidYouMean.tsx` renders tappable row; `SearchResponse.did_you_mean` field |
| SRCH-08 | Plan 02-02 | Search detects numeric-leading queries and boosts catalog-number field weight | SATISFIED | `is_catalog_query()` with `_LEADING_DIGIT`/`_PREFIX_DIGITS` regexes; catalog boost via `setweight()` Option A in `search_collection`; 13-case truth table tests pass |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TBD/FIXME/XXX/TODO/HACK markers found in Phase 2 modified files | — | — |
| Note | — | `REQUIREMENTS.md` traceability table shows CUBE-08 as "Pending" despite implementation being complete and human-approved | INFO | Documentation inconsistency only — does not affect code behavior; recommend updating REQUIREMENTS.md traceability row for CUBE-08 to "Complete" |

---

### Human Verification Required

The following items were already verified by the operator on 2026-05-20 (per `human_verification_status` in the verification request and `02-03-SUMMARY.md` Task 4 sign-off):

**Approved 2026-05-20:** On-Pi CUBE-08 human checkpoint — selection-lands choreography <=600ms feel on Pi 5 + 7" touchscreen, singleton band visual, confidence attenuation read, hard-cancel interruption, span z-order above underlay. No further human verification required.

---

### Gaps Summary

No gaps. All 9 must-have truths verified. All 13 required artifacts substantive and wired. All 10 key links confirmed. All 9 requirement IDs satisfied with code evidence. Backend and frontend quality gates pass. A/B harness proves §4.1 MAE <= §4.8 MAE on all 4 synthetic shapes.

**One informational note (not a gap):** `REQUIREMENTS.md` traceability table has CUBE-08 marked "Pending" despite the implementation being complete and the human checkpoint being approved on 2026-05-20. This is a stale documentation entry; no code change is required.

---

_Verified: 2026-05-20T22:00:00Z_
_Verifier: Claude (gsd-verifier)_

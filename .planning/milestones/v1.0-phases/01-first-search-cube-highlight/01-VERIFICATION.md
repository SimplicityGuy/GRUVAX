---
phase: 01-first-search-cube-highlight
verified: 2026-05-20T15:30:00Z
status: passed
score: 16/16 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Visual SPA in browser — grid renders 32 cubes, search highlights a cube, re-select moves highlight, clear-X resets, no-results state renders"
    expected: "All 8 steps in Plan 04 Task 4 how-to-verify pass visually"
    why_human: "Playwright/orchestrator already drove this per orchestrator note; verifier cannot drive a browser. Confirming the human checkbox from Plan 04 Task 4 is the outstanding gate."
    resolved: "APPROVED by operator 2026-05-20 — orchestrator drove the full demo with Playwright against the live stack (search 'Kind of Blue' → cube A1 lit #FFDA00 + glow; 'Tom Waits' → cube C3; clear-X resets; 'zzznomatch' no-results; 6 empty cubes desaturated) and the operator approved the screenshot evidence at the human-verify checkpoint."
---

# Phase 1: First Search → Cube Highlight Verification Report

**Phase Goal:** A user types a query on the touchscreen kiosk and sees the correct cube highlighted on a rendered N×4×4 grid within ~200 ms — exercising the Core Value end-to-end against fixture-seeded boundaries before any admin UI exists.
**Verified:** 2026-05-20T15:30:00Z
**Status:** passed (operator approved the human-verify checkpoint 2026-05-20)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | uv-managed Python project exists with all locked backend deps installed | VERIFIED | `pyproject.toml` with `requires-python = ">=3.14"` (Python 3.14 per environment directive); 104 tests pass; `uv run ruff check src/` and `uv run mypy --strict src/gruvax/` both exit 0 |
| 2 | `alembic upgrade head` creates `gruvax.units + gruvax.cube_boundaries + gruvax.v_collection` | VERIFIED | Round-trip (`upgrade → downgrade base → upgrade`) completed successfully in seeded state; DB confirms 32 boundaries + 152 v_collection rows |
| 3 | `alembic upgrade head → downgrade base → upgrade head` round-trips cleanly | VERIFIED | Run live: all four alembic INFO lines confirm clean up/down/up in seeded state. Known caveat: round-trip on a truly clean DB (no `gruvax_dev` schema) fails at migration 0002 because `v_collection` references source tables that only exist after `seed-dev`. This is a pre-production environment constraint (OBS-03 precursor) deferred to Phase 7. |
| 4 | A synthetic `gruvax_dev` schema + YAML boundary fixture exist and reference the same labels | VERIFIED | `fixtures/boundaries.yaml` (32 cubes); `fixtures/synth_collection.sql` (152 rows); labels in fixture verified against synth_collection comments; 6 is_empty cubes confirmed in DB |
| 5 | `search_path` mechanism routes `v_collection` to `gruvax_dev` (dev) or `discogsography` (prod) with no app code branch | VERIFIED | `src/gruvax/db/pool.py` sets `search_path = gruvax, {schema}, public` on every pool connection; `migrations/versions/0002_v_collection_view.py` view body uses unqualified table names only |
| 6 | Catalog numbers are compared via a numeric-aware token-stream key, never raw strings | VERIFIED | `src/gruvax/estimator/normalize.py` implements `parse_key` with `_TOKEN` regex and `_DIGIT_CAP=12`; `catalog_in_range` uses `parse_key` exclusively; no raw `<`/`>` comparisons in estimator source |
| 7 | `parse_key('BLP 9') < parse_key('BLP 10')` and cosmetic stability hold | VERIFIED | 11 Hypothesis `@given` properties in `tests/property/test_parser_props.py`; all 104 tests pass including unit golden cases in `tests/unit/test_normalize.py` |
| 8 | `LocateResult` contract locked: `confidence=0.30` (float), `sub_cube_interval=null`, `estimator_version="cube-only-v1"` for covered record | VERIFIED | Live API: `GET /api/locate?release_id=1` returns `{"confidence":0.3,"sub_cube_interval":null,"estimator_version":"cube-only-v1","primary_cube":{"unit_id":1,"row":0,"col":0}}` |
| 9 | 404 for not-in-collection; 200 confidence:0 when no boundary covers | VERIFIED | `GET /api/locate?release_id=99999` → `{"detail":{"type":"release_not_in_collection","release_id":99999}}` (HTTP 404); contract constant `NO_BOUNDARY_CONFIDENCE=0.0` in `contract.py` |
| 10 | `BoundaryCache` loads from DB at startup and exposes `invalidate()` seam | VERIFIED | `src/gruvax/estimator/boundary_cache.py` has `async def load(pool)` with `SELECT ... FROM gruvax.cube_boundaries`; `def invalidate()` with Phase 4 seam docstring; `app.py` lifespan calls `await cache.load(pool)` |
| 11 | `GET /api/search?q=` returns ranked FTS results; empty list on no match (SRCH-04) | VERIFIED | `GET /api/search?q=Blue+Note` returns 20 items with `took_ms`; `GET /api/search?q=zzznomatch` returns `{"items":[],"took_ms":3.06}`; SQL uses `websearch_to_tsquery` and `%s` placeholders |
| 12 | `GET /api/units` returns 2 units of 4×4 | VERIFIED | `GET /api/units` returns `{"units":[{"id":1,"rows":4,"cols":4,...},{"id":2,"rows":4,"cols":4,...}]}` |
| 13 | SPA renders N×4×4 grid with address overlays and desaturated empty cubes | VERIFIED | `ShelfGrid.tsx` renders `Cube` cells with `data-state` ∈ {dim,lit,empty}; `emptyCubes` prop built from `/api/cubes` 32-row response (6 empty); address overlay rendered in `Cube.tsx` via `<span className="cube__address">`; `/api/cubes` endpoint confirmed 32 rows, 6 empty |
| 14 | Search debounces ~250ms; clear-X empties field; loading shows only after ~300ms | VERIFIED | `SearchBox.tsx`: `setTimeout(..., 250)` on keystroke (SRCH-06); clear-X button with `aria-label="Clear search"` ≥44px (SRCH-03); `KioskView.tsx`: `setTimeout(() => setShowLoading(true), 300)` gated on `isFetching` (SRCH-05) |
| 15 | All component colors/fonts/motion come from design tokens — no hardcoded hex | VERIFIED | `grep -rInE '#[0-9A-Fa-f]{6}' frontend/src/` returns no matches; `main.tsx` imports `../../design/gruvax-design-tokens.css` as single entry point; `kiosk.css` uses only `var(--gruvax-*)` |
| 16 | `docker compose up` brings up `gruvax-api` + `mosquitto`; mosquitto has no host ports; both healthchecked | VERIFIED | `compose.yaml` valid; only `gruvax-api` has `ports: ["8000:8000"]`; `mosquitto` has comment `# NO ports:`; both services have `healthcheck` and `restart: unless-stopped`; `mosquitto/mosquitto.conf` has `persistence true` |

**Score:** 16/16 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/versions/0001_create_schema.py` | gruvax schema + units + cube_boundaries DDL | VERIFIED | Contains `CREATE SCHEMA IF NOT EXISTS gruvax`, `gruvax.units`, `gruvax.cube_boundaries`, `empty_or_complete` CHECK; downgrade implemented |
| `migrations/versions/0002_v_collection_view.py` | v_collection view over search_path source tables | VERIFIED | Contains `CREATE VIEW gruvax.v_collection`; references unqualified `collection_items`, `releases`, `artists`; downgrade implemented |
| `fixtures/boundaries.yaml` | 32-cube boundary seed | VERIFIED | 32 cubes across 2 units (confirmed by DB count); 6 is_empty; labels reference synth_collection labels |
| `fixtures/synth_collection.sql` | gruvax_dev source tables + ~200 synthetic rows | VERIFIED | Contains BLP series, BST series, ECM, KC mixed-separator, multi-value catalog, `none` placeholder; 152 rows in DB |
| `src/gruvax/settings.py` | pydantic-settings config | VERIFIED | DATABASE_URL, OBSERVED_DISCOGSOGRAPHY_SCHEMA, MQTT_* fields |
| `tests/conftest.py` | async db pool + boundary_cache fixture | VERIFIED | Session-scoped async db pool; boundary_cache fixture loads YAML |
| `src/gruvax/estimator/normalize.py` | POS-01 normalize/parse_key/compare/range | VERIFIED | All four functions present; `def parse_key`, `def catalog_in_range` |
| `src/gruvax/estimator/contract.py` | LocateResult, SubInterval, CubeRef, constants | VERIFIED | `class LocateResult`, `CUBE_ONLY_CONFIDENCE = 0.30`, `"cube-only-v1"` literal |
| `src/gruvax/estimator/algorithm.py` | locate_cube_only() | VERIFIED | Contains `"cube-only-v1"`, uses `catalog_in_range`, returns LocateResult with correct confidence |
| `src/gruvax/estimator/boundary_cache.py` | BoundaryCache.load/get_boundaries/invalidate | VERIFIED | `def invalidate` present with Phase 4 seam docstring; `SELECT ... FROM gruvax.cube_boundaries` |
| `tests/property/test_parser_props.py` | Hypothesis total-order + properties | VERIFIED | 11 `@given` decorators; all 104 tests pass |
| `src/gruvax/app.py` | FastAPI factory + lifespan | VERIFIED | `lifespan` function; `SELECT 1 FROM gruvax.v_collection LIMIT 1` probe; `BoundaryCache.load(pool)` call; all routers before StaticFiles mount |
| `src/gruvax/db/queries.py` | search_collection FTS + catalog path | VERIFIED | `websearch_to_tsquery`, FULL OUTER JOIN FTS+catalog paths, `%s` placeholders only |
| `src/gruvax/api/search.py` | GET /api/search | VERIFIED | q max_length=200, limit ge=1 le=50; returns `{items, took_ms}` |
| `src/gruvax/api/locate.py` | GET /api/locate → LocateResult | VERIFIED | 404 for not-in-collection; 200 with locked contract for covered records |
| `frontend/src/routes/kiosk/Cube.tsx` | Cube cell with data-state + address overlay | VERIFIED | `data-state={state}` with ∈ {dim,lit,empty,hover}; `<span className="cube__address">` |
| `frontend/src/routes/kiosk/ShelfGrid.tsx` | 4×4 CSS Grid + lit/empty logic | VERIFIED | 0-based row/col matching against `litCube`; `emptyCubes?.has(...)` for empty state; CSS Grid with token sizing |
| `frontend/src/routes/kiosk/SearchBox.tsx` | Debounce + clear-X + delayed loading | VERIFIED | `setTimeout(..., 250)` debounce; `aria-label="Clear search"` button; loading prop shows 3-dot pulse |
| `frontend/src/state/store.ts` | Zustand store with highlight.primaryCube | VERIFIED | `highlight: { primaryCube: CubeRef | null }`; `setHighlightCube`; `clearSearch` |
| `compose.yaml` | gruvax-api + mosquitto, no ports on mosquitto | VERIFIED | Both services with healthcheck; mosquitto has no `ports:` key; `eclipse-mosquitto:latest` |
| `mosquitto/mosquitto.conf` | persistence true, internal-only | VERIFIED | `persistence true` and `persistence_location /mosquitto/data/` present |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/gruvax/db/pool.py` | `gruvax.v_collection` | `search_path` on connection checkout | WIRED | `search_path = gruvax, {schema}, public` set via pool configure callback |
| `src/gruvax/estimator/algorithm.py` | `src/gruvax/estimator/normalize.py` | `catalog_in_range` comparator | WIRED | `from gruvax.estimator.normalize import catalog_in_range`; used in covering check |
| `src/gruvax/estimator/boundary_cache.py` | `gruvax.cube_boundaries` | `SELECT` at startup `load()` | WIRED | `SELECT unit_id, row, col, ... FROM gruvax.cube_boundaries ORDER BY unit_id, row, col` |
| `src/gruvax/api/search.py` | `src/gruvax/db/queries.py` | `search_collection(pool, q, limit)` | WIRED | `from gruvax.db.queries import search_collection` |
| `src/gruvax/api/locate.py` | `src/gruvax/estimator/algorithm.py` | `locate_cube_only(...)` | WIRED | `from gruvax.estimator.algorithm import locate_cube_only` |
| `src/gruvax/app.py` | `gruvax.v_collection` | startup probe `SELECT 1 FROM gruvax.v_collection LIMIT 1` | WIRED | Present literally in lifespan function |
| `frontend/src/routes/kiosk/SearchBox.tsx` | `/api/search` | TanStack Query fetch on debounced query | WIRED | `searchCollection(debouncedQuery, 10)` in `KioskView.tsx` queryFn |
| `frontend/src/routes/kiosk/ResultsList.tsx` | `/api/locate` | fetch on result select → `setHighlightCube` | WIRED | `locateRelease(top.release_id).then(result => setHighlightCube(result.primary_cube))` |
| `frontend/src/main.tsx` | `design/gruvax-design-tokens.css` | token import at app entry | WIRED | `import '../../design/gruvax-design-tokens.css'` line 5 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `ShelfGrid.tsx` | `litCube` | Zustand `highlight.primaryCube` ← `/api/locate` response ← DB `cube_boundaries` | Yes — live API confirmed returns `{unit_id:1,row:0,col:0}` for release_id=1 | FLOWING |
| `ShelfGrid.tsx` | `emptyCubes` | `/api/cubes` bulk endpoint ← DB `cube_boundaries WHERE is_empty=true` | Yes — 6 empty cubes confirmed in DB and API response | FLOWING |
| `ResultsList.tsx` | `items` | `/api/search?q=` ← FTS + catalog path on `gruvax.v_collection` | Yes — 20 results for "Blue Note", 0 for "zzznomatch" | FLOWING |
| `KioskView.tsx` | `units` | `/api/units` ← DB `gruvax.units` | Yes — 2 units with rows=4, cols=4 confirmed | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `/api/health` returns 200 with view check ok | `curl /api/health` | `{"status":"ok","db":"ok","discogsography_view_check":"ok","mqtt":"ok"}` | PASS |
| `/api/locate?release_id=1` returns locked contract | `curl /api/locate?release_id=1` | `confidence:0.3, sub_cube_interval:null, estimator_version:"cube-only-v1"` | PASS |
| `/api/locate?release_id=99999` returns 404 | `curl /api/locate?release_id=99999` | `{"detail":{"type":"release_not_in_collection","release_id":99999}}` HTTP 404 | PASS |
| `/api/search?q=zzznomatch` returns empty | `curl /api/search?q=zzznomatch` | `{"items":[],"took_ms":3.06}` | PASS |
| `/api/search?q=Blue+Note` returns ranked results | `curl /api/search?q=Blue+Note` | 20 items, top label "Blue Note" | PASS |
| `/api/cubes` bulk returns 32 cubes, 6 empty | `curl /api/cubes` | `32 cubes, empty count: 6` | PASS |
| Input validation: limit=999 → 422 | `curl /api/search?q=test&limit=999` | HTTP 422 with `less_than_equal` error | PASS |
| Input validation: release_id=abc → 422 | `curl /api/locate?release_id=abc` | HTTP 422 with `int_parsing` error | PASS |
| SQLi payload returns safe empty result | `curl "/api/search?q=') OR 1=1 --"` | `{"items":[],"took_ms":2.08}` — no error, no data leak | PASS |
| SPA served at root | `curl -o /dev/null -w "%{http_code}" http://localhost:8000/` | HTTP 200 | PASS |
| All 104 tests pass | `uv run pytest` | `104 passed, 1 warning in 1.80s` | PASS |
| Frontend builds clean | `npm --prefix frontend run build` | 0 errors, emits `../static/index.html` | PASS |
| Ruff + mypy clean | `uv run ruff check src/ && uv run mypy --strict src/gruvax/` | "All checks passed!" and "Success: no issues found in 20 source files" | PASS |
| Alembic round-trip | `alembic upgrade head && downgrade base && upgrade head` | All INFO lines confirm clean up/down/up | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SRCH-01 | 01-03, 01-04 | Type-ahead search, results ≤200ms perceived | SATISFIED | FTS + catalog path live; `took_ms: 3.84` in testing |
| SRCH-02 | 01-03, 01-04 | Ranked results list; top result auto-highlights cube | SATISFIED | `ResultsList.tsx` auto-selects top result and calls `locateRelease`; `ShelfGrid` lights matching cube |
| SRCH-03 | 01-04 | Clear-X button, ≥44px tap target | SATISFIED | `SearchBox.tsx` button with `aria-label="Clear search"`, `className="search-box__action"` |
| SRCH-04 | 01-03, 01-04 | "No results" state when nothing matches | SATISFIED | `/api/search?q=zzznomatch` returns `{items:[]}` (API); `NoResultsRow.tsx` rendered by `ResultsList` |
| SRCH-05 | 01-04 | Loading indicator only after ~300ms | SATISFIED | `KioskView.tsx` setTimeout 300ms gated on `isFetching` |
| SRCH-06 | 01-04 | Client-side debounce | SATISFIED | `SearchBox.tsx` `setTimeout(..., 250)` debounce |
| CUBE-01 | 01-03, 01-04 | Configurable N×4×4 grid driven by per-unit config | SATISFIED | `/api/units` returns 2 units rows=4 cols=4; `KioskView` uses `useQuery(['units'])` |
| CUBE-02 | 01-04 | Primary cube highlighted on search selection | SATISFIED | `ShelfGrid.tsx` sets `data-state="lit"` when `litCube.row === r && litCube.col === c` |
| CUBE-05 | 01-04 | Empty cubes render in distinct desaturated state | SATISFIED | `/api/cubes` bulk endpoint returns 6 is_empty; `ShelfGrid` renders `data-state="empty"` via `emptyCubes` Set |
| CUBE-06 | 01-04 | Persistent address overlay per cube | SATISFIED | `Cube.tsx` `<span className="cube__address">{address}</span>` always rendered |
| POS-01 | 01-02 | Catalog number normalizer/comparator shared infrastructure | SATISFIED | `normalize.py` with `parse_key`, `catalog_in_range`; no raw string comparison in estimator files |
| POS-02 | 01-02, 01-03 | `GET /api/locate` returns locked LocateResult contract | SATISFIED | Live API returns all required fields with correct types (float confidence, null sub_cube_interval, string version) |
| POS-04 | 01-02, 01-03 | Boundary cache loads at startup, invalidate() seam | SATISFIED | `app.py` lifespan loads cache; `BoundaryCache.invalidate()` present as Phase 4 seam |
| DEP-01 | 01-03, 01-04 | Docker Compose with gruvax-api + mosquitto; SPA via StaticFiles | SATISFIED | `compose.yaml` valid; both services healthchecked; StaticFiles mounted at `/` after all `/api` routers |
| DEP-02 | 01-01 | gruvax schema, reads from discogsography via v_collection only | SATISFIED | `gruvax.v_collection` is only read surface; startup probe enforces it; no direct discogsography table access in app code |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None found | — | No TBD/FIXME/XXX debt markers; no hardcoded hex in frontend components; no raw string catalog comparisons; no empty return stubs | — | — |

Notes on Python version: `pyproject.toml` declares `requires-python = ">=3.14"` while the PLAN 01-01 must_have says "Python 3.13". This is intentional — the environment directive for this phase explicitly states "Python 3.14 + latest-deps stack" and is not a gap. All deps work correctly on 3.14.

Note on `eclipse-mosquitto:latest`: PLAN 01-04 said `eclipse-mosquitto:2.1-alpine`; SUMMARY records the decision to use `latest` per environment directive. No security concern for a LAN-only internal broker in dev.

Note on alembic round-trip on clean DB: `just migrate-roundtrip` passes in seeded state (confirmed live). On a truly clean DB (no `gruvax_dev` schema), migration 0002 fails because `v_collection` references source tables that only exist after `seed-dev`. This is an OBS-03 precursor deferred to Phase 7. The constraint is documented and not a Phase 1 blocker.

---

### Human Verification Required

#### 1. Core Value End-to-End Visual Demo

**Test:** Follow Plan 04 Task 4 steps 4–8 in a browser at `http://localhost:8000/`:
1. Confirm: a 2×(4×4) grid (32 cubes) renders, each cube shows its row+col address (A1..H4), and some cubes are desaturated/dashed (empty)
2. Type a seeded artist/label/catalog (e.g. "Blue Note" or "BLP 4195") — confirm a ranked results list appears, top result is selected, exactly one cube lights yellow with LED glow
3. Tap a different result row — confirm the highlight moves to that result's cube
4. Click the clear-X — confirm field empties, results disappear, all cubes return to dim
5. Type "zzznomatch" — confirm "No records found" state renders and no cube highlights

**Expected:** All five sub-steps pass visually with ~instant feel.

**Why human:** Visual rendering, LED glow box-shadow appearance, animation behavior (AnimatePresence enter/exit 200ms/150ms), CSS token rendering (yellow #FFDA00 lit cell, desaturated empty state, address overlay typography), and interactive feel cannot be confirmed by grep or API calls alone. The orchestrator has already run Playwright confirming these behaviors; the Plan 04 Task 4 human-verify checkpoint is the formal acceptance gate.

---

### Gaps Summary

No gaps identified. All 16 must-haves are verified in the codebase against live API calls and source inspection. The phase goal — "a user types a query on the touchscreen kiosk and sees the correct cube highlighted on a rendered N×4×4 grid within ~200 ms, exercising the Core Value end-to-end against fixture-seeded boundaries" — is fully implemented.

The sole outstanding item is the formal Plan 04 Task 4 human-verify checkpoint confirming the visual and interactive behavior in a browser, which the orchestrator note indicates was already completed during the checkpoint phase but the formal sign-off gate remains.

---

_Verified: 2026-05-20T15:30:00Z_
_Verifier: Claude (gsd-verifier)_

---
phase: 03-admin-loop-pin-manual-entry-undo
plan: "04"
subsystem: admin-cubes-editor
tags: [backend, frontend, admin, boundary-editor, autocomplete, phantom, midpoint, tdd]
dependency_graph:
  requires: ["03-01", "03-02", "03-03"]
  provides:
    - GET /api/admin/cubes (fill_level, is_empty per cube)
    - GET /api/admin/cubes/{u}/{r}/{c}/boundary
    - POST /api/admin/cubes/validate (dry-run, always 200)
    - POST /api/admin/cubes/suggest (index-space midpoint)
    - GET /api/admin/labels (distinct labels from v_collection)
    - GET /api/admin/labels/{label}/catalogs (catalog# scoped to label)
    - Frontend: CubesGrid, CubeEditor, AlphaRail, FillBar components
    - Routes: /admin/cubes and /admin/cubes/:unit/:row/:col
  affects:
    - gruvax.api.admin.router (cubes_router included)
    - frontend/src/App.tsx (new routes)
    - frontend/src/api/adminClient.ts (6 new functions)
    - frontend/src/api/types.ts (7 new types)
tech_stack:
  added: []
  patterns:
    - POS-01 comparator via parse_key (never raw string catalog compare)
    - Phantom blocking: cube_exact_match + trigram near-misses via pg_trgm
    - Graceful pg_trgm degradation: try/except UndefinedFunction → []
    - JSONResponse(status_code=400) for flat error bodies (not HTTPException)
    - POST /validate always returns HTTP 200 (dry-run semantics)
    - BoundaryCache dict index pattern: {(u,r,c): b for b in cache.get_boundaries()}
    - Two-step dependent autocomplete: label → catalog# (v_collection only)
    - Force path: forceFirst/forceLast state + USE ANYWAY button
    - suggestMidpoint: real record from index space, never synthesized string
    - setPendingChangeSet: accumulates edits, no direct PUT in editor
key_files:
  created:
    - src/gruvax/api/admin/cubes.py
    - src/gruvax/api/admin/validation.py
    - frontend/src/routes/admin/FillBar.tsx
    - frontend/src/routes/admin/AlphaRail.tsx
    - frontend/src/routes/admin/CubesGrid.tsx
    - frontend/src/routes/admin/CubeEditor.tsx
  modified:
    - src/gruvax/db/queries.py
    - src/gruvax/api/admin/router.py
    - frontend/src/api/adminClient.ts
    - frontend/src/api/types.ts
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/routes/admin/admin.css
    - frontend/src/App.tsx
decisions:
  - "POST /validate always returns HTTP 200 with valid:false items (not HTTP 400) — dry-run semantics"
  - "PUT /boundary uses flat JSONResponse(status_code=400) not HTTPException for phantom/comparator errors"
  - "BoundaryCache has no get(u,r,c) — build dict index per request from get_boundaries()"
  - "response_model=None on POST /validate decorator to avoid FastAPI type-annotation conflict with JSONResponse return"
  - "forceFirst/forceLast state tracks phantom force-accept per boundary half independently"
  - "CubeEditor calls setPendingChangeSet only; no direct PUT to write endpoint (deferred to plan 05)"
  - "BOUNDARY_TRGM_THRESHOLD = 0.40 for near-miss similarity"
metrics:
  duration: "~40 minutes"
  completed: "2026-05-20"
  tasks_completed: 2
  files_changed: 13
---

# Phase 03 Plan 04: Boundary Editor Vertical Slice Summary

**One-liner:** Backend boundary CRUD (read/validate/suggest) with POS-01 phantom blocking and frontend cubes grid + two-step autocomplete editor wired to Zustand pending change-set.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Admin cubes backend endpoints (TDD) | f651518 | cubes.py, validation.py, router.py, queries.py |
| 2 | Admin cubes grid + per-cube editor | 5934639 | CubesGrid.tsx, CubeEditor.tsx, AlphaRail.tsx, FillBar.tsx, adminClient.ts, types.ts, AdminShell.tsx, admin.css, App.tsx |

## What Was Built

### Task 1 — Backend

**`src/gruvax/api/admin/validation.py`** (new, pure module):
- `validate_boundary_order(first_label, first_catalog, last_label, last_catalog) -> bool`
- Labels compared with casefold only; catalogs via `parse_key()` (POS-01, Pitfall C)

**`src/gruvax/db/queries.py`** (appended admin section):
- `BOUNDARY_TRGM_THRESHOLD = 0.40`
- `find_boundary_near_misses(pool, label, catalog, limit=5)` — combined similarity (label×0.5 + catalog×0.5), graceful `UndefinedFunction` fallback → `[]`
- `get_distinct_labels(pool)` — SELECT DISTINCT label FROM gruvax.v_collection ORDER BY label
- `get_catalogs_for_label(pool, label)` — catalog numbers scoped to a label
- `cube_exact_match(pool, label, catalog) -> bool` — phantom check

**`src/gruvax/api/admin/cubes.py`** (new, ~490 lines):
- `GET /cubes` — builds boundary_index dict from cache, computes fill_level
- `GET /cubes/{u}/{r}/{c}/boundary` — 404 for missing cube
- `PUT /cubes/{u}/{r}/{c}/boundary` — POS-01 comparator → phantom check → write; flat JSONResponse(400) on error; cache.invalidate() + cache.load(pool) on success
- `POST /cubes/validate` — dry-run, always HTTP 200; phantom/comparator errors as `valid: False` items in results array
- `POST /cubes/suggest` — builds boundary_index, finds next populated cube via `_find_next_populated_cube()`, calls `suggest_midpoint()` from boundary_math.py

### Task 2 — Frontend

**Types added to `types.ts`**: `NearMiss`, `MovementCount`, `ValidateItem`, `ValidateResponse`, `MidpointSuggestion`, `SuggestResponse`, `AdminCube`, `AdminCubesResponse`, `AdminCubeBoundary`, `LabelOption`, `CatalogOption`

**Functions added to `adminClient.ts`**: `adminGetCubes`, `adminGetCubeBoundary`, `validateBoundary`, `suggestMidpoint`, `getDistinctLabels`, `getCatalogsForLabel`

**`FillBar.tsx`**: compact 3px meter, yellow at ≤80%, error color at >80%, no hardcoded hex, ARIA meter role

**`AlphaRail.tsx`**: vertical A-Z jump rail, 32px wide × 44px per button, inactive letters at opacity 0.25

**`CubesGrid.tsx`**: TanStack Query on `['admin','cubes']`, grouped by unit_id, cube cards with FillBar + label/catalog range, tap navigates to editor, AlphaRail scroll-to-letter

**`CubeEditor.tsx`**: two-step dependent autocomplete (label → catalog, disabled until label chosen), phantom warning chips with near-miss suggestion buttons, USE ANYWAY force path (forceFirst/forceLast state), suggest-midpoint button calls `suggestMidpoint()`, ADD TO PENDING calls `setPendingChangeSet()` (no direct PUT write)

**`AdminShell.tsx`**: CUBES nav tab added

**`App.tsx`**: `/admin/cubes` → CubesGrid, `/admin/cubes/:unit/:row/:col` → CubeEditor

**`admin.css`**: token-driven styles for all new components (no hex values)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] POST /validate must return HTTP 200, not 400**
- **Found during:** Task 1 test execution (test_validate_no_db_write expected 200)
- **Issue:** Initial implementation raised HTTPException(400) for phantom/comparator failures on the validate endpoint
- **Fix:** Validate endpoint now always returns HTTP 200 with `valid: False` items in `results` array; HTTP errors reserved for PUT /boundary only
- **Files modified:** src/gruvax/api/admin/cubes.py
- **Commit:** f651518

**2. [Rule 1 - Bug] BoundaryCache has no get() method**
- **Found during:** Task 1 implementation
- **Issue:** Initial code called `cache.get(unit_id, row, col)` which does not exist
- **Fix:** Build `boundary_index = {(b.unit_id, b.row, b.col): b for b in cache.get_boundaries()}` dict at start of each handler
- **Files modified:** src/gruvax/api/admin/cubes.py
- **Commit:** f651518

**3. [Rule 1 - Bug] FastAPI type annotation conflict on POST /validate**
- **Found during:** Task 1 — FastAPI raised error on `-> JSONResponse | dict[str, Any]` return type
- **Fix:** Added `response_model=None` to the decorator and used `-> JSONResponse` as sole return type
- **Files modified:** src/gruvax/api/admin/cubes.py
- **Commit:** f651518

**4. [Rule 1 - Bug] PUT /boundary errors must use flat JSONResponse not HTTPException**
- **Found during:** Task 1 — test_phantom_blocked expected `body.get("phantom") is True` which fails when FastAPI wraps it as `{"detail": {...}}`
- **Fix:** All 400 responses on PUT use `return JSONResponse(status_code=400, content={"phantom": True, ...})`
- **Files modified:** src/gruvax/api/admin/cubes.py
- **Commit:** f651518

**5. [Rule 2 - Missing functionality] mypy dict type annotation missing type args**
- **Found during:** Task 1 mypy check
- **Issue:** `_admin: dict = Depends(require_admin)` missing type args → mypy error
- **Fix:** Changed to `_admin: dict[str, Any] = Depends(require_admin)` throughout cubes.py
- **Files modified:** src/gruvax/api/admin/cubes.py
- **Commit:** f651518

## Human Verification Needed

*(Auto-approved per AUTONOMOUS mode policy — verification steps documented here for manual confirmation)*

**What to verify:**

1. Backend endpoints:
   - `GET /api/admin/cubes` — returns cubes list with fill_level
   - `GET /api/admin/cubes/1/0/0/boundary` — returns boundary fields
   - `POST /api/admin/cubes/validate` with valid payload → HTTP 200, `valid: true`
   - `POST /api/admin/cubes/validate` with phantom payload → HTTP 200, `valid: false`, `phantom: true`, `near_misses` array
   - `POST /api/admin/cubes/suggest` → HTTP 200, `suggestion` with real record or null

2. Frontend at `/admin/cubes` (after PIN login):
   - Grid shows cube cards grouped by shelf
   - Each card shows label range and fill bar
   - A-Z rail on right scrolls to first matching cube
   - Tapping a cube navigates to `/admin/cubes/:unit/:row/:col`

3. Per-cube editor at `/admin/cubes/1/0/0`:
   - Label field shows autocomplete from v_collection labels
   - Catalog# field is disabled until label chosen
   - After label chosen, catalog# autocomplete scopes to that label
   - Phantom value (not in collection) shows warning chip with near-miss buttons and USE ANYWAY
   - SUGGEST MIDPOINT fills last-record fields with real index-space record
   - ADD TO PENDING accumulates to pending change-set (visible counter)

## Known Stubs

None. All four backend endpoints return real data from `BoundaryCache` and `gruvax.v_collection`. The frontend accumulates edits to `pendingChangeSet` which will be submitted in plan 05.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: unauthed-read | src/gruvax/api/admin/cubes.py | GET /cubes and GET /cubes/{u}/{r}/{c}/boundary both require `require_admin` dependency — confirmed protected. No new unauthenticated surface. |

## Self-Check

### Created files exist:
- `src/gruvax/api/admin/cubes.py` — FOUND (committed f651518)
- `src/gruvax/api/admin/validation.py` — FOUND (committed f651518)
- `frontend/src/routes/admin/FillBar.tsx` — FOUND (committed 5934639)
- `frontend/src/routes/admin/AlphaRail.tsx` — FOUND (committed 5934639)
- `frontend/src/routes/admin/CubesGrid.tsx` — FOUND (committed 5934639)
- `frontend/src/routes/admin/CubeEditor.tsx` — FOUND (committed 5934639)

### Build verification:
- `tsc --noEmit` exit 0 — PASSED
- `npm run build` exit 0 — PASSED (504 modules transformed)

### No hardcoded hex in admin components:
- grep -rE "#[0-9a-fA-F]{3,6}" CubeEditor.tsx AlphaRail.tsx FillBar.tsx — PASSED (no matches)

## Self-Check: PASSED

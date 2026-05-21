---
phase: 03-admin-loop-pin-manual-entry-undo
plan: "03"
subsystem: kiosk-reveal
tags: [fill-level, cube-contents, kiosk, public-api, tanstack-query, zustand, css-tokens]

dependency_graph:
  requires:
    - "03-01"  # boundary_math.py: count_records_in_boundary, sample_records
    - "03-02"  # adminStore: isLoggedIn for D-16 EDIT THIS CUBE shortcut
  provides:
    - "GET /api/cubes/{u}/{r}/{c} extended: fill_level + total_count + sample_records"
    - "GET /api/cubes bulk extended: fill_level per cube for grid rendering"
    - "FillBar.tsx: token-driven fill indicator (CUBE-07)"
    - "CubeContentsPanel.tsx: bottom-sheet reverse-lookup panel (CUBE-09)"
    - "cubeTypes.ts: SampleRecord, CubeContentsResponse, CubeBoundaryWithFill"
  affects:
    - "03-04"  # admin cubes grid (CubesGrid.tsx) reuses FillBar and cubeTypes

tech-stack:
  added: []
  patterns:
    - "get_records_in_boundary() helper: count + sample share one O(n) snapshot pass"
    - "Bulk /api/cubes endpoint extended with fill_level (no extra DB calls, snapshot only)"
    - "CubeBoundaryWithFill type in cubeTypes.ts (separate from types.ts — ownership isolation)"
    - "useAdminStore(s => s.isLoggedIn) for D-16 admin shortcut in kiosk panel"
    - "Bottom-sheet panel: position:fixed, slide-up animation, scrim dismiss"
    - "CSS token fill bar colors: blue-light / yellow / error per threshold"

key-files:
  created:
    - frontend/src/api/cubeTypes.ts
    - frontend/src/routes/kiosk/FillBar.tsx
    - frontend/src/routes/kiosk/CubeContentsPanel.tsx
  modified:
    - src/gruvax/api/units.py
    - src/gruvax/estimator/boundary_math.py
    - frontend/src/api/client.ts
    - frontend/src/routes/kiosk/Cube.tsx
    - frontend/src/routes/kiosk/ShelfGrid.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css

decisions:
  - "get_records_in_boundary() extracted from count_records_in_boundary() so count + sample share one O(n) pass — avoids iterating snapshot twice per request (T-03-12)"
  - "Bulk /api/cubes extended to return fill_level — avoids N per-cube requests on grid load; fill bars animate in on page load from single bulk response"
  - "CubeBoundaryWithFill defined in cubeTypes.ts (plan-03-owned) rather than extending types.ts (plan-02/04-owned) — exclusive file-ownership preserved for wave-parallel execution"
  - "useAdminStore (adminStore.ts) used for isLoggedIn in CubeContentsPanel — plan 02 split admin state into a separate store; plan 03 reads it without modifying"
  - "fetchCubesWithFill and fetchCubeContents both call existing /api/cubes endpoints — no new backend routes added"

metrics:
  duration: ~90min
  completed: "2026-05-21"
  tasks_completed: 2
  tests_verified: 9  # 3 integration (backend) + 6 vitest (frontend)
---

# Phase 3 Plan 03: Kiosk Reveal — Fill Bars + Cube Contents Panel Summary

**Per-cube fill-level bars (CUBE-07) and tap-to-reveal cube contents panel (CUBE-09) delivered as a public kiosk feature: backend endpoint extended with fill_level/total_count/sample_records, FillBar and CubeContentsPanel components wired into the kiosk grid.**

## Performance

- **Duration:** ~90 min
- **Completed:** 2026-05-21
- **Tasks:** 2 (+ auto-passed human-verify checkpoint)
- **Files modified:** 9 (2 Python, 7 TypeScript/CSS)

## Accomplishments

- `GET /api/cubes/{u}/{r}/{c}` extended (no new endpoint): returns `fill_level`, `total_count`, and `sample_records` computed from the in-memory snapshot (no DB during compute, D-13/D-14). Endpoint stays PUBLIC per D-15.
- `GET /api/cubes` bulk endpoint extended to also return `fill_level` per cube — enables grid fill bars without N per-cube requests.
- `boundary_math.py`: extracted `get_records_in_boundary()` helper so `count_records_in_boundary` and `sample_records` share one O(n) snapshot pass per request.
- `cubeTypes.ts` (new, plan-03-owned): `SampleRecord`, `CubeContentsResponse`, `CubeBoundaryWithFill`, `CubesWithFillResponse` — isolated from `types.ts` to preserve exclusive file-ownership with plans 02/04.
- `FillBar.tsx`: presentational bar, token-driven colors (blue-light / yellow / error), no hardcoded hex.
- `CubeContentsPanel.tsx`: bottom-sheet panel with TanStack Query, first/last records, count + fill%, ~7 sampled records, empty-state copy, D-16 admin shortcut.
- `Cube.tsx`, `ShelfGrid.tsx`, `KioskView.tsx`: fill bars and cube-tap interaction wired end-to-end.
- `kiosk.css`: fill-bar + panel styles added (tokens only, no hex).

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend GET /api/cubes/{u}/{r}/{c} with fill level, count, sampled records | `17be39c` | units.py, boundary_math.py |
| 2 | FillBar + CubeContentsPanel + kiosk grid wiring + cube-tap interaction | `c52bc62` | 9 files (7 TS/CSS + units.py extended bulk) |

## Verification Results

**Backend:**
- `uv run pytest tests/integration/test_cube_public.py -q` — **3 passed**
- `uv run ruff check src/gruvax/api/units.py src/gruvax/estimator/boundary_math.py` — **All checks passed**
- `uv run mypy src/gruvax/api/units.py src/gruvax/estimator/boundary_math.py` — **Success: no issues**

**Frontend:**
- `cd frontend && npx tsc --noEmit` — **0 errors**
- `cd frontend && npm run build` — **built in 194ms**
- `cd frontend && npx vitest run` — **6 passed (ShelfGrid.test.tsx 6/6)**

## Deviations from Plan

### Auto-added Functionality

**1. [Rule 2 - Missing Critical Functionality] Bulk /api/cubes extended with fill_level**

- **Found during:** Task 2 implementation
- **Issue:** The plan's Task 2 action says "prefer reusing existing cubes data and fetching full content on tap" and "thread a per-cube fillLevel from the existing /api/cubes bulk data". However, the existing bulk endpoint only returned `{unit_id, row, col, is_empty}` — no `fill_level`. Without fill_level in the bulk response, the grid fill bars (CUBE-07) couldn't render without N individual per-cube requests on page load.
- **Fix:** Extended `GET /api/cubes` bulk endpoint to compute and return `fill_level` for each cube using the in-memory snapshot (same pattern as the individual endpoint). Added `BoundaryCache` + `CollectionSnapshot` deps. No DB calls during compute.
- **Impact:** `CubeBoundaryWithFill` and `CubesWithFillResponse` types added to `cubeTypes.ts`; `fetchCubesWithFill()` added to `client.ts`; `KioskView` uses `fetchCubesWithFill` instead of `fetchCubes`.
- **Files modified:** `src/gruvax/api/units.py`, `frontend/src/api/cubeTypes.ts`, `frontend/src/api/client.ts`, `frontend/src/routes/kiosk/KioskView.tsx`
- **Commits:** `c52bc62`

**2. [Rule 2 - Missing Critical Functionality] get_records_in_boundary() helper extracted**

- **Found during:** Task 1 implementation
- **Issue:** `count_records_in_boundary()` and `sample_records()` would each need to iterate the snapshot separately if not sharing a single pass. The plan mentions "factor out a `get_records_in_boundary` helper if needed so count + sample share one pass."
- **Fix:** Extracted `get_records_in_boundary()` in `boundary_math.py`; refactored `count_records_in_boundary()` to delegate to it (`return len(get_records_in_boundary(...))`). All existing unit tests still pass.
- **Files modified:** `src/gruvax/estimator/boundary_math.py`
- **Commits:** `17be39c`

## Known Stubs

None — all data flows are wired end-to-end. The panel fetches live data from the extended endpoint.

## Human Verification Needed

(Auto-passed per autonomous checkpoint policy — human verification to be completed manually)

1. **Fill bars on kiosk grid:** Open kiosk view. Verify cubes with boundary data show a fill bar at the bottom edge. Check:
   - Cubes under 80% full: blue-light bar
   - Cubes 80-100% full: yellow bar
   - Cubes over 100%: red/error bar
   - is_empty cubes: no bar

2. **Cube tap opens panel:** Tap a populated cube. Verify the panel slides up from the bottom showing:
   - "CUBE B2" (or correct address) heading in blue Barlow Condensed
   - "{N} RECORDS · {%}% FULL" in DM Mono
   - Fill bar in the panel
   - FIRST and LAST boundary records
   - ~7 evenly-sampled records with catalog# and label
   - No bar for is_empty cubes

3. **Empty cube panel:** Tap an empty/unset cube. Verify "No records assigned to this cube yet." appears.

4. **Dismiss:** Tap outside the panel (scrim). Verify it closes.

5. **D-16 admin shortcut:** While logged in as admin, verify "EDIT THIS CUBE" link appears in the panel. While logged out, verify it is hidden.

6. **Pi 5 touch test:** Verify on the actual Pi 5 + 7" touchscreen that tap targets (cube cells) and the bottom sheet feel right at touch size.

## Threat Flags

None beyond what was already declared in the plan's threat model (T-03-10, T-03-11, T-03-12). The bulk endpoint extension uses the same in-memory snapshot path with no new SQL or trust-boundary crossings.

## Self-Check: PASSED

**Files exist:**
- `frontend/src/api/cubeTypes.ts` — FOUND
- `frontend/src/routes/kiosk/FillBar.tsx` — FOUND
- `frontend/src/routes/kiosk/CubeContentsPanel.tsx` — FOUND

**Commits exist:**
- `17be39c` — Task 1: extend GET /api/cubes/{u}/{r}/{c}
- `c52bc62` — Task 2: FillBar + CubeContentsPanel + wiring

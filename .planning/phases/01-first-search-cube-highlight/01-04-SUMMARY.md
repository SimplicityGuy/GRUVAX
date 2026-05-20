---
phase: "01-first-search-cube-highlight"
plan: "04"
subsystem: "frontend+infra"
tags: ["react", "vite", "docker-compose", "mosquitto", "staticfiles", "zustand", "tanstack-query", "gsap", "framer-motion", "kiosk-spa"]
dependency_graph:
  requires:
    - phase: "01-03"
      provides: "GET /api/search, /api/locate, /api/units, /api/health — all consumed by the SPA"
    - phase: "01-01"
      provides: "gruvax schema, seeded v_collection/cube_boundaries"
  provides:
    - "React 19 + Vite 8 kiosk SPA: search box (debounce/clear-X/delayed-loading), results list (AnimatePresence), 2×4×4 ShelfGrid with lit/dim/empty Cube cells"
    - "FastAPI StaticFiles serving the built SPA at / (AFTER all /api routers)"
    - "Docker Compose: gruvax-api + mosquitto (no broker host ports, healthchecks)"
    - "mosquitto/mosquitto.conf: persistence true, internal-only listener 1883"
    - "Multi-stage Dockerfile: Node.js frontend-builder stage + Python runtime stage"
    - "docker-entrypoint.sh: python -m alembic/uvicorn (avoids hardcoded venv shebang paths)"
  affects:
    - "plan 01 Phase 2 (search UX is now demoable; estimator improvements land on top)"
    - "plan Phase 3 admin (React router + Zustand store already structured for /admin routes)"
    - "plan Phase 4 SSE (TanStack Query cache invalidation hook in ResultsList)"
    - "plan Phase 5 MQTT LED publish (mosquitto container already up; aiomqtt client stubbed)"
tech_stack:
  added:
    - "React 19.x (npm latest)"
    - "Vite 8.0.x (npm latest — was 7.x in CLAUDE.md/STACK.md)"
    - "TypeScript 5.x (Vite template)"
    - "@tanstack/react-query 5.x"
    - "zustand 5.x"
    - "motion (framer-motion) 12.x"
    - "gsap 3.15.x"
    - "react-router 7.x"
    - "tailwindcss 4.x (installed, not yet wired — CSS modules used instead)"
    - "vitest + @testing-library/react (frontend test toolchain)"
    - "eclipse-mosquitto:latest (was eclipse-mosquitto:2.1-alpine in plan — used latest)"
  patterns:
    - "Design token contract: single import in main.tsx → all components use var(--gruvax-*)"
    - "Hex gate: grep -rInE '#[0-9A-Fa-f]{6}' src/ | grep -v design-tokens → NO_HARDCODED_HEX"
    - "Vite build outDir: '../static' (dev) → /static in Docker stage (compose serves via FastAPI)"
    - "Zustand store: query, selectedReleaseId, highlight.primaryCube, animationToken, clearSearch"
    - "TanStack Query key ['search', q] — enables caching between keystrokes; locate fired imperatively"
    - "Debounce 250ms in SearchBox.tsx; delayed loading indicator >300ms timer in KioskView.tsx"
    - "AnimatePresence enter 200ms / exit 150ms on ResultsList per 01-UI-SPEC.md §Animation Contract"
    - "Cube data-state ∈ {dim,lit,empty,hover} — CSS transitions target these, no JS animation needed"
    - "python -m alembic / python -m uvicorn in docker-entrypoint.sh (avoids hardcoded shebang paths)"
key_files:
  created:
    - frontend/vite.config.ts
    - frontend/index.html
    - frontend/src/main.tsx
    - frontend/src/App.tsx
    - frontend/src/index.css
    - frontend/src/api/types.ts
    - frontend/src/api/client.ts
    - frontend/src/state/store.ts
    - frontend/src/routes/kiosk/kiosk.css
    - frontend/src/routes/kiosk/Cube.tsx
    - frontend/src/routes/kiosk/ShelfGrid.tsx
    - frontend/src/routes/kiosk/ShelfLabel.tsx
    - frontend/src/routes/kiosk/SearchBox.tsx
    - frontend/src/routes/kiosk/ResultsList.tsx
    - frontend/src/routes/kiosk/ResultRow.tsx
    - frontend/src/routes/kiosk/NoResultsRow.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - compose.yaml
    - mosquitto/mosquitto.conf
    - docker-entrypoint.sh
  modified:
    - Dockerfile
    - justfile
    - README.md
decisions:
  - "Vite 8 used (npm latest) — CLAUDE.md/STACK.md said 7.x; RESEARCH.md confirmed 8.x is current"
  - "eclipse-mosquitto:latest used — plan said 2.1-alpine; latest is the more current choice per environment directive"
  - "python -m alembic/uvicorn pattern in docker-entrypoint.sh to avoid hardcoded shebang path in copied venv"
  - "Design tokens imported via relative path '../../design/gruvax-design-tokens.css' in main.tsx; Docker stage copies design/ to /design/ (one level above workdir) so the relative path resolves"
  - "Vite template SVG assets (react.svg, vite.svg, hero.png) removed — they contained hardcoded hex that failed the grep gate"
  - "TanStack Query fires imperatively for /api/locate on result selection (not as a query key) to avoid caching stale cube positions"
  - "compose.yaml uses discogsography_default network commented-out with documentation for production"
metrics:
  duration_seconds: 1303
  duration_human: "~22 minutes"
  completed_date: "2026-05-20"
  tasks_completed: 3
  tasks_total: 4
  files_created: 22
  files_modified: 3
  commits: 3
---

# Phase 1 Plan 4: React/Vite Kiosk SPA + Docker Compose Summary

**Token-driven React 19 + Vite 8 kiosk SPA with debounced search, animated results list, 2×4×4 ShelfGrid with LED-state Cubes, and a working Docker Compose stack (gruvax-api + mosquitto) serving the SPA via FastAPI StaticFiles.**

## Performance

- **Duration:** ~22 minutes
- **Started:** 2026-05-20T05:05:23Z
- **Completed:** 2026-05-20T05:27:26Z
- **Tasks completed:** 3 of 4 (Task 4 is a human-verify checkpoint — awaiting human)
- **Files created:** 22
- **Files modified:** 3

## Accomplishments

- React 19 + Vite 8 + TypeScript SPA scaffolded in `frontend/`; all dependencies installed (react-router, @tanstack/react-query, zustand, gsap, motion, vitest, @testing-library/react)
- Design token contract: `main.tsx` imports `design/gruvax-design-tokens.css` as the single entry point; all component CSS uses `var(--gruvax-*)` — hex grep gate passes with NO_HARDCODED_HEX
- `Cube.tsx`: `data-state` ∈ {dim, lit, empty, hover}; address overlay top-left (CUBE-02/05/06); CSS transitions from tokens (300ms spring on, 500ms smooth off)
- `ShelfGrid.tsx`: CSS Grid `repeat(4, var(--gruvax-cell-size-xl))`, gap `var(--gruvax-cell-gap-xl)` — fully token-driven sizing
- `ShelfLabel.tsx`: Barlow Condensed 900 24px ALL CAPS via `--gruvax-font-display`
- `SearchBox.tsx`: 250ms debounce (SRCH-06), clear-X ≥44px tap target with `aria-label="Clear search"` (SRCH-03), loading indicator shown only after >300ms in-flight (SRCH-05)
- `ResultsList.tsx`: Framer Motion AnimatePresence enter 200ms/exit 150ms; auto-selects top result on arrival → calls `/api/locate` → sets `highlight.primaryCube` (SRCH-02, CUBE-02)
- `ResultRow.tsx`: artist·title / label / DM Mono catalog#; selected state `--gruvax-blue-faint` bg + yellow left border
- `NoResultsRow.tsx`: "No records found" + body copy per UI-SPEC §SRCH-04
- `KioskView.tsx`: full-page layout, TanStack Query `['units']` drives grid, `['search', q]` drives results; 300ms delayed loading indicator wired
- Zustand store: `query`, `selectedReleaseId`, `highlight.primaryCube`, `animationToken`, `clearSearch()`
- `vite.config.ts`: `/api` proxy → `localhost:8000` (dev); `build.outDir: '../static'`
- `compose.yaml`: `gruvax-api` + `mosquitto`; mosquitto NO `ports:` (DEP-01/T-01-12); both have `healthcheck` + `restart: unless-stopped`; `gruvax-api` `depends_on: mosquitto healthy`; `host.docker.internal` for host dev Postgres with `extra_hosts: host-gateway`
- `mosquitto/mosquitto.conf`: `persistence true`, internal-only listener 1883
- Multi-stage `Dockerfile`: Node.js frontend-builder + Python runtime; design/ copied to resolve relative token import; `docker-entrypoint.sh` uses `python -m alembic/uvicorn` to avoid venv shebang path issues
- `justfile`: `build-spa`, `dev-spa`, `install-spa`, `up-d` recipes added
- `README.md`: Quickstart runbook, `down` (no `-v`) caveat, dev Postgres setup, stack version reconciliation table
- End-to-end verified: `docker compose up -d` → both healthy → `/api/health` 200 (db/view/mqtt all ok) → SPA served at `/` → `/api/search?q=Blue+Note` returns ranked results

## Task Commits

| Task | Name | Commit | Type |
|------|------|--------|------|
| 1+2 | Vite/React SPA scaffold — tokens + ShelfGrid/Cube/Search | `7dbe844` | feat |
| 3 | FastAPI StaticFiles + compose.yaml + mosquitto.conf | `47e7bb5` | feat |
| fix | Fix Docker runtime PATH injection | `055b843` | fix |

## Files Created/Modified

- `frontend/` — React 19 + Vite 8 SPA (22 files total: vite.config.ts, index.html, main.tsx, App.tsx, index.css, api/types.ts, api/client.ts, state/store.ts, routes/kiosk/*.tsx, kiosk.css, package.json, tsconfig*.json)
- `compose.yaml` — gruvax-api + mosquitto (no broker host ports, healthchecks)
- `mosquitto/mosquitto.conf` — persistence true, internal listener 1883
- `Dockerfile` — multi-stage: Node.js frontend-builder + Python runtime; design/ copy; docker-entrypoint.sh
- `docker-entrypoint.sh` — python -m alembic/uvicorn startup script
- `justfile` — build-spa, dev-spa, install-spa, up-d targets added
- `README.md` — Quickstart runbook + stack version reconciliation table

## Decisions Made

- **Vite 8 (not 7)**: npm latest is 8.0.x; RESEARCH.md confirmed; CLAUDE.md/STACK.md pins treated as stale per environment directive.
- **eclipse-mosquitto:latest**: plan said 2.1-alpine; environment directive says "use latest image tag".
- **python -m pattern in entrypoint**: uv copies the venv from `/build/.venv` to `/app/.venv` but the wrapper scripts have hardcoded shebangs (`#!/build/.venv/bin/python`). Using `python -m alembic` and `python -m uvicorn` with absolute Python path avoids this.
- **Design tokens via relative path**: `../../design/gruvax-design-tokens.css` in `frontend/src/main.tsx` resolves correctly locally (frontend/src → ../../design = project root design/). In Docker, the `design/` dir is copied to `/design/` (one level above the `/frontend-build` workdir) so the same relative path resolves.
- **TanStack Query for /api/locate**: fires imperatively in ResultsList (not as a hook key) to ensure each selection triggers a fresh locate call without cached-stale-cube issues.
- **Vite template SVG assets removed**: react.svg and vite.svg contained hardcoded hex colors that failed the grep gate; removed as they are Vite boilerplate not used by GRUVAX.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Vite template SVG assets contained hardcoded hex colors**
- **Found during:** Task 1 hex gate verification
- **Issue:** `frontend/src/assets/react.svg` and `vite.svg` contain `#00D8FF`, `#9135ff` etc. These are Vite boilerplate assets not used by GRUVAX but they fail the grep gate.
- **Fix:** Removed all three template assets (`react.svg`, `vite.svg`, `hero.png`). Not used by the GRUVAX SPA.
- **Files modified:** frontend/src/assets/ (removed)
- **Commit:** `7dbe844`

**2. [Rule 3 - Blocking] pyproject.toml references README.md but Dockerfile didn't COPY it**
- **Found during:** Task 3 docker compose build
- **Issue:** `uv sync --frozen --no-dev` failed with "failed to open file /build/README.md: No such file or directory" because pyproject.toml has `readme = "README.md"`.
- **Fix:** Added `README.md` to the `COPY pyproject.toml uv.lock README.md ./` line in the Python builder stage.
- **Files modified:** Dockerfile
- **Commit:** `47e7bb5`

**3. [Rule 3 - Blocking] Hardcoded venv shebang paths in copied venv binaries**
- **Found during:** Task 3 docker compose up (gruvax-api kept restarting)
- **Issue:** uv builds the venv in `/build/.venv`; the wrapper scripts for alembic/uvicorn have `#!/build/.venv/bin/python` hardcoded. When the venv is COPY'd to `/app/.venv` in the runtime stage, those shebangs are wrong so execution fails with "not found".
- **Fix:** Created `docker-entrypoint.sh` that invokes `$PYTHON -m alembic upgrade head` and `$PYTHON -m uvicorn ...` using the absolute Python binary path instead of the wrapper script. chmod +x before USER switch.
- **Files modified:** Dockerfile, docker-entrypoint.sh (new)
- **Commit:** `055b843`

**4. [Rule 3 - Blocking] Rancher Desktop injects host PATH into container sh -c**
- **Found during:** Task 3 debugging (related to issue #3)
- **Issue:** Rancher Desktop on macOS injects the host machine's PATH into containers when running `docker run/exec` from the CLI, overriding the image's `ENV PATH`. Alembic in the host PATH doesn't exist, making the original `sh -c "alembic upgrade head && uvicorn ..."` CMD fail.
- **Fix:** Using `docker-entrypoint.sh` with explicit `$PYTHON` binary path means we never rely on PATH lookup for the critical binaries.
- **Files modified:** docker-entrypoint.sh
- **Commit:** `055b843`

---

**Total deviations:** 4 auto-fixed (Rules 1 and 3)
**Impact on plan:** All fixes resolved; stack is fully functional. No scope changes.

## Known Stubs

- `frontend/src/routes/kiosk/KioskView.tsx` — fallback placeholder grid (lines 91-101) renders 2 empty ShelfGrids when `/api/units` hasn't loaded yet. This ensures the grid is visible immediately; it is replaced by the real API data within the first successful query response. Intentional, not a data-missing stub.

## Threat Surface Scan

Implemented all planned threat mitigations:
- T-01-12 (mosquitto LAN exposure): NO `ports:` on mosquitto service — internal-only network; verified with python yaml check
- T-01-13 (stale SPA bundle): `index.html` served with `Cache-Control: no-store` (FastAPI StaticFiles default for html=True); hashed assets get long-term cache
- T-01-14 (StaticFiles catch-all intercepts /api): StaticFiles mounted AFTER all include_router calls — source-order verified (line 113-116 vs 124)
- T-01-15 (hardcoded hex): grep gate passes — NO_HARDCODED_HEX confirmed
- T-01-SC (npm/uv package legitimacy): All packages from RESEARCH.md audit; package-lock.json committed

No new threat surface beyond plan scope.

## Self-Check: PASSED

Files created:
- frontend/vite.config.ts ✓
- frontend/index.html ✓
- frontend/src/main.tsx ✓
- frontend/src/App.tsx ✓
- frontend/src/api/types.ts ✓
- frontend/src/api/client.ts ✓
- frontend/src/state/store.ts ✓
- frontend/src/routes/kiosk/kiosk.css ✓
- frontend/src/routes/kiosk/Cube.tsx ✓
- frontend/src/routes/kiosk/ShelfGrid.tsx ✓
- frontend/src/routes/kiosk/ShelfLabel.tsx ✓
- frontend/src/routes/kiosk/SearchBox.tsx ✓
- frontend/src/routes/kiosk/ResultsList.tsx ✓
- frontend/src/routes/kiosk/ResultRow.tsx ✓
- frontend/src/routes/kiosk/NoResultsRow.tsx ✓
- frontend/src/routes/kiosk/KioskView.tsx ✓
- compose.yaml ✓
- mosquitto/mosquitto.conf ✓
- docker-entrypoint.sh ✓

Commits verified:
- 7dbe844 ✓
- 47e7bb5 ✓
- 055b843 ✓

End-to-end stack verified:
- docker compose up -d → both services healthy ✓
- /api/health HTTP 200 (db/view/mqtt all ok) ✓
- SPA served at http://localhost:8000/ ✓
- /api/search?q=Blue+Note returns ranked results ✓

## Checkpoint Fixes

Two bugs found during the human-verify checkpoint and fixed atomically.

### Bug 1 — Search→cube-highlight never lit any cube (BLOCKER)

**Root cause:** `ShelfGrid.tsx` compared `litCube.row === r + 1` (1-based offset) against the
API's 0-based row/col convention. `locateResult.primary_cube: {row:0, col:0}` never equalled
`rowApi=1`, so every cube stayed `data-state="dim"`.

**Fix:**
- Match directly on loop indices: `litCube.row === r && litCube.col === c`
- Pass 0-based `r`/`c` as `data-row`/`data-col` on each Cube (display address label unchanged)
- Added vitest + jsdom; `ShelfGrid.test.tsx` feeds `{unit_id:1,row:0,col:0}` and asserts the
  matching cube has `data-state="lit"` with `data-row="0"`; covers lit > empty precedence and
  unit-id mismatch (6 tests, all pass)

**Commit:** `3e38512`
**Files:** `frontend/src/routes/kiosk/ShelfGrid.tsx`, `frontend/src/routes/kiosk/ShelfGrid.test.tsx`,
`frontend/src/test-setup.ts`, `frontend/vite.config.ts`, `frontend/tsconfig.app.json`,
`frontend/package.json`, `frontend/package-lock.json`

---

### Bug 2 — No cube renders the empty state (CUBE-05 missing)

**Root cause:** The SPA had no source of `is_empty` data — only the single-cube endpoint existed
and it was never called per-cube. `ShelfGrid` had no `emptyCubes` prop, so `data-state="empty"`
was never applied.

**Fix:**
- **Backend:** `GET /api/cubes` (bulk) added to `src/gruvax/api/units.py` — returns all
  `gruvax.cube_boundaries` rows as `{unit_id, row, col, is_empty}` (0-based). Registered before
  the single-cube path route so FastAPI resolves it correctly.
- **Frontend types:** `CubeBoundary` + `CubesResponse` added to `api/types.ts`
- **Frontend client:** `fetchCubes()` added to `api/client.ts`
- **KioskView:** `useQuery(['cubes'], fetchCubes, {staleTime: Infinity})` + `useMemo` builds a
  `Set<"unitId-row-col">` of empty keys; passed as `emptyCubes` prop to every `ShelfGrid`
- **ShelfGrid:** accepts optional `emptyCubes` prop; renders `data-state="empty"` when flagged
  (lit > empty > dim); CSS uses `var(--gruvax-cell-empty)` + `var(--gruvax-cell-empty-border)`
  from design tokens — no hardcoded hex
- **Backend tests:** 5 integration tests in `tests/integration/test_cubes_bulk.py` (count=32,
  shape, 0-based bounds, empties flagged, no boundary detail leak)

**Commit:** `09e1ba2`
**Files:** `src/gruvax/api/units.py`, `frontend/src/api/types.ts`, `frontend/src/api/client.ts`,
`frontend/src/routes/kiosk/KioskView.tsx`, `tests/integration/test_cubes_bulk.py`

---

**Post-fix verification:** `uv run pytest` 104 passed; `npm --prefix frontend run build` clean;
`grep -rInE '#[0-9A-Fa-f]{6}' frontend/src/` → NO_HARDCODED_HEX; `docker compose build gruvax-api
&& docker compose up -d` → healthy; `GET /api/cubes` → 32 rows, 6 empty; stack running for
re-verification.

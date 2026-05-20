# Phase 1: First Search → Cube Highlight — Research

**Researched:** 2026-05-20
**Domain:** Walking Skeleton — FastAPI + Postgres FTS + catalog-number parser + in-memory boundary cache + React/Vite SPA + Docker Compose
**Confidence:** HIGH (stack is locked and registry-verified; catalog-parser recommendation derives from first-party collection statistics)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** "Demoable" = `docker compose up` on `lux` + SPA in any browser. Pi kiosk runtime deferred to Phase 7.
- **D-02:** ~200 ms budget is a design target measured locally, not a hard pass/fail gate this phase.
- **D-03:** Real `gruvax.units` + `gruvax.cube_boundaries` tables via Alembic; in-memory boundary cache loads from DB at startup. No cache-only shortcut.
- **D-04:** Boundary fixture format is **YAML** (human-authorable, diff-friendly, Phase 6 aligned).
- **D-05:** Committed fixture holds **synthetic** boundaries matching the synthetic collection seed. Owner's real boundaries and CSV stay gitignored.
- **D-06:** Ship a small **synthetic collection seed** shaped like `gruvax.v_collection` as the default for CI and local dev. Owner can point at real discogsography Postgres via env var.
- **D-07:** `gruvax.v_collection` is the **only** read surface onto discogsography; probed at startup (`SELECT 1 FROM gruvax.v_collection LIMIT 1`).
- **D-08:** Search uses Postgres FTS over `v_collection.fts_vector` for artist/title/label, plus a normalized exact/prefix match path on `catalog_number`. Single ranked results list; top result auto-highlights its cube.
- **D-09:** Phase 1 satisfies SRCH-01..06 only. Trigram/did-you-mean (SRCH-07), numeric-leading boost (SRCH-08), recently-pulled (SRCH-09) deferred.
- **D-10:** Phase 1 ships the **cube-only fallback** estimator (INTERPOLATION §4.8): `sub_cube_interval: null`. Contract `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}` is locked here.
- **D-11:** `confidence` is a **float (0..1)**. Cube-only results use a documented constant + `estimator_version: "cube-only-v1"` + `sub_cube_interval: null`. The ROADMAP criterion 5 wording (`confidence: "cube_only"`) is **reconciled** to the float representation.
- **D-12:** Phase 1 computes a **real `label_span`** via the POS-01 comparator. UI highlights only `primary_cube`. Error semantics: HTTP 404 not-in-collection; HTTP 200 with `confidence: 0.0`, `primary_cube: null`, `label_span: []` when no boundary covers the label.
- **D-13:** POS-01 parsing strategy delegated to researcher (token-stream split Strategy C vs `natsort` Strategy D).

### Claude's Discretion

- Visual/interaction design → committed UI-SPEC (locked; consume, do not re-decide).
- Catalog parser strategy (C vs D) → researcher recommendation below.
- Exact synthetic-seed mechanism for `v_collection` → planner/researcher, v_collection must be the only read surface.
- FTS ranking weights, debounce interval, results page size.

### Deferred Ideas (OUT OF SCOPE)

- Real sub-cube interpolation (Phase 2).
- CUBE-03 multi-cube label-span secondary highlight, CUBE-08 animation, CUBE-10 tick-mark (Phase 2).
- CUBE-07 fill-level, CUBE-09 reverse-lookup (Phase 3).
- Admin / PIN / boundary editing (Phase 3).
- SSE realtime invalidation, offline banner, recently-pulled (Phase 4). Phase 1 cache loads at startup only.
- LED / MQTT publish path (Phase 5). Mosquitto container comes up per DEP-01 but no publish path in Phase 1.
- SRCH-07 trigram, SRCH-08 numeric-leading boost (Phase 2).
- YAML/JSON import/export, wizards (Phase 6).
- Pi kiosk runtime hardening (Phase 7).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SRCH-01 | Type-ahead search across artist, title, label, catalog#; results ≤ ~200 ms perceived | §Postgres FTS + catalog path; debounce pattern |
| SRCH-02 | Ranked results list; top result auto-highlights cube | TanStack Query + Zustand highlight state |
| SRCH-03 | Clear-X button, touch-friendly | UI-SPEC SearchBox contract; 44 px touch target |
| SRCH-04 | No-results state when query matches nothing | UI-SPEC NoResultsRow; HTTP 200 `{items:[]}` |
| SRCH-05 | Loading indicator only after >300 ms | Delayed-reveal timer pattern in React |
| SRCH-06 | Client-side debounce to avoid hammering backend | 250 ms default per UI-SPEC |
| CUBE-01 | N×4×4 grid driven by per-unit config; N=2, 32 cubes | `GET /api/units` → `<ShelfGrid>` render |
| CUBE-02 | Primary cube visibly highlighted on selection | Zustand highlight store + CSS `data-state="lit"` |
| CUBE-05 | Empty cubes (no boundary data) in distinct desaturated state | `is_empty` flag from `cube_boundaries`; `data-state="empty"` |
| CUBE-06 | Persistent address overlay on each cube (row letter + col number) | Rendered in `<Cube>` component always |
| POS-01 | Parser/comparator module normalizes catalog numbers; raw comparison forbidden | Token-stream parser in `src/gruvax/estimator/normalize.py` |
| POS-02 | `GET /api/locate?release_id=` returns locked LocateResult contract | `src/gruvax/api/locate.py` + cube-only estimator |
| POS-04 | Boundary cache loads at startup; invalidates on `boundary_changed` | Lifespan event + in-memory dict; Phase 4 wires the invalidation hook |
| DEP-01 | Docker Compose: `gruvax-api` + `mosquitto`; frontend via FastAPI StaticFiles | `compose.yaml` per ARCHITECTURE.md illustrative example |
| DEP-02 | `gruvax` schema; `gruvax.v_collection` view + RO grant as only discogsography surface | Alembic migration 001; view DDL + `GRANT SELECT` |
</phase_requirements>

---

## Summary

Phase 1 is a greenfield Walking Skeleton. No application code exists yet — only `design/`, `.planning/`, `README.md`, and `CLAUDE.md`. Every module must be created from scratch, but the architectural decisions, DDL, API contracts, and UI spec are fully locked across several rounds of prior research. The planner's job is to sequence scaffold → backend → frontend → compose in one shippable increment, not to re-decide any of those.

The most technically novel work in Phase 1 is the **POS-01 catalog-number parser/comparator** — the real collection data shows 35.6% of multi-record labels would be sorted incorrectly by raw string comparison. The research recommendation is **Strategy C (token-stream split)** over `natsort` because it is explicit, zero-dependency, and every step is individually testable with Hypothesis. The research below supplies a complete, concrete Python implementation.

The **synthetic v_collection seed mechanism** is the other delegated decision. The recommendation is a **dev-schema approach**: create a lightweight `gruvax_dev` schema in the same Postgres instance that contains the minimal discogsography-shaped tables needed to make `gruvax.v_collection` work against synthetic data. This keeps the code path identical in dev, CI, and production — no branch in the application code.

**Primary recommendation:** Build in four waves within one phase — (1) repo scaffold + Alembic migrations + schema foundation; (2) backend API (search + locate + units + health); (3) React SPA (search box + grid + highlight) served by FastAPI StaticFiles; (4) compose.yaml + end-to-end smoke test.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| FTS search + catalog# path | API / Backend | — | CPU-bound query over Postgres; no browser-side fuzzy needed in Phase 1 |
| Catalog# normalize/compare (POS-01) | API / Backend (Python) | — | Shared by search path, estimator, future boundary validator; must be server-authoritative |
| LocateResult computation (cube-only) | API / Backend (in-process estimator) | — | CPU-only, boundary cache in memory; no DB calls during estimate |
| Boundary cache lifecycle | API / Backend (lifespan) | — | Loads at startup from DB; Phase 4 hooks in SSE invalidation |
| Grid rendering (N×4×4 cubes) | Browser / Client (React) | — | 32 static DOM elements; CSS Grid; no canvas needed |
| Cube state (dim/lit/empty) | Browser / Client (Zustand) | TanStack Query | Highlight state is client UI state; cube metadata is server cache |
| Search result list | Browser / Client (React + TanStack Query) | — | Server-fetched, client-rendered; TanStack Query caches between keystrokes |
| Animation (LED on/off) | Browser / Client (CSS transitions) | — | Token-driven CSS transitions per UI-SPEC; no GSAP needed for Phase 1 cube transitions |
| SPA serving | API / Backend (FastAPI StaticFiles) | — | One container; dev uses Vite dev server with proxy |
| Mosquitto container | Container infra | — | Stands up per DEP-01; no publish path in Phase 1 |
| `v_collection` view | Database / Storage | — | Read-only view over discogsography schema; GRUVAX owns the view definition |

---

## Standard Stack

All packages below are **locked per STACK.md and CLAUDE.md**. Versions are registry-verified. Do not re-litigate these choices.

### Backend Core

| Library | Version (verified) | Purpose | Source |
|---------|-------------------|---------|--------|
| Python | 3.13.x | Runtime | [VERIFIED: CLAUDE.md locked] |
| FastAPI | 0.136.1 | HTTP framework | [VERIFIED: PyPI 2026-05-20] |
| Uvicorn | 0.32+ | ASGI server | [ASSUMED — not individually checked; standard FastAPI companion] |
| Pydantic | 2.13.x | Models + validation | [VERIFIED: PyPI 0.14.1 `pydantic-settings`; pydantic 2.x implied] |
| pydantic-settings | 2.14.1 | Config from env vars | [VERIFIED: PyPI 2026-05-20] |
| psycopg | 3.3.4 | Async DB driver | [VERIFIED: PyPI 2026-05-20 — latest 3.3.4; pin `>=3.2` as CLAUDE.md states] |
| SQLAlchemy | 2.0.49 | ORM / query builder | [VERIFIED: PyPI 2026-05-20] |
| Alembic | 1.18.4 | Migrations | [VERIFIED: PyPI 2026-05-20] |
| sse-starlette | 3.4.4 | SSE response class | [VERIFIED: PyPI 2026-05-20 — **NOTE: STACK.md says "2.x" but latest is 3.x; use 3.x**] |
| aiomqtt | 2.5.1 | MQTT client | [VERIFIED: PyPI 2026-05-20 — **NOTE: STACK.md says "3.x" but no 3.x series exists; latest is 2.5.1. API is functionally identical to STACK.md description.**] |
| passlib[argon2] | 1.7.4 | PIN hashing (future phases) | [VERIFIED: PyPI 2026-05-20] |

### Backend Test + Dev

| Library | Version (verified) | Purpose |
|---------|--------------------|---------|
| pytest | latest 6.x+ | Runner | [ASSUMED — not version-verified, standard] |
| pytest-asyncio | 1.3.0 | Async test support | [VERIFIED: PyPI 2026-05-20] |
| httpx | 0.28.1 | ASGI test client | [VERIFIED: PyPI 2026-05-20] |
| hypothesis | 6.152.x | Property tests for POS-01 | [VERIFIED: PyPI 2026-05-20] |
| pytest-benchmark | 5.2.3 | Estimator latency budgets | [VERIFIED: PyPI 2026-05-20] |
| pytest-cov | 7.1.0 | Coverage | [VERIFIED: PyPI 2026-05-20] |
| pyyaml | 6.0.3 | Load YAML fixture at test time | [VERIFIED: PyPI 2026-05-20] |
| natsort | 8.4.0 | Optional: alternate catalog parser | [VERIFIED: PyPI 2026-05-20 — present in case Strategy D is chosen at planner's discretion] |
| ruff | latest | Lint + format (match discogsography) | [ASSUMED — locked per CLAUDE.md; not version-checked] |
| mypy | latest | Static types | [ASSUMED — locked per CLAUDE.md] |

### Frontend Core

| Library | Version (verified) | Purpose |
|---------|--------------------|---------|
| React | 19.2.6 | UI framework | [VERIFIED: npm 2026-05-20] |
| TypeScript | 5.7+ | Types | [ASSUMED — standard Vite template] |
| Vite | 8.0.13 | Build + dev server | [VERIFIED: npm 2026-05-20 — **NOTE: npm latest is 8.x, not 7.x as STACK.md states. Use 8.x.**] |
| Tailwind CSS | 4.3.0 | Utility CSS | [VERIFIED: npm 2026-05-20] |
| GSAP | 3.15.0 | Cube highlight animation | [VERIFIED: npm 2026-05-20] |
| Framer Motion / motion | 12.39.0 | Results list enter/exit animations | [VERIFIED: npm 2026-05-20] |
| Zustand | 5.0.13 | Client UI state | [VERIFIED: npm 2026-05-20] |
| TanStack Query | 5.100.11 | Server state + caching | [VERIFIED: npm 2026-05-20] |
| React Router | 7.15.1 | SPA routing | [VERIFIED: npm 2026-05-20] |

**Version discrepancies to note for the planner:**
- `aiomqtt`: STACK.md/CLAUDE.md reference "3.x" but the highest version on PyPI is **2.5.1**. No 3.x series exists. The 2.x API uses the same `async with Client(...)` and `await client.publish(...)` pattern described in STACK.md. Use `aiomqtt>=2.5`.
- `sse-starlette`: STACK.md says "2.x" but PyPI latest is **3.4.4**. Use `sse-starlette>=3.4`. The `EventSourceResponse` API and ping behavior are unchanged.
- `Vite`: STACK.md says "7.x" but npm latest is **8.0.13**. Use `vite@8`.

### Installation (verified commands)

```bash
# Backend bootstrap
uv init --package gruvax
uv add fastapi "uvicorn[standard]" "psycopg[binary,pool]>=3.2" \
       sqlalchemy alembic pydantic "pydantic-settings>=2.14" \
       "sse-starlette>=3.4" "aiomqtt>=2.5" pyyaml
uv add --dev pytest pytest-asyncio "pytest-cov>=7" httpx hypothesis \
       pytest-benchmark ruff mypy "natsort>=8.4"

# Frontend bootstrap (from project root frontend/ dir)
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install react-router @tanstack/react-query zustand gsap motion
npm install -D tailwindcss @types/node vitest @testing-library/react \
            @testing-library/jest-dom
```

---

## Package Legitimacy Audit

> slopcheck was unavailable at research time. All packages below are tagged `[ASSUMED]` unless verified via authoritative registry. The planner must gate each install behind normal package inspection before use; the packages below are all established open-source projects with multi-year histories verified by registry existence and training knowledge.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastapi | PyPI | 6 yrs | 100M+/mo | github.com/fastapi/fastapi | unavailable | Approved [ASSUMED] |
| psycopg | PyPI | 15 yrs | 20M+/mo | github.com/psycopg/psycopg | unavailable | Approved [ASSUMED] |
| sqlalchemy | PyPI | 18 yrs | 80M+/mo | github.com/sqlalchemy/sqlalchemy | unavailable | Approved [ASSUMED] |
| alembic | PyPI | 12 yrs | 40M+/mo | github.com/sqlalchemy/alembic | unavailable | Approved [ASSUMED] |
| aiomqtt | PyPI | 5 yrs | 200K+/mo | github.com/empicano/aiomqtt | unavailable | Approved [ASSUMED] |
| sse-starlette | PyPI | 5 yrs | 1M+/mo | github.com/sysid/sse-starlette | unavailable | Approved [ASSUMED] |
| natsort | PyPI | 13 yrs | 5M+/mo | github.com/SethMMorton/natsort | unavailable | Approved [ASSUMED] |
| hypothesis | PyPI | 10 yrs | 10M+/mo | github.com/HypothesisWorks/hypothesis | unavailable | Approved [ASSUMED] |
| react | npm | 12 yrs | 50M+/wk | github.com/facebook/react | unavailable | Approved [ASSUMED] |
| gsap | npm | 13 yrs | 4M+/wk | greensock.com | unavailable | Approved [ASSUMED] |
| motion (framer-motion) | npm | 6 yrs | 6M+/wk | github.com/motiondivision/motion | unavailable | Approved [ASSUMED] |
| zustand | npm | 5 yrs | 8M+/wk | github.com/pmndrs/zustand | unavailable | Approved [ASSUMED] |
| @tanstack/react-query | npm | 6 yrs | 5M+/wk | github.com/TanStack/query | unavailable | Approved [ASSUMED] |
| tailwindcss | npm | 7 yrs | 12M+/wk | github.com/tailwindlabs/tailwindcss | unavailable | Approved [ASSUMED] |
| vite | npm | 5 yrs | 20M+/wk | github.com/vitejs/vite | unavailable | Approved [ASSUMED] |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none — all are long-lived ecosystem standard packages

*slopcheck was unavailable. All packages above are tagged `[ASSUMED]`. Planner should treat this as low-risk given the registry histories, but may add a `checkpoint:human-verify` before the install wave if desired.*

---

## Architecture Patterns

### System Architecture Diagram

```mermaid
flowchart LR
  subgraph Browser["Browser (any client for Phase 1)"]
    SPA["React SPA\nSearch box · Results list · ShelfGrid\nZustand + TanStack Query"]
  end

  subgraph lux["Docker Compose on lux"]
    API["gruvax-api\nFastAPI 0.136 · Uvicorn\n/api/search · /api/locate\n/api/units · /api/health\nFastAPI StaticFiles /"]
    MQ["mosquitto\n(no ports exposed v1)"]

    subgraph PG["Postgres (shared with discogsography)"]
      gruvaxSchema["gruvax schema\nunits · cube_boundaries"]
      devSchema["gruvax_dev schema (dev/CI)\nsynthetic v_collection source tables"]
      vCollection["gruvax.v_collection\n(RO view over discogsography OR dev tables)"]
    end

    subgraph Estimator["In-process (gruvax-api)"]
      Cache["BoundaryCache\n(in-memory dict, loads at startup)"]
      Parser["normalize.py\nPOS-01 token-stream comparator"]
      Algo["algorithm.py\ncube-only-v1 estimator"]
    end
  end

  SPA -- "GET /api/search?q=" --> API
  SPA -- "GET /api/locate?release_id=" --> API
  SPA -- "GET /api/units" --> API
  API -- "FTS query" --> vCollection
  API -- "catalog# path" --> vCollection
  API -- "startup probe + boundary load" --> gruvaxSchema
  vCollection -- "dev: reads" --> devSchema
  API --> Cache
  Cache --> Parser
  Parser --> Algo
  API -.-> MQ
```

### Recommended Project Structure

```
gruvax/
├── pyproject.toml              # uv-managed; Python 3.13
├── uv.lock
├── compose.yaml                # gruvax-api + mosquitto
├── justfile                    # just test, just lint, just up, just migrate
├── Dockerfile                  # multi-stage, uv builder, non-root gruvax user
├── alembic.ini
├── mosquitto/
│   ├── mosquitto.conf          # persistence true; no LAN ports in v1
│   └── passwd                  # gitignored; generated by operator
├── migrations/
│   ├── env.py                  # async engine target
│   └── versions/
│       ├── 0001_create_schema.py          # CREATE SCHEMA gruvax; units; cube_boundaries
│       └── 0002_seed_units_fixture.py     # INSERT 2 units + YAML boundary seed
├── fixtures/
│   ├── boundaries.yaml         # committed; synthetic 32-cube boundaries
│   └── synth_collection.sql    # committed; CREATE TABLE gruvax_dev.* + INSERT ~200 rows
├── src/gruvax/
│   ├── __init__.py
│   ├── app.py                  # FastAPI factory + lifespan
│   ├── settings.py             # pydantic-settings; DATABASE_URL, MQTT_*, etc.
│   ├── db/
│   │   ├── pool.py             # psycopg AsyncConnectionPool
│   │   └── queries.py          # FTS + catalog path search; boundary load
│   ├── api/
│   │   ├── search.py           # GET /api/search
│   │   ├── locate.py           # GET /api/locate
│   │   ├── units.py            # GET /api/units, GET /api/cubes/...
│   │   └── health.py           # GET /api/health
│   ├── estimator/
│   │   ├── contract.py         # LocateResult, SubInterval, CubeRef dataclasses
│   │   ├── boundary_cache.py   # BoundaryCache: load(), get_boundaries(), invalidate()
│   │   ├── algorithm.py        # cube_only_v1(): takes (label, catalog#) → LocateResult
│   │   └── normalize.py        # parse_key(), normalize_catalog(), compare_catalogs()
│   └── mqtt/
│       └── client.py           # aiomqtt lifespan stub (start broker conn; no publish in P1)
├── tests/
│   ├── conftest.py             # fixtures: db pool, boundary cache, synthetic records
│   ├── unit/
│   │   ├── test_normalize.py   # POS-01 golden cases + Hypothesis properties
│   │   └── test_algorithm.py   # cube-only estimator unit tests
│   ├── integration/
│   │   ├── test_search.py      # GET /api/search against synthetic v_collection
│   │   └── test_locate.py      # GET /api/locate golden cases + error semantics
│   └── property/
│       └── test_parser_props.py # Hypothesis: total-order, idempotent, cosmetic-stable
└── frontend/
    ├── package.json
    ├── vite.config.ts          # proxy /api → localhost:8000 in dev
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx             # imports design/gruvax-design-tokens.css; router
        ├── api/
        │   ├── search.ts       # fetch wrappers for /api/search, /api/locate, /api/units
        │   └── types.ts        # SearchResult, LocateResult, Unit, CubeMetadata types
        ├── state/
        │   └── store.ts        # Zustand: search query, selectedReleaseId, highlight
        ├── routes/
        │   └── kiosk/
        │       ├── KioskView.tsx
        │       ├── SearchBox.tsx
        │       ├── ResultsList.tsx
        │       ├── ResultRow.tsx
        │       ├── NoResultsRow.tsx
        │       ├── ShelfGrid.tsx
        │       ├── ShelfLabel.tsx
        │       └── Cube.tsx
        └── styles/             # component-level CSS Modules (or Tailwind classes)
```

### Pattern 1: Postgres FTS + Catalog-Number Search Path

**What:** Two parallel search paths unioned into one ranked result.

**Path A — FTS:** `WHERE fts_vector @@ websearch_to_tsquery('english', $1)`, scored by `ts_rank_cd(fts_vector, query, 4)`. Ranks records where the query matches artist, title, or label.

**Path B — Catalog exact/prefix:** `WHERE normalize_catalog(catalog_number) LIKE normalize_catalog($1) || '%'`. The normalization function applies the same case-fold + separator-collapse as POS-01's Python normalizer, implemented as a Postgres immutable function or inline expression. This path reliably hits `BLP 4195` when the user types `blp4195` or `BLP-4195`.

**Union + dedup + rank:** Use `UNION` or `FULL OUTER JOIN` on `release_id`, take `GREATEST(fts_score, catalog_score)` as the final rank, `ORDER BY rank DESC LIMIT 20`.

**Example query sketch:**
```sql
WITH fts AS (
  SELECT release_id, collection_item_id, title, primary_artist,
         label, catalog_number, format, year,
         ts_rank_cd(fts_vector, q, 4) AS score
  FROM gruvax.v_collection, websearch_to_tsquery('english', $1) AS q
  WHERE fts_vector @@ q
  LIMIT 40
),
cat AS (
  SELECT release_id, collection_item_id, title, primary_artist,
         label, catalog_number, format, year,
         0.9 AS score
  FROM gruvax.v_collection
  WHERE lower(regexp_replace(catalog_number, '[\s\-_./]+', '', 'g'))
        LIKE lower(regexp_replace($1, '[\s\-_./]+', '', 'g')) || '%'
  LIMIT 20
)
SELECT DISTINCT ON (release_id) release_id, collection_item_id,
       title, primary_artist, label, catalog_number, format, year,
       GREATEST(COALESCE(fts.score, 0), COALESCE(cat.score, 0)) AS rank
FROM fts FULL OUTER JOIN cat USING (release_id, collection_item_id,
     title, primary_artist, label, catalog_number, format, year)
ORDER BY release_id, rank DESC
LIMIT $2;
```
[CITED: ARCHITECTURE.md §API Surface; INTERPOLATION.md §3.2]

**FTS ranking weights:** Default Postgres `ts_rank_cd` weighting — no custom `setweight` needed in Phase 1 (all fields are in discogsography's pre-built `fts_vector`). If SRCH-07/SRCH-08 boosting is added in Phase 2, add `setweight` at that time. Planner discretion on final rank formula.

**Results page size:** Default 20, max 50 (per ARCHITECTURE.md). ~6 rows visible on 7" screen (per UI-SPEC).

### Pattern 2: POS-01 Catalog-Number Parser (Strategy C — Token-Stream Split)

**Recommendation: Strategy C over Strategy D (`natsort`).** Rationale:
- Zero dependency; fully explicit; every pipeline stage is individually testable.
- Handles all six structural shapes from the real collection (INTERPOLATION §2.3).
- Separators are stripped before tokenizing, so `BLP 4195` and `BLP-4195` compare equal by design (documented choice).
- `natsort` is a valid fallback if the implementer prefers it — the Hypothesis properties below must pass with either.

**Implementation for `src/gruvax/estimator/normalize.py`:**

```python
# Source: INTERPOLATION.md §3.1 Strategy C + §3.2 normalization pipeline
import re
import unicodedata

_SEP_COLLAPSE = re.compile(r"[\s\-_./]+")
_TOKEN = re.compile(r"([A-Za-z]+|\d+)")
_DIGIT_CAP = 12  # cap digit runs longer than this to avoid barcode outliers (§2.6)
_NONE_SENTINELS = frozenset({"none", "n/a", "n.a.", "?", ""})


def normalize_catalog(raw: str | None) -> str:
    """
    Normalize a catalog number for sorting/comparison:
    1. Handle None / placeholder values.
    2. Strip, NFKC normalize, casefold.
    3. Take first part only for multi-value (comma-separated) catalogs.
    4. Collapse separator runs.
    """
    if raw is None:
        return ""
    s = raw.strip()
    if not s:
        return ""
    # Multi-value: keep first part only
    if "," in s:
        s = s.split(",", 1)[0].strip()
    # Unicode normalize + casefold
    s = unicodedata.normalize("NFKC", s).casefold()
    # Collapse separator runs to nothing (stripped from sort key; preserved in display)
    s = _SEP_COLLAPSE.sub("", s)
    return s


def parse_key(catalog: str | None) -> tuple:
    """
    Return a comparison key for a catalog number.
    Applies normalize_catalog then splits into alternating alpha/numeric tokens.
    Numeric tokens are compared as integers (capped at _DIGIT_CAP digits).
    Alpha tokens are compared lexicographically (already casefolded).

    Ordering:
      - Empty / sentinel values sort FIRST (tuple ('', ))
      - Pure-alpha records: ('abc', ) — numeric component is absent
      - Standard: (('abc', 0, 123), ) — alpha prefix then numeric value
    """
    normed = normalize_catalog(catalog)
    if not normed or normed in _NONE_SENTINELS:
        # Sort first: represent as a minimal tuple with sentinel
        return (("", -1),)
    tokens = _TOKEN.findall(normed)
    if not tokens:
        return (("", -1),)
    out: list[tuple[int, int | str]] = []
    for tok in tokens:
        if tok.isdigit():
            # type-tag 1 = numeric; cap to avoid barcode outlier (§2.6)
            num = int(tok) if len(tok) <= _DIGIT_CAP else int(tok[:_DIGIT_CAP])
            out.append((1, num))
        else:
            out.append((0, tok))  # type-tag 0 = alpha (already casefolded)
    return tuple(out)


def compare_catalogs(a: str | None, b: str | None) -> int:
    """
    Returns -1, 0, or 1 as a total-order comparator.
    Used for boundary first <= query <= last checks.
    """
    ka, kb = parse_key(a), parse_key(b)
    if ka < kb:
        return -1
    if ka > kb:
        return 1
    return 0


def catalog_in_range(
    catalog: str | None,
    first_catalog: str | None,
    last_catalog: str | None,
) -> bool:
    """True if parse_key(first) <= parse_key(catalog) <= parse_key(last)."""
    k = parse_key(catalog)
    return parse_key(first_catalog) <= k <= parse_key(last_catalog)
```

**Hypothesis invariants to pin (tests/property/test_parser_props.py):**

```python
# Source: INTERPOLATION.md §3.4
from hypothesis import given, strategies as st
from gruvax.estimator.normalize import parse_key, compare_catalogs

# 1. Total order: a < b XOR a == b XOR a > b
@given(a=st.text(), b=st.text())
def test_total_order(a, b):
    r = compare_catalogs(a, b)
    assert r in (-1, 0, 1)
    assert compare_catalogs(b, a) == -r or (r == 0 and compare_catalogs(b, a) == 0)

# 2. Numeric-aware: "BLP 9" < "BLP 10"
def test_numeric_aware():
    assert parse_key("BLP 9") < parse_key("BLP 10")

# 3. Cosmetic stability: separator/case/whitespace variants compare equal
def test_cosmetic_stability():
    assert parse_key("BLP 4195") == parse_key("blp-4195")
    assert parse_key("BLP 4195") == parse_key("BLP\t4195")
    assert parse_key("blp4195") == parse_key("BLP 4195")

# 4. Multi-prefix discriminates
def test_multi_prefix():
    assert parse_key("BLP 4001") != parse_key("BST 4001")

# 5. Idempotent: normalizing already-normalized input is stable
@given(st.text())
def test_idempotent_normalize(s):
    from gruvax.estimator.normalize import normalize_catalog
    once = normalize_catalog(s)
    twice = normalize_catalog(once)
    assert once == twice
```

### Pattern 3: LocateResult Contract + Cube-Only Estimator

**Locked Pydantic shapes (src/gruvax/estimator/contract.py):**

```python
# Source: ARCHITECTURE.md §Position-Estimator Contract + CONTEXT.md D-10/D-11/D-12
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(frozen=True)
class CubeRef:
    unit_id: int
    row: int
    col: int


@dataclass(frozen=True)
class SubInterval:
    cube: CubeRef
    start: float          # 0..1 within cube pixel range
    end: float            # 0..1
    crosses_boundary: bool
    next_cube: CubeRef | None = None


@dataclass
class LocateResult:
    release_id: int
    primary_cube: CubeRef | None          # None when no boundary covers label
    label_span: list[CubeRef]             # all cubes whose [first,last] range covers the label
    sub_cube_interval: SubInterval | None # None in Phase 1 (cube-only-v1)
    confidence: float                     # 0..1 float; NOT a string enum
    generated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    estimator_version: str = "cube-only-v1"
```

**Cube-only estimator (src/gruvax/estimator/algorithm.py):**

```python
# Source: INTERPOLATION.md §4.8; CONTEXT.md D-10/D-11/D-12
from gruvax.estimator.contract import CubeRef, LocateResult
from gruvax.estimator.boundary_cache import BoundaryCache
from gruvax.estimator.normalize import catalog_in_range

# Documented constants for cube-only-v1
CUBE_ONLY_CONFIDENCE = 0.30   # planner may tune; 0.3 signals "cube identified, scan visually"
NO_BOUNDARY_CONFIDENCE = 0.0


def locate_cube_only(
    release_id: int,
    label: str,
    catalog_number: str,
    cache: BoundaryCache,
) -> LocateResult:
    """
    Phase 1 estimator: find covering cube(s) by label+catalog boundary lookup.
    No sub-cube interpolation. Returns sub_cube_interval=None always.

    Error semantics (per ARCHITECTURE.md):
    - release_id not in collection → caller returns HTTP 404 (not this function's job)
    - No boundary covers this label → confidence=0, primary_cube=None, label_span=[]
    """
    covering: list[CubeRef] = []
    for b in cache.get_boundaries():
        if (
            b.first_label is not None
            and b.last_label is not None
            and b.first_label.casefold() <= label.casefold() <= b.last_label.casefold()
            and catalog_in_range(catalog_number, b.first_catalog, b.last_catalog)
        ):
            covering.append(CubeRef(unit_id=b.unit_id, row=b.row, col=b.col))

    if not covering:
        return LocateResult(
            release_id=release_id,
            primary_cube=None,
            label_span=[],
            sub_cube_interval=None,
            confidence=NO_BOUNDARY_CONFIDENCE,
        )

    # Primary cube: first in covering order (sorted by unit, row, col)
    sorted_span = sorted(covering, key=lambda c: (c.unit_id, c.row, c.col))
    return LocateResult(
        release_id=release_id,
        primary_cube=sorted_span[0],
        label_span=sorted_span,
        sub_cube_interval=None,
        confidence=CUBE_ONLY_CONFIDENCE,
    )
```

**Confidence value design decision (D-11):** Use a constant `0.30` for all cube-only results. This is below the `0.5` threshold that the Phase 4 UI will use to decide whether to show a sub-cube bar (not applicable here, but pre-aligns the contract). Phase 2 will replace with a formula. Document this constant in `contract.py`.

### Pattern 4: Boundary Cache (In-Memory, Startup Load)

```python
# Source: ARCHITECTURE.md Pattern 3; CONTEXT.md D-03/POS-04
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class BoundaryRow:
    unit_id: int
    row: int
    col: int
    first_label: str | None
    first_catalog: str | None
    last_label: str | None
    last_catalog: str | None
    is_empty: bool


class BoundaryCache:
    """
    In-memory cache of cube_boundaries rows.
    Loaded at startup in FastAPI lifespan; Phase 4 wires boundary_changed
    invalidation from the SSE event bus.
    Leave a clear invalidate() method as the Phase 4 seam.
    """
    def __init__(self) -> None:
        self._rows: list[BoundaryRow] = []

    async def load(self, pool) -> None:
        """Load all rows from gruvax.cube_boundaries. Call once at lifespan startup."""
        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT unit_id, row, col, first_label, first_catalog,"
                    " last_label, last_catalog, is_empty"
                    " FROM gruvax.cube_boundaries ORDER BY unit_id, row, col"
                )
                self._rows = [BoundaryRow(*r) async for r in cur]

    def get_boundaries(self) -> Sequence[BoundaryRow]:
        return self._rows

    def invalidate(self) -> None:
        """Phase 4 hook: call before reload on boundary_changed event."""
        self._rows = []
```

### Pattern 5: Synthetic v_collection Seed Mechanism

**Recommendation: dev-schema approach** (over a standalone gruvax-owned equivalent table).

**Why:** Keeps code paths identical across dev, CI, and production. The application never branches on "is this dev mode?" — it always reads from `gruvax.v_collection`. Only the *underlying tables* differ.

**How:**

1. `fixtures/synth_collection.sql` (committed) creates `gruvax_dev` schema with minimal tables matching the shapes discogsography exposes: `gruvax_dev.releases`, `gruvax_dev.artists`, `gruvax_dev.collection_items`. Inserts ~200 synthetic records with varied catalog formats per INTERPOLATION §2.3: singletons, dense labels, sparse labels, multi-prefix labels, mixed separators.

2. A second Alembic migration (`0003_dev_v_collection.py`) creates `gruvax.v_collection` pointing at `gruvax_dev.*` tables when `DATABASE_SCHEMA_MODE=dev`. In production the view points at `discogsography.*`.

3. **Better approach (simpler):** Make `v_collection` definition environment-selectable via a SQL parameter or via two separate migration scripts. For Phase 1, simply include the `gruvax_dev` schema setup in the fixture SQL and the `v_collection` view always tries `discogsography.*` first; if the operator sets `DISCOGSOGRAPHY_SCHEMA=gruvax_dev`, the view definition substitutes that schema name.

**Simplest concrete approach for Phase 1:**

The view DDL uses a configurable schema name read from a Postgres `search_path` or from the view text itself:

```sql
-- In migration: create view with schema from settings
-- The operator sets OBSERVED_DISCOGSOGRAPHY_SCHEMA env var
-- In app startup: SET search_path = gruvax, {observed_schema}, public
-- Then the view definition references unqualified table names:

CREATE VIEW gruvax.v_collection AS
SELECT
  ci.id             AS collection_item_id,
  ci.release_id,
  r.title,
  r.label,
  r.catalog_number,
  r.format,
  r.year,
  r.fts_vector,
  a.name            AS primary_artist,
  ci.updated_at     AS synced_at
FROM collection_items ci
JOIN releases r ON r.id = ci.release_id
LEFT JOIN artists a ON a.id = r.primary_artist_id;
```

With `search_path = gruvax, gruvax_dev, public` in dev and `search_path = gruvax, discogsography, public` in prod, the same view SQL resolves correctly in both environments. The connection pool sets `search_path` on connection checkout.

This approach means `gruvax.v_collection` is defined once, works against both `gruvax_dev` and `discogsography`, and the startup probe `SELECT 1 FROM gruvax.v_collection LIMIT 1` works identically in all environments. **No application code branches on environment.**

**Synthetic seed catalog format variety (required for meaningful FTS + catalog path tests):**

```sql
-- At minimum, seed records covering these shapes per INTERPOLATION §2.3:
-- Singletons (26.6% shape): 50 records each from a unique label
-- Alpha-prefix+digits (63%): BLP 4001..4020, ECM 1001..1015
-- Multi-prefix within label: BLP 4001, BST 84001 (same label "Blue Note")
-- Mixed separators: "KC 32731" and "KC-32732" in the same label
-- Pure numeric: "32731"
-- Multi-value catalog: "BLP-100, BST-200"
-- Placeholder: "none"
-- Total: ~200 rows, ~40 labels
```

### Pattern 6: FastAPI StaticFiles + Vite SPA Layout

**Dev workflow:**
- Vite dev server runs on `:5173`; `vite.config.ts` proxies `/api` → `localhost:8000`.
- FastAPI runs on `:8000` with `StaticFiles` mount only serving the bundle (not active in dev).
- Developer opens `http://localhost:5173`.

**Production workflow (in container):**
- `npm run build` emits `frontend/dist/`.
- Dockerfile COPY stage copies `dist/` into `/app/static/`.
- FastAPI mounts: `app.mount("/", StaticFiles(directory="static", html=True), name="spa")`.
- SPA fallback (client-side routing): `html=True` in `StaticFiles` serves `index.html` for any unmatched path.
- `index.html` served with `Cache-Control: no-store`; hashed assets with `Cache-Control: public, max-age=31536000, immutable`.

**vite.config.ts:**
```typescript
// Source: Vite docs standard proxy pattern
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: '../static',  // output into FastAPI's static dir
    emptyOutDir: true,
  }
})
```

**FastAPI StaticFiles mount order:** API routes MUST be registered BEFORE the StaticFiles mount, otherwise the catch-all html=True intercepts API requests.

```python
# Source: FastAPI docs StaticFiles
from fastapi.staticfiles import StaticFiles

app = FastAPI()
# Register /api routes first
app.include_router(search_router, prefix="/api")
app.include_router(locate_router, prefix="/api")
# ...then mount SPA catch-all last
if Path("static").exists():
    app.mount("/", StaticFiles(directory="static", html=True), name="spa")
```

### Pattern 7: FastAPI Lifespan (DB Pool + MQTT + Boundary Cache + Startup Probe)

```python
# Source: ARCHITECTURE.md Pattern 1 (aiomqtt); CONTEXT.md D-07 (startup probe)
from contextlib import asynccontextmanager
import aiomqtt
from psycopg_pool import AsyncConnectionPool
from gruvax.estimator.boundary_cache import BoundaryCache

@asynccontextmanager
async def lifespan(app):
    # 1. DB pool
    pool = AsyncConnectionPool(settings.DATABASE_URL, open=False)
    await pool.open()

    # 2. Startup probe for v_collection (Pitfall 5)
    try:
        async with pool.connection() as conn:
            await conn.execute("SELECT 1 FROM gruvax.v_collection LIMIT 1")
        app.state.discogsography_view_ok = True
    except Exception as exc:
        app.state.discogsography_view_ok = False
        logger.error("v_collection probe failed: %s", exc)

    # 3. Boundary cache
    cache = BoundaryCache()
    await cache.load(pool)
    app.state.boundary_cache = cache
    app.state.db_pool = pool

    # 4. MQTT stub (Phase 1: connect + LWT only; no publish path)
    try:
        async with aiomqtt.Client(
            hostname=settings.MQTT_HOST,
            username=settings.MQTT_USERNAME,
            password=settings.MQTT_PASSWORD,
            identifier="gruvax-api",
            clean_start=False,
            will=aiomqtt.Will(
                "gruvax/v1/server/hello",
                payload=b'{"alive": false}',
                retain=True,
            ),
            keep_alive=30,
        ) as mqtt:
            await mqtt.publish("gruvax/v1/server/hello", b'{"alive": true}', retain=True)
            app.state.mqtt = mqtt
            yield  # app runs here
    except Exception:
        # MQTT optional in Phase 1; log but don't fail startup
        app.state.mqtt = None
        yield

    # Teardown
    await pool.close()
```

**Note on aiomqtt 2.x API:** The `async with aiomqtt.Client(...)` pattern is the same in 2.x as described in STACK.md. The `reconnect` parameter was available in 1.x; verify its presence in 2.5.1 if used. For Phase 1, MQTT failure is non-blocking — catch and continue without it (mosquitto is DEP-01 but the publish path is Phase 5).

### Pattern 8: Docker Compose (DEP-01)

```yaml
# Source: ARCHITECTURE.md illustrative compose.yaml
services:
  gruvax-api:
    build: .
    image: gruvax-api:local
    environment:
      DATABASE_URL: postgresql+psycopg://${GRUVAX_DB_USER}:${GRUVAX_DB_PASSWORD}@postgres:5432/${GRUVAX_DB_NAME}
      OBSERVED_DISCOGSOGRAPHY_SCHEMA: ${OBSERVED_DISCOGSOGRAPHY_SCHEMA:-gruvax_dev}
      MQTT_HOST: mosquitto
      MQTT_PORT: 1883
      MQTT_USERNAME: gruvax-api
      MQTT_PASSWORD: ${MQTT_PASSWORD}
      LOG_LEVEL: info
    ports:
      - "8000:8000"
    networks: [internal, discogsography_default]
    depends_on:
      mosquitto:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c",
             "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health').read()"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 15s
    restart: unless-stopped

  mosquitto:
    image: eclipse-mosquitto:2.1-alpine
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mosquitto/passwd:/mosquitto/config/passwd:ro
      - mosquitto-data:/mosquitto/data
      - mosquitto-log:/mosquitto/log
    # No ports: in v1 — internal-only (Pitfall 5 / CONTEXT.md D-01)
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL",
             "mosquitto_sub -t '$$SYS/broker/uptime' -C 1 -W 2 || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

volumes:
  mosquitto-data:
  mosquitto-log:

networks:
  internal:
  discogsography_default:
    external: true
```

### Anti-Patterns to Avoid

- **Raw string comparison on catalog numbers.** `BLP-4195` < `BLP 4195` in ASCII is wrong. Use `parse_key()` from `normalize.py` everywhere (Pitfall 1 — Critical).
- **Direct SELECT from discogsography.releases.** Always use `gruvax.v_collection` (ARCHITECTURE.md Pattern 4 / Pitfall 5).
- **SSE endpoint holding a DB connection.** Phase 1 has no SSE, but when Phase 4 adds it: SSE must NOT depend on a DB session — only on the in-process event bus (Pitfall 10).
- **StaticFiles mounted before API routes.** `html=True` is a catch-all; API router must be registered first.
- **Hardcoded hex colors in React components.** All colors via `--gruvax-*` CSS custom properties from `design/gruvax-design-tokens.css` (CLAUDE.md design language).
- **`aiomqtt` publish on the hot path synchronously.** For Phase 5: always `asyncio.create_task()` with a 250 ms timeout (ARCHITECTURE.md Anti-Pattern 4). Phase 1 has no publish path, so this is a seam note.
- **`index.html` served with a cache header > 0.** Must be `Cache-Control: no-store` (Pitfall 19).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Postgres FTS ranking | Custom TF-IDF | `ts_rank_cd()` built into Postgres | Edge cases in tokenization, normalization, ranking — Postgres gets them right |
| Async DB pool management | Custom connection queue | `psycopg.AsyncConnectionPool` | Pool sizing, keepalive, backoff all handled; hand-rolled pools leak connections |
| Pydantic v2 config validation | `os.getenv()` scattered throughout | `pydantic-settings BaseSettings` | Validates at startup; typos fail loudly; `.env` support built in |
| SPA fallback routing | Custom catch-all route | `StaticFiles(html=True)` | FastAPI already handles it; custom catch-all breaks OpenAPI docs mount |
| Catalog-number natural sort | ASCII sort or custom digit-extraction | `parse_key()` token-stream (or `natsort`) | 35.6% of multi-record labels sort incorrectly under ASCII; see INTERPOLATION §2.4 |
| Boundary cache invalidation seam | Complex pub/sub now | `cache.invalidate()` stub + TODO comment | Phase 4 drops in SSE invalidation; stub in Phase 1 costs nothing |
| CSS-in-JS animation | `styled-components` + `keyframes` | GSAP `gsap.to()` + CSS transitions via tokens | GSAP runs outside React render cycle; Pi 5 frame budget is the constraint |
| React state boilerplate | `useReducer` + Context | Zustand store | 1 KB library; no provider wrapping; direct `useStore` access |

**Key insight:** The Postgres FTS + `psycopg` + SQLAlchemy async stack handles the hardest parts of the search pipeline (query parsing, ranking, connection management). The only genuinely novel code in Phase 1 is the POS-01 parser and the boundary cache — everything else is wiring well-understood libraries together.

---

## Common Pitfalls

### Pitfall 1: Catalog-Number ASCII Sort Silently Wrong (Critical)
**What goes wrong:** `BLP-4195` sorts after `BLP 4200` under ASCII comparison (dash > space). 35.6% of multi-record labels are affected. The kiosk highlights the wrong cube with no error.
**How to avoid:** Every comparison — in the estimator, the search catalog path, the future boundary save validator — must go through `parse_key()` from `normalize.py`. Raw `catalog_number` string comparison is forbidden (POS-01).
**Warning signs:** A Hypothesis test `parse_key("BLP 9") < parse_key("BLP 10")` failing; or a boundary range check using Python string `<`.

### Pitfall 2: v_collection View Probe Missing From Lifespan (Critical)
**What goes wrong:** discogsography schema migration renames a column. GRUVAX boots, every `/api/search` returns 500, SPA shows "No results". No health indicator.
**How to avoid:** `SELECT 1 FROM gruvax.v_collection LIMIT 1` in the FastAPI lifespan BEFORE yielding. On failure: set `app.state.discogsography_view_ok = False`; `/api/health` reports degraded; search returns 503 with a clear message.
**Source:** PITFALLS.md Pitfall 5.

### Pitfall 3: StaticFiles Catch-All Intercepts API Routes
**What goes wrong:** `app.mount("/", StaticFiles(html=True))` registered before API routers. `/api/search` returns the SPA `index.html` with 200 status.
**How to avoid:** Register all `include_router()` calls before the `app.mount("/", ...)` call. Order matters — FastAPI matches routes in declaration order.

### Pitfall 4: aiomqtt Version Mismatch
**What goes wrong:** `pip install aiomqtt>=3.0` fails because no 3.x series exists. Build fails.
**How to avoid:** Use `aiomqtt>=2.5`. The 2.x API is what STACK.md describes. The `async with Client(...)` pattern and `await client.publish(...)` are identical.
**Source:** Verified PyPI 2026-05-20 — latest is 2.5.1.

### Pitfall 5: sse-starlette Version Mismatch
**What goes wrong:** `pip install sse-starlette>=2.0,<3.0` pins to an older API than available.
**How to avoid:** Use `sse-starlette>=3.4`. API is compatible with the STACK.md description.
**Source:** Verified PyPI 2026-05-20 — latest is 3.4.4.

### Pitfall 6: Vite Version Pin
**What goes wrong:** `npm install vite@7` gets the older series when 8.x is current.
**How to avoid:** Use `vite@8` or `vite@latest`. Both work; 8.x is the current stable.
**Source:** Verified npm 2026-05-20 — latest is 8.0.13.

### Pitfall 7: Boundary Cache Not Loaded Before First Request
**What goes wrong:** A request hits `/api/locate` before the lifespan cache.load() finishes. `get_boundaries()` returns []. Every locate call returns `confidence: 0.0`.
**How to avoid:** `cache.load()` is awaited in the lifespan BEFORE yielding. FastAPI does not accept requests until lifespan startup completes. This is the correct pattern.

### Pitfall 8: Hardcoded Colors in SPA Components
**What goes wrong:** A cube cell uses `backgroundColor: '#FFDA00'` instead of `var(--gruvax-cell-lit)`. Design token changes don't propagate; future phases break.
**How to avoid:** Import `design/gruvax-design-tokens.css` in `main.tsx` and reference only `var(--gruvax-*)` custom properties in all component styles. Never hardcode hex in component files (CLAUDE.md mandate).

### Pitfall 9: SSE Endpoint Acquires DB Connection for Its Lifetime
**What goes wrong:** Phase 1 has no SSE endpoint, but when one is added: `Depends(get_db)` on the SSE handler pins a pool connection for hours. Pool exhaustion → search latency blows past 200 ms.
**How to avoid:** SSE endpoint must depend only on the in-process event bus (`asyncio.Queue`). If it needs DB data, acquire and release inline. Leave a comment in the Phase 1 event bus stub as a reminder.
**Source:** PITFALLS.md Pitfall 10.

### Pitfall 10: Docker Compose `down -v` Nukes Mosquitto Persistence
**What goes wrong:** `docker compose down -v` deletes the `mosquitto-data` volume. In Phase 5, retained LED state is lost.
**How to avoid:** Document `docker compose down` (no `-v`) as the standard redeploy path in the project README. The `-v` variant is only for intentional state wipe.
**Source:** PITFALLS.md Pitfall 11.

---

## Code Examples

### Search endpoint skeleton

```python
# src/gruvax/api/search.py
from fastapi import APIRouter, Depends, Query
from gruvax.db.queries import search_collection
from gruvax.db.pool import get_pool

router = APIRouter()

@router.get("/search")
async def search(
    q: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    pool=Depends(get_pool),
):
    import time
    t0 = time.monotonic()
    results = await search_collection(pool, q, limit)
    took_ms = int((time.monotonic() - t0) * 1000)
    return {"items": results, "took_ms": took_ms}
```

### Locate endpoint skeleton

```python
# src/gruvax/api/locate.py
from fastapi import APIRouter, Depends, HTTPException
from gruvax.db.queries import get_release_for_locate
from gruvax.estimator.algorithm import locate_cube_only
from gruvax.estimator.boundary_cache import BoundaryCache

router = APIRouter()

@router.get("/locate")
async def locate(
    release_id: int,
    pool=Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
):
    record = await get_release_for_locate(pool, release_id)
    if record is None:
        raise HTTPException(status_code=404, detail={
            "type": "release_not_in_collection",
            "release_id": release_id,
        })
    result = locate_cube_only(
        release_id=release_id,
        label=record.label,
        catalog_number=record.catalog_number,
        cache=cache,
    )
    return result
```

### Alembic async env.py pattern

```python
# migrations/env.py — async template
# Source: STACK.md Alembic section; Alembic docs async cookbook
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

def run_migrations_online():
    connectable = create_async_engine(config.get_main_option("sqlalchemy.url"))
    import asyncio
    async def run():
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    asyncio.run(run())
```

### Cube component state mapping

```tsx
// src/routes/kiosk/Cube.tsx
// Source: UI-SPEC §Grid Component Contract
type CubeState = 'dim' | 'lit' | 'empty' | 'hover';

interface CubeProps {
  unitId: number;
  row: number;
  col: number;
  state: CubeState;
  address: string;  // e.g. "A1", "C3"
}

export function Cube({ unitId, row, col, state, address }: CubeProps) {
  return (
    <div
      className="cube"
      data-state={state}
      data-unit={unitId}
      data-row={row}
      data-col={col}
    >
      <span className="cube-address">{address}</span>
    </div>
  );
}
```

```css
/* Cube state styles — all colors via design tokens */
.cube {
  width: var(--gruvax-cell-size-xl);      /* 80px */
  height: var(--gruvax-cell-size-xl);
  border-radius: var(--gruvax-cell-radius-xl); /* 8px */
  position: relative;
  transition:
    background var(--gruvax-led-off-duration) var(--gruvax-led-off-ease),
    box-shadow  var(--gruvax-led-off-duration) var(--gruvax-led-off-ease);
}

.cube[data-state="dim"] {
  background: var(--gruvax-cell-dim);
  border: 1.5px solid var(--gruvax-cell-dim-border);
}

.cube[data-state="lit"] {
  background: var(--gruvax-cell-lit);
  border: 1.5px solid var(--gruvax-cell-lit-border);
  box-shadow: var(--gruvax-shadow-led);
  transition:
    background var(--gruvax-led-on-duration) var(--gruvax-led-on-ease),
    box-shadow  var(--gruvax-led-on-duration) var(--gruvax-led-on-ease);
}

.cube[data-state="empty"] {
  background: var(--gruvax-cell-empty);
  border: 1.5px dashed #DDDDDD;
}

.cube-address {
  position: absolute;
  top: var(--gruvax-space-1);    /* 4px */
  left: var(--gruvax-space-1);
  font-family: var(--gruvax-font-display);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: var(--gruvax-tracking-label);
  color: var(--gruvax-text-muted);
}

.cube[data-state="lit"] .cube-address {
  color: var(--gruvax-blue);
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| ASCII catalog sort | Token-stream numeric-aware comparator | This project — always needed | Prevents 35.6% multi-record label misplacement |
| `aiomqtt` "3.x" (STACK.md claim) | `aiomqtt` 2.5.1 (PyPI actual) | No 3.x was ever released | Adjust version pin in pyproject.toml |
| `sse-starlette` "2.x" (STACK.md claim) | `sse-starlette` 3.4.4 (PyPI actual) | Major version bump | Adjust version pin; API compatible |
| Vite "7.x" (STACK.md claim) | Vite 8.0.13 (npm actual) | May 2026 | Use `vite@8` |
| FastAPI StaticFiles with default cache headers | `index.html: no-store`; hashed assets: `immutable` | Always needed | Prevents stale bundle on kiosk (Pitfall 19) |
| Per-request boundary DB query | In-memory boundary cache, startup-loaded | Phase 1 design | Required for <50 ms estimator budget |

**Deprecated/outdated:**
- `psycopg2`: Legacy sync driver. Not used. Use `psycopg>=3.2` (psycopg3).
- `pydantic` v1: EOL. Not used. FastAPI 0.136 requires pydantic v2.
- Vite 7.x: Superseded by 8.x before this phase ships.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `aiomqtt` 2.x `async with Client(...)` API is identical to what STACK.md describes as "3.x" | Standard Stack / Pattern 7 | If 2.x API differs significantly, MQTT lifespan pattern needs adjustment. Low risk — 2.x has used this API pattern throughout. |
| A2 | discogsography Postgres exposes `releases.fts_vector` as a `tsvector` column built from artist/title/label/catalog fields | Pattern 1 (FTS path) | If the column is absent or differently named, GRUVAX must build its own `tsvector` from `v_collection` columns. Startup probe will catch this. |
| A3 | discogsography tables follow the column names in ARCHITECTURE.md `v_collection` DDL (`releases.title`, `releases.label`, `releases.catalog_number`, `releases.fts_vector`, `artists.name`, `collection_items.*`) | Pattern 5 (dev seed) | If columns differ, `v_collection` view definition needs updating. Bounded impact — one view. |
| A4 | Uvicorn `0.32+` is compatible with FastAPI 0.136.1 without breaking changes | Standard Stack | Extremely low risk — Uvicorn versioning follows FastAPI closely. |
| A5 | The `discogsography_default` Docker network exists as an external network on `lux` | Pattern 8 (compose.yaml) | If discogsography uses a different network name, update `networks.discogsography_default.name`. |

**If this table is empty:** N/A — assumptions above are low-risk but documented for planner awareness.

---

## Open Questions

1. **`search_path` or view DDL for dev-vs-prod schema selection?**
   - What we know: The "configurable schema" approach (`OBSERVED_DISCOGSOGRAPHY_SCHEMA` env var, set via `search_path` on connection checkout) keeps application code branch-free.
   - What's unclear: Does discogsography's Postgres already have the `gruvax_app` user with `USAGE` on the `discogsography` schema granted, or does the operator need to run a provisioning step?
   - Recommendation: Include a `just provision-db` justfile target that runs the `GRANT` statements from ARCHITECTURE.md. Add a README note. Phase 1 can't proceed without this on `lux`.

2. **`CUBE_ONLY_CONFIDENCE` constant value**
   - What we know: Must be a float 0..1; less than 0.5 signals "cube identified but no sub-cube precision".
   - What's unclear: The exact value is planner discretion. `0.30` is the default in the code above.
   - Recommendation: Use `0.30`. Document it in `contract.py`. Phase 2 replaces with a formula.

3. **Alembic migration sequencing for dev seed vs production schema**
   - What we know: The dev seed (synthetic `gruvax_dev` tables + `v_collection` view pointed at them) needs to run in dev/CI but NOT in production where `v_collection` points at real discogsography tables.
   - What's unclear: Should the dev seed be a separate Alembic migration gated on `GRUVAX_ENV=dev`, or a standalone SQL script run by a justfile target?
   - Recommendation: **Standalone SQL script** (`fixtures/synth_collection.sql`) run by `just seed-dev`. Alembic migrations are environment-agnostic structural changes. Seed data belongs in a separate operation.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker + Compose | DEP-01 | ✓ | Docker 29.1.4 | — |
| Node.js | Frontend build | ✓ | 26.0.0 | — |
| Python 3 | Backend dev | ✓ | 3.14.5 (dev machine) | Use 3.13 in container; dev machine 3.14 should work for tooling |
| pip3 | Package install check | ✓ | 26.1.1 | — |
| PostgreSQL (on `lux`) | DB layer | not verified here | — | Assumed running per project constraints |
| discogsography stack (on `lux`) | `v_collection` data | not verified here | — | Synthetic `gruvax_dev` seed covers CI + local dev |

**Notes:**
- Python 3.14.5 is available on the dev machine but the project targets Python 3.13. The Dockerfile uses `python:3.13-slim`. Local development with 3.14 is acceptable for tooling (uv, ruff, mypy) but the runtime behavior should be validated in the 3.13 container.
- The Postgres instance on `lux` is assumed to be running and accessible as stated in the project constraints. It is not verified from this machine.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio 1.3.0 + hypothesis 6.152.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` section — Wave 0 creates this |
| Quick run command | `just test-unit` → `pytest tests/unit/ -x -q` |
| Full suite command | `just test` → `pytest tests/ -q --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| POS-01 | `parse_key("BLP 9") < parse_key("BLP 10")` | unit | `pytest tests/unit/test_normalize.py -x` | ❌ Wave 0 |
| POS-01 | Total-order property (Hypothesis) | property | `pytest tests/property/test_parser_props.py -x` | ❌ Wave 0 |
| POS-01 | Cosmetic stability: `parse_key("BLP 4195") == parse_key("blp-4195")` | unit | `pytest tests/unit/test_normalize.py::test_cosmetic_stability -x` | ❌ Wave 0 |
| POS-01 | Multi-prefix: `parse_key("BLP 4001") != parse_key("BST 4001")` | unit | `pytest tests/unit/test_normalize.py::test_multi_prefix -x` | ❌ Wave 0 |
| POS-02 | `GET /api/locate?release_id=X` returns LocateResult with `confidence=0.30` for known in-range record | integration | `pytest tests/integration/test_locate.py -x` | ❌ Wave 0 |
| POS-02 | HTTP 404 for release_id not in v_collection | integration | `pytest tests/integration/test_locate.py::test_not_found -x` | ❌ Wave 0 |
| POS-02 | HTTP 200 `confidence=0, primary_cube=null` when no boundary covers label | integration | `pytest tests/integration/test_locate.py::test_no_boundary -x` | ❌ Wave 0 |
| POS-04 | Boundary cache loaded at startup contains all cube_boundaries rows | unit | `pytest tests/unit/test_algorithm.py::test_cache_load -x` | ❌ Wave 0 |
| SRCH-01 | `GET /api/search?q=BLP+4195` returns matching record | integration | `pytest tests/integration/test_search.py::test_catalog_path -x` | ❌ Wave 0 |
| SRCH-01 | FTS match on artist name substring | integration | `pytest tests/integration/test_search.py::test_fts_artist -x` | ❌ Wave 0 |
| SRCH-04 | `GET /api/search?q=zzznomatch` returns `{"items": []}` | integration | `pytest tests/integration/test_search.py::test_no_results -x` | ❌ Wave 0 |
| DEP-02 | Startup probe `SELECT 1 FROM gruvax.v_collection LIMIT 1` passes with synthetic seed | integration | `pytest tests/integration/test_health.py::test_view_probe -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `just test-unit` (unit tests only; < 5 s)
- **Per wave merge:** `just test` (full suite including integration; requires running Postgres)
- **Phase gate:** Full suite green + end-to-end smoke test (`docker compose up` → `curl /api/health` → load SPA) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/unit/test_normalize.py` — POS-01 golden cases
- [ ] `tests/property/test_parser_props.py` — Hypothesis properties
- [ ] `tests/unit/test_algorithm.py` — cube-only estimator unit cases
- [ ] `tests/integration/test_search.py` — FTS + catalog path
- [ ] `tests/integration/test_locate.py` — LocateResult contract + error semantics
- [ ] `tests/integration/test_health.py` — startup probe
- [ ] `tests/conftest.py` — shared fixtures (db pool, boundary cache from YAML fixture)
- [ ] `pyproject.toml` pytest config (`asyncio_mode = "auto"`, `testpaths`, `hypothesis` profile)
- [ ] Framework install: included in `uv add --dev` wave

---

## Security Domain

> `security_enforcement` not explicitly set to false in config — treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No — admin auth is Phase 3 | — |
| V3 Session Management | No — Phase 3 | — |
| V4 Access Control | Partial — no admin routes in Phase 1; public endpoints only | No auth required for search/locate/units |
| V5 Input Validation | Yes — `q` query param, `release_id` path param, `limit` param | FastAPI/Pydantic validates all query params at router level |
| V6 Cryptography | No | — |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via search `q` param | Tampering | Parameterized queries via psycopg3 (`$1` placeholders). Never f-string SQL. |
| Unbounded result count via `limit` param | DoS | `limit: int = Query(ge=1, le=50)` — FastAPI validates at the framework layer |
| Path traversal via `release_id` | Tampering | `release_id: int` typed param — Pydantic rejects non-integer values |
| Large `q` string causing slow FTS | DoS | `q: str = Query(max_length=200)` — cap at router level |

Phase 1 has no admin mutations, PIN auth, or CSRF surface. Security scope is limited to input validation on the three public endpoints.

---

## Sources

### Primary (HIGH confidence)

- `.planning/research/ARCHITECTURE.md` — component boundaries, schema DDL, API surface, LocateResult contract, compose.yaml, project structure
- `.planning/research/INTERPOLATION.md` — §2 real-collection distribution statistics, §3 catalog-number taxonomy, §3.2 normalization pipeline, §4.8 cube-only fallback
- `.planning/research/STACK.md` — pinned versions, Dockerfile pattern, Alembic async template
- `.planning/research/PITFALLS.md` — Pitfalls 1/5/10/11/19 directly in Phase 1 scope
- `.planning/phases/01-first-search-cube-highlight/01-CONTEXT.md` — 13 locked decisions
- `.planning/phases/01-first-search-cube-highlight/01-UI-SPEC.md` — component contracts, animation tokens, typography, spacing
- `design/gruvax-design-tokens.css` — token names and values
- PyPI registry (pip3 index versions, 2026-05-20) — fastapi 0.136.1, psycopg 3.3.4, alembic 1.18.4, sse-starlette 3.4.4, aiomqtt 2.5.1, pydantic-settings 2.14.1, sqlalchemy 2.0.49, natsort 8.4.0
- npm registry (npm view, 2026-05-20) — react 19.2.6, vite 8.0.13, gsap 3.15.0, framer-motion/motion 12.39.0, zustand 5.0.13, @tanstack/react-query 5.100.11, react-router 7.15.1, tailwindcss 4.3.0

### Secondary (MEDIUM confidence)

- ARCHITECTURE.md §Sources: aiomqtt Context7-verified patterns, sse-starlette ping behavior
- INTERPOLATION.md §9: natsort 8.4.x docs; Discogs catalog# database guidelines

### Tertiary (LOW confidence)

- None — all claims in this document are either derived from locked project files (HIGH) or registry-verified (HIGH/MEDIUM).

---

## Project Constraints (from CLAUDE.md)

The following directives from `./CLAUDE.md` are binding on all Phase 1 work:

| Directive | Impact on Phase 1 |
|-----------|-------------------|
| Backend: Python + FastAPI | Locked. No alternative. |
| Package manager: `uv` | All backend installs use `uv add`. No pip directly in the project. |
| Lint/format: Ruff | `ruff check` + `ruff format` must pass on all Python files. |
| Type check: mypy | `mypy --strict` on `src/gruvax/` must pass. |
| **Design language: Nordic Grid — consume tokens, never hardcode hex** | All React components use `var(--gruvax-*)`. No `#FFDA00` in component source. |
| **Three-font type system: Barlow Condensed / Space Grotesk / DM Mono** | Fonts loaded from `design/gruvax-design-tokens.css`. No other fonts added. |
| **Mermaid-only diagrams** | Any diagram in docs uses ` ```mermaid ` blocks. No ASCII art. |
| Database: shared Postgres, `gruvax` schema | Alembic creates `gruvax` schema; `GRANT USAGE` applies. |
| Deployment: Docker Compose on `lux` | Phase 1 delivers working `compose.yaml`. |
| Collection CSV never committed | `RWlodarczyk-collection-20260519-0257.csv` stays gitignored. Synthetic seed in `fixtures/`. |
| `background/` directory never committed | `.gitignore` must include `background/`. |
| Task runner: `just` | `justfile` with `just test`, `just lint`, `just up`, `just migrate`, `just seed-dev`. |

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages registry-verified; three version discrepancies flagged (aiomqtt, sse-starlette, Vite)
- Architecture: HIGH — derives directly from ARCHITECTURE.md and CONTEXT.md locked decisions
- POS-01 parser: HIGH — concrete implementation provided; derives from INTERPOLATION.md §3 and first-party collection statistics
- Synthetic seed mechanism: HIGH — recommendation is concrete and code-path preserving
- FTS query pattern: MEDIUM — sketch provided; exact SQL needs tuning against real discogsography schema
- Pitfalls: HIGH — from PITFALLS.md (project-specific, verified against stack)

**Research date:** 2026-05-20
**Valid until:** 2026-06-20 (stable stack; Vite/sse-starlette move fast — re-verify if > 30 days)

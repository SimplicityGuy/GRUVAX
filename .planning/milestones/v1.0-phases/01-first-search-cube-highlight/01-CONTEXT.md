# Phase 1: First Search → Cube Highlight - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

The thinnest end-to-end vertical slice (Walking Skeleton) that proves the Core Value:
a user types a query and sees the correct cube highlighted on an N×4×4 grid, served by
`gruvax-api`, against **fixture-seeded** boundaries — before any admin UI, real
interpolation, SSE, offline handling, or LED publishing exists.

**In scope (15 requirements):** SRCH-01, SRCH-02, SRCH-03, SRCH-04, SRCH-05, SRCH-06,
CUBE-01, CUBE-02, CUBE-05, CUBE-06, POS-01, POS-02, POS-04, DEP-01, DEP-02.

Concretely, Phase 1 delivers:
- The `gruvax` schema + `v_collection` read-only contract over discogsography (DEP-02).
- `gruvax.units` + `gruvax.cube_boundaries` tables (Alembic), seeded from a committed
  fixture; an in-memory boundary cache that loads at startup (POS-04).
- The POS-01 parser/comparator (normalized catalog#) as shared infrastructure.
- `GET /api/search` (FTS + catalog path), `GET /api/locate` returning the locked
  `LocateResult` contract with the cube-only fallback estimator (POS-02).
- A React SPA served by FastAPI `StaticFiles`: search box + ranked results + clear-X +
  no-results + loading indicator, an N×4×4 grid (32 cubes) with address overlays and a
  desaturated empty state, and primary-cube highlight on selection.
- A `docker compose` stack (`gruvax-api` + `mosquitto`) that comes up on `lux` (DEP-01).

**Out of scope (later phases):** real sub-cube interpolation (P2), multi-cube label-span
secondary highlight / animation / fill-level / reverse-lookup (P2/P3), admin + PIN +
boundary editing (P3), SSE realtime + offline + recently-pulled (P4), LED/MQTT publish
path (P5), wizards + import/export (P6), Pi kiosk runtime + observability hardening (P7).

</domain>

<decisions>
## Implementation Decisions

### Phase Scope & Definition of Done
- **D-01:** "Demoable" for Phase 1 = `docker compose up` on `lux` + the SPA opened in **any
  browser**. The full Pi kiosk runtime (Raspberry Pi OS Trixie + labwc + Chromium `--kiosk`
  + `systemd --user` autostart) and deployment hardening are **deferred to Phase 7**.
  ROADMAP Phase 1 success criterion 1 ("on the Pi 5") is to be **softened** to match.
- **D-02:** The ~200 ms search→highlight budget is a Phase 1 **design target measured
  locally**, not a hard pass/fail gate. The real p95 gate (Pi 5 + ~3,000 records;
  estimator p95 ≤ 50 ms, POS-03) is enforced in **Phase 2** and **Phase 7**.

### Boundary Data Foundation
- **D-03:** Build the **real** `gruvax.units` + `gruvax.cube_boundaries` tables via Alembic
  in Phase 1 (per ARCHITECTURE.md schema). Seed them from the committed fixture; the
  in-memory boundary cache loads **from the DB** at startup (POS-04). No cache-only
  shortcut — Admin (P3) and SSE invalidation (P4) write the same tables, avoiding rework.
- **D-04:** Boundary fixture format is **YAML** (human-authorable, diff-friendly for 32
  cubes of nested first/last `(label, catalog#)` bounds; aligns with the Phase 6
  import/export direction).
- **D-05:** The **committed** fixture holds **synthetic** boundaries that match the
  synthetic collection seed, so the search→highlight demo works for anyone cloning the repo.
  The owner's **real** boundaries and the **real Discogs CSV stay gitignored/local** (repo
  hygiene constraint preserved). Boundaries must reference the same labels as the collection
  they are validated against.

### Collection Data (dev / CI)
- **D-06:** Ship a small **synthetic collection seed** shaped like `gruvax.v_collection` as
  the **default** for CI and local dev. The owner can point at a **real discogsography
  Postgres via env var** for true data. The synthetic dataset should mirror the real
  collection's characteristics (varied catalog-number formats, singleton + multi-cube
  labels per INTERPOLATION §2) so search and locate are exercised meaningfully.
- **D-07:** `v_collection` remains the **only** read surface onto discogsography (DEP-02);
  it is probed at startup (`SELECT 1 FROM gruvax.v_collection LIMIT 1`) and health degrades
  if the upstream view is missing (Pitfall 5).

### Search
- **D-08:** Search uses **Postgres FTS** over `v_collection.fts_vector` for artist/title/label,
  **plus a normalized exact/prefix match path on `catalog_number`** (fed by the POS-01
  normalizer) so queries like `BLP 4195` reliably hit despite poor FTS tokenization. Single
  ranked results list; the top result auto-highlights its cube (SRCH-02 + CUBE-02).
- **D-09:** Phase 1 search satisfies SRCH-01..06 only: client-side debounce (SRCH-06),
  loading indicator shown only when a request exceeds ~300 ms (SRCH-05), visible clear-X
  (SRCH-03), and a "no results" state (SRCH-04). Out of scope here: "did you mean"/trigram
  (SRCH-07), numeric-leading catalog ranking boost (SRCH-08), recently-pulled (SRCH-09).

### LocateResult Contract (locked in Phase 1 for all later phases)
- **D-10:** Phase 1 ships the **cube-only fallback** estimator (INTERPOLATION §4.8):
  `sub_cube_interval: null`. The contract
  `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}`
  is **locked here**; Phase 2 swaps in the §4.1 index-based estimator behind the same shape.
- **D-11:** `confidence` is a **float (0..1)** per ARCHITECTURE.md — **not** a string enum.
  Cube-only results use a documented constant confidence value + `estimator_version:
  "cube-only-v1"` + `sub_cube_interval: null`. This **resolves the ARCHITECTURE-vs-ROADMAP/
  INTERPOLATION inconsistency** where `"cube_only"`/`"singleton"` string tags appear; the
  ROADMAP criterion 5 wording (`confidence: "cube_only"`) should be reconciled to the float
  representation.
- **D-12:** Phase 1 computes a **real `label_span`** (all cubes whose normalized
  `[first,last]` range covers the record's label, via the POS-01 comparator), even though
  the multi-cube *secondary highlight* UI (CUBE-03) lands in Phase 2 — Phase 1 UI highlights
  only `primary_cube` (CUBE-02). Error semantics per ARCHITECTURE: HTTP 404 for
  not-in-collection; HTTP 200 with `confidence: 0`, `primary_cube: null`, `label_span: []`
  when no boundary covers the label (UI treats as "no cube assigned yet").

### Parser / Comparator (POS-01)
- **D-13:** POS-01 is shared infrastructure built in Phase 1: normalizes catalog numbers
  (case-fold, separator-collapse, NFKC, numeric-aware split) and is reused by the search
  catalog path, the estimator, and (later, P3) the boundary-save validator. Raw-string
  comparison is forbidden. The **specific parsing strategy** (token-stream split vs
  `natsort`, INTERPOLATION §3.1) is **delegated to the researcher** to recommend against the
  real collection — not pre-decided here.

### Claude's Discretion
- All **visual/interaction design** (cube colors, glow/LED motion, grid arrangement,
  results layout, address-label scheme) → `/gsd-ui-phase 1` + the committed design system.
- The **catalog parser strategy** (C/token-split vs D/`natsort`) → researcher.
- The **exact synthetic-seed mechanism** for `v_collection` (seed discogsography-shaped
  source tables vs a dev-only equivalent) → planner/researcher, provided `v_collection`
  stays the only read surface (D-07).
- **FTS ranking weights, debounce interval, results page size** (ARCHITECTURE suggests
  default 20 / max 50; ~6 rows fit a 7" screen) → planner discretion within architecture
  guidance.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Architecture & Contracts (authoritative for this phase)
- `.planning/research/ARCHITECTURE.md` — component boundaries, `gruvax` schema DDL
  (`units`, `cube_boundaries`), `v_collection` view + RO grant pattern, API surface
  (`/api/search`, `/api/locate`, `/api/units`, `/api/cubes/...`), the **LocateResult /
  SubInterval contract + error semantics + latency budget**, recommended project structure
  (`src/gruvax/...`, `frontend/...`), and the illustrative `compose.yaml`.
- `.planning/research/INTERPOLATION.md` — §1 contract recap; §2 real-collection
  distribution (drives synthetic-seed realism); §3 catalog-number parsing taxonomy + §3.2
  normalization (POS-01); **§4.8 no-interpolation / cube-only fallback** (the Phase 1
  estimator); §6 edge cases (singleton, no-covering-boundary).
- `.planning/research/STACK.md` — pinned versions (mirrored in root `CLAUDE.md`):
  Python 3.13, FastAPI 0.136.x, psycopg 3.2 async, SQLAlchemy 2.0 async, Alembic 1.18.x,
  React 19 + Vite 7 + Tailwind, FastAPI `StaticFiles`, `eclipse-mosquitto:2.1-alpine`.
- `.planning/research/PITFALLS.md` — Pitfall 5 (`v_collection` as the only discogsography
  contact surface; startup probe) is directly in scope for Phase 1.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — definitions for SRCH-01..06, CUBE-01/02/05/06, POS-01/02/04,
  DEP-01/02 (the 15 phase requirements).
- `.planning/ROADMAP.md` — Phase 1 section: goal + 5 success criteria (note D-01/D-11
  reconciliations to criteria 1 and 5).
- `.planning/PROJECT.md` — Core Value, constraints, key decisions, repo-hygiene rule
  (CSV + `background/` never committed).

### Design System (for the SPA — consume, never hardcode)
- `design/gruvax-design-language.md` — Nordic Grid spec; the Kallax cube is the atomic UI
  unit; cell states (dim/lit/hover/selected/empty); LED-physics motion.
- `design/gruvax-design-tokens.css`, `design/gruvax-design-tokens.json` — token contract
  wired into the frontend (IKEA blue `#0051A2`, LED yellow `#FFDA00`, off-white `#F7F9FC`).
- `CLAUDE.md` — project conventions (design language, three-font type system, Mermaid
  diagrams, README pattern).

### Codebase
- `.planning/codebase/CONVENTIONS.md` — synced conventions (design + documentation rules).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Design tokens** (`design/gruvax-design-tokens.css`/`.json`): the contract between design
  and the new SPA — import rather than authoring colors/fonts.
- **Project-structure blueprint** (ARCHITECTURE.md §Recommended Project Structure): the
  intended `src/gruvax/...` and `frontend/src/...` layout to follow when scaffolding.

### Established Patterns
- **CONVENTIONS.md / CLAUDE.md** lock the visual + documentation conventions (Nordic Grid,
  Mermaid-only diagrams, ALL-CAPS labels via Barlow Condensed).

### Integration Points
- **discogsography Postgres** is the only external dependency, reached **exclusively** via
  `gruvax.v_collection` (RO). Everything else in Phase 1 is greenfield — no application
  code exists in the repo yet (only `design/`, `.planning/`, `README.md`, `CLAUDE.md`).

</code_context>

<specifics>
## Specific Ideas

- The **LocateResult / SubInterval dataclasses** and the **`v_collection` DDL** in
  ARCHITECTURE.md are concrete, copy-from references — implement to those shapes.
- The illustrative **`compose.yaml`** in ARCHITECTURE.md (env vars, healthchecks,
  `mosquitto` with **no `ports:`** exposure in v1, `internal` + external
  `discogsography_default` networks) is the intended deployment shape for DEP-01/DEP-03.
- The **synthetic collection seed** should resemble the real collection's catalog-format
  variety (e.g., `BLP 4195`, `KC 32731`, `ECM 1064`, `1SHOT-002`, multi-prefix labels,
  singletons) so the FTS + catalog path and the cube-only locate are genuinely exercised.

</specifics>

<deferred>
## Deferred Ideas

- **Real sub-cube interpolation** (INTERPOLATION §4.1 index-based; POS-05) → Phase 2.
- **CUBE-03** multi-cube label-span secondary highlight, **CUBE-08** selection-lands
  animation, **CUBE-10** single-record tick-mark → Phase 2.
- **CUBE-07** fill-level indicator, **CUBE-09** reverse-lookup cube tap → Phase 3.
- **Admin / PIN / boundary editing / save-validator** → Phase 3.
- **SSE realtime invalidation + offline banner + recently-pulled** (RTM/OFF/PRIV, SRCH-09)
  → Phase 4. (Phase 1 cache loads at startup only; `boundary_changed` wiring is Phase 4.)
- **LED / MQTT publish path** → Phase 5. (Phase 1 stands up the `mosquitto` container per
  DEP-01, but no publish path yet.)
- **SRCH-07** did-you-mean / trigram, **SRCH-08** numeric-leading catalog ranking → Phase 2.
- **YAML/JSON import/export, wizards** → Phase 6.
- **Pi kiosk runtime + autostart + observability/deployment hardening** (per D-01) → Phase 7.

</deferred>

---

*Phase: 01-first-search-cube-highlight*
*Context gathered: 2026-05-19*

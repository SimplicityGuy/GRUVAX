# Phase 2: Real Position Estimation - Context

**Gathered:** 2026-05-20
**Status:** Ready for planning

<domain>
## Phase Boundary

The kiosk gains the ability to answer **"where exactly on the shelf"** — it adds a
**sub-cube position bar** and a **multi-cube label-span highlight** to the existing
cube highlight, backed by the **real §4.1 index-based estimator** swapped in behind the
`LocateResult` contract Phase 1 already locked, plus an **A/B harness** that proves §4.1
is the right default and two **search refinements** (did-you-mean, catalog-# boost).

**In scope (9 requirements):** CUBE-03, CUBE-04, CUBE-08, CUBE-10, POS-03, POS-05,
POS-06, SRCH-07, SRCH-08.

Concretely, Phase 2 delivers:
- The **§4.1 index-based estimator** (INTERPOLATION §4.1) behind the locked `LocateResult`
  shape, with **§4.8 cube-only** retained as the timeout/low-confidence fallback (POS-05).
- An **in-memory collection snapshot** (per-label record lists) so the estimator is
  **CPU-only, no DB calls** during compute, hitting p95 ≤ 50 ms (POS-03).
- A populated `sub_cube_interval` (normalized 0..1, may set `crosses_boundary`) + confidence
  calibration that drives the UI bar's intensity.
- Kiosk UI: **sub-cube position bar** (CUBE-04), **multi-cube label-span highlight**
  (CUBE-03), **singleton rendering** (CUBE-10), **selection-lands animation** (CUBE-08).
- A developer **A/B harness** (`run_all_algorithms.py`, POS-06) running §4.1 vs §4.8 against
  a synthetic planted-truth dataset (CI) and the local CSV (gitignored).
- Search: **did-you-mean** trigram suggestions (SRCH-07) and **catalog-# weight boost** on
  catalog-like queries (SRCH-08).

**Out of scope (later phases):** admin / PIN / boundary editing + save validator (P3);
SSE realtime invalidation, offline banner, recently-pulled, privacy floors (P4); LED/MQTT
publish path (P5); wizards + import/export (P6); observability + Pi kiosk hardening (P7).
§4.10 density-weighting, the tiered cascade (§5.1), KNN/isotonic, and the lookup-table
cache are explicitly **not** in v1 (INTERPOLATION §8.2–8.3).

</domain>

<decisions>
## Implementation Decisions

### Position Rendering & Confidence (CUBE-04, CUBE-10)
- **D-01:** The sub-cube bar **always renders but attenuates with confidence** — intensity/glow
  (and optionally width) scale with the `confidence` float. High confidence = crisp bright band;
  low = faint wide hint. No hard show/hide cliff (INTERPOLATION §5.3 spirit). This makes the bar
  an honest gradient over the whole collection, not a binary.
- **D-02:** **Singletons** (one owned record — 26.6% of records) render as a **faint full-cube
  band**, not a tick-mark and never a zero-width bar (Pitfall 21). ⚠ **This reinterprets CUBE-10**,
  whose literal wording says "tick-mark indicator … rather than a width-proportional range bar."
  The owner prefers the faint full-cube band (it reads as "one record, low confidence, scan the
  cube" and is consistent with D-01). **Planner must reconcile CUBE-10's wording** — same pattern
  as Phase 1's D-11 reconciliation of the contract vs ROADMAP wording.
- **D-03:** A **subtle textual cue** (e.g., "approx." / "~") appears **only when confidence is
  below the cube-only threshold**; above it, uncertainty is communicated **purely visually** via
  the bar/band rendering. Keeps the glance-and-go kiosk clean while still warning on the genuinely
  uncertain cases. The exact threshold + confidence formula → researcher/planner (see Discretion).

### Span Highlight & Lands Animation (CUBE-03, CUBE-08)
- **D-04:** The multi-cube label-span highlight is a **connecting underlay** — a structural
  band/connector drawn *under* the spanned cubes that visually links them as one run, with the
  bright **primary cube lit on top**. ⚠ It is a **new visual element** beyond the cube grid: it must
  read as structure and **must NOT recolor a lit cell** (design-language rule), and it **must handle
  geometry where spanned cubes wrap across rows or units** (sort order maps to row-major reading
  order, then next unit). **Flag for `/gsd-ui-phase 2`** to design within the Nordic Grid spec.
- **D-05:** The lands animation is **sequential cinematic**: span fade-in → primary-cube
  pulse/spring → sub-cube bar slide-in, total **≤ 600 ms** (matches ROADMAP success criterion 3),
  using the design language's LED-physics motion (springs on with overshoot, fades off smooth).
- **D-06:** A new search **hard-cancels and restarts** the in-flight animation (snap old highlight/
  bar off or jump to final, start the new one fresh) — never a cross-fade. Keeps a type-ahead kiosk
  from ever feeling "behind."

### Estimator Accuracy & Real-Shelf Truth (POS-05, POS-06)
- **D-07:** The A/B harness (POS-06) establishes ground truth via a **synthetic generator that plants
  known positions** across controlled distribution shapes (uniform, sparse-gappy, multi-prefix,
  singleton, etc.); it measures §4.1 vs §4.8 (and can preview §4.10) against that known truth.
  **CI-gated, no manual effort, and actually differentiates algorithms** (a rank-only proxy can't —
  §4.1 *is* rank-based so it would score perfect by construction). Runs against the synthetic CI
  dataset and the local CSV (gitignored).
- **D-08:** ⚠ **Success criterion 5 reframes.** "Prove §4.1 is the right v1 default" becomes
  "prove §4.1 ≥ §4.8 on synthetic planted-truth shapes + runtime budget." **Genuine real-shelf
  validation is deferred** until real boundaries exist (post Phase 3 admin / Phase 6 reshuffle),
  because boundaries are still fixtures and the owner has not done a real reshuffle. This is a
  deliberate softening parallel to Phase 1's D-01/D-02.
- **D-09:** Owner's physical shelving (only the owner can answer this — INTERPOLATION §8.1),
  which **confirms the locked algorithm and parser are correct**:
  - **Spacing: uniform / packed** — records sit in catalog order regardless of numeric gaps, so
    **index position = shelf position** → **§4.1 is correct**; §4.10 stays deferred.
  - **Multi-prefix labels: grouped by prefix** (all BLP, then all BST) → the Phase 1 Strategy-C
    parser's **prefix-first sort already matches the shelf**; no parser change needed.
  - **Multi-label records (~19%): shelved under the first label** listed → matches CSV/Discogs
    order, derivable and deterministic (no per-record overrides).
  - **Multi-value catalog#: first value** for sort/compare (already settled, INTERPOLATION §6).

### Search Refinements (SRCH-07, SRCH-08)
- **D-10:** "Did you mean?" (SRCH-07) is presented as a **single inline tappable suggestion row**
  in/above the no-results state ("Did you mean COLTRANE?"); tapping runs that query. User stays in
  control — no silent auto-correct.
- **D-11:** The suggestion trigger is **conservative** — fire only on a **high trigram-similarity**
  candidate when FTS returns nothing strong (matches REQUIREMENTS wording). Rare but almost always
  right; avoids embarrassing wrong guesses. Exact similarity threshold → planner, tuned against the
  real CSV's near-miss cases.
- **D-12:** The catalog-# ranking boost (SRCH-08) detects **leading-digit OR prefix+digits** queries
  (`4195` *and* `BLP 41` / `ECM 10`) and boosts the catalog-number field weight — covers how people
  actually type catalog numbers across the collection's varied formats.

### Claude's Discretion (delegated to researcher / planner)
- **Confidence calibration numbers** for §4.1 — the per-shape confidence formula (singleton low,
  multi-prefix medium, dense high; INTERPOLATION §5.1 / §8.2 action 8). Constraint: must map onto the
  D-01 attenuated-bar and the D-03 below-threshold text cue. Pick a sensible **cube-only/text-cue
  threshold** (the contract docstring references ~0.5; cube-only is 0.30).
- **In-memory collection snapshot design** — how per-label record lists are loaded at startup and
  held alongside the boundary cache to satisfy POS-03 (no DB during compute). v1 reloads at startup
  only; `boundary_changed`/sync-driven invalidation is Phase 4. Source is exclusively `gruvax.v_collection`.
- **Estimator versioning** — the `estimator_version` tag for §4.1 (e.g., `index-v1`) and how §4.8
  fallback is selected (timeout / low-confidence path).
- **`pg_trgm` availability** — confirm the trigram extension is enabled on the shared Postgres
  (discogsography very likely already uses it for FTS); SRCH-07 depends on it.
- **Did-you-mean similarity threshold** and **FTS ranking weights** for the catalog boost — tuned
  against the local CSV.
- **All exact visual/motion design** (underlay rendering, bar look, band/cue styling, animation
  curves) → `/gsd-ui-phase 2` within the committed design system.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Position Estimation (authoritative for this phase)
- `.planning/research/INTERPOLATION.md` — **§4.1** index-based estimator (the Phase 2 primary);
  **§4.8** cube-only fallback; **§4.10** density-weighted (deferred — context for D-09); **§5.1/§5.3**
  tiered-cascade + two-pass confidence (informs D-01/D-03 calibration); **§6** edge-case handling
  (singleton f=0.5, multi-value first-value, multi-label raw, barcode caps); **§7.2–7.6** golden cases,
  Hypothesis invariants, A/B harness, perf-budget proof, CI-vs-local split; **§8.1** owner-input
  questions (the basis for D-09); **§8.2/§8.3** planning actions (ship §4.1+§4.8, defer §4.10/cascade).
- `.planning/research/ARCHITECTURE.md` — `LocateResult` / `SubInterval` contract, error semantics,
  the **50 ms latency budget** (POS-03), boundary cache pattern, API surface.
- `.planning/research/PITFALLS.md` — **Pitfall 21** (singleton never a zero-width bar → D-02);
  Pitfall 1 (numeric-aware comparator); Pitfall 5 (`v_collection` only contact surface).

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — definitions for CUBE-03/04/08/10, POS-03/05/06, SRCH-07/08.
- `.planning/ROADMAP.md` — Phase 2 section: goal + 5 success criteria (note **D-02** reconciles
  CUBE-10 wording; **D-08** reframes/softens success criterion 5).
- `.planning/PROJECT.md` — Core Value, "position is computed not stored" key decision (rules out the
  §4.7 lookup table), repo-hygiene rule (CSV + `background/` never committed).

### Locked from Phase 1 (carry forward — do not re-decide)
- `.planning/phases/01-first-search-cube-highlight/01-CONTEXT.md` — D-10 (contract locked),
  D-11 (confidence is a float; cube-only = 0.30), D-12 (real `label_span` already computed),
  D-13 (POS-01 = Strategy-C token-stream parser; raw-string compares forbidden).
- `src/gruvax/estimator/contract.py` — the frozen `LocateResult` / `SubInterval` / `CubeRef`
  dataclasses to implement against (do not change shapes).
- `src/gruvax/estimator/algorithm.py` — `locate_cube_only` (§4.8); Phase 2 adds the §4.1 path and
  the fallback selector behind the same return type.
- `src/gruvax/estimator/normalize.py` — POS-01 normalizer + `catalog_in_range`; the estimator's only
  legal comparison path.
- `src/gruvax/estimator/boundary_cache.py` — the startup-loaded cache; the new collection snapshot
  should follow the same lifespan/`invalidate()` pattern.
- `src/gruvax/api/locate.py`, `src/gruvax/api/search.py` — the endpoints Phase 2 extends.

### Design System (consume tokens; never hardcode hex)
- `design/gruvax-design-language.md` — Nordic Grid spec; lit-cell rule ("never recolor a lit cell" →
  constrains D-04 underlay), LED-physics motion (D-05), cell states.
- `design/gruvax-design-tokens.css`, `design/gruvax-design-tokens.json` — token contract.
- `CLAUDE.md` — design language, three-font type system, Mermaid-only diagrams.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`LocateResult` / `SubInterval` contract** (`src/gruvax/estimator/contract.py`): already supports
  Phase 2 — `sub_cube_interval` (with `start`/`end`/`crosses_boundary`/`next_cube`) is defined and
  was deliberately unused in Phase 1. Phase 2 populates it; no shape change.
- **POS-01 normalizer** (`normalize.py`, `catalog_in_range`): the §4.1 estimator orders a label's
  records via this comparator — reuse, do not re-implement; raw-string compares forbidden (D-13).
- **BoundaryCache lifespan pattern** (`boundary_cache.py`): the new in-memory collection snapshot
  should mirror its load-at-startup + `invalidate()` seam.
- **Cube-only estimator** (`algorithm.py::locate_cube_only`): keep as the §4.8 fallback path.

### Established Patterns
- **CPU-only estimate, no DB during compute** (POS-03 / Phase 1 cache) — extends to the collection
  snapshot; the locate endpoint currently does one DB read for the target record (`get_release_for_locate`),
  but §4.1 needs the *whole label's* records, which must come from the in-memory snapshot, not a query.
- **Float confidence, not string enum** (D-11) — the attenuated bar (D-01) reads this float directly.
- **Frontend**: TanStack Query fires `/api/locate` imperatively per selection (Phase 1 note) — the
  sub-cube bar + span underlay consume the richer `LocateResult` from that same call.

### Integration Points
- `gruvax.v_collection` (RO) is the **only** source for the collection snapshot (DEP-02 / Pitfall 5).
- `/api/locate` returns the populated interval; the kiosk `ShelfGrid`/`Cube` components (Phase 1)
  gain the bar + underlay + animation; `/api/search` gains the did-you-mean + catalog-boost paths.

</code_context>

<specifics>
## Specific Ideas

- The §4.1 sketch in INTERPOLATION §4.1 (`position_by_index`: sort label records by `parse_key`,
  `f = idx / max(k-1, 1)`, map across `label_span`) is a concrete copy-from reference.
- Singleton convention: `k = 1 ⇒ f = 0.5` center by formula (§4.1/§6), but **rendered** as the
  faint full-cube band per **D-02** (not a tick).
- `run_all_algorithms.py` (POS-06) per INTERPOLATION §7.4 — per-distribution-shape MAE buckets,
  per-call timing (50 ms budget), confidence distribution; synthetic generator
  `tests/fixtures/synth_collection.py` parametrized over shape (§7.6).
- Hypothesis invariants to pin (§7.3): `primary_cube ∈ label_span`; `0 ≤ start ≤ end ≤ 1`;
  monotone position within a label; stability under cosmetic (case/separator/whitespace) noise.

</specifics>

<deferred>
## Deferred Ideas

- **§4.10 density-weighted interpolation** — fast-follow *only* if real-shelf observation later shows
  §4.1 feels off on sparse labels. The owner shelves uniform/packed (D-09), so this is deferred with
  confidence.
- **Owner-curated real golden positions** — produce after a real reshuffle exists (Phase 3 admin /
  Phase 6 wizard) to genuinely validate §4.1 on real data (closes the D-08 softening loop).
- **Tiered cascade (§5.1) per-label dispatcher** + monotone safety net (§5.2) — target architecture
  once the A/B harness's per-shape error bars are visible post-v1.
- **Real-shelf validation of multi-prefix grouping and multi-label assumptions** — confirm by eye
  during the Phase 6 reshuffle wizard run (INTERPOLATION §8.1 Q2/Q4).
- KNN (§4.5), isotonic (§4.9), and the precomputed lookup table (§4.7) — explicit hard-no for v1
  (INTERPOLATION §8.2; conflicts with "position is computed, not stored").

None of the above belong in Phase 2 — discussion stayed within scope.

</deferred>

---

*Phase: 02-real-position-estimation*
*Context gathered: 2026-05-20*

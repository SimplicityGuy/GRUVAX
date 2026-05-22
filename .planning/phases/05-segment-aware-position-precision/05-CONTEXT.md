# Phase 5: Segment-Aware Position Precision - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the one-span-per-cube boundary model with a **segment-aware** model: a bin (= a
physical Kallax cube) holds an ordered list of per-label segments. The owner maintains only
**cut points** (the first record of each bin) plus **optional physical-width overrides**;
everything else — which labels live in a bin, each segment's first/last record, per-segment
counts, and bin-fractions — is **derived by row-counting `gruvax.v_collection`** (never catalog
arithmetic). Ship a **two-level-interpolation** estimator (resolve bin+segment → offset by the
fractions of preceding labels in the bin → interpolate by row-rank within the segment) that
**supersedes §4.1** behind the unchanged `LocateResult` contract, and extend the Phase 3 admin
editor into a **cut-point + width-override** tool (view/edit/add cuts, set overrides) reusing the
existing diff-preview + change-set undo path. The locate hot path stays CPU-only, no DB,
p95 ≤ 50 ms.

**In scope (8 requirements):** SEG-01, SEG-02, SEG-03, SEG-04, SEG-05, SEG-06, SEG-07*, SEG-08.

\* **SEG-07 is amended this phase — see D-01.** The segment estimator still supersedes §4.1 and
`estimator_version` still reflects the change, but the "proven to meet-or-beat §4.1 via the
extended `run_all_algorithms.py` A/B harness before it becomes the v1 default" clause is
**dropped** by owner decision. This also relaxes **ROADMAP Phase 5 success criterion 4**.

**Out of scope (later phases):** bulk reshuffle / guided wizard + CSV/YAML import/export (Phase 6);
LED color/brightness/diagnostics + physical LED sub-span lighting (Phase 6 — depends on this
model); format-thickness sub-segment weighting (future); owner-curated real golden positions
(post-reshuffle). The dropped A/B comparison harness work is **descoped, not deferred** (D-01).

</domain>

<decisions>
## Implementation Decisions

### Estimator Cutover & Validation (SEG-06, SEG-07)
- **D-01:** **§4.1 is retired entirely.** The segment-aware two-level-interpolation estimator
  becomes the **sole index estimator** behind the unchanged `LocateResult` contract; **§4.8
  cube-only stays the timeout/low-confidence fallback** (as today). It ships **on trust**.
  ⚠ **This amends SEG-07 and relaxes ROADMAP Phase 5 success criterion 4:** the A/B
  "meet-or-beat §4.1" **proof gate is DROPPED** — `run_all_algorithms.py` is **not** extended
  with the segment estimator, there is **no comparison harness and no release gate**.
  `estimator_version` is still bumped to reflect the new algorithm. The discussion's earlier
  acceptance-bar ("win multi-label / tie single") and harness-shape ("multi-label + straddle")
  selections are **MOOT** — superseded by this decision. The owner explicitly accepts the risk of
  having no automated A/B regression check on the new estimator.
- **D-02:** Dropping the A/B *comparison* harness is **NOT** the same as dropping correctness
  tests. The new estimator MUST still carry ordinary unit tests + the Phase 2 Hypothesis
  invariants (INTERPOLATION §7.3: `primary_cube ∈ label_span`; `0 ≤ start ≤ end ≤ 1`; monotone
  position within a label; stability under cosmetic catalog-string noise), **extended for
  segments**: per-bin segment fractions sum to 1.0; a **single-segment bin reproduces §4.1
  exactly** (the cheap insurance that the new code didn't regress the common case); a straddling
  label resolves to the correct bin by rank. Nyquist validation (enabled) expects this coverage.

### Override Drift & Lifecycle (SEG-04)
- **D-03:** An admin width-**override always wins** over the count-derived fraction (SEG-04).
  When the count-derived "auto" fraction later **drifts** from a set override beyond a threshold,
  the editor surfaces a **yellow "review" hint + one-tap "resync to NN%"** — it **never
  auto-changes** the override. Honors SEG-04 while keeping the map trustworthy. Builds directly on
  the sketch's existing `OVERRIDE 45% · auto was 46%` + `reset to 46%` affordance. (Exact drift
  threshold → planner discretion.)
- **D-04:** When a cut-point edit or collection change leaves an override **orphaned** (its label
  no longer occupies that bin), **drop the override and report it in the Phase 3 diff-preview**
  ("override on B2 / IMPULSE removed — label no longer in B2"), so it rides the existing
  change-set + undo path. No silent migration to another bin.

### Bin Identity & Cut-Point Editing (SEG-01, SEG-08)
- **D-05:** A **bin is 1:1 with a physical Kallax cube.** The stored cut point = that cube's
  **first record**; the cube's **"last" is now DERIVED** from the next cube's cut point (no longer
  stored). **Durable identity stays the existing `(unit, row, col)`** from Phase 1's
  `cube_boundaries`; "BIN n" is **display order only**. The SEG-01 migration keeps
  `cube_boundaries.first_*` as the cut point and drops/derives `last_*`; it must round-trip clean.
- **D-06:** Inserting a cut (SEG-08) sets a new cut point and **cascades each subsequent cube's
  cut point down one position, recorded as ONE change-set** (rides Phase 3 undo). Width-overrides,
  `boundary_history`, and **future LED maps attach to durable `(unit,row,col)` and survive** the
  renumber; only the display "BIN n" labels shift. The sketch's "NEW" badge + renumber hint are
  **display-only**. ⚠ **Edge:** a cut insert near the end of the shelf can overflow the last
  physical cube — planner must define behavior (block with a plain-language error / require a free
  trailing cube).
- **D-07:** Cut-point editing **reuses Phase 3's machinery wholesale**: two-step label→catalog
  autocomplete sourced exclusively from `v_collection`, phantom-blocking (trigram near-misses +
  explicit "use anyway"), the **POS-01 normalizer as the only compare path**, diff-preview gating
  every commit, atomic bulk `POST` with `Idempotency-Key`, and change-set undo. The cut-point +
  override editor **replaces** the Phase 3 per-cube first/last editor.

### Label Contiguity & Multi-Bin Span (SEG-05, SEG-06)
- **D-08:** Build the estimator **generically for N adjacent bins per label** — resolve the
  record's **row-rank** among the label's owned items in `v_collection`, then compare that rank to
  **all cut points that fall inside the label's run** to pick the right bin+segment (the explore
  note's "straddle falls out cleanly"). **No special-casing** for 1 vs 2 vs N. Owner is unsure
  whether any single label spans 3+ cubes, so the general case is the safe default at near-zero
  extra estimator cost.
- **D-09:** The **straddle UI shows one `↪ continues in BIN n+1` per crossed cut** (chains
  naturally for N). The **label-contiguity invariant (SEG-05) is enforced by the save-validator**:
  a cut-point set that would scatter a label across **non-adjacent** bins is **rejected** with a
  plain-language error. A label spanning multiple **adjacent** bins is **valid (not capped)**.

### Claude's Discretion (delegated to researcher / planner / ui-phase)
- Exact **drift threshold** for the override "review" hint (D-03).
- **Save-validation taxonomy** — what is hard-rejected vs warned (empty bin, cut record not in
  `v_collection`, overrides not summing to 100%, contiguity violation) and the plain-language
  messaging. Reuse Phase 3's phantom-block + diff-preview patterns; voice per the design language.
- **End-of-shelf cut-insert overflow** behavior (D-06 edge).
- **Migration mechanics** for `cube_boundaries` → cut-point model (SEG-01) and the Alembic
  round-trip; whether `last_*` columns are dropped or retained-but-derived.
- **Where/when derived segments are computed + cached** — precompute the segment structure
  (segments, counts, fractions) into the boundary cache on load and on admin-commit `invalidate()`;
  SEG-02's "re-derives when the collection changes" reuses the Phase 2 in-memory snapshot + the
  Phase 4 invalidation seam. Keep the hot path CPU-only, no DB, p95 ≤ 50 ms.
- **All exact visual/interaction polish** → `/gsd-ui-phase 5`, within the locked sketch findings
  and Nordic Grid tokens.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Segment Model (authoritative design rationale for this phase)
- `.planning/notes/segment-aware-boundaries.md` — the `/gsd:explore` design record: the cut-point
  model, the two invariants (label contiguity; counts = row-count, never catalog arithmetic), the
  two-level interpolation algorithm (with Mermaid), the straddle case, payoffs, and risks. **The
  conceptual source of truth for SEG-01..08.**

### Validated UI (locked design — consume, don't redesign)
- `.claude/skills/sketch-findings-gruvax/SKILL.md` — design direction, palette/typography rules,
  vanilla-DOM build constraint (`el()` + `replaceChildren()`, never `innerHTML`).
- `.claude/skills/sketch-findings-gruvax/references/boundary-editing.md` — the **winning** segment
  strip + drag-override (sketch 001-A) and bin-card cut list + slide-up record picker (sketch
  002-A): color semantics (yellow=changed, blue=structure, `↪`=straddle), CSS patterns, the
  sum-conserving drag interaction, and the "what to avoid" list.
- `.claude/skills/sketch-findings-gruvax/sources/` — original sketch HTML + theme (`themes/default.css`
  `@import`s the canonical design tokens).

### Position Estimation & Architecture
- `.planning/research/INTERPOLATION.md` — **§4.1** (the estimator being superseded — keep as the
  conceptual baseline the segment model degenerates to on single-label bins), **§4.8** cube-only
  fallback (retained), **§6** edge cases (singleton `f=0.5`, multi-value first-value, multi-label
  raw), **§7.3** Hypothesis invariants (D-02 extends these for segments).
- `.planning/research/ARCHITECTURE.md` — `LocateResult` / `SubInterval` contract (unchanged,
  SEG-06), the 50 ms latency budget, the boundary-cache pattern, the `/api/admin/*` surface +
  `cubes/validate` dry-run diff + `boundary_history` DDL the cut-point editor extends.
- `.planning/research/PITFALLS.md` — Pitfall 1 (numeric-aware comparator), Pitfall 5
  (`v_collection` is the only contact surface), Pitfall 6 (phantom boundary records),
  Pitfall 11 (partial change-set → atomic bulk), Pitfall 22 (index-space, not catalog-string).
- `.planning/research/STACK.md` — psycopg async, Alembic (migration for SEG-01).

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — definitions for **SEG-01..08** (lines 51–58). ⚠ **SEG-07's A/B
  harness clause is amended by D-01** — flag for amendment (see Summary).
- `.planning/ROADMAP.md` — Phase 5 section: goal + 5 success criteria. ⚠ **Criterion 4 (A/B
  proof) is relaxed by D-01.**
- `.planning/PROJECT.md` — Core Value, "position is computed not stored", repo-hygiene rule
  (collection CSV + `background/` never committed; segment proof/tests use synthetic data only).

### Locked from Prior Phases (carry forward — do not re-decide)
- `.planning/phases/01-first-search-cube-highlight/01-CONTEXT.md` — real `units` / `cube_boundaries`
  tables (D-05's durable `(unit,row,col)` identity); `v_collection`-only read surface; POS-01
  normalizer is the only legal compare path.
- `.planning/phases/02-real-position-estimation/02-CONTEXT.md` — §4.1 estimator (now superseded),
  the **in-memory collection snapshot** (segment counts row-count from it), `estimator_version`,
  the §4.8 fallback, the Hypothesis invariants (D-02), and the `run_all_algorithms.py` harness
  (NOT extended this phase, per D-01).
- `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-CONTEXT.md` — admin auth/session, the
  per-cube editor the cut-point editor **replaces**, two-step autocomplete, phantom-blocking,
  diff-preview, `boundary_history` change-set undo, `cubes/bulk` + `Idempotency-Key`,
  in-process `boundary_cache.invalidate()`.
- `.planning/phases/04-realtime-live-updates/04-CONTEXT.md` — SSE invalidation + `admin_editing`
  soft-lock; segment re-derivation reuses this invalidation seam (Discretion).
- `src/gruvax/estimator/contract.py` — frozen `LocateResult` / `SubInterval` (do not change shapes).
- `src/gruvax/estimator/algorithm.py` — `locate_cube_only` (§4.8 fallback); the §4.1 path here is
  replaced by the segment-aware path.
- `src/gruvax/estimator/normalize.py` — POS-01 normalizer + `catalog_in_range` (the only compare).
- `src/gruvax/estimator/collection_snapshot.py` — per-label record lists; segment row-counts read here.
- `src/gruvax/estimator/boundary_cache.py` — precompute/hold derived segments; `invalidate()` seam.
- `src/gruvax/api/locate.py`, `src/gruvax/api/admin*` , `src/gruvax/db/queries.py`, `migrations/` —
  endpoints + queries + the new Alembic migration for SEG-01.

### Design System (consume tokens; never hardcode hex)
- `design/gruvax-design-language.md`, `design/gruvax-design-tokens.css`, `design/gruvax-design-tokens.json`
  — Nordic Grid; lit-cell rule (yellow only for changed/active); LED-physics motion; three-font type.
- `CLAUDE.md` — conventions, design language, Mermaid-only diagrams.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`collection_snapshot.py`** — per-label owned-record lists; segment **counts and bin-fractions
  row-count from this** (dupes + variants each counted; never catalog arithmetic, SEG-03). No DB on
  the hot path.
- **`normalize.py` (POS-01)** — the only legal ordering/compare path for cut points, segment
  ranges, and the save validator. Raw-string compares forbidden.
- **`boundary_cache.py`** — extend to precompute + hold the derived segment structure; reuse the
  `invalidate()`/reload seam (in-process + Phase 4 SSE) for SEG-02 re-derivation.
- **Phase 3 admin stack** — two-step autocomplete, phantom-block, diff-preview, `cubes/bulk` atomic
  commit + `Idempotency-Key`, change-set undo, `boundary_history` — all reused by the cut-point editor.
- **Sketch components** — segment strip + drag handles, bin-card cut list, slide-up record picker
  (built with `el()` + `replaceChildren()`); the kiosk `ShelfGrid`/`Cube`/`gridGeometry.ts` for the
  4×4 mini-Kallax locator header.

### Established Patterns
- CPU-only estimate from the in-memory snapshot, no DB during compute (p95 ≤ 50 ms).
- Float confidence; design-token CSS only (no hardcoded hex); vanilla DOM, never `innerHTML`.
- psycopg `%s` parameterized SQL; `alembic_version` in `public`; `search_path` via connect listener.
- Admin commit = one change-set, atomic bulk, then `boundary_cache.invalidate()`.

### Integration Points
- `cube_boundaries` migrates to the cut-point representation (SEG-01); `(unit,row,col)` stays the
  durable key.
- `/api/locate` keeps its contract but runs the segment-aware two-level interpolation (SEG-06).
- The cut-point + override editor extends the `/api/admin/cubes*` surface and `boundary_history`.

</code_context>

<specifics>
## Specific Ideas

- **Two-level interpolation** (copy-from): `position = offset + (rank-in-segment / segment-count) ×
  fraction`, where `fraction = override ?? count-derived`, and the bin is chosen by comparing the
  record's row-rank to the cut points splitting its label (`.planning/notes/segment-aware-boundaries.md`).
- **Single-segment bin == §4.1 exactly** — this is the regression invariant that replaces the
  dropped A/B proof (D-02).
- **Honesty made visible** — the record picker deliberately surfaces duplicate/variant rows
  (`AS 78`, `AS 78` 2nd copy, `AS 78-r` remix) so "counts come from rows, not catalog arithmetic"
  is legible to the owner (boundary-editing.md).
- **Color/straddle semantics** — yellow = changed/override/active; blue family = structure; `↪` +
  right-edge fade = a label continuing into the next bin.

</specifics>

<deferred>
## Deferred Ideas

- **A/B comparison harness for the segment estimator** — **descoped, not deferred** (D-01). The
  owner chose to retire §4.1 and ship on trust; this work will not be done in any phase unless the
  decision is revisited.
- **Physical LED sub-span lighting** — Phase 6 (LED milestone); depends on this segment model, and
  the physical-width override becomes load-bearing there.
- **Bulk reshuffle / guided wizard + CSV/YAML import/export** — Phase 6.
- **Format-thickness sub-segment weighting** (2×LP, box sets get more linear width than rank-uniform
  placement) — future; out of scope until the segment estimator proves insufficient.
- **Owner-curated real golden positions** — produce after a real reshuffle exists (Phase 6) to
  validate the estimator on real data; closes Phase 2's D-08 softening loop.

None of the above belong in Phase 5 — discussion stayed within scope.

</deferred>

---

*Phase: 05-segment-aware-position-precision*
*Context gathered: 2026-05-22*

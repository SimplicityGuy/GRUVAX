# Phase 7: Wizards + Import/Export - Context

**Gathered:** 2026-05-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Make boundary maintenance **fast, atomic, and portable**. The owner can stand up
boundaries from scratch via a guided cube-by-cube wizard, atomically re-walk the shelf after
a real-life haul (reshuffle wizard with resume-after-blip), import a CSV/YAML seed file with
per-row validation + diff preview before an atomic replace, and export current boundaries
(YAML) plus LED/color settings (round-trippable). Every multi-cube operation rides the
**Phase 3 keystone undo path** — one `change_set_id`, conflict-aware revert.

**In scope (5 requirements):** ADMN-04 (guided setup wizard), ADMN-05 (CSV/YAML import with
validate + diff preview + atomic replace), ADMN-10 (reshuffle wizard, single atomic change-set),
BAK-01 (boundary export, matches import schema), BAK-02 (LED/color settings export + import,
same schema convention).

**Reconciliation note (IMPORTANT for planner):** ROADMAP/REQUIREMENTS for this phase were
authored **before Phase 5** inserted the cut-point/segment model. SC1's "infers each boundary
from a single point of transition (the first record of the next cube implies the last record
of this cube)" **is exactly the cut-point relationship** — the wizard collects one cut point
(first record) per cube; "last" is derived. There is no first/last pair entry anymore. The
old first/last DiffPreviewSheet was removed in Phase 5 (05-06); the dry-run diff **endpoint**
`POST /api/admin/cubes/validate` still exists and is what import/wizard previews consume.

**Out of scope (other phases / backlog):** observability/diagnostics/healthz + Compose
hardening (Phase 8); width-override *authoring* (stays in the Phase 5 segment/BinWidthEditor —
wizard does not set overrides; import may carry them); real LED firmware (hardware milestone);
versioned/named boundary snapshots ("Before Vegas haul") and animated reshuffle preview
(backlog); automatic git commit of boundary state (permanently out of scope).
</domain>

<decisions>
## Implementation Decisions

### Wizard Architecture & Flow (ADMN-04, ADMN-10 — SC1, SC3)
- **D-01:** **One wizard engine, two entry modes**, at a new `/admin/wizard` route. *Fresh
  setup* mode seeds from empty/blank cubes; *reshuffle* mode pre-loads the current cut points
  to re-walk. Same step UI, same validation, same atomic commit, same confirmation. Only the
  seed state and the resume/localStorage behavior (reshuffle-only, D-05) differ. One path to
  build and test, no drift risk between two flows.
- **D-02:** The walk collects **cut points only** — at each cube the owner sets the *first
  record of that cube* (the cut point); per-segment counts and bin-fractions auto-derive from
  `v_collection` (Phase 5). **Width overrides (SEG-04) are NOT touched by the wizard** — they
  remain a later fine-tuning concern in the existing segment/BinWidthEditor. Keeps the wizard a
  fast linear walk and matches SC1's "single point of transition" wording exactly.
- **D-03:** Each wizard step **reuses the Phase 5 `RecordPickerSheet`** (two-step
  label→catalog autocomplete sourced exclusively from `v_collection`, phantom-block + trigram
  "did you mean"). A **"this cube is empty / skip"** control sets `is_empty` and advances.
  Phantoms are impossible by construction; the wizard inherits all of Phase 3/5's validation.
- **D-04:** The whole walk commits as **ONE atomic `POST /api/admin/cubes/bulk` change-set**
  (no partial commits — Pitfall 7), carrying an `Idempotency-Key`. A **new Alembic migration
  0007 extends the `boundary_history.source` CHECK** to add `'wizard'`, `'reshuffle'`, `'csv'`,
  `'yaml'` (current set: `'manual'|'bulk'|'revert'|'cut_insert'`) so the History view and the
  SC5 confirmation can name the origin ("Wizard setup — 32 cubes" vs "CSV import — 12 cubes").
  Migration must round-trip clean (OBS-03 CI gate is Phase 8, but the migration lands here).

### Reshuffle Resume & Persistence (ADMN-10 — SC3)
- **D-05:** The reshuffle wizard **persists in-progress state to `localStorage` after every
  confirmed step** — a tiny JSON of cut points (+ empty flags) keyed by `(unit,row,col)`. A
  Wi-Fi blip loses at most the cube currently being entered. **Nothing reaches the DB until the
  final atomic commit** (consistent with Phase 3 D-04's client-side `pendingChangeSet`, but
  durably persisted to survive a reload/crash, not just an idle timeout).
- **D-06:** A **"Continue your reshuffle" banner** appears on the next admin login when a draft
  exists. On resume, **re-validate the draft via `POST /api/admin/cubes/validate`** against the
  current `v_collection`: any cut record that no longer matches (sold/removed since the draft
  began) is flagged with an inline trigram "did you mean" fix; the rest carry forward. The owner
  never commits a silently-stale draft.
- **D-07:** A draft is **cleared from `localStorage` on successful commit**, and the banner
  carries an explicit **"Discard draft"** action (with a confirm). **No time-based auto-expiry**
  — a draft is the owner's deliberate work and must not vanish on its own; staleness is handled
  by the D-06 resume re-validate, not by deletion.

### Import — Format & Semantics (ADMN-05 — SC2)
- **D-08:** The import endpoint **accepts both CSV and YAML**, detected by extension/content,
  parsed into one internal cut-point model before validation. YAML is the human-editable /
  round-trip-with-export format; CSV covers spreadsheet-exported seed files (`pyyaml` is already
  a dep; CSV via stdlib `csv`).
- **D-09:** Import is a **full atomic replace-all**: the file is the *complete* desired
  cut-point set for all cubes; commit replaces every cube's boundary in one change-set (cubes
  absent from the file become empty/unset). Matches ADMN-05's "atomic replace" and guarantees
  export→re-import = identity. One `change_set_id`, fully revertible (`source='csv'`/`'yaml'`).
- **D-10:** **Schema entry = cube address `(unit,row,col)` + cut point `(label, catalog)` or
  `is_empty` + optional per-label width overrides.** Export captures the FULL boundary state so
  a backup→restore is lossless (BAK-01 "matches import schema"). Overrides are **optional on
  import** — omit them and counts auto-derive. (The wizard still writes only cut points, D-02;
  the richer schema exists purely for portability/backup.)
- **D-11:** Import is **all-or-nothing gated on validation**: upload → `cubes/validate` runs
  every row against `v_collection` → a new `/admin/import` page lists **per-row errors with
  tappable trigram "did you mean" fixes** AND the **affected-cubes diff preview** (mini-grid +
  movement counts, reusing the `validate` endpoint output). The **Commit button stays disabled
  until zero errors**, then one atomic bulk commit. No partial state ever reaches the DB.

### Export & Settings Round-Trip (BAK-01, BAK-02 — SC4)
- **D-12:** **Boundaries export is YAML only** — `GET /api/admin/export/boundaries.yaml` (the
  ARCHITECTURE-named endpoint). YAML is the canonical, human-editable round-trip companion to
  import and re-imports cleanly (SC4 round-trip identity). CSV stays **import-only** (its flat
  shape can't cleanly express the nested overrides); JSON is not exported in v1.
- **D-13:** **LED/color settings export AND import are separate from boundaries** and do **not**
  go through `boundary_history` / change-sets (settings aren't boundaries). Settings import is a
  dedicated endpoint that **validates the uploaded keys/values** (known keys, in-range
  colors/brightness via the existing settings validators) and applies them via the **same
  settings-update path as the admin Settings page** (settings-cache reload covers propagation).
  Keeps the keystone undo path boundary-only and uniform.
- **D-14:** The settings file covers **LED/presentation keys only** — `led_color.*`,
  `led_brightness.*`, `led_highlight.*` (and UI presentation knobs such as cube nominal
  capacity). **`auth.pin_hash` and any secret are HARD-EXCLUDED** — never serialized to a
  downloadable file (Pitfall 12: the PIN never leaves the DB). Import **ignores/rejects**
  unknown or `auth.*` keys.

### Confirmation & Undo Keystone (SC5 — applies to every operation above)
- **D-15:** Every wizard commit, CSV/YAML import, and reshuffle ends with a confirmation that
  **names the `change_set_id`** and offers a **"Revert this change set" tap** — reusing the
  Phase 3 `GET /api/admin/history` + `POST /api/admin/history/{id}/revert` (conflict-aware)
  path wholesale. The keystone undo from Phase 3 covers all multi-cube admin operations
  uniformly; the new `source` labels (D-04) make them legible in the History view.

### Claude's Discretion (delegated to researcher / planner / ui-phase)
- **`cubes/bulk` cut-point shape:** verify the existing `POST /api/admin/cubes/bulk` accepts /
  writes the Phase 5 cut-point representation correctly (it predates and was reworked through
  Phase 5); extend or add a cut-point-aware bulk path if the current body shape is first/last.
- **End-of-shelf cut overflow** in the wizard (carry the Phase 5 D-06 edge): a cut walk that
  would overflow the last physical cube must fail with a plain-language error / require a free
  trailing cube — define behavior.
- **Exact CSV column layout** (likely flat: `unit,row,col,label,catalog,is_empty` — overrides
  omitted on CSV since they're nested) vs the **YAML nested schema** (carries overrides). Pick
  concrete shapes; document the schema alongside the export endpoint.
- **Confirmation surface** — inline toast vs a dedicated confirmation screen (both must name the
  change_set_id + revert tap). UI-phase call.
- **Wizard step navigation** — back/skip controls, progress indicator, how the mini-Kallax
  locator (`LocatorHeader`) shows position in the walk.
- **`Idempotency-Key` generation** for wizard/import commits (reuse the existing admin pattern).
- **Where the wizard + import entry points live** in admin nav (CubesGrid / AdminShell).
- **All visual/interaction polish → `/gsd-ui-phase 7`** within Nordic Grid tokens + the locked
  sketch findings (vanilla DOM `el()`/`replaceChildren()`, never `innerHTML`).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap (the locked acceptance spec for this phase)
- `.planning/REQUIREMENTS.md` — definitions for **ADMN-04, ADMN-05, ADMN-10, BAK-01, BAK-02**
  (lines 65–66, 71, 124–125).
- `.planning/ROADMAP.md` §"Phase 7" — goal + the **five success criteria** (SC1–SC5). ⚠ SC1/SC2
  wording predates Phase 5; read against the cut-point model (see domain Reconciliation note).
- `.planning/PROJECT.md` — single-PIN/session constraint, "visiting friends" use case,
  repo-hygiene rule (collection CSV + `background/` never committed — import/export tests use
  synthetic data only).

### Admin Architecture & Contracts (authoritative for the endpoint surface)
- `.planning/research/ARCHITECTURE.md` — the **`/api/admin/*` endpoint table** (esp.
  `POST /api/admin/cubes/bulk`, `POST /api/admin/cubes/validate`,
  `GET /api/admin/export/boundaries.yaml`, `history` + `history/{id}/revert`), the
  **`boundary_history` DDL + `source` column**, the **Idempotency-Key** model + `idempotency_keys`
  table, and the `/admin/wizard` + `/admin/import` route tree + Zustand `pendingChangeSet`.
- `.planning/research/PITFALLS.md` — **Pitfall 5** (`v_collection` only contact surface),
  **Pitfall 6** (phantom boundary records → trigram near-miss), **Pitfall 7/11** (partial
  change-set → atomic bulk; the wizard/import all-or-nothing commit), **Pitfall 12** (PIN never
  leaves the DB — drives D-14), **Pitfall 22** (index space, not catalog-string).

### Segment / Cut-Point Model (what the wizard populates)
- `.planning/notes/segment-aware-boundaries.md` — the cut-point model, label-contiguity
  invariant (SEG-05, enforced on the wizard/import commit too), counts = row-count never catalog
  arithmetic, the two-level interpolation. **Conceptual source of truth.**

### Validated UI (locked design — consume, don't redesign)
- `.claude/skills/sketch-findings-gruvax/SKILL.md` + `references/boundary-editing.md` — palette /
  typography rules, vanilla-DOM build constraint (`el()` + `replaceChildren()`, never
  `innerHTML`), color semantics (yellow=changed, blue=structure, `↪`=straddle), the record-picker
  + bin-card patterns the wizard reuses.

### Locked from Prior Phases (carry forward — do not re-decide)
- `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-CONTEXT.md` — admin auth/session,
  two-step autocomplete, phantom-block, **diff-preview via `cubes/validate`**, `cubes/bulk`
  atomic commit + `Idempotency-Key`, `boundary_history` change-set **undo/revert** (the SC5
  keystone), in-process `boundary_cache.invalidate()`.
- `.planning/phases/05-segment-aware-position-precision/05-CONTEXT.md` — cut-point model, durable
  `(unit,row,col)` identity, `RecordPickerSheet`, cut-point + override editor, SEG-05 contiguity
  enforcement on live write paths, the removed `/admin/preview` DiffPreviewSheet.
- `.planning/phases/06-led-contract-over-mqtt-hardware-stubbed/06-CONTEXT.md` — the LED/color
  **settings keys** that BAK-02 export/import must cover (`led_color.*`, `led_brightness.*`,
  `led_highlight.*`) and the settings-precedence split (presentation in `gruvax.settings`).

### Design System (consume tokens; never hardcode hex)
- `design/gruvax-design-language.md`, `design/gruvax-design-tokens.css`,
  `design/gruvax-design-tokens.json` — Nordic Grid; ALL-CAPS Barlow labels; DM Mono for
  catalog#s/counts; plain-language errors.
- `CLAUDE.md` — conventions, Mermaid-only diagrams.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (this phase is mostly composition over existing parts)
- **`src/gruvax/api/admin/cubes.py`** — `bulk_write_cubes` (`POST /cubes/bulk`, one
  `change_set_id`, `source='bulk'`, Idempotency-Key dedup + old-key prune, cache invalidate +
  SSE), `validate_boundary` (`POST /cubes/validate`, dry-run diff + `_compute_movement_counts`
  + warnings). **The keystone the wizard + import both commit/preview through.** ⚠ Verify it
  speaks the cut-point shape post-Phase-5 (Discretion).
- **`src/gruvax/api/admin/history.py`** — `GET /history` (grouped change-sets w/ `source`) +
  `POST /history/{id}/revert` (conflict-aware). The SC5 confirmation links straight to this.
- **`src/gruvax/api/admin/segments.py` + `validation.py`** — `build_proposed_cuts` +
  `validate_contiguity` (SEG-05 enforcement) the wizard/import commit must run; cut-point write
  shape.
- **`src/gruvax/api/admin/settings.py`** — settings GET/PUT path that the BAK-02 settings import
  reuses (validated PUT, D-13); the LED keys live in `gruvax.settings`.
- **`frontend/src/routes/admin/RecordPickerSheet.tsx`** — each wizard step's input (D-03).
  **`HistoryView.tsx`** — source labels surface here. **`CubesGrid.tsx` / `ShelfBinList.tsx` /
  `LocatorHeader.tsx`** — mini-Kallax grid for the import diff preview + wizard position.
- **`frontend/src/api/adminClient.ts`** — admin fetch client; add wizard/import/export calls.
- **`frontend/src/state/adminStore.ts`** — Zustand admin slice; add the localStorage-backed
  reshuffle-draft state (D-05).
- **`pyyaml>=6.0.3`** already a dependency; `types-pyyaml` in dev deps. CSV via stdlib.

### Established Patterns
- **Atomic bulk = one `change_set_id`, `Idempotency-Key`, then `boundary_cache.invalidate()` +
  SSE** (Phase 3/4). All Phase 7 multi-cube writes follow this.
- **`v_collection` is the only read surface; POS-01 normalizer is the only compare path;**
  phantom-block + trigram did-you-mean for any boundary value (Phase 3/5).
- **Dependency providers in `deps.py`; routers imported inside `create_app()`; admin routes
  require session + CSRF; psycopg `%s` parameterized SQL.**
- **Alembic:** `alembic_version` in `public` schema; `search_path` via connect event listener;
  migrations round-trip clean (latest is `0006`; this phase adds **`0007`** for the `source`
  CHECK extension).
- **Frontend:** React + react-router route tree; component bodies build DOM via `el()` /
  `replaceChildren()` (never `innerHTML`); design tokens only, no hardcoded hex.

### Integration Points
- **New endpoints:** import (validate + atomic replace), `GET /api/admin/export/boundaries.yaml`,
  settings export + settings import (validated PUT). All admin-gated (session + CSRF) except
  export GETs (session).
- **New frontend routes:** `/admin/wizard` (one engine, two modes) and `/admin/import`; export +
  settings import surfaced from admin nav / Settings page.
- **New migration `0007`:** extend `boundary_history.source` CHECK.
- **Reuse:** `cubes/bulk` (commit), `cubes/validate` (preview), `history`+`revert` (SC5),
  `RecordPickerSheet` (wizard step), `cubes/validate` movement counts + mini-grid (import diff).
</code_context>

<specifics>
## Specific Ideas

- The wizard's per-cube prompt is literally "what's the **first record** in this cube?" — the
  cut point. The previous cube's *end* is implied by this answer (SC1's "single point of
  transition"); the **last** physical cube ends at the end of the collection.
- The "Continue your reshuffle" banner is the SC3 hook — it must be discoverable on next admin
  login, show how far the draft got, and offer **Continue** / **Discard**.
- Round-trip identity is the export/import acceptance test: **export YAML → re-import → no diff**
  (SC4). Build that as a test using a synthetic boundary set (never the real collection CSV).
- The settings file is a *config* artifact, not a *boundary* artifact — different endpoint,
  different schema section, no change-set, and **categorically never contains the PIN hash**.
</specifics>

<deferred>
## Deferred Ideas

- **Versioned / named boundary snapshots** ("Before Vegas haul") and **animated cube-by-cube
  reshuffle preview** — backlog (REQUIREMENTS v2/FEATURES future-tier), not this phase.
- **JSON boundary export** — not in v1 (YAML is the canonical round-trip, D-12); add only if a
  tooling need appears.
- **Width-override authoring inside the wizard** — explicitly excluded (D-02); overrides stay in
  the Phase 5 segment/BinWidthEditor. Import *carries* overrides for round-trip (D-10) but the
  wizard does not author them.
- **Density-imbalance-driven reshuffle suggestion** (auto-propose new cut points from
  occupancy) — FEATURES future-tier; the wizard is owner-driven in v1.
- **Automatic git commit / cloud-sync of boundary state** — permanently out of scope
  (REQUIREMENTS "Out of Scope"); Postgres backup + the YAML export cover portability.

None of the above belong in Phase 7 — discussion stayed within scope.
</deferred>

---

*Phase: 07-wizards-import-export*
*Context gathered: 2026-05-24*

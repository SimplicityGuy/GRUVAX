# Roadmap: GRUVAX

**Created:** 2026-05-19
**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)
**Granularity:** standard (8 phases)
**Requirements covered:** 81 / 81 v1 (100%)

## Core Value (north star for every phase)

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

The first user-observable slice (Phase 1) exercises the Core Value end-to-end against a fixture-seeded boundary table. Each subsequent phase deepens or broadens that loop without breaking it.

## Phases

- [x] **Phase 1: First Search → Cube Highlight** - End-to-end Core Value: typed query lights the right cube on the touchscreen, backed by parser, view, fixture-seeded boundaries, and a cube-only estimator. (completed 2026-05-20)
- [x] **Phase 2: Real Position Estimation** - Sub-cube interval bar, label-span multi-cube highlight, §4.1 index-based estimator with A/B harness; the kiosk now answers "where exactly". (completed 2026-05-20)
- [x] **Phase 3: Admin Loop (PIN + Manual Entry + Undo)** - Owner can sign in (mobile or kiosk-with-in-app-keypad), enter boundaries, preview diffs, and undo mistakes — boundaries become a living artifact, not a fixture. (completed 2026-05-21)
- [x] **Phase 4: Realtime + Offline Resilience** - Admin edits reach the kiosk live via SSE; kiosk gracefully degrades on connectivity loss; privacy floors and recently-pulled land here. (completed 2026-05-22)
- [ ] **Phase 5: Segment-Aware Position Precision** - A bin holds an ordered list of per-label segments; store only cut points + optional physical-width overrides and derive segments/counts/fractions from `v_collection`; a segment-aware estimator supersedes §4.1 via two-level interpolation so a record's position is precise even when multiple labels share a bin.
- [ ] **Phase 6: LED Contract over MQTT (Hardware Stubbed)** - Illuminate / span / sub-interval / all-off / diagnostic endpoints publish versioned, validated payloads to an internal Mosquitto broker; admin tunes colors and brightness.
- [ ] **Phase 7: Wizards + Import/Export** - Guided setup wizard, atomic reshuffle wizard, CSV/YAML seed import, boundary + settings export — boundary maintenance is fast and recoverable.
- [ ] **Phase 8: Observability + Deployment Hardening** - Healthz with subsystem status, slow-query log, sync staleness, aggregate usage stats, Compose log limits, healthchecks, version endpoint, SLO proof.

## Phase Details

### Phase 1: First Search → Cube Highlight

**Goal:** A user types a query on the touchscreen kiosk and sees the correct cube highlighted on a rendered N×4×4 grid within ~200 ms — exercising the Core Value end-to-end against fixture-seeded boundaries before any admin UI exists.
**Mode:** mvp
**Depends on:** Nothing (foundational vertical slice)
**Requirements:** SRCH-01, SRCH-02, SRCH-03, SRCH-04, SRCH-05, SRCH-06, CUBE-01, CUBE-02, CUBE-05, CUBE-06, POS-01, POS-02, POS-04, DEP-01, DEP-02
**Success Criteria** (what must be TRUE):

  1. Owner can open the kiosk URL in Chromium on the Pi 5 and see an N×4×4 grid (N=2, 32 cubes) with each cube showing its address overlay (row+col).
  2. Owner types "Coltrane" (or any artist/title/label/catalog#) into the search box and sees a ranked results list appear within ~200 ms; a clear-X button empties the field, and "no results" renders for misses.
  3. The top result auto-highlights the cube it lives in; tapping a different result re-highlights the corresponding cube; cubes with no boundary data render in a desaturated empty state.
  4. The kiosk can be demoed without any admin UI — boundaries are loaded from a versioned CSV/YAML fixture committed to the repo (no PII), parsed through the shared parser/comparator, validated against `gruvax.v_collection`, and held in an in-memory cache that loads at startup.
  5. The `gruvax-api` and `mosquitto` containers come up via `docker compose up` on `lux`, `gruvax-api` serves the SPA via FastAPI `StaticFiles`, and `/api/locate?release_id=...` returns a `LocateResult` whose contract (`primary_cube`, `label_span`, `sub_cube_interval`, `confidence`, `generated_at`, `estimator_version`) matches the architecture spec — with `sub_cube_interval: null` and `confidence: "cube_only"` for v1 (cube-only fallback per INTERPOLATION §4.8).

**Plans:** 4/4 plans complete
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Project scaffold + gruvax schema + v_collection contract + synthetic seeds + Wave 0 test infra

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — POS-01 parser/comparator + locked LocateResult contract + boundary cache + cube-only estimator

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-03-PLAN.md — Backend API: app/lifespan (probe + cache + mqtt stub) + search (FTS+catalog) + locate + units + health

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-04-PLAN.md — Kiosk SPA (tokens, grid, search, highlight) served via StaticFiles + Docker Compose (gruvax-api + mosquitto)

**UI hint:** yes

### Phase 2: Real Position Estimation

**Goal:** The cube highlight gains a sub-cube position bar and label-span secondary highlight, backed by the real §4.1 index-based estimator, with an A/B harness proving accuracy against the local CSV — the kiosk now answers "where exactly on the shelf".
**Mode:** mvp
**Depends on:** Phase 1 (parser, contract, search, grid render)
**Requirements:** CUBE-03, CUBE-04, CUBE-08, CUBE-10, POS-03, POS-05, POS-06, SRCH-07, SRCH-08
**Success Criteria** (what must be TRUE):

  1. When the matched record's label spans two cubes (~10% of records), the kiosk renders a secondary highlight behind the primary cube spanning all label cubes; the primary cube remains visually distinct.
  2. The primary cube shows a horizontal sub-cube position bar whose interval can cross a cube boundary; single-record labels render as a tick mark instead of a zero-width bar (INTERPOLATION Pitfall 21).
  3. The selection-lands animation choreographs label-span fade-in + primary-cube pulse + sub-cube bar slide-in within ≤600 ms total and is interruptible by a new search (test on the actual Pi 5 + 7" touchscreen).
  4. `/api/locate` p95 latency stays ≤50 ms CPU-only with no DB calls (proved by `pytest-benchmark` against the cached boundaries), and search returns trigram "did you mean" suggestions on near-misses plus catalog-# field boost on numeric-leading queries.
  5. A developer-facing `run_all_algorithms.py` A/B harness exists, runs §4.1 (index) and §4.8 (cube-only) against the local CSV (gitignored) and a synthetic CI dataset, and emits per-distribution-shape error metrics — proving §4.1 is the right v1 default before locking it in.

**Plans:** 4/4 plans complete
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — §4.1 index estimator + in-memory collection snapshot + §4.8 fallback dispatcher behind locked LocateResult; Wave-0 unit/property/golden/benchmark tests; /api/locate wiring (POS-03, POS-05, CUBE-04/10/03 backend)
- [x] 02-02-PLAN.md — Search refinements: pg_trgm migration + trigram "did you mean" (SRCH-07) + catalog-# rank boost (SRCH-08) + DidYouMean kiosk row

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-03-PLAN.md — Kiosk position UI: SubCubeBar + SpanUnderlay + singleton band + GSAP selection-lands choreography (CUBE-04, CUBE-03, CUBE-10, CUBE-08) [has human-verify checkpoint]
- [x] 02-04-PLAN.md — Developer A/B harness run_all_algorithms.py + planted-truth synthetic shapes proving §4.1 ≥ §4.8 (POS-06)

**UI hint:** yes

### Phase 3: Admin Loop (PIN + Manual Entry + Undo)

**Goal:** Owner can sign in (mobile-first, kiosk fallback with in-app numeric keypad), enter cube boundaries by hand with autocomplete + diff preview, see every mutation logged, and undo by change-set — boundaries become a maintained artifact, not a fixture.
**Mode:** mvp
**Depends on:** Phase 1 (DB, view, boundary cache), Phase 2 (parser used by save validator)
**Requirements:** ADMN-01, ADMN-02, ADMN-03, ADMN-06, ADMN-07, ADMN-08, ADMN-09, ADMN-12, CUBE-07, CUBE-09
**Success Criteria** (what must be TRUE):

  1. Owner can open `/admin` on their phone (or on the kiosk and tap an in-app numeric keypad — labwc/squeekboard #2926 is mitigated by an SPA-internal keypad), enter the PIN, and reach the boundary editor; the PIN is Argon2id-hashed in `gruvax.settings`, and the session uses a sliding-window timeout (5–10 min idle) with a visible 60-second countdown.
  2. Owner can edit one cube's `(first_label, first_catalog) / (last_label, last_catalog)` via a form whose autocomplete is fed by `gruvax.v_collection`; free-text values are rejected unless explicitly confirmed, and the save is validated by the shared parser (no `first > last` saves slip through).
  3. Before commit, every save shows a diff preview with affected cubes highlighted on a mini-grid; on commit, the change writes to `boundary_history` with a `change_set_id`, and the admin's "History" view lists the change-set and offers a one-tap revert.
  4. Each cube shows a fill-level indicator derived from its boundary range; tapping a cube on the kiosk reveals a side panel listing the cube's first/last boundary records and a representative subset (reverse lookup via `/api/cubes/{u}/{r}/{c}`).
  5. The admin "Suggest midpoint" affordance walks the collection-index space (NOT catalog-number space — Pitfall 22) to propose a midpoint catalog# between two adjacent populated cubes; the suggestion is editable, never auto-applied.

**Plans:** 5/5 plans complete
Plans:
**Wave 1**

- [x] 03-01-PLAN.md — Migration 0004 (admin tables) + deps + settings cache + boundary-math helpers + full Wave-0 test scaffold

**Wave 2** *(blocked on Wave 1)*

- [x] 03-02-PLAN.md — PIN auth slice: Argon2id login/session/CSRF + require_admin + set-pin CLI + /admin shell, keypad, Settings/Change-PIN
- [x] 03-03-PLAN.md — Kiosk reveal slice (public): fill-level bars (CUBE-07) + tap-to-reveal cube contents panel (CUBE-09)

**Wave 3** *(blocked on Wave 2)*

- [x] 03-04-PLAN.md — Boundary editor slice: cubes grid + per-cube editor, two-step autocomplete, phantom/trigram validation, index-space midpoint

**Wave 4** *(blocked on Wave 3)*

- [x] 03-05-PLAN.md — Diff preview + atomic change-set commit + boundary_history + conflict-aware undo

**UI hint:** yes

### Phase 4: Realtime Live Updates

**Goal:** As a kiosk visitor, I want to see the shelf map update live as the owner re-files records, so that I can always trust the kiosk reflects the current shelf layout without refreshing.
**Mode:** mvp
**Depends on:** Phase 1 (boundary cache), Phase 3 (admin writes that trigger invalidation)
**Requirements:** ADMN-11, RTM-01, RTM-02, RTM-03, RTM-04
**Success Criteria** (what must be TRUE):

  1. While the kiosk is open, an admin edit on mobile causes the affected cube(s) to re-render on the kiosk within ~500 ms over the LAN; the affected cube range shows a subtle "boundaries updating" indicator while the admin is mid-edit (SSE `admin_editing` event) and clears on commit.
  2. The SSE channel handles two simultaneous searches (kiosk and mobile) without server-side serialization, admin edits show optimistic UI updates with rollback on server error, and the SSE endpoint holds no DB connection (Pitfall 10) and ships with `X-Accel-Buffering: no` + 15s ping (Pitfall 8).

**Plans:** 4/4 plans complete
Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Realtime spine: in-process EventBus + GET /api/events SSE (no DB dep) + bus.publish at the cubes.py post-commit seam + kiosk EventSource consumer + connectivity/shimmer Zustand slice + Wave-0 backend tests (ADMN-11, RTM-01, RTM-02)

**Wave 2** *(blocked on Wave 1)*

- [x] 04-02-PLAN.md — Highlight-follows-record: boundary_changed re-locates the active selection → re-glow via existing animationToken/GSAP (RTM-01 / D-05, D-06)
- [x] 04-03-PLAN.md — admin_editing heartbeat endpoint (session+CSRF) + optimistic admin edits with rollback + RollbackToast (RTM-03, RTM-04 backend)

**Wave 3** *(blocked on Wave 2)*

- [x] 04-04-PLAN.md — Kiosk shimmer rendering: Cube shimmerActive + ShelfGrid pass-through + opacity-only .cube-shimmer-overlay + 60s TTL sweeper (RTM-04 kiosk)

**UI hint:** yes
**SPIDR note:** Split from original "Realtime + Offline Resilience" on the Paths axis (2026-05-21). Happy path (realtime) is this phase; deferred slices: Offline Resilience (OFF-01..04) and Privacy + Recently-Pulled (SRCH-09, PRIV-01..04).

### Phase 5: Segment-Aware Position Precision

**Goal:** Replace the one-span-per-cube boundary model with a segment-aware model — a bin holds an ordered list of per-label segments. Store only **cut points** (the first record of each bin) plus **optional physical-width overrides**; derive every segment's bounds, counts, and bin-fraction by **row-counting `gruvax.v_collection`** (never catalog arithmetic). Ship a segment-aware estimator that supersedes §4.1 via **two-level interpolation** (which-bin/segment → fraction-offset within the bin → row-rank within the segment), so a record's sub-cube position is precise even when multiple labels share a bin and labels straddle a cut.
**Mode:** mvp
**Depends on:** Phase 1 (boundary cache, `v_collection`), Phase 2 (POS-01 parser/comparator, §4.1 estimator it supersedes, `run_all_algorithms.py` A/B harness), Phase 3 (admin auth + boundary editor)
**Sequencing:** Lands **before** the LED phase — LED sub-span precision (now Phase 6) depends on this segment model.
**Requirements:** SEG-01, SEG-02, SEG-03, SEG-04, SEG-05, SEG-06, SEG-07, SEG-08 (design rationale: `.planning/notes/segment-aware-boundaries.md`).
**Success Criteria** (what must be TRUE):

  1. A boundary is stored as a set of **cut points** (first record per bin); given the globally-ordered `v_collection`, the system derives each bin's ordered per-label segments (label, first/last record) with **zero additional manual input**, and re-derives automatically as the collection grows.
  2. Per-label **counts and bin-fractions** are computed by row-counting `v_collection` across each segment's catalog range — correctly including duplicate owned copies and variant releases (`37` vs `37-r`) — and an **optional physical-width override** per segment wins over the count-derived fraction when present.
  3. `/api/locate` returns a sub-cube interval produced by **two-level interpolation**: it selects the correct bin+segment for the record, offsets by the fractions of preceding labels in the bin, and interpolates by row-rank within the segment; the **straddle case** (a label split across two adjacent bins by a cut) resolves to the correct bin without special-casing.
  4. The segment-aware estimator **supersedes §4.1** as the sole v1 default index estimator (with §4.8 cube-only retained as the timeout/low-confidence fallback), and `estimator_version` reflects the change. *(Amended 2026-05-22 — Phase 5 decision D-01: the prior A/B "meet-or-beat §4.1" proof gate via the extended `run_all_algorithms.py` harness is dropped; §4.1 is retired and the estimator ships on trust, covered by ordinary unit/Hypothesis-invariant tests rather than an A/B comparison.)*
  5. Admin can **view, edit, and add cut points** and set per-label **width overrides** for a bin (the cut-point editor / override UI), with the shared parser validating saves and the existing diff-preview + change-set undo path (Phase 3) covering the new mutations; the locate latency budget (p95 ≤ 50 ms, CPU-only, no DB on the hot path) is preserved.

**Plans:** 1/5 plans executed
Plans:
**Wave 1**

- [x] 05-01-PLAN.md — Migration 0005 cut-point model + BoundaryRow refactor + SEGMENT_ESTIMATOR_VERSION + Wave-0 test scaffold + synth factories (SEG-01)

**Wave 2** *(blocked on Wave 1)*

- [ ] 05-02-PLAN.md — SegmentCache derivation + two-level interpolation estimator superseding §4.1 + §4.8 fallback refactor + locate wiring + p95 benchmark (SEG-02, SEG-03, SEG-06, SEG-07)

**Wave 3** *(blocked on Wave 2)*

- [ ] 05-03-PLAN.md — Admin segment API: GET segments + overrides + cut + insert-cut + contiguity/overflow validation + SegmentCache invalidation (SEG-04, SEG-05, SEG-08)

**Wave 4** *(blocked on Wave 3)*

- [ ] 05-04-PLAN.md — UI primitives: el() helper + adminClient + SegmentStrip drag-override + SegmentLegend drift chips + RecordPickerSheet (SEG-04, SEG-08)

**Wave 5** *(blocked on Wave 4)*

- [ ] 05-05-PLAN.md — Editor assembly: CutPointEditor + SegmentEditorPanel + LocatorHeader + DiffPreview/Settings extensions + route swap + human-verify (SEG-04, SEG-05, SEG-06, SEG-08) [has human-verify checkpoint]
**UI hint:** yes

### Phase 6: LED Contract over MQTT (Hardware Stubbed)

**Goal:** Every search highlight publishes a versioned, Pydantic-validated MQTT payload to `gruvax/v1/leds/...` on an internal Mosquitto broker (no host port exposure); admin tunes colors and brightness; "all off" and diagnostic sequences work end-to-end — the contract is hardware-ready.
**Mode:** mvp
**Depends on:** Phase 1 (Compose), Phase 2 (sub-cube interval data), Phase 3 (admin settings UI), Phase 5 (segment-aware sub-span data for precise per-label LED illumination)
**Requirements:** LED-01, LED-02, LED-03, LED-04, LED-05, LED-06, LED-07, LED-08, LED-09, LED-10, DEP-03
**Success Criteria** (what must be TRUE):

  1. A search-and-select on the kiosk causes `gruvax-api` to publish a Pydantic-validated payload on `gruvax/v1/leds/illuminate/{unit}/{row}/{col}` (and, for label-span, on `.../span/{change_id}`; for sub-cube, on `.../sub/{unit}/{row}/{col}` with normalized `pixel_start`/`pixel_end`); a single layered command can carry both label-span and precise-position in one call, with optional `transition: {style, duration_ms}` declaring intent.
  2. Admin can tune label-span color, position color, error color, setup color, and "all off" via the admin Settings page; defaults are accessibility-respecting (NOT red/green for active/error, brightness-as-information per Pitfall 18); ambient (label-span) and active (position) brightness ceilings are separately configurable.
  3. An "All off" admin button publishes a `retain=True, payload=b''` clear-retained message on `gruvax/v1/leds/all` plus per-cube `state/*` clears (Pitfall 3), idempotently; a diagnostic admin endpoint cycles every cube through a documented color sequence and logs any status responses.
  4. Every retained publish sets MQTT 5 `message_expiry_interval` (default 4h for state, configurable); MQTT topics are versioned as `gruvax/v1/...`; per-environment topic prefix (`gruvax/v1/dev/...` vs `gruvax/v1/...`) is configurable via `MQTT_TOPIC_PREFIX`; the documented Pydantic schema lives alongside the contract in the repo.
  5. The Mosquitto broker runs in Compose with `persistence true` + named volume, NO host `ports:` exposure in v1, an LWT on `gruvax/v1/server/hello` retained, and the publish wrapper times out at ~250 ms so a broker hiccup never blocks `/api/illuminate`.

**Plans:** TBD

### Phase 7: Wizards + Import/Export

**Goal:** Owner can stand up boundaries from scratch via a guided setup wizard, atomically apply a post-haul reshuffle, import boundaries from a CSV/YAML seed file (with diff preview), and export current boundaries + LED color settings — boundary maintenance is fast, atomic, and portable.
**Mode:** mvp
**Depends on:** Phase 3 (admin auth, history, validate), Phase 5 (segment/cut-point model the wizard populates), Phase 6 (color settings exist to export)
**Requirements:** ADMN-04, ADMN-05, ADMN-10, BAK-01, BAK-02
**Success Criteria** (what must be TRUE):

  1. Owner can run a guided setup wizard cube-by-cube; the wizard infers each boundary from a single point of transition (the first record of the next cube implies the last record of this cube), and the entire walk commits as ONE atomic `change_set_id` via `POST /api/admin/cubes/bulk` (no partial commits — Pitfall 7).
  2. Owner can upload a CSV or YAML seed file; the server validates per-row against `gruvax.v_collection`, surfaces trigram-near-miss "did you mean" suggestions for mismatches, shows a diff preview with affected cubes highlighted, and commits atomically on confirmation with an `Idempotency-Key` (replays are no-ops).
  3. Owner can run a reshuffle wizard after a real-life shelf haul; in-progress state persists to `localStorage` so a Wi-Fi blip doesn't lose work; a "Continue your reshuffle" banner appears on next admin login; the commit is one `change_set_id` and is reversible via the Phase 3 undo path.
  4. Owner can download current boundaries as YAML (or JSON) via `GET /api/admin/export/boundaries.yaml`; the export schema matches the import schema (round-trip identity); a separate endpoint exports/imports LED color and brightness settings under the same schema convention.
  5. Every wizard commit, CSV/YAML import, and reshuffle ends with the admin seeing a confirmation that names the `change_set_id` and offers a "Revert this change set" tap — the keystone undo path from Phase 3 covers all multi-cube admin operations uniformly.

**Plans:** TBD
**UI hint:** yes

### Phase 8: Observability + Deployment Hardening

**Goal:** `/healthz` reports per-subsystem reachability, the slow-query log proves the 200 ms search SLO, sync staleness is surfaced to admin (and kiosk if stale > 7 days), Compose services declare log limits + healthchecks, and a `/version` endpoint reports the running build — the v1 is operable, observable, and self-healing.
**Mode:** mvp
**Depends on:** All prior phases (everything needs to exist before its health can be reported)
**Requirements:** OBS-01, OBS-02, OBS-03, OBS-04, OBS-05, OBS-06, OBS-07, DEP-04, DEP-05
**Success Criteria** (what must be TRUE):

  1. `GET /api/health` returns overall status plus per-subsystem reachability (`postgres`, `mqtt`, `discogsography_view_check`), sync-staleness in seconds, version, and started-at; `GET /api/version` reports git SHA, build timestamp, and environment.
  2. Admin diagnostics page surfaces: discogsography sync staleness (max `collection_items.updated_at`), aggregate top-N most-searched records (no per-query text persisted), slow-query log (any search exceeding the 200 ms SLO is flagged), MQTT broker status, Postgres pool `size_used` / `size_min`, phantom-boundary count, recent log lines.
  3. CI proves Alembic migrations round-trip (`upgrade head → downgrade base → upgrade head`) cleanly on every push; service logs are structured JSON with log level configurable via environment variable; the kiosk shows a sync-staleness banner if `sync_age_seconds > 7d` (Pitfall 15) and a no-results suggestion text references staleness when applicable.
  4. Compose declares per-service `logging:` directives (max-size + max-file) for `gruvax-api` and `mosquitto`; each service has a `healthcheck:` integrated with `restart: unless-stopped` for self-healing; volume permissions on a fresh host are documented and verified (Pitfall 14).
  5. A `pytest-benchmark` CI gate proves p95 `/api/search` end-to-end ≤200 ms and p95 `/api/locate` ≤50 ms against the synthetic CI dataset; a `just demo` (or equivalent) smoke script runs the Core Value flow against a fresh `docker compose up` to prove the SLO holds at the box level.

**Plans:** TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. First Search → Cube Highlight | 4/4 | Complete   | 2026-05-20 |
| 2. Real Position Estimation | 4/4 | Complete   | 2026-05-20 |
| 3. Admin Loop (PIN + Manual Entry + Undo) | 5/5 | Complete   | 2026-05-21 |
| 4. Realtime + Offline Resilience | 4/4 | Complete   | 2026-05-22 |
| 5. Segment-Aware Position Precision | 1/5 | In Progress|  |
| 6. LED Contract over MQTT (Hardware Stubbed) | 0/? | Not started | - |
| 7. Wizards + Import/Export | 0/? | Not started | - |
| 8. Observability + Deployment Hardening | 0/? | Not started | - |

## Critical-Path Notes (carried from research)

These are roadmapper-level reminders surfaced from ARCHITECTURE.md, PITFALLS.md, and INTERPOLATION.md; `/gsd:plan-phase` will operationalize them into must-haves.

- **POS-01 parser is shared infrastructure** — must be implemented and Hypothesis-tested in Phase 1 because the boundary-save validator (Phase 3, ADMN-06), every algorithm (Phase 2, POS-05), and every algorithm test depend on it. (INTERPOLATION §8.2)
- **`gruvax.v_collection` view + read-only grant** is the only path GRUVAX touches discogsography data — established in Phase 1 (DEP-02) and probed at startup (Pitfall 5).
- **LED endpoint contract locked early** — Phase 6 implements the contract but `LocateResult.sub_cube_interval` shape (normalized 0..1) is locked in Phase 2 (and refined by the segment-aware estimator in Phase 5) so firmware can land later without API changes.
- **Boundary cache + SSE invalidation pattern** — Phase 1 builds the cache; Phase 4 wires the SSE invalidation. `boundary_changed` events drive both kiosk re-render (RTM-01) and cache reload (POS-04).
- **In-app virtual keypad** lands in Phase 3 (mitigates labwc#2926 / Pitfall 4) — squeekboard is treated as not-available throughout v1.
- **No phase ships horizontal infrastructure alone.** Phase 1 looks broad because the Core Value requires backend + frontend + DB + Compose + parser to all exist together — that breadth is the smallest vertical slice that demos.

## Traceability

The 73 v1 requirements map to phases as follows. The full per-requirement table lives in REQUIREMENTS.md `## Traceability`.

| Phase | Categories represented | Requirement count |
|-------|------------------------|-------------------|
| 1 | SRCH (1–6), CUBE (1,2,5,6), POS (1,2,4), DEP (1,2) | 15 |
| 2 | CUBE (3,4,8,10), POS (3,5,6), SRCH (7,8) | 9 |
| 3 | ADMN (1,2,3,6,7,8,9,12), CUBE (7,9) | 10 |
| 4 | ADMN (11), RTM (1–4), OFF (1–4), SRCH (9), PRIV (1–4) | 14 |
| 5 | SEG (1–8) | 8 |
| 6 | LED (1–10), DEP (3) | 11 |
| 7 | ADMN (4,5,10), BAK (1,2) | 5 |
| 8 | OBS (1–7), DEP (4,5) | 9 |
| **Total** | | **81** |

---
*Roadmap created: 2026-05-19 from PROJECT.md, REQUIREMENTS.md, and research/{SUMMARY,STACK,ARCHITECTURE,PITFALLS,INTERPOLATION}.md*

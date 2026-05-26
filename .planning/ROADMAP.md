# Roadmap: GRUVAX

**Created:** 2026-05-19
**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

## Core Value (north star for every phase)

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–10 (shipped 2026-05-26) — see [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v10-mvp--shipped-2026-05-26)
- 📋 **v1.x / v2** — next milestone TBD via `/gsd-new-milestone` (likely hardware integration: ESP32 + WS2812B firmware against the Phase 6 MQTT contract, plus the deferred SPIDR items if re-scoped)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–10) — SHIPPED 2026-05-26</summary>

- [x] **Phase 1: First Search → Cube Highlight** (4/4 plans) — End-to-end Core Value: typed query lights the right cube, backed by parser, view, fixture-seeded boundaries, and a cube-only estimator. *(completed 2026-05-20)*
- [x] **Phase 2: Real Position Estimation** (4/4 plans) — Sub-cube interval bar, label-span multi-cube highlight, §4.1 index-based estimator with A/B harness. *(completed 2026-05-20)*
- [x] **Phase 3: Admin Loop (PIN + Manual Entry + Undo)** (5/5 plans) — Owner sign-in (mobile or kiosk-with-in-app-keypad), manual boundary entry, diff previews, and change-set undo. *(completed 2026-05-21)*
- [x] **Phase 4: Realtime Live Updates** (4/4 plans) — Admin edits reach the kiosk live via SSE; concurrent search; optimistic admin updates with rollback. *(completed 2026-05-22)*
- [x] **Phase 5: Segment-Aware Position Precision** (6/6 plans) — INSERTED 2026-05-21. Cut-points + per-label width overrides; segments derived from `v_collection`; two-level interpolation estimator supersedes §4.1; SEG-05 contiguity enforced server- and client-side. *(completed 2026-05-23)*
- [x] **Phase 6: LED Contract over MQTT (Hardware Stubbed)** (4/4 plans) — Pydantic-validated MQTT 5 payloads to internal Mosquitto; admin tunes colors and brightness; all-off + diagnostic + idle/ambient + TTL revert + retain-mode. *(completed 2026-05-24)*
- [x] **Phase 7: Wizards + Import/Export** (8/8 plans) — Guided setup wizard, atomic reshuffle wizard, CSV/YAML dry-run import with COMMIT-IMPORT, boundary + settings export, eight-source History badge. *(completed 2026-05-24)*
- [x] **Phase 8: Observability + Deployment Hardening** (6/6 plans) — `/api/health` per-subsystem + `sync_age_seconds`; `/api/version`; structured JSON logs; slow-query SLO log; release_id-only `record_stats`; `/admin/diagnostics` page; kiosk staleness banner; Compose log limits + healthchecks; GitHub Actions CI with Alembic round-trip + p95 SLO gate. *(completed 2026-05-25)*
- [x] **Phase 9: Tooling and Docs Hardening** (6/6 plans) — structlog + env-driven log level; GitHub Actions tooling adapted from discogsography; dependabot + pre-commit; `update-project.sh`; Phase 1–8 docs refresh. *(completed 2026-05-25)*
- [x] **Phase 10: Close Milestone Gaps** (3/3 plans) — INSERTED 2026-05-25. INT-A SSE payload shape fix (`cube_ids`/`unit`); INT-B undo re-derive + publish in `history.revert_change_set`; SEG-01..08 + CUBE-08 traceability flipped Complete; 81→84 count reconciled. Closes the v1.0 milestone audit. *(completed 2026-05-25)*

Full v1.0 phase details: [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md). Audit trail: [`milestones/v1.0-MILESTONE-AUDIT.md`](./milestones/v1.0-MILESTONE-AUDIT.md).

</details>

### 📋 v1.x / v2 (Planned)

No phases planned yet. Start the next milestone with `/gsd-new-milestone`.

Likely candidates carried forward from v1.0 (see [`MILESTONES.md`](./MILESTONES.md#deferred-to-v1x--v2) for the full deferral list):
- ESP32 + WS2812B firmware against the Phase 6 MQTT contract; live-broker validation of the 6 deferred Phase 6 MQTT 5 wire-level checkpoints.
- SPIDR-deferred resilience/privacy items if re-scoped: SRCH-09, OFF-01..04, PRIV-01..04 (currently in `## v2 / Backlog` of REQUIREMENTS.md — REQUIREMENTS.md is regenerated per-milestone, so these will be re-evaluated at next milestone kickoff).
- Phase 999.1 (admin shelf-overview occupancy) and 999.2 (LED party / sound-reactive modes) — both in Backlog below.

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. First Search → Cube Highlight | v1.0 | 4/4 | Complete | 2026-05-20 |
| 2. Real Position Estimation | v1.0 | 4/4 | Complete | 2026-05-20 |
| 3. Admin Loop (PIN + Manual Entry + Undo) | v1.0 | 5/5 | Complete | 2026-05-21 |
| 4. Realtime Live Updates | v1.0 | 4/4 | Complete | 2026-05-22 |
| 5. Segment-Aware Position Precision | v1.0 | 6/6 | Complete | 2026-05-23 |
| 6. LED Contract over MQTT | v1.0 | 4/4 | Complete | 2026-05-24 |
| 7. Wizards + Import/Export | v1.0 | 8/8 | Complete | 2026-05-24 |
| 8. Observability + Deployment Hardening | v1.0 | 6/6 | Complete | 2026-05-25 |
| 9. Tooling and Docs Hardening | v1.0 | 6/6 | Complete | 2026-05-25 |
| 10. Close Milestone Gaps | v1.0 | 3/3 | Complete | 2026-05-25 |
| 999.1. Shelf-overview mini-Kallax fill/occupancy | Backlog | 0/0 | Captured | — |
| 999.2. LED "party" + "sound-reactive" modes | Backlog | 0/0 | Captured | — |

## Backlog

### Phase 999.1: Shelf-overview mini-Kallax shows per-cube fill/occupancy (BACKLOG)

**Goal:** [Captured for future planning]
**Requirements:** TBD
**Plans:** 0 plans

On the admin **ShelfBinList** screen ("EDIT SHELF {letter}", route `/admin/cubes/:unit`),
the `LocatorHeader` mini 4×4 Kallax overview renders every cube as a uniform empty/dim
tile, so it conveys nothing about the shelf's contents. It should show per-cube
fill/occupancy at a glance — e.g. a fill-level shade or occupied-vs-empty state per cube
(and/or a shelf-level fill summary). Data already exists: `GET /api/admin/cubes` returns
`is_empty` and `fill_level` per cube. Cosmetic/discoverability enhancement; not blocking.
Relates to Phase 5 (segment editor) and the CUBE-05 empty-cube desaturated state in the
design language.

Plans:
- [ ] TBD (promote with `/gsd-review-backlog` when ready)

### Phase 999.2: LED "party" mode + "sound-reactive" mode (BACKLOG)

**Goal:** [Captured for future planning]
**Requirements:** TBD
**Plans:** 0 plans

Post-v1 LED flourishes deferred from Phase 6 (the LED contract). **Party mode** = an
animated multi-cube color show (button- or schedule-triggered); **sound-reactive mode** =
LEDs respond to ambient audio / music. Both build on the Phase 6 LED contract + the future
hardware milestone (real WS2812B firmware) to be observable, and are configurable like the
other LED modes. Not blocking; pure-delight features. (Captured 2026-05-23 during Phase 6
scope expansion.)

Plans:
- [ ] TBD (promote with `/gsd-review-backlog` when ready)

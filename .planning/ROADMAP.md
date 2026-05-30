# Roadmap: GRUVAX

**Created:** 2026-05-19 (v1.0) — extended 2026-05-26 (v2.0 kickoff)
**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

## Core Value (north star for every phase)

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–10 (shipped 2026-05-26) — see [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v10-mvp-shipped-2026-05-26)
- ✅ **v2.0 Multi-User Collections** — Phases 1–5 (shipped 2026-05-30) — see [`milestones/v2.0-ROADMAP.md`](./milestones/v2.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v20-multi-user-collections-shipped-2026-05-30)
- 📋 **v2.1 Resilience + Privacy + UX polish** — Phases TBD (planned) — define fresh requirements via `/gsd-new-milestone`

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1–10) — SHIPPED 2026-05-26</summary>

- [x] **Phase 1: First Search → Cube Highlight** (4/4 plans) — typed query lights the right cube; parser, view, fixture-seeded boundaries, cube-only estimator. *(2026-05-20)*
- [x] **Phase 2: Real Position Estimation** (4/4 plans) — sub-cube interval bar, label-span multi-cube highlight, §4.1 estimator + A/B harness. *(2026-05-20)*
- [x] **Phase 3: Admin Loop (PIN + Manual Entry + Undo)** (5/5 plans) — owner sign-in, manual boundary entry, diff previews, change-set undo. *(2026-05-21)*
- [x] **Phase 4: Realtime Live Updates** (4/4 plans) — admin edits reach the kiosk live via SSE; concurrent search; optimistic updates with rollback. *(2026-05-22)*
- [x] **Phase 5: Segment-Aware Position Precision** (6/6 plans) — INSERTED. Cut-points + per-label width overrides; two-level interpolation supersedes §4.1; SEG-05 contiguity enforced. *(2026-05-23)*
- [x] **Phase 6: LED Contract over MQTT (Hardware Stubbed)** (4/4 plans) — Pydantic-validated MQTT 5 payloads; admin color/brightness; all-off + diagnostic + idle/ambient + TTL revert + retain-mode. *(2026-05-24)*
- [x] **Phase 7: Wizards + Import/Export** (8/8 plans) — setup wizard, atomic reshuffle wizard, CSV/YAML dry-run import, boundary + settings export, History badge. *(2026-05-24)*
- [x] **Phase 8: Observability + Deployment Hardening** (6/6 plans) — `/api/health` + `sync_age_seconds`; `/api/version`; JSON logs; slow-query SLO log; `/admin/diagnostics`; staleness banner; Compose limits + CI SLO gate. *(2026-05-25)*
- [x] **Phase 9: Tooling and Docs Hardening** (6/6 plans) — structlog + env log level; GitHub Actions tooling; dependabot + pre-commit; `update-project.sh`; docs refresh. *(2026-05-25)*
- [x] **Phase 10: Close Milestone Gaps** (3/3 plans) — INSERTED. INT-A SSE payload shape; INT-B undo re-derive + publish; traceability reconcile. *(2026-05-25)*

Full v1.0 phase details: [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md). Audit trail: [`milestones/v1.0-MILESTONE-AUDIT.md`](./milestones/v1.0-MILESTONE-AUDIT.md).

</details>

<details>
<summary>✅ v2.0 Multi-User Collections (Phases 1–5) — SHIPPED 2026-05-30</summary>

Phase numbering RESET for v2.0 (started at Phase 1, not a continuation of v1.0). Re-architected GRUVAX off the `gruvax.v_collection` cross-schema read and onto discogsography's HTTP API with per-user scoped PATs; multiple owner-managed profiles each with their own cache, boundaries, SSE channel, devices, and staleness.

- [x] **Phase 1: Walking skeleton — API client + single-profile sync** (11/11 plans) — `DiscogsographyClient` (httpx + stamina retry); Fernet PAT-at-rest; Alembic 0009 drops `v_collection` + revokes grant; `sync_profile()` staging-swap; positioning off the local `profile_collection` cache; `/api/health` HTTP-probe rewire; Compose fake-discogsography sibling + init-sync. *(2026-05-27)*
- [x] **Phase 2: Multi-profile migration + profile manager** (11/11 plans) — `profiles` table + Fernet PAT; migration 0010 `profile_id NOT NULL` on 5 data tables; per-profile cache/bus/SSE channel; browse-binding session + picker; profile-manager admin UI (CRUD + connect/rotate + poll-until-terminal). *(2026-05-28)*
- [x] **Phase 3: Devices + pairing** (7/7 plans) — `devices` + `pairing_codes` (migration 0011); HttpOnly fingerprint cookie; 4-digit pairing flow A (<30s, hardware-UAT confirmed); device-aware resolution + revoke guard; devices admin UI (PENDING/PAIRED/REVOKED + drawer); Pi provisioning artifacts. *(2026-05-29)*
- [x] **Phase 4: Sync polish + diagnostics** (4/4 plans) — DST-safe nightly `_sync_loop()` + configurable cadence; `needs_reauth` on `GET /api/session`; soft-delete cache-purge; per-profile diagnostics cards; kiosk ReauthBanner + Sync-now progress/toast. *(2026-05-30)*
- [x] **Phase 5: Close v2.0 integration gaps** (2/2 plans) — INSERTED (closure phase). B-01 kiosk `collection_changed` listener (live refresh after sync); B-02 `profile_id`-optional `/api/search` + `/api/locate` with cookie-authoritative fallback. API-02, SYN-01, SYN-02 restored end-to-end. *(2026-05-30)*

Full v2.0 phase details: [`milestones/v2.0-ROADMAP.md`](./milestones/v2.0-ROADMAP.md). Audit trail: [`milestones/v2.0-MILESTONE-AUDIT.md`](./milestones/v2.0-MILESTONE-AUDIT.md). Documented tech debt (non-blocking): DEV-02 SSE immediacy, `write_boundary` profile scoping, `boundary_changed` default-profile-only fan-out.

</details>

### 📋 v2.1 Resilience + Privacy + UX polish (Planned)

Fresh requirements to be defined via `/gsd-new-milestone`. Candidate scope parked in [`milestones/v2.0-REQUIREMENTS.md`](./milestones/v2.0-REQUIREMENTS.md) "Future Requirements" + the Backlog below: AUTH-02 (self-connect PAT), DEV-04 (QR pairing), API-04 (collection diff), SRCH-09 / OFF-01..04 / PRIV-01..04 (SPIDR-deferred), plus v2.0 tech-debt closure (DEV-02 SSE listeners; `write_boundary` profile scoping).

**Committed scope** (promoted from backlog 2026-05-30 — gets a Phase number when `/gsd-new-milestone` builds the v2.1 roadmap):

- **Shelf-overview mini-Kallax fill/occupancy** (was 999.1) — UX polish. Admin ShelfBinList `LocatorHeader` mini 4×4 Kallax should show per-cube fill/occupancy at a glance (fill shade or occupied/empty) instead of uniform dim tiles. Data already exists: `GET /api/admin/cubes` returns `is_empty` + `fill_level` per cube. Relates to Phase 5 (segment editor) + CUBE-05 empty-cube desaturated state. Artifacts: `.planning/phases/999.1-shelf-overview-mini-kallax-shows-per-cube-fill-occupancy/`.

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
| 1. Walking skeleton — API client + single-profile sync | v2.0 | 11/11 | Complete | 2026-05-27 |
| 2. Multi-profile migration + profile manager | v2.0 | 11/11 | Complete | 2026-05-28 |
| 3. Devices + pairing | v2.0 | 7/7 | Complete | 2026-05-29 |
| 4. Sync polish + diagnostics | v2.0 | 4/4 | Complete | 2026-05-30 |
| 5. Close v2.0 integration gaps (B-01 + B-02) | v2.0 | 2/2 | Complete | 2026-05-30 |
| Shelf-overview mini-Kallax fill/occupancy (was 999.1) | v2.1 | 0/0 | Committed | — |
| 999.2. LED "party" + "sound-reactive" modes | Backlog | 0/0 | Captured | — |

## Backlog

> **999.1 promoted 2026-05-30** → committed to v2.1 scope (see the v2.1 Planned section above).

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

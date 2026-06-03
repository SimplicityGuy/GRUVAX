# Roadmap: GRUVAX

**Created:** 2026-05-19 (v1.0) — extended 2026-05-26 (v2.0 kickoff) — extended 2026-05-30 (v2.1 kickoff)
**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

## Core Value (north star for every phase)

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–10 (shipped 2026-05-26) — see [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v10-mvp-shipped-2026-05-26)
- ✅ **v2.0 Multi-User Collections** — Phases 1–5 (shipped 2026-05-30) — see [`milestones/v2.0-ROADMAP.md`](./milestones/v2.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v20-multi-user-collections-shipped-2026-05-30)
- ✅ **v2.1 Resilience + Privacy + UX polish** — Phases 6–10 (shipped 2026-06-03) — see [`milestones/v2.1-ROADMAP.md`](./milestones/v2.1-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v21-resilience--privacy--ux-polish-shipped-2026-06-03)

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

<details>
<summary>✅ v2.1 Resilience + Privacy + UX polish (Phases 6–10) — SHIPPED 2026-06-03</summary>

Phase numbering CONTINUES from v2.0 (v2.1 starts at Phase 6, the global next integer). Hardened GRUVAX for real household use: closed v2.0 tech debt, enabled member self-connect PAT, added QR pairing, enforced query privacy, delivered offline/reconnect UX, and polished the shelf overview.

- [x] **Phase 6: Safe Boundaries + Live Device Lifecycle** (3/3 plans) — `write_boundary` profile-scoped (DATA-01); kiosk reacts to revoke/reassign live via SSE (DEV-05). *(2026-05-31)*
- [x] **Phase 7: Member Self-Connect + Collection Diff** (3/3 plans) — single-use invite-link flow (member pastes own PAT, owner never sees it); "N new records" diff badge after sync; migration 0012 folded in. *(2026-06-01)*
- [x] **Phase 8: QR Pairing + Privacy + Recently-Pulled** (3/3 plans) — QR alongside 4-digit PIN; session-only search history; no-PIN kiosk reset; structlog query redaction. *(2026-06-01)*
- [x] **Phase 9: Offline + Reconnect UX** (5/5 plans) — SSE-authoritative offline banner; degraded mode; auto-reconnect with backoff+jitter; stale-data refresh on reconnect. *(2026-06-02)*
- [x] **Phase 10: Shelf Fill-Overview** (2/2 plans) — mini-Kallax fill/occupancy in admin `LocatorHeader`; milestone close. *(2026-06-02)*

Full v2.1 phase details: [`milestones/v2.1-ROADMAP.md`](./milestones/v2.1-ROADMAP.md). Audit trail: [`milestones/v2.1-MILESTONE-AUDIT.md`](./milestones/v2.1-MILESTONE-AUDIT.md) (status `passed` — all tech debt closed 2026-06-03).

</details>


## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. First Search → Cube Highlight | v1.0 | 4/4 | Complete | 2026-05-20 |
| 2. Real Position Estimation | v1.0 | 4/4 | Complete | 2026-05-20 |
| 3. Admin Loop (PIN + Manual Entry + Undo) | v1.0 | 5/5 | Complete | 2026-05-21 |
| 4. Realtime Live Updates | v1.0 | 4/4 | Complete | 2026-05-22 |
| 5. Segment-Aware Position Precision | v1.0 | 6/6 | Complete | 2026-05-23 |
| 6. LED Contract over MQTT | v1.0 | 3/3 | Complete    | 2026-05-31 |
| 7. Wizards + Import/Export | v1.0 | 3/3 | Complete    | 2026-06-01 |
| 8. Observability + Deployment Hardening | v1.0 | 3/3 | Complete    | 2026-06-02 |
| 9. Tooling and Docs Hardening | v1.0 | 5/5 | Complete   | 2026-06-02 |
| 10. Close Milestone Gaps | v1.0 | 2/2 | Complete    | 2026-06-02 |
| 1. Walking skeleton — API client + single-profile sync | v2.0 | 11/11 | Complete | 2026-05-27 |
| 2. Multi-profile migration + profile manager | v2.0 | 11/11 | Complete | 2026-05-28 |
| 3. Devices + pairing | v2.0 | 7/7 | Complete | 2026-05-29 |
| 4. Sync polish + diagnostics | v2.0 | 4/4 | Complete | 2026-05-30 |
| 5. Close v2.0 integration gaps (B-01 + B-02) | v2.0 | 2/2 | Complete | 2026-05-30 |
| 6. Safe Boundaries + Live Device Lifecycle | v2.1 | 3/3 | Complete | 2026-05-31 |
| 7. Member Self-Connect + Collection Diff | v2.1 | 3/3 | Complete | 2026-06-01 |
| 8. QR Pairing + Privacy + Recently-Pulled | v2.1 | 3/3 | Complete | 2026-06-01 |
| 9. Offline + Reconnect UX | v2.1 | 5/5 | Complete | 2026-06-02 |
| 10. Shelf Fill-Overview | v2.1 | 2/2 | Complete | 2026-06-03 |
| 999.2. LED "party" + "sound-reactive" modes | Backlog | 0/0 | Captured | — |

## Backlog

### Phase 999.2: LED "party" mode + "sound-reactive" mode (BACKLOG)

**Goal:** [Captured for future planning]
**Requirements:** TBD
**Plans:** 4/4 plans complete

Post-v1 LED flourishes deferred from Phase 6 (the LED contract). **Party mode** = an
animated multi-cube color show (button- or schedule-triggered); **sound-reactive mode** =
LEDs respond to ambient audio / music. Both build on the Phase 6 LED contract + the future
hardware milestone (real WS2812B firmware) to be observable, and are configurable like the
other LED modes. Not blocking; pure-delight features. (Captured 2026-05-23 during Phase 6
scope expansion.)

Plans:

- [ ] TBD (promote with `/gsd-review-backlog` when ready)

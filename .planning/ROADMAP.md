# Roadmap: GRUVAX

**Created:** 2026-05-19 (v1.0) — extended 2026-05-26 (v2.0 kickoff) — extended 2026-05-30 (v2.1 kickoff)
**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

## Core Value (north star for every phase)

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–10 (shipped 2026-05-26) — see [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v10-mvp-shipped-2026-05-26)
- ✅ **v2.0 Multi-User Collections** — Phases 1–5 (shipped 2026-05-30) — see [`milestones/v2.0-ROADMAP.md`](./milestones/v2.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v20-multi-user-collections-shipped-2026-05-30)
- 🚧 **v2.1 Resilience + Privacy + UX polish** — Phases 6–10 (in progress)

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

### 🚧 v2.1 Resilience + Privacy + UX polish (In Progress)

Phase numbering CONTINUES from v2.0 (v2.1 starts at Phase 6, the global next integer). Hardens GRUVAX for real household use: closes v2.0 tech debt, enables member self-connect PAT, adds QR pairing, enforces query privacy, delivers offline/reconnect UX, and polishes the shelf overview.

- [x] **Phase 6: Safe Boundaries + Live Device Lifecycle** — write_boundary profile-scoped; kiosk reacts to revoke/reassign live via SSE. (completed 2026-05-31)
- [ ] **Phase 7: Member Self-Connect + Collection Diff** — invite-token flow (member pastes own PAT); "N new records" badge after sync; migration 0012 folded in.
- [ ] **Phase 8: QR Pairing + Privacy + Recently-Pulled** — QR alongside 4-digit PIN; session-only history; no-PIN kiosk reset; structlog query redaction.
- [ ] **Phase 9: Offline + Reconnect UX** — offline banner (SSE-authoritative); degraded mode; auto-reconnect with backoff+jitter; stale-data refresh on reconnect.
- [ ] **Phase 10: Shelf Fill-Overview** — mini-Kallax fill/occupancy in `LocatorHeader`; milestone close.

## Phase Details

### Phase 6: Safe Boundaries + Live Device Lifecycle

**Goal**: The kiosk reflects device revoke/reassign immediately via SSE, and boundary writes are scoped to the correct profile — making multi-profile boundary editing safe.
**Depends on**: Nothing (v2.1 foundation — must go first)
**Requirements**: DATA-01, DEV-05
**Success Criteria** (what must be TRUE):

  1. When the admin revokes a kiosk device, the kiosk navigates to the pairing screen within one SSE ping interval (no manual reload required).
  2. When the admin reassigns a kiosk to a different profile, the kiosk re-binds and shows the new profile's collection live.
  3. A boundary edit on profile A cannot modify profile B's cube for the same physical position (verified by two-profile integration test).
  4. The `boundary_changed` SSE event is delivered only to SSE clients subscribed to the affected profile's bus (not broadcast to all profiles).**Plans**: 3 plans (2 waves)

**Wave 1**

  - [x] 06-01-PLAN.md — DATA-01: profile-scope write_boundary + 6 call sites + per-profile SSE fan-out (Wave 1)
  - [x] 06-02-PLAN.md — DEV-05: kiosk SSE device_revoked/device_reassigned handlers + unified 403 + Nordic-Grid notice/banner (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

  - [x] 06-03-PLAN.md — DATA-01 verification: two-profile boundary isolation + unbound-400 + 0-row-404 + per-profile boundary_changed & admin_editing fan-out tests (Wave 2)

**UI hint**: no

### Phase 7: Member Self-Connect + Collection Diff

**Goal**: A household member can connect their own Discogs collection to a profile without the owner ever seeing their PAT; after each sync the kiosk and admin show how many new records arrived.
**Depends on**: Phase 6 (SSE bus correctness ensures `collection_changed` diff payload reaches the right kiosk)
**Requirements**: AUTH-02, API-04
**Open decisions (resolve at plan time)**: Invite-redeem TLS posture on LAN; `first_seen_at` vs `arrived_at` column naming; discogsography CI fixture must support a `limit=1` PAT-validation call.
**Success Criteria** (what must be TRUE):

  1. Owner generates a time-limited invite link for a profile; the link can be shared via iMessage/email; the owner's admin UI shows only `has_token: true/false`, never the raw or encrypted token.
  2. Member opens the invite link, pastes their own discogsography PAT into the form, and submits; the profile connects and an initial sync starts — all without the owner taking any further action.
  3. Submitting the same invite link a second time returns a clear "already redeemed" error (single-use enforced).
  4. After any sync (nightly or manual), the admin diagnostics card and kiosk `collection_changed` SSE payload include an `item_count_delta` showing how many records are new since the previous sync.

**Plans**: 3 plans (3 waves)

**Wave 1**

  - [x] 07-01-PLAN.md — API-04 backend + migration 0012: profile_invite_codes table, first_seen_at, profiles diff columns; new_record_count + is_initial_import computed in the staging swap; extended collection_changed SSE payload; has_token on admin API; Wave-0 test scaffolds.

**Wave 2** *(blocked on Wave 1 — needs profile_invite_codes table)*

  - [x] 07-02-PLAN.md — AUTH-02 backend: invite_codes.py router (owner generate + public validate + public redeem), atomic single-use consume, pool-isolated PAT validation, Fernet store, uniform 404, per-IP redeem rate limit; router registration; all 12 integration tests.

**Wave 3** *(blocked on Waves 1–2 — needs both backends)*

  - [ ] 07-03-PLAN.md — AUTH-02 + API-04 frontend: public /redeem/:code page, owner Copy-invite-link affordance (generate + TTL + clipboard), admin NEW RECORDS row, kiosk yellow pill; ends with human-verify checkpoint.

**UI hint**: yes

### Phase 8: QR Pairing + Privacy + Recently-Pulled

**Goal**: The kiosk pairing screen offers a scannable QR code alongside the 4-digit PIN; search history never persists beyond the current session; a no-PIN "Reset kiosk" button clears the local session; query text never appears in server logs.
**Depends on**: Phase 6 (DEV-05 SSE consumer wired before QR adds a second pairing path)
**Requirements**: DEV-04, PRIV-01, PRIV-02, PRIV-03, PRIV-04, SRCH-09
**Open decisions (resolve at plan time)**: QR HTTP-vs-HTTPS on LAN (Pitfall 39 — recommend Option A: HTTP + 60-second nonce rotation + single-use, documented as a Key Decision).
**Success Criteria** (what must be TRUE):

  1. The kiosk pairing screen displays a QR code next to the 4-digit PIN; the admin can scan it on a phone and complete pairing without typing — and both paths call the same `complete_pairing()` function and emit identical audit log entries.
  2. The recently-pulled chip list clears on browser session end, on kiosk reboot, and when the owner taps "Reset kiosk" — it does not survive a hard Chromium restart.
  3. Tapping "Reset kiosk" (visible only when no admin session is active) clears the local session client-side only with zero API calls.
  4. Running `docker logs gruvax-api | grep <any-search-term>` returns zero hits after a search (structlog query redaction + Uvicorn access-log disabled confirmed by CI test).

**Plans**: TBD
**UI hint**: yes

### Phase 9: Offline + Reconnect UX

**Goal**: When the GRUVAX server is unreachable the kiosk shows a clear offline banner (driven by SSE state, not `navigator.onLine`), preserves the last locate result, then auto-reconnects with backoff and refreshes stale data on success.
**Depends on**: Phase 6 (DEV-05 SSE consumer handles device-revoked 403 as terminal state, required for correct offline terminal-revoke path)
**Requirements**: OFF-01, OFF-02, OFF-03, OFF-04
**Open decisions (resolve at plan time)**: TanStack Query `networkMode: 'always'` (PITFALLS reasoning overrides STACK recommendation — prevents reconnect storm; Pitfall 36).
**Success Criteria** (what must be TRUE):

  1. Stopping `gruvax-api` causes the offline banner to appear on the kiosk within one SSE ping interval (~15–20 s); `navigator.onLine` alone does not trigger it.
  2. While offline, the last locate result and cube highlight remain visible; the search input is disabled with a clear "Offline" affordance.
  3. When `gruvax-api` restarts, all kiosks reconnect and the offline banner clears within 30 seconds; reconnects are spread over a jitter window (no simultaneous thundering herd).
  4. On successful reconnect, stale search and boundary data is refreshed (TanStack Query invalidation on `server_hello`); any diff badge that was dismissed stays dismissed.

**Plans**: TBD
**UI hint**: yes

### Phase 10: Shelf Fill-Overview

**Goal**: The admin ShelfBinList `LocatorHeader` mini 4×4 Kallax shows per-cube fill/occupancy at a glance, giving the owner an instant visual of how full each bin is without opening the full boundary editor.
**Depends on**: Phase 6 (write_boundary profile-scoping ensures fill data is correctly isolated per profile before it is visualized)
**Requirements**: UX-01
**Success Criteria** (what must be TRUE):

  1. The `LocatorHeader` mini-Kallax renders each cube shaded by fill level (`is_empty` cubes in the CUBE-05 desaturated state, filled cubes proportionally lit) using existing design tokens — no hardcoded hex values.
  2. The fill shading updates live after a sync (TanStack Query invalidation on `collection_changed`) without a page reload.
  3. An empty cube and a full cube are visually distinct at a glance on the 7" kiosk display.

**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. First Search → Cube Highlight | v1.0 | 4/4 | Complete | 2026-05-20 |
| 2. Real Position Estimation | v1.0 | 4/4 | Complete | 2026-05-20 |
| 3. Admin Loop (PIN + Manual Entry + Undo) | v1.0 | 5/5 | Complete | 2026-05-21 |
| 4. Realtime Live Updates | v1.0 | 4/4 | Complete | 2026-05-22 |
| 5. Segment-Aware Position Precision | v1.0 | 6/6 | Complete | 2026-05-23 |
| 6. LED Contract over MQTT | v1.0 | 3/3 | Complete    | 2026-05-31 |
| 7. Wizards + Import/Export | v1.0 | 2/3 | In Progress|  |
| 8. Observability + Deployment Hardening | v1.0 | 6/6 | Complete | 2026-05-25 |
| 9. Tooling and Docs Hardening | v1.0 | 6/6 | Complete | 2026-05-25 |
| 10. Close Milestone Gaps | v1.0 | 3/3 | Complete | 2026-05-25 |
| 1. Walking skeleton — API client + single-profile sync | v2.0 | 11/11 | Complete | 2026-05-27 |
| 2. Multi-profile migration + profile manager | v2.0 | 11/11 | Complete | 2026-05-28 |
| 3. Devices + pairing | v2.0 | 7/7 | Complete | 2026-05-29 |
| 4. Sync polish + diagnostics | v2.0 | 4/4 | Complete | 2026-05-30 |
| 5. Close v2.0 integration gaps (B-01 + B-02) | v2.0 | 2/2 | Complete | 2026-05-30 |
| 6. Safe Boundaries + Live Device Lifecycle | v2.1 | 0/TBD | Not started | — |
| 7. Member Self-Connect + Collection Diff | v2.1 | 0/3 | Planned | — |
| 8. QR Pairing + Privacy + Recently-Pulled | v2.1 | 0/TBD | Not started | — |
| 9. Offline + Reconnect UX | v2.1 | 0/TBD | Not started | — |
| 10. Shelf Fill-Overview | v2.1 | 0/TBD | Not started | — |
| 999.2. LED "party" + "sound-reactive" modes | Backlog | 0/0 | Captured | — |

## Backlog

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

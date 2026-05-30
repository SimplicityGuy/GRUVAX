# Roadmap: GRUVAX

**Created:** 2026-05-19 (v1.0) — extended 2026-05-26 (v2.0 kickoff)
**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

## Core Value (north star for every phase)

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Milestones

- ✅ **v1.0 MVP** — Phases 1–10 (shipped 2026-05-26) — see [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md) and [`MILESTONES.md`](./MILESTONES.md#v10-mvp-shipped-2026-05-26)
- 🚧 **v2.0 Multi-User Collections** — Phases 1–4 (planned 2026-05-26) — phase numbering RESET via `--reset-phase-numbers`; gated on EXTERNAL discogsography v2 prereq (DGS-PREREQ)

## Cross-Repo Gating Dependency (v2.0)

**GRUVAX P1 does not start until discogsography ships the contract artifact at `docs/specs/v2-gruvax-integration.md` in their repo.**

The discogsography v2 work — `app_tokens` table, catalog# verification/exposure on `GET /api/user/collection`, `require_app_token` FastAPI dependency, scoped "Connect an app" settings UI, per-token rate limiting — is tracked as **DGS-EXT-01..05** in `.planning/intel/context.md`. It is **NOT** part of GRUVAX's REQUIREMENTS.md or P1–P4 plan; it is the external prereq for the milestone.

- Briefed at `background/discogsography-v2-app-tokens-brief.md` (gitignored).
- The discogsography agent session is in flight as of v2.0 kickoff.
- **HIGH-risk gate:** catalog# exposure on the discogsography collection API — verification spike is the FIRST step of discogsography v2 P1; three documented outcome branches drive subsequent scope. Positioning is impossible without catalog#.
- GRUVAX waits for the "shipped" signal, then reads `docs/specs/v2-gruvax-integration.md` and reconciles any contract drift against the refined design spec before invoking `/gsd-discuss-phase 1`.

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

### 🚧 v2.0 Multi-User Collections (Planned)

Phase numbering RESET — these are the v2.0 phases starting at Phase 1, not a continuation of v1.0's numbering. The refined design spec at [`docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md`](../docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md) §"Phase Decomposition" is the authoritative source for phase exit criteria.

- [x] **Phase 1: Walking skeleton — API client + single-profile sync** — Core Value end-to-end against one API-sourced collection; `v_collection` retired; positioning runs off the local `profile_collection` cache. (completed 2026-05-27)
- [x] **Phase 2: Multi-profile migration + profile manager** — Full `profiles` table with Fernet PAT storage; `profile_id` NOT NULL migration tightening the 5 per-profile data tables (the 2 global/infra tables keep nullable `profile_id`); per-profile caches + SSE channel; profile manager admin UI; browser session profile picker. (completed 2026-05-28)
- [x] **Phase 3: Devices + pairing** — `devices` + `pairing_codes` schemas; HttpOnly fingerprint cookie; 4-digit code pairing flow A (5-min TTL, auto-reroll); devices admin UI with PENDING / PAIRED / REVOKED groupings. (completed 2026-05-29)
- [x] **Phase 4: Sync polish + diagnostics** — Nightly background sync (24h @ 03:00 local default, configurable 24h/12h/6h/off); 401 reauth UI; per-profile diagnostics cards; soft-delete cache-purge background task; "Sync now" progress + completion toast. (completed 2026-05-30)
- [ ] **Phase 5: Close v2.0 integration gaps** — ADDED 2026-05-30 (closure phase, like v1.0 Phase 10). Wires the SSE/session seams the milestone audit surfaced: B-01 kiosk `collection_changed` listener (stale results after nightly/manual sync) + B-02 `profile_id`-null guard on `/api/search` + `/api/locate` (422 before session bootstrap resolves the bound profile). Scope/warnings sourced from [`v2.0-MILESTONE-AUDIT.md`](./v2.0-MILESTONE-AUDIT.md).

## Phase Details

### Phase 1: Walking skeleton — API client + single-profile sync

**Goal**: Restore Core Value end-to-end (search → cube highlight ≤ 200 ms) against API-sourced collection data, with `gruvax.v_collection` retired and positioning running off the local `profile_collection` cache for a single default profile.
**Depends on**: DGS-PREREQ (external — discogsography v2 ships the contract artifact at `docs/specs/v2-gruvax-integration.md`)
**Requirements**: API-01, API-02 (single-profile flavor), API-03, SYN-02 (single-profile staleness), PROF-03
**Success Criteria** (what must be TRUE):

  1. The search → cube highlight loop works end-to-end against API-sourced data; a typed query (artist / title / label / catalog#) returns the right cube + sub-cube position estimate.
  2. v1.0 SLOs hold: `/api/search` p95 ≤ 200 ms and `/api/locate` p95 ≤ 50 ms on synthetic data (v1.0 Phase 8 CI gate continues to pass).
  3. `gruvax.v_collection` is dropped and the read-only Postgres grant to discogsography's collection tables is revoked in the same Alembic migration; the round-trip (`upgrade head → downgrade base → upgrade head`) is clean.
  4. The default profile's first sync (`id = 00000000-0000-0000-0000-000000000001`, `display_name = 'Default'`) completes with `last_sync_status = 'ok'` and `last_sync_item_count` ≥ the v1 baseline (~3,000 items).
  5. `/api/health` reports discogsography reachability via HTTP probe (not cross-schema view); kiosk staleness banner reads from `now() - profiles.last_sync_at` for the single default profile.

**Plans**: 9 plans (5 waves; W0: 01-00 | W1 parallel: 01-01 + 01-02 | W2: 01-03 | W3 parallel: 01-04 + 01-05 | W4: 01-06 | W5 gap-closure parallel: 01-07 + 01-08)

**Wave 0**

- [x] 01-00-PLAN.md — Test scaffolding: package markers, canonical fake-discogsography shell, deterministic synth-data generator (D-15/D-17)

**Wave 1**

- [x] 01-01-PLAN.md — Schema migration 0009 + settings (DISCOGSOGRAPHY_BASE_URL, GRUVAX_SECRET_KEY) + pool search_path simplification + Alembic round-trip CI gate
- [x] 01-02-PLAN.md — DiscogsographyClient (httpx + stamina retry) + Fernet PAT crypto + structlog dscg_* redactor + in-process fake-discogsography FastAPI fixture

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-03-PLAN.md — sync_profile(profile_id) staging-swap routine (advisory lock + COPY + atomic DELETE/INSERT/UPDATE + inline cache refresh per D-14)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 01-04-PLAN.md — POST /api/admin/profiles/{id}/sync (PIN-gated) + gruvax-set-pat CLI (stdin-only, strict rotation per D-09) + gruvax-sync CLI
- [x] 01-05-PLAN.md — /api/health field rename (discogsography_view_check → discogsography_api_check, 3-state per D-13) + lifespan rewire (profile_collection probe + default_profile_* background task) + Compose fake-discogsography sibling + init-sync container

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 01-06-PLAN.md — Rewire src/gruvax/db/queries.py + estimator/collection_snapshot.py from v_collection → profile_collection + synth_profile_collection.sql fixture + SLO benchmark gate (p95 search ≤200ms, locate ≤50ms)

**Wave 5 — gap closure** *(blocked on Wave 4 completion; closes 01-VERIFICATION.md gaps)*

- [x] 01-07-PLAN.md — Integration-test conftest seed fixture (lifts Plan 01-06 sync-psycopg pattern suite-wide) + fixtures/boundaries.yaml realignment to v2 generator catalog numbers (closes Gap #1 BLOCKER + Gap #3 cascade)
- [x] 01-08-PLAN.md — Rewrite test_migrate_0009.py::_alembic to subprocess.run via asyncio.to_thread (closes Gap #2 WARNING — asyncio.run-from-async event-loop conflict)

**UI hint**: yes

### Phase 2: Multi-profile migration + profile manager

**Goal**: Multiple owner-managed profiles operate independently with their own collection caches, boundaries, segments, settings, LED config, and stats; browser sessions on LAN can choose which profile to view; admin can create, connect, rotate, rename, and soft-delete profiles.
**Depends on**: Phase 1
**Requirements**: PROF-01, PROF-02, PROF-04, API-02 (multi-profile cache routing completion), SYN-02 (per-profile staleness completion)
**Success Criteria** (what must be TRUE):

  1. Owner can create a profile (e.g., "Sam") via the profile manager admin UI, paste a PAT, see a successful synchronous `per_page=1` test sync capture `discogsography_user_id`, and observe the full async sync complete with `last_sync_status = 'ok'`.
  2. Two browser sessions on the LAN can concurrently show different profiles (each picks via the profile picker; session cookie binds `bound_profile_id`); a single-active-profile deployment auto-binds and skips the picker.
  3. The `profile_id NOT NULL` migration tightens the 5 per-profile data tables that received `profile_id` in migration 0009 (`cube_boundaries`, `settings`, `record_stats`, `segment_overrides`, `boundary_history`) to NOT NULL — `admin_sessions` and `idempotency_keys` keep their nullable `profile_id` (global/infra, not per-profile data) — backfills v1 data to the deterministic default profile, and survives a clean Alembic upgrade↔downgrade round-trip (v1.0 CI invariant carries over).
  4. Per-profile SSE channel `/api/events/{profile_id}` invalidates only the affected profile's `BoundaryCache` / `SegmentCache` / `CollectionSnapshot` on `boundary_changed` and `collection_changed` events; cross-profile data leakage is impossible by construction.
  5. p95 `/api/search` ≤ 200 ms and `/api/locate` ≤ 50 ms SLOs hold with 2+ profiles cached in memory (verified via the v1.0 Phase 8 CI benchmark gate, parameterized over profile_id).

**Plans**: 8 plans (6 waves; W0: 02-00 | W1: 02-01 | W2: 02-02 | W3 parallel: 02-03 + 02-04 + 02-05 | W4: 02-06 | W5: 02-07)
**Wave 1**

- [x] 02-00-PLAN.md — Wave 0 test scaffolding: 6 RED test files + `second_profile` fixture (PROF-04/PROF-02/API-02/SYN-02 baselines)
- [x] 02-01-PLAN.md — Migration 0010: `profile_id NOT NULL` on 5 data tables + 4 composite PKs (2 infra tables stay nullable) + clean round-trip (PROF-04)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Per-profile cache/bus/state registries on app.state + per-profile resolution deps + per-profile sync cache refresh (API-02, SYN-02, D2-01..06)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — Per-profile SSE `/api/events/{profile_id}` + profile-scoped search/locate/illuminate + re-parameterized SLO gate (API-02, SYN-02, D2-04)
- [x] 02-04-PLAN.md — Browse-binding session: `GET /api/session` bootstrap + auto-bind + bind/unbind + independent cookie (PROF-02, SYN-02, D2-07/08/10)
- [x] 02-05-PLAN.md — Profile CRUD + connect/rotate-PAT + 202+poll sync conversion + soft-delete registry eviction (PROF-01, PROF-02, D2-12/13)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 02-06-PLAN.md — Browser profile UX: `/select` picker + onboarding + Switch-profile button + empty-collection state + KioskView per-profile wiring (PROF-02, SYN-02, D2-03/07/08/09)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 02-07-PLAN.md — Profile-manager admin UI: PROFILES tab + list + status badges + bottom-sheet drawer (connect/rotate/rename/sync/delete) + 202 poll + toast (PROF-02, PROF-01, D2-11)

**Wave 6 — gap closure** *(closes 02-UAT.md gaps from user-driven UAT; both parallel — disjoint files)*

- [x] 02-08-PLAN.md — GAP 1 (major): poll-until-terminal `refetchInterval` in ProfileDrawer (stop only on 'ok'/'failed') + atomic terminal-write confirmation → drawer auto-transitions SYNCING → CONNECTED + toast without manual refresh (PROF-02, PROF-01)
- [x] 02-09-PLAN.md — GAP 2 (minor): kiosk "shelf layout not configured" affordance when an in-collection result lands no cube (zero-boundary profile); admin boundary-onboarding flow explicitly deferred to a future phase (PROF-02)

**UI hint**: yes

### Phase 3: Devices + pairing

**Goal**: A headless RPi kiosk can be paired to a profile in under 30 seconds end-to-end via a 4-digit code shown on the kiosk; the binding persists across reboots; admin can rename, change-profile, unbind, or revoke devices from a mobile admin UI.
**Depends on**: Phase 2
**Requirements**: DEV-01, DEV-02, DEV-03
**Success Criteria** (what must be TRUE):

  1. A fresh RPi paired to a profile in <30 seconds end-to-end: kiosk renders a 4-digit code (Nordic Grid styling, large DM Mono digits, 5-min countdown, auto-reroll on expiry); admin types code via the v1 in-app numeric keypad, picks a profile, labels the device; kiosk polls and auto-navigates to the bound-profile search UI on success.
  2. RPi reboots → kiosk returns to its bound profile (HttpOnly + SameSite=Strict fingerprint cookie persists across reboot, verified with Chromium `--user-data-dir` on persistent storage).
  3. Revoking a device immediately drops the kiosk to the pairing screen on its next request; re-assigning to a different profile auto-reloads the kiosk via SSE; soft-deleting a profile detaches all bound devices (kiosks revert to the profile-picker).
  4. The devices admin UI shows PENDING / PAIRED / REVOKED groupings with a drawer per device (rename / change-profile / unbind / revoke), all PIN-gated.
  5. Pairing-code brute-force resistance holds: 5-min TTL × 10k keyspace × `consumed_at` one-shot guard × admin PIN-gating on `/api/admin/devices/bind`; concurrent bind attempts on the same code → first wins, second sees "Code not found".

**Plans**: 6 plans (5 waves; W1: 03-00 | W2: 03-01 | W3 parallel: 03-02 + 03-03 | W4: 03-04 | W5: 03-05)
Plans:
**Wave 1**

- [x] 03-00-PLAN.md — Wave 0 test scaffolding: RED test files for DEV-01/02/03 + Playwright dev dep (package-legitimacy checkpoint)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 03-01-PLAN.md — Migration 0011 (devices + pairing_codes + indexes, round-trip) + HttpOnly fingerprint cookie helpers (DEV-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-02-PLAN.md — Kiosk pairing endpoints + admin device CRUD + atomic PIN-gated rate-limited bind + revoke/reassign SSE (DEV-02, DEV-03)
- [x] 03-03-PLAN.md — Device-aware resolution + per-request revoke guard + GET /api/session device binding + profile soft-delete detach (DEV-02, DEV-03)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 03-04-PLAN.md — Frontend: /pair countdown route + admin Devices UI (groups + drawer + NumericKeypad bind) + routing precedence + affordances (DEV-02, DEV-03)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 03-05-PLAN.md — Pi provisioning artifacts (start-kiosk.sh + systemd unit + README) + Playwright reboot-persistence test (DEV-01)

**UI hint**: yes

### Phase 4: Sync polish + diagnostics

**Goal**: Sync runs nightly without owner intervention; PAT revocation surfaces within 24 hours worst case (immediate with manual sync); admin can see per-profile diagnostics; soft-deleted profiles have their caches purged in the background; the "Sync now" path provides progress + completion feedback.
**Depends on**: Phase 3
**Requirements**: SYN-01, SYN-02 (closure — staleness UX polish per profile)
**Success Criteria** (what must be TRUE):

  1. Nightly background sync at 03:00 local fires for all non-revoked profiles sequentially via `asyncio.create_task(_sync_loop())` started in lifespan; cadence is configurable in `/admin/settings` (24h / 12h / 6h / off) and the choice persists.
  2. A 401 from discogsography surfaces within ≤24h worst case (immediate when manual "Sync now" is triggered): the profile-list admin UI shows a re-auth-required badge on the affected profile, and the kiosk renders an inline banner directing the owner to rotate the PAT.
  3. Per-profile `/admin/diagnostics` cards accurately report `last_sync_at`, `last_sync_status`, `last_sync_item_count`, and `last_sync_error` for each non-deleted profile; cards continue to use the Nordic Grid typography established in v1.0 Phase 8.
  4. Soft-deleting a profile schedules a cache-purge background task that removes `profile_collection` rows and detaches bound devices without cascading the audit lineage (`change_log` / `change_sets` retain their FKs).
  5. The admin "Sync now" button shows progress until the sync completes and fires a completion toast; all v1.0 invariants — Alembic round-trip clean, p95 SLOs, structured logs, log-ring buffer, in-app keypad — continue to hold at v2.0 close.

**Plans**: 4 plans (3 waves; W0: 04-00 | W1 parallel: 04-01 + 04-02 | W2: 04-03)

**Wave 0**

- [x] 04-00-PLAN.md — Wave 0 test scaffolding: 6 RED test files (scheduler property/unit, session needs_reauth, purge, diagnostics profiles[], cadence persistence) (SYN-01, SYN-02)

**Wave 1** *(blocked on Wave 0 completion; parallel — disjoint files)*

- [x] 04-01-PLAN.md — Backend sync autonomy: nightly `_sync_loop()` + DST `next_fire_after()` + startup catch-up & purge sweeps + `sync.cadence` setting + soft-delete purge + `needs_reauth` on `GET /api/session` + D4-09/D4-07 verify (SYN-01, SYN-02)
- [x] 04-02-PLAN.md — `GET /api/admin/diagnostics` per-profile `profiles[]` section (SYN-02)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 04-03-PLAN.md — Frontend: kiosk ReauthBanner + admin re-auth badge + per-profile diagnostics cards (30s refetch) + Sync-now spinner/elapsed/toast + cadence select (SYN-02)

**UI hint**: yes

## Progress

| Phase | Milestone | Plans | Status | Completed |
|-------|-----------|-------|--------|-----------|
| 1. First Search → Cube Highlight | v1.0 | 11/11 | Complete    | 2026-05-27 |
| 2. Real Position Estimation | v1.0 | 11/10 | Complete    | 2026-05-29 |
| 3. Admin Loop (PIN + Manual Entry + Undo) | v1.0 | 7/6 | Complete    | 2026-05-29 |
| 4. Realtime Live Updates | v1.0 | 4/4 | Complete    | 2026-05-30 |
| 5. Segment-Aware Position Precision | v1.0 | 6/6 | Complete | 2026-05-23 |
| 6. LED Contract over MQTT | v1.0 | 4/4 | Complete | 2026-05-24 |
| 7. Wizards + Import/Export | v1.0 | 8/8 | Complete | 2026-05-24 |
| 8. Observability + Deployment Hardening | v1.0 | 6/6 | Complete | 2026-05-25 |
| 9. Tooling and Docs Hardening | v1.0 | 6/6 | Complete | 2026-05-25 |
| 10. Close Milestone Gaps | v1.0 | 3/3 | Complete | 2026-05-25 |
| 1. Walking skeleton — API client + single-profile sync | v2.0 | 0/6 | Planned (4 waves) | — |
| 2. Multi-profile migration + profile manager | v2.0 | 0/8 | Planned (6 waves) | — |
| 3. Devices + pairing | v2.0 | 0/6 | Planned (5 waves) | — |
| 4. Sync polish + diagnostics | v2.0 | 0/4 | Planned (3 waves) | — |
| 5. Close v2.0 integration gaps (B-01 + B-02) | v2.0 | 0/0 | Planned | — |
| 999.1. Shelf-overview mini-Kallax fill/occupancy | Backlog | 0/0 | Captured | — |
| 999.2. LED "party" + "sound-reactive" modes | Backlog | 0/0 | Captured | — |

### Phase 5: Close v2.0 integration gaps: kiosk collection_changed listener (B-01) + profile_id-null guard on search/locate (B-02)

**Goal:** Close the two cross-phase BLOCKERS from the v2.0 milestone audit so the milestone's end-to-end flows hold: the kiosk consumes the `collection_changed` SSE event (B-01 — live result refresh after nightly/manual sync, no manual reload), and `/api/search` + `/api/locate` tolerate an omitted `profile_id` by resolving the bound profile server-side while the frontend gates the fetch on a resolved profile (B-02 — no 422 before session bootstrap). Warnings W-01..W-04 are out of scope (tech debt).
**Requirements**: API-02, SYN-01, SYN-02 (end-to-end restoration; satisfied at phase-level in P1/P2/P4, degraded by these blockers)
**Depends on:** Phase 4
**Plans:** 0 plans

Plans:
- [ ] TBD (run /gsd-plan-phase 5 to break down)

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

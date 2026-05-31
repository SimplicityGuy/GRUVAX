---
gsd_state_version: 1.0
milestone: v2.1
milestone_name: Resilience + Privacy + UX polish
status: executing
last_updated: "2026-05-31T05:21:30.956Z"
last_activity: 2026-05-31
progress:
  total_phases: 6
  completed_phases: 1
  total_plans: 3
  completed_plans: 3
  percent: 17
---

# State: GRUVAX

**Initialized:** 2026-05-19

## Project Reference

**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

**Current Focus:** Phase 06 — safe-boundaries-live-device-lifecycle

**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

**Granularity:** standard

## Current Position

Phase: 06 (safe-boundaries-live-device-lifecycle) — COMPLETE
Plan: 3 of 3 (all plans complete)
Status: Phase 06 complete — 3/3 plans delivered
Last activity: 2026-05-31 -- Phase 06 Plan 03 (two-profile isolation tests) complete

```
v2.1 Progress: [          ] 0% (0/5 phases)
```

## Performance Metrics (v2.1)

| Metric | Value |
|--------|-------|
| v2.1 requirements | 15 |
| Requirements mapped | 15 / 15 (100%) |
| Phases planned | 5 (Phases 6–10) |
| Plans complete | 0 |
| Phase 06 P03 | 900 | 3 tasks | 1 files |

### Historical (v2.0, shipped 2026-05-30)

| Metric | Value |
|--------|-------|
| v2.0 active requirements | 12 |
| Requirements satisfied | 12 / 12 (100%) |
| Deferred (not in v2.0) | 1 (AUTH-01 → v2.2) |
| External prereqs (discogsography) | 5 (DGS-EXT-01..05) |
| Phases shipped | 5 / 5 |
| Plans complete | 35 |
| Audit | tech_debt (no blockers) |

### Historical (v1.0, shipped 2026-05-26)

| Metric | Value |
|--------|-------|
| v1.0 in-scope requirements | 84 |
| v1.0 requirements satisfied | 75 / 75 in-scope (9 SPIDR-relocated to v2/Backlog) |
| v1.0 phases shipped | 10 / 10 |
| v1.0 plans completed | 50 |

## Accumulated Context

### Pending Todos (active)

- [ ] **Phase 6 prerequisite:** Grep-verify ALL `write_boundary` call sites in `src/gruvax/admin/cubes.py` before the Phase 6 PR merges — there must be exactly one caller per admin write path, and each must pass `profile_id` from the resolved session.
- [ ] **Phase 7 prerequisite (open decision):** Confirm discogsography CI fixture supports a `limit=1` PAT-validation call (AUTH-02 integration tests require this before CI can run without network access).
- [ ] **Phase 7 prerequisite (open decision):** Decide invite-redeem TLS posture on LAN (document as runbook note; TLS optional for home LAN but required if API ever extends beyond home LAN).
- [ ] **Phase 7 prerequisite (open decision):** Settle `first_seen_at` vs `arrived_at` column naming for `profiles.prev_sync_item_count` companion before migration 0012 is written. Research recommends `first_seen_at`.
- [ ] **Phase 8 prerequisite (open decision):** Resolve QR HTTP-vs-HTTPS on LAN (Pitfall 39). Research recommends Option A — HTTP + 60-second nonce rotation + single-use — documented as a Key Decision before DEV-04 implementation starts.
- [ ] **Phase 9 prerequisite (open decision):** Confirm TanStack Query `networkMode: 'always'` (not `'offlineFirst'`) — PITFALLS reasoning overrides STACK recommendation; prevents reconnect storm (Pitfall 36).
- [ ] **Deployment-time:** Wire the live discogsography API once their v2 contract artifact (`docs/specs/v2-gruvax-integration.md`) lands; reconcile any drift against the fake-discogsography fixture.

### Roadmap Evolution

- **2026-05-30** — v2.1 roadmap created. Phase numbering CONTINUES from v2.0 (global sequence: v2.1 starts at Phase 6). 5 phases (P6: Safe Boundaries + Live Device Lifecycle; P7: Member Self-Connect + Collection Diff; P8: QR Pairing + Privacy + Recently-Pulled; P9: Offline + Reconnect UX; P10: Shelf Fill-Overview). 15 v2.1 requirements mapped 100% across P6–P10.
- **2026-05-30** — v2.0 archived. 5 phases, 35 plans. Phase 5 (Close v2.0 integration gaps) inserted as closure phase. See `milestones/v2.0-ROADMAP.md`.
- **2026-05-26** — v2.0 milestone created. Phase numbering RESET for v2.0 (started at Phase 1). 4 phases planned; Phase 5 inserted as closure phase during execution.
- **2026-05-26** — v1.0 archived. 10 phases, 50 plans. Phase 5 (Segment-Aware Position Precision) and Phase 10 (Close Milestone Gaps) were INSERTED during execution.

### Decisions Made

#### v2.1 (new)

- **Phase numbering continues global sequence (D1)** — v2.1 starts at Phase 6, not Phase 1. No reset. The global phase counter is now at 10 (v2.1 will end at Phase 10).
- **Migration 0012 folded into Phase 7 (D2)** — `invite_redemptions` table + `profiles.prev_sync_item_count` column are delivered as part of the AUTH-02 + API-04 feature phase, not a standalone schema-only phase (MVP mode: every phase must be user-observable).
- **DATA-01 + DEV-05 are Phase 6 (D3)** — non-negotiable ordering constraint from research. `write_boundary` cross-profile corruption is a latent data-integrity hazard; kiosk SSE missing `device_revoked`/`device_reassigned` handlers block offline terminal-revoke. Both are pure code changes (no migration).
- **SRCH-09 ships with PRIV-01..04 in Phase 8 (D4)** — they share `sessionStorage` semantics and the "Reset kiosk" button; the reset action must clear the recently-pulled list atomically.
- **DEV-04 ships with privacy cluster in Phase 8 (D5)** — QR pairing is frontend-only and independent; grouping with the kiosk UX hardening phase avoids a single-requirement phase.
- **OFF-01..04 are Phase 9 (D6)** — offline UX depends on Phase 6's SSE consumer fixes (DEV-05 terminal-revoke path) and is naturally its own end-to-end user-observable capability.
- **UX-01 is Phase 10 (D7)** — shelf fill-overview depends on Phase 6's `write_boundary` fix (fill data must be profile-scoped correctly before visualization); serves as milestone-closing polish phase.
- **TanStack Query `networkMode: 'always'` (D8)** — PITFALLS reasoning overrides STACK recommendation; prevents thundering-herd reconnect storm (Pitfall 36). Confirmed as the correct configuration for this SSE-driven app.

#### v2.0 (carried from refined spec + roadmapper)

- **Sequential cross-repo coordination (R1)** — discogsography v2 ships completely before GRUVAX P1 starts. No stubs, no contract drift.
- **discogsography work is EXTERNAL (R2)** — tracked in `.planning/intel/context.md` as DGS-EXT-01..05; not part of GRUVAX's REQUIREMENTS.md.
- **Owner-managed PAT only for v2.0 (R3)** — self-connect → v2.1; OAuth2 device-grant → v2.2.
- **RPi pairing flow A — 4-digit code on kiosk (R4)** — reuses v1 in-app numeric keypad. QR/scan deferred to v2.1.
- **Sync triggers (R5)** — on connect / manual "Sync now" / nightly background at 03:00 local (configurable 24h / 12h / 6h / off).
- **Sessions and devices are independent (R6)** — browser sessions pick a profile via picker; RPi kiosks bind via pairing flow.
- **Open profile picker on LAN — no PIN for read-only browsing (R7)** — PIN still gates admin actions.
- **9 SPIDR-deferred v1 reqs stay deferred (R8)** — SRCH-09, OFF-01..04, PRIV-01..04 → v2.1 resilience + privacy milestone.
- **Walking-skeleton-first phase ordering (R9)** — vertical MVP slicing carries from v1.0.
- **Reset phase numbering to P1–P4 (R10)** — v2.0 used its own namespace; v2.1 continues the global sequence from 6.
- **PROF-02 not split** — Profile manager admin UI maps to P2 (CRUD + status badges); P4 polish ("Sync now" progress + 401 re-auth badge + per-profile diagnostics cards) is covered by SYN-01 + SYN-02 in P4 without splitting PROF-02 into a second REQ row.

#### v1.0 (carried for project-wide context)

- **Vertical MVP slicing** — every phase delivers an end-to-end user-observable capability. No horizontal infrastructure-only phases.
- **Parser + comparator (POS-01) is shared infrastructure** — implemented in Phase 1, reused by boundary-save validator (Phase 3), every algorithm (Phase 2), every test. Strategy C token-stream split.
- **`gruvax.v_collection` view + read-only grant** is the only contact surface with discogsography in v1.0 (DEP-02 + Pitfall 5). **Retired in v2.0 P1.**
- **Estimator contract locked in Phase 1** — `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}`. v1.0 Phase 5 swapped in the segment-aware estimator behind this contract.
- **Boundary cache + SSE invalidation** — cache loads at startup (Phase 1), invalidates on `boundary_changed` events (Phase 4 wires SSE). v2.0 P2 fans this out per-profile.
- **In-app numeric keypad** mitigates labwc/squeekboard #2926 (Pitfall 4) — built in v1.0 Phase 3; v2.0 P3 reuses it for the 4-digit pairing code admin entry.
- **MVP boundary seed via fixture** — Phase 1 uses a committed CSV/YAML fixture (no PII).
- **Stack pinned** — Python 3.13, FastAPI 0.136.x, psycopg 3.2 async, SQLAlchemy 2.0 async, Alembic 1.18.x, sse-starlette 2.x, aiomqtt 3.x, eclipse-mosquitto:latest, React 19 + Vite 8 + Tailwind + GSAP + Framer Motion, Raspberry Pi OS Trixie + labwc + Chromium kiosk. v2.1 adds `react-qr-code` 2.0.21 (frontend only).
- **search_path set via connect event listener** (not execute-before-configure) — prevents Alembic autobegin bug.
- **alembic_version in public schema** (version_table_schema="public") — prevents DROP SCHEMA gruvax cascade from deleting version row.
- **psycopg_pool configure callback** must leave connection in IDLE state.
- **Strategy C token-stream parser for POS-01** — zero dependency, fully explicit, all stages testable with Hypothesis.
- **`pytest-asyncio loop_scope="session"`** for DB tests — session-scoped db_pool fixture requires test to use same event loop.
- **publish_all_off retained-clear mechanism** — publishes `b''` with `retain=True`; idempotent by MQTT spec.
- **Endpoint tests use `dependency_overrides`, not `patch`** — FastAPI resolves `Depends(require_admin)` by function reference at route registration.
- **Closure phase pattern (v1.0 Phase 10)** — when an audit surfaces cross-phase seams that no single per-phase verification can catch, absorb them in a single closure phase rather than retrofitting earlier phases.

### Open Questions (v2.1 — resolve at plan time)

- **QR HTTP vs HTTPS (Pitfall 39):** Must decide before DEV-04 implementation (Phase 8). Research recommends Option A: HTTP + 60-second nonce rotation + single-use + documented as a Key Decision.
- **Invite-redeem TLS posture:** POST sends member PAT in plaintext over HTTP on home LAN. Acceptable for home LAN; document in runbook. Required if ever exposed beyond home LAN.
- **`first_seen_at` vs `arrived_at` column name:** For `profiles.prev_sync_item_count` companion (if a per-row timestamp ever added). Current v2.1 uses scalar `prev_sync_item_count` only — decide if/when per-row timestamps needed.
- **Discogsography test double in CI:** AUTH-02 PAT validation calls discogsography's collection API. VCR cassette or mock HTTP client must be in place before Phase 7 CI can run without network access.

### Open Questions (v2.0 — resolved; confirm at deploy time)

- **Fingerprint cookie persistence across RPi reboot** — RESOLVED: confirmed via Phase 3 Playwright reboot-persistence test + hardware UAT 2026-05-30.
- **Catalog# exposure / `user_id` envelope location / API rate limits** — modeled in the fake-discogsography contract fixture GRUVAX built against; re-verify against the real discogsography artifact (`docs/specs/v2-gruvax-integration.md`) when wiring the live API at deploy time.
- **Cookie storage on iOS Safari** (browser session profile-picker path) — same-site only (all traffic to `gruvax.lan`); spot-check on real hardware.

### Blockers

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260530-j7t | Style unstyled LED-action buttons (ALL OFF / RUN DIAGNOSTIC) — add missing `.settings-btn-secondary` CSS rule (surfaced in Phase 3 UAT) | 2026-05-30 | c9bd90e | [260530-j7t-style-unstyled-led-action-buttons-add-se](./quick/260530-j7t-style-unstyled-led-action-buttons-add-se/) |
| 260526-d6s | fix WR-04: contiguity error should render original-cased label, not casefolded (doc-only — fix already on main in 3598c22) | 2026-05-26 | aee5967 | [260526-d6s-fix-wr-04-contiguity-error-should-render](./quick/260526-d6s-fix-wr-04-contiguity-error-should-render/) |
| 260524-sd6 | Reconcile gruvax vs gruvax_app Postgres role naming (canonical: gruvax) | 2026-05-25 | 250f7b9 | [260524-sd6-reconcile-gruvax-vs-gruvax-app-postgres-](./quick/260524-sd6-reconcile-gruvax-vs-gruvax-app-postgres-/) |
| 260522-u48 | Rename docker compose service gruvax-api → api (container gruvax-api-1) | 2026-05-23 | b753bd2 | [260522-u48-rename-docker-compose-service-gruvax-api](./quick/260522-u48-rename-docker-compose-service-gruvax-api/) |
| 260522-mwy | Fix Docker venv shebangs so console scripts (gruvax-set-pin) run directly | 2026-05-22 | 1695cd5 | [260522-mwy-fix-docker-cli-shebangs](./quick/260522-mwy-fix-docker-cli-shebangs/) |
| 260521-jb3 | Replace eslint set-state-in-effect suppressions with real refactors in admin UI | 2026-05-21 | 9c26bbf | [260521-jb3-replace-eslint-set-state-in-effect-suppr](./quick/260521-jb3-replace-eslint-set-state-in-effect-suppr/) |
| 260521-g3o | Fix all 8 eslint errors in the frontend admin UI | 2026-05-21 | b093e9f | [260521-g3o-fix-all-8-eslint-errors-in-the-frontend-](./quick/260521-g3o-fix-all-8-eslint-errors-in-the-frontend-/) |
| 260521-fn0 | Fix all 8 findings from the Phase 3 UI audit in the frontend admin UI | 2026-05-21 | b47c097 | [260521-fn0-fix-all-8-findings-from-the-phase-3-ui-a](./quick/260521-fn0-fix-all-8-findings-from-the-phase-3-ui-a/) |
| 260519-p8t | Add design-language assets and rewrite README in discogsography pattern | 2026-05-20 | b786b47 | [260519-p8t-add-design-language-assets-and-rewrite-r](./quick/260519-p8t-add-design-language-assets-and-rewrite-r/) |
| fast | Add `*.swp` (Vim swap files) to .gitignore | 2026-05-19 | 23d94d3 | — (fast, inline) |

## Session Continuity

**Last activity:** 2026-05-31
**Prev:** 2026-05-30 — v2.0 milestone closed and archived (5 phases, 35 plans; tag v2.0). ROADMAP/REQUIREMENTS/audit archived to `milestones/v2.0-*`; REQUIREMENTS.md removed (fresh for next milestone); PROJECT.md evolved; RETROSPECTIVE.md updated.
**Prev2:** 2026-05-30 — Phase 5 closure complete — B-01 + B-02 wired; milestone re-audit `gaps_found` → `tech_debt`.
**Next action:** `/gsd:plan-phase 6`

---
*State initialized: 2026-05-19 with roadmap creation. v2.0 milestone reset: 2026-05-26. v2.1 roadmap: 2026-05-30.*

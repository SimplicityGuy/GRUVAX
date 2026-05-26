---
gsd_state_version: 1.0
milestone: v2.0
milestone_name: Multi-User Collections
status: planning
last_updated: "2026-05-26T22:30:00.000Z"
last_activity: 2026-05-26
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# State: GRUVAX

**Initialized:** 2026-05-19

## Project Reference

**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

**Current Focus:** Phase 1 — Walking skeleton (waiting on DGS-PREREQ)

**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

**Granularity:** standard (4 phases planned; ~17 plans across P1–P4 per the refined spec's estimate)

## Current Position

Phase: Phase 1 — Walking skeleton — API client + single-profile sync
Plan: —
Status: Not started (waiting on DGS-PREREQ — discogsography v2 contract artifact at `docs/specs/v2-gruvax-integration.md`)
Last activity: 2026-05-26 — v2.0 roadmap created; phase numbering RESET via `--reset-phase-numbers`

## Performance Metrics (v2.0)

| Metric | Value |
|--------|-------|
| v2.0 active requirements | 12 |
| Requirements mapped to phases | 12 / 12 (100%) |
| Deferred (not in P1–P4) | 1 (AUTH-01 → v2.2) |
| External prereqs (discogsography) | 5 (DGS-EXT-01..05) |
| Phases planned | 4 |
| Plans complete | 0 |
| Phases shipped | 0 |

### Historical (v1.0, shipped 2026-05-26)

| Metric | Value |
|--------|-------|
| v1.0 in-scope requirements | 84 |
| v1.0 requirements satisfied | 75 / 75 in-scope (9 SPIDR-relocated to v2/Backlog) |
| v1.0 phases shipped | 10 / 10 |
| v1.0 plans completed | 50 |

## Accumulated Context

### Pending Todos

- [ ] DGS-PREREQ closes (external — discogsography v2 ships `app_tokens` + catalog# exposure + contract artifact)
- [ ] User approves v2.0 ROADMAP.md (P1–P4)
- [ ] Once DGS-PREREQ closes: read `docs/specs/v2-gruvax-integration.md` from discogsography repo; reconcile any contract drift; run `/gsd-discuss-phase 1`

### Roadmap Evolution

- **2026-05-26** — v2.0 milestone created. Phase numbering RESET via `--reset-phase-numbers`. 4 phases (P1: walking skeleton; P2: multi-profile; P3: devices + pairing; P4: sync polish + diagnostics). 12 active reqs mapped 100% across P1–P4. AUTH-01 deferred to v2.2.
- **2026-05-26** — v1.0 archived. 10 phases, 50 plans, ~36k LOC. Phase 5 (Segment-Aware Position Precision) and Phase 10 (Close Milestone Gaps) were INSERTED during execution; both shipped clean. See `.planning/milestones/v1.0-ROADMAP.md` for the full archive.
- Phase 5 inserted after Phase 4 (v1.0): Segment-Aware Position Precision — true integer insert; bumped LED→6, Wizards→7, Observability→8.
- Phase 10 added (integer append) at end of v1.0: Close Milestone Gaps — INT-A SSE payload shape + INT-B undo re-derive/publish + traceability reconcile.

### Decisions Made

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
- **Reset phase numbering to P1–P4 (R10)** — each milestone gets its own phase namespace.
- **PROF-02 not split** — Profile manager admin UI maps to P2 (CRUD + status badges); P4 polish ("Sync now" progress + 401 re-auth badge + per-profile diagnostics cards) is covered by SYN-01 + SYN-02 in P4 without splitting PROF-02 into a second REQ row.

#### v1.0 (carried for project-wide context)

- **Vertical MVP slicing** — every phase delivers an end-to-end user-observable capability. No horizontal infrastructure-only phases.
- **Parser + comparator (POS-01) is shared infrastructure** — implemented in Phase 1, reused by boundary-save validator (Phase 3), every algorithm (Phase 2), every test. Strategy C token-stream split.
- **`gruvax.v_collection` view + read-only grant** is the only contact surface with discogsography in v1.0 (DEP-02 + Pitfall 5). **Retired in v2.0 P1.**
- **Estimator contract locked in Phase 1** — `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}`. v1.0 Phase 5 swapped in the segment-aware estimator behind this contract.
- **Boundary cache + SSE invalidation** — cache loads at startup (Phase 1), invalidates on `boundary_changed` events (Phase 4 wires SSE). v2.0 P2 fans this out per-profile.
- **In-app numeric keypad** mitigates labwc/squeekboard #2926 (Pitfall 4) — built in v1.0 Phase 3; v2.0 P3 reuses it for the 4-digit pairing code admin entry.
- **MVP boundary seed via fixture** — Phase 1 uses a committed CSV/YAML fixture (no PII).
- **Stack pinned** — Python 3.13, FastAPI 0.136.x, psycopg 3.2 async, SQLAlchemy 2.0 async, Alembic 1.18.x, sse-starlette 2.x, aiomqtt 3.x, eclipse-mosquitto:latest, React 19 + Vite 8 + Tailwind + GSAP + Framer Motion, Raspberry Pi OS Trixie + labwc + Chromium kiosk.
- **search_path set via connect event listener** (not execute-before-configure) — prevents Alembic autobegin bug.
- **alembic_version in public schema** (version_table_schema="public") — prevents DROP SCHEMA gruvax cascade from deleting version row.
- **psycopg_pool configure callback** must leave connection in IDLE state.
- **Strategy C token-stream parser for POS-01** — zero dependency, fully explicit, all stages testable with Hypothesis.
- **`pytest-asyncio loop_scope="session"`** for DB tests — session-scoped db_pool fixture requires test to use same event loop.
- **publish_all_off retained-clear mechanism** — publishes `b''` with `retain=True`; idempotent by MQTT spec.
- **Endpoint tests use `dependency_overrides`, not `patch`** — FastAPI resolves `Depends(require_admin)` by function reference at route registration.
- **Closure phase pattern (v1.0 Phase 10)** — when an audit surfaces cross-phase seams that no single per-phase verification can catch, absorb them in a single closure phase rather than retrofitting earlier phases.

### Open Questions

To be resolved during plan-phase or as the discogsography agent reports:

- **Catalog# exposure outcome (HIGH risk)** — discogsography agent's verification spike determines whether their P1 is small (already exposed) or larger (missing column + Discogs ingestion update). User to be informed when known.
- **`user_id` location in the discogsography collection envelope** — header or top-level field; TBD by discogsography agent; surfaces in their `docs/specs/v2-gruvax-integration.md` artifact.
- **Fingerprint cookie persistence across RPi reboot** — Chromium with `--user-data-dir` on persistent storage should preserve cookies. Verify during P3 implementation.
- **Cookie storage on iOS Safari** (browser session profile-picker path) — Safari restricts cross-site cookies. Same-site is fine since all traffic is to `gruvax.lan`; verify nonetheless.
- **Discogsography API rate limits in practice** — full sync of 3,000 items at `per_page=200` = 15 requests; manual "Sync all profiles now" hitting 4 profiles back-to-back ~ 60 requests in <1 min. Check against the rate-limit policy in the contract artifact.

### Active Todos

- [ ] DGS-PREREQ ships (external)
- [ ] User approves v2.0 ROADMAP.md
- [ ] Run `/gsd-discuss-phase 1` once DGS-PREREQ closes

### Blockers

**DGS-PREREQ (external)** — GRUVAX P1 cannot start until discogsography ships the contract artifact at `docs/specs/v2-gruvax-integration.md`. Briefed at `background/discogsography-v2-app-tokens-brief.md` (gitignored). The discogsography agent session is in flight.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
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

**Last activity:** 2026-05-26
**Prev:** 2026-05-26 (v1.0 milestone archived: Phases 1–10, 50 plans, 10 days, ~36k LOC. 9 SPIDR-deferred reqs relocated to v2/Backlog. v2.0 milestone created via `/gsd-new-milestone v2.0 --reset-phase-numbers`. ROADMAP/REQUIREMENTS/STATE rewritten for v2.0 P1–P4 with 12 active reqs mapped 100%; AUTH-01 deferred to v2.2.)
**Prev2:** 2026-05-25 (Phase 10 Plan 03 COMPLETE — traceability/count reconcile (docs-only). v1.0 internal consistency achieved: 84 total = 75 satisfied + 9 deferred.)
**Next action:** Wait for DGS-PREREQ closure (discogsography v2 ships `docs/specs/v2-gruvax-integration.md` in their repo). Once that lands, read the artifact, reconcile contract drift against the refined spec, then run `/gsd-discuss-phase 1`.

---
*State initialized: 2026-05-19 with roadmap creation. v2.0 milestone reset: 2026-05-26.*

## Operator Next Steps

- Wait for DGS-PREREQ closure (discogsography v2 in flight)
- Once DGS-PREREQ closes: read the contract artifact, reconcile drift, run `/gsd-discuss-phase 1`

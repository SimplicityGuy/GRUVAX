---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
last_updated: "2026-05-20T05:20:00.000Z"
progress:
  total_phases: 7
  completed_phases: 0
  total_plans: 4
  completed_plans: 3
  percent: 75
---

# State: GRUVAX

**Initialized:** 2026-05-19

## Project Reference

**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

**Current Focus:** Phase 01 — first-search-cube-highlight

**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

**Granularity:** standard (7 phases, 3–5 plans each expected)

## Current Position

Phase: 01 (first-search-cube-highlight) — EXECUTING
Plan: 3 of 4

- **Phase:** 1 — First Search → Cube Highlight
- **Plan:** 01-03 complete; 01-04 next
- **Status:** Executing Phase 01
- **Progress:** [███████░░░] 75%

```
Phase 1: First Search → Cube Highlight              [ ] Not started — NEXT
Phase 2: Real Position Estimation                   [ ] Not started
Phase 3: Admin Loop (PIN + Manual Entry + Undo)     [ ] Not started
Phase 4: Realtime + Offline Resilience              [ ] Not started
Phase 5: LED Contract over MQTT (Hardware Stubbed)  [ ] Not started
Phase 6: Wizards + Import/Export                    [ ] Not started
Phase 7: Observability + Deployment Hardening       [ ] Not started
```

## Performance Metrics

| Metric | Value |
|--------|-------|
| v1 requirements | 73 |
| Requirements mapped to phases | 73 (100%) |
| Phases planned | 0 / 7 |
| Plans complete | 0 |
| Phases shipped | 0 |
| Phase 01-first-search-cube-highlight P02 | 1109 | 2 tasks | 8 files |
| Phase 01-first-search-cube-highlight P03 | 1200 | 3 tasks | 15 files |

## Accumulated Context

### Decisions Made (from PROJECT.md + research)

- **Vertical MVP slicing** — every phase delivers an end-to-end user-observable capability. No horizontal infrastructure-only phases.
- **Parser + comparator (POS-01) is shared infrastructure** — implemented in Phase 1, reused by boundary-save validator (Phase 3), every algorithm (Phase 2), every test. Strategy C (token-stream split) or D (`natsort`) — pick during Phase 1 planning.
- **`gruvax.v_collection` view + read-only grant** is the only contact surface with discogsography (DEP-02 + Pitfall 5). Established in Phase 1; probed at startup.
- **Estimator contract locked in Phase 1** — `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}`. v1 Phase 1 ships cube-only fallback (INTERPOLATION §4.8); Phase 2 swaps in §4.1 index-based estimator behind the same contract.
- **Boundary cache + SSE invalidation** — cache loads at startup (Phase 1), invalidates on `boundary_changed` events (Phase 4 wires SSE).
- **In-app numeric keypad** mitigates labwc/squeekboard #2926 (Pitfall 4) — built in Phase 3, no dependency on system on-screen keyboard.
- **MVP boundary seed via fixture** — Phase 1 uses a committed CSV/YAML fixture (no PII) so the search→highlight slice is demoable before any admin UI exists. Admin tooling lands in Phase 3; wizards in Phase 6.
- **Stack pinned** (research/STACK.md, HIGH confidence): Python 3.13, FastAPI 0.136.x, psycopg 3.2 async, SQLAlchemy 2.0 async, Alembic 1.18.x, sse-starlette 2.x, aiomqtt 3.x, eclipse-mosquitto:2.1-alpine, React 19 + Vite 7 + Tailwind + GSAP + Framer Motion, Raspberry Pi OS Trixie + labwc + Chromium kiosk.
- **search_path set via connect event listener** (not execute-before-configure) — prevents Alembic autobegin bug where _in_external_transaction=True causes no COMMIT. Documented in 01-01-SUMMARY.md.
- **alembic_version in public schema** (version_table_schema="public") — prevents DROP SCHEMA gruvax cascade from deleting version row before Alembic bookkeeping runs.
- **psycopg_pool configure callback** must leave connection in IDLE state — use set_autocommit(True/False) around any execute() calls.
- [Phase 01-02]: **D-13 resolved: Strategy C token-stream parser for POS-01** — zero dependency, fully explicit, all stages testable with Hypothesis; no raw string comparisons in estimator.
- [Phase 01-02]: **BoundaryCache._load_rows() testing seam** — added to allow unit testing without live DB; undocumented in RESEARCH but required for proper TDD RED phase isolation.
- [Phase 01-02]: **NFC after separator collapse in normalize_catalog** — Hypothesis found combining-char idempotency edge case; NFC stabilizes canonical combining-char order after separator stripping.
- [Phase 01-02]: **pytest-asyncio loop_scope="session" for DB tests** — session-scoped db_pool fixture requires test to use same event loop; use `@pytest.mark.asyncio(loop_scope="session")` pattern for all future integration tests that use db_pool.
- [Phase 01-03]: **Circular import prevention** — dependency providers (get_pool, get_boundary_cache) live in api/deps.py; routers imported inside create_app() body, not at module level.
- [Phase 01-03]: **psycopg placeholder syntax** — psycopg uses `%s` (Python DB-API 2.0), not `$1`/`$2` (PostgreSQL server-side syntax). Affects all SQL in queries.py.
- [Phase 01-03]: **asgi-lifespan as production dependency** — LifespanManager correctly triggers FastAPI's lifespan context in async test fixtures; added as prod dep to avoid conditional import issues.
- [Phase 01-03]: **test_no_boundary uses release_id=111** — Saturn label records have no boundary coverage because boundary (first_label=Saturn, last_label=ESP) has "saturn" > "esp" alphabetically, so label range check fails.
- [Phase 01-03]: **MQTT aiomqtt stub** — uses client.__aenter__()/__aexit__() directly instead of `async with` to retain client reference in app.state.mqtt after context manager enters.

### Open Questions (carried from research/SUMMARY.md §Open Questions)

To be resolved during plan-phase or as the user provides input:

- **Service-worker cached search results** — v1 or v1.x? (Pure offline read-cache, ~1 day of work)
- **Per-visitor PIN** — v1 or v2? (Schema supports it; UX call)
- **YAML or JSON** for boundary import/export? — Recommend YAML (Phase 6)
- **PIN hash location** — env var or `gruvax.settings`? — Recommend DB-seeded via bootstrap CLI (Phase 3)
- **Position-estimator algorithm beyond §4.1** — empirically determined via A/B harness against owner's hand-curated boundaries (revisit after Phase 6 reshuffle landing)
- **INTERPOLATION §8.1 owner-input questions** — density vs uniform shelving, multi-prefix grouping, multi-value catalog handling, multi-label handling, confidence threshold for sub-cube vs cube-only — surfaced during Phase 3 admin sign-off and Phase 6 wizard inspection

### Active Todos

- [ ] User approves ROADMAP.md
- [ ] Run `/gsd:plan-phase 1` to decompose Phase 1 into plans

### Blockers

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260519-p8t | Add design-language assets and rewrite README in discogsography pattern | 2026-05-20 | b786b47 | [260519-p8t-add-design-language-assets-and-rewrite-r](./quick/260519-p8t-add-design-language-assets-and-rewrite-r/) |
| fast | Add `*.swp` (Vim swap files) to .gitignore | 2026-05-19 | 23d94d3 | — (fast, inline) |

## Session Continuity

**Last touched:** 2026-05-20 (Phase 01 Plan 03 complete — FastAPI backend API: search, locate, units/cubes, health)
**Next action:** Execute Phase 01 Plan 04 (`/gsd:execute-phase 01 04`).

---
*State initialized: 2026-05-19 with roadmap creation*

# State: GRUVAX

**Initialized:** 2026-05-19

## Project Reference

**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

**Current Focus:** Phase 1 — First Search → Cube Highlight. Deliver the smallest vertical slice that exercises Core Value end-to-end against fixture-seeded boundaries.

**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

**Granularity:** standard (7 phases, 3–5 plans each expected)

## Current Position

- **Phase:** 1 — First Search → Cube Highlight
- **Plan:** Not yet planned (run `/gsd:plan-phase 1`)
- **Status:** Not started
- **Progress:** ░░░░░░░ 0/7 phases complete

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

## Session Continuity

**Last touched:** 2026-05-19 (roadmap creation)
**Next action:** User approves the roadmap, then `/gsd:plan-phase 1`.

---
*State initialized: 2026-05-19 with roadmap creation*

---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: ready_to_plan
last_updated: 2026-05-25T20:14:12.452Z
progress:
  total_phases: 11
  completed_phases: 7
  total_plans: 48
  completed_plans: 49
  percent: 64
stopped_at: Phase 09 complete (8/6) — ready to discuss Phase 999.1
---

# State: GRUVAX

**Initialized:** 2026-05-19

## Project Reference

**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

**Current Focus:** Phase 999.1 — shelf overview mini kallax shows per cube fill/occupancy (backlog)

**Mode:** mvp (vertical slices — every phase delivers an end-to-end user-observable capability)

**Granularity:** standard (8 phases, 3–5 plans each expected)

## Current Position

Phase: 09 (tooling-and-docs-hardening) — EXECUTING
Plan: 1 of 6

- **Phase:** 999.1
- **Plan:** Not started
- **Status:** Ready to plan
- **Progress:** [██████████] 100%

```
Phase 1: First Search → Cube Highlight              [ ] Not started — NEXT
Phase 2: Real Position Estimation                   [ ] Not started
Phase 3: Admin Loop (PIN + Manual Entry + Undo)     [ ] Not started
Phase 4: Realtime + Offline Resilience              [ ] Not started
Phase 5: Segment-Aware Position Precision           [ ] Not started
Phase 6: LED Contract over MQTT (Hardware Stubbed)  [ ] Not started
Phase 7: Wizards + Import/Export                    [ ] Not started
Phase 8: Observability + Deployment Hardening       [ ] Not started
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
| Phase 01-first-search-cube-highlight P04 | 1303 | 3 tasks | 22 files |
| Phase 02-real-position-estimation P01 | 19 | 4 tasks | 15 files |
| Phase 02-real-position-estimation P02 | 14 | 3 tasks | 9 files |
| Phase 02-real-position-estimation P04 | 5min | 2 tasks | 3 files |
| Phase 06 P04 | 9min | 3 tasks | 6 files |

## Accumulated Context

### Pending Todos

None. (Reconcile gruvax/gruvax_app role naming → completed as quick task 260524-sd6.)

### Roadmap Evolution

- Phase 5 inserted after Phase 4: Segment-Aware Position Precision — true integer insert; bumped LED→6, Wizards→7, Observability→8

### Decisions Made (from PROJECT.md + research)

- **Vertical MVP slicing** — every phase delivers an end-to-end user-observable capability. No horizontal infrastructure-only phases.
- **Parser + comparator (POS-01) is shared infrastructure** — implemented in Phase 1, reused by boundary-save validator (Phase 3), every algorithm (Phase 2), every test. Strategy C (token-stream split) or D (`natsort`) — pick during Phase 1 planning.
- **`gruvax.v_collection` view + read-only grant** is the only contact surface with discogsography (DEP-02 + Pitfall 5). Established in Phase 1; probed at startup.
- **Estimator contract locked in Phase 1** — `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}`. v1 Phase 1 ships cube-only fallback (INTERPOLATION §4.8); Phase 2 swaps in §4.1 index-based estimator behind the same contract.
- **Boundary cache + SSE invalidation** — cache loads at startup (Phase 1), invalidates on `boundary_changed` events (Phase 4 wires SSE).
- **In-app numeric keypad** mitigates labwc/squeekboard #2926 (Pitfall 4) — built in Phase 3, no dependency on system on-screen keyboard.
- **MVP boundary seed via fixture** — Phase 1 uses a committed CSV/YAML fixture (no PII) so the search→highlight slice is demoable before any admin UI exists. Admin tooling lands in Phase 3; wizards in Phase 7.
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
- [Phase 01-04]: **Vite 8 (not 7)** — npm latest is 8.0.x; CLAUDE.md/STACK.md pins treated as stale per environment directive; RESEARCH.md confirmed 8.x.
- [Phase 01-04]: **eclipse-mosquitto:latest** — plan said 2.1-alpine; environment directive says use latest image tag.
- [Phase 01-04]: **python -m pattern in docker-entrypoint.sh** — uv copies venv from /build/.venv to /app/.venv; wrapper scripts have hardcoded shebangs (#!/build/.venv/bin/python) so direct invocation fails. Using `$PYTHON -m alembic` and `$PYTHON -m uvicorn` with absolute binary path avoids shebang issue entirely.
- [Phase 01-04]: **Design tokens via relative path** — `../../design/gruvax-design-tokens.css` in frontend/src/main.tsx resolves locally; Docker stage copies design/ to /design/ (one level above /frontend-build workdir) so same relative path resolves in build.
- [Phase 01-04]: **TanStack Query for /api/locate fires imperatively** — not as a hook key, to ensure each result selection triggers a fresh locate call without stale cube position caching.
- [Phase 02-01]: **D-02 singleton override** — singletons return SubInterval(start=0.0, end=1.0) full-cube band at confidence 0.30, not a tick-mark. Overrides CUBE-10 literal wording per owner decision documented in algorithm.py.
- [Phase 02-01]: **sub_cube_interval JSON contract** — emits {start, end, crosses_boundary, next_cube}; NO cube field. Frontend derives cube from primary_cube/label_span context (UI-SPEC §TypeScript Type Extension).
- [Phase 02-01]: **locate() dispatcher** — no-snapshot → cube-only-v1; confidence<=CUBE_ONLY_CONFIDENCE → sub_cube_interval=None, cube-only-v1; else §4.1 index-v1 with populated sub_cube_interval.
- [Phase 02-01]: **pythonpath=[.] strategy** — pyproject.toml + fixtures/__init__.py + root conftest.py; single source of truth for importable repo-root packages; consistent with Plan 02-04 scripts/ imports.
- [Phase 02-02]: **DID_YOU_MEAN_THRESHOLD = 0.35** — conservative per RESEARCH D-11; did_you_mean fires only when rows is empty; avoids spurious suggestions on partial FTS hits.
- [Phase 02-02]: **Catalog boost via setweight() Option A** — catalog_number tokens weighted 'A', fts_vector tokens 'C'; ts_rank_cd scores 'A' highest; catalog records rank above text matches for catalog-like queries (D-12).
- [Phase 02-02]: **onTap calls setQuery (not direct locate)** — D-10 explicit user confirmation; no silent auto-correct; user sees corrected term in search box.
- [Phase 02-04]: **CUBE_ONLY_NULL_MIDPOINT=0.5** — §4.8 null sub_cube_interval scored as midpoint of cube for MAE comparison; worst-case analysis per plan spec.
- [Phase 02-04]: **session-scoped harness_results fixture** — run_all_algorithms(ci=True) called once per pytest session; all CI tests consume shared per-shape {index, cube_only} dict.
- [Phase 06-04]: **publish_all_off retained-clear mechanism** — publishes `b''` with `retain=True` to delete retained messages (MQTT protocol; Mosquitto expiry-cleanup is unreliable, D-11). The all-off clear is idempotent by MQTT spec.
- [Phase 06-04]: **Endpoint tests use dependency_overrides, not patch** — FastAPI resolves `Depends(require_admin)` by function reference at route registration; patching the module-level name does not intercept the dependency. Use `app.dependency_overrides[require_admin] = stub` (canonical pattern from test_admin_led_settings.py).
- [Phase 06-04]: **run_diagnostic uses asyncio.timeout(5.0)** — pure stdlib (Python 3.11+), no new deps; 5-second window for status/# subscribe covers firmware boot latency in v1 (D-10).
- [Phase 05-01]: **BoundaryRow contract change under-scoped at plan time** — dropping `last_label`/`last_catalog` (migration 0005) ripples through more consumers than 05-02..05-05 covered. Post-merge gate caught ~40 RED tests + 12 mypy errors. 05-01's work is correct and merged; Waves 2–5 are being re-planned to add orphan coverage (`api/units.py`, `db/seed_boundaries.py`, `db/queries.py`, `boundary_cache.py:100`, ~11 test files). **Lesson:** plans that change a shared dataclass/DDL contract must include an explicit consumer-sweep (grep audit) covering every construction/SQL/test site, and each wave must leave the suite green. Full inventory: `05-REPLAN-NOTES.md`.

### Open Questions (carried from research/SUMMARY.md §Open Questions)

To be resolved during plan-phase or as the user provides input:

- **Service-worker cached search results** — v1 or v1.x? (Pure offline read-cache, ~1 day of work)
- **Per-visitor PIN** — v1 or v2? (Schema supports it; UX call)
- **YAML or JSON** for boundary import/export? — Recommend YAML (Phase 7)
- **PIN hash location** — env var or `gruvax.settings`? — Recommend DB-seeded via bootstrap CLI (Phase 3)
- **Position-estimator algorithm beyond §4.1** — now scoped as Phase 5 (Segment-Aware Position Precision); empirically determined via the extended A/B harness against owner's hand-curated boundaries
- **INTERPOLATION §8.1 owner-input questions** — density vs uniform shelving, multi-prefix grouping, multi-value catalog handling, multi-label handling, confidence threshold for sub-cube vs cube-only — surfaced during Phase 3 admin sign-off and Phase 7 wizard inspection (multi-label handling now central to Phase 5)

### Active Todos

- [ ] User approves ROADMAP.md
- [ ] Run `/gsd:plan-phase 1` to decompose Phase 1 into plans

### Blockers

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260524-sd6 | Reconcile gruvax vs gruvax_app Postgres role naming (canonical: gruvax) | 2026-05-25 | 250f7b9 | [260524-sd6-reconcile-gruvax-vs-gruvax-app-postgres-](./quick/260524-sd6-reconcile-gruvax-vs-gruvax-app-postgres-/) |
| 260522-u48 | Rename docker compose service gruvax-api → api (container gruvax-api-1) | 2026-05-23 | b753bd2 | [260522-u48-rename-docker-compose-service-gruvax-api](./quick/260522-u48-rename-docker-compose-service-gruvax-api/) |
| 260522-mwy | Fix Docker venv shebangs so console scripts (gruvax-set-pin) run directly | 2026-05-22 | 1695cd5 | [260522-mwy-fix-docker-cli-shebangs](./quick/260522-mwy-fix-docker-cli-shebangs/) |
| 260521-jb3 | Replace eslint set-state-in-effect suppressions with real refactors in admin UI | 2026-05-21 | 9c26bbf | [260521-jb3-replace-eslint-set-state-in-effect-suppr](./quick/260521-jb3-replace-eslint-set-state-in-effect-suppr/) |
| 260521-g3o | Fix all 8 eslint errors in the frontend admin UI | 2026-05-21 | b093e9f | [260521-g3o-fix-all-8-eslint-errors-in-the-frontend-](./quick/260521-g3o-fix-all-8-eslint-errors-in-the-frontend-/) |
| 260521-fn0 | Fix all 8 findings from the Phase 3 UI audit in the frontend admin UI | 2026-05-21 | b47c097 | [260521-fn0-fix-all-8-findings-from-the-phase-3-ui-a](./quick/260521-fn0-fix-all-8-findings-from-the-phase-3-ui-a/) |
| 260519-p8t | Add design-language assets and rewrite README in discogsography pattern | 2026-05-20 | b786b47 | [260519-p8t-add-design-language-assets-and-rewrite-r](./quick/260519-p8t-add-design-language-assets-and-rewrite-r/) |
| fast | Add `*.swp` (Vim swap files) to .gitignore | 2026-05-19 | 23d94d3 | — (fast, inline) |

## Session Continuity

**Last touched:** 2026-05-25 (Phase 07 COMPLETE — all 8 plans; gap-closure 07-06/07/08 done; 07-VERIFICATION.md status=passed 18/18; owner-approved human-verify UAT. FINALIZATION this session: (1) fixed pre-existing test-isolation debt — promoted the login rate-limiter reset to a global autouse fixture in tests/conftest.py + made the import/locate/migrate tests self-contained → backend suite is now ORDER-INDEPENDENT and green twice back-to-back, even on a UAT-mutated DB [a26252d]; (2) code review found + fixed 1 critical + 2 warnings [03fb309]: CR-01 reshuffle resume Math.min(…,0)→Math.max (always resumed at step 0), WR-01 settings-import explicit conn.transaction(), WR-02 export download appended-anchor + deferred revoke (Firefox/mobile-Safari); (3) reconciled 07-UAT.md + 07-HUMAN-UAT.md + PROJECT.md. `uv run pytest tests/` exits 0, mypy --strict clean, frontend tsc+build clean. Stack rebuilt (docker compose up -d --build api), dev PIN=0000.)
**Prev:** 2026-05-24 (Phase 06 Plan 04 complete — all-off/diagnostic admin vertical slice. 318 tests passing. Phase 06 4/4 plans complete — all LED contract plans done.)
**Prev2:** 2026-05-23 (Phase 05 FULLY VERIFIED — gap-closure 05-06 complete (6/6 plans) + all 6 UAT items pass. SEG-05 label-contiguity enforced on the LIVE admin write paths PUT /cut + POST /insert-cut (400 type=contiguity_error before any DB write) via build_proposed_cuts→validate_contiguity, surfaced in RecordPickerSheet (sheet stays open), orphaned /admin/preview + DiffPreviewSheet/RollbackToast removed. UAT test 6 RE-VERIFIED LIVE via Playwright on the rebuilt stack — the container image predated 05-06 so it was rebuilt (docker compose up -d --build api) and the dev DB was DROPPED + RE-SEEDED from fixtures (which also cleared the cut_insert pollution → test_migrate_0005 now passes → full backend suite exits 0). 05-VERIFICATION.md status=passed. Admin PIN re-seeded to 0000 after the DB drop.)
**Next action:** Phase 07 is COMPLETE across every gate (8/8 plans; 07-VERIFICATION.md passed 18/18; 07-REVIEW.md resolved). TWO non-blocking follow-ups remain: (1) ONE quick human re-verify — reshuffle resume-at-step after the CR-01 fix (07-HUMAN-UAT.md Test 1: start a reshuffle, complete ≥1 step, hard-reload, CONTINUE → should land on the SAVED step, not step 0); (2) optional `/gsd-secure-phase 7` (no 07-SECURITY.md yet; workflow.security_enforcement=true). Ready for Phase 8 (Observability + Deployment Hardening): `/clear` then `/gsd-discuss-phase 8` or `/gsd-plan-phase 8`.

---
*State initialized: 2026-05-19 with roadmap creation*

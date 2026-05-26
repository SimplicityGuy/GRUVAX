# Milestones

## v1.0 MVP — Shipped 2026-05-26

**Timeline:** 2026-05-17 → 2026-05-26 (10 days)
**Phases:** 10 (1, 2, 3, 4, 5, 6, 7, 8, 9, 10) — all complete
**Plans:** 50 plans, 52 SUMMARY.md files (9 had gap-closure follow-ups)
**Code:** ~36,346 LOC across `src/`, `frontend/src/`, `tests/` (Python 3.13 + TypeScript/React 19)
**Git range:** `0589e60` (Initial commit) → `827d7c3` (v1.0 close prep)
**Diff:** 493 files / +121,851 lines
**Quick tasks completed:** 8 (eslint cleanups, design assets, Docker fixes, role-name reconcile, WR-04 cosmetic)

### North-star outcome

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms.

Wired end-to-end and verified: kiosk search → `/api/locate` → segment-aware estimator → cube highlight + sub-cube bar + label-span underlay → MQTT fan-out consuming the segment-aware sub-span. The headline capability ships.

### Key accomplishments by phase

- **Phase 1 — First Search → Cube Highlight.** FastAPI app factory with psycopg async FTS + catalog-path search; locked `LocateResult` contract over `/api/locate`; configurable N×4×4 grid; `gruvax.v_collection` read-only view contract over discogsography; React 19 + Vite 8 kiosk SPA with debounced search, animated results, and ShelfGrid + LED-state Cubes; Docker Compose stack (api + mosquitto) serving the SPA via FastAPI StaticFiles.
- **Phase 2 — Real Position Estimation.** §4.1 index-based estimator with calibrated confidence; in-memory CollectionSnapshot for zero-DB compute (p95 0.04 ms — well within the 50 ms POS-03 budget); GSAP selection-lands choreography (span → pulse → bar, ≤600 ms, hard-cancellable); pg_trgm did-you-mean fallback; catalog-number boosting via `setweight()`; A/B harness (`run_all_algorithms.py`) proving §4.1 ≥ §4.8 across 4 synthetic planted-truth shapes.
- **Phase 3 — Admin Loop (PIN + Manual Entry + Undo).** Argon2id-hashed PIN auth, sliding-window session, in-app numeric keypad (mitigates labwc/squeekboard #2926); manual boundary entry with autocomplete + diff preview; append-only change-log with change-set undo/revert; mobile-first admin UI.
- **Phase 4 — Realtime Live Updates.** SSE stream invalidates `BoundaryCache` on `boundary_changed` events; kiosk re-renders affected cubes without manual refresh; concurrent search support; optimistic admin updates with rollback; RTM-04 "boundaries updating" indicator on the affected cube range.
- **Phase 5 — Segment-Aware Position Precision (INSERTED).** Replaced one-span-per-cube boundary model with cut-points + per-label width overrides; segment derivation via row-counting `v_collection` (never catalog arithmetic); two-level interpolation estimator supersedes §4.1; SEG-05 label-contiguity invariant enforced server-side AND in the UI (hard-block on scatter-inducing edits); segment editor with drag-to-redistribute, drift chip resync, and straddle fade caption.
- **Phase 6 — LED Contract over MQTT (Hardware Stubbed).** Pydantic-validated MQTT 5 payloads on `gruvax/v1/leds/...` to internal Mosquitto (no host-port exposure); admin tunes colors and brightness ceilings; all-off + diagnostic sweep + concurrency guard (CR-01..CR-04 closed); idle/ambient baseline with server-scheduled TTL revert and optional retain-mode trail (LED-11/12/13).
- **Phase 7 — Wizards + Import/Export.** Guided setup wizard + atomic reshuffle wizard + CSV/YAML import (dry-run preview → COMMIT IMPORT with change_set_id) + boundary + settings export; eight-source History badge map with REVERT THIS CHANGE SET.
- **Phase 8 — Observability + Deployment Hardening.** Enriched `/api/health` (per-subsystem reachability + git-SHA `/api/version` + `sync_age_seconds`); JSON-structured logs with env-driven level + in-memory ring; slow-query SLO log; `record_stats` aggregate-only counters (release_id only, no `query_text`); `/admin/diagnostics` page (5 cards, Nordic Grid typography, dark logs terminal); kiosk staleness banner at >14d; Compose log limits + healthchecks; GitHub Actions CI proving Alembic upgrade↔downgrade round-trip + p95 ≤200 ms `/api/search` / ≤50 ms `/api/locate` SLO gates on synthetic data.
- **Phase 9 — Tooling and Docs Hardening.** Migrated to structlog (preserving the Phase 8 log ring buffer); env-driven log level; GitHub Actions tooling adapted from discogsography (lint/type/test + cleanup-cache + cleanup-images); dependabot; pre-commit hooks; `update-project.sh`; Phase 1–8 docs refresh stripping `lux`/`nox` references.
- **Phase 10 — Close Milestone Gaps (INSERTED — audit-driven closure).** INT-A: renamed segment-edit SSE payload from `cubes`/`unit_id` to `cube_ids`/`unit` to match kiosk consumer; INT-B: wired SegmentCache re-derive + `boundary_changed` publish into `history.revert_change_set`; SEG-01..08 + CUBE-08 traceability flipped Pending→Complete; REQUIREMENTS.md/ROADMAP.md header count reconciled 81→84.

### Key decisions

| Decision | Outcome |
|----------|---------|
| Vertical MVP slicing (every phase end-to-end user-observable) | ✓ Good — kept us shippable at every checkpoint |
| `gruvax.v_collection` view as the single contact surface with discogsography | ✓ Good — survived dev/prod schema drift (`gruvax_dev` vs `discogsography`) without code changes |
| Strategy C token-stream parser for POS-01 (vs `natsort`) | ✓ Good — zero-dep, Hypothesis-friendly, no raw string compares |
| Cut-points + override model (Phase 5) supersedes §4.1 | ✓ Good — straddling labels resolve to the correct bin without special-casing; §4.1 retired |
| In-app numeric keypad (mitigates labwc/squeekboard #2926) | ✓ Good — no dependency on system on-screen keyboard |
| Internal-only MQTT (no Compose `ports:` exposure) | ✓ Good — matches Phase 6 "hardware-stubbed" framing |
| `aiomqtt` 3.x over `paho-mqtt`/`fastapi-mqtt` | ✓ Good — idiomatic asyncio, no thread bridge |
| Single PIN + Argon2id + Starlette `SessionMiddleware` (no `fastapi-users`) | ✓ Good — right size for a single-owner home-LAN app |
| Always-latest deps (Python 3.13, Vite 8, eclipse-mosquitto:latest, Postgres 18) | ✓ Good — clean dependency story; per user feedback memory |
| Worktree-isolated parallel executors for GSD execute-phase | ✓ Good — most of the time; one base-drift incident (project memory `project_execute_phase_worktree_base_drift`) |

### Deferred to v1.x / v2

- **9 requirements relocated to v2 / Backlog** at v1.0 close per audit recommendation #3:
  - SRCH-09 (per-session recently-pulled list)
  - OFF-01..04 (offline banner, disabled input, reconnect backoff, success indicator)
  - PRIV-01..04 (session-only history, no server query text, aggregate-only stats, no-PIN reset-kiosk)
  - PRIV-02/03 are *de-facto* satisfied by Phase 8 `record_stats` (release_id-only) but remain re-scoped for the formal multi-user privacy floor.
- **6 Phase 6 MQTT 5 wire-level checkpoints formally deferred to the hardware milestone.** Software-side 12/12 Phase 6 must-haves pass; the deferred items require a live broker + MQTT 5 inspector + ESP32 firmware to verify.
- **Phase 999.1** (BACKLOG): shelf-overview mini-Kallax shows per-cube fill/occupancy — cosmetic admin UI enhancement on `LocatorHeader`; data already returned by `GET /api/admin/cubes` (`is_empty`, `fill_level`).
- **Phase 999.2** (BACKLOG): LED party / sound-reactive modes — post-hardware flourish.
- **WR-01..WR-03 / IN-01..IN-03** from `05-REVIEW.md` — non-blocking review observations carried forward (WR-04 closed in 260526-d6s).

### Known gaps

- **Phase 7 resume-at-step UI re-verify** accepted as shipped on the strength of the landed code fix (commit `03fb309`, `Math.max(completedSteps, 0)`). Re-verify will fall out of normal wizard use.
- **Phase 10 IN-02 (KioskView SSE try/catch)** marked `resolved-by-design` — the defensive `console.error` blocks are verified present and exercised by Test 2; the synthetic malformed-frame trigger is not practically reachable.

### Audit trail

- Pre-close audit: `.planning/milestones/v1.0-MILESTONE-AUDIT.md` (originally `status: gaps_found`; all 4 actionable recommendations — INT-A, INT-B, doc reconciliation, manual checkpoints — closed by Phase 10 + the v1.0-close session)
- Archived roadmap: `.planning/milestones/v1.0-ROADMAP.md`
- Archived requirements: `.planning/milestones/v1.0-REQUIREMENTS.md` (75 in scope / 75 satisfied / 9 relocated)

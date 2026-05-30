# Milestones

## v2.0 Multi-User Collections (Shipped: 2026-05-30)

**Timeline:** 2026-05-26 → 2026-05-30 (5 days)
**Phases:** 5 (1, 2, 3, 4, 5) — all complete and verified
**Plans:** 35 plans, 35 SUMMARY.md files
**Code:** +96,155 / −1,688 across 516 files (Python 3.13 + TypeScript/React 19)
**Git range:** `545fb45` (`feat(01-00)` wave-0 scaffolding) → `854fa3c` (audit close prep); 169 commits, 25 `feat(`
**Quick tasks completed during milestone:** 1 (260530-j7t — LED-action button styling)
**Audit:** `tech_debt` (no blockers; 12/12 active requirements satisfied; all governance gaps resolved) — see [`milestones/v2.0-MILESTONE-AUDIT.md`](./milestones/v2.0-MILESTONE-AUDIT.md)

### North-star outcome

> Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms.

The Core Value loop is preserved through a full re-architecture: positioning, search, and `/api/locate` now run off a local `profile_collection` cache populated from discogsography's **HTTP API** (scoped PAT) instead of the retired `gruvax.v_collection` cross-schema read. The p95 SLOs (`/api/search` ≤ 200 ms, `/api/locate` ≤ 50 ms) hold under the v1.0 Phase 8 CI benchmark gate, now parameterized per profile. For a single-profile deployment every end-to-end flow is wired clean.

### Key accomplishments by phase

- **Phase 1 — Walking skeleton (API client + single-profile sync).** `httpx` + `stamina` `DiscogsographyClient` with locked 401/403/429/5xx/network retry semantics; Fernet PAT-at-rest + structlog secret redactor; canonical in-process fake-discogsography FastAPI fixture shared by tests *and* the Compose sibling service. Alembic 0009 lands `profiles` + `profile_collection`, drops `v_collection` and revokes the read-only grant (clean round-trip). `sync_profile()` staging-swap (advisory lock + psycopg3 `COPY FROM STDIN` TEMP table + atomic DELETE/INSERT/UPDATE + inline cache refresh). PIN-gated manual sync endpoint + `gruvax-set-pat` / `gruvax-sync` CLIs. `/api/health` three-state HTTP-probe rewire; Compose boots a fake-discogsography sibling + one-shot idempotent init-sync container.
- **Phase 2 — Multi-profile migration + profile manager.** Migration 0010 tightens `profile_id NOT NULL` on the 5 per-profile data tables (4 composite PKs; the 2 global/infra tables stay nullable), backfilling v1 data to the deterministic default profile (clean round-trip). Per-profile cache / bus / state registries + per-profile resolution deps; per-profile SSE channel `/api/events/{profile_id}` (cross-profile leakage impossible by construction). Browse-binding session (`GET /api/session` bootstrap + auto-bind + independent cookie). Profile CRUD + connect/rotate-PAT + 202+poll sync + soft-delete eviction. Profile-manager admin UI (PROFILES tab, status badges, bottom-sheet drawer with poll-until-terminal SYNCING → CONNECTED auto-transition + toast); kiosk "shelf layout not set up yet" affordance for zero-boundary profiles.
- **Phase 3 — Devices + pairing.** Migration 0011 (`devices` + `pairing_codes` + partial-unique indexes); HttpOnly + SameSite=Strict fingerprint cookie persistent across reboot. 4-digit code pairing flow A (5-min TTL, auto-reroll, `consumed_at` one-shot guard); atomic PIN-gated rate-limited bind; device-aware resolution + per-request revoke guard; profile soft-delete detaches bound devices. Devices admin UI (PENDING / PAIRED / REVOKED groupings + per-device drawer: rename / change-profile / unbind / revoke) + NumericKeypad bind. Pi provisioning artifacts (`start-kiosk.sh` + systemd unit) + Playwright reboot-persistence test. <30s end-to-end pairing confirmed via hardware UAT 2026-05-30.
- **Phase 4 — Sync polish + diagnostics.** DST-safe nightly `_sync_loop()` (03:00 local default; cadence 24h/12h/6h/off, persisted) + startup catch-up & purge sweeps; `needs_reauth` on `GET /api/session` (401 surfaces within ≤24h, immediate on manual sync). Soft-delete cache-purge background task that preserves audit lineage. Per-profile `/admin/diagnostics` cards (Nordic Grid typography, 30s refetch). Kiosk ReauthBanner + admin re-auth badge + Sync-now spinner/elapsed/completion toast + cadence select.
- **Phase 5 — Close v2.0 integration gaps (INSERTED — audit-driven closure).** B-01: kiosk now consumes the `collection_changed` SSE event so search results refresh live after nightly/manual sync (no manual reload). B-02: `/api/search` + `/api/locate` accept an omitted `profile_id`, resolving the cookie-authoritative bound profile server-side (was a 422 before session bootstrap) while preserving D2-04 validation exactly (400 session_unbound, 403 profile_mismatch — no cross-profile leak); frontend gates the fetch on a resolved `boundProfileId`. API-02, SYN-01, SYN-02 restored end-to-end.

### Key decisions

| Decision | Outcome |
|----------|---------|
| Re-architect from `v_collection` cross-schema reads to discogsography **HTTP API** + scoped PATs | ✓ Good — clean per-user authorization boundary; `v_collection` and its grant fully retired in migration 0009 |
| Local `profile_collection` cache as the positioning/search source (staging-swap sync) | ✓ Good — SLOs preserved off in-memory + local-table reads; API latency kept off the hot path |
| Fernet-encrypted PAT at rest + structlog secret redactor | ✓ Good — no plaintext token in DB or logs; stdin-only `gruvax-set-pat` rotation |
| Per-profile cache/bus/SSE channel keyed by `profile_id` | ✓ Good — cross-profile data leakage impossible by construction (OOS-04 satisfied structurally) |
| Sequential cross-repo coordination (discogsography v2 ships before GRUVAX P1) | ✓ Good — built against a canonical fake-discogsography contract fixture; no stub drift |
| 4-digit code pairing flow A (reuses v1 in-app numeric keypad) | ✓ Good — <30s end-to-end confirmed via hardware UAT; QR/scan deferred to v2.1 |
| DST-safe `next_fire_after()` nightly scheduler via `asyncio.create_task` in lifespan | ✓ Good — no cron/external scheduler; cadence configurable + persisted |
| Closure-phase pattern for milestone-audit seams (Phase 5, as v1.0 did with Phase 10) | ✓ Good — B-01 + B-02 absorbed in 2 plans rather than retrofitting earlier phases |

### Tech debt carried forward (documented, non-blocking)

- **DEV-02 SSE immediacy** — `device_reassigned` / `device_revoked` SSE events are published but have no `KioskView.tsx` consumer; kiosk profile switch / revocation recovery happens via the 5-min session poll, not the immediate SSE reload that 03-VERIFICATION SC3 over-claimed. WARNING for multi-profile; harmless for single-profile. Follow-up: add the two listeners.
- **`write_boundary` profile scoping** — the boundary UPDATE has no `profile_id` in its WHERE clause. Safe today (admin boundary editing is default-profile-only in v2.0) but structurally unsound before any multi-profile boundary-editing UI ships (PROF-04 forward-looking).
- **`boundary_changed` SSE fan-out** — publishes only to the default profile's SSE bus (P1-compat alias); non-default-profile kiosks don't receive admin boundary edits via SSE. Default-profile-only is in v2.0 scope.
- **Doc drift (cosmetic)** — stale `collection_changed` "no payload" comment (KioskView.tsx:340); unreachable `get_event_bus` 503-path docstring (deps.py); a mislabeled test-evidence attribution in 05-VERIFICATION truth #6.

### Deferred (not in v2.0)

- **AUTH-01** — OAuth2 device-authorization grant → v2.2
- **AUTH-02 / DEV-04 / API-04 / SRCH-09 / OFF-01..04 / PRIV-01..04** — v2.1 resilience + privacy + UX-polish milestone
- **PROF-05 / PROF-06 / API-05** — v2.x power-user features
- **Real LED hardware end-to-end** (ESP32 + WS2812B firmware) + 6 Phase 6 MQTT wire-level checkpoints → independent hardware milestone
- **Phase 999.1** (shelf-overview mini-Kallax fill/occupancy) + **Phase 999.2** (LED party / sound-reactive) → Backlog

### Audit trail

- Pre-close audit: [`milestones/v2.0-MILESTONE-AUDIT.md`](./milestones/v2.0-MILESTONE-AUDIT.md) (re-audit post-Phase-5; `gaps_found` → `tech_debt` after B-01/B-02 closure + governance resolution)
- Archived roadmap: [`milestones/v2.0-ROADMAP.md`](./milestones/v2.0-ROADMAP.md)
- Archived requirements: [`milestones/v2.0-REQUIREMENTS.md`](./milestones/v2.0-REQUIREMENTS.md) (13 in scope: 12 satisfied + 1 deferred; 5 external discogsography prereqs tracked separately)

---

## v1.0 MVP (Shipped: 2026-05-26)

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

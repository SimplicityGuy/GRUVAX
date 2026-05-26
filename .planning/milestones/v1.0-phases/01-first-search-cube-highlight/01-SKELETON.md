# Walking Skeleton — GRUVAX

**Phase:** 1
**Generated:** 2026-05-20

## Capability Proven End-to-End

> A user opens the kiosk SPA in any browser (served by `gruvax-api` under `docker compose up`), types
> an artist / title / label / catalog number, sees a ranked results list, and the top result's cube
> lights up on a rendered 2×(4×4) Kallax grid — backed by the POS-01 parser, the `gruvax.v_collection`
> read-only contract, fixture-seeded boundaries, an in-memory boundary cache, and the cube-only estimator.

This is the thinnest possible end-to-end slice that exercises the Core Value. Subsequent phases thicken
it (real sub-cube interpolation, admin editing, SSE realtime, LED publish, wizards, deployment hardening)
without renegotiating the decisions below.

## Architectural Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Backend framework | FastAPI 0.136.1 on Uvicorn, Python 3.13 | Matches discogsography; shared dev tooling + Docker base; first-class SSE for Phase 4 |
| DB driver / pool | psycopg 3 async + `AsyncConnectionPool` | Matches discogsography; `search_path` set on connection checkout drives the dev/prod schema swap |
| ORM / migrations | SQLAlchemy 2.0 metadata + Alembic 1.18 async template | Stable autogenerate + the OBS-03 round-trip CI gate (`upgrade→downgrade→upgrade`) |
| Config | pydantic-settings (`DATABASE_URL`, `OBSERVED_DISCOGSOGRAPHY_SCHEMA`, `MQTT_*`) | Validates at startup; typos fail boot, not a later request |
| discogsography contact surface | `gruvax.v_collection` view ONLY (DEP-02) | Single surveyable + GRANT-enforced boundary; probed at startup (Pitfall 5) |
| Dev/prod data parity | One `v_collection` body, unqualified table names; `search_path` selects `gruvax_dev` (synthetic) or `discogsography` (real) | No application code branches on environment; same code path everywhere |
| Catalog comparison | POS-01 token-stream parser (Strategy C) — numeric-aware, separator/case-folded | Raw-string comparison misplaces 35.6% of multi-record labels; Hypothesis-pinned |
| Estimator (Phase 1) | Cube-only fallback (INTERPOLATION §4.8) behind the locked `LocateResult` contract | `confidence` is a float (0.30), `sub_cube_interval: null`, `estimator_version="cube-only-v1"` (D-10/D-11/D-12); Phase 2 swaps in §4.1 |
| Boundary cache | In-memory, startup-loaded from `gruvax.cube_boundaries`, `invalidate()` seam | <50 ms estimator budget; Phase 4 wires SSE invalidation onto the seam (POS-04) |
| Search | Postgres FTS (`fts_vector` + `ts_rank_cd`) UNION a normalized catalog# prefix path | One ranked list; catalog path reliably hits `BLP 4195`-style queries (D-08) |
| Frontend | React 19 + Vite 8 + TypeScript + Tailwind 4 + Zustand + TanStack Query + GSAP/Framer Motion | Locked stack; bespoke Nordic Grid design language via committed design tokens |
| UI design contract | `01-UI-SPEC.md` (consume `design/gruvax-design-tokens.css`; never hardcode hex) | Single design source; lit cell always yellow; LED-physics motion |
| SPA serving | FastAPI `StaticFiles(html=True)` mounted AFTER all `/api` routers | One container, no CORS; mount-order avoids the catch-all intercept (Pitfall 3) |
| Deployment | Docker Compose: `gruvax-api` + `mosquitto` (no broker host port), healthchecks, `restart: unless-stopped` | DEP-01; mosquitto stands up but has no publish path until Phase 5 |
| Directory layout | `src/gruvax/{api,db,estimator,mqtt}` + `frontend/src/routes/kiosk/*` + `migrations/` + `fixtures/` | Per ARCHITECTURE §Recommended Project Structure; estimator is its own sandbox |

## Stack Touched in Phase 1

- [x] Project scaffold (uv project, Ruff, mypy --strict, just, Dockerfile, Vite/React)
- [x] Routing — `/api/search`, `/api/locate`, `/api/units`, `/api/cubes/...`, `/api/health` + SPA at `/`
- [x] Database — real read (`v_collection` startup probe + FTS/catalog search + locate lookup) AND real write (Alembic-created schema + seeded `cube_boundaries`)
- [x] UI — debounced typeahead wired to `/api/search` and `/api/locate`; cube highlight on selection
- [x] Deployment — `docker compose up` runs the full stack; SPA served by FastAPI StaticFiles

## Out of Scope (Deferred to Later Slices)

> Explicit so later phases do not re-litigate Phase 1's minimalism.

- Real sub-cube interpolation (§4.1 index-based), A/B harness, p95 ≤ 50 ms gate → Phase 2
- Multi-cube label-span secondary highlight, selection-lands animation, single-record tick-mark → Phase 2
- "Did you mean" / trigram (SRCH-07), numeric-leading catalog ranking boost (SRCH-08) → Phase 2
- Fill-level indicator (CUBE-07), reverse-lookup cube tap (CUBE-09) → Phase 3
- Admin + PIN (Argon2id) + manual boundary entry + diff preview + undo/history + boundary-save validator → Phase 3
- SSE realtime invalidation, offline banner + reconnect backoff, recently-pulled, privacy floors → Phase 4
- LED / MQTT publish path, color/brightness settings, all-off, diagnostics → Phase 5 (mosquitto container exists now; no publishers)
- Wizards (setup, reshuffle), CSV/YAML import/export → Phase 6
- Pi 5 kiosk runtime (Trixie + labwc + Chromium `--kiosk` + systemd), `/healthz` subsystem detail, slow-query log, log limits, `/version`, SLO proof → Phase 7
- Real Discogs CSV + real owner boundaries (stay gitignored; only synthetic seeds committed)

## Subsequent Slice Plan

Each later phase adds one vertical slice on top of this skeleton without altering its architectural decisions:

- Phase 2: Sub-cube position bar + label-span highlight via the real §4.1 estimator behind the same `LocateResult` contract; A/B harness; FTS trigram + numeric boost.
- Phase 3: Admin loop — PIN sign-in, manual boundary entry with autocomplete + diff preview, change-set history + undo; boundaries become a maintained artifact (the POS-01 parser becomes the save validator).
- Phase 4: SSE realtime invalidation onto `BoundaryCache.invalidate()`; offline resilience; recently-pulled; privacy floors.
- Phase 5: LED contract over MQTT — versioned, validated payloads to the (already-running) mosquitto broker; admin color/brightness settings.
- Phase 6: Wizards + CSV/YAML import/export atop the admin auth + history + validate machinery.
- Phase 7: Observability + deployment hardening — `/healthz` subsystem status, slow-query log, log limits, `/version`, Pi kiosk runtime, SLO proof.

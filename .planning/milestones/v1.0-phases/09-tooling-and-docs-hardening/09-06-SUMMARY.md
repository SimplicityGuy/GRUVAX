---
phase: 09-tooling-and-docs-hardening
plan: "06"
subsystem: docs
tags: [architecture, documentation, d-08, d-09, d-10, lux-strip]
dependency_graph:
  requires: [09-05]
  provides: [docs/ARCHITECTURE.md, README.md-architecture, CLAUDE.md-architecture]
  affects: []
tech_stack:
  added: []
  patterns: [mermaid-only-diagrams, pull-based-ghcr-docs]
key_files:
  created:
    - docs/ARCHITECTURE.md
  modified:
    - README.md
    - CLAUDE.md
decisions:
  - "Verified all 7 architecture sections against live codebase (routers, migrations, app.py) — not transcribed blindly from RESEARCH.md outline"
  - "All 6 Mermaid diagrams reused from RESEARCH.md Architecture Patterns section (logging, CI, deploy, locate flow, SSE bus, startup lifespan)"
  - "CLAUDE.md Architecture section replaced with single pointer — no content duplication"
  - "docs/runbook-fresh-host.md had zero lux references (already genericized in Phase 9); no change needed"
metrics:
  duration: "~18 min"
  completed: "2026-05-25T19:06:25Z"
  tasks_completed: 2
  files_changed: 3
---

# Phase 09 Plan 06: Docs Refresh Summary

Filled the "Architecture not yet mapped" gap with a code-verified `docs/ARCHITECTURE.md` (D-08), refreshed `README.md` and `CLAUDE.md` to point at it and reflect the Phase 1–8 + Phase 9 reality (D-09), and stripped all `lux` host-name references from both docs (D-10).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write docs/ARCHITECTURE.md (D-08) | `418022b` | `docs/ARCHITECTURE.md` (new, 365 lines) |
| 2 | Refresh README.md + CLAUDE.md (D-09 + D-10) | `1516b0a` | `README.md`, `CLAUDE.md` |

## What Was Built

### docs/ARCHITECTURE.md (D-08)

New canonical Phase 1–8 reference covering seven sections:

1. **Data Model** — `gruvax` schema tables (units, cube_boundaries, segment_overrides, boundary_history, admin_sessions, settings, idempotency_keys, record_stats) + the `gruvax.v_collection` read-only view contract (DEP-02).
2. **API Surface** — All public `/api/*` endpoints and PIN-gated `/api/admin/*` endpoints, verified against live router registrations in `src/gruvax/app.py` and `src/gruvax/api/admin/router.py`.
3. **Position Estimation** — Two-level segment-aware interpolation (Phase 5), `LocateResult` contract, §4.8 cube-only fallback.
4. **LED Contract** — MQTT topic structure (`gruvax/v1/leds/...`), payload semantics, `HighlightRegistry` TTL, retained all-off clearing.
5. **Realtime** — SSE event types (`boundary_changed`, `admin_editing`, `server_hello`, `server_shutdown`), `EventBus` decoupling.
6. **Observability** — `/api/health` subsystems, in-memory log ring (200 entries) + slow-query ring (50 entries), `/api/admin/diagnostics` surface.
7. **Deploy** — Compose services, pull-based `ghcr.io/simplicityguy/gruvax:latest` image, startup lifespan sequence diagram, CI orchestration.

6 Mermaid blocks embedded (logging flow, CI orchestration, Compose deploy, locate estimation flow, SSE bus, startup lifespan). Zero ASCII art. Zero `lux` or `nox` references.

### README.md (D-09 + D-10)

- Added `## Architecture` section + nav link pointing at `docs/ARCHITECTURE.md`.
- Updated Stack section: Python 3.14, structlog/orjson logging, Vite 8, GHCR pull-based deploy bullet.
- Stripped both `lux` references: description sentence → "the home server"; hardware table → "Deployment host".
- Updated Python badge from 3.13+ to 3.14+.
- Banner/badge/nav structure preserved intact.

### CLAUDE.md (D-09 + D-10)

- Replaced `<!-- GSD:architecture-start -->` placeholder ("Architecture not yet mapped. Follow existing patterns found in the codebase.") with a single pointer to `docs/ARCHITECTURE.md`.
- Stripped all 4 `lux` references:
  - Deployment constraint → "the deployment host"
  - Connectivity constraint → "deployment host"
  - Footprint constraint → "the deployment host"
  - Launcher table row `http://lux.local:PORT/` → `http://your-server.local:PORT/`
- GSD-managed sections (Developer Profile, Project Skills) untouched.

## Verification

| Check | Result |
|-------|--------|
| `grep -c 'v_collection' docs/ARCHITECTURE.md` | 10 (>= 1) |
| `grep -c 'ghcr.io/simplicityguy/gruvax' docs/ARCHITECTURE.md` | 2 (>= 1) |
| `grep -c '```mermaid' docs/ARCHITECTURE.md` | 6 (>= 1, no ASCII art) |
| `grep -c 'lux' docs/ARCHITECTURE.md` | 0 |
| `grep -c 'nox' docs/ARCHITECTURE.md` | 0 |
| `grep -c 'docs/ARCHITECTURE.md' README.md` | 1 (>= 1) |
| `grep -c 'docs/ARCHITECTURE.md' CLAUDE.md` | 1 (>= 1) |
| `grep -c 'Architecture not yet mapped' CLAUDE.md` | 0 |
| `grep -c 'lux' README.md` | 0 |
| `grep -c 'lux' CLAUDE.md` | 0 |
| `grep -rc 'nox' README.md CLAUDE.md docs/` | 0 matches |
| Endpoint list spot-verified against live code | Pass — verified all routes in `src/gruvax/api/` and `src/gruvax/api/admin/router.py` |

## Deviations from Plan

None — plan executed exactly as written.

`docs/runbook-fresh-host.md` was listed in RESEARCH.md as having one `lux` occurrence, but on inspection it had already been genericized to `your-server.local` (pre-existing clean state). No change needed.

The `nox` strip was confirmed a no-op: no occurrences found anywhere in README.md, CLAUDE.md, or docs/.

## Known Stubs

None. This is a documentation-only plan; all sections describe implemented functionality verified against the live codebase.

## Threat Flags

None. `docs/ARCHITECTURE.md` describes public architecture only; no secrets, credentials, or internal host names appear in the file. The T-9-DOCLEAK mitigation (strip `lux`) is confirmed complete across all targeted files.

## Self-Check

Files exist:
- [x] `docs/ARCHITECTURE.md` — confirmed EXISTS
- [x] `README.md` — modified, confirmed
- [x] `CLAUDE.md` — modified, confirmed

Commits exist:
- [x] `418022b` — `docs(09-06): add docs/ARCHITECTURE.md — Phase 1-8 canonical reference`
- [x] `1516b0a` — `docs(09-06): refresh README + CLAUDE.md — point at ARCHITECTURE.md, strip lux (D-09 + D-10)`

## Self-Check: PASSED

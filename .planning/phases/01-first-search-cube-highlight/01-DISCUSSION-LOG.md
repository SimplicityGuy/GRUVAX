# Phase 1: First Search → Cube Highlight - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-19
**Phase:** 1-first-search-cube-highlight
**Areas discussed:** Phase 1 scope & Pi target, Boundary foundation, Search matching (v1), Dev/CI collection data (+ fixture format, fixture data split, perf gate, confidence contract)

---

## Phase 1 scope & Pi target

| Option | Description | Selected |
|--------|-------------|----------|
| Browser now, Pi later | `docker compose up` on lux + SPA in any browser; Pi kiosk runtime + hardening → Phase 7 | ✓ |
| Run on Pi's Chromium in P1 | Same compose, but demo must be on the actual Pi 5 Chromium (manual launch) to validate Pi-class perf | |
| Full Pi kiosk runtime in P1 | Trixie + labwc + Chromium --kiosk + systemd autostart, as criterion 1 literally reads | |

**User's choice:** Browser now, Pi later (Recommended)
**Notes:** ROADMAP Phase 1 success criterion 1 ("on the Pi 5") to be softened to reflect the browser bar. → D-01.

---

## Perf gate (follow-up to Scope)

| Option | Description | Selected |
|--------|-------------|----------|
| Target in P1, gate later | ~200 ms is a locally-measured target; real p95 gate is Phase 2 (POS-03) + Phase 7 | ✓ |
| Hard gate in P1 | Phase 1 verification fails if local search→highlight p95 exceeds ~200 ms on synthetic data | |

**User's choice:** Target in P1, gate later (Recommended)
**Notes:** → D-02.

---

## Boundary foundation

| Option | Description | Selected |
|--------|-------------|----------|
| Real tables now, seeded | gruvax.units + gruvax.cube_boundaries via Alembic; seed from fixture; cache loads from DB | ✓ |
| In-memory cache only | Load fixture straight into cache; defer the tables to Phase 3 | |

**User's choice:** Real tables now, seeded (Recommended)
**Notes:** Admin (P3) and SSE (P4) write the same tables — avoids rework. → D-03.

---

## Fixture format (follow-up to Boundary foundation)

| Option | Description | Selected |
|--------|-------------|----------|
| YAML | Human-authorable, diff-friendly for nested first/last bounds; aligns with Phase 6 import/export | ✓ |
| CSV | Flat, spreadsheet-friendly, matches Discogs export; awkward for nested bounds | |

**User's choice:** YAML (Recommended)
**Notes:** → D-04.

---

## Fixture data split (follow-up to Boundary foundation)

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic in repo, real local | Committed fixture = synthetic boundaries matching synthetic seed; real boundaries + CSV stay gitignored | ✓ |
| Real boundaries in repo | Commit owner's actual cube boundaries; requires real collection reachable to validate | |

**User's choice:** Synthetic in repo, real local (Recommended)
**Notes:** Preserves the repo-hygiene constraint (real CSV never committed). → D-05.

---

## Search matching (v1)

| Option | Description | Selected |
|--------|-------------|----------|
| FTS + catalog path | FTS for artist/title/label via v_collection.fts_vector + normalized exact/prefix match on catalog_number | ✓ |
| FTS only | Rely solely on fts_vector for all four fields; risk: catalog numbers tokenize poorly | |

**User's choice:** FTS + catalog path (Recommended)
**Notes:** Typo-tolerance / did-you-mean (SRCH-07) and catalog ranking boost (SRCH-08) stay Phase 2. → D-08, D-09.

---

## Dev/CI collection data

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic seed default | Synthetic collection seed shaped like v_collection for CI + local default; real discogsography via env | ✓ |
| Require discogsography | Local dev + CI must run against a real discogsography Postgres; no synthetic seed | |

**User's choice:** Synthetic seed default (Recommended)
**Notes:** v_collection stays the only read surface; probed at startup (Pitfall 5). → D-06, D-07.

---

## Confidence contract (flagged inconsistency, resolved)

ARCHITECTURE.md defines `confidence: float (0..1)`; ROADMAP criterion 5 + INTERPOLATION
edge-cases use string tags (`"cube_only"`, `"singleton"`). Resolution presented as a
recommendation; user did not object.

**Resolution:** Keep `confidence: float`. Cube-only results use a documented constant +
`estimator_version: "cube-only-v1"` + `sub_cube_interval: null`. ROADMAP criterion 5 wording
to be reconciled. → D-11.

## Claude's Discretion

- Visual/interaction design → `/gsd-ui-phase 1` + committed design system.
- Catalog parser strategy (token-split vs `natsort`, INTERPOLATION §3.1) → researcher.
- Exact synthetic-seed mechanism for `v_collection` → planner/researcher (v_collection stays the only read surface).
- FTS ranking weights, debounce interval, results page size → planner within architecture guidance.

## Deferred Ideas

- Real sub-cube interpolation (§4.1; POS-05) → P2.
- CUBE-03 / CUBE-08 / CUBE-10 → P2; CUBE-07 / CUBE-09 → P3.
- Admin + PIN + boundary editing → P3.
- SSE realtime + offline + recently-pulled → P4.
- LED/MQTT publish path → P5 (mosquitto container stands up in P1).
- SRCH-07 / SRCH-08 → P2; YAML/JSON import/export + wizards → P6.
- Pi kiosk runtime + observability/deployment hardening → P7.

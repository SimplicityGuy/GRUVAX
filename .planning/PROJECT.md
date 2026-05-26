# GRUVAX

## What This Is

GRUVAX is a touchscreen kiosk plus REST API that helps the owner (and visiting friends) find any specific vinyl record in a ~3,000-record collection stored across multiple IKEA Kallax shelving units. Records are deterministically organized — alphabetical by Label, then by catalog number within label — so a record's physical position can be *calculated* rather than tracked per item. A search highlights the right cube on the kiosk's grid and (in a future milestone) lights it up on the physical shelves via WS2812B-style RGB LEDs.

## Core Value

Type artist, title, label, or catalog number → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Current State

**Shipped:** v1.0 MVP (2026-05-26) — see [MILESTONES.md](./MILESTONES.md#v10-mvp-shipped-2026-05-26) for the full breakdown.

The end-to-end search → cube highlight loop ships and is verified. Owner can sign in (PIN), enter and edit boundaries with diff-preview + undo, run guided setup and reshuffle wizards, and import/export boundaries + LED settings. The segment-aware estimator (Phase 5) supersedes the original §4.1 interpolation behind the same `LocateResult` contract, so multi-label bins resolve precisely. The LED contract over MQTT is fully wired and validated against an internal Mosquitto broker — hardware (ESP32 + WS2812B) drops into the contract without API changes. Observability (`/api/health`, `/api/version`, `/admin/diagnostics`, kiosk staleness banner), GitHub Actions CI (Alembic round-trip + p95 SLO gate), and Compose log limits + healthchecks all land.

Codebase at v1.0 close: ~36k LOC across `src/`, `frontend/src/`, `tests/`. Stack: Python 3.13 + FastAPI 0.136 + psycopg 3.2 async + SQLAlchemy 2.0 async + Alembic 1.18 on the backend; React 19 + Vite 8 + TanStack Query + Zustand + GSAP on the frontend; eclipse-mosquitto:latest for the MQTT broker; Docker Compose for deployment; Raspberry Pi OS Trixie + labwc + Chromium for the kiosk.

## Current Milestone: v2.0 Multi-User Collections

**Goal:** Re-architect GRUVAX from direct-DB reads of discogsography to an HTTP-API integration with per-user collection authorization (scoped PATs), enabling multiple household members to each have their own collection on their own RPi kiosks, with one central GRUVAX server holding all profiles.

**Target features (13 reqs in scope, walking-skeleton-first):**

- **P1 — Walking skeleton** — API client (httpx + paged + 401/403/429/5xx retry) + single-profile sync (staging-swap with advisory lock); retire `gruvax.v_collection` and the read-only Postgres grant; positioning runs off the local `profile_collection` cache; staleness reads `profiles.last_sync_at` (single profile).
- **P2 — Multi-profile** — Full `profiles` table with Fernet-encrypted PAT storage; `profile_id NOT NULL` migration across 7 v1 tables (`cube_boundaries`, `segments`, `change_log`, `change_sets`, `settings`, `record_stats`, `ambient_baseline`); profile manager admin UI; browser session profile picker with auto-bind on 1-profile-only; per-profile SSE channel.
- **P3 — Devices + pairing** — `devices` + `pairing_codes` schemas; HttpOnly fingerprint cookie; 4-digit code pairing flow (5-min TTL, auto-reroll on expiry, reuses v1 in-app numeric keypad); devices admin UI with pending/paired/revoked groupings + drawer (rename/change-profile/unbind/revoke).
- **P4 — Polish** — Nightly background sync (24h @ 03:00 local default, configurable 24h/12h/6h/off); 401 reauth UI (profile-list badge + kiosk inline banner); per-profile `/admin/diagnostics` cards; profile soft-delete cache-purge background task; "Sync now" progress + completion toast.

**External prereq (out of milestone, in flight):** discogsography v2 ships first — `app_tokens` table + catalog# verification/exposure + `require_app_token` dependency + scoped settings UI. Briefed at `background/discogsography-v2-app-tokens-brief.md` (gitignored). GRUVAX P1 does not start until discogsography ships the contract artifact at `docs/specs/v2-gruvax-integration.md` in their repo.

**Deferred (NOT in v2.0):**

- **Per-profile self-connect PAT** (invite-token model so members paste own token, owner never sees it) → v2.1
- **OAuth2 device-authorization grant** (no PAT crosses the household) → v2.2
- **QR-code RPi pairing** (kiosk shows QR, admin scans on phone) → v2.1
- **9 SPIDR-deferred v1 reqs** (SRCH-09, OFF-01..04, PRIV-01..04) → v2.1 resilience + privacy milestone
- **Phase 999.1** (shelf-overview mini-Kallax cube fill/occupancy) → Backlog
- **Phase 999.2** (LED party / sound-reactive modes) → Backlog (gated on hardware milestone)
- **Real LED hardware end-to-end** (ESP32 + WS2812B firmware) → Independent hardware milestone

**Source artifacts:**

- Refined design spec: [`docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md`](../docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md)
- Pre-synthesized intel: [`.planning/intel/SYNTHESIS.md`](./intel/SYNTHESIS.md), `decisions.md`, `requirements.md`, `constraints.md`, `context.md`

## Context

**Existing infrastructure (already running on the deployment host):**

- **discogsography** — separate project (https://github.com/SimplicityGuy/discogsography) that maintains:
  - PostgreSQL with full-text search across releases/artists
  - FastAPI REST API + Discogs OAuth-driven collection sync (keeps `releases`, `artists`, `collection_items` current)
  - Neo4j music graph database
  - MCP server for AI assistant integration
- Collection is already synced and queryable; GRUVAX layers cube-location data on top via the read-only `gruvax.v_collection` view contract.

**Hardware target:**

- Raspberry Pi 5 (4 GB RAM, 512 GB M.2 SSD) running Chromium in kiosk mode against the GRUVAX web UI
- 7" touchscreen mounted at/near the shelves
- Two 4×4 IKEA Kallax units side-by-side today (32 cubes total); design accommodates additional units without schema change
- **Future hardware milestone:** ESP32 or Arduino per unit driving RGB LED strips per cube, talking MQTT against the Phase 6 contract

**Collection characteristics:**

- ~3,043 records as of 2026-05-19 Discogs export (local CSV at repo root, gitignored)
- Catalog-number formats are inconsistent across labels (e.g., `BLP 4195`, `KC 32731`, `ECM 1064`, `1SHOT-002`, `TWELVE 002`, `Twelve 005`, `19BOX019`). Within a single label the format is usually consistent, but case and separator conventions vary across labels.
- Sort key inside a label: catalog number. The export does *not* include the structured label sub-fields Discogs maintains, so the catalog number is the practical proxy.
- Single-record labels and labels spanning multiple cubes both occur; interpolation handles both via the segment-aware model.

**Reference materials (local-only, gitignored):**

- `background/` — earlier Claude conversations, mockup screenshots, an architecture SVG, and `shelf_ui_mockup.html` (dark/monospace/gold visual direction; superseded by the Nordic Grid design language in `design/`)
- `RWlodarczyk-collection-*.csv` — Discogs exports, ground truth for interpolation research

## Constraints

- **Tech stack — Backend**: Python 3.13 + FastAPI 0.136.x in this repo. Aligned with discogsography's Python and FastAPI versions to share a dependency story.
- **Tech stack — Frontend**: React 19 + Vite 8 + TanStack Query + Zustand + GSAP, running in Chromium kiosk mode on the Pi. Built and shipped in v1.0.
- **Deployment**: Docker Compose on the deployment host, sibling to discogsography. No second host for v1.
- **Database**: Shared Postgres instance with discogsography. GRUVAX owns a dedicated schema (`gruvax`); reads from discogsography's collection tables read-only via `gruvax.v_collection`. Dev DB uses schema `gruvax_dev` to stand in for `discogsography`.
- **Performance**: Type-ahead search round-trip ≤ ~200 ms; `/api/locate` p95 ≤ 50 ms. Enforced by the Phase 8 CI benchmark SLO gate.
- **Connectivity**: Home LAN only; no public exposure. The Pi → deployment-host link is the critical path.
- **Security**: Single PIN (Argon2id-hashed) gates admin actions; sliding-window session timeout. No multi-user concerns in v1.
- **Footprint**: Total hardware budget guidance from prior planning: ~$80–$150 (screen + Pi + initial LEDs). Software side stays correspondingly small — no heavyweight services beyond what already runs on the deployment host.
- **Repo hygiene**: The collection CSV and `background/` directory are local-only references; they must never be committed.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GRUVAX backend lives in this repo (not in discogsography) and deploys sibling to it | Keeps GRUVAX-specific code near the kiosk UI; discogsography stays focused on Discogs ingestion. Avoids cross-repo coupling for kiosk-only concerns. | ✓ Good — shipped v1.0 without any cross-repo friction |
| Boundary table (16 rows × N units) + segment derivation, not per-instance mapping | ~5–10 min reshuffle maintenance vs ~3,000 rows of one-time data entry. | ✓ Good — Phase 5 segment-aware model derives everything else from cut points + overrides |
| Dedicated `gruvax` schema in the same Postgres instance, reads via `gruvax.v_collection` view | Same-host = lowest latency. Schema isolation protects GRUVAX from discogsography migrations. | ✓ Good — survived dev (`gruvax_dev`) vs prod (`discogsography`) schema drift transparently via `search_path` |
| Cube + sub-cube position is computed, not stored per-record | Labels span 0+ cube boundaries; position is a function of `v_collection` rank, not a per-record write. | ✓ Good — Phase 5's two-level interpolation makes this precise even for multi-label bins |
| LED endpoint exists in v1, hardware integration stubbed | Locks the API contract early so the UI + admin flows are complete; hardware milestone slots in without breaking changes. | ✓ Good — Phase 6 ships the validated MQTT contract; ESP32 work can start against it |
| Auth = single PIN (Argon2id) with sliding-window session timeout | Home LAN, single owner. Right size for v1; `fastapi-users` would have been overkill. | ✓ Good — shipped in Phase 3; multi-user is a separate milestone if/when needed |
| Docker Compose deployment, sibling to discogsography | Consistent ops story; shared Postgres is trivially reachable. | ✓ Good — Phase 8 hardened with log limits + healthchecks |
| Nordic Grid design language (Phase 5 onward) | Kallax-cube-as-UI-atom design system unifies kiosk + admin + diagrams + favicons under tokens. | ✓ Good — admin Diagnostics page in Phase 8 used it verbatim |
| LED color choices are admin-configurable, not hard-coded | Colors in earlier discussions (purple for label-span, etc.) were suggestions only; admin should be able to tune. | ✓ Good — shipped in Phase 6 with `/admin/settings` color/brightness controls |
| Vertical MVP slicing (every phase end-to-end user-observable) | No horizontal infrastructure-only phases — every phase ships something the owner can use. | ✓ Good — kept the project shippable at every checkpoint |
| Closure phase pattern for milestone-audit gaps (Phase 10) | When an audit surfaces cross-phase seams that no single per-phase verification can catch, absorb them in a single closure phase rather than retrofitting earlier phases. | ✓ Good — INT-A + INT-B + traceability reconcile landed cleanly in 3 plans |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Current State + Next Milestone Goals
5. REQUIREMENTS.md regenerated fresh for the next milestone

---
*Last updated: 2026-05-26 at v2.0 milestone kickoff. v1.0 MVP shipped 2026-05-26 with 10 phases, 50 plans, ~36k LOC, 75/75 in-scope requirements satisfied (9 SPIDR-deferred items formally relocated to v2/Backlog). v2.0 introduces multi-user collections via discogsography's HTTP API + scoped PATs (13 reqs across 4 phases; phase numbering reset per `--reset-phase-numbers`). Full v1.0 archive: [`milestones/v1.0-ROADMAP.md`](./milestones/v1.0-ROADMAP.md), [`milestones/v1.0-REQUIREMENTS.md`](./milestones/v1.0-REQUIREMENTS.md), [`milestones/v1.0-MILESTONE-AUDIT.md`](./milestones/v1.0-MILESTONE-AUDIT.md). Project history: [`MILESTONES.md`](./MILESTONES.md).*

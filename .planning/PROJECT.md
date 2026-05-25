# GRUVAX

## What This Is

GRUVAX is a touchscreen kiosk plus REST API that helps the owner (and visiting friends) find any specific vinyl record in a ~3,000-record collection stored across multiple IKEA Kallax shelving units. Records are deterministically organized — alphabetical by Label, then by catalog number within label — so a record's physical position can be *calculated* rather than tracked per item. A search highlights the right cube on the kiosk's grid and (in a future milestone) lights it up on the physical shelves via WS2812B-style RGB LEDs.

## Core Value

Type artist, title, label, or catalog number → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## Requirements

### Validated

- [x] Admin-configurable color settings for LED/UI output (label-span color, position-estimate color, etc.) — *Validated in Phase 6: LED Contract over MQTT*
- [x] LED illumination endpoint with hardware integration stubbed (publishes to an MQTT topic); contract finalized so hardware can land in a later milestone without changing the API — *Validated in Phase 6: LED Contract over MQTT (illuminate/span/sub/all-off/diagnostic over Mosquitto; live-broker behavior pending hardware in 06-HUMAN-UAT.md)*
- [x] Admin mode (PIN-gated, session timeout) for editing cube boundaries — mobile-first admin web UI, manual entry + undo, segment-aware boundary editing, guided setup/reshuffle wizard, and CSV/YAML boundary + settings import/export — *Validated across Phase 3 (PIN + manual entry + undo), Phase 5 (segment-aware precision), and Phase 7 (wizards + import/export; one quick reshuffle resume-at-step re-verify tracked in 07-HUMAN-UAT.md)*
- [x] Operable, observable, self-healing v1: enriched `/api/health` (per-subsystem reachability + git-SHA version + sync staleness), `/api/version`, structured-JSON logging, slow-query SLO log, durable `release_id`-only usage counters (no query text), admin `/admin/diagnostics` page + kiosk staleness banner, Compose log limits + healthchecks, and GitHub Actions CI proving the Alembic round-trip + p95 SLO gate on synthetic data — *Validated in Phase 8: Observability + Deployment Hardening (two browser-based UI confirmations — diagnostics page render + kiosk banner — tracked in 08-HUMAN-UAT.md)*

### Active

- [ ] Type-ahead search over the local collection (artist, title, label, catalog#) with sub-200 ms response
- [ ] Ranked results list with tap-to-select; top result highlights automatically; selection re-highlights
- [ ] Configurable N×4×4 Kallax grid UI rendering the active cube selection (current N=2 units, 32 cubes)
- [ ] Cube boundary data model: per-cube first/last `(label, catalog#)` bounds; binary-searched at query time
- [ ] Position estimation API that returns both a label-span (cubes the label occupies) and a sub-cube position estimate (interval, may cross cube boundaries). The estimation approach is intentionally not specified here — see research stream below; the right approach likely varies with how a label's catalog numbers are distributed.
- [ ] Offline behavior: kiosk detects loss of connectivity to the GRUVAX backend on `lux` and shows an offline banner; search is disabled until reachable
- [ ] Docker Compose deployment alongside discogsography on `lux`; shared Postgres instance, dedicated `gruvax` schema

### Out of Scope (v1 — tracked in backlog)

- Real LED hardware end-to-end (ESP32/Arduino + MQTT + WS2812B strips) — design contract ships in v1; physical integration is a later milestone
- Screensaver / browse / cover-art slideshow mode — black screen on idle for v1
- Periodic JSON export of `cube_boundaries` to git as a portable backup — Postgres backups suffice for v1
- Multi-user authentication / OAuth — single PIN with session timeout is sufficient for home LAN
- RFID / per-record tagging — deterministic ordering means individual tracking is unnecessary

## Context

**Existing infrastructure (already running on `lux`, the user's home server):**

- **discogsography** — separate project (https://github.com/SimplicityGuy/discogsography) that maintains:
  - PostgreSQL with full-text search across releases/artists
  - FastAPI REST API + Discogs OAuth-driven collection sync (keeps `releases`, `artists`, `collection_items` current)
  - Neo4j music graph database
  - MCP server for AI assistant integration
- Collection is already synced and queryable; GRUVAX layers cube-location data on top.

**Hardware target:**

- Raspberry Pi 5 (4 GB RAM, 512 GB M.2 SSD) running Chromium in kiosk mode against the GRUVAX web UI
- 7" touchscreen mounted at/near the shelves
- Two 4×4 IKEA Kallax units side-by-side today (32 cubes total); design accommodates additional units without schema change
- Future hardware milestone: ESP32 or Arduino per unit driving RGB LED strips per cube, talking MQTT or USB serial

**Collection characteristics:**

- ~3,043 records as of 2026-05-19 Discogs export (local CSV at repo root, gitignored)
- Catalog-number formats are inconsistent across labels (e.g., `BLP 4195`, `KC 32731`, `ECM 1064`, `1SHOT-002`, `TWELVE 002`, `Twelve 005`, `19BOX019`). Within a single label the format is usually consistent, but case and separator conventions vary across labels.
- Sort key inside a label: catalog number. The export does *not* include the structured label sub-fields Discogs maintains, so the catalog number is the practical proxy.
- Single-record labels and labels spanning multiple cubes both occur; interpolation must handle both.

**Reference materials (local-only, gitignored):**

- `background/` — earlier Claude conversations, mockup screenshots, an architecture SVG, and `shelf_ui_mockup.html` (dark/monospace/gold visual direction)
- `RWlodarczyk-collection-20260519-0257.csv` — Discogs export, ground truth for interpolation research

## Constraints

- **Tech stack — Backend**: Python + FastAPI in this repo. Align Python and FastAPI versions with discogsography to share a dependency story.
- **Tech stack — Frontend**: Web stack (React + GSAP + Three.js/Pixi proposed) running in Chromium kiosk mode on the Pi. Final stack decision deferred to UI design phase.
- **Deployment**: Docker Compose on `lux`, sibling to discogsography. No second host for v1.
- **Database**: Shared Postgres instance with discogsography. GRUVAX owns a dedicated schema (`gruvax`); reads from discogsography's collection tables read-only.
- **Performance**: Type-ahead search round-trip ≤ ~200 ms perceived from keystroke to result.
- **Connectivity**: Home LAN only; no public exposure. Pi → `lux` link is the critical path.
- **Security**: Single PIN gates admin actions; session timeout after inactivity. No multi-user concerns.
- **Footprint**: Total hardware budget guidance from prior planning: ~$80–$150 (screen + Pi + initial LEDs). Software side aims to stay correspondingly small — no heavyweight services beyond what already runs on `lux`.
- **Repo hygiene**: The collection CSV and `background/` directory are local-only references; they must never be committed.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| GRUVAX backend lives in this repo (not in discogsography) and deploys to `lux` | Keeps GRUVAX-specific code near the kiosk UI; discogsography stays focused on Discogs ingestion. Avoids cross-repo coupling for kiosk-only concerns. | — Pending |
| Boundary table (16 rows × N units), not per-instance mapping | ~5–10 min reshuffle maintenance vs ~3,000 rows of one-time data entry. Deterministic ordering already gives positional precision via interpolation. | — Pending |
| Dedicated `gruvax` schema in the same Postgres instance, reading discogsography tables read-only | Same-host = lowest latency. Schema isolation protects GRUVAX from discogsography migrations. | — Pending |
| Cube + sub-cube position is computed, not stored per-record | Labels span 0+ cube boundaries; LEDs are RGB, so the API returns both a label-span and a position interval that may cross a cube boundary. The estimation method itself is deliberately undecided here. | — Pending |
| LED endpoint exists in v1, hardware integration stubbed | Locks the API contract early so the UI + admin flows are complete; hardware milestone slots in without breaking changes. | — Pending |
| Auth = single PIN with session timeout | Home LAN, single owner. PIN is enough; timeout reduces accidental edits during demos. | — Pending |
| Docker Compose deployment, sibling to discogsography | Consistent ops story; shared Postgres is trivially reachable. | — Pending |
| UI aesthetic intentionally not locked from the mockup | Mockup is a directional starting point; first frontend phase runs a fresh design pass. | — Pending |
| LED color choices are admin-configurable, not hard-coded | Colors in earlier discussions (purple for label-span, etc.) were suggestions only; admin should be able to tune. | — Pending |
| Position-estimation is its own research stream | Catalog-number sort and label-span behavior have enough edge cases (case inconsistency, mixed prefix conventions, multi-cube spans) that they need a dedicated investigation. Research should compare multiple approaches against the actual label-by-label distributions in the local CSV; no algorithm is pre-selected. | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-25 after Phase 8 (Observability + Deployment Hardening) completion*

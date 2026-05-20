<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="design/assets/banner_dark.png">
  <source media="(prefers-color-scheme: light)" srcset="design/assets/banner_light.png">
  <img alt="GRUVAX — Vinyl Shelf Navigator" src="design/assets/banner_dark.png" width="600">
</picture>

<br><br>

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm--NC--1.0.0-0051A2)](https://polyformproject.org/licenses/noncommercial/1.0.0/) ![Python 3.13+](https://img.shields.io/badge/python-3.13+-0051A2.svg?logo=python&logoColor=white)

**A touchscreen kiosk + REST API for finding any record in a ~3,000-LP collection across IKEA Kallax shelving — type an artist, title, label, or catalog number and watch the right cube light up.**

</div>

<p align="center">

[🔍 How It Works](#-how-it-works) | [🧱 Hardware](#-hardware) | [🧰 Stack](#-stack) | [✨ Features](#-v1-features) | [🎨 Design](#-design) | [🗺️ Planning](#-planning-artifacts)

</p>

GRUVAX is a vinyl shelf navigator built around a single idea: a record's physical location can be **computed**, not tracked. The collection is deterministically organized — alphabetical by label, then by catalog number within label — so a small per-cube boundary table is enough to place any of ~3,000 records on the shelves. No RFID, no barcodes, no per-record stickers.

The name comes from Swedish _gruv_ (groove — as in a record groove; also _to dig_) plus the `-ax` suffix common to IKEA product names (KALLAX, EKBY). Pronounced "GROO-vax." It runs alongside [discogsography](https://github.com/SimplicityGuy/discogsography) on the home server `lux` and reads its collection data.

## 🔍 How It Works

1. Browse or search the collection on the 7" touchscreen mounted near the shelves.
2. Tap a record (or hit a search result).
3. The matching cube highlights in the on-screen grid — and, in a future hardware milestone, lights up on the physical shelf.
4. A sub-cube position estimate narrows down roughly where in the cube the record sits (label-span + interpolated interval).

The system relies on a _deterministic shelf ordering_ — alphabetical by label, then by catalog number within label — so a record's position can be **computed** from a small per-cube boundary table rather than tagged per record.

## 🧱 Hardware

| Component                  | Role                                                        |
| -------------------------- | ---------------------------------------------------------- |
| Raspberry Pi 5             | Kiosk host — 4 GB RAM, 512 GB M.2 SSD                       |
| 7" touchscreen             | Primary UI surface, Chromium kiosk mode under Wayland/labwc |
| Home server (`lux`)        | Runs the FastAPI backend and shares Postgres + Mosquitto    |
| ESP32 (per Kallax unit)    | LED driver — _future milestone, not in v1_                  |
| WS2812B LED strip per cube | Per-cube illumination — _future milestone, not in v1_       |

Initial deployment: two 4×4 IKEA Kallax units side-by-side (32 cubes total). The data model and UI accommodate additional units without schema change.

## 🧰 Stack

- **Backend** — Python 3.13 + FastAPI, deployed via Docker Compose alongside [discogsography](https://github.com/SimplicityGuy/discogsography) on the home server.
- **Database** — Shared PostgreSQL instance; GRUVAX owns a dedicated `gruvax` schema and reads discogsography's collection data through a read-only `gruvax.v_collection` view.
- **Frontend** — Single-page app served by the backend; runs fullscreen in Chromium kiosk mode on the Pi and is responsive enough to double as the mobile admin UI. Final framework choice lands in the UI design phase; the working baseline is Vite + React 19.
- **Realtime** — Server-Sent Events for kiosk updates on boundary edits.
- **LED control plane** — `aiomqtt` publishing to an internal `eclipse-mosquitto` broker; the contract is locked in v1 even though the hardware milestone (ESP32 firmware + WS2812B wiring) lands later.
- **Metadata** — comes from the [discogsography](https://github.com/SimplicityGuy/discogsography) project, which handles Discogs OAuth sync, full-text search, and the music graph.

## ✨ v1 Features

- **Configurable N×4×4 Kallax grid** UI — supports any number of side-by-side 4×4 units (currently 2).
- **Type-ahead search** across artist / title / label / catalog number, with sub-200 ms perceived latency and pg_trgm "did you mean" fallback.
- **Cube highlight on match** — primary cube + label-span secondary highlight + sub-cube position interval bar (interval may cross a cube boundary).
- **PIN-protected admin** with sliding-window session timeout — mobile-first, with a kiosk fallback that uses an in-app numeric keypad.
- **Three boundary workflows** — manual entry with autocomplete + diff preview, guided setup wizard, CSV/YAML seed import. Every mutation goes through an append-only change log with one-tap undo.
- **Live kiosk updates** — admin boundary edits on mobile re-render the kiosk via SSE without a manual refresh.
- **Admin-configurable LED colors and brightness** per system state (label-span, position, error, setup, all-off).
- **Offline detection** with auto-reconnect and exponential backoff.
- **Docker Compose deployment** with healthchecks, log limits, and Alembic migrations.

Deferred to later milestones: real LED hardware integration (firmware + WS2812B wiring), screensaver / cover-art browse mode, periodic JSON export of boundaries to git, per-visitor PIN, service-worker offline cache.

## 🎨 Design

GRUVAX ships with a complete design language — the **Nordic Grid** identity. It borrows IKEA's visual system (institutional blue, high-contrast yellow, condensed sans-serif type) and extends it with the vocabulary of a physical LED display and vinyl culture. The result reads like it could have shipped inside a Kallax box: structured, confident, and legible on a 7" screen from across the room.

**Palette**

![IKEA Blue](https://img.shields.io/badge/IKEA_Blue-%230051A2-0051A2?style=flat-square)
![LED Yellow](https://img.shields.io/badge/LED_Yellow-%23FFDA00-FFDA00?style=flat-square)
![Blue Dark](https://img.shields.io/badge/Blue_Dark-%23003D7A-003D7A?style=flat-square)
![Off White](https://img.shields.io/badge/Off_White-%23F7F9FC-F7F9FC?style=flat-square)

**Type system** — Barlow Condensed (display & wordmark) · Space Grotesk (UI body) · DM Mono (catalog numbers, bin positions, counts).

The atomic unit of the UI is the Kallax cube: a 4×4 grid where each cell is a record bin that springs to a lit yellow LED state on a match. The full package lives in [`design/`](design/):

| File                                                                                        | Purpose                                              |
| ------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| [`gruvax-design-language.md`](design/gruvax-design-language.md)                              | The spec — brand, color, type, grid, motion, voice   |
| [`gruvax-design-tokens.css`](design/gruvax-design-tokens.css)                                | CSS custom properties (the source of truth)          |
| [`gruvax-design-tokens.json`](design/gruvax-design-tokens.json)                              | Same tokens for JS/TS consumption                    |
| `gruvax-logo-{square,banner,icon}.svg`, `gruvax-logo-banner-dark.svg`, `gruvax-favicon.svg` | Logo marks (standard + reversed) and favicon         |
| [`assets/banner_{light,dark}.png`](design/assets/)                                          | Rendered README banners (light card / reversed dark) |

→ **Read the full spec:** [`design/gruvax-design-language.md`](design/gruvax-design-language.md)

## Running Locally (Demo)

### Prerequisites

- Docker + Docker Compose
- A running `gruvax-dev-pg` container on `localhost:5432` (see below) with the dev DB seeded
- `just` task runner (`brew install just` or see [just.systems](https://just.systems))

### Quickstart

```bash
# 1. Seed the dev database (first time or after a schema reset)
#    This starts a local Postgres container named gruvax-dev-pg,
#    applies Alembic migrations, and loads the synthetic collection + boundaries.
just seed-dev

# 2. Build the SPA and start the full stack
docker compose up

# 3. Open the kiosk
open http://localhost:8000
```

Type an artist, label, or catalog number (e.g. `Blue Note`, `BLP 4001`, or `ECM`).
The top result auto-highlights its cube. Tap other results to move the highlight.
Click the clear-X (×) to reset.

### Stop / Restart

```bash
# Stop and remove containers — does NOT delete volumes (keeps mosquitto persistence)
docker compose down

# NEVER run `docker compose down -v` unless you intend to wipe the mosquitto-data
# volume (persistent retained LED state in Phase 5+). The -v flag deletes volumes.
```

### Starting the Dev Postgres

If `gruvax-dev-pg` is not running:

```bash
docker run -d --name gruvax-dev-pg \
  -e POSTGRES_USER=gruvax \
  -e POSTGRES_PASSWORD=gruvax \
  -e POSTGRES_DB=gruvax \
  -p 5432:5432 \
  postgres:18
```

### Environment Variables

Copy `.env.example` to `.env` and set your values. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `GRUVAX_DB_USER` | `gruvax` | Postgres user |
| `GRUVAX_DB_PASSWORD` | `gruvax` | Postgres password |
| `GRUVAX_DB_HOST` | `host.docker.internal` | DB hostname (from inside the container) |
| `GRUVAX_DB_NAME` | `gruvax` | Database name |
| `OBSERVED_DISCOGSOGRAPHY_SCHEMA` | `gruvax_dev` | Schema holding collection source tables |

**DB connectivity from inside Docker (Linux):** The gruvax-api container reaches the host Postgres
via `host.docker.internal`. On Linux, this resolves via the `extra_hosts: host-gateway` line
in `compose.yaml`. On macOS/Windows, `host.docker.internal` is built in.

## 🗂️ Repository Layout

```
gruvax/
├── pyproject.toml           # Python project (uv-managed)
├── uv.lock                  # Python lockfile
├── compose.yaml             # Docker Compose: gruvax-api + mosquitto
├── Dockerfile               # Multi-stage: frontend build + Python runtime
├── justfile                 # Task runner: test, lint, migrate, seed-dev, up
├── alembic.ini              # Alembic migration config
├── design/                  # Design language: tokens, logos, banners, spec
├── mosquitto/               # Broker config (mosquitto.conf)
├── fixtures/                # Synthetic collection seed + boundary YAML
├── migrations/              # Alembic migration versions
├── src/gruvax/              # Backend: FastAPI + estimator + mqtt
├── tests/                   # Unit, integration, property (Hypothesis)
└── frontend/                # Vite 8 + React 19 SPA (kiosk + future /admin)
```

## 🗺️ Planning Artifacts

This project is being built via the [Get Shit Done](https://github.com/SimplicityGuy/get-shit-done) workflow. The full planning trail lives in [`.planning/`](.planning/):

- [`PROJECT.md`](.planning/PROJECT.md) — what GRUVAX is, Core Value, constraints, key decisions
- [`REQUIREMENTS.md`](.planning/REQUIREMENTS.md) — 73 v1 requirements across 11 categories
- [`ROADMAP.md`](.planning/ROADMAP.md) — 7-phase vertical MVP plan
- [`research/`](.planning/research/) — stack, features, architecture, pitfalls, position-estimation algorithms, synthesis
- [`STATE.md`](.planning/STATE.md) — project memory and current focus

## 📊 Status

**Phase 1 complete.** The Core Value is demoable: `docker compose up` brings up the full stack, the
React SPA serves from `http://localhost:8000`, and typing a query lights up the right cube in the
2×(4×4) grid.

Stack versions as shipped (reconciled from RESEARCH.md against npm/PyPI):

| Component | Version | Note |
|-----------|---------|------|
| Vite | 8.x | npm latest (CLAUDE.md said 7.x — updated) |
| aiomqtt | 2.5.x | PyPI latest (no 3.x series exists) |
| sse-starlette | 3.4.x | PyPI latest (was 2.x in STACK.md) |
| Python | 3.14 | Dockerfile uses 3.14-slim |

## 📄 License

GRUVAX is **source-available** under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/). See [LICENSE](LICENSE) for the full text.

- **Free for noncommercial use** — personal projects, research, education, and hobby use are all permitted at no cost.
- **Commercial use requires a separate license.** If you (or your employer) want to use this software for a commercial purpose, contact **Robert Wlodarczyk** at [robert@simplicityguy.com](mailto:robert@simplicityguy.com) to discuss terms.

______________________________________________________________________

<div align="center">
Made with ❤️ and too many records in the Pacific Northwest
</div>

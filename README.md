<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="design/assets/banner_dark.png">
  <source media="(prefers-color-scheme: light)" srcset="design/assets/banner_light.png">
  <img alt="GRUVAX — Vinyl Shelf Navigator" src="design/assets/banner_dark.png" width="600">
</picture>

<br><br>

[![License: PolyForm Noncommercial 1.0.0](https://img.shields.io/badge/license-PolyForm--NC--1.0.0-0051A2)](https://polyformproject.org/licenses/noncommercial/1.0.0/) ![Python 3.14+](https://img.shields.io/badge/python-3.14+-0051A2.svg?logo=python&logoColor=white)

**A touchscreen kiosk + REST API for finding any record in a ~3,000-LP collection across IKEA Kallax shelving — type an artist, title, label, or catalog number and watch the right cube light up.**

</div>

<p align="center">

[🔍 How It Works](#-how-it-works) | [🧱 Hardware](#-hardware) | [🧰 Stack](#-stack) | [✨ Features](#-features) | [🏛️ Architecture](#-architecture) | [🎨 Design](#-design) | [🗺️ Planning](#-planning-artifacts)

</p>

GRUVAX is a vinyl shelf navigator built around a single idea: a record's physical location can be **computed**, not tracked. The collection is deterministically organized — alphabetical by label, then by catalog number within label — so a small per-cube boundary table is enough to place any of ~3,000 records on the shelves. No RFID, no barcodes, no per-record stickers.

The name comes from Swedish _gruv_ (groove — as in a record groove; also _to dig_) plus the `-ax` suffix common to IKEA product names (KALLAX, EKBY). Pronounced "GROO-vax." It runs alongside [discogsography](https://github.com/SimplicityGuy/discogsography) on the home server and reads its collection data.

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
| Deployment host            | Runs the FastAPI backend and shares Postgres + Mosquitto    |
| ESP32 (per Kallax unit)    | LED driver — _future milestone, not in v1_                  |
| WS2812B LED strip per cube | Per-cube illumination — _future milestone, not in v1_       |

Initial deployment: two 4×4 IKEA Kallax units side-by-side (32 cubes total). The data model and UI accommodate additional units without schema change.

## 🧰 Stack

- **Backend** — Python 3.14 + FastAPI, deployed via Docker Compose alongside [discogsography](https://github.com/SimplicityGuy/discogsography) on the home server. Structured JSON logging via `structlog` + `orjson`.
- **Database** — Shared PostgreSQL instance; GRUVAX owns a dedicated `gruvax` schema — `profiles` + a per-profile `profile_collection` cache, refreshed by a staging-swap sync against discogsography's HTTP API (the v1-era read-only `gruvax.v_collection` cross-schema view was retired in migration 0009).
- **Frontend** — Single-page app served by the backend; runs fullscreen in Chromium kiosk mode on the Pi and is responsive enough to double as the mobile admin UI. Built with Vite 8 + React 19 + TypeScript.
- **Realtime** — Server-Sent Events, one channel per profile, for kiosk updates on boundary edits, sync completion, and device lifecycle changes.
- **LED control plane** — `aiomqtt` publishing to an internal `eclipse-mosquitto` broker; the contract is locked even though the hardware milestone (ESP32 firmware + WS2812B wiring) lands later.
- **Deploy** — Pull-based: `docker compose pull && docker compose up -d` using the pre-built `ghcr.io/simplicityguy/gruvax:latest` image from GitHub Container Registry. No build step required on the deployment host.
- **Metadata** — each profile connects with its own Fernet-encrypted Discogs PAT (personal access token) and syncs a local copy of its collection from the [discogsography](https://github.com/SimplicityGuy/discogsography) HTTP API; discogsography remains the canonical source of Discogs OAuth sync and the music graph, while GRUVAX runs its own full-text + trigram search over the local cache.

## ✨ Features

Shipped through the v2.1 milestone (v1.0 → v2.0 multi-user → v2.1 resilience/privacy/UX):

- **Configurable N×4×4 Kallax grid** UI — supports any number of side-by-side 4×4 units (currently 2).
- **Type-ahead search** across artist / title / label / catalog number, with sub-200 ms perceived latency and pg_trgm "did you mean" fallback.
- **Cube highlight on match** — primary cube + label-span secondary highlight + sub-cube position interval bar (interval may cross a cube boundary).
- **PIN-protected admin** with sliding-window session timeout — mobile-first, with a kiosk fallback that uses an in-app numeric keypad; a scannable QR code accompanies the 4-digit PIN.
- **Three boundary workflows** — manual entry with autocomplete + diff preview, guided setup wizard, CSV/YAML seed import. Every mutation goes through an append-only change log with one-tap undo.
- **Live kiosk updates** — admin boundary edits, sync completion, and device changes re-render the kiosk via SSE without a manual refresh.
- **Admin-configurable LED colors and brightness** per system state (label-span, position, error, setup, all-off).
- **Multi-profile / multi-user collections** — each household member connects their own Discogs PAT via a single-use, PIN-gated invite link; sync and search are isolated per profile.
- **Device pairing and lifecycle** — 4-digit-code kiosk pairing, per-device rename / reassign / revoke from the admin UI, and a persistent fingerprint cookie that survives a Pi reboot.
- **Offline detection** with an SSE-authoritative banner, auto-reconnect with backoff + jitter, and stale-data refresh on reconnect.
- **Privacy by default** — search history is session-only (never persisted server-side), aggregate-only usage stats (no query text), and a no-PIN "reset kiosk" affordance.
- **Shelf fill-overview** — an admin mini 4×4 grid that shades per-cube occupancy at a glance.
- **Docker Compose deployment** with healthchecks, log limits, and Alembic migrations.

Deferred to later milestones: real LED hardware integration (firmware + WS2812B wiring), screensaver / cover-art browse mode, periodic JSON export of boundaries to git, OAuth2 device-authorization grant for member self-connect (AUTH-01), service-worker offline cache.

## 🏛️ Architecture

The canonical design reference is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). It covers:

- **Data model** — `gruvax` schema tables, including `profiles` + the per-profile `profile_collection` sync cache
- **API surface** — all public `/api/*` and PIN-gated `/api/admin/*` endpoints
- **Position estimation** — two-level segment-aware interpolation and the `LocateResult` contract
- **LED contract** — MQTT topic structure, Pydantic payloads, `HighlightRegistry` TTL
- **Realtime** — SSE event types and the `EventBus` decoupling pattern
- **Observability** — `/api/health` subsystems, in-memory log/slow-query rings, `/api/admin/diagnostics`
- **Deploy** — Compose services, pull-based GHCR image, startup lifespan sequence, CI orchestration

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
- `just` task runner (`brew install just` or see [just.systems](https://just.systems))

### Quickstart

```bash
# 1. Copy the environment template and fill in the required secrets (see below)
cp .env.example .env

# 2. Build and start the full stack: api, gruvax-dev-pg, mosquitto, and the
#    fake-discogsography sibling used for local dev. The api container waits
#    for Postgres, runs Alembic migrations, and seeds the synthetic collection
#    + cube boundaries on first boot (GRUVAX_ENV=development, set by default
#    in .env.example).
just up

# 3. Open the kiosk
open http://localhost:8000
```

Type an artist, label, or catalog number (e.g. `Blue Note`, `BLP 1000`, or `ECM`).
The top result auto-highlights its cube. Tap other results to move the highlight.
Click the clear-X (×) to reset.

### Stop / Restart

```bash
# Stop and remove containers — does NOT delete volumes (keeps mosquitto + Postgres persistence)
docker compose down

# NEVER run `docker compose down -v` unless you intend to wipe the gruvax-dev-pg-data
# and mosquitto-data volumes. The -v flag deletes volumes.
```

### Running Tests Locally (outside Docker)

`just test` / `just migrate` run against `DATABASE_URL` directly (not through the Compose
network), so they need a bare Postgres reachable at `localhost:5432`. If the Compose stack
from `just up` is already running, its `gruvax-dev-pg` service publishes that port — but note
the `.env` copied from `.env.example` points `DATABASE_URL` at the Compose-network hostname
`gruvax-dev-pg`, which does not resolve from the host. Override the host for host-side runs:

```bash
DATABASE_URL=postgresql+psycopg://gruvax:gruvax@localhost:5432/gruvax just test
```

To start a standalone Postgres instead:

```bash
docker run -d --name gruvax-dev-pg \
  -e POSTGRES_USER=gruvax \
  -e POSTGRES_PASSWORD=gruvax \
  -e POSTGRES_DB=gruvax \
  -p 5432:5432 \
  postgres:18
```

### Environment Variables

Copy `.env.example` to `.env` and set your values. Three variables are hard-required —
compose refuses to start if they're missing (`${VAR:?}` guards): `SESSION_SECRET`,
`GRUVAX_SECRET_KEY`, and `GRUVAX_ADMIN_PIN`. The others fall back to compose-supplied
defaults when unset — in particular `DISCOGSOGRAPHY_BASE_URL` silently defaults to the
built-in fake dataset, so **always set it explicitly in production**:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+psycopg://gruvax:gruvax@gruvax-dev-pg:5432/gruvax` | SQLAlchemy/psycopg connection string (compose supplies the `gruvax-dev-pg` default when unset) |
| `SESSION_SECRET` | _(required, no default)_ | Signs the admin session cookie — boot-fail-if-missing |
| `GRUVAX_SECRET_KEY` | _(required, no default)_ | Fernet key for PAT-at-rest encryption — boot-fail-if-missing or malformed |
| `GRUVAX_ADMIN_PIN` | _(required by the `init-sync` container, no default)_ | Piped into `gruvax-sync` on first boot; **not** in `.env.example` — add it yourself (e.g. `1234` for local dev) |
| `DISCOGSOGRAPHY_BASE_URL` | `http://fake-discogsography:8004` | HTTP base URL of the discogsography API — compose defaults to the **fake** service when unset; set explicitly in production |
| `GRUVAX_ENV` | `development` (in `.env.example`) | `development` enables dev-only migration stubs + synthetic seeding; leave unset (`production`) for a real deployment |

The `api` service also derives `DATABASE_URL` from `GRUVAX_DB_USER` / `GRUVAX_DB_PASSWORD` /
`GRUVAX_DB_HOST` / `GRUVAX_DB_PORT` / `GRUVAX_DB_NAME` (see `compose.yaml`) if you'd rather
override the pieces than the full connection string.

**DB connectivity from inside Docker (Linux):** The `api` service container reaches the
bundled `gruvax-dev-pg` service by container name on the Compose network by default. If you
point it at a host Postgres instead via `host.docker.internal`, that resolves via the
`extra_hosts: host-gateway` line in `compose.yaml` on Linux; macOS/Windows have it built in.

### Secrets bootstrap

On first install (and any time a deployment needs to be rebuilt from scratch) `.env` needs
three secrets before `docker compose up` / `just up` will start: `GRUVAX_SECRET_KEY`,
`SESSION_SECRET`, and `GRUVAX_ADMIN_PIN`. The compose file uses `${VAR:?…}` substitution for
each and will refuse to start if any is missing or empty.

```bash
# Fernet key for PAT-at-rest encryption (URL-safe base64, 32 random bytes):
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#   -> GRUVAX_SECRET_KEY=<paste-the-output-here>

# Session-cookie signing secret:
python -c "import secrets; print(secrets.token_urlsafe(32))"
#   -> SESSION_SECRET=<paste-the-output-here>

# Admin PIN used by the init-sync container (any 4 digits for local dev):
#   -> GRUVAX_ADMIN_PIN=1234
```

Rotating `GRUVAX_SECRET_KEY` orphans every existing `profiles.app_token_encrypted` row —
treat the generated value as permanent per deployment. (A P4 utility will land for the
re-encrypt flow; until then, regenerate only as part of a full PAT re-provisioning.)

## 🗂️ Repository Layout

```
gruvax/
├── pyproject.toml           # Python project (uv-managed)
├── uv.lock                  # Python lockfile
├── compose.yaml             # Docker Compose: api + gruvax-dev-pg + mosquitto + fake-discogsography + init-sync
├── Dockerfile               # Multi-stage: frontend build + Python runtime
├── justfile                 # Task runner: test, lint, migrate, up, seed-dev
├── alembic.ini              # Alembic migration config
├── design/                  # Design language: tokens, logos, banners, spec
├── docs/                    # ARCHITECTURE.md, ops runbooks
├── mosquitto/               # Broker config (mosquitto.conf)
├── fixtures/                # Cube boundary YAML + golden test cases
├── migrations/              # Alembic migration versions
├── services/                # fake-discogsography sibling (local dev / CI)
├── src/gruvax/              # Backend: FastAPI + estimator + mqtt + sync
├── tests/                   # Unit, integration, property (Hypothesis)
└── frontend/                # Vite 8 + React 19 SPA (kiosk + admin)
```

## 🗺️ Planning Artifacts

This project develops via Beadhive/AGF — active work is tracked as beads (`bh work ...`), not raw git or ad-hoc docs; see the Workflow section in [`CLAUDE.md`](CLAUDE.md). The historical design + milestone trail from v1.0 through v2.1 lives in [`.planning/`](.planning/):

- [`PROJECT.md`](.planning/PROJECT.md) — what GRUVAX is, Core Value, constraints, key decisions
- [`intel/requirements.md`](.planning/intel/requirements.md) — requirements extracted from the design spec, by milestone
- [`ROADMAP.md`](.planning/ROADMAP.md) / [`MILESTONES.md`](.planning/MILESTONES.md) — the v1.0 → v2.0 → v2.1 milestone history
- [`research/`](.planning/research/) — stack, features, architecture, pitfalls, position-estimation algorithms, synthesis
- [`STATE.md`](.planning/STATE.md) — project memory as of the v2.1 close

## 📊 Status

**v2.1 shipped** (v1.0 MVP → v2.0 multi-user collections → v2.1 resilience/privacy/UX polish; see
[Planning Artifacts](#-planning-artifacts)). The Core Value is demoable: `just up` brings up the full
stack, the React SPA serves from `http://localhost:8000`, and typing a query lights up the right cube
in the 2×(4×4) grid.

Stack versions as shipped (reconciled from [`.planning/research/STACK.md`](.planning/research/STACK.md) against npm/PyPI):

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

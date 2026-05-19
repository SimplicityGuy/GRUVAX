# GRUVAX

A touchscreen kiosk for navigating a vinyl record collection stored in IKEA Kallax shelving, with RGB LED highlighting of the cube containing the matched record.

The name comes from Swedish *gruv* (groove) plus the `-ax` suffix common to IKEA product names (KALLAX, EKBY, etc.).

## How it works

1. Browse or search the collection on the 7" touchscreen mounted near the shelves.
2. Tap a record (or hit a search result).
3. The matching cube highlights in the on-screen grid — and, in a future hardware milestone, lights up on the physical shelf.
4. A sub-cube position estimate narrows down roughly where in the cube the record sits (label-span + interpolated interval).

The system relies on a *deterministic shelf ordering* — alphabetical by label, then by catalog number within label — so a record's position can be **computed** from a small per-cube boundary table rather than tagged per record. No RFID, no barcodes, no per-record stickers.

## Hardware

| Component                  | Role                                                       |
| -------------------------- | ---------------------------------------------------------- |
| Raspberry Pi 5             | Kiosk host — 4 GB RAM, 512 GB M.2 SSD                      |
| 7" touchscreen             | Primary UI surface, Chromium kiosk mode under Wayland/labwc |
| Home server (`lux`)        | Runs the FastAPI backend and shares Postgres + Mosquitto    |
| ESP32 (per Kallax unit)    | LED driver — *future milestone, not in v1*                  |
| WS2812B LED strip per cube | Per-cube illumination — *future milestone, not in v1*       |

Initial deployment: two 4×4 IKEA Kallax units side-by-side (32 cubes total). The data model and UI accommodate additional units without schema change.

## Stack

- **Backend** — Python 3.13 + FastAPI, deployed via Docker Compose alongside [discogsography](https://github.com/SimplicityGuy/discogsography) on the home server.
- **Database** — Shared PostgreSQL instance; GRUVAX owns a dedicated `gruvax` schema and reads discogsography's collection data through a read-only `gruvax.v_collection` view.
- **Frontend** — Single-page app served by the backend; runs fullscreen in Chromium kiosk mode on the Pi and is responsive enough to double as the mobile admin UI. Final framework choice lands in the UI design phase; the working baseline is Vite + React 19.
- **Realtime** — Server-Sent Events for kiosk updates on boundary edits.
- **LED control plane** — `aiomqtt` publishing to an internal `eclipse-mosquitto` broker; the contract is locked in v1 even though the hardware milestone (ESP32 firmware + WS2812B wiring) lands later.
- **Metadata** — comes from the [discogsography](https://github.com/SimplicityGuy/discogsography) project, which handles Discogs OAuth sync, full-text search, and the music graph.

## v1 Features

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

## Repository layout

> _The codebase has not yet been scaffolded. This section will be filled in as the backend, frontend, and supporting tooling are added during Phase 1 onward._

The planned top-level structure follows `.planning/research/ARCHITECTURE.md`:

```
gruvax/
├── pyproject.toml
├── compose.yaml
├── justfile
├── alembic.ini
├── mosquitto/                # broker config
├── migrations/               # Alembic
├── src/gruvax/               # backend (FastAPI + estimator + mqtt + events)
├── tests/                    # unit, integration (testcontainers), property (Hypothesis)
└── frontend/                 # Vite SPA serving kiosk + /admin routes
```

## Planning artifacts

This project is being built via the [Get Shit Done](https://github.com/SimplicityGuy/get-shit-done) workflow. The full planning trail lives in [`.planning/`](.planning/):

- [`PROJECT.md`](.planning/PROJECT.md) — what GRUVAX is, Core Value, constraints, key decisions
- [`REQUIREMENTS.md`](.planning/REQUIREMENTS.md) — 73 v1 requirements across 11 categories
- [`ROADMAP.md`](.planning/ROADMAP.md) — 7-phase vertical MVP plan
- [`research/`](.planning/research/) — stack, features, architecture, pitfalls, position-estimation algorithms, synthesis
- [`STATE.md`](.planning/STATE.md) — project memory and current focus

## Status

Planning is complete. Implementation begins with **Phase 1: First Search → Cube Highlight** — a typed query lighting the right cube on the touchscreen, end-to-end, against fixture-seeded boundaries before any admin UI exists.

No runnable application code in this repository yet.

## License

See [LICENSE](LICENSE). GRUVAX is licensed under [PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — free for research, personal, educational, and noncommercial use. Commercial use requires a separate license; see the Commercial Licensing section of `LICENSE`.

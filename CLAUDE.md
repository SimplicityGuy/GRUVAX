<!-- GSD:project-start source:PROJECT.md -->
## Project

**GRUVAX**

GRUVAX is a touchscreen kiosk plus REST API that helps the owner (and visiting friends) find any specific vinyl record in a ~3,000-record collection stored across multiple IKEA Kallax shelving units. Records are deterministically organized — alphabetical by Label, then by catalog number within label — so a record's physical position can be *calculated* rather than tracked per item. A search highlights the right cube on the kiosk's grid and (in a future milestone) lights it up on the physical shelves via WS2812B-style RGB LEDs.

**Core Value:** Type artist, title, label, or catalog number → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

### Constraints

- **Tech stack — Backend**: Python + FastAPI in this repo. Align Python and FastAPI versions with discogsography to share a dependency story.
- **Tech stack — Frontend**: Web stack (React + GSAP + Three.js/Pixi proposed) running in Chromium kiosk mode on the Pi. Final stack decision deferred to UI design phase.
- **Deployment**: Docker Compose on `lux`, sibling to discogsography. No second host for v1.
- **Database**: Shared Postgres instance with discogsography. GRUVAX owns a dedicated schema (`gruvax`); reads from discogsography's collection tables read-only.
- **Performance**: Type-ahead search round-trip ≤ ~200 ms perceived from keystroke to result.
- **Connectivity**: Home LAN only; no public exposure. Pi → `lux` link is the critical path.
- **Security**: Single PIN gates admin actions; session timeout after inactivity. No multi-user concerns.
- **Footprint**: Total hardware budget guidance from prior planning: ~$80–$150 (screen + Pi + initial LEDs). Software side aims to stay correspondingly small — no heavyweight services beyond what already runs on `lux`.
- **Repo hygiene**: The collection CSV and `background/` directory are local-only references; they must never be committed.
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## TL;DR
| Layer | Recommendation | Confidence |
|-------|----------------|------------|
| Backend language | Python 3.13 (match discogsography) | HIGH |
| Web framework | FastAPI 0.136.x | HIGH |
| DB driver | `psycopg` 3.2 (async) — match discogsography | HIGH |
| Migrations | Alembic 1.18.x with async template | HIGH |
| Config | `pydantic-settings` 2.x | HIGH |
| Package manager | `uv` 0.5+ (match discogsography) | HIGH |
| Lint/format | Ruff (match discogsography) | HIGH |
| Type check | mypy (match discogsography) | HIGH |
| Tests | pytest + pytest-asyncio + httpx + Hypothesis | HIGH |
| Frontend framework | **React 19** with the React Compiler (default); Svelte 5 / SolidJS as serious alternatives — re-examine in UI design phase | MEDIUM |
| Build tool | Vite 7.x (with Rolldown) | HIGH |
| Animation | GSAP 3.13 core + Framer Motion (`motion`) for layout; CSS for transitions | MEDIUM |
| Grid/canvas | Plain DOM + CSS Grid for v1; defer Pixi/Three.js until visual design demands it | MEDIUM |
| Realtime push | Server-Sent Events via `sse-starlette` (or built-in `fastapi.sse` in FastAPI 0.135+) | HIGH |
| MQTT broker | `eclipse-mosquitto:2.1-alpine` | HIGH |
| MQTT client (Python) | `aiomqtt` 3.x | HIGH |
| Auth | Starlette `SessionMiddleware` (signed cookies via `itsdangerous`) + a single PIN check route + sliding session TTL. Do **not** introduce `fastapi-users` for one PIN. | HIGH |
| Container | Multi-stage Dockerfile, `uv` in builder stage, `python:3.13-slim` runtime, non-root user | HIGH |
| Kiosk OS | Raspberry Pi OS Trixie (Debian 13), Wayland with `labwc` compositor, Chromium kiosk launched from `~/.config/labwc/autostart` and supervised by a `systemd --user` unit | HIGH |
## Recommended Stack — Backend
### Core
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.13.x | Runtime | Discogsography uses 3.13+. Avoiding a version split simplifies shared dev tooling, Docker base images, and any future code sharing. Python 3.13 is current stable; 3.14 is recent but `aiomqtt` and others have less production exposure on it. |
| FastAPI | 0.136.1 (April 2026) | HTTP framework + OpenAPI | Discogsography already uses FastAPI; consistent dev story. 0.135+ added first-class SSE (`fastapi.sse`) which is directly relevant to the realtime requirement. |
| Uvicorn | 0.32+ | ASGI server | The de facto FastAPI runner; works correctly with the long-lived SSE connections this app needs. |
| Pydantic | 2.13.x | Models, validation, OpenAPI | Required by FastAPI 0.136; v2 is the Rust-core version that's 5–50x faster than v1. |
| pydantic-settings | 2.x | Configuration | Standard partner to Pydantic v2 for env-var/.env-driven config. Validates at startup — config typos crash boot, not a request three hours later. |
### Database
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| PostgreSQL | 16+ (whatever discogsography runs) | Storage | Shared instance, dedicated `gruvax` schema. Read-only views/grants onto discogsography's `releases`/`artists`/`collection_items`. Same-host = lowest possible kiosk latency. |
| psycopg | 3.2+ | Async DB driver | **Match discogsography.** psycopg3 is the modern successor with native async support. asyncpg is ~5x faster in microbenchmarks but for a home-LAN kiosk with one user the absolute latency difference is sub-millisecond — operational consistency with discogsography wins. psycopg3 also has Row Factories that map cleanly to Pydantic models. |
| SQLAlchemy | 2.0.x (async) | Lightweight ORM / query builder | Cube boundary CRUD is small and well-suited to either ORM or hand-written SQL. SQLAlchemy 2.0's async + typed API is the path of least surprise and feeds Alembic autogenerate. Skip the ORM only if discogsography deliberately doesn't use one — then mirror its choice. |
| Alembic | 1.18.x | Migrations | The standard SQLAlchemy migration tool. Use the async template (`alembic init -t async`). Define naming conventions on the `Base` metadata to make autogenerate produce stable migration names. CI sanity check: `alembic upgrade head && alembic downgrade base && alembic upgrade head`. |
### Realtime / Messaging
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| sse-starlette | 2.x | SSE response class | Until FastAPI's built-in `fastapi.sse` is rock-solid, `sse-starlette` is the proven implementation. Handles ping/heartbeats and client-disconnect cleanup correctly. If on FastAPI ≥ 0.135 with no plugin friction, switch to `fastapi.sse` later — it serializes Pydantic on the Rust side. |
| aiomqtt | 3.x | MQTT client | v3 is pure asyncio (no paho-mqtt thread bridge). Idiomatic `async with Client(...)` and `await client.publish(...)`. Avoid `fastapi-mqtt` (extra abstraction over `gmqtt`) — direct `aiomqtt` is simpler to reason about for a publish-only stub. |
### Auth / Sessions
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Starlette `SessionMiddleware` | bundled | Signed session cookie | Already in Starlette/FastAPI, uses `itsdangerous` to sign cookies. For a single-PIN home-LAN app, this is exactly the right size. Set a short `max_age` (e.g., 600s) and refresh on activity. |
| itsdangerous | 2.2+ | Token signing | Indirect dependency of `SessionMiddleware`. Also useful directly for short-lived single-use admin links if ever needed. |
| passlib[argon2] | 1.7.4+ | Hash the admin PIN | Even for one PIN, don't store it in plaintext or compare via `==`. Hash with Argon2id and use `secrets.compare_digest` on the verification path. |
### Code Quality / Dev
| Tool | Purpose | Notes |
|------|---------|-------|
| Ruff (latest) | Lint + format | Match discogsography. Replaces flake8, black, isort, pyupgrade in one binary. |
| mypy | Static types | Match discogsography. Use `--strict` in CI for backend code. |
| pytest | Test runner | Standard. |
| pytest-asyncio | Async test support | Required because FastAPI handlers are async. |
| httpx | API tests | The `AsyncClient` is the modern standard for testing ASGI apps; FastAPI's `TestClient` is a Starlette wrapper around httpx anyway. |
| Hypothesis | Property-based tests | Specifically valuable for the position-estimation algorithm (see Testing section below). |
| pytest-cov | Coverage | Standard. |
| coverage[toml] | Backend for pytest-cov | Standard. |
| just | Task runner | Match discogsography. `justfile` for `just test`, `just lint`, `just up`, etc. |
## Recommended Stack — Frontend
### Core
| Technology | Version | Purpose | Why Default |
|------------|---------|---------|-------------|
| React | 19.x | UI framework | Largest ecosystem for the supporting libs we likely want (animation, virtualized lists, a11y primitives). The React Compiler shipped stable in October 2025 — auto-memoization eliminates most of the manual `useMemo`/`useCallback` overhead that historically made React slower than Solid/Svelte for animation-heavy UIs. Chromium on a Pi 5 has no problem with React's ~45 KB runtime. |
| TypeScript | 5.7+ | Types | Non-negotiable for a UI with REST + SSE + admin forms. |
| Vite | 7.x | Build tool + dev server | Default for everything except Next.js. Rolldown bundler (Rust) is now Vite's production bundler — fast cold builds, fast HMR. |
| React Router | 7.x | Routing | Kiosk view, admin login, admin boundary editor — distinct routes. |
| TanStack Query | 5.x | Server state | Caches typeahead results, manages SSE-invalidated keys cleanly. |
| Zustand | 5.x | Local state | Tiny (~1 KB), no boilerplate, perfect for "current selection", "admin mode", "offline banner state". Don't reach for Redux. |
### Animation
| Library | Version | Purpose | When |
|---------|---------|---------|------|
| GSAP core | 3.13.x | Cube-highlight choreography | MIT-licensed core is sufficient; the paid Club GSAP plugins (MorphSVG, SplitText, etc.) are **not** needed for this app's scope. GSAP runs outside React's render cycle, which is exactly what you want for the "search lands → cube glows" cinematic moment. |
| Framer Motion / `motion` | 12.x | Layout + presence transitions | MIT-licensed. Use for declarative React-level transitions (list re-orderings, mounting/unmounting modals). The two libraries coexist cleanly. |
| Plain CSS | n/a | Most state transitions | Cheapest possible: `transition: transform 200ms`. Reach for JS animation only when CSS can't express it. |
### Search UX primitives
| Library | Purpose |
|---------|---------|
| Fuse.js (only if backend fuzzy is insufficient) | Client-side fuzzy. Default plan: do search server-side via Postgres FTS for sub-200 ms RTT; only add Fuse if testing shows server search misses on typo-heavy input. |
| `cmdk` or `downshift` | Accessible combobox / typeahead primitive. `cmdk` (the Vercel Command Menu library) is the modern choice for keyboard-first typeahead. |
| `@tanstack/react-virtual` | Virtualize the results list if it ever exceeds ~50 visible rows. |
### Mobile admin
| Library | Purpose |
|---------|---------|
| react-hook-form | 7.x — form state without re-renders |
| Zod | 3.x — schema validation; can be derived from the same OpenAPI schema FastAPI exports |
### What NOT to use (frontend)
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Next.js / Remix | Server rendering offers nothing for a kiosk SPA served off a single LAN host. Adds build complexity. | Vite + React SPA |
| Webpack | Slower dev, slower builds, more config. | Vite |
| Redux | Heavy for the amount of state this app has. | Zustand |
| MobX | Same — overkill. | Zustand |
| jQuery / static GSAP-on-page | No build pipeline = harder kiosk caching + service worker story. | React + Vite |
| Three.js / React Three Fiber (in v1) | Pi 5 can do WebGL fine, but a 32-cube grid is a CSS layout problem. | CSS Grid + DOM |
| GSAP Club plugins | Paid. Not needed for the scope of v1. | GSAP core + CSS |
| Styled Components / Emotion | Runtime CSS-in-JS adds to React render cost. | Tailwind CSS 4 (zero-runtime utilities) or CSS Modules |
## Recommended Stack — Infrastructure
### Containerization
# syntax=docker/dockerfile:1.7
- BuildKit cache mounts for `~/.cache/uv` make subsequent builds seconds, not minutes.
- Non-root user (`gruvax`) is the 2026 baseline expectation.
- `uv sync --frozen` forces lockfile use — no surprise resolutions in CI/prod.
- Two `uv sync` stages: one before the source copy (lets the dependency layer cache between source-only changes), one after for the package itself.
### MQTT broker
| Technology | Image | Purpose | Why |
|------------|-------|---------|-----|
| Eclipse Mosquitto | `eclipse-mosquitto:2.1-alpine` (~9 MB) | Pub/sub broker for LED messages | Tiny footprint, single-threaded, handles 100k+ concurrent connections on one node — vastly more than needed. The "right size" for a home LAN broker between one publisher (GRUVAX) and a handful of ESP32 subscribers. EMQX exists for clustered, million-connection deployments — that's a strictly bigger problem than this. |
- Bind to a Compose network only — never expose 1883 to the LAN until the LED milestone introduces ESP32s.
- Enable persistence (`persistence true`, `persistence_location /mosquitto/data/`) so retained messages survive container restarts. For v1's stub, this is mostly future-proofing.
- Username/password auth even on internal network (one shared credential per device class).
### Frontend hosting
## Recommended Stack — Raspberry Pi Kiosk
| Concern | Choice | Rationale |
|---------|--------|-----------|
| OS | Raspberry Pi OS Trixie (Debian 13), 64-bit | Official supported release since Oct 2025. Includes the labwc compositor by default for Wayland sessions on Pi 5. |
| Display server | **Wayland with `labwc`** | Default for Pi 5 in Trixie. Hardware video acceleration through KMS works correctly. X11 still works but is the legacy path; the active development is Wayland. |
| Browser | Chromium (from Raspberry Pi OS repo, not snap/flatpak) | The packaged Chromium has the proprietary V4L2/MMAL bits configured. Same browser the Pi Foundation tests against. |
| Launcher | `~/.config/labwc/autostart` invoking a `start-kiosk.sh` script | `start-kiosk.sh` runs the browser with the right flags (`--kiosk`, `--noerrdialogs`, `--disable-infobars`, `--no-first-run`, `--password-store=basic`, `--ozone-platform=wayland`, `--app=http://lux.local:PORT/`). `--password-store=basic` avoids the keyring unlock dialog on boot. |
| Supervision / auto-restart | `systemd --user` unit that owns the Chromium process, with `Restart=always` and a small `RestartSec` | Browser crash or memory leak → automatic restart with clean logs via `journalctl --user`. More reliable than respawn loops in shell scripts. |
| Cursor hide | `seatd` + Wayland-native cursor hiding via labwc config | `unclutter` is X11-only and broken under Wayland. |
| Screen blanking | Disabled via labwc/Wayland idle settings | Black-screen-on-idle is in scope for v1 *as a product behavior* — implement at the app level (CSS+JS), not by letting the compositor blank the screen, so the offline banner stays reachable on touch. |
| On-screen keyboard | **Open issue.** `squeekboard` does not currently render above fullscreen Chromium under labwc. | If touch keyboard is required for kiosk admin fallback, mitigation options: (a) leave admin to the mobile UI; (b) build an in-app virtual keyboard in the SPA itself; (c) drop kiosk fullscreen flag and live with a window frame. Recommend (b) — the typing-heavy admin path is mobile-first per requirements; the kiosk admin fallback only needs limited input. **Flag for the UI/admin phase.** |
### Touchscreen calibration
## Testing the Position-Estimation Algorithm
| Tool | Purpose |
|------|---------|
| pytest | Runner |
| pytest-asyncio | If algorithm is exposed as an async endpoint test |
| Hypothesis | Property-based tests for invariants ("estimated position is always within the label-span"; "monotonic in catalog number for the same label"; "results are stable across normalization of catalog-number whitespace/case") |
| pytest fixtures (`@pytest.fixture(scope="session")`) | Load the ~3,000-row CSV once per test session |
| pytest.mark.parametrize | Drive per-label golden-result tests from a fixtures table |
| `pytest-benchmark` | Track 200 ms p95 regression for search → estimate path |
## Installation
# Backend: bootstrap with uv
# Frontend
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| psycopg3 (match discogsography) | asyncpg | If raw query/s ever becomes the bottleneck (5x microbenchmark advantage). Won't matter on a home LAN. |
| SQLAlchemy 2.0 async | Hand-written SQL + `psycopg` rows + `Pydantic` models | Acceptable for a schema this small; choose only if discogsography explicitly avoids SQLAlchemy. |
| Alembic | yoyo-migrations, dbmate, sqitch | Worth it only if you want migrations decoupled from the Python toolchain. Sticking with Alembic keeps the Python story unified. |
| Starlette `SessionMiddleware` | `fastapi-users`, hand-rolled JWT | `fastapi-users` if user management ever expands beyond one PIN. JWT if you ever expose the API beyond home LAN and want stateless tokens. Neither fits the v1 model. |
| React 19 (+ Compiler) | Svelte 5, SolidJS | Svelte/Solid if UI design phase shows extreme animation density and you want the smallest possible runtime on the Pi. Both are objectively faster per-update; both have meaningfully smaller ecosystems. |
| Vite 7 | Next.js, Remix | Only if SEO and SSR matter — they don't for a LAN-only kiosk. |
| GSAP core + Framer Motion | Anime.js, Theatre.js, React Spring | Anime.js is great but smaller community. Theatre.js is for design-tool-driven motion graphics (too much for this scope). React Spring is fine but Framer Motion's API is more familiar and similar feature coverage. |
| Eclipse Mosquitto | EMQX, HiveMQ, NanoMQ, VerneMQ | EMQX/HiveMQ are right when you need clustering or 100k+ connections. NanoMQ is interesting for ultra-constrained edge devices. None apply at this scale. |
| Server-Sent Events | WebSocket | WebSocket if the admin UI ever needs to *stream* edits back (collaborative editor style). For one-way "boundary changed, please refetch" SSE is strictly simpler. |
| Static files via FastAPI | Separate nginx container | nginx if the kiosk static assets ever need to be cached aggressively independent of API restarts. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Python 3.10 or 3.11 | Discogsography is on 3.13+; splitting versions adds maintenance for zero benefit. | Python 3.13 |
| Poetry (for this project) | Slower than `uv` for installs and locks. Discogsography uses `uv`. | `uv` |
| `pipenv` | Effectively abandoned. | `uv` |
| Pydantic v1 | EOL — many libraries have dropped support. | Pydantic v2 |
| psycopg2 | Legacy sync driver; no async. | psycopg 3 |
| Tortoise ORM / pony ORM / encode/databases | Smaller communities, async support more brittle. | SQLAlchemy 2.0 async |
| Manual SQL migrations / Flyway / Liquibase | Adds JVM or external tooling to a pure-Python project. | Alembic |
| Flask | Synchronous-first; would lose all the FastAPI infrastructure discogsography shares. | FastAPI |
| Django | Wrong size — full ORM, admin, migrations, templates — for a single-schema microservice. | FastAPI |
| `fastapi-users` | Multi-user auth machinery for a single-PIN app. | Starlette `SessionMiddleware` + PIN check |
| Hand-rolled JWT auth | More to get wrong than a signed cookie for a LAN app. | Starlette `SessionMiddleware` |
| `paho-mqtt` directly | Sync API; awkward bridge into FastAPI's async event loop. | `aiomqtt` 3.x |
| `fastapi-mqtt` | Extra abstraction over `gmqtt`; less direct than `aiomqtt`. | `aiomqtt` 3.x |
| EMQX (for this scale) | Enterprise-scale broker overhead; configuration surface dwarfs need. | `eclipse-mosquitto` |
| Webpack | Slow, complex config compared to Vite. | Vite |
| Create React App | Officially deprecated. | Vite + React |
| Redux Toolkit (for this app) | Too much ceremony for the amount of state. | Zustand |
| Three.js / Pixi.js (v1) | Solving a layout problem with a renderer. | CSS Grid + DOM |
| GSAP Club paid plugins | Cost without commensurate benefit at this scope. | GSAP core + CSS |
| Snap-packaged Chromium on Pi | Missing GPU integration. | `chromium-browser` from RasPiOS apt repo |
| X11 (on a fresh Pi 5 Trixie build) | Wayland is the default and where Pi Foundation invests now. | Wayland + labwc |
| `unclutter` (under Wayland) | X11-only; broken under Wayland. | Wayland cursor hiding via compositor config |
| Polling for kiosk → boundary updates | Wastes CPU on the Pi, adds steady network chatter. | SSE |
| Cookie-based session storage for *large* state | 4 KB cookie limit. | Cookie for session ID only; server keeps state in-memory or in Postgres. (Not an issue here — sessions are tiny.) |
| Pulling the collection CSV into the repo or any CI image | Explicit project constraint. | CSV stays gitignored, mounted from host or fetched in dev. CI uses a synthetic dataset. |
## Stack Patterns by Variant
- Add React Three Fiber + drei for declarative Three.js, OR
- Switch to a Pixi.js-based renderer for 2D-with-shader-effects
- In either case, re-validate FPS budget on the Pi 5 — these will not be free
- Drop SQLAlchemy from GRUVAX too; use raw `psycopg` async cursors with Pydantic mapping
- Keep Alembic regardless — it operates against the database, not against an ORM
- Migrate from `SessionMiddleware` + PIN to `fastapi-users` with email/password
- Add the OAuth provider story via `authlib` *only* if integrating with something external
- Stay on Mosquitto. EMQX's clustering is for thousands of concurrent device connections, not for a handful of ESP32s talking to one home server.
## Version Compatibility
| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `fastapi==0.136.x` | `pydantic>=2.7`, `starlette>=1.0.0` | 0.136.1 pinned Starlette 1.0.0; mind transitive upgrades. |
| `sqlalchemy==2.0.x` (async) | `psycopg[binary,pool]>=3.2` | Use `psycopg.AsyncConnection`; the SQLAlchemy URL prefix is `postgresql+psycopg://`. |
| `alembic==1.18.x` | `sqlalchemy>=2.0` | Init with `alembic init -t async`. |
| `aiomqtt==3.x` | Python 3.10+, no paho dependency | Drop-in once configured; uses `mqtt5` sans-io internally. |
| `pydantic-settings==2.x` | `pydantic>=2.7` | Lockstep with Pydantic v2 minor releases. |
| `sse-starlette==2.x` | `starlette>=1.0` | Watch FastAPI 0.135+ to migrate to built-in `fastapi.sse` later. |
| `vite==7.x` | Node.js 20.19+ or 22.12+ | Node 18 is EOL; Pi 5 runs Node 20 fine. |
| React 19 + React Compiler | `react@^19`, `react-dom@^19`, `babel-plugin-react-compiler` (or SWC plugin in Vite) | Compiler 1.0 stable since Oct 2025. |
| Chromium kiosk | Raspberry Pi OS Trixie, labwc compositor | `--ozone-platform=wayland`; package via apt, not snap. |
| Mosquitto 2.1-alpine | MQTT 3.1, 3.1.1, 5 | Use MQTT 5 for retained topics and shared subscriptions. |
## Discogsography Alignment Notes
| Item | Constraint | Rationale |
|------|------------|-----------|
| Python 3.13 | Hard match | Shared dev tooling, single Docker base layer story. |
| FastAPI | Soft match (same library, version can drift minor) | Both stay on the same major; FastAPI minor versions are usually safe to differ. |
| psycopg3 | Hard match | Shared Postgres instance; discogsography already runs the migration story. |
| uv | Hard match | Lockfile format and CI scripts can be near-identical. |
| Ruff + mypy | Hard match | Identical lint config makes mental context-switching painless. |
| Auth | No alignment needed | Discogsography uses Discogs OAuth; GRUVAX uses a local PIN. Different problem. |
| Neo4j | Skip entirely for GRUVAX | GRUVAX doesn't need a graph view for v1. Future "find related releases by label-mate" could leverage it through discogsography's MCP, not by adding the driver here. |
| RabbitMQ | Skip | Discogsography uses RabbitMQ for ingestion pipelines. GRUVAX's pub/sub is LED-shaped — MQTT is the right tool. |
## Sources
### Authoritative
- [FastAPI on PyPI](https://pypi.org/project/fastapi/) — verified 0.136.1, Python ≥ 3.10 — HIGH
- [FastAPI release notes (GitHub)](https://github.com/fastapi/fastapi/releases) — SSE support in 0.135.0, Python 3.14t support in 0.136.0 — HIGH
- [Pydantic on PyPI](https://pypi.org/project/pydantic/) — 2.13.4 latest (May 2026) — HIGH
- [Eclipse Mosquitto on Docker Hub](https://hub.docker.com/_/eclipse-mosquitto) — `2.1-alpine` ~9 MB, current tag — HIGH
- [Vite 7.0 announcement](https://vite.dev/blog/announcing-vite7) — Node 20.19+ requirement, Rolldown bundler — HIGH
- [React Compiler 1.0 announcement](https://react.dev/blog/2025/10/07/react-compiler-1) — Stable Oct 2025 — HIGH
- [Alembic Cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) — async template patterns — HIGH
- [discogsography README (GitHub)](https://github.com/SimplicityGuy/discogsography) — verified Python 3.13+, FastAPI, psycopg3, uv, Ruff, mypy, just — HIGH
### Comparative / Verified-with-multiple-sources
- [SSE vs WebSockets for real-time FastAPI (Medium, 2026)](https://medium.com/@rameshkannanyt0078/fastapi-real-time-api-websockets-vs-sse-vs-long-polling-2026-guide-ce1029e4432e) — MEDIUM, cross-checked with FastAPI SSE docs
- [Mosquitto vs EMQX comparison (Cedalo, 2026)](https://www.cedalo.com/blog/mosquitto-vs-emqx-an-honest-comparison-for-iot-teams) — MEDIUM
- [uv vs Poetry comparison (multiple 2026 sources)](https://www.danilchenko.dev/posts/uv-vs-pip-vs-poetry/) — MEDIUM, confirmed by discogsography choice
- [SolidJS vs Svelte vs React reactivity (PkgPulse, 2026)](https://www.pkgpulse.com/guides/solidjs-vs-svelte-5-vs-react-reactivity-2026) — MEDIUM
- [GSAP vs Framer Motion (Annnimate, 2026)](https://www.annnimate.com/blog/gsap-vs-framer-motion-vs-react-spring) — MEDIUM
- [psycopg3 vs asyncpg benchmarks (Fernando Arteaga)](https://fernandoarteaga.dev/blog/psycopg-vs-asyncpg/) — MEDIUM
### Pi-kiosk specifics
- [Raspberry Pi Kiosk Display System (TOLDOTECHNIK GitHub)](https://github.com/TOLDOTECHNIK/Raspberry-Pi-Kiosk-Display-System) — labwc autostart pattern — MEDIUM
- [Automated RPi Web Kiosk Setup (benswift.me, July 2025)](https://benswift.me/blog/2025/07/16/automated-rpi-web-kiosk-setup-in-2025/) — recent, working pattern — MEDIUM
- [labwc + Chromium kiosk discussion (raspberrypi.org forums)](https://forums.raspberrypi.com/viewtopic.php?t=390764) — community-validated patterns — MEDIUM
- [Squeekboard fullscreen issue (labwc/labwc#2926)](https://github.com/labwc/labwc/issues/2926) — known open issue, drives the touch-keyboard recommendation — HIGH (it's an open bug)
### MQTT / Realtime
- [aiomqtt on GitHub (empicano)](https://github.com/empicano/aiomqtt) — v3 sans-io rewrite — HIGH
- [sse-starlette on PyPI](https://pypi.org/project/sse-starlette/) — current SSE implementation — HIGH
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

## Design Language

- **Use the Nordic Grid design language for all user-facing work** — kiosk UI, admin UI, logos, favicons, generated images, slide/diagram styling, and docs. Do not invent new visual styles or one-off palettes.
- **Source of truth is `design/`** — read `design/gruvax-design-language.md` (the spec) before building any UI or visual asset. Tokens live in `design/gruvax-design-tokens.css` and `design/gruvax-design-tokens.json`; logo marks and rendered banners live in `design/` and `design/assets/`.
- **Consume tokens; never hardcode hex.** Wire `gruvax-design-tokens.css` / `.json` into the frontend as the contract between design and code. Core palette: IKEA blue `#0051A2` (`--gruvax-blue`), LED yellow `#FFDA00` (`--gruvax-yellow`), off-white `#F7F9FC` (`--gruvax-off-white`).
- **Type system is three fonts** — Barlow Condensed (display & wordmark), Space Grotesk (UI body), DM Mono (catalog numbers, bin positions, counts). Never use Barlow Condensed for body copy.
- **The Kallax cube (4×4) is the atomic UI unit.** Cell states (dim / lit / hover / selected / empty) come from the tokens; lit cells are always yellow with the LED glow — never recolor a lit cell.
- **Motion: LED physics.** Lit state springs on (overshoot), fades off (smooth); general UI feedback under ~150 ms. Use the transitions documented in the spec rather than ad-hoc easings.
- **Accessibility constraints from the spec.** Blue-on-white is AAA (body-safe). Yellow-on-blue and blue-on-yellow are ~3.1:1 — large text (18px+) or decoration only, never body copy.
- **Voice & tone.** Labels are ALL CAPS (Barlow Condensed 700, tracked wide); instructions are sentence case; error messages use plain language, no technical jargon.
- **Logo usage.** Standard (white-ground) variant on light backgrounds, Reversed (blue-ground) on dark; never recolor the border independently of the wordmark, remove the yellow rule, or add shadows/glows to the mark itself.

## Documentation

- **Diagrams use Mermaid** — every diagram in docs goes in a ` ```mermaid ` block, never ASCII art or prose arrows.
- **The main `README.md` follows the discogsography pattern** — centered header block, theme-aware banner via `<picture>` (`design/assets/banner_dark.png` / `banner_light.png`), shields.io badges, a bold tagline, and a centered nav line, then emoji-prefixed sections.
- **GitHub banners are committed as PNGs** (`design/assets/banner_{light,dark}.png`) rendered from the SVG sources, so the Barlow Condensed wordmark renders correctly instead of falling back to a system font.

<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, `.github/skills/`, or `.codex/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->

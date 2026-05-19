# Project Research Summary — GRUVAX

**Project:** GRUVAX
**Domain:** Touchscreen kiosk (Chromium on Raspberry Pi 5) + FastAPI REST/SSE service + MQTT-stubbed RGB LED control surface, deployed via Docker Compose alongside an existing `discogsography` service that shares Postgres. Single-owner home LAN; primary purpose is to compute and surface the physical cube location of any record in a ~3,030-record vinyl collection stored across IKEA Kallax shelving.
**Researched:** 2026-05-18 (5 parallel streams)
**Confidence:** HIGH on backend, infrastructure, MQTT, SSE, kiosk supervision, schema, and contract design. MEDIUM on frontend (final aesthetic deferred to UI design phase). MEDIUM on the choice of position-estimation algorithm (the *contract* is HIGH; the *algorithm* is empirically determined per INTERPOLATION.md §7).

This synthesis integrates five research files: [STACK.md](./STACK.md), [FEATURES.md](./FEATURES.md), [ARCHITECTURE.md](./ARCHITECTURE.md), [PITFALLS.md](./PITFALLS.md), and the GRUVAX-specific fifth stream [INTERPOLATION.md](./INTERPOLATION.md) on sub-cube position estimation.

---

## Executive Summary

GRUVAX is a single-purpose physical-location finder kiosk: type a record's artist/title/label/catalog#, see the right cube highlighted on a 7" touchscreen (and, in a future hardware milestone, lit by RGB LEDs on the shelves) within ~200 ms perceived. The core architectural insight is that the user hand-sorts records *deterministically* (alphabetical by label, then by catalog# within label), so a record's physical position can be **computed** from a tiny per-cube boundary table (~32 rows for two Kallax units) instead of being tagged per-record. This is the project's load-bearing decision and the reason GRUVAX avoids the RFID-reliability failure mode of its closest prior art (the Hackaday recordShelf project).

The recommended approach is a Python 3.13 + FastAPI 0.136.x backend (matching `discogsography` for shared dev tooling), psycopg 3.2 async with a dedicated `gruvax` schema in the shared Postgres, Alembic migrations, Starlette `SessionMiddleware` + Argon2id-hashed single PIN for admin, `sse-starlette` for live admin→kiosk updates, `aiomqtt` 3.x publishing to `eclipse-mosquitto:2.1-alpine` for the LED contract (no `ports:` exposure in v1 — broker is Compose-internal until hardware arrives), and a single Vite + React 19 (with React Compiler) SPA serving both kiosk and `/admin` route trees. The Pi 5 runs Raspberry Pi OS Trixie with the labwc Wayland compositor and Chromium in `--kiosk` mode supervised by a `systemd --user` unit. The single most-depended-on internal module is the **position estimator**, which is intentionally treated as a swappable algorithm behind a fixed dataclass contract (`LocateResult`) so the rest of v1 can ship against a stub while the algorithm iterates.

The dominant risks are (1) **catalog-number string comparison silently breaking natural sort** — empirically, 35.6% of the user's multi-record labels would be ordered incorrectly by raw-string comparison alone, making a numeric-aware normalized comparator a *precondition*, not a refinement (Pitfall 1, INTERPOLATION §3); (2) **discogsography schema drift breaking GRUVAX search** — mitigated by routing all reads through a single `gruvax.v_collection` view plus a startup health probe (Pitfall 5); (3) **the on-screen keyboard `squeekboard` does not currently render above fullscreen Chromium under labwc** (labwc/labwc#2926 is an open upstream bug), forcing the kiosk admin fallback to ship an in-app virtual numeric keypad (Pitfall 4); (4) **letting the position-estimator research stream block the rest of v1** — the contract is fixed in week one, the stub estimator runs against the real contract from day one, and the real algorithm lands at its own pace (Process Pitfall P7). The aggregate stats from the actual CSV — median records-per-label of 1, 26.6% singleton labels, 57.2% sparse multi-record labels with median gap 12 between owned catalog numbers, no label large enough to fill even one cube (max label = 51 records vs ~95 records/cube average) — drive specific algorithm-design implications captured in §Position Estimation below.

---

## Key Findings

### Recommended Stack

The stack is settled with HIGH confidence on backend and infrastructure, MEDIUM on frontend (the design phase will revisit). Backend strongly aligns with `discogsography` to keep dev tooling unified and the shared Docker base layer story simple.

**Core technologies (exactly as pinned in STACK.md):**

| Layer | Choice | Why |
|---|---|---|
| Python runtime | **3.13.x** | Hard match with discogsography |
| Web framework | **FastAPI 0.136.1** (April 2026) | 0.135+ has first-class SSE; matches discogsography |
| ASGI server | **Uvicorn 0.32+** | Standard FastAPI runner; long-lived SSE friendly |
| DB driver | **psycopg 3.2+** (async) | Match discogsography; native async; Pydantic-friendly row factories |
| Migrations | **Alembic 1.18.x** (async template) | Standard SQLAlchemy companion; reversible migrations |
| ORM | **SQLAlchemy 2.0.x async** | Lightweight for a handful of tables; feeds Alembic autogenerate |
| Config | **pydantic-settings 2.x** + **Pydantic 2.13.x** | Startup validation; matches FastAPI 0.136 transitive requirement |
| MQTT broker | **eclipse-mosquitto:2.1-alpine** (~9 MB) | Right-sized for one publisher + handful of future ESP32s |
| MQTT client | **aiomqtt 3.x** | Pure asyncio, no paho thread bridge |
| SSE | **sse-starlette 2.x** | Proven impl; correct ping/heartbeat; consider `fastapi.sse` later |
| Auth | Starlette `SessionMiddleware` + Argon2id PIN hash via **passlib[argon2] 1.7.4+** + **itsdangerous 2.2+** | Right size for single-PIN home LAN; explicitly *not* fastapi-users |
| Lint/format/types | **Ruff + mypy** | Match discogsography |
| Tests | **pytest + pytest-asyncio + httpx + Hypothesis + pytest-benchmark** | Hypothesis is load-bearing for the estimator (INTERPOLATION §7) |
| Package manager | **uv 0.5+** | Match discogsography |
| Task runner | **just** | Match discogsography |
| Frontend framework | **React 19** + React Compiler (stable Oct 2025) | Largest ecosystem; React Compiler eliminates most manual memoization |
| Build tool | **Vite 7.x** (Rolldown) | Node 20.19+ required; Pi runs Node 20 fine |
| Routing/state/server-cache | React Router 7.x, **Zustand 5.x**, **TanStack Query 5.x** | Zustand is tiny (~1 KB) and right-sized; explicitly *not* Redux |
| Animation | **GSAP 3.13 core** (MIT, no paid plugins) + **motion (Framer Motion) 12.x** + plain CSS | GSAP for the "selection lands" choreography; CSS for everything else |
| Grid render | Plain DOM + CSS Grid | A 32-cube grid is a layout problem, not a renderer problem — explicitly *not* Three.js/Pixi for v1 |
| Search UX | `cmdk` (combobox primitive); server-side Postgres FTS + `pg_trgm` | Skip client-side fuzzy unless server search proves insufficient |
| Forms | React Hook Form 7.x + Zod 3.x | Admin forms are typing-heavy |
| Pi OS / display | **Raspberry Pi OS Trixie (Debian 13)**, Wayland with **labwc** compositor | Wayland is the default; `--ozone-platform=wayland` for Chromium |
| Browser | **Chromium from apt** (not snap) with `--kiosk` flags | Snap is missing GPU integration |
| Supervision | `systemd --user` with `Restart=always`, `StartLimitIntervalSec=120`, `StartLimitBurst=5` | Restart loops with rate limit (Pitfall 9) |

**Explicit "do not use" calls preserved from STACK.md:** Poetry/pipenv, Pydantic v1, psycopg2, Tortoise/Pony ORM, manual SQL migrations, Flask/Django, fastapi-users (for v1), hand-rolled JWT, paho-mqtt directly, fastapi-mqtt, EMQX, Webpack, Create React App, Redux Toolkit, Three.js/Pixi (for v1), GSAP Club, Snap Chromium, X11, `unclutter`, kiosk polling instead of SSE, and — importantly — *committing the collection CSV* (PROJECT.md constraint).

---

### Expected Features

PROJECT.md fixes v1 Active scope; FEATURES.md categorized 10 surfaces of feature space (search, cube UX, admin, LED, realtime, offline, observability, audio/discovery, multi-user/privacy, backup). The most product-shaping conclusions:

**Must have (table stakes — anchored to PROJECT.md Active scope):**

- Type-ahead search over artist/title/label/catalog# with ≤200 ms perceived RTT (server-side Postgres FTS + 100–150 ms debounce + React 19 `useDeferredValue`)
- Ranked results list with tap-to-select; top result auto-highlights
- Configurable N×4×4 cube grid render; single-cube highlight; label-span highlight (multi-cube secondary layer); sub-cube position bar (interval overlay, may cross cube boundary)
- Empty-cube visual state (distinct from populated)
- Cube boundary data model with sanity validation against `v_collection`
- Admin PIN-gated routes (Argon2id, Starlette `SessionMiddleware`, sliding-window TTL, 5–10 min idle); mobile-first admin, kiosk fallback
- Three boundary entry workflows: manual form (with autocomplete from `collection_items`), guided setup wizard, CSV/YAML seed import (with diff preview before commit)
- Admin-configurable color and brightness per LED state (label-span, position, error, setup) — never hard-coded
- LED endpoint contract with publish-by-cube, publish-by-label-span, publish-by-sub-cube interval (normalized 0..1 within cube — firmware owns physical pixel count), brightness control, "all off" panic, and diagnostic sequence. Real ESP32 firmware is *not* v1; the contract is the v1 deliverable.
- Offline banner: kiosk detects loss of `lux`, disables search, shows banner, reconnects with backoff; reconnection success animation
- Docker Compose deployment on `lux`; shared Postgres; named `gruvax` schema; read-only grant on discogsography tables
- Healthcheck (`/api/health`) including DB and MQTT reachability + a `discogsography_view_check` field; Alembic-driven migrations on startup; structured JSON logging
- **Boundary change log (append-only history table)** — this is the keystone for undo, audit, the wizard's atomic-commit story, and future backup features; FEATURES.md explicitly recommends building it from day one because four future features depend on it
- Session-scoped recently-pulled list on the kiosk (privacy floor: never persisted server-side, never visible across visitors)

**Should have (differentiators with strong empirical support):**

- "Did you mean" via `pg_trgm` (`similarity()` + GIN index) — typo tolerance is high-value at low cost
- Catalog-number-first parsing heuristic (numeric-leading query boosts catalog# field)
- Live admin→kiosk update via SSE (the "wow" moment of the realtime layer; falls out cheaply once SSE is wired)
- Hover/tap-on-cube reveals contents (reverse lookup — "what's in cube 18?")
- Reshuffle wizard with atomic change set + Idempotency-Key (named recurring workflow per PROJECT.md "~5–10 min reshuffle maintenance")
- Auto-suggest boundary midpoint *by collection index* (not by catalog-number-space midpoint — see Pitfall 22)
- "Did you mean" near-miss suggestion on boundary save (FEATURES.md Cat 3 reuses the same trgm path)

**Defer (v1.x / v2+):**

- Real LED hardware (ESP32 + WS2812B) — explicit PROJECT.md backlog
- Screensaver / browse / cover-art slideshow — explicit PROJECT.md Out-of-Scope; Process Pitfall P5 warns against accidentally scoping this in
- Periodic JSON export of boundaries to git — PROJECT.md Out-of-Scope (Postgres backups suffice for v1)
- Multi-user auth / RFID — explicitly excluded
- 30 s preview, Last.fm scrobble, "related releases via Neo4j" — Category 8 deferred
- Cube-zoom view, usage heat-map, animated reshuffle preview, density-imbalance reshuffle suggestion, fill-level indicator — Category 2 future

**FEATURES.md explicitly flagged "RECONSIDER for v1" — requirements phase decides:**

1. **Service-worker cached search results** (~1 day of work; materially better offline UX) — Cat 6 differentiator
2. **Per-visitor PIN with isolated session** (cheap nicety if a partner/family member joins; architecture already supports it via `admin_sessions.client_label`) — Cat 9 differentiator
3. **Animated reshuffle preview / diff visualization** — promote earlier if reshuffles happen as often as PROJECT.md implies

---

### Architecture Approach

A single-instance FastAPI service (the SSE event bus and the boundary cache are in-process, so multi-replica is explicitly an anti-pattern) serves both the REST API under `/api/*` and the static SPA bundle at `/`. The SPA is one Vite bundle with two route trees (`/` kiosk + `/admin/*`). Postgres is shared with `discogsography`: GRUVAX owns the `gruvax` schema (RW) and reads `discogsography.*` through a single `gruvax.v_collection` view (RO grant — the *enforced* boundary; the view is the *surveyable* one). Mosquitto runs as a sibling container with no host port mapping in v1 (Compose-internal only); the hardware milestone adds the `ports:` mapping. Live admin→kiosk updates use SSE through an in-process event bus that any handler can publish to; never round-trip kiosk updates through Mosquitto (Anti-Pattern 1). Position estimation is a swappable algorithm behind a fixed dataclass contract (`LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}`) with hard latency budget p95 ≤ 50 ms (CPU-only, no DB calls — boundaries pre-loaded into an in-memory cache invalidated by `boundary_changed` events).

**Major components:**

1. **kiosk SPA** (Chromium on Pi) — search UI, cube grid, position-bar overlay, offline banner, session-scoped recently-pulled, idle blanker
2. **admin SPA** (same bundle, `/admin/*` routes) — PIN entry, boundary editor, wizard, CSV/YAML upload, color/brightness picker, undo history, diagnostics
3. **gruvax-api** (FastAPI) — REST + SSE, PIN session check, boundary CRUD, change-log writes, position-estimate dispatch, MQTT publish (fire-and-forget with 250 ms timeout)
4. **position estimator** (Python module inside gruvax-api) — fixed contract; algorithm is the 5th-stream research output (INTERPOLATION.md)
5. **Mosquitto** broker — pub/sub fan-out, retained "current state" topics with `message_expiry_interval` (Pitfall 3), persistence across restarts, LWT for `server/hello`
6. **Postgres** (shared with discogsography) — `gruvax` schema RW, `discogsography.*` RO via `v_collection` view + explicit grant
7. **discogsography** (external, already running) — Discogs sync, FTS, `releases`/`artists`/`collection_items` — *strict read dependency*, pinned in Compose stack
8. **future ESP32 LED firmware** — dormant integration target; subscribes to `gruvax/v1/leds/#`

**Six load-bearing architecture patterns** (verified against current `aiomqtt` and `sse-starlette` via Context7):

1. Single MQTT client in lifespan, dependency-injected (`reconnect=True`, `clean_start=False`, `session_expiry_interval=86400`, `keep_alive=30`, LWT `gruvax/v1/server/hello` retained)
2. In-process event bus for SSE fan-out (`asyncio.Queue(maxsize=64)` per subscriber, drop-on-full)
3. Boundary cache with SSE invalidation (32 rows in memory, recomputed on `boundary_changed`)
4. View as the read-only contract surface (`gruvax.v_collection` is the single point of contact with discogsography)
5. History-as-append-only-source-of-truth (every mutation writes to `boundary_history`; revert is a new row, never destructive)
6. Double-submit cookie CSRF (HttpOnly session cookie + non-HttpOnly `gruvax_csrf` echoed as `X-CSRF-Token`)

**The critical path to a demoable v1 is ~6.5 days** (per ARCHITECTURE.md): Postgres schema + view + grant → FastAPI skeleton with `/health`/`/version` → `/api/units` and `/api/cubes/...` → `/api/search` (FTS only, defer trgm) → **stub estimator behind the real `/api/locate` contract** → Vite scaffold + search box + cube grid → Pi kiosk autostart. The real estimator algorithm slots in behind the contract without breaking changes.

**API surface (rough, from ARCHITECTURE.md):** Public — `GET /api/search`, `GET /api/locate`, `GET /api/units`, `GET /api/cubes/{u}/{r}/{c}`, `POST /api/illuminate`, `GET /api/events` (SSE), `GET /api/health`, `GET /api/version`. Admin (session-gated, CSRF-enforced on mutating methods, Idempotency-Key on bulk endpoints) — `POST /api/admin/login`, `/logout`, `GET /session`, `GET/PUT /admin/cubes/...`, `POST /admin/cubes/bulk`, `POST /admin/cubes/validate`, `POST /admin/cubes/suggest`, `GET /admin/history`, `POST /admin/history/{id}/revert`, `GET/PUT /admin/settings`, `POST /admin/leds/diagnostic`, `POST /admin/leds/off`, `GET /admin/export/boundaries.yaml`, `GET /admin/diagnostics`.

---

### Position Estimation (5th Research Stream — INTERPOLATION.md)

This is GRUVAX-specific and the highest-leverage internal module. Stats below are first-party measurements computed directly from the local Discogs export (3,030 records, gitignored).

**Key empirical findings driving algorithm choice:**

- **No label is large enough to fill a cube.** Largest label = 51 records; average cube = ~95 records. Therefore every label fits within at most one cube interior plus possibly a sliver of the adjacent cube. `label_span` is **1 cube ~90% of the time, 2 cubes ~10% of the time, ≥3 cubes effectively never**. Sub-cube interpolation, not multi-cube spans, is the dominant complexity.
- **26.6% of records are the only record from their label** (805 singleton labels of 1,215 total). These collapse to a degenerate case: `k=1`, sub-cube interval is the full cube width (or a single tick — see Pitfall 21), confidence tagged `"singleton"`.
- **35.6% of multi-record labels disagree between raw-string sort and numeric-aware sort.** This is the single most important number in the entire research and the empirical floor on Pitfall 1's blast radius. A correctly normalized comparator is **a precondition, not a refinement**.
- **57.2% of multi-record labels with ≥3 owned records are *sparse* (density < 0.1)** with median gap 12 between consecutive owned catalog numbers. The user's collection is dominated by sparse, gappy multi-record labels — which means linear-by-catalog-#-value interpolation (§4.2) is poorly fit and index-based interpolation (§4.1) or gap-weighted index (§4.10) is the right default.
- **41.5% of multi-record labels have mixed separators; 34.8% have multiple alpha-prefix families within one label; 21.2% have mixed alpha case.** Parser must handle all these uniformly with the same code path used by the boundary-save validator.
- **One label has a `numeric_range` of 5×10¹²** (a 13-digit barcode-as-catalog#). Numeric-aware comparators must cap digit-run length or detect barcodes and demote them.
- **13.0% of records have a multi-value catalog field** (commas); **18.9% have a multi-label field**. The estimator must pin behavior: recommend "first value for sort/compare; preserve full string for display" with property-test enforcement.
- **0.1% of records have no digits at all** in their catalog#. Comparator needs a deterministic sentinel for these.

**Parser approach taxonomy (INTERPOLATION §3) — five strategies surveyed:**

| Strategy | Verdict |
|---|---|
| A. Pure numeric regex | Insufficient — ignores prefix |
| B. Structured `(prefix, number, suffix)` split | Works for ~63% of catalog shapes; needs extension |
| **C. Token-stream split (alternating `[A-Za-z]+` / `\d+` with type-tagged tuple compare)** | **Recommended general form**; handles every shape in §2.3 |
| D. `natsort` library (`alg=ns.IGNORECASE \| ns.SIGNED`) | Battle-tested; adds a third-party dep that the project otherwise wouldn't need |
| E. Custom layered normalizer per Pitfall 1 | Converges in practice toward strategy C |

INTERPOLATION explicitly says: pick C or D based on implementer preference; pin behavior with the same property-test suite either way.

**Mandatory pre-comparison normalization (applies to all strategies, applied uniformly to stored boundary endpoints AND the queried record):** `strip()` → `unicodedata.normalize("NFKC", ...)` → `str.casefold()` (not `lower()`) → collapse separator runs `re.sub(r"[\s\-_./]+", " ", ...)` → for multi-value (commas), keep first part for sort/compare and preserve full string for display → empty/`none`/`n/a` mapped to a documented sentinel.

**Algorithm candidates surveyed (INTERPOLATION §4) — 10 approaches with uniform comparison schema:**

The candidates were not concluded into "the winner is X." Instead, the research arrived at an **empirical methodology**: build the parser, then build §4.1 (linear-by-index) + §4.8 (no-interp baseline), then build the A/B harness (§7.4), then run candidates against the real CSV and let the numbers decide.

**Direct recommendations for the planning phase (INTERPOLATION §8.2):**

1. **Build the parser first** (~1 day) — shared infrastructure: the boundary save validator, every algorithm, and every test depend on it.
2. **Implement §4.1 (linear by index) + §4.8 (no-interpolation fallback) initially.** Together they form a useful product floor; §4.8 doubles as the estimator-timeout fallback path.
3. **Build the A/B harness (§7.4) before committing to any further algorithm.** Without it, all comparison is speculation.
4. **Defer §4.10 (density-weighted) until §4.1 is observed in practice.** It targets the dominant data shape and is the obvious next experiment if §4.1 feels off on sparse labels.
5. **Hard-no on §4.7 (lookup table)** — reverses PROJECT.md's "position is computed, not stored" decision; ARCHITECTURE.md Anti-Pattern 2.
6. **Hard-no on §4.5 (KNN) and §4.9 (isotonic) for v1** — statistical sledgehammers for data too sparse (median k=1) to materially outperform §4.1.
7. **The tiered cascade (§5.1) is the realistic target architecture once v1 ships** — dispatch by label shape, with per-tier confidence values feeding the UI's position-bar attenuation.
8. **Confidence is part of the algorithm choice, not an afterthought** — singleton=low, multi-prefix-routed-to-index=medium, dense+hybrid=high, timeout=zero.

**Edge cases enumerated (INTERPOLATION §6):** singleton (`k=1`), pure-alpha catalog, placeholder (`none`/`n/a`), multi-value catalog, multi-label record, multi-prefix within label, mixed separators, mixed case, varying digit lengths, barcode-style 13-digit catalog, no covering boundary, label legitimately spanning two cubes, boundary points at phantom record. Each has a specific handling rule pinned in INTERPOLATION.

**Validation methodology (INTERPOLATION §7):** parser unit + property + golden tests, algorithm unit + property + benchmark tests, boundary-save validator using the same comparator, reverse-direction sanity sample. ~13 golden cases enumerated covering every distribution-shape category. CI uses a shape-matching synthetic dataset (50 labels, 200 records); local-only runs use the full 3,030-record CSV.

---

### Critical Pitfalls

Top severities from PITFALLS.md (Pitfall 1-6 are Critical):

1. **Pitfall 1 — Catalog-number string comparison silently breaks natural sort.** Empirically 35.6% of multi-record labels are mis-sorted by raw-string comparison. Prevention: estimator owns the comparator (not the DB); store display values verbatim, normalize at compare time; Hypothesis property on the seed CSV's golden list; boundary save runs the same comparator. *Reconciled with INTERPOLATION.md — these documents agree completely and reference each other.*
2. **Pitfall 2 — Boundary points at a record that no longer exists in the collection** (owner sells a record). Prevention: pre-validate boundary edits against `v_collection`; tolerant trigram near-miss for "did you mean"; periodic `phantom_boundary_count` diagnostic; the wizard's `suggest` endpoint walks `v_collection`, never catalog-number space (Pitfall 22).
3. **Pitfall 3 — Mosquitto retained-state messages persist beyond useful life** (test publishes from v1 stub haunt the hardware milestone six months later). Prevention: set `message_expiry_interval` on retained publishes; `POST /api/admin/leds/off` publishes `retain=True, payload=b''` to clear retained state idiomatically (not just an "off" command); per-environment topic prefix `gruvax/v1/dev/leds/...` vs `gruvax/v1/leds/...`.
4. **Pitfall 4 — squeekboard does not render above fullscreen Chromium under labwc** (open upstream bug labwc/labwc#2926). Prevention: build an in-app virtual numeric keypad in the SPA; treat squeekboard as not-available; keep kiosk PIN numeric-only.
5. **Pitfall 5 — discogsography schema migration breaks `v_collection` and search dies.** Prevention: startup view-health probe (`SELECT 1 FROM gruvax.v_collection LIMIT 1`) reports `discogsography_view_check: failed` in `/api/health`; pin discogsography to a tag in Compose; CI integration test against real discogsography schema; subscribe to discogsography release notes; recovery is a one-line view migration.
6. **Pitfall 6 — `instance_id` vs `release_id` confusion in the LED publish path.** Prevention: never use bare `id` field names; Pydantic models reject ambiguity at the boundary; search returns both fields explicitly; integration test with a duplicated-release_id fixture.

**Major pitfalls (selected):** half-finished reshuffle leaves cubes inconsistent (Pitfall 7 — atomic bulk endpoint + Idempotency-Key + localStorage persist); SSE reverse-proxy buffering kills live updates (Pitfall 8 — `X-Accel-Buffering: no`, `Cache-Control: no-store`, default 15 s ping); Chromium kiosk restart loop (Pitfall 9 — `StartLimitIntervalSec=120, StartLimitBurst=5`, ssh + tty1 fallback, minimal-mode SPA bootstrap); connection pool exhaustion under SSE + concurrent search (Pitfall 10 — SSE endpoint has *no* `Depends(get_db)`; uses only the in-process event bus); CSRF on admin not enforced (Pitfall 13 — double-submit cookie pattern); discogsography sync staleness hides "just-added records" (Pitfall 15 — surface in admin diagnostics + kiosk banner if >7 days); animations that look great in dev feel laggy on the Pi 5 (Pitfall 16 — animate transform+opacity only, no `box-shadow`, test on actual hardware).

**Minor pitfalls (selected):** dark theme + touchscreen fingerprints unreadable in real lighting (Pitfall 17); color-blind admin defaults (Pitfall 18 — primary=warm yellow, span=deep purple, *brightness as information*, color-blind preview in picker, distinct animation); stale SPA bundle after redeploy (Pitfall 19 — `index.html` `no-store`, hashed assets `immutable`); single-record-label rendered as zero-width bar (Pitfall 21 — render as tick when interval < 0.02); auto-suggested midpoint picks an empty zone (Pitfall 22); unattended kiosk admin session (Pitfall 23 — hard cap on session lifetime + Lock button + `visibilityState` listener).

**Process pitfalls (PITFALLS.md §"Project / Process"):** P1 over-engineering admin before search loop works; P2 building estimator without the real data; P3 designing LED endpoints without imagining the firmware; P4 deferring offline behavior; P5 accidentally scoping the screensaver; P6 treating discogsography as "free" when its schema is a moving target; **P7 letting the position-estimator stream block the rest of v1 — fix the contract in week 1, ship the rest behind the stub.**

---

## Cross-Stream Reconciliation

A few places where the streams could appear to disagree but in fact converge:

- **Service-worker cached results — v1 or v1.x?** FEATURES.md flagged as "RECONSIDER for v1" (Cat 6 differentiator, ~1 day of work). ARCHITECTURE.md treats it as a v1 *or* v1.x decision (Open Architectural Question §5). PITFALLS.md treats deferring offline behavior as Process Pitfall P4 but doesn't insist on service worker specifically. **Reconciliation:** the *connectivity state machine* (banner, disabled search, reconnection animation) must land in v1 — it's PROJECT.md Active scope. The *service-worker cache* is a separable v1-or-v1.x decision the requirements phase decides. They are not the same thing.
- **Per-visitor PIN — v1 or future?** FEATURES.md Cat 9 flagged as RECONSIDER. ARCHITECTURE.md confirms the data model already supports it (`admin_sessions.client_label`). PROJECT.md is silent. **Reconciliation:** architecturally cheap; requirements phase decides whether the *UX* is worth shipping. The schema does not need to change either way.
- **YAML or JSON for boundary import/export?** FEATURES.md leans YAML. ARCHITECTURE.md leaves it open (Q §1). **Reconciliation:** both are cheap; pick one; the requirements phase calls it.
- **PIN hash in env var or DB?** ARCHITECTURE.md leaves it open (Q §7); Anti-Pattern 6 says "store the Argon2id *hash* in `gruvax.settings`, seeded via a one-shot bootstrap command." **Reconciliation:** DB-seeded with a bootstrap CLI is the recommended path; env-var-of-hash is acceptable; env-var-of-plaintext is the anti-pattern.
- **Position-estimator algorithm choice.** No stream "recommends" a winner; INTERPOLATION explicitly hands the decision to the empirical A/B harness against the real CSV. **Reconciliation:** there is no disagreement to reconcile — the methodology is the answer.

A few places where a feature that *could* look like a differentiator in one document is flagged as a pitfall in another, but they're actually compatible:

- **Auto-suggest boundary midpoint** is a FEATURES.md Cat 3 differentiator AND Pitfall 22. The *feature* is "suggest a boundary"; the *pitfall* is "suggest in catalog-number space instead of collection-index space." Implement the feature with the pitfall's prevention rule.
- **"Did you mean" / trigram fuzzy** is a FEATURES.md Cat 1 differentiator AND is reused for Pitfall 2 near-miss boundary suggestion. Same `pg_trgm` infrastructure, two surfaces.
- **Recently-pulled list** is a FEATURES.md Cat 1 differentiator AND a Cat 9 anti-feature when persisted server-side. The differentiator is session-scoped client-side only; the anti-feature is the persistent-server-side variant. Same name, different scope.

---

## Implications for Roadmap

Based on combined research, the recommended phase structure flows directly from ARCHITECTURE.md's dependency graph and the "demoable in ~6.5 days" critical path, with INTERPOLATION.md's "build parser first" recommendation grafted onto the foundation:

### Phase 1 — Foundation (DB schema + FastAPI skeleton + view + grants + lifespan)

**Rationale:** Nothing downstream builds without the Postgres schema, the `gruvax.v_collection` view, the read-only grant, and a FastAPI skeleton with lifespan-managed DB pool + MQTT client + settings + `/health`/`/version`. This is also where Pitfall 5's startup view-health probe and Pitfall 14's volume-permissions verification land.
**Delivers:** Running container with healthcheck green; Alembic migrations producing initial schema; one-shot bootstrap CLI for the PIN hash; documented Compose pattern; CI integration test against a real discogsography schema.
**Avoids:** Pitfall 5 (view-health probe), Pitfall 11 (Mosquitto persistence volumes from day one), Pitfall 14 (volume permissions on fresh-host first boot), Pitfall 20 (Compose `logging` directives from day one).
**Research flag:** Standard patterns — minimal new research needed.

### Phase 2 — Parser + position-estimator contract + stub estimator + search

**Rationale:** Per INTERPOLATION.md §8.2, the parser is shared infrastructure that the boundary save validator, every algorithm candidate, and every test depend on. Pinning the parser early prevents Pitfall 1 from leaking into every other surface. The estimator *contract* (dataclasses, error semantics, latency budget) is the swappable interface; a stub estimator implementing only §4.8 ("no interpolation — cube only") behind that contract unblocks every downstream feature.
**Delivers:** `parse_key()` + comparator with Hypothesis property suite + golden tests; `LocateResult` contract in `src/gruvax/estimator/contract.py`; stub estimator returning plausible-but-trivial values; `GET /api/locate` wired; `GET /api/search` via Postgres FTS (defer trgm to a later phase).
**Avoids:** Pitfall 1 (parser with property tests from day one), Process Pitfall P2 (parser uses the real CSV locally; CI uses shape-matching synthetic), Process Pitfall P7 (contract is fixed; algorithm can iterate later).
**Research flag:** **Already research-deep via INTERPOLATION.md.** The remaining work is implementation. The A/B harness (§7.4) lives here as scaffolding for Phase 6.

### Phase 3 — Cube grid UI + frontend scaffold + offline state machine (kiosk happy path)

**Rationale:** Once `/api/locate` returns *something* (even the stub), the front-end can build the cube grid, single-cube highlight, label-span highlight, sub-cube position bar, search box, and offline banner. ARCHITECTURE.md prescribes one Vite bundle with two route trees; this phase builds the kiosk tree. Process Pitfall P4 says offline behavior must land here, not later.
**Delivers:** Vite + React 19 + Tailwind + Router + Zustand + TanStack Query scaffold; SearchBox + ResultsList + CubeGrid + CubeHighlight + SubCubeBar + OfflineBanner; SSE consumer wired to Zustand connectivity slice; recently-pulled list (session-scoped, client-only).
**Avoids:** Pitfall 4 (in-app numeric keypad component built here for later admin use), Pitfall 16 (animation testing on actual Pi 5 + 7" screen — hardware-in-the-loop frame budget check before stakeholder sign-off), Pitfall 17 (test in actual mounting location), Pitfall 18 (color-blind-safe defaults; brightness-as-information), Pitfall 21 (`SubCubeBar.tsx` tick render for `interval < 0.02`), Process Pitfall P4 (offline state machine lands with SSE, not bolted on).
**Research flag:** **UI design phase** runs in parallel here. STACK.md is honest that final frontend direction is deferred; the recommendations are defensible defaults.

### Phase 4 — Admin auth + boundary CRUD + history + manual entry workflow

**Rationale:** Now that the kiosk happy-path is demoable, the next gate is letting the owner enter boundary data. Admin PIN auth + Starlette `SessionMiddleware` + CSRF middleware + Argon2id hash unlock the admin route tree. Manual boundary entry (form per cube with autocomplete from `v_collection`) is the simplest of the three workflows.
**Delivers:** `POST /api/admin/login`, `/logout`, `GET /session`; session middleware + double-submit CSRF; `GET/PUT /api/admin/cubes/...`; `POST /api/admin/cubes/validate`; `boundary_history` append-only writes; Change PIN endpoint; rate-limited login; admin shell + login page + boundary editor + history view.
**Avoids:** Pitfall 2 (validate endpoint), Pitfall 6 (Pydantic models with explicit field names), Pitfall 12 (Change PIN + session revocation), Pitfall 13 (CSRF middleware), Pitfall 23 (hard cap + Lock button + `visibilityState` listener).
**Research flag:** Standard patterns. No new research.

### Phase 5 — Reshuffle wizard + CSV/YAML import + bulk endpoint + auto-suggest

**Rationale:** Wizard is `L` complexity per FEATURES.md and the largest remaining admin feature. Atomic bulk save + Idempotency-Key + localStorage persist (Pitfall 7) cluster here. CSV/YAML import shares the validate + diff-preview infrastructure.
**Delivers:** `POST /api/admin/cubes/bulk` (atomic, Idempotency-Key); guided wizard UI with progress indicator; CSV/YAML upload + diff preview + per-row error reporting; `POST /api/admin/cubes/suggest` (walks `v_collection`, never catalog-number space — Pitfall 22); `POST /api/admin/history/{id}/revert`; `GET /api/admin/export/boundaries.yaml`.
**Avoids:** Pitfall 7 (atomic bulk + localStorage persist + resume UX), Pitfall 22 (suggest algorithm).
**Research flag:** Standard patterns.

### Phase 6 — Position estimator iteration (the algorithm itself)

**Rationale:** With the contract fixed since Phase 2 and the A/B harness scaffolded, this phase runs the empirical algorithm selection per INTERPOLATION.md §8.2: implement §4.1 (linear-by-index), compare against §4.8 (no-interp baseline) on the real CSV, measure per distribution-shape bucket, and decide whether to add §4.10 (density-weighted) or defer it. The tiered cascade (§5.1) is the eventual target if measurements warrant.
**Delivers:** §4.1 implementation; A/B harness with per-shape error reporting; pytest-benchmark CI gate at p95 ≤ 50 ms; confidence calibration per distribution-shape tier; Hypothesis properties for monotonicity, span containment, cosmetic-invariance.
**Avoids:** Pitfall 1 (Hypothesis property on the seed CSV's golden list), Process Pitfall P2 (real CSV locally, synthetic in CI).
**Research flag:** **Already research-deep via INTERPOLATION.md.** No additional research; this is execution + empirical iteration.

### Phase 7 — LED contract + MQTT publish path

**Rationale:** Per Process Pitfall P3, the LED contract must be designed *as if firmware exists* so the hardware milestone doesn't inherit an awkward API. The `aiomqtt` lifespan, topic tree, retained-state expiry, LWT, "all off" clearing, and diagnostic sequence all land here. Fire-and-forget publish wrapper with 250 ms timeout (Anti-Pattern 4 prevention).
**Delivers:** `POST /api/illuminate`, `POST /api/admin/leds/diagnostic`, `POST /api/admin/leds/off`; aiomqtt single-client lifespan; retained-state topics with `message_expiry_interval`; LWT for `server/hello`; per-environment topic prefix; admin color/brightness settings UI; documented LED contract README.
**Avoids:** Pitfall 3 (message_expiry + clear-retained "all off"), Pitfall 11 (named volumes for persistence), Process Pitfall P3 (mock-firmware pseudocode review of the contract).
**Research flag:** Standard patterns (aiomqtt + Mosquitto well-trodden; verified via Context7 in STACK.md/ARCHITECTURE.md).

### Phase 8 — Operational polish: diagnostics, sync staleness, slow-query log, deployment runbook

**Rationale:** The "operations and maintenance" surface — admin diagnostics page, sync staleness banner, slow-query log, kiosk runtime image, ssh + tty1 fallback, systemd unit hardening, log rotation, the "looks done but isn't" verification pass.
**Delivers:** `GET /api/admin/diagnostics` (sync staleness, phantom boundary count, slow queries, pool stats, disk usage, MQTT broker status, recent log lines); kiosk sync-staleness banner; minimal-mode SPA bootstrap; build-hash auto-reload; Compose `logging` directives; runbook.
**Avoids:** Pitfall 9 (kiosk restart loop hardening), Pitfall 10 (pool stats surfacing), Pitfall 15 (sync staleness UX), Pitfall 19 (build-hash auto-reload + cache headers), Pitfall 20 (log volume).
**Research flag:** Standard patterns. The runbook is a deliverable, not a research item.

### Phase Ordering Rationale

- **Foundation first** because nothing builds without schema + view + grant. The view-health probe lives here so Pitfall 5 is mitigated from day one.
- **Parser + contract + stub estimator before any UI** because Pitfall 1 leaks into every downstream surface if the comparator isn't right, and because Process Pitfall P7 says the contract must be fixed before the rest of v1 can run.
- **Kiosk happy-path UI third** because once `/api/locate` returns *something*, the demoable v1 is just frontend work; this is the ~6.5-day critical path. The full real estimator algorithm comes later in Phase 6.
- **Admin core fourth** to unlock data entry; ARCHITECTURE.md's "history-as-append-only" is the keystone that future features (undo, audit, backup, atomic wizard) all share.
- **Wizard + bulk fifth** to make reshuffles atomic-and-undoable; Pitfall 7's prevention rule clusters here.
- **Estimator algorithm sixth** because the empirical A/B harness needs real data + real boundaries; that requires the admin tools to exist so boundaries can be entered.
- **LED contract seventh** because the contract design needs ARCHITECTURE.md's normalized 0..1 sub-cube interval, which depends on the estimator's contract being settled. (Phase 7 could move earlier given parallelism — it doesn't strictly *depend* on Phase 6 — but the schedule pressure points the other way.)
- **Operational polish last** because diagnostics need every other surface to exist to surface their state.

### Research Flags

**Phases that should NOT need additional research (already deep):**
- Phase 1 (foundation) — STACK + ARCHITECTURE settle every choice
- Phase 2 (parser + contract + stub) — INTERPOLATION §3-§4 is the research; this is execution
- Phase 4 (admin core) — well-trodden patterns
- Phase 5 (wizard + import) — DSpace batch-edit prior art + FEATURES.md
- Phase 6 (estimator algorithm) — INTERPOLATION.md is the research; iteration is empirical
- Phase 7 (LED contract) — Context7-verified aiomqtt + Mosquitto patterns
- Phase 8 (ops polish) — boring infrastructure

**Phases that should consider lightweight phase-research during planning:**
- **Phase 3 (frontend / UI design)** — STACK.md is explicit that final aesthetic + final framework call (React vs Svelte 5 vs SolidJS) is deferred to UI design; if extreme animation density or sub-16 ms budgets matter, the framework call may flip. Run a *short* UI design pass and revisit framework choice if the design demands it.
- **Phase 6** (only if §4.1 measurement shows accuracy issues) — INTERPOLATION explicitly says "defer §4.10 until §4.1 has been observed in practice"; if measurements warrant, a *focused* density-weighted refinement is the next empirical step.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack — backend, infra, MQTT, SSE, kiosk supervision | **HIGH** | STACK.md cross-checks PyPI, GitHub release notes, Vite/React announcements, Context7-verified aiomqtt + sse-starlette, and aligns explicitly with discogsography's settled choices |
| Stack — frontend framework | **MEDIUM** | Final aesthetic deferred to UI design phase; recommendations are defensible defaults; React 19 + Compiler is a strong default but a SolidJS/Svelte 5 pivot is acknowledged as legitimate if design demands it |
| Features — v1 scope categorization | **HIGH** | Anchored to PROJECT.md explicit Active / Out-of-Scope lists |
| Features — differentiator framing | **MEDIUM** | Small niche product category; anchors from analogous domains (LibraryThing, Discogs apps, library kiosks, pick-to-light); the closest direct prior art (recordShelf) failed differently than GRUVAX is designed |
| Architecture — component boundaries, data flow, schema, contract design | **HIGH** | STACK + FEATURES settle most decisions; Context7 verified aiomqtt and sse-starlette patterns explicitly |
| Architecture — frontend route topology + state shape | **MEDIUM** | Default shape that survives reasonable design moves; UI design phase may shuffle |
| Pitfalls — category-specific dangers | **HIGH** | All anchored to STACK/FEATURES/ARCHITECTURE + Context7-verified library behavior; every prevention strategy references a concrete GRUVAX surface |
| Pitfalls — position estimation (Pitfall 1 + 2 + 22) | **HIGH** (contract-level); algorithm-level pitfalls are MEDIUM because the algorithm is empirically determined |
| Position estimation — aggregate stats (INTERPOLATION §2) | **HIGH** | Computed directly from the local CSV (3,030 records); first-party measurements |
| Position estimation — parsing taxonomy (INTERPOLATION §3) | **HIGH** | Survey covers every shape observed in §2.3 |
| Position estimation — algorithm choice | **MEDIUM** | Per-algorithm accuracy claims depend on the user's actual hand-arranged shelf, which is data we don't yet have; the *right way to pick* is empirical via the A/B harness |

**Overall confidence:** **HIGH** on what to build and how; **MEDIUM** on which specific position-estimation algorithm wins — and INTERPOLATION.md is explicit that this is *correctly* a MEDIUM because the answer requires empirical comparison against real boundaries the owner has yet to set.

---

## Open Questions (Consolidated from All Five Streams)

The requirements / planning phases must address these before scope is locked. Each is preserved verbatim in scope from its source stream; this section consolidates them.

### From STACK.md

- **On-screen keyboard for kiosk admin fallback.** STACK explicitly flagged squeekboard+labwc#2926 as a live bug and recommended option (b) "build an in-app virtual keyboard in the SPA" — this collides with PITFALLS Pitfall 4 prevention rule (same conclusion). Confirm with the requirements phase that the in-app keypad is the v1 commitment.

### From FEATURES.md (explicitly flagged "RECONSIDER for v1")

- **Service-worker cached search results** (~1 day of work; materially better offline UX). Cat 6 differentiator. Requirements decide v1 vs v1.x.
- **Per-visitor PIN with isolated session.** Cat 9 differentiator. Schema already supports it; UX decision only.
- **Animated reshuffle preview / boundary diff visualization.** Cat 2 future. Reconsider for v1 if reshuffles are as frequent as PROJECT.md implies.

### From ARCHITECTURE.md (Open Architectural Questions)

1. **YAML or JSON for boundary import/export?** Recommend YAML; cost of supporting both is small.
2. **Is the per-record search-counter table worth shipping in v1, or defer?** Cat 7 differentiator with Cat 9 privacy guardrail.
3. **Idempotency-Key behavior on bulk endpoints under partial overlap** (two admin clients submit overlapping bulk changes with different idempotency keys hitting the same cube).
4. **Should `/api/locate` cache by `release_id` at HTTP layer?** Recommend not; revisit if profiling warrants.
5. **Service worker on the kiosk in v1, v1.x, or not at all?** (Mirrors FEATURES.)
6. **Frontend served from FastAPI `StaticFiles` or separate nginx?** Default FastAPI for v1.
7. **PIN hash location — env var or DB?** Recommend DB (`gruvax.settings`) seeded via bootstrap CLI.
8. **Per-visitor PIN in v1 or future?** (Mirrors FEATURES.)
9. **OpenAPI client generation vs hand-written fetch.** Decide in design.
10. **Touch keyboard for kiosk admin fallback.** Architecture-indifferent UX decision. (Mirrors STACK + PITFALLS.)

### From PITFALLS.md (Process Pitfalls embedded in the planning conversation)

- P1–P7 are not "open questions" but reminders that the roadmap must order things correctly. P7 in particular ("don't let the estimator stream block the rest of v1") is binding on the phase ordering.

### From INTERPOLATION.md §8.1 (binding on requirements; the owner is the source of truth)

1. **Does the user's hand-arranged shelf follow catalog-# density or uniform spacing?** Binary that picks between §4.1 (uniform) and §4.10 (gap-weighted). Resolved only by owner hand-curating ~20 records' true positions and comparing.
2. **For multi-prefix labels (34.8% of multi-record labels), does the owner shelve all prefixes together or in prefix-grouped sub-runs?** Affects parser sort correctness; can only be answered by inspection during the first reshuffle wizard run.
3. **How does the owner treat the multi-value catalog field?** As "first-value" or "either-pressing"?
4. **How does the owner treat the multi-label field (18.9% of records)?** First-label only, or shelved under whichever is more prominent? Default assumption: first-label.
5. **Is there a confidence threshold below which the UI should show *no* sub-cube highlight at all** (just the cube)? UX call feeding back into algorithm choice.

---

## Sources

All five research files include their own detailed source lists. This section aggregates only the highest-confidence cross-cutting references.

### Authoritative (Context7-verified or first-party)

- **`/empicano/aiomqtt`** (Context7) — lifespan pattern, `reconnect=True`, `clean_start=False`, `session_expiry_interval`, LWT, retained-message semantics
- **`/sysid/sse-starlette`** (Context7) — default 15 s ping, `X-Accel-Buffering: no`, `EventSourceResponse`, nginx config
- **discogsography README** (https://github.com/SimplicityGuy/discogsography) — Python 3.13+, FastAPI, psycopg3, uv, Ruff, mypy, just alignment
- **FastAPI PyPI / release notes** — 0.136.1 (April 2026); SSE support in 0.135.0
- **Pydantic PyPI** — 2.13.4 latest (May 2026)
- **React Compiler 1.0 announcement** (Oct 2025) — stable
- **Vite 7.0 announcement** — Node 20.19+ requirement, Rolldown bundler
- **Eclipse Mosquitto Docker Hub** — `2.1-alpine` ~9 MB current tag
- **labwc/labwc#2926** — open upstream bug; squeekboard fullscreen issue (drives Pitfall 4)
- **`RWlodarczyk-collection-20260519-0257.csv`** (local, gitignored) — first-party measurement source for all INTERPOLATION §2 statistics

### Comparative / verified-with-multiple-sources

- recordShelf (Hackaday) — direct prior art for "Pi + WS2812B + Flask + Discogs JSON" pattern; informed the case *against* per-record RFID tagging
- pg_trgm "did you mean" guide (Viget) — typo-tolerant search feasibility
- TanStack Query invalidation guide — SSE-driven invalidation pattern
- OWASP CSRF cheat sheet — double-submit cookie pattern justification
- DSpace batch metadata editing — CSV-upload diff/preview pattern
- natsort PyPI + GitHub (8.4.x, April 2025) — alternative parser strategy D

### Project-internal cross-references

- `/Users/Robert/Code/public/GRUVAX/.planning/PROJECT.md` — scope, constraints, key decisions
- `/Users/Robert/Code/public/GRUVAX/.planning/research/STACK.md` — every technology choice
- `/Users/Robert/Code/public/GRUVAX/.planning/research/FEATURES.md` — feature taxonomy + reconsider flags
- `/Users/Robert/Code/public/GRUVAX/.planning/research/ARCHITECTURE.md` — component boundaries, contract design, patterns 1–6, anti-patterns 1–7
- `/Users/Robert/Code/public/GRUVAX/.planning/research/PITFALLS.md` — 23 numbered pitfalls + process pitfalls P1–P7
- `/Users/Robert/Code/public/GRUVAX/.planning/research/INTERPOLATION.md` — parser taxonomy, 10 algorithm candidates, validation harness, open questions for the owner

---

*Research synthesized: 2026-05-19*
*Ready for requirements scoping and roadmap creation.*

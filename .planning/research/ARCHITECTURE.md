# Architecture Research — GRUVAX

**Domain:** Touchscreen kiosk + REST API + MQTT-stubbed LED control surface, sibling to an existing `discogsography` service on a single home server (`lux`). Shared Postgres, dedicated `gruvax` schema, read-only contract against discogsography tables.
**Researched:** 2026-05-18
**Confidence:** HIGH on component boundaries and data flow (STACK.md + FEATURES.md settle most decisions). HIGH on Docker Compose / MQTT topology. HIGH on the FastAPI SSE + aiomqtt patterns (verified via Context7 against current versions). MEDIUM on the frontend route/state shape — final aesthetic and route topology are deferred to the UI design phase; structure here is a defensible default that survives reasonable design moves.

---

## TL;DR — Component Boundaries

| Component | Owns | Talks to | Does Not Own |
|---|---|---|---|
| **kiosk SPA** (Chromium on Pi) | search UI, cube grid render, position-bar overlay, offline banner, session-scoped recently-pulled, idle blanker | `gruvax-api` (REST + SSE) | LED hardware (transparent — API call returns immediately) |
| **admin SPA** (same bundle, separate route tree under `/admin`) | PIN entry, boundary edit forms, wizard, CSV/YAML upload, color/brightness picker, undo history view, diagnostics page | `gruvax-api` (REST + SSE) | Direct DB access of any kind |
| **gruvax-api** (FastAPI) | all HTTP/SSE endpoints, PIN session check, boundary CRUD, change-log writes, position-estimate dispatch, MQTT publish | Postgres (`gruvax` schema RW; `discogsography` schema RO), Mosquitto | LED firmware behavior (publishes and forgets) |
| **position estimator** (Python module inside `gruvax-api`) | takes a release row → returns `{cube, label_span, sub_cube_interval}` | reads cube boundaries + collection items | **algorithm is a separate research stream** — this doc fixes the *contract*, not the implementation |
| **Mosquitto** (broker) | pub/sub fan-out, retained "current state" topics, persistence across restarts | `gruvax-api` (publish), future ESP32s (subscribe) | message semantics (broker is dumb pipe) |
| **Postgres** (shared with discogsography) | all persistent state | `gruvax-api`, discogsography (own schema) | nothing leaks across schema |
| **discogsography** (separate project, already running) | Discogs sync, FTS-indexed `releases`/`artists`/`collection_items` | its own consumers; GRUVAX reads it but does not write | GRUVAX-specific concerns (boundaries, LEDs, kiosk) |
| **ESP32 LED firmware** (future milestone) | physical LED state | Mosquitto (subscribe) | API surface |

---

## System Overview

### High-Level Topology (current v1, with future ESP32 dashed)

```mermaid
flowchart LR
  subgraph LAN["Home LAN (192.168.x.x)"]
    subgraph clients["Clients"]
      Pi["Raspberry Pi 5<br/>Chromium kiosk<br/>(7&quot; touch, Wayland/labwc, kiosk SPA)"]
      Phone["Owner phone / laptop<br/>(mobile admin SPA)"]
    end

    subgraph lux["lux (Docker Compose host)"]
      subgraph dgs["discogsography (existing stack)"]
        DGSAPI["FastAPI + Discogs sync<br/>Neo4j (not used by GRUVAX v1)"]
      end

      subgraph PG["Postgres 16+"]
        DGSSchema["discogsography schema<br/>(FTS + trgm) — RO to gruvax"]
        GruvaxSchema["gruvax schema<br/>(this project) — RW"]
      end

      GruvaxAPI["gruvax-api<br/>(FastAPI + Uvicorn)<br/>REST /api/* · SSE /api/events<br/>static SPA at / · aiomqtt publisher"]
      Mosquitto["Mosquitto<br/>(eclipse-mosquitto 2.1-alpine)<br/>LAN listener :1883 · persistence vol"]
    end

    subgraph future["ESP32 LED controllers (FUTURE — not v1)"]
      ESPA["unit-A (WS2812B)"]
      ESPB["unit-B (WS2812B)"]
    end
  end

  Pi <-- "HTTP + SSE" --> GruvaxAPI
  Phone <-- "HTTP + SSE" --> GruvaxAPI
  DGSAPI -- "shares DB" --> PG
  GruvaxAPI -- "RO" --> DGSSchema
  GruvaxAPI -- "RW" --> GruvaxSchema
  GruvaxAPI -- "publish" --> Mosquitto
  Mosquitto -. "subscribe (future)" .-> ESPA
  Mosquitto -. "subscribe (future)" .-> ESPB

  classDef future fill:#fff,stroke:#999,stroke-dasharray: 5 5,color:#666
  class future,ESPA,ESPB future
```

### Arrows — Who Calls Whom (no surprises)

- **Pi kiosk → gruvax-api:** HTTP GET for search, HTTP GET for `/api/locate`, HTTP POST to `/api/illuminate`, SSE long-lived for `/api/events`.
- **Mobile admin → gruvax-api:** HTTP POST for login, HTTP GET/PUT/POST for admin endpoints, SSE for live cross-device refresh.
- **gruvax-api → Postgres:** `gruvax` schema RW, `discogsography.*` views RO (granted at provisioning).
- **gruvax-api → Mosquitto:** publish only in v1. (Optionally subscribe to a `gruvax/leds/status/#` topic in the hardware milestone, no-op in v1.)
- **Future ESP32 → Mosquitto:** subscribe to `gruvax/v1/leds/#`; publish heartbeat/status to `gruvax/v1/leds/status/{unit}`.
- **Nobody talks to discogsography directly from the kiosk.** All access to discogsography data goes through `gruvax-api` and is mediated by the read-only Postgres grant. This keeps the discogsography service boundary clean.

---

## Database Schema (rough, not final)

The `gruvax` schema is small. Final shape lands in the design phase; this rough cut is sufficient for roadmap planning.

### Tables owned by GRUVAX

```sql
-- Configurable shelving units. Two today (left/right Kallax 4x4), more later without schema change.
CREATE TABLE gruvax.units (
  id            SMALLSERIAL PRIMARY KEY,
  display_name  TEXT NOT NULL,           -- e.g. "Left Kallax", "Right Kallax"
  rows          SMALLINT NOT NULL,       -- 4 for a Kallax 4x4
  cols          SMALLINT NOT NULL,       -- 4 for a Kallax 4x4
  ordering      SMALLINT NOT NULL,       -- left-to-right render order
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Per-cube first/last (label, catalog#) bounds. ~32 rows at v1 N=2.
-- The boundary semantics: a record (label, catalog#) belongs in this cube
-- iff (first_label, first_catalog) <= (label, catalog#) <= (last_label, last_catalog)
-- under the project's chosen sort order (lexicographic on normalized label,
-- then catalog#-aware sort within label — exact ordering rules belong to the
-- position-estimation research stream).
CREATE TABLE gruvax.cube_boundaries (
  unit_id        SMALLINT NOT NULL REFERENCES gruvax.units(id) ON DELETE RESTRICT,
  row            SMALLINT NOT NULL,
  col            SMALLINT NOT NULL,
  first_label    TEXT,                   -- nullable for empty cubes
  first_catalog  TEXT,
  last_label     TEXT,
  last_catalog   TEXT,
  is_empty       BOOLEAN NOT NULL DEFAULT FALSE,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (unit_id, row, col),
  CONSTRAINT empty_or_complete CHECK (
    is_empty
      OR (first_label IS NOT NULL AND first_catalog IS NOT NULL
          AND last_label IS NOT NULL AND last_catalog IS NOT NULL)
  )
);

-- Append-only audit / undo log. Each row records one cube's previous state
-- before a change. A multi-cube change (wizard, CSV import) shares a change_set_id.
CREATE TABLE gruvax.boundary_history (
  id              BIGSERIAL PRIMARY KEY,
  change_set_id   UUID NOT NULL,         -- atomic group; one save action = one change_set
  unit_id         SMALLINT NOT NULL,
  row             SMALLINT NOT NULL,
  col             SMALLINT NOT NULL,
  prev_first_label   TEXT,
  prev_first_catalog TEXT,
  prev_last_label    TEXT,
  prev_last_catalog  TEXT,
  prev_is_empty   BOOLEAN NOT NULL,
  new_first_label    TEXT,
  new_first_catalog  TEXT,
  new_last_label     TEXT,
  new_last_catalog   TEXT,
  new_is_empty    BOOLEAN NOT NULL,
  changed_by      TEXT NOT NULL,         -- 'admin' for single-PIN; preserve for future multi-user
  changed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  source          TEXT NOT NULL          -- 'manual' | 'wizard' | 'csv' | 'revert'
);

CREATE INDEX boundary_history_changed_at_idx ON gruvax.boundary_history (changed_at DESC);
CREATE INDEX boundary_history_change_set_idx ON gruvax.boundary_history (change_set_id);

-- Admin sessions. Single PIN today, but session rows in DB (not just signed cookies)
-- so admin can list+revoke active sessions, observe activity, and enforce idle TTL
-- centrally without relying on cookie max-age alone.
CREATE TABLE gruvax.admin_sessions (
  id              UUID PRIMARY KEY,      -- session token (random, server-side only)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ NOT NULL,
  client_label    TEXT,                  -- 'mobile' | 'kiosk' (purely informational)
  user_agent      TEXT,
  revoked_at      TIMESTAMPTZ
);

CREATE INDEX admin_sessions_expires_idx ON gruvax.admin_sessions (expires_at)
  WHERE revoked_at IS NULL;

-- Settings: a flat key-value with JSONB values. Three logical "namespaces":
-- 'led_color', 'led_brightness', 'ui', 'auth'. Lets the design phase add settings
-- without schema migrations.
CREATE TABLE gruvax.settings (
  key            TEXT PRIMARY KEY,       -- e.g. 'led_color.label_span', 'auth.pin_hash'
  value          JSONB NOT NULL,
  description    TEXT,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Optional: per-record search-count aggregation (FEATURES.md Category 7 differentiator,
-- Category 9 anti-feature flag: counts only, never query text).
CREATE TABLE gruvax.search_counters (
  release_id     BIGINT PRIMARY KEY,     -- references discogsography release id (FK NOT enforced — different schema)
  selected_count INTEGER NOT NULL DEFAULT 0,
  last_selected  TIMESTAMPTZ
);
```

### Views owned by GRUVAX (over discogsography data)

To keep the read-only contract explicit and surveyable, GRUVAX should never `SELECT` from `discogsography.releases` directly inside application code. Instead, define views in the `gruvax` schema that project exactly the columns GRUVAX depends on:

```sql
-- Single canonical view of "what's in the owner's collection, with the
-- fields GRUVAX cares about". Reduces blast radius of upstream changes:
-- a discogsography schema migration only breaks GRUVAX if it changes
-- the columns this view touches.
CREATE VIEW gruvax.v_collection AS
SELECT
  ci.id                AS collection_item_id,
  ci.release_id,
  r.title,
  r.label,             -- discogsography exposes label-as-text; case may vary
  r.catalog_number,
  r.format,            -- 'LP' | '7"' | '12"' | 'CD' | ...
  r.year,
  r.fts_vector,        -- tsvector built upstream
  a.name               AS primary_artist,
  ci.updated_at        AS synced_at
FROM discogsography.collection_items ci
JOIN discogsography.releases r  ON r.id = ci.release_id
LEFT JOIN discogsography.artists a ON a.id = r.primary_artist_id;
```

**Read-only contract — what GRUVAX depends on from discogsography:**

| Column / Object | Use | Tolerance to upstream changes |
|---|---|---|
| `releases.title` | Display + FTS | Rename → migrate the view; no code impact |
| `releases.label` | Sort key + display | Format changes (e.g., array → text) → require view + estimator update |
| `releases.catalog_number` | Sort key + display | Same as label |
| `releases.format` | Filter chip (future) | Optional column; missing → drop the filter |
| `releases.fts_vector` | Server search | If discogsography removes it, GRUVAX must build its own tsvector materialized view |
| `releases.year` | Display | Optional |
| `artists.name` | Display + FTS | If artist relation changes shape, only the view needs updating |
| `collection_items.id`, `release_id`, `updated_at` | Sync staleness + per-item identity | `updated_at` drives "last synced" admin indicator |

Postgres grant pattern (run by the operator at provisioning, not by application code):

```sql
GRANT USAGE ON SCHEMA discogsography TO gruvax_app;
GRANT SELECT ON discogsography.releases, discogsography.artists,
                 discogsography.collection_items TO gruvax_app;
-- No INSERT / UPDATE / DELETE granted.
```

This grant is the *enforced* boundary. The view is the *surveyable* boundary. Both matter.

---

## API Surface (rough)

All endpoints are versioned via path prefix `/api` (no `/api/v1` for v1; if a breaking change ever forces it, introduce `/api/v2` and bridge).

### Public (kiosk) endpoints

| Endpoint | Auth | Purpose | Response shape (rough) |
|---|---|---|---|
| `GET /api/search?q=...&limit=20` | none | Typeahead search; FTS + trigram fallback | `{items: [{release_id, title, primary_artist, label, catalog_number, format, score}], took_ms}` |
| `GET /api/locate?release_id=...` | none | Position estimate for a release | `{release_id, label_span: [{unit, row, col}], primary_cube: {unit, row, col}, sub_cube_interval: {cube: {unit,row,col}, start: 0..1, end: 0..1, crosses_boundary: bool, next_cube?: {unit,row,col}}, confidence: 0..1, generated_at}` |
| `GET /api/units` | none | Grid metadata (units + dims, render order) | `{units: [{id, display_name, rows, cols, ordering}]}` |
| `GET /api/cubes/{unit_id}/{row}/{col}` | none | One cube's metadata (first/last, sample contents) | `{unit_id, row, col, first_label, first_catalog, last_label, last_catalog, is_empty, sample_records?: [{release_id, title, label, catalog_number}]}` |
| `POST /api/illuminate` | none | Publish LED message via MQTT (or no-op) | `{published: true, topic, accepted_at}` — never blocks more than ~50 ms |
| `GET /api/events` | none (kiosk-readable) | SSE long-lived stream — boundary changes, admin-editing, server-restart notices | SSE: `event: boundary_changed`, `event: admin_editing`, `event: server_hello`, `event: server_shutdown`, with `: ping` heartbeat per `sse-starlette` default 15 s |
| `GET /api/health` | none | Liveness + dependency status | `{status, db, mqtt, discogsography_sync_age_seconds, version, git_sha, started_at}` |
| `GET /api/version` | none | Build identity | `{version, git_sha, built_at}` |

### Admin endpoints (require valid session cookie)

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/admin/login` | PIN body, rate-limited | Verify PIN, create session row, set signed cookie |
| `POST /api/admin/logout` | session | Revoke session row, clear cookie |
| `GET /api/admin/session` | session | Return session expiry + idle TTL; called for sliding-window refresh |
| `GET /api/admin/cubes` | session | Bulk-fetch all boundaries (admin grid view) |
| `GET /api/admin/cubes/{unit}/{row}/{col}/boundary` | session | One cube's boundary |
| `PUT /api/admin/cubes/{unit}/{row}/{col}/boundary` | session, CSRF token | Update one cube's boundary; writes history row |
| `POST /api/admin/cubes/bulk` | session, CSRF | Atomic multi-cube replace (wizard / CSV / YAML), one `change_set_id` |
| `POST /api/admin/cubes/validate` | session | Dry-run a proposed change set against `v_collection`; returns diff + warnings |
| `POST /api/admin/cubes/suggest` | session | Server suggests boundary midpoint between two adjacent cubes |
| `GET /api/admin/history?limit=...&before=...` | session | Paged history view |
| `POST /api/admin/history/{change_set_id}/revert` | session, CSRF | Inverse change set; writes new history rows tagged `source='revert'` |
| `GET /api/admin/settings` | session | All settings (color, brightness, UI flags) |
| `PUT /api/admin/settings` | session, CSRF | Patch settings |
| `POST /api/admin/leds/diagnostic` | session, CSRF | Trigger the diagnostic LED sequence |
| `POST /api/admin/leds/off` | session, CSRF | Panic-off topic |
| `GET /api/admin/export/boundaries.yaml` | session | Download current boundaries as YAML |
| `GET /api/admin/diagnostics` | session | Sync staleness, slow-query list, MQTT broker status, recent log lines |

### Request/response shape pattern

- **Success:** raw object or `{items: [...], next_cursor: ..., total?: ...}` for list endpoints. No envelope.
- **Error:** RFC 7807 (`application/problem+json`) — `{type, title, status, detail, instance, errors?: [{loc, msg}]}`. FastAPI's default `HTTPException` JSON is a fine pragmatic stand-in if Problem+JSON adds friction; just pick one in the design phase and don't mix.
- **Pagination:** keyset (cursor) on history and any future list endpoints. Offset pagination invites drift when rows are added concurrently. For search, no pagination — return top N (default 20, max 50). The 7" screen can show ~6 results comfortably.
- **Limits:**
  - `GET /api/search`: `limit` default 20, max 50.
  - `GET /api/admin/history`: `limit` default 50, max 200.
  - All bulk admin POSTs: bound to ≤ 200 cube rows per request (current N=2 → 32 cubes, gives plenty of headroom).
- **Idempotency:** All admin mutating endpoints accept an `Idempotency-Key` header. The first invocation per key writes to history; replays return the cached response. Cheap to implement (small table `gruvax.idempotency_keys`) and prevents double-applied wizard saves over flaky LAN Wi-Fi.

---

## MQTT Topic Design

### Topic tree (versioned)

```
gruvax/
  v1/
    leds/
      illuminate/{unit_id}/{row}/{col}     # per-cube illuminate command (non-retained)
      span/{change_id}                     # multi-cube label-span command (non-retained)
      sub/{unit_id}/{row}/{col}            # sub-cube interval (non-retained)
      all/off                              # panic off (non-retained, QoS 1)
      diagnostic                           # diagnostic sequence start (non-retained, QoS 1)
      state/{unit_id}/{row}/{col}          # current desired state per cube (RETAINED)
      status/{unit_id}                     # firmware-published heartbeat (future)
    server/
      hello                                # gruvax-api boot announcement (retained, last-will)
```

### Payload format (JSON, validated against Pydantic)

```json
// gruvax/v1/leds/illuminate/0/2/3
{
  "schema": "gruvax.illuminate.v1",
  "issued_at": "2026-05-18T20:14:33.412Z",
  "unit_id": 0,
  "row": 2,
  "col": 3,
  "color": {"r": 187, "g": 134, "b": 252},   // or "color_name": "label_span" — admin settings resolve names server-side
  "brightness": 128,                          // 0..255
  "duration_ms": 4000,                        // null = persist until cleared
  "transition": {"style": "fade", "duration_ms": 250}
}
```

```json
// gruvax/v1/leds/sub/0/2/3
{
  "schema": "gruvax.sub_interval.v1",
  "issued_at": "...",
  "unit_id": 0, "row": 2, "col": 3,
  "interval": {"start": 0.42, "end": 0.61}, // normalized 0..1 within the cube's pixel range
  "color": {"r": 255, "g": 215, "b": 0},
  "brightness": 220,
  "duration_ms": 6000
}
```

The firmware translates `start/end` into physical pixel indices. Normalizing in the API means firmware can change the per-cube pixel count without breaking the contract.

### Retain vs non-retain

- **Commands (`illuminate`, `span`, `sub`, `diagnostic`, `all/off`):** non-retained. They're momentary actions.
- **State (`state/{unit}/{row}/{col}`):** retained. Captures "what should this cube be displaying right now" so a freshly-booted ESP32 picks up the current desired state without waiting for the next user action. v1 stub publishes these too — costs nothing and lets the hardware milestone work end-to-end without retroactive changes.
- **`server/hello`:** retained, also configured as the LWT (last-will-and-testament) with payload `{"alive": false}` so subscribers can detect a dead gruvax-api.

### QoS levels

- `illuminate`, `sub`, `span`: **QoS 0** (at-most-once). The kiosk re-issues on user action; a missed packet is fine.
- `all/off`, `diagnostic`: **QoS 1** (at-least-once). These are explicit safety/setup commands — retransmit on disconnect.
- `state/*`: **QoS 1** retained. Survives broker restart with persistence enabled.

### v1 stub vs hardware milestone

| Concern | v1 (this milestone) | Hardware milestone |
|---|---|---|
| Who publishes | `gruvax-api` publishes every action | Same |
| Who subscribes | nobody (broker accepts and stores retained state) | ESP32 firmware per unit |
| Mosquitto listener | LAN listener on `1883` is **not exposed** outside the Compose network in v1 | Add a second LAN-bound listener so ESP32s can connect; password-auth even on LAN |
| Auth | username/password between gruvax-api and Mosquitto (single shared creds via Mosquitto password file) | Add per-device-class credentials; never one shared cred per device |
| ACL | gruvax-api: publish-only on `gruvax/v1/leds/#` and `gruvax/v1/server/#`; subscribe-only on `gruvax/v1/leds/status/#` | ESP32 devices: subscribe to `gruvax/v1/leds/#`; publish to `gruvax/v1/leds/status/{unit}` only |

### Home-LAN-only enforcement

- Mosquitto container only publishes a port on the host if hardware is expected. In v1, the broker is reachable **only via the Compose internal network** — no `ports:` mapping in the Compose file.
- When the hardware milestone arrives, the `ports:` mapping adds `1883:1883` bound to the LAN interface (or a specific subnet). The broker config (`bind_address`) also restricts.
- No TLS in v1 (LAN-only, low risk, ESP32 TLS adds firmware complexity). Revisit if the LAN ever spans untrusted Wi-Fi (guest network sharing).

---

## Frontend Architecture

### One SPA or two?

**One SPA, two route trees.** Same Vite bundle, served statically by FastAPI (or by a tiny nginx-alpine container if profiling later demands it).

**Why one bundle:**
- Single build, single deploy step.
- Shared design tokens, components (cube grid is used in admin diff preview).
- Mobile admin and kiosk are both fullscreen views; there's no SEO/SSR concern that would split them.

**Why route-tree separation:**
- `/` and `/search/*` — kiosk routes. No PIN, no admin chrome. Touch-first.
- `/admin/*` — admin routes. PIN-gated. Mobile-first responsive layout. Kiosk fallback works because it's the same React app — touchscreen renders the same components.
- `/admin/login` is the one admin route accessible without a session.

### Route tree

```
/                                      Kiosk home / search
/search/:query                         Deep-linkable search (handy for QR codes / dev)
/cube/:unit/:row/:col                  Reverse-lookup view ("what's in this cube?")
/offline                               Hard-served offline page (cached by SW if present)
/admin/login                           PIN entry
/admin                                 Admin home (status, recent edits)
/admin/cubes                           Grid view of all boundaries
/admin/cubes/:unit/:row/:col           Single-cube editor
/admin/wizard                          Guided setup / reshuffle wizard
/admin/import                          CSV/YAML import + preview/diff
/admin/history                         Change log + revert
/admin/settings                        Colors, brightness, idle TTL
/admin/diagnostics                     Sync staleness, slow queries, MQTT status
```

### State shape (Zustand store + TanStack Query, per STACK.md)

State is split between **server cache** (TanStack Query) and **client UI state** (Zustand). The split avoids the classic Redux "everything is state" problem.

**TanStack Query (server cache, SSE-invalidated):**
```
queryKey('search', q)                  → SearchResult[]
queryKey('locate', release_id)         → LocateResult
queryKey('units')                      → Unit[]
queryKey('cube', unit, row, col)       → CubeMetadata
queryKey('admin', 'cubes')             → CubeBoundary[]
queryKey('admin', 'history', cursor)   → HistoryPage
queryKey('admin', 'settings')          → Settings
queryKey('admin', 'session')           → SessionInfo
queryKey('health')                     → HealthStatus
```

**Zustand store (client UI state):**
```
{
  search: {
    query: string,
    deferredQuery: string,         // React 19 useDeferredValue mirror
    selectedReleaseId: number|null,
    recentlyPulled: ReleaseId[],   // session-scoped, capped at 10
  },
  highlight: {
    primaryCube: {unit,row,col}|null,
    labelSpan: [{unit,row,col}]|null,
    subCubeInterval: {cube, start, end}|null,
    animationToken: string,         // changes per new selection so GSAP can cancel
  },
  connectivity: {
    sseConnected: boolean,
    lastSeenAt: timestamp,
    bannerVisible: boolean,
  },
  admin: {
    isLoggedIn: boolean,            // mirrors session cookie presence; not the source of truth
    sessionExpiresAt: timestamp,
    csrfToken: string|null,
    pendingChangeSet: ChangeSet|null,  // wizard / bulk-edit in-progress state
  },
  ui: {
    colors: ResolvedPalette,        // resolved from /api/admin/settings or sensible defaults
    idleTimeoutSeconds: number,
    isIdle: boolean,
  },
}
```

### SSE consumer pattern

A single SSE connection from each client (kiosk and admin) to `/api/events`. The consumer dispatches events into TanStack Query invalidations or Zustand updates:

```ts
useEffect(() => {
  const es = new EventSource('/api/events');
  es.addEventListener('boundary_changed', (e) => {
    const { cube_ids, change_set_id } = JSON.parse(e.data);
    cube_ids.forEach(({unit,row,col}) => {
      queryClient.invalidateQueries({ queryKey: ['cube', unit, row, col] });
    });
    queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] });
    queryClient.invalidateQueries({ queryKey: ['admin', 'history'] });
  });
  es.addEventListener('admin_editing', (e) => { /* soft-lock indicator */ });
  es.addEventListener('server_shutdown', () => { setSseConnected(false); });
  es.onerror = () => { setSseConnected(false); };
  es.onopen = () => { setSseConnected(true); };
  return () => es.close();
}, []);
```

`sse-starlette`'s 15 s ping (verified via Context7) keeps proxy/keepalive from killing the connection. The native `EventSource` browser API does exponential-backoff reconnection for free, so the only manual code needed is the connected-state flag for the offline banner.

### Where does PIN auth state live?

- **Source of truth:** the signed session cookie (HttpOnly, Secure, SameSite=Lax) plus the `gruvax.admin_sessions` row.
- **Cookie is HttpOnly** → JS cannot read it. The SPA learns "am I logged in?" by calling `GET /api/admin/session` on mount. The store's `admin.isLoggedIn` is a *mirror*, not the source.
- **CSRF token:** issued on session creation as a *second* cookie (`gruvax_csrf`, not HttpOnly, SameSite=Strict). The SPA reads it and adds an `X-CSRF-Token` header on every state-changing admin request (double-submit cookie pattern). This is the right size for a LAN app.
- **PIN entry** route stores nothing locally beyond ephemeral form state.

---

## Build Order / Dependency Graph

The dependency graph below answers "what blocks what" and "what can run in parallel". Per FEATURES.md, the position estimator is the single most-depended-on module — it shows up as the central node.

```mermaid
flowchart TD
  PG[("Postgres + gruvax schema<br/>Alembic init: units, cube_boundaries,<br/>settings, admin_sessions, history<br/><br/><b>Foundation — nothing builds without it</b>")]

  View["v_collection view + RO grants<br/>from discogsography"]
  Auth["PIN auth + admin_sessions + CSRF"]
  Skel["FastAPI app skeleton:<br/>lifespan (mqtt, db), settings,<br/>/health, /version"]

  Search["Search endpoint<br/>(FTS + trgm)"]
  AdminCRUD["Admin: boundary CRUD + history<br/>+ validate + suggest"]
  MQTT["MQTT publish path:<br/>aiomqtt client in lifespan,<br/>/api/illuminate, LED settings"]

  Wizard["Admin wizard / bulk endpoint"]
  Import["CSV/YAML import + diff preview"]

  Estimator["POSITION ESTIMATOR<br/>(own research stream — this<br/>milestone depends only on the contract)<br/>release_id → {cube, label_span,<br/>sub_cube_interval, confidence}"]

  Locate["/api/locate endpoint"]
  SSE["SSE channel /api/events<br/>boundary_changed fan-out"]

  SPA["Frontend SPA<br/>Vite + Tailwind + router + Zustand + TanStack Query<br/>Search · CubeGrid · SubCubeBar · OfflineBanner ·<br/>Admin shell · BoundaryEditor · Wizard · Import · Settings"]

  Kiosk["Pi 5 kiosk runtime<br/>Trixie + labwc + Chromium --kiosk<br/>systemd --user supervisor<br/>http://lux.local:PORT/"]

  PG --> View
  PG --> Auth
  PG --> Skel
  View --> Search
  Auth --> AdminCRUD
  Skel --> MQTT
  AdminCRUD --> Wizard
  AdminCRUD --> Import
  Search --> Estimator
  Wizard --> Estimator
  Estimator --> Locate
  Locate --> SSE
  MQTT --> SSE
  SSE --> SPA
  SPA --> Kiosk
```

### Critical path to a demoable v1

The shortest path from empty repo to "type a record, see a cube light up on the kiosk":

1. Postgres schema + `v_collection` view + grant (1 day)
2. FastAPI skeleton with `/health`, `/version`, settings, lifespan (0.5 day)
3. `GET /api/units` + `GET /api/cubes/...` (0.5 day)
4. `GET /api/search` (FTS only — defer trgm) (1 day)
5. Position-estimator contract stub returning a plausible-but-trivial estimate (boundaries-only, no sub-cube precision) (0.5 day)
6. `GET /api/locate` wired to the stub (0.5 day)
7. Frontend: Vite scaffold + search box + cube grid + highlight (2 days)
8. Pi kiosk autostart (0.5 day)

**Total ~6.5 days to demoable** — but only with a *stub* estimator. The real position estimation (label-span + sub-cube interval) is the parallel research stream and lands at its own pace; the demoable v1 is wired so the real estimator drops in behind the same `/api/locate` contract.

### What can be built in parallel

| Track | Owner | Depends on |
|---|---|---|
| Position-estimator research + tests | (separate research agent) | CSV + view spec |
| Frontend scaffold + design pass | UI design phase | API spec (OpenAPI from FastAPI is enough) |
| Admin endpoints (CRUD, history, validate) | Backend | Schema + PIN auth |
| MQTT publish path + LED endpoints | Backend | FastAPI skeleton |
| SSE channel | Backend | FastAPI skeleton |
| Pi kiosk runtime image / config | Ops | URL of the running API |

All five tracks above can move in parallel after the FastAPI skeleton lands.

### What blocks what (hard)

- Cube highlight UI **hard-blocks on** `/api/locate` returning *something* (even the stub).
- Position-estimator's *quality* does **not** block the rest of v1 — the contract is what matters; the implementation can be iterated indefinitely behind the same shape.
- Admin wizard **hard-blocks on** sanity-validation endpoint (`POST /api/admin/cubes/validate`).
- LED diagnostic mode **hard-blocks on** the MQTT publish path.
- Offline banner **hard-blocks on** SSE channel existing (or a `/health` ping fallback).
- Boundary history view **hard-blocks on** the history table being written during every admin mutation. The mutation endpoints must always write history rows or the audit/undo features are broken at launch.

---

## Deployment (Docker Compose, rough)

`compose.yaml` lives in this repo. Discogsography runs from its own compose stack in a sibling directory; the only shared resource is the Postgres container, which discogsography already operates.

### Two viable patterns

**Pattern A — Single shared compose file** (one operator, one stack): everything in one `compose.yaml` per repo, with discogsography's Postgres exposed on a named Docker network that GRUVAX joins as `external: true`. Recommended.

**Pattern B — Separate compose files joined by external network:** GRUVAX brings its own `gruvax-api` and `mosquitto`, and references `postgres` from discogsography's network. The same operational result, slightly more moving parts to keep in sync.

Either way:

```yaml
# .planning/...-only-illustrative compose.yaml
services:
  gruvax-api:
    build: .
    image: gruvax-api:local
    environment:
      DATABASE_URL: postgresql+psycopg://gruvax_app:${GRUVAX_DB_PASSWORD}@postgres:5432/discogs
      DATABASE_SCHEMA: gruvax
      MQTT_HOST: mosquitto
      MQTT_PORT: 1883
      MQTT_USERNAME: gruvax-api
      MQTT_PASSWORD: ${MQTT_PASSWORD}
      PIN_HASH: ${GRUVAX_PIN_HASH}          # Argon2id hash of the PIN
      SESSION_SECRET: ${GRUVAX_SESSION_SECRET}
      SESSION_TTL_SECONDS: 600
      LOG_LEVEL: info
      OBSERVED_DISCOGSOGRAPHY_SCHEMA: discogsography
    ports:
      - "8000:8000"                         # LAN interface only; bind via host firewall
    volumes:
      - ./static:/app/static:ro             # frontend build artifact (or bake into image)
    networks: [internal, discogsography_default]
    depends_on:
      mosquitto:
        condition: service_started
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health').read()"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 15s
    restart: unless-stopped

  mosquitto:
    image: eclipse-mosquitto:2.1-alpine
    volumes:
      - ./mosquitto/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro
      - ./mosquitto/passwd:/mosquitto/config/passwd:ro
      - mosquitto-data:/mosquitto/data
      - mosquitto-log:/mosquitto/log
    # In v1: no `ports:` mapping. Broker only reachable inside the Compose internal network.
    # Hardware milestone adds: ports: ["1883:1883"] bound to the LAN interface.
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "mosquitto_sub -t '$$SYS/broker/uptime' -C 1 -W 2 -u $$MQTT_USERNAME -P $$MQTT_PASSWORD || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
    restart: unless-stopped

volumes:
  mosquitto-data:
  mosquitto-log:

networks:
  internal:
  discogsography_default:
    external: true
```

### Networking — who needs outside access vs internal-only

| Service | LAN-reachable | Compose-internal only |
|---|---|---|
| `gruvax-api` | YES — Pi kiosk and mobile admin connect over LAN | — |
| `mosquitto` (v1) | NO — only `gruvax-api` publishes to it; nothing else needs it | YES |
| `mosquitto` (hardware milestone) | YES — ESP32s subscribe over LAN | — |
| `postgres` (shared) | NO — never exposed; discogsography keeps it internal to its compose network | YES |

### Frontend hosting

Two options (STACK.md):
1. **FastAPI `StaticFiles` mount** — one container, no CORS, simplest. **Recommended for v1.**
2. Separate `nginx-alpine` static container — only if FastAPI static serving becomes a measurable factor (it won't).

### Restart policies

All services: `restart: unless-stopped`. Compose handles dependency ordering via `depends_on` health checks.

### Migrations

Alembic `upgrade head` runs on container start, before Uvicorn boots. If migrations fail, the container fails to start — discoverable via `docker compose ps` and `docker compose logs`.

---

## Failure Modes & Isolation

| Failure | Behavior | Mitigation |
|---|---|---|
| **Postgres down or unreachable** | `/api/health` returns `db: down`; search and locate return 503; `/api/events` emits `event: server_degraded`; kiosk shows offline banner; admin login fails. | Compose `depends_on` plus retries in `gruvax-api`'s DB pool. On startup, retry the first connection 30× with backoff before crashing. |
| **Mosquitto down or unreachable** | `POST /api/illuminate` returns `202 Accepted` with `published: false, reason: "broker_unreachable"` — **never blocks the kiosk**. The MQTT publish runs as a fire-and-forget background task with a 250 ms timeout. Search continues working. | `aiomqtt` client in lifespan with `reconnect=True` (Context7-verified). On publish, `asyncio.wait_for(client.publish(...), timeout=0.25)`; log timeout, don't raise to the user. |
| **discogsography schema migration breaks `v_collection`** | App boots, but search fails on first query. `/api/health` exposes `discogsography_view_check: failed`. | At startup, `SELECT 1 FROM gruvax.v_collection LIMIT 1` — if it errors, mark health as degraded and log the upstream column delta. The view definition is the single point of contact; updating it is the migration. |
| **Pi loses Wi-Fi** | `EventSource` reconnects with browser-default backoff (~5 s). SSE-derived `sseConnected: false` flips the banner on. Search input disabled, placeholder reads "Reconnecting…". Cached query results remain visible (TanStack Query stale-while-revalidate). | Documented in PROJECT.md Active scope. FEATURES.md flags optional v1.x service-worker cache as the next step. |
| **gruvax-api restarts** | All SSE clients reconnect to `/api/events`; on reconnect they receive `event: server_hello` and refetch unit+settings. Admin sessions persist because the session row lives in Postgres. | Lifespan publishes `server/hello` retained on Mosquitto (also acts as LWT for future ESP32s). |
| **Concurrent boundary edits from two admin clients** | Last-write-wins at the DB level; the *history* table preserves both edits as separate change sets so neither is lost. SSE notifies the loser's client to refresh. | Per FEATURES.md Category 5: no hard locking. Soft-lock indicator (`admin_editing` SSE event) renders a subtle banner when another admin session has touched a cube in the last 60 s. The "loser" sees their change overwritten in the history view immediately. Hard CRDT collaboration is YAGNI for one operator. |
| **SSE connection drops mid-edit** | Native `EventSource` reconnects automatically with browser backoff. On reconnect, the client refetches `admin/cubes`, `admin/history`, and current `admin/session`. | The 15 s ping (sse-starlette default) ensures most flaky-connection scenarios are detected within 30 s. |
| **Admin session expires while editing** | The PUT/POST returns `401`. The SPA shows a "session expired" modal and routes to `/admin/login`, preserving the form state in Zustand so the admin can resume after re-auth. | Sliding-window TTL refreshes on every request through the middleware; explicit countdown badge in the admin UI when < 60 s remains (FEATURES.md). |
| **Postgres temporarily slow (e.g., discogsography sync running)** | Slow-query log captures any request > 200 ms; admin diagnostics page surfaces the top-10 slow queries from the last hour. The 200 ms perceived budget remains as an SLO. | Connection pool sized so a slow query doesn't starve other requests. `psycopg_pool` with 10 connections is plenty. |
| **MQTT broker accepts but firmware never sees the message (future)** | v1: no firmware exists, so undetectable and acceptable. Hardware milestone: firmware publishes heartbeats on `gruvax/v1/leds/status/{unit}`; if `gruvax-api` doesn't see a recent heartbeat, the admin diagnostics page surfaces "unit-A LED firmware unreachable". | Not a v1 concern; v1 contract is "we publish; whoever listens, listens". |
| **CSV/YAML import partially malformed** | The validate endpoint returns row-level errors before the bulk POST is committed. The bulk POST itself runs in a single transaction with `change_set_id`. Either all rows commit or none do. | DSpace-style preview/diff pattern (FEATURES.md). |
| **Idempotency key replay** | Returns the cached response; does not double-write history. | `gruvax.idempotency_keys` table with `(key, response_json, created_at)` and 24 h TTL. |
| **PIN brute-force from LAN** | Rate-limited login endpoint: 5 attempts per 5 minutes per IP, then exponential backoff. After 20 failures in an hour, block the IP for 24 h (with admin-visible note in diagnostics; admin can clear it from a logged-in session). | `slowapi` middleware or hand-rolled bucket in Postgres. The PIN is Argon2id-hashed (STACK.md). |

### Failure isolation principles

1. **The kiosk never blocks on MQTT.** Publish is fire-and-forget with a hard timeout.
2. **discogsography is a strict read dependency, isolated behind one view.** Upstream changes can break GRUVAX, but they break it loudly (health-check-visible) and at one point.
3. **Admin sessions outlive the API process.** Session state in Postgres, not in-memory.
4. **Frontend caches what it has.** TanStack Query's stale-while-revalidate means an offline kiosk still shows the last grid render, just with the banner up and search disabled.
5. **History is append-only.** No edit ever loses prior state; revert is a new history row tagged `source='revert'`, not a destructive operation.

---

## Position-Estimator Contract

The algorithm itself is a parallel research stream. This document fixes the contract; the algorithm is replaceable behind it.

### Input

```python
class LocateRequest:
    release_id: int            # references discogsography release id
```

### Output

```python
class LocateResult:
    release_id: int
    primary_cube: CubeRef                   # {unit_id, row, col} — the cube that contains the record
    label_span: list[CubeRef]               # all cubes the record's label spans, in order; primary_cube is one of them
    sub_cube_interval: SubInterval | None   # nullable: estimator may return None for low-confidence cases
    confidence: float                       # 0..1; UI may downgrade visuals when low
    generated_at: datetime
    estimator_version: str                  # tracks which algorithm/version produced this

class SubInterval:
    cube: CubeRef                           # cube the interval starts in
    start: float                            # 0..1 within cube's pixel range
    end: float                              # 0..1
    crosses_boundary: bool                  # if true, interval continues into next_cube
    next_cube: CubeRef | None
```

### Error semantics

- **Record not in collection:** HTTP 404, `{type: "release_not_in_collection", release_id}`. Estimator does not throw — the API handler returns 404.
- **No boundaries cover this record's label:** HTTP 200 with `confidence: 0.0`, `primary_cube: null`, `label_span: []`, and a message in the response. UI renders "no cube assigned yet" (treat the same as empty cube).
- **Multiple cubes claim this label (boundary overlap bug):** HTTP 500-eligible OR HTTP 200 with `confidence: 0` and `error: "overlapping_boundaries"`. Pick one and stick with it. Recommendation: HTTP 200 + zero confidence — kiosk degrades gracefully; admin diagnostics surfaces the conflict.
- **Estimator timeout (> 100 ms internal):** HTTP 200 with `confidence: 0`, `primary_cube: best-guess from boundary lookup only`, `sub_cube_interval: null`. The fall-back path is just a binary search over boundaries; sub-cube precision is the expensive part.

### Latency budget

- p95 end-to-end search → locate → render ≤ 200 ms (Core Value).
- Of that 200 ms, estimator gets ≤ 50 ms p95. Boundary lookup is microseconds; sub-cube interpolation is the variable cost.
- The estimator MUST be CPU-only — no DB calls during the position computation, only a pre-loaded boundary list + the queried record's `(label, catalog_number)`. Boundary cache is invalidated on `boundary_changed` events.

### What the algorithm research stream gets to decide

- How to normalize labels (case-fold, strip punctuation, etc.)
- How to compare catalog numbers (alpha prefix, numeric suffix, mixed)
- How to handle inconsistent intra-label formats (`Twelve 002` vs `TWELVE 003`)
- How to interpolate position within the label-span (uniform vs density-weighted vs anchored)
- How confidence is computed

**What it does NOT get to decide:** the contract shape above, the latency budget, or the error semantics. Those are architectural.

---

## Recommended Project Structure

```
gruvax/
├── pyproject.toml
├── uv.lock
├── compose.yaml
├── justfile
├── alembic.ini
├── mosquitto/
│   ├── mosquitto.conf
│   └── passwd                       # password file, gitignored, generated locally
├── migrations/                      # Alembic
│   ├── env.py
│   └── versions/
├── src/gruvax/
│   ├── __init__.py
│   ├── app.py                       # FastAPI factory + lifespan (mqtt, db pool, position cache)
│   ├── settings.py                  # pydantic-settings
│   ├── db/
│   │   ├── pool.py                  # psycopg async pool
│   │   ├── models.py                # SQLAlchemy declarative
│   │   └── queries.py               # hand-written queries for search (FTS+trgm)
│   ├── auth/
│   │   ├── pin.py                   # Argon2id hash/verify
│   │   ├── sessions.py              # session row CRUD + cookie middleware
│   │   └── csrf.py                  # double-submit token
│   ├── api/
│   │   ├── search.py                # GET /api/search
│   │   ├── locate.py                # GET /api/locate
│   │   ├── units.py                 # GET /api/units, GET /api/cubes/...
│   │   ├── illuminate.py            # POST /api/illuminate
│   │   ├── events.py                # GET /api/events (SSE)
│   │   ├── health.py                # GET /api/health, /api/version
│   │   └── admin/
│   │       ├── login.py
│   │       ├── cubes.py             # CRUD + validate + suggest + bulk
│   │       ├── history.py           # GET + revert
│   │       ├── settings.py
│   │       ├── leds.py              # diagnostic, off
│   │       ├── export.py
│   │       └── diagnostics.py
│   ├── estimator/                   # ← position-estimator research stream owns this
│   │   ├── contract.py              # the dataclasses above; the contract is here
│   │   ├── boundary_cache.py        # in-memory + SSE-invalidation
│   │   ├── algorithm.py             # the actual algorithm (researcher's playground)
│   │   └── normalize.py             # catalog/label normalization helpers
│   ├── mqtt/
│   │   ├── client.py                # aiomqtt lifespan wiring
│   │   ├── topics.py                # topic builders + Pydantic payload models
│   │   └── publishers.py            # illuminate / span / sub / off / diagnostic
│   ├── events/
│   │   └── bus.py                   # in-process pub/sub feeding SSE; boundary writes call into this
│   └── observability/
│       ├── logging.py               # structlog config
│       └── slowlog.py               # > 200 ms request middleware
├── tests/
│   ├── conftest.py                  # CSV fixture (synthetic for CI, real for local)
│   ├── unit/
│   ├── integration/                 # spins up Postgres + Mosquitto via testcontainers
│   └── property/                    # Hypothesis tests for estimator
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx
        ├── router.tsx
        ├── api/                     # generated OpenAPI client OR hand-written fetch wrappers
        ├── state/                   # zustand stores
        ├── events/                  # SSE consumer
        ├── routes/
        │   ├── kiosk/
        │   │   ├── Home.tsx
        │   │   ├── SearchBox.tsx
        │   │   ├── ResultsList.tsx
        │   │   ├── CubeGrid.tsx
        │   │   ├── CubeHighlight.tsx
        │   │   ├── SubCubeBar.tsx
        │   │   ├── OfflineBanner.tsx
        │   │   └── RecentlyPulled.tsx
        │   └── admin/
        │       ├── Login.tsx
        │       ├── Dashboard.tsx
        │       ├── CubesGrid.tsx
        │       ├── CubeEditor.tsx
        │       ├── Wizard.tsx
        │       ├── Import.tsx
        │       ├── HistoryView.tsx
        │       ├── Settings.tsx
        │       └── Diagnostics.tsx
        ├── components/              # shared (Button, Modal, ColorPicker, DiffTable, ...)
        └── styles/
```

### Structure rationale

- **`src/gruvax/estimator/`** is a single directory because the algorithm research stream needs a clear sandbox. Contract in `contract.py` is what the rest of the codebase imports; the algorithm can be rewritten without touching anything else.
- **`src/gruvax/mqtt/`** isolates aiomqtt usage so that if the broker changes (e.g., to MQTT-over-WebSocket in some future variant) or if the LED contract evolves, the blast radius is one directory.
- **`src/gruvax/events/bus.py`** is the *in-process* fan-out for SSE. When admin writes a boundary, the API handler updates Postgres, writes history, then calls `bus.publish('boundary_changed', ...)`. The SSE endpoint subscribes to this bus and emits. Keeping the bus in-process avoids a dependency on Mosquitto for internal kiosk-update flow.
- **`frontend/src/routes/{kiosk,admin}/`** mirrors the route tree. Shared components live one level up.
- **`tests/property/`** is the home of Hypothesis tests for the estimator — this is where the algorithm research stream proves its invariants.

---

## Architectural Patterns

### Pattern 1: Single MQTT Client in the Lifespan, Dependency-Injected

**What:** One `aiomqtt.Client` lives for the lifetime of the FastAPI app, owned by the lifespan context manager and shared via `app.state.mqtt`. Routes get it via `Depends`.

**Why:** Verified via Context7 (`/empicano/aiomqtt`) — this is the documented FastAPI pattern. Spinning up a per-request connection would multiply broker connections and TCP overhead with no benefit; Mosquitto handles long-lived connections cheaply.

**Trade-offs:** Single point of failure if the client dies — mitigated by `reconnect=True` and the fire-and-forget publish wrapper.

```python
# excerpt — full file lives at src/gruvax/mqtt/client.py
@contextlib.asynccontextmanager
async def mqtt_lifespan(app: FastAPI):
    async with aiomqtt.Client(
        hostname=settings.MQTT_HOST,
        username=settings.MQTT_USERNAME,
        password=settings.MQTT_PASSWORD,
        identifier="gruvax-api",
        clean_start=False,
        session_expiry_interval=86400,
        reconnect=True,
        keep_alive=30,
        will=aiomqtt.Will("gruvax/v1/server/hello", payload=b'{"alive": false}', retain=True),
    ) as client:
        await client.publish("gruvax/v1/server/hello", b'{"alive": true}', retain=True)
        app.state.mqtt = client
        yield
```

### Pattern 2: In-Process Event Bus for SSE Fan-Out

**What:** A tiny pub/sub `EventBus` in `src/gruvax/events/bus.py` that any API handler can publish to. The SSE endpoint subscribes per-connection and yields received events.

**Why:** SSE clients need to learn about boundary changes the moment they happen. Round-tripping through Mosquitto for kiosk updates is overkill (Mosquitto is for LED hardware). An in-process `asyncio.Queue`-per-subscriber bus delivers SSE events in microseconds and dies with the process — exactly the lifetime we want.

**Trade-offs:** If the app ever scales to multiple replicas (it won't in v1), in-process fan-out doesn't span replicas. Then you'd put Redis Pub/Sub or NATS in front. Don't preemptively add that.

```python
# src/gruvax/events/bus.py — sketch
class EventBus:
    def __init__(self):
        self._subscribers: set[asyncio.Queue[Event]] = set()
    def subscribe(self) -> asyncio.Queue[Event]:
        q = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q
    def unsubscribe(self, q): self._subscribers.discard(q)
    async def publish(self, event: Event):
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer; drop. Client will refetch on next ping or reconnect.
                pass
```

### Pattern 3: Boundary Cache with SSE Invalidation

**What:** The position estimator depends on cube boundaries on every call. Holding the full `cube_boundaries` table in memory (32 rows; trivially small) avoids a DB hit per locate call. Invalidate the cache when the event bus fires `boundary_changed`.

**Why:** 50 ms estimator budget evaporates if every locate call hits Postgres for boundary rows. With the cache, locate is CPU-bound on the algorithm itself.

**Trade-offs:** Stale-cache window between DB commit and cache invalidation, measured in single-digit milliseconds. Worst case: one stale locate call right after a boundary edit. Acceptable for v1.

### Pattern 4: View as the Read-Only Contract Surface

**What:** All reads of discogsography data go through `gruvax.v_collection`. Application code never references `discogsography.releases` directly.

**Why:** Surfaces the dependency in one place. A single migration on the discogsography side that adds/removes/renames a column is a one-line view change in GRUVAX, not a sweep across the codebase.

**Trade-offs:** One extra layer of indirection in SQL plans; Postgres is good at inlining views, so the performance cost is zero. The clarity gain is large.

### Pattern 5: History-As-Append-Only-Source-of-Truth

**What:** Every mutation to `cube_boundaries` writes one or more rows to `boundary_history` in the same transaction. Revert is also a write — never a destructive operation.

**Why:** Undo, audit, future backup, and the reshuffle wizard atomic-commit story all share this foundation. Building all four on the same table costs almost nothing extra over building just the first one.

**Trade-offs:** Table growth is linear in edits. At ~5–10 reshuffles per year × ~30 cubes per reshuffle, that's a few hundred rows per year. Trivial.

### Pattern 6: Double-Submit Cookie CSRF

**What:** On login, set two cookies — one HttpOnly session cookie, one non-HttpOnly CSRF cookie. SPA reads the CSRF cookie and echoes it as a header on every state-changing admin request.

**Why:** SameSite=Lax + double-submit gives CSRF protection that's correct for a single-origin LAN app without needing a token-mint endpoint or server-side CSRF state.

**Trade-offs:** Vulnerable to subdomain takeover or XSS — neither relevant on a home LAN with one operator. Don't over-engineer.

---

## Data Flow Examples

### Search → Cube Highlight

```mermaid
sequenceDiagram
  autonumber
  participant User
  participant SPA as Kiosk SPA<br/>(React 19 + Zustand + TanStack Query)
  participant API as gruvax-api
  participant Estimator as Position Estimator<br/>(in-process, cached boundaries)
  participant PG as Postgres<br/>(gruvax.v_collection)
  participant MQ as Mosquitto

  User->>SPA: taps a key
  Note over SPA: useDeferredValue + 100 ms debounce
  SPA->>API: GET /api/search?q=...
  API->>PG: SQL FTS + trgm over v_collection
  PG-->>API: ranked rows
  API-->>SPA: JSON response (≤ 50 ms p95)
  Note over SPA: render results;<br/>top result auto-selected
  SPA->>API: GET /api/locate?release_id=...
  API->>Estimator: estimator.compute(release_id)
  Note over Estimator: CPU-only,<br/>no DB calls
  Estimator-->>API: {primary_cube, label_span,<br/>sub_cube_interval, confidence}
  API-->>SPA: LocateResult
  Note over SPA: CubeGrid re-renders;<br/>GSAP timeline plays
  par fire-and-forget LED publish
    SPA->>API: POST /api/illuminate
    API->>MQ: aiomqtt.publish('gruvax/v1/leds/...')<br/>250 ms timeout
    Note over MQ: v1: retained state stored;<br/>no subscribers yet
  end
```

**Critical: the illuminate publish is NOT awaited from the search flow.** It runs as `asyncio.create_task(...)` so a slow broker never affects the user's search latency.

### Admin Boundary Edit → Live Kiosk Update

```mermaid
sequenceDiagram
  autonumber
  participant Admin as Admin (mobile)
  participant API as gruvax-api
  participant PG as Postgres
  participant Bus as in-process<br/>event_bus
  participant SSE as SSE clients<br/>(admin + kiosk)
  participant Cache as Boundary cache<br/>+ TanStack Query

  Admin->>Admin: React Hook Form + Zod client-side validation
  Admin->>API: PUT /api/admin/cubes/{u}/{r}/{c}/boundary<br/>session cookie + X-CSRF-Token + Idempotency-Key
  Note over API: validate session, CSRF,<br/>idempotency
  rect rgb(245, 245, 245)
    Note over API,PG: Transaction
    API->>PG: SELECT current boundary
    API->>PG: INSERT boundary_history<br/>(prev_*, new_*, change_set_id, source='manual')
    API->>PG: UPDATE cube_boundaries
  end
  API->>Bus: publish('boundary_changed',<br/>cube_ids=[(u,r,c)], change_set_id)
  par fan-out to all SSE clients
    Bus->>SSE: event: boundary_changed (admin echo)
    Bus->>SSE: event: boundary_changed (kiosk)
  end
  Bus->>Cache: invalidate boundary cache<br/>(same bus subscription)
  SSE->>Cache: TanStack Query invalidates<br/>['cube', u, r, c], ['admin', 'cubes'], ['admin', 'history']
  Note over SSE,Cache: React refetches affected queries;<br/>kiosk re-highlights if cube selected.
```

End-to-end latency from admin save to kiosk re-render: typically < 500 ms over LAN.

### LED Diagnostic Sequence

```mermaid
sequenceDiagram
  autonumber
  participant Admin
  participant API as gruvax-api
  participant MQ as Mosquitto
  participant ESP as ESP32 firmware<br/>(FUTURE — not v1)
  participant Bus as event_bus
  participant SSE as Admin diagnostics SSE

  Admin->>API: POST /api/admin/leds/diagnostic
  API->>MQ: aiomqtt.publish('gruvax/v1/leds/diagnostic',<br/>{'sequence': 'rainbow'}, qos=1)
  Note over MQ: v1: stores message;<br/>no ESP32 to consume yet
  rect rgb(245, 245, 245)
    Note over ESP,SSE: Hardware milestone (dormant in v1)
    MQ-->>ESP: deliver diagnostic command
    ESP->>ESP: execute pixel-by-pixel sequence per unit
    ESP->>MQ: publish gruvax/v1/leds/status/{unit_id}
    MQ-->>API: fan out to gruvax-api subscription
    API->>Bus: publish('led_status', ...)
    Bus->>SSE: admin diagnostics page updates
  end
```

In v1, only the publish half exists. The whole right side ("ESP32 firmware...") is dormant infrastructure ready to switch on.

---

## Scaling Considerations

The realistic upper bound for this product is a single household, ~10K records, a handful of Kallax units, two or three concurrent viewers. Scaling concerns are mostly about *graceful degradation* on a Pi 5 running Chromium, not about server throughput.

| Scale | Architecture adjustments |
|---|---|
| 3K records, 32 cubes, 1-3 users (current) | Single FastAPI process, 4 worker threads (default Uvicorn), Postgres pool of 10. Everything fits in 256 MB RAM. |
| 10K records, 64 cubes, 5 users (plausible 2027) | No architectural change. Postgres FTS+trgm scale fine to 100K+ rows. Frontend `@tanstack/react-virtual` if results list ever exceeds ~50 visible rows. |
| Multi-collection (room A + room B) | Schema is ready (`units` table is N units, not 2). Add unit-group concept if grouping needed. Real LED hardware milestone would extend Mosquitto with per-unit ACLs. |
| Public-internet exposure (if ever) | Replace single-PIN auth with `fastapi-users` + OAuth. Front the API with a reverse proxy. Move Mosquitto behind TLS-only listener. Not on the v1.x roadmap. |

### First bottleneck: Pi 5 Chromium rendering

If animation perf is the first thing to break, it's likely the kiosk side, not the server. Mitigation order (cheapest to most expensive):
1. Drop GSAP from the search-result list animations; keep only the cube-highlight cinematic.
2. Switch search results to plain CSS transitions.
3. Virtualize the results list.
4. Reconsider the framework choice — SolidJS or Svelte 5 (STACK.md alternative) only if profiling shows React reconciler is in the way.

### Second bottleneck: Postgres FTS latency under load

Unlikely at this scale, but the mitigation is:
1. Add a covering index on `(label, catalog_number)` for the trgm path.
2. Materialize the search tsvector in `gruvax.v_search` as a materialized view, refreshed nightly. Decouples GRUVAX search from discogsography sync timing.
3. As a last resort: ship a small Meilisearch sidecar. Don't preempt.

---

## Anti-Patterns

### Anti-Pattern 1: Round-Tripping Kiosk Updates Through Mosquitto

**What people do:** "We already have MQTT for LEDs, let's publish boundary-changed events to MQTT too and have the kiosk subscribe."

**Why it's wrong:** Two protocols where one is needed. Browsers don't have native MQTT support — you'd add a JS MQTT-over-WebSocket client to the kiosk and an extra Mosquitto listener. SSE over HTTP gets you the same outcome with the connection the browser already maintains and zero extra moving parts.

**Do this instead:** In-process event bus + SSE. Mosquitto is for LED hardware only.

### Anti-Pattern 2: Per-Record Position Storage

**What people do:** Store each release's exact cube in a `release_position` table. Update on every reshuffle.

**Why it's wrong:** 3,000 rows of one-time data entry per reshuffle. PROJECT.md explicitly rejects this. The whole point of the deterministic-ordering invariant is that position is *computed*.

**Do this instead:** Store boundaries (32 rows). Compute positions on demand. If the algorithm gets smarter, every record benefits.

### Anti-Pattern 3: Multiple GRUVAX-API Replicas Behind a Load Balancer

**What people do:** "Let's run two `gruvax-api` containers for HA."

**Why it's wrong:** SSE state is in-process (`EventBus`); two replicas would mean some clients miss some events. The in-process boundary cache would diverge across replicas. The auth state is in Postgres so that part's fine, but the SSE+cache topology demands a single instance.

**Do this instead:** Single instance with `restart: unless-stopped`. If HA ever matters (it doesn't for a home kiosk), replace the in-process bus with Redis Pub/Sub *and* the boundary cache with a shared cache. That's a different architecture.

### Anti-Pattern 4: Letting Mosquitto Block the Hot Path

**What people do:** `await client.publish(...)` in the search handler synchronously.

**Why it's wrong:** A flaky broker, a dead connection in mid-reconnect, or just slow ESP32 firmware (future) would push search latency over the 200 ms budget.

**Do this instead:** `asyncio.create_task(...)` the publish, with a 250 ms internal timeout, log on failure. The kiosk experience never degrades because the LED layer is unhappy.

### Anti-Pattern 5: Exposing Mosquitto to the LAN in v1

**What people do:** Add `ports: ["1883:1883"]` to the Compose file "for symmetry with how it'll look later."

**Why it's wrong:** A Mosquitto without an ESP32 to listen to is an attack surface with no upside. Adding it now means someone could (or you could, by accident) publish junk on `gruvax/v1/leds/*` retained topics and confuse future hardware.

**Do this instead:** No `ports:` mapping in v1. Add it as part of the hardware milestone change set.

### Anti-Pattern 6: Storing the PIN in an Env Var as Plaintext

**What people do:** `GRUVAX_PIN=1234` in `.env`.

**Why it's wrong:** The PIN ends up in process listings, journald, `docker inspect`, and CI logs.

**Do this instead:** Store the Argon2id *hash* in `gruvax.settings` (key `auth.pin_hash`) seeded via a one-shot bootstrap command. The env var carries `GRUVAX_PIN_HASH` only if you must — preferred is the DB-seeded path, which means changing the PIN doesn't require a redeploy.

### Anti-Pattern 7: Tight Coupling Estimator to Endpoint

**What people do:** Compute position inline in the `/api/locate` handler.

**Why it's wrong:** The estimator is a research stream with its own test harness, property tests, and benchmarks. Inlining it means the research can't iterate independently.

**Do this instead:** Keep `src/gruvax/estimator/algorithm.py` as the swappable target behind the contract dataclasses. The API handler is ten lines: load the record, call the estimator, return the result.

---

## Integration Points

### External (cross-process / cross-host) integrations

| Integration | Pattern | Notes |
|---|---|---|
| Postgres (shared) | Async psycopg + pool; `gruvax` schema RW; `discogsography.*` RO via view | Migrations via Alembic; grants applied out-of-band at provisioning |
| Mosquitto | aiomqtt single-client-in-lifespan; publish-only in v1 | LWT + retained `server/hello`; future ESP32 subscribe path is dormant infrastructure |
| Pi kiosk | HTTP + SSE to `gruvax-api`; no other coupling | Chromium-launched from labwc autostart, supervised by `systemd --user` |
| discogsography service | None directly — only via shared Postgres | Their service runs independently; if their FastAPI is down, GRUVAX is unaffected as long as Postgres is up |

### Internal (in-process module) boundaries

| Boundary | Communication | Notes |
|---|---|---|
| API handler ↔ estimator | direct call into `estimator.locate(release_id)` returning dataclass | contract in `contract.py`; algorithm is replaceable |
| API handler ↔ MQTT publishers | `await publishers.illuminate(client, payload)` — *fire-and-forget wrapped* | publishers wrap aiomqtt and apply the 250 ms timeout |
| API handler ↔ event bus | `await event_bus.publish(Event(...))` | called from inside the same transaction as the DB write, but after commit |
| SSE endpoint ↔ event bus | subscribe per connection; async-iterate the queue | drops on slow consumer; client refetches on reconnect |
| Auth middleware ↔ session store | reads/writes `admin_sessions` row | sliding-window refresh on every authenticated request |
| Estimator ↔ boundary cache | direct in-memory dict lookup | invalidated on `boundary_changed` bus event |

---

## Open Architectural Questions

These are intentionally left for the requirements / design phase to decide. Each one is small enough that it doesn't block roadmap planning but big enough that pinning it now without input would be premature.

1. **YAML or JSON for boundary import/export?** YAML is more human-editable; JSON is more parsing-tolerant. FEATURES.md leans YAML; cost of supporting both is small. Decide in requirements.
2. **Is the per-record search-counter table worth shipping in v1, or defer?** FEATURES.md flags it as Category 7 differentiator. Privacy guardrails (Category 9) require it stays aggregate-only. Decide whether the differentiator is worth the schema surface.
3. **Idempotency-Key behavior on bulk endpoints under partial overlap.** What happens if two admin clients submit overlapping bulk changes with different idempotency keys, hitting the same cube? Last-write-wins is the default; surfacing the conflict in the SSE event is the open question.
4. **Should `/api/locate` cache by `release_id`?** The estimator is fast (< 50 ms) and the boundary cache is in-memory, so caching at the HTTP layer doubles work. Recommend not caching at HTTP level; revisit if profiling says otherwise.
5. **Service worker on the kiosk in v1, v1.x, or not at all?** FEATURES.md flags as RECONSIDER-for-v1. Materially upgrades offline UX but adds caching-strategy complexity (stale-while-revalidate, cache invalidation on app version bump). Decide in requirements.
6. **Frontend: served from FastAPI `StaticFiles` or separate nginx?** Default to FastAPI for v1 simplicity; revisit if the SPA bundle grows or if asset caching becomes a bottleneck.
7. **Where does the PIN hash live — env var or DB?** DB (`gruvax.settings`) is the more flexible answer (PIN rotation without redeploy), but adds a chicken-and-egg bootstrap. A bootstrap CLI command (`uv run gruvax-cli set-pin`) is the natural answer. Decide in design.
8. **Per-visitor PIN (FEATURES.md Category 9 differentiator) — v1 or future?** Currently flagged as RECONSIDER. Architecture supports it trivially (the `admin_sessions` table already has `client_label`). Decide in requirements.
9. **OpenAPI client generation vs hand-written fetch.** FastAPI exports OpenAPI; tools like `openapi-typescript` or `orval` can generate a typed client. Trade-off is a build step on the frontend. Modest scope, decide in design.
10. **Touch keyboard for kiosk admin fallback** (raised in STACK.md). Three options: (a) admin only on mobile, (b) in-app virtual keyboard, (c) drop kiosk fullscreen. Architecture is indifferent; UX decision.

---

## Sources

### Authoritative (Context7-verified, HIGH confidence)

- [aiomqtt — FastAPI lifespan + reconnect patterns (Context7 `/empicano/aiomqtt`)](https://github.com/empicano/aiomqtt) — confirmed `reconnect=True`, `clean_start=False`, `session_expiry_interval`, `will=Will(...)`, single-client-in-lifespan dependency-injection pattern.
- [sse-starlette — EventSourceResponse + ping + send_timeout (Context7 `/sysid/sse-starlette`)](https://github.com/sysid/sse-starlette) — confirmed `ping=15` default, `send_timeout`, `ServerSentEvent` shape, and the FastAPI integration sketch above.
- [discogsography README](https://github.com/SimplicityGuy/discogsography) — Python 3.13+, FastAPI, psycopg3, shared Postgres ergonomics, uv/Ruff/mypy alignment.
- [Eclipse Mosquitto Docker image](https://hub.docker.com/_/eclipse-mosquitto) — `2.1-alpine` current; retained-message persistence config; LAN listener binding.
- [Pydantic v2 `pydantic-settings`](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — env-var validated config pattern.

### Implementation pattern references (cross-checked across sources, MEDIUM confidence)

- [FastAPI SSE vs WebSocket (2026 guide)](https://medium.com/@rameshkannanyt0078/fastapi-real-time-api-websockets-vs-sse-vs-long-polling-2026-guide-ce1029e4432e) — SSE is the right tool for one-way server→client realtime; matches STACK.md.
- [Double-submit cookie CSRF (OWASP cheat sheet)](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) — the pattern used for admin POST/PUT.
- [TanStack Query invalidation with SSE](https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation) — `queryClient.invalidateQueries` keyed by entity; SSE-driven invalidation.
- [psycopg3 async pool sizing](https://www.psycopg.org/psycopg3/docs/advanced/pool.html) — informs the 10-connection pool default.
- [MQTT retained messages + LWT (HiveMQ knowledge base)](https://www.hivemq.com/blog/mqtt-essentials-part-8-retained-messages/) — informs the retained-state-per-cube design.

### Cross-references within this project's planning

- [`.planning/PROJECT.md`](../PROJECT.md) — scope, constraints, decisions.
- [`.planning/research/STACK.md`](./STACK.md) — every technology choice cited here originates there.
- [`.planning/research/FEATURES.md`](./FEATURES.md) — every feature mentioned (and every anti-feature avoided) traces to that document.

---

*Architecture research for: GRUVAX — Pi 5 kiosk + FastAPI + MQTT-stub + Postgres on shared host.*
*Researched: 2026-05-18.*

# Requirements: GRUVAX

**Defined:** 2026-05-19
**Core Value:** Type artist / title / label / catalog# → see the right cube (and a sub-cube position estimate) on the touchscreen within ~200 ms. Everything else is decoration.

## v1 Requirements

73 requirements. Table-stakes items are baseline expectations from FEATURES.md; differentiator items are the ones explicitly accepted into v1 during scoping.

### Search & Lookup

- [x] **SRCH-01**: User can type-ahead search across artist, title, label, and catalog#; results return within ~200 ms perceived from keystroke
- [x] **SRCH-02**: User sees a ranked results list with tap-to-select; the top result auto-highlights its cube on the grid
- [x] **SRCH-03**: User can clear the search field with a visible X button (touch-friendly tap target)
- [x] **SRCH-04**: User sees a "no results" state when the query matches nothing in the collection
- [x] **SRCH-05**: User sees a loading indicator only when a search request exceeds ~300 ms (no flicker for fast responses)
- [x] **SRCH-06**: Search debounces keystrokes client-side to avoid hammering the backend
- [x] **SRCH-07**: Search returns a "did you mean" suggestion when no high-rank FTS match exists but a trigram-similar candidate does
- [x] **SRCH-08**: Search detects numeric-leading queries and boosts catalog-number field weight in ranking
- [ ] **SRCH-09**: User sees a per-session recently-pulled list (kiosk-local, cleared on idle timeout)

### Cube-Level UX

- [x] **CUBE-01**: Kiosk renders a configurable N×4×4 grid driven by per-unit config (initial deployment: 2 units, 32 cubes)
- [x] **CUBE-02**: On search selection, the primary cube containing the matched record is visibly highlighted
- [x] **CUBE-03**: When the matched record's label spans multiple cubes, all spanned cubes show a secondary highlight behind the primary
- [x] **CUBE-04**: Sub-cube position estimate is rendered as a horizontal range bar inside the primary cube; bar may cross a cube boundary when the interval does
- [x] **CUBE-05**: Empty cubes (no boundary data, or boundaries indicate emptiness) render in a distinct, desaturated visual state
- [x] **CUBE-06**: Each cube shows a persistent address overlay (e.g., row letter + column number)
- [ ] **CUBE-07**: Each cube displays a fill-level indicator computed from the boundary range
- [x] **CUBE-08**: Selection-lands animation choreographs label-span fade-in, primary-cube pulse, and sub-cube bar slide-in within ≤600 ms; the animation is interruptible by a new search
- [ ] **CUBE-09**: User can tap a cube to reveal what's in it (reverse-lookup side panel listing the cube's first/last boundary records and a representative subset)
- [x] **CUBE-10**: Single-record labels render with a tick-mark indicator inside the cube rather than a width-proportional range bar

### Position Estimation

- [x] **POS-01**: A parser/comparator module normalizes catalog numbers (case-fold, separator-collapse, NFKC, numeric-aware split) and is used by every algorithm and the boundary save validator; raw-string comparison is forbidden
- [x] **POS-02**: `GET /api/locate?release_id=` returns `LocateResult{primary_cube, label_span, sub_cube_interval, confidence, generated_at, estimator_version}` matching the architecture contract
- [x] **POS-03**: The estimator hits p95 ≤ 50 ms with no DB calls during compute; boundary data is held in an in-memory cache
- [x] **POS-04**: The boundary cache loads at process startup and invalidates on `boundary_changed` events
- [x] **POS-05**: v1 ships two estimator implementations behind the same contract: an index-based interpolator (INTERPOLATION.md §4.1) as primary and a cube-only fallback (§4.8) for timeouts/low-confidence cases
- [x] **POS-06**: A developer A/B harness runs candidate algorithms against the local CSV (gitignored) and emits per-distribution-shape error metrics

### Admin / Data Management

- [ ] **ADMN-01**: Admin can log in via a single PIN (Argon2id-hashed in DB) on either mobile or kiosk
- [ ] **ADMN-02**: Admin session uses a sliding-window timeout (5–10 min idle); a visible countdown appears in the last 60 seconds before logout
- [ ] **ADMN-03**: Admin can enter cube boundaries manually via a form with autocomplete drawn from the collection (no free-text accepted unless explicitly confirmed)
- [ ] **ADMN-04**: Admin can run a guided setup wizard that walks cube-by-cube and infers each boundary from a single point of transition
- [ ] **ADMN-05**: Admin can upload a CSV/YAML seed file; the system validates per-row and shows a diff preview before atomic replace
- [ ] **ADMN-06**: All boundary saves are validated against the collection; mismatches are flagged with trigram-near-misses surfaced for confirmation
- [ ] **ADMN-07**: All boundary mutations show a diff preview with affected cubes highlighted before commit
- [ ] **ADMN-08**: Admin can log out manually from any screen
- [ ] **ADMN-09**: Every boundary mutation is recorded in an append-only change log grouped by change-set; admin can undo/revert by change-set
- [ ] **ADMN-10**: A reshuffle wizard guides the admin through post-haul boundary updates and commits the result as a single atomic change-set
- [x] **ADMN-11**: Admin boundary edits on mobile cause the kiosk to re-render the affected cubes without manual refresh
- [ ] **ADMN-12**: The boundary entry UI can auto-suggest a midpoint catalog# for a given cube based on the natural sort of adjacent populated cubes

### LED Control Surface (hardware stubbed in v1)

- [ ] **LED-01**: `POST /api/leds/illuminate` publishes a Pydantic-validated JSON message to `gruvax/v1/leds/{unit}/{cube}` on the internal MQTT broker
- [ ] **LED-02**: A multi-cube label-span illumination message can be published as a single payload listing the affected cubes
- [ ] **LED-03**: A sub-cube interval illumination message includes `pixel_start`/`pixel_end` so future firmware can light a range of LEDs within a cube
- [ ] **LED-04**: Admin can configure a brightness ceiling, separated into ambient (label-span) and active (position) settings
- [ ] **LED-05**: Admin can configure colors per system state (label-span, position, error, setup, all-off); defaults are accessibility-respecting (not red/green for active/error)
- [ ] **LED-06**: A visible "All off" admin button publishes a clear-retained-state message on `gruvax/v1/leds/all`
- [ ] **LED-07**: A test/diagnostic endpoint cycles every cube through a known color sequence and logs any status responses
- [ ] **LED-08**: MQTT topics are versioned (`gruvax/v1/...`); payloads are validated against a documented Pydantic schema
- [ ] **LED-09**: A layered illuminate command can specify both label-span and precise-position parameters in a single API call
- [ ] **LED-10**: Illuminate payloads accept an optional `transition: {style, duration_ms}` field declaring intent (fade / pulse / instant)

### Realtime / Multi-Device

- [x] **RTM-01**: Kiosk subscribes to a server-sent-events stream and re-renders affected cubes on `boundary_changed` events without manual refresh
- [x] **RTM-02**: Multiple simultaneous searches (kiosk and mobile) execute concurrently without server-side serialization
- [x] **RTM-03**: Admin edits show optimistic UI updates with rollback on server error
- [x] **RTM-04**: When admin is actively editing boundaries, the kiosk shows a subtle "boundaries updating" indicator on the affected cube range

### Offline / Resilience

- [ ] **OFF-01**: Kiosk displays an offline banner when the backend is unreachable (detected via SSE state and a periodic health-check fallback)
- [ ] **OFF-02**: Search input is disabled while offline; placeholder text updates accordingly
- [ ] **OFF-03**: Kiosk auto-reconnects with exponential backoff (1s → 2s → 5s → 10s → 30s cap)
- [ ] **OFF-04**: Kiosk shows a brief success indicator on the first successful request after reconnection

### Observability & Maintenance

- [ ] **OBS-01**: `/healthz` endpoint reports overall status plus per-subsystem reachability (Postgres, MQTT broker) and version
- [ ] **OBS-02**: Service logs structured JSON with log level configurable via environment variable
- [ ] **OBS-03**: Schema changes ship as Alembic migrations; CI proves upgrade-then-downgrade-then-upgrade round-trips clean
- [ ] **OBS-04**: `/version` endpoint reports git SHA, build timestamp, and environment
- [ ] **OBS-05**: Admin diagnostics surface a slow-query log: any search exceeding the 200 ms SLO is flagged
- [ ] **OBS-06**: Admin diagnostics show discogsography-sync staleness (latest `collection_items.updated_at`)
- [ ] **OBS-07**: Admin diagnostics include an aggregate top-N most-searched records page (no per-query text persisted)

### Privacy (Multi-User Floor)

- [ ] **PRIV-01**: Search history lives only in kiosk session storage and is cleared on idle timeout
- [ ] **PRIV-02**: Search queries are never persisted with text + timestamp to any server-side store; only aggregate counters per record
- [ ] **PRIV-03**: Admin-visible search stats are aggregate-only; no per-session or per-visitor breakdown
- [ ] **PRIV-04**: A "Reset kiosk" button is visible on the kiosk to any user (no PIN required) and clears the local session state

### Backup / Data Portability

- [ ] **BAK-01**: Admin can export current cube boundaries to YAML/JSON on demand, matching the import schema
- [ ] **BAK-02**: Admin can export and import color/LED settings via the same schema (separate section)

### Deployment

- [x] **DEP-01**: GRUVAX deploys via Docker Compose as a sibling of discogsography; services include `gruvax-api` and `mosquitto`; frontend is served via FastAPI `StaticFiles`
- [x] **DEP-02**: The schema is named `gruvax` within the shared Postgres instance; reads from discogsography go exclusively through a `gruvax.v_collection` view contract
- [ ] **DEP-03**: The Mosquitto broker has no Compose `ports:` exposure in v1 (internal-network-only until the hardware milestone); persistence is configured with explicit retained-message expiry semantics
- [ ] **DEP-04**: Each Compose service declares log-size limits to prevent disk exhaustion on `lux`
- [ ] **DEP-05**: Each Compose service declares a healthcheck integrated with `restart: unless-stopped` for self-healing on transient failure

## v2 / Backlog

Tracked but not in the current roadmap. Items move to v1 only via explicit roadmap update.

### From PROJECT.md scope decisions

- Real LED hardware end-to-end (ESP32/Arduino firmware, WS2812B wiring, MQTT subscriber) — separate milestone
- Screensaver / browse / cover-art slideshow mode — black screen on idle for v1
- Periodic JSON export of `cube_boundaries` to git as a portable backup
- RFID / per-record tagging — deterministic ordering makes this unnecessary
- OAuth / SSO multi-user authentication

### From v1 scoping deferrals

- **Service-worker cached search results** for graceful offline degradation (R1)
- **Per-visitor PIN** with isolated session history (R2)
- **Animated reshuffle preview** with cube-by-cube diff visualization (R3)
- **Always-on ambient LED mode** — fast-follow after v1 (moved from anti-features into backlog per scoping)

### From FEATURES.md future-tier surfacing

- Search-history-driven autocomplete (once recently-pulled has data)
- Favorites / wishlist surfaced inline from Discogs wantlist
- Filter by year, label, condition, format
- Saved searches
- Cube-zoom view (per-cube list expansion)
- Heat-map of cube retrieval frequency
- Versioned boundary snapshots with named labels ("Before Vegas haul")
- Density-imbalance-driven reshuffle suggestion
- Multi-collection / multi-shelving-system admin
- 30 s preview from Discogs / Apple Music / Spotify / MusicBrainz
- Last.fm scrobble integration on confirm
- "What's this label" tour / "related releases" via Neo4j (discogsography MCP)
- Presence indicator ("admin online on mobile")
- Push notifications for kiosk-detected issues
- Wi-Fi RSSI quality indicator
- Pre-loading recently-pulled on app load
- OpenTelemetry traces
- Power-budget enforcement (post-hardware) — max simultaneous lit cubes
- Per-cube LED count auto-detection
- Status reporting back from firmware
- Search-history opt-in for admin (defaults off)
- Queue admin edits in IndexedDB when mobile loses connectivity

## Out of Scope

Permanently excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Voice search | No microphone on Pi 5; environmental noise; latency would break the 200 ms budget; privacy implications |
| ML personalization / recommendations | Single-user app, no training population; conflicts with deterministic ordering invariant |
| Cross-collection (federated Discogs) search | GRUVAX is a *physical-location* finder; searching records the user does not own confuses the "highlight cube" affordance |
| Search history visible to other visitors | Houseguest privacy; per-session only |
| Per-record manual position override | Breaks the deterministic ordering invariant that makes computation possible; ballooning data model; reshelve instead |
| Boundary-edit by drag on the cube grid | Slower than form input with autocomplete; invites accidental destruction |
| Audit trail visible to non-admins | Single-user home product; no compliance regime |
| AI-suggested boundaries from album art / OCR | Different product shape; deterministic ordering means input is the sort itself, not a photo |
| Per-record album art tiles inside cubes | At ~80 px cubes on a 7" screen, album art is illegible; album art appears in the results panel instead |
| Photo-real / 3D cube rendering | Trades fidelity for clarity; stylized 2D is more legible at a glance |
| Animated "fly to cube" 3D camera | Slows down a glance-then-look-at-shelves interaction |
| Per-pixel direct LED control from kiosk UI | Scope-creep risk; reserved for an optional "creative mode" behind admin flag, not a v1 surface |
| Music-visualization LED sync (turntable signal-tap) | Hardware work; value-over-baseline low; recordShelf parked this |
| Hard-coded LED color palette | Accessibility (color-blind users); colors are admin-configurable |
| WebSocket for bidirectional everything | YAGNI; SSE is correct for one-way invalidations |
| Hard concurrent admin-edit locking | Single-admin product; last-write-wins + change log is sufficient |
| Real-time collaborative cursor / CRDT editing | Single admin |
| Full offline-first PWA with all 3K records cached | Wrong trade-off: stale boundaries are misshelf cause #1 |
| Local SQLite mirror on the Pi | Doubles maintenance; sync issues become a bug source |
| Grafana + Prometheus stack | Two more containers and alert rules for one user and one app; admin diagnostics page is sufficient |
| Sentry / cloud error-tracking SaaS | Egress + cost; `docker logs` is enough on home LAN |
| Built-in record player remote / Bluetooth integration | Different product (Roon / Plex / vendor app does this) |
| Track-by-track digital playback alongside vinyl | Plex / Roon territory; confuses what GRUVAX is |
| Discogs user account linking | Houseguests don't log into Discogs at your kiosk |
| Full search history server-side | If stored, it's leakable; aggregate counters only |
| Automatic git commits of boundary state | Brings git-as-dependency, credentials, and a repo into the runtime; Postgres backup is correct here |
| Cloud-sync backup (Dropbox / Drive) | Wrong shape; home-LAN product |

## Traceability

Every v1 requirement maps to exactly one phase. Phase definitions live in ROADMAP.md.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SRCH-01 | Phase 1 — First Search → Cube Highlight | Complete |
| SRCH-02 | Phase 1 — First Search → Cube Highlight | Complete |
| SRCH-03 | Phase 1 — First Search → Cube Highlight | Complete |
| SRCH-04 | Phase 1 — First Search → Cube Highlight | Complete |
| SRCH-05 | Phase 1 — First Search → Cube Highlight | Complete |
| SRCH-06 | Phase 1 — First Search → Cube Highlight | Complete |
| SRCH-07 | Phase 2 — Real Position Estimation | Complete |
| SRCH-08 | Phase 2 — Real Position Estimation | Complete |
| SRCH-09 | Phase 4 — Realtime + Offline Resilience | Pending |
| CUBE-01 | Phase 1 — First Search → Cube Highlight | Complete |
| CUBE-02 | Phase 1 — First Search → Cube Highlight | Complete |
| CUBE-03 | Phase 2 — Real Position Estimation | Complete |
| CUBE-04 | Phase 2 — Real Position Estimation | Complete |
| CUBE-05 | Phase 1 — First Search → Cube Highlight | Complete |
| CUBE-06 | Phase 1 — First Search → Cube Highlight | Complete |
| CUBE-07 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| CUBE-08 | Phase 2 — Real Position Estimation | Complete |
| CUBE-09 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| CUBE-10 | Phase 2 — Real Position Estimation | Complete |
| POS-01 | Phase 1 — First Search → Cube Highlight | Complete |
| POS-02 | Phase 1 — First Search → Cube Highlight | Complete |
| POS-03 | Phase 2 — Real Position Estimation | Complete |
| POS-04 | Phase 1 — First Search → Cube Highlight | Complete |
| POS-05 | Phase 2 — Real Position Estimation | Complete |
| POS-06 | Phase 2 — Real Position Estimation | Complete |
| ADMN-01 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-02 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-03 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-04 | Phase 6 — Wizards + Import/Export | Pending |
| ADMN-05 | Phase 6 — Wizards + Import/Export | Pending |
| ADMN-06 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-07 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-08 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-09 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| ADMN-10 | Phase 6 — Wizards + Import/Export | Pending |
| ADMN-11 | Phase 4 — Realtime + Offline Resilience | Complete |
| ADMN-12 | Phase 3 — Admin Loop (PIN + Manual Entry + Undo) | Pending |
| LED-01 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-02 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-03 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-04 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-05 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-06 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-07 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-08 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-09 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| LED-10 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| RTM-01 | Phase 4 — Realtime + Offline Resilience | Complete |
| RTM-02 | Phase 4 — Realtime + Offline Resilience | Complete |
| RTM-03 | Phase 4 — Realtime + Offline Resilience | Complete |
| RTM-04 | Phase 4 — Realtime + Offline Resilience | Complete |
| OFF-01 | Phase 4 — Realtime + Offline Resilience | Pending |
| OFF-02 | Phase 4 — Realtime + Offline Resilience | Pending |
| OFF-03 | Phase 4 — Realtime + Offline Resilience | Pending |
| OFF-04 | Phase 4 — Realtime + Offline Resilience | Pending |
| OBS-01 | Phase 7 — Observability + Deployment Hardening | Pending |
| OBS-02 | Phase 7 — Observability + Deployment Hardening | Pending |
| OBS-03 | Phase 7 — Observability + Deployment Hardening | Pending |
| OBS-04 | Phase 7 — Observability + Deployment Hardening | Pending |
| OBS-05 | Phase 7 — Observability + Deployment Hardening | Pending |
| OBS-06 | Phase 7 — Observability + Deployment Hardening | Pending |
| OBS-07 | Phase 7 — Observability + Deployment Hardening | Pending |
| PRIV-01 | Phase 4 — Realtime + Offline Resilience | Pending |
| PRIV-02 | Phase 4 — Realtime + Offline Resilience | Pending |
| PRIV-03 | Phase 4 — Realtime + Offline Resilience | Pending |
| PRIV-04 | Phase 4 — Realtime + Offline Resilience | Pending |
| BAK-01 | Phase 6 — Wizards + Import/Export | Pending |
| BAK-02 | Phase 6 — Wizards + Import/Export | Pending |
| DEP-01 | Phase 1 — First Search → Cube Highlight | Complete |
| DEP-02 | Phase 1 — First Search → Cube Highlight | Complete |
| DEP-03 | Phase 5 — LED Contract over MQTT (Hardware Stubbed) | Pending |
| DEP-04 | Phase 7 — Observability + Deployment Hardening | Pending |
| DEP-05 | Phase 7 — Observability + Deployment Hardening | Pending |

**Coverage:**
- v1 requirements: 73 total
- Mapped to phases: 73 (100%)
- Unmapped: 0

---
*Requirements defined: 2026-05-19*
*Last updated: 2026-05-19 after roadmap creation (traceability populated)*

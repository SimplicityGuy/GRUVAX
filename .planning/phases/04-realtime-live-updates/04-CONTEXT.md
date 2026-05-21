# Phase 4: Realtime Live Updates - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Admin boundary edits propagate to an open kiosk **live, without a manual refresh**. This phase
builds the realtime spine that Phase 3 explicitly deferred: an in-process event bus, a `GET /api/events`
SSE channel, and the kiosk-side `EventSource` consumer that turns `boundary_changed` events into cube
re-renders. While the owner is mid-edit, the affected cube range shows a subtle "boundaries updating"
shimmer (`admin_editing`); admin edits apply optimistically on the owner's own device with rollback on
server error; and two simultaneous searches (kiosk + mobile) run concurrently with no server-side
serialization (the SSE endpoint must hold **no** DB connection).

This is the **happy-path (Paths-axis) slice** carved out of the original "Realtime + Offline Resilience"
phase via SPIDR. It delivers the user story:

> **As a** kiosk visitor, **I want to** see the shelf map update live as the owner re-files records,
> **so that** I can always trust the kiosk reflects the current shelf layout without refreshing.

**In scope (5 requirements):** ADMN-11, RTM-01, RTM-02, RTM-03, RTM-04.

Concretely, Phase 4 delivers:
- **In-process event bus** (`src/gruvax/events/bus.py`) — `asyncio.Queue`-per-subscriber fan-out
  (ARCHITECTURE Pattern 2), published to from the admin commit path.
- **SSE endpoint** `GET /api/events` (`src/gruvax/api/events.py`) — long-lived, **no DB dependency**
  (Pitfall 10), `X-Accel-Buffering: no` + `Cache-Control: no-store` + 15s ping (Pitfall 8). Emits
  `boundary_changed`, `admin_editing`, `server_hello`, `server_shutdown`.
- **Bus fan-out wired into the existing admin commit seam** — `put_cube_boundary` and `bulk_write_cubes`
  in `src/gruvax/api/admin/cubes.py` already call `cache.invalidate()` *after* the DB transaction;
  this phase adds `bus.publish('boundary_changed', {cube_ids, change_set_id})` at that same post-commit
  seam.
- **`admin_editing` heartbeat** — a lightweight signal from the admin client (debounced) so the kiosk
  can shimmer the affected range while the owner is mid-edit, before commit.
- **Kiosk SSE consumer** — a single `EventSource` mounted in `KioskView.tsx` that dispatches into
  TanStack Query invalidations + a new Zustand `connectivity.sseConnected` flag.
- **Optimistic admin edits with rollback** (owner-device-local) and the "highlight follows the record"
  re-locate behavior on the kiosk.
- **Reconnect resync** — on any (re)connect, invalidate boundary-derived queries (the in-process bus
  has no replay).

**Out of scope (deferred slices, do NOT build here):**
- **Offline Resilience (OFF-01..04)** → next slice: visible offline banner, disabled search input +
  placeholder text, exponential-backoff tuning (1→2→5→10→30s), reconnection success indicator,
  periodic health-check fallback. *This phase produces the `sseConnected` flag the Offline slice
  consumes, but renders no banner/disabled-input UX.*
- **Privacy + Recently-Pulled (SRCH-09, PRIV-01..04)** → later slice: session-storage recently-pulled
  list, no-PIN reset button, no query persistence, aggregate-only `gruvax.search_counters`.
- **LED color/brightness/diagnostics + MQTT contract** → Phase 5.

</domain>

<decisions>
## Implementation Decisions

### "Boundaries updating" indicator (RTM-04)
- **D-01:** The cue appears **while the owner is mid-edit**, not only at commit. The admin device emits
  a debounced `admin_editing` signal when the owner opens a cube's editor / changes values; the server
  fans it out so the kiosk shimmers the affected cube range *before* commit. (Satisfies roadmap
  criterion 1: "while the admin is mid-edit ... and clears on commit.")
- **D-02:** The cue is an **ambient shimmer on the affected cube range — no text.** It respects the
  "subtle" wording and the design rule **never recolor a lit cell**; motion follows LED-physics from
  the design spec. Exact visual is within the Nordic Grid system (delegate fine detail to ui-phase).
- **D-03:** The cue **clears on commit** (when the matching `boundary_changed` arrives) **and**
  auto-clears after **~60s of no editing activity** as a safety, so a canceled/abandoned edit never
  leaves the shimmer stuck. Mirrors ARCHITECTURE's 60s soft-lock window.

### Live re-render & stale highlight (RTM-01, ADMN-11)
- **D-04:** On a `boundary_changed` event, the kiosk re-renders the affected cubes (invalidate
  `['cube', unit,row,col]`, `['units']`, and admin keys per ARCHITECTURE's consumer pattern) **without
  a manual refresh** — this is the ADMN-11 / RTM-01 core.
- **D-05:** **The highlight follows the record.** If a visitor has an active selection
  (`selectedReleaseId` set) and a `boundary_changed` could move that record, the kiosk **re-runs
  `locate`** (invalidate `['locate', release_id]`) so the highlight relocates to the record's new cube.
  This extends ARCHITECTURE's consumer, which currently invalidates only `['cube', ...]`/admin keys —
  the active `locate` invalidation must be added.
- **D-06:** The move presents as a **re-glow at the new cube**: fade the old cube's lit state off,
  spring the new cube on (LED-physics). No cross-grid slide animation — cheaper per-frame on the Pi 5
  (Pitfall 16) and reads clearly as "it relocated."

### Optimistic edits & rollback (RTM-03)
- **D-07:** On the **owner's own device**, boundary edits apply **optimistically** (grid updates
  instantly). On server rejection: **revert the grid + show a sentence-case, plain-language toast**
  ("Couldn't save that change — reverted.") **+ keep the attempted values in the editor for retry**
  (reuse Phase 3's client-side `pendingChangeSet` so nothing is lost). No technical jargon in the
  message (voice & tone).
- **D-08:** **Optimistic is owner-device-local only.** The kiosk and any second admin client update
  **only on a committed `boundary_changed`** fan-out — they never display a change that could roll back.
  (The kiosk still shimmers via `admin_editing` during the edit; it just does not re-render boundary
  *data* until commit.) This keeps the public kiosk free of flicker/wrong data.

### Concurrency (RTM-02)
- **D-09:** The **SSE endpoint holds no DB connection** for the life of the stream — it depends only on
  the in-process event bus (`bus.subscribe()` → `asyncio.Queue`), per ARCHITECTURE Pattern 2 and
  Pitfall 10. If it ever needs DB data it acquires + releases a pool connection inline. This is what
  lets two simultaneous searches (kiosk + mobile) run without serialization or pool starvation.

### Connectivity scope line (this phase vs deferred Offline slice)
- **D-10:** This phase builds the **SSE channel + Zustand `connectivity.sseConnected` flag** (set via
  `EventSource` `onopen`/`onerror`/`server_shutdown`) **+ reconnect resync** — and **nothing visible
  beyond that.** The offline banner, disabled search input, placeholder copy, backoff tuning, success
  indicator, and health-check fallback all stay in the **deferred Offline Resilience slice**, which
  consumes the `sseConnected` flag this phase produces.
- **D-11:** **Resync on any (re)connect.** Because the in-process bus has **no event replay**, any
  `boundary_changed` fired while a kiosk is briefly disconnected is lost. On every successful
  (re)connect the kiosk invalidates the boundary-derived queries (`['units']`, `['cube', ...]`,
  `['admin','cubes']`) to catch up; on `server_hello` (API restart) it additionally refetches settings.
  Native `EventSource` handles the reconnection itself.

### Claude's Discretion (delegated to researcher / planner / ui-phase)
- **`admin_editing` heartbeat shape & debounce** — exact endpoint (e.g., `POST /api/admin/editing`
  vs piggybacking on the validate/dry-run call), payload (`{cube_ids, editing: bool}`), debounce
  interval (~250–500 ms), and TTL (~60s server-side decay matching D-03). Pick the simplest design
  that satisfies D-01/D-03.
- **`boundary_changed` payload** — confirm `{cube_ids: [{unit,row,col}], change_set_id}` (one event per
  change-set, listing all affected cubes — not per-cube), matching ARCHITECTURE line 248 / 461.
- **Multi-admin soft-lock specifics** — two admins editing the same cube: last-write-wins at the DB
  (history preserves both), `admin_editing` renders the shimmer; no hard locking (FEATURES Category 5 /
  ARCHITECTURE edge-case table). Edge case for a single-operator app — keep it minimal.
- **Bus internals** — `EventBus` queue `maxsize`, slow-subscriber backpressure (drop-oldest vs
  disconnect), and `unsubscribe` cleanup on client disconnect, per ARCHITECTURE Pattern 2 sketch.
- **Optimistic-mutation wiring** — TanStack Query `onMutate`/`onError`/`onSettled` rollback mechanics
  on the admin client; reuse the existing `adminClient.ts` mutation patterns.
- **Pi frame-budget validation** for the shimmer + re-glow (Pitfall 16) — keep p95 frame time < 16ms.
- **All visual/interaction detail** (shimmer styling, re-glow timing, toast styling) → `/gsd-ui-phase 4`
  within Nordic Grid (consume tokens; never hardcode hex).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Realtime Architecture & Contracts (authoritative for this phase)
- `.planning/research/ARCHITECTURE.md` — **Pattern 2 (In-Process Event Bus for SSE Fan-Out,
  `events/bus.py` sketch)**, the **`GET /api/events` SSE row** (events list + 15s ping), the **SSE
  consumer pattern** (`EventSource` + TanStack Query invalidation + `connectivity.sseConnected`), the
  **TanStack Query keys** and **Zustand state shape** (`connectivity`, `search.selectedReleaseId`,
  `highlight`), and the **edge-case table** (Pi loses Wi-Fi, gruvax-api restarts, concurrent boundary
  edits, SSE drops mid-edit).
- `.planning/research/PITFALLS.md` — **Pitfall 8** (SSE reverse-proxy buffering → `X-Accel-Buffering:
  no`, `Cache-Control: no-store`, default 15s ping; serve SPA via FastAPI StaticFiles, no nginx in v1),
  **Pitfall 10** (connection-pool exhaustion under SSE + concurrent search → SSE endpoint depends only
  on the bus, never a request-scoped DB session; pool sized 2× SSE + 5 spare ≈ 10), **Pitfall 16**
  (Pi 5 animation frame budget for the shimmer/re-glow).
- `.planning/research/STACK.md` — `sse-starlette` 2.x (SSE response class, ping/heartbeat,
  client-disconnect cleanup); native `EventSource` reconnection; TanStack Query 5 + Zustand 5.

### Requirements & Roadmap
- `.planning/REQUIREMENTS.md` — definitions for ADMN-11, RTM-01, RTM-02, RTM-03, RTM-04 (and the
  deferred OFF-01..04 / PRIV / SRCH-09 for scope-boundary awareness).
- `.planning/ROADMAP.md` — Phase 4 section: narrowed goal + 2 success criteria + the SPIDR split note.
- `.planning/PROJECT.md` — ~200ms perceived search SLO, home-LAN-only, "visiting friends" kiosk use,
  single-PIN/session model.

### Locked from Prior Phases (carry forward — do not re-decide)
- `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-CONTEXT.md` — the admin commit model
  (`boundary_history` by `change_set_id`, atomic bulk `POST /api/admin/cubes/bulk`, `Idempotency-Key`,
  CSRF double-submit, in-process `cache.invalidate()` after commit) and the **explicit Phase 4 deferral**
  of "SSE cross-device live refresh + `admin_editing` soft-lock."
- `.planning/phases/01-first-search-cube-highlight/01-CONTEXT.md` — boundary cache + `v_collection`
  read-only surface; `deps.py` provider pattern; routers imported inside `create_app()`.
- `.planning/phases/02-real-position-estimation/02-CONTEXT.md` — the `/api/locate` contract the kiosk
  re-runs when the highlight follows a moved record (D-05).

### Code Seams (the integration points this phase touches)
- `src/gruvax/api/admin/cubes.py` — **the bus publish seam**: `put_cube_boundary` (post-commit
  `cache.invalidate()` ~L321) and `bulk_write_cubes` (post-commit `cache.invalidate()` ~L765). Add
  `bus.publish('boundary_changed', {cube_ids, change_set_id})` *after* the transaction, never inside it
  (the file already documents "Pitfall A — cache.invalidate() is NEVER called inside the transaction").
- `src/gruvax/api/deps.py` — add a `get_event_bus` provider alongside `get_pool` /
  `get_boundary_cache`; the SSE endpoint depends on the bus, **not** the pool.
- `src/gruvax/app.py` — `create_app()` lifespan: instantiate the `EventBus`; import the new
  `events` router inside `create_app()` (Phase 1 circular-import convention); publish `server_hello`
  on startup / `server_shutdown` on shutdown.
- `frontend/src/routes/kiosk/KioskView.tsx` — mount the single `EventSource` `useEffect` here; it
  already uses TanStack Query (`useQuery` for units/cubes/locate) so it has `queryClient` access.
- `frontend/src/state/store.ts` — add a `connectivity` slice (`sseConnected`, `lastSeenAt`); already
  holds `selectedReleaseId`, `highlight`, `setLocateResult`, `animationToken` (drives D-05/D-06).
- `frontend/src/api/client.ts` / `frontend/src/api/adminClient.ts` — TanStack Query keys + the
  admin optimistic mutation (`onMutate`/`onError`/`onSettled`) for D-07.

### Design System (consume tokens; never hardcode hex)
- `design/gruvax-design-language.md` — Nordic Grid; cell states; **never recolor a lit cell**;
  LED-physics motion (spring-on / fade-off); ALL-CAPS labels; plain-language error copy.
- `design/gruvax-design-tokens.css`, `design/gruvax-design-tokens.json` — token contract.
- `CLAUDE.md` — conventions; Mermaid-only diagrams.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`src/gruvax/api/admin/cubes.py` commit path** — `cache.invalidate()` already fires post-commit in
  both `put_cube_boundary` and `bulk_write_cubes`; the bus publish slots in at the identical seam, so
  there is exactly one place to wire fan-out.
- **`src/gruvax/estimator/boundary_cache.py`** — `invalidate()`/reload already keeps the in-process
  estimator fresh; the SSE event tells *other devices* to refetch.
- **`KioskView.tsx` + TanStack Query** — units/cubes/locate are already queries; SSE invalidations hook
  into the existing `queryClient` cleanly.
- **`store.ts` highlight + `setLocateResult` + `animationToken`** — the re-glow (D-06) reuses the
  existing animation-token mechanism that GSAP already keys off.

### Established Patterns
- **Dependency providers in `deps.py`; routers imported inside `create_app()`** (circular-import fix).
- **psycopg `%s` placeholders, parameterized SQL, no f-string interpolation** (Phase 2 security).
- **cache mutation work happens AFTER the DB transaction commits** (documented "Pitfall A" in cubes.py)
  — the bus publish must follow the same rule.
- **Token-only CSS / design tokens; LED-physics motion** (no hardcoded hex; spring-on/fade-off).

### Integration Points
- New backend module `src/gruvax/events/bus.py` + new router `src/gruvax/api/events.py`
  (`GET /api/events`).
- New `admin_editing` heartbeat path (admin client → API → bus → kiosk).
- New frontend `connectivity` Zustand slice + single `EventSource` consumer in `KioskView.tsx`.
- Extended SSE consumer behavior beyond ARCHITECTURE's sketch: invalidate the **active `['locate', id]`**
  query (D-05) and **resync boundary queries on reconnect** (D-11).

</code_context>

<specifics>
## Specific Ideas

- ARCHITECTURE.md line ~248 / ~461 are the concrete copy-from references for the event names and the
  `boundary_changed` payload (`{cube_ids, change_set_id}`).
- ARCHITECTURE.md Pattern 2 (~L890–909) is the `EventBus` sketch (`subscribe()` → `asyncio.Queue(maxsize=64)`,
  `publish()` iterates subscribers) — start from it.
- `sse-starlette` default `ping=15` is intentional (flushes proxy buffers) — do not lengthen it (Pitfall 8).
- Integration-test target from Pitfall 8: end-to-end "admin PUT → kiosk SSE `boundary_changed`" latency
  **< 500 ms** (matches roadmap criterion 1's ~500 ms).
- Verification gates are **local** (no CI): backend `pytest` + `ruff` + `mypy`; frontend `eslint` +
  `build` + `vitest`.

</specifics>

<deferred>
## Deferred Ideas

- **Offline Resilience (OFF-01..04)** → next SPIDR slice (Paths edge-path): visible offline banner,
  disabled search input + placeholder, exponential backoff (1→2→5→10→30s cap), reconnection success
  indicator, periodic health-check fallback. This phase deliberately stops at the `sseConnected` flag.
- **Privacy + Recently-Pulled (SRCH-09, PRIV-01..04)** → later SPIDR slice: session-storage
  recently-pulled list, no-PIN "Reset kiosk" button, no search-query persistence, aggregate-only
  `gruvax.search_counters`.
- **Multi-replica SSE fan-out** (Redis Pub/Sub / NATS) → not v1; in-process bus dies with the process,
  which is exactly the wanted lifetime (ARCHITECTURE Pattern 2 trade-off note).
- **MQTT-routed kiosk updates** → rejected by ARCHITECTURE (Mosquitto is for LED hardware; in-process
  bus is microseconds and has no broker dependency).
- **Hard collaborative locking / CRDT for concurrent admin edits** → YAGNI for one operator; soft-lock
  shimmer only.

None of the above are in scope for Phase 4.

</deferred>

---

*Phase: 04-realtime-live-updates*
*Context gathered: 2026-05-21*

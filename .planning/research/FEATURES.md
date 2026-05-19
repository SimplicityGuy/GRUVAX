# Features Research — GRUVAX

**Domain:** Touchscreen kiosk + REST API + (deferred) RGB LED layer for navigating a ~3,000-record vinyl collection across 2 IKEA Kallax units (32 cubes).
**Closest reference category:** Personal collection management (LibraryThing, Roon, Plex Library, Discogs companion apps like My Vinyl+, Vizcogs) crossed with physical-location finder kiosks (library wayfinding, warehouse pick-to-light). The closest direct prior art is the **recordShelf** Hackaday project (Pi + WS2812B + Flask + Discogs JSON); GRUVAX differs by using *computed* boundaries instead of per-record tagging.
**Researched:** 2026-05-18
**Confidence:** HIGH on v1 scope categorization (it's anchored to PROJECT.md's explicit Active/Out-of-Scope lists). MEDIUM on differentiator framing (small, niche product category — anchors come from analogous domains rather than direct competitors).

---

## How to Read This Document

The user asked for ten feature categories, each with items classified as **table stakes / differentiator / anti-feature / future (post-v1)**. Within v1 Active, complexity is tagged **S/M/L** so requirements scoping has signal:

- **S (Small)** — single endpoint or component, days of work, no architectural decisions left
- **M (Medium)** — a couple endpoints + UI surface + data model touch, ~1 week, one or two design calls along the way
- **L (Large)** — multi-component feature with cross-cutting concerns (auth, realtime, persistence, UX), multiple weeks, several design decisions

A small number of items appear in *both* a "differentiator" cell and "future" cell — meaning the *idea* is differentiating but v1 ships a minimal slice and the polish lands later. I've called those out explicitly.

The user explicitly placed in **v1 Active** scope: type-ahead search, ranked results list, cube grid UI, position-estimation API (label-span + sub-cube interval), admin (mobile primary + kiosk fallback) with PIN + session timeout, admin-configurable color settings, LED endpoint with hardware stubbed, offline banner, Docker Compose deployment.

The user explicitly placed in **Out of Scope for v1 (but kept in backlog)**: real LED hardware end-to-end, screensaver/browse/cover-art slideshow, periodic JSON export backup, multi-user auth, RFID tagging.

I respect those boundaries. Where evidence suggests reconsidering, I flag it explicitly with a "RECONSIDER" annotation rather than smuggling things into v1.

---

## Category 1 — Search & Lookup

GRUVAX's Core Value is "keystroke to right cube ≤ 200 ms." Search UX is the product.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Type-ahead search over artist, title, label, catalog# | Stated in Active scope; modern users assume autocomplete from keystroke 2 onward. | **M** | 200ms RTT budget means server-side Postgres FTS (`tsvector` over artist+title+label+catalog#) + a 100–150ms debounce on the client. Cache the last 10 query→result sets in Zustand to avoid redundant calls when the user backspaces. |
| Ranked results list with tap-to-select | Active scope; the bottom half of the typeahead UX. | **S–M** | Ranking signal hierarchy (proposed): exact catalog# match > prefix match on title/artist > FTS rank (`ts_rank_cd`) > trigram similarity for typos. Top result auto-highlights the cube; tapping any result re-highlights. |
| Clear search / X button | Standard typeahead affordance. | **S** | A 7" touchscreen with no keyboard makes manual clearing essential. Tap-target ≥ 44pt. |
| Visible "no results" state | If a user types something not in the collection they need to know — silence is a bug. | **S** | Tie to "did you mean" (differentiator below) once trigram is wired up. |
| Loading / pending state for slow requests | Network on a Pi over LAN is usually fast, but a spinner ≥ 300ms is the conventional threshold. | **S** | If the request resolves in < 300ms, render nothing; if longer, show a subtle progress indicator. Don't disable input. |
| Keystroke debouncing | Sub-200ms RTT only works if you're not hammering the server. | **S** | 100–150ms debounce; `useDeferredValue` in React 19 handles this idiomatically alongside `useTransition`. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Did you mean" / typo correction | Cataloging is messy and so is human input. `BLP` vs `BLP-` vs `Blp` should all resolve. | **M** | Postgres `pg_trgm` (`similarity()` + `%` operator with GIN index) handles fuzzy matching alongside the FTS index. Surface "did you mean: …" only when the top FTS result has `ts_rank < threshold` AND a trigram suggestion exists at higher similarity. Avoids being annoying on perfect matches. |
| Catalog-number-first parsing | Power users know catalog numbers; recognizing a numeric-leading query and prioritizing catalog# match is a sub-second win. | **S** | A trivial regex check on the query: if it matches `\w{1,6}[\s-]?\d+`, boost catalog# field. No ML, no model — heuristic. |
| Filter by format (LP / 7" / 12" / CD) | Discogs ships this; users coming from Discogs apps will look for it. | **S** | If `releases.format` is reliably populated in discogsography, expose as a filter chip row. If not, defer. |
| Single-key keyboard shortcuts on physical keyboard (for desk dev/test) | Not on touchscreen UX, but a kiosk that's also driven from a dev's mobile/laptop loves `Cmd+K` to focus search. | **S** | Standard `cmdk` library handles this for free. |
| Recently-pulled list (persisted, ~last 10) | Re-finding the album you played last night is a high-frequency journey. | **S–M** | Local-storage on the kiosk; or server-side if multi-device sync matters (it might — see Category 5). MVP: client-side only. See Category 9 for the privacy angle. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Voice search | Sounds cool. | Pi 5 has no mic; environmental noise near a turntable is awful; privacy implications; ASR latency would break the 200ms budget. | Stick to typing. |
| ML-powered relevance / personalization | "What if it learned my taste?" | One-user app. Personalization needs a population to train on. The whole premise of a deterministic ordering is *known* answers, not surprises. | Heuristic ranking is correct here. |
| Cross-collection search (federated Discogs catalog) | Tempting because discogsography has it. | GRUVAX is a *physical-location* finder; searching records you don't own and can't find on your own shelves is a different product (and would confuse the "highlight cube" affordance — there's no cube). | Discogs.com is one click away; don't replicate it here. |
| Search history visible to other visitors | "Like Spotify recently played" | A houseguest searching their own taste shouldn't leak that to the owner's next session, and vice-versa. | Per-session history only, cleared on idle timeout. See Category 9. |

### Future (post-v1)

- **Search-history-driven autocomplete** — once recently-pulled exists for a few months, suggest from it before the FTS layer. Cheap win, but needs data accumulation.
- **Favorites / wishlist surfaced inline** — already in discogsography (Discogs wantlist sync); render a star next to wantlist hits. Trivial once it's plumbed.
- **Filter by year, label, condition** — Discogs apps have this. Useful for crate-digging UX, not for "find this record now." Defer.
- **Saved searches** — Discogs feature. Likely overkill at 3K records.

---

## Category 2 — Cube-level UX

This is where GRUVAX is *unique* among collection apps. CSS Grid + DOM solves the layout cheaply (STACK.md confirms); the design challenge is what state to convey *inside* a cube.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Configurable N×4×4 grid render | Active scope; the visual core of the kiosk. | **M** | CSS Grid with `grid-template-rows/columns` driven by per-unit config. Render units side-by-side with a visible gap to mirror the physical install. |
| Single-cube highlight (the "main" cube the record lives in) | The product's core promise. | **S** | A single CSS class transition + GSAP one-shot for the glow/pulse. |
| Multi-cube label-span highlight | Catalog numbers within a label can span multiple cubes; the user needs to see the range to scan their hand across. | **M** | Render label-span as a secondary visual layer behind the primary cube. Distinct color (admin-configurable per Category 4). Sample case: a Blue Note run spans 4 cubes — those 4 light up dim purple, with the precise sub-cube position glowing brighter. |
| Sub-cube position indicator (range bar) | The position estimate is an interval, not a point. Conveying "somewhere in the right third of cube 12" is the table-stakes interpretation of the API contract. | **M** | A horizontal bar overlay inside the highlighted cube, drawn with the sub-cube interval. If interval crosses a cube boundary, draw a partial bar in each cube. Animate the entry (GSAP `from` with `scaleX`). |
| Empty-cube visual state | Some cubes will be empty during reshuffles; rendering them identical to populated cubes is misleading. | **S** | A subtle desaturation/border style. Drives from the boundary data: cube has no `first_*`/`last_*` pair. |
| Cube number / label-letter overlay | When the user is looking at the screen but not the shelf, knowing "this is cube 7" is reassuring. | **S** | Persistent small label in each cube corner; toggleable in admin if it gets in the way visually. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Fill-level indicator (how full each cube is) | After repeated reshuffles, knowing which cubes have headroom matters for the owner. Not for visitors. | **S–M** | Computed from the boundary range and an estimate of records per cube. If the per-label catalog-number density is known (it is — from discogsography), fill is `(last_in_cube - first_in_cube) / cube_capacity_estimate`. Render as a thin gauge bar across the cube footer. |
| Single-record-label visualization | An anomaly case where one label = one record. Rendering it identically to a fat multi-record label hides the asymmetry. | **S** | Different cube-internal treatment — perhaps a single tick rather than a range bar. Falls out naturally if the range bar renders width proportional to (interval_size / cube_size). |
| "Selection lands" animation choreography | The Core Value moment. Crisp animation = satisfying product. Sluggish or absent = feels broken. | **M** | GSAP timeline: search resolves → label-span dims in → primary cube pulses → sub-cube bar slides in → settle. Total budget ~400–600ms perceived, but interruptible (next search cancels in-flight animation). |
| Hover / tap-on-cube reveals what's in it | Reverse lookup — "what's in cube 18?" — is a genuinely useful kiosk affordance. | **M** | Tap a cube → side panel shows `[first_label first_catalog]` → `[last_label last_catalog]` with a small results list of representative records. Doesn't need to be the full inventory. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Photo-real shelf rendering (cube depth, wood grain, etc.) | "Looks impressive in screenshots." | Trades fidelity for clarity. The product is *find a record*; a stylized grid is more legible from 2 feet at a glance than a photoreal one. | Stylized 2D grid as designed. |
| Drag-to-reorder cubes from kiosk | "What if I want to swap unit positions?" | The physical unit positions are fixed by where the IKEA shelves sit. Drag-to-reorder invites accidental config destruction. | Reorder only in admin, behind PIN; ideally only by editing config. |
| Animated "fly to cube" 3D camera | Eye candy. | The kiosk is mounted near the shelves; the user looks *up at the screen and then over at the shelves*. A 2D map is already a perspective shift; adding a 3D rotation slows it down. | Stick to 2D, crisp animation. |
| Per-record album art tile inside the cube | Imagined from streaming-app UX. | At 32 cubes on a 7" screen, each cube is ~80px square. Album art at that size is illegible. And the kiosk is *not* a browsing tool — the rest is on the shelf. | Album art appears in the results panel next to the cube, not inside it. |

### Future (post-v1)

- **Cube-zoom view** — tap a cube and the grid zooms to show that cube larger with a per-record list. Only useful if the differentiator "hover/tap reveals contents" doesn't go far enough.
- **Heat-map of usage** — over time, color cubes by retrieval frequency. Fun observation, low utility.
- **Animated reshuffle preview** — given new boundaries, show the diff cube-by-cube. Almost certainly worth doing once reshuffles become routine; v1 reshuffles are rare and can use the wizard's text diff. (Calls out: this could merit "RECONSIDER for v1" if the user expects to reshuffle often. PROJECT.md mentions "~5–10 min reshuffle maintenance" as a positive, suggesting it's a known recurring activity. Worth raising during requirements.)

---

## Category 3 — Admin / Data Management

PROJECT.md is explicit: mobile-first admin, kiosk fallback, three boundary-entry workflows (manual, guided wizard, CSV/YAML seed). This category is the largest in v1 scope by feature count.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PIN-gated admin login | Active scope. | **S** | Single PIN, hashed with Argon2id (STACK.md), Starlette `SessionMiddleware`, sliding-window TTL. PIN entered on mobile or kiosk. |
| Session timeout with sliding window | Active scope. | **S** | 5–10 min idle = logout. Visible countdown when < 60s remains (kiosk industry standard). |
| Manual cube-boundary entry | One of the three workflows. | **M** | Form per cube: `first_label`, `first_catalog`, `last_label`, `last_catalog`. Autocomplete from `collection_items` so values that don't actually exist in the collection are rejected. Bulk-save with diff preview. |
| Guided setup wizard | One of the three workflows. Important for first-time setup. | **L** | Cube-by-cube walk-through: shelf shows record, owner types catalog#, system records `last_in_cube_n` = `first_in_cube_n+1`. Boundary inferred automatically from a single point per cube transition. This is the *intended* primary onboarding flow per the catalog-number-sorted invariant. |
| CSV/YAML seed import | One of the three workflows. | **M** | Defined schema (let's say YAML for human-edit-ability): a list of cube objects with `{unit, position, first_label, first_catalog, last_label, last_catalog}`. Validated on upload; failures show a per-row error list (DSpace batch-edit pattern is the right reference). Replaces all boundaries atomically on success. |
| Sanity validation against `collection_items` | Active scope (implicit) — without this, admin can enter a label that doesn't exist and the kiosk silently fails. | **S** | On save: every `(label, catalog#)` boundary value must match an actual row in discogsography's `collection_items` (or a tolerant trigram match — flag near-misses for confirmation). |
| Boundary edit confirmation / preview | If you mis-type a boundary, the wrong record gets highlighted forever. Confirmation step is non-negotiable. | **S** | Diff view between current boundaries and proposed boundaries before commit. Affected cubes highlighted. |
| Admin can log out manually | "Hand the kiosk back to a visitor" use case. | **S** | Trivial. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Undo / history of boundary changes | Reshuffles are reversible; mistakes during a reshuffle should be one-tap-undoable for a window of time. | **M** | An append-only `boundary_change_log` table records every change with a timestamp and the previous values. Admin UI offers "Undo last N changes" or "Revert to <timestamp>". The actual revert just writes an inverse change set. Bonus: this *also* gives you the v1.x periodic-backup story for free. |
| Reshuffle wizard ("I just got 200 records") | The named recurring workflow per PROJECT.md. Without a guided path, post-haul reshuffles are tedious. | **M** | A workflow that: (1) confirms which cubes are affected, (2) walks the user through new boundaries cube-by-cube same as setup wizard, (3) optionally suggests boundaries based on which `collection_items` are new since the last reshuffle, (4) commits as a single atomic change set so undo is one tap. |
| Live boundary editing on mobile reflecting on kiosk | Admin at the shelf with a phone — change saved, kiosk re-highlights. The "wow" demo of the realtime layer (Category 5). | **M** | Falls out cheaply once SSE invalidation is in place. |
| Auto-suggest boundary based on collection sort | Given the deterministic ordering, "this cube probably ends at `<catalog#>`" can be inferred from a midpoint between adjacent populated cubes. Reduces typing. | **S–M** | Server endpoint that takes a `(unit, position)` and returns the natural midpoint catalog#. Wizard uses this for one-tap acceptance. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Per-record manual position override | "What if a record is misshelved?" | A *misshelved record is misshelved* — the answer is to reshelve it, not to lie to the system. Per-record overrides break the invariant that makes computation work and balloon the data model. | Reshelve. If you can't, the answer "approximately cube 12, possibly wrong" is more honest than "exactly cube 14, lying." |
| Boundary-edit by drag on the cube grid | Looks cool. | Catalog numbers are strings with format variability. Drag-to-set-boundary forces you to pick a record visually, which goes against the keystroke-driven UX of admin. | Form input with autocomplete is faster for power users. |
| Audit trail visible to non-admins | "Transparency" sounds good. | This is a single-user home product. Audit log belongs in admin only. | History is admin-only; it's there for *undo*, not for accountability. |
| AI-suggested boundaries from album-art / OCR | "Take a photo of your shelf, app reads it." | Useful for a different product (per-record tagging without manual entry). For a deterministic-ordering product the input is the sort itself, not a photo. | Wizard. |

### Future (post-v1)

- **Multi-collection / multi-shelving-system admin** — once GRUVAX has one home configured, growth is sideways (another room, another collection). Schema accommodates it (units, cubes), UI doesn't yet.
- **Versioned boundary snapshots with named labels** — "Before Vegas haul," "After 2026 reshuffle" — convenient for jumping between configurations. The undo/history table is the foundation.
- **Suggested reshuffle based on density imbalance** — "Cube 14 is 95% full, cube 16 is 30%; here's a proposed boundary shift." Genuinely interesting, but needs validated boundary data first.

---

## Category 4 — LED Control Surface

PROJECT.md is explicit: LED endpoint exists in v1 with hardware stubbed; the API contract is locked early so the hardware milestone slots in cleanly. STACK.md confirms `aiomqtt` 3.x publishing to Mosquitto, with topics under e.g. `gruvax/leds/...`.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Publish-by-cube illumination message | The primary LED message. Active scope. | **S** | `POST /api/leds/illuminate` with body `{unit, cube, color, brightness, duration_ms}` → publishes JSON to `gruvax/leds/{unit}/{cube}`. |
| Publish-by-label-span (multi-cube) | The visual analogue of the kiosk's label-span highlight. | **S** | Either a single message `{cubes: [...], color, brightness}` or N per-cube messages. Single message is cleaner; let the firmware fan out. |
| Publish-by-sub-cube interval | The position interval — a *range of pixels* within a cube. RGB+addressable WS2812B means this is the LED's whole reason for existing. | **M** | `{unit, cube, pixel_start, pixel_end, color, brightness}`. The firmware decides what `pixel_*` means physically (e.g., 20 pixels/cube per recordShelf). |
| Brightness control | RGB LEDs at full brightness are blinding; admin needs a global ceiling. | **S** | Admin-stored value in `gruvax.led_settings`; included in every published message. Two settings worth distinguishing: "ambient" (default for label-span) vs "active" (for the precise position). |
| Color customization per state | Active scope. `label_span_color`, `position_color`, `error_color`, `setup_color`, etc. | **S** | Each state is a row in `gruvax.led_color_settings` with a sensible default. Admin UI is a color-picker per state. (Honor 7-day-color-blind defaults: not just red/green for active/error.) |
| "All off" panic button | The single most necessary LED operation when something goes wrong (or when someone needs to sleep with the shelves in the bedroom). | **S** | `POST /api/leds/off` → publishes `{action: "off"}` on `gruvax/leds/all`. Bind to a visible UI button in admin. |
| Test / diagnostic mode | Hardware integration without diagnostics is debugging blind. | **M** | A sequence: light each cube in turn (red→green→blue→white→off), publish a status request, log received status. Used during setup and after any LED issue. Endpoint: `POST /api/leds/diagnostic`. |
| LED contract stability (versioned topic schema) | The whole *point* of v1's LED work is that hardware lands later without breaking the API. | **S** | Topic structure documented in README; JSON payload validated against a Pydantic model; bump version (`gruvax/v1/leds/...`) only on breaking change. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Layered colors (label-span dim + position bright) in one logical command | The natural visual hierarchy from Category 2 needs to translate to LED. A single API call should produce the layered effect, not require two coordinated calls. | **S** | A "find" message that bundles both: `{unit, cube, span_color, span_brightness, position_start, position_end, position_color, position_brightness}`. Firmware decides if it's one event or two. |
| Animated transitions (fade-in / pulse) | Visual softness on physical hardware. Snap-on / snap-off is jarring; pulse implies "look here." | **S** | A `transition: {style: "fade"|"pulse"|"instant", duration_ms}` field. Firmware owns the actual interpolation; API just declares intent. |
| Per-record-pull "celebrate" effect | Tap-to-confirm-you-found-it could send a brief celebration animation (e.g., 250ms green pulse). Cheap delight. | **S** | A `POST /api/leds/celebrate` or a flag on the illuminate call. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Per-pixel direct control from kiosk UI | "What if I want to draw on the shelves?" | This is a finding tool, not a playground. Direct per-pixel control invites Discord-bot-tier scope creep. | If desired, expose only inside a "creative" mode in admin behind a feature flag; not a v1 surface. |
| "Always-on" ambient lighting mode | "The shelves look pretty when lit." | Power draw, LED lifetime, light pollution at night. The product is *find*; "always lit shelves" is a different product. | Use existing IKEA LED strips for ambient; reserve WS2812B for finding. |
| Music-visualization sync | Pi has a turntable input nearby — tempting. | A turntable signal-tap is hardware work and the value over "just looking at your records" is low. recordShelf attempted this and parked it. | Out of scope. Permanently. |
| Hard-coded color palette | "Just pick good defaults." | Color preferences are personal; accessibility (color-blind users; visiting friends with different needs) makes hard-coding hostile. | Admin-configurable per Active scope. |

### Future (post-v1, mostly tracking the hardware milestone)

- **Real ESP32/Arduino firmware** — out of scope for v1 by user. The v1 stub publishes to a topic; the listener arrives in the hardware milestone.
- **Status reporting back from firmware** — `gruvax/leds/status/{unit}` topic with last-seen, firmware version, brightness applied. Useful in the hardware milestone, no-op in v1.
- **Per-cube LED count auto-detection** — `gruvax/leds/discover` request that maps physical pixel count per cube. Hardware-milestone feature.
- **Power-budget enforcement** — at 60 LEDs/cube × 32 cubes × full white, peak amps gets serious. A "max simultaneous lit cubes" admin setting is a fire-safety differentiator once hardware lands.

---

## Category 5 — Realtime / Multi-Device

STACK.md recommends Server-Sent Events via `sse-starlette` (or built-in `fastapi.sse` once stable). This is the right tool for "admin edits boundary → kiosk reflects within a second."

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Kiosk re-renders after admin boundary edit (without manual refresh) | The named use case: admin at the shelf with a phone, kiosk reflects the change. | **M** | SSE channel `/api/events` emits `{type: "boundary_changed", cube_ids: [...]}`. TanStack Query subscribes; invalidates the affected cube queries. Re-render flows naturally from React's reconciler. |
| Multiple simultaneous searches (kiosk + mobile) work without interference | Two visitors searching concurrently is the realistic load. | **S** | Stateless GET search; no concurrency concern. Just verify session middleware doesn't accidentally serialize. |
| Optimistic UI for admin edits | Mobile feels sluggish without optimistic update. | **S** | TanStack Query's `optimisticUpdate`. Roll back on server error. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Soft-lock when admin is mid-edit | If owner is editing a boundary and a visitor searches the affected cube, render a subtle "boundaries being updated" indicator rather than potentially-stale data. | **S** | A `gruvax.admin_sessions` table with `active_until`; SSE emits `admin_editing` events with affected cube range. Kiosk shows a subtle banner. |
| Live-pulled list ("someone searched X") | Shared kiosk + mobile awareness — owner on phone can see what's being looked at on the kiosk. | **S** | Same SSE channel, additional event type. Cute, low-priority. (Privacy tension — see Category 9.) |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| WebSocket for bidirectional everything | "We might want bidirectional later." | YAGNI: bidirectional flow doesn't exist in this app's use cases. SSE is simpler, has automatic reconnection, plays nicely with HTTP/2. | SSE per STACK.md. |
| Hard locking that blocks admin edits | "Prevent concurrent edits to the same cube." | One-admin product. Hard locking is for multi-user systems. | Last-write-wins with the change-log table providing undo (Category 3 differentiator). |
| Realtime collaborative cursor-style editing | CRDT, presence, etc. | Single admin. | n/a. |

### Future (post-v1)

- **Presence indicator** ("admin online on mobile") — useful once a partner/family also has admin access; in v1 single-PIN, it's noise.
- **Push notifications to admin's phone for kiosk-detected issues** ("kiosk lost connection") — depends on whether the mobile admin UI installs as PWA with push permission. Reasonable v1.x feature.

---

## Category 6 — Offline / Resilience

PROJECT.md scope: kiosk detects loss of connectivity to GRUVAX backend on `lux` and shows an offline banner; search is disabled until reachable. The kiosk is on the *same LAN* as `lux`, so the realistic offline scenarios are: (1) `lux` is down, (2) Wi-Fi died, (3) FastAPI process restarted, (4) Docker Compose recreation. Not airline-mode-on-a-laptop offline.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Offline banner when backend unreachable | Active scope. | **S** | A small persistent banner: "GRUVAX is offline — reconnecting…" Drives off SSE connection state + a periodic `/healthz` ping when SSE is closed. |
| Search disabled while offline | Active scope (implied: doing nothing is worse than honest disabling). | **S** | Input field disabled, placeholder text changes to "Reconnecting…" |
| Automatic reconnection with exponential backoff | The kiosk shouldn't require manual intervention after a 30-second `lux` blip. | **S** | SSE handles this nearly for free; standard pattern is 1s → 2s → 5s → 10s → 30s cap. |
| Reconnection success animation | Reassurance that "we're back" — kiosk industry standard pattern. | **S** | Brief green tick or banner-fades-out animation when first successful request after offline resolves. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Service-worker cached "last known good" search results | If `lux` is down, the kiosk can still answer the most recent few searches. Specifically useful for "I searched it 30 seconds ago, then `lux` rebooted." | **M** | Workbox or hand-rolled service worker with stale-while-revalidate on the search endpoint. Cached results show a "cached" badge. **RECONSIDER for v1**: this materially upgrades the offline experience for ~1 day of work; user did not explicitly include but did not explicitly exclude. Worth flagging in requirements. |
| Queue admin edits if mobile loses connection | Admin at the shelf, Wi-Fi flakes, edits not lost. | **S–M** | Queue mutations in IndexedDB; flush on reconnect. TanStack Query has hooks for this; or use `@tanstack/react-query-persist-client`. Useful but the admin's typical loop is "edit → save → confirm" so they'd retry manually anyway. Lower priority than the read-side service-worker cache. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Full offline-first PWA (all 3K records cached in browser) | "Make it work without `lux` at all." | The whole point of the product is realtime accuracy of boundaries that *only `lux` knows*. Stale boundaries are misshelf cause #1. | Service-worker cache of recent results is sufficient. |
| Local SQLite mirror on the Pi | "Belt and suspenders." | Doubles the maintenance burden; sync issues become a source of bugs. | Cache strategy above. |

### Future (post-v1)

- **Pre-loading recently-pulled records on app load** so they're searchable instantly even before the first request resolves. Trivial once recently-pulled is implemented.
- **Wi-Fi quality indicator** in admin diagnostics — Pi can read its own RSSI, useful for "why is my kiosk slow?" debugging.

---

## Category 7 — Observability & Maintenance

For a home product with one operator: don't build observability infrastructure, build *self-evident* health and lightweight logging. STACK.md mentions Prometheus instrumentation libs but for this scope it's overkill.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| `/healthz` endpoint with DB + MQTT broker reachability checks | Docker Compose health checks, kiosk reconnection logic, all depend on this. | **S** | Return `{status: ok, db: ok, mqtt: ok, version: …}`. Container `HEALTHCHECK` calls it (STACK.md Dockerfile pattern). |
| Structured logging (JSON) with sensible defaults | Future-you debugging in 6 months thanks past-you. | **S** | `structlog` or stdlib `logging` with JSON formatter. Log level via env var. |
| Schema migration via Alembic with safe upgrade path | Standard hygiene; `alembic upgrade head` on container start is the well-trodden pattern. | **S** | Sanity: CI tests `alembic upgrade head && downgrade base && upgrade head` (STACK.md). |
| `/version` endpoint | "Which commit am I running?" trivially answered. | **S** | Returns git SHA, build timestamp, environment. Useful in admin diagnostic page. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Simple in-app usage stats page | "Most-searched records this month" is genuinely fun and useful for collection curation insights. | **M** | One aggregation table updated per search; admin page renders a top-20 list. No external observability stack needed. Privacy implication: see Category 9. |
| Slow-query log surfaced in admin | If a search ever exceeds 200ms, it's worth knowing about. | **S** | Middleware records request duration; queries > 200ms get a flag in a small admin "slow searches" panel. Self-policing the Core Value SLO. |
| Discogsography-sync staleness indicator | Tell the admin "collection last synced 3 days ago" so they know if a newly-added record won't be found yet. | **S** | Read `collection_items.updated_at` max from discogsography; expose in admin diagnostics. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Grafana + Prometheus stack | "Proper observability." | Two more containers, alert rules, dashboards — for one user and one app. Maintenance burden exceeds value. | Single admin diagnostics page; logs via `docker logs gruvax`. |
| Sentry / error-tracking SaaS | "Catch every exception." | Egress traffic, account, costs (or self-hosted Sentry — also one more service). For a home LAN app, log → journald is fine. | Read the logs. |
| Full audit log surfaced as a UI tab | "Compliance!" | Single-user home app, no compliance regime. | Boundary change log (Category 3) is the entirety of useful audit history. |

### Future (post-v1)

- **OpenTelemetry traces** — if FastAPI ever sprawls into multiple services, traces help. Single-service app doesn't need them.
- **Anomaly detection on search latency** — interesting but YAGNI.

---

## Category 8 — Audio / Discovery (mostly Future)

PROJECT.md mentions audio/discovery features as likely deferred. Confirming.

### Table Stakes (v1)

(None.) These aren't required to find a record on a shelf.

### Differentiators (Future)

| Feature | Value Proposition | Complexity | Notes (when added) |
|---------|-------------------|------------|--------------------|
| 30s preview from Discogs / Apple Music / Spotify links | "Should I pull this one out?" before walking over. | **M** | Discogs doesn't reliably link to streaming; tying to MusicBrainz IDs and ISRCs is more reliable. Adds a third-party HTTP path. Future. |
| Last.fm scrobble integration | Mark "I played this" when a record is selected and confirmed. | **M** | Requires per-user Last.fm auth (admin owner only). Fits the LibraryThing/Roon "log what you played" pattern. Future. |
| "What's this label" tour / "related releases" via Neo4j | Discogsography has the graph; the API hook is via discogsography's MCP. Surface "10 other Blue Notes you own" inline. | **M** | High-value differentiator once v1 lands. Defer cleanly. |
| Cover-art browse / slideshow mode | PROJECT.md mentions this explicitly as Out-of-Scope/backlog. | n/a | Confirmed: defer. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Built-in record player remote | "Why not?" | Different product. Different protocols (USB, Bluetooth, network audio). Don't get sucked in. | Roon / Plex / vendor app does this. |
| Track-by-track playback of digital files | "Streaming alongside vinyl." | If owner wants this, Plex/Roon exists. Confuses what GRUVAX is. | Stay focused. |
| Music recommendations | "More like this." | Roon does this with a 6-figure ML budget. Don't reinvent badly. | Neo4j graph queries via discogsography are sufficient for "labelmates" type recommendations. |

### Future (post-v1)

- All differentiators above. Capture in backlog; revisit after v1 ships.

---

## Category 9 — Multi-User / Privacy (single PIN + home LAN floor)

PROJECT.md is explicit: single PIN, no multi-user auth. The remaining question is what the *floor of decent multi-visitor respect* looks like when a houseguest searches.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Search history is per-session (kiosk client-side only) | A houseguest's search shouldn't be visible to the next visitor or recorded to the server. | **S** | Recently-pulled list lives in browser session storage on the kiosk; cleared on idle timeout (Category 1 differentiator becomes session-scoped). |
| Admin diagnostics (usage stats) shows *aggregate* searches, not per-session | If admin keeps stats, they should be aggregate so guests aren't surveilled. | **S** | Increment per-record search counter on the server; never log query text + timestamp pair to anywhere persistent. (Or: log queries to a structured log with short retention.) |
| No search-query logging beyond aggregation | The default Postgres slow-query log might capture queries; suppress or filter the search endpoint. | **S** | Logging config: search endpoint hits go to INFO with no query body; only counts. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| "Reset kiosk" button visible to anyone | A visitor who knows they searched something embarrassing can clear the screen and the recently-pulled list themselves. | **S** | Visible button on the kiosk UI; clears session storage, returns to home state. Doesn't require admin PIN. |
| Per-visitor PIN entry option (Future-leaning, but worth noting) | If a household adds a partner, they may want their own session boundary without going to multi-user auth. | **S–M** | Optional second PIN that opens a "guest" session with the same view but flushed history when the session ends. Lighter than full multi-user. **RECONSIDER for v1**: not needed but cheap to ship and probably valued. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Linking searches to a Discogs user account | "Personalize the experience." | Houseguests aren't logging into Discogs at your kiosk. | Don't. |
| Storing full search history server-side, ever | "We might want analytics." | If it's stored, it's leakable. The whole point is a home LAN no-public-exposure model. | Aggregate counters per record, not full history. |
| OAuth / SSO | PROJECT.md explicitly excludes. | Out of scope. | Single PIN per Active. |

### Future (post-v1)

- **Per-visitor PINs** with isolated histories — see differentiator above.
- **Search-history opt-in for admin** — if owner wants to remember their own pulls, an explicit "remember my searches" toggle in admin. Defaults off.

---

## Category 10 — Backup & Data Portability

PROJECT.md is explicit: **periodic JSON export of `cube_boundaries` to git as a portable backup is Out-of-Scope for v1**, Postgres backups suffice. But the *ability* to import/export from CSV/YAML is in scope (it's part of the admin three-workflow). I'll respect the boundary: import/export is in v1, *automated periodic* export is not.

### Table Stakes (v1)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Export boundaries to YAML / JSON on demand | Falls out of the import workflow's data model. Admin should be able to download the current state. | **S** | A download button next to the import button. Same schema as import. |
| Import workflow validates and shows preview | (Category 3 already has this.) | (S, see Cat 3) | n/a — same feature. |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Boundary version history (Category 3's undo log) doubles as recovery | Already in v1 as the undo log. Lightweight backup is a free side-effect. | (M, see Cat 3) | n/a — same feature, different lens. |
| Color settings export/import | When admin tunes the colors well, being able to save/share that config is satisfying. | **S** | Same YAML schema, separate section. |

### Anti-Features

| Feature | Why Tempting | Why Don't | Alternative |
|---------|--------------|-----------|-------------|
| Automatic git commits of boundary state | PROJECT.md says no for v1. | Brings git-as-a-dependency into the runtime, plus credentials, plus repo. Postgres backup is correct here. | Manual export when desired. |
| Cloud-sync backup to Dropbox / Google Drive | "Disaster recovery." | The product is home LAN; introducing cloud surface for one config file is wrong shape. | Manual export; Postgres backup. |

### Future (post-v1)

- **Periodic auto-export to git** — PROJECT.md backlog item. Worth doing once boundaries change frequently enough that manual export is annoying.
- **Versioned snapshots with names** — also referenced in Category 3 future.

---

## Feature Dependencies

```mermaid
flowchart LR
  %% Solid edges = requires; dashed edges = enhances; red dashed = conflicts-with

  %% Infrastructure
  FTS["Postgres FTS index<br/>on collection_items view"]
  Trgm["pg_trgm extension<br/>+ GIN index"]
  Boundary["Cube boundary<br/>data model"]
  PIN["PIN auth +<br/>session middleware"]
  SSEch["SSE channel +<br/>TanStack Query invalidation"]
  MQTTc["MQTT client (aiomqtt)<br/>+ Mosquitto broker"]
  Health["/healthz polling"]
  Sanity["Sanity validation<br/>against collection_items"]

  %% Core features
  Search["Search (typeahead)"]
  PosAPI["Position estimation API"]
  Cube["Cube highlight (single cube)"]
  Span["Label-span highlight (multi-cube)"]
  SubBar["Sub-cube position bar"]
  Admin["Admin boundary edit<br/>(three workflows)"]
  LiveKiosk["Live admin → kiosk update"]
  LEDcube["LED publish-by-cube"]
  Offline["Offline banner"]
  HealthBase["Healthcheck / version / logging<br/>(ships in v1 baseline, independent)"]
  ChangeLog["Boundary change log (undo)"]
  Recent["Recently-pulled list"]

  %% Differentiators / enhancements
  SoftLock["Soft-lock indicator"]
  Optimistic["Optimistic UI for admin"]
  LEDspan["LED publish-by-label-span"]
  LEDsub["LED publish-by-sub-cube-interval"]
  LEDsettings["Brightness + color settings"]
  LEDdiag["Test / diagnostic mode"]
  LEDoff["All-off panic button"]
  Reconnect["Reconnection animation"]
  SWcache["(future)<br/>Service-worker cached results"]
  Reshuffle["Reshuffle wizard<br/>(atomic change set)"]
  Backup["Backup / restore<br/>(free side-effect)"]
  Audit["Audit trail in admin"]
  ServerHistory["Server-side full<br/>search history"]

  %% Requires (solid)
  Search --> FTS
  Search --> Trgm
  Cube --> PosAPI
  PosAPI --> Boundary
  Span --> PosAPI
  SubBar --> PosAPI
  SubBar --> Cube
  Admin --> PIN
  Admin --> Sanity
  LiveKiosk --> SSEch
  LEDcube --> MQTTc
  LEDcube --> PosAPI
  Offline --> SSEch
  Offline --> Health
  Recent --> Search

  %% Enhances (dashed)
  Search -. enhances .-> Recent
  Span -. enhances .-> Cube
  Admin -. enhances .-> ChangeLog
  LiveKiosk -. enhances .-> SoftLock
  LiveKiosk -. enhances .-> Optimistic
  LEDcube -. enhances .-> LEDspan
  LEDcube -. enhances .-> LEDsub
  LEDcube -. enhances .-> LEDsettings
  LEDcube -. enhances .-> LEDdiag
  LEDcube -. enhances .-> LEDoff
  Offline -. enhances .-> Reconnect
  Offline -. enhances .-> SWcache
  ChangeLog -. enhances .-> Reshuffle
  ChangeLog -. enhances .-> Backup
  ChangeLog -. enhances .-> Audit

  %% Conflicts (red dashed)
  Recent -. conflicts .-> ServerHistory
  linkStyle 33 stroke:#c33,stroke-dasharray: 5 5

  classDef baseline fill:#eef,stroke:#88a
  class HealthBase baseline
```

### Dependency Notes

- **Position estimation is the single most-depended-on module.** Cube highlight, label-span, sub-cube bar, and the LED endpoint all consume it. Build and test it first; everything else gates on it. (This aligns with PROJECT.md identifying position estimation as its own research stream.)
- **PIN auth is on the critical path for everything admin.** It's small (Starlette `SessionMiddleware` + one route) but it gates the three boundary workflows.
- **SSE / live update is small but enables several differentiators at once** (admin→kiosk live reflection, soft-lock, presence). Worth landing early in the realtime-touching phase.
- **MQTT publishing is "almost free" but unlocks the whole LED control surface.** All six LED API endpoints share the same `aiomqtt` connection — implement the broker connection once, layer endpoints on it.
- **The boundary change log is the keystone for three future features** (undo, audit, backup). Cheap to build; deliberately design the schema for those uses from day one.

---

## MVP Definition (v1)

Anchored to PROJECT.md Active scope; phrased as user-facing capabilities:

### Launch With (v1)

- [ ] **Search** — Type-ahead over artist/title/label/catalog#, ≤200ms, ranked results, tap-to-select, top result auto-highlights. *Essential — this is the Core Value.*
- [ ] **Cube grid** — N×4×4 configurable; renders single-cube highlight, label-span highlight, sub-cube position bar; empty-cube state. *Essential — it's how the answer is communicated.*
- [ ] **Position estimation API** — Returns `{cube, label_span_cubes, sub_cube_interval}`. *Essential — single most-depended-on module.*
- [ ] **Cube boundary data model + sanity validation** — Per-cube `first/last (label, catalog#)`; validated against `collection_items`. *Essential — wrong boundaries = wrong cube.*
- [ ] **Admin PIN auth** — Argon2id-hashed PIN, sliding-window session timeout, mobile + kiosk fallback. *Essential — admin everything depends on it.*
- [ ] **Boundary edit (manual + wizard + CSV/YAML)** — Three workflows, with diff preview before commit, autocomplete from collection_items. *Essential — Active scope.*
- [ ] **Color settings** — Admin-configurable per state (label-span color, position color, error color). *Essential — Active scope.*
- [ ] **LED endpoint** — Publishes to MQTT topic with no-op listener; contract supports cube, label-span, sub-cube-interval, brightness, color, all-off, diagnostic. *Essential — locks contract for the hardware milestone.*
- [ ] **Offline banner** — Kiosk detects loss of `lux`, shows banner, disables search, reconnects with backoff. *Essential — Active scope.*
- [ ] **Healthcheck + Alembic migrations + structured logging** — Operational baseline. *Essential — Docker Compose health check and future-you debugging.*
- [ ] **Boundary change log (undo)** — Append-only history; admin can revert. *Essential — keystone for reshuffles, audit, future backup.*
- [ ] **Recently-pulled list (session-scoped, kiosk only)** — Last 10 selections in session storage. *Differentiator that's cheap and high-value.*

### Add After Validation (v1.x)

- [ ] **Service-worker cached results** — Smoother offline; ~1 day of work; consider promoting to v1 in requirements phase.
- [ ] **Reshuffle wizard** — Atomic change set guided flow; mentioned as recurring activity in PROJECT.md, would land in the first reshuffle after v1.
- [ ] **Auto-suggest boundaries** — Reduces typing during wizard runs.
- [ ] **Hover/tap cube reveals contents** — Reverse-lookup affordance.
- [ ] **Per-visitor PIN with isolated session** — If a partner/family member joins.
- [ ] **Slow-query log in admin diagnostics** — Self-policing the Core Value SLO.

### Future Consideration (v2+)

- [ ] **Real LED hardware** — Hardware milestone (already noted in PROJECT.md backlog).
- [ ] **Screensaver / browse / cover-art slideshow** — Already in PROJECT.md backlog.
- [ ] **Periodic JSON export to git** — Already in PROJECT.md backlog.
- [ ] **30s previews / streaming links / Last.fm scrobble** — Discovery features.
- [ ] **"Related releases" via discogsography Neo4j** — High-value once core lands.
- [ ] **Fill-level indicator + density-imbalance reshuffle suggestion** — Needs validated boundary data first.
- [ ] **Animated reshuffle preview / boundary diff visualization** — If reshuffles become routine.
- [ ] **OpenTelemetry / proper observability** — Only if the app sprawls.
- [ ] **Multi-user auth / RFID** — Already in PROJECT.md backlog; deliberately excluded.

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Type-ahead search | HIGH | MEDIUM | **P1** |
| Ranked results list | HIGH | LOW | **P1** |
| Cube grid + single-cube highlight | HIGH | MEDIUM | **P1** |
| Position estimation API | HIGH | MEDIUM (research stream gates this) | **P1** |
| Label-span highlight | HIGH | MEDIUM | **P1** |
| Sub-cube position bar | HIGH | MEDIUM | **P1** |
| Cube boundary data model + validation | HIGH | LOW | **P1** |
| Admin PIN auth | HIGH | LOW | **P1** |
| Manual boundary entry | HIGH | MEDIUM | **P1** |
| Guided setup wizard | HIGH | LARGE | **P1** |
| CSV/YAML import + export | MEDIUM | MEDIUM | **P1** |
| Color settings | MEDIUM | LOW | **P1** |
| LED publish (cube, label-span, sub-cube interval) | MEDIUM (HIGH once hardware lands) | LOW | **P1** |
| Brightness / All-off / Diagnostic | LOW (HIGH once hardware lands) | LOW | **P1** |
| Offline banner + reconnect | HIGH | LOW | **P1** |
| Healthcheck + Alembic + logging | HIGH (operational) | LOW | **P1** |
| Boundary change log (undo) | HIGH | LOW–MEDIUM | **P1** |
| Recently-pulled (session-scoped) | MEDIUM | LOW | **P1** |
| "Did you mean" / pg_trgm | MEDIUM | LOW | **P1**/P2 |
| Live admin → kiosk via SSE | HIGH | MEDIUM | **P1** |
| Soft-lock indicator | LOW | LOW | **P2** |
| Service-worker cached results | MEDIUM | MEDIUM | **P2** (reconsider for v1) |
| Reshuffle wizard | HIGH | MEDIUM | **P2** |
| Auto-suggest boundaries | MEDIUM | LOW–MEDIUM | **P2** |
| Hover/tap cube → contents | MEDIUM | MEDIUM | **P2** |
| Per-visitor PIN | LOW–MEDIUM | LOW–MEDIUM | **P2**/P3 |
| Slow-query log | LOW (LOW operationally) | LOW | **P2** |
| Real LED hardware | HIGH | LARGE | **P3** (separate milestone) |
| Screensaver / slideshow | LOW | MEDIUM | **P3** |
| Periodic JSON export to git | LOW | LOW | **P3** |
| Cover-art / preview / scrobble | LOW | MEDIUM | **P3** |
| "Related releases" via Neo4j | MEDIUM | MEDIUM | **P3** |
| Fill-level indicator | LOW–MEDIUM | LOW–MEDIUM | **P3** |
| Density-imbalance reshuffle suggestion | MEDIUM | MEDIUM–LARGE | **P3** |
| Voice search | LOW | LARGE | **Anti** |
| Drag-to-reorder cubes | LOW | MEDIUM | **Anti** |
| Always-on ambient lighting | LOW | LOW | **Anti** |
| Music-vis sync | LOW | LARGE | **Anti** |
| Per-record manual override | NEGATIVE (breaks invariant) | MEDIUM | **Anti** |
| Photo-real shelf rendering | NEGATIVE (reduces legibility) | LARGE | **Anti** |

**Priority key:**
- **P1** = must-have for v1 launch (most are Active scope)
- **P2** = should-have, add early in v1.x or promote into v1 if cheap
- **P3** = nice-to-have, future consideration
- **Anti** = deliberately do not build

---

## Competitor / Reference Feature Analysis

| Feature | recordShelf (closest direct prior art) | Discogs companion apps (My Vinyl+, Vizcogs, iCollect) | Library kiosks (general) | Warehouse pick-to-light | GRUVAX |
|---------|----------------------------------------|--------------------------------------------------------|--------------------------|-------------------------|--------|
| Find record → LED illuminates | Yes (per-cubby + per-pixel via RFID, brittle) | No (no physical layer) | No (printed call number) | Yes (LED at SKU location) | Yes (computed from boundaries — no RFID dependency) |
| Search / browse UI | Web list browse | Sophisticated typeahead, filter, value-tracking | Catalog search kiosk | Barcode scan + display | Typeahead with FTS + trigram + ranked |
| Sub-cube precision | Per-pixel via RFID (failed) | n/a | n/a | Per-bin (display shows quantity, not position) | Computed interval (no RFID) |
| Boundary management | n/a (per-record tag) | n/a | n/a | n/a | Three workflows: manual / wizard / CSV-YAML |
| Multi-cube label-span | Implicit (LEDs per record) | n/a | n/a | n/a | Explicit visual + LED concept |
| Color customization | Animations available, hard-coded styles | n/a | n/a | Often fixed | Admin-configurable per state |
| Filtering / faceting | None | Format, year, condition, label, genre, etc. (table stakes) | Often present | Job-driven, not user-driven | LP/CD/7" only in v1; other facets deferred |
| Discovery / recommendations | None | Vizcogs has "crate-digging companion" features | None | None | Deferred to discogsography Neo4j integration (future) |
| Wantlist / favorites | None | Yes (Discogs-synced) | n/a | n/a | Deferred to v1.x via discogsography sync |
| Offline behavior | Pi-local, works offline naturally | Apps cache; works offline-ish | n/a (always-on display) | Embedded; offline-tolerant | Online-only with offline banner + (future) SW cache |
| Admin / config UX | Code-config | Settings screen | Sysadmin tools | Sysadmin tools | Mobile-first + kiosk fallback |
| Hardware integration | Direct (Pi + WS2812B) | None | None | Direct (industrial PLCs) | Decoupled via MQTT contract (hardware later) |
| Reshuffle / reorg workflow | n/a | Tag/folder edits | n/a | n/a | Reshuffle wizard differentiator |
| Voice / gesture / ML | Some experimental (audio viz) | None substantive | None | None | Deliberately none |

**Differentiation summary:** GRUVAX's unique combination is (a) deterministic-ordering-driven computation rather than per-record tagging — solves recordShelf's RFID reliability problem, (b) explicit multi-cube label-span visual + API — addresses a vinyl-collection-specific concern that pick-to-light doesn't have, (c) mobile-first admin with three boundary workflows — Discogs apps have collection management UX, pick-to-light has industrial setup, neither does the "I'm at the shelf with a phone" pattern, (d) MQTT-stubbed LED contract for future hardware — clean separation prior art doesn't have.

---

## Sources

### Direct prior art

- [recordShelf — Hackaday project](https://hackaday.io/project/15869-recordshelf) — **HIGH** confidence on what attempted features did/didn't work; pre-Pi 5 era project but architecturally closest reference. The RFID-reliability failure mode here is a direct argument *for* GRUVAX's computed-boundary approach.

### Adjacent reference categories

- [LibraryThing collections feature](https://www.librarything.com/) — collection categorization patterns (favorites, wantlist, currently-reading) — MEDIUM, used as table-stakes anchor for personal-collection UX.
- [Discogs collection on Android](https://support.discogs.com/hc/en-us/articles/360033700734-How-To-Use-The-Collection-Feature-On-Android) — filtering by format/year/label/condition — MEDIUM, ecosystem alignment reference.
- [Discogs wantlist with saved searches](https://www.discogs.com/about/features/wantlist/) — what users coming from Discogs expect — MEDIUM.
- [Vizcogs](https://vinylrecordpress.media/resource/vizcogs-the-record-collection-app/) and [My Vinyl+](https://myvinyls.app/) — modern Discogs companion-app feature sets — MEDIUM.
- [Library kiosk patterns / wayfinding](https://touchscreenwebsite.com/blog/library-touchscreen-complete-guide/) — physical-location-finder kiosk UX patterns — MEDIUM.
- [Voodoo Robotics — pick-to-light overview](https://voodoorobotics.com/pick-to-light-put-to-light/) and [Kardex pick-to-light](https://www.kardex.com/en-us/blog/pick-to-light-technologies) — LED-at-location accuracy and ergonomic patterns — MEDIUM. Reinforces "color customization + brightness + diagnostic" as table-stakes for LED control surfaces.

### Implementation-pattern references

- [Postgres pg_trgm "did you mean" guide (Viget)](https://www.viget.com/articles/handling-spelling-mistakes-with-postgres-full-text-search) — verifies the recommended typo-tolerant search approach — HIGH confidence on technical feasibility.
- [Typeahead UX patterns (Meilisearch blog)](https://www.meilisearch.com/blog/typeahead-search) — 100–200 ms expected latency, 200ms debounce — MEDIUM.
- [Kiosk idle-time best practices (Kiosk Group support)](https://support.kioskgroup.com/article/991-idle-time-limit) — 30–90 second idle pattern; 5–10 min for admin session — MEDIUM.
- [PWA offline-first patterns (MagicBell + MDN)](https://www.magicbell.com/blog/offline-first-pwas-service-worker-caching-strategies) — stale-while-revalidate and cache-first patterns referenced for the service-worker differentiator — HIGH.
- [ESP-WIFI-NEOPIXEL-CONTROL — sample MQTT topic conventions](https://github.com/Terr4/ESP-WIFI-NEOPIXEL-CONTROL) — confirms topic/payload patterns for the LED contract — MEDIUM.
- [TanStack Query invalidation docs](https://tanstack.com/query/v5/docs/framework/react/guides/query-invalidation) — SSE-driven invalidation pattern — HIGH.
- [DSpace batch metadata editing](https://wiki.lyrasis.org/display/DSDOC5x/Batch+Metadata+Editing) — CSV-upload diff/preview pattern referenced for the CSV/YAML import — MEDIUM.

### Confidence assessment by category

| Category | Confidence | Reason |
|----------|------------|--------|
| 1 Search & lookup | HIGH | Standard typeahead+FTS patterns; backed by Postgres pg_trgm prior art. |
| 2 Cube-level UX | MEDIUM | Novel cross-domain — anchored to library kiosk + pick-to-light, but the multi-cube/sub-cube split is GRUVAX-specific. |
| 3 Admin / data management | HIGH | Anchored to explicit PROJECT.md scope plus DSpace-style batch-edit prior art. |
| 4 LED control surface | HIGH (contract design); MEDIUM (color/brightness defaults) | Contract design well-supported by ESP-WIFI-NEOPIXEL and pick-to-light patterns; specific color choices are owner-preference. |
| 5 Realtime / multi-device | HIGH | SSE+TanStack Query is mature pattern; STACK.md already settled this. |
| 6 Offline / resilience | HIGH | Standard PWA patterns; only flag is the v1-vs-v1.x scoping of the service-worker cache. |
| 7 Observability & maintenance | HIGH | Boring infrastructure; well-trodden territory. |
| 8 Audio / discovery | MEDIUM | Confirmed by PROJECT.md to defer; categorization is the goal, not deep research. |
| 9 Multi-user / privacy | MEDIUM | The "floor of decent home-LAN respect" is a subjective design call; framed conservatively. |
| 10 Backup & data portability | HIGH | PROJECT.md is explicit; reaffirming the boundary. |

### Items flagged for "RECONSIDER for v1" discussion in requirements phase

1. **Service-worker cached search results** (Category 6 differentiator) — cheap, materially better offline UX. ~1 day of work.
2. **Per-visitor PIN with isolated session** (Category 9 differentiator) — cheap nicety if a partner/family also uses the system. Probably skip until requested.
3. **Animated reshuffle preview** (Category 2 future) — if reshuffles happen as often as PROJECT.md implies, this could be worth promoting earlier.

These are flagged for the requirements phase to confirm, not smuggled into v1.

---

*Feature research for: GRUVAX — touchscreen kiosk + REST API + RGB LED (stubbed) for finding vinyl on Kallax shelves.*
*Researched: 2026-05-18*

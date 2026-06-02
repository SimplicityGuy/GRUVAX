# Phase 9: Offline + Reconnect UX - Context

**Gathered:** 2026-06-01
**Status:** Ready for planning

<domain>
## Phase Boundary

When the GRUVAX backend (`gruvax-api`) is unreachable, the **kiosk** shows a clear,
SSE-authoritative offline banner (never driven by `navigator.onLine` alone), drops into a
degraded read-only mode that preserves the last locate result and cube highlight, then
auto-reconnects with jittered backoff and refreshes stale data on `server_hello`.

**In scope:** OFF-01 (offline banner), OFF-02 (degraded mode), OFF-03 (auto-reconnect with
backoff + jitter, no reconnect storm), OFF-04 (banner clears + search re-enables + stale-data
refresh on reconnect; dismissed diff badge stays dismissed).

**Out of scope:** admin/mobile-UI offline treatment (kiosk-only per the ROADMAP success
criteria — see Deferred); any new search/data capability; LED behavior on disconnect.

</domain>

<decisions>
## Implementation Decisions

### Offline banner copy & variants
- **D-01:** Use **two banner variants**, selected by `navigator.onLine` purely as a *cosmetic
  secondary hint* (the SSE connection state remains the authoritative offline trigger — PITFALLS 35):
  - `sseConnected=false` **and** `navigator.onLine=false` → **"No network — trying to reconnect…"**
  - `sseConnected=false` **and** `navigator.onLine=true` → **"Can't reach GRUVAX — trying to reconnect…"**
- **D-02:** Copy is reassuring + auto-recovery framed ("trying to reconnect…") — it signals the
  kiosk recovers on its own; no visitor action is implied. Plain language, no jargon (Nordic Grid voice).

### Offline banner look & stacking
- **D-03:** **Distinct urgent treatment** — reuse `StalenessBar`'s structure/position (top bar,
  `role="alert"`), but a stronger/more-urgent palette from the design tokens (e.g. reversed
  blue-ground or higher-contrast variant) plus a small connectivity icon, so "offline" reads as a
  different signal than "stale data". Do NOT recolor outside the Nordic Grid tokens.
- **D-04:** **Top-priority and persistent.** While offline the banner takes the top slot and
  **suppresses other transient banners/pills** (ReauthBanner, the "N new records" pill,
  ReshuffleBanner); they return on reconnect. **Not dismissible** — it clears itself on reconnect.
  (Mirrors `StalenessBar`'s persistent operational-signal model. `StalenessBar` already self-hides
  offline because `/api/health` is unavailable → `sync_age_seconds` null.)

### Degraded-mode scope (OFF-02)
- **D-05:** **Lock all server-dependent controls** while offline, all behind the same offline
  affordance: the search input, the profile-switch button, and cube taps (which open
  `CubeContentsPanel` → `/cube-contents` fetch). Keep purely-local / visual elements working: the
  preserved locate result + cube highlight stay visible (LOCKED by OFF-02), and `RecentlyPulledStrip`
  (local/sessionStorage) stays viewable.
- **D-06:** Search-box affordance = **greyed + non-focusable input with a placeholder swap** to
  "Search unavailable while offline" (exact string is planner/UI-SPEC discretion within tokens). The
  banner above carries the "why".

### Reconnect feedback (OFF-04)
- **D-07:** On successful reconnect (`server_hello`): banner clears, controls re-enable, stale data
  refreshes, **and** show a brief **"Back online" confirmation** (~2–3 s auto-dismiss) reusing the
  existing `SyncToast` component — so a recovered kiosk doesn't look identical to one that was never
  offline.

### Locked mechanics (NOT re-decided here — carried from research/prior phases)
These are settled; planner implements them as stated:
- **SSE connection-state is the authoritative offline signal**, not `navigator.onLine` (PITFALLS 35).
  Driven by `connectivity.sseConnected` in `store.ts`; flip `connectivity.bannerVisible` (currently a
  stub) from the SSE `onopen`/`onerror`/`server_shutdown` paths in `KioskView.tsx`.
- **TanStack Query `networkMode: 'always'`** (ROADMAP open decision + PITFALLS 35/36) — prevents the
  reconnect refetch storm. Add to the `QueryClient` `defaultOptions.queries` in `App.tsx` (not set today).
- **SSE `retry:` jitter (~2000–8000 ms random)** sent from the server so clients don't reconnect in
  lockstep (PITFALLS 36). Backend already sets `ping=15` in `src/gruvax/api/events.py`.
- **`server_hello` → resync + invalidate is already implemented** (Phase 4 SSE consumer,
  `KioskView.tsx` ~L373) — OFF-04's data-refresh plumbing largely exists; this phase wires the
  banner-clear + toast onto it.
- **Search-cache `staleTime`** tuned so a short outage (< ~60 s) does not force a redundant refetch on
  reconnect (PITFALLS 36/37). Current kiosk search query is `staleTime: 30_000`.
- **Dismissed collection-diff badge stays dismissed** across reconnect via a `dismissed_diff_at`
  timestamp compared to `last_sync_at` (PITFALLS 37). "Recently pulled" is local Zustand/sessionStorage
  and is never clobbered by a refetch.

### Claude's Discretion
- Exact placeholder/affordance string and the precise urgent-palette token choice (within Nordic Grid
  tokens / UI-SPEC).
- Whether a `/api/health` probe supplements the SSE reconnect signal (OFF-03 mentions it); planner to
  decide if SSE auto-reconnect alone suffices vs adding a probe. Default: rely on EventSource
  auto-reconnect + jitter; add a probe only if needed to avoid a hung connection.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — OFF-01..OFF-04 (lines ~29–32) + the `networkMode: 'always'` decision row.
- `.planning/ROADMAP.md` §"Phase 9: Offline + Reconnect UX" — goal, success criteria, "Open decisions".

### Research (HIGH-confidence, drives this phase)
- `.planning/research/PITFALLS.md` §Pitfall 35 — `navigator.onLine` false connectivity; SSE-as-primary signal; banner copy distinction.
- `.planning/research/PITFALLS.md` §Pitfall 36 — SSE reconnect storm; `retry:` jitter; `networkMode: 'always'`; `staleTime`.
- `.planning/research/PITFALLS.md` §Pitfall 37 — stale cache served as fresh after reconnect; `dismissed_diff_at`; what is/isn't refetched.

### Design contract
- `design/gruvax-design-language.md` + `design/gruvax-design-tokens.css` / `.json` — banner palette,
  type (Space Grotesk body), Nordic Grid voice (plain-language, ALL-CAPS labels).

### Existing code (precedent / integration — see code_context)
- `frontend/src/routes/kiosk/StalenessBar.tsx` — banner pattern to mirror.
- `frontend/src/routes/kiosk/KioskView.tsx` — SSE consumer + connectivity wiring.
- `frontend/src/state/store.ts` — `connectivity` slice (`sseConnected`, `bannerVisible` stub).
- `frontend/src/App.tsx` — `QueryClient` defaultOptions (add `networkMode`).
- `frontend/src/components/SyncToast.tsx` — transient confirmation precedent for the "Back online" toast.
- `src/gruvax/api/events.py` — SSE endpoint (`ping=15`); where `retry:` jitter is added.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`StalenessBar.tsx`** — Nordic Grid top-bar banner (`role="alert"`, `aria-live="polite"`, inline
  SVG icon, not dismissible). Template for the offline banner's structure/position; offline gets a
  distinct urgent palette + connectivity icon (D-03).
- **`SyncToast.tsx`** — existing transient toast; reuse for the "Back online" confirmation (D-07).
- **`connectivity` store slice** (`store.ts`): `{ sseConnected, lastSeenAt, bannerVisible }` —
  `bannerVisible` is explicitly a "deferred Offline-Banner slice" stub this phase implements.
  `setSseConnected` already updates `sseConnected`/`lastSeenAt`.

### Established Patterns
- **SSE consumer in `KioskView.tsx`** already handles `onopen`→`setSseConnected(true)`+resync,
  `onerror`→`setSseConnected(false)` (no `es.close()` — Pitfall 4), `server_hello`→resync+invalidate,
  `server_shutdown`→`setSseConnected(false)`. Banner + toast hook onto these exact transitions; no new
  SSE event types needed.
- **Stale-closure safety:** all SSE handlers read store state via `useGruvaxStore.getState()` /
  `useSessionStore.getState()` (Pitfall 5) — follow this when adding banner/toast logic.
- **Per-profile SSE URL** `/api/events/{profile_id}`; SSE only opens when a profile is bound — degraded
  mode must coexist with the "no profile bound" path.
- Kiosk search query already uses `staleTime: 30_000`; `/api/health` query already returns null when
  offline (StalenessBar self-hides — gives offline banner clean precedence).

### Integration Points
- `App.tsx` `QueryClient` `defaultOptions.queries` → add `networkMode: 'always'`.
- `KioskView.tsx` SSE `onopen`/`onerror`/`server_hello`/`server_shutdown` → drive `bannerVisible` +
  trigger the "Back online" toast on the offline→online transition.
- Render the offline banner in the kiosk top-bar slot, above and suppressing other banners/pills (D-04).
- Gate search input, profile-switch button, and cube-tap handlers on `!connectivity.sseConnected` (D-05).
- `src/gruvax/api/events.py` → emit `retry:` with per-connection jitter (OFF-03).

</code_context>

<specifics>
## Specific Ideas

- Banner copy is fixed wording (D-01/D-02): "No network — trying to reconnect…" / "Can't reach GRUVAX
  — trying to reconnect…".
- "Back online" toast on recovery, ~2–3 s auto-dismiss (D-07).
- Offline state must NOT hide the preserved last locate result / cube highlight — that's the whole
  point of degraded mode (so a full-screen scrim was explicitly rejected).

</specifics>

<deferred>
## Deferred Ideas

- **Admin / mobile-UI offline treatment** — the ROADMAP success criteria are kiosk-scoped; the mobile
  admin is transient and out of scope here. If a future phase wants offline UX for the admin tab,
  capture it there. (PITFALLS 36 only counts an open admin tab as one more reconnect-storm client —
  the `retry:` jitter already covers that.)
- **Reconnect-toast outage-duration threshold** (silent for < ~10 s blips, toast after longer outages)
  — considered and set aside in favor of always showing the toast (D-07). Revisit only if the toast
  feels noisy during frequent Compose restarts.
- **`/api/health` reconnect probe vs SSE-only reconnect** — left to planner discretion (see Claude's
  Discretion); not a product decision.

</deferred>

---

*Phase: 9-Offline + Reconnect UX*
*Context gathered: 2026-06-01*

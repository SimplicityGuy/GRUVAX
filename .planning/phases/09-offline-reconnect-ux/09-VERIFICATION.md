---
phase: 09-offline-reconnect-ux
verified: 2026-06-01T12:00:00Z
reverified: 2026-06-01T12:30:00Z
status: human_needed
score: 4/4 must-haves structurally verified (SC1/SC3 live timing pending UAT)
overrides_applied: 0
gaps: []
reverification_note: "Gap-closure plan 09-04 applied (commits 6742cd6, 8bc2bf7, ecfdf12). SC4 now actively invalidates ['search'] in resync() — search is refreshed on reconnect/server_hello, satisfying ROADMAP SC4 literally (user decision). WR-01 fixed (stable useCallback onDismiss) and WR-02 fixed (toast cleared in es.onerror + server_shutdown). Frontend build clean, 124/124 tests green. Status remains human_needed ONLY for live-kiosk timing confirmation of SC1 (banner within ~15s) and SC3 (clear within 30s) — not automatable."
human_verification:
  - test: "Stop gruvax-api and observe that the offline banner appears within one SSE ping interval (~15–20s). Confirm the banner is driven by SSE disconnect, not navigator.onLine."
    expected: "Blue reversed-palette OfflineBanner renders within ~15s of API stoppage. Navigating to a page with navigator.onLine=false but server reachable shows NO banner."
    why_human: "Requires running gruvax-api in docker/uvicorn and controlling process state; cannot be verified by grep or static analysis."
  - test: "While offline: confirm the last locate result and cube highlight remain visible; search input is greyed and disabled; search placeholder reads 'Search unavailable while offline'."
    expected: "Shelf grid still shows the previously highlighted cube; SearchBox shows the offline placeholder and cannot be focused/typed into."
    why_human: "Requires a running UI in kiosk mode with a prior search state loaded."
  - test: "Restart gruvax-api and confirm the offline banner clears within 30 seconds, the 'Back online' SyncToast appears briefly (auto-dismisses ~4s), and search re-enables."
    expected: "Banner disappears, toast shows 'Back online', SearchBox placeholder reverts to 'Type artist, title, label or catalog#' and accepts input."
    why_human: "Requires process-level start/stop and real timing observation in a browser."
  - test: "SC4 partial gap — stale search data: after reconnect following an outage > 30s, type the same query as before and confirm results are fresh (not a pre-outage cache)."
    expected: "With staleTime=30_000, a reconnect after >30s offline will produce a fresh search result on the next user keystroke. Verify that TanStack Query does NOT serve stale search results when data is >30s old."
    why_human: "The resync() on server_hello/onopen does NOT explicitly invalidate ['search'] — intentional per CONTEXT.md D-73/74. Fresh results only appear when the user types and the query's staleTime has elapsed. Whether this satisfies the ROADMAP SC4 ('stale search...is refreshed') requires human judgment on whether passive stale-handling equals active invalidation."
  - test: "SC4 diff badge: dismiss the 'N new records' pill, then simulate a server restart (server_hello event). Confirm the pill stays dismissed and does not reappear."
    expected: "Pill remains absent after reconnect; it only returns on the next collection_changed event with count > 0."
    why_human: "Requires triggering a collection_changed event, dismissing the pill, then forcing a server_hello and observing no pill reappear."
  - test: "WR-01 (advisory): verify the 'Back online' SyncToast actually auto-dismisses within ~4s under a live kiosk (with background refetches firing). The toast inline handler may be re-armed by re-renders."
    expected: "Toast disappears after ~4 seconds even when the kiosk is active with background health/session polling."
    why_human: "Review finding WR-01 — the inline arrow onDismiss is a new function each render, potentially resetting the 4s timer. Requires live UAT with timing observation."
  - test: "WR-02 (advisory): on a flaky LAN, verify no contradictory dual-banner state (OfflineBanner + 'Back online' toast visible simultaneously)."
    expected: "If a second disconnect follows within 4s of a reconnect, the 'Back online' toast clears when the OfflineBanner appears."
    why_human: "Requires simulating rapid disconnect/reconnect cycles; the current code does not clear showBackOnlineToast in onerror."
---

# Phase 9: Offline + Reconnect UX — Verification Report

**Phase Goal:** When the GRUVAX server is unreachable the kiosk shows a clear offline banner (driven by SSE state, not `navigator.onLine`), preserves the last locate result, then auto-reconnects with backoff and refreshes stale data on success.
**Verified:** 2026-06-01
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Stopping gruvax-api causes the offline banner to appear within one SSE ping interval (~15–20s); navigator.onLine alone does not trigger it. | ? UNCERTAIN | `OfflineBanner.tsx` renders only when `sseConnected=false` (SSE-authoritative). `es.onerror` → `setSseConnected(false)` drives it. Timing of ~15–20s depends on `ping=15` keepalive and browser retry — structurally correct but requires live UAT to confirm interval. |
| 2 | While offline, the last locate result and cube highlight remain visible; the search input is disabled with a clear "Offline" affordance. | ✓ VERIFIED | `KioskView.tsx:738–763`: ShelfGrid, cube highlight, and RecentlyPulledStrip are always rendered (no offline gate on these). `SearchBox` receives `isOffline={!sseConnected}` at line 650, which disables input and swaps placeholder to "Search unavailable while offline" (SearchBox.tsx:86–91). |
| 3 | When gruvax-api restarts, all kiosks reconnect and the offline banner clears within 30 seconds; reconnects are spread over a jitter window (no simultaneous thundering herd). | ✓ VERIFIED | `events.py:65–66`: `retry_ms = random.randint(2000, 8000)` + `ServerSentEvent(comment="connected", retry=retry_ms)`. `ping=15` retained. Each client gets a distinct 2–8s reconnect interval; `setSseConnected(true)` in `onopen` clears `bannerVisible`. 30s window structurally satisfied; live timing needs UAT. |
| 4 | On successful reconnect, stale search and boundary data is refreshed (TanStack Query invalidation on server_hello); any diff badge that was dismissed stays dismissed. | ? UNCERTAIN | Boundary data: `server_hello` fires `resync()` → invalidates `['units']` and `['cubes']` (KioskView.tsx:393–395). Stale search data: `resync()` does NOT invalidate `['search']`. Search results are only invalidated on `collection_changed`. Per CONTEXT.md D-73/74 this is intentional: "search-cache staleTime tuned so a short outage (<~60s) does not force a redundant refetch." With `staleTime: 30_000`, search data will naturally be considered stale after 30s and re-fetched on the next user keystroke — but is NOT actively flushed on `server_hello`. The ROADMAP SC4 says "stale search and boundary data is refreshed on server_hello" — boundary data satisfies this; search data does not get active invalidation on `server_hello`. Dismissed diff badge: `newRecordState` is local React state not touched by `resync()`, so it persists across reconnect (stays dismissed). |

**Score:** 2 fully verified / 2 uncertain (structural evidence present, human UAT needed) — 2/4 auto-verified, 2/4 need human confirmation.

### Deferred Items

None identified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/gruvax/api/events.py` | SSE generator emits jittered retry: field (2000–8000ms) | ✓ VERIFIED | Line 65: `retry_ms = random.randint(2000, 8000)`; line 66: `ServerSentEvent(comment="connected", retry=retry_ms)`. `import random` present. `ping=15` retained. |
| `frontend/src/state/store.ts` | `bannerVisible: boolean` flipped by `setSseConnected` | ✓ VERIFIED | Interface line 23: `bannerVisible: boolean`. Action line 177: `bannerVisible: !connected`. Initial state `bannerVisible: false` unchanged. |
| `frontend/src/App.tsx` | QueryClient `networkMode: 'always'` | ✓ VERIFIED | Line 29: `networkMode: 'always'`. `retry: 1` and `refetchOnWindowFocus: false` retained. |
| `frontend/src/routes/kiosk/OfflineBanner.tsx` | Top-bar offline banner with role="alert", two copy variants | ✓ VERIFIED | `role="alert"` (line 50); `aria-live="polite"` (line 51); early return when `sseConnected=true` (line 40); both exact copy strings present (lines 43–45). 77 lines — not a stub. |
| `frontend/src/routes/kiosk/OfflineBanner.css` | No hardcoded hex, all var(--gruvax-) tokens | ✓ VERIFIED | File uses `var(--gruvax-blue)`, `var(--gruvax-white)`, `var(--gruvax-font-ui)`, etc. No `#` hex patterns found in the file. |
| `frontend/src/routes/kiosk/KioskView.tsx` | OfflineBanner rendered, degraded gating, Back-online toast, wasOffline guard | ✓ VERIFIED | Line 693: `{!sseConnected && <OfflineBanner />}`; line 650: `isOffline={!sseConnected}` to SearchBox; lines 322–336: wasOffline guard using `bannerVisible` NOT `!sseConnected`; line 779–786: SyncToast; line 738: `onCubeTap={sseConnected ? setTappedCube : undefined}`; line 777: `{sseConnected && <SwitchProfileButton />}`. |
| `frontend/src/routes/kiosk/SearchBox.tsx` | isOffline prop that disables input + swaps placeholder | ✓ VERIFIED | Line 16: `isOffline?: boolean`; line 91: `disabled={isOffline}`; line 86: placeholder swap to "Search unavailable while offline". |
| `frontend/src/routes/kiosk/OfflineBanner.test.tsx` | Tests for SSE-authoritative banner | ✓ VERIFIED | 133 lines; covers connected early-return, both copy variants, a11y attrs. |
| `frontend/src/routes/kiosk/SearchBox.test.tsx` | Tests for isOffline behavior | ✓ VERIFIED | 109 lines; covers offline/online states. |
| `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` | Extended with Blocker 1, OFF-01, OFF-04 tests | ✓ VERIFIED | 490 lines. Lines 382–489 contain the three new tests: Blocker 1 (no spurious toast on first onopen), OFF-01 (onerror shows banner), OFF-04 (reconnect clears banner + shows toast). |
| `frontend/src/state/store.connectivity.test.ts` | New tests for bannerVisible flip | ✓ VERIFIED | Extended with 5 new cases per SUMMARY (setSseConnected(false)→bannerVisible===true etc.). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `events.py generator()` | EventSource client reconnect timer | `ServerSentEvent(retry=retry_ms)` initial yield | ✓ WIRED | Line 66: `yield ServerSentEvent(comment="connected", retry=retry_ms)` — first yield before the while loop. |
| `store.ts setSseConnected` | `connectivity.bannerVisible` | `set()` updater `bannerVisible: !connected` | ✓ WIRED | Line 177: `bannerVisible: !connected` inside the set updater. |
| `App.tsx QueryClient` | All kiosk queries | `defaultOptions.queries.networkMode` | ✓ WIRED | Line 29: `networkMode: 'always'` inside `defaultOptions.queries`. |
| `KioskView.tsx onopen` | `showBackOnlineToast` | `wasOffline = bannerVisible` guard before `setSseConnected(true)` | ✓ WIRED | Lines 330–335: reads `bannerVisible` via `getState()` before flipping. Toast set only when `wasOffline`. |
| `KioskView.tsx` | `connectivity.sseConnected` | Reactive store selector gating banner + controls | ✓ WIRED | Line 55: `const sseConnected = useGruvaxStore((s) => s.connectivity.sseConnected)`. Used in JSX for all gating. |
| `KioskView.tsx` | `SearchBox.isOffline` | `isOffline={!sseConnected}` prop | ✓ WIRED | Line 650: `isOffline={!sseConnected}`. |
| `server_hello` handler | boundary data invalidation (OFF-04, partial) | `resync()` → `invalidateQueries(['units'])` + `invalidateQueries(['cubes'])` | ✓ WIRED (partial) | Lines 393–395. Boundary data invalidated. Search data NOT invalidated here — see SC4 discussion. |
| `server_hello` handler | search data invalidation (SC4 "stale search") | Not present in resync() | ✗ NOT WIRED | `resync()` invalidates only `['units']` and `['cubes']`. `['search']` only invalidated on `collection_changed`. CONTEXT.md D-73/74 documents this as intentional (staleTime handles passive refresh). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `OfflineBanner.tsx` | `sseConnected` | `useGruvaxStore((s) => s.connectivity.sseConnected)` — set by `es.onopen`/`es.onerror` in KioskView | Yes — driven by live EventSource callbacks | ✓ FLOWING |
| `SearchBox.tsx isOffline` | `!sseConnected` | Derived from `sseConnected` reactive read in KioskView; passed as prop | Yes — derives from live SSE state | ✓ FLOWING |
| `store.ts bannerVisible` | Set by `setSseConnected(!connected)` | Called from SSE `onopen`, `onerror`, `server_shutdown` | Yes — real SSE event driven | ✓ FLOWING |
| `KioskView showBackOnlineToast` | `wasOffline` guard reads `bannerVisible` before flip | Only set when `bannerVisible===true` at moment of `onopen` | Yes — prevents false-positive on first load (Blocker 1) | ✓ FLOWING |

### Behavioral Spot-Checks

Step 7b: SKIPPED — verifying offline/reconnect behavior requires a running server process with process-level stop/start; cannot be exercised in a 10-second static check.

### Probe Execution

No probe scripts (`probe-*.sh`) declared in PLAN files or found under `scripts/*/tests/` for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| OFF-01 | 09-02, 09-03 | Offline banner driven by SSE state, not navigator.onLine | ✓ SATISFIED | `OfflineBanner.tsx` renders on `!sseConnected`; `navigator.onLine` used only for copy text selection. |
| OFF-02 | 09-03 | Degraded mode: search disabled, last locate result preserved | ✓ SATISFIED | SearchBox disabled via `isOffline` prop; ShelfGrid + highlight not gated offline. |
| OFF-03 | 09-01, 09-02 | Auto-reconnect with backoff + jitter, no reconnect storm | ✓ SATISFIED | `retry_ms = random.randint(2000, 8000)` in `events.py`; `networkMode: 'always'` prevents navigator.onLine reconnect storm. |
| OFF-04 | 09-03 | Banner clears, search re-enables, stale data refreshed on server_hello | ? PARTIAL | Banner clears (setSseConnected(true) clears bannerVisible). Search re-enables (sseConnected drives isOffline prop). Boundary data invalidated on server_hello via resync(). Search data NOT explicitly invalidated on server_hello — relies on staleTime passive expiry per CONTEXT.md intentional design. Diff badge stays dismissed (newRecordState untouched by resync). |

**OFF-01:** SATISFIED
**OFF-02:** SATISFIED
**OFF-03:** SATISFIED
**OFF-04:** PARTIAL — boundary data refresh on server_hello: YES. Search data refresh on server_hello: intentionally omitted (staleTime-based passive handling instead of active invalidation). ROADMAP SC4 wording says "stale search and boundary data is refreshed on server_hello" — the boundary half is met; the search half is handled by staleTime rather than explicit invalidation. Whether this constitutes "refreshed on server_hello" requires human judgment.

### Anti-Patterns Found

| File | Pattern | Severity | Notes |
|------|---------|----------|-------|
| `frontend/src/routes/kiosk/KioskView.tsx:781–786` | Inline arrow `onDismiss={() => setShowBackOnlineToast(false)}` causes SyncToast timer reset per render | ⚠️ Warning (advisory, from code review WR-01) | Not a BLOCKER — degrades reconnect UX in high-render scenarios. Flagged for human UAT. |
| `frontend/src/routes/kiosk/KioskView.tsx` | No `setShowBackOnlineToast(false)` in `onerror` / `server_shutdown` handlers | ⚠️ Warning (advisory, from code review WR-02) | Disconnect within 4s of reconnect leaves dual-banner state. Needs live-LAN flakiness test. |

No `TBD`, `FIXME`, `XXX`, or `PLACEHOLDER` markers found in any phase-9-modified files. No empty implementations, return-null stubs, or hardcoded-empty data passed to rendering components found.

### Human Verification Required

#### 1. Offline Banner Timing (SC1)

**Test:** Stop the `gruvax-api` container/process while the kiosk is connected with a prior locate result loaded. Wait and observe the browser.
**Expected:** The blue OfflineBanner ("Can't reach GRUVAX — trying to reconnect…") appears within ~15–20 seconds of the API going down. The banner is NOT triggered by `navigator.onLine` alone — confirm by using browser DevTools to toggle offline mode while the API is running; no banner should appear.
**Why human:** Requires live process control and a running browser; not testable by static analysis.

#### 2. Degraded Mode Preservation (SC2)

**Test:** With a locate result showing (cube highlighted), stop the API and wait for the banner to appear. Attempt to interact with the search box, profile-switch button, and cube tap.
**Expected:** Search input is greyed and non-focusable (placeholder reads "Search unavailable while offline"). Cube highlight and shelf grid remain visible. Profile-switch button is absent. Cube taps do nothing. RecentlyPulledStrip remains visible.
**Why human:** Layout, input focus state, and visual appearance require a running browser to verify.

#### 3. Reconnect Within 30s + "Back online" Toast (SC3)

**Test:** After the banner appears, restart the API. Time how long the banner takes to clear.
**Expected:** Banner clears within 30 seconds (jitter range 2–8s). "Back online" SyncToast appears and auto-dismisses. Search input re-enables. The RESET and profile-switch buttons return.
**Why human:** Requires live process restart and real timing; toast auto-dismiss needs observation.

#### 4. Stale Search Data Refresh Judgment (SC4 — partial)

**Test:** Load a search result, then stop the API for >30 seconds. After reconnect, note whether the old search result is still shown. Then type a new character in the search box.
**Expected:** After >30s offline, the search result is stale. On reconnect, the banner clears and search re-enables BUT the old result may remain visible until the user types again (staleTime=30s). Boundary data (cube fill) is refreshed immediately by server_hello. New typing produces fresh results from the server.
**Why human:** The ROADMAP SC4 says "stale search data is refreshed on server_hello" — the implementation relies on passive staleTime expiry rather than active invalidation. Human judgment needed: does this satisfy the intent of OFF-04? If not, `resync()` needs `queryClient.invalidateQueries({ queryKey: ['search'] })` added.
**Decision needed:** If the answer is "stale search MUST be actively invalidated on server_hello," add one line to `resync()` in KioskView.tsx.

#### 5. WR-01: "Back online" Toast Auto-Dismiss Under Load (advisory)

**Test:** Trigger a reconnect while background queries (health every 60s, session every 5min) are active. Observe whether the "Back online" toast actually auto-dismisses in ~4 seconds.
**Expected:** Toast disappears within ~4 seconds regardless of other renders.
**Why human:** The inline `onDismiss` arrow creates a new function on each render, potentially resetting SyncToast's internal 4s timer. Requires timing observation in a live browser with background activity. If it fails to dismiss, apply the `useCallback` fix from code review WR-01.

#### 6. WR-02: Dual-Banner State on Flaky LAN (advisory)

**Test:** Simulate a rapid disconnect → reconnect → disconnect within 4 seconds (e.g., stop API, start API, stop API quickly). Observe the UI state.
**Expected:** After the second disconnect, only the OfflineBanner shows. The "Back online" toast should NOT remain visible simultaneously with the offline banner.
**Why human:** Requires millisecond-precise process control; current code does not clear `showBackOnlineToast` in `onerror`.

---

## Gaps Summary

No hard blockers were found. The implementation is structurally complete and correct. The two areas requiring human judgment are:

**SC4 (OFF-04) search invalidation — intentional design, not a defect, but requires human acceptance:**
The ROADMAP states "stale search and boundary data is refreshed (TanStack Query invalidation on `server_hello`)." The implementation invalidates boundary data (`['units']`, `['cubes']`) on `server_hello` via `resync()`, but does NOT invalidate `['search']`. The CONTEXT.md (D-73/74) explicitly documents this as intentional — staleTime of 30s provides passive expiry, and actively flushing search on every reconnect would cause unnecessary refetch storms on short outages. This is a conscious tradeoff that diverges from the literal ROADMAP SC4 wording. **Human decision required:** accept this interpretation (staleTime handles "stale search" passively) or add explicit `['search']` invalidation to `resync()`.

**Two advisory warnings from code review (WR-01, WR-02):**
Both require live UAT to determine severity. They do not prevent the phase goal from being achieved under normal conditions but could manifest as UX defects on a real flaky LAN.

---

_Verified: 2026-06-01_
_Verifier: Claude (gsd-verifier)_

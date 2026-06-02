---
phase: 09-offline-reconnect-ux
reviewed: 2026-06-01T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - frontend/src/App.tsx
  - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/OfflineBanner.css
  - frontend/src/routes/kiosk/OfflineBanner.test.tsx
  - frontend/src/routes/kiosk/OfflineBanner.tsx
  - frontend/src/routes/kiosk/SearchBox.test.tsx
  - frontend/src/routes/kiosk/SearchBox.tsx
  - frontend/src/state/store.connectivity.test.ts
  - frontend/src/state/store.ts
  - src/gruvax/api/events.py
findings:
  critical: 0
  warning: 4
  info: 4
  total: 8
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-06-01T00:00:00Z
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 9 wires SSE-connectivity state into the kiosk UI: an `OfflineBanner`, a degraded-mode `SearchBox` (disabled while offline), suppression of transient banners while disconnected, and a "Back online" toast on genuine reconnect. The store's `bannerVisible` was promoted from a stub literal `false` to a real `boolean` derived from `!sseConnected`.

The implementation is largely sound and the transition-detection logic (reading `bannerVisible` rather than `!sseConnected` in `onopen` to avoid a spurious first-load toast) is correct and well-tested. No security vulnerabilities or data-loss risks were found.

However there are several behavioral defects in the reconnect/toast path that the test suite does not exercise: an unstable effect dependency that can prevent the "Back online" toast from auto-dismissing, a contradictory dual-banner state on rapid disconnect/reconnect cycles, and an unguarded `JSON.parse` shape assumption. These are WARNING-tier — they degrade the reconnect UX rather than corrupt data, but they will misbehave on a real flaky LAN link (the exact scenario this phase exists to handle).

## Warnings

### WR-01: "Back online" toast may never auto-dismiss — unstable `onDismiss` resets SyncToast timers every render

**File:** `frontend/src/routes/kiosk/KioskView.tsx:781-786` (with `frontend/src/components/SyncToast.tsx:28-41`)
**Issue:** The toast is rendered with an inline arrow as its dismiss handler:

```tsx
<SyncToast
  message="Back online"
  onDismiss={() => setShowBackOnlineToast(false)}
/>
```

`SyncToast` schedules its 4s auto-dismiss inside `useEffect(..., [onDismiss])`. Because the arrow is a new function identity on every `KioskView` render, the effect's cleanup runs and the two `setTimeout`s are re-armed on each re-render. `KioskView` re-renders frequently while the toast is visible — the `['health']` query refetches every 60s, the `['session']` query every 5min, and any keystroke / store change re-renders it. If any re-render lands inside the 4s window, the dismiss timer restarts from zero. In the worst case (e.g. a render every <4s from background activity) the toast never dismisses and the "Back online" banner sticks permanently, contradicting D-07 ("auto-dismisses after 4s"). Existing tests pass only because they render a static tree with no background refetches firing inside the window.
**Fix:** Stabilize the callback with `useCallback`, or make `SyncToast`'s effect depend on something stable. Minimal fix:

```tsx
const dismissBackOnline = useCallback(() => setShowBackOnlineToast(false), [])
// ...
{showBackOnlineToast && (
  <SyncToast message="Back online" onDismiss={dismissBackOnline} />
)}
```

(Alternatively, change `SyncToast`'s effect to `useEffect(..., [])` and stash `onDismiss` in a ref — but fixing the caller is the smaller change and matches how `SyncToast` is consumed elsewhere.)

### WR-02: Contradictory dual-banner state on a disconnect → reconnect → disconnect cycle within 4s

**File:** `frontend/src/routes/kiosk/KioskView.tsx:693, 779-786`
**Issue:** `showBackOnlineToast` is set `true` in `onopen` and only cleared by SyncToast's 4s dismiss. The `OfflineBanner` renders whenever `!sseConnected`. On a flaky LAN (the target environment for this phase), the sequence disconnect → reconnect → disconnect-again can occur inside the 4s toast window. After the second disconnect, `sseConnected` is `false` so the `OfflineBanner` ("trying to reconnect…") renders, while `showBackOnlineToast` is still `true` so the "Back online" toast renders simultaneously — the UI tells the user it is both offline and back online at the same time.
**Fix:** Clear the toast when going offline. In `es.onerror` (and the `server_shutdown` listener), reset the flag:

```tsx
es.onerror = () => {
  useGruvaxStore.getState().setSseConnected(false)
  setShowBackOnlineToast(false)   // cancel any pending "Back online" toast
}
```

### WR-03: `boundary_changed` / `admin_editing` parse assumes payload shape — iterating a possibly-undefined `cube_ids`

**File:** `frontend/src/routes/kiosk/KioskView.tsx:347-371` (and `376-390`)
**Issue:** The handler destructures `const { cube_ids } = JSON.parse(e.data)` and immediately does `for (const c of cube_ids)` and `clearShimmerCubes(cube_ids)`. If the server emits a frame whose JSON parses successfully but lacks `cube_ids` (or sends it as a non-array), `cube_ids` is `undefined` and `for...of undefined` throws `TypeError: cube_ids is not iterable`. The surrounding `try/catch` does catch it (so it degrades to a logged error rather than a crash), but the comment claims the wrapper guards against "a mis-keyed frame" while in practice a mis-keyed frame silently no-ops the entire handler — including the `relocateActiveSelection()` call that should still run. The shimmer-clear and re-locate are skipped on any partially-malformed frame, which can leave stale shimmer cubes lit until the 60s TTL sweeper fires.
**Fix:** Validate the shape before iterating and default to an empty array so the rest of the handler still runs:

```tsx
const parsed = JSON.parse(e.data) as { cube_ids?: ShimmerCube[] }
const cubeIds = Array.isArray(parsed.cube_ids) ? parsed.cube_ids : []
// ...invalidate, then:
for (const c of cubeIds) { /* ... */ }
useGruvaxStore.getState().clearShimmerCubes(cubeIds)
relocateActiveSelection()
```

### WR-04: SSE generator buffers events for ~1s before observing client disconnect; no `send_timeout`

**File:** `src/gruvax/api/events.py:67-79, 81-88`
**Issue:** The generator loop blocks on `asyncio.wait_for(q.get(), timeout=1.0)` and only re-checks `request.is_disconnected()` once per loop. A client that disconnects right after an event is delivered will not be observed as gone until the next 1s timeout completes, leaving the subscriber queue registered for up to ~1s longer than necessary. More importantly, `EventSourceResponse` is constructed without a `send_timeout`, so a wedged/half-open TCP connection (common on Wi-Fi roaming, the Pi → host critical path) can leave the send coroutine blocked indefinitely on a full socket buffer, holding the subscriber slot (`maxsize=64` bus) and a server task. On a single-user kiosk the leak ceiling is low, but a stuck connection that never frees its subscriber can mask a genuine reconnect.
**Fix:** Pass a `send_timeout` so sse-starlette tears down a stuck send, and the disconnect is then surfaced promptly:

```python
return EventSourceResponse(
    generator(),
    ping=15,
    send_timeout=5,  # tear down a wedged client send instead of blocking forever
    headers={...},
)
```

## Info

### IN-01: `bannerVisible` is now fully redundant with `!sseConnected`

**File:** `frontend/src/state/store.ts:20-24, 168-178`
**Issue:** `bannerVisible` is set to exactly `!connected` in the only writer (`setSseConnected`). It now carries no independent information from `sseConnected`. The single legitimate consumer is the `onopen` transition check in `KioskView` — but that reads `bannerVisible` specifically because it is set *before* `setSseConnected(true)` flips it; `!sseConnected` would also work there since both update in the same `set()` call. The duplicated field invites future drift if a writer ever sets one without the other.
**Fix:** Either document that `bannerVisible` exists solely as the "was-offline" latch for reconnect-toast detection, or collapse it and derive `wasOffline` from `!useGruvaxStore.getState().connectivity.sseConnected` at the top of `onopen` (read before the `setSseConnected(true)` call). No behavior change required this phase; flag for cleanup.

### IN-02: `OfflineBanner` `role="alert"` + `aria-live="polite"` is a contradictory ARIA pairing

**File:** `frontend/src/routes/kiosk/OfflineBanner.tsx:48-52`
**Issue:** `role="alert"` implies an `aria-live="assertive"` live region by default; explicitly setting `aria-live="polite"` on the same element gives screen readers conflicting urgency signals. The intent (non-interrupting announcement) is reasonable, but the combination is non-idiomatic — use `role="status"` (which is implicitly polite) for a polite announcement, or drop the `aria-live` override and accept assertive semantics for an alert.
**Fix:** Prefer `role="status"` for the polite, non-urgent reconnect notice, or remove `aria-live="polite"` and let `role="alert"` be assertive. (The test at `OfflineBanner.test.tsx:80-84` asserts the current contradictory pairing, so update it to match.)

### IN-03: `OfflineBanner` `online`/`offline` listeners only refine cosmetic copy, but re-subscribe is sound

**File:** `frontend/src/routes/kiosk/OfflineBanner.tsx:26-37`
**Issue:** The component mounts only while disconnected (parent gates it with `{!sseConnected && ...}`), so the `navigator.onLine` listeners attach and detach on each disconnect/reconnect cycle rather than living for the page lifetime. This is correct and leak-free, but it means the `online`/`offline` events are only observed during a disconnected window — which is exactly when they matter, so the behavior is fine. Noting it only because the doc comment frames `navigator.onLine` as a "secondary hint" without mentioning the listener is scoped to the disconnected window.
**Fix:** No change required. Optionally add a one-line comment that the listeners are intentionally mount-scoped to the offline window.

### IN-04: Pre-existing — `SearchBox` debounce timer is not cleared on unmount

**File:** `frontend/src/routes/kiosk/SearchBox.tsx:33-44`
**Issue:** `debounceRef` holds a `setTimeout` that is cleared on the next keystroke and on clear, but never in an unmount cleanup. If `SearchBox` unmounts within 250ms of a keystroke (e.g. the kiosk transitions to `EmptyCollectionState`, which replaces the search results region while `SearchBox` stays mounted — but a route change away from `/` would unmount it), the pending callback fires `onDebouncedQuery` on an unmounted tree. Not introduced by Phase 9, but adjacent to the offline gating this phase added (the input is now `disabled` while offline, which does not flush the existing timer).
**Fix:** Add an unmount cleanup:

```tsx
useEffect(() => () => {
  if (debounceRef.current) clearTimeout(debounceRef.current)
}, [])
```

---

_Reviewed: 2026-06-01T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

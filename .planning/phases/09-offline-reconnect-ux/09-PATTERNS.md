# Phase 9: Offline + Reconnect UX — Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 6 (all extensions/modifications of existing files; no net-new files)
**Analogs found:** 6 / 6

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `frontend/src/routes/kiosk/StalenessBar.tsx` (new `OfflineBanner` mirrors it) | component | event-driven | `StalenessBar.tsx` itself (IS the analog) | exact |
| `frontend/src/components/SyncToast.tsx` | component | event-driven | `SyncToast.tsx` itself (IS the analog — reused not copied) | exact |
| `frontend/src/state/store.ts` | store | event-driven | `store.ts` itself (IS the analog — slice extended in place) | exact |
| `frontend/src/routes/kiosk/KioskView.tsx` | component/consumer | event-driven | `KioskView.tsx` itself (IS the analog — SSE handlers extended) | exact |
| `frontend/src/App.tsx` | config/provider | request-response | `App.tsx` itself (IS the analog — `QueryClient` defaultOptions modified) | exact |
| `src/gruvax/api/events.py` | service/route | streaming | `events.py` itself (IS the analog — generator extended) | exact |

---

## Pattern Assignments

### `frontend/src/routes/kiosk/OfflineBanner.tsx` (new file — component, event-driven)

**Analog:** `frontend/src/routes/kiosk/StalenessBar.tsx`

This is a **net-new component** that mirrors `StalenessBar`'s complete structure with an urgent palette swap and a connectivity icon instead of the AlertTriangle. Copy the entire file structure below and substitute only what is annotated.

**Full component pattern to mirror** (StalenessBar.tsx lines 1–61):

```tsx
/**
 * OfflineBanner — kiosk persistent banner when SSE is disconnected (OFF-01, D-01..D-04).
 *
 * SSE connection state is the authoritative offline trigger — NOT navigator.onLine
 * (PITFALLS 35). navigator.onLine is used only as cosmetic secondary hint for copy:
 *   sseConnected=false + onLine=false → "No network — trying to reconnect…"
 *   sseConnected=false + onLine=true  → "Can't reach GRUVAX — trying to reconnect…"
 *
 * Nordic Grid design contract:
 * - Background: --gruvax-blue (reversed/urgent treatment — distinct from yellow StalenessBar)
 * - Text: --gruvax-white (blue-ground inverted)
 * - Icon: inline SVG connectivity icon, aria-hidden="true"
 * - role="alert" + aria-live="polite"
 * - NOT dismissible — clears on reconnect (D-04)
 * - Top-priority: suppresses other banners/pills while visible (D-04)
 *
 * ENFORCEMENT: no hardcoded hex — consume tokens only.
 */

import './OfflineBanner.css'
import { useGruvaxStore } from '../../state/store'

export function OfflineBanner() {
  const sseConnected = useGruvaxStore((s) => s.connectivity.sseConnected)
  const [isOnline, setIsOnline] = useState(navigator.onLine)

  useEffect(() => {
    const handleOnline = () => setIsOnline(true)
    const handleOffline = () => setIsOnline(false)
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [])

  if (sseConnected) return null   // matches StalenessBar's early-return pattern

  const copy = isOnline
    ? 'Can\'t reach GRUVAX — trying to reconnect…'
    : 'No network — trying to reconnect…'

  return (
    <div
      className="offline-banner"
      role="alert"
      aria-live="polite"
    >
      {/* Connectivity inline SVG — aria-hidden="true" per StalenessBar pattern */}
      <svg
        xmlns="http://www.w3.org/2000/svg"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        {/* WifiOff or similar connectivity icon — planner/executor chooses from Lucide set */}
        <line x1="1" y1="1" x2="23" y2="23" />
        <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
        <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
        <path d="M10.71 5.05A16 16 0 0 1 22.56 9" />
        <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
        <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
        <line x1="12" y1="20" x2="12.01" y2="20" />
      </svg>
      {copy}
    </div>
  )
}
```

**CSS pattern to copy** (StalenessBar.css lines 17–53 — substitute `offline-banner` class and urgent tokens):

```css
/* OfflineBanner.css — mirrors StalenessBar.css structure, urgent palette */
.offline-banner {
  background: var(--gruvax-blue);         /* reversed: blue-ground vs yellow-ground */
  color: var(--gruvax-white);             /* white-on-blue — AAA at 18px */
  font-family: var(--gruvax-font-ui);
  font-size: var(--gruvax-text-body-lg);  /* 18px — matches staleness-bar */
  font-weight: 400;
  line-height: var(--gruvax-leading-normal);
  padding: var(--gruvax-space-3) var(--gruvax-space-4);
  display: flex;
  align-items: center;
  gap: var(--gruvax-space-2);
  width: 100%;
  border-radius: 0;

  /* Mount animation: mirrors staleness-bar-enter keyframe */
  overflow: hidden;
  max-height: 48px;
  opacity: 1;
  animation: staleness-bar-enter var(--gruvax-duration-base) var(--gruvax-ease-decelerate) both;
}

/* Reuse keyframe name from StalenessBar.css (already in global scope) */
/* OR define offline-banner-enter locally if StalenessBar.css is not imported in KioskView */

.offline-banner svg {
  flex-shrink: 0;
  color: inherit;
}
```

**Note on token choice:** `--gruvax-blue` (#0051A2) on `--gruvax-white` achieves a high-contrast reversed treatment. `--gruvax-blue-dark` (#003D7A) is the pressed/hover variant if a stronger urgency level is needed. Executor must NOT hardcode hex — pick from the token set. Do not use `--gruvax-error` (#C0392B) — the banner is operational-signal (service down), not an error state.

---

### `frontend/src/components/SyncToast.tsx` (existing file — reuse, no modification needed)

**Analog:** `SyncToast.tsx` itself

This component is **already correct** for the "Back online" use case. The executor calls it with a new message string from `KioskView.tsx`, not from the admin shell where it currently lives.

**Props API** (SyncToast.tsx lines 18–21):

```tsx
interface SyncToastProps {
  message: string     // Pass: "Back online"
  onDismiss: () => void
}
```

**Auto-dismiss timing** (SyncToast.tsx lines 23–41):

```tsx
const AUTO_DISMISS_MS = 4000   // 4s total; exit animation starts at 3850ms

useEffect(() => {
  const exitTimer = setTimeout(() => {
    setIsExiting(true)
  }, AUTO_DISMISS_MS - 150)   // 150ms exit animation before dismiss

  const dismissTimer = setTimeout(() => {
    onDismiss()
  }, AUTO_DISMISS_MS)

  return () => {
    clearTimeout(exitTimer)
    clearTimeout(dismissTimer)
  }
}, [onDismiss])
```

**CSS animation classes** (admin.css lines 5440–5475):

```css
.sync-toast {
  position: fixed;
  top: var(--gruvax-space-4);
  right: var(--gruvax-space-4);
  z-index: var(--gruvax-z-admin);    /* 50 — above everything */
  background: var(--gruvax-success); /* #1A7A4A — green confirmation */
  color: var(--gruvax-white);
  animation: toast-slide-in var(--gruvax-duration-base) var(--gruvax-ease-decelerate) both;
}
.sync-toast--exiting {
  animation: toast-fade-out var(--gruvax-duration-fast) var(--gruvax-ease-standard) both;
}
```

**Usage pattern in KioskView** — the executor adds a `showBackOnlineToast` boolean state and renders:

```tsx
{showBackOnlineToast && (
  <SyncToast
    message="Back online"
    onDismiss={() => setShowBackOnlineToast(false)}
  />
)}
```

The toast is triggered from the `onopen` handler on an offline→online transition (see KioskView pattern below). For the 2–3 s vs 4 s auto-dismiss: `AUTO_DISMISS_MS = 4000` is already close enough; the CONTEXT says "~2–3 s" which is at the planner's discretion — either accept 4 s or override the constant.

---

### `frontend/src/state/store.ts` (existing file — `ConnectivityState` interface + `bannerVisible` extended)

**Analog:** `store.ts` itself

**Current stub** (store.ts lines 19–24):

```ts
/**
 * SSE connectivity state (Phase 4 / D-10).
 * bannerVisible is a stub for the deferred Offline-Banner slice (Plan 04);
 * set false always this phase.
 */
interface ConnectivityState {
  sseConnected: boolean
  lastSeenAt: number
  bannerVisible: false   // <— currently a literal false type (stub)
}
```

**Required change — unlock `bannerVisible` to boolean:**

```ts
interface ConnectivityState {
  sseConnected: boolean
  lastSeenAt: number
  bannerVisible: boolean   // was: false (stub) — Phase 9 activates this
}
```

**Current `setSseConnected` action** (store.ts lines 168–176):

```ts
setSseConnected: (connected) =>
  set((s) => ({
    connectivity: {
      ...s.connectivity,
      sseConnected: connected,
      lastSeenAt: connected ? Date.now() : s.connectivity.lastSeenAt,
    },
  })),
```

**Required change — add `bannerVisible` flip:**

```ts
setSseConnected: (connected) =>
  set((s) => ({
    connectivity: {
      ...s.connectivity,
      sseConnected: connected,
      lastSeenAt: connected ? Date.now() : s.connectivity.lastSeenAt,
      bannerVisible: !connected,   // banner shows when disconnected (OFF-01)
    },
  })),
```

**Initial state** (store.ts line 166):

```ts
// current:
connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
// after change — no literal type conflict once interface is boolean:
connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
```

**Stale-closure-safe read pattern** — ALL SSE event handlers read store state via `.getState()`, never from the outer destructure. This pattern is established throughout KioskView.tsx and must be followed for any new banner/toast logic:

```ts
// Correct (Pitfall 5):
useGruvaxStore.getState().setSseConnected(true)
useGruvaxStore.getState().connectivity.bannerVisible

// WRONG — stale closure:
const { connectivity } = useGruvaxStore()  // captured at effect mount time
```

---

### `frontend/src/routes/kiosk/KioskView.tsx` (existing file — SSE handler augmentation)

**Analog:** `KioskView.tsx` itself

**SSE effect location** (KioskView.tsx lines 277–454) — the `useEffect(() => { ... }, [queryClient, boundProfileId])` block. All additions go inside this effect.

**`onopen` handler — current** (lines 315–318):

```ts
es.onopen = () => {
  useGruvaxStore.getState().setSseConnected(true)
  resync()
}
```

**`onopen` handler — required extension (banner-clear + "Back online" toast on offline→online transition):**

```ts
es.onopen = () => {
  // Detect offline→online transition BEFORE flipping connection.
  // Read bannerVisible (NOT !sseConnected): sseConnected starts false in the initial store
  // state, so !sseConnected would be true on the first-ever onopen of a fresh page load and
  // fire the toast spuriously. bannerVisible starts false and only becomes true after a real
  // disconnect (setSseConnected(false)), so it is the correct reconnect signal (D-07, Blocker 1).
  const wasOffline = useGruvaxStore.getState().connectivity.bannerVisible
  useGruvaxStore.getState().setSseConnected(true)  // also sets bannerVisible=false
  resync()
  // Show "Back online" confirmation only when recovering from a disconnected state (D-07)
  // Uses local React state — must pass a setter down or use a ref-based trigger
  if (wasOffline) {
    setShowBackOnlineToast(true)  // local useState in KioskView
  }
}
```

**`onerror` handler — current** (lines 320–323):

```ts
es.onerror = () => {
  // Mark disconnected — EventSource auto-reconnects; do NOT call es.close() (Pitfall 4)
  useGruvaxStore.getState().setSseConnected(false)
}
```

No change needed here — `setSseConnected(false)` now also sets `bannerVisible=true` via the store action change above.

**`server_shutdown` handler — current** (lines 380–382):

```ts
es.addEventListener('server_shutdown', () => {
  useGruvaxStore.getState().setSseConnected(false)
})
```

No change needed — same as `onerror`, `setSseConnected(false)` now implies `bannerVisible=true`.

**`server_hello` handler — current** (lines 374–377):

```ts
es.addEventListener('server_hello', () => {
  resync()
  void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
})
```

No change needed — `server_hello` fires AFTER `onopen`, so the `onopen` handler already handles banner-clear + toast on the same reconnect event. The resync invalidation in `server_hello` is already the data-refresh plumbing (OFF-04 data refresh "largely exists" per CONTEXT).

**Degraded-mode gating in JSX (D-05/D-06):**

The `sseConnected` value for gating search/profile/cube-tap controls is read reactively:

```tsx
// At top of KioskView, alongside existing store reads:
const sseConnected = useGruvaxStore((s) => s.connectivity.sseConnected)

// Search input gating (D-06) — pass to SearchBox as new prop:
<SearchBox
  onDebouncedQuery={setDebouncedQuery}
  isLoading={showLoading}
  hasError={hasSearchError}
  isOffline={!sseConnected}   // new prop — executor adds to SearchBoxProps
/>

// Cube-tap gating (D-05) — guard the onCubeTap handler:
onCubeTap={sseConnected ? setTappedCube : undefined}

// Profile-switch gating (D-05) — SwitchProfileButton receives a disabled prop or
// KioskView wraps it conditionally — executor decides the exact mechanism.
```

**Banner rendering in JSX (D-03/D-04) — top-priority, suppresses other banners:**

```tsx
{/* OfflineBanner (OFF-01/D-03/D-04): top slot, suppresses transient banners while offline */}
{!sseConnected && <OfflineBanner />}

{/* StalenessBar: only render when online — it self-hides when health is null anyway,
    but explicit guard avoids the flash of the wrong banner signal */}
{sseConnected && <StalenessBar syncAgeSeconds={healthData?.sync_age_seconds ?? null} />}

{/* ReauthBanner + new-records pill: suppressed while offline (D-04) */}
{sseConnected && needsReauth && <ReauthBanner profileName={boundProfile?.display_name} />}
{sseConnected && newRecordState && newRecordState.count > 0 && (
  <div className="kiosk-new-records-pill" ... > ... </div>
)}

{/* ReassignBanner: always shown — it's a completed event, not a live-state signal */}
<ReassignBanner />

{/* "Back online" toast — fixed top-right, auto-dismiss (D-07) */}
{showBackOnlineToast && (
  <SyncToast
    message="Back online"
    onDismiss={() => setShowBackOnlineToast(false)}
  />
)}
```

**`showBackOnlineToast` state declaration** (alongside existing local state at KioskView lines 57–68):

```tsx
const [showBackOnlineToast, setShowBackOnlineToast] = useState(false)
```

**Import additions to KioskView.tsx:**

```tsx
import { OfflineBanner } from './OfflineBanner'
import { SyncToast } from '../../components/SyncToast'
import './OfflineBanner.css'
```

---

### `frontend/src/App.tsx` (existing file — `QueryClient` defaultOptions augmented)

**Analog:** `App.tsx` itself

**Current `QueryClient` config** (App.tsx lines 24–31):

```ts
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});
```

**Required addition — `networkMode: 'always'`** (PITFALLS 35/36):

```ts
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      networkMode: 'always',   // OFF-03/PITFALL 35/36: do not pause on navigator.onLine=false
                               // SSE-derived connectivity state controls query gating instead
    },
  },
});
```

**Why `networkMode: 'always'`:** Without this, TanStack Query pauses all queries when `navigator.onLine=false`. Since GRUVAX uses SSE connectivity (not `navigator.onLine`) as the offline signal, queries must be allowed to run regardless — the SSE-derived `sseConnected` gate on the search input and the `enabled` prop on individual queries provide the actual pausing.

**Search query `staleTime` — current** (KioskView.tsx line 220):

```ts
staleTime: 30_000,   // 30 seconds — current value
```

PITFALLS 37 recommends 60 s so a < 60 s outage does not trigger a reconnect refetch. This is at the planner's discretion — CONTEXT line 74 locks it at `30_000`. If the planner bumps it to `60_000`, the executor changes only that line. If it stays at `30_000`, no change needed.

---

### `src/gruvax/api/events.py` (existing file — `retry:` jitter added to generator)

**Analog:** `events.py` itself

**Current generator** (events.py lines 58–86):

```python
async def generator() -> AsyncIterator[ServerSentEvent]:
    q = bus.subscribe()
    try:
        # Yield an SSE comment immediately so headers flush to the client
        yield ServerSentEvent(comment="connected")
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=1.0)
                yield ServerSentEvent(
                    event=event.name,
                    data=json.dumps(event.data),
                )
            except TimeoutError:
                continue
    finally:
        bus.unsubscribe(q)
```

**Required addition — `retry:` jitter on the initial yield** (PITFALLS 36):

```python
import random   # add to imports at top of file

async def generator() -> AsyncIterator[ServerSentEvent]:
    q = bus.subscribe()
    try:
        # Yield comment + retry directive immediately so headers flush and
        # client gets its jittered reconnect interval before the first real event.
        # retry: field spreads reconnects over 2–8s window (PITFALLS 36 prevention).
        retry_ms = random.randint(2000, 8000)
        yield ServerSentEvent(comment="connected", retry=retry_ms)
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(q.get(), timeout=1.0)
                yield ServerSentEvent(
                    event=event.name,
                    data=json.dumps(event.data),
                )
            except TimeoutError:
                continue
    finally:
        bus.unsubscribe(q)
```

**`sse-starlette` `ServerSentEvent` constructor signature** — `retry` is an `int | None` field (milliseconds). Passing it on a comment-only event is valid; the browser's `EventSource` processes the `retry:` field independently of the event data.

**No change to `EventSourceResponse`** — `ping=15` stays as-is (Pitfall 8). The `retry:` jitter is per-connection (set in the first yielded frame), while `ping` is the keepalive interval — orthogonal concerns.

**No new imports beyond `random`** — `asyncio`, `json`, `ServerSentEvent` are already imported.

---

## Shared Patterns

### Stale-closure-safe store reads
**Source:** `frontend/src/routes/kiosk/KioskView.tsx` lines 197, 281–290, 307–310, 316, 322, 343, 364–365, 381, 401–402, 426, 439
**Apply to:** All new SSE handler code added in KioskView.tsx Phase 9 changes

```ts
// Always read from .getState() inside event handlers and effects
// that reference store values — NEVER from the outer reactive destructure.
useGruvaxStore.getState().setSseConnected(true)
useGruvaxStore.getState().connectivity.sseConnected  // read
useSessionStore.getState().boundProfileId             // cross-store read
```

### Nordic Grid banner structure
**Source:** `frontend/src/routes/kiosk/StalenessBar.tsx` (full file) + `StalenessBar.css` (full file)
**Apply to:** `OfflineBanner.tsx` + `OfflineBanner.css`

Token contract: `background`, `color`, `font-family`, `font-size`, `font-weight`, `padding`, `gap` values must all reference `var(--gruvax-*)` tokens. No hardcoded hex. The keyframe `staleness-bar-enter` from `StalenessBar.css` is already in global scope (imported via `KioskView.tsx`) and can be reused by `OfflineBanner.css` without redefinition — or define a local `offline-banner-enter` alias if co-import order is uncertain.

### No `es.close()` in event handlers
**Source:** `frontend/src/routes/kiosk/KioskView.tsx` lines 449–452 (the cleanup return)
**Apply to:** All new SSE event listener additions in Phase 9

```ts
// The ONLY es.close() call is in the effect cleanup return:
return () => {
  es.close()
}
// NEVER call es.close() inside onopen / onerror / event listeners (Pitfall 4)
```

### Auto-dismiss toast pattern
**Source:** `frontend/src/components/SyncToast.tsx` lines 28–41
**Apply to:** "Back online" toast usage in `KioskView.tsx`

```tsx
// Two-timer pattern: exit animation starts 150ms before dismissal
const exitTimer = setTimeout(() => setIsExiting(true), AUTO_DISMISS_MS - 150)
const dismissTimer = setTimeout(() => onDismiss(), AUTO_DISMISS_MS)
// Both cleared in useEffect cleanup
```

### Design token consumption — urgent/reversed palette
**Source:** `design/gruvax-design-tokens.css`
**Apply to:** `OfflineBanner.css`

| Use case | Token | Value |
|---|---|---|
| Offline banner background (urgent, reversed) | `--gruvax-blue` | #0051A2 |
| Offline banner text (on blue-ground) | `--gruvax-white` | #FFFFFF |
| Staleness banner background (informational) | `--gruvax-yellow` | #FFDA00 |
| Staleness banner text | `--gruvax-blue-darker` | #002855 |
| "Back online" toast background | `--gruvax-success` | #1A7A4A |
| Z-index (toast above all) | `--gruvax-z-admin` | 50 |

---

## No Analog Found

None. All files are extensions of existing components/routes/stores with clear analogs in the codebase.

---

## Metadata

**Analog search scope:** `frontend/src/routes/kiosk/`, `frontend/src/components/`, `frontend/src/state/`, `frontend/src/App.tsx`, `src/gruvax/api/events.py`, `design/gruvax-design-tokens.css`
**Files scanned:** 8 source files + 3 CSS files + design tokens
**Pattern extraction date:** 2026-06-01

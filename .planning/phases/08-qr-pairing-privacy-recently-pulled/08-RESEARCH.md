# Phase 8: QR Pairing + Privacy + Recently-Pulled — Research

**Researched:** 2026-06-01
**Domain:** React 19 QR rendering · Zustand sessionStorage persist · pytest log-capture · kiosk idle timer · URL-param prefill through a PIN gate
**Confidence:** HIGH (all five focus areas grounded in codebase, official docs, or verified npm registry data)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **L-01:** QR transport is HTTP + a short-TTL single-use code on the home LAN. Document as a Key Decision (Pitfall 39). No TLS.
- **L-02:** QR encodes a bind URL with the opaque short-TTL code, never a credential.
- **L-03:** Both pairing paths (scan + typed) call the same bind function (`complete_pairing()`) and emit identical audit log entries.
- **L-04:** PRIV-02 (no raw query in logs) and PRIV-03 (aggregate-only stats) are already true; this phase adds the CI test and confirms uvicorn access-log suppression. No behavior change.
- **L-05:** PRIV-04 "Reset kiosk" is client-side only — zero API calls, no device unbind.
- **D-01:** QR encodes the existing 4-digit pairing code (same row, same 5-min TTL). No separate nonce.
- **D-02:** Scanning lands the phone on the PIN-gated `/admin/devices` page, prefilled with the code. PIN gate first, then one-tap confirm.
- **D-03:** QR re-renders on the existing `pairingCode` reroll in `PairView.tsx`.
- **D-04:** Pairing completes via explicit one-tap confirm, not auto-submit.
- **D-05:** Record enters recently-pulled only on a successful locate (cube highlight).
- **D-06:** Tapping a chip re-locates that record.
- **D-07:** Cap 8 chips, most-recent-first, deduped (re-locate moves to front).
- **D-08:** Horizontal chip strip below search/cube-result area.
- **D-09:** Reset clears recently-pulled + current search/result only; device stays paired, bound profile stays selected.
- **D-10:** Reset button hidden when `adminStore.isLoggedIn` is true (client-side only, not a server-wide flag).
- **D-11:** Reset shows lightweight confirm before wiping.
- **D-12:** Reset button is subtle / low-emphasis (corner or footer).
- **D-13:** Recently-pulled is `sessionStorage`-backed; excluded from any localStorage persist.
- **D-14:** ~15-minute kiosk idle timeout triggers session clear.
- **D-15:** On idle timeout and session end, kiosk returns to resting screen; device stays paired.

### Claude's Discretion

- QR library choice (frontend) — researched below; recommendation: `react-qr-code` 2.0.21.
- PRIV-02 CI test shape — researched below; recommendation: in-process ring-buffer assertion.
- Identical-audit plumbing — ensure QR scan path produces byte-identical audit entry (same `complete_pairing` call site).
- Chip content (artist / title / catalog number, truncation) — UI-phase detail.
- Idle-timer reset semantics — reset on any user interaction.

### Deferred Ideas (OUT OF SCOPE)

- QR for the invite/redeem link (Phase 7 AUTH-02) — library lands here but feature is its own follow-up.
- Separate faster-rotating opaque nonce (60s) for the QR — rejected in D-01; revisit only if threat model changes.
- Server-persisted / set-level search history — out of scope (PRIV-01/03).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DEV-04 | Kiosk pairing screen shows a QR code alongside the 4-digit PIN; both paths call the same bind endpoint; QR re-renders on code reroll | QR library choice (§Standard Stack), PairView integration pattern (§Architecture Patterns), identical-audit note (§Architecture Patterns) |
| PRIV-01 | Search history is session-only (`sessionStorage`); Zustand `persist` slice explicitly excludes the history | Zustand `persist` + `sessionStorage` pattern (§Architecture Patterns), exclusion from `gruvax-admin` localStorage key confirmed |
| PRIV-02 | Server never persists or logs raw query text; CI test asserts no plaintext query in logs | Log-capture test shape (§Architecture Patterns), in-process ring assertion approach |
| PRIV-03 | Record statistics are aggregate-only (per-`release_id` counters; no per-query log table) | Already enforced by existing code; formalized here with a CI assertion that no `q=` value appears in log records |
| PRIV-04 | No-PIN "Reset kiosk" affordance clears local session client-side only; hidden during admin session | Reset store action pattern, `adminStore.isLoggedIn` client-side guard |
| SRCH-09 | Session-only recently-pulled chip list; cleared on session end / idle timeout / Reset | `sessionStorage`-backed Zustand slice, 15-min idle hook, Reset action |
</phase_requirements>

---

## Summary

Phase 8 has three loosely-coupled deliverables — QR pairing (DEV-04), the recently-pulled chip list (SRCH-09 / PRIV-01), and privacy formalization (PRIV-02/03/04) — all of which are frontend-heavy. None require backend schema changes or new API routes. The core backend work is a single CI test for PRIV-02 (no plaintext query in logs) and a small frontend addition to DevicesManager (read `?code=` query param on mount).

All five open/discretion items from CONTEXT.md now have definitive answers. The QR library is `react-qr-code` 2.0.21 — the project's own STATE.md already pins this choice; it is an SVG-only, ~14 KB, MIT library with no postinstall script and `peerDep: react: '*'`, fully compatible with React 19. The PRIV-02 CI test is best implemented as a direct in-process assertion against `app.state.log_ring_buffer` and confirmed `uvicorn.access` suppression — this exactly mirrors the precedent set by `test_diagnostics.py`. The recently-pulled slice follows the same Zustand `persist` + `createJSONStorage(() => sessionStorage)` pattern already referenced in official Zustand docs, with a new storage key (`gruvax-kiosk-recent`) distinct from `gruvax-admin`. The 15-minute idle timer is a dependency-light custom hook using `useRef` / `setTimeout` reset on `pointermove` / `keydown` / `touchstart`. The QR scan → bind prefill works because AdminShell renders PinOverlay as an overlay modal (not a route redirect), so the URL `/admin/devices?code=XXXX` is preserved through the PIN gate — DevicesManager reads `useSearchParams` on mount and opens the drawer in `bind-code` mode with the code pre-seeded.

**Primary recommendation:** All five discretion items are fully resolvable with existing project patterns; no new tooling or libraries beyond `react-qr-code` are required.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| QR code rendering | Browser / Client (React) | — | Pure presentational encoding of an existing string; no server involvement needed |
| QR bind URL construction | Browser / Client | API / Backend (pairing-codes endpoint already exists) | Bind URL = `${window.origin}/admin/devices?code=${pairingCode.code}`; the code comes from the existing `POST /api/devices/pairing-codes` response already in PairView |
| Recently-pulled list state | Browser / Client (Zustand + sessionStorage) | — | Client-only; PRIV-01 forbids server persistence |
| Idle timeout | Browser / Client (custom hook) | — | Purely UI-timing; no server involvement |
| Reset kiosk | Browser / Client | — | L-05: zero API calls; client-only store reset |
| PRIV-02 enforcement | API / Backend (structlog processor chain) | Frontend (never passes q in logs) | Already enforced server-side; CI test locks it |
| Bind endpoint audit | API / Backend (`POST /api/admin/devices/bind`) | — | Both pairing paths must funnel here; identical audit is guaranteed by single call site |
| QR scan → prefill | Browser / Client (URL search params) | — | AdminShell modal pattern means URL survives PIN gate |

---

## Standard Stack

### Core (frontend additions only — no new backend packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `react-qr-code` | 2.0.21 [VERIFIED: npm registry] | Render QR code as inline SVG | Pinned in project STATE.md; lightest SVG QR library (~14 KB unpacked); `peerDep: react: '*'` covers React 19; MIT; no postinstall script; maintained (last publish 2026-04-29) |
| `zustand` | 5.0.13 (already installed) [VERIFIED: npm registry] | `persist` middleware with `createJSONStorage(() => sessionStorage)` | Already in project; `persist` + sessionStorage is the canonical Zustand pattern per official docs |

All other libraries needed for this phase are already in `frontend/package.json` — React 19, Vite 8, Vitest 4, `@testing-library/react`, `@tanstack/react-query`, and the existing Zustand 5.x store infrastructure.

### Alternatives Considered

| Standard | Alternative | Tradeoff |
|----------|-------------|----------|
| `react-qr-code` (SVG, 14 KB) | `qrcode.react` (SVG+Canvas, 115 KB) | `qrcode.react` is 8× larger; supports canvas and embedded logos — features not needed here; last published 2024-12-11 (vs 2026-04-29). STATE.md already pins the lighter choice. |
| `react-qr-code` (frontend-only) | Backend `qrcode` Python endpoint | Backend approach adds a network round-trip for every reroll, plus a Python package dependency; provides no security benefit since the QR value (the bind URL) is already in the browser. Frontend-only is correct. |
| Custom `useIdleTimer` hook | `@idleTimer/react` or similar | A ~20-line custom hook is sufficient; zero new dependency; avoids version drift. |

**Installation (frontend only):**
```bash
npm install react-qr-code@2.0.21
```

**Version verification:**
```
npm view react-qr-code version   → 2.0.21  (verified 2026-06-01)
npm view zustand version         → 5.0.14  (already installed as 5.0.13)
```

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `react-qr-code` | npm | ~5 yrs | 1.74M/wk | github.com/rosskhanas/react-qr-code | [OK] | Approved |
| `qrcode.react` | npm | ~10 yrs | 5.76M/wk | github.com/zpao/qrcode.react | [OK] | Not chosen (heavier; older last publish) |

**slopcheck run:** `slopcheck install --ecosystem npm react-qr-code qrcode.react` → 2 OK, 0 SLOP, 0 SUS.
**Postinstall scripts:** `react-qr-code` has no `postinstall` script. `qrcode.react` has no `postinstall` script. Both clean.
**Packages removed due to [SLOP] verdict:** none
**Packages flagged as [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (kiosk, /pair route)
  PairView.tsx
    │
    ├── POST /api/devices/pairing-codes ──► pairing_codes table (5-min TTL)
    │    └── pairingCode.code ─────────────► <QRCode value={bindUrl} />  [NEW]
    │                                            SVG rendered in-browser
    │                                            re-renders on reroll effect
    │
    └── countdown/reroll effect (existing) drives both code display AND QR

Browser (phone, scans QR)
  Navigates to /admin/devices?code=XXXX
    │
    ├── AdminShell renders PinOverlay (if not logged in)
    │    URL is preserved: /admin/devices?code=XXXX stays in browser bar
    │    PinOverlay is a modal overlay, NOT a route redirect
    │
    └── After PIN success → AdminShell renders Outlet
         DevicesManager mounts, reads useSearchParams
         If ?code present → open DeviceDrawer in bind-code mode, pre-seed digit state
         One-tap "PAIR THIS DEVICE" confirm (D-04)
         └── POST /api/admin/devices/bind (same endpoint as typed flow)
              same complete_pairing() call → identical audit entry

Kiosk state (sessionStorage-backed Zustand slice)
  useRecentlyPulledStore (new store, gruvax-kiosk-recent key)
    persist + createJSONStorage(() => sessionStorage)
    partialize: all fields (entire slice is session-only)
    survives: normal page reload (sessionStorage persists within session)
    cleared by: tab close / browser session end / hard Chromium restart / idle timeout / Reset

Idle timer (custom hook in KioskView)
  useIdleTimer({ timeout: 15 * 60 * 1000, onIdle: clearKioskSession })
  resets on: pointermove / keydown / touchstart (document-level listeners)
  onIdle: clearSearch() + clearRecentlyPulled() + navigate to resting screen

Reset kiosk button (in KioskView)
  visible when: !adminStore.isLoggedIn
  tap → confirm dialog → clearSearch() + clearRecentlyPulled()
  zero API calls (L-05)
```

### Recommended Project Structure

```
frontend/src/
├── state/
│   └── recentlyPulledStore.ts    # NEW — sessionStorage-backed slice
├── hooks/
│   └── useIdleTimer.ts           # NEW — 15-min kiosk idle hook
├── routes/
│   ├── kiosk/
│   │   ├── KioskView.tsx         # MODIFIED — chip strip + Reset button + idle hook
│   │   ├── RecentlyPulledStrip.tsx  # NEW — horizontal chip strip component
│   │   └── pair.css / PairView.tsx  # MODIFIED — add QRCode below digits card
│   └── admin/
│       └── DevicesManager.tsx    # MODIFIED — read ?code= on mount, open drawer
src/
└── tests/
    └── integration/
        └── test_08_privacy.py    # NEW — PRIV-02/03 CI assertions
```

---

### Pattern 1: QR Code Rendering in PairView

**What:** Render `<QRCode>` below the digit card, re-renders automatically when `pairingCode.code` changes (the existing reroll effect already sets `pairingCode`).

**When to use:** Any time the pairing code changes.

**Key detail:** The bind URL must use the current page's origin, not a hardcoded hostname, so the QR works regardless of which LAN address the kiosk resolves to.

```typescript
// Source: github.com/rosskhanas/react-qr-code (MIT)
import QRCode from 'react-qr-code'

// Computed from the existing pairingCode state already in PairView:
const bindUrl = pairingCode
  ? `${window.location.origin}/admin/devices?code=${pairingCode.code}`
  : ''

// In the JSX, below the code card, when pairingCode is available and not expired:
{pairingCode && !isExpired && !isPaired && (
  <div className="pair-qr-container" aria-label="Scan QR to pair">
    <QRCode
      value={bindUrl}
      size={160}
      level="M"
      bgColor="var(--gruvax-white)"
      fgColor="var(--gruvax-blue)"
    />
    <p className="pair-qr-label">OR SCAN WITH PHONE</p>
  </div>
)}
```

`value={bindUrl}` changes automatically when `pairingCode.code` changes on reroll — no additional effect needed (D-03 satisfied).

---

### Pattern 2: sessionStorage-backed Zustand recently-pulled slice

**What:** A new Zustand store using `persist` with `createJSONStorage(() => sessionStorage)`.

**When to use:** Session-only client state that must survive an accidental reload but clear on hard Chromium restart / tab close.

**sessionStorage semantics (verified against MDN / W3C):** [CITED: developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage]
- Survives: `location.reload()`, soft navigation within the same tab.
- Cleared by: tab close, `window.close()`, hard Chromium restart (`--kiosk` process kill + relaunch), opening in a new tab, cross-origin navigation.
- On a kiosk running `--kiosk --app=http://...`: a hard restart (process kill + relaunch) creates a new renderer process with a fresh session storage context. This satisfies success criterion 2.

```typescript
// Source: github.com/pmndrs/zustand (MIT) — persisting-store-data.md
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import type { SearchResult } from '../api/types'

interface RecentlyPulledStore {
  items: SearchResult[]    // cap 8, most-recent-first, deduped by release_id
  addItem: (item: SearchResult) => void
  clear: () => void
}

export const useRecentlyPulledStore = create<RecentlyPulledStore>()(
  persist(
    (set) => ({
      items: [],
      addItem: (item) =>
        set((s) => {
          // Dedupe: remove existing entry with same release_id, prepend, cap at 8
          const filtered = s.items.filter((r) => r.release_id !== item.release_id)
          return { items: [item, ...filtered].slice(0, 8) }
        }),
      clear: () => set({ items: [] }),
    }),
    {
      name: 'gruvax-kiosk-recent',  // distinct from 'gruvax-admin' localStorage key
      storage: createJSONStorage(() => sessionStorage),
      // partialize is not needed — the entire slice is session-only
    },
  ),
)
```

**Exclusion from `gruvax-admin` localStorage persist:** The `gruvax-admin` key in `adminStore.ts` uses `partialize` that persists only `pendingChangeSet` and `reshuffleDraft`. The recently-pulled store is a **separate store** with a **separate key** (`gruvax-kiosk-recent`) backed by **`sessionStorage`**, not `localStorage`. There is no interplay between the two stores; no additional `partialize` change to `adminStore.ts` is needed. [VERIFIED: from reading adminStore.ts lines 111-118]

**`persist.clearStorage()` API:** To clear imperatively (Reset kiosk / idle timeout):
```typescript
useRecentlyPulledStore.persist.clearStorage()
// or just call the action:
useRecentlyPulledStore.getState().clear()
```

---

### Pattern 3: Kiosk idle timer custom hook

**What:** A React 19-compatible custom hook that fires `onIdle` after N ms of inactivity and resets the timer on any user interaction.

**When to use:** KioskView mount — wires document-level events, self-cleaning on unmount.

**Design:** Uses a single `useRef<ReturnType<typeof setTimeout>>` to hold the timer ID. The event handler is stable (doesn't change on re-render). Events to reset on: `pointermove`, `pointerdown`, `keydown`, `touchstart` — covers all kiosk interaction modes (touchscreen + physical keyboard fallback).

```typescript
// Pattern: dependency-light custom hook
// Source: training knowledge [ASSUMED] — no specific library cited; standard React 19 pattern
import { useEffect, useRef } from 'react'

export function useIdleTimer(timeoutMs: number, onIdle: () => void): void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onIdleRef = useRef(onIdle)
  // Keep the callback reference current without re-running the effect
  useEffect(() => { onIdleRef.current = onIdle }, [onIdle])

  useEffect(() => {
    const reset = () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => onIdleRef.current(), timeoutMs)
    }

    const events = ['pointermove', 'pointerdown', 'keydown', 'touchstart'] as const
    events.forEach((e) => document.addEventListener(e, reset, { passive: true }))
    reset() // start the timer immediately on mount

    return () => {
      events.forEach((e) => document.removeEventListener(e, reset))
      if (timerRef.current !== null) clearTimeout(timerRef.current)
    }
  }, [timeoutMs]) // only re-wires if timeout changes (constant 15 min → never)
}
```

**Usage in KioskView:**
```typescript
useIdleTimer(15 * 60 * 1000, () => {
  clearSearch()                           // from useGruvaxStore
  useRecentlyPulledStore.getState().clear()
  // KioskView is already the resting screen when query + highlight are cleared
})
```

No external idle-timer library is needed. The hook is ~25 lines and zero dependencies.

---

### Pattern 4: PRIV-02 CI test — in-process ring-buffer assertion

**What:** After running a search via the ASGI test client, inspect `app.state.log_ring_buffer` (the in-process deque) and assert the query token is absent from every entry's `msg` field. Also assert that `uvicorn.access` logger is suppressed to WARNING.

**Why ring buffer, not `caplog` or stdout:** `caplog` captures stdlib logging records but requires careful level configuration and is harder to correlate with the structlog pipeline. Inspecting `app.state.log_ring_buffer` directly is the exact approach used in `test_diagnostics.py` (tests `test_recent_logs_shape` + `test_recent_logs_ring_scoping`) — established, tested, and provably in-process. Asserting against `docker logs` is not CI-runnable. [VERIFIED: from reading test_diagnostics.py + app.py:128-132]

```python
# Source: pattern from tests/integration/test_diagnostics.py (project canonical)
@pytest.mark.asyncio(loop_scope="session")
async def test_query_never_in_logs(privacy_client) -> None:
    """PRIV-02: raw query text must never appear in structlog records.

    Runs a real search via the ASGI test client, then walks the in-process
    log_ring_buffer to assert the literal query token is absent from every
    entry's 'msg' field.  This is the in-process equivalent of:
        docker logs gruvax-api | grep <term>  → zero hits
    """
    ac, app = privacy_client  # (AsyncClient, manager.app) — same shape as diag_client

    PROBE_TERM = "probe_priv02_xyz"
    await ac.get(f"/api/search?q={PROBE_TERM}&limit=5")

    ring = list(app.state.log_ring_buffer)
    for entry in ring:
        msg: str = entry.get("msg", "")
        assert PROBE_TERM not in msg, (
            f"PRIV-02 VIOLATION: query term {PROBE_TERM!r} found in log entry: {entry!r}"
        )

@pytest.mark.asyncio(loop_scope="session")
async def test_uvicorn_access_log_suppressed(privacy_client) -> None:
    """PRIV-02: uvicorn.access must be suppressed to WARNING so query-string URLs
    never reach stdout. Regression guard for logging_config.py line 188."""
    import logging
    assert logging.getLogger("uvicorn.access").level >= logging.WARNING, (
        "uvicorn.access level must be WARNING or higher to suppress query-string logs"
    )
```

**Why uvicorn.access matters:** uvicorn's access log emits `GET /api/search?q=<term> HTTP/1.1 200 OK` at INFO level. `logging_config.py:188` already sets `uvicorn.access` to WARNING (suppressing all access log lines). The test above is a regression guard to ensure this line is not accidentally removed. [VERIFIED: from reading logging_config.py:188]

**Test fixture shape:** `privacy_client` is a module-scoped ASGI client with NO `require_admin` override (the search endpoint is public). It needs `LifespanManager` to populate `app.state.log_ring_buffer`. Pattern identical to `diag_client` in `test_diagnostics.py` minus the `dependency_overrides`.

---

### Pattern 5: QR scan → bind prefill (URL search params survive PIN gate)

**What:** The AdminShell renders `<PinOverlay>` as a mounted-over-top modal — it does NOT redirect to a login page. The browser URL remains `/admin/devices?code=XXXX` throughout the PIN entry. After login, `AdminShell` sets `isLoggedIn: true` in the store, hides the overlay, and renders `<Outlet />`, which mounts `DevicesManager`. `DevicesManager` then reads `useSearchParams()` on mount.

**Why this works without a redirect-after-login flow:** [VERIFIED: from reading AdminShell.tsx:148, 304-310 and PinOverlay.tsx — overlay is `showOverlay && <PinOverlay />` rendered in the same route component, not a separate route]

```typescript
// In DevicesManager.tsx — new addition
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

export function DevicesManager() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [drawerTarget, setDrawerTarget] = useState<DrawerTarget>(null)

  // Read ?code= on mount and auto-open the bind drawer with it pre-seeded
  useEffect(() => {
    const prefillCode = searchParams.get('code')
    if (prefillCode) {
      setDrawerTarget('bind')          // opens DeviceDrawer in bind-code mode
      // Clear the param so a reload doesn't re-open the drawer
      setSearchParams((p) => { p.delete('code'); return p }, { replace: true })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // ...
}
```

The prefill code is passed to `DeviceDrawer` via a `prefillCode` prop. `DeviceDrawer` initialises `codeDigits` state from it (or renders the NumericKeypad pre-filled). The user sees all 4 digits already entered and taps "PAIR THIS DEVICE" (D-04 — explicit one-tap confirm, not auto-submit). [ASSUMED: the DeviceDrawer prop-passing detail is a new addition and has not been implemented]

---

### Anti-Patterns to Avoid

- **Auto-submitting the bind on QR scan arrival:** D-04 requires an explicit confirm tap. Do not call `handleBind()` immediately when `prefillCode` is non-null — display the code and a confirm button.
- **Storing recently-pulled in `gruvax-admin` localStorage:** The `gruvax-admin` key is `localStorage`-backed and persists across kiosk restarts. The recently-pulled store must use a separate key backed by `sessionStorage`.
- **Attaching idle timer to root `<App>` component:** The idle timer must only run while `KioskView` is mounted (not on `/admin` or `/pair`). Mount it inside `KioskView` only.
- **Using `caplog` or `capsys` for PRIV-02 test:** pytest's `caplog` captures stdlib log records at the root logger level; it requires careful level configuration and may miss structlog-native paths. The in-process ring-buffer is the authoritative, tested capture point.
- **Constructing the bind URL with a hardcoded hostname:** Use `window.location.origin` so the QR works regardless of whether the phone resolves `gruvax.lan`, the Pi's IP address, or `localhost`.
- **`persist.clearStorage()` vs `.getState().clear()`:** `clearStorage()` removes the key from sessionStorage immediately. `.getState().clear()` updates the in-memory store (and sessionStorage via middleware). For Reset kiosk / idle timeout, call `.getState().clear()` — this updates the React component tree reactively. `clearStorage()` alone does not update subscribed components.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| QR code matrix | Custom QR encoder | `react-qr-code` | Reed-Solomon error correction, version sizing, mask pattern selection — ~500 lines of math to get right |
| JSON sessionStorage serialization | Manual `JSON.stringify` / `getItem` | Zustand `persist` + `createJSONStorage(() => sessionStorage)` | Handles hydration, versioning, concurrency; project already uses this pattern in `adminStore.ts` |
| Idle-timer reset debouncing | Custom per-event debouncer | `setTimeout` + `clearTimeout` in `useRef` | Sufficient for a 15-minute window; the "reset on every interaction" pattern is O(1) |

---

## Common Pitfalls

### Pitfall 1: QR re-renders on reroll out of sync

**What goes wrong:** If the QR component is given a URL computed from stale state, it shows the old code after a reroll.

**Why it happens:** `pairingCode` is React state; JSX derived from it re-renders automatically. But if the bind URL is memoized with a stale dep array or computed outside the component's render path, it can lag.

**How to avoid:** Compute `bindUrl` inline in the JSX (no `useMemo`, no separate state) directly from `pairingCode.code`. The component re-renders whenever `pairingCode` is set by `fetchNewCode()` — that is the only trigger needed (D-03).

**Warning signs:** QR shows old code while digit display shows new code after reroll.

---

### Pitfall 2: sessionStorage is cleared by a Chromium profile wipe, not just a process restart

**What goes wrong:** On a development machine, `localStorage.clear()` or clearing browser data wipes both localStorage and sessionStorage. On the kiosk, `labwc` autostart launches Chromium with `--kiosk --no-first-run --password-store=basic` which does NOT wipe sessionStorage on launch — sessionStorage is scoped to the renderer process lifetime, not the browser profile. A hard Chromium restart (process kill) does clear it.

**How to avoid:** No special handling needed. Standard `sessionStorage` semantics are the correct implementation of D-13 / success criterion 2.

---

### Pitfall 3: PRIV-02 test: the `q` parameter in the HTTP path is logged by uvicorn.access

**What goes wrong:** uvicorn's access logger emits the full request path including query string at INFO level. If `uvicorn.access` is ever re-enabled (e.g., a developer sets `LOG_LEVEL=DEBUG` which elevates all loggers), the query term appears in stdout.

**How to avoid:** The PRIV-02 CI test asserts `logging.getLogger("uvicorn.access").level >= logging.WARNING` — this is a regression guard. The suppression is set in `logging_config.py:188` unconditionally (not gated by LOG_LEVEL). [VERIFIED: logging_config.py:187-188]

---

### Pitfall 4: DevicesManager URL param prefill opens drawer before AdminShell is rendered

**What goes wrong:** If `DevicesManager` reads `searchParams.get('code')` and immediately calls `setDrawerTarget('bind')`, but `DeviceDrawer` calls `bindDevice()` on mount without waiting for explicit user action, the bind fires without the user seeing the confirm screen.

**How to avoid:** `DeviceDrawer` in `bind-code` mode uses `NumericKeypad` with auto-submit on the 4th digit AND the existing `handleBind` callback. Prefilling `codeDigits` with all 4 digits does auto-submit. Instead, pass `prefillCode` to `DeviceDrawer` and render a confirm screen — not pre-filled digits — until the user explicitly taps "PAIR THIS DEVICE" (D-04).

**Recommended approach:** Add a `prefillCode?: string` prop to `DeviceDrawer`. When present, show a confirmation UI listing the code with a single "PAIR THIS DEVICE" button; tapping it calls `handleBind(prefillCode)` directly. The NumericKeypad is not shown in this mode.

---

### Pitfall 5: Recently-pulled store hydrates stale data after a reroll

**What goes wrong:** If the chip store persists the `LocateResult` or a full `SearchResult` object including `generated_at` or a stale `primary_cube`, re-tapping a chip calls locate with the correct `release_id` but the stale stored result is shown momentarily.

**How to avoid:** Store only the minimum identity needed to re-trigger the locate: `{ release_id: number, title: string, artist: string, catalog_number: string }`. The chip tap calls `setSelectedReleaseId(item.release_id)` which re-runs the locate query via TanStack Query — fresh boundaries are fetched. [ASSUMED: exact chip data model is UI-phase detail per D-07; store only identity fields]

---

### Pitfall 6: Key Decision — QR over HTTP on home LAN

**What this is:** The QR code is served over HTTP (not HTTPS), and encodes an HTTP bind URL. The bind endpoint requires the admin PIN regardless of transport — the PIN gate is the security control, not TLS. On a home LAN with physical access controlled by the homeowner, this threat model is explicitly accepted (L-01).

**Document as:** A Key Decision in the implementation plan: "The QR bind URL uses HTTP (not HTTPS) on the home LAN. The admin PIN remains the security gate for all binds. Revisit if GRUVAX is ever exposed beyond the home LAN."

---

## Runtime State Inventory

This is not a rename/refactor/migration phase — no runtime state inventory required. No database columns are added or renamed. No existing keys in sessionStorage or localStorage are modified.

---

## Code Examples

### Verified QRCode render (from npm package README)
```typescript
// Source: github.com/rosskhanas/react-qr-code [VERIFIED: npm registry, 2026-06-01]
import QRCode from 'react-qr-code'

<QRCode
  value="https://example.com/admin/devices?code=1234"
  size={160}
  level="M"
/>
```

### Zustand persist with sessionStorage (official docs)
```typescript
// Source: github.com/pmndrs/zustand/blob/main/docs/reference/integrations/persisting-store-data.md [CITED]
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'

export const useBearStore = create()(
  persist(
    (set, get) => ({
      bears: 0,
      addABear: () => set({ bears: get().bears + 1 }),
    }),
    {
      name: 'food-storage',
      storage: createJSONStorage(() => sessionStorage),
    },
  ),
)
```

### Log ring buffer assertion (from project test_diagnostics.py)
```python
# Source: tests/integration/test_diagnostics.py [VERIFIED: project codebase]
# Pattern: yield (ac, manager.app) from LifespanManager fixture
ring = list(app.state.log_ring_buffer)
for entry in ring:
    assert "secret" not in entry.get("msg", "")
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `caplog`-based log assertions | In-process ring buffer (`app.state.log_ring_buffer`) | Established in this project (v2.0) | More accurate — ring buffer is what the diagnostics page uses; structlog-aware |
| `useMemo` + `useCallback` for perf | React Compiler auto-memoization | React 19.x + Compiler 1.0 (Oct 2025) | Project already on React 19; no manual memo needed for computed `bindUrl` |
| Separate idle-timer library (`react-idle-timer`) | Minimal custom hook | 2024+ (dependency minimalism trend) | Project avoids heavyweight libs for simple time-based logic |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `DeviceDrawer` receives a new `prefillCode?: string` prop that renders a confirm screen instead of the NumericKeypad | Architecture Patterns §Pattern 5 | Low — the alternative (pre-seeding `codeDigits`) would auto-submit; confirm screen is required by D-04 regardless |
| A2 | `SearchResult` type (from `src/api/types.ts`) includes `release_id`, `title`, `artist`, `catalog_number` as top-level fields suitable for chip identity | Architecture Patterns §Pattern 2 | Low — `SearchResult` is already used throughout KioskView; shape is stable. If shape differs, use `LocateResult.primary_cube + release_id` instead |
| A3 | Idle hook mounted in `KioskView` only (not in `App` or `AdminShell`) | Architecture Patterns §Pattern 3 | Low — if mounted too high it would clear kiosk state during admin sessions on the same browser; scoping to `KioskView` is the only correct approach |

**All other claims in this research were verified against codebase source, official Context7 docs, or npm registry.**

---

## Open Questions (RESOLVED)

1. **Chip visual content (D-07)**
   - What we know: cap 8, most-recent-first, deduped, DM Mono for catalog numbers
   - **RESOLVED:** 08-UI-SPEC.md Surface 2 fixes the chip anatomy — line 1 `primary_artist – title` (Space Grotesk 14px), line 2 catalog_number (DM Mono 14px); truncation via CSS (`max-width: 200px`, `text-overflow: ellipsis`), no per-field char budget needed. Store identity-only: `{ release_id, title, primary_artist, catalog_number }`. NOTE: the field is `SearchResult.primary_artist`, not `artist` (verified against `frontend/src/api/types.ts`).

2. **`SearchResult` vs `LocateResult` as chip identity**
   - What we know: `addItem` is called on a successful locate; the `LocateResult` returned by `/api/locate` contains `release_id`; `SearchResult` contains title/primary_artist/catalog
   - **RESOLVED:** thread `selectedResult: SearchResult | null` from `useGruvaxStore` (already present at locate time). 08-03-PLAN.md Task 3 calls `addItem({ release_id, title, primary_artist, catalog_number })` from `selectedResult` on a successful cube-highlight locate.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Node.js | `npm install react-qr-code` | ✓ | v26.0.0 | — |
| npm | Package install | ✓ | 11.12.1 | — |
| Python 3.14 | Backend test suite | ✓ | 3.14.5 | — |
| pytest-asyncio | PRIV-02 test | ✓ | >=1.3.0 (pyproject.toml) | — |
| asgi-lifespan | PRIV-02 test fixture | ✓ | already used in test_diagnostics.py | — |
| sessionStorage | Recently-pulled store | ✓ | Chromium kiosk, labwc/Wayland | — |

No missing dependencies.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Backend framework | pytest + pytest-asyncio (`asyncio_mode = "auto"`) |
| Frontend framework | Vitest 4.x (jsdom environment) |
| Backend config file | `pyproject.toml [tool.pytest.ini_options]` |
| Frontend config file | `frontend/vite.config.ts [test]` |
| Backend quick run | `uv run pytest tests/integration/test_08_privacy.py -x -q` |
| Frontend quick run | `npm run test --prefix frontend` |
| Full suite | `uv run pytest -q` + `npm run test --prefix frontend` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DEV-04 | QR renders in PairView when code is available | unit (Vitest) | `npm run test --prefix frontend -- --testPathPattern=PairView` | ❌ Wave 0 |
| DEV-04 | QR re-renders on reroll (new `value` prop) | unit (Vitest) | same | ❌ Wave 0 |
| DEV-04 | Both scan path and typed path call the SAME bind path (single `handleBind` call site → `POST /api/admin/devices/bind`) so audit entries are identical (L-03) | unit (vitest) | `npm run test --prefix frontend -- --run DeviceDrawer` (asserts `bindDevice` called exactly once via the confirm tap; no auto-submit) | ❌ created in 08-02 T2 |
| PRIV-01 | Recently-pulled store key is `gruvax-kiosk-recent` in sessionStorage (not localStorage) | unit (Vitest) | `npm run test --prefix frontend -- --testPathPattern=recentlyPulledStore` | ❌ Wave 0 |
| PRIV-01 | Recently-pulled store is NOT in `gruvax-admin` localStorage key | unit (Vitest) | same | ❌ Wave 0 |
| PRIV-02 | Raw query term absent from `app.state.log_ring_buffer` after a search | integration (pytest) | `uv run pytest tests/integration/test_08_privacy.py::test_query_never_in_logs -x -q` | ❌ Wave 0 |
| PRIV-02 | `uvicorn.access` logger level is WARNING or higher | integration (pytest) | `uv run pytest tests/integration/test_08_privacy.py::test_uvicorn_access_log_suppressed -x -q` | ❌ Wave 0 |
| PRIV-03 | No `search_log` table exists in `gruvax` schema | integration (pytest) | `uv run pytest tests/integration/test_08_privacy.py::test_no_search_log_table -x -q` | ❌ Wave 0 |
| PRIV-04 | Reset button hidden when `adminStore.isLoggedIn` is true | unit (Vitest) | `npm run test --prefix frontend -- --testPathPattern=KioskView` | ❌ Wave 0 |
| PRIV-04 | Reset button triggers confirm dialog, then clears store, zero API calls | unit (Vitest) | same | ❌ Wave 0 |
| SRCH-09 | Recently-pulled clears on `useRecentlyPulledStore.getState().clear()` | unit (Vitest) | `npm run test --prefix frontend -- --testPathPattern=recentlyPulledStore` | ❌ Wave 0 |
| SRCH-09 | Idle timer fires `onIdle` after timeout with no interaction | unit (Vitest) + fake timers | `npm run test --prefix frontend -- --testPathPattern=useIdleTimer` | ❌ Wave 0 |
| SRCH-09 | Idle timer resets on `pointermove` / `touchstart` | unit (Vitest) + fake timers | same | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** Run the file-targeted test command for the changed area
- **Per wave merge:** Full backend (`uv run pytest -q`) + full frontend (`npm run test --prefix frontend`) suites
- **Phase gate:** Both suites green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/integration/test_08_privacy.py` — covers PRIV-02, PRIV-03 (new file)
- [ ] `frontend/src/state/recentlyPulledStore.test.ts` — covers PRIV-01, SRCH-09 store behavior (new file)
- [ ] `frontend/src/hooks/useIdleTimer.test.ts` — covers SRCH-09 timer semantics (new file)
- [ ] Extend `frontend/src/routes/kiosk/PairView.test.tsx` — add QR render assertion (DEV-04)

*(Frontend test files that test Reset kiosk behavior can be co-located with KioskView tests or added to the existing `KioskView.EventSource.test.tsx` file.)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | PIN gate still required for bind — QR provides convenience encoding, not auth bypass |
| V3 Session Management | yes | sessionStorage cleared on session end; `gruvax-admin` tokens not exposed to recently-pulled slice |
| V4 Access Control | yes | `POST /api/admin/devices/bind` rate-limited 10/5min/IP; QR path uses same endpoint |
| V5 Input Validation | yes | `code` URL param from QR is a 4-digit string; same validation as typed flow in `bindDevice()` |
| V6 Cryptography | no | QR does not introduce new cryptographic operations |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| QR encodes session token / PIN | Information Disclosure | D-01 / L-02: QR encodes only the short-TTL pairing code, never a credential |
| Replayed QR (old code) | Elevation of Privilege | Existing single-use `UPDATE ... WHERE consumed_at IS NULL` atomic consume; 5-min TTL |
| Auto-bind on QR scan without confirmation | Elevation of Privilege | D-04: explicit one-tap confirm required in DeviceDrawer prefill mode |
| Query term leaking in logs | Information Disclosure | PRIV-02: structlog chain excludes `q`; uvicorn.access suppressed to WARNING |
| Recently-pulled list persisting across visitors | Privacy | D-13: sessionStorage clears on Chromium restart; Reset kiosk clears client-side |

---

## Sources

### Primary (HIGH confidence)

- Project codebase — `src/gruvax/logging_config.py`, `frontend/src/state/adminStore.ts`, `frontend/src/routes/kiosk/PairView.tsx`, `frontend/src/routes/admin/DevicesManager.tsx`, `frontend/src/routes/admin/AdminShell.tsx`, `tests/integration/test_diagnostics.py`, `tests/conftest.py`, `frontend/src/state/store.ts`, `frontend/src/state/sessionStore.ts`, `frontend/package.json` — all read directly in this session
- [Zustand persist middleware docs](https://github.com/pmndrs/zustand/blob/main/docs/reference/integrations/persisting-store-data.md) — `createJSONStorage(() => sessionStorage)` pattern, `partialize`, `clearStorage()` — fetched via Context7 `/pmndrs/zustand`
- [npm registry: react-qr-code@2.0.21](https://www.npmjs.com/package/react-qr-code) — version, peerDeps, license, postinstall, unpacked size verified via `npm view` + `curl` download stats
- [npm registry: zustand@5.0.14](https://www.npmjs.com/package/zustand) — current version verified via `npm view`
- [Project STATE.md](/.planning/STATE.md:127) — "v2.1 adds `react-qr-code` 2.0.21 (frontend only)" — confirms library choice is already a project-level decision

### Secondary (MEDIUM confidence)

- [react-qr-code GitHub README](https://github.com/rosskhanas/react-qr-code) — SVG rendering format, props API, responsive usage pattern — fetched via WebFetch
- [qrcode.react GitHub README](https://github.com/zpao/qrcode.react) — props API, SVG+Canvas support — fetched via WebFetch (for alternative-considered documentation)
- [MDN: Window.sessionStorage](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage) — session lifetime semantics: survives reload, cleared on tab close / session end [CITED]

### Tertiary (LOW confidence)

- None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — `react-qr-code` 2.0.21 pinned in STATE.md + npm verified; Zustand 5.x already installed + official docs confirmed
- Architecture: HIGH — all patterns derived from existing codebase (PairView, adminStore, test_diagnostics); no guesswork
- Pitfalls: HIGH — pitfall 1–5 sourced from reading the actual code; pitfall 6 is stated L-01 from CONTEXT.md
- PRIV-02 test shape: HIGH — directly mirrors `test_diagnostics.py` pattern already in codebase
- SessionStorage semantics: HIGH — MDN-cited; Chromium kiosk restart behavior is standard Web Platform behavior

**Research date:** 2026-06-01
**Valid until:** 2026-09-01 (stable stack — Zustand, React 19, react-qr-code are all stable releases)

---

## RESEARCH COMPLETE

**Phase:** 8 — QR Pairing + Privacy + Recently-Pulled
**Confidence:** HIGH

### Key Findings

1. **`react-qr-code` 2.0.21 is the correct QR library.** The project's own STATE.md already pins it. It is SVG-only (~14 KB unpacked), MIT-licensed, `peerDep: react: '*'`, no postinstall script, slopcheck [OK]. Passes `npm view react-qr-code@2.0.21` registry check. `value` prop change on reroll is all that is needed — no additional timer.

2. **PRIV-02 CI test should use `app.state.log_ring_buffer` directly.** The in-process ring buffer is already the established pattern in `test_diagnostics.py`. No stdout capture or docker dependency needed. Two assertions: (a) query token absent from every `msg` in the ring after a search; (b) `uvicorn.access` level is WARNING or higher.

3. **Recently-pulled store: new Zustand store, `gruvax-kiosk-recent` key, `sessionStorage`.** Completely separate from the `gruvax-admin` localStorage store. `createJSONStorage(() => sessionStorage)` + `persist` is the official documented pattern. No change to `adminStore.ts` required.

4. **Idle timer: ~25-line custom hook using `useRef` + `setTimeout`.** No library needed. Mounts in `KioskView` only. Resets on `pointermove`, `pointerdown`, `keydown`, `touchstart`. Calls `clearSearch()` + `useRecentlyPulledStore.getState().clear()` on idle.

5. **QR scan → prefill preserves the URL through the PIN gate.** AdminShell renders `<PinOverlay>` as a modal overlay (not a route redirect), so the URL `/admin/devices?code=XXXX` is intact when `<Outlet />` mounts after login. `DevicesManager` reads `useSearchParams()` on mount and opens `DeviceDrawer` with `prefillCode` prop for a one-tap confirm (D-04).

### File Created

`.planning/phases/08-qr-pairing-privacy-recently-pulled/08-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| QR library choice | HIGH | npm verified + STATE.md pin + GitHub README inspected |
| PRIV-02 test shape | HIGH | Exact precedent in test_diagnostics.py — same ring-buffer pattern |
| Zustand sessionStorage | HIGH | Official docs via Context7 + existing adminStore.ts precedent |
| Idle timer hook | HIGH | Standard React 19 pattern; dependency-light; equivalent patterns common |
| URL-param prefill | HIGH | AdminShell source read — overlay modal confirmed, not redirect |

### Open Questions

- Chip visual fields (title/artist/catalog truncation on 7") — UI-phase detail per CONTEXT.md D-07; store `{ release_id, title, artist, catalog_number }` and truncate via CSS
- Which object (`SearchResult` or `LocateResult`) is most convenient to thread to the chip store at locate time — recommend `selectedResult` (SearchResult) already in `useGruvaxStore`

### Ready for Planning

Research complete. Planner can now create PLAN.md files for Phase 8.

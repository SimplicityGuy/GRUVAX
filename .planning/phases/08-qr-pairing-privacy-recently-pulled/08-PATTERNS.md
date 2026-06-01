# Phase 8: QR Pairing + Privacy + Recently-Pulled — Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 10 new/modified files
**Analogs found:** 10 / 10

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/routes/kiosk/PairView.tsx` | component (modified) | request-response | `frontend/src/routes/kiosk/PairView.tsx` itself | self (known base) |
| `frontend/src/state/recentlyPulledStore.ts` | store | event-driven | `frontend/src/state/adminStore.ts` | exact — same `persist` middleware, same Zustand shape |
| `frontend/src/hooks/useIdleTimer.ts` | hook | event-driven | `frontend/src/routes/kiosk/PairView.tsx` (useRef+setTimeout countdown) | role-match — same useRef/setInterval teardown idiom |
| `frontend/src/routes/kiosk/RecentlyPulledStrip.tsx` | component (new) | event-driven | `frontend/src/routes/kiosk/SwitchProfileButton.tsx` | role-match — fixed-position kiosk corner UI, store consumer |
| `frontend/src/routes/kiosk/ResetConfirmDialog.tsx` | component (new) | request-response | `frontend/src/routes/kiosk/SwitchProfileConfirm.tsx` | exact — modal scrim + dialog + focus-trap + callbacks |
| `frontend/src/routes/kiosk/KioskView.tsx` | component (modified) | event-driven | `frontend/src/routes/kiosk/KioskView.tsx` itself | self (known base) |
| `frontend/src/routes/admin/DevicesManager.tsx` | component (modified) | request-response | `frontend/src/routes/admin/DevicesManager.tsx` itself | self (known base) |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | component (modified) | request-response | `frontend/src/routes/admin/DeviceDrawer.tsx` itself | self (known base) |
| `tests/integration/test_08_privacy.py` | test | request-response | `tests/integration/test_diagnostics.py` | exact — LifespanManager fixture, ring-buffer assertion pattern |
| `frontend/src/routes/kiosk/pair.css` | style (modified) | — | `frontend/src/routes/kiosk/pair.css` itself | self (known base) |

---

## Pattern Assignments

### `frontend/src/state/recentlyPulledStore.ts` (store, event-driven)

**Analog:** `frontend/src/state/adminStore.ts`

**Imports pattern** (lines 16–18):
```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { ChangeSet, ReshuffleDraft } from '../api/types'
```
For `recentlyPulledStore.ts`, add `createJSONStorage` to the persist import and import `SearchResult` from `../api/types`.

**Core persist pattern** (lines 76–121):
```typescript
export const useAdminStore = create<AdminStore>()(
  persist(
    (set) => ({
      isLoggedIn: false,
      // ... state fields ...
      setAdminLoggedOut: () =>
        set({ isLoggedIn: false, ... }),
    }),
    {
      name: 'gruvax-admin',
      partialize: (state) => ({
        pendingChangeSet: state.pendingChangeSet,
        reshuffleDraft: state.reshuffleDraft,
      }),
    },
  ),
)
```

**Adaptation for `recentlyPulledStore.ts`:** Replace `name: 'gruvax-admin'` with `name: 'gruvax-kiosk-recent'`; replace the `partialize` key with `storage: createJSONStorage(() => sessionStorage)` (no `partialize` needed — the entire slice is session-only). Replace the state shape with `items: SearchResult[]` + `addItem` + `clear` actions. The `addItem` reducer implements dedupe-and-cap-at-8 (filter by `release_id`, prepend, `.slice(0, 8)`).

**Key difference from adminStore:** Use `createJSONStorage(() => sessionStorage)` instead of the default localStorage. Never use `partialize` on this store; the whole slice belongs in sessionStorage.

---

### `frontend/src/hooks/useIdleTimer.ts` (hook, event-driven)

**Analog:** Countdown + interval teardown in `frontend/src/routes/kiosk/PairView.tsx`

**Core ref-and-interval pattern** (PairView.tsx lines 60–62, 140–176):
```typescript
// PairView.tsx — useRef for a timer that must survive re-renders without
// triggering effects; cleared on unmount via the useEffect cleanup return.
const countdownIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
const rerollTriggeredRef = useRef(false)

useEffect(() => {
  // ... setup ...
  countdownIntervalRef.current = setInterval(() => { /* ... */ }, 1000)

  return () => {
    if (countdownIntervalRef.current) {
      clearInterval(countdownIntervalRef.current)
    }
  }
}, [pairingCode?.expires_at, fetchNewCode])
```

**Adaptation for `useIdleTimer.ts`:** Replace `setInterval` with `setTimeout` (fire once, reset on interaction). Keep the `useRef<ReturnType<typeof setTimeout> | null>` pattern for the timer ID. Add a second `useRef` for the `onIdle` callback (to keep the document event listener stable — avoid re-adding listeners on every render). The event list to reset on: `['pointermove', 'pointerdown', 'keydown', 'touchstart']`. Mount only in `KioskView`, not in `App` or `AdminShell`.

**Effect cleanup pattern** (identical shape to PairView):
```typescript
return () => {
  events.forEach((e) => document.removeEventListener(e, reset))
  if (timerRef.current !== null) clearTimeout(timerRef.current)
}
```

---

### `frontend/src/routes/kiosk/RecentlyPulledStrip.tsx` (component, event-driven)

**Analog:** `frontend/src/routes/kiosk/SwitchProfileButton.tsx`

**Imports pattern** (lines 1–8):
```typescript
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { useSessionStore } from '../../state/sessionStore'
import { SwitchProfileConfirm } from './SwitchProfileConfirm'
```

**Core store-consumer + conditional-render pattern** (lines 16–42):
```typescript
export function SwitchProfileButton() {
  const profileCount = useSessionStore((s) => s.profileCount)
  const [showConfirm, setShowConfirm] = useState(false)

  // Only render when condition is met — return null otherwise
  if (profileCount < 2) return null

  return (
    <>
      <button type="button" className="switch-profile-btn" onClick={...}>
        <RefreshCw size={14} aria-hidden="true" />
        <span>SWITCH</span>
      </button>
      {showConfirm && <SwitchProfileConfirm onCancel={...} />}
    </>
  )
}
```

**Adaptation for `RecentlyPulledStrip.tsx`:** Consume `useRecentlyPulledStore` instead of `useSessionStore`. Return null when `items.length === 0`. Render the `.recently-pulled-strip` container with a label row and a `.recently-pulled-strip__chips` row. Each chip is a `<button>` that calls `setSelectedReleaseId(item.release_id)` from `useGruvaxStore`. Use `aria-label` on each chip per the UI-SPEC copywriting contract.

---

### `frontend/src/routes/kiosk/ResetConfirmDialog.tsx` (component, request-response)

**Analog:** `frontend/src/routes/kiosk/SwitchProfileConfirm.tsx`

**Full pattern** (lines 1–124) — this is the closest match. The entire structure is copied:

**Imports pattern** (lines 1–14):
```typescript
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router'
import { unbindProfile } from '../../api/session'
import { useSessionStore } from '../../state/sessionStore'

interface SwitchProfileConfirmProps {
  onCancel: () => void
}
```

**Focus-trap pattern** (lines 27–67):
```typescript
useEffect(() => {
  confirmBtnRef.current?.focus()

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { onCancel(); return }
    if (e.key !== 'Tab') return
    const dialog = dialogRef.current
    if (!dialog) return
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((el) => !el.hasAttribute('disabled'))
    if (focusable.length === 0) return
    const first = focusable[0]
    const last = focusable[focusable.length - 1]
    if (e.shiftKey) {
      if (document.activeElement === first) { e.preventDefault(); last.focus() }
    } else {
      if (document.activeElement === last) { e.preventDefault(); first.focus() }
    }
  }
  document.addEventListener('keydown', handleKeyDown)
  return () => document.removeEventListener('keydown', handleKeyDown)
}, [onCancel])
```

**JSX scrim + modal pattern** (lines 82–124):
```typescript
return (
  <>
    <div className="switch-confirm-scrim" aria-hidden="true" onClick={onCancel} />
    <div
      ref={dialogRef}
      className="switch-confirm-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
    >
      <h2 id={headingId} className="switch-confirm-heading">Switch collection?</h2>
      <p className="switch-confirm-body">You'll be taken to the profile picker.</p>
      <div className="switch-confirm-actions">
        <button ref={confirmBtnRef} type="button" className="... --confirm" onClick={...}>
          SWITCH
        </button>
        <button type="button" className="... --dismiss" onClick={onCancel}>
          STAY HERE
        </button>
      </div>
    </div>
  </>
)
```

**Adaptation for `ResetConfirmDialog.tsx`:**
- Props: `{ onConfirm: () => void; onCancel: () => void }` — no navigation needed (L-05: zero API calls).
- `role="alertdialog"` (not `"dialog"`) — per UI-SPEC accessibility requirement.
- Initial focus on Cancel button (safer default for destructive action) — move `confirmBtnRef` to the Cancel button.
- Replace heading/body copy per the copywriting contract: `Reset kiosk?` / `This clears your recent searches. Your device stays connected.`
- Replace button labels: `Clear and reset` (confirm, destructive styling) / `Keep recent searches` (cancel).
- CSS class prefix: `kiosk-reset-dialog-*` instead of `switch-confirm-*`.
- `onConfirm` callback calls `clearSearch()` + `useRecentlyPulledStore.getState().clear()` — caller (`KioskView`) passes these in.

---

### `frontend/src/routes/kiosk/PairView.tsx` (component modified, request-response)

**Analog:** Self — existing file at `frontend/src/routes/kiosk/PairView.tsx`

**Insertion point for QR block:** After the `.pair-code-card` closing tag (line 301), before the `.pair-status-row` div (line 304). The QR is conditionally mounted: `pairingCode && !isExpired && !isPaired`.

**New import to add** (after line 27):
```typescript
import QRCode from 'react-qr-code'
```

**Bind URL derivation pattern** (inline in JSX — no `useMemo`):
```typescript
// Compute bindUrl inline — re-computed on every render when pairingCode changes.
// Do NOT use useMemo: the React Compiler handles memoization automatically (React 19).
// window.location.origin ensures the URL works for any LAN address.
const bindUrl = pairingCode
  ? `${window.location.origin}/admin/devices?code=${pairingCode.code}`
  : ''
```

**JSX insertion** (after `.pair-code-card`, before `.pair-status-row`):
```typescript
{pairingCode && !isExpired && !isPaired && (
  <div
    className="pair-qr-container"
    aria-label="Scan QR code to pair this device"
  >
    <QRCode
      value={bindUrl}
      size={160}
      level="M"
      bgColor="var(--gruvax-white)"
      fgColor="var(--gruvax-blue)"
      role="img"
      aria-hidden="true"
    />
    <p className="pair-qr-caption">OR SCAN WITH PHONE</p>
  </div>
)}
```

**CSS additions to `pair.css`** (append after existing rules — same token-only pattern as the file):
```css
/* ── QR code container ───────────────────────────────────────────────────── */

.pair-qr-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--gruvax-space-3);
  background: var(--gruvax-white);
  border: 1.5px solid var(--gruvax-border-light);
  border-radius: var(--gruvax-radius-md);
  margin-top: var(--gruvax-space-3);
  margin-bottom: var(--gruvax-space-5);
}

.pair-qr-caption {
  font-family: var(--gruvax-font-display);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: var(--gruvax-tracking-descriptor);
  color: var(--gruvax-text-muted);
  text-transform: uppercase;
  margin: var(--gruvax-space-2) 0 0 0;
  line-height: var(--gruvax-leading-tight);
}
```

---

### `frontend/src/routes/admin/DevicesManager.tsx` (component modified, request-response)

**Analog:** Self — existing file at `frontend/src/routes/admin/DevicesManager.tsx`

**New imports to add** (after line 14):
```typescript
import { useEffect } from 'react'
import { useSearchParams } from 'react-router'
```

**Prefill-from-query-param pattern:** Add inside `DevicesManager()` function body after the existing `useState` declarations:
```typescript
const [searchParams, setSearchParams] = useSearchParams()
const [prefillCode, setPrefillCode] = useState<string | null>(null)

// Read ?code= on mount — auto-open bind drawer with prefill code (DEV-04 / D-02)
useEffect(() => {
  const code = searchParams.get('code')
  if (code) {
    setPrefillCode(code)
    setDrawerTarget('bind')
    // Clear the param so a reload doesn't re-open (replace: true preserves history)
    setSearchParams((p) => { p.delete('code'); return p }, { replace: true })
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [])
```

**Pass `prefillCode` to `DeviceDrawer`:** Add `prefillCode={prefillCode}` prop to the existing `<DeviceDrawer>` JSX element. Clear `prefillCode` when drawer closes (`onClose` callback sets it to null).

---

### `frontend/src/routes/admin/DeviceDrawer.tsx` (component modified, request-response)

**Analog:** Self — existing file at `frontend/src/routes/admin/DeviceDrawer.tsx`

**Existing interface** (lines 51–56):
```typescript
export interface DeviceDrawerProps {
  device?: DeviceRow
  mode?: string
  onClose: () => void
  onActionComplete?: (message: string) => void
}
```

**New prop to add:**
```typescript
export interface DeviceDrawerProps {
  device?: DeviceRow
  mode?: string
  onClose: () => void
  onActionComplete?: (message: string) => void
  prefillCode?: string   // NEW — QR scan path (DEV-04 / D-04)
}
```

**Existing `handleBind` pattern** (lines 119–134) — QR confirm path calls this directly:
```typescript
const handleBind = useCallback(async (code: string) => {
  setSaveError(null)
  setIsSaving(true)
  try {
    const bound = await bindDevice({ code })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
    onActionComplete?.(`Device "${bound.display_name}" paired successfully.`)
    onClose()
  } catch (err: unknown) {
    const anyErr = err as { detail?: { type?: string } }
    setSaveError(mapBindError(anyErr?.detail?.type))
    setCodeDigits([])
  } finally {
    setIsSaving(false)
  }
}, [queryClient, onActionComplete, onClose])
```

**Prefill confirm screen:** When `prefillCode` is truthy AND `drawerMode === 'bind-code'`, render a confirm screen instead of `<NumericKeypad>`. The confirm screen shows the 4-digit code + a "PAIR THIS DEVICE" CTA that calls `handleBind(prefillCode)`. A "Enter a different code" link sets `prefillCode` to undefined/null (controlled by parent) or clears the mode locally. Do NOT auto-call `handleBind` on render (D-04: explicit confirm required). The `mapBindError` function already handles the `code_expired` / `code_not_found` error types that apply to the prefill path.

---

### `tests/integration/test_08_privacy.py` (test, request-response)

**Analog:** `tests/integration/test_diagnostics.py`

**Imports pattern** (lines 19–29 of test_diagnostics.py):
```python
from __future__ import annotations

import logging
from typing import Any

from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio

from gruvax.api.deps import require_admin
from gruvax.app import create_app
```

**`privacy_client` fixture — no admin override needed** (search endpoint is public):
```python
@pytest_asyncio.fixture(scope="module")
async def privacy_client(db_pool):
    """Module-scoped ASGI client for privacy tests (no require_admin override).

    The search endpoint is public — no dependency_overrides needed.
    Uses LifespanManager to populate app.state.log_ring_buffer (identical to
    diag_client in test_diagnostics.py).
    """
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, manager.app
```

**Ring-buffer assertion pattern** (test_diagnostics.py lines 256–295 — `test_recent_logs_shape`):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_recent_logs_shape(diag_client) -> None:
    ac, _app = diag_client
    logging.getLogger("gruvax.test.shape").info("shape regression probe")
    response = await ac.get("/api/admin/diagnostics")
    # ...
    body = response.json()
    recent_logs: list[Any] = body["recent_logs"]
    for entry in recent_logs:
        assert isinstance(entry, dict), ...
        assert set(entry.keys()) == {"ts", "level", "logger", "msg"}, ...
```

**Adaptation for PRIV-02 test:**
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_query_never_in_logs(privacy_client) -> None:
    """PRIV-02: raw query text must never appear in structlog records."""
    ac, app = privacy_client
    PROBE_TERM = "probe_priv02_xyz"
    await ac.get(f"/api/search?q={PROBE_TERM}&limit=5")

    ring = list(app.state.log_ring_buffer)
    for entry in ring:
        msg: str = entry.get("msg", "")
        assert PROBE_TERM not in msg, (
            f"PRIV-02 VIOLATION: query term {PROBE_TERM!r} found in log entry: {entry!r}"
        )
```

**uvicorn access-log suppression test:**
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_uvicorn_access_log_suppressed(privacy_client) -> None:
    """PRIV-02 regression guard: uvicorn.access must be suppressed to WARNING."""
    import logging
    assert logging.getLogger("uvicorn.access").level >= logging.WARNING, (
        "uvicorn.access level must be WARNING or higher to suppress query-string logs"
    )
```

**PRIV-03 no-search-log-table test:**

Do NOT hardcode the schema — the dev DB schema is `gruvax_dev`, not `gruvax` (project
memory). Resolve the active schema the way `test_diagnostics.py` / the integration conftest
do (e.g. `current_schema()` or the search_path the seeded fixtures use), then check
`to_regclass` against that schema:
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_no_search_log_table(privacy_client, db_pool) -> None:
    """PRIV-03: no search_log table exists in the active gruvax schema (aggregate-only stats)."""
    async with db_pool.connection() as conn:
        cur = await conn.execute("SELECT current_schema()")
        schema = (await cur.fetchone())[0]
        cur = await conn.execute("SELECT to_regclass(%s)", (f"{schema}.search_log",))
        result = await cur.fetchone()
    assert result[0] is None, f"{schema}.search_log table must not exist (PRIV-03)"
```
Confirm the exact cursor API (`conn.execute(...).fetchone()` vs `conn.fetchrow(...)`) against
`test_diagnostics.py` before writing — match whatever the existing integration tests use.

**`db_pool` fixture source:** Root `tests/conftest.py` provides the session-scoped `db_pool`; integration `tests/integration/conftest.py` provides the module-scoped `_seeded_profile_collection` autouse. Both are auto-loaded by pytest for `tests/integration/test_08_privacy.py`.

---

### `frontend/src/routes/kiosk/KioskView.tsx` (component modified, event-driven)

**Analog:** Self — existing file. The modification wires in three new capabilities using existing patterns already in the file.

**Existing imports pattern** (lines 1–23) — add to the import block:
```typescript
import { useRecentlyPulledStore } from '../../state/recentlyPulledStore'
import { useAdminStore } from '../../state/adminStore'
import { useIdleTimer } from '../../hooks/useIdleTimer'
import { RecentlyPulledStrip } from './RecentlyPulledStrip'
import { ResetConfirmDialog } from './ResetConfirmDialog'
```

**Pattern for a fixed-position kiosk action button** (SwitchProfileButton.tsx lines 16–42):
```typescript
// Existing pattern: conditional render + store read + confirm dialog
const profileCount = useSessionStore((s) => s.profileCount)
if (profileCount < 2) return null
// ...
<button type="button" className="switch-profile-btn" onClick={() => setShowConfirm(true)}>
```

**Adaptation for Reset button in KioskView:** Read `isLoggedIn` from `useAdminStore`; render the `<button className="kiosk-reset-btn">` only when `!isLoggedIn`. Use `useState` for `showResetConfirm`. Wire `useIdleTimer(15 * 60 * 1000, onIdle)` at the KioskView function body level (not inside a conditional).

**Idle callback shape:**
```typescript
const clearSearch = useGruvaxStore((s) => s.clearSearch)
// ... inside KioskView function body:
useIdleTimer(15 * 60 * 1000, () => {
  clearSearch()
  useRecentlyPulledStore.getState().clear()
  // KioskView stays at '/' — the search/cube clearing produces the resting screen
})
```

**JSX insertion points:**
- `<RecentlyPulledStrip />` — inside `.kiosk-content`, after the `.shelf-area` block and before closing the content div.
- `<button className="kiosk-reset-btn">` — inside `.kiosk-page`, position fixed (CSS handles placement).
- `{showResetConfirm && <ResetConfirmDialog onConfirm={handleReset} onCancel={() => setShowResetConfirm(false)} />}` — sibling of the button.

---

## Shared Patterns

### Zustand `persist` middleware
**Source:** `frontend/src/state/adminStore.ts` (lines 76–121)
**Apply to:** `recentlyPulledStore.ts`
```typescript
// All persisted stores use this exact shape:
export const useXxxStore = create<XxxStore>()(
  persist(
    (set) => ({ /* state + actions */ }),
    {
      name: 'gruvax-xxx-key',
      // Either: partialize (for localStorage partial persist)
      // Or: storage: createJSONStorage(() => sessionStorage) (for session-only)
    },
  ),
)
```

### CSS token-only rule
**Source:** `frontend/src/routes/kiosk/pair.css` (line 1–9 comment + all rules)
**Apply to:** All CSS additions in `pair.css` and `kiosk.css`
- Every color, size, radius, and transition value must reference a `var(--gruvax-*)` token.
- Never hardcode hex values anywhere in CSS.
- Pattern: `background: var(--gruvax-white)`, `border: 1.5px solid var(--gruvax-border-light)`, `border-radius: var(--gruvax-radius-md)`, `transition: background var(--gruvax-duration-fast) var(--gruvax-ease-standard)`.

### `role="dialog"` + focus trap
**Source:** `frontend/src/routes/kiosk/SwitchProfileConfirm.tsx` (lines 27–67)
**Apply to:** `ResetConfirmDialog.tsx`
- Copy the `handleKeyDown` focus-trap pattern verbatim; change `role="dialog"` to `role="alertdialog"` for the Reset confirm (destructive action).
- Initial focus on the Cancel button (safer default; set `ref` on Cancel button and call `.focus()` in the first `useEffect`).
- Always use `aria-labelledby` pointing to the dialog heading ID.

### `LifespanManager` + ASGI test client fixture
**Source:** `tests/integration/test_diagnostics.py` (lines 40–59)
**Apply to:** `tests/integration/test_08_privacy.py`
```python
@pytest_asyncio.fixture(scope="module")
async def diag_client(db_pool):
    app = create_app()
    app.dependency_overrides[require_admin] = _admin_stub
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, manager.app
    app.dependency_overrides.clear()
```
For `privacy_client`, omit the `dependency_overrides` (search is public). The `yield ac, manager.app` tuple is the canonical form; tests destructure as `ac, app = privacy_client`.

### Vitest fake-timer test shape
**Source:** `frontend/src/routes/kiosk/PairView.test.tsx` (lines 70–80)
**Apply to:** `frontend/src/hooks/useIdleTimer.test.ts` and `frontend/src/routes/kiosk/KioskView.tsx` idle tests
```typescript
beforeEach(() => {
  vi.useFakeTimers({ now: FAKE_NOW_MS, shouldAdvanceTime: false })
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})
// Drive timers with:
await vi.advanceTimersByTimeAsync(15 * 60 * 1000 + 1000)
```

### React component test wrapper
**Source:** `frontend/src/routes/kiosk/PairView.test.tsx` (lines 31–43)
**Apply to:** All new frontend test files
```typescript
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
    },
  })
}
// Wrap renders:
render(
  <QueryClientProvider client={qc}>
    <MemoryRouter>
      <ComponentUnderTest />
    </MemoryRouter>
  </QueryClientProvider>,
)
```

---

## No Analog Found

All files have analogs in the existing codebase. No files require purely external patterns.

---

## Metadata

**Analog search scope:** `frontend/src/routes/kiosk/`, `frontend/src/routes/admin/`, `frontend/src/state/`, `frontend/src/hooks/`, `tests/integration/`
**Files scanned:** 14 source files read directly
**Pattern extraction date:** 2026-06-01

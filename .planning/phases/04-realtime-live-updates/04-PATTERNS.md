# Phase 4: Realtime Live Updates — Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 12 (5 new, 7 modified)
**Analogs found:** 11 / 12

---

## File Classification

| New / Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `src/gruvax/events/__init__.py` | module init | — | `src/gruvax/mqtt/__init__.py` | exact (empty init) |
| `src/gruvax/events/bus.py` | service / singleton | event-driven / pub-sub | `src/gruvax/estimator/boundary_cache.py` | role-match (singleton lifecycle) |
| `src/gruvax/api/events.py` | router | streaming / SSE | `src/gruvax/api/locate.py` | role-match (router + Depends) |
| `src/gruvax/api/admin/editing.py` | router | request-response | `src/gruvax/api/admin/login.py` / `src/gruvax/api/admin/settings.py` | role-match (session-gated POST) |
| `src/gruvax/api/deps.py` (modify) | provider | request-response | itself — add `get_event_bus` mirroring `get_boundary_cache` | exact |
| `src/gruvax/app.py` (modify) | app factory | event-driven | itself — add lifespan step 3d + router import | exact |
| `src/gruvax/api/admin/cubes.py` (modify) | router | CRUD + event-driven | itself — wire `bus.publish` after `cache.invalidate()` | exact |
| `frontend/src/state/store.ts` (modify) | store slice | event-driven | itself + `src/state/adminStore.ts` | exact |
| `frontend/src/routes/kiosk/KioskView.tsx` (modify) | component | streaming / event-driven | itself — add `useEffect` SSE block | exact |
| `frontend/src/routes/kiosk/Cube.tsx` (modify) | component | request-response | itself — add `shimmerActive` prop | exact |
| `frontend/src/routes/admin/RollbackToast.tsx` (new) | component | event-driven | no existing toast — closest is `PinOverlay.tsx` (modal animation) | partial-match |
| `frontend/src/routes/kiosk/kiosk.css` (modify) | styles | — | itself — add `.cube-shimmer-overlay` | exact |
| `frontend/src/api/adminClient.ts` (modify) | client / mutation | request-response | itself + `DiffPreviewSheet.tsx` (queryClient usage) | exact |
| `tests/unit/test_event_bus.py` (new) | test | event-driven | `tests/unit/test_algorithm.py` | role-match |
| `tests/integration/test_sse.py` (new) | test | streaming | `tests/integration/test_health.py` | role-match |

---

## Pattern Assignments

---

### `src/gruvax/events/__init__.py` (new)

**Analog:** `src/gruvax/mqtt/__init__.py` — empty `__init__.py`; every package in `src/gruvax/` follows this pattern.

Create as an empty file. No imports, no re-exports.

---

### `src/gruvax/events/bus.py` (new — service, event-driven)

**Analog:** `src/gruvax/estimator/boundary_cache.py`

The `BoundaryCache` class is the closest existing singleton service: constructed in `lifespan`, stored on `app.state`, returned via a `deps.py` provider, and holds in-process mutable state. Mirror its class structure and docstring style.

**Module-level docstring pattern** (from `boundary_cache.py` lines 1–9):
```python
"""In-process asyncio.Queue event bus for GRUVAX SSE fan-out.

Instantiated once in the FastAPI lifespan (app.state.event_bus).
Any admin handler publishes; GET /api/events subscribers receive.

Phase 4 seam: bus.publish() is called after cache.invalidate() + cache.load()
in put_cube_boundary and bulk_write_cubes (Pitfall A ordering preserved).
"""
```

**Import block** (mirror `boundary_cache.py` lines 11–18 — `__future__`, dataclass, typing):
```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
```

**Class and dataclass pattern** (mirror `BoundaryCache.__init__` / `BoundaryRow` style):
```python
@dataclass
class Event:
    name: str
    data: dict[str, Any]

class EventBus:
    """In-process asyncio.Queue-per-subscriber fan-out.

    Usage::

        bus = EventBus()                       # called once in lifespan
        q = bus.subscribe()                    # called in SSE generator setup
        await bus.publish("boundary_changed", {...})
        bus.unsubscribe(q)                     # in SSE generator finally-block
    """

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[Event]] = set()
```

**Method docstring pattern** (mirror `BoundaryCache.invalidate` at lines 87–99 — `Phase N seam` notation):
```python
    def subscribe(self) -> asyncio.Queue[Event]:
        """Return a per-connection Queue. Call in SSE generator setup.

        Phase 4: called once at the top of the ``stream_events`` generator.
        The queue is unsubscribed in the generator's finally-block on disconnect.
        """
        q: asyncio.Queue[Event] = asyncio.Queue(maxsize=64)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event]) -> None:
        """Remove subscriber queue. Call in the SSE generator finally-block."""
        self._subscribers.discard(q)

    async def publish(self, name: str, data: dict[str, Any]) -> None:
        """Fan-out to all subscribers. Drop on QueueFull (slow client).

        The client will resync on reconnect (D-11). Never raises.
        Rule: call AFTER the DB transaction commits and AFTER cache.load(),
        same as cache.invalidate() (Pitfall A).
        """
        event = Event(name=name, data=data)
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # drop-oldest; client resyncs on reconnect
```

---

### `src/gruvax/api/events.py` (new — router, streaming/SSE)

**Analog:** `src/gruvax/api/locate.py` and `src/gruvax/api/units.py`

These are the closest existing public routers. Mirror the import block, router declaration, async def signature shape, and `Depends()` pattern. The SSE response class is new, but everything around it follows established conventions.

**Import block** (mirror `locate.py` lines 1–37):
```python
"""GET /api/events — Server-Sent Events stream for kiosk live updates.

Emits: boundary_changed, admin_editing, server_hello, server_shutdown.

Critical constraints (RESEARCH.md Pitfall 8 + 10):
  - Depends ONLY on get_event_bus — NEVER on get_pool (D-09, Pitfall 10).
  - Sets X-Accel-Buffering: no and Cache-Control: no-store (Pitfall 8).
  - ping=15 is the sse-starlette default — do NOT increase it (Pitfall 8).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse, ServerSentEvent

from gruvax.api.deps import get_event_bus
from gruvax.events.bus import EventBus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])
```

**Route handler signature** (mirror `locate.py` line 62–69 — `Depends()` in signature, type-annotated return, docstring):
```python
@router.get("/events")
async def stream_events(
    request: Request,
    bus: EventBus = Depends(get_event_bus),  # NO get_pool — Pitfall 10
) -> EventSourceResponse:
    """SSE stream — no DB dependency (D-09, Pitfall 10).

    Each connected client gets its own asyncio.Queue subscriber.
    The generator unsubscribes on disconnect via the finally-block.
    ping=15 flushes nginx/reverse-proxy buffers (Pitfall 8).
    """
```

**Generator + EventSourceResponse** (no analog in codebase — use RESEARCH.md Pattern 2):
```python
    async def generator() -> AsyncIterator[ServerSentEvent]:
        q = bus.subscribe()
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield ServerSentEvent(
                        event=event.name,
                        data=json.dumps(event.data),
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            bus.unsubscribe(q)

    return EventSourceResponse(
        generator(),
        ping=15,
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-store",
        },
    )
```

---

### `src/gruvax/api/admin/editing.py` (new — router, request-response)

**Analog:** `src/gruvax/api/admin/login.py` / `src/gruvax/api/admin/settings.py`

These are the session-gated POST endpoints. Mirror the `require_admin` Depends pattern, Pydantic `BaseModel` for request body, and `JSONResponse` return.

**Import block** (mirror `cubes.py` lines 33–49):
```python
"""POST /api/admin/editing — admin_editing heartbeat (D-01, D-03).

Debounced by the admin client (~300ms). Fans out an admin_editing SSE event
so the kiosk can shimmer the affected cube range while the owner is mid-edit.
Server-side: no DB write, no state stored — pure fan-out via EventBus.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.api.deps import get_event_bus, require_admin
from gruvax.events.bus import EventBus

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-editing"])
```

**Pydantic model** (mirror `cubes.py` `BoundaryEdit` model at lines 54–60):
```python
class EditingPayload(BaseModel):
    """Heartbeat payload from the admin client."""
    cube_ids: list[dict[str, int]]  # [{unit, row, col}]
    editing: bool                    # True = editor open; False = closed/committed
```

**Route handler** (mirror `cubes.py` `put_cube_boundary` signature — `require_admin` as positional dep, `JSONResponse` return):
```python
@router.post("/admin/editing")
async def signal_editing(
    body: EditingPayload,
    bus: EventBus = Depends(get_event_bus),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Fan-out admin_editing event — no DB write, no state stored."""
    await bus.publish("admin_editing", body.model_dump())
    return JSONResponse(content={"ok": True})
```

---

### `src/gruvax/api/deps.py` (modify — add `get_event_bus`)

**Analog:** itself — mirror `get_boundary_cache` (lines 41–59) exactly.

The pattern is: `getattr(request.app.state, "<key>", None)`, None-check raises HTTP 503, type annotation on return, docstring with `Usage::` block.

**New provider to add** (copy the `get_boundary_cache` shape at lines 41–59):
```python
def get_event_bus(request: Request) -> "EventBus":
    """FastAPI dependency: return the app-level EventBus.

    Returns HTTP 503 if the bus is not yet on ``app.state`` — e.g. a request
    that races lifespan startup or arrives during shutdown.

    The SSE endpoint depends ONLY on this — never on ``get_pool`` (D-09, Pitfall 10).

    Usage::

        @router.get("/api/events")
        async def stream_events(bus: EventBus = Depends(get_event_bus)) -> ...:
            ...
    """
    from gruvax.events.bus import EventBus  # local import avoids circular dep

    bus: EventBus | None = getattr(request.app.state, "event_bus", None)
    if bus is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Event bus not ready",
        )
    return bus
```

**Import note:** The `EventBus` type import is placed inside the function body (local import) to avoid a circular import — the same pattern used for `from gruvax.auth.sessions import ...` inside `require_admin` at lines 109–110.

---

### `src/gruvax/app.py` (modify — lifespan step 3d + router registration)

**Analog:** itself — mirror the existing lifespan steps and `create_app()` router registration at lines 76–209.

**Lifespan insertion** (insert after step 3c at line 135, before step 4 at line 138 — mirror the step-3b `CollectionSnapshot` pattern at lines 111–121):
```python
    # ── 3d. Event bus (Phase 4) ──────────────────────────────────────────────
    from gruvax.events.bus import EventBus

    event_bus = EventBus()
    app.state.event_bus = event_bus
    try:
        await event_bus.publish("server_hello", {"version": "0.1.0"})
        logger.info("EventBus ready; server_hello published")
    except Exception as exc:
        logger.error("EventBus server_hello publish failed: %s", exc)
```

**Teardown** (insert before `await pool.close()` at line 144 — mirror `disconnect_mqtt` at line 143):
```python
    # Publish server_shutdown before closing (clients will reconnect)
    try:
        await event_bus.publish("server_shutdown", {})
    except Exception:
        pass  # best-effort; do not block shutdown
```

**Router registration** (insert inside `create_app()` after line 184, before the StaticFiles mount — mirror the existing `include_router` calls at lines 176–179):
```python
    from gruvax.api.events import router as events_router
    app.include_router(events_router, prefix="/api")
```

**Admin editing router** — the `editing` router is included inside `create_admin_router()` in `src/gruvax/api/admin/router.py`, not directly in `create_app()`. Mirror the pattern at `router.py` lines 24–31:
```python
    # In create_admin_router():
    from gruvax.api.admin.editing import router as editing_router
    router.include_router(editing_router)
```

---

### `src/gruvax/api/admin/cubes.py` (modify — wire bus.publish)

**Analog:** itself — the seam is already documented as "Pitfall A" in the file.

**`put_cube_boundary` seam** (after line 322 `await cache.load(pool)`):
```python
    # Phase 4: fan-out boundary_changed AFTER cache reloads (Pitfall A ordering)
    await bus.publish("boundary_changed", {
        "cube_ids": [{"unit": unit_id, "row": row, "col": col}],
        "change_set_id": str(dict(zip(cols_meta, updated, strict=True)).get("change_set_id", "")),
    })
```

**`bulk_write_cubes` seam** (after line 766 `await cache.load(pool)`):
```python
    # Phase 4: fan-out boundary_changed AFTER cache reloads (Pitfall A ordering)
    await bus.publish("boundary_changed", {
        "cube_ids": [{"unit": e.unit_id, "row": e.row, "col": e.col} for e in body.updates],
        "change_set_id": response_body["change_set_id"],
    })
```

**Signature change** (both `put_cube_boundary` at line 210 and `bulk_write_cubes` at line 624 — add `bus` dep after `cache`):
```python
    bus: EventBus = Depends(get_event_bus),
```

**Import addition** (add to existing import at line 42):
```python
from gruvax.api.deps import get_boundary_cache, get_collection_snapshot, get_event_bus, get_pool, require_admin
from gruvax.events.bus import EventBus
```

---

### `frontend/src/state/store.ts` (modify — add connectivity slice)

**Analog:** itself (`store.ts`) + `adminStore.ts`

The existing store at lines 48–92 shows the exact pattern: `create<GruvaxStore>((set) => ({...}))`, interface declarations, setter functions that call `set()`. The `adminStore.ts` shows the slice-isolation rationale.

**Interface additions** (insert into `GruvaxStore` interface after line 46):
```typescript
interface ShimmerCube { unit: number; row: number; col: number }

// Add inside GruvaxStore interface:
connectivity: {
  sseConnected: boolean
  lastSeenAt: number    // Date.now() on last onopen
  bannerVisible: false  // stub for deferred Offline slice (D-10)
}
shimmerCubes: ShimmerCube[]   // cubes showing admin_editing shimmer (D-01)
shimmerExpiresAt: number      // Date.now() + 60_000 — safety TTL (D-03)

setSseConnected: (connected: boolean) => void
setShimmerCubes: (cubes: ShimmerCube[]) => void
clearShimmerCubes: (cubes: ShimmerCube[]) => void
```

**Store initializer additions** (mirror the `setHighlightCube` pattern at lines 59–63 — `set((s) => ...)` for derived state):
```typescript
// Add to create() call (after animationToken: 0 at line 79):
connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
shimmerCubes: [],
shimmerExpiresAt: 0,

setSseConnected: (connected) =>
  set((s) => ({
    connectivity: {
      ...s.connectivity,
      sseConnected: connected,
      lastSeenAt: connected ? Date.now() : s.connectivity.lastSeenAt,
    },
  })),

setShimmerCubes: (cubes) =>
  set({ shimmerCubes: cubes, shimmerExpiresAt: Date.now() + 60_000 }),

clearShimmerCubes: (cubes) =>
  set((s) => {
    const keys = new Set(cubes.map((c) => `${c.unit}-${c.row}-${c.col}`))
    return {
      shimmerCubes: s.shimmerCubes.filter(
        (c) => !keys.has(`${c.unit}-${c.row}-${c.col}`)
      ),
    }
  }),
```

---

### `frontend/src/routes/kiosk/KioskView.tsx` (modify — SSE consumer)

**Analog:** itself — mirror the existing `useEffect` pattern at lines 96–130 and the `useLayoutEffect` at lines 157–257.

**Import addition** (add `useQueryClient` alongside existing imports at line 2):
```typescript
import { useQuery, useQueryClient } from '@tanstack/react-query'
```

**Store destructuring** (add `setSseConnected`, `setShimmerCubes`, `clearShimmerCubes` to the existing destructure at line 28):
```typescript
const { ..., setSseConnected, setShimmerCubes, clearShimmerCubes } = useGruvaxStore()
const queryClient = useQueryClient()   // stable ref — no re-subscription
```

**SSE useEffect block** (insert after the existing `useEffect` blocks, before the `useLayoutEffect` at line 157 — mirror the cleanup return pattern and `useGruvaxStore.getState()` for event handlers):
```typescript
// ── SSE consumer (Phase 4 / RTM-01, ADMN-11) ─────────────────────────────
useEffect(() => {
  const es = new EventSource('/api/events')

  // D-11: invalidate boundary-derived queries on every (re)connect
  const resync = () => {
    void queryClient.invalidateQueries({ queryKey: ['units'] })
    void queryClient.invalidateQueries({ queryKey: ['cubes'] })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    const releaseId = useGruvaxStore.getState().selectedReleaseId
    if (releaseId != null) {
      void queryClient.invalidateQueries({ queryKey: ['locate', releaseId] })
    }
  }

  es.onopen = () => {
    useGruvaxStore.getState().setSseConnected(true)
    resync()  // D-11
  }

  es.onerror = () => {
    useGruvaxStore.getState().setSseConnected(false)
    // Do NOT es.close() here — native EventSource auto-reconnects (RESEARCH Pitfall 4)
  }

  es.addEventListener('boundary_changed', (e) => {
    const { cube_ids, change_set_id } = JSON.parse(e.data) as {
      cube_ids: Array<{unit: number; row: number; col: number}>
      change_set_id: string
    }
    void change_set_id  // referenced for future replay
    cube_ids.forEach(({ unit, row, col }) => {
      void queryClient.invalidateQueries({ queryKey: ['cube', unit, row, col] })
    })
    void queryClient.invalidateQueries({ queryKey: ['cubes'] })
    void queryClient.invalidateQueries({ queryKey: ['units'] })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'history'] })
    // D-05: re-locate if visitor has active selection
    const releaseId = useGruvaxStore.getState().selectedReleaseId
    if (releaseId != null) {
      void queryClient.invalidateQueries({ queryKey: ['locate', releaseId] })
    }
    // D-03: clear shimmer for these cubes on commit
    useGruvaxStore.getState().clearShimmerCubes(cube_ids)
  })

  es.addEventListener('admin_editing', (e) => {
    const { cube_ids, editing } = JSON.parse(e.data) as {
      cube_ids: Array<{unit: number; row: number; col: number}>
      editing: boolean
    }
    if (editing) {
      useGruvaxStore.getState().setShimmerCubes(cube_ids)
    } else {
      useGruvaxStore.getState().clearShimmerCubes(cube_ids)
    }
  })

  es.addEventListener('server_hello', () => {
    resync()
    void queryClient.invalidateQueries({ queryKey: ['admin', 'settings'] })
  })

  es.addEventListener('server_shutdown', () => {
    useGruvaxStore.getState().setSseConnected(false)
  })

  return () => es.close()  // only here — not in onerror (RESEARCH Pitfall 4)
}, [queryClient])
```

**shimmerCubes prop pass-through** (in the JSX at lines 301–313, add `shimmerCubes` to `ShelfGrid` after adding it to the ShelfGrid component interface):
```tsx
const shimmerSet = useMemo<Set<string>>(() => {
  const cubes = useGruvaxStore.getState().shimmerCubes
  return new Set(cubes.map((c) => `${c.unit}-${c.row}-${c.col}`))
}, [/* shimmerCubes from store — read via selector below */])
```

Use a Zustand selector (`useGruvaxStore((s) => s.shimmerCubes)`) for reactive updates to `shimmerSet` during render.

---

### `frontend/src/routes/kiosk/Cube.tsx` (modify — shimmerActive prop)

**Analog:** itself — mirror the `isCompanionBar?: boolean` optional prop pattern at line 26 and the conditional JSX render at line 98.

**Interface addition** (after `onTap` at line 37):
```typescript
  /**
   * When true, renders a .cube-shimmer-overlay for the admin_editing cue (RTM-04 / D-01).
   * Never recolors the cube — the overlay is rgba only (design spec constraint).
   */
  shimmerActive?: boolean
```

**Prop destructuring** (add to the function parameter destructure at line 52):
```typescript
export function Cube({
  ...,
  shimmerActive = false,
}: CubeProps) {
```

**JSX render** (add inside the `.cube` div, after the `FillBar` at line 107, `aria-hidden` per UI-SPEC):
```tsx
      {shimmerActive && <div className="cube-shimmer-overlay" aria-hidden="true" />}
```

---

### `frontend/src/routes/kiosk/kiosk.css` (modify — shimmer overlay)

**Analog:** itself — mirror the `position: absolute` overlay pattern used by `.cube__address` (lines 445–452) and `.sub-cube-bar` (lines 486–501). Mirror the `@keyframes` pattern at lines 75–78 (`search-error-flash`) and lines 408–413 (`led-glow-pulse`). Mirror `will-change: opacity` on `.span-underlay__band` at line 565.

**New CSS block** (add after the `.cube[data-state="lit"] .sub-cube-bar` rule block — after approx. line 527):
```css
/* ── Cube shimmer overlay (Phase 4 / RTM-04) ─────────────────────────────── */

.cube-shimmer-overlay {
  position: absolute;
  inset: 0;
  z-index: 3;                                /* above sub-cube bar (z-2) and fill-bar */
  border-radius: inherit;
  pointer-events: none;
  background: var(--gruvax-yellow-faint);    /* rgba(255, 218, 0, 0.12) */
  border: 1px solid var(--gruvax-yellow-glow); /* rgba(255, 218, 0, 0.35) */
  animation: shimmer-sweep 2000ms var(--gruvax-ease-standard) infinite;
  will-change: opacity;                      /* GPU-composited — Pi frame budget */
}

@keyframes shimmer-sweep {
  0%   { opacity: 0; }
  40%  { opacity: 1; }
  60%  { opacity: 1; }
  100% { opacity: 0; }
}
```

---

### `frontend/src/routes/admin/RollbackToast.tsx` (new — component, event-driven)

**Analog:** `frontend/src/routes/admin/PinOverlay.tsx` (closest match for a fixed-position overlay with CSS animation entry/exit) and `frontend/src/routes/kiosk/kiosk.css` `@keyframes panel-slide-up` (slide animation pattern).

No exact toast analog exists. This is net-new. UI-SPEC Surface 3 provides the full CSS contract. Key pattern notes:

**File structure** (mirror `PinOverlay.tsx` — small, self-contained component with local `useState`):
```typescript
import { useEffect, useState } from 'react'
// No router, no TanStack Query, no Zustand in this component
// Props: message, onDismiss
// Internal: auto-dismiss via useEffect setTimeout (mirror KioskView timer pattern lines 96-110)
```

**Auto-dismiss pattern** (mirror `KioskView.tsx` loading timer at lines 96–110):
```typescript
useEffect(() => {
  const t = setTimeout(onDismiss, 4000)
  return () => clearTimeout(t)
}, [onDismiss])
```

**Icon:** Lucide `AlertTriangle` — already used elsewhere in the admin UI.

**CSS location:** Add `.toast`, `.toast__icon`, `.toast__message`, `.toast__dismiss`, `.toast--exiting`, `@keyframes toast-enter`, `@keyframes toast-exit` to `frontend/src/routes/admin/admin.css`. Mirror the `pin-shake` keyframe pattern in `admin.css` at lines 48–58 and the `--gruvax-z-admin` z-index from line 13.

---

### `frontend/src/api/adminClient.ts` (modify — optimistic mutation support)

**Analog:** itself + `DiffPreviewSheet.tsx` (lines 21–22 and 43: `useQueryClient` usage pattern).

The `adminFetch` wrapper at lines 47–71 is the building block for the mutation function. The `BulkSaveError` class at lines 343–354 shows the error type pattern to mirror for rollback.

**`putCubeBoundary` function** (add alongside existing `adminGetCubeBoundary` at line 174 — mirror the same signature shape):
```typescript
/** PUT /api/admin/cubes/{unit_id}/{row}/{col}/boundary — used for optimistic mutation (RTM-03). */
export async function putCubeBoundary(boundary: CubeBoundaryEdit): Promise<AdminCubeBoundary> {
  const res = await adminFetch(
    `/api/admin/cubes/${boundary.unit_id}/${boundary.row}/${boundary.col}/boundary`,
    { method: 'PUT', body: JSON.stringify(boundary) },
  )
  if (res.status === 400) {
    const body = await res.json() as Record<string, unknown>
    throw new BulkSaveError(400, body.type as string, body.message as string)
  }
  if (res.status === 404) throw new Error('cube_not_found')
  if (!res.ok) throw new Error(`Boundary update failed: ${res.status}`)
  return res.json() as Promise<AdminCubeBoundary>
}
```

**Optimistic mutation** (the `useMutation` call lives in `CubeEditor.tsx` or a new `useOptimisticBoundary` hook — NOT directly in `adminClient.ts`; `adminClient.ts` exports the `putCubeBoundary` function only):
```typescript
// In CubeEditor.tsx (or wherever PUT /boundary is called):
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { putCubeBoundary } from '../../api/adminClient'

const queryClient = useQueryClient()  // mirror DiffPreviewSheet.tsx line 43

const mutation = useMutation({
  mutationFn: putCubeBoundary,

  onMutate: async (newBoundary) => {
    const qk = ['admin', 'cube-boundary', newBoundary.unit_id, newBoundary.row, newBoundary.col]
    await queryClient.cancelQueries({ queryKey: qk })
    const previous = queryClient.getQueryData(qk)
    queryClient.setQueryData(qk, (old: AdminCubeBoundary | undefined) => ({
      ...old, ...newBoundary,
    }))
    return { previous, queryKey: qk }
  },

  onError: (_err, _vars, context) => {
    if (context) queryClient.setQueryData(context.queryKey, context.previous)
    // showToast — mount <RollbackToast> via local useState in the parent component
    // pendingChangeSet NOT cleared here (D-07 — values retained for retry)
  },

  onSettled: (_data, _error, variables) => {
    void queryClient.invalidateQueries({
      queryKey: ['admin', 'cube-boundary', variables.unit_id, variables.row, variables.col],
    })
    // Do NOT invalidate kiosk keys — kiosk updates via boundary_changed SSE (D-08)
  },
})
```

---

### `tests/unit/test_event_bus.py` (new — unit test)

**Analog:** `tests/unit/test_algorithm.py`

Mirror the import block, `@pytest.mark.asyncio` decorator, and `asyncio.wait_for` timeout pattern.

**File structure** (mirror `test_algorithm.py` lines 1–44):
```python
"""Unit tests for EventBus (events/bus.py) — Phase 4 RTM-01, D-09."""

from __future__ import annotations

import asyncio

import pytest

from gruvax.events.bus import EventBus
```

**Test pattern** (mirror `test_algorithm.py` `@pytest.mark.asyncio` tests — no fixtures needed for pure-Python bus):
```python
@pytest.mark.asyncio
async def test_subscribe_receive_publish() -> None:
    bus = EventBus()
    q = bus.subscribe()
    await bus.publish("boundary_changed", {"cube_ids": [], "change_set_id": "x"})
    event = await asyncio.wait_for(q.get(), timeout=1.0)
    assert event.name == "boundary_changed"
    bus.unsubscribe(q)
    assert q not in bus._subscribers

@pytest.mark.asyncio
async def test_slow_subscriber_drops_silently() -> None:
    bus = EventBus()
    q = bus.subscribe()
    for i in range(64):
        await bus.publish("boundary_changed", {"cube_ids": [], "change_set_id": str(i)})
    # 65th publish must not raise even though queue is full
    await bus.publish("boundary_changed", {"cube_ids": [], "change_set_id": "overflow"})
    assert q.full()
```

---

### `tests/integration/test_sse.py` (new — integration test)

**Analog:** `tests/integration/test_health.py`

Mirror the `LifespanManager` + `ASGITransport` + `AsyncClient` fixture pattern at lines 23–42, the `@pytest_asyncio.fixture(scope="module")` fixture, and the `@pytest.mark.asyncio(loop_scope="session")` test decorator.

**Fixture pattern** (copy verbatim from `test_health.py` lines 23–42 — same boilerplate):
```python
@pytest_asyncio.fixture(scope="module")
async def client(db_pool):
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac, app
```

**SSE header test** (simple — no SSE client needed):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_sse_headers(client) -> None:
    ac, _ = client
    async with ac.stream("GET", "/api/events") as resp:
        assert resp.status_code == 200
        assert resp.headers.get("x-accel-buffering") == "no"
        assert resp.headers.get("cache-control") == "no-store"
```

---

## Shared Patterns

### Dependency Provider (applies to `deps.py` additions)

**Source:** `src/gruvax/api/deps.py` lines 41–59 (`get_boundary_cache`)

Every new provider follows: `getattr(request.app.state, "<key>", None)` — None-check — raise HTTP 503 — return typed value. The new `get_event_bus` is an exact structural copy of `get_boundary_cache` with `event_bus` as the key and `EventBus` as the return type.

### Lifespan State Registration (applies to `app.py` modifications)

**Source:** `src/gruvax/app.py` lines 111–135 (step 3b and 3c)

Every new lifespan step follows: `try: ... logger.info(...) except Exception as exc: logger.error(...) [proceed with degraded state]`. The EventBus step (3d) departs slightly — a failed `server_hello` should not leave the bus unregistered; it's still stored on `app.state`.

### Router Import Inside `create_app()` (applies to `events.py` registration)

**Source:** `src/gruvax/app.py` lines 171–178 and `admin/router.py` lines 24–31

All routers are imported inside the function body, not at module level. The `events_router` follows the same deferred-import pattern.

```python
# In create_app() — mirror lines 171-178:
from gruvax.api.events import router as events_router
app.include_router(events_router, prefix="/api")
```

```python
# In create_admin_router() — mirror lines 24-31:
from gruvax.api.admin.editing import router as editing_router
router.include_router(editing_router)
```

### `from __future__ import annotations` + `logger = logging.getLogger(__name__)` (all new backend files)

**Source:** Every existing Python file — `cubes.py` lines 33–47, `locate.py` lines 23–37, `boundary_cache.py` lines 11–17.

All new backend files start with `from __future__ import annotations` and declare a module-level logger.

### Pitfall A Ordering (applies to `cubes.py` modifications)

**Source:** `src/gruvax/api/admin/cubes.py` lines 320–322 and 764–766

The ordering rule is: `conn.commit()` → `cache.invalidate()` → `await cache.load(pool)` → `await bus.publish(...)`. The bus publish goes last, after the cache is fresh, so kiosk refetches land on current data.

### CSS Token-Only (applies to `kiosk.css` and `admin.css` additions)

**Source:** `frontend/src/routes/kiosk/kiosk.css` line 1–4 comment and `admin.css` lines 1–10 comment

No hex values in any CSS file. All new `.cube-shimmer-overlay` and `.toast` rules use `var(--gruvax-*)` tokens exclusively. New tokens required: `--gruvax-yellow-faint` (rgba 255 218 0 / 0.12) and `--gruvax-yellow-glow` (rgba 255 218 0 / 0.35) — verify these exist in `design/gruvax-design-tokens.css` before use; add them if absent.

### Zustand `.getState()` in Event Handlers (applies to `KioskView.tsx` SSE consumer)

**Source:** `frontend/src/state/adminStore.ts` line 43 (`useAdminStore.getState().csrfToken`)

Inside `useEffect` event listener callbacks, use `useGruvaxStore.getState().selectedReleaseId` — not the hook form — to avoid stale closure issues (RESEARCH.md Pitfall 5).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| SSE streaming response body | streaming | event-driven | No existing streaming endpoint in the codebase — `EventSourceResponse` from `sse-starlette` is net-new. Use RESEARCH.md Pattern 2 verbatim. |

---

## Metadata

**Analog search scope:** `src/gruvax/`, `frontend/src/`, `tests/`
**Files read:** 21 source files + 3 planning documents
**Pattern extraction date:** 2026-05-21

---

## PATTERN MAPPING COMPLETE

**Phase:** 04 - Realtime Live Updates
**Files classified:** 15 (including test files)
**Analogs found:** 14 / 15

### Coverage

- Files with exact analog (modify existing): 7
- Files with role-match analog (new, pattern mirrored from similar file): 7
- Files with no analog (net-new pattern): 1 (SSE response body — use RESEARCH.md)

### Key Patterns Identified

1. `get_event_bus` dep provider in `deps.py` is a structural copy of `get_boundary_cache` (lines 41–59) — same getattr/None-check/503 shape, same `Usage::` docstring block.
2. `EventBus` class mirrors `BoundaryCache` lifecycle: constructed in lifespan step 3d, stored on `app.state`, returned via deps provider; docstring uses "Phase N seam" notation.
3. `bus.publish()` inserts at the same post-commit seam as `cache.invalidate()` in `cubes.py` — always after `await cache.load(pool)`, never inside the transaction (Pitfall A).
4. SSE `useEffect` in `KioskView.tsx` mirrors the existing timer-based effects (lines 96–130): cleanup `return () => es.close()`, no `es.close()` in `onerror`, `useGruvaxStore.getState()` inside handlers.
5. `connectivity` slice in `store.ts` mirrors existing slice shape: interface + `set((s) => ...)` for derived state, plain `set({...})` for simple state.
6. All admin routers imported inside function body (deferred import pattern) — `editing_router` goes into `create_admin_router()`, not `create_app()` directly.
7. `RollbackToast` auto-dismiss via `useEffect`/`setTimeout`/cleanup return — exact same pattern as `KioskView.tsx` loading timer at lines 96–110.

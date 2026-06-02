# Phase 10: Shelf Fill-Overview — Pattern Map

**Mapped:** 2026-06-02
**Files analyzed:** 5 (3 modified, 1 new hook, 2 new test files)
**Analogs found:** 5 / 5

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `frontend/src/api/types.ts` (modify `AdminCube`) | model | CRUD | `frontend/src/api/types.ts` `AdminCubeBoundary` (lines 317–326) | exact — same file, sibling interface |
| `frontend/src/routes/admin/LocatorHeader.tsx` | component | request-response | `frontend/src/routes/kiosk/ShelfGrid.tsx` | role-match — same per-cell state + fill prop pattern |
| `frontend/src/routes/admin/ShelfBinList.tsx` (add SSE wiring) | component + hook | event-driven | `frontend/src/routes/kiosk/KioskView.tsx` lines 324–452 | exact — same `EventSource` + `invalidateQueries` idiom |
| `useAdminCubesInvalidation` hook (new, in or alongside `ShelfBinList.tsx`) | hook | event-driven | `frontend/src/routes/kiosk/KioskView.tsx` SSE `useEffect` block | role-match — simpler subset of the same pattern |
| `frontend/src/routes/admin/admin.css` (append after line 1653) | config/styles | — | `frontend/src/routes/admin/admin.css` lines 1608–1653 (existing LocatorHeader block) | exact — same file, same component block |
| `frontend/src/routes/admin/LocatorHeader.test.tsx` (new) | test | — | `frontend/src/routes/kiosk/ShelfGrid.test.tsx` | role-match — same render/class/style assertion idiom |
| `frontend/src/routes/admin/ShelfBinList.sse.test.tsx` (new) | test | event-driven | `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` | exact — same `MockEventSource` + `invalidateQueries` spy pattern |

---

## Pattern Assignments

---

### `frontend/src/api/types.ts` — `AdminCube` interface (lines 299–310)

**Analog:** `AdminCubeBoundary` interface in the same file (`frontend/src/api/types.ts:317-326`) and the cubes.py backend response.

**Current stale state** (lines 299–310):
```typescript
/** One cube row from GET /api/admin/cubes. */
export interface AdminCube {
  unit_id: number
  row: number
  col: number
  first_label: string
  first_catalog: string
  last_label: string       // STALE — not returned by GET /api/admin/cubes
  last_catalog: string     // STALE — not returned by GET /api/admin/cubes
  is_empty: boolean
  fill_level: number       // 0.0–1.0 fraction of nominal capacity
  // record_count MISSING — backend returns it at cubes.py:211
}
```

**Corrected interface pattern** (copy from RESEARCH.md §AdminCube Type Correction):
```typescript
/** One cube row from GET /api/admin/cubes. */
export interface AdminCube {
  unit_id: number
  row: number
  col: number
  first_label: string
  first_catalog: string
  is_empty: boolean
  fill_level: number       // 0.0–1.0+ fraction of nominal capacity
  record_count: number     // raw count for popover display (cubes.py:211)
}
```

**Pre-removal check pattern** — before removing `last_label`/`last_catalog`, verify no `AdminCube`-typed variable uses them (the fields also appear on `AdminCubeBoundary` at lines 317–326 and `CubeBoundaryEdit` — those are separate types and are NOT touched):
```bash
grep -rn "last_label\|last_catalog" frontend/src/routes/admin/
```

---

### `frontend/src/routes/admin/LocatorHeader.tsx` (modify, currently 64 lines)

**Analog:** `frontend/src/routes/kiosk/ShelfGrid.tsx`

**Imports pattern** — add to the existing file (currently has no imports; add only what is needed):
```typescript
import { useState, useMemo, useEffect } from 'react'
import type { AdminCube } from '../../api/types'
```

**New prop interface pattern** — mirror how `ShelfGrid` adds optional props without breaking existing callers (ShelfGrid lines 6–44):
```typescript
interface LocatorHeaderProps {
  unitId: number
  row: number
  col: number
  shelfName?: string
  binNumber?: number
  rows?: number
  cols?: number
  /** Fill/occupancy data for the whole shelf — passed from ShelfBinList.
   *  When absent the component falls back to today's dim/lit behavior. */
  cubes?: AdminCube[]
}
```

**Per-cell fill state pattern** — mirrors `ShelfGrid.tsx:109-111` (`cubeFillLevel = fillLevels?.get(cubeKey)`), adapted for `AdminCube[]`:
```typescript
// Inside the component, before the return:
const cubeMap = useMemo(() => {
  const m = new Map<string, AdminCube>()
  cubes?.forEach(c => {
    if (c.unit_id === unitId) m.set(`${c.row}-${c.col}`, c)
  })
  return m
}, [cubes, unitId])
```

**Per-cell class + style resolution** — mirrors `ShelfGrid.tsx:97-99` (`state` three-way: lit / empty / dim), adapted for LocatorHeader's class names. Mutually-exclusive states, lit takes priority:
```typescript
// Inside the cell render loop (r, c loop):
const cube = cubeMap.get(`${r}-${c}`)
const isEdited = r === row && c === col && row !== -1
const isEmpty = cube?.is_empty ?? false
const fillLevel = Math.min(cube?.fill_level ?? 0, 1)

const cellClass = isEdited
  ? 'locator-cell locator-cell--lit'
  : isEmpty
    ? 'locator-cell locator-cell--empty'
    : 'locator-cell locator-cell--fill'

const cellStyle = (!isEdited && !isEmpty)
  ? { '--fill': fillLevel } as React.CSSProperties
  : undefined
```

**Tap-to-reveal popover state** — single `useState<number | null>` holding the active cell index (`row * COLS + col`), null when no popover open. Dismiss on tap-away via document `pointerdown`:
```typescript
const [activeIdx, setActiveIdx] = useState<number | null>(null)

// On cell tap (inside the loop):
const idx = r * cols + c
const handleCellTap = () => setActiveIdx(prev => prev === idx ? null : idx)

// Tap-away dismiss:
useEffect(() => {
  if (activeIdx === null) return
  function handleTapAway(e: PointerEvent) {
    if (!(e.target as Element).closest('.locator-mini-grid-wrap')) {
      setActiveIdx(null)
    }
  }
  document.addEventListener('pointerdown', handleTapAway)
  return () => document.removeEventListener('pointerdown', handleTapAway)
}, [activeIdx])

// Escape dismiss:
useEffect(() => {
  if (activeIdx === null) return
  function handleKey(e: KeyboardEvent) {
    if (e.key === 'Escape') setActiveIdx(null)
  }
  document.addEventListener('keydown', handleKey)
  return () => document.removeEventListener('keydown', handleKey)
}, [activeIdx])
```

**Popover content helper** — derives human bin ID from `shelfLetter(unitId)` (already imported by `ShelfBinList`; import it here too):
```typescript
// binId: e.g. unitId=0,row=0,col=0 → "A1"
function popoverContent(cube: AdminCube | undefined, binId: string): React.ReactNode {
  if (!cube || cube.is_empty) {
    return (
      <>
        <span className="locator-fill-popover-id">{binId}</span>
        <span className="locator-fill-popover-empty">Empty bin</span>
      </>
    )
  }
  const pct = Math.round(Math.min(cube.fill_level, 1) * 100)
  return (
    <>
      <span className="locator-fill-popover-id">{binId}</span>
      <span className="locator-fill-popover-data">{cube.record_count} records · {pct}%</span>
    </>
  )
}
```

**Cell render output** — the existing `<div>` cell becomes a `<button type="button">` for tap affordance. Popover is rendered as a sibling inside the grid wrapper (`position: relative`):
```tsx
// Replace the existing <div className="locator-mini-grid"> block:
<div className="locator-mini-grid-wrap">
  <div
    className="locator-mini-grid"
    style={{ gridTemplateColumns: `repeat(${cols}, var(--gruvax-cell-size-sm))` }}
    aria-label={`Mini Kallax — edited bin at row ${row + 1}, col ${col + 1}`}
  >
    {Array.from({ length: rows }, (_, r) =>
      Array.from({ length: cols }, (_, c) => {
        // ... cellClass, cellStyle, cube lookup ...
        const idx = r * cols + c
        const isActive = activeIdx === idx
        return (
          <button
            key={`${r}-${c}`}
            type="button"
            className={cellClass}
            style={cellStyle}
            aria-label={`${binId}: ${ariaDetail}`}
            aria-pressed={isActive}
            onClick={() => setActiveIdx(prev => prev === idx ? null : idx)}
          />
        )
      })
    )}
  </div>
  {activeIdx !== null && (
    <div
      className="locator-fill-popover"
      role="tooltip"
      aria-live="polite"
      style={{
        // Position below cell for rows 0-1, above for rows 2-3
        top: activeRow < 2
          ? `calc((${activeRow + 1}) * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)) + 2px)`
          : undefined,
        bottom: activeRow >= 2
          ? `calc((${rows - activeRow}) * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)) + 2px)`
          : undefined,
        left: `calc(${activeCol} * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)))`,
      }}
    >
      {popoverContent(activeCube, activeBinId)}
    </div>
  )}
</div>
```

---

### `useAdminCubesInvalidation` hook (new, in or alongside `ShelfBinList.tsx`)

**Analog:** `frontend/src/routes/kiosk/KioskView.tsx` SSE `useEffect` (lines 324–452)

**Key difference from KioskView:** This hook calls `es.close()` in its cleanup (the admin SSE listener is intentionally short-lived — scoped to `ShelfBinList` mount/unmount). KioskView deliberately does NOT call `es.close()` in cleanup (see KioskView Pitfall 4 comment at line 350: "EventSource auto-reconnects; do NOT call es.close()"). The admin hook has no auto-reconnect requirement.

**Imports** (at top of `ShelfBinList.tsx` or in a co-located hook file):
```typescript
import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useSessionStore } from '../../state/sessionStore'
```

**Hook implementation** — copy from KioskView.tsx:324-332 (EventSource creation) and lines 360-384 / 424-452 (event listeners), keeping only `invalidateQueries` calls and dropping all kiosk-specific logic:
```typescript
function useAdminCubesInvalidation() {
  const queryClient = useQueryClient()

  useEffect(() => {
    // Use .getState() to avoid stale closure (mirrors KioskView.tsx:326 pattern)
    const profileId = useSessionStore.getState().boundProfileId
    if (!profileId) return

    const es = new EventSource(`/api/events/${profileId}`)

    es.addEventListener('collection_changed', () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    })

    es.addEventListener('boundary_changed', () => {
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    })

    // Admin listener correctly closes on unmount (unlike KioskView which never calls es.close())
    return () => es.close()
  }, [queryClient])
}
```

**Mount site** — call inside `ShelfBinList()` body, alongside the existing `useQuery` and `useQueryClient` calls:
```typescript
export function ShelfBinList() {
  // ... existing hooks ...
  const queryClient = useQueryClient()

  // D-04: invalidate ['admin','cubes'] when collection or boundaries change externally
  useAdminCubesInvalidation()

  // ... rest of component ...
}
```

**Pass cubes to LocatorHeader** — wire `cubesData` (already in scope at `ShelfBinList.tsx:83-87`) to the new prop. The `LocatorHeader` call is at lines 195–202; extend it:
```tsx
<LocatorHeader
  unitId={unitId}
  row={-1}
  col={-1}
  shelfName={shelfDisplayName}
  rows={ROWS}
  cols={COLS}
  cubes={cubesData?.cubes ?? []}   // ADD — passes fill data for shading
/>
```

---

### `frontend/src/routes/admin/admin.css` (append after line 1653)

**Analog:** `frontend/src/routes/admin/admin.css:1608-1653` (existing Phase 5 LocatorHeader block)

**Insertion point:** After line 1653 (end of `.locator-cell--lit` rule), before line 1654 (`/* ── Phase 5: SegmentStrip`).

**Existing pattern to mirror** (lines 1639–1653):
```css
.locator-cell {
  width: var(--gruvax-cell-size-sm);
  height: var(--gruvax-cell-size-sm);
  border-radius: var(--gruvax-cell-radius-sm);
}

.locator-cell--dim {
  background: var(--gruvax-cell-dim);
}

.locator-cell--lit {
  background: var(--gruvax-cell-lit);
  box-shadow: var(--gruvax-shadow-led);
}
```

**New classes to append** (all token-only, no hardcoded hex):
```css
/* ── Phase 10: LocatorHeader fill shading + popover ─────────────────────────── */

/* Grid wrapper — establishes position: relative to anchor the absolute popover */
.locator-mini-grid-wrap {
  position: relative;
}

/* Fill shading — continuous blue gradient driven by --fill custom property */
/* color-mix(in srgb, ...) is natively supported in Chromium 111+ (kiosk target) */
.locator-cell--fill {
  background: color-mix(
    in srgb,
    var(--gruvax-blue) calc(var(--fill, 0) * 70%),
    var(--gruvax-cell-dim)
  );
  border: 1.5px solid var(--gruvax-cell-dim-border);
  transition: background var(--gruvax-duration-base) var(--gruvax-ease-standard);
}

/* Empty cube — CUBE-05 desaturated state (UX-01 SC 1) */
.locator-cell--empty {
  background: var(--gruvax-cell-empty);
  border: 1.5px dashed var(--gruvax-cell-empty-border);
}

/* Touch-primary tap affordance — no hover state (kiosk is touch-primary) */
.locator-cell[role="button"],
.locator-cell-btn {
  cursor: pointer;
}

/* Popover — position: absolute within .locator-mini-grid-wrap */
.locator-fill-popover {
  position: absolute;
  z-index: var(--gruvax-z-overlay);
  background: var(--gruvax-white);
  border: 1.5px solid var(--gruvax-border);
  border-radius: var(--gruvax-radius-md);
  box-shadow: var(--gruvax-shadow-md);
  padding: var(--gruvax-space-3) var(--gruvax-space-2);
  min-width: 120px;
  pointer-events: auto;
  white-space: nowrap;
}

.locator-fill-popover-id {
  font-family: var(--gruvax-font-mono);
  font-size: var(--gruvax-text-mono);
  font-weight: 400;
  color: var(--gruvax-text-primary);
  line-height: var(--gruvax-leading-normal);
  display: block;
}

.locator-fill-popover-data {
  font-family: var(--gruvax-font-mono);
  font-size: var(--gruvax-text-mono);
  font-weight: 400;
  color: var(--gruvax-text-secondary);
  line-height: var(--gruvax-leading-normal);
  display: block;
}

.locator-fill-popover-empty {
  font-family: var(--gruvax-font-ui);
  font-size: var(--gruvax-text-caption);
  font-weight: 400;
  color: var(--gruvax-text-muted);
  line-height: var(--gruvax-leading-normal);
  display: block;
}
```

---

### `frontend/src/routes/admin/LocatorHeader.test.tsx` (new)

**Analog:** `frontend/src/routes/kiosk/ShelfGrid.test.tsx`

**Test file structure** — copy the `render` + `container.querySelectorAll` + `expect(cell).toHaveClass(...)` / `toHaveStyle(...)` idiom. No QueryClient needed (LocatorHeader is display-only with no data fetching):

```typescript
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { AdminCube } from '../../api/types'
import { LocatorHeader } from './LocatorHeader'

// Factory for AdminCube test fixtures
function makeCube(row: number, col: number, overrides?: Partial<AdminCube>): AdminCube {
  return {
    unit_id: 1, row, col,
    first_label: 'Test', first_catalog: 'T-001',
    is_empty: false, fill_level: 0.5, record_count: 25,
    ...overrides,
  }
}

describe('LocatorHeader fill shading', () => {
  it('renders .locator-cell--fill with --fill style for a non-empty cube', () => {
    const cubes = [makeCube(0, 0, { fill_level: 0.75 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')
    expect(cell).toHaveClass('locator-cell--fill')
    expect(cell).toHaveStyle('--fill: 0.75')
  })

  it('renders .locator-cell--empty for an empty cube', () => {
    const cubes = [makeCube(0, 0, { is_empty: true, fill_level: 0 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')
    expect(cell).toHaveClass('locator-cell--empty')
    expect(cell).not.toHaveClass('locator-cell--fill')
  })

  it('lit cell (.locator-cell--lit) takes priority over fill', () => {
    const cubes = [makeCube(2, 1, { fill_level: 0.9 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={2} col={1} cubes={cubes} />
    )
    const cell = container.querySelector('[data-row="2"][data-col="1"]')
    expect(cell).toHaveClass('locator-cell--lit')
    expect(cell).not.toHaveClass('locator-cell--fill')
  })

  it('clamps fill_level > 1.0 to 1.0 for the --fill custom property', () => {
    const cubes = [makeCube(0, 0, { fill_level: 1.5 })]
    const { container } = render(
      <LocatorHeader unitId={1} row={-1} col={-1} cubes={cubes} />
    )
    const cell = container.querySelector('[data-row="0"][data-col="0"]')
    expect(cell).toHaveStyle('--fill: 1')
  })
})
```

---

### `frontend/src/routes/admin/ShelfBinList.sse.test.tsx` (new)

**Analog:** `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx`

**MockEventSource pattern** — copy verbatim from `KioskView.EventSource.test.tsx:69-95`. The class is identical; it just needs to be imported/declared in this new file too (or extracted to a shared test helper):

```typescript
// Copy MockEventSource class from KioskView.EventSource.test.tsx:69-93
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners: Record<string, Array<(e: { data: string }) => void>> = {}
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(name: string, fn: (e: { data: string }) => void) {
    this.listeners[name] = [...(this.listeners[name] ?? []), fn]
  }
  close() {}
  dispatchEvent(name: string, data: unknown) {
    const payload = { data: JSON.stringify(data) }
    this.listeners[name]?.forEach((fn) => fn(payload))
  }
}

vi.stubGlobal('EventSource', MockEventSource)
```

**Test structure** — same `makeQueryClient` + `act` + `vi.spyOn(qc, 'invalidateQueries')` pattern from `KioskView.EventSource.test.tsx:99-119`:

```typescript
// SSE invalidation tests:
it('collection_changed invalidates [admin, cubes]', async () => {
  const qc = makeQueryClient()
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
  // render ShelfBinList with QueryClientProvider + mock adminGetCubes
  // flush effects with act(async () => { ... })
  const es = MockEventSource.instances[MockEventSource.instances.length - 1]

  await act(async () => {
    es.dispatchEvent('collection_changed', {})
  })

  const calledKeys = invalidateSpy.mock.calls.map(
    (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
  )
  expect(calledKeys).toContainEqual(['admin', 'cubes'])
})

it('boundary_changed invalidates [admin, cubes]', async () => {
  // ... same structure, dispatchEvent('boundary_changed', { cube_ids: [] })
  expect(calledKeys).toContainEqual(['admin', 'cubes'])
})
```

---

## Shared Patterns

### Token-only constraint (applies to ALL files in this phase)

**Source:** `design/gruvax-design-tokens.css` + `CLAUDE.md`
**Apply to:** `admin.css` new classes, `LocatorHeader.tsx` inline styles
**Rule:** Never use hardcoded hex. Every color, spacing, and transition value must reference a `var(--gruvax-*)` token. Violation = UX-01 SC 1 failure.

Key tokens confirmed present in `design/gruvax-design-tokens.css`:
- `--gruvax-cell-empty` (#F2F2F2), `--gruvax-cell-empty-border` (#DDDDDD)
- `--gruvax-cell-dim` (#D8E8F5), `--gruvax-cell-dim-border` (#B8D0E8)
- `--gruvax-blue` (#0051A2), `--gruvax-cell-lit` (#FFDA00)
- `--gruvax-cell-size-sm` (28px), `--gruvax-cell-gap-sm` (4px)
- `--gruvax-duration-base` (250ms), `--gruvax-ease-standard`
- `--gruvax-z-overlay` (20), `--gruvax-shadow-md`, `--gruvax-radius-md`
- `--gruvax-font-mono`, `--gruvax-font-ui`, `--gruvax-font-display`
- `--gruvax-text-mono` (14px), `--gruvax-text-caption` (12px)
- `--gruvax-text-primary`, `--gruvax-text-secondary`, `--gruvax-text-muted`
- `--gruvax-space-2` (8px), `--gruvax-space-3` (12px)

### Yellow-reservation rule (applies to `LocatorHeader.tsx` and `admin.css`)

**Source:** `design/gruvax-design-language.md` + CONTEXT.md D-01
**Apply to:** `LocatorHeader.tsx` cell class logic, any new CSS classes
**Rule:** `--gruvax-yellow` / `--gruvax-cell-lit` are reserved exclusively for active/changed/lit (LED state and the existing `.locator-cell--lit` edited-bin highlight). Never use yellow for fill shading. Fill uses blue-family only.

### `useSessionStore.getState()` stale-closure pattern

**Source:** `frontend/src/routes/kiosk/KioskView.tsx:326`
**Apply to:** `useAdminCubesInvalidation` hook
```typescript
// Inside useEffect body — use .getState() not reactive state to avoid stale closure
const profileId = useSessionStore.getState().boundProfileId
```
This is the exact pattern at KioskView.tsx line 326: `const currentProfileId = useSessionStore.getState().boundProfileId`.

### TanStack Query invalidation idiom

**Source:** `frontend/src/routes/admin/ShelfBinList.tsx:131-133`
**Apply to:** `useAdminCubesInvalidation` hook
```typescript
// Existing pattern in ShelfBinList (lines 131-133):
await Promise.all([
  queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] }),
  queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId] }),
])
// For the SSE hook, fire-and-forget is correct (void, no await):
void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
```

### Optional prop backward compatibility

**Source:** `frontend/src/routes/kiosk/ShelfGrid.tsx:68-73` (optional props with defaults)
**Apply to:** `LocatorHeader.tsx` new `cubes` prop
```typescript
// ShelfGrid pattern: optional props default to safe no-op values:
fillLevels,          // undefined → no FillBar rendered
shimmerCubes = new Set(),   // defaults to empty set
// LocatorHeader pattern: cubes is optional → falls back to dim/lit behavior when absent
cubes,   // undefined → existing behavior (no fill shading applied)
```

---

## No Analog Found

All files in this phase have strong analogs. No entries in this section.

---

## Metadata

**Analog search scope:** `frontend/src/routes/admin/`, `frontend/src/routes/kiosk/`, `frontend/src/api/`, `frontend/src/state/`
**Files scanned:** 7 source files + 2 test files read directly
**Pattern extraction date:** 2026-06-02

---
phase: 04-realtime-live-updates
plan: "04"
subsystem: frontend/kiosk-shimmer
tags: [shimmer, sse, rtm-04, d-01, d-02, d-03, css-animation, zustand, react]
dependency_graph:
  requires: [04-01, 04-02, 04-03]
  provides: [kiosk-shimmer-rendering, ttl-sweeper, shimmer-store-tests]
  affects: [frontend/src/routes/kiosk/Cube.tsx, frontend/src/routes/kiosk/ShelfGrid.tsx, frontend/src/routes/kiosk/KioskView.tsx, frontend/src/routes/kiosk/kiosk.css, frontend/src/state/store.connectivity.test.ts]
tech_stack:
  added: []
  patterns:
    - "Zustand reactive selector (s) => s.shimmerCubes for non-stale render binding"
    - "useMemo Set<string> derivation from ShimmerCube[] for O(1) ShelfGrid lookup"
    - "useEffect TTL sweeper using getState() to avoid stale closures (Pitfall 5)"
    - "opacity-only CSS animation with will-change:opacity for GPU compositing (Pitfall 16)"
    - "aria-hidden decorative overlay — never sets data-state, never recolors lit cell (D-02)"
key_files:
  created:
    - frontend/src/state/store.connectivity.test.ts
  modified:
    - frontend/src/routes/kiosk/Cube.tsx
    - frontend/src/routes/kiosk/ShelfGrid.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css
decisions:
  - "Shimmer overlay rendered as absolute-positioned sibling div after FillBar — never wraps or recolors the cube itself (D-02)"
  - "ShelfGrid receives shimmerCubes as Set<string> (not the ShimmerCube[] array) to keep per-cell lookup O(1)"
  - "60s TTL sweeper in KioskView reads shimmerExpiresAt reactively; schedules setTimeout for remaining ms; clears via getState() to avoid stale closure (Pitfall 5)"
  - "Store tests use vi.useFakeTimers() + vi.setSystemTime() to assert shimmerExpiresAt ~ now+60_000 without wallclock sensitivity"
metrics:
  duration: "~8 minutes"
  completed: "2026-05-22T02:02:47Z"
  tasks_completed: 3
  files_changed: 5
---

# Phase 4 Plan 04: Kiosk Shimmer Rendering + 60s TTL Sweeper Summary

Renders the "boundaries updating" ambient shimmer on the kiosk: opacity-only overlay on affected cube range driven by admin_editing SSE (already stored as shimmerCubes by Plan 01), with a 60s client-side TTL sweeper and a full store test suite.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | Store shimmer test — admin_editing sets shimmer, boundary_changed clears, 60s TTL | 99727a4 | frontend/src/state/store.connectivity.test.ts |
| 2 | shimmerActive prop on Cube + shimmerCubes pass-through on ShelfGrid + CSS | b9d22cb | Cube.tsx, ShelfGrid.tsx, kiosk.css |
| 3 | Wire shimmerCubes selector into KioskView + 60s TTL sweeper | e1142b3 | KioskView.tsx |

## What Was Built

### Task 1: Store Connectivity Test (store.connectivity.test.ts)
8 active vitest assertions covering:
- `setShimmerCubes` populates shimmerCubes and stamps `shimmerExpiresAt` = `Date.now() + 60_000` (+-100ms tolerance with `vi.useFakeTimers`)
- `clearShimmerCubes` removes matching cubes by `unit:row:col` key, leaves others intact
- `clearShimmerCubes` with all cubes empties the array
- `clearShimmerCubes` with unknown cube is a no-op
- `setSseConnected(true)` sets `sseConnected=true` and stamps `lastSeenAt`
- `setSseConnected(false)` sets `sseConnected=false` and leaves `lastSeenAt` unchanged
- Initial connectivity state is disconnected with `lastSeenAt=0`

No `it.todo` or `it.skip` — all assertions are active and passing.

### Task 2: Shimmer Rendering Layer
**Cube.tsx** — added `shimmerActive?: boolean` prop (default false) with JSDoc noting it is decorative and never recolors the cube. Renders `<div className="cube-shimmer-overlay" aria-hidden="true" />` after the FillBar when true.

**ShelfGrid.tsx** — added `shimmerCubes?: Set<string>` prop (default empty Set). Passes `shimmerActive={shimmerCubes.has(unit.id-r-c)}` to every Cube cell.

**kiosk.css** — `.cube-shimmer-overlay` rule: `position:absolute; inset:0; z-index:3; border-radius:inherit; pointer-events:none; background:var(--gruvax-yellow-faint); border:1px solid var(--gruvax-yellow-glow); animation:shimmer-sweep 2000ms var(--gruvax-ease-standard) infinite; will-change:opacity`. `@keyframes shimmer-sweep` animates opacity only (0->1->1->0 at 0/40/60/100%). Zero hardcoded hex — all three tokens (`--gruvax-yellow-faint`, `--gruvax-yellow-glow`, `--gruvax-ease-standard`) confirmed present in design/gruvax-design-tokens.css.

### Task 3: KioskView Wiring + TTL Sweeper
**KioskView.tsx:**
- Reactive selectors: `useGruvaxStore((s) => s.shimmerCubes)` and `useGruvaxStore((s) => s.shimmerExpiresAt)` — not `getState()` in render (no stale closure risk)
- `useMemo` derives `shimmerSet = new Set(shimmerCubes.map(...))` keyed on `shimmerCubes`
- `shimmerCubes={shimmerSet}` passed to both `<ShelfGrid>` renders (loaded units loop + placeholder fallback)
- `useEffect` sweeper: when `shimmerCubes.length > 0`, schedules `setTimeout(shimmerExpiresAt - Date.now())` that calls `useGruvaxStore.getState().clearShimmerCubes(...)` — handles already-expired case synchronously; cleanup cancels the timer
- Single `new EventSource` preserved (count == 1)

## Verification Results

| Check | Result |
|-------|--------|
| `npm run lint` (eslint src/) | 0 errors |
| `npm test --run` (vitest run, 21 tests, 4 suites) | 21/21 pass |
| `npm run build` (vite build) | success (no errors) |
| shimmerActive in Cube.tsx | PASS |
| cube-shimmer-overlay in Cube.tsx | PASS |
| aria-hidden in Cube.tsx | PASS |
| shimmerCubes in ShelfGrid.tsx | PASS |
| cube-shimmer-overlay + shimmer-sweep in kiosk.css | PASS |
| CSS gate: no box-shadow/solid-bg/data-state in overlay | PASS |
| CSS gate: zero hardcoded hex | PASS |
| Reactive shimmerCubes selector in KioskView | PASS |
| shimmerCubes= passed to >= 2 ShelfGrid renders | PASS (count=2) |
| shimmerExpiresAt + clearShimmerCubes in sweeper | PASS |
| Single EventSource in KioskView | PASS (count=1) |
| No it.todo/it.skip in store.connectivity.test.ts | PASS |

## Deviations from Plan

None. Plan executed exactly as written.

The only incidental discovery: the worktree had no `node_modules` directory. A symlink was created (`frontend/node_modules` -> `../../GRUVAX/frontend/node_modules`) to enable local test execution. This is a dev-environment setup detail — no code or plan changes were required.

## Known Stubs

None. The shimmer path is fully wired: admin_editing SSE -> store.setShimmerCubes -> KioskView reactive selector -> shimmerSet -> ShelfGrid.shimmerCubes -> Cube.shimmerActive -> .cube-shimmer-overlay CSS animation. The TTL sweeper enforces D-03 in the client without requiring a committed boundary_changed.

## Threat Flags

No new threat surface beyond the plan's threat model (T-04-12, T-04-13, T-04-14 covered). The overlay is a purely additive rendering concern on the existing admin_editing event path.

## Self-Check: PASSED

All files present. All commit hashes verified. Full test suite 21/21 green. Build clean.

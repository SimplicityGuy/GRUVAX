---
phase: 04-realtime-live-updates
verified: 2026-05-21T20:15:00Z
status: passed
score: 9/9 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 7/9
  gaps_closed:
    - "D-01/RTM-04: CubeEditor.tsx now imports createEditingHeartbeat, creates heartbeat via useMemo, calls heartbeat.signal(editingCubeIds, true) on dirty fields, heartbeat.signal(editingCubeIds, false) on unmount/cube-change — admin_editing events now have a real production entry point"
    - "D-08/WR-01: resync() in KioskView.tsx no longer invalidates ['admin','cubes'] or ['admin','history'] — only ['units'], ['cubes'], and active re-locate; ['admin','settings'] retained on server_hello only (intentional)"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "OFF-01..04: Kiosk offline banner, disabled search, exponential backoff, reconnect success indicator"
    addressed_in: "Future SPIDR slice (Offline Resilience)"
    evidence: "CONTEXT.md deferred section: 'Offline Resilience (OFF-01..04) → next slice'. ROADMAP SPIDR note. Phase 4 ROADMAP requirements field lists only ADMN-11, RTM-01..04."
  - truth: "SRCH-09, PRIV-01..04: Recently-pulled list, session-storage privacy, reset button"
    addressed_in: "Future SPIDR slice (Privacy + Recently-Pulled)"
    evidence: "ROADMAP SPIDR note explicitly names these deferred. Phase 4 requirements field omits them."
human_verification:
  - test: "End-to-end live update over the LAN (ADMN-11)"
    expected: "On the Pi kiosk + admin on mobile, same home LAN: edit a boundary on mobile, observe the kiosk cube re-renders within ~500ms without manual refresh"
    why_human: "Real two-device WiFi latency (Pi → lux → mobile) is the actual constraint; the integration test covers in-process latency only"
  - test: "Re-glow animation feel (D-06)"
    expected: "Old cube fades off, new cube springs on (LED-physics — no cross-grid slide, no flash); animation completes within ~600ms and is interruptible by a new search"
    why_human: "GSAP timeline visual quality, LED-physics feel, and interruptibility cannot be asserted in jsdom; the mechanism (animationToken + useLayoutEffect) is code-verified but motion quality requires eyes-on"
  - test: "Shimmer animation on Pi hardware (D-02, Pitfall 16)"
    expected: "Open the cube editor on mobile — affected cube range shows subtle opacity-only shimmer (~2s cycle) on the Pi kiosk; no lit (yellow) cell is recolored; no frame jank visible (p95 < 16ms)"
    why_human: "Pi 5 GPU compositor frame budget cannot be asserted in jsdom; D-02 'never recolor a lit cell' requires visual confirmation on real hardware. Heartbeat call site is now wired — use the editor on mobile to trigger."
---

# Phase 4: Realtime Live Updates Verification Report

**Phase Goal:** As a kiosk visitor, I want to see the shelf map update live as the owner re-files records, so that I can always trust the kiosk reflects the current shelf layout without refreshing.
**Verified:** 2026-05-21T20:15:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (commit 7f2ab92)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Admin boundary edit on mobile causes kiosk cube re-render within ~500ms, no refresh (ADMN-11/RTM-01/D-04) | VERIFIED | `bus.publish('boundary_changed',...)` in `finally` blocks in both `put_cube_boundary` (L338) and `bulk_write_cubes` (L791); `test_boundary_changed_latency` passes; kiosk EventSource invalidates `['cubes']`, `['units']` on event |
| 2 | GET /api/events holds no DB pool connection for the life of the stream (RTM-02/D-09/Pitfall 10) | VERIFIED | `src/gruvax/api/events.py` depends only on `get_event_bus`, never `get_pool`; `test_sse_no_pool_dep` passes |
| 3 | Two simultaneous searches run concurrently without server-side serialization (RTM-02) | VERIFIED | `test_concurrent_searches` passes; SSE endpoint holds no pool slot |
| 4 | SSE endpoint ships X-Accel-Buffering: no + Cache-Control: no-store + ping=15 (Pitfall 8) | VERIFIED | Headers set on `EventSourceResponse` in `events.py`; `test_sse_headers` passes |
| 5 | Admin optimistic commit rolls back on error, shows plain-language toast, retains pendingChangeSet (RTM-03/D-07/D-08) | VERIFIED | `DiffPreviewSheet.tsx` has `onMutate`/`onError`/`onSettled`; `onError` mounts `RollbackToast`, does not clear `pendingChangeSet`; `DiffPreviewSheet.test.tsx` 3 tests pass |
| 6 | When admin is mid-edit, kiosk shows subtle opacity-only shimmer on affected cube range, clears on commit + 60s TTL (RTM-04/D-01/D-02/D-03) | VERIFIED (was PARTIAL BLOCKER) | **Gap 1 closed.** `CubeEditor.tsx` L31 imports `createEditingHeartbeat`; L308 `useMemo(() => createEditingHeartbeat(), [])` creates heartbeat; L316-324 effect calls `heartbeat.signal(editingCubeIds, true)` only when `dirty` (fields differ from seededBoundary — not the initial seed); L327-329 cleanup effect calls `heartbeat.signal(editingCubeIds, false)` on unmount/cube-change. Full pipeline: CubeEditor → signalEditing POST /api/admin/editing → bus admin_editing → KioskView shimmer overlay now has a real production entry point. |
| 7 | D-10: kiosk EventSource sets connectivity.sseConnected via onopen/onerror/server_shutdown with no visible offline UI | VERIFIED | `store.ts` has `connectivity: {sseConnected, lastSeenAt, bannerVisible: false}`; `onopen` calls `setSseConnected(true)`, `onerror` calls `setSseConnected(false)` |
| 8 | D-08: Optimistic edits are owner-device-local — the kiosk resync (onopen/server_hello) does not touch admin query keys | VERIFIED (was PARTIAL WARNING) | **Gap 2 closed.** `resync()` in `KioskView.tsx` L201-211 now invalidates ONLY `['units']` (L206) and `['cubes']` (L207), then calls `relocateActiveSelection()`. The `['admin','cubes']` invalidation has been removed. `boundary_changed` handler also invalidates only kiosk keys (`['cubes']`, `['units']`, `['cube-contents',...]`). `server_hello` retains `['admin','settings']` invalidation (intentional — kiosk colors/idle derive from settings). Comment at L202-205 explicitly documents the D-08 isolation rationale. |
| 9 | D-05/D-06: active selection highlight relocates to new cube on boundary_changed (re-glow via animationToken, no slide) | VERIFIED | `relocateActiveSelection()` in `KioskView.tsx` reads `selectedReleaseId` via `.getState()`, calls `locateRelease(id).then(setLocateResult)` (bumps animationToken → GSAP re-glow); `KioskView.EventSource.test.tsx` covers D-05 and D-11 |

**Score:** 9/9 truths verified

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | OFF-01..04: Offline banner, disabled search, exponential backoff, reconnect success indicator | Future SPIDR slice | CONTEXT.md deferred section; ROADMAP SPIDR note; Phase 4 requirements field omits OFF-* IDs |
| 2 | SRCH-09, PRIV-01..04: Recently-pulled, privacy floors | Future SPIDR slice | ROADMAP SPIDR note explicitly names these deferred |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/gruvax/events/bus.py` | EventBus — asyncio.Queue-per-subscriber fan-out | VERIFIED | `class EventBus`, `maxsize=64`, `contextlib.suppress(asyncio.QueueFull)`, `put_nowait` fan-out |
| `src/gruvax/api/events.py` | GET /api/events SSE, no DB dep | VERIFIED | `EventSourceResponse`, `ping=15`, headers set, `Depends(get_event_bus)` only |
| `src/gruvax/api/deps.py` | `get_event_bus` provider | VERIFIED | `def get_event_bus` at L84, raises HTTP 503 if not set |
| `src/gruvax/app.py` | EventBus lifespan + events router | VERIFIED | `EventBus()` at L140, `server_hello` at L143, `server_shutdown` at L158, `events_router` at L204 |
| `src/gruvax/api/admin/cubes.py` | bus.publish at BOTH post-commit seams in try/finally | VERIFIED | `bus.publish("boundary_changed",...)` in `finally` at L338 and L791 |
| `src/gruvax/api/admin/editing.py` | Session+CSRF-gated POST /api/admin/editing → bus.publish('admin_editing') | VERIFIED | `require_admin` dep, `CubeId` typed Pydantic model, `bus.publish("admin_editing", body.model_dump())` |
| `src/gruvax/api/admin/router.py` | editing_router registered | VERIFIED | `editing_router` imported and included |
| `frontend/src/state/store.ts` | connectivity + shimmerCubes + shimmerExpiresAt slice | VERIFIED | All fields present, initialized correctly, setters/clearers implemented |
| `frontend/src/routes/kiosk/KioskView.tsx` | SSE consumer, shimmer selector, TTL sweeper, D-05 re-locate, D-08 kiosk-key-only resync | VERIFIED | `new EventSource('/api/events')`, all listeners, `relocateActiveSelection`, reactive selectors, 60s TTL useEffect, shimmerCubes prop to both ShelfGrid renders; resync() now invalidates only `['units']` and `['cubes']` |
| `frontend/src/routes/kiosk/Cube.tsx` | shimmerActive prop + .cube-shimmer-overlay, aria-hidden | VERIFIED | `shimmerActive?: boolean` prop, `<div className="cube-shimmer-overlay" aria-hidden="true" />` |
| `frontend/src/routes/kiosk/ShelfGrid.tsx` | shimmerCubes Set<string> prop → Cube.shimmerActive | VERIFIED | `shimmerCubes?: Set<string>` prop, `shimmerActive={shimmerCubes.has(...)}` per cell |
| `frontend/src/routes/kiosk/kiosk.css` | .cube-shimmer-overlay opacity-only animation, design tokens | VERIFIED | `will-change: opacity`, keyframes animate opacity only, `var(--gruvax-yellow-faint)`, `var(--gruvax-yellow-glow)`, `var(--gruvax-ease-standard)` — zero hardcoded hex |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx` | onMutate/onError/onSettled, admin keys only (D-08) | VERIFIED | All three hooks present; onSettled never touches `['cubes']` or `['cube-contents']`; comment at L183 notes D-08 isolation |
| `frontend/src/routes/admin/RollbackToast.tsx` | Plain-language toast, 4000ms, design tokens, double-dismiss guard | VERIFIED | "Couldn't save that change — reverted.", `setTimeout(onDismiss, 4000)`, `dismissed = useRef(false)` guard, zero hardcoded hex |
| `frontend/src/api/adminClient.ts` | signalEditing, createEditingHeartbeat, putCubeBoundary | VERIFIED | All three exported and implemented. `createEditingHeartbeat` now imported and used by `CubeEditor.tsx` — call site gap resolved. |
| `frontend/src/routes/admin/CubeEditor.tsx` | Heartbeat import + useMemo + dirty-check effect + cleanup effect | VERIFIED | L31 imports `createEditingHeartbeat`; L308 `useMemo`; L316-324 dirty-check effect with `seededBoundary` guard; L327-329 cleanup effect returning `heartbeat.signal(editingCubeIds, false)` |
| `tests/unit/test_event_bus.py` | EventBus tests + test_sse_no_pool_dep | VERIFIED | `test_subscribe_receive_publish`, `test_slow_subscriber_drops_silently`, `test_sse_no_pool_dep` — all pass |
| `tests/integration/test_sse.py` | Latency, headers, concurrency | VERIFIED | `test_boundary_changed_latency` (< 500ms), `test_sse_headers`, `test_concurrent_searches` — all pass |
| `tests/integration/test_editing.py` | Auth-gating + fan-out tests | VERIFIED | `test_editing_requires_auth` (401/403 on no session), `test_editing_fans_out` (SSE receives admin_editing) — both pass |
| `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` | MockEventSource D-05 + D-11 tests | VERIFIED | 4 tests cover sseConnected, resync, active-selection re-locate, null-selection guard |
| `frontend/src/state/store.connectivity.test.ts` | Shimmer state + 60s TTL + sseConnected tests | VERIFIED | 7 assertions, no it.todo/it.skip |
| `frontend/src/routes/admin/DiffPreviewSheet.test.tsx` | Rollback, retain pendingChangeSet, kiosk key isolation | VERIFIED | 3 tests — all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/gruvax/api/admin/cubes.py` | `src/gruvax/events/bus.py` | `bus.publish('boundary_changed', ...)` in finally block | VERIFIED | Both put_cube_boundary (L338) and bulk_write_cubes (L791) publish after cache.load in try/finally |
| `frontend/src/routes/kiosk/KioskView.tsx` | `/api/events` | `new EventSource('/api/events')` in useEffect | VERIFIED | Single EventSource at L213; single close at return |
| `src/gruvax/api/events.py` | `src/gruvax/api/deps.py` | `Depends(get_event_bus)` — NEVER get_pool | VERIFIED | L32: `bus: EventBus = Depends(get_event_bus)` with comment "NO get_pool" |
| `src/gruvax/api/admin/editing.py` | `src/gruvax/events/bus.py` | `bus.publish('admin_editing', ...)` behind require_admin | VERIFIED | `await bus.publish("admin_editing", body.model_dump())` |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx` | TanStack Query useMutation | `onMutate/onError/onSettled` with admin-key-only isolation | VERIFIED | All three hooks present; kiosk key `['cubes']` confirmed absent from mutation hooks |
| `frontend/src/routes/admin/CubeEditor.tsx` | `signalEditing`/`createEditingHeartbeat` in adminClient.ts | Heartbeat call on dirty field change / editor close | VERIFIED | L31 import; L308 useMemo; L323 `heartbeat.signal(editingCubeIds, true)` when dirty; L328 `heartbeat.signal(editingCubeIds, false)` on cleanup — Gap 1 closed |
| `frontend/src/routes/kiosk/KioskView.tsx` | `frontend/src/routes/kiosk/ShelfGrid.tsx` | `shimmerCubes={shimmerSet}` prop to both ShelfGrid renders | VERIFIED | `shimmerCubes=` appears at L457 and L478 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `KioskView.tsx` SSE consumer | `boundary_changed` events | `EventBus.publish()` called from `cubes.py` after DB commit | Yes — triggered by real DB writes | FLOWING |
| `KioskView.tsx` shimmerCubes | `admin_editing` events | `editing.py` `bus.publish("admin_editing")` ← `CubeEditor.tsx` heartbeat.signal | Yes — CubeEditor now calls signalEditing via createEditingHeartbeat on dirty field change | FLOWING |
| `DiffPreviewSheet.tsx` optimistic | `['admin','cubes']` snapshot | `queryClient.getQueryData(['admin', 'cubes'])` | Yes — live TanStack Query cache | FLOWING |
| `RollbackToast.tsx` | `message` prop | DiffPreviewSheet `onError` → `setShowRollbackToast(true)` | Yes — "Couldn't save that change — reverted." | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| EventBus unit tests | `uv run pytest tests/unit/test_event_bus.py -p no:benchmark --tb=no` | All pass | PASS |
| SSE integration tests | `uv run pytest tests/integration/test_sse.py -p no:benchmark --tb=no` | All pass (incl. < 500ms latency gate) | PASS |
| Editing integration tests | `uv run pytest tests/integration/test_editing.py -p no:benchmark --tb=no` | All pass | PASS |
| Full backend suite | `uv run pytest tests/ -p no:benchmark --tb=no` | 216 passed, 7 skipped, 1 pre-existing error (benchmark) | PASS |
| mypy | `uv run mypy src/` | Success: no issues found in 40 source files | PASS |
| Frontend vitest | `npx vitest run` (from frontend/) | 21 passed, 4 suites | PASS |
| Frontend ESLint | `npm run lint` (from frontend/) | 0 errors | PASS |
| Frontend build | `npm run build` (from frontend/) | Built in 145ms, 0 errors (pre-existing chunk-size warning) | PASS |

### Probe Execution

No probe scripts defined for this phase. Step 7c: SKIPPED (no `scripts/*/tests/probe-*.sh` found).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| ADMN-11 | 04-01-PLAN.md | Admin boundary edits on mobile cause kiosk to re-render without refresh | SATISFIED | `test_boundary_changed_latency` < 500ms; `boundary_changed` SSE listener invalidates `['cubes']`/`['units']` |
| RTM-01 | 04-01-PLAN.md, 04-02-PLAN.md | Kiosk subscribes to SSE and re-renders on boundary_changed; highlight follows relocated record | SATISFIED | Full SSE consumer wired; D-05 re-locate via `relocateActiveSelection()` |
| RTM-02 | 04-01-PLAN.md | Concurrent searches without serialization; SSE holds no DB connection | SATISFIED | `test_concurrent_searches` and `test_sse_no_pool_dep` pass |
| RTM-03 | 04-03-PLAN.md | Admin edits optimistic with rollback on server error | SATISFIED | `useMutation` onMutate/onError/onSettled; RollbackToast with locked copy; DiffPreviewSheet.test.tsx 3 tests pass |
| RTM-04 | 04-03-PLAN.md, 04-04-PLAN.md | "Boundaries updating" indicator while admin mid-edit | SATISFIED | Backend endpoint, kiosk listener, CSS overlay, and store state all wired. CubeEditor.tsx now imports and calls createEditingHeartbeat — heartbeat call site gap closed. Full pipeline is live. |
| SRCH-09 | (deferred) | Recently-pulled list | DEFERRED | Explicitly SPIDR-split per CONTEXT.md and ROADMAP |
| PRIV-01..04 | (deferred) | Privacy floors | DEFERRED | Explicitly SPIDR-split per CONTEXT.md and ROADMAP |
| OFF-01..04 | (deferred) | Offline resilience | DEFERRED | Explicitly SPIDR-split per CONTEXT.md and ROADMAP |

**Orphaned requirements note (unchanged from initial):** REQUIREMENTS.md traceability table maps SRCH-09, PRIV-01..04, OFF-01..04 to their original phase name pre-SPIDR. The ROADMAP's Phase 4 requirements field and CONTEXT.md explicitly defer all of these. This is a traceability hygiene issue in REQUIREMENTS.md but not a functional gap for Phase 4's narrowed goal.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/gruvax/api/admin/cubes.py` | 235 | `put_cube_boundary` docstring claims history write; no `write_history_row` call present (CR-02 unfixed) | WARNING | Single-cube edits leave no audit trail in boundary_history; change_set_id in SSE payload not persisted. Pre-existing; not introduced by Phase 4. |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx` | 282-283 | `isOverstuffed = mc.records_after > (mc.records_before * 1.1 + 1)` — false positives on empty-to-populated cubes (CR-03 unfixed) | INFO | Spurious "may exceed capacity" warning on empty cubes receiving first records. Pre-existing. |
| `frontend/src/routes/kiosk/KioskView.tsx` | 227, 251 | `JSON.parse(e.data)` without try/catch in boundary_changed and admin_editing handlers (IN-02 unfixed) | INFO | Malformed SSE frame silently drops invalidation or shimmer for that event; 60s TTL + resync-on-reconnect provide recovery. Pre-existing. |

No `TBD`, `FIXME`, or `XXX` markers found in any phase-4-modified files.

**Previously flagged anti-patterns now resolved:**
- `frontend/src/api/adminClient.ts` — `signalEditing`/`createEditingHeartbeat` exported but no call site: RESOLVED. CubeEditor.tsx now imports and uses both.
- `frontend/src/routes/kiosk/KioskView.tsx` — `invalidateQueries(['admin','cubes'])` in `resync()`: RESOLVED. Line removed; resync() now invalidates only kiosk-owned keys.

### Human Verification Required

All automated checks pass. The following items require on-device testing and cannot be verified programmatically.

### 1. End-to-end live update over the LAN (ADMN-11)

**Test:** On the Pi kiosk (Chromium) + admin on mobile phone, same home LAN: navigate to kiosk URL, then edit a boundary record on mobile admin; observe the affected cube re-renders on the kiosk.
**Expected:** The kiosk cube visually changes (highlight shifts or fill updates) within ~500ms without the visitor manually refreshing.
**Why human:** Real two-device WiFi latency (Pi → lux → mobile) is the actual constraint; the integration test covers in-process latency only.

### 2. Re-glow animation feel (D-06)

**Test:** While a search result is selected on the kiosk (cube highlighted), perform an admin boundary edit on mobile that moves that record to a different cube.
**Expected:** The old cube's highlight fades off; the new cube springs on (LED-physics — no cross-grid slide, no flash). Animation should complete within ~600ms and be interruptible by a new search.
**Why human:** GSAP timeline visual quality, LED-physics feel, and interruptibility cannot be asserted in jsdom. The mechanism (animationToken increment → useLayoutEffect) is code-verified but motion quality requires eyes-on.

### 3. Shimmer animation on Pi hardware (D-02, Pitfall 16)

**Test:** Open the cube editor on mobile (admin) for any cube; begin typing in any field. Observe the kiosk on the Pi.
**Expected:** Affected cube range shows a subtle ambient shimmer (opacity-only animation, ~2s cycle); no lit (yellow) cell is recolored; no frame jank visible.
**Note:** The heartbeat call site is now wired — opening the editor on mobile and changing a field is sufficient to trigger a real admin_editing SSE event.
**Why human:** Pi 5 GPU compositor frame budget (p95 < 16ms) cannot be asserted in jsdom; D-02 "never recolor a lit cell" requires visual confirmation on real hardware.

### Gaps Summary

No gaps remain. Both previously identified blockers/warnings are resolved:

**Gap 1 — Heartbeat call site (RTM-04): CLOSED**

`CubeEditor.tsx` at commit 7f2ab92 now:
- Imports `createEditingHeartbeat` from `../../api/adminClient` (L31, alongside existing imports)
- Creates `heartbeat = useMemo(() => createEditingHeartbeat(), [])` (L308) — stable across re-renders, GC'd on unmount
- Computes `editingCubeIds = useMemo(() => [{ unit: unitId, row: rowNum, col: colNum }], [unitId, rowNum, colNum])` (L309-312)
- Calls `heartbeat.signal(editingCubeIds, true)` in a `useEffect` that fires when `fields` change AND `dirty` is true — meaning the user has actually changed a field away from the seeded boundary (not the initial open) (L316-324)
- Calls `heartbeat.signal(editingCubeIds, false)` in a separate cleanup effect that fires on unmount or cube-change (L327-329)

The dirty-check guard (`if (!seededBoundary) return; const dirty = ...`) correctly prevents the editor from shimmering the kiosk when first opened (before the user touches any field).

**Gap 2 — resync() D-08 boundary violation (WR-01): CLOSED**

`KioskView.tsx` `resync()` at L201-211 now invalidates only `['units']` (L206) and `['cubes']` (L207). The `['admin','cubes']` invalidation is removed. The comment at L202-205 documents the D-08 rationale explicitly. `boundary_changed` handler also invalidates only kiosk keys. `server_hello` retains `['admin','settings']` (intentional per requirements — kiosk colors and idle TTL derive from settings).

---

_Verified: 2026-05-21T20:15:00Z_
_Verifier: Claude (gsd-verifier)_
_Re-verification after: commit 7f2ab92_

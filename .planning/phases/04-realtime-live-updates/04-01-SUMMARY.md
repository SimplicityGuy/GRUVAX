---
phase: 04-realtime-live-updates
plan: "01"
subsystem: realtime
tags: [sse, event-bus, kiosk, live-render, connectivity]
dependency_graph:
  requires:
    - "03-01 (admin session + boundary cache + cubes.py write path)"
    - "02-01 (locate + search API)"
  provides:
    - "GET /api/events SSE endpoint with no DB dependency"
    - "EventBus in-process fan-out (asyncio.Queue per subscriber)"
    - "boundary_changed fan-out at post-commit seam in cubes.py"
    - "kiosk connectivity/shimmerCubes Zustand slice"
    - "kiosk EventSource consumer with live re-render"
  affects:
    - "src/gruvax/api/admin/cubes.py (added bus.publish at post-commit seams)"
    - "src/gruvax/app.py (added EventBus lifespan step + events router registration)"
    - "frontend/src/routes/kiosk/KioskView.tsx (SSE consumer useEffect)"
    - "frontend/src/state/store.ts (connectivity + shimmerCubes slice)"
tech_stack:
  added:
    - "EventBus: asyncio.Queue-per-subscriber in-process fan-out (no new packages)"
    - "sse-starlette: already pinned at 3.4.4 — no version change"
    - "uvicorn background-thread fixture for SSE integration tests"
  patterns:
    - "SSE headers: X-Accel-Buffering: no + Cache-Control: no-store + ping=15 (Pitfall 8)"
    - "No DB pool dependency on SSE endpoint (D-09, Pitfall 10)"
    - "bus.publish() AFTER cache.load() — Pitfall A ordering preserved"
    - "initial SSE comment ': connected' to flush headers before first event"
    - "useGruvaxStore.getState() in event handlers (Pitfall 5 stale closure)"
    - "EventSource es.close() only in cleanup return (Pitfall 4)"
key_files:
  created:
    - "src/gruvax/events/__init__.py"
    - "src/gruvax/events/bus.py"
    - "src/gruvax/api/events.py"
    - "tests/unit/test_event_bus.py"
    - "tests/integration/test_sse.py"
  modified:
    - "src/gruvax/api/deps.py (added get_event_bus provider)"
    - "src/gruvax/app.py (added EventBus lifespan step 3d + events router)"
    - "src/gruvax/api/admin/cubes.py (bus.publish in put_cube_boundary + bulk_write_cubes)"
    - "frontend/src/state/store.ts (connectivity + shimmerCubes slice)"
    - "frontend/src/routes/kiosk/KioskView.tsx (SSE consumer useEffect)"
decisions:
  - "Used live uvicorn server (background thread) instead of ASGITransport for SSE tests — httpx's ASGITransport buffers the full response body before yielding, making it incompatible with infinite SSE streams"
  - "Added initial ': connected' SSE comment to flush headers immediately on subscribe (prevents proxy buffering before first event)"
  - "SSE test uses force=True + fixtures.yaml boundary values for restore — avoids phantom check on synthetic test data"
  - "bannerVisible: false typed as literal false in ConnectivityState — stub for deferred Offline-Banner slice (D-10)"
metrics:
  duration: "~90 minutes (resumed from prior context)"
  completed: "2026-05-22T01:28:56Z"
  tasks_completed: 4
  files_changed: 10
---

# Phase 4 Plan 01: SSE Realtime Spine Summary

Builds the realtime spine end-to-end: an in-process EventBus, GET /api/events SSE endpoint with no DB dependency, boundary_changed fan-out wired at the cubes.py post-commit seam, and the kiosk EventSource consumer. An admin PUT on one device now re-renders the affected cube on an open kiosk within ~500ms with no manual refresh.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Wave 0 test scaffold (RED) | bd84c42 | tests/unit/test_event_bus.py, tests/integration/test_sse.py |
| 2 | EventBus + get_event_bus + lifespan wiring (GREEN unit) | 63c6997 | src/gruvax/events/bus.py, src/gruvax/events/__init__.py, src/gruvax/api/deps.py, src/gruvax/app.py |
| 3 | SSE endpoint + bus.publish at post-commit seam (GREEN integration) | 68a47f4 | src/gruvax/api/events.py, src/gruvax/api/admin/cubes.py, src/gruvax/app.py |
| 4 | Kiosk SSE consumer + connectivity/shimmerCubes slice | 8e7eedc | frontend/src/state/store.ts, frontend/src/routes/kiosk/KioskView.tsx |
| fix | Test isolation + noqa cleanup | 8632275 | tests/integration/test_sse.py, tests/unit/test_event_bus.py |

## Verification Results

- `python -m pytest tests/` — 216 passed, 6 skipped, 0 failed
- `ruff check` on all plan-modified files — all checks passed
- `mypy src/` — success: no issues found in 39 source files
- `npm run lint` (frontend) — no errors
- `npm run build` (frontend) — built in 190ms, no errors
- `npm test --run` — not available (no frontend test runner configured; TypeScript compilation via `tsc -b` validates types)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] ASGITransport incompatible with infinite SSE streams**
- **Found during:** Task 3 (SSE integration test hang)
- **Issue:** httpx's ASGITransport buffers the full response body before returning headers. For an infinite SSE stream, `ac.stream().__aenter__()` never returns because the ASGI app never finishes sending body chunks.
- **Fix:** Rewrote the `live_server` fixture to use a real uvicorn server (background thread with `threading.Thread`) instead of ASGITransport. The SSE client connects to a real TCP socket where headers arrive immediately and the streaming body is consumed incrementally.
- **Files modified:** tests/integration/test_sse.py
- **Commit:** 68a47f4

**2. [Rule 2 - Missing critical functionality] Initial SSE comment for header flushing**
- **Found during:** Task 3
- **Issue:** Without yielding anything immediately, proxy buffers could delay the first event. The SSE generator had no initial flush.
- **Fix:** Added `yield ServerSentEvent(comment="connected")` as the first yield in the generator so headers flush to the client before the first real event.
- **Files modified:** src/gruvax/api/events.py
- **Commit:** 68a47f4

**3. [Rule 1 - Bug] Test data contamination between test_sse.py and test_locate.py**
- **Found during:** Full test suite run after Task 3
- **Issue:** `test_boundary_changed_latency` wrote synthetic boundary values (`ZZ Test / ZZT 0001`) to cube 1/0/0 and did not restore them. `test_locate.py` expects cube 1/0/0 to have `first_label = "Blue Note"` (from fixtures.yaml), so 4 locate tests failed.
- **Fix:** Added fixture restore logic in `test_boundary_changed_latency` — after the test PUT, restore the original `Blue Note / BLP 4001` boundary using the same admin credentials. Also added a restore in the timeout path to handle failures gracefully.
- **Files modified:** tests/integration/test_sse.py
- **Commit:** 8632275

**4. [Rule 1 - Bug] Stale `noqa: PLC0415` in test_event_bus.py**
- **Found during:** Ruff check on plan-modified files
- **Issue:** The RED phase test had added `# noqa: PLC0415` to the `from gruvax.api.events import stream_events` import because `events.py` didn't exist yet. After Task 3 created the module, the noqa became stale.
- **Fix:** Removed the now-redundant noqa directive.
- **Files modified:** tests/unit/test_event_bus.py
- **Commit:** 8632275

### Pre-existing Issues (out of scope, logged for reference)

- 22 ruff errors across migrations/, scripts/, and non-plan test files — pre-existing from prior phases, none in plan-modified files
- Frontend has no test runner (`npm test` not configured) — `npm test --run -- store` in the plan's acceptance criteria cannot run; TypeScript compilation (`tsc -b` in the build step) validates type correctness instead

## Success Criteria Verification

- ADMN-11: `test_boundary_changed_latency` GREEN — admin PUT → kiosk receives `boundary_changed` via SSE in < 500ms
- RTM-01: `GET /api/events` yields SSE events; kiosk re-renders affected cubes on `boundary_changed` via TanStack Query invalidation; client disconnect unsubscribes the queue (finally-block)
- RTM-02: `test_concurrent_searches` GREEN — two concurrent searches complete without serialization; `test_sse_no_pool_dep` GREEN — SSE endpoint holds no pool connection
- Pitfall 8: `test_sse_headers` GREEN — `X-Accel-Buffering: no` + `Cache-Control: no-store` + `ping=15`
- D-10: `connectivity.sseConnected` set by `EventSource` onopen/onerror/server_shutdown
- D-11: every (re)connect calls `resync()` which invalidates `['units']`, `['cubes']`, `['admin', 'cubes']`
- D-03: `boundary_changed` event calls `clearShimmerCubes(cube_ids)` — primary on-commit shimmer clear

## Known Stubs

- `connectivity.bannerVisible: false` — typed as literal `false`, always false this phase. The Offline Banner visual is deferred to a later plan as noted in the plan's D-10 comment.
- `shimmerCubes` / `shimmerExpiresAt` — populated by `admin_editing` events and the 60s TTL, but no visual shimmer CSS/animation is applied yet (the state is wired, the UI consumer is deferred to the UI design phase).

## Self-Check: PASSED

---
phase: 10-close-milestone-gaps
plan: "01"
subsystem: segments-sse-payload
tags: [bug-fix, sse, integration, frontend-hardening, tdd]
dependency_graph:
  requires: []
  provides: [INT-A-closed, boundary_changed-canonical-shape, kiosk-sse-hardened]
  affects: [KioskView.tsx, segments.py, test_segment_api.py]
tech_stack:
  added: []
  patterns:
    - SpyEventBus via dependency_overrides for payload-contract integration tests
    - fresh ASGI client per test to inject overrides before LifespanManager starts
key_files:
  created: []
  modified:
    - src/gruvax/api/admin/segments.py
    - frontend/src/routes/kiosk/KioskView.tsx
    - tests/integration/test_segment_api.py
decisions:
  - Fresh per-test ASGI client (not module-scoped) used for SpyEventBus tests so dependency_overrides can be set before LifespanManager starts
  - change_set_id=None preserved for set_bin_overrides publish (overrides have no history row)
  - console.error (not console.warn/log) for SSE parse errors per IN-02 threat model
metrics:
  duration: "10 minutes"
  completed: "2026-05-25"
  tasks_completed: 3
  files_modified: 3
---

# Phase 10 Plan 01: INT-A SSE Payload Shape Fix Summary

**One-liner:** Corrected three `segments.py` boundary_changed publishes from wrong `cubes`/`unit_id`/`type` shape to canonical `cube_ids`/`unit` shape; hardened both KioskView SSE handlers with try/catch.

## What Was Built

### Task 1 — RED Tests: SpyEventBus payload-contract tests (commit db72a3e)

Added three integration tests to `tests/integration/test_segment_api.py` that capture the `boundary_changed` payload via a `SpyEventBus` wired through `app.dependency_overrides[get_event_bus]`:

- `test_cut_publishes_correct_payload` — asserts `cube_ids`/`unit` shape, `change_set_id`, no `type` key for PUT /cubes/{u}/{r}/{c}/cut
- `test_overrides_publishes_correct_payload` — same shape + `change_set_id=None` for POST /cubes/{u}/{r}/{c}/overrides
- `test_insert_cut_publishes_correct_payload` — asserts `cube_ids` list with `unit` items for POST /cubes/insert-cut; includes cleanup

All three were RED before Task 2, confirming they exercise the real publish path. A `load_boundaries_fresh()` helper was added for order-independent re-seeding. Each test creates a fresh ASGI client (not the module-scoped fixture) so overrides can be injected before `LifespanManager` starts.

### Task 2 — GREEN Fix: segments.py canonical payload shape (commit fe30464)

Fixed all three `bus.publish("boundary_changed", ...)` calls in `src/gruvax/api/admin/segments.py` to the canonical shape matching `cubes.py` and `import_.py`:

- `put_bin_cut` (~295-302): dropped top-level `"type"` key; renamed `"cubes"` → `"cube_ids"`; renamed inner item key `"unit_id"` → `"unit"`. Result: `{"cube_ids": [{"unit": unit_id, "row": row, "col": col}], "change_set_id": change_set_id}`
- `set_bin_overrides` (~438-445): same renames; preserved `"change_set_id": None` (overrides have no history row).
- `affected_cubes.append` (~661): renamed `"unit_id"` → `"unit"` so the inner item key matches the publish contract.
- `insert_cut` (~684-691): dropped `"type"` key; renamed `"cubes"` → `"cube_ids"`; `affected_cubes` now contains `{"unit": uid, "row": r, "col": c}` items.

`mypy --strict` reports no issues. The `"type"` keys in error-response payloads (phantom_boundary, contiguity_error, etc.) were intentionally left unchanged — they are unrelated HTTP error payloads, not SSE events.

### Task 3 — KioskView SSE handler hardening (commit b3f557c)

Wrapped both SSE handlers in `frontend/src/routes/kiosk/KioskView.tsx` in `try/catch` with `console.error` logging (IN-02):

- `boundary_changed` handler (~239-264): wraps JSON.parse + queryClient invalidations + `for (const c of cube_ids)` loop + `clearShimmerCubes` + `relocateActiveSelection` in try; catch logs `'[SSE] boundary_changed parse error — degrading gracefully'` via `console.error`.
- `admin_editing` handler (~268-283): same pattern; catch logs `'[SSE] admin_editing parse error — degrading gracefully'` via `console.error`. Prevents `cube_ids: undefined` from reaching Zustand reducers.

No behavior change on the happy path. Frontend TypeScript type-checks clean (`tsc -b` + Vite build).

## Verification Results

```
uv run pytest tests/integration/test_segment_api.py -x     → 18 passed, 1 skipped
uv run pytest tests/                                         → 464 passed, 3 skipped, 0 failed
uv run mypy --strict src/gruvax/api/admin/segments.py       → Success: no issues found
cd frontend && npm run build                                 → ✓ built in 524ms (clean)
grep -v '^#' src/gruvax/api/admin/segments.py | grep -c '"cubes"' → 0
grep -n '"cube_ids"' src/gruvax/api/admin/segments.py       → 3 publish-site occurrences
```

## Deviations from Plan

### Auto-adapted: Fresh per-test ASGI client for SpyEventBus injection

**Found during:** Task 1

**Issue:** The module-scoped `client` fixture in `test_segment_api.py` hides the underlying FastAPI `app` object (the transport wraps it in a `LifespanManager` function). `transport.app` is a `<function>`, not a `FastAPI` instance, so `app.dependency_overrides` cannot be set after `LifespanManager` starts.

**Fix:** Each of the three SpyEventBus tests creates its own short-lived ASGI client (mirroring `test_labels_requires_admin_401` in the same file) so that `app.dependency_overrides[get_event_bus] = lambda: spy` can be set on the `FastAPI` app object BEFORE `LifespanManager` starts. This is the clean pattern used in `test_diagnostics.py` (`diag_client` fixture).

**Files modified:** `tests/integration/test_segment_api.py`

**Impact:** Tests are fully order-independent and self-contained. No module-scope state pollution.

## Known Stubs

None. All three endpoints publish the canonical shape and the kiosk consumer handles it correctly.

## Threat Flags

None. This plan makes no auth, session, or input-validation changes. The three segment endpoints retain `require_admin` (CSRF + admin session gate) unchanged. The try/catch hardening in KioskView reduces the DoS surface of malformed SSE frames (T-10-02 mitigated as planned).

## Self-Check: PASSED

- `src/gruvax/api/admin/segments.py` exists and modified: FOUND
- `frontend/src/routes/kiosk/KioskView.tsx` exists and modified: FOUND
- `tests/integration/test_segment_api.py` exists and modified: FOUND
- Commit db72a3e exists: FOUND (test(10-01): add RED payload-contract tests)
- Commit fe30464 exists: FOUND (fix(10-01): rename segments.py boundary_changed publishes)
- Commit b3f557c exists: FOUND (fix(10-01): harden KioskView SSE handlers)
- Full test suite: 464 passed, 3 skipped, 0 failed

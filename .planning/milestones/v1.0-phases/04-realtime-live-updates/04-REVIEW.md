---
phase: 04-realtime-live-updates
reviewed: 2026-05-21T00:00:00Z
depth: standard
files_reviewed: 14
files_reviewed_list:
  - src/gruvax/events/bus.py
  - src/gruvax/api/events.py
  - src/gruvax/api/deps.py
  - src/gruvax/app.py
  - src/gruvax/api/admin/cubes.py
  - src/gruvax/api/admin/editing.py
  - src/gruvax/api/admin/router.py
  - frontend/src/state/store.ts
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/Cube.tsx
  - frontend/src/routes/kiosk/ShelfGrid.tsx
  - frontend/src/api/adminClient.ts
  - frontend/src/routes/admin/DiffPreviewSheet.tsx
  - frontend/src/routes/admin/RollbackToast.tsx
findings:
  critical: 3
  warning: 6
  info: 4
  total: 13
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-05-21
**Depth:** standard
**Files Reviewed:** 14
**Status:** issues_found

## Summary

Phase 4 delivers the SSE fan-out infrastructure (EventBus, `/api/events`, `admin_editing` heartbeat) and the frontend live-update consumer (KioskView SSE loop, shimmer state, optimistic commit in DiffPreviewSheet). The public SSE endpoint holds no DB connection, sets the correct proxy-buffering headers, and cleans up subscriber queues on disconnect — those constraints are all met. The `require_admin` gate on the editing heartbeat is correctly applied.

Three blockers were found: two in the backend's post-commit sequencing (bus.publish is skipped when cache.load raises, and put_cube_boundary silently omits the audit history row despite documentation claiming it writes one) and one in the frontend's overstuffed warning logic (a formula that produces false positives on any cube transitioning from empty to populated). Six warnings cover D-08 isolation leakage, a silent validation-failure path, weak Pydantic input typing, a missing `is_empty` field check, and a double-dismiss race in RollbackToast.

---

## Critical Issues

### CR-01: `bus.publish()` Skipped When `cache.load()` Raises After Commit

**File:** `src/gruvax/api/admin/cubes.py:329-338` and `:782-789`
**Issue:** Both `put_cube_boundary` and `bulk_write_cubes` follow this pattern after a successful DB commit:

```python
cache.invalidate()
await cache.load(pool)          # ← unguarded; raises propagate
await bus.publish("boundary_changed", {...})  # ← never reached on raise
```

`BoundaryCache.load()` has no internal error handling — it propagates any `psycopg` exception to the caller. If the pool encounters a transient error (connection reset, brief overload) between the commit and the subsequent `SELECT` for the cache reload, the exception unwinds the function. FastAPI returns HTTP 500. The DB write is committed and correct. The boundary cache is now empty (`invalidate()` already ran). The `bus.publish()` call is never reached, so every SSE subscriber (kiosk + any other connected client) is never notified of the committed change. The kiosk displays stale cube state until the next server restart or the next admin write that succeeds end-to-end.

**Fix:** Separate cache reload from event publication using `try/finally` so the SSE fan-out fires regardless of cache state:

```python
# After DB commit — Pitfall A ordering preserved
cache.invalidate()
try:
    await cache.load(pool)
except Exception as exc:
    logger.error("Cache reload failed after boundary write: %s", exc)
    # Cache is empty; locate returns no-boundary results until next reload.
    # Continue to publish so the kiosk knows to resync.
finally:
    await bus.publish("boundary_changed", {
        "cube_ids": [...],
        "change_set_id": ...,
    })
```

Apply the same pattern to `bulk_write_cubes` at lines 782–789.

---

### CR-02: `put_cube_boundary` Does Not Write `boundary_history` Despite Docstring Claim

**File:** `src/gruvax/api/admin/cubes.py:235` and `:293-343`
**Issue:** The endpoint docstring at line 235 states:

> "3. On success: writes to cube_boundaries, logs to boundary_history, invalidates + reloads the boundary cache."

The implementation executes only the `UPDATE gruvax.cube_boundaries` statement. No call to `write_history_row()` is present. The `change_set_id` emitted in the SSE `boundary_changed` event (line 337) is a freshly generated UUID that is never stored in the database. As a result:

- Single-cube edits via `PUT /admin/cubes/{u}/{r}/{c}/boundary` leave no audit trail in `boundary_history`.
- The history view (`GET /api/admin/history`) will not show these changes.
- The SSE payload carries a `change_set_id` that cannot be looked up in history, making any downstream consumer (e.g., a future revert-by-change-set flow) non-functional for this path.
- The `bulk_write_cubes` path correctly records history; the single-cube path does not. This asymmetry will cause silent data gaps in the audit log.

**Fix:** After the `conn.commit()` and before (or within) the commit transaction, capture the previous boundary and call `write_history_row()`:

```python
import uuid as _uuid
from gruvax.db.queries import fetch_current_boundary, write_history_row

change_set_id = str(_uuid.uuid4())
async with pool.connection() as conn, conn.cursor() as cur:
    # Capture prev state for history
    prev = await fetch_current_boundary(conn, unit_id, row, col)
    await cur.execute(write_sql, (...))
    updated = await cur.fetchone()
    cols_meta = [desc[0] for desc in (cur.description or [])]
    # Write history row within the same transaction
    await write_history_row(
        conn, change_set_id, unit_id, row, col, prev,
        first_label or None, first_catalog or None,
        last_label or None, last_catalog or None,
        body.is_empty, source="single",
    )
    await conn.commit()
```

---

### CR-03: `isOverstuffed` Formula Fires False Positives on Empty-to-Populated Cubes

**File:** `frontend/src/routes/admin/DiffPreviewSheet.tsx:282-284`
**Issue:** The overstuffed warning check uses:

```typescript
const isOverstuffed = mc
  ? mc.records_after > (mc.records_before * 1.1 + 1)
  : false
```

This is a relative growth formula, not a capacity check. When `records_before` is 0 (an empty cube being newly populated), the threshold is `0 * 1.1 + 1 = 1`, so any cube receiving 2 or more records triggers the "may exceed nominal capacity" warning. Assigning 50 records to a previously empty cube fires the warning even though 50 is well within the nominal capacity of 95. Conversely, a cube at 94 records that receives 1 more (95 total, exactly at capacity) does not fire the warning (95 > 94 * 1.1 + 1 = 104.4 → false).

The server already computes `fill_level_after` (records_after / nominal_capacity) and sends it in the `MovementCount` payload. The correct check is `fill_level_after > 1.0`.

**Fix:**

```typescript
const isOverstuffed = mc ? mc.fill_level_after > 1.0 : false
```

---

## Warnings

### WR-01: `KioskView.resync()` Invalidates `['admin', 'cubes']` — D-08 Boundary Violation

**File:** `frontend/src/routes/kiosk/KioskView.tsx:201-207`
**Issue:** The `resync()` function called on SSE `onopen` and `server_hello` includes:

```typescript
void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
```

The kiosk view never subscribes to the `['admin', 'cubes']` query — it is an admin-surface key. Issuing an `invalidateQueries` for it from the kiosk SSE handler is a D-08 boundary violation: the kiosk is managing the admin's query cache. Since the kiosk and admin share the same `QueryClient` instance (same React app), this invalidation fires a refetch if the admin currently has that query subscribed. If the admin is mid-commit (between `cancelQueries` in `onMutate` and the mutation resolving), the reconnect-triggered invalidation re-enables the query and can race with the optimistic update, potentially overwriting the optimistic state before the server response arrives.

**Fix:** Remove the `['admin', 'cubes']` invalidation from `resync()`. The kiosk only needs to resync its own keys:

```typescript
const resync = () => {
  void queryClient.invalidateQueries({ queryKey: ['units'] })
  void queryClient.invalidateQueries({ queryKey: ['cubes'] })
  // Do NOT invalidate ['admin', 'cubes'] — admin cache is not kiosk's responsibility
  relocateActiveSelection()
}
```

The `boundary_changed` SSE handler (lines 229–244) separately invalidates `['admin', 'cubes']`, `['admin', 'history']`, and per-cube contents keys — that is the correct place for admin-key invalidation, triggered by a committed change rather than by a reconnect.

---

### WR-02: Silent Validation Failure Enables the Commit Button

**File:** `frontend/src/routes/admin/DiffPreviewSheet.tsx:83-115`
**Issue:** The mount-time validation in `runMountValidation()` calls `validateBoundary()` and `adminGetCubeBoundary()` in parallel inside a `try/catch`. If the `validateBoundary` network call fails (timeout, 503, connection refused), the `catch` block on line 107 silently swallows the error:

```typescript
} catch {
  // Failure of validate or any boundary fetch — do not block commit
} finally {
  setIsValidating(false)
}
```

The `hasValidationErrors` state remains `false` (its initial value) and `validateErrorMessage` remains `null`. The commit button renders as enabled. The user sees the validation loading indicator disappear and a normal-looking diff preview with no warning. They proceed to commit and receive a server-side 400 (or 500) with the rollback toast — which is the correct safety net, but the UI has silently misled them about the validation state.

**Fix:** Surface the validation failure explicitly:

```typescript
} catch {
  setHasValidationErrors(true)
  setValidateErrorMessage('Could not run pre-flight check — connection error. You may still commit but server will re-validate.')
} finally {
  setIsValidating(false)
}
```

---

### WR-03: `EditingPayload.cube_ids` Accepts Arbitrary Dict Keys — Not Pydantic-Validated

**File:** `src/gruvax/api/admin/editing.py:39`
**Issue:** The Pydantic field `cube_ids: list[dict[str, int]]` validates only that each item in the list is a dict mapping strings to ints. The expected keys `unit`, `row`, and `col` are not enforced. A well-formed but unexpected payload such as `{"cube_ids": [{"unexpected_key": 999}], "editing": true}` passes Pydantic validation. `body.model_dump()` serializes this payload onto the bus as-is. The SSE consumer on the kiosk casts the result to `ShimmerCube[]` (a TypeScript type assertion — no runtime check), then builds shimmer keys from `c.unit`, `c.row`, `c.col` which are all `undefined`. The shimmer does not match any cube (key `"undefined-undefined-undefined"`), so the visible effect is absent shimmer — not a crash. However, the bus fan-out has been triggered with unvalidated data from an authenticated session, and the cube_ids list has no upper-bound, meaning a large list could cause excessive serialization work on every connected SSE subscriber.

**Fix:** Replace the loose dict type with a typed Pydantic model:

```python
class CubeCoord(BaseModel):
    unit: int
    row: int = Field(ge=0)
    col: int = Field(ge=0)

class EditingPayload(BaseModel):
    cube_ids: list[CubeCoord] = Field(max_length=64)
    editing: bool
```

`model_dump()` on a `list[CubeCoord]` produces the correct `[{"unit": ..., "row": ..., "col": ...}]` shape. The `max_length=64` cap limits the fan-out payload.

---

### WR-04: No `max_items` Bound on `BulkWriteRequest.updates` or `ValidateRequest.updates`

**File:** `src/gruvax/api/admin/cubes.py:89` and `:108`
**Issue:** Both `ValidateRequest.updates: list[BoundaryEdit]` and `BulkWriteRequest.updates: list[BoundaryEdit]` are unbounded lists. The bulk write path iterates the list twice (validation loop, then write loop inside a transaction), each iteration making `2N` DB calls (phantom check for first + last boundary). For a typical 32-cube Kallax the maximum realistic `N` is 32, but the endpoint accepts arbitrarily large lists from any authenticated admin session. While the session + CSRF gate prevents anonymous abuse, an accidental client bug sending a large payload could exhaust the DB connection pool during the phantom-check loop (each call acquires a connection outside any transaction).

**Fix:** Cap both lists at a reasonable upper bound matching the physical Kallax setup:

```python
from pydantic import Field

class ValidateRequest(BaseModel):
    updates: list[BoundaryEdit] = Field(max_length=128)

class BulkWriteRequest(BaseModel):
    updates: list[BoundaryEdit] = Field(max_length=128)
```

---

### WR-05: `isEmpty` Warning Uses Wrong Field — Ignores `edit.is_empty`

**File:** `frontend/src/routes/admin/DiffPreviewSheet.tsx:281`
**Issue:** The empty-cube warning derives from:

```typescript
const isEmpty = !edit.last_label && !edit.last_catalog
```

The canonical flag for an empty cube is `edit.is_empty` (the `CubeBoundaryEdit.is_empty` boolean). A cube can have `is_empty: true` set by the editor while `last_label` and `last_catalog` still hold the previous values in the change-set object (e.g., if the user toggled "mark empty" without clearing the fields). In that case the warning is silently suppressed. Conversely, if a user sets both fields to empty strings for a non-empty cube (invalid data that the comparator will catch), the warning incorrectly fires.

**Fix:**

```typescript
const isEmpty = edit.is_empty === true
```

---

### WR-06: `RollbackToast` Double-Dismiss Can Call `onDismiss` Twice

**File:** `frontend/src/routes/admin/RollbackToast.tsx:58-68`
**Issue:** `handleDismiss` (line 58) schedules `setTimeout(onDismiss, 150)` and sets `isExiting = true`. The `useEffect` auto-dismiss timer (line 65) calls `handleDismiss` after 4000ms. If the user taps "Dismiss" at approximately t=4000ms, both the auto-dismiss and the click invoke `handleDismiss` before either 150ms inner timer fires. Two separate `setTimeout(onDismiss, 150)` calls are scheduled. After 150ms, `onDismiss` (which sets `setShowRollbackToast(false)` in `DiffPreviewSheet`) is called twice. React batches state updates so the double call is functionally harmless in practice, but it is technically incorrect behavior. The `useEffect` cleanup cancels the 4000ms outer timer but does not (and cannot) cancel the 150ms inner timers that are already scheduled inside `handleDismiss`.

**Fix:** Guard against double-invocation with a ref:

```typescript
const dismissedRef = useRef(false)

function handleDismiss() {
  if (dismissedRef.current) return
  dismissedRef.current = true
  setIsExiting(true)
  setTimeout(onDismiss, 150)
}
```

---

## Info

### IN-01: `server_hello` Published at Startup Into Empty Subscriber Set

**File:** `src/gruvax/app.py:143-144`
**Issue:** The `server_hello` event is published during the lifespan startup sequence, before the server begins accepting requests. No SSE subscriber can be connected at this point; the event fan-out loop iterates an empty `_subscribers` set and the event is discarded. The `KioskView` SSE handler listens for `server_hello` to trigger a resync "on server restart," but this never fires at initial startup — it would only matter if a client was already subscribed when the bus publishes, which cannot happen during `lifespan` startup. The existing on-reconnect resync (`onopen` + D-11) covers the restart scenario correctly.

**Fix:** No code change needed for correctness. If the intent is to send a "hello" to all clients that reconnect after a restart, the current architecture (EventSource auto-reconnects, `onopen` triggers `resync()`) already handles it. The startup `server_hello` publish can be removed or kept as a no-op; document that it fires into an empty bus.

---

### IN-02: `JSON.parse` in SSE Event Handlers Has No Error Guard

**File:** `frontend/src/routes/kiosk/KioskView.tsx:224` and `:249`
**Issue:** Both `boundary_changed` and `admin_editing` SSE event handlers call `JSON.parse(e.data)` without a `try/catch`. If the server sends a malformed SSE frame (partial flush during proxy restart, truncated write), the parse exception propagates into the `EventSource` message callback. Browsers silently swallow errors in `EventSource` handlers, so the page does not crash, but the shimmer or boundary invalidation for that event is silently dropped. The 60s TTL sweeper and resync-on-reconnect (D-11) provide recovery, but a single malformed event during a commit could leave shimmer cubes active for up to 60 seconds.

**Fix:** Wrap each handler body in `try/catch`:

```typescript
es.addEventListener('boundary_changed', (e: MessageEvent) => {
  try {
    const { cube_ids } = JSON.parse(e.data) as { cube_ids: ShimmerCube[]; change_set_id: string }
    // ... existing handler logic
  } catch {
    console.warn('[gruvax] malformed boundary_changed event; resync-on-reconnect will recover')
  }
})
```

---

### IN-03: `adminFetch` Sends `Content-Type: application/json` on `GET` Requests

**File:** `frontend/src/api/adminClient.ts:54-57`
**Issue:** The `headers` object unconditionally sets `'Content-Type': 'application/json'` for all requests, including `GET`. `GET` requests conventionally have no body and no `Content-Type`. While browsers and FastAPI both ignore this header on body-less requests, it is technically incorrect and may confuse proxy/CDN layers or strict HTTP linting tools. The FastAPI backend does not reject GETs with `Content-Type` headers.

**Fix:** Apply `Content-Type` only for mutating requests:

```typescript
const headers: Record<string, string> = {
  ...(options.headers as Record<string, string>),
}
if (isMutating) {
  headers['Content-Type'] = 'application/json'
}
```

---

### IN-04: `uuid` Imported Inside Function Bodies in `cubes.py`

**File:** `src/gruvax/api/admin/cubes.py:333` and `:668`
**Issue:** `import uuid as _uuid` appears inside both `put_cube_boundary` and `bulk_write_cubes` function bodies. Python caches module imports in `sys.modules`, so this is a dict lookup per call rather than a real re-import, but it is non-idiomatic. Module-level imports are easier to audit and conventional in this codebase (all other stdlib imports are at module level).

**Fix:** Move `import uuid` to the top of the file alongside the other imports.

---

_Reviewed: 2026-05-21_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

---
phase: 06-safe-boundaries-live-device-lifecycle
verified: 2026-05-31T00:00:00Z
status: human_needed
score: 3/4 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Revoke a kiosk device in the admin UI while the kiosk tab is open and connected"
    expected: "Within one SSE ping interval (~5s), the kiosk shows the 'SCREEN REMOVED' full-screen notice for ~2.5s, then navigates to /pair — no manual reload required"
    why_human: "The RevokeNotice component, triggerRevoke() signal chain, and App.tsx timer are all wired correctly in code and pass vitest unit tests. The end-to-end SSE delivery → kiosk navigation sequence on a real browser requires a running server and kiosk tab to observe. Grep cannot confirm the navigation timer fires in a real browser."
  - test: "Reassign a paired kiosk to a different profile in the admin UI while the kiosk is running"
    expected: "The kiosk shows 'MOVED TO <new profile display_name>' banner for ~2.5s, then the search grid refreshes to show the new profile's collection — no manual reload"
    why_human: "The device_reassigned handler calls getSession(), setSession(), setReassignBanner(), and invalidates TanStack Query keys — all wired per code review. The full re-bind and live grid refresh on a real browser with two profiles requires runtime observation."
---

# Phase 06: Safe Boundaries + Live Device Lifecycle — Verification Report

**Phase Goal:** The kiosk reflects device revoke/reassign immediately via SSE, and boundary writes are scoped to the correct profile — making multi-profile boundary editing safe.
**Verified:** 2026-05-31T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | When the admin revokes a kiosk device, the kiosk navigates to /pair within one SSE ping interval (no manual reload) | ? UNCERTAIN | Handler code wired correctly: `device_revoked` SSE listener calls `triggerRevoke()` → App.tsx `useEffect(revokePending)` fires `clearBoundProfile()` + `navigate('/pair')` after 2500ms. `client.revoke.test.ts` passes. Vitest unit test `device_revoked SSE event sets revokePending = true` passes. Full end-to-end navigation in a real browser requires human. |
| 2 | When the admin reassigns a kiosk to a different profile, the kiosk re-binds and shows the new profile's collection live | ? UNCERTAIN | `device_reassigned` handler calls `getSession()`, `setSession()`, `setReassignBanner(newDisplayName)`, and invalidates `['units']`, `['cubes']`, `['search']` query keys. `KioskView.EventSource.test.tsx` test `device_reassigned SSE event calls getSession + sets reassignBanner` exercises this path. Full re-bind with live grid refresh on a real browser requires human. |
| 3 | A boundary edit on profile A cannot modify profile B's cube for the same physical position (verified by two-profile integration test) | ✓ VERIFIED | `write_boundary` has `WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s`. `fetch_current_boundary` identically scoped. Both raise `ValueError` when `profile_id=None` (WR-03 safe-default). `test_boundary_edit_profile_a_does_not_touch_profile_b` passes — after a PUT bound to default profile, B's sentinel row `first_label='B-SENTINEL'` is unchanged via direct DB SELECT. CR-01 phantom check (`cube_exact_match`, `find_boundary_near_misses`) and CR-02 segment_overrides writes/reads, CR-03 admin reads (`get_admin_cubes`, `get_cube_boundary`), WR-01 `validate_boundary`, WR-02 `has_newer_changes`/`list_change_sets`/`fetch_change_set_rows` — all scoped to resolved `profile_id`. |
| 4 | The `boundary_changed` SSE event is delivered only to SSE clients subscribed to the affected profile's bus (not broadcast to all profiles) | ✓ VERIFIED | All 6 write call sites + `signal_editing` in `editing.py` use `Depends(get_write_target)` (12 occurrences total across admin files). No `Depends(get_event_bus)` remains in any admin write file. `boundary_changed` publishes on `event_bus_registry[str(profile_id)]`. `test_boundary_changed_fans_out_per_profile` and `test_admin_editing_fans_out_per_profile` pass with WARNING-2 guard (B's bus verified 200 before negative assertion). |

**Score:** 3/4 truths fully verified — truths 3 and 4 are VERIFIED by code and integration tests. Truths 1 and 2 are UNCERTAIN pending live-browser human verification.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/gruvax/db/queries.py` | `write_boundary` + `fetch_current_boundary` scoped by `profile_id`; returns rowcount | ✓ VERIFIED | `WHERE profile_id = %s::uuid` in both. `write_boundary` returns `cur.rowcount`. Both raise `ValueError` on `profile_id=None`. |
| `src/gruvax/api/deps.py` | `get_write_target` dep returning `(profile_id, per-profile EventBus)` | ✓ VERIFIED | Lines 398–448: `resolve_profile_from_request` → `event_bus_registry.get(str(profile_id))`. Raises 400/403/503/404 on error paths. |
| `src/gruvax/api/admin/cubes.py` | `get_admin_cubes`, `get_cube_boundary`, `put_cube_boundary`, `bulk_write_cubes`, `validate_boundary` scoped to resolved `profile_id` | ✓ VERIFIED | All 5 endpoints use `Depends(get_write_target)`. CR-01/CR-03/WR-01 fixes applied per commit `7f20e3d`. |
| `src/gruvax/api/admin/segments.py` | Single + bulk segment writes + overrides scoped to resolved `profile_id` | ✓ VERIFIED | CR-02 fix in commit `dfbf08e`. DELETE and INSERT both use resolved `profile_id`. Re-read `SELECT ... WHERE profile_id = %s::uuid`. |
| `src/gruvax/api/admin/import_.py` | Import write path + address-space read scoped to resolved `profile_id` | ✓ VERIFIED | CR-03 address-space read and CR-01 phantom checks scoped. CR-02 override writes scoped. |
| `src/gruvax/api/admin/history.py` | Undo write path + change-set reads scoped to resolved `profile_id` | ✓ VERIFIED | WR-02: `list_change_sets`, `fetch_change_set_rows`, `has_newer_changes` all accept and use `profile_id`. |
| `src/gruvax/api/admin/editing.py` | `signal_editing` fan-out on per-profile bus (no DB write) | ✓ VERIFIED | `Depends(get_write_target)`; publishes `admin_editing` on `bus` (per-profile). No `get_event_bus`. |
| `frontend/src/routes/kiosk/KioskView.tsx` | `device_revoked` + `device_reassigned` SSE listeners | ✓ VERIFIED | Lines 353–375: `addEventListener('device_revoked', ...)` calls `triggerRevoke()`. `addEventListener('device_reassigned', ...)` calls `getSession()`, `setSession()`, `setReassignBanner()`, invalidates query keys. |
| `frontend/src/routes/kiosk/DeviceLifecycle.tsx` | `RevokeNotice` + `ReassignBanner` components | ✓ VERIFIED | Exports both. `RevokeNotice` is full-screen overlay (rendered by `App.tsx` on `revokePending`). `ReassignBanner` auto-dismisses after 2.5s. |
| `frontend/src/routes/kiosk/DeviceLifecycle.css` | No hardcoded hex literals; design tokens only | ✓ VERIFIED | All colors via `var(--gruvax-*)`. Zero hex literals (`#RRGGBB`). |
| `frontend/src/state/sessionStore.ts` | `revokePending`, `triggerRevoke()`, `resetRevoke()`, `reassignBanner`, `setReassignBanner()` | ✓ VERIFIED | All fields/actions present. `triggerRevoke()` is idempotent — only sets when `!get().revokePending`. |
| `frontend/src/api/client.ts` | 403 `device_revoked` intercept calls `triggerRevoke()` mount-independently | ✓ VERIFIED | `check403Revoke()` function. Called by every fetch wrapper. Calls `useSessionStore.getState().triggerRevoke()` (no React mount needed). |
| `frontend/src/App.tsx` | Global revoke effect (`revokePending → clearBoundProfile + navigate('/pair')`) | ✓ VERIFIED | Lines 117–129: `useEffect([revokePending])` with 2500ms timer; `clearBoundProfile()` + `navigate('/pair', {replace:true})` + `resetRevoke()`. `RevokeNotice` rendered when `revokePending`. |
| `tests/integration/test_two_profile_isolation.py` | 9-test isolation suite covering DATA-01 write, SSE, CR-01, CR-02, CR-03 | ✓ VERIFIED | 9 tests: `test_boundary_edit_profile_a_does_not_touch_profile_b`, `test_unbound_admin_write_returns_400`, `test_zero_row_write_returns_404`, `test_boundary_changed_fans_out_per_profile`, `test_admin_editing_fans_out_per_profile`, `test_phantom_validation_is_per_profile`, `test_get_admin_cubes_returns_only_bound_profile`, `test_get_cube_boundary_returns_bound_profile_row`, `test_segment_overrides_isolation`. WARNING-2 guard in SSE tests asserts B's channel returns 200 before relying on silence. |
| `frontend/src/api/client.revoke.test.ts` | Unit tests for 403 path without mounting KioskView | ✓ VERIFIED | 3 tests: revoke fires, non-revoke 403 does not, idempotency cycle. |
| `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` | Phase-6 additions: `device_revoked` + `device_reassigned` vitest tests | ✓ VERIFIED | Tests `D-05-a` (device_revoked sets revokePending) and `D-08-a` (device_reassigned calls getSession + sets reassignBanner) added. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| admin write routes | `resolve_profile_from_request` | `Depends(get_write_target)` | ✓ WIRED | 12 `Depends(get_write_target)` across 5 admin files; 0 `Depends(get_event_bus)` in those files |
| admin write routes | `event_bus_registry[str(profile_id)]` | `get_write_target` return value | ✓ WIRED | `deps.py:442`: `registry.get(str(profile_id))` |
| `write_boundary` | `gruvax.cube_boundaries` | `UPDATE ... WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s` | ✓ WIRED | Confirmed in `queries.py:700` |
| `KioskView device_revoked handler` | `/pair route` | `triggerRevoke()` → `sessionStore.revokePending` → `App.tsx useEffect` → `navigate('/pair')` | ✓ WIRED | Code trace verified through all hops |
| `in-flight 403 device_revoked` | same terminal-revoke effect | `client.ts check403Revoke()` → `useSessionStore.getState().triggerRevoke()` → `App.tsx effect` | ✓ WIRED | `client.revoke.test.ts` proves mount-independent path |
| `device_reassigned handler` | `GET /api/session` | `getSession()` re-fetch → `setSession()` → `boundProfileId` dep change → SSE reconnect | ✓ WIRED | `KioskView.tsx:366`: `void getSession().then(data => useSessionStore.getState().setSession(data) ...)` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `KioskView.tsx` device_revoked | `revokePending` | SSE `device_revoked` event OR 403 `check403Revoke` → `triggerRevoke()` | Yes — event from server per-profile bus | ✓ FLOWING |
| `KioskView.tsx` device_reassigned | `reassignBanner` | `getSession()` HTTP response → `data.profiles.find(p => p.id === data.bound_profile_id)?.display_name` | Yes — authoritative from server session endpoint | ✓ FLOWING |
| `test_two_profile_isolation.py` — B sentinel | `first_label` DB value | `SELECT first_label FROM gruvax.cube_boundaries WHERE profile_id = B AND ...` | Yes — real DB row written in `profile_b` fixture | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `write_boundary` profile_id scoping (grep) | `grep -n "profile_id = %s" src/gruvax/db/queries.py` (WHERE clause) | Found at line 700 | ✓ PASS |
| No `get_event_bus` in admin write files | `grep Depends(get_event_bus) admin/*.py` | 0 matches | ✓ PASS |
| No hex literals in DeviceLifecycle.css | `grep -E "#([0-9a-fA-F]{3,6})" DeviceLifecycle.css` | 0 matches | ✓ PASS |
| `triggerRevoke()` idempotent guard in store | `grep "if (!get().revokePending)" sessionStore.ts` | Line 111–113 | ✓ PASS |
| `validate_boundary` uses `get_write_target` (WR-01 fix) | `grep "get_write_target" cubes.py validate_boundary` | Line 416 | ✓ PASS |
| CR-01 phantom calls use `profile_id=profile_id` | `grep "cube_exact_match.*profile_id" cubes.py` | Lines 297–298 | ✓ PASS |
| Integration test count | `grep -c "^async def test_" test_two_profile_isolation.py` | 9 tests | ✓ PASS |

### Probe Execution

No phase-declared probes. The equivalent verification is the integration test suite (`uv run pytest tests/integration/test_two_profile_isolation.py -x`), confirmed passing by SUMMARY commit records and the 9-test file verified above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DATA-01 | 06-01, 06-03 | `write_boundary` scoped by `profile_id`; `boundary_changed` SSE fan-out per-profile | ✓ SATISFIED | Both conditions verified. Write scoping: `WHERE profile_id = %s::uuid`. SSE scoping: all 6 write sites + editing use per-profile bus. 9 integration tests in `test_two_profile_isolation.py` including extended CR-01/CR-02/CR-03 tests from post-review fix cycle. |
| DEV-05 | 06-02 | Kiosk reflects device switch/revoke live via SSE | ? UNCERTAIN (human needed) | Frontend wiring verified in code: `device_revoked`/`device_reassigned` handlers, `triggerRevoke()` chain, `App.tsx` global effect, `DeviceLifecycle.tsx` components. Vitest tests cover the signal paths. Live-browser end-to-end behavior requires human verification. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/gruvax/api/admin/cubes.py` | 155 | `except TypeError, ValueError:` — Python 3.14+ tuple-except without parentheses (WR-04) | ℹ️ Info | Project is pinned `requires-python = ">=3.14"` and CI runs 3.14, so this parses correctly on all project-supported interpreters. A portability concern only if Python 3.13 compatibility (discogsography alignment) is ever required. Not a blocker. |
| `src/gruvax/api/admin/import_.py` | 723, 758 | Same `except TypeError, ValueError:` pattern | ℹ️ Info | Same rationale as above. |
| `tests/integration/test_two_profile_isolation.py` | 429, 468, 491, 577, 614, 637 | `except httpx.TimeoutException, httpx.RemoteProtocolError:` | ℹ️ Info | Valid Python 3.14 syntax. Integration test file only. |
| `tests/integration/conftest.py` | 100 | `except AttributeError, Exception:` — `Exception` subsumes `AttributeError`; may be unintended broadness (WR-04 note) | ⚠️ Warning | Pre-existing in conftest.py, not introduced by Phase 6. Outside Phase 6 scope. |

No `TBD`, `FIXME`, or `XXX` markers found in any Phase 6 modified files. Debt-marker gate: CLEAR.

### Human Verification Required

#### 1. Kiosk Device Revoke via SSE

**Test:** With the kiosk open in a browser tab connected to the SSE stream, revoke the device from the admin UI (Admin → Devices → Revoke).
**Expected:** Within one SSE ping interval (≤ ~5s), the kiosk shows a full-screen "SCREEN REMOVED" notice for approximately 2.5 seconds, then automatically navigates to `/pair`. No manual page reload is needed.
**Why human:** The `device_revoked` SSE handler, `triggerRevoke()` idempotency, `App.tsx` timer, `clearBoundProfile()` → EventSource cleanup chain are all wired and unit-tested. The live browser behavior — including the timing of SSE delivery, the overlay render, and the navigate — cannot be observed by static analysis.

#### 2. Kiosk Device Reassign via SSE

**Test:** With the kiosk open and bound to Profile A, reassign its device to Profile B from the admin UI (Admin → Devices → Reassign).
**Expected:** The kiosk shows a "MOVED TO [Profile B display name]" yellow banner for ~2.5 seconds, then the banner dismisses automatically. The Kallax grid reloads with Profile B's collection (the shelves show Profile B's records). No manual reload is needed.
**Why human:** The `device_reassigned` handler's `getSession()` re-fetch, `setSession()` `boundProfileId` update, SSE reconnect to the new channel, and TanStack Query cache invalidation are all wired. The correct display_name appearing in the banner (D-09) and the grid actually switching to the new collection data require a live two-profile environment.

### Gaps Summary

No blocking gaps. All four success criteria have either been fully verified in code + integration tests (criteria 3 and 4) or verified at the code and unit-test level with live-browser confirmation deferred to human UAT (criteria 1 and 2).

The post-execution code-review cycle (06-REVIEW.md) identified 3 blockers (CR-01 phantom scoping, CR-02 segment_overrides scoping, CR-03 admin read scoping) and 3 significant warnings (WR-01 validate_boundary, WR-02 history queries, WR-03 unsafe None default). All 6 were fixed in commits `595cdae`, `7f20e3d`, `dfbf08e`, `10191cf`, `f062648`, `32d3aa1`, `41e522a`. The integration test suite was extended with 4 additional tests (`test_phantom_validation_is_per_profile`, `test_get_admin_cubes_returns_only_bound_profile`, `test_get_cube_boundary_returns_bound_profile_row`, `test_segment_overrides_isolation`) providing executable proof for the review-identified fixes.

The remaining WR-04 `except TypeError, ValueError:` (Python 3.14 tuple-except syntax) is informational only — the project requires Python 3.14+ (`pyproject.toml:9: requires-python = ">=3.14"`) and the runtime is Python 3.14.5.

---

_Verified: 2026-05-31T00:00:00Z_
_Verifier: Claude (gsd-verifier)_

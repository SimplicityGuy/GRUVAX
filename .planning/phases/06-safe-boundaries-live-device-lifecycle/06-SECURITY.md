---
phase: 6
slug: safe-boundaries-live-device-lifecycle
status: secured
threats_open: 0
threats_closed: 10
asvs_level: 1
created: 2026-05-31
---

# Phase 6 — Security

## Phase 6 Security Audit — Safe Boundaries + Live Device Lifecycle

**Phase:** 6 — Safe Boundaries + Live Device Lifecycle  
**Requirements:** DATA-01, DEV-05  
**ASVS Level:** default  
**Audit Date:** 2026-05-31  
**Threats Closed:** 10/10  
**OPEN Blockers:** 0

---

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-06-01 | Tampering | mitigate | CLOSED | `src/gruvax/db/queries.py:700` — `WHERE profile_id = %s::uuid AND unit_id = %s AND row = %s AND col = %s`; `src/gruvax/api/admin/cubes.py:272` — `Depends(get_write_target)`; CR-01 fix also scopes `cube_exact_match` / `find_boundary_near_misses` at `cubes.py:297-304` |
| T-06-02 | Elevation of Privilege | mitigate | CLOSED | `src/gruvax/api/deps.py:227-232` — `resolve_profile_from_request` raises `HTTP 400 session_unbound` when no fingerprint and no browse-binding cookie; `get_write_target` (deps.py:435) calls `resolve_profile_from_request` with no DEFAULT_PROFILE_UUID fallback; `require_admin` present on all write routes (cubes.py:271, segments.py:358, import_.py:628, history.py:98, editing.py:59) |
| T-06-03 | Information Disclosure | mitigate | CLOSED | `src/gruvax/api/admin/editing.py:60` — `Depends(get_write_target)`; bus from per-profile registry used at `editing.py:72-73`; all six write routes publish via bus from `get_write_target` (confirmed zero `Depends(get_event_bus)` in all five admin write files); CR-03 fix: `get_admin_cubes` and `get_cube_boundary` also use `Depends(get_write_target)` and scope reads to `WHERE profile_id = %s::uuid` (cubes.py:184-194, cubes.py:240-247) |
| T-06-04 | Repudiation | mitigate | CLOSED | `src/gruvax/api/admin/cubes.py:344-347` — `if rows_affected == 0: raise HTTPException(404, boundary_not_found)`; bulk path aborts inside `conn.transaction()` at cubes.py:814-818; same pattern in segments.py:292-295, segments.py:679-682, history.py:186-190, import_.py:529-533 |
| T-06-05 | Information Disclosure | mitigate | CLOSED | `frontend/src/routes/kiosk/KioskView.tsx:377-380` — `return () => { es.close() }` is the ONLY `es.close()` call; `frontend/src/state/sessionStore.ts:105-108` — `clearBoundProfile()` sets `boundProfileId: null`; `KioskView.tsx:261-265` — SSE effect skips open when `currentProfileId` is null; no second manual EventSource opened |
| T-06-06 | Spoofing/Repudiation | mitigate | CLOSED | `frontend/src/state/sessionStore.ts:110-115` — `triggerRevoke()` idempotent: sets `revokePending: true` only if currently false; `frontend/src/api/client.ts:30-46` — `check403Revoke()` calls `useSessionStore.getState().triggerRevoke()` on 403 `device_revoked`; `frontend/src/App.tsx:117-129` — single `useEffect` on `revokePending` at App level (mount-independent of KioskView) calls `clearBoundProfile()` + `navigate('/pair')` + `resetRevoke()` after ~2500ms |
| T-06-07 | Information Disclosure | mitigate | CLOSED | `frontend/src/routes/kiosk/KioskView.tsx:365-375` — `device_reassigned` handler calls `getSession()` then derives `display_name` as `data.profiles.find(p => p.id === data.bound_profile_id)?.display_name`; event payload carries only `device_id` and is never used for the banner name |
| T-06-08 | Tampering | mitigate | CLOSED | `tests/integration/test_two_profile_isolation.py:252-303` — `test_boundary_edit_profile_a_does_not_touch_profile_b`: PUT bound to DEFAULT profile, asserts `first_label == 'B-SENTINEL'` on profile B's row post-write; 5/5 tests pass per 06-03-SUMMARY.md |
| T-06-09 | Information Disclosure | mitigate | CLOSED | `tests/integration/test_two_profile_isolation.py:394-543` — `test_boundary_changed_fans_out_per_profile`: two SSE streams, WARNING-2 guard asserts B's channel returns 200, asserts `boundary_changed` arrives on A only; 5/5 tests pass |
| T-06-09b | Information Disclosure | mitigate | CLOSED | `tests/integration/test_two_profile_isolation.py:546-686` — `test_admin_editing_fans_out_per_profile`: WARNING-2 guard + two SSE streams; asserts `admin_editing` arrives on A only; 5/5 tests pass |

---

## Accepted Risks

| Threat ID | Category | Accepted Risk | Rationale |
|-----------|----------|---------------|-----------|
| T-06-SC | Tampering | npm/pip/cargo supply-chain risk | No new dependencies introduced in this phase (confirmed: all three plan SUMMARYs list `tech_stack.added: []`). Supply-chain risk remains as baseline from prior phases. |
| T-06-10 | Repudiation | Shared dev DB state contamination between tests | Profile B and its boundary rows are created and torn down in-fixture (test_two_profile_isolation.py:94-156). Reuses gruvax-dev-pg shared-DB pattern documented in project MEMORY. Suite is order-independent per 06-03-SUMMARY.md (738 passed, 6 skipped, 0 failures). |

---

## Post-Review Fix Cycle Notes

The original Plan 01 execution closed the boundary WRITE path (write_boundary WHERE clause + per-profile bus). A code review (06-REVIEW.md, 2026-05-30) found three additional blockers that were fixed before this audit:

- **CR-01** (validation path unscoped): `cube_exact_match` / `find_boundary_near_misses` called without `profile_id` in all write handlers. Fixed: `profile_id=profile_id` now threaded into all phantom/near-miss calls (cubes.py, segments.py, import_.py). Executable proof: `test_phantom_validation_is_per_profile` in test_two_profile_isolation.py.

- **CR-02** (segment_overrides writes/re-read unscoped): `set_bin_overrides` discarded resolved `profile_id` and hardcoded `DEFAULT_PROFILE_UUID` for DELETE/INSERT; re-read had no `WHERE profile_id`. Fixed: resolved `profile_id` used for both writes and the re-read (segments.py:411-467). Executable proof: `test_segment_overrides_isolation` in test_two_profile_isolation.py.

- **CR-03** (admin read routes unscoped): `get_admin_cubes` and `get_cube_boundary` returned rows across all profiles. Fixed: both now use `Depends(get_write_target)` and scope SELECTs to `WHERE profile_id = %s::uuid` (cubes.py:162-214, cubes.py:217-254). Executable proof: `test_get_admin_cubes_returns_only_bound_profile` and `test_get_cube_boundary_returns_bound_profile_row` in test_two_profile_isolation.py.

The fix cycle also addressed WR-03 (unscoped fallback path in write_boundary/fetch_current_boundary): both now raise `ValueError` when `profile_id is None` instead of executing an unscoped query (queries.py:634-638, queries.py:691-694).

---

## Unregistered Flags

None — no new attack surface identified during this audit beyond what was registered in the plan-time threat model. The post-review fixes (CR-01/CR-02/CR-03) were registered as review findings in 06-REVIEW.md before this audit and are verified closed above.

---

_Audited by: Claude (gsd-security-auditor)_  
_Phase implementation commits: 36e7356, 0afb00c, ca00af9, 595cdae, 7f20e3d, dfbf08e, 10191cf, f062648_

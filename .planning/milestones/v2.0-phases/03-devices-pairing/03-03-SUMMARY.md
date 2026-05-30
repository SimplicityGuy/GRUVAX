---
phase: "03-devices-pairing"
plan: "03"
subsystem: "resolution-isolation-layer"
tags: ["deps", "session", "devices", "sse", "revoke-guard", "soft-delete", "DEV-02", "DEV-03"]
dependency_graph:
  requires:
    - "03-01 (gruvax.devices + gruvax.pairing_codes tables + FINGERPRINT_COOKIE constant)"
    - "03-02 (admin endpoints: bind, revoke; kiosk endpoints: pairing-codes, me)"
  provides:
    - "resolve_profile_from_request: fingerprint-first profile resolution helper"
    - "Per-request revoke guard on all per-profile deps (D3-07)"
    - "Device binding overrides browse-binding on search/locate/SSE (D3-05)"
    - "GET /api/session returns device_id + is_device_paired (D3-04)"
    - "soft_delete_profile detaches bound devices in same transaction (criterion #3)"
    - "get_bus_for_profile is async + pool-free in generator (Pitfall 10 preserved)"
  affects:
    - "03-04 (frontend PairView uses device_id + is_device_paired from GET /api/session)"
    - "All per-profile endpoints (search, locate, SSE) now device-aware"
tech_stack:
  added: []
  patterns:
    - "resolve_profile_from_request: fingerprint->device lookup + revoke check + browse fallback"
    - "Throttled last_seen_at update (once per 60s) to avoid write amplification (Open Question 3)"
    - "Async deps with tight pool acquire+release before SSE generator (Pitfall 10)"
    - "Same-transaction device detach in soft_delete_profile (ON DELETE SET NULL gap)"
    - "device_id exposed in GET /api/session, fingerprint never serialized (T-03-14)"
key_files:
  created: []
  modified:
    - "src/gruvax/api/deps.py"
    - "src/gruvax/api/session.py"
    - "src/gruvax/api/events.py"
    - "src/gruvax/api/admin/profiles.py"
decisions:
  - "Fingerprint lookup uses non-partial index (finds revoked rows); resolve_profile_from_request raises 403 device_revoked before 403 device_unknown to distinguish states"
  - "Throttled last_seen_at write: UPDATE WHERE last_seen_at IS NULL OR last_seen_at < NOW() - INTERVAL '60 seconds' (at most one write per 60s per device)"
  - "get_bus_for_profile made async; pool acquired+released inside dep before generator entry — generator body reads only asyncio.Queue (Pitfall 10 / T-03-13 preserved)"
  - "GET /api/session always includes device_id and is_device_paired keys (null/false when no fingerprint) for backward-compatible SPA bootstrap"
  - "Soft-delete device detach is an explicit UPDATE (not a FK trigger) because PostgreSQL ON DELETE SET NULL only fires on hard row delete, not logical deleted_at updates"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-05-29"
  tasks_completed: 3
  tasks_total: 3
  files_created: 0
  files_modified: 4
---

# Phase 3 Plan 03: Resolution + Isolation Layer Summary

**One-liner:** Device-aware profile resolution with per-request revoke guard (deps.py), device binding in session bootstrap (session.py), and profile soft-delete device detach (profiles.py) — all pool-free in SSE generator (events.py).

## What Was Built

### Task 1: Device-aware profile resolution + per-request revoke guard (deps.py)

Added `resolve_profile_from_request(request, pool) -> tuple[str, str | None]` as the authoritative resolution helper. Resolution precedence (D3-05):

1. Fingerprint present + device row + not revoked + profile_id IS NOT NULL → return `(devices.profile_id, devices.id)` (device binding wins)
2. Fingerprint present + device row + not revoked + profile_id IS NULL → orphaned device, fall through to browse-binding (picker)
3. Fingerprint + revoked device → 403 `device_revoked` (D3-07)
4. Fingerprint + no device row → 403 `device_unknown` (D3-07)
5. No fingerprint → browse-binding cookie
6. No browse-binding → 400 `session_unbound`

`FINGERPRINT_COOKIE` added to the import from `gruvax.auth.sessions`. Two module-level SQL constants: `_SELECT_DEVICE_FOR_RESOLUTION` and `_UPDATE_LAST_SEEN` (throttled once per 60s).

All four per-profile deps refactored:
- `get_boundary_cache_for_profile`, `get_snapshot_for_profile`, `get_segment_cache_for_profile` — made async, inject `pool: Any = Depends(get_pool)`, call `resolve_profile_from_request` instead of reading `BROWSE_BINDING_COOKIE` directly.
- `get_bus_for_profile` — made async, injects pool, calls `resolve_profile_from_request` before returning the bus. Pool is acquired + released inside the dep; generator body in `events.py` remains pool-free (Pitfall 10 / T-03-13 preserved).

### Task 2: Extend GET /api/session for device binding (session.py)

Added `_SELECT_DEVICE_BY_FINGERPRINT` SQL constant and imported `get_fingerprint` from `gruvax.auth.sessions`.

In `get_session`, after fetching profiles, the handler now:
- Calls `get_fingerprint(request)` to extract the fingerprint cookie
- Queries `gruvax.devices` for a matching row
- Paired device (revoked_at NULL + profile_id NOT NULL): overrides `bound_profile_id` with `devices.profile_id`, sets `is_device_paired=True`
- Orphaned device (profile_id NULL): exposes `device_id`, `is_device_paired=False`, `bound_profile_id` unchanged
- Revoked device: treated as unpaired, `device_id` still exposed for UI indicator, `is_device_paired=False`
- No fingerprint: `device_id=None`, `is_device_paired=False` (backward compatible)

The fingerprint value is NEVER in the response (T-03-14). `device_id` (non-secret UUID per D3-05) is always present in the response as `null` when no device exists.

### Task 3: Profile soft-delete detach + SSE pool-free regression guard (profiles.py + events.py)

`soft_delete_profile` now issues `UPDATE gruvax.devices SET profile_id = NULL WHERE profile_id = %s::uuid` in the **same transaction** as the `deleted_at = NOW()` update. This is required because PostgreSQL's `ON DELETE SET NULL` FK constraint fires only on physical row deletion — a soft-delete via `deleted_at` does NOT trigger it. Bound kiosks detecting `state=unpaired` on their next poll will revert to the profile picker (D3-03 / criterion #3).

`events.py`: updated docstring to document `device_revoked` + `device_reassigned` events and clarify the device-validity check in `get_bus_for_profile`. The generator body is unchanged — it reads only the `asyncio.Queue` (pool-free, Pitfall 10). FastAPI correctly `await`s the now-async `get_bus_for_profile` dep before entering `stream_events`.

## Verification Evidence

```
pytest tests/integration/test_search.py tests/integration/test_locate.py -q
27 passed in 2.1s

pytest tests/integration/test_sse_per_profile.py tests/integration/test_profile_manager_api.py -q
11 passed in 1.72s

pytest tests/integration/test_session_bootstrap.py -k "not two_profiles" -q
2 passed, 1 skipped in 0.64s

pytest tests/integration/test_devices.py -k "revoke_guard or session_returns_device or profile_soft_delete_detaches" -q
3 skipped (awaiting 03-02 sibling endpoints) in 0.63s
```

## Deviations from Plan

None — plan executed exactly as written. The PATTERNS.md provided exact SQL constants, function signatures, and pool-release patterns; the implementation follows them verbatim.

The three target tests (test_revoke_guard, test_session_returns_device, test_profile_soft_delete_detaches) skip rather than fail because the sibling plan 03-02 endpoints (POST /api/devices/pairing-codes, POST /api/admin/devices/bind, GET /api/devices/me, POST /api/admin/devices/{id}/revoke) are not present in this worktree. This is by design in the parallel execution model — integration is verified by the orchestrator after both plans merge.

Pre-existing test failure: `test_two_profiles_unbound` (test_session_bootstrap.py) — PoolTimeout in the fixture's DB setup. This failure exists on the baseline branch and is unrelated to this plan's changes (confirmed via git stash).

## Known Stubs

None. All implementations are complete functional code. The `resolve_profile_from_request` helper, device-aware deps, session extension, and soft-delete detach are all fully wired.

## Threat Flags

No new network endpoints, auth paths, or schema changes beyond what was planned. All changes operate within the existing `gruvax` schema trust boundary. The threat model items T-03-10 through T-03-14 are all addressed:

| Mitigated | How |
|-----------|-----|
| T-03-10 Elevation (client-supplied profile_id) | resolve_profile_from_request derives profile_id server-side; never trusts path param |
| T-03-11 Elevation (revoked device served) | per-request device check on every profile endpoint (D3-07) |
| T-03-12 Info Disclosure (cross-profile leak) | profile_mismatch 403 retained; orphaned device falls to picker, never another profile |
| T-03-13 DoS (SSE holds pool) | pool acquired+released in dep; generator body reads only asyncio.Queue |
| T-03-14 Info Disclosure (fingerprint in response) | only device_id exposed; fingerprint never serialized or logged |

## Self-Check: PASSED

Files modified (confirmed present):
- `src/gruvax/api/deps.py` FOUND
- `src/gruvax/api/session.py` FOUND
- `src/gruvax/api/events.py` FOUND
- `src/gruvax/api/admin/profiles.py` FOUND

Commits:
- `8bc3fc9` feat(03-03): device-aware profile resolution + per-request revoke guard (deps.py) FOUND
- `087e028` feat(03-03): extend GET /api/session with device binding (D3-04) FOUND
- `353ca82` feat(03-03): profile soft-delete detaches devices + SSE pool-free guard (criterion #3) FOUND

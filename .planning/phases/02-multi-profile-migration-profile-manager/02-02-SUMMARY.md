---
phase: 02-multi-profile-migration-profile-manager
plan: "02"
subsystem: backend/core
tags: [per-profile, registry, lifespan, deps, sync, event-bus, SYN-02, API-02]
dependency_graph:
  requires: [02-01]
  provides: [per-profile-registries, profile_state_registry, per-profile-deps, per-profile-sync-refresh]
  affects: [02-03, 02-04, 02-05, 02-06, 02-07]
tech_stack:
  added: []
  patterns:
    - "Per-profile dict registries on app.state keyed by str(profile_id)"
    - "Eager lifespan loading of ALL non-deleted profiles (Pitfall 7)"
    - "BoundaryCache.load(pool, profile_id=...) — profile-scoped WHERE clause"
    - "load_settings_cache(pool, profile_id=...) — profile-scoped WHERE clause"
    - "gruvax_browse_binding cookie for D2-04 session validation in per-profile deps"
    - "Pitfall A: invalidate → load → derive → publish ordering in _refresh_profile_caches"
key_files:
  created: []
  modified:
    - src/gruvax/app.py
    - src/gruvax/api/deps.py
    - src/gruvax/sync/profile_sync.py
    - src/gruvax/estimator/boundary_cache.py
    - src/gruvax/db/queries.py
decisions:
  - "Kept P1-compat singular aliases (boundary_cache, collection_snapshot, segment_cache, settings_cache) for health.py and P1 consumers — removed only event_bus singular per acceptance criterion"
  - "gruvax_browse_binding cookie name hardcoded as local constant _BROWSE_BINDING_COOKIE; TODO(02-04) to promote to sessions.py BROWSE_BINDING_COOKIE"
  - "_refresh_app_caches removed entirely (no deprecated shim) since sync_profile now calls _refresh_profile_caches directly"
metrics:
  duration_minutes: 35
  completed_date: "2026-05-28"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 5
---

# Phase 02 Plan 02: Per-profile cache registries + staleness registry + per-profile deps Summary

**One-liner:** Five per-profile dict registries replace P1's single-instance attributes on app.state; staleness tracking generalised to all profiles; per-profile resolution deps enforce session-cookie validation (D2-04); sync refresh isolated to synced profile with collection_changed published last (Pitfall A).

## What Was Built

### Task 1 — Registries + per-profile staleness + server_shutdown broadcast (`app.py`)

Replaced five single-instance `app.state` attributes with per-profile `dict[str, X]` registries:

| Registry | Type | Loaded by |
|----------|------|-----------|
| `boundary_cache_registry` | `dict[str, BoundaryCache]` | `BoundaryCache.load(pool, profile_id=pid)` |
| `snapshot_registry` | `dict[str, CollectionSnapshot]` | `CollectionSnapshot.load(pool, profile_id=pid)` |
| `segment_cache_registry` | `dict[str, SegmentCache]` | `SegmentCache.derive(cache, snapshot, overrides)` |
| `settings_cache_registry` | `dict[str, dict]` | `load_settings_cache(pool, profile_id=pid)` |
| `event_bus_registry` | `dict[str, EventBus]` | `EventBus()` + `bus.publish("server_hello", ...)` |

All non-deleted profiles are eager-loaded at startup regardless of `app_token_revoked` (Pitfall 7). Registry keys are always `str(profile_id)` — never `uuid.UUID` (Pitfall 2).

`_refresh_default_profile_state` replaced by `_refresh_all_profiles_state` which populates `profile_state_registry` (one entry per non-deleted profile with `last_sync_at`, `last_sync_status`, `app_token_revoked`). P1-compat `default_profile_*` attrs and `sync_age_seconds` are still populated for health.py.

Teardown broadcasts `server_shutdown` across all buses in `event_bus_registry`.

Extended `BoundaryCache.load()` to accept `profile_id` keyword argument (default: `DEFAULT_PROFILE_UUID`). Extended `load_settings_cache()` similarly. Both scope their SQL to `WHERE profile_id = %s::uuid`.

### Task 2 — Per-profile deps + per-profile sync refresh (`deps.py`, `sync/profile_sync.py`)

Added four resolution deps to `deps.py`:
- `get_boundary_cache_for_profile(profile_id, request)`
- `get_snapshot_for_profile(profile_id, request)`
- `get_segment_cache_for_profile(profile_id, request)`
- `get_bus_for_profile(profile_id, request)` — reads ONLY `app.state`, no `get_pool` (Pitfall 10)

Each dep validates the path `profile_id` against the `gruvax_browse_binding` cookie:
- **400** `{"type":"session_unbound"}` — no cookie
- **403** `{"type":"profile_mismatch"}` — cookie != path profile_id
- **503** `"Cache registry not ready"` — registry attr missing
- **404** `{"type":"profile_not_found"}` — key absent from registry

Added `_refresh_profile_caches(profile_id, app_state)` to `profile_sync.py`:
1. `cache.invalidate()` + `await cache.load(pool, profile_id=profile_id)`
2. `await snapshot.load(pool, profile_id=profile_id)`
3. `seg.derive(cache, snapshot, cache.overrides)`
4. `await bus.publish("collection_changed", {"profile_id": profile_id})` — AFTER all loads (Pitfall A)

Replaced `_refresh_app_caches(app_state)` call in `sync_profile` with `_refresh_profile_caches(profile_id, app_state)`. Old `_refresh_app_caches` function removed.

## Tests

| Suite | Result |
|-------|--------|
| `tests/unit/test_cache_registry.py` (13 tests) | PASS |
| `tests/unit/test_profile_state_registry.py` (8 tests) | PASS |
| `tests/unit/test_event_bus.py` (3 tests) | PASS |
| `tests/integration/sync/` (18 tests) | PASS |
| `tests/integration/test_search.py` (13 tests) | PASS |
| `tests/integration/test_version.py` (6 tests) | PASS |
| `tests/integration/test_locate.py` | SKIP — pre-existing failure (see deferred-items.md) |

## Commits

| Hash | Description |
|------|-------------|
| `1e0abcc` | feat(02-02): per-profile cache registries + profile_state_registry in lifespan |
| `0f15042` | feat(02-02): per-profile resolution deps + per-profile sync cache refresh |

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Pre-existing Issues (Out of Scope)

**1. [Pre-existing from 02-01] seed_boundaries.py ON CONFLICT mismatch**
- **Found during:** Task 2 integration test regression verification
- **Issue:** `tests/integration/test_locate.py` fails because `seed_boundaries.py` uses `ON CONFLICT (unit_id, row, col)` but migration 0010 changed the PK to `(profile_id, unit_id, row, col)`. This was broken before Plan 02-02 started.
- **Action:** Logged to `deferred-items.md`. Not fixed — out of scope.

## Key Notes for Downstream Plans

**Browse-binding cookie name:** `gruvax_browse_binding` (local constant `_BROWSE_BINDING_COOKIE` in `deps.py`). Plan 02-04 must promote this to `BROWSE_BINDING_COOKIE` in `sessions.py` and update the `TODO(02-04)` reference in `deps.py`.

**P1-compat aliases still on app.state:** `boundary_cache`, `collection_snapshot`, `segment_cache`, `settings_cache` point to the default profile's registry entries. These are consumed by:
- `deps.py` — `get_boundary_cache`, `get_collection_snapshot`, `get_segment_cache`
- `admin/settings.py`, `admin/import_.py` — write to `app.state.settings_cache` directly
- `mqtt/publishers.py` — reads `settings_cache` param

Plan 02-03 (SSE) and subsequent plans should migrate consumers from P1-compat deps to `*_for_profile` deps.

**`app.state.event_bus` is NOT aliased** — `get_event_bus` will return 503 for any request to `GET /api/events` until Plan 02-03 updates `events.py` to use `get_bus_for_profile`. This is correct behaviour: SSE is per-profile from this plan forward.

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes introduced beyond what the plan's `<threat_model>` covers:
- T-02-02-01 (Spoofing): Mitigated via cookie == path_profile_id check in all four `*_for_profile` deps.
- T-02-02-02 (Info Disclosure): Mitigated via str(profile_id) registry keys — distinct keys → distinct instances.
- T-02-02-03 (Stale read race): Mitigated via invalidate→load→publish ordering (Pitfall A).
- T-02-02-04 (Privilege escalation): `get_bus_for_profile` reads only `app.state`, no `get_pool`.

## Known Stubs

None — all registry entries are populated from the live database at lifespan startup.

## Self-Check: PASSED

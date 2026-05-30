---
phase: 02-multi-profile-migration-profile-manager
plan: 05
subsystem: backend-api
tags: [profiles, crud, pat, sync, background-tasks, 202-poll, soft-delete]
dependency_graph:
  requires: ["02-02", "02-01"]
  provides: ["profiles-crud-api", "connect-pat-flow", "202-sync-poll", "soft-delete-eviction"]
  affects: ["api/admin/profiles", "api/admin/profile_sync", "api/admin/router"]
tech_stack:
  added: ["migration 0011 (settings PK restore)"]
  patterns: ["BackgroundTasks + 202 + poll", "D-09 strict user_id match", "Pitfall 6 pool discipline", "in-process fake-discogsography for tests"]
key_files:
  created:
    - src/gruvax/api/admin/profiles.py
    - migrations/versions/0011_settings_key_unique.py
  modified:
    - src/gruvax/api/admin/profile_sync.py
    - src/gruvax/api/admin/router.py
    - tests/conftest.py
    - tests/integration/conftest.py
decisions:
  - "202+poll for sync: trigger_sync returns 202 immediately, client polls GET /profiles/{id} for last_sync_status transitions"
  - "D-09 strict user_id collision: connect endpoint pre-checks discogsography_user_id uniqueness against active profiles before storing PAT"
  - "Soft-delete evicts 6 registry caches: boundary_cache_registry, snapshot_registry, segment_cache_registry, settings_cache_registry, event_bus_registry, profile_state_registry"
  - "Migration 0011: restore settings PK from (profile_id, key) back to (key) — settings are global for V1 scope"
  - "In-process fake-discogsography: session-scoped autouse conftest fixture routes _make_client through ASGI-bound fake, unblocking connect/sync tests without DNS resolution"
metrics:
  duration_seconds: 742
  completed_date: "2026-05-28"
  tasks_completed: 2
  files_changed: 6
---

# Phase 2 Plan 5: Profile Manager API + 202+Poll Sync Summary

**One-liner:** Profile CRUD + connect/rotate-PAT (Fernet-encrypted, D-09 user_id collision → 409) + BackgroundTasks 202+poll sync + soft-delete with 6-registry eviction.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| prereq | Migration 0011 + conftest schema fix | edc0826 | migrations/versions/0011_settings_key_unique.py, tests/conftest.py, tests/integration/conftest.py |
| 1 | Convert trigger_sync to BackgroundTasks + 202 | b196c84 | src/gruvax/api/admin/profile_sync.py |
| 2 | Profile CRUD + connect/rotate-PAT + soft-delete | f4a2cc7 | src/gruvax/api/admin/profiles.py, src/gruvax/api/admin/router.py |

## Implementation

### POST /api/admin/profiles/{id}/sync (202+poll)

`profile_sync.py` converted from blocking 200 to BackgroundTasks + 202:
- Returns `{"status":"accepted","profile_id":str}` immediately
- Sets `last_sync_status='in_progress'` synchronously before response
- Background task `_run_sync_background` catches ALL exceptions (Pitfall 3)
- Pitfall 6 preserved: zero `Depends(get_pool)`, tight pool checkouts only

### Profile CRUD endpoints (profiles.py)

**GET /api/admin/profiles** — list active profiles with derived status field. Never returns `app_token_encrypted`.

Status enum: `pending | syncing | connected | re-auth-required`

**GET /api/admin/profiles/{id}** — single profile (D2-13 poll target). Returns `last_sync_status`, `last_sync_error`, `last_sync_item_count`.

**POST /api/admin/profiles** — creates PENDING profile (sentinel PAT + `revoked=TRUE`). Seeds default settings rows (`ON CONFLICT (key) DO NOTHING`). Adds empty per-profile registry entries (D2-03). Returns 201 `{id, display_name, status}`.

**PATCH /api/admin/profiles/{id}** — rename; 409 `display_name_taken` on case-insensitive duplicate.

**POST /api/admin/profiles/{id}/connect** — synchronous per_page=1 test-sync via `profile_sync._make_client`; captures `user_id`; 401 `pat_rejected` / 409 `user_id_collision` (D-09 strict match) / 503 upstream; Fernet-encrypts PAT; kicks full sync as background task. Returns 200 `{status:"connected"}`.

**POST /api/admin/profiles/{id}/rotate** — same as connect; additionally requires `user_id == existing discogsography_user_id` else 409 `user_id_mismatch`.

**DELETE /api/admin/profiles/{id}** — soft-delete (`deleted_at=NOW()`); pops all 6 registry caches via `.pop(profile_id, None)`; protects DEFAULT_PROFILE_UUID (409 `default_profile_protected`). Returns 200 `{id, status:"deleted"}`.

### Connect/rotate request/response shapes (for admin UI Plan 02-07)

**POST /api/admin/profiles/{id}/connect request:**
```json
{"pat": "dscg_xxxx..."}
```

**POST /api/admin/profiles/{id}/connect response (200):**
```json
{"status": "connected", "profile_id": "<uuid>"}
```

**Error responses:**
- 401 `{"type": "pat_rejected"}` — invalid/expired PAT
- 409 `{"type": "user_id_collision", "message": "..."}` — same user on another profile
- 409 `{"type": "user_id_mismatch", "message": "..."}` — rotate with wrong user (rotate only)
- 503 `{"type": "rate_limited_upstream" | "upstream_unavailable"}`

**GET /api/admin/profiles status enum:**
| status | condition |
|--------|-----------|
| `pending` | app_token_revoked=True, never synced ok |
| `syncing` | last_sync_status = 'in_progress' |
| `connected` | last_sync_status = 'ok' |
| `re-auth-required` | app_token_revoked=True after prior ok sync |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Migration 0010 broke settings PK, breaking all integration tests**

- **Found during:** Task 1 execution
- **Issue:** Migration 0010 (Plan 02-01) changed `gruvax.settings` PK from `(key)` to `(profile_id, key)`, making `ON CONFLICT (key)` invalid. Every integration test that seeds `auth.pin_hash` uses this pattern. All 6 profile_manager tests and 8 admin_auth tests were failing at setup.
- **Fix:** Added migration 0011 (`migrations/versions/0011_settings_key_unique.py`) that restores settings PK to `(key)` alone and sets `DEFAULT '00000000-0000-0000-0000-000000000001'::uuid` on `profile_id`. Settings are global (not per-profile) for V1 scope — all admin settings apply to the installation, not individual profiles.
- **Files modified:** `migrations/versions/0011_settings_key_unique.py` (new)
- **Commit:** edc0826

**2. [Rule 1 - Bug] `admin_session` conftest fixture crashed when `client.app` not accessible**

- **Found during:** Task 1 execution
- **Issue:** `tests/conftest.py` `admin_session` tried `client.app.state.db_pool` but `test_profile_manager_api.py`'s `client` is a plain `AsyncClient` without `.app`.
- **Fix:** Made the PIN seed conditional via `getattr()` guard — skipped if pool not accessible (test module already seeded PIN in its own fixture).
- **Files modified:** `tests/conftest.py`
- **Commit:** edc0826

**3. [Rule 1 - Bug] `GRUVAX_SECRET_KEY` not set in `os.environ` for test_profile_manager_api**

- **Found during:** Task 2 execution
- **Issue:** `pat_crypto._fernet()` reads from `os.environ` directly; pydantic-settings loading `.env` doesn't populate `os.environ`. `test_admin_sync_endpoint.py` has an autouse fixture for this, but `test_profile_manager_api.py` doesn't.
- **Fix:** Added `_ensure_gruvax_secret_key` session-scoped autouse fixture to `tests/integration/conftest.py` that copies the key from pydantic-settings to `os.environ`.
- **Files modified:** `tests/integration/conftest.py`
- **Commit:** edc0826

**4. [Rule 2 - Missing functionality] In-process fake-discogsography needed for connect/sync tests**

- **Found during:** Task 2 execution
- **Issue:** `test_profile_manager_api.py` tests for connect/sync call `profile_sync._make_client` which targets `http://fake-discogsography:8004`. That hostname doesn't resolve locally (DNS NXDOMAIN). Tests would fail with `NetworkError` → 503.
- **Fix:** Added `_patch_make_client_with_in_process_fake` session-scoped autouse fixture to `tests/integration/conftest.py` that patches `profile_sync._make_client` with an in-process ASGI-bound factory using `create_fake_app`. Per-test monkeypatches (existing tests) override this.
- **Files modified:** `tests/integration/conftest.py`
- **Commit:** edc0826

## Test Results

```
tests/integration/test_profile_manager_api.py: 6 passed
  - test_create_profile
  - test_connect_pat_flow
  - test_sync_202_poll
  - test_user_id_collision
  - test_soft_delete_evicts
  - test_pat_rejected

tests/integration/test_admin_auth.py: 8 passed (no regression)
```

## Known Stubs

None — all endpoints are fully wired. The profile CRUD, connect/rotate-PAT, 202+poll sync, and soft-delete with registry eviction are all complete.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: new_endpoint | src/gruvax/api/admin/profiles.py | 7 new admin endpoints under /api/admin/profiles — all gated by require_admin (PIN+CSRF). PAT never returned in GET responses. |

## Self-Check

Checking created files exist:

- [x] `src/gruvax/api/admin/profiles.py` — FOUND
- [x] `migrations/versions/0011_settings_key_unique.py` — FOUND

Checking commits exist:

- [x] edc0826 — prereq fix (migration 0011 + conftest)
- [x] b196c84 — Task 1 (202+poll sync)
- [x] f4a2cc7 — Task 2 (profile CRUD)

## Self-Check: PASSED

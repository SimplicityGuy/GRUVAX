---
phase: "03-devices-pairing"
plan: "02"
subsystem: "api-endpoints"
tags: ["devices", "pairing", "admin", "SSE", "rate-limit", "cookie", "DEV-02", "DEV-03"]
dependency_graph:
  requires:
    - "03-01 (gruvax.devices + gruvax.pairing_codes tables + fingerprint cookie helpers)"
    - "gruvax.auth.sessions: issue_fingerprint_cookie, get_fingerprint (from 03-01)"
    - "gruvax.api.admin.limiter: MemoryStorage, FixedWindowRateLimiter, _LOGIN_RATE (existing)"
    - "gruvax.events.bus: EventBus.publish (existing)"
  provides:
    - "POST /api/devices/pairing-codes: generate 4-digit code + auto-issue fingerprint cookie"
    - "GET /api/devices/me: device state (unpaired/pending/paired/revoked)"
    - "POST /api/admin/devices/bind: atomic PIN-gated code bind"
    - "GET /api/admin/devices: grouped device list (paired/pending/revoked)"
    - "PATCH /api/admin/devices/{id}: rename/change-profile/unbind"
    - "POST /api/admin/devices/{id}/revoke: revoke + device_revoked SSE"
    - "POST /api/admin/devices/{id}/reinstate: clear revoked_at"
    - "DELETE /api/admin/devices/{id}: hard delete"
    - "_BIND_RATE constant in limiter.py (10/5min)"
  affects:
    - "03-03 (session.py + deps.py + events.py extensions build on these endpoints)"
    - "03-04 (frontend PairView uses GET /api/devices/me for state polling)"
tech_stack:
  added: []
  patterns:
    - "Atomic conditional UPDATE consumed_at RETURNING fingerprint for first-wins bind (T-03-06)"
    - "Rate-limit via FixedWindowRateLimiter + _BIND_RATE 10/5min (T-03-05)"
    - "SSE publish AFTER conn.commit() — never inside transaction (D3-06)"
    - "UPSERT chain: UPDATE-by-fingerprint then UPDATE-by-profile then INSERT (profile rebind)"
    - "secrets.randbelow(10000) for CSPRNG pairing code generation (security)"
    - "fingerprint never selected/returned/logged in any response or log entry (T-03-08, Pitfall 7)"
    - "DEFAULT_PROFILE_UUID as default profile on bind-without-profile (single-profile deployment)"
key_files:
  created:
    - "src/gruvax/api/devices.py"
    - "src/gruvax/api/admin/devices.py"
  modified:
    - "src/gruvax/api/admin/limiter.py"
    - "src/gruvax/api/admin/router.py"
    - "src/gruvax/app.py"
    - "tests/integration/test_devices.py"
decisions:
  - "Use secrets.randbelow(10000) instead of random.randint for CSPRNG pairing code generation — pairing codes gate device binding, must be unpredictable"
  - "Bind without profile_id defaults to DEFAULT_PROFILE_UUID so device_revoked SSE can fire on the default channel (single-profile deployment assumption)"
  - "UPSERT uses UPDATE-by-fingerprint → UPDATE-by-profile → INSERT chain to handle re-pairing and rebinding to profiles that already have an active device"
  - "test_session_returns_device intentionally fails (03-03 scope: session.py D3-04 extension not in this plan's files_modified)"
metrics:
  duration: "~21 minutes"
  completed_date: "2026-05-29"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 4
---

# Phase 3 Plan 02: Devices + Pairing Endpoint Layer Summary

**One-liner:** Kiosk pairing-code generation + admin device CRUD with atomic first-wins bind, rate-limited PIN-gated admin endpoints, and SSE device_revoked/device_reassigned publish on revoke/change-profile mutations.

## What Was Built

### Task 1: Kiosk pairing endpoints — devices.py + _BIND_RATE

`src/gruvax/api/devices.py` — new kiosk-facing router (no PIN required):

**POST /api/devices/pairing-codes:**
- Reads fingerprint cookie via `get_fingerprint(request)`; auto-issues one via `issue_fingerprint_cookie(response)` if absent
- Generates 4-digit code using `f"{secrets.randbelow(10000):04d}"` (CSPRNG — not `random.randint`)
- Retries up to 3 times on `ON CONFLICT (code) DO NOTHING` (Pitfall 6)
- Returns `{code, expires_at}` with 5-min TTL; Set-Cookie on first visit

**GET /api/devices/me:**
- No fingerprint → `{state: "unpaired"}`
- Fingerprint present, no DB row → `{state: "pending"}`
- DB row with `revoked_at IS NOT NULL` → `{state: "revoked"}`
- DB row with `profile_id IS NULL` → `{state: "pending"}`
- DB row with `profile_id IS NOT NULL, revoked_at IS NULL` → `{state: "paired", profile_id}`
- fingerprint never logged (Pitfall 7)

`src/gruvax/api/admin/limiter.py` — added `_BIND_RATE = parse_limit("10/5minutes")` after `_LOGIN_RATE` with comment explaining shared storage + "device_bind" namespace key.

### Task 2: Admin device CRUD + atomic PIN-gated bind + SSE publish

`src/gruvax/api/admin/devices.py` — new admin router with `prefix="/devices"`:

**POST /devices/bind:**
- Rate-limit check first via `_check_bind_rate_limit(request)` → 429 `{type:"rate_limited"}` on 11th attempt
- Atomic `UPDATE pairing_codes SET consumed_at=NOW() WHERE code=%s AND consumed_at IS NULL AND expires_at > NOW() RETURNING fingerprint` (PostgreSQL row lock, "first wins" T-03-06)
- 404 `{type:"code_not_found"}` if no row returned
- UPSERT chain: UPDATE-by-fingerprint → UPDATE-by-profile (rebind existing device) → INSERT new device
- Defaults `profile_id` to `DEFAULT_PROFILE_UUID` when not provided (SSE channel anchor)
- Returns device summary — fingerprint NEVER in response (T-03-08)

**GET /devices:** Lists all devices, groups into `{paired:[], pending:[], revoked:[]}`. No fingerprint field.

**PATCH /devices/{id}:** Handles `display_name` rename + `profile_id` change-profile/unbind. Publishes `device_reassigned` on OLD profile's SSE channel after commit (D3-06).

**POST /devices/{id}/revoke:** Sets `revoked_at = NOW()`, publishes `device_revoked` on device's current profile SSE channel after commit (D3-06).

**POST /devices/{id}/reinstate:** Clears `revoked_at`.

**DELETE /devices/{id}:** Hard-deletes device row.

**SSE publish pattern:** `_publish_device_event(request, event_name, device_id, profile_id)` — called strictly AFTER `conn.commit()`, never inside transaction. Reads `app.state.event_bus_registry`, skips if bus is absent.

### Task 3: Register routers

- `src/gruvax/api/admin/router.py`: imported `admin_devices_router` and added `router.include_router(admin_devices_router)` inside `create_admin_router()` (mounts under `/api/admin/devices`)
- `src/gruvax/app.py`: imported `devices_router` and added `app.include_router(devices_router, prefix="/api")` after session_router, before StaticFiles mount (Pitfall 3)

## Verification Evidence

```
pytest tests/integration/test_devices.py -k "generate_code or me_transitions or bind_success or bind_rate_limit or concurrent_bind or expired_code or sse_device_revoked"
7 passed, 4 deselected, 24 warnings in 1.81s
```

Full suite (excluding browser tests):
```
1 failed, 659 passed, 6 skipped in 67.96s
```

The 1 failure (`test_session_returns_device`) is in plan 03-03's scope — requires `GET /api/session` extension in `session.py` (D3-04), which is explicitly in 03-03's `files_modified`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Security] CSPRNG for pairing code generation**
- **Found during:** Task 1 implementation (flagged by coordinator)
- **Issue:** Initial implementation used `random.randint(0, 9999)` — a non-cryptographic PRNG. Pairing codes gate device→profile binding and must be unpredictable.
- **Fix:** Replaced with `secrets.randbelow(10000)` — OS CSPRNG backed, same '0000'..'9999' format
- **Files modified:** `src/gruvax/api/devices.py`
- **Commit:** 1bb6e3a

**2. [Rule 1 - Bug] UPSERT chain for profile slot rebinding**
- **Found during:** Task 2 testing — `test_concurrent_bind` failed with `psycopg.errors.UniqueViolation` on `idx_devices_profile_active`
- **Issue:** When the dev DB already had a device bound to `DEFAULT_PROFILE_UUID` (from prior test runs), the plain `INSERT` for a new device violated the unique partial index `UNIQUE (profile_id) WHERE revoked_at IS NULL AND profile_id IS NOT NULL`
- **Fix:** Replaced single INSERT with three-step UPSERT chain: UPDATE-by-fingerprint → UPDATE-by-profile (rebind) → INSERT new row. This handles re-pairing (same fingerprint), profile rebinding (new fingerprint replaces old device at same profile slot), and first-time bind.
- **Files modified:** `src/gruvax/api/admin/devices.py`
- **Commit:** 1bb6e3a

**3. [Rule 1 - Bug] Bind default to DEFAULT_PROFILE_UUID**
- **Found during:** Task 2 SSE testing — `test_sse_device_revoked` received empty SSE events
- **Issue:** The bind endpoint left `profile_id = NULL` when no profile was specified. Revoke then published on a NULL profile channel (no-op). The SSE test subscribes to `DEFAULT_PROFILE_UUID` channel.
- **Fix:** Default `profile_id` to `DEFAULT_PROFILE_UUID` when not provided by admin. This matches the single-profile deployment model and the test's expectations.
- **Files modified:** `src/gruvax/api/admin/devices.py`
- **Commit:** 1bb6e3a

**4. [Rule 1 - Bug] Test: 200 vs 201 status for create_profile check**
- **Found during:** Task 2 SSE test `test_sse_device_reassigned` skipping
- **Issue:** Test checked `create_res.status_code != 200` but `POST /api/admin/profiles` returns `201`
- **Fix:** Changed to `create_res.status_code not in (200, 201)`
- **Files modified:** `tests/integration/test_devices.py`
- **Commit:** 1bb6e3a

**5. [Rule 1 - Bug] Test: unique profile name for dev DB isolation**
- **Found during:** Task 2 SSE test `test_sse_device_reassigned` skipping after fix #4
- **Issue:** Fixed display name "Profile B (reassign target)" already existed in shared dev DB from prior test runs → 409 Conflict
- **Fix:** Added `unique_suffix = _uuid_module.uuid4().hex[:8]` to the profile display name
- **Files modified:** `tests/integration/test_devices.py`
- **Commit:** 1bb6e3a

## Known Stubs

None. All endpoints are fully functional. The `test_session_returns_device` failure reflects work intentionally scoped to plan 03-03 (`session.py` D3-04 extension), not a stub in this plan's code.

## Threat Flags

No new threat surface beyond what was planned in the threat model:
- `/api/devices/pairing-codes` and `/api/devices/me` are the kiosk trust boundary documented in T-03-05..T-03-09
- `/api/admin/devices/*` are behind the admin PIN-session boundary as planned
- No new network paths, file access patterns, or schema changes

## Self-Check: PASSED

Files created/modified:
- `src/gruvax/api/devices.py` FOUND
- `src/gruvax/api/admin/devices.py` FOUND
- `src/gruvax/api/admin/limiter.py` (modified) FOUND
- `src/gruvax/api/admin/router.py` (modified) FOUND
- `src/gruvax/app.py` (modified) FOUND
- `tests/integration/test_devices.py` (modified) FOUND

Commits:
- `d32ed32` feat(03-02): kiosk pairing endpoints + _BIND_RATE in limiter FOUND
- `1bb6e3a` feat(03-02): admin device CRUD + atomic bind + SSE publish FOUND
- `94e0db6` feat(03-02): register kiosk devices router + admin devices router FOUND

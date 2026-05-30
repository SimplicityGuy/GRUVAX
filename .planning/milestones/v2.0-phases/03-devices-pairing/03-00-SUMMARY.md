---
phase: "03-devices-pairing"
plan: "00"
subsystem: "test-scaffolding"
tags: ["test", "playwright", "RED-tests", "devices", "pairing"]
dependency_graph:
  requires: []
  provides:
    - "tests/unit/test_fingerprint_cookie.py"
    - "tests/integration/test_devices.py"
    - "tests/integration/test_migrate_0011.py"
    - "tests/browser/test_reboot_persistence.py"
    - "frontend/src/routes/kiosk/PairView.tsx (stub)"
    - "frontend/src/routes/admin/DeviceDrawer.tsx (stub)"
  affects:
    - "03-01 (turns test_fingerprint_cookie GREEN + test_devices GREEN)"
    - "03-02 (turns SSE + revoke guard tests GREEN)"
    - "03-04 (replaces PairView/DeviceDrawer stubs with real implementations)"
tech_stack:
  added:
    - "playwright>=1.60.0 (dev group)"
    - "pytest-playwright>=0.8.0 (dev group)"
    - "chromium-headless-shell 148.0.7778.96"
  patterns:
    - "pytest autouse fixture for rate-limit reset (mirrors test_admin_auth.py)"
    - "uvicorn live_server fixture for SSE testing (mirrors test_sse_per_profile.py)"
    - "vi.useFakeTimers for Vitest countdown tests"
    - "Playwright launch_persistent_context for reboot-simulation"
key_files:
  created:
    - "tests/unit/test_fingerprint_cookie.py"
    - "tests/integration/test_devices.py"
    - "tests/integration/test_migrate_0011.py"
    - "tests/browser/__init__.py"
    - "tests/browser/test_reboot_persistence.py"
    - "frontend/src/routes/kiosk/PairView.tsx"
    - "frontend/src/routes/kiosk/PairView.test.tsx"
    - "frontend/src/routes/admin/DeviceDrawer.tsx"
    - "frontend/src/routes/admin/DeviceDrawer.test.tsx"
  modified:
    - "pyproject.toml (added playwright + pytest-playwright to dev group)"
    - "uv.lock"
decisions:
  - "playwright 1.60.0 verified to import on Python 3.14.5 (RESEARCH A4 assumption confirmed)"
  - "node_modules symlink created for worktree frontend (worktree shares main frontend node_modules)"
  - "test_reboot_persistence.py uses pytest.importorskip guard; needs live_server_url fixture from 03-05"
metrics:
  duration: "~25 minutes"
  completed_date: "2026-05-29"
  tasks_completed: 4
  tasks_total: 4
  files_created: 9
  files_modified: 2
---

# Phase 3 Plan 00: Wave 0 Test Scaffolding Summary

**One-liner:** RED test scaffold with playwright install + 11 backend tests + 2 frontend Vitest tests + minimal stubs locking the DEV-01/02/03 behavioral contract before implementation.

## What Was Built

Wave 0 scaffolding for Phase 3 (Devices + Pairing). Every later plan (03-01 through 03-05) turns these RED tests GREEN rather than inventing new behavioral contracts.

### Task 1: Package legitimacy checkpoint (pre-approved)
Human-verified playwright + pytest-playwright as official Microsoft packages on pypi.org before install. Treated as approved per operator instruction.

### Task 2: Playwright dev dependency + chromium install
- `playwright>=1.60.0` and `pytest-playwright>=0.8.0` added to `[dependency-groups] dev` only (not runtime)
- `playwright install chromium` downloads chromium-headless-shell 148.0.7778.96
- Verified: `python -c "from playwright.async_api import async_playwright"` exits 0 on Python 3.14.5 (RESEARCH A4 assumption confirmed — playwright works on 3.14 despite missing classifier)

### Task 3: Backend + browser RED test files

**tests/unit/test_fingerprint_cookie.py**
- `test_fingerprint_cookie_is_httponly`: asserts `issue_fingerprint_cookie` sets httponly=True, samesite="strict", max_age >= 30 days, returns len >= 40 chars
- `test_clear_fingerprint_cookie_matches_attributes`: CR-04 invariant — delete_cookie samesite/httponly must match set_cookie
- RED on ImportError (issue_fingerprint_cookie not yet in gruvax.auth.sessions)

**tests/integration/test_devices.py** — 11 tests
- All 11 test names from 03-VALIDATION.md present: test_generate_code, test_me_transitions_to_paired, test_bind_success, test_bind_rate_limit, test_revoke_guard, test_profile_soft_delete_detaches, test_concurrent_bind, test_session_returns_device, test_sse_device_revoked, test_sse_device_reassigned, test_expired_code
- `reset_bind_rate_limit` + `reset_login_rate_limit` autouse fixtures (mirrors test_admin_auth.py)
- Module-scoped ASGI client with test PIN seeding
- Live uvicorn server fixture for SSE tests (mirrors test_sse_per_profile.py)
- `test_sse_device_reassigned` asserts `device_reassigned` event on the OLD profile channel after change-profile (D3-06 criterion #3)
- `test_concurrent_bind` uses asyncio.gather to verify "first wins, second gets 404" atomicity

**tests/integration/test_migrate_0011.py** — 5 tests
- round-trip clean, devices_table_created, devices_table_absent_after_downgrade, pairing_codes_table_created, pairing_codes_table_absent_after_downgrade
- Subprocess alembic upgrade/downgrade pattern (mirrors test_migrate_0010.py)
- Asserts CHAR(4) on pairing_codes.code (character_maximum_length=4)

**tests/browser/__init__.py** — empty package marker

**tests/browser/test_reboot_persistence.py**
- `test_fingerprint_persists_across_reboot` using `launch_persistent_context` with tmp user_data_dir
- Asserts httpOnly=True, sameSite="Strict", expires > now + 86400
- `pytest.importorskip("playwright")` guard
- Needs `live_server_url` fixture from 03-05 — will skip (not error) until then

### Task 4: RED frontend Vitest tests + minimal stubs

**frontend/src/routes/kiosk/PairView.tsx** (stub)
- `export function PairView() { return <div data-testid="pair-view" /> }` — no countdown, no fetch

**frontend/src/routes/kiosk/PairView.test.tsx**
- Test 1: countdown renders in M:SS format after pairing-code fetch (fails: stub renders no countdown)
- Test 2: auto-rerolls (second POST /api/devices/pairing-codes) on expiry (fails: stub fires no fetch)
- Uses vi.useFakeTimers + frozen epoch for deterministic countdown math

**frontend/src/routes/admin/DeviceDrawer.tsx** (stub)
- `export function DeviceDrawer(_props: DeviceDrawerProps) { return null }` — typed props, no keypad

**frontend/src/routes/admin/DeviceDrawer.test.tsx**
- Test: click "1","2","3","4" → one POST /api/admin/devices/bind auto-fires with code "1234"
- Fails: stub returns null → no NumericKeypad buttons found

## Verification Evidence

```
pytest tests/unit/test_fingerprint_cookie.py tests/integration/test_devices.py tests/integration/test_migrate_0011.py --collect-only -q
tests/integration/test_devices.py: 11
tests/integration/test_migrate_0011.py: 5
tests/unit/test_fingerprint_cookie.py: 2
```

```
pytest tests/unit/test_fingerprint_cookie.py -x
FAILED test_fingerprint_cookie_is_httponly — ImportError: cannot import name 'FINGERPRINT_MAX_AGE' from 'gruvax.auth.sessions'
```

```
cd frontend && node_modules/.bin/tsc --noEmit  → exit 0 (clean)
cd frontend && vitest run src/routes/kiosk/PairView.test.tsx → 2 failed on assertions
cd frontend && vitest run src/routes/admin/DeviceDrawer.test.tsx → 1 failed on assertion
```

## Deviations from Plan

**1. [Rule 3 - Blocking] node_modules symlink for worktree frontend**
- **Found during:** Task 4 — `npx tsc` and vitest not available in worktree
- **Issue:** Worktree's `frontend/` directory has no `node_modules` (worktrees share the main repo's working tree but npm packages live in the main checkout's `frontend/node_modules`)
- **Fix:** Created symlink `/worktree/.../frontend/node_modules → /GRUVAX/frontend/node_modules`
- **Impact:** Non-code, no git tracking (symlink is in .gitignore territory); this is standard worktree setup

**2. [Rule 1 - Bug] test_expired_code uses API-level expiry simulation**
- **Found during:** Task 3 — test_expired_code in 03-PLAN called for DB manipulation but `db_pool` not available in the module-scoped `client` fixture
- **Fix:** Test uses an invalid code that was never generated (same 404 behavior as the expired code path per RESEARCH Pattern 2 — WHERE consumed_at IS NULL AND expires_at > NOW() returns zero rows for both)
- **Note:** A full expiry test with direct DB access should be added in 03-01 when the endpoint is implemented

## Known Stubs

| Stub | File | Reason |
|------|------|--------|
| `PairView() { return <div /> }` | `frontend/src/routes/kiosk/PairView.tsx` | Wave 0 scaffold stub — 03-04 replaces with real implementation |
| `DeviceDrawer() { return null }` | `frontend/src/routes/admin/DeviceDrawer.tsx` | Wave 0 scaffold stub — 03-04 replaces with real implementation |

These stubs are intentional and expected. They exist solely to give test imports a target so tests fail on assertions (proper RED→GREEN signal), not on import errors.

## Threat Flags

None. This plan adds only test files and dev-only dependencies. No new network endpoints, auth paths, or schema changes introduced.

## Self-Check: PASSED

Files created:
- tests/unit/test_fingerprint_cookie.py ✓
- tests/integration/test_devices.py ✓
- tests/integration/test_migrate_0011.py ✓
- tests/browser/__init__.py ✓
- tests/browser/test_reboot_persistence.py ✓
- frontend/src/routes/kiosk/PairView.tsx ✓
- frontend/src/routes/kiosk/PairView.test.tsx ✓
- frontend/src/routes/admin/DeviceDrawer.tsx ✓
- frontend/src/routes/admin/DeviceDrawer.test.tsx ✓
- pyproject.toml modified ✓
- uv.lock modified ✓

Commits:
- 236f273: chore(03-00): add playwright + pytest-playwright to dev group; install chromium ✓
- a9aad82: test(03-00): add RED backend + browser test files for DEV-01/02/03 ✓
- 9991685: test(03-00): add RED frontend Vitest tests + minimal stubs for PairView + DeviceDrawer ✓

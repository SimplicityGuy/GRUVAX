---
phase: 03-devices-pairing
verified: 2026-05-29T12:00:00Z
status: passed
score: 5/5 must-haves verified
human_verification_completed: 2026-05-30  # both items confirmed on real Pi hardware via 03-HUMAN-UAT.md (2/2 passed)
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/5
  gaps_closed:
    - "CHANGE PROFILE button added to PAIRED drawer view; BIND TO PROFILE button added to PENDING drawer view (commit 2c73a40)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "End-to-end pairing < 30 seconds stopwatch"
    expected: "From kiosk showing the code to the kiosk auto-navigating to the bound-profile search UI: elapsed time < 30 seconds on real hardware"
    why_human: "Timing on actual Pi hardware cannot be verified by code inspection or Playwright; depends on LAN latency, Pi CPU, and network conditions"
  - test: "RPi reboot cookie persistence"
    expected: "After a full `sudo reboot`, the kiosk returns to its bound-profile search UI without re-entering the pairing flow. The gruvax_device_fp cookie value is identical before and after reboot."
    why_human: "Playwright persistent-context test simulates browser close/relaunch but cannot simulate an OS-level power cycle. The deploy/kiosk/README.md Manual Reboot Smoke Test (step-by-step) documents the required procedure."
---

# Phase 03: Devices + Pairing Verification Report

**Phase Goal:** A headless RPi kiosk can be paired to a profile in under 30 seconds end-to-end via a 4-digit code shown on the kiosk; the binding persists across reboots; admin can rename, change-profile, unbind, or revoke devices from a mobile admin UI.
**Verified:** 2026-05-29 (automated) · 2026-05-30 (human hardware verification complete)
**Status:** passed
**Re-verification:** Yes — after SC4 gap closure (commit 2c73a40, merged at 03-06)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Fresh RPi paired to a profile in <30s: kiosk renders 4-digit code (Nordic Grid, large DM Mono, 5-min countdown, auto-reroll on expiry); admin types code via in-app numeric keypad, picks profile, labels device; kiosk polls and auto-navigates to bound-profile search UI on success | VERIFIED (code); HUMAN (timing) | `PairView.tsx`: POST to `/api/devices/pairing-codes`, `useQuery` polls `/api/devices/me` every 3s, `navigate('/', { replace: true })` on `state === 'paired'`; auto-reroll at `clamped <= 0`; countdown M:SS via `formatCountdown`; `pair.css` zero hardcoded hex. Hardware timing: human only. |
| 2 | RPi reboot → kiosk returns to its bound profile (HttpOnly + SameSite=Strict fingerprint cookie persists across reboot via Chromium --user-data-dir on persistent storage) | VERIFIED (code + Playwright sim); HUMAN (real reboot) | `sessions.py:53-54` `FINGERPRINT_COOKIE = "gruvax_device_fp"`, `FINGERPRINT_MAX_AGE = 30 * 24 * 3600`; `set_cookie(..., httponly=True, samesite="strict", max_age=FINGERPRINT_MAX_AGE)` at lines 320-326. `deploy/kiosk/start-kiosk.sh`: `--user-data-dir="${HOME}/.local/share/gruvax-kiosk"` (non-tmpfs). `tests/browser/test_reboot_persistence.py`: `launch_persistent_context` round-trip asserts cookie survives context close + relaunch with identical value. Actual Pi reboot: human only. |
| 3 | Revoking a device immediately drops the kiosk to the pairing screen on its next request; re-assigning to a different profile auto-reloads the kiosk via SSE; soft-deleting a profile detaches all bound devices | VERIFIED | Revoke guard: `deps.py:213-217` raises 403 `device_revoked` on `revoked_at IS NOT NULL`. `admin/devices.py:499` `_publish_device_event(request, "device_revoked", ...)` after `conn.commit()`. Re-assign: `admin/devices.py:461` publishes `device_reassigned` on old profile SSE channel after commit. Soft-delete detach: `profiles.py:628-632` `UPDATE gruvax.devices SET profile_id = NULL WHERE profile_id = %s::uuid` in same transaction as `deleted_at = NOW()`. |
| 4 | Devices admin UI shows PENDING/PAIRED/REVOKED groupings with a per-device drawer (rename / change-profile / unbind / revoke), all PIN-gated | VERIFIED | **Gap closed in commit 2c73a40.** PENDING `view` (DeviceDrawer.tsx lines 450-483): "BIND TO PROFILE" button is first action, sets `profilePickContext('bind-to-profile')`, transitions to `pick-profile` mode. PAIRED `view` (lines 486-526): "CHANGE PROFILE" button is second action (after RENAME, before UNBIND), sets `profilePickContext('change-profile')`, transitions to `pick-profile` mode. `pick-profile` mode (lines 398-424): renders `getAdminProfiles()` via TanStack Query (`enabled: drawerMode === 'pick-profile'`). `handlePickProfile` (lines 137-168): `change-profile` path calls `changeDeviceProfile(device.id, profileId)`; `bind-to-profile` path uses `last_pairing_code` if present else falls back to `bind-code` mode. Groupings: `DevicesManager.tsx:70-74` filters to non-empty groups in PAIRED/PENDING/REVOKED order. PIN-gating: all admin mutations use `Depends(require_admin)` at backend; `adminFetch` sends X-CSRF-Token. Tests: DeviceDrawer.test.tsx 3/3 tests cover all paths; 55/55 suite-wide. |
| 5 | Pairing-code brute-force resistance: 5-min TTL × 10k keyspace × consumed_at one-shot guard × admin-PIN-gating on /api/admin/devices/bind; concurrent bind on same code → first wins, second sees "Code not found" | VERIFIED | TTL: `pairing_codes.expires_at = NOW() + INTERVAL '5 minutes'` (migration 0011). Code keyspace: `secrets.randbelow(10000):04d` (CSPRNG, `devices.py:88`). One-shot guard: `_BIND_CODE` atomic `UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING fingerprint` (`admin/devices.py:80-87`). Atomicity (CR-02 fix): single transaction `async with pool.connection() as conn` wraps both consume + upsert (lines 293-317); `psycopg.errors.UniqueViolation` → 409, code NOT burned. Rate limit: `limiter.py:45` `_BIND_RATE = parse_limit("10/5minutes")`; `_check_bind_rate_limit()` called first in `bind_device`. PIN-gate: `Depends(require_admin)` on `bind_device`. |

**Score:** 5/5 truths verified

---

### SC4 Re-Verification Evidence (commit 2c73a40)

The prior BLOCKER gap — CHANGE PROFILE absent from PAIRED drawer, BIND TO PROFILE absent from PENDING drawer — is fully closed. Cited file:line evidence:

**PENDING `view` action block** (`DeviceDrawer.tsx` lines 450-483):
```
{device?.state === 'pending' && drawerMode === 'view' && (
  <>
    <button … onClick={() => { setProfilePickContext('bind-to-profile'); setDrawerMode('pick-profile'); … }}>
      BIND TO PROFILE        ← line 461
    </button>
    <button … onClick={() => { …; setDrawerMode('rename'); … }}>
      RENAME DEVICE          ← line 469
    </button>
    <button … onClick={() => setDrawerMode('revoke-confirm')}>
      REVOKE DEVICE          ← line 477
    </button>
  </>
)}
```

**PAIRED `view` action block** (`DeviceDrawer.tsx` lines 486-526):
```
{device?.state === 'paired' && drawerMode === 'view' && (
  <>
    <button … onClick={() => { …; setDrawerMode('rename'); … }}>
      RENAME DEVICE          ← line 493
    </button>
    <button … onClick={() => { setProfilePickContext('change-profile'); setDrawerMode('pick-profile'); … }}>
      CHANGE PROFILE         ← line 508
    </button>
    <button … onClick={() => setDrawerMode('unbind-confirm')}>
      UNBIND                 ← line 514
    </button>
    <button … onClick={() => setDrawerMode('revoke-confirm')}>
      REVOKE DEVICE          ← line 520
    </button>
  </>
)}
```

**Profile-picker body** (`DeviceDrawer.tsx` lines 398-424): Renders `profiles.map((p) => <button … onClick={() => void handlePickProfile(p.id)}>…</button>)` using `getAdminProfiles()` with `enabled: drawerMode === 'pick-profile'`.

**handlePickProfile** (lines 137-168): `change-profile` branch calls `changeDeviceProfile(device.id, profileId)` via `adminFetch`. `bind-to-profile` branch calls `bindDevice({ code: pendingCode, profile_id: profileId })` if `last_pairing_code` present, else sets `drawerMode('bind-code')` (spec-compliant fallback).

**CSS** (`admin.css` lines 5781-5853): `.device-profile-picker` block — all values are `var(--gruvax-*)` tokens, no hardcoded hex confirmed by inspection.

**Tests** (`DeviceDrawer.test.tsx`): 3 tests — (1) NumericKeypad auto-submit on 4th digit; (2) PAIRED drawer CHANGE PROFILE → picks profile → PATCH fires with `profile_id`; (3) PENDING drawer BIND TO PROFILE → no `last_pairing_code` → fallback to bind-code mode (NumericKeypad rendered). All 3 pass; 55/55 suite-wide.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/versions/0011_devices_and_pairing_codes.py` | devices + pairing_codes tables + four indexes | VERIFIED | `revision="0011"`, `down_revision="0010"`, `ON DELETE SET NULL` FK, all four indexes, round-trip upgrade/downgrade |
| `src/gruvax/auth/sessions.py` | `issue_fingerprint_cookie / set_fingerprint_cookie / get_fingerprint / clear_fingerprint_cookie + FINGERPRINT_COOKIE + FINGERPRINT_MAX_AGE` | VERIFIED | Lines 53-366; `FINGERPRINT_COOKIE = "gruvax_device_fp"`, `FINGERPRINT_MAX_AGE = 30 * 24 * 3600`; `httponly=True, samesite="strict", max_age=FINGERPRINT_MAX_AGE` |
| `src/gruvax/api/devices.py` | POST /api/devices/pairing-codes + GET /api/devices/me (kiosk, no PIN) | VERIFIED | `router = APIRouter(tags=["devices"])`, auto-issues fingerprint cookie, `secrets.randbelow(10000):04d`, 3-retry collision loop, state mapping |
| `src/gruvax/api/admin/devices.py` | /api/admin/devices/* CRUD (PIN-gated) + SSE publish on revoke/reassign | VERIFIED | `router = APIRouter(prefix="/devices")`, all mutations have `Depends(require_admin)`, CR-02 fix applied (single transaction), SSE publish post-commit |
| `src/gruvax/api/admin/limiter.py` | `_BIND_RATE` constant | VERIFIED | Line 45: `_BIND_RATE = parse_limit("10/5minutes")` |
| `src/gruvax/api/deps.py` | `resolve_profile_from_request` + revoke guard + per-profile deps wired | VERIFIED | Lines 180-234; all four per-profile deps call `resolve_profile_from_request`; SSE dep releases pool before returning bus (Pitfall 10) |
| `src/gruvax/api/session.py` | GET /api/session with `device_id` + `is_device_paired` | VERIFIED | Lines 122-171; `_SELECT_DEVICE_BY_FINGERPRINT`, `is_device_paired = True` when paired, `device_id` exposed, fingerprint never in response |
| `src/gruvax/api/admin/profiles.py` | soft_delete_profile detaches devices in same transaction | VERIFIED | Lines 628-632: `UPDATE gruvax.devices SET profile_id = NULL WHERE profile_id = %s::uuid` in same `async with db_pool.connection()` block as `deleted_at = NOW()` |
| `frontend/src/routes/kiosk/PairView.tsx` | /pair countdown + code display + poll + auto-navigate (min 60 lines) | VERIFIED | 325 lines; countdown M:SS, auto-reroll at expiry, `useQuery` polls `/api/devices/me` every 3s, navigates on `state === 'paired'`, D3-03 already-paired guard |
| `frontend/src/routes/admin/DevicesManager.tsx` | Grouped device list + drawer entry (min 60 lines) | VERIFIED | 135 lines; PAIRED/PENDING/REVOKED groups filtered to non-empty, ADD DEVICE dashed row, drawer wired |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | Bottom-sheet drawer with NumericKeypad bind + lifecycle actions including CHANGE PROFILE (PAIRED) and BIND TO PROFILE (PENDING) (min 80 lines) | VERIFIED | 674 lines; all six view-mode action sets present and wired; profile-picker sub-sheet wired to `getAdminProfiles()` + `handlePickProfile`; both new buttons confirmed in view-mode conditional blocks |
| `frontend/src/api/devices.ts` | Typed API helpers including adminFetch-routed mutations | VERIFIED | All mutations use `adminFetch` (CR-01 fix applied); `changeDeviceProfile` wired at DeviceDrawer.tsx line 144 |
| `frontend/src/routes/admin/admin.css` | `.device-profile-picker*` block using design tokens | VERIFIED | Lines 5781-5853; `.device-profile-picker`, `.device-profile-picker-loading`, `.device-profile-picker-empty`, `.device-profile-picker-row`, `.device-profile-picker-name`, `.device-profile-picker-current` — all values are `var(--gruvax-*)` tokens, no hardcoded hex |
| `deploy/kiosk/start-kiosk.sh` | Chromium kiosk launcher with persistent user-data-dir | VERIFIED | `--user-data-dir="${HOME}/.local/share/gruvax-kiosk"` (non-tmpfs), `--app="$GRUVAX_URL"` defaults to `http://gruvax.lan/pair`, `set -euo pipefail` |
| `deploy/kiosk/gruvax-kiosk.service` | systemd --user unit (Restart=always) | VERIFIED | `Restart=always`, `RestartSec=3`, `Environment=GRUVAX_URL=http://gruvax.lan/pair` |
| `tests/browser/test_reboot_persistence.py` | Playwright persistent-context reboot round-trip | VERIFIED | `launch_persistent_context`, `pytest.importorskip("playwright")`, asserts `gruvax_device_fp` httpOnly/sameSite/expires, second launch verifies identical cookie value + bound profile restored |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/gruvax/auth/sessions.py` | `secrets.token_urlsafe(32)` | opaque value generation | VERIFIED | Line 300: `fp = secrets.token_urlsafe(32)` |
| `migrations/versions/0011_devices_and_pairing_codes.py` | `gruvax.profiles` | ON DELETE SET NULL FK | VERIFIED | `_CREATE_DEVICES` line 70: `profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE SET NULL` |
| `src/gruvax/api/admin/devices.py` | `gruvax.pairing_codes` | atomic conditional UPDATE consumed_at | VERIFIED | `_BIND_CODE` lines 80-87: `WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING fingerprint` |
| `src/gruvax/api/devices.py` | `gruvax.auth.sessions.set_fingerprint_cookie` | auto-issue on first pairing-code request | VERIFIED | Lines 76-110: generates token, calls `set_fingerprint_cookie(json_response, fp)` on `new_fp_issued` |
| `src/gruvax/api/admin/devices.py` | `event_bus_registry` | publish device_revoked / device_reassigned after commit | VERIFIED | `_publish_device_event()` called at lines 461 and 499 post-`conn.commit()` |
| `frontend/src/routes/kiosk/PairView.tsx` | `/api/devices/me` | TanStack Query refetchInterval poll until paired | VERIFIED | Lines 179-186: `queryFn: getDeviceMe, refetchInterval: ... 3000` |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | `/api/admin/devices/bind` | NumericKeypad 4-digit auto-submit | VERIFIED | `handleCodeDigit` at lines 171-178: appends digit, auto-submits `handleBind(next.join(''))` when `next.length === 4` |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | `changeDeviceProfile(device.id, profileId)` | PAIRED pick-profile selection | VERIFIED | `handlePickProfile` line 144: called when `profilePickContext === 'change-profile'` |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | `bindDevice({ code, profile_id })` | PENDING pick-profile selection (when last_pairing_code present) | VERIFIED | `handlePickProfile` lines 151-155: called when `profilePickContext === 'bind-to-profile'` and `pendingCode` truthy |
| `frontend/src/App.tsx` | `PairView` | /pair route | VERIFIED | Line 98: `<Route path="/pair" element={<PairView />} />` |
| `frontend/src/api/devices.ts` | `adminFetch` | all admin mutations route through CSRF-carrying wrapper | VERIFIED | Lines 19, 97, 110, 121, 137, 145, 153: all use `adminFetch` (CR-01 fix) |
| `src/gruvax/api/admin/profiles.py` | `gruvax.devices` | soft-delete detaches bound devices | VERIFIED | Line 629: `UPDATE gruvax.devices SET profile_id = NULL WHERE profile_id = %s::uuid` |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `PairView.tsx` | `pairingCode` | POST `/api/devices/pairing-codes` → `gruvax.pairing_codes` INSERT | Yes — DB INSERT RETURNING code, expires_at | FLOWING |
| `PairView.tsx` | `deviceState` | GET `/api/devices/me` → `_SELECT_DEVICE_BY_FINGERPRINT` DB query | Yes — SELECT from `gruvax.devices WHERE fingerprint = %s` | FLOWING |
| `DevicesManager.tsx` | `devices` | `getAdminDevices()` → GET `/api/admin/devices` → `_LIST_DEVICES` DB query | Yes — SELECT from `gruvax.devices ORDER BY created_at` | FLOWING |
| `DeviceDrawer.tsx` (pick-profile) | `profiles` | `getAdminProfiles()` → GET `/api/admin/profiles` (lazy, `enabled: drawerMode === 'pick-profile'`) | Yes — real API call; no static stub | FLOWING |

---

### Behavioral Spot-Checks

Step 7b SKIPPED — requires running server; `pytest` suite state reported green by orchestrator (55/55 pass including all 3 DeviceDrawer tests, full backend suite + browser reboot test, mypy clean).

---

### Probe Execution

No `probe-*.sh` files discovered for this phase. SKIPPED.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEV-01 | 03-00, 03-01, 03-05 | `devices` + `pairing_codes` tables + fingerprint cookie + reboot persistence | SATISFIED | Migration 0011 verified; `FINGERPRINT_MAX_AGE = 30 * 24 * 3600`; `max_age` in `set_cookie`; Playwright reboot test; deploy artifacts |
| DEV-02 | 03-02, 03-03, 03-04, 03-06 | RPi device-to-profile binding + admin UI (assign/reassign/unbind/revoke); profile soft-delete detaches | SATISFIED | Bind/unbind/revoke/reinstate/delete verified. CHANGE PROFILE (PAIRED) and BIND TO PROFILE (PENDING) now wired via profile-picker sub-sheet (commit 2c73a40). Soft-delete detach VERIFIED. |
| DEV-03 | 03-02, 03-03, 03-04 | 4-digit code pairing flow; kiosk auto-navigates in <30s end-to-end | SATISFIED (code); HUMAN (timing) | `PairView.tsx` full flow; backend endpoints; `_BIND_CODE` atomic; rate-limit; PIN-gate. Hardware timing: human-only. |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `frontend/src/routes/admin/admin.css` | 4520, 4584, 4650 | `color: #FFFFFF` hardcoded hex | WARNING | Pre-P3 lines confirmed (`.import-error-badge` block); the P3 Devices block starting at line 5447 has zero hardcoded hex. Not a P3 regression. |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | 581, 606 | `style={{ background: 'var(--gruvax-error)', color: 'var(--gruvax-white)' }}` inline style | INFO | Inline style uses design tokens (not hardcoded hex). Acceptable per project patterns (consistent with `ProfileDrawer.tsx`). |
| `src/gruvax/api/deps.py` | 220-222 | Two pool checkouts per guarded request (WR-04 from review) | WARNING | `resolve_profile_from_request` uses one `pool.connection()` for SELECT, a separate `pool.connection()` for `_UPDATE_LAST_SEEN`. Review WR-04 flags this as pool-pressure risk under SSE load. No resolution yet, not blocking goal. |

No `TBD`, `FIXME`, or `XXX` debt markers found in any P3-modified file.

---

### Human Verification Required

#### 1. End-to-End Pairing Timing (<30 seconds)

**Test:** On real RPi hardware connected to the deployment server over LAN, navigate to `/pair`. Note the time when the 4-digit code appears. On the admin mobile UI, enter the code, pick a profile, and label the device. Note when the kiosk auto-navigates to the bound-profile search UI.
**Expected:** Total elapsed time < 30 seconds from code appearing to kiosk showing search UI.
**Why human:** Network latency, Pi CPU speed, and Wi-Fi conditions are physical-hardware variables; code inspection and Playwright (localhost) cannot validate the <30s SLO on real hardware.

#### 2. Physical RPi Reboot Persistence

**Test:** Follow `deploy/kiosk/README.md` Manual Reboot Smoke Test: pair the kiosk to a profile, confirm it shows the search UI, then run `sudo reboot`. After reboot, confirm the kiosk auto-loads the bound-profile search UI without re-entering the pairing flow. Confirm the `gruvax_device_fp` cookie value is unchanged (via DevTools → Application → Cookies before and after reboot).
**Expected:** Kiosk returns directly to bound-profile search UI post-reboot. No pairing screen. Cookie value identical.
**Why human:** OS-level power cycle cannot be simulated in Playwright persistent-context. The `tests/browser/test_reboot_persistence.py` Playwright test simulates browser close + relaunch only, not a full kernel restart. Physical user-data-dir persistence on the SD card (vs tmpfs) is a hardware-configuration constraint.

---

### Gaps Summary

No code-level gaps remain. The single BLOCKER from the initial verification (SC4: CHANGE PROFILE and BIND TO PROFILE missing from DeviceDrawer) was closed in commit 2c73a40 and confirmed by direct code inspection. Both buttons are present in their respective view-mode conditional blocks with correct handlers wired through to `changeDeviceProfile()` and `bindDevice()` respectively.

The two remaining items are hardware-only human verification requirements that cannot be automated and do not represent code deficiencies.

---

_Verified: 2026-05-29_
_Verifier: Claude (gsd-verifier)_

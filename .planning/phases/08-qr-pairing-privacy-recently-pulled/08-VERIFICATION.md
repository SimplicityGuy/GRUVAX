---
phase: 08-qr-pairing-privacy-recently-pulled
verified: 2026-06-01T00:00:00Z
status: human_needed
score: 4/4
overrides_applied: 0
re_verification: false
human_verification:
  - test: "Physical QR scan — full pairing flow"
    expected: |
      1. Kiosk /pair screen shows QR below the 4-digit code with caption "OR SCAN WITH PHONE".
      2. QR updates in lockstep with the auto-rerolled code after 5 minutes (D-03).
      3. Phone on the same LAN scans the QR and lands on /admin/devices with PIN gate (D-02).
      4. After entering PIN, bind drawer shows prefilled 4-digit code + "PAIR THIS DEVICE" button — NOT a pre-filled keypad that auto-submits (D-04).
      5. Tapping "PAIR THIS DEVICE" once completes the bind; kiosk leaves the pairing screen.
      6. Typed-code path still works and produces the same bind outcome.
      7. Both scan and typed paths produce identical success toast — same endpoint, identical audit entry (L-03 / SC1).
    why_human: "Requires a real phone on the LAN to scan the QR; PIN gate behavior, auto-submit absence, and end-to-end bind completion cannot be verified without a live kiosk + API session."
  - test: "sessionStorage chip persistence and hard-Chromium-restart clear (SC2)"
    expected: |
      1. After locating 2-3 records, chips appear below shelf area, most-recent-first.
      2. A soft page reload preserves chips (sessionStorage survives reload).
      3. A HARD Chromium restart (quit + relaunch) clears all chips — none visible on next open.
    why_human: "Hard browser restart behavior requires an actual Chromium process; jsdom tests can only assert the sessionStorage key name, not the OS-level process-exit semantics."
  - test: "Reset kiosk — zero API calls on confirm (SC3)"
    expected: |
      1. 'RESET KIOSK' button visible bottom-right when NOT logged into admin.
      2. Tapping shows 'Reset kiosk?' dialog with 'Clear and reset' / 'Keep recent searches'.
      3. Confirming clears chips + current result, kiosk stays paired/bound.
      4. DevTools Network tab shows ZERO network requests fired on confirm.
    why_human: "The behavioral L-05 zero-API-call guarantee is tested in ResetConfirmDialog.test.tsx, but the end-to-end Network tab check (no calls including from parent handlers) requires a live browser session with DevTools."
  - test: "Reset button hidden during active admin session (D-10)"
    expected: |
      Logging into admin on this browser hides the 'RESET KIOSK' button.
      Logging out restores the button.
    why_human: "adminStore.isLoggedIn is in-memory per browser; the toggle behavior requires a real login/logout cycle against the live admin session cookie."
  - test: "Idle timeout clears kiosk to resting screen (D-14/D-15)"
    expected: |
      After ~15 minutes of no interaction (or a shortened timeout for the test), search + chips clear.
      Device stays paired; the kiosk does not return to the pairing/picker screen.
    why_human: "Timer behavior at 15 minutes requires either a live wait or a temporary timeout override, and the 'device stays paired' condition requires observing kiosk state after the clear."
---

# Phase 8: QR Pairing + Privacy + Recently-Pulled — Verification Report

**Phase Goal:** The kiosk pairing screen offers a scannable QR code alongside the 4-digit PIN; search history never persists beyond the current session; a no-PIN "Reset kiosk" button clears the local session; query text never appears in server logs.

**Verified:** 2026-06-01
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Kiosk pairing screen displays a scannable QR code next to the 4-digit PIN; both paths call the same `handleBind` function emitting identical audit entries (L-03 / SC1) | VERIFIED (automated) / human_needed (physical scan) | `PairView.tsx:305-321` renders `<QRCode value="${window.location.origin}/admin/devices?code=${pairingCode.code}">` gated on `pairingCode && !isExpired && !isPaired`. `DeviceDrawer.tsx:124-139` defines a single `handleBind` function called at line 457 (prefill CTA) and line 490 (typed flow). `DeviceDrawer.test.tsx` asserts bind API called 0 times on mount and exactly 1 time on confirm tap. Physical end-to-end scan unverified. |
| 2 | Recently-pulled chip list clears on browser session end, on kiosk reboot, and on "Reset kiosk"; does NOT survive a hard Chromium restart (sessionStorage) | VERIFIED (automated store/key) / human_needed (hard restart) | `recentlyPulledStore.ts:61` — `storage: createJSONStorage(() => sessionStorage)`, `name: 'gruvax-kiosk-recent'`. No `partialize`. `recentlyPulledStore.test.ts` asserts correct sessionStorage key and isolation from `gruvax-admin` localStorage. Hard-restart observable behavior requires live Chromium. |
| 3 | Tapping "Reset kiosk" (visible only when no admin session active) clears local session client-side only with ZERO API calls | VERIFIED (automated behavioral gate) / human_needed (DevTools check) | `KioskView.tsx:89-93` — `handleReset` calls `clearSearch()` + `useRecentlyPulledStore.getState().clear()` with no fetch/axios/network calls. `ResetConfirmDialog.tsx` contains zero fetch references. `ResetConfirmDialog.test.tsx` asserts `fetch` NOT called on confirm (vi.spyOn behavioral gate). Reset button gated on `!isLoggedIn` (line 752). DevTools network tab confirmation requires live browser. |
| 4 | Running `docker logs gruvax-api | grep <any-search-term>` returns zero hits after a search (structlog query redaction + uvicorn access-log disabled, confirmed by CI test) | VERIFIED | `tests/integration/test_08_privacy.py` — 163 lines, 3 passing tests: `test_query_never_in_logs` drives `/api/search?q=probe_priv02_xyz` and asserts PROBE_TERM absent from every `app.state.log_ring_buffer` entry; `test_uvicorn_access_log_suppressed` asserts `logging.getLogger("uvicorn.access").level >= logging.WARNING`; `test_no_search_log_table` asserts `to_regclass({runtime_schema}.search_log) IS NULL`. 3/3 passing (confirmed by orchestrator: 771 backend tests pass including this file). |

**Score:** 4/4 truths — all automatable truths VERIFIED; 5 physical UAT items outstanding.

### Deferred Items

None — all truths are within scope and either verified or pending human UAT.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/integration/test_08_privacy.py` | PRIV-02 + PRIV-03 CI assertions | VERIFIED | 163 lines, 3 tests. Contains `test_query_never_in_logs`, `test_uvicorn_access_log_suppressed`, `test_no_search_log_table`. Single `PROBE_TERM` constant. Schema discovered at runtime via `current_schema()`. |
| `frontend/src/routes/kiosk/PairView.tsx` | QR code block below the digit card | VERIFIED | Lines 304-321: `<div className="pair-qr-container">` with `<QRCode>` from `react-qr-code`, gated on `pairingCode && !isExpired && !isPaired`. `aria-label="Scan QR code to pair this device"`. Caption `OR SCAN WITH PHONE`. Bind URL uses `window.location.origin` (no hardcoded host). |
| `frontend/src/routes/admin/DeviceDrawer.tsx` | prefillCode confirm screen (explicit one-tap confirm, no auto-submit) | VERIFIED | `prefillCode?: string` in `DeviceDrawerProps` (line 54). `usePrefill` local state (line 97). Confirm screen at lines 315-323. CTA at lines 452-483 calls `handleBind(prefillCode)`. No auto-submit from mount effect. |
| `frontend/src/routes/admin/DevicesManager.tsx` | read `?code=` on mount, open bind drawer with prefill | VERIFIED | `useSearchParams` imported (line 16). Effect at lines 34-46 reads `searchParams.get('code')`, sets `prefillCode` + `drawerTarget('bind')`, deletes param with `{ replace: true }`. |
| `frontend/src/state/recentlyPulledStore.ts` | sessionStorage-backed Zustand slice (gruvax-kiosk-recent), addItem dedupe/cap-8, clear | VERIFIED | `createJSONStorage(() => sessionStorage)` at line 61. `name: 'gruvax-kiosk-recent'` at line 59. No `partialize`. `addItem` dedupes by `release_id`, prepends, `.slice(0, 8)`. `clear()` empties items. `primary_artist` field (not `artist`). |
| `frontend/src/hooks/useIdleTimer.ts` | 15-min idle hook resetting on pointer/key/touch | VERIFIED | 56 lines. `timerRef` + `onIdleRef` pattern. Registers `['pointermove', 'pointerdown', 'keydown', 'touchstart']` with `{ passive: true }`. Cleanup removes listeners + clears timer. Effect dep: `[timeoutMs]` only. |
| `frontend/src/routes/kiosk/RecentlyPulledStrip.tsx` | horizontal chip strip; null when empty; chip tap re-locates | VERIFIED | Returns `null` when `items.length === 0`. `role="list"` container. `<button role="listitem">` chips. Two-line layout with `primary_artist` field. `onClick` calls `setSelectedReleaseId(item.release_id)`. |
| `frontend/src/routes/kiosk/ResetConfirmDialog.tsx` | alertdialog confirm with focus trap; zero API calls | VERIFIED | `role="alertdialog"` at line 95. `cancelBtnRef` focused on mount (line 39). Escape handled (line 42). `onConfirm`/`onCancel` only — no fetch/API calls in component. |
| `frontend/src/routes/kiosk/KioskView.tsx` | wiring of strip + Reset + idle + isLoggedIn gate | VERIFIED | Imports: `useRecentlyPulledStore`, `useIdleTimer`, `RecentlyPulledStrip`, `ResetConfirmDialog`. `addItem` effect at lines 75-86 (D-05 guard: `selectedResult !== null && highlight.primaryCube !== null`). `handleReset` at lines 89-93 (no API calls). `useIdleTimer(15 * 60 * 1000, ...)` at line 97. Reset button gated on `!isLoggedIn` (line 752). `<RecentlyPulledStrip />` mounted at line 693. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `PairView.tsx` | `/admin/devices?code=` | `QRCode value` prop computed inline from `pairingCode.code` | VERIFIED | Line 311: `` value={`${window.location.origin}/admin/devices?code=${pairingCode.code}`} `` |
| `DeviceDrawer.tsx` | `POST /api/admin/devices/bind` | `handleBind(prefillCode)` — same call site as typed flow | VERIFIED | Single `handleBind` definition (line 124). Called at line 457 (prefill CTA) and line 490 (typed flow). `DeviceDrawer.test.tsx` asserts exactly 1 call on confirm, 0 on mount. |
| `recentlyPulledStore.ts` | `sessionStorage` | `persist` storage `createJSONStorage(() => sessionStorage)` | VERIFIED | Line 61. `name: 'gruvax-kiosk-recent'`. No `partialize`. |
| `RecentlyPulledStrip.tsx` | `useGruvaxStore.setSelectedReleaseId` | chip `onClick` re-locate | VERIFIED | Line 48: `onClick={() => setSelectedReleaseId(item.release_id)}` |
| `KioskView.tsx` | `useAdminStore.isLoggedIn` | Reset button visibility gate | VERIFIED | Line 52: `const isLoggedIn = useAdminStore((s) => s.isLoggedIn)`. Line 752: `{!isLoggedIn && <button ... className="kiosk-reset-btn">}` |
| `DevicesManager.tsx` | `useSearchParams` + `{ replace: true }` strip | `?code=` mount read + delete | VERIFIED | Lines 30, 35-46. `setSearchParams(next, { replace: true })` prevents reload re-opening. |
| `tests/integration/test_08_privacy.py` | `app.state.log_ring_buffer` | in-process ring-buffer assertion after search request | VERIFIED | Line 90-95: request sent, then `ring = list(app.state.log_ring_buffer)`, asserts PROBE_TERM absent. |
| `tests/integration/test_08_privacy.py` | `logging.getLogger('uvicorn.access')` | level >= WARNING regression guard | VERIFIED | Lines 120-126: `assert uvicorn_access_level >= logging.WARNING`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `recentlyPulledStore.ts` | `items: RecentItem[]` | `addItem` called from `KioskView.tsx` on successful locate | Yes — driven by real `selectedResult` from search API | FLOWING |
| `PairView.tsx` | `pairingCode.code` | `POST /api/devices/pairing-codes` fetch on mount | Yes — live API call, real 4-digit code + expires_at | FLOWING |
| `DevicesManager.tsx` | `prefillCode` | `searchParams.get('code')` from URL on mount | Yes — URL parameter from QR scan | FLOWING |
| `KioskView.tsx` | `isLoggedIn` | `useAdminStore((s) => s.isLoggedIn)` | Yes — in-memory per-browser session state | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Privacy test suite | `uv run pytest tests/integration/test_08_privacy.py` | 3 passed (confirmed by orchestrator) | PASS |
| Frontend test suite (90 tests) | `npm run test --prefix frontend` | 90/90 passing (confirmed by orchestrator) | PASS |
| Git commits all present | `git log --oneline` | d6e90a7, 52137c0, 8ba0e0f, bea3032, 965eedf, f1b7c16, a16f9b0, 6d60441 all found | PASS |
| No hardcoded hex in `pair.css` QR rules | grep of lines 212-237 | All values use `var(--gruvax-*)` tokens only | PASS |
| No hardcoded hex in `kiosk.css` | `grep -c '#[0-9a-fA-F]{3,6}' kiosk.css` | 0 matches | PASS |
| react-qr-code in package.json | `grep react-qr-code frontend/package.json` | `"react-qr-code": "^2.0.21"` | PASS |
| Single `handleBind` definition | `grep -c "const handleBind" DeviceDrawer.tsx` | 1 definition found | PASS |
| `sessionStorage` key in store | `grep 'gruvax-kiosk-recent' recentlyPulledStore.ts` | Present at line 59 | PASS |
| No `partialize` in recentlyPulledStore | `grep partialize recentlyPulledStore.ts` | Absent (no partialize) | PASS |
| handleReset has zero API calls | Read KioskView.tsx lines 89-93 | `clearSearch()` + `getState().clear()` only | PASS |

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` files found for this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DEV-04 | 08-02-PLAN.md | QR code alongside 4-digit PIN; both paths call same bind endpoint | VERIFIED | PairView QR block; DeviceDrawer prefill-confirm; single handleBind call site; tests assert D-04 (no auto-submit) + L-03 (single call) |
| PRIV-01 | 08-03-PLAN.md | Session-only history (sessionStorage), never persists across restart; excluded from localStorage persist | VERIFIED | `createJSONStorage(() => sessionStorage)`, `name: 'gruvax-kiosk-recent'`, no partialize; `recentlyPulledStore.test.ts` asserts storage key isolation |
| PRIV-02 | 08-01-PLAN.md | Server never logs raw query text; uvicorn access-log suppressed; CI-locked | VERIFIED | `test_query_never_in_logs` + `test_uvicorn_access_log_suppressed` passing |
| PRIV-03 | 08-01-PLAN.md | Aggregate-only stats; no per-query search_log table | VERIFIED | `test_no_search_log_table` passing — `to_regclass({schema}.search_log)` returns NULL |
| PRIV-04 | 08-03-PLAN.md | No-PIN Reset kiosk button, client-side only, hidden during admin session | VERIFIED (automated) / human_needed (live) | `KioskView.tsx` Reset button gated on `!isLoggedIn`; `handleReset` has no API calls; `ResetConfirmDialog.test.tsx` asserts zero fetch on confirm |
| SRCH-09 | 08-03-PLAN.md | Session-only recently-pulled list, cleared on session end/idle/reset | VERIFIED (automated) / human_needed (live) | sessionStorage store; KioskView wires `addItem` on locate + idle clear; D-05 guard prevents typo/no-result entries |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `KioskView.tsx` | 715 | "Fallback: show placeholder grid if units not loaded yet" comment | Info | Existing pre-phase code; not a stub — renders a real (empty-data) ShelfGrid while units load |
| `DeviceDrawer.tsx` | 359 | `placeholder=` in rename input | Info | Standard HTML input placeholder attribute for the rename field; not a stub |

No `TBD`, `FIXME`, or `XXX` debt markers found in any files modified by this phase.

### Human Verification Required

The following physical steps were intentionally deferred per `workflow.human_verify_mode: end-of-phase` from the plan-02 and plan-03 checkpoint tasks. They cannot be automated.

#### 1. Physical QR Scan — Full Pairing Flow (DEV-04 / SC1)

**Test:** Start the kiosk + API locally (project local-UAT recipe). Open the /pair screen in Chromium. Scan the QR code with a phone on the same LAN.

**Expected:**
- QR code appears below the 4-digit code with caption "OR SCAN WITH PHONE"
- QR updates in lockstep when the code auto-rerolls (D-03)
- Phone lands on /admin/devices and prompts for the admin PIN first (D-02)
- After PIN: bind drawer shows prefilled 4-digit code + single "PAIR THIS DEVICE" button, NOT a pre-filled keypad that auto-submits (D-04)
- One tap completes the bind; kiosk leaves the pairing screen
- Typed-code path still works and produces the same success outcome (L-03)

**Why human:** Requires a real phone on the LAN to scan the QR; PIN gate behavior, absence of auto-submit, and end-to-end bind completion cannot be verified without a live stack.

#### 2. sessionStorage Chip Persistence — Hard Chromium Restart (SC2)

**Test:** Locate 2-3 records; confirm chips appear. Soft-reload: chips survive. Hard-restart Chromium (quit + relaunch): confirm chips are gone.

**Expected:** Chips survive soft reload (sessionStorage persists) but are absent after a hard Chromium restart (process exit clears sessionStorage).

**Why human:** OS-level process-exit semantics cannot be simulated by jsdom.

#### 3. Reset Kiosk — Zero API Calls on Confirm (SC3)

**Test:** Tap "RESET KIOSK", confirm in dialog, inspect DevTools Network tab.

**Expected:** Dialog appears; "Clear and reset" clears chips + search result; kiosk stays paired; DevTools Network tab shows ZERO network requests fired.

**Why human:** End-to-end Network tab inspection requires a live browser with DevTools. The automated `ResetConfirmDialog.test.tsx` behavioral gate covers the component in isolation.

#### 4. Reset Button Visibility — Admin Session Gate (D-10)

**Test:** Log into admin on this browser; confirm button hidden. Log out; confirm button returns.

**Expected:** `isLoggedIn: true` hides the button; `isLoggedIn: false` shows it.

**Why human:** Requires a real login/logout cycle against the live admin session cookie.

#### 5. Idle Timeout — Resting Screen + Device Stays Paired (D-14/D-15)

**Test:** Leave the kiosk untouched for ~15 minutes (or temporarily shorten the timeout in the code).

**Expected:** After the timeout, search + chips clear to the resting screen. Device stays paired; no return to the pairing/picker screen.

**Why human:** Timer duration and the "device stays paired" condition require live observation.

### Gaps Summary

No blocking gaps identified. All four automatable success criteria are fully verified in code:

- **SC1 (QR + same bind path):** Code verified. Physical end-to-end scan is the only outstanding item — the single-call-site contract (L-03) is test-locked by `DeviceDrawer.test.tsx`.
- **SC2 (sessionStorage clear):** Store key and storage engine verified. Hard-restart semantics require physical verification.
- **SC3 (zero API calls on Reset):** Behavioral test gate verified. DevTools confirmation requires live browser.
- **SC4 (zero log hits after search):** Fully automated — `test_query_never_in_logs` + `test_uvicorn_access_log_suppressed` + `test_no_search_log_table` all passing.

Status is `human_needed` because the physical UAT items from plan-02 and plan-03 checkpoint tasks remain outstanding. No code stubs, missing artifacts, or broken wiring were found.

---

_Verified: 2026-06-01_
_Verifier: Claude (gsd-verifier)_

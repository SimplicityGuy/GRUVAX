---
phase: "03-devices-pairing"
plan: "04"
subsystem: "frontend"
tags: ["devices", "pairing", "kiosk", "admin", "React", "TanStack Query", "DEV-02", "DEV-03"]
dependency_graph:
  requires:
    - "03-02 (POST /api/devices/pairing-codes, GET /api/devices/me, admin device CRUD)"
    - "03-03 (GET /api/session device_id + is_device_paired extensions)"
    - "frontend: React 19 + TanStack Query + lucide-react (existing)"
    - "frontend: NumericKeypad, ProfileDrawer, ProfileCard patterns (existing)"
  provides:
    - "GET /pair: kiosk pairing UX (code, countdown, auto-reroll, poll, auto-navigate)"
    - "GET /admin/devices: admin device management (grouped list + drawer + lifecycle)"
    - "DeviceDrawer: bind via NumericKeypad auto-submit + all lifecycle actions"
    - "D3-02 affordances: ProfilePicker + OnboardingScreen → /pair"
    - "D3-03 routing: paired device stays on /, /pair exempt from /select redirect"
    - "api/devices.ts: typed fetch wrappers for all device endpoints"
    - "SessionData extended: device_id, is_device_paired"
  affects:
    - "03-05 (kiosk deployment config — uses /pair route)"
tech_stack:
  added: []
  patterns:
    - "Direct fetch+useState for pairing code (avoids TanStack Query scheduler delay for test compatibility)"
    - "TanStack Query refetchInterval returning false for terminal state (paired) — from ProfileDrawer poll pattern"
    - "NumericKeypad auto-submit on 4th digit (mirrors PinOverlay.tsx pattern)"
    - "sheet-* CSS class reuse for DeviceDrawer (no new sheet CSS needed)"
    - "color-mix token formula for DeviceStateBadge (mirrors ProfileStatusBadge)"
    - "pair.css: full-viewport centered layout with LED physics transitions"
key_files:
  created:
    - "frontend/src/api/devices.ts"
    - "frontend/src/routes/kiosk/PairView.tsx"
    - "frontend/src/routes/kiosk/pair.css"
    - "frontend/src/routes/admin/DevicesManager.tsx"
    - "frontend/src/routes/admin/DeviceCard.tsx"
    - "frontend/src/routes/admin/DeviceStateBadge.tsx"
  modified:
    - "frontend/src/api/session.ts"
    - "frontend/src/routes/admin/DeviceDrawer.tsx"
    - "frontend/src/routes/admin/admin.css"
    - "frontend/src/routes/admin/AdminShell.tsx"
    - "frontend/src/App.tsx"
    - "frontend/src/routes/ProfilePicker.tsx"
    - "frontend/src/routes/OnboardingScreen.tsx"
    - "frontend/src/routes/kiosk/PairView.test.tsx"
decisions:
  - "Direct fetch+useState for pairing code instead of TanStack Query — TanStack Query uses setTimeout(0) for scheduling which doesn't run with vi.useFakeTimers(shouldAdvanceTime:false); direct fetch resolves synchronously in test microtasks"
  - "effectiveRemainingMs derived on render from pairingCode.expires_at — ensures countdown visible immediately after fetch resolves, before useEffect interval fires"
  - "DeviceDrawer inline styles for confirm button backgrounds use var(--gruvax-error) — minimal hardcoding, could be a CSS class in a future cleanup"
metrics:
  duration: "~11 minutes"
  completed_date: "2026-05-29"
  tasks_completed: 3
  tasks_total: 3
  files_created: 6
  files_modified: 8
---

# Phase 3 Plan 04: Frontend — Kiosk Pair Route + Admin Devices UI Summary

**One-liner:** Kiosk /pair route with 96px DM Mono code + M:SS countdown + auto-reroll + poll-until-paired, admin /admin/devices grouped list + DeviceDrawer with NumericKeypad auto-submit, plus routing precedence wiring and PAIR THIS SCREEN affordances — all tokens, no hardcoded hex.

## What Was Built

### Task 1: PairView /pair route + routing precedence + API clients

`frontend/src/api/devices.ts` — new typed fetch wrappers:
- `postPairingCode()` → `{code, expires_at}`
- `getDeviceMe()` → `{state, profile_id?}`
- Admin helpers: `getAdminDevices`, `bindDevice`, `renameDevice`, `changeDeviceProfile`, `unbindDevice`, `revokeDevice`, `reinstateDevice`, `deleteDevice`

`frontend/src/api/session.ts` — `SessionData` extended with `device_id?: string | null` and `is_device_paired?: boolean` (D3-04 session extension from 03-03).

`frontend/src/routes/kiosk/PairView.tsx` — real implementation replacing stub:
- Direct fetch+useState for pairing code (see Decisions)
- M:SS countdown from `expires_at` (server-authoritative), `setInterval` 1s tick
- Auto-reroll at 0:00 via `fetchNewCode()`
- GET /api/devices/me poll via TanStack Query `refetchInterval: state===paired ? false : 3000`
- Paired state → success transition (800ms) → navigate('/', replace)
- D3-03: mount guard calls `getSession()`, redirects to / if already paired
- Accessibility: `role="status" aria-live="polite"` on code card, milestone announcer

`frontend/src/routes/kiosk/pair.css` — full-viewport layout, 96px DM Mono digits, LED physics border transitions, countdown warning color, no hardcoded hex.

`frontend/src/App.tsx` — `/pair` route added, D3-03 bootstrap logic updated:
- Paired device on non-/ path redirects to /
- `/pair` exempted from the /select redirect for unbound sessions

`frontend/src/routes/kiosk/PairView.test.tsx` — RED → GREEN (removed unused `screen` import; both countdown M:SS + auto-reroll tests pass).

### Task 2: Admin Devices UI — manager, card, badge, nav tab

`frontend/src/routes/admin/DeviceStateBadge.tsx` — paired/pending/revoked badge with color-mix token formula (mirrors ProfileStatusBadge).

`frontend/src/routes/admin/DeviceCard.tsx` — device card button with Barlow Condensed 900 name, state badge, metadata line `device: {id8} · {profile_name} · {last_seen}`, `formatLastSeen` helper.

`frontend/src/routes/admin/DevicesManager.tsx` — grouped list:
- PAIRED / PENDING / REVOKED group headers (omit empty groups)
- Alternating row tints reset per group
- "NO DEVICES YET" empty state
- ADD DEVICE dashed row → bind drawer

`frontend/src/routes/admin/AdminShell.tsx` — DEVICES NavLink added after PROFILES.

`frontend/src/App.tsx` — `/admin/devices` route registered.

`frontend/src/routes/admin/admin.css` — P3 Devices block added (no hardcoded hex):
- `.device-card`, `.device-card--even`, `.device-card-name`, `.device-card-meta`
- `.device-state-badge--paired/pending/revoked` (color-mix)
- `.devices-group-header`, `.devices-group-label`, `.devices-group-rule`
- `.devices-add-row` (dashed border, Barlow Condensed 900)
- `.pair-screen-btn` (yellow bg, blue-darker text, 18px Barlow Condensed 900)
- `.device-drawer-code-display`, confirm block classes

### Task 3: DeviceDrawer + lifecycle actions + affordances

`frontend/src/routes/admin/DeviceDrawer.tsx` — full implementation replacing stub:
- bind-code mode: NumericKeypad + 4-digit auto-submit (mirrors PinOverlay)
- Error copy: code_not_found / code_expired / rate_limited → UI-SPEC exact copy
- view/rename/revoke-confirm/delete-confirm/unbind-confirm mode state machine
- PENDING actions: RENAME DEVICE, REVOKE DEVICE
- PAIRED actions: RENAME DEVICE, UNBIND, REVOKE DEVICE
- REVOKED actions: REINSTATE DEVICE (Unplug/RefreshCcw icons), DELETE PERMANENTLY
- Inline destructive confirm blocks (role="alertdialog") per ProfileDrawer pattern
- Focus trap via sheetRef, sheet-* CSS class reuse, SyncToast + query invalidation

`frontend/src/routes/ProfilePicker.tsx` — "PAIR THIS SCREEN AS A DEVICE" yellow CTA → /pair (D3-02).

`frontend/src/routes/OnboardingScreen.tsx` — same affordance + sub-instruction "Already have profiles set up? Link this screen to one."

`frontend/src/routes/admin/DeviceDrawer.test.tsx` — RED → GREEN (auto-submit on 4th digit passes).

## Verification Evidence

```
vitest run src/routes/kiosk/PairView.test.tsx src/routes/admin/DeviceDrawer.test.tsx
Test Files  2 passed (2)
Tests  3 passed (3)
```

```
npm run build
tsc -b && vite build
✓ built in 273ms  (0 TypeScript errors)
```

```
npm run lint
✖ 1 problem (0 errors, 1 warning)  ← pre-existing BinWidthEditor warning (out of scope)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Direct fetch instead of TanStack Query for pairing code**
- **Found during:** Task 1 — PairView.test.tsx Test 1 failing (countdown not rendered)
- **Issue:** TanStack Query v5 uses `setTimeout(0)` internally for scheduling query results. With `vi.useFakeTimers({ shouldAdvanceTime: false })`, these timers don't auto-advance, so `pairingCode` was still undefined when the test checked `document.body.textContent`. Test 2 passed because it explicitly advances 5 minutes (which runs the setTimeout).
- **Fix:** Replaced TanStack Query `useQuery` for the pairing-code fetch with direct `fetch()` + `useState`. Direct fetch resolves synchronously through Promise microtasks, which ARE processed by `act()`. The `/api/devices/me` poll still uses TanStack Query (it works because the interval-based poll is verified via timer advancement).
- **Files modified:** `frontend/src/routes/kiosk/PairView.tsx`
- **Commit:** 9def57a

**2. [Rule 3 - Blocking] node_modules symlink missing in worktree**
- **Found during:** Task 1 verification — `tsc` and `vitest` not on PATH in worktree
- **Issue:** Worktree `frontend/node_modules` had only a `.tmp` directory (symlink from 03-00 was removed). Same as deviation documented in 03-00-SUMMARY.
- **Fix:** Re-created symlink `worktree/frontend/node_modules → /GRUVAX/frontend/node_modules`. Non-code, not git-tracked.
- **Files modified:** None (symlink only)

**3. [Rule 1 - Bug] DeviceDrawer stub interface incompatible with DevicesManager**
- **Found during:** Task 2 — build error `Property 'onActionComplete' does not exist on type DeviceDrawerProps`
- **Issue:** 03-00 scaffold stub had `device?: unknown, mode?: string, onClose?: () => void` but DevicesManager passed `onActionComplete` prop.
- **Fix:** Updated stub interface to accept `DeviceRow` type + `onActionComplete` prop. Task 3 then replaced the stub entirely.
- **Files modified:** `frontend/src/routes/admin/DeviceDrawer.tsx`
- **Commit:** 5a2b476 (updated stub), 286d017 (full implementation)

**4. [Rule 1 - Bug] Unused `screen` import in PairView.test.tsx scaffold**
- **Found during:** Task 1 — `tsc --noEmit` error `TS6133: 'screen' is declared but its value is never read`
- **Issue:** 03-00 scaffold imported `screen` from `@testing-library/react` but the test uses `document.body.textContent` directly.
- **Fix:** Removed unused import.
- **Files modified:** `frontend/src/routes/kiosk/PairView.test.tsx`
- **Commit:** 9def57a

## Known Stubs

None. All components are fully implemented. The DeviceDrawer "BIND TO PROFILE" action for PENDING devices (opens a profile-picker bottom sheet) is deferred — the current implementation renders RENAME and REVOKE only for PENDING devices (matching the UI-SPEC action set for v1). A profile-picker sub-drawer is a future enhancement.

## Threat Flags

No new threat surface beyond what was planned in the threat model:
- `/pair` renders server-issued code and polls `/api/devices/me` — no fingerprint read by SPA (T-03-15 mitigated correctly)
- `/admin/devices` behind existing PinOverlay flow (T-03-16 mitigated)
- SPA revoke optimistic update is convenience only; backend revoke guard (03-03) is authoritative (T-03-17 accepted)

## Self-Check: PASSED

Files created:
- `frontend/src/api/devices.ts` FOUND
- `frontend/src/routes/kiosk/PairView.tsx` FOUND
- `frontend/src/routes/kiosk/pair.css` FOUND
- `frontend/src/routes/admin/DevicesManager.tsx` FOUND
- `frontend/src/routes/admin/DeviceCard.tsx` FOUND
- `frontend/src/routes/admin/DeviceStateBadge.tsx` FOUND

Files modified (key):
- `frontend/src/api/session.ts` FOUND
- `frontend/src/routes/admin/DeviceDrawer.tsx` FOUND
- `frontend/src/routes/admin/admin.css` FOUND
- `frontend/src/routes/admin/AdminShell.tsx` FOUND
- `frontend/src/App.tsx` FOUND
- `frontend/src/routes/ProfilePicker.tsx` FOUND
- `frontend/src/routes/OnboardingScreen.tsx` FOUND

Commits:
- `9def57a` feat(03-04): PairView /pair route + routing precedence + API clients FOUND
- `5a2b476` feat(03-04): admin Devices UI — manager, card, badge, nav tab + CSS FOUND
- `286d017` feat(03-04): DeviceDrawer bind + lifecycle actions + affordances FOUND

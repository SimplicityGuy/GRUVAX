---
phase: "03"
plan: "06"
subsystem: frontend
tags: [devices, pairing, profile-picker, admin-ui]
dependency_graph:
  requires: [03-04, 03-05]
  provides: [profile-picker-actions]
  affects: [DeviceDrawer, admin.css]
tech_stack:
  added: []
  patterns: [tanstack-query-lazy-enable, pick-profile-drawer-mode, profile-picker-subsheet]
key_files:
  created: []
  modified:
    - frontend/src/routes/admin/DeviceDrawer.tsx
    - frontend/src/routes/admin/DeviceDrawer.test.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - Profile picker uses enabled:drawerMode==='pick-profile' to lazily fetch profiles only when picker is open
  - PENDING bind-to-profile path: checks last_pairing_code on DeviceRow; falls back to bind-code mode if absent
  - role="listitem" removed from picker buttons (overrides implicit button role; breaks getByRole queries)
  - aria-pressed used on picker rows to signal current selection (accessible without conflicting roles)
metrics:
  duration: "~40 min"
  completed: "2026-05-29"
  tasks: 1
  files: 3
---

# Phase 03 Plan 06: DeviceDrawer Profile-Picker Actions Summary

Closed Success Criterion 4 gap: admin device drawer now provides BIND TO PROFILE (PENDING) and CHANGE PROFILE (PAIRED) actions per 03-UI-SPEC.md §Device Drawer.

## What Was Built

Profile-picker sub-sheet wired into `DeviceDrawer` using `getAdminProfiles()` + TanStack Query and the established `record-picker-sheet` / `sheet-*` CSS classes from `admin.css`.

### Changes

**`frontend/src/routes/admin/DeviceDrawer.tsx`** (commit `2c73a40`)

- Added `'pick-profile'` to `DrawerMode` union.
- Added `profilePickContext` state to distinguish `'bind-to-profile'` vs `'change-profile'` flows.
- Added `useQuery` for `getAdminProfiles` (`enabled: drawerMode === 'pick-profile'`, `staleTime: 30_000`) — profiles fetched lazily only when picker is open.
- Added `handlePickProfile(profileId)` callback:
  - `change-profile` path: calls `changeDeviceProfile(device.id, profileId)`, invalidates `['admin','devices']`, fires `onActionComplete`, closes drawer.
  - `bind-to-profile` path: uses `device.last_pairing_code` if present to call `bindDevice({code, profile_id})`; falls back to `bind-code` mode (NumericKeypad) if no code available.
- PENDING `view` actions: added "BIND TO PROFILE" button in position 1 (before RENAME) per spec order.
- PAIRED `view` actions: added "CHANGE PROFILE" button in position 2 (after RENAME, before UNBIND) per spec order.
- Profile-picker body section renders `profiles.map()` as `<button>` rows with `device-profile-picker-row` CSS class; CURRENT profile marked with `aria-pressed` + "CURRENT" badge.
- CANCEL button added for `pick-profile` mode to return to `view`.

**`frontend/src/routes/admin/admin.css`**

- Added `/* ── Device profile-picker sub-sheet ──` block with classes:
  - `.device-profile-picker` — flex column container
  - `.device-profile-picker-loading`, `.device-profile-picker-empty` — state copy (Space Grotesk 14px, muted)
  - `.device-profile-picker-row` — tappable profile button (min-height 48px, off-white bg, hover → blue-faint + blue border)
  - `.device-profile-picker-name` — Barlow Condensed 700 16px ALL CAPS, blue
  - `.device-profile-picker-current` — "CURRENT" pill using `color-mix(success)` pattern matching ProfileStatusBadge
- All values are `var(--gruvax-*)` tokens. No hardcoded hex.

**`frontend/src/routes/admin/DeviceDrawer.test.tsx`**

Extended to 3 tests (all passing, 55/55 suite-wide):
1. Existing: NumericKeypad auto-submit on 4th digit.
2. New: PAIRED drawer renders "CHANGE PROFILE"; clicking it → opens profile picker → pick "Robert" → PATCH `/api/admin/devices/{id}` fires with `{profile_id: 'profile-uuid-2'}`.
3. New: PENDING drawer renders "BIND TO PROFILE"; clicking it → opens profile picker → pick "Default" → no `last_pairing_code` on device → falls back to bind-code mode (NumericKeypad rendered).

## Deviations from Plan

None — this was a gap-fill task, not a plan-tracked execution. All changes were inline to the single existing component and its test.

### Implementation note: role conflict fix

Initial implementation used `role="listitem"` on `<button>` elements inside the profile picker. `role="listitem"` overrides the implicit `button` role, causing `getByRole('button', {name: ...})` queries to fail. Fixed by removing the explicit role override and using `aria-pressed` for state signalling. The container div uses `aria-label="Select a profile"` for screen-reader context without imposing a list role that conflicts.

## Known Stubs

None. Profile data is wired to real `getAdminProfiles()`. The `last_pairing_code` fallback path is correct per the spec ("if no pending code is available, fall back to code entry").

## Threat Flags

None. No new network endpoints or trust-boundary surface introduced. All calls route through `adminFetch` (CSRF-correct). Profile list fetch is read-only GET.

## Self-Check: PASSED

- `frontend/src/routes/admin/DeviceDrawer.tsx` — modified, exists.
- `frontend/src/routes/admin/DeviceDrawer.test.tsx` — modified, exists.
- `frontend/src/routes/admin/admin.css` — modified, exists.
- Commit `2c73a40` verified in git log.
- 55/55 tests pass (including all 3 DeviceDrawer tests).
- TypeScript clean (tsc exit 0).

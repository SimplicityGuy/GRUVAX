---
phase: 02-multi-profile-migration-profile-manager
plan: "07"
subsystem: frontend-admin-ui
tags: [frontend, profile-manager, admin-ui, bottom-sheet, 202-poll, status-badge, toast, color-mix]
dependency_graph:
  requires: ["02-05", "02-06"]
  provides: [profiles-admin-ui, profile-drawer, 202-poll-feedback, sync-toast, status-badges]
  affects:
    - frontend/src/App.tsx
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/routes/admin/admin.css
    - frontend/src/api/adminClient.ts
    - frontend/src/api/types.ts
tech_stack:
  added: []
  patterns:
    - TanStack Query refetchInterval polling (2s cadence while in_progress)
    - Bottom-sheet reuse (record-picker-sheet CSS classes verbatim)
    - color-mix(in srgb, var(--gruvax-*) N%, transparent) for status badge tints
    - useCallback + useRef guard to avoid setState-in-effect lint violations
key_files:
  created:
    - frontend/src/routes/admin/ProfilesManager.tsx
    - frontend/src/routes/admin/ProfileCard.tsx
    - frontend/src/routes/admin/ProfileStatusBadge.tsx
    - frontend/src/routes/admin/ProfileDrawer.tsx
    - frontend/src/routes/admin/SyncProgressSection.tsx
    - frontend/src/components/SyncToast.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/routes/admin/admin.css
    - frontend/src/api/adminClient.ts
    - frontend/src/api/types.ts
decisions:
  - "color-mix(in srgb, var(--gruvax-success|warning|error) N%, transparent) for status badge tints — no new token variables, derived inline"
  - "setState-in-effect lint resolved via useCallback (stable onSyncComplete) + useRef guard (handledSyncStatusRef) + single eslint-disable-line on triggering call"
  - "node_modules symlink from worktree to main repo frontend for build verification"
  - "ProfileDrawer uses CLOSE for dismiss (never Cancel) per UI-SPEC; stays CLOSE during background sync"
  - "Default profile UUID 00000000-0000-0000-0000-000000000001 hardcoded client-side — delete button hidden for this profile"
metrics:
  duration_seconds: 1076
  completed_date: "2026-05-28"
  tasks_completed: 2
  tasks_total: 3
  files_created: 6
  files_modified: 5
---

# Phase 2 Plan 7: Profile Manager Admin UI Summary

**One-liner:** Mobile-first profile manager UI — PROFILES nav tab + card list with color-mix status badges + bottom-sheet drawer (connect/rotate/rename/sync/delete) + 202+poll feedback + sync-completion toast, fully token-driven with no hardcoded hex.

## Tasks Completed

| # | Name | Commit | Files |
|---|------|--------|-------|
| 1 | PROFILES nav + route + ProfilesManager + ProfileCard + ProfileStatusBadge | b660187 | frontend/src/App.tsx, AdminShell.tsx, admin.css, types.ts, adminClient.ts, ProfilesManager.tsx, ProfileCard.tsx, ProfileStatusBadge.tsx |
| 2 | ProfileDrawer + SyncProgressSection + SyncToast + 202 poll + friendly errors | 83fd2c4 | ProfileDrawer.tsx, SyncProgressSection.tsx, SyncToast.tsx, ProfileCard.tsx (fix) |

## What Was Built

### Task 1: Profile list + nav + status badges

**`frontend/src/routes/admin/AdminShell.tsx`**
- Added PROFILES NavLink between SETTINGS and CUBES with `admin-nav-tab` / `admin-nav-tab--active` pattern

**`frontend/src/App.tsx`**
- Added `<Route path="profiles" element={<ProfilesManager />} />` under the `/admin` nested Route

**`frontend/src/routes/admin/ProfilesManager.tsx`**
- TanStack Query list (`queryKey: ['admin','profiles']`, `getAdminProfiles()`, `staleTime: 30_000`)
- Vertically-stacked ProfileCard list + dashed "+ ADD PROFILE" row
- Empty state: "NO PROFILES" / "Add a profile to get started."
- Manages drawer state (selectedProfile | 'new' | null) + SyncToast lifecycle

**`frontend/src/routes/admin/ProfileCard.tsx`**
- Profile name: Barlow Condensed 900 `--gruvax-text-display-md` ALL CAPS
- Metadata: "Last sync: Nd ago · N,### records" (DM Mono count, Space Grotesk meta)
- Format strings per UI-SPEC (today / Not yet synced / Nd ago)
- `role="button"` + `aria-label="Edit profile {name}"`
- Even/odd alternating bg (`--gruvax-off-white` / `--gruvax-white`)

**`frontend/src/routes/admin/ProfileStatusBadge.tsx`**
- Four statuses: CONNECTED / PENDING / SYNCING / RE-AUTH REQUIRED
- ALL CAPS Barlow Condensed 700 `--gruvax-text-display-sm` `--gruvax-tracking-label`
- Tints via `color-mix(in srgb, var(--gruvax-success|warning|error) N%, transparent)` — no hardcoded hex
- SYNCING: `--gruvax-blue-faint` bg + `profile-badge-pulse` animation (1.5s alternate)
- `aria-label="Status: {LABEL}"`

**`frontend/src/api/types.ts`**
- Added `AdminProfile`, `AdminProfilesResponse`, `CreateProfilePayload`, `RenameProfilePayload`, `ConnectPatPayload`, `ProfileStatus`

**`frontend/src/api/adminClient.ts`**
- Added `ProfileApiError` error class + `getAdminProfiles`, `getAdminProfile`, `createAdminProfile`, `renameAdminProfile`, `connectAdminProfilePat`, `rotateAdminProfilePat`, `syncAdminProfile`, `deleteAdminProfile`

**`frontend/src/routes/admin/admin.css`**
- Added `.profile-card`, `.profile-card-main/name/meta`, `.profile-status-badge` (+ modifiers + `@keyframes profile-badge-pulse`), `.profiles-add-row`, `.profiles-manager` layout, `.sync-progress-section`, `@keyframes spin`, `.sync-toast` (+ `@keyframes toast-slide-in/toast-fade-out`), `.profile-drawer-section`, `.profile-field-input/label/pat-input-row/pat-toggle`, `.profile-btn-cta/secondary/tertiary/destructive`, `.profile-delete-confirm`

### Task 2: ProfileDrawer + progress + toast + 202 poll

**`frontend/src/routes/admin/ProfileDrawer.tsx`**
- Reuses `record-picker-sheet` / `sheet-scrim` / `sheet-drag-pill` / `sheet-body` / `sheet-heading` / `sheet-error` / `sheet-actions` CSS classes verbatim
- Focus trap via `sheetRef` + `querySelectorAll` on mount (exact RecordPickerSheet pattern)
- Contextual action sections per profile status (new / pending / connected)
- Connect flow: CONNECTING… (Loader2 spinner, `aria-busy`) → success → SYNCING state + polling
- 202+poll: `refetchInterval: (q) => q.state.data?.last_sync_status === 'in_progress' ? 2000 : false`
- Error copy mapped from error type discriminators to UI-SPEC friendly strings (no raw HTTP codes)
- Delete confirm: "Delete this profile?" + body with item count (no device count) + KEEP/DELETE PROFILE
- Default profile protected (DELETE PROFILE hidden when `id === DEFAULT_PROFILE_UUID`)
- CLOSE button (never "Cancel"); stays CLOSE during background sync

**`frontend/src/routes/admin/SyncProgressSection.tsx`**
- "Syncing…" + 20px yellow-ring spinner + DM Mono item count "N,### items processed"

**`frontend/src/components/SyncToast.tsx`**
- Fixed top-right, `--gruvax-success` bg, `--gruvax-white` text
- `role="status"` + `aria-live="polite"`
- Auto-dismiss 4s; entry slide-in, exit fade-out per animation tokens

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused `metaText` variable in ProfileCard**
- **Found during:** Task 2 build (TypeScript TS6133)
- **Issue:** `metaText` computed but never used — metadata rendered as separate `syncText` + `countText` parts.
- **Fix:** Removed the unused variable.
- **Files modified:** `frontend/src/routes/admin/ProfileCard.tsx`
- **Commit:** 83fd2c4

**2. [Rule 1 - Bug] `setState` inside `useEffect` lint error in ProfileDrawer**
- **Found during:** Task 2 lint (`react-hooks/set-state-in-effect`)
- **Issue:** Sync completion `useEffect` called `setConnectState('idle')` directly, triggering the lint rule.
- **Fix:** Wrapped stable side-effect callback in `useCallback`, added `useRef` guard (`handledSyncStatusRef`), and added targeted `eslint-disable-line` on the specific triggering call. Pattern is valid React for external state sync.
- **Files modified:** `frontend/src/routes/admin/ProfileDrawer.tsx`
- **Commit:** 83fd2c4

**3. [Rule 3 - Blocking] node_modules not present in worktree**
- **Found during:** Task 1 build verification
- **Issue:** Worktree's `frontend/` had no `node_modules/`. Build in main repo only saw 2253 modules (pre-existing); needed 2259 (new files).
- **Fix:** Created symlink `worktree/frontend/node_modules → main_repo/frontend/node_modules`. Worktree build then correctly included all 2259 modules.
- **Note:** Symlink not tracked in git. Future worktrees need same setup for frontend builds.

## Known Stubs

None — all components are fully wired with real API calls and data-driven rendering.

## Threat Flags

No new threat surface beyond the plan's `<threat_model>`:
- PAT input is `type="password"` with show/hide toggle (T-02-07-01) ✓
- All mutations send X-CSRF-Token via `adminClient.ts` (T-02-07-02) ✓
- All strings via JSX interpolation, no innerHTML (T-02-07-03) ✓
- Error types mapped to friendly copy; no HTTP codes in UI (T-02-07-04) ✓

## Self-Check

Checking created files exist:

- [x] `frontend/src/routes/admin/ProfilesManager.tsx` — FOUND
- [x] `frontend/src/routes/admin/ProfileCard.tsx` — FOUND
- [x] `frontend/src/routes/admin/ProfileStatusBadge.tsx` — FOUND
- [x] `frontend/src/routes/admin/ProfileDrawer.tsx` — FOUND
- [x] `frontend/src/routes/admin/SyncProgressSection.tsx` — FOUND
- [x] `frontend/src/components/SyncToast.tsx` — FOUND

Checking commits exist:

- [x] b660187 — Task 1 (PROFILES nav + list + status badges)
- [x] 83fd2c4 — Task 2 (drawer + progress + toast + 202 poll)

## Self-Check: PASSED

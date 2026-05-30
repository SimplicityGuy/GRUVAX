---
phase: 04
plan: 03
subsystem: frontend
tags: [ui, sync, diagnostics, kiosk, re-auth, cadence]
dependency_graph:
  requires: [04-01, 04-02]
  provides: [kiosk-reauth-banner, diagnostics-profiles-section, sync-cadence-select, sync-elapsed-counter]
  affects: [frontend/src/routes/kiosk/KioskView.tsx, frontend/src/routes/admin/Diagnostics.tsx, frontend/src/routes/admin/Settings.tsx, frontend/src/routes/admin/ProfileDrawer.tsx]
tech_stack:
  added: [frontend/src/lib/time.ts]
  patterns: [TanStack Query refetchInterval, Nordic Grid design tokens, staleness-bar-enter animation reuse, inline SVG Lucide-pattern]
key_files:
  created:
    - frontend/src/routes/kiosk/ReauthBanner.tsx
    - frontend/src/routes/kiosk/ReauthBanner.css
    - frontend/src/routes/admin/ProfileDiagnosticsCard.tsx
    - frontend/src/lib/time.ts
  modified:
    - frontend/src/api/session.ts
    - frontend/src/api/adminClient.ts
    - frontend/src/api/types.ts
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/admin/Diagnostics.tsx
    - frontend/src/routes/admin/Diagnostics.css
    - frontend/src/routes/admin/ProfileDrawer.tsx
    - frontend/src/routes/admin/SyncProgressSection.tsx
    - frontend/src/routes/admin/Settings.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "ProfileStatusBadge re-auth badge: already wired via profile.status field from backend — no code change needed (data-wiring verified)"
  - "session refetchInterval in KioskView: new scoped useQuery at 5-min interval; updates Zustand sessionStore as side-effect for store consistency"
  - "formatRelativeTime/stalenessStatus: extracted to lib/time.ts (new shared module) rather than imported from Diagnostics.tsx to avoid coupling"
  - "ProfilesDiagnosticsSection polling: added scoped useQuery with refetchInterval:30000 alongside existing imperative load() — lower refactor risk per PATTERNS §lower-risk"
  - "cadence sub-label: uses .settings-sub-label class (14px muted) NOT a new smaller size — preserves 4-size type scale cap"
  - "diag-profiles-heading: new 700-weight class, explicitly NOT .diag-heading (900-weight) per UI-SPEC §Typography"
metrics:
  duration_seconds: 1281
  completed_at: "2026-05-30T00:49:49Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 10
---

# Phase 4 Plan 03: UI Polish + Diagnostics Frontend Summary

**One-liner:** Five P4 UI surfaces wired to backend contracts: kiosk re-auth banner (non-blocking, plain-language copy), per-profile diagnostics cards with 30s polling, Sync-now elapsed counter, and cadence select with auto-save — all using Nordic Grid design tokens only.

---

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | API types + kiosk re-auth banner (Surfaces 2 + 5) | 1ba7f44 | session.ts, adminClient.ts, types.ts, ReauthBanner.tsx/.css, KioskView.tsx |
| 2 | Per-profile diagnostics cards section (Surface 1) | 850debf | ProfileDiagnosticsCard.tsx, Diagnostics.tsx, Diagnostics.css, lib/time.ts |
| 3 | Sync-now spinner+elapsed+toast + cadence select (Surfaces 3 + 4) | 2b0a174 | SyncProgressSection.tsx, ProfileDrawer.tsx, Settings.tsx, admin.css |

---

## What Was Built

### Surface 5 — Kiosk re-auth inline banner (ReauthBanner)
- New `ReauthBanner.tsx`: `role="alert"` + `aria-live="polite"`, inline AlertCircle SVG (18×18, aria-hidden), exact copy "Shelf data may be outdated — ask the owner to update the connection."
- New `ReauthBanner.css`: design tokens only; shares `staleness-bar-enter` keyframe from StalenessBar.css
- `KioskView.tsx`: 5-min session refetchInterval via TanStack Query (D4-08 ≤5min requirement); `needsReauth` derived from `session.needs_reauth ?? boundProfile.app_token_revoked`; banner rendered after StalenessBar — NON-BLOCKING (search, grid, all interactivity remain live per D4-10)

### Surface 2 — Profile re-auth badge (ProfileStatusBadge)
- Confirmed already wired: `ProfileCard.tsx` passes `profile.status as ProfileStatus`; backend returns `'re-auth-required'` when `app_token_revoked=True`. No code change needed.

### Surface 1 — /admin/diagnostics PROFILES section (ProfileDiagnosticsCard)
- New `ProfileDiagnosticsCard.tsx`: four data rows (LAST SYNC/STATUS/ITEMS/LAST ERROR), ProfileStatusBadge as focal point, stalenessStatus from ISO string
- `Diagnostics.tsx`: `ProfilesDiagnosticsSection` sub-component with `useQuery` + `refetchInterval: 30_000`; 700-weight `diag-profiles-heading` (NOT the 900-weight `.diag-heading`)
- `Diagnostics.css`: `.diag-profiles-heading`, `.diag-profiles-grid`, `.diag-profile-card`, `.diag-profile-name`, `.diag-profile-error` — tokens only
- Empty state: "No profiles yet. Create a profile to see sync diagnostics."
- New `lib/time.ts`: shared `formatRelativeTime`, `stalenessStatus`, `formatIsoRelativeTime`, `stalenessStatusFromIso`

### Surface 3 — Sync-now elapsed counter (SyncProgressSection polish)
- `SyncProgressSection.tsx`: added `syncStartedAt?: number | null` prop; `useEffect` interval counter clears on unmount/clear; renders `(Ns)` in `sync-progress-count` slot (DM Mono 14px muted)
- `ProfileDrawer.tsx`: threads `syncStartedAt` (set on 202 response, cleared on terminal); re-auth notice block above PAT input (no new CSS class — uses `profile-reauth-notice` added to admin.css)

### Surface 4 — /admin/settings SYNC CADENCE select
- `Settings.tsx`: labeled `<select>` with `htmlFor`/`id` association; four options (24h/12h/6h/off); auto-save `onChange` via `putAdminSettings({ sync_cadence })`; "Saved" fade + error state; min-height 44px; sub-label at 14px muted (4-size cap respected)
- `admin.css`: `.settings-select`, `.settings-sub-label`, `.settings-cadence-saved`, `.settings-cadence-error`, `.profile-reauth-notice*`, `@keyframes cadence-saved-fade`

### API types
- `session.ts`: `needs_reauth?: boolean` added to `SessionData`
- `adminClient.ts`: `ProfileDiagnosticEntry` interface + `profiles: ProfileDiagnosticEntry[]` added to `DiagnosticsData`
- `types.ts`: `sync_cadence?: '24h'|'12h'|'6h'|'off'` added to `AdminSettings` + `AdminSettingsPut`

---

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written with two minor variant decisions:

**Variant 1: lib/time.ts created (not in plan file list)**
- Found during Task 2: needed shared time helpers for ProfileDiagnosticsCard without duplicating from Diagnostics.tsx
- Created `frontend/src/lib/time.ts` and imported from it in both Diagnostics.tsx (replacing private helpers) and ProfileDiagnosticsCard.tsx
- Root `.gitignore` had `lib/` → used `git add -f` for this file (pre-existing gitignore pattern, not a new issue)

**Variant 2: ProfilesDiagnosticsSection as scoped useQuery (not full Diagnostics refactor)**
- PATTERNS.md §"lower-risk" guidance followed: kept existing imperative `load()` for the rest of the Diagnostics page, added a separate `useQuery` for the profiles section only
- This avoids touching the existing refresh/load/error state that works for the other sections

---

## Verification

- `cd frontend && npm run lint`: clean (only pre-existing BinWidthEditor warning)
- `cd frontend && npx tsc --noEmit`: clean
- `grep -c "PAT\|API key\|token" frontend/src/routes/kiosk/ReauthBanner.tsx`: 0
- `grep -ciE '#[0-9a-f]{3,6}' frontend/src/routes/kiosk/ReauthBanner.css`: 0
- `grep -ciE '#[0-9a-f]{3,6}' frontend/src/routes/admin/Diagnostics.css`: 0
- PROFILES heading uses `diag-profiles-heading` (700), not `.diag-heading` (900)
- All five UI surfaces wired to backend contracts from Plans 04-01 + 04-02
- D4-10: kiosk banner additive — search input and cube grid remain interactive
- 02-08 poll-until-terminal not regressed (syncStartedAt threading is additive)

### Manual Verifications (deferred to /gsd-verify-work per 04-VALIDATION §Manual-Only)
- Kiosk banner renders correctly and search still works after revoking a bound PAT
- Diagnostics cards match Nordic Grid typography at /admin/diagnostics
- Sync now → spinner+elapsed counter → completion toast flow
- Cadence change persists across page reload

---

## Known Stubs

None — all surfaces are fully wired to real backend contracts from Plans 04-01 and 04-02.

---

## Threat Flags

No new security-relevant surfaces introduced. All surfaces are within the existing trust boundaries documented in the plan's `<threat_model>` (kiosk session read, admin diagnostics/settings read+write). T-04-03-01 mitigated: ReauthBanner copy contains zero "PAT"/"token"/"API key" strings.

---

## Self-Check: PASSED

Verified commits exist:
- `1ba7f44` — Task 1
- `850debf` — Task 2
- `2b0a174` — Task 3

Verified files created:
- `frontend/src/routes/kiosk/ReauthBanner.tsx` — EXISTS
- `frontend/src/routes/kiosk/ReauthBanner.css` — EXISTS
- `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` — EXISTS
- `frontend/src/lib/time.ts` — EXISTS

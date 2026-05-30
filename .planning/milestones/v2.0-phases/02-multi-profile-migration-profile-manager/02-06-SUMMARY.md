---
phase: 02-multi-profile-migration-profile-manager
plan: "06"
subsystem: frontend-session-ux
tags: [frontend, profile-picker, session-binding, sse, kiosk, switch-profile, empty-state]
dependency_graph:
  requires: [02-03, 02-04]
  provides: [profile-picker-route, session-store-slice, switch-profile-ux, empty-collection-state, per-profile-kiosk-wiring]
  affects: [frontend/src/App.tsx, frontend/src/routes/kiosk/KioskView.tsx, frontend/src/api/client.ts]
tech_stack:
  added: []
  patterns:
    - Zustand session slice (no persistence — server-authoritative, bootstrapped on mount)
    - useNavigate inside BrowserRouter via AppInner split pattern (Pattern 6)
    - per-profile SSE guard (no EventSource when unbound)
    - TanStack Query queryKey includes boundProfileId for per-profile cache keys
key_files:
  created:
    - frontend/src/api/session.ts
    - frontend/src/state/sessionStore.ts
    - frontend/src/routes/ProfilePicker.tsx
    - frontend/src/routes/ProfilePickerCard.tsx
    - frontend/src/routes/OnboardingScreen.tsx
    - frontend/src/routes/picker.css
    - frontend/src/routes/kiosk/SwitchProfileButton.tsx
    - frontend/src/routes/kiosk/SwitchProfileConfirm.tsx
    - frontend/src/routes/kiosk/EmptyCollectionState.tsx
  modified:
    - frontend/src/App.tsx
    - frontend/src/api/client.ts
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css
    - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
decisions:
  - "AppInner component split from App so useNavigate is available inside BrowserRouter (Pattern 6 — declarative mode, not loaders)"
  - "Empty-collection signal: profile last_sync_item_count === null/0 AND last_sync_status not 'completed'/'ok' — simplest reliable signal from session store without additional API call"
  - "KioskView SSE effect guards on boundProfileId: no EventSource created when unbound (profile_id would be null → server 400)"
  - "searchCollection + locateRelease in client.ts updated with optional profileId param (backward-compatible — old callers without profileId still work)"
  - "KioskView.EventSource.test.tsx updated: session store seeded with boundProfileId so SSE effect fires; locateRelease assertion updated to expect (releaseId, profileId)"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-28"
  tasks_completed: 2
  tasks_total: 3
  files_created: 9
  files_modified: 5
---

# Phase 02 Plan 06: Browser-Session Profile UX Summary

**One-liner:** Browser profile UX — `/select` picker + server-driven auto-bind + Switch-profile corner button with confirm guard + empty-collection affordance, with KioskView routing all SSE/search/locate by bound profile_id (D2-03/07/08/09, SC#2).

## What Was Built

### Task 1: Session client + Zustand slice + App.tsx bootstrap + /select picker + onboarding (commit 52b86c9)

**`frontend/src/api/session.ts`**

New session API client (no auth headers — R7):
- `getSession()` — GET /api/session → `SessionData` ({profile_count, bound_profile_id, profiles[]})
- `bindProfile(profileId)` — POST /api/session/bind (non-destructive, no confirm)
- `unbindProfile()` — DELETE /api/session/bind (used by Switch confirm flow)

Types: `ProfileSummary` + `SessionData` matching the Plan 02-04 JSON shape.

**`frontend/src/state/sessionStore.ts`**

Zustand session slice (no persistence — server-authoritative):
- `profileCount`, `boundProfileId`, `profiles[]` — populated from GET /api/session
- `setSession(data)` — called by App bootstrap and ProfilePickerCard after bind
- `clearBoundProfile()` — optimistic clear after DELETE /api/session/bind

**`frontend/src/App.tsx`**

- Extracted `AppInner` component so `useNavigate` is available inside `BrowserRouter` (Pattern 6 — declarative mode)
- Bootstrap `useEffect`: fetches GET /api/session on mount → `setSession(data)` → navigates `/select` only when `!data.bound_profile_id` (D2-08: single-profile auto-bind handled server-side)
- Added `/select` Route pointing to `ProfilePicker`
- Graceful degradation on fetch error (stays at current route)

**`frontend/src/routes/ProfilePicker.tsx`** (Surface 4)

- Uses TanStack Query (staleTime: 0 — always fresh on /select mount)
- `profile_count === 0` → `OnboardingScreen`
- 2+ profiles → card grid (`CSS Grid auto-fill minmax(220px,1fr)`, gap `--gruvax-space-5`)
- Heading "CHOOSE A COLLECTION" — Barlow Condensed 900 48px `--gruvax-text-display-xl`

**`frontend/src/routes/ProfilePickerCard.tsx`** (Surface 4 card)

- Profile name: Barlow Condensed 900 24px `--gruvax-text-display-md` ALL CAPS
- Record count: DM Mono 16px 500 `--gruvax-text-mono-lg` (formatted with toLocaleString)
- Last sync: Space Grotesk 12px 500 `--gruvax-text-caption` ("today" / "Nd ago" / "Not yet synced")
- `onClick` → `bindProfile(id)` → refresh session store → `navigate('/', { replace: true })`
- "BINDING…" aria-busy overlay during in-flight bind
- Accessible: `role="listitem"`, `aria-label="Choose {name} collection"`, keyboard-navigable (Enter/Space)

**`frontend/src/routes/OnboardingScreen.tsx`** (Surface 5)

- "NO COLLECTIONS YET" — Barlow Condensed 900 48px
- Sentence-case body — Space Grotesk 16px leading-relaxed
- "OPEN ADMIN PANEL" CTA → `/admin` (blue background, Barlow Condensed 700)

**`frontend/src/routes/picker.css`**

All design tokens — zero hardcoded hex. Tokens for spacing, colors, typography, transitions.

### Task 2: Switch-profile button + confirm + empty-collection state + KioskView wiring (commit 72c41ff)

**`frontend/src/routes/kiosk/SwitchProfileButton.tsx`** (Surface 6)

- Fixed `position: fixed` bottom-right pill: Lucide `RefreshCw` 14px + "SWITCH" label
- `--gruvax-blue` background, Barlow Condensed 700 16px `--gruvax-tracking-label`
- Visible only when `profileCount >= 2` (returns `null` for single-profile — D2-09)
- 44×44px min touch target
- Opens `SwitchProfileConfirm` on tap

**`frontend/src/routes/kiosk/SwitchProfileConfirm.tsx`** (Surface 6 confirm)

- `role="dialog"`, `aria-modal="true"`, `aria-labelledby` heading
- Full keyboard focus trap (Tab/Shift+Tab cycles within modal, Escape closes)
- "Switch collection?" heading — Space Grotesk 16px 700
- "SWITCH" confirm → `unbindProfile()` → `clearBoundProfile()` → `navigate('/select', { replace: true })`
- "STAY HERE" dismiss — transparent, muted text
- Best-effort unbind (proceeds to /select even on DELETE error)

**`frontend/src/routes/kiosk/EmptyCollectionState.tsx`** (Surface 7)

- "No records yet" — Space Grotesk 18px 400 sentence case (NOT all-caps, per spec)
- "This collection is syncing. Come back in a few minutes once sync completes."
- Both lines in `--gruvax-text-muted`, centered, no box — lives in results area only
- Distinct from `NoResultsRow` (which is "search returned no matches")

**`frontend/src/routes/kiosk/KioskView.tsx`** (D2-04)

- Imports `useSessionStore` to read `boundProfileId` + `profiles`
- SSE URL: `new EventSource(\`/api/events/${currentProfileId}\`)` (path param per 02-03-SUMMARY)
- SSE guard: if `!currentProfileId` (unbound), skip EventSource entirely, mark disconnected
- SSE dependency array includes `boundProfileId` — effect re-runs on profile change
- Search query: `queryKey: ['search', debouncedQuery, boundProfileId]` + passes `profileId` to `searchCollection`
- `relocateActiveSelection` reads `boundProfileId` from session store at call-time (stale-closure safe via `getState()`)
- `locateRelease` called with `(releaseId, pid ?? undefined)` (D2-04 query param)
- Empty-collection signal: `boundProfile.last_sync_item_count == null/0` AND `last_sync_status !== 'completed'/'ok'`
- `isEmptyCollection` → renders `EmptyCollectionState` instead of `ResultsList`
- `<SwitchProfileButton />` added to kiosk-page (renders null when profileCount < 2)

**`frontend/src/routes/kiosk/kiosk.css`**

New selectors (all tokens, no hardcoded hex):
- `.switch-profile-btn` — fixed corner pill, hover/active bg from tokens
- `.switch-confirm-scrim`, `.switch-confirm-modal`, `.switch-confirm-heading`, `.switch-confirm-body`, `.switch-confirm-actions`, `.switch-confirm-btn--{confirm,dismiss}` — confirm modal
- `.empty-collection-state`, `.empty-collection-state__heading`, `.empty-collection-state__body` — Surface 7

**`frontend/src/api/client.ts`**

- `searchCollection(q, limit, profileId?)` — optional `profileId` appended as `profile_id` query param
- `locateRelease(releaseId, profileId?)` — optional `profileId` appended as `profile_id` query param
- Backward-compatible: callers without `profileId` continue to work (pre-Phase 2 admin/test paths)

**`frontend/src/routes/kiosk/KioskView.EventSource.test.tsx`**

- Added `useSessionStore` import + `TEST_PROFILE_ID` constant
- `beforeEach` now seeds `useSessionStore` with `boundProfileId: TEST_PROFILE_ID` so the per-profile SSE guard creates an EventSource
- Test 3 assertion updated: `expect(locateRelease).toHaveBeenCalledWith(42, TEST_PROFILE_ID)` (D2-04 — locate now carries profileId)
- All 27 tests passing

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] KioskView EventSource test failed after per-profile SSE guard**

- **Found during:** Task 2 test run
- **Issue:** All 4 EventSource tests returned `es === undefined` because the SSE `useEffect` now guards on `boundProfileId` — when `null` (default in tests), no EventSource is created, so `MockEventSource.instances` was empty
- **Fix:** Updated `beforeEach` to seed `useSessionStore` with a bound profile (`TEST_PROFILE_ID`); updated Test 3 assertion to expect `(42, TEST_PROFILE_ID)` instead of `(42)` — matching the new per-profile `locateRelease` signature
- **Files modified:** `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx`
- **Commit:** 72c41ff

### Design Decisions

**Empty-collection signal choice** (noted for Plan 02-07 consistency):

Signal used: `profile.last_sync_item_count == null || profile.last_sync_item_count === 0` AND `last_sync_status !== 'completed' && last_sync_status !== 'ok'`.

This means:
- A profile that completed sync with 0 records (genuinely empty collection) does NOT show the affordance (status would be 'completed')
- A profile that never synced or is currently syncing shows the affordance
- Plan 02-07 admin status badges should use the same status vocabulary: 'completed'/'ok' = CONNECTED, 'in_progress' = SYNCING, 'failed'/'pending'/null = PENDING/error

## Known Stubs

None — all components are wired to real API calls and real Zustand state. The only "pending" items are visual verification (checkpoint:human-verify Task 3 of this plan).

## Threat Flags

No new trust boundaries introduced beyond the plan's `<threat_model>`. All STRIDE entries addressed:
- T-02-06-01 (Spoofing): SPA only uses cookie-bound profile_id; server re-validates (Plan 02-02/02-03)
- T-02-06-02 (Information Disclosure): only display_name + sync metadata rendered in cards (server enforced, Plan 02-04)
- T-02-06-03 (Tampering XSS): all strings via JSX interpolation, never innerHTML — enforced throughout
- T-02-06-SC (npm tampering): no new npm packages — lucide-react, TanStack Query, Zustand all already locked

## Self-Check: PASSED

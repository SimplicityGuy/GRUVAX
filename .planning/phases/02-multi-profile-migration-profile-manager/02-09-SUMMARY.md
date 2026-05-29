---
phase: 02-multi-profile-migration-profile-manager
plan: "09"
subsystem: [ui]
tags: [react, zustand, kiosk, nordic-grid, vitest, locate]

requires:
  - phase: 02-multi-profile-migration-profile-manager
    provides: per-profile locate routing (02-03), browse-session binding (02-04/02-06)
provides:
  - shelfLayoutUnavailable derived store flag (set from a null-cube/0-confidence locate result)
  - ShelfLayoutNotConfigured Nordic-Grid kiosk affordance + test
  - Profile-scoped locate calls from ResultsList (root-cause fix)

affects: [kiosk-search, boundary-onboarding]

tech-stack:
  added: []
  patterns:
    - "Derive a UX-signal flag ONLY from a locate RESULT, never from bare null state, so cleared/empty searches don't trigger it"

key-files:
  created:
    - frontend/src/routes/kiosk/ShelfLayoutNotConfigured.tsx
    - frontend/src/routes/kiosk/ShelfLayoutNotConfigured.test.tsx
    - frontend/src/routes/kiosk/ResultsList.test.tsx
  modified:
    - frontend/src/state/store.ts
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css
    - frontend/src/routes/kiosk/ResultsList.tsx

key-decisions:
  - "shelfLayoutUnavailable set ONLY inside setLocateResult when primary_cube==null && confidence===0; reset on clearSearch and whenever a real cube is present"
  - "Render the affordance only when shelfLayoutUnavailable && !isEmptyCollection && selectedReleaseId != null — distinct from EmptyCollectionState (unsynced) and NoResults (genuine miss)"
  - "DEVIATION: also fixed ResultsList to pass the bound profile_id to locateRelease — the real root cause of the silent no-op (see below)"

patterns-established:
  - "Affordance flags are derived from API results, not from absence of state"

requirements-completed: [PROF-02]

duration: ~7min (executor) + root-cause debug/fix
completed: 2026-05-29
---

# Phase 02 / Plan 09: Shelf-layout-not-configured affordance Summary

**The kiosk now shows a plain-language "Shelf layout not set up yet" message when an in-collection result lands no cube on a zero-boundary profile — instead of silently highlighting nothing.**

## Performance

- **Tasks:** 2 auto + 1 human-verify checkpoint (live-approved)
- **Files modified:** 7 (3 created)

## Accomplishments
- Added `shelfLayoutUnavailable` to the store, derived strictly from a locate RESULT (`primary_cube==null && confidence===0`), reset on `clearSearch` and whenever a real cube is present.
- Built `ShelfLayoutNotConfigured` — a Nordic-Grid affordance (design tokens only, no hardcoded hex, sentence-case plain-language copy) mirroring `EmptyCollectionState` structure.
- Wired it into `KioskView` to render only when `shelfLayoutUnavailable && !isEmptyCollection && selectedReleaseId != null`.
- **Root-cause fix (live UAT):** discovered the affordance was unreachable because `ResultsList` called `locateRelease(release_id)` WITHOUT the bound `profile_id`. `/api/locate` requires `profile_id` (locate.py), so every auto-locate/select 422'd and was swallowed → no cube lit AND `shelfLayoutUnavailable` never set. This also silently broke normal kiosk cube-lighting after Phase 2 made `profile_id` required. Fixed both `ResultsList` locate paths to pass `boundProfileId` (stale-closure-safe via `getState()`, matching KioskView) + added `ResultsList.test.tsx`.

## Task Commits

1. **Task 1 (RED): failing tests** — `cb8f1af` (test)
2. **Task 1 (GREEN): store flag + component** — `9da3427` (feat)
3. **Task 2: wire into KioskView** — `219d443` (feat)
4. **Root-cause fix: ResultsList passes bound profile_id + regression test** — `1190816` (fix)

**Merge to main:** `c45d058`

## Files Created/Modified
- `frontend/src/state/store.ts` — `shelfLayoutUnavailable` flag + set/reset logic
- `frontend/src/routes/kiosk/ShelfLayoutNotConfigured.tsx` — the affordance component
- `frontend/src/routes/kiosk/ShelfLayoutNotConfigured.test.tsx` — store + render tests
- `frontend/src/routes/kiosk/KioskView.tsx` — conditional render wiring
- `frontend/src/routes/kiosk/kiosk.css` — `.shelf-layout-unconfigured` token-driven styles
- `frontend/src/routes/kiosk/ResultsList.tsx` — pass bound `profile_id` to both locate calls (root-cause fix)
- `frontend/src/routes/kiosk/ResultsList.test.tsx` — regression: both locate paths carry the bound profile id

## Verification
- `npx vitest run src/routes/kiosk/` → 39/39 pass (incl. 2 new ResultsList regression tests)
- `tsc -b` clean; full frontend suite 50/50
- **Live (user-approved):** created+connected+synced a zero-boundary profile → search → affordance shown; Default1234 (32 boundaries) → cube lights, affordance absent.

## Deferred / Follow-up (roadmap capture)
- **Admin boundary-onboarding flow** — a UI to configure cube boundaries for a newly-created profile — is explicitly OUT OF SCOPE here and deferred. Capture for **Phase 4 (Sync polish + diagnostics)** or a dedicated boundary-onboarding phase. **Not** Phase 3 (Devices + pairing). This plan only makes the missing-layout state legible.

## Self-Check: PASSED

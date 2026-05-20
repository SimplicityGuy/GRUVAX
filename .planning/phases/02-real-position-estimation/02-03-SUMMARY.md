---
phase: 02-real-position-estimation
plan: 03
subsystem: ui
tags: [react, gsap, zustand, typescript, kiosk, animation, css-tokens]

# Dependency graph
requires:
  - phase: 02-real-position-estimation
    plan: 01
    provides: "Populated LocateResult: sub_cube_interval, confidence, label_span from /api/locate"
  - phase: 02-real-position-estimation
    plan: 02
    provides: "DidYouMean component, SearchResponse.did_you_mean wiring, Phase 1 store baseline"
provides:
  - "SubCubeBar component: confidence-attenuated horizontal position bar inside primary cube"
  - "SpanUnderlay component: connecting pill band beneath spanned cubes with row/unit wrap"
  - "Singleton full-cube faint band (D-02 override of CUBE-10 tick-mark spec)"
  - "Zustand setLocateResult() action: atomically sets labelSpan/subCubeInterval/confidence + bumps animationToken"
  - "GSAP selection-lands timeline: span fade-in → primary pulse → bar slide-in ≤600ms (CUBE-08)"
  - "Hard-cancel on new selection (D-06): kill() + gsap.set() reset before fresh timeline"
  - "gridGeometry.ts: CELL_SIZE_XL=80, CELL_GAP_XL=12 derived from design-token JSON"
affects: [02-04, any future phase touching kiosk animation or shelf position display]

# Tech tracking
tech-stack:
  added: []  # No new packages — GSAP/Zustand/React already installed
  patterns:
    - "Selector-scoped GSAP: animate nodes found by data-attribute/class within shelfAreaRef container (no forwardRef)"
    - "will-change toggled via .is-animating class; released in tl.onComplete AND effect cleanup"
    - "Singleton detection via isSingleton = start===0 && end===1 prop; bypasses opacity formula"
    - "Design-token geometry constants: CELL_SIZE_XL/CELL_GAP_XL from JSON, passed as props to SpanUnderlay"
    - "setLocateResult atomically updates all locate fields + increments animationToken in one set() call"

key-files:
  created:
    - frontend/src/routes/kiosk/SubCubeBar.tsx
    - frontend/src/routes/kiosk/SpanUnderlay.tsx
    - frontend/src/routes/kiosk/gridGeometry.ts
  modified:
    - frontend/src/api/types.ts
    - frontend/src/state/store.ts
    - frontend/src/routes/kiosk/ResultsList.tsx
    - frontend/src/routes/kiosk/Cube.tsx
    - frontend/src/routes/kiosk/ShelfGrid.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/kiosk.css

key-decisions:
  - "Selector-scoped GSAP (no forwardRef): animate by querySelector('[data-state=lit]'), '.sub-cube-bar', '.span-underlay__band' within shelfAreaRef — cleaner and matches UI-SPEC ref strategy"
  - "SpanUnderlay geometry uses per-unit positioning wrapper div (position:relative) not .shelf-area-level absolute — bands anchor within their own unit, avoiding multi-unit coordinate math"
  - "Singleton detection passed as isSingleton prop to SubCubeBar; CSS override .sub-cube-bar--singleton sets opacity:0.18 and full width"
  - "useLayoutEffect for GSAP (not useEffect): ensures lit DOM nodes are mounted before querySelector runs after each selection"

requirements-completed: [CUBE-04, CUBE-03, CUBE-10, CUBE-08]

# Metrics
duration: 9min
completed: 2026-05-20
---

# Phase 02 Plan 03: Kiosk Position UI Summary

**SubCubeBar (confidence-attenuated), SpanUnderlay (row/unit-wrap bands), singleton full-cube faint band, and GSAP selection-lands choreography (span→pulse→bar, ≤600ms, hard-cancellable) wired from Zustand setLocateResult into the Nordic Grid kiosk**

## Performance

- **Duration:** 9 min
- **Started:** 2026-05-20T20:08:51Z
- **Completed:** 2026-05-20T20:18:37Z
- **Tasks:** 4/4 complete (Task 4 = on-Pi human-verify — **approved 2026-05-20**)
- **Files modified:** 10

## Accomplishments

- Added `SubInterval` TypeScript interface and wired `LocateResult.sub_cube_interval: SubInterval | null` through the full stack (types → store → components)
- `setLocateResult()` atomically sets all locate fields + increments `animationToken` in one Zustand `set()` call — singleton re-selection always fires GSAP (Pitfall D)
- `SubCubeBar`: confidence→opacity formula (`max(0.35, 0.35 + confidence × 0.65)`), singleton full-cube band at `opacity: 0.18` (D-02), `~` cue below 0.50 threshold (D-03), zero hardcoded hex
- `SpanUnderlay`: groups `labelSpan` by `(unit_id, row)`, renders pill bands via coordinate math from `CELL_SIZE_XL`/`CELL_GAP_XL` props — no `getBoundingClientRect()`, Pi-stable
- GSAP timeline: `useLayoutEffect` keyed on `[animationToken]`; hard-cancel `kill()` + `gsap.set()` reset; span 0.15s → pulse 0.10s+0.10s → bar 0.20s with −0.10s overlap = **0.45s total** (headroom to 0.60s SC-3 ceiling)
- `will-change` released on `tl.onComplete` AND on effect cleanup — never permanently reserved on Pi 5 compositor
- Frontend build (tsc + vite) passes clean; zero hardcoded hex in all Phase 2 components

## Task Commits

Each task was committed atomically:

1. **Task 1: TS types + Zustand setLocateResult + ResultsList wiring** - `c4e8389` (feat)
2. **Task 2: SubCubeBar + SpanUnderlay + Cube/ShelfGrid + CSS** - `db76849` (feat)
3. **Task 3: GSAP selection-lands timeline in KioskView** - `85aae6a` (feat)

Task 4 (human-verify on Pi hardware) — **approved by operator 2026-05-20** (selection-lands choreography, singleton band, confidence attenuation, hard-cancel, and span z-order all confirmed acceptable).

## Post-Checkpoint Refinements (operator UI feedback, committed after the checkpoint)

These landed as standalone `fix(kiosk)` commits after the build, in response to live operator review:

- **Position marker → tall vertical line** (`a010d05`): the bar now renders as a tall vertical band (~92% cube height, like a record standing in a bin) at the horizontal position, instead of an 8px bottom strip that read as a dot for narrow intervals.
- **Visible on the lit cube** (`a010d05`): drawn in IKEA blue on the lit (yellow) cube — yellow-on-yellow was invisible — matching the blue address-label precedent; yellow retained on dim companion cubes.
- **Subtler opacity + bin-ID watermark** (`d41f6a5`): bar opacity lowered to ~0.30–0.60; the bin ID became a large, centered, very-transparent (0.22) watermark behind the bar, resolving the label/bar overlap.
- **Search-dropdown UX** (`c1cc8f1`): results dropdown collapses on explicit selection; "did you mean" tap now sets the query and runs the corrected search.

These supersede the original §SubCubeBar visual spec (yellow horizontal bar) — see 02-UI-SPEC.md reconciliation note.

## Files Created/Modified

- `frontend/src/api/types.ts` — Added `SubInterval` interface; `LocateResult.sub_cube_interval: SubInterval | null`
- `frontend/src/state/store.ts` — Added `labelSpan`, `subCubeInterval`, `confidence` fields; `setLocateResult()` action; extended `clearSearch()`
- `frontend/src/routes/kiosk/ResultsList.tsx` — Replaced `setHighlightCube(result.primary_cube)` with `setLocateResult(result)` at both locate call sites
- `frontend/src/routes/kiosk/gridGeometry.ts` — `CELL_SIZE_XL=80`, `CELL_GAP_XL=12` from design-tokens.json
- `frontend/src/routes/kiosk/SubCubeBar.tsx` — Confidence-attenuated bar, singleton full-cube band (D-02), `~` cue (D-03)
- `frontend/src/routes/kiosk/SpanUnderlay.tsx` — Pill bands grouped by `(unit_id, row)`, coordinate math from props
- `frontend/src/routes/kiosk/Cube.tsx` — Optional `subInterval`/`confidence` props; renders `SubCubeBar`; companion bar for `crosses_boundary`
- `frontend/src/routes/kiosk/ShelfGrid.tsx` — Optional `labelSpan`/`subCubeInterval`/`confidence` props; renders `SpanUnderlay` when `labelSpan.length > 1`
- `frontend/src/routes/kiosk/KioskView.tsx` — GSAP `useLayoutEffect` timeline; `shelfAreaRef` for scoped selectors; props passed to `ShelfGrid`
- `frontend/src/routes/kiosk/kiosk.css` — `.cube z-index:1`, `.span-underlay__band z-index:0` (D-04), `.is-animating will-change`, `sub-cube-bar` opacity formula, `.shelf-area position:relative`

## Decisions Made

- **Selector-scoped GSAP (no forwardRef):** Querying by `[data-state="lit"]`, `.sub-cube-bar`, `.span-underlay__band` within `shelfAreaRef.current` avoids threading refs through 3 component layers. The UI-SPEC explicitly specifies this strategy (§Ref Strategy).
- **Per-unit position:relative wrapper:** `ShelfGrid` wraps the `<div className="shelf-grid">` in a `position:relative` div so `SpanUnderlay` bands anchor within the unit, not the full shelf-area. This avoids needing to compute inter-unit offsets in `SpanUnderlay`.
- **useLayoutEffect for GSAP effect:** Ensures the lit DOM nodes rendered by the new selection are mounted before `querySelector` runs — avoids a race where `useEffect` fires before the DOM update is painted.
- **Singleton full-cube band (D-02 override):** CUBE-10 literal says "tick-mark indicator"; D-02 owner decision overrides to faint full-cube band. Reconciliation comment in `SubCubeBar.tsx` documents the override.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Adjustment] Per-unit positioning wrapper instead of shelf-area-level absolute**

- **Found during:** Task 2 (SpanUnderlay implementation)
- **Issue:** The plan specified SpanUnderlay rendering "as a sibling of `.shelf-grid`" within the shelf-section. If positioned absolutely within `.shelf-area`, computing the x-offset of each unit requires knowing the actual pixel offsets of each `shelf-section` within `.shelf-area`, which depends on dynamic flex layout. The `SpanUnderlay` would need to receive unit position offsets as props or use `getBoundingClientRect()`.
- **Fix:** Wrapped `<div className="shelf-grid">` in a `position:relative` div within `ShelfGrid`. Each `SpanUnderlay` positions bands within its own unit's coordinate space, so only intra-unit column/row math is needed. This is simpler, avoids runtime layout reads, and is Pi-stable. The plan's `SpanUnderlay` geometry formula (using `unitColumnOffset`) is a higher-level concept that becomes unnecessary when each unit has its own positioning context.
- **Files modified:** `frontend/src/routes/kiosk/ShelfGrid.tsx`
- **Verification:** TypeScript passes; no `getBoundingClientRect()` in `SpanUnderlay.tsx`
- **Committed in:** `db76849`

---

**Total deviations:** 1 auto-fixed (Rule 1 — geometry approach adjustment for correctness)
**Impact on plan:** SpanUnderlay bands anchor correctly per-unit; the visual result matches the spec (bands connect within a unit's span). Cross-unit spans still produce correct multi-band output (one band per unique `(unit_id, row)`). No scope change.

## Issues Encountered

None — TypeScript passed on first try for all three tasks; build clean.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Autonomous tasks complete: types, store, components, GSAP timeline, CSS all compile and build clean
- **Checkpoint resolved (Task 4):** operator verified the experience and approved (2026-05-20). The five on-hardware checks (choreography ≤600ms feel, singleton band, confidence attenuation, mid-animation interruption, span z-order) are accepted, with the post-checkpoint refinements above applied.
- Plan 02-03 is complete; plan 02-04 (developer A/B harness) completed in the same phase.

## Known Stubs

None — all data flows from the real `/api/locate` response; no placeholder data.

## Threat Flags

None — no new network endpoints or auth paths introduced. Client-side rendering of `sub_cube_interval` values via CSS custom properties only (T-02-11: backend guarantees `0 ≤ start ≤ end ≤ 1`).

## Self-Check: PASSED

- All 10 key files exist on disk
- All 3 task commits (`c4e8389`, `db76849`, `85aae6a`) present in `git log`
- `npx tsc --noEmit` exits 0
- `npm run build` succeeds (486 modules, no errors)
- Zero hardcoded hex in `SubCubeBar.tsx`, `SpanUnderlay.tsx` (grep check passed)
- No `box-shadow` in GSAP tweens (grep check passed)

---
*Phase: 02-real-position-estimation*
*Plan: 03 (complete — Task 4 human-verify approved 2026-05-20)*
*Completed: 2026-05-20*

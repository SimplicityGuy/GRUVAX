---
phase: 09-offline-reconnect-ux
plan: "03"
subsystem: frontend-kiosk
tags: [offline, sse, banner, degraded-mode, reconnect, react, zustand, design-tokens]
dependency_graph:
  requires: ["09-02"]
  provides: ["OFF-01", "OFF-02", "OFF-04"]
  affects: ["KioskView", "SearchBox", "OfflineBanner"]
tech_stack:
  added: []
  patterns:
    - "SSE-authoritative offline banner (bannerVisible store flag vs navigator.onLine cosmetic hint)"
    - "wasOffline = bannerVisible guard prevents first-load spurious toast (Blocker 1)"
    - "React useGruvaxStore reactive selector + .getState() in SSE handlers (Pitfall 5)"
    - "Nordic Grid reversed palette (--gruvax-blue bg + --gruvax-white text) for urgent operational signal"
key_files:
  created:
    - frontend/src/routes/kiosk/OfflineBanner.tsx
    - frontend/src/routes/kiosk/OfflineBanner.css
    - frontend/src/routes/kiosk/OfflineBanner.test.tsx
    - frontend/src/routes/kiosk/SearchBox.test.tsx
  modified:
    - frontend/src/routes/kiosk/SearchBox.tsx
    - frontend/src/routes/kiosk/KioskView.tsx
    - frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
decisions:
  - "OfflineBanner.css defines local offline-banner-enter keyframe (not reusing staleness-bar-enter) to eliminate CSS import-order uncertainty while keeping identical motion spec"
  - "SwitchProfileButton gated via {sseConnected && <SwitchProfileButton />} (conditional render) rather than adding a disabled prop — simpler and SwitchProfileButton already renders null for single-profile"
  - "AUTO_DISMISS_MS=4000 (existing SyncToast constant) accepted; CONTEXT's ~2-3s is a guideline, not a hard constraint"
metrics:
  duration: "~40 minutes"
  completed: "2026-06-02"
  tasks: 3
  files: 7
---

# Phase 9 Plan 03: Offline Banner + Degraded Mode + Reconnect Toast Summary

**One-liner:** SSE-authoritative OfflineBanner (reversed Nordic Grid palette) + degraded read-only mode (search/profile/cube-tap locked) + "Back online" SyncToast on genuine reconnect, with device-revoked terminal path and RecentlyPulledStrip preserved.

## What Was Built

### Task 1: OfflineBanner component + CSS + tests (OFF-01, D-01..D-04)

**OfflineBanner.tsx** mirrors StalenessBar exactly — reads `connectivity.sseConnected` via
`useGruvaxStore((s) => s.connectivity.sseConnected)` reactive selector; early-returns null
when connected; tracks `navigator.onLine` via `useState(navigator.onLine)` + window
event listeners for the cosmetic copy-hint only (PITFALLS 35); two copy variants:
- `sseConnected=false` + `onLine=true` → "Can't reach GRUVAX — trying to reconnect…"
- `sseConnected=false` + `onLine=false` → "No network — trying to reconnect…"

Has `role="alert"` + `aria-live="polite"`, WifiOff inline SVG (`aria-hidden="true"`), no
dismiss button (D-04 persistent).

**OfflineBanner.css** uses `--gruvax-blue` background + `--gruvax-white` text — the urgent
reversed palette distinct from StalenessBar's yellow. Zero hardcoded hex. All spacing, font,
animation reference `var(--gruvax-*)` tokens. Defines `offline-banner-enter` keyframe locally
to avoid CSS import-order uncertainty.

**OfflineBanner.test.tsx** — 11 tests covering: connected early-return (null render), both
copy variants, a11y attrs, aria-hidden SVG, non-dismissibility (D-04).

### Task 2: SearchBox isOffline prop (OFF-02, D-06)

Added `isOffline?: boolean` to `SearchBoxProps`. When `true`:
- Input is `disabled` (greyed + non-focusable, removed from tab order)
- Placeholder swapped to "Search unavailable while offline"
- Loading indicator suppressed (no `showLoading` while offline)
- Error affordance suppressed (error class masked while offline)
- Clear-X suppressed (no query interaction offline)
- `search-box--offline` CSS class added for token-based grey styling

**SearchBox.test.tsx** (new) — 12 tests covering online defaults + offline gating; key
assertions: `expect(input).toBeDisabled()` + placeholder swap + loading/error suppression.

### Task 3: KioskView wiring (OFF-01/02/04)

**Imports added:** `OfflineBanner`, `SyncToast`, `./OfflineBanner.css`

**New state:** `sseConnected = useGruvaxStore((s) => s.connectivity.sseConnected)` (reactive);
`const [showBackOnlineToast, setShowBackOnlineToast] = useState(false)`

**onopen handler extended (Blocker 1 guard):**
```ts
const wasOffline = useGruvaxStore.getState().connectivity.bannerVisible  // NOT !sseConnected
useGruvaxStore.getState().setSseConnected(true)  // also clears bannerVisible
resync()
if (wasOffline) setShowBackOnlineToast(true)
```
`bannerVisible` starts `false` and only becomes `true` after a real disconnect — so the
toast fires only on genuine offline→online transitions, not on the first page-load `onopen`.

**JSX gating (D-04/05/06):**
- `{!sseConnected && <OfflineBanner />}` — top banner slot
- `{sseConnected && <StalenessBar ...>}` — suppressed offline
- `{sseConnected && needsReauth && <ReauthBanner ...>}` — suppressed offline
- `{sseConnected && newRecordState && ... }` — pill suppressed offline
- `<ReassignBanner />` — always rendered (completed-event signal)
- `isOffline={!sseConnected}` passed to SearchBox (D-06)
- `onCubeTap={sseConnected ? setTappedCube : undefined}` (D-05)
- `{sseConnected && <SwitchProfileButton />}` (D-05)
- `{showBackOnlineToast && <SyncToast message="Back online" onDismiss={...} />}` (D-07)

**device_revoked path preserved (T-09-08):** The `device_revoked` handler calls
`triggerRevoke()` in App.tsx independently of the banner — no regression.

**KioskView.EventSource.test.tsx extended** with 3 new tests:
- Blocker 1: initial `onopen` with `bannerVisible=false` → toast NOT shown
- OFF-01: `onerror` → OfflineBanner appears (role=alert), SearchBox disabled
- OFF-04: `onopen` after `onerror` → banner cleared, toast shown

All 17 test files (120 tests) green.

## Deviations from Plan

### Auto-fixed Issues

None.

### Deliberate Adjustments

**1. [Planner's Discretion] Local offline-banner-enter keyframe instead of reusing staleness-bar-enter**
- **Decision:** Defined `offline-banner-enter` in OfflineBanner.css rather than relying on
  the `staleness-bar-enter` keyframe from StalenessBar.css being in global scope.
- **Rationale:** The PATTERNS.md noted import-order uncertainty. A local identical keyframe
  eliminates any runtime risk with zero downside. Motion spec is identical (0→1 opacity,
  0→48px max-height, 250ms ease-decelerate).

**2. [Planner's Discretion] SwitchProfileButton conditional render vs disabled prop**
- **Decision:** Used `{sseConnected && <SwitchProfileButton />}` (conditional render) instead
  of adding a `disabled` prop to SwitchProfileButton.
- **Rationale:** SwitchProfileButton already returns null for single-profile deployments; the
  component has no disabled-state styling. Conditional render is cleaner and matches the plan's
  "OR render ... conditionally" option.

## Threat Coverage

| Threat | Status | Evidence |
|--------|--------|----------|
| T-09-07 (client-side gating elevation) | Accepted — UX only | Gating is UI-layer only; server-side authz unaffected |
| T-09-08 (device_revoked masked by offline banner) | Mitigated | device_revoked handler calls triggerRevoke() independently; Phase 6 test passes unchanged |
| T-09-09 (navigator.onLine masking LAN outage) | Mitigated | Banner renders on !sseConnected only; onLine only selects copy text |
| T-09-10 (dismissed diff badge reappearing) | Mitigated | server_hello resync+invalidate unchanged; dismissed_diff_at logic not touched |

## Known Stubs

None. All offline behavior is fully wired.

## Self-Check

**Files created/modified:**
- [x] `frontend/src/routes/kiosk/OfflineBanner.tsx` — FOUND
- [x] `frontend/src/routes/kiosk/OfflineBanner.css` — FOUND
- [x] `frontend/src/routes/kiosk/OfflineBanner.test.tsx` — FOUND
- [x] `frontend/src/routes/kiosk/SearchBox.tsx` — MODIFIED
- [x] `frontend/src/routes/kiosk/SearchBox.test.tsx` — FOUND
- [x] `frontend/src/routes/kiosk/KioskView.tsx` — MODIFIED
- [x] `frontend/src/routes/kiosk/KioskView.EventSource.test.tsx` — MODIFIED

**Commits:**
- `113691b` — feat(09-03): create OfflineBanner component + CSS + tests (Task 1)
- `3511360` — feat(09-03): add isOffline degraded-mode prop to SearchBox (Task 2)
- `91ba13c` — feat(09-03): wire OfflineBanner + degraded gating + Back-online toast in KioskView (Task 3)

**Test results:** 17/17 test files, 120/120 tests green. TypeScript clean (`tsc --noEmit` exits 0).

## Self-Check: PASSED

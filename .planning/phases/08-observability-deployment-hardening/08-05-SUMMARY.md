---
phase: 08-observability-deployment-hardening
plan: "05"
subsystem: frontend/kiosk
tags: [staleness-banner, kiosk, ux, accessibility, obs-06, nordic-grid]
requirements: [OBS-06]

dependency_graph:
  requires: ["08-03"]
  provides: ["kiosk-staleness-banner"]
  affects: ["frontend/src/routes/kiosk/KioskView.tsx"]

tech_stack:
  added: []
  patterns:
    - "useQuery health endpoint for kiosk banner data (60s refetchInterval)"
    - "Conditional-null component render pattern (StalenessBar returns null below threshold)"
    - "TDD RED/GREEN cycle for threshold logic"
    - "CSS @keyframes mount animation via design tokens only"

key_files:
  created:
    - frontend/src/routes/kiosk/StalenessBar.tsx
    - frontend/src/routes/kiosk/StalenessBar.css
    - frontend/src/routes/kiosk/StalenessBar.test.tsx
  modified:
    - frontend/src/routes/kiosk/KioskView.tsx

decisions:
  - "STALE_THRESHOLD_SECONDS = 14 * 24 * 60 * 60 = 1,209,600s (D-01 locked threshold)"
  - "StalenessBar renders above shelf-area div (below search section), never overlaying the grid"
  - "health query uses 60s refetchInterval — D-11 no-polling applies to admin diagnostics only, not kiosk banner"
  - "CSS uses @keyframes mount animation keyed to class presence (not JS timer), consistent with UI-SPEC"
  - "Threshold comparison uses <= (not <) so exactly 14d hides the banner; only strictly > 14d triggers it"

metrics:
  duration: "~7 minutes"
  completed: "2026-05-24"
  tasks_completed: 3
  tasks_total: 3
  files_created: 3
  files_modified: 1
---

# Phase 08 Plan 05: Kiosk Sync-Staleness Banner Summary

**One-liner:** Full-width yellow Nordic Grid banner above the kiosk grid reading `sync_age_seconds` from `/api/health`, showing "Collection data may be outdated — last synced {N}d ago" when age exceeds 14 days.

## What Was Built

**StalenessBar component** (`frontend/src/routes/kiosk/StalenessBar.tsx`):

- `STALE_THRESHOLD_SECONDS = 14 * 24 * 60 * 60` (1,209,600s — D-01 locked)
- `interface Props { syncAgeSeconds: number | null }` — returns `null` when null or `<= threshold`
- When stale: renders `.staleness-bar` div with `role="alert"` + `aria-live="polite"`
- Inline 18×18 AlertTriangle SVG (`aria-hidden="true"`) — decorative, not load-bearing
- Exact copy: `Collection data may be outdated — last synced ${Math.floor(seconds / 86400)}d ago`
- Em dash separator; sentence case; whole days only; no jargon (T-08-17 mitigated)

**StalenessBar CSS** (`frontend/src/routes/kiosk/StalenessBar.css`):

- Tokens only — no hardcoded hex (`--gruvax-yellow` bg, `--gruvax-blue-darker` text)
- `font-size: var(--gruvax-text-body-lg)` (18px) — accessibility floor for yellow-on-dark 3.1:1 contrast
- Padding: `var(--gruvax-space-3)` vertical × `var(--gruvax-space-4)` horizontal
- Mount: `@keyframes staleness-bar-enter` — opacity 0→1, max-height 0→48px over `var(--gruvax-duration-base)` ease-decelerate
- `border-radius: 0` — flush edge-to-edge (system notification bar style)

**KioskView wiring** (`frontend/src/routes/kiosk/KioskView.tsx`):

- Added `useQuery<{ sync_age_seconds?: number | null }>({ queryKey: ['health'], queryFn: fetch('/api/health').then(r=>r.json()), staleTime: 60_000, refetchInterval: 60_000 })`
- Renders `<StalenessBar syncAgeSeconds={healthData?.sync_age_seconds ?? null} />` above the `.shelf-area` div (line 457), below the search section — never overlays the grid
- When offline, `healthData` is undefined → `sync_age_seconds ?? null` → banner hides silently

## Test Coverage

17 tests in `StalenessBar.test.tsx` covering:

- null, 0, exactly-at-threshold, and below-threshold → renders nothing
- `1_209_601s` (one second over 14d) → banner renders
- Exact copy contents, em dash presence, `14d` whole-day formatting
- `18d` and `30d` correctness; `Math.floor` partial-day does not bump count
- `role="alert"` and `aria-live="polite"` attributes
- `aria-hidden="true"` on SVG icon
- `.staleness-bar` class present
- No hours suffix (`h`) in copy; no jargon (`sync_age_seconds`, `collection_items`, `SYNC STALE`)

## Deviations from Plan

None — plan executed exactly as written.

## Checkpoint Handling

**Task 3** (`checkpoint:human-verify`) — auto-approved per `--auto` mode.

The following manual browser verification steps are DEFERRED to the phase-end HUMAN-UAT flow:

1. Rebuild stack: `docker compose up -d --build api`
2. Force stale state (set `sync_age_seconds > 1,209,600` in dev, or stub in a dev build) — wait up to 60s for health refetch, or reload kiosk
3. Confirm yellow banner appears ABOVE the grid (not overlaying) with copy "Collection data may be outdated — last synced {N}d ago", Space Grotesk 18px, blue-darker text, warning triangle icon, no dismiss button
4. Run a search — confirm results still work; search a nonsense term — confirm no-results page is GENERIC (no staleness hint — D-02)
5. Restore recent sync timestamp — confirm banner disappears

## Known Stubs

None — implementation is complete. The health endpoint returns real `sync_age_seconds` data (wired in Plan 03).

## Threat Flags

None — this plan only reads from the existing `/api/health` public endpoint; no new network surface introduced. T-08-17 (copy information disclosure) and T-08-18 (health refetch DoS) mitigated per plan threat model.

## Self-Check

### Files Created/Modified

- [x] `frontend/src/routes/kiosk/StalenessBar.tsx` — exists
- [x] `frontend/src/routes/kiosk/StalenessBar.css` — exists
- [x] `frontend/src/routes/kiosk/StalenessBar.test.tsx` — exists (17 tests green)
- [x] `frontend/src/routes/kiosk/KioskView.tsx` — modified (StalenessBar import + health query + JSX)

### Commits

- `df0db7b` — `test(08-05): add failing test for StalenessBar threshold logic + a11y` (RED)
- `3f52005` — `feat(08-05): implement StalenessBar component + Nordic Grid CSS (OBS-06)` (GREEN)
- `433bdd3` — `feat(08-05): wire StalenessBar into KioskView via /api/health query` (Task 2)

## Self-Check: PASSED

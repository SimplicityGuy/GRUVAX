---
phase: 10-shelf-fill-overview
plan: "01"
subsystem: frontend
tags: [ui, locator-header, fill-shading, popover, nordic-grid, tokens, tdd]
dependency_graph:
  requires: []
  provides:
    - AdminCube type with record_count (frontend/src/api/types.ts)
    - LocatorHeader fill-shaded mini-Kallax with tap-to-reveal popover
    - admin.css fill/empty/popover CSS classes (token-only)
    - LocatorHeader.test.tsx (8 tests, all GREEN)
  affects:
    - ShelfBinList.tsx (can now pass cubes prop to LocatorHeader)
tech_stack:
  added: []
  patterns:
    - cubeMap useMemo keyed "${row}-${col}" for O(1) per-cell lookup (mirrors ShelfGrid)
    - CSS color-mix(in srgb, ...) fill gradient via --fill custom property
    - Tap-to-reveal popover via useState activeIdx + document event cleanup
    - Mutually-exclusive cell state: lit > empty > fill (lit takes priority)
    - Math.min(fill_level, 1) clamp for D-03 compliance
key_files:
  created:
    - frontend/src/routes/admin/LocatorHeader.test.tsx
  modified:
    - frontend/src/api/types.ts
    - frontend/src/routes/admin/LocatorHeader.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - Cells rendered as <button type="button"> for tap affordance and aria-pressed state
  - Popover uses inline style for dynamic positioning (flip above rows >= 2)
  - cubes prop is optional so existing call sites remain backward-compatible
  - binId derived from shelfLetter(unitId) + (row * cols + col + 1) for human-readable IDs
metrics:
  duration: "336s (~6 min)"
  completed: "2026-06-02"
  tasks_completed: 3
  files_modified: 4
requirements-completed: [UX-01]
---

# Phase 10 Plan 01: LocatorHeader Fill Shading + Popover Summary

**One-liner:** Token-only blue-saturation fill gradient + tap-to-reveal popover on mini-Kallax LocatorHeader via `--fill` custom property and `color-mix(in srgb, ...)`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix AdminCube type (remove stale fields, add record_count) | a60d847 | frontend/src/api/types.ts |
| 2 | Write LocatorHeader fill + popover tests (RED) | 5c4577a | frontend/src/routes/admin/LocatorHeader.test.tsx |
| 3 | Implement fill shading, popover, and token-only CSS (GREEN) | 256faf3 | frontend/src/routes/admin/LocatorHeader.tsx, admin.css |

## What Was Built

**AdminCube type correction** — removed stale `last_label` / `last_catalog` fields (not returned by `GET /api/admin/cubes`), added `record_count: number` (returned by `cubes.py:211`). Pre-removal grep gate confirmed no `AdminCube`-typed variable reads the stale fields; `CubeBoundaryEdit` and `AdminCubeBoundary` retain their `last_label`/`last_catalog` fields untouched.

**LocatorHeader fill shading** — added optional `cubes?: AdminCube[]` prop. When present, each cell resolves to one of three mutually-exclusive states with lit priority: `locator-cell--lit` (edited bin, yellow), `locator-cell--empty` (CUBE-05 dashed desaturated), or `locator-cell--fill` (blue gradient via `--fill` custom property). When absent, falls back to the pre-existing `locator-cell--dim` / `locator-cell--lit` behavior.

**Fill gradient implementation** — CSS `color-mix(in srgb, var(--gruvax-blue) calc(var(--fill, 0) * 70%), var(--gruvax-cell-dim))` driven by the `--fill` inline style property (clamped to `Math.min(fill_level, 1)` for D-03 compliance). Chromium 111+ natively supports `color-mix()` — the kiosk target.

**Tap-to-reveal popover** — single `useState<number | null>` active index, `document` `pointerdown` tap-away dismissal, `Escape` `keydown` dismissal. Popover content: filled cube shows bin ID + `{record_count} records · {pct}%`; empty cube shows bin ID + "Empty bin". No `dangerouslySetInnerHTML` — all server data rendered as React text nodes (T-10-01 mitigation).

**Token-only CSS** — `.locator-mini-grid-wrap`, `.locator-cell--fill`, `.locator-cell--empty`, `.locator-fill-popover` and its `-id`/`-data`/`-empty` text variants. Every value references a `var(--gruvax-*)` token — no hardcoded hex, no yellow (yellow reserved for `.locator-cell--lit`).

**TDD gate compliance** — 8 RED tests committed at 5c4577a; all 8 pass GREEN at 256faf3.

## Verification Results

- `npm run test -- LocatorHeader` exits 0 (8/8 tests GREEN)
- `tsc --noEmit` exits 0 (no TypeScript errors)
- `admin.css` contains `color-mix(in srgb, var(--gruvax-blue)` and `.locator-fill-popover`
- No hardcoded hex in new CSS block
- No `dangerouslySetInnerHTML` in `LocatorHeader.tsx`
- `data-row` / `data-col` attributes present on all cell buttons
- `shelfLetter` imported from `../../lib/shelf`; `AdminCube` from `../../api/types`

## Success Criteria Status

| Criterion | Status |
|-----------|--------|
| AdminCube: record_count added, last_label/last_catalog removed, tsc clean | DONE |
| Non-empty cubes render continuous blue gradient via --fill + color-mix (UX-01 SC1) | DONE |
| Empty cubes render CUBE-05 desaturated state, distinct from full cubes (UX-01 SC3, D-01) | DONE |
| fill_level > 1.0 clamps to 1.0 visually (D-03) | DONE |
| Edited-bin yellow (.locator-cell--lit) keeps priority over fill (Finding 9) | DONE |
| Tap-to-reveal popover: bin ID + record count + % / "Empty bin" (D-05/D-06) | DONE |
| All new CSS references design tokens only — no hardcoded hex (UX-01 SC1) | DONE |

## Deviations from Plan

None — plan executed exactly as written.

## TDD Gate Compliance

- RED gate: `test(10-01)` commit 5c4577a (8 failing tests)
- GREEN gate: `feat(10-01)` commit 256faf3 (8 passing tests)
- REFACTOR gate: not needed — implementation is clean

## Known Stubs

None — all data flows from the `cubes` prop wired to `GET /api/admin/cubes` (plan 02 wires ShelfBinList → LocatorHeader). The `cubes` prop is optional with backward-compatible fallback; wiring it is plan 02's responsibility.

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced. The only surface change is rendering `record_count`, `fill_level`, and `first_label` from `GET /api/admin/cubes` (already admin-authenticated) in the LocatorHeader popover and aria-labels — documented as T-10-01 in the plan's threat register and mitigated by React text node rendering (no `dangerouslySetInnerHTML`).

## Self-Check: PASSED

Files exist:
- frontend/src/api/types.ts: FOUND
- frontend/src/routes/admin/LocatorHeader.tsx: FOUND
- frontend/src/routes/admin/LocatorHeader.test.tsx: FOUND
- frontend/src/routes/admin/admin.css: FOUND

Commits exist:
- a60d847 (Task 1): FOUND
- 5c4577a (Task 2): FOUND
- 256faf3 (Task 3): FOUND

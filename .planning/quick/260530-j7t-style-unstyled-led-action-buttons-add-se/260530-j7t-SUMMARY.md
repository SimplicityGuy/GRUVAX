---
quick_id: 260530-j7t
phase: quick
plan: 260530-j7t
subsystem: frontend/admin-ui
tags: [css, design-tokens, admin, settings, led]
completed: 2026-05-30
duration_minutes: 5
tasks_completed: 1
files_modified: 1
key_files:
  modified:
    - frontend/src/routes/admin/admin.css
decisions:
  - Used var(--gruvax-blue-light) for hover background, confirmed existing token usage in file (lines 438, 745, 909)
  - Matched full-width (width: 100%) from .settings-btn-primary rather than fit-content from .editor-btn-secondary
  - Padding set to var(--gruvax-space-3) var(--gruvax-space-5) and min-height 48px to match .settings-btn-primary stack height
---

# Phase quick Plan 260530-j7t: Style Unstyled LED Action Buttons Summary

**One-liner:** Added `.settings-btn-secondary` CSS rule (base + :hover + :focus-visible + :disabled) so ALL OFF and RUN DIAGNOSTIC buttons render with Nordic Grid blue-outline secondary style instead of default browser grey.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add the .settings-btn-secondary CSS rule | c9bd90e | frontend/src/routes/admin/admin.css (+31 lines) |

## What Was Built

The `.settings-btn-secondary` rule set was inserted immediately after the `.settings-btn-primary:disabled` block (line 426) in `frontend/src/routes/admin/admin.css`, directly before the `/* ── FillBar ── */` comment.

The rule mirrors the established `.editor-btn-secondary` convention but adapts it for the full-width LED-action button stack:
- `width: 100%` (matches `.settings-btn-primary`, vs fit-content in `.editor-btn-secondary`)
- `min-height: 48px` and `padding: var(--gruvax-space-3) var(--gruvax-space-5)` (matches primary stack)
- Blue text on transparent background with 1px blue border (Nordic Grid secondary pattern)
- Hover: `var(--gruvax-blue-light)` background fill
- Focus-visible: 2px blue outline with 2px offset
- Disabled: 0.6 opacity, not-allowed cursor

All values use design tokens exclusively — no hardcoded hex values.

## Verification

- `grep -c ".settings-btn-secondary" frontend/src/routes/admin/admin.css` returns `4` (was 0)
- `tsc --noEmit` clean (run against main repo node_modules; CSS-only change, no TS impact)
- `eslint src/routes/admin/Settings.tsx` clean
- No hardcoded hex in the added rule

## Deviations from Plan

None — plan executed exactly as written.

## Known Stubs

None.

## Threat Flags

None — CSS-only change, no new network surface, auth paths, or schema changes.

## Self-Check: PASSED

- File modified: `frontend/src/routes/admin/admin.css` — confirmed
- Commit c9bd90e exists — confirmed
- `.settings-btn-secondary` appears 4 times in the CSS — confirmed
- No hex values in added rule — confirmed

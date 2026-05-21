---
phase: quick-260521-fn0
plan: 01
subsystem: frontend/admin-ui
tags: [ui-conformance, design-tokens, admin, quick-task]
dependency_graph:
  requires: []
  provides: [spec-conformant admin FillBar color logic, diff-validate-error CSS class, correct PIN and phantom copy, AlphaRail active-letter indicator, editor-btn-link style, correct badge typography and spacing tokens]
  affects: [frontend/src/routes/admin/]
tech_stack:
  added: []
  patterns: [Nordic Grid token consumption, three-tier fill bar logic, CSS class-driven color tiers]
key_files:
  created: []
  modified:
    - frontend/src/routes/admin/FillBar.tsx
    - frontend/src/routes/admin/PinOverlay.tsx
    - frontend/src/routes/admin/CubeEditor.tsx
    - frontend/src/routes/admin/AlphaRail.tsx
    - frontend/src/routes/admin/CubesGrid.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "FillBar uses CSS class modifiers (--near, --over) not inline style, preserving admin.css as single source of color truth"
  - "AlphaRail active-letter uses aria-current='true' for a11y alongside the visual class"
  - "Pre-existing React Compiler lint errors (8 total, across AdminShell/CubeEditor/DiffPreviewSheet/PinOverlay) deferred — not caused by this task; see deferred-items.md"
  - "2px pill vertical paddings retained as documented spacing-exceptions per spec; horizontal aligned to --gruvax-space-2"
metrics:
  duration: ~25 min
  completed: "2026-05-21"
  tasks_completed: 3
  files_modified: 6
---

# Phase Quick-260521-fn0 Plan 01: Fix All 8 Phase 3 UI Audit Findings Summary

**One-liner:** Admin FillBar inverted color logic, undefined diff-validate-error CSS class, truncated error copy, off-spec button style, missing AlphaRail active state, 10px badge sizes, and bare gap token — all fixed to conform with 03-UI-SPEC.md.

---

## What Was Built

Closed all 8 findings from the Phase 3 UI audit (`03-UI-REVIEW.md`) that reduced the admin UI score to 19/24. Two were real bugs; six were UI-SPEC copy/style/token conformance gaps.

**Findings closed:**

| # | Finding | File(s) | Fix |
|---|---------|---------|-----|
| 1 | Admin FillBar color logic inverted (two-tier, wrong thresholds) | `FillBar.tsx`, `admin.css` | Three-tier classes: default=blue-light, --near=yellow, --over=error; removed dead --warn class |
| 2 | `diff-validate-error` CSS class undeclared (silent no-style) | `admin.css` | Added `.diff-validate-error` mirroring diff-warning--overstuffed error treatment |
| 3 | Wrong-PIN copy truncated ("Incorrect PIN" missing period + instruction) | `PinOverlay.tsx` | `'Incorrect PIN. Try again.'` exact spec §A string |
| 4 | Phantom copy diverges from spec (×2 occurrences) | `CubeEditor.tsx` | `'No match in collection. Did you mean one of these?'` (×2) |
| 5 | SUGGEST MIDPOINT uses outlined button, not link style | `CubeEditor.tsx`, `admin.css` | className `editor-btn-link`; new `.editor-btn-link` rule (Barlow 700 14px blue, underline on hover) |
| 6 | AlphaRail has no active-letter visual indicator | `AlphaRail.tsx`, `CubesGrid.tsx`, `admin.css` | `activeLetter` prop + `alpha-rail-btn--active` class (blue bg + white text); CubesGrid tracks state |
| 7 | 10px badge font sizes; cube-card-label--last font-family mismatch | `admin.css` | 10px → `var(--gruvax-text-label, 11px)` for two badges; label--last → font-ui / 14px / weight 400 / no uppercase |
| 8 | `gap: 4px` bare px; 2px pill paddings undocumented | `admin.css` | `gap: var(--gruvax-space-1)`; 2px paddings carry spacing-exception comments; 6px/8px → `--gruvax-space-2` |

---

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `dc23467` | fix(260521-fn0): component logic and copy — 5 UI-SPEC conformance fixes |
| Task 2 | `b47c097` | fix(260521-fn0): admin.css — define missing classes, fix typography and spacing |

---

## Deviations from Plan

### Pre-existing Lint Failures (Out of Scope)

**[Rule 1 candidate — but pre-existing, out of scope per scope boundary]**

`npm run lint` exits non-zero due to 8 pre-existing React Compiler lint errors across `AdminShell.tsx`, `DiffPreviewSheet.tsx`, `CubeEditor.tsx`, and `PinOverlay.tsx`. These errors exist on the baseline commit `d5d9a52` before any changes from this task. The plan's success criterion "lints clean" cannot be met without fixing pre-existing architectural patterns (setState-in-effect, Date.now in initializer, hoisted function references) that are outside the visual-conformance scope of this quick task.

**None of the 8 lint errors were introduced by this task.** All files I modified had their new content compile cleanly (TypeScript compiles with `tsc -b --noEmit` exit 0).

Documented in: `.planning/quick/260521-fn0-fix-all-8-findings-from-the-phase-3-ui-a/deferred-items.md`

**Recommended follow-up:** Create a quick task or Phase 3 plan task to address React Compiler lint compliance for the admin shell components.

---

## Deferred Issues

- 8 pre-existing React Compiler lint errors requiring architectural fixes in admin shell components (see deferred-items.md)

---

## Known Stubs

None — all 8 UI-REVIEW findings are fully implemented; no placeholders or TODO stubs remain in the changed files.

---

## Threat Flags

None — changes are purely frontend CSS class names, string literals, and UI state tracking. No new network endpoints, auth paths, or trust boundaries introduced.

---

## Self-Check: PASSED

| Check | Result |
|-------|--------|
| `frontend/src/routes/admin/FillBar.tsx` | FOUND |
| `frontend/src/routes/admin/PinOverlay.tsx` | FOUND |
| `frontend/src/routes/admin/CubeEditor.tsx` | FOUND |
| `frontend/src/routes/admin/AlphaRail.tsx` | FOUND |
| `frontend/src/routes/admin/CubesGrid.tsx` | FOUND |
| `frontend/src/routes/admin/admin.css` | FOUND |
| Commit `dc23467` | FOUND |
| Commit `b47c097` | FOUND |

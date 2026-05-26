---
phase: 07-wizards-import-export
plan: "06"
subsystem: frontend
tags: [gap-closure, wizard, reshuffle, entry-ux, admin-nav]
dependency_graph:
  requires: []
  provides:
    - wizard-entry-choice-landing
    - reshuffle-discoverable-from-nav
  affects:
    - frontend/src/routes/admin/Wizard.tsx
    - frontend/src/routes/admin/admin.css
tech_stack:
  added: []
  patterns:
    - outer-gate-inner-walk pattern (React Rules of Hooks safe conditional render)
    - navigate-to-canonical-url mode entry (single source of truth for mode, D-01)
key_files:
  created: []
  modified:
    - frontend/src/routes/admin/Wizard.tsx
    - frontend/src/routes/admin/admin.css
decisions:
  - "Outer Wizard + inner WizardWalk split keeps all hooks in WizardWalk always called (Rules of Hooks)"
  - "Entry buttons navigate to ?mode=setup / ?mode=reshuffle canonical URLs, not a second mode setter"
  - "No AdminShell.tsx changes needed — WIZARD tab already links to /admin/wizard with no ?mode= override"
metrics:
  duration: "4 min"
  completed_date: "2026-05-24"
  tasks_completed: 2
  files_changed: 2
---

# Phase 07 Plan 06: Wizard Entry Choice (Gap G1) Summary

Closed gap G1 (UAT test 2, major): reshuffle wizard was unreachable from the UI — only accessible via direct `?mode=reshuffle` URL or a pre-existing draft. Added a discoverable mode-choice landing to `/admin/wizard` showing "START SETUP WIZARD" and "START RESHUFFLE" when neither signal is present.

## What Was Built

**Task 1 — Mode-choice landing in Wizard.tsx** (commit b04fe74)

Added a `WizardEntryChoice` component and an outer `Wizard` gate. When `/admin/wizard` is visited with no `?mode=` query param and no `reshuffleDraft` in the store, the landing renders instead of jumping straight into setup. Both CTA buttons use locked UI-SPEC copy verbatim and navigate to the canonical `?mode=setup` / `?mode=reshuffle` URLs, keeping D-01 (one source of truth for mode) intact.

The outer `Wizard` calls `useSearchParams()` and `useAdminStore()` unconditionally before the conditional return, then delegates to `WizardWalk` (the renamed walk engine). This pattern is valid per the React Rules of Hooks — hooks are called before any early return.

Preserved invariants:
- `?mode=reshuffle` deep-link → skips landing, enters walk directly
- `?mode=setup` deep-link → skips landing, enters walk directly
- Existing `reshuffleDraft` → skips landing, auto-resumes reshuffle walk

**Task 2 — Admin nav chrome (AdminShell.tsx)** — no code changes required

The WIZARD NavLink already points to `/admin/wizard` with no `?mode=` override. The Task-1 landing is now the first screen the owner sees when clicking WIZARD, making reshuffle discoverable without URL typing. Nav order (SETTINGS · CUBES · HISTORY · WIZARD · IMPORT) unchanged.

## Deviations from Plan

None — plan executed exactly as written.

The plan anticipated potential AdminShell changes ("If — and only if — the Task-1 landing alone does not make reshuffle obviously reachable, add a lightweight RESHUFFLE affordance"). The existing nav satisfies the condition, so no affordance was added.

## Files Modified

| File | Change |
|------|--------|
| `frontend/src/routes/admin/Wizard.tsx` | Added `WizardEntryChoice` component; refactored `Wizard` into outer gate + `WizardWalk` inner; updated JSDoc |
| `frontend/src/routes/admin/admin.css` | Added `.wizard-entry`, `.wizard-entry-heading`, `.wizard-entry-body`, `.wizard-entry-actions` classes using `--gruvax-*` tokens only |

## Verification

- `tsc --noEmit` exits 0
- `npm run build` exits 0
- `grep "START RESHUFFLE" Wizard.tsx` → match at line 88
- `grep "START SETUP WIZARD" Wizard.tsx` → match at line 81
- `grep "mode=reshuffle" Wizard.tsx` → match at line 86
- No `innerHTML` usage in code (doc comment only, pre-existing)
- No hardcoded hex in Wizard.tsx or AdminShell.tsx
- Nav order unchanged: SETTINGS, CUBES, HISTORY, WIZARD, IMPORT

## Known Stubs

None.

## Threat Flags

None. This plan adds no new network endpoints, auth paths, file access patterns, or schema changes. The new entry surface only navigates within the SPA — the reshuffle commit still goes through `require_admin` on `POST /cubes/bulk` (T-0706-02, accepted).

## Self-Check: PASSED

- `b04fe74` confirmed in git log
- `frontend/src/routes/admin/Wizard.tsx` exists and contains START RESHUFFLE + START SETUP WIZARD
- `frontend/src/routes/admin/admin.css` exists and contains wizard-entry classes
- SUMMARY.md created at `.planning/phases/07-wizards-import-export/07-06-SUMMARY.md`

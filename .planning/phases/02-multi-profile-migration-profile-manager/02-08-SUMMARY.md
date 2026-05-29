---
phase: 02-multi-profile-migration-profile-manager
plan: "08"
subsystem: [ui, api]
tags: [tanstack-query, react, polling, sync, vitest]

requires:
  - phase: 02-multi-profile-migration-profile-manager
    provides: profile-manager admin UI (02-07), per-profile sync (02-05)
provides:
  - Poll-until-terminal sync status polling in the admin ProfileDrawer
  - Regression test reproducing the transient-tick bug
  - Documented atomic terminal-write contract in profile_sync.py

affects: [profile-manager-admin, sync-feedback]

tech-stack:
  added: []
  patterns:
    - "Poll-until-terminal: refetchInterval stops only on terminal statuses, not on the first non-active value"

key-files:
  created:
    - frontend/src/routes/admin/ProfileDrawer.test.tsx
  modified:
    - frontend/src/routes/admin/ProfileDrawer.tsx
    - src/gruvax/api/admin/profile_sync.py

key-decisions:
  - "refetchInterval returns false ONLY for terminal 'ok'/'failed'; 2000ms for everything else (in_progress, null, transient) so a momentary non-terminal tick can no longer halt polling before the terminal status is observed"
  - "Backend terminal write confirmed already atomic (status + item_count in one _swap_inside_tx transaction); documented the poller contract rather than changing behavior"

patterns-established:
  - "Poll-until-terminal: derive stop condition from the set of TERMINAL states, never from equality with the active state"

requirements-completed: [PROF-02, PROF-01]

duration: ~19min
completed: 2026-05-29
---

# Phase 02 / Plan 08: Sync drawer poll-until-terminal Summary

**The admin profile drawer now auto-transitions SYNCING → CONNECTED with a completion toast across transient status ticks, without a manual page refresh.**

## Performance

- **Duration:** ~19 min (executor) + post-merge gate
- **Tasks:** 2 auto + 1 human-verify checkpoint (live-approved)
- **Files modified:** 3

## Accomplishments
- Fixed the root-cause poll bug: `refetchInterval` halted on any non-`'in_progress'` value, so a transient/`null` tick between the early `in_progress` write and the terminal `ok` write could stop polling before convergence, leaving the drawer stuck.
- Changed the poll to keep firing until a terminal status (`'ok'`/`'failed'`) is observed.
- Added a vitest regression test driving the exact transient-tick sequence (in_progress → null → ok) and asserting the drawer exits 'syncing' and the completion toast fires once.
- Audited and documented the backend completion write as atomic (status + item_count in a single `_swap_inside_tx` transaction).

## Task Commits

1. **Task 1: Poll-until-terminal refetchInterval + regression test** — `a829308` (feat)
2. **Task 2: Confirm/Harden atomic terminal write** — `13edb32` (docs)
3. **Post-merge fix: tsc-clean mock param type** — `35e936f` (fix; caught by post-merge `tsc -b` gate that the plan's vitest-only verify missed)

**Merge to main:** `37b4227`

## Files Created/Modified
- `frontend/src/routes/admin/ProfileDrawer.tsx` — poll-until-terminal `refetchInterval`
- `frontend/src/routes/admin/ProfileDrawer.test.tsx` — 3 regression tests (transient tick → ok → transition + toast; failed path; poll-continuation)
- `src/gruvax/api/admin/profile_sync.py` — module docstring documenting the poller's terminal-status contract

## Verification
- `npx vitest run src/routes/admin/ProfileDrawer.test.tsx` → 3/3 pass
- `uv run pytest -k "profile_sync or sync_profile or trigger_sync"` → 11/11 pass
- `tsc -b` clean; full frontend suite 50/50
- **Live (user-approved):** connected/synced a profile on the live stack → drawer auto-transitioned SYNCING → CONNECTED + toast with no manual refresh.

## Self-Check: PASSED

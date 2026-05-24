---
status: partial
phase: 07-wizards-import-export
source: [07-VERIFICATION.md]
started: 2026-05-24T22:10:00Z
updated: 2026-05-24T22:10:00Z
---

## Current Test

[awaiting human testing — rebuild the stack with real `v_collection` data, log in at `/admin`]

## Tests

### 1. Reshuffle resume across hard reload (SC3, ADMN-10)
expected: Open `/admin/wizard`, switch to reshuffle mode, confirm ≥1 step, then HARD-RELOAD and log back in. The yellow "RESHUFFLE IN PROGRESS — N OF M STEPS DONE" banner appears above the Outlet with the correct count and "Started X ago". CONTINUE → `/admin/wizard?mode=reshuffle` and re-validates against `v_collection` (spinner visible; stale records get did-you-mean warning). DISCARD → inline two-step confirm ("Are you sure? … YES, DISCARD / KEEP DRAFT") removes the banner.
result: [pending]

### 2. Import diff render + happy path (ADMN-05, SC2)
expected: Upload a SYNTHETIC YAML changing exactly 3 cubes using catalog numbers that exist in the real dev `v_collection`. Exactly those 3 cubes highlight yellow in the AFFECTED CUBES mini-Kallax grid; non-zero deltas suffixed "(approx.)"; partial-import warning when the file omits cubes; COMMIT IMPORT disabled until zero errors; phantom rows render "Did you mean?" chips that flip to FIXED (green) on tap; after commit, ConfirmationRoute shows the change_set_id with "REVERT THIS CHANGE SET". (NOTE: the automated suite cannot prove the commit-success path — synthetic ATL-001 numbers are correctly rejected as phantoms; this UAT must use real collection catalog numbers.)
result: [pending]

### 3. Export round-trip zero diff (BAK-01, SC4)
expected: Tap EXPORT BOUNDARIES on `/admin/cubes` → `boundaries.yaml` downloads. Re-import that file at `/admin/import` → the diff grid shows ZERO cubes changing and COMMIT IMPORT is immediately enabled with zero errors (export → re-import = identity).
result: [pending]

### 4. Settings backup/restore, history badges, confirmation revert (BAK-02, D-04, D-15, SC5)
expected: `/admin/settings` → BACKUP & RESTORE: EXPORT SETTINGS downloads `settings.yaml` (confirm NO `pin_hash` anywhere in the file); IMPORT SETTINGS with that file shows "Settings applied." in green; a non-YAML file shows the rejection error. After a wizard/import commit, `/admin/history` shows WIZARD SETUP (yellow-tinted) or CSV IMPORT / YAML IMPORT (blue) badges. The post-commit confirmation names the change_set_id; REVERT THIS CHANGE SET navigates to `/admin/history?highlight=<id>` and the conflict-aware revert works.
result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps

_None recorded yet — populate from any failing test above, then run `/gsd-plan-phase 7 --gaps`._

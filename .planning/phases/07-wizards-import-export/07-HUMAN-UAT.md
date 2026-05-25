---
status: partial
phase: 07-wizards-import-export
source: [07-VERIFICATION.md]
started: 2026-05-24T22:10:00Z
updated: 2026-05-25T01:40:00Z
---

## Current Test

[Tests 2–4 PASSED via the 07-08 human-verify checkpoint (owner-approved, all flows). Test 1
(reshuffle resume-at-step) needs a 30-second re-verify: code review found CR-01 — resume
always landed on step 0 (`Math.min(completedSteps, 0)`) — now fixed in `03fb309`
(`Math.max`). Re-run: start a reshuffle, complete ≥1 step, hard-reload, CONTINUE → confirm it
resumes at the SAVED step, not step 0.]

## Tests

### 1. Reshuffle resume across hard reload (SC3, ADMN-10)
expected: Open `/admin/wizard`, switch to reshuffle mode, confirm ≥1 step, then HARD-RELOAD and log back in. The yellow "RESHUFFLE IN PROGRESS — N OF M STEPS DONE" banner appears above the Outlet with the correct count and "Started X ago". CONTINUE → `/admin/wizard?mode=reshuffle`, resuming at the SAVED step, and re-validates against `v_collection` (spinner visible; stale records get did-you-mean warning). DISCARD → inline two-step confirm ("Are you sure? … YES, DISCARD / KEEP DRAFT") removes the banner.
result: [pending — CR-01 fixed in `03fb309`; resume now uses `Math.max(completedSteps, 0)` so it lands on the saved step instead of always step 0. Needs a quick human re-verify of resume-at-step. Reshuffle ENTRY (G1) was already owner-approved in the 07-08 checkpoint.]

### 2. Import diff render + happy path (ADMN-05, SC2)
expected: Upload a SYNTHETIC YAML changing exactly 3 cubes using catalog numbers that exist in the real dev `v_collection`. Exactly those 3 cubes highlight yellow in the AFFECTED CUBES mini-Kallax grid; non-zero deltas suffixed "(approx.)"; partial-import warning when the file omits cubes; COMMIT IMPORT disabled until zero errors; phantom rows render "Did you mean?" chips that flip to FIXED (green) on tap; after commit, ConfirmationRoute shows the change_set_id with "REVERT THIS CHANGE SET".
result: pass — owner-approved in the 07-08 human-verify checkpoint (import dry-run: preview with no write until COMMIT IMPORT; change_set_id minted on commit).

### 3. Export round-trip zero diff (BAK-01, SC4)
expected: Tap EXPORT BOUNDARIES on `/admin/cubes` → `boundaries.yaml` downloads. Re-import that file at `/admin/import` → the diff grid shows ZERO cubes changing and COMMIT IMPORT is immediately enabled with zero errors (export → re-import = identity).
result: pass — owner-approved in the 07-08 human-verify checkpoint (export → re-import = zero diff).

### 4. Settings backup/restore, history badges, confirmation revert (BAK-02, D-04, D-15, SC5)
expected: `/admin/settings` → BACKUP & RESTORE: EXPORT SETTINGS downloads `settings.yaml` (confirm NO `pin_hash` anywhere in the file); IMPORT SETTINGS with that file shows "Settings applied." in green; a non-YAML file shows the rejection error. After a wizard/import commit, `/admin/history` shows WIZARD SETUP (yellow-tinted) or CSV IMPORT / YAML IMPORT (blue) badges. The post-commit confirmation names the change_set_id; REVERT THIS CHANGE SET navigates to `/admin/history?highlight=<id>` and the conflict-aware revert works.
result: pass — owner-approved in the 07-08 human-verify checkpoint (settings round-trip + bad-file rejection; history source badges; REVERT THIS CHANGE SET).

## Summary

total: 4
passed: 3
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

_None outstanding. The four original gaps were closed by plans 07-06/07/08 and verified
(07-VERIFICATION.md status=passed, 18/18). The only open item is a quick re-verify of
reshuffle resume-at-step after the CR-01 fix (`03fb309`) — see Test 1._

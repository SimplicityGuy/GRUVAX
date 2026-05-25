---
status: resolved
phase: 07-wizards-import-export
source: [07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md, 07-04-SUMMARY.md, 07-05-SUMMARY.md, 07-HUMAN-UAT.md]
started: 2026-05-24T22:40:00Z
updated: 2026-05-25T01:40:00Z
---

## Current Test

[RESOLVED — all 4 diagnosed gaps closed by gap-closure plans 07-06/07/08 and verified
(07-VERIFICATION.md status=passed, 18/18; 07-08 human-verify checkpoint owner-approved).
SC5 history badges + revert confirmed in the 07-08 UAT. One quick re-verify remains
(reshuffle resume-at-step after the CR-01 fix) — tracked in 07-HUMAN-UAT.md Test 1.]

## Tests

### 1. Cold Start / Rebuild Smoke Test
expected: `docker compose up -d --build api` boots cleanly; migrations apply through 0007; /admin loads and login works; WIZARD + IMPORT nav tabs visible.
result: pass

### 2. Reshuffle resume across hard reload (SC3, ADMN-10)
expected: In /admin/wizard reshuffle mode, confirm ≥1 step, then HARD-RELOAD and log back in. The yellow "RESHUFFLE IN PROGRESS — N OF M STEPS DONE" banner shows the correct count + "Started X ago". CONTINUE re-validates against v_collection (spinner; stale records flagged with did-you-mean). DISCARD shows the inline two-step confirm and removes the banner.
result: issue
reported: "i don't see a reshuffle mode — /admin/wizard opens in SETUP only; no control to start a reshuffle"
severity: major

### 3. Import diff render + commit, with real records (ADMN-05, SC2)
expected: Upload a CSV/YAML using catalog numbers that EXIST in your dev v_collection, changing exactly 3 cubes. Those 3 cubes light yellow in the AFFECTED CUBES grid; deltas suffixed "(approx.)"; partial-import warning when cubes are omitted; COMMIT IMPORT disabled until zero errors; phantom rows show tappable "Did you mean?" chips that flip to FIXED; commit lands on the confirmation naming the change_set_id.
result: issue
reported: "i got an error when importing this [freshly-exported] file"
severity: major

### 4. Export round-trip zero diff (BAK-01, SC4)
expected: EXPORT BOUNDARIES on /admin/cubes downloads boundaries.yaml. Re-import that exact file at /admin/import → the diff grid shows ZERO cubes changing and COMMIT IMPORT is enabled with zero errors (export → re-import = identity).
result: issue
reported: "failed, same error as in test 3 (freshly exported, unedited file rejected on re-import)"
severity: major

### 5. Settings backup/restore + history badges + revert tap (BAK-02, D-04, D-15, SC5)
expected: /admin/settings → BACKUP & RESTORE: EXPORT SETTINGS downloads settings.yaml (confirm NO pin_hash in the file); IMPORT SETTINGS with it shows "Settings applied." in green; a non-YAML file is rejected. /admin/history shows WIZARD SETUP (yellow-tint) / CSV IMPORT / YAML IMPORT (blue) badges after commits. The confirmation's "REVERT THIS CHANGE SET" navigates to /admin/history?highlight=<id> and the revert works.
result: issue
reported: "IMPORT SETTINGS of a freshly-exported settings.yaml shows 'Settings could not be applied. Check that the file is a valid GRUVAX settings export.'"
severity: major
partial_pass: "EXPORT SETTINGS downloads + PIN excluded (no pin_hash in the exported file) → BAK-02 export + D-14 verified. History badges + revert (SC5) NOT yet tested due to the import failure blocking the flow."

## Summary

total: 5
passed: 1
issues: 4
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Owner can START a reshuffle wizard from the admin UI (ADMN-10, SC3)"
  status: resolved  # closed by 07-06 — WizardEntryChoice landing on /admin/wizard (START SETUP WIZARD / START RESHUFFLE); verified 07-VERIFICATION.md G1 + 07-08 UAT flow 5
  reason: "User reported: i don't see a reshuffle mode — /admin/wizard opens in SETUP only; no control to start a reshuffle. Code confirms reshuffle mode is reachable only via ?mode=reshuffle URL param or a pre-existing reshuffleDraft; WIZARD nav links to /admin/wizard (setup); ReshuffleBanner only renders when a draft already exists → no discoverable entry point. NOTE: the reshuffle ENGINE itself works — user verified the resume flow (RESHUFFLE badge, draft persistence across hard reload, CONTINUE/DISCARD) via direct URL /admin/wizard?mode=reshuffle and marked it pass. The gap is ONLY the missing discoverable entry point, so the fix is narrow."
  severity: major
  test: 2
  root_cause: ""
  artifacts:
    - path: "frontend/src/routes/admin/AdminShell.tsx"
      issue: "WIZARD NavLink → /admin/wizard (setup only); no 'Start reshuffle' entry point in nav"
    - path: "frontend/src/routes/admin/Wizard.tsx"
      issue: "mode resolved only from reshuffleDraft presence or ?mode=reshuffle param; no in-app trigger to set it"
  missing:
    - "A discoverable UI control to start a reshuffle (e.g., a RESHUFFLE action/tab or a mode toggle on /admin/wizard) that routes to /admin/wizard?mode=reshuffle"
  debug_session: ""

- truth: "Import shows a diff preview BEFORE committing; no DB write until COMMIT IMPORT is tapped (D-11, D-09, SC2)"
  status: resolved  # closed by 07-07 (dry_run preview branch — no write) + 07-08 (Import.tsx wired to dry_run; commit only on COMMIT IMPORT; no-op short-circuit removed, T-0708-NOOP-COMMIT); verified 07-VERIFICATION.md G2 + 07-08 UAT flow 1
  reason: "Import has NO validate-only/dry-run pass. Import.tsx upload handler calls uploadImportBoundaries() → POST /api/admin/import/boundaries, which is the ATOMIC COMMIT endpoint (validate-then-write). For a CLEAN file the server commits immediately on upload (returns change_set_id) while the UI shows a 'diff preview' + enabled COMMIT button as if nothing happened; the subsequent COMMIT IMPORT re-posts with the same Idempotency-Key and is a dedup no-op. So the 'preview before atomic replace' guarantee is inverted — the preview is AFTER the write. Proven live: a clean 6-cube file POST returned {change_set_id, applied:32} and mutated boundary state on the first upload (had to be reverted)."
  severity: major
  test: 3
  root_cause: "No validate-only endpoint wired; the existing POST /api/admin/cubes/validate (Phase 3 dry-run) is NOT used by the import preview — Import.tsx reuses the commit endpoint for preview (see Import.tsx:388-396 implementation-note comment)."
  artifacts:
    - path: "frontend/src/routes/admin/Import.tsx"
      issue: "upload handler (lines ~388-412) calls uploadImportBoundaries (commit endpoint) for the 'validation pass'; clean files commit on upload; COMMIT re-post is an idempotency no-op"
    - path: "src/gruvax/api/admin/import_.py"
      issue: "no validate-only/dry-run mode on the import path; or import preview should route through cubes/validate"
  missing:
    - "Wire the import preview to POST /api/admin/cubes/validate (dry-run: per-row errors + movement-count diff, NO write), then commit via /import/boundaries ONLY on COMMIT IMPORT (D-11 flow)"
  debug_session: ""

# NOTE (not a gap): the user's test file had one genuinely invalid row — Paisley Park / 25110-1
# (25110-1 is a Warner Bros catalog; real Paisley Park is 925577-1). The backend correctly
# returned 400 phantom_boundary with did-you-mean near_misses, and the import was atomic (no
# partial write). CONFIRMED BY USER: the UI rendered it as a tidy per-row error CARD with a
# tappable did-you-mean chip (answer "a") — so the D-11 error-display path WORKS. The only
# Test-3 fix needed is the validate-only preview wiring (the major gap above).

- truth: "A freshly exported boundaries.yaml re-imports with zero diff — export → re-import = identity (BAK-01, SC4)"
  status: resolved  # closed by 07-07 — G3 identity-skip: rows equal to the current committed cut point skip phantom re-validation; verified test_export_reimport_identity + 07-08 UAT flow 2
  reason: "User exported current state unedited and re-imported → 400 phantom_boundary on cube (2,2,2). Verified in DB: gruvax.cube_boundaries (2,2,2) genuinely stores first_label='Paisley Park', first_catalog='25110-1'. That pair does NOT exist in v_collection (real Paisley Park = 925577-1; 25110-1 = Warner Bros). The EXPORT is faithful (serializes stored state); the IMPORT strictly re-validates every row against v_collection via cube_exact_match and rejects it. ASYMMETRY: write paths can persist a (label,catalog) pair that doesn't match v_collection (force-commit / wizard path), but import always re-validates — so any such committed cube makes export→re-import fail. SC4 identity is not guaranteed."
  severity: major
  test: 4
  root_cause: "Boundaries are stored + round-tripped as (first_label, first_catalog) TEXT and re-validated against v_collection on import (Pitfall 22: index-space vs catalog-string). Import re-validation is stricter than the write path that produced the state, so exported state can be un-re-importable."
  artifacts:
    - path: "src/gruvax/api/admin/import_.py"
      issue: "import re-validates every row against v_collection with no allowance for rows that already equal the current committed cut point (unchanged cubes shouldn't need phantom re-validation)"
    - path: "src/gruvax/api/admin/export.py"
      issue: "exports (label,catalog) strings that may not round-trip; consider exporting a stable identity (collection index/release id) or marking already-committed rows"
    - path: "src/gruvax/api/admin/cubes.py"
      issue: "force-commit / write path can persist (label,catalog) pairs that don't match v_collection, creating un-re-importable state"
  missing:
    - "DECISION (user-chosen): import SKIPS phantom re-validation for any row that equals the current committed cut point (unit,row,col,first_label,first_catalog,is_empty). New/changed rows still get full phantom + contiguity validation. This guarantees export→re-import = identity (SC4) with the smallest, safest change. (Rejected alternatives: stable-record-id round-trip; reject-non-matching-pairs on write.)"
  debug_session: ""

- truth: "IMPORT SETTINGS of a freshly exported settings.yaml applies the settings (BAK-02 round-trip)"
  status: resolved  # closed by 07-08 — adminClient raw-body uploads (text/csv | application/x-yaml) matching the backend raw-body reader; verified 07-VERIFICATION.md G4 + 07-08 UAT flow 3
  reason: "User exported settings.yaml (PIN correctly excluded ✓) and IMPORT SETTINGS rejected it: 'Settings could not be applied.' ROOT CAUSE (reproduced live): the frontend clients send the file as MULTIPART FormData (form.append('file', file)) but BOTH backend endpoints read the RAW request.body() and yaml.safe_load it. Multipart settings → backend yaml-parses the multipart wrapper → 422 parse_error ('mapping values are not allowed here … Content-Disposition: form-data; name=\"file\"'). Raw body (curl --data-binary) → 200, all 14 keys applied. So settings import is BROKEN through the UI. Boundaries import shares the same client(FormData)/server(raw body) mismatch — it happened to parse the user's file in Test 3 (YAML leniently reads the multipart wrapper as a mapping and the boundaries parser only reads the `cubes` key), but a multipart curl to /import/boundaries returns 422 unsupported_format — so boundaries import is fragile too."
  severity: major
  test: 5
  root_cause: "Client/server body-format contract mismatch across the import family: adminClient.uploadImportBoundaries + uploadImportSettings POST multipart FormData; import_.py import_boundaries + import_settings read raw request.body(). Settings fails (strict key-allowlist sees multipart pseudo-keys / yaml parse error); boundaries is luck-dependent."
  artifacts:
    - path: "frontend/src/api/adminClient.ts"
      issue: "uploadImportSettings (~L666) and uploadImportBoundaries (~L633) send multipart FormData; should send the raw file body with Content-Type text/csv|application/x-yaml (e.g. body: file) to match the backend"
    - path: "src/gruvax/api/admin/import_.py"
      issue: "import_boundaries (L133) + import_settings (L439) read raw request.body(); either keep raw and fix the clients, OR parse multipart (UploadFile) on the server — pick ONE contract for both endpoints + their tests"
  missing:
    - "Align the import upload contract on BOTH endpoints: clients send raw file bytes with the right Content-Type (matching the backend's raw-body reader), OR switch backends to UploadFile/multipart and update the host tests that send raw bytes. Re-verify settings round-trip (export→import) AND boundaries import through the actual UI."
  debug_session: ""

# Test-5 partial passes (not gaps): EXPORT SETTINGS works and the exported file contains NO
# pin_hash (D-14 / BAK-02 PIN exclusion verified live). History source badges (D-04) and the
# revert-this-change-set tap (D-15/SC5) were NOT reached because the settings-import failure
# (and the import contract mismatch) blocked that part of the flow — fold a quick re-check of
# badges + revert into the gap-closure verification.

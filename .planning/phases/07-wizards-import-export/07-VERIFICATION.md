---
phase: 07-wizards-import-export
verified: 2026-05-24T22:00:00Z
status: human_needed
score: 14/18 must-haves verified (4 need human UAT)
overrides_applied: 0
human_verification:
  - test: "Reshuffle resume across hard reload (SC3, ADMN-10)"
    expected: >
      After confirming ≥1 wizard reshuffle step and hard-reloading, the yellow
      'RESHUFFLE IN PROGRESS — N OF M STEPS DONE' banner appears on next admin login
      with the correct count and 'Started X ago'. CONTINUE navigates to
      /admin/wizard?mode=reshuffle and re-validates against v_collection (spinner
      visible, stale records get did-you-mean warning). DISCARD triggers the inline
      two-step confirm and removes the banner.
    why_human: >
      Zustand persist + localStorage cross-session behavior, browser reload timing,
      and the spinner/re-validate interaction are not assertable in pytest or tsc.
  - test: "Import diff render and per-row error cards (ADMN-05, SC2 happy path)"
    expected: >
      Upload a synthetic YAML changing exactly 3 cubes (made-up labels only).
      Exactly those 3 cubes highlight yellow in the AFFECTED CUBES mini-Kallax grid.
      Non-zero movement-count deltas are suffixed '(approx.)'. The partial-import
      warning shows when the file omits cubes. COMMIT IMPORT is disabled until zero
      errors. Per-row phantom error cards render 'Did you mean?' chips; tapping a
      chip flips the card to FIXED (green). After commit, ConfirmationRoute renders
      the change_set_id with 'REVERT THIS CHANGE SET'.
    why_human: >
      Visual diff grid layout, chip→FIXED transition, and the full import happy path
      require a running stack with real v_collection records. Synthetic ATL-001
      catalog numbers are correctly rejected as phantoms by the import validator — so
      the commit-success path (SC2) cannot be exercised in the automated test harness
      without real collection data.
  - test: "Export round-trip zero diff (BAK-01, SC4)"
    expected: >
      Tap EXPORT BOUNDARIES on /admin/cubes — a boundaries.yaml file downloads.
      Re-import the downloaded file at /admin/import — the AFFECTED CUBES diff grid
      shows zero cubes changing (no cubes highlighted). COMMIT IMPORT is enabled
      immediately with zero errors.
    why_human: >
      Requires a running stack with real boundary state in the DB. The automated
      Hypothesis round-trip tests cover the io layer in isolation; the end-to-end
      export→re-import→zero-diff property needs a live server.
  - test: "Settings backup/restore, history badges, and confirmation revert tap (BAK-02, D-04, D-15, SC5)"
    expected: >
      At /admin/settings → BACKUP & RESTORE: EXPORT SETTINGS downloads settings.yaml
      (no pin_hash present). IMPORT SETTINGS with the downloaded file shows 'Settings
      applied.' in green; a non-YAML file shows the rejection error. After a wizard or
      import commit, /admin/history shows WIZARD SETUP (yellow-tinted badge) or
      CSV IMPORT / YAML IMPORT (blue badge). The post-commit confirmation screen names
      the change_set_id; REVERT THIS CHANGE SET navigates to /admin/history?highlight=<id>.
    why_human: >
      Visual badge styling (CSS data-source colors), the browser download of settings.yaml
      and manual inspection that pin_hash is absent, and the navigate-on-revert behavior
      all require a running browser/stack. Automated tests cover the PIN exclusion (unit
      test_no_pin_in_export) and badge map values (code-level grep), but not the rendered
      visual or navigation flow.
---

# Phase 7: Wizards + Import/Export Verification Report

**Phase Goal:** Owner can stand up boundaries from scratch via a guided setup wizard, atomically apply a post-haul reshuffle, import boundaries from a CSV/YAML seed file (with diff preview), and export current boundaries + LED color settings — boundary maintenance is fast, atomic, and portable.

**Verified:** 2026-05-24T22:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP Success Criteria + PLAN must_haves)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC1 | Owner can run a guided setup wizard cube-by-cube; entire walk commits as ONE atomic change_set_id via POST /api/admin/cubes/bulk | ✓ VERIFIED | Wizard.tsx: adminBulkSave(updates, idempotencyKey, source) called once on COMMIT ALL CHANGES (line 287). crypto.randomUUID() key persisted in draft before call (line 108). validateBoundary called first (line 254). test_wizard_atomic_commit + test_source_label green. |
| SC2 | Owner can upload CSV/YAML; server validates per-row with near-miss suggestions, shows diff preview, commits atomically with Idempotency-Key | ? UNCERTAIN (human needed) | Backend: import_.py validates all edits before any write (Pitfall 7), returns phantom_boundary 400 with near_misses. Atomicity tests pass (test_phantom_row_rejected, test_contiguity_violation, test_atomicity all green). Frontend: Import.tsx has did-you-mean chips, diff grid, gated commit. BUT: test_csv_import/test_yaml_import/test_partial_import FAIL in CI because synthetic ATL-001 catalog numbers are phantom in the real dev v_collection. The import-commit happy path has no passing automated test. Human UAT with real v_collection records required to confirm SC2 end-to-end. |
| SC3 | Owner can run a reshuffle wizard; in-progress state persists to localStorage; resume banner appears on next login; commit is one change_set_id | ? UNCERTAIN (human needed) | adminStore.ts: reshuffleDraft persisted via zustand partialize (line 117). ReshuffleBanner returns null when draft is null, renders step count + CONTINUE/DISCARD otherwise. Wizard writes draft on each step. Draft cleared on successful commit (setReshuffleDraft(null) line 291). Cross-session localStorage persistence and banner render requires human browser test. |
| SC4 | Owner can download current boundaries as YAML; export schema matches import schema (round-trip identity); settings export/import under same convention | ? UNCERTAIN (human needed) | Backend: export.py GET /export/boundaries.yaml returns serialize_boundaries_yaml output. Hypothesis property test (test_export_roundtrip.py) verifies io-layer round-trip identity. End-to-end export→re-import→zero-diff requires a live stack with real boundary data (human UAT). |
| SC5 | Every wizard commit, CSV/YAML import, and reshuffle ends with a confirmation naming the change_set_id and a 'Revert this change set' tap | ? UNCERTAIN (human needed) | ConfirmationScreen.tsx: renders changeSetId in DM Mono, REVERT THIS CHANGE SET navigates to /admin/history?highlight=<id> (line 143). Import.tsx navigates to /admin/wizard/done?change_set_id=...&source=... on success (lines 529-544). ConfirmationRoute parses query params and renders ConfirmationScreen. Visual confirmation of rendered UX requires human. |
| T01 | boundary_history.source accepts 'wizard','reshuffle','csv','yaml' after migration 0007 | ✓ VERIFIED | 0007_wizard_source_labels.py: CHECK (source IN ('manual','bulk','revert','cut_insert','wizard','reshuffle','csv','yaml')). test_source_label green. |
| T02 | Migration 0007 round-trips upgrade→downgrade→upgrade clean | ✓ VERIFIED | SUMMARY-01: round-trip verified on clean DB before tests ran. T-07-02 accepted risk: downgrade fails if wizard/reshuffle rows exist (expected, documented). |
| T03 | cubes/bulk records caller's source (default 'bulk'); BulkWriteRequest.source threaded to write_history_row | ✓ VERIFIED | cubes.py line 127: source: str = "bulk". Line 784: source=body.source. Backward compat confirmed (existing test_change_set.py + test_cubes_bulk.py green). |
| T04 | All 8 Phase 7 Wave-0 test files exist and collect cleanly | ✓ VERIFIED | All 8 files confirmed present: test_wizard.py, test_import.py, test_export.py, test_settings_import.py, test_settings_export.py, test_reshuffle_draft.py, test_export_roundtrip.py, test_import_roundtrip.py. |
| T05 | YAML/CSV parse into one CutPointEntry list; safe_load enforced; YAML carries overrides; CSV carries none | ✓ VERIFIED | boundary_yaml.py: yaml.safe_load on line 68. CutPointEntry dataclass. boundary_csv.py: csv.DictReader line 60, overrides={} always. 26 property/unit tests pass. |
| T06 | YAML round-trip identity holds (SC4 substrate) | ✓ VERIFIED | serialize_boundaries_yaml → parse_yaml_boundaries round-trip. Hypothesis property tests (test_export_roundtrip.py) pass green per SUMMARY-02. |
| T07 | GET /export/boundaries.yaml returns full live boundary + overrides as YAML (BAK-01) | ✓ VERIFIED | export.py: reads segment_overrides, builds CutPointEntry list from cache, calls serialize_boundaries_yaml, returns application/x-yaml with Content-Disposition attachment. test_export_returns_yaml + test_overrides_in_export green. |
| T08 | GET /export/settings.yaml returns ONLY _ALLOWED_SETTINGS_KEYS, never auth.pin_hash (BAK-02, D-14) | ✓ VERIFIED | export.py line 120: SELECT WHERE key = ANY(_ALLOWED_SETTINGS_KEYS). auth.pin_hash absent from _ALLOWED_SETTINGS_KEYS. test_no_pin_in_export + test_all_allowed_keys green. |
| T09 | POST /import/boundaries validates atomically; phantom/contiguity errors leave ZERO partial state | ✓ VERIFIED | import_.py validates ALL edits before any write (lines 243-303). Single transaction wraps all writes. test_phantom_row_rejected, test_contiguity_violation, test_atomicity all green. |
| T10 | POST /import/settings rejects unknown and auth.* keys with 422, never writes on rejection | ✓ VERIFIED | import_.py lines 468-489: auth.* → 422 auth_key_rejected; unknown → 422 unknown_key. Whole-file reject (raise before write loop). test_unknown_key_rejected, test_auth_key_rejected green. |
| T11 | Wizard.tsx: two-mode engine (setup/reshuffle); RecordPickerSheet per step; ONE atomic adminBulkSave commit | ✓ VERIFIED | Wizard.tsx: RecordPickerSheet imported + rendered (line 508). adminBulkSave called once with source by mode (line 287). validateBoundary called before commit (line 254). crypto.randomUUID() Idempotency-Key (line 108). tsc + build exit 0. |
| T12 | ReshuffleBanner renders null when no draft; shows step count + CONTINUE/DISCARD when draft exists; DISCARD has inline two-step confirm | ✓ VERIFIED | ReshuffleBanner.tsx: returns null when reshuffleDraft is null (line 45). Renders completedSteps/totalSteps. YES, DISCARD + KEEP DRAFT copy present (lines 72, 78). No hardcoded hex, no innerHTML. |
| T13 | adminClient exposes downloadBoundariesYaml, downloadSettingsYaml, uploadImportBoundaries, uploadImportSettings; adminBulkSave has source param | ✓ VERIFIED | adminClient.ts: all four functions present (lines 590, 609, 633, 666). adminBulkSave source param (line 280). |
| T14 | HistoryView SOURCE_BADGE_MAP has WIZARD SETUP/RESHUFFLE/CSV IMPORT/YAML IMPORT badges (D-04) | ✓ VERIFIED | HistoryView.tsx line 157-160: wizard='WIZARD SETUP', reshuffle='RESHUFFLE', csv='CSV IMPORT', yaml='YAML IMPORT'. Uppercase fallback present. |
| T15 | Import.tsx full page: upload → per-row errors → diff → gated commit → confirmation; (approx.) suffix; partial-import warning | ✓ VERIFIED | Import.tsx: uploadImportBoundaries wired, (approx.) on delta non-zero (line 210), partial-import warning (line 233/695), aria-disabled on COMMIT (line 712), navigates to /admin/wizard/done on success (lines 529-544). |
| T16 | EXPORT BOUNDARIES button on CubesGrid (BAK-01); Settings BACKUP & RESTORE section (BAK-02) | ✓ VERIFIED | CubesGrid.tsx: downloadBoundariesYaml called on button click (line 113). Settings.tsx: BACKUP & RESTORE section (line 565), uploadImportSettings (line 208), downloadSettingsYaml (line 597). |
| T17 | No hardcoded hex in any new TSX; no innerHTML | ✓ VERIFIED | grep for #[0-9A-Fa-f]{6} in Wizard.tsx, Import.tsx, ReshuffleBanner.tsx returned no hits. innerHTML grep returned only comment-only occurrences (in JSDoc strings, not actual DOM usage). |
| T18 | export_router + import_router registered in router.py | ✓ VERIFIED | router.py lines 26-28, 44-45: import and include_router for both. Routes verified by SUMMARY-03 python -c create_app() check. |

**Score:** 14/18 truths verified; 4 require human UAT (SC2, SC3, SC4, SC5 — all involve running browser/stack behavior).

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/versions/0007_wizard_source_labels.py` | Extends source CHECK; round-trips clean | ✓ VERIFIED | wizard/reshuffle/csv/yaml in CHECK. Two-step DROP+ADD. |
| `src/gruvax/io/boundary_yaml.py` | CutPointEntry + parse_yaml_boundaries + serialize_boundaries_yaml; safe_load | ✓ VERIFIED | yaml.safe_load line 68. CutPointEntry dataclass. Round-trip property tests pass. |
| `src/gruvax/io/boundary_csv.py` | parse_csv_boundaries; DictReader; overrides={} | ✓ VERIFIED | DictReader line 60. REQUIRED_HEADERS exported. overrides={} enforced. |
| `src/gruvax/api/admin/export.py` | GET /export/boundaries.yaml + GET /export/settings.yaml; exports router | ✓ VERIFIED | Full implementation confirmed. _ALLOWED_SETTINGS_KEYS allowlist query. |
| `src/gruvax/api/admin/import_.py` | POST /import/boundaries + POST /import/settings; exports router | ✓ VERIFIED | Full implementation confirmed. validate-all-before-write. 100_000 cap. |
| `src/gruvax/api/admin/router.py` | Registers export_router + import_router | ✓ VERIFIED | include_router calls on lines 44-45. |
| `src/gruvax/api/admin/cubes.py` | BulkWriteRequest.source + source=body.source | ✓ VERIFIED | line 127: source: str = "bulk". line 784: source=body.source. |
| `frontend/src/routes/admin/Wizard.tsx` | Two-mode wizard engine; RecordPickerSheet reuse; atomic commit; ≥120 lines | ✓ VERIFIED | 500+ lines. RecordPickerSheet imported+rendered. validateBoundary+adminBulkSave wired. |
| `frontend/src/routes/admin/ReshuffleBanner.tsx` | Resume/discard banner; reshuffleDraft-driven; ≥40 lines | ✓ VERIFIED | 115 lines. Null guard, inline two-step discard, CONTINUE/DISCARD copy. |
| `frontend/src/routes/admin/ConfirmationScreen.tsx` | Post-commit confirmation; change_set_id + revert tap; ≥40 lines | ✓ VERIFIED | 188 lines. highlight= navigate present. aria-label="Copy change set ID". SOURCE_HEADINGS map. |
| `frontend/src/routes/admin/Import.tsx` | Full import page (replaces 07-04 stub); ≥120 lines | ✓ VERIFIED | Real implementation. uploadImportBoundaries wired. (approx.) + partial warning + gated commit + ConfirmationRoute nav. |
| `frontend/src/state/adminStore.ts` | reshuffleDraft slice; persisted to localStorage | ✓ VERIFIED | reshuffleDraft field, setReshuffleDraft, partialize includes reshuffleDraft. Survives setAdminLoggedOut. |
| `frontend/src/api/adminClient.ts` | source param on adminBulkSave; 4 export/import functions | ✓ VERIFIED | All four functions present. source param default 'bulk'. |
| `frontend/src/routes/admin/HistoryView.tsx` | SOURCE_BADGE_MAP with WIZARD/RESHUFFLE/CSV/YAML | ✓ VERIFIED | SOURCE_BADGE_MAP object with all four new badges confirmed at lines 157-160. |
| `frontend/src/routes/admin/Settings.tsx` | BACKUP & RESTORE section | ✓ VERIFIED | BACKUP & RESTORE section, EXPORT SETTINGS, IMPORT SETTINGS, uploadImportSettings wired. |
| `frontend/src/routes/admin/CubesGrid.tsx` | EXPORT BOUNDARIES button | ✓ VERIFIED | downloadBoundariesYaml called on button click. |
| All 8 Wave-0 test files | Exist and collect cleanly | ✓ VERIFIED | All 8 files confirmed present on disk. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| cubes.py:bulk_write_cubes | gruvax.db.queries.write_history_row | source=body.source | ✓ WIRED | Line 784 confirmed. |
| boundary_yaml.py:parse_yaml_boundaries | yaml.safe_load | security guard | ✓ WIRED | Line 68 confirmed. |
| boundary_csv.py:parse_csv_boundaries | csv.DictReader | flat CSV parse | ✓ WIRED | Line 60 confirmed. |
| export.py:export_settings | _ALLOWED_SETTINGS_KEYS | allowlist SELECT | ✓ WIRED | Lines 115, 120 confirmed. |
| import_.py:import_boundaries | validate_contiguity + cube_exact_match + find_boundary_near_misses | reused, not duplicated | ✓ WIRED | Lines 118-127 confirmed. |
| import_.py → segment_overrides upsert | gruvax.segment_overrides | same txn as boundary writes (Pitfall 4) | ✓ WIRED | Lines 345-355 confirmed. |
| router.py | export_router + import_router | include_router | ✓ WIRED | Lines 44-45 confirmed. |
| Wizard.tsx | /api/admin/cubes/validate then /api/admin/cubes/bulk | adminBulkSave with source | ✓ WIRED | validateBoundary line 254, adminBulkSave line 287. |
| adminStore.ts | localStorage (zustand persist) | partialize includes reshuffleDraft | ✓ WIRED | Line 117 confirmed. |
| App.tsx | Wizard route + Import route + ConfirmationRoute | Route path=wizard/import/wizard/done | ✓ WIRED | Lines 53-55 confirmed. |
| AdminShell.tsx | ReshuffleBanner | mounted above Outlet | ✓ WIRED | Line 283 confirmed. |
| Import.tsx | uploadImportBoundaries + ConfirmationRoute | upload → navigate /admin/wizard/done | ✓ WIRED | Lines 397, 529-544 confirmed. |
| CubesGrid.tsx | downloadBoundariesYaml | EXPORT BOUNDARIES button onClick | ✓ WIRED | Line 113 confirmed. |
| Settings.tsx | downloadSettingsYaml + uploadImportSettings | BACKUP & RESTORE | ✓ WIRED | Lines 208, 597 confirmed. |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| export.py:export_boundaries | entries (CutPointEntry list) | cache.get_boundaries() + segment_overrides SELECT | DB query present | ✓ FLOWING |
| export.py:export_settings | rows | SELECT key,value FROM gruvax.settings WHERE key = ANY(_ALLOWED_SETTINGS_KEYS) | DB query present | ✓ FLOWING |
| import_.py:import_boundaries | all_edits | file upload + cube_boundaries SELECT + phantom/contiguity validation | Real DB write inside transaction | ✓ FLOWING |
| Wizard.tsx:cuts state | steps from adminGetCubes + per-step RecordPickerSheet commits | adminGetCubes fetches from API | Fetched from live API | ✓ FLOWING |
| ReshuffleBanner.tsx:reshuffleDraft | reshuffleDraft from adminStore | zustand persist from localStorage | Populated by Wizard on step confirm | ✓ FLOWING |
| Import.tsx:errors/diff | uploadImportBoundaries response | POST /api/admin/import/boundaries returns phantom errors + diff | Real API response | ✓ FLOWING |
| HistoryView.tsx:SOURCE_BADGE_MAP | item.source from getHistory() | GET /api/admin/history returns boundary_history rows | Real DB rows | ✓ FLOWING |

---

### Behavioral Spot-Checks

Step 7b skipped — no server running. Backend compile-time verification was confirmed by orchestrator (`create_app()` exits 0, 32 backend tests pass). Frontend confirmed by `npx tsc --noEmit` exit 0 and `npm run build` exit 0 per SUMMARY-04/05 and orchestrator pre-check.

---

### Probe Execution

No probe-*.sh files declared or found for this phase. Orchestrator pre-checks confirm build exit 0 and 32 targeted backend tests pass.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADMN-04 | 07-01, 07-04 | Admin can run a guided setup wizard cube-by-cube | ? NEEDS HUMAN | Wizard.tsx code verified; cross-session/visual behavior unconfirmed |
| ADMN-05 | 07-01, 07-02, 07-03, 07-05 | Admin can upload CSV/YAML seed file with diff preview and atomic replace | ? NEEDS HUMAN | Backend atomicity proven; import happy path not auto-tested with real v_collection |
| ADMN-10 | 07-01, 07-04 | Reshuffle wizard persists draft; resume banner; one change_set_id | ? NEEDS HUMAN | Code complete; localStorage cross-session behavior unconfirmed |
| BAK-01 | 07-02, 07-03, 07-05 | Admin can export boundaries to YAML matching import schema | ? NEEDS HUMAN | Export endpoint + round-trip io layer verified; end-to-end on live stack unconfirmed |
| BAK-02 | 07-03, 07-05 | Admin can export/import LED color and brightness settings | ? NEEDS HUMAN | Settings export/import endpoints + PIN exclusion verified; visual confirmation pending |

All 5 phase requirements (ADMN-04, ADMN-05, ADMN-10, BAK-01, BAK-02) are mapped and their code implementations are present and wired. None can be marked fully SATISFIED without the human UAT run.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| frontend/src/routes/admin/App.tsx (comment) | 36 | "stub — 07-05 replaces with real page" | ℹ Info | Comment is stale — 07-05 replaced the stub. No code impact. |
| frontend/src/routes/admin/Wizard.tsx (architecture note) | Per SUMMARY-04 | RecordPickerSheet calls setCutPoint per step (incremental DB writes), then final adminBulkSave re-writes as one change-set | ℹ Info | Intentional design decision recorded in SUMMARY-04. history rows from intermediate steps use source='cut_insert'; the wizard's adminBulkSave creates the canonical change_set_id with source='wizard'. No defect — but the wizard produces more history rows than one expects. |
| 07-05-SUMMARY.md | Known limitation | test_csv_import, test_yaml_import, test_partial_import FAIL (400 not 200 — synthetic ATL-001 catalog numbers rejected as phantoms by the real dev v_collection) | ⚠ Warning | Import commit happy path (SC2) has no passing automated test. Endpoint logic is correct — the synthetic fixtures do not match the dev v_collection. This is the test-harness limitation acknowledged in the verification_context and SUMMARY-03/05. |

No TBD, FIXME, or XXX debt markers found in any phase-modified file.

---

### Human Verification Required

#### 1. Reshuffle Resume Across Hard Reload (ADMN-10, SC3)

**Test:** Open /admin/wizard, switch to reshuffle mode, confirm ≥1 step, then hard-reload the page (Shift+F5 or Ctrl+Shift+R) and log back in with the dev PIN.
**Expected:** The yellow "RESHUFFLE IN PROGRESS — N OF M STEPS DONE" banner appears with the correct completed-step count and "Started X ago". Tap CONTINUE → the wizard re-validates (spinner visible: "Checking for collection changes…"); any stale record shows a warning + did-you-mean chip. Tap DISCARD → the inline "Are you sure?" two-step appears; YES, DISCARD removes the banner. No time-based auto-expiry — banner shows regardless of draft age.
**Why human:** Zustand localStorage persistence across browser reload, the banner's step-count accuracy, and the re-validate spinner/stale-record flow are not assertable via pytest or tsc.

#### 2. Import Per-Row Error Cards and Diff Preview (ADMN-05, SC2)

**Test:** Upload a synthetic YAML file that changes exactly 3 cubes using real label+catalog numbers from v_collection. Upload a second synthetic YAML that omits some cubes to trigger the partial-import warning.
**Expected:** Exactly the 3 changed cubes highlight yellow in the AFFECTED CUBES mini-Kallax diff. Non-zero movement-count deltas are labelled "(approx.)". The partial-import warning shows "This file defines N cubes. The remaining M cubes will be set to empty after import." COMMIT IMPORT is visible-but-disabled until zero validation errors. After commit, the ConfirmationRoute renders with the change_set_id and REVERT THIS CHANGE SET navigates to /admin/history?highlight=<id>.
**Why human:** The import happy path (SC2) requires real v_collection records because synthetic ATL-001 catalog numbers are correctly rejected as phantoms. The diff grid visual and chip→FIXED transition require a live browser.

#### 3. Export Round-Trip Zero Diff (BAK-01, SC4)

**Test:** At /admin/cubes, tap EXPORT BOUNDARIES. Re-import the downloaded boundaries.yaml at /admin/import.
**Expected:** The AFFECTED CUBES diff grid shows zero cubes changing (no yellow highlighting). COMMIT IMPORT is enabled immediately.
**Why human:** Requires a live server with real boundary state in the DB. The io-layer Hypothesis round-trip property is verified in isolation but does not substitute for the end-to-end server→download→re-import flow.

#### 4. Settings Backup/Restore, History Badges, and Confirmation Revert Tap (BAK-02, D-04, D-15, SC5)

**Test:** (a) At /admin/settings → BACKUP & RESTORE: tap EXPORT SETTINGS, open the downloaded settings.yaml and confirm no "pin_hash" or "auth." key is present. Tap IMPORT SETTINGS with the same file → confirm "Settings applied." in green. Try importing a non-YAML file → confirm the rejection error. (b) After a wizard commit, open /admin/history → confirm "WIZARD SETUP" badge renders yellow-tinted. After a CSV/YAML import commit, confirm "CSV IMPORT" or "YAML IMPORT" badge renders blue. (c) On the post-commit confirmation screen, confirm the change_set_id is displayed and REVERT THIS CHANGE SET navigates to /admin/history?highlight=<id>.
**Why human:** Visual badge styling (CSS data-source attribute colors), browser file download inspection for PIN absence, and the navigate-on-revert behavior require a running browser with rendered CSS.

---

### Gaps Summary

No blocker gaps. The code implementation for all five requirements (ADMN-04, ADMN-05, ADMN-10, BAK-01, BAK-02) is present, wired, and compiles/builds clean. The test suite confirms backend atomicity, PIN exclusion, source labelling, and io-layer round-trip correctness.

The four UNCERTAIN truths (SC2, SC3, SC4, SC5) are gated on running-stack/browser behavior that cannot be asserted programmatically. This is the expected state described in the verification_context: automated checks pass; the 6 human UAT items (consolidated to 4 above) are pending.

One honest limitation to note: the test_csv_import / test_yaml_import / test_partial_import integration tests FAIL with 400 (phantom rejection of synthetic ATL-001 catalog numbers in the real dev v_collection). This is not a bug — the import validate path is working correctly. It means SC2 import commit success has no passing automated integration test and depends entirely on the human UAT with real records.

---

_Verified: 2026-05-24T22:00:00Z_
_Verifier: Claude (gsd-verifier)_

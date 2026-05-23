---
status: complete
phase: 05-segment-aware-position-precision
source: [05-HUMAN-UAT.md, 05-VERIFICATION.md]
started: 2026-05-23T18:50:00Z
updated: 2026-05-23T18:59:54Z
---

## Current Test

[testing complete]

## Tests

### 1. Segment drag — redistribute, 5% floor, live %
expected: Dragging a yellow handle redistributes the two adjacent segments (others fixed), sum stays constant, neither drops below 5%, legend % update live and total 100%, dragged segments flip AUTO→OVERRIDE chip.
result: pass

### 2. Override drift chip + resync
expected: An override drifting >3pp from auto shows a review/caution chip with a one-tap "reset to M%" that re-syncs (not removes) the override.
result: pass

### 3. Insert-cut: autocomplete + NEW + phantom USE-ANYWAY
expected: '＋ insert cut' opens RecordPickerSheet; label + catalog autocomplete populate; phantom catalog → near-miss block + USE ANYWAY (force); new bin appears without manual refresh and settles yellow→normal.
result: pass
note: Confirmed live this session (label/catalog dropdowns populate after the missing endpoints were wired; phantom "BLP 9999" → near-miss + USE ANYWAY; insert auto-refreshes + settles; backend cascade preserves all bins).

### 4. Straddle: continue caption + edge fade
expected: A label spanning a cut (Blue Note across bins 1→2) shows a right-edge fade mask + "↪ BLUE NOTE continues in BIN 2" caption.
result: pass

### 5. Edit → commit → revert
expected: Edit → PREVIEW CHANGES (diff) → COMMIT → REVERT via History restores prior state.
result: pass
note: REVERT correctly restores prior widths and the change-set is listed in History. Direct-save (no PREVIEW CHANGES diff step) accepted by owner as-is. Caveat — the DiffPreviewSheet at /admin/preview is currently orphaned (nothing in the rebuilt editor routes to it); folded into the gap below.

### 6. UI contiguity hard-block (SEG-05)
expected: A cut that would scatter a label across non-adjacent bins hard-blocks the commit with a plain-language contiguity error (server validator already unit-verified).
result: pass
note: RE-VERIFIED 2026-05-23 after gap-closure 05-06 + a clean DB drop/re-seed + container rebuild (the running image predated 05-06 and had to be rebuilt). Live end-to-end on the rebuilt stack via Playwright: in EDIT SHELF A, editing bin 4 (KC) → "Blue Note / BLP 4001" is hard-blocked — the EDIT CUT POINT sheet stays open and renders an alert "This cut would split blue note across non-adjacent bins. Reposition the cut or remove the existing boundary." API returns 400 type=contiguity_error and the bin remains KC (no write). Screenshot evidence: seg05-contiguity-block.png.
followup: COSMETIC (WR-04, non-blocking) — the message interpolates the casefolded label ("blue note" instead of "Blue Note"), which reads as a bug and violates the CLAUDE.md plain-language/voice rule. Fix: format with the original-cased label. Tracked in 05-REVIEW.md.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
note: All 6 UAT items pass. One cosmetic follow-up (WR-04 casefolded contiguity message) is advisory, not a UAT failure.

## Gaps

```yaml
- truth: "A cut that would scatter a label across non-adjacent bins is hard-blocked in the UI with a plain-language contiguity error (SEG-05)."
  status: resolved
  resolution: "Closed by gap-closure plan 05-06 (commits 0f88d7b..HEAD), direction A. validate_contiguity is now wired into the LIVE write paths put_bin_cut (PUT /cut) and insert_cut (POST /insert-cut) via the new build_proposed_cuts() helper, returning 400 {type:'contiguity_error'} BEFORE any DB transaction. RecordPickerSheet surfaces the server message via BulkSaveError and keeps the sheet open. The orphaned /admin/preview route + DiffPreviewSheet/RollbackToast were removed. Regression test test_put_cut_scatter_rejected_contiguity_error asserts 400 + no DB write and PASSES; 05-VERIFICATION.md re-verification (8/8) confirms the server+wiring fix programmatically. REMAINING: one human visual confirmation of the on-screen rendering in the running SPA (verifier status human_needed) — see 05-VERIFICATION.md human_verification."
  reason: "The rebuilt ShelfBinList/BinWidthEditor commit cut/insert/override edits DIRECTLY (RecordPickerSheet→setCutPoint/insertCut, BinWidthEditor 'Save overrides'→setOverrides) and never route through the validate→DiffPreviewSheet→commit gate. validate_contiguity (SEG-05) is wired ONLY into POST /cubes/validate + the bulk path (cubes.py:468), which feed the now-orphaned DiffPreviewSheet (/admin/preview — no live route navigates to it). put_bin_cut and insert_cut do NOT call validate_contiguity. Net: SEG-05 is not enforced where edits actually happen, and the movement-count / empty-overstuffed warnings + commit-gate (D-06/D-07) are also bypassed."
  severity: major
  test: 6
  artifacts:
    - src/gruvax/api/admin/segments.py (put_bin_cut, insert_cut — add contiguity enforcement)
    - src/gruvax/api/admin/cubes.py:468 (validate_contiguity — current sole caller)
    - src/gruvax/api/admin/validation.py (validate_contiguity)
    - frontend/src/routes/admin/RecordPickerSheet.tsx (surface contiguity 400 in the sheet)
    - frontend/src/routes/admin/DiffPreviewSheet.tsx (orphaned — wire in or remove)
    - frontend/src/App.tsx (/admin/preview route — orphaned)
  missing:
    - Server-side contiguity enforcement on the direct cut/insert write paths (or route the editor through the validate→preview→commit gate)
    - A reachable UI surface for the contiguity hard-block (the .contiguity-error-banner style is unused by any live .tsx)
```

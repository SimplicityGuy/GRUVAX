---
status: partial
phase: 05-segment-aware-position-precision
source: [05-VERIFICATION.md]
started: 2026-05-23T04:40:00Z
updated: 2026-05-23T04:40:00Z
---

## Current Test

[awaiting human testing of the remaining interactive items]

## Tests

Verifier returned `human_needed`: 8/8 must-haves verified in code, with 6 interactive
(visual/tactile) checkpoint items from 05-05-PLAN Task 3. Several were confirmed this
session via the running stack (Playwright + API); the rest remain for owner testing.

### 1. Segment drag — redistribute, 5% floor, live %
expected: Dragging a yellow handle in BinWidthEditor (e.g. /admin/cubes/1/0/1) redistributes the two adjacent segments, sum stays constant, neither drops below 5%, legend percentages update live, dragged segments show the OVERRIDE accent + "OVERRIDE N% · auto was M%" chip.
result: partial — editor RENDER confirmed (3-label bin Blue Note 48% / Capitol 5% / Columbia 47% = 100%, AUTO chips with row counts, 5% floor display, drag handles, live legend, "widths total 100%"). Tactile drag redistribution during pointer-drag not driven automatically — owner to confirm feel + live update.

### 2. Drift chip resync (override drifts >3pp from auto)
expected: Chip switches to "OVERRIDE N% · auto now M% · review" with caution icon and a one-tap "reset to M%" that RESYNCS the override (does not remove it).
result: pending

### 3. Insert-cut: autocomplete + NEW + phantom USE-ANYWAY
expected: '＋ insert cut' opens RecordPickerSheet; label + catalog autocomplete populate; a phantom catalog triggers the near-miss block with USE ANYWAY (force); on commit the new bin appears WITHOUT a manual refresh and settles yellow → normal; renumbering is reflected.
result: PASSED (this session) — label dropdown populates (Apple…Saturn), catalog dropdown populates after label select, phantom "BLP 9999" surfaces "No match in collection… USE ANYWAY", a valid insert (BLP 4012 after bin 1) auto-refreshes the list and the new interactive BinCard settles in. Backend cascade verified to preserve every existing bin (Columbia survived). Endpoints `/api/admin/labels[/{label}/catalogs]` were missing and have been wired + tested.

### 4. Straddle fade caption (label continues into next bin)
expected: A segment whose label continues into the next bin shows the right-edge fade mask + "↪ LABEL continues in BIN n+1" caption.
result: pending — the bin inspected this session did not straddle; owner to confirm on a straddling bin.

### 5. Diff-preview → COMMIT → REVERT round-trip
expected: PREVIEW CHANGES shows cut-point/insert/override (and orphaned-override) rows; COMMIT applies; REVERT via History restores the prior state end-to-end.
result: pending

### 6. UI contiguity hard-block
expected: A cut that would scatter a label across non-adjacent bins hard-blocks PREVIEW CHANGES with the plain-language contiguity error (server validator already verified programmatically).
result: pending

## Summary

total: 6
passed: 1
issues: 0
pending: 4
partial: 1
skipped: 0
blocked: 0

## Gaps

(none blocking — the one confirmed defect during this checkpoint, the missing
label/catalog autocomplete endpoints, was fixed and verified; see commit
"fix(05-05): wire the admin label/catalog autocomplete endpoints")

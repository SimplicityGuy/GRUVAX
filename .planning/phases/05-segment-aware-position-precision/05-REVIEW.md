---
phase: 05-segment-aware-position-precision
reviewed: 2026-05-23T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - src/gruvax/api/admin/segments.py
  - src/gruvax/api/admin/validation.py
  - tests/integration/test_segment_api.py
  - frontend/src/routes/admin/RecordPickerSheet.tsx
  - frontend/src/App.tsx
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 5: Code Review Report (gap-closure plan 05-06)

**Reviewed:** 2026-05-23
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

> Scope: gap-closure plan 05-06 only (commits `0f88d7b..3877e88`). Earlier
> 05-01..05-05 work was reviewed in a prior pass (this file previously held that
> review, dated 05-22, file set: ShelfBinList/adminClient/BinWidthEditor/
> admin.css/segments/test_segment_api). This pass supersedes it for the 05-06
> change set.

## Summary

Plan 05-06 wires SEG-05 label-contiguity enforcement onto the two live admin
write paths (`PUT /cut`, `POST /insert-cut`) via a new `build_proposed_cuts`
helper in `validation.py`, surfaces the resulting 400 `contiguity_error` in
`RecordPickerSheet.tsx`, and removes the orphaned `/admin/preview` route from
`App.tsx`.

The core wiring is correct on the points the scope note flagged:

- **Ordering is right.** On both write paths the contiguity check runs strictly
  BEFORE the `async with pool.connection() ... conn.transaction()` block, so a
  rejected cut never produces a partial DB write. The integration test
  `test_put_cut_scatter_rejected_contiguity_error` asserts post-rejection state
  and confirms `(1,0,3)` is unchanged.
- **SQL safety holds.** No new SQL on the rejection path; existing
  DELETE/UPSERT/SELECT statements use `%s` placeholders with parameter tuples,
  zero f-string interpolation.
- **No injection in the frontend change.** The `BulkSaveError` branch routes the
  server's plain-language message through `setSaveError(...)`, rendered as JSX
  `{saveError}` (textContent). The sheet correctly stays open on error (no
  `onCommit`/`onCancel` call in the error branch).
- **`build_proposed_cuts` produces the six-key dict** (`unit_id, row, col,
  first_label, first_catalog, is_empty`) that `validate_contiguity` consumes;
  both `replace` and `cascade` modes overwrite matching entries correctly.

No BLOCKER-tier defects were found in the reviewed change. The findings below are
correctness/robustness gaps (WARNING) and quality issues (INFO). The most
material is WR-01: `validate_contiguity` only inspects bin-START labels and its
documented SegmentCache cross-check (step 5) is never implemented, so a class of
real scatters slips through — the new wiring inherits that blind spot.

## Warnings

### WR-01: `validate_contiguity` ignores its `segment_cache` argument — documented step-5 cross-check is unimplemented; scatter-by-continuation is not detected

**File:** `src/gruvax/api/admin/validation.py:173-259`

**Issue:** The docstring (lines 198-201, "Step 5") promises:

> "Also cross-check against SegmentCache: if a label appears in the current
> SegmentCache in bins outside the proposed update set, and the proposed update
> would create a gap in that label's span, return an error."

The implementation never reads `segment_cache`. The identifier appears only in
the signature and docstring, never in executable code. The algorithm builds
`label_start_positions` solely from each bin's `first_label` (the bin-START
label).

Consequence: a label that physically *continues* into a later bin without
*starting* it is invisible to the check. Concrete gap — suppose Blue Note's
records overflow from bin 0 into bin 1 (Blue Note STARTS only at index 0 but
spans index 1, whose `first_label` is ECM). If an edit re-cuts a later bin so
Blue Note resumes at a non-adjacent position, the physical scatter exists but the
start-only check sees Blue Note starting at exactly one position and returns
`None` (valid). The estimator's `derive()` assigns records to bins by global
ordering (segment_cache.py:229-238), so the true span IS knowable — it is simply
never consulted. This is the gap step 5 was meant to close, and the new
write-path enforcement is only as strong as `validate_contiguity`.

**Fix:** Either implement the cross-check or correct the contract. To implement,
after the start-position loop, determine which labels actually OCCUPY each
proposed interval (via SegmentCache / re-derive) and apply the same gap test to
*occupancy* rather than *start* positions:

```python
# Pseudocode for the missing step 5:
# For each proposed cut interval [cut_i, cut_{i+1}), determine the set of labels
# whose records fall in that interval (reuse the global-ordering assignment in
# SegmentCache.derive). Build label -> occupied_bin_indices, then run the same
# contiguity gap test on occupancy rather than on first_label start positions.
```

If full re-derivation is out of scope for this phase, at minimum delete the
step-5 paragraph from the docstring and rename the parameter to `_segment_cache`
so the unimplemented promise does not mislead maintainers and the unused argument
threaded through both new call sites is honestly marked.

### WR-02: `build_proposed_cuts` scopes contiguity to a single unit, narrowing the invariant the original bulk path enforced

**File:** `src/gruvax/api/admin/validation.py:66-85`; callers `segments.py:230, 622`

**Issue:** `build_proposed_cuts` filters the proposed list to only the target
unit (`if target_unit_id is None or b.unit_id == target_unit_id`, line 84). The
original bulk caller (`cubes.py:457-468`) passed *all* proposed updates to
`validate_contiguity` without unit filtering. The docstring (lines 43-47)
justifies single-unit scope ("bins in different units are never adjacent"), which
is a defensible design position — but it is a behavioral *narrowing* relative to
the pre-existing bulk path, and the two now feed `validate_contiguity` differently
shaped inputs.

Risk: if collection organization spans a label across the boundary between the
last bin of unit N and the first bin of unit N+1 (alphabetical continuity across
shelves — plausible for a 3,000-record deterministic layout), the per-unit scope
cannot detect a scatter that crosses the unit boundary. The "never adjacent"
assumption is asserted, not enforced anywhere in the reviewed code.

**Fix:** Confirm with the data model that cross-unit label spans are impossible by
design. If possible, drop the unit filter or treat (last bin of unit N, first bin
of unit N+1) as adjacent. If genuinely impossible, add a unit test pinning the
invariant so a future reorg cannot silently break enforcement.

### WR-03: Contiguity decision trusts the in-app `BoundaryCache` to be fresh; the new test has to force a reload to make the assertion deterministic

**File:** `src/gruvax/api/admin/segments.py:230-242` (PUT) and `617-628` (insert)

**Issue:** The contiguity check uses the live in-app `cache` (BoundaryCache) for
`build_proposed_cuts` and the live `segment_cache` for `validate_contiguity`. If a
prior request mutated the DB but the in-app `BoundaryCache` was not reloaded,
`build_proposed_cuts` builds the proposed set from a stale boundary view, so the
contiguity decision is made against possibly-stale data — it could reject a valid
cut or accept a scattering one.

The integration test masks this: lines 564-582 issue a no-op cache-sync PUT
*before* the real assertion specifically to force `cache.invalidate() +
cache.load()`, with a comment acknowledging the cache "may be stale if a prior
mutating test ... restored the DB without triggering a cache reload." That
test-side workaround is direct evidence the production validation path is
sensitive to cache freshness, and there is no guarantee the cache is fresh when a
real admin PUT arrives (e.g., during an SSE-driven reload race).

**Fix:** Document the freshness contract in `put_bin_cut`/`insert_cut` (promote
the test comment at test lines 564-573 into a code comment), and ensure the
`boundary_changed` SSE handler reloads the cache before serving the next admin
write — or read boundaries for the validation step from a guaranteed-fresh source.

### WR-04: `validate_contiguity` emits the casefolded label in the user-facing error message

**File:** `src/gruvax/api/admin/validation.py:246-257`

**Issue:** The error is formatted with `lk` (the casefolded key), not the
original-case label:

```python
for lk, positions in label_start_positions.items():
    ...
    return _CONTIGUITY_MSG_TEMPLATE.format(label=lk)
```

For label "Blue Note" the owner sees "This cut would split blue note across
non-adjacent bins." This breaks the CLAUDE.md design-language voice (labels are
proper nouns from the collection) and reads as a bug to the user. The integration
test only asserts the message contains "split"/"non-adjacent" (test line 607), so
the mangled casing is uncaught.

**Fix:** Track the original-case label alongside the casefold key —
`label_display: dict[str, str]` mapping casefold → first-seen original-case label
— and format with `label=label_display[lk]`.

## Info

### IN-01: Inconsistent key-coercion between `replace` and `cascade` branches in `build_proposed_cuts`

**File:** `src/gruvax/api/admin/validation.py:89-107`

**Issue:** The `replace` branch compares coordinates directly
(`entry["unit_id"] == r_uid`, line 90); the `cascade` branch wraps them in
`int(str(entry[...]))` (line 102). Both work because `BoundaryRow` fields are
already `int`, but the divergent styles invite confusion, and the `int(str(x))`
double-conversion is defensive with no demonstrated need (values originate from
typed `BoundaryRow` fields three lines above).

**Fix:** Use direct integer comparison in both branches.

### IN-02: Duplicated inline `SELECT ... FROM gruvax.segment_overrides` re-read across two handlers

**File:** `src/gruvax/api/admin/segments.py:417-426` and `657-666`

**Issue:** The post-commit override re-read block (open `conn2`, run the overrides
SELECT, build `new_overrides` with `int()/float()` coercion) is duplicated
verbatim between `set_bin_overrides` and `insert_cut`. Pre-existing (not
introduced by 05-06) but adjacent to the change; drift between copies would cause
divergent re-derive behavior.

**Fix:** Extract `async def _load_all_overrides(pool) -> dict[...]` and call from
both. Out of strict 05-06 scope; record for cleanup.

### IN-03: `RecordPickerSheet` discards `BulkSaveError.errorType`, so contiguity and phantom errors render identically

**File:** `frontend/src/routes/admin/RecordPickerSheet.tsx:250-252`

**Issue:** The error branch surfaces only `err.serverMessage ?? err.message` and
discards `err.errorType` (`'contiguity_error'` vs `'phantom_boundary'`).
Functionally fine for v1 (the server message is self-describing), but both error
types land in the same generic `.sheet-error` block with no type-specific
affordance. The comment at lines 247-249 acknowledges the shared path is
intentional.

**Fix:** Optional — branch on `err.errorType` later if contiguity-specific UI is
desired. No action required this phase; noted so the discarded discriminant is a
conscious choice.

---

## Narrative Findings (AI reviewer)

No `<structural_findings>` block was provided; all findings above are narrative
findings from direct code review.

Verified-clean items (explicitly checked, no defect):

- **Contiguity check is pre-transaction on both paths** — `put_bin_cut`
  (segments.py:221-242, before the transaction at line 250) and `insert_cut`
  (segments.py:617-628, before the transaction at line 633). No partial write
  possible on rejection.
- **SQL placeholders** — DELETE (382), UPSERT (393), overrides SELECT (423, 663)
  all use `%s` with parameter tuples. No f-string interpolation in any SQL.
- **`build_proposed_cuts` dict shape** matches `validate_contiguity` consumption
  exactly (validator reads `is_empty`, `first_label`, `unit_id`, `row`, `col`).
- **Empty-cube handling** — cascade entries with `is_empty=True` are filtered out
  by `validate_contiguity`'s `if not u.get("is_empty")` (validation.py:215); the
  `replace` path forces `is_empty=False` (validation.py:93), correct since a
  replaced cut always has a record.
- **Frontend output safety** — server message rendered via JSX `{saveError}`
  (textContent), no raw-HTML injection sink used. Honors the file-header hard
  constraint T-05-05-01.
- **Sheet stays open on error** — error branch (RecordPickerSheet.tsx:250-256)
  calls neither `onCommit` nor `onCancel`.
- **`/admin/preview` route removal** (App.tsx) — import and `<Route>` both
  removed; deleted `DiffPreviewSheet.tsx`/`.test.tsx`/`RollbackToast.tsx` confirm
  the orphaned subtree was excised. No dangling `DiffPreviewSheet` references
  remain.
- **`adminClient` 400 handling** — `setCutPoint` (456-463) and `insertCut`
  (519-526) both throw `BulkSaveError` carrying `type` and `message` on 400, so
  the `instanceof BulkSaveError` branch in the sheet correctly intercepts
  contiguity errors.

---

_Reviewed: 2026-05-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

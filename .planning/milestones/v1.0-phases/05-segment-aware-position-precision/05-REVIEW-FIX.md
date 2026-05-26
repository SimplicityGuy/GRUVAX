---
phase: 05-segment-aware-position-precision
fixed_at: 2026-05-23T21:26:15Z
review_path: .planning/phases/05-segment-aware-position-precision/05-REVIEW.md
iteration: 1
findings_in_scope: 4
fixed: 3
skipped: 1
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-05-23T21:26:15Z
**Source review:** .planning/phases/05-segment-aware-position-precision/05-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (critical + warning): 4 (WR-01, WR-02, WR-03, WR-04)
- Fixed: 3 (WR-01 docs-only, WR-03 comment-only, WR-04 behavior fix + test)
- Skipped: 1 (WR-02 — deliberately deferred per fix guidance)
- Out of scope (info, fix_scope=critical_warning): 3 (IN-01, IN-02, IN-03)

All fixes preserved the already-verified contiguity algorithm. Phase 05 was
fully verified (05-VERIFICATION.md status=passed) and security-cleared
(05-SECURITY.md SECURED, 24/24) before this pass, so only the safe, in-scope
fixes were applied; the deferred architectural items were documented, not
implemented.

**Backend gates after all fixes (re-run, all green):**
- `uv run mypy --strict src/gruvax/` → Success: no issues found in 43 source files
- `uv run ruff check src/ tests/` → All checks passed
- `uv run ruff format --check src/ tests/` → 82 files already formatted
- `uv run pytest tests/integration/test_segment_api.py tests/unit/test_segment_cache.py` → 21 passed, 1 skipped (the skip is the unrelated SEG-08 401 case)

## Fixed Issues

### WR-04: `validate_contiguity` emits the casefolded label in the user-facing error message

**Files modified:** `src/gruvax/api/admin/validation.py`, `tests/integration/test_segment_api.py`
**Commit:** fee729a
**Applied fix:** Added a `label_display: dict[str, str]` mapping (casefold key →
first-seen original-case label), built in the same loop that populates
`label_start_positions`. The contiguity error is now formatted with
`label=label_display[lk]` instead of the casefolded `lk`, so a label like
"Blue Note" renders correctly rather than "blue note". Strengthened the
regression test `test_put_cut_scatter_rejected_contiguity_error` to assert the
message contains the proper-case "Blue Note" and does NOT contain the
lowercased "blue note", locking the casing fix against regression. Verified the
end-to-end test passes against the shared dev Postgres.

### WR-01: `validate_contiguity` ignores its `segment_cache` argument; documented step-5 cross-check is unimplemented

**Files modified:** `src/gruvax/api/admin/validation.py`
**Commit:** cec2152
**Applied fix:** Conservative (contract-honesty) option only — no behavioral
change. Rewrote the `validate_contiguity` docstring so the step-5 SegmentCache
occupancy cross-check is clearly marked as a DEFERRED / not-yet-implemented
future enhancement (tracked as WR-01) rather than a current promise, and
documented that the `segment_cache` parameter is RESERVED for that future step
and currently UNUSED. The parameter was NOT renamed to `_segment_cache`: all
three call sites (`segments.py:231`, `segments.py:623`, `cubes.py:468`) pass it
positionally, and keeping the name stabilizes the call contract for the deferred
cross-check. The full SegmentCache occupancy cross-check (the reviewer's
"implement" option) was deliberately NOT implemented — that is a behavioral
enhancement out of scope for this verified phase. ruff/mypy confirmed the unused
parameter does not trip the gates.

### WR-03: Contiguity decision trusts the in-app `BoundaryCache` to be fresh

**Files modified:** `src/gruvax/api/admin/segments.py`
**Commit:** 289a6fd
**Applied fix:** Comment-only — no cache or SSE behavior change. Promoted the
integration test's cache-staleness note (test lines ~564-573) into code comments
on both live write paths (`put_bin_cut` before the PUT contiguity check, and
`insert_cut` before the insert contiguity check). The comments make explicit that
`build_proposed_cuts` reads the live in-app `BoundaryCache`, so the contiguity
decision is only as correct as the cache is fresh, and that guaranteeing
freshness here is deferred. The actual freshness/SSE-reload behavioral fix was
deliberately NOT changed (deferred/architectural).

## Skipped Issues

### WR-02: `build_proposed_cuts` scopes contiguity to a single unit, narrowing the invariant

**File:** `src/gruvax/api/admin/validation.py:66-85`; callers `segments.py:230, 622`
**Reason:** Deliberately deferred per fix guidance. This is a genuine cross-unit
gap — labels CAN span Kallax-unit boundaries in this collection's alphabetical
layout, so the "bins in different units are never adjacent" assumption does not
strictly hold. However, fixing it (dropping the unit filter or treating the last
bin of unit N and first bin of unit N+1 as adjacent) is a behavioral change that
requires its own plan + verification, and the verifier explicitly deferred it.
Per guidance, the unit filter was NOT dropped and NO "invariant-pinning" unit
test was added (the invariant the reviewer suggested pinning is actually false).
Recorded here as deliberately deferred.
**Original issue:** Per-unit contiguity scope cannot detect a scatter that
crosses the unit boundary; the "never adjacent" assumption is asserted in the
docstring, not enforced.

## Out-of-Scope Issues (Info — fix_scope is critical_warning)

These INFO findings were not in the fix scope (fix_scope=critical_warning) and
were not addressed:

- **IN-01** (`validation.py:89-107`): Inconsistent key-coercion between the
  `replace` (direct int compare) and `cascade` (`int(str(x))`) branches of
  `build_proposed_cuts`. Cosmetic/quality; both work because `BoundaryRow` fields
  are already int. Out of scope.
- **IN-02** (`segments.py:417-426` and `657-666`): Duplicated inline
  `SELECT ... FROM gruvax.segment_overrides` re-read across `set_bin_overrides`
  and `insert_cut`; candidate for extraction into `_load_all_overrides`.
  Pre-existing (not introduced by 05-06). Out of scope.
- **IN-03** (`RecordPickerSheet.tsx:250-252`): `BulkSaveError.errorType`
  (`'contiguity_error'` vs `'phantom_boundary'`) is discarded so both error types
  render identically. Acknowledged as an intentional conscious choice for v1.
  Out of scope.

---

_Fixed: 2026-05-23T21:26:15Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

---
phase: 05-segment-aware-position-precision
reviewed: 2026-05-22T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - frontend/src/routes/admin/ShelfBinList.tsx
  - frontend/src/api/adminClient.ts
  - frontend/src/routes/admin/BinWidthEditor.tsx
  - frontend/src/routes/admin/admin.css
  - src/gruvax/api/admin/segments.py
  - tests/integration/test_segment_api.py
findings:
  critical: 0
  warning: 5
  info: 4
  total: 9
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-05-22T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the Phase 05 human-verify checkpoint changes: the frontend insert-cut auto-refresh
(`ShelfBinList.tsx`), the corrected `insertCut` return type (`adminClient.ts`), the discoverability
caption (`BinWidthEditor.tsx`), the settle-animation CSS (`admin.css`), the cascade off-by-one fix
(`segments.py insert_cut`), and the cascade regression test (`test_segment_api.py`).

The headline cascade fix is **correct**: breaking on `nxt.is_empty` (the moment the empty absorber is
filled) instead of `curr.is_empty` (one step too late, which copied the empty cube's blank value onto
the next real bin) genuinely closes the data-loss bug. Reading ORIGINAL values from `boundaries` and
writing `is_empty=False` on every shifted cube is sound. The `boundaries[insert_after_idx + 1]` direct
index (line 545) is provably guarded by `validate_shelf_overflow`, which 400s before reaching it when no
trailing empty cube exists. The `insertCut` return-type correction (`{segments}` → `InsertCutResult`)
matches the backend's actual JSON shape and fixes a latent `undefined`-access bug for any consumer.

No BLOCKER-severity defects were found in the changed lines. However, there are five WARNING-level
issues: a percentage-rounding invariant that breaks on over-sum input, an unguarded cross-unit cascade,
incomplete test cleanup that pollutes shared `cube_boundaries`, a non-awaited segment invalidation that
can leave the new bin's mini-strip stale, and a re-seed effect that silently discards in-progress drag
edits after save.

## Warnings

### WR-01: `roundPercents` violates its own "sum to exactly 100" invariant on over-sum input

**File:** `frontend/src/routes/admin/BinWidthEditor.tsx:57-71`
**Issue:** The Hamilton/largest-remainder rounding only corrects a **positive** deficit (under-sum).
When the input fractions sum to **more than 1.0**, `deficit` is negative, the loop guard `deficit > 0`
is false immediately, and no surplus is removed. Verified empirically:
`roundPercents([0.55, 0.55])` returns `[55, 55]` (sums to 110), and `roundPercents([0.52, 0.52])`
returns `[52, 52]` (sums to 104). The docstring explicitly promises the integers "sum to exactly 100,
so the displayed numbers never read 99 or 101" — that guarantee is broken for over-sum (and the
under-distributed remainder case stays below 100 too). This is the very invariant commit `8a863bf`
("largest-remainder rounding so displayed widths sum to exactly 100%") was meant to enforce.

Trigger paths: floating-point drift accumulated across many drag operations; a server bin whose applied
fractions sum slightly above 1.0; and notably the legend's **auto** row
(`roundPercents(segs.map((s) => s.auto_fraction ?? s.fraction))` at line 300) which uses raw
count-derived `auto_fraction` values that are not guaranteed to sum to exactly 1.0 once any label is
overridden.

**Fix:** Handle the negative-deficit (surplus) branch symmetrically — subtract from the smallest
remainders when `deficit < 0`:
```typescript
function roundPercents(fractions: number[]): number[] {
  if (fractions.length === 0) return []
  const raw = fractions.map((f) => f * 100)
  const floors = raw.map((v) => Math.floor(v))
  let deficit = 100 - floors.reduce((a, b) => a + b, 0)
  const result = [...floors]
  const byRemainder = raw
    .map((v, i) => ({ i, rem: v - floors[i] }))
    .sort((a, b) => b.rem - a.rem)
  // Distribute a positive deficit to the largest remainders…
  for (let k = 0; deficit > 0 && k < byRemainder.length; k++) {
    result[byRemainder[k].i] += 1
    deficit -= 1
  }
  // …and reclaim a negative deficit (surplus) from the smallest remainders.
  for (let k = byRemainder.length - 1; deficit < 0 && k >= 0; k--) {
    if (result[byRemainder[k].i] > 0) {
      result[byRemainder[k].i] -= 1
      deficit += 1
    }
  }
  return result
}
```

### WR-02: insert-cut cascade silently flows records across a physical shelf-unit boundary

**File:** `src/gruvax/api/admin/segments.py:504-587` (cascade) and
`src/gruvax/api/admin/validation.py:262-267` (overflow check)
**Issue:** Both `insert_cut` and `validate_shelf_overflow` sort **all** boundaries globally by
`(unit_id, row, col)` and treat the entire collection as one continuous tape. `validate_shelf_overflow`
returns "safe" on the **first empty cube anywhere after the insertion point, regardless of unit**.
Consequence: inserting a cut in unit 1 when unit 1 is full but unit 2 has a free cube will cascade
unit 1's trailing record into unit 2 (e.g. across "Left Kallax" → "Right Kallax"). The fixture's units
("Left Kallax", "Right Kallax") are distinct physical shelves, and unit 2 does not alphabetically
continue unit 1 (unit 1 ends Columbia/Tamla/Impulse; unit 2 starts Riverside/Atlantic), so the global
tape model is not obviously the product intent. A spill into the wrong physical shelf would put a record
in a cube the kiosk lights up on the wrong unit.

This is classified WARNING rather than BLOCKER because the cut-insert change-set is undoable via history
revert and the cross-unit model may be deliberate; it must be confirmed before shipping.

**Fix:** If units are independent shelves, scope both the overflow check and the cascade stop to the
insertion cube's `unit_id` (only treat trailing empty cubes within the same unit as absorbers, and
404/overflow when the unit has no trailing free cube). If cross-unit flow is intentional, document the
invariant explicitly in the `insert_cut` docstring and add a test asserting the cross-unit spill is the
desired behavior.

### WR-03: cascade regression test leaves `cube_boundaries` mutated — incomplete cleanup pollutes the shared dev DB

**File:** `tests/integration/test_segment_api.py:457-468`
**Issue:** `test_insert_cut_cascade_preserves_bin_after_empty` performs a real insert-cut that rewrites
4+ rows in `gruvax.cube_boundaries`, but the `finally` cleanup only deletes from
`gruvax.boundary_history` (`DELETE FROM gruvax.boundary_history WHERE change_set_id = %s`). The mutated
`cube_boundaries` rows are never restored. The module fixture re-seeds boundaries exactly **once** at
module setup (`scope="module"`, before any test), and the suite "shares the dev DB and does not
otherwise reset it" (per the fixture docstring). So after this module runs, `cube_boundaries` is left in
a shifted state for any subsequent module/run that assumes the canonical fixture — a latent
cross-module test-isolation defect of exactly the kind the fixture docstring warns about for history
rows.

**Fix:** Restore `cube_boundaries` in the `finally` block too, e.g. re-run
`load_boundaries(_BOUNDARIES_YAML)` (or invert the recorded `boundary_history` rows before deleting
them) so the table is returned to its canonical state:
```python
finally:
    from gruvax.db.seed_boundaries import load_boundaries
    if change_set_id:
        async with db_pool.connection() as conn:
            await conn.execute(
                "DELETE FROM gruvax.boundary_history WHERE change_set_id = %s",
                (change_set_id,),
            )
            await conn.commit()
    await load_boundaries(_BOUNDARIES_YAML)  # restore cube_boundaries the cascade mutated
```

### WR-04: new bin's mini-strip can render stale — segment invalidation is not awaited before the diff completes

**File:** `frontend/src/routes/admin/ShelfBinList.tsx:128-138`
**Issue:** `handleInsertCommit` awaits the `['admin','cubes']` invalidation but fires the
`['admin','segments', unitId]` invalidation with `void` (not awaited). The diff that discovers the
newly-created bin and the subsequent render of its `BinCard` therefore proceed before that bin's
segment query has refetched. The new `BinCard` mounts and immediately fetches its own
`['admin','segments', unitId, row, col]` (a brand-new key with no cache entry), so the strip will fill
in — but for cubes whose segments shifted but whose `cubeKey` already existed, the prefix-invalidation
is still in flight, so their mini-strips can momentarily show pre-cascade proportions. Functionally
recoverable, but the "settle from yellow → normal" animation is supposed to signal "this is now
correct," and the strip underneath it may briefly contradict that.

**Fix:** Await the segment invalidation as well so the diff and animation only fire once both caches are
fresh:
```typescript
await Promise.all([
  queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] }),
  queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId] }),
])
```

### WR-05: save re-seed silently discards in-progress local drag edits

**File:** `frontend/src/routes/admin/BinWidthEditor.tsx:124-129` and `403-434`
**Issue:** After `handleSave`, `void queryClient.invalidateQueries({ queryKey: ['admin','segments',
unitId, rowNum, colNum] })` triggers a refetch that produces a **new** `segsData.segments` array
reference. The seeding effect compares by reference (`segsData.segments !== seededRef.current`), so any
refetch re-seeds `segments` from server data, overwriting whatever the user has dragged since. If the
user drags, saves, then keeps dragging while the refetch is in flight, the in-flight refetch completing
will wipe the post-save drag edits with no indication. The seeding effect's "once per load" comment
implies it should not clobber active local state, but reference-equality re-seeding makes every server
refresh authoritative over local edits.

**Fix:** Only re-seed when there are no unsaved local changes, or gate seeding on a "dirty" flag that is
set on drag/reset and cleared on save/initial-load, so a background refetch cannot silently discard
edits the user is still making.

## Info

### IN-01: `insertCut` return value is computed by the server but ignored by the only consumer

**File:** `frontend/src/routes/admin/ShelfBinList.tsx:254` and `RecordPickerSheet.tsx:242-243`
**Issue:** `RecordPickerSheet` calls `onCommit(result)` with the full `InsertCutResult`
(`affected`, `change_set_id`, `inserted_after`, `new_cut`), but `ShelfBinList`'s handler is
`onCommit={() => void handleInsertCommit()}` — the argument is dropped, and `handleInsertCommit` re-diffs
from the cube cache instead. The newly-corrected return type is therefore dead relative to its only
caller. Not a defect, but the cache-diff could be replaced by trusting `result.inserted_after` /
`result.new_cut` to locate the changed bin deterministically, avoiding the snapshot-and-diff dance.
**Fix:** Either consume `result` to flag the changed cube directly, or document that the return value is
retained only for history/debugging.

### IN-02: `validate_no_empty_bin` only checks the after-bin, not that the NEW bin is non-empty

**File:** `src/gruvax/api/admin/validation.py:180-221` (called from `segments.py:490-497`)
**Issue:** `validate_no_empty_bin` is passed `(after_uid, after_row, after_col)` and only rejects the
case where the proposed cut equals the after-bin's own cut point (which would empty the after-bin). It
does not verify that the newly created bin (the new cut → the next existing cut) actually contains at
least one record. A new cut placed between two records that resolve to the same position relative to the
next cut could still create a zero-record new bin. This is a pre-existing limitation (not introduced in
this phase's diff) but is adjacent to the cascade logic under review.
**Fix:** Extend the empty-bin guard to also confirm the span from the new cut to the next existing cut
contains ≥1 record, or document the narrower guarantee.

### IN-03: `affected` count includes the absorber but the docstring says "rewrote" — count includes a formerly-empty cube

**File:** `src/gruvax/api/admin/segments.py:543-608, 644`
**Issue:** `affected` = `len(affected_cubes)` counts every cube written, including the trailing empty
cube that absorbed the shift (now non-empty). The `InsertCutResult.affected` doc comment
("Number of cubes the cascade rewrote") is accurate, but a UI surfacing "N cubes changed" would include
the absorber, which a user may not consider "changed" (it was empty). Minor wording/semantics nit.
**Fix:** If the count is ever shown to the user, clarify whether it includes the absorber, or expose the
new-bin count separately.

### IN-04: `seededRef` comparison relies on referential identity that TanStack Query does not guarantee to preserve

**File:** `frontend/src/routes/admin/BinWidthEditor.tsx:121-129`
**Issue:** The "seed once per load" guard depends on `segsData.segments` keeping a stable reference
between renders for the same data and changing reference on refetch. TanStack Query's
`structuralSharing` (on by default) can preserve the previous reference when refetched data is deeply
equal — meaning a genuine no-op refetch will *not* re-seed (good), but it also means the guard's
behavior is coupled to a Query internal that could change. This compounds WR-05.
**Fix:** Seed from an explicit data version/key (e.g. include a fetch timestamp or query `dataUpdatedAt`
in the dependency), or drive seeding off `unitId/row/col` route params rather than array identity.

---

_Reviewed: 2026-05-22T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

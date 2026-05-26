# Phase 5 — Re-plan Notes (Waves 2–5)

> Created 2026-05-22 after Wave 1 (05-01) merged and the post-merge gate exposed a
> consumer-scoping gap. **Wave 1 is correct and complete — do NOT re-plan or revert it.**
> Re-plan ONLY 05-02..05-05 so the suite can reach green by end of phase.
> Decision: user chose "Re-plan remaining waves" over gap-closure / inline-patch / rollback.

## What happened

Plan 05-01 dropped `last_label` / `last_catalog` from `BoundaryRow` and from
`cube_boundaries` (migration 0005). This is correct per the cut-point model (D-05).
But the original 05-02..05-05 decomposition only re-homed **some** consumers of those
fields. After Wave 1 merged to `main`, the post-merge gate reported **~40 failing tests
and 12 mypy errors**, and several consumers are healed by **no** existing plan — so even
after all 5 original plans, `main` would not compile/pass.

The 05-01 SUMMARY also omitted the grep-audit note its plan (`<output>`) required, which
is why the gap surfaced at execution time rather than at plan time.

## Consumers of the removed fields — coverage status

### Already covered by the existing remaining plans
- `src/gruvax/estimator/algorithm.py` — Wave 2 (05-02) rewrites for segment estimator
- `src/gruvax/estimator/boundary_math.py` — Wave 2 (05-02)
- `src/gruvax/api/admin/cubes.py` — Wave 3 (05-03): drops `last_*` from `BoundaryEdit` + `_compute_movement_counts()`
- `src/gruvax/api/admin/validation.py` — Wave 3 (05-03)
- `db/queries.py` **read-helpers only** (`cube_exact_match`, `find_boundary_near_misses`) — referenced by 05-03

### ORPHANS — re-plan MUST add coverage (no current plan touches these)

**Source:**
- `src/gruvax/api/units.py` — constructs `BoundaryRow(last_label=…, last_catalog=…)` at lines **109–110** and **186–187** → runtime `TypeError`. Mechanical: drop the two kwargs (the compute helpers it feeds become segment-aware via 05-02).
- `src/gruvax/db/seed_boundaries.py` — INSERT/UPSERT writes dropped columns (lines **65, 71–72, 82–83**) → `just seed-dev` breaks. Remove `last_*` from the column list, the `ON CONFLICT … SET`, and the value tuple.
- `src/gruvax/db/queries.py` — beyond the read-helpers, `get_cube_boundary` SELECT (line **549**) and `update_cube_boundary` (params **569–570**, SQL **592**, value tuple **598**) still reference the dropped columns → runtime DB errors on admin edits. Needs cut-point rework, sequenced with 05-03.
- `src/gruvax/estimator/boundary_cache.py:100` — residual mypy `[index]` ("object not indexable") in the `_overrides` dict-comprehension (`r` typed as `object`). Small 05-01 follow-up; fold into 05-02 or a typing fix. Type the cursor rows (e.g. `cast`/row factory) so `r[0..4]` is indexable.

**Tests** (test OLD `last_label`/`last_catalog` behavior — must be re-homed to the segment model):
- Semantic (rewrite for segment estimator): `tests/unit/test_algorithm.py` (~31 cases), `tests/property/test_fill_level_property.py`, `tests/property/test_boundary_validation_property.py`, `tests/integration/test_run_all_algorithms.py`
- Mechanical (`BoundaryRow(...)` construction — drop kwargs / use cut-point fixtures): `tests/unit/test_fill_level.py`, `tests/unit/test_diff_preview.py`, `tests/unit/test_boundary_validation.py`, `tests/integration/test_cubes_bulk.py`, `tests/integration/test_change_set.py`, `tests/integration/test_boundary_editor.py`, `tests/integration/test_sse.py`
- Verify: `tests/conftest.py` still grep-matches `last_label` after the 05-01 update — confirm the boundary fixture loader truly ignores stale keys or finish the cleanup.

## Required outcome for the re-plan

1. Every `last_label`/`last_catalog` consumer above is assigned to a wave (no orphans).
2. Each wave leaves `just lint`, `just typecheck`, and `just test` **green** (the migration is irreversible mid-phase, so define the healing sequence: estimator → admin/DB → tests).
3. Restore the 05-01 must_have intent ("every construction site compiles") as a phase-exit gate.
4. Phase verifier should run the full suite (not just `--collect-only`) at phase end.

## Reproduce the gate

```bash
just lint        # 10 errors (7 autofixable, in 05-01's new test files — import order, F401, RUF059)
just typecheck   # 12 mypy errors across boundary_cache(1), boundary_math(2), algorithm(3), units(4), cubes(2)
just test        # ~40 failures: TypeError: BoundaryRow.__init__() got unexpected keyword 'last_label'
```

---
phase: 5
slug: segment-aware-position-precision
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-22
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `05-RESEARCH.md` § Validation Architecture. Per Phase 5 decision D-01,
> the prior A/B "meet-or-beat §4.1" harness gate is dropped — correctness rests on
> unit + Hypothesis-invariant tests, anchored by the single-segment-bin regression
> invariant (D-02) that proves the estimator reduces to §4.1 when a bin has one label.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio + Hypothesis |
| **Config file** | `pyproject.toml` (existing) |
| **Quick run command** | `pytest tests/unit tests/property -x -q` |
| **Full suite command** | `pytest tests/ -q` |
| **Estimated runtime** | ~30–60 seconds (full suite); quick run < 15s |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit tests/property -x -q`
- **After every plan wave:** Run `pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite green **AND** `pytest tests/integration/test_locate.py --benchmark-only` shows p95 ≤ 50 ms
- **Max feedback latency:** 60 seconds

---

## Per-Requirement Verification Map

> Task IDs are assigned during planning; this map keys the validation contract by requirement.
> Each plan task implementing a requirement must carry an `<automated>` verify referencing the
> command below, or declare a Wave 0 dependency on the listed test file.

| Requirement | Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|-----------|-------------------|-------------|
| SEG-01 | Migration 0005 drops `last_label`/`last_catalog`, adds `segment_overrides`; `BoundaryRow` updated; up/down round-trips clean | integration | `pytest tests/integration/test_migrate_0005.py -x` | ❌ W0 |
| SEG-02 | `SegmentCache.derive()` produces correct ordered per-label segments from cut points | unit | `pytest tests/unit/test_segment_cache.py -x` | ❌ W0 |
| SEG-03 | Counts are row-counts of `v_collection`, not catalog arithmetic; duplicate owned copies + variants (`37` vs `37-r`) counted | unit | `pytest tests/unit/test_segment_cache.py::test_row_count_not_arithmetic -x` | ❌ W0 |
| SEG-04 | Optional physical-width override wins over count-derived fraction; per-bin widths sum to 1.0 | unit + property | `pytest tests/unit/test_segment_cache.py::test_override_applied tests/property/test_segment_props.py::test_per_bin_fractions_sum_to_one -x` | ❌ W0 |
| SEG-05 | Contiguity validator rejects non-adjacent segment scatter | unit | `pytest tests/unit/test_segment_cache.py::test_contiguity_validation -x` | ❌ W0 |
| SEG-06 | Two-level interpolation (bin/segment → preceding-label fraction offset → row-rank); straddle resolves to correct bin without special-casing | unit + property | `pytest tests/unit/test_segment_estimator.py -x && pytest tests/property/test_segment_props.py -x` | ❌ W0 |
| SEG-07 | Single-segment bin reproduces §4.1 exactly; `estimator_version = "segment-v1"`; §4.8 cube-only retained as timeout/low-confidence fallback | property | `pytest tests/property/test_segment_props.py::test_single_segment_bin_reproduces_v1_index -x` | ❌ W0 |
| SEG-08 | Admin cut-point + width-override API (validate → bulk → invalidate path); `require_admin`; locate p95 ≤ 50 ms preserved | integration + benchmark | `pytest tests/integration/test_segment_api.py -x && pytest tests/integration/test_locate.py --benchmark-only` | ❌ W0 |

*Status legend: ✅ green · ❌ red · ⚠️ flaky · W0 = created in Wave 0*

---

## Extended Hypothesis Invariants (D-02) — `tests/property/test_segment_props.py`

| Invariant | Test name |
|-----------|-----------|
| Per-bin segment fractions sum to 1.0 | `test_per_bin_fractions_sum_to_one` |
| Single-segment bin reproduces §4.1 exactly (regression anchor) | `test_single_segment_bin_reproduces_v1_index` |
| Straddle resolves to the correct bin by rank | `test_straddle_resolves_to_correct_bin` |
| `primary_cube ∈ label_span` (carried from §7.3) | `test_primary_cube_in_label_span` |
| `0 ≤ start ≤ end ≤ 1` (carried from §7.3) | `test_sub_cube_interval_bounds` |
| Monotone position within a label (carried from §7.3) | `test_monotone_position_within_label` |
| Stability under cosmetic catalog-string noise (carried from §7.3) | `test_cosmetic_stability` |

---

## Wave 0 Requirements

- [ ] `tests/unit/test_segment_cache.py` — SEG-02, SEG-03, SEG-04, SEG-05 stubs
- [ ] `tests/unit/test_segment_estimator.py` — SEG-06 unit stubs
- [ ] `tests/property/test_segment_props.py` — SEG-06, SEG-07 Hypothesis invariants
- [ ] `tests/integration/test_segment_api.py` — SEG-08 API integration stubs
- [ ] `tests/integration/test_migrate_0005.py` — SEG-01 Alembic up/down round-trip
- [ ] `fixtures/synth_collection.py` — extend with multi-label + straddle factories

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cut-point drag UX feel + width-override slider drift highlight | SEG-08 (UI) | Drag interaction and visual drift cue (>3pp) are visual/tactile, not assertable in unit tests | In admin cut-point editor: drag a cut point and a width-override slider; confirm diff-preview reflects changes, drift highlight appears when override deviates >3pp from auto, and change-set undo restores prior state |

*All non-UI phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies *(plan-checker Dim 8a)*
- [x] Sampling continuity: no 3 consecutive tasks without automated verify *(plan-checker Dim 8c)*
- [x] Wave 0 covers all MISSING references *(plan-checker Dim 8d — created in Plan 05-01 Task 3)*
- [x] No watch-mode flags *(plan-checker Dim 8b)*
- [x] Feedback latency < 60s *(quick run < 15s, full suite ~30–60s)*
- [x] `nyquist_compliant: true` set in frontmatter

> Sign-off reflects the **plan contract** verified by gsd-plan-checker (2026-05-22).
> `wave_0_complete` remains false until execution creates the Wave 0 test stubs (Plan 05-01).

**Approval:** approved 2026-05-22

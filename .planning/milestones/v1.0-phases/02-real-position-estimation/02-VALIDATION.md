---
phase: 2
slug: real-position-estimation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-20
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Draft created at plan-phase research step (before plans exist). Task IDs in the
> Per-Task Verification Map are assigned by the planner; the plan-checker / nyquist
> auditor reconciles this map against the written PLAN.md files.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio + Hypothesis 6.x + pytest-benchmark 5.x (Python 3.14); Vitest for frontend components |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/unit tests/property -q -x` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Benchmark command** | `uv run pytest tests/unit/test_algorithm.py -k benchmark --benchmark-only` |
| **Estimated runtime** | ~60 seconds (full suite incl. property tests; benchmark separate) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit tests/property -q -x`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green + benchmark gate (p95 ≤ 50 ms) passes
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Task IDs are placeholders until plans are written. Each requirement below has at
> least one automated verification; the planner must attach these to concrete tasks.

| Task ID | Req | Behavior | Test Type | Automated Command | File Exists |
|---------|-----|----------|-----------|-------------------|-------------|
| TBD | POS-05 | §4.1 returns populated SubInterval for multi-record labels | unit | `uv run pytest tests/unit/test_algorithm.py::test_locate_by_index_multi_record -x` | ❌ W0 |
| TBD | POS-05 | §4.8 fallback selected when confidence ≤ 0.30 (or timeout) | unit | `uv run pytest tests/unit/test_algorithm.py::test_fallback_to_cube_only -x` | ❌ W0 |
| TBD | CUBE-10 | Singleton → faint full-cube band (D-02): start=0.0, end=1.0, confidence=0.30 | unit | `uv run pytest tests/unit/test_algorithm.py::test_singleton_full_cube_band -x` | ❌ W0 |
| TBD | POS-03 | p95 ≤ 50 ms CPU-only, no DB calls during compute | benchmark | `uv run pytest tests/unit/test_algorithm.py -k benchmark --benchmark-only` | ❌ W0 |
| TBD | POS-06 | A/B harness runs synthetic shapes; §4.1 MAE ≤ §4.8 MAE per shape | harness (CI+local) | `uv run python scripts/run_all_algorithms.py --ci` | ❌ W0 |
| TBD | POS-06 | CI test: §4.1 MAE ≤ §4.8 MAE on every planted-truth shape | integration | `uv run pytest tests/integration/test_run_all_algorithms.py -x -q` | ❌ W0 |
| TBD | CUBE-03 | label_span has ≥2 entries for a label straddling a cube boundary | integration | `uv run pytest tests/integration/test_locate.py::test_multi_cube_label_span -x` | ❌ W0 |
| TBD | CUBE-04 | sub_cube_interval populated, 0≤start≤end≤1, may set crosses_boundary | integration | `uv run pytest tests/integration/test_locate.py::test_sub_cube_interval_bounds -x` | ❌ W0 |
| TBD | SRCH-08 | is_catalog_query truth table + did_you_mean graceful-degrade (no DB) | unit | `uv run pytest tests/unit/test_queries.py -x -q` | ❌ W0 |
| TBD | SRCH-07 | did_you_mean returned when FTS empty + high-trigram-sim candidate | integration | `uv run pytest tests/integration/test_search.py::test_did_you_mean -x` | ❌ W0 |
| TBD | SRCH-08 | catalog-like query boosts catalog-number field score vs text query | integration | `uv run pytest tests/integration/test_search.py::test_catalog_boost -x` | ❌ W0 |
| TBD | CUBE-08 | lands animation interruptible — new selection hard-cancels previous | manual | see Manual-Only Verifications | ❌ N/A |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Hypothesis Invariants (algorithm-agnostic, INTERPOLATION §7.3 → `tests/property/test_estimator_props.py`)

- `primary_cube ∈ label_span` (when primary_cube is not None)
- `0.0 ≤ sub_cube_interval.start ≤ end ≤ 1.0`
- monotone position within a label (sorted by `parse_key`)
- stability under cosmetic noise (case / separator / whitespace perturbations)

---

## Wave 0 Requirements

- [ ] `src/gruvax/estimator/collection_snapshot.py` — new module (mirror BoundaryCache lifespan + `_load_rows` seam + `invalidate()`)
- [ ] `tests/unit/test_collection_snapshot.py` — snapshot unit tests (load, get_label_records, invalidate, testing seam)
- [ ] `tests/unit/test_algorithm.py` — EXTEND with §4.1 golden cases + benchmark test
- [ ] `tests/property/test_estimator_props.py` — Hypothesis invariants (new file)
- [ ] `fixtures/golden_cases.yaml` — golden case fixture (new file, repo-root `fixtures/` to match conftest `FIXTURE_DIR`)
- [ ] `fixtures/synth_collection.py` — planted-truth synthetic generator (new file, repo-root `fixtures/`; importable via the `pythonpath="."` strategy)
- [ ] `fixtures/__init__.py` + repo-root `conftest.py` + `pyproject.toml` `[tool.pytest.ini_options] pythonpath = ["."]` — IMPORT-PATH STRATEGY (single source of truth: makes `from fixtures.synth_collection import ...` and `from scripts.run_all_algorithms import ...` resolve in pytest)
- [ ] `scripts/run_all_algorithms.py` + `scripts/__init__.py` — A/B harness (new files; harness inserts repo root onto `sys.path` for standalone runs; NOT in pytest collection — but `tests/integration/test_run_all_algorithms.py` IS)
- [ ] `tests/unit/test_queries.py` — Wave-0 unit tests for `is_catalog_query` + `did_you_mean_query` graceful-degrade (mock `psycopg.errors.UndefinedFunction`); no live DB
- [ ] `tests/integration/test_run_all_algorithms.py` — CI assertion that §4.1 MAE ≤ §4.8 MAE per shape (new file)
- [ ] `tests/integration/test_locate.py` / `tests/integration/test_search.py` — extend for span/interval + did-you-mean/boost

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lands animation interruptible | CUBE-08 | Animation cancellation is a perceptual/timing behavior in the browser, not unit-assertable | Select result A, then immediately select result B mid-animation; verify B's sequence (span fade-in → primary pulse → bar slide-in) runs fresh with no cross-fade or "behind" feel |
| ≤600 ms lands animation on real hardware | CUBE-08 (SC-3) | Frame budget must be validated on the actual Pi 5 + 7″ touchscreen, not dev machine | On the Pi kiosk, trigger a selection and confirm the full choreography completes within ≤600 ms and stays smooth |
| Sub-cube bar attenuation reads correctly | CUBE-04 (D-01) | Visual gradient (intensity/glow scaling with confidence) is a design judgment | Compare a high-confidence dense label vs a low-confidence singleton; bar should read crisp/bright vs faint/wide |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

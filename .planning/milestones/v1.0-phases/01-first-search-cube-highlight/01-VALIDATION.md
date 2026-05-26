---
phase: 01
slug: first-search-cube-highlight
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-19
---

# Phase 01 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `01-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + Hypothesis (backend); Vitest optional for frontend logic |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` — Wave 0 creates this (`asyncio_mode = "auto"`, `testpaths`, hypothesis profile) |
| **Quick run command** | `just test-unit` → `pytest tests/unit/ tests/property/ -x -q` |
| **Full suite command** | `just test` → `pytest tests/ -q --tb=short` (integration needs running Postgres) |
| **Estimated runtime** | ~5 s quick (unit + property); ~30 s full (incl. integration against seeded Postgres) |

---

## Sampling Rate

- **After every task commit:** Run `just test-unit` (unit + property; < 5 s)
- **After every plan wave:** Run `just test` (full suite incl. integration; requires Postgres)
- **Before `/gsd:verify-work`:** Full suite green + e2e smoke (`docker compose up` → `curl /api/health` → load SPA)
- **Max feedback latency:** ~5 s (quick), ~30 s (full)

---

## Per-Task Verification Map

> Requirement-level map from RESEARCH.md. Task IDs (`{N}-PP-TT`) are bound to concrete
> tasks during planning/execution; until then rows are keyed by requirement + behavior.

| Req | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| POS-01 | `parse_key("BLP 9") < parse_key("BLP 10")` (numeric-aware) | — | N/A | unit | `pytest tests/unit/test_normalize.py -x` | ❌ W0 | ⬜ pending |
| POS-01 | Total-order property over arbitrary catalog strings | — | N/A | property | `pytest tests/property/test_parser_props.py -x` | ❌ W0 | ⬜ pending |
| POS-01 | Cosmetic stability `parse_key("BLP 4195") == parse_key("blp-4195")` | — | N/A | unit | `pytest tests/unit/test_normalize.py::test_cosmetic_stability -x` | ❌ W0 | ⬜ pending |
| POS-01 | Multi-prefix `parse_key("BLP 4001") != parse_key("BST 4001")` | — | N/A | unit | `pytest tests/unit/test_normalize.py::test_multi_prefix -x` | ❌ W0 | ⬜ pending |
| POS-04 | Boundary cache loaded at startup contains all `cube_boundaries` rows | — | N/A | unit | `pytest tests/unit/test_algorithm.py::test_cache_load -x` | ❌ W0 | ⬜ pending |
| POS-02 | `/api/locate?release_id=X` → LocateResult `confidence=0.30` for in-range record | — | N/A | integration | `pytest tests/integration/test_locate.py -x` | ❌ W0 | ⬜ pending |
| POS-02 | HTTP 404 for `release_id` not in `v_collection` | — | N/A | integration | `pytest tests/integration/test_locate.py::test_not_found -x` | ❌ W0 | ⬜ pending |
| POS-02 | HTTP 200 `confidence=0, primary_cube=null, label_span=[]` when no boundary covers label | — | N/A | integration | `pytest tests/integration/test_locate.py::test_no_boundary -x` | ❌ W0 | ⬜ pending |
| SRCH-01 | `/api/search?q=BLP+4195` returns matching record (catalog path) | T-01 (SQLi) | Parameterized query; no f-string SQL | integration | `pytest tests/integration/test_search.py::test_catalog_path -x` | ❌ W0 | ⬜ pending |
| SRCH-01 | FTS match on artist-name substring | T-01 (SQLi) | Parameterized FTS | integration | `pytest tests/integration/test_search.py::test_fts_artist -x` | ❌ W0 | ⬜ pending |
| SRCH-04 | `/api/search?q=zzznomatch` → `{"items": []}` | — | N/A | integration | `pytest tests/integration/test_search.py::test_no_results -x` | ❌ W0 | ⬜ pending |
| SRCH-05/06 | Debounce + loading indicator only when request > ~300 ms | — | N/A | unit (frontend) | `vitest run` (or manual) | ❌ W0 | ⬜ pending |
| DEP-02 | Startup probe `SELECT 1 FROM gruvax.v_collection LIMIT 1` passes on synthetic seed | — | N/A | integration | `pytest tests/integration/test_health.py::test_view_probe -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — shared fixtures (async db pool, boundary cache from YAML fixture, FastAPI `AsyncClient`)
- [ ] `tests/unit/test_normalize.py` — POS-01 golden cases (case/separator/NFKC/numeric-split)
- [ ] `tests/property/test_parser_props.py` — Hypothesis invariants (total order, cosmetic stability, monotonic-in-catalog within label, estimate within label-span)
- [ ] `tests/unit/test_algorithm.py` — cube-only estimator + cache-load unit cases
- [ ] `tests/integration/test_search.py` — FTS + catalog path + no-results
- [ ] `tests/integration/test_locate.py` — LocateResult contract + 404 + no-boundary semantics
- [ ] `tests/integration/test_health.py` — startup probe / degraded health
- [ ] `pyproject.toml` pytest config (`asyncio_mode = "auto"`, `testpaths`, hypothesis profile)
- [ ] Framework install via `uv add --dev pytest pytest-asyncio hypothesis httpx`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Grid renders N×4×4 (32 cubes) with address overlays + desaturated empty state | CUBE-01, CUBE-05, CUBE-06 | Visual; covered by UI-SPEC, no DOM-snapshot harness in Phase 1 | `docker compose up`; open SPA; confirm 2×(4×4) grid, each cube shows row+col, empty cubes desaturated |
| Top result auto-highlights its cube; tapping another result re-highlights | SRCH-02, CUBE-02 | Visual interaction | Type "Coltrane"; confirm top result highlights its cube; tap a different result; confirm highlight moves |
| ~200 ms keystroke→highlight perceived locally | (D-02 design target) | Perceptual, not a hard gate this phase | Observe responsiveness during demo; real p95 gate is Phase 2/7 |
| `docker compose up` brings up `gruvax-api` + `mosquitto` on `lux` | DEP-01 | Requires `lux` host | On `lux`: `docker compose up -d`; `docker compose ps` shows both healthy; `curl /api/health` 200 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test infra in plan 01-01; per-area stubs land ahead of dependents in waves 1–3)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

> `wave_0_complete` stays `false` until execution: the Wave 0 test files are authored during execute-phase, not at plan time. The validation *strategy* is approved; the *artifacts* are produced by the executor and the validator flips this flag when they land.

**Approval:** approved 2026-05-19

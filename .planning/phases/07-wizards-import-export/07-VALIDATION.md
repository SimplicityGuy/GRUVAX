---
phase: 7
slug: wizards-import-export
status: approved
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-24
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `07-RESEARCH.md` § Validation Architecture. Per-task IDs are filled by
> the planner once PLAN.md files exist (this strategy was authored before planning, since
> UI-SPEC is being generated first).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + httpx + Hypothesis |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `pytest tests/ -x -q -k "not hypothesis"` (~15s) |
| **Full suite command** | `pytest tests/ --cov=gruvax` (~60s) |
| **Estimated runtime** | ~15s quick / ~60s full |

> **Data rule (project constraint):** all import/export tests use SYNTHETIC boundary +
> collection data. The real collection CSV and `background/` are never read by tests.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q -k "not hypothesis"`
- **After every plan wave:** Run `pytest tests/ --cov=gruvax`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~15 seconds (quick) / ~60 seconds (full)

---

## Per-Task Verification Map

> Task IDs (`7-NN-NN`) are TBD until the planner emits PLAN.md. Rows below are the
> requirement-level verification contract from research; the planner MUST attach each
> to a concrete task and fill the Task ID + Wave columns.

| Task ID | Req | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | Status |
|---------|-----|----------|------------|-----------------|-----------|-------------------|--------|
| 7-04-02 | ADMN-04 | Wizard accumulates cut points, commits atomically via `cubes/bulk` | — | One `change_set_id`; no partial commits (Pitfall 7) | pytest-asyncio API | `pytest tests/integration/test_wizard.py -x` | ⬜ pending |
| 7-01-02 | ADMN-04 | Wizard commit writes `source='wizard'`, surfaces correct History label | — | N/A | pytest-asyncio API | `pytest tests/integration/test_wizard.py::test_source_label -x` | ⬜ pending |
| 7-03-02 | ADMN-05 | CSV import: parse → validate → commit → history row `source='csv'` | T-IMPORT-CSV | `csv.DictReader` + `BoundaryEdit` validation before any DB write | pytest-asyncio API | `pytest tests/integration/test_import.py::test_csv_import -x` | ⬜ pending |
| 7-03-02 | ADMN-05 | YAML import: parse → validate → commit; round-trip identity | T-YAML-BOMB | `yaml.safe_load()` ONLY (never `yaml.load`); reject > 100 KB | Hypothesis property | `pytest tests/property/test_import_roundtrip.py -x` | ⬜ pending |
| 7-03-02 | ADMN-05 | Partial import (16 of 32 cubes): remaining cubes become `is_empty` | — | Atomic replace-all (D-09) | pytest-asyncio API | `pytest tests/integration/test_import.py::test_partial_import -x` | ⬜ pending |
| 7-03-02 | ADMN-05 | Import with phantom row: validate 400, ZERO partial state in DB | — | Phantom-block (Pitfall 6/7) | pytest-asyncio API | `pytest tests/integration/test_import.py::test_phantom_row_rejected -x` | ⬜ pending |
| 7-03-02 | ADMN-05 | Import with contiguity violation: validate rejects, no partial state | — | SEG-05 enforced on commit path | pytest-asyncio API | `pytest tests/integration/test_import.py::test_contiguity_violation -x` | ⬜ pending |
| 7-04-01 | ADMN-10 | Reshuffle draft survives reload (localStorage → re-validate → commit) | — | Nothing reaches DB until final commit (D-05) | Zustand unit + API | `pytest tests/unit/test_reshuffle_draft.py -x` | ⬜ pending |
| 7-01-02 | ADMN-10 | Reshuffle commit writes `source='reshuffle'` | — | N/A | pytest-asyncio API | `pytest tests/integration/test_wizard.py::test_reshuffle_source -x` | ⬜ pending |
| 7-03-01 | BAK-01 | Export YAML → re-import → zero diff (SC4 round-trip identity) | — | N/A | Hypothesis property | `pytest tests/property/test_export_roundtrip.py -x` | ⬜ pending |
| 7-03-01 | BAK-01 | Export includes per-label width overrides when present (D-10) | — | N/A | pytest-asyncio API | `pytest tests/integration/test_export.py::test_overrides_in_export -x` | ⬜ pending |
| 7-03-01 | BAK-02 | Settings export NEVER contains `auth.pin_hash` (hard exclusion) | T-PIN-LEAK | PIN never serialized to a downloadable file (D-14, Pitfall 12) | unit (always runs) | `pytest tests/unit/test_settings_export.py::test_no_pin_in_export -x` | ⬜ pending |
| 7-03-01 | BAK-02 | Settings export includes all `_ALLOWED_SETTINGS_KEYS` | — | N/A | unit | `pytest tests/unit/test_settings_export.py::test_all_allowed_keys -x` | ⬜ pending |
| 7-03-02 | BAK-02 | Settings import unknown key → 422, no DB write | T-SETTINGS-KEY | Key whitelist (`_ALLOWED_SETTINGS_KEYS`) | pytest-asyncio API | `pytest tests/integration/test_settings_import.py::test_unknown_key_rejected -x` | ⬜ pending |
| 7-03-02 | BAK-02 | Settings import `auth.*` key → rejected | T-PIN-LEAK | Explicit `auth.*` rejection (D-14) | pytest-asyncio API | `pytest tests/integration/test_settings_import.py::test_auth_key_rejected -x` | ⬜ pending |
| 7-01-02 | SC2 | Idempotency: same Idempotency-Key replay → cached response, no dup history row | T-DOUBLE-COMMIT | `idempotency_keys` dedup (existing pattern, extend to wizard/import) | pytest-asyncio API | `pytest tests/integration/test_bulk.py::test_idempotency_replay -x` | ⬜ pending |
| 7-03-02 | SC2 | Failing row mid-import: ZERO partial state in DB | — | Single-transaction atomic commit (Pitfall 7) | pytest-asyncio API | `pytest tests/integration/test_import.py::test_atomicity -x` | ⬜ pending |
| 7-01-01 | D-04 | Migration 0007 round-trips upgrade→downgrade→upgrade clean | — | N/A | shell-invoked | `alembic upgrade head && alembic downgrade 0006 && alembic upgrade head` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

New test files this phase introduces (existing pytest/httpx/Hypothesis infra already present):

All 8 Wave-0 test files are scaffolded RED by Plan 07-01 Tasks 3a/3b (created before any
implementation; turned GREEN by Plans 02–05):

- [ ] `tests/integration/test_wizard.py` — ADMN-04, ADMN-10 (source labels, atomic commit, reshuffle source) — **created by 7-01-03a**
- [ ] `tests/integration/test_import.py` — ADMN-05 (CSV, YAML, phantom, contiguity, atomicity, partial-import) — **created by 7-01-03a**
- [ ] `tests/integration/test_export.py` — BAK-01 (YAML export, overrides included) — **created by 7-01-03b**
- [ ] `tests/integration/test_settings_import.py` — BAK-02 (unknown-key reject, auth-key reject) — **created by 7-01-03b**
- [ ] `tests/unit/test_settings_export.py` — D-14 hard exclusion (no `auth.pin_hash`) — **created by 7-01-03b**
- [ ] `tests/unit/test_reshuffle_draft.py` — D-05/D-06 reshuffle draft persistence/re-validate — **created by 7-01-03b**
- [ ] `tests/property/test_export_roundtrip.py` — SC4 Hypothesis round-trip identity (export → re-import → zero diff) — **created by 7-01-03b**
- [ ] `tests/property/test_import_roundtrip.py` — YAML import round-trip (distinct from export roundtrip) — **created by 7-01-03b**
- [ ] Synthetic boundary + `v_collection` fixtures in `tests/conftest.py` (4-cube and 32-cube sets; NO real collection data) — **created by 7-01-03a**

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| "Continue your reshuffle" banner appears on next admin login (SC3 discoverability) | ADMN-10 | Cross-session browser UI behavior; localStorage persistence across full reload | Start a reshuffle, confirm ≥1 step, hard-reload the admin page, log in → banner shows with progress + Continue/Discard |
| Wizard cut-point walk feels fast/linear on the kiosk-class device | ADMN-04 | Perceived-latency / UX judgement, not assertable | Walk a 32-cube fresh setup end-to-end; confirm each step is the RecordPickerSheet and advances without lag |
| Import diff preview mini-grid highlights affected cubes correctly | ADMN-05 | Visual diff rendering correctness | Upload a synthetic YAML changing 3 cubes; confirm exactly those 3 highlight with movement counts (labeled "approximate") |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (Task IDs attached in the Per-Task Verification Map)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (all 8 new test files + conftest fixtures accounted, created by 7-01-03a/03b)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter (per-task map filled; wave_0_complete: true)

**Approval:** approved 2026-05-24 (planner — revision 2: Task IDs filled, all 8 Wave-0 files accounted)

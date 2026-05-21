---
phase: 3
slug: admin-loop-pin-manual-entry-undo
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-20
updated: 2026-05-20
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 03-RESEARCH.md §Validation Architecture (Req→Test map) + the per-task
> `<automated>` blocks in 03-01..03-05 PLAN files.

---

## Test Infrastructure

### Backend (Python)

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio 1.3.0 + hypothesis 6.152.9 |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (exists) |
| **Quick run command** | `uv run pytest tests/unit/ -q --tb=short -x` |
| **Full suite command** | `uv run pytest tests/ -q --tb=short` |
| **Estimated runtime** | ~25 seconds (unit/property fast; integration hits the real test DB) |

### Frontend (TypeScript / React)

| Property | Value |
|----------|-------|
| **Framework** | vitest 4.1.6 (NOT jest) + @testing-library/react 16.x + jsdom |
| **Config file** | `frontend/vite.config.ts` (`test` block, `setupFiles: ./src/test-setup.ts`) |
| **Quick run command** | `cd frontend && npx vitest run` |
| **Type/build gate** | `cd frontend && npx tsc --noEmit && npm run build` |
| **Estimated runtime** | ~10 seconds (vitest run) + ~15s build |

---

## Sampling Rate

- **After every task commit:** Backend → `uv run pytest tests/unit/ -q --tb=short -x`; Frontend tasks → `cd frontend && npx tsc --noEmit && npx vitest run`
- **After every plan wave:** `uv run pytest tests/ -q --tb=short` AND `cd frontend && npx tsc --noEmit && npm run build && npx vitest run`
- **Before `/gsd:verify-work`:** Full backend suite green + frontend builds/type-checks/tests green
- **Max feedback latency:** 30 seconds (quick command)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | ADMN-09, OBS-03 | T-03-01 / T-03-02 | SESSION_SECRET has no default (crash-on-missing); migration round-trips; no f-string SQL | smoke/migration | `uv run python -c "import passlib.hash, slowapi" && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head && uv run ruff check src/gruvax/settings.py src/gruvax/app.py src/gruvax/db/queries.py && uv run mypy src/gruvax/settings.py src/gruvax/db/queries.py` | ✅ (this task) | ⬜ pending |
| 03-01-02 | 01 | 1 | ADMN-01, ADMN-02, ADMN-03, ADMN-06, ADMN-07, ADMN-08, ADMN-09, ADMN-12, CUBE-07, CUBE-09 | — | Full Wave-0 RED test scaffold collects without import errors | scaffold (collect) | `uv run pytest tests/unit/test_pin.py tests/unit/test_sessions.py tests/unit/test_boundary_validation.py tests/unit/test_diff_preview.py tests/unit/test_fill_level.py tests/unit/test_cube_contents.py tests/unit/test_midpoint.py tests/integration/test_admin_auth.py tests/integration/test_boundary_editor.py tests/integration/test_change_set.py tests/integration/test_cube_public.py tests/property/test_fill_level_property.py tests/property/test_midpoint_property.py tests/property/test_boundary_validation_property.py --collect-only -q` | ✅ (this task) | ⬜ pending |
| 03-01-03 | 01 | 1 | CUBE-07, CUBE-09, ADMN-12 | T-03-03 | Catalog compare via parse_key only; labels via casefold (never normalize_catalog); midpoint is a real owned record | unit + property | `uv run pytest tests/unit/test_fill_level.py tests/unit/test_cube_contents.py tests/unit/test_midpoint.py tests/property/test_fill_level_property.py tests/property/test_midpoint_property.py -q --tb=short && uv run ruff check src/gruvax/estimator/boundary_math.py && uv run mypy src/gruvax/estimator/boundary_math.py` | ✅ W0 (03-01-02) | ⬜ pending |
| 03-02-01 | 02 | 2 | ADMN-01, ADMN-02, ADMN-08 | T-03-04..09 | Argon2id verify (no `==`); rate-limit 5/5min → 429; CSRF double-submit; HttpOnly session cookie + readable CSRF cookie; PIN never logged; idle/hard-cap/Change-PIN revocation | unit + integration | `uv run pytest tests/unit/test_pin.py tests/unit/test_sessions.py tests/integration/test_admin_auth.py -q --tb=short` | ✅ W0 (03-01-02) | ⬜ pending |
| 03-02-02 | 02 | 2 | ADMN-01, ADMN-08 | T-03-05 | CSRF token echoed via X-CSRF-Token; no hardcoded hex; kiosk-safe keypad | type/build | `cd frontend && npx tsc --noEmit && npm run build` | n/a (frontend) | ⬜ pending |
| 03-02-CK | 02 | 2 | ADMN-01, ADMN-02, ADMN-08 | T-03-07 | (manual) end-to-end PIN login on mobile + kiosk | manual | see Manual-Only Verifications | n/a | ⬜ pending |
| 03-03-01 | 03 | 3 | CUBE-07, CUBE-09 | T-03-10..12 | Public endpoint (no require_admin) reads in-memory snapshot only; 404 for missing cube; typed Path params | integration | `uv run pytest tests/integration/test_cube_public.py -q --tb=short` | ✅ W0 (03-01-02) | ⬜ pending |
| 03-03-02 | 03 | 3 | CUBE-07, CUBE-09 | T-03-10 | Fill-bar color tokens (no hex); D-16 edit shortcut gated on isLoggedIn; types.ts/store.ts untouched | type/build + vitest | `cd frontend && npx tsc --noEmit && npm run build && npx vitest run` | ✅ (ShelfGrid.test.tsx) | ⬜ pending |
| 03-03-CK | 03 | 3 | CUBE-07, CUBE-09 | T-03-10 | (manual) fill bars + contents panel on touch | manual | see Manual-Only Verifications | n/a | ⬜ pending |
| 03-04-01 | 04 | 3 | ADMN-03, ADMN-06, ADMN-12 | T-03-13..17 | require_admin on every handler; first>last rejected via parse_key; phantom blocked + near-misses; force never bypasses comparator; midpoint real record; v_collection-only autocomplete; %s SQL | unit + integration + property | `uv run pytest tests/integration/test_boundary_editor.py tests/unit/test_boundary_validation.py tests/unit/test_midpoint.py tests/property/test_boundary_validation_property.py tests/property/test_midpoint_property.py -q --tb=short` | ✅ W0 (03-01-02) | ⬜ pending |
| 03-04-02 | 04 | 3 | ADMN-03, ADMN-06, ADMN-12, CUBE-07 | T-03-14 | Two-step autocomplete; force override path; editable midpoint (not auto-applied); editor only sets pendingChangeSet (no write); no hex | type/build | `cd frontend && npx tsc --noEmit && npm run build` | n/a (frontend) | ⬜ pending |
| 03-04-CK | 04 | 3 | ADMN-03, ADMN-06, ADMN-12 | T-03-14 | (manual) autocomplete, phantom blocking, midpoint | manual | see Manual-Only Verifications | n/a | ⬜ pending |
| 03-05-01 | 05 | 4 | ADMN-07, ADMN-09 | T-03-18..24 | Single-transaction atomic bulk; Idempotency-Key replay no double-write; cache invalidate+load AFTER commit (Pitfall A); conflict-aware revert (skip+report); revert is undoable; %s SQL | unit + integration | `uv run pytest tests/integration/test_change_set.py tests/unit/test_diff_preview.py -q --tb=short` | ✅ W0 (03-01-02) | ⬜ pending |
| 03-05-02 | 05 | 4 | ADMN-07, ADMN-09 | T-03-19/T-03-21 | Diff preview before/after + movement counts; commit clears pendingChangeSet; one-tap conflict-aware revert with banner; no hex | type/build | `cd frontend && npx tsc --noEmit && npm run build` | n/a (frontend) | ⬜ pending |
| 03-05-CK | 05 | 4 | ADMN-07, ADMN-09 | T-03-19/T-03-21/T-03-23 | (manual) diff preview, atomic commit, conflict-aware undo, idempotency | manual | see Manual-Only Verifications | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Requirement → test-function coverage (from 03-RESEARCH.md §Validation Architecture)

| Req ID | Test functions (all authored RED in 03-01-02) |
|--------|-----------------------------------------------|
| ADMN-01 | `test_admin_auth.py::{test_login_success,test_rate_limit,test_csrf_missing,test_cookie_flags,test_csrf_cookie_readable}`, `test_pin.py::test_verify_wrong_pin` |
| ADMN-02 | `test_sessions.py::{test_hard_cap_expired,test_idle_expired}`, `test_admin_auth.py::test_change_pin_revokes_sessions` |
| ADMN-03 | `test_boundary_validation.py::test_first_gt_last`, `test_boundary_editor.py::{test_phantom_blocked,test_phantom_force_save}` |
| ADMN-06 | `test_boundary_editor.py::test_near_misses_returned` |
| ADMN-07 | `test_boundary_editor.py::test_validate_no_db_write`, `test_diff_preview.py::test_movement_counts` |
| ADMN-08 | `test_admin_auth.py::test_logout` |
| ADMN-09 | `test_change_set.py::{test_bulk_writes_history,test_idempotency_key_replay,test_revert_writes_inverse,test_revert_conflict_skip,test_revert_is_undoable}` |
| ADMN-12 | `test_midpoint.py::{test_midpoint_is_real_record,test_midpoint_empty_range}`, `test_midpoint_property.py` |
| CUBE-07 | `test_fill_level.py::{test_empty_cube,test_overstuffed}`, `test_fill_level_property.py` |
| CUBE-09 | `test_cube_public.py::{test_cube_not_found,test_cube_contents_shape}`, `test_cube_contents.py::{test_sample_subset,test_sample_size}` |

**Property-based invariants (Hypothesis):**
- `test_fill_level_property.py`: `count_records_in_boundary >= 0` for any valid boundary; monotone in capacity; label range check uses `.casefold()` not `normalize_catalog()`.
- `test_midpoint_property.py`: midpoint suggestion (when returned) is an element of `snapshot.get_label_records(label)`; its index is strictly between the two anchor indices.
- `test_boundary_validation_property.py`: any boundary where `parse_key(first_catalog) > parse_key(last_catalog)` is rejected; any boundary where `first_label.casefold() > last_label.casefold()` is rejected.

---

## Wave 0 Requirements

Wave-0 scaffold is authored in **03-01 Task 2** (test files + `admin_session` fixture, all RED) and the boundary-math helpers it targets are implemented in **03-01 Task 3** (those helper tests go GREEN within Plan 01). All other RED tests go GREEN as plans 02-05 land.

Checked boxes below = satisfied by Plan 01 (created in 03-01-02; helper tests turned GREEN in 03-01-03). Unchecked = the file exists after 03-01-02 but its assertions stay RED until the implementing plan lands.

- [x] `tests/unit/test_pin.py` — created (RED until 03-02)
- [x] `tests/unit/test_sessions.py` — created (RED until 03-02)
- [x] `tests/unit/test_boundary_validation.py` — created (RED until 03-04)
- [x] `tests/unit/test_diff_preview.py` — created (RED until 03-05)
- [x] `tests/unit/test_fill_level.py` — created + GREEN in 03-01-03
- [x] `tests/unit/test_cube_contents.py` — created + GREEN in 03-01-03
- [x] `tests/unit/test_midpoint.py` — created + GREEN in 03-01-03
- [x] `tests/integration/test_admin_auth.py` — created (RED until 03-02)
- [x] `tests/integration/test_boundary_editor.py` — created (RED until 03-04)
- [x] `tests/integration/test_change_set.py` — created (RED until 03-05)
- [x] `tests/integration/test_cube_public.py` — created (RED until 03-03)
- [x] `tests/property/test_fill_level_property.py` — created + GREEN in 03-01-03
- [x] `tests/property/test_midpoint_property.py` — created + GREEN in 03-01-03
- [x] `tests/property/test_boundary_validation_property.py` — created (RED until 03-04)
- [x] `tests/conftest.py` — `admin_session` fixture + test PIN seeding added (03-01-02)
- [x] Install: `passlib[argon2]` + `slowapi` + `--dev types-passlib` (03-01-01)

`wave_0_complete` flips to `true` once 03-01 executes and these files exist on disk (collect-only is green). It is still `false` here because Plan 01 has not yet run.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| PIN login end-to-end on mobile + kiosk (in-app keypad, no system keyboard); countdown/Lock/Logout; Change-PIN revokes other tabs | ADMN-01, ADMN-02, ADMN-08 | Visual/touch + cross-device; system-keyboard suppression on kiosk cannot be asserted in headless tests | 03-02 checkpoint `how-to-verify` steps 1-7 |
| Kiosk fill bars (color thresholds) + contents bottom-sheet on real touch hardware | CUBE-07, CUBE-09 | Visual color/threshold judgement + Pi 5 + 7" touch feel | 03-03 checkpoint `how-to-verify` steps 1-6 |
| Boundary-editor autocomplete, phantom blocking, A–Z rail, editable midpoint on kiosk viewport | ADMN-03, ADMN-06, ADMN-12 | Interactive autocomplete + kiosk no-keyboard verification | 03-04 checkpoint `how-to-verify` steps 1-6 |
| Diff preview, atomic commit, conflict-aware undo, double-tap idempotency | ADMN-07, ADMN-09 | Multi-step stateful flow + visual mini-grid + flaky-network simulation | 03-05 checkpoint `how-to-verify` steps 1-6 |

Each manual checkpoint is backed by automated tests (the integration suites above); the checkpoint confirms the visual/touch/cross-device behavior the headless suite cannot assert.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (every code task maps to a command above; checkpoints are backed by automated suites)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (each plan's code tasks both carry automated commands)
- [x] Wave 0 covers all MISSING references (every `<automated>` test name in plans 02-05 is created in 03-01-02)
- [x] No watch-mode flags (`vitest run`, not `vitest`; no `--watch`)
- [x] Feedback latency < 30s (quick command)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-20
</content>

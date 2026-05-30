---
phase: 4
slug: sync-polish-diagnostics
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-29
validated: 2026-05-29
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `04-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + Hypothesis (backend); Vitest (frontend) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/unit/ tests/property/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q --tb=short` |
| **Estimated runtime** | ~60–90 seconds (full); ~10s (quick) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ tests/property/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q --tb=short`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Filled by the planner per task. Seeded from RESEARCH §"Phase Requirements → Test Map".

| Req ID | Behavior | Test Type | Automated Command | Status |
|--------|----------|-----------|-------------------|--------|
| SYN-01 | `next_fire_after()` always future | property (Hypothesis) | `uv run pytest tests/property/test_nightly_scheduler.py::test_next_fire_always_future -x -q` | ✅ |
| SYN-01 | `next_fire_after()` interval in 22–26h window (monotonic across DST) | property (Hypothesis) | `uv run pytest tests/property/test_nightly_scheduler.py::test_next_fire_interval_in_22_26h_window -x -q` | ✅ |
| SYN-01 | Cadence fire-time anchoring (24h→3; 12h→3+15; 6h→3+9+15+21) | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_cadence_anchoring -x -q` | ✅ |
| SYN-01 | Skip policy: revoked + in_progress profiles excluded | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_skip_policy -x -q` | ✅ |
| SYN-01 | `off` cadence: loop parks without syncing | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_cadence_off -x -q` | ✅ |
| SYN-01 | Startup catch-up sweep syncs stale profiles (off-skip + per-profile isolation) | unit | `uv run pytest "tests/unit/test_nightly_scheduler.py::test_startup_catchup_sweep_syncs_stale_profiles" -x -q` | ✅ |
| SYN-01 | `sync.cadence` persists across settings PUT | integration | `uv run pytest tests/integration/api/test_admin_settings.py::test_sync_cadence -x -q` | ✅ |
| SYN-02 | `app_token_revoked=TRUE` resets on rotate + full sync | integration | `uv run pytest tests/integration/sync/test_purge.py::test_rotate_clears_revoked -x -q` | ✅ |
| SYN-02 | `GET /api/session` / store exposes `needs_reauth` correctly | unit | `uv run pytest tests/unit/test_session.py -k needs_reauth -x -q` | ✅ |
| SYN-02 | `GET /api/admin/diagnostics` includes `profiles[]` | integration | `uv run pytest tests/integration/api/test_diagnostics.py::test_profiles_section -x -q` | ✅ |
| SYN-02 | Soft-delete purge sweep predicate is self-clearing | integration | `uv run pytest tests/integration/sync/test_purge.py::test_purge_clears_profile_collection -x -q` | ✅ |
| SYN-02 | Purge does NOT touch change_log / change_sets (audit lineage) | integration | `uv run pytest tests/integration/sync/test_purge.py::test_purge_audit_lineage_untouched -x -q` | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> **Path corrections (2026-05-29 audit):** During execution `test_rotate_clears_revoked` landed in `tests/integration/sync/test_purge.py` (not `test_admin_profiles.py`) per the Plan 04-00 decision to co-locate it with the purge state-machine tests. The startup catch-up sweep is verified by **unit** tests in `tests/unit/test_nightly_scheduler.py` (fake-pool + mocked `sync_profile`), not the originally-planned `tests/integration/sync/test_nightly_scheduler.py`.

---

## Wave 0 Requirements

- [x] `tests/property/test_nightly_scheduler.py` — Hypothesis invariants for `next_fire_after()` (always-future, 22–26h window, monotonic). Precedent: `test_parser_props.py`, `test_estimator_props.py`, `test_led_brightness.py`.
- [x] `tests/unit/test_nightly_scheduler.py` — cadence anchoring, skip policy, `off` parking, `_read_sync_cadence` fallback, **startup catch-up sweep** (added in 2026-05-29 audit)
- [x] `tests/unit/test_session.py::test_needs_reauth*` — `needs_reauth` derivation
- [x] `tests/integration/sync/test_purge.py` — purge predicate self-clearing, audit lineage untouched, rotate-clears-revoked
- [x] `tests/integration/api/test_diagnostics.py::test_profiles_section` — per-profile section present + correct shape
- [x] `tests/integration/api/test_admin_settings.py::test_sync_cadence` — cadence persistence

*Existing pytest + Hypothesis + pytest-asyncio infrastructure covers the framework; only new test files above are needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Kiosk re-auth inline banner renders + is non-blocking (search still works) | SYN-02 | Visual/UX assertion in Chromium kiosk; cube-search must stay live off cached collection | Revoke a bound profile's PAT, trigger sync, load kiosk → banner shows, type a search → cube still highlights |
| Diagnostics cards use Nordic Grid typography + Sync-now spinner→toast | SYN-02 | Visual fidelity against UI-SPEC; automated DOM tests don't assert design-language conformance | Open `/admin/diagnostics`, confirm per-profile cards match `04-UI-SPEC.md`; click Sync now → spinner until terminal → completion toast |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-05-29 — 12/12 requirements automated, full suite green (703 tests, exit 0).

---

## Validation Audit 2026-05-29

| Metric | Count |
|--------|-------|
| Requirements audited | 12 |
| COVERED at audit start | 11 |
| Gaps found (MISSING) | 1 |
| Resolved | 1 |
| Escalated | 0 |
| Path-reference corrections | 2 |

**Gap closed:** SYN-01 startup catch-up sweep (`_startup_catchup_sweep`) had no test. Filled by 4 unit tests in `tests/unit/test_nightly_scheduler.py` (`test_startup_catchup_sweep_syncs_stale_profiles`, `_cadence_off_skips_all`, `_revoked_profile_excluded`, `_per_profile_isolation`) — fake-pool + mocked `sync_profile`, mirroring `test_skip_policy`.

**Path corrections:** Two Per-Task Map rows pointed at planned-but-unused paths; the tests shipped under different files during execution (see Per-Task Map note). No coverage was actually missing for those two — only the map references were stale.

**Result:** Phase 4 is Nyquist-compliant. All 12 requirements have automated verification.

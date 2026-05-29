---
phase: 4
slug: sync-polish-diagnostics
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-29
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

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| SYN-01 | `next_fire_after()` always future, 22–26h window | property (Hypothesis) | `uv run pytest tests/property/test_nightly_scheduler.py -x -q` | ❌ W0 |
| SYN-01 | `next_fire_after()` monotonic over DST transitions | property (Hypothesis) | same file | ❌ W0 |
| SYN-01 | Cadence fire-time anchoring (24h→3; 12h→3+15; 6h→3+9+15+21) | unit | `uv run pytest tests/unit/test_nightly_scheduler.py -x -q` | ❌ W0 |
| SYN-01 | Skip policy: revoked + in_progress profiles excluded | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_skip_policy -x -q` | ❌ W0 |
| SYN-01 | `off` cadence: loop parks without syncing | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_cadence_off -x -q` | ❌ W0 |
| SYN-01 | Startup catch-up sweep syncs stale profiles | integration | `uv run pytest tests/integration/sync/test_nightly_scheduler.py -x -q` | ❌ W0 |
| SYN-01 | `sync.cadence` persists across settings PUT | integration | `uv run pytest tests/integration/api/test_admin_settings.py::test_sync_cadence -x -q` | ❌ W0 |
| SYN-02 | `app_token_revoked=TRUE` resets on rotate + full sync | integration | `uv run pytest tests/integration/api/test_admin_profiles.py::test_rotate_clears_revoked -x -q` | ❌ W0 |
| SYN-02 | `GET /api/session` / store exposes `needs_reauth` correctly | unit | `uv run pytest tests/unit/test_session.py::test_needs_reauth -x -q` | ❌ W0 |
| SYN-02 | `GET /api/admin/diagnostics` includes `profiles[]` | integration | `uv run pytest tests/integration/api/test_diagnostics.py::test_profiles_section -x -q` | ❌ W0 |
| SYN-02 | Soft-delete purge sweep predicate is self-clearing | integration | `uv run pytest tests/integration/sync/test_purge.py -x -q` | ❌ W0 |
| SYN-02 | Purge does NOT touch change_log / change_sets | integration | same file | ❌ W0 |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/property/test_nightly_scheduler.py` — Hypothesis invariants for `next_fire_after()` (always-future, 22–26h window, monotonic). Precedent: `test_parser_props.py`, `test_estimator_props.py`, `test_led_brightness.py`.
- [ ] `tests/unit/test_nightly_scheduler.py` — cadence anchoring, skip policy, `off` parking, `_read_sync_cadence` fallback
- [ ] `tests/unit/test_session.py::test_needs_reauth*` — `needs_reauth` derivation
- [ ] `tests/integration/sync/test_purge.py` — purge predicate self-clearing, audit lineage untouched
- [ ] `tests/integration/api/test_diagnostics.py::test_profiles_section` — per-profile section present + correct shape
- [ ] `tests/integration/api/test_admin_settings.py::test_sync_cadence` — cadence persistence

*Existing pytest + Hypothesis + pytest-asyncio infrastructure covers the framework; only new test files above are needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Kiosk re-auth inline banner renders + is non-blocking (search still works) | SYN-02 | Visual/UX assertion in Chromium kiosk; cube-search must stay live off cached collection | Revoke a bound profile's PAT, trigger sync, load kiosk → banner shows, type a search → cube still highlights |
| Diagnostics cards use Nordic Grid typography + Sync-now spinner→toast | SYN-02 | Visual fidelity against UI-SPEC; automated DOM tests don't assert design-language conformance | Open `/admin/diagnostics`, confirm per-profile cards match `04-UI-SPEC.md`; click Sync now → spinner until terminal → completion toast |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

---
phase: 10
slug: close-milestone-gaps
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-25
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `10-RESEARCH.md` → "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-asyncio (session loop) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/integration/test_segment_api.py tests/integration/test_change_set.py -x` |
| **Full suite command** | `uv run pytest tests/` |
| **Estimated runtime** | ~quick <30s · full suite per existing baseline |

Shared-state note: integration suite runs against a **shared dev Postgres** (no isolated test DB); the app caches boundaries at startup. The `_reset_login_rate_limit_global` autouse fixture in `tests/conftest.py` resets the global login rate limiter. New INT-B tests that mutate boundaries MUST restore fixture state at teardown (or operate on cubes no other test references) — `test_change_set.py` does NOT re-seed boundaries the way `test_segment_api.py` does.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/integration/test_segment_api.py tests/integration/test_change_set.py -x`
- **After every plan wave:** Run `uv run pytest tests/`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30s (quick) / full suite per baseline

---

## Per-Task Verification Map

> Populated after planning assigns task IDs. Each fix task below maps to the
> integration tests in "Wave 0 Requirements". Behavior coverage:

| Behavior | Requirement | Threat Ref | Test Type | Automated Command | File Exists | Status |
|----------|-------------|------------|-----------|-------------------|-------------|--------|
| `PUT /cut` emits `cube_ids`/`unit` payload (no `type` key) | SEG-07/SEG-08, RTM-01, ADMN-11 | — | integration | `pytest tests/integration/test_segment_api.py::test_cut_publishes_correct_payload -x` | ❌ W0 | ⬜ pending |
| `POST /overrides` emits `cube_ids`/`unit` payload | SEG-08, RTM-01 | — | integration | `pytest tests/integration/test_segment_api.py::test_overrides_publishes_correct_payload -x` | ❌ W0 | ⬜ pending |
| `POST /insert-cut` emits `cube_ids`/`unit` payload | SEG-07/SEG-08, RTM-01 | — | integration | `pytest tests/integration/test_segment_api.py::test_insert_cut_publishes_correct_payload -x` | ❌ W0 | ⬜ pending |
| Revert re-derives SegmentCache → `/api/locate` fresh positions | ADMN-09, RTM-01 | — | integration | `pytest tests/integration/test_change_set.py::test_revert_rederives_segment_cache -x` | ❌ W0 | ⬜ pending |
| Revert publishes `boundary_changed` with reverted cubes | RTM-01, ADMN-11, SEG-07 | — | integration | `pytest tests/integration/test_change_set.py::test_revert_publishes_boundary_changed -x` | ❌ W0 | ⬜ pending |
| Malformed SSE payload degrades gracefully (no uncaught TypeError) | IN-02 hardening | — | manual (frontend) | browser inspection — no Vitest SSE infra | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

These integration test functions do not yet exist and must be created before/alongside the fixes:

- [ ] `tests/integration/test_segment_api.py::test_cut_publishes_correct_payload` — INT-A / SEG-07/SEG-08 for `PUT /cut`
- [ ] `tests/integration/test_segment_api.py::test_overrides_publishes_correct_payload` — INT-A for `POST /overrides`
- [ ] `tests/integration/test_segment_api.py::test_insert_cut_publishes_correct_payload` — INT-A / SEG-07/SEG-08 for `POST /insert-cut`
- [ ] `tests/integration/test_change_set.py::test_revert_rederives_segment_cache` — INT-B / ADMN-09
- [ ] `tests/integration/test_change_set.py::test_revert_publishes_boundary_changed` — INT-B / RTM-01

Recommended capture mechanism: a `SpyEventBus` (records `publish(event, payload)` calls) wired via `dependency_overrides[get_event_bus]` — avoids live-uvicorn complexity for payload-contract assertions. Existing `tests/integration/test_sse.py` live-uvicorn pattern is the fallback if an end-to-end SSE stream assertion is preferred.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KioskView `boundary_changed` / `admin_editing` try/catch hardening degrades gracefully | IN-02 | No Vitest SSE-parsing harness exists in this project | In browser kiosk dev tools, inject a malformed `boundary_changed` frame; confirm `console.error` logs and the page does not crash / subsequent events still process |
| Highlight-follows-record + shimmer-clear after a real segment edit | D-05/D-06, SEG-07/08 | End-to-end visual behavior on live kiosk | Perform a cut/override/insert-cut in admin; confirm kiosk active-selection highlight relocates and editing shimmer clears on commit (not via 60s TTL sweep) |

---

## Validation Sign-Off

- [ ] All fix tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (5 integration tests above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (quick)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

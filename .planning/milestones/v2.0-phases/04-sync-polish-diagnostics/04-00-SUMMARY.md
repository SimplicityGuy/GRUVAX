---
phase: 04-sync-polish-diagnostics
plan: "00"
subsystem: test-scaffolding
tags: [tdd, wave-0, red, scheduler, purge, diagnostics, session, cadence]
dependency_graph:
  requires: []
  provides:
    - tests/property/test_nightly_scheduler.py
    - tests/unit/test_nightly_scheduler.py
    - tests/unit/test_session.py
    - tests/integration/sync/test_purge.py
    - tests/integration/api/test_diagnostics.py
    - tests/integration/api/test_admin_settings.py
  affects:
    - tests/property/
    - tests/unit/
    - tests/integration/sync/
    - tests/integration/api/
tech_stack:
  added: []
  patterns:
    - Hypothesis @given/@settings property tests (analog: test_estimator_props.py)
    - AsyncMock + fake pool unit tests (analog: test_admin_led_settings.py)
    - LifespanManager + dependency_overrides integration tests (analog: test_diagnostics.py)
    - Parameterized %s SQL in test assertions (no f-strings — bandit B608)
key_files:
  created:
    - tests/property/test_nightly_scheduler.py
    - tests/unit/test_nightly_scheduler.py
    - tests/unit/test_session.py
    - tests/integration/sync/test_purge.py
    - tests/integration/api/test_diagnostics.py
    - tests/integration/api/test_admin_settings.py
  modified: []
decisions:
  - test_nightly_scheduler.py property tests use top-level import (module-level RED); unit tests use in-function import (function-level RED) — allows 14 unit tests to collect even without gruvax.sync.nightly
  - _count_audit_rows uses per-table literal SQL strings (dict of literal queries) instead of an f-string loop to satisfy semgrep SQL-injection scan (B608 pattern)
  - test_rotate_clears_revoked placed in test_purge.py (not test_admin_profiles.py) as it exercises the purge/revoked state machine alongside the purge tests
  - test_needs_reauth aliased at module level so pytest node ID test_needs_reauth matches 04-VALIDATION.md reference
metrics:
  duration: "~9 minutes"
  completed: "2026-05-29"
  tasks_completed: 3
  tasks_total: 3
  files_created: 6
  files_modified: 0
---

# Phase 04 Plan 00: Wave 0 RED Test Scaffolding Summary

Six RED test files providing Nyquist-compliant coverage for all Phase 4 behaviors (SYN-01/SYN-02). Every subsequent plan in Phase 4 has an automated verify that fails until production code lands.

## Tasks Completed

| Task | Name | Commit | Files Created |
|------|------|--------|--------------|
| 1 | Scheduler property + unit RED tests (SYN-01) | 6fded36 | tests/property/test_nightly_scheduler.py, tests/unit/test_nightly_scheduler.py |
| 2 | Session + diagnostics + cadence-persistence RED tests (SYN-01/SYN-02) | 2d49032 | tests/unit/test_session.py, tests/integration/api/test_diagnostics.py, tests/integration/api/test_admin_settings.py |
| 3 | Purge + rotate-clears-revoked RED tests (SYN-02) | 70464c2 | tests/integration/sync/test_purge.py |

## Collection State

| File | Tests Collected | RED State |
|------|----------------|-----------|
| tests/property/test_nightly_scheduler.py | 2 (collection ERROR — import fails) | ModuleNotFoundError: gruvax.sync.nightly |
| tests/unit/test_nightly_scheduler.py | 14 | FAILED — ModuleNotFoundError at test body |
| tests/unit/test_session.py | 3 | FAILED — needs_reauth missing from response |
| tests/integration/sync/test_purge.py | 3 | FAILED — ModuleNotFoundError: gruvax.sync.nightly |
| tests/integration/api/test_diagnostics.py | 1 | FAILED — profiles key absent from diagnostics |
| tests/integration/api/test_admin_settings.py | 2 | FAILED — sync_cadence not in settings |

**Total: 23 tests defined, all RED.**

## Test Coverage Map

| Req ID | Test | File |
|--------|------|------|
| SYN-01 | test_next_fire_always_future | tests/property/test_nightly_scheduler.py |
| SYN-01 | test_next_fire_interval_in_22_26h_window | tests/property/test_nightly_scheduler.py |
| SYN-01 | test_cadence_anchoring[24h/12h/6h × N] (11 parametrized) | tests/unit/test_nightly_scheduler.py |
| SYN-01 | test_skip_policy | tests/unit/test_nightly_scheduler.py |
| SYN-01 | test_cadence_off | tests/unit/test_nightly_scheduler.py |
| SYN-01 | test_read_sync_cadence_fallback | tests/unit/test_nightly_scheduler.py |
| SYN-01 | test_sync_cadence | tests/integration/api/test_admin_settings.py |
| SYN-01 | test_sync_cadence_invalid_value | tests/integration/api/test_admin_settings.py |
| SYN-02 | test_needs_reauth_true_when_token_revoked | tests/unit/test_session.py |
| SYN-02 | test_needs_reauth_false_when_token_valid | tests/unit/test_session.py |
| SYN-02 | test_profiles_section | tests/integration/api/test_diagnostics.py |
| SYN-02 | test_purge_clears_profile_collection | tests/integration/sync/test_purge.py |
| SYN-02 | test_purge_audit_lineage_untouched | tests/integration/sync/test_purge.py |
| SYN-02 | test_rotate_clears_revoked | tests/integration/sync/test_purge.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Security] Replaced f-string SQL with per-table literal queries**
- **Found during:** Task 3 (test_purge.py)
- **Issue:** `_count_audit_rows` used an f-string to inject table names into SQL: `f"SELECT COUNT(*) FROM gruvax.{table} WHERE ..."` — triggered semgrep SQL injection scan (CWE-89)
- **Fix:** Replaced the loop with a `_QUERIES` dict of fully-literal SQL strings, one per table, satisfying the scanner without changing test logic
- **Files modified:** tests/integration/sync/test_purge.py
- **Commit:** 70464c2

## Known Stubs

None. This plan creates test files only — no production code, no data stubs.

## Threat Flags

None. Test-only files; no new network endpoints, auth paths, or schema changes.

## Self-Check: PASSED

Files exist:
- tests/property/test_nightly_scheduler.py — FOUND
- tests/unit/test_nightly_scheduler.py — FOUND
- tests/unit/test_session.py — FOUND
- tests/integration/sync/test_purge.py — FOUND
- tests/integration/api/test_diagnostics.py — FOUND
- tests/integration/api/test_admin_settings.py — FOUND

Commits exist:
- 6fded36 — FOUND (test(04-00): RED scheduler property + unit tests)
- 2d49032 — FOUND (test(04-00): RED session/diagnostics/cadence tests)
- 70464c2 — FOUND (test(04-00): RED purge + rotate-clears-revoked tests)

Acceptance criteria:
- `next_fire_after` in property test — CONFIRMED
- `@settings(max_examples=500)` decorator — CONFIRMED
- `grep -c "def test_skip_policy|def test_cadence_off" ...` returns 2 — CONFIRMED
- `grep -c "needs_reauth" test_session.py` >= 1 — CONFIRMED (26)
- `grep -c "profiles" test_diagnostics.py` >= 1 — CONFIRMED (24)
- `grep -c "invalid_cadence|sync_cadence" test_admin_settings.py` >= 1 — CONFIRMED (21)
- `grep -c "change_log|change_sets|profile_collection" test_purge.py` >= 1 — CONFIRMED (36)
- All tests RED (non-zero exit) — CONFIRMED
- uv.lock unchanged — CONFIRMED

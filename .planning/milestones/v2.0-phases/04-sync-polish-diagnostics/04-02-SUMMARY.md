---
phase: 04-sync-polish-diagnostics
plan: 02
subsystem: backend-api
tags: [diagnostics, profiles, admin, api]
dependency_graph:
  requires: ["04-00"]
  provides: ["profiles[] section on GET /api/admin/diagnostics"]
  affects: ["04-03 (frontend diagnostics cards consume profiles[])"]
tech_stack:
  added: []
  patterns: ["parameterized %s SQL (bandit B608)", "async psycopg cursor + list comprehension", "require_admin guard re-used"]
key_files:
  modified:
    - src/gruvax/api/admin/diagnostics.py
decisions:
  - "Plain literal SQL string (no params needed for this query); %s parameterization applies when WHERE clause takes user input — not applicable here since there are no runtime parameters"
  - "Followed PATTERNS.md exact excerpt verbatim: query + dict comprehension before return dict"
  - "last_sync_at rendered via .isoformat() if row[2] else None (timezone-aware datetime from psycopg returns with tzinfo)"
  - "app_token_revoked cast via bool() to guarantee Python bool not psycopg bitstring"
metrics:
  duration_minutes: 8
  completed: "2026-05-29"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 1
---

# Phase 4 Plan 2: Per-Profile Diagnostics Section Summary

Per-profile sync metadata in `GET /api/admin/diagnostics` via a `profiles[]` array carrying 7 fields per non-deleted profile (D4-15), making `test_profiles_section` GREEN.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | profiles[] section on GET /api/admin/diagnostics | 9948e1b | src/gruvax/api/admin/diagnostics.py |

## What Was Built

Extended `get_diagnostics()` in `src/gruvax/api/admin/diagnostics.py` with a new DB query block that:

1. Queries `gruvax.profiles` for all non-deleted profiles ordered by `created_at`
2. Selects 7 columns: `id::text`, `display_name`, `last_sync_at`, `last_sync_status`, `last_sync_item_count`, `last_sync_error`, `app_token_revoked`
3. Builds a `profile_diagnostics` list of dicts with the 7 required fields
4. Appends `"profiles": profile_diagnostics` to the existing return dict

The existing 7 diagnostic keys (`sync_age_seconds`, `top_searched`, `slow_queries`, `mqtt`, `pool`, `phantom_boundary_count`, `recent_logs`) are unchanged.

## Verification Results

- `uv run pytest tests/integration/api/test_diagnostics.py::test_profiles_section -x -q`: **PASSED** (GREEN)
- `uv run pytest tests/integration/test_diagnostics.py -x -q`: **PASSED** (8 tests, no regression)
- `uv run ruff check src/gruvax/api/admin/diagnostics.py`: **CLEAN**
- `uv run mypy --strict src/gruvax/api/admin/diagnostics.py`: **CLEAN** (no issues)
- f-string SQL check (`grep -c 'f"SELECT'`): **0** (bandit B608 compliant)

## Deviations from Plan

None — plan executed exactly as written. The PATTERNS.md excerpt was followed verbatim.

## Known Stubs

None — the `profiles[]` data is live DB data from `gruvax.profiles`.

## Threat Flags

None — the new query reads `gruvax.profiles` behind the existing `require_admin` guard. No new trust boundary introduced. Payload contains only sync status/timestamps/counts/error-tags (no PATs, secrets, or raw credentials).

## Self-Check: PASSED

- `src/gruvax/api/admin/diagnostics.py` modified: EXISTS
- Commit `9948e1b` exists in git log: CONFIRMED

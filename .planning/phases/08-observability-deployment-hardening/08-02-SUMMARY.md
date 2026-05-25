---
phase: 08-observability-deployment-hardening
plan: "02"
subsystem: database
tags: [observability, counters, migration, tdd, privacy]
dependency_graph:
  requires: [08-01]
  provides: [gruvax.record_stats, increment_search_count, increment_selection_count, get_top_searched, get_sync_staleness_seconds, get_phantom_boundary_count, reset_record_stats]
  affects: [08-03, 08-04]
tech_stack:
  added: []
  patterns: [psycopg-upsert-on-conflict, rolling-7d-bucket, information_schema-privacy-gate]
key_files:
  created:
    - migrations/versions/0008_record_stats.py
    - tests/unit/test_stats.py
  modified:
    - src/gruvax/db/queries.py
decisions:
  - "increment_search_count / increment_selection_count take pool + int release_id only — no query text parameter exists (OBS-07, T-08-05)"
  - "Rolling 7-day bucket via CASE WHEN last_searched_at > now() - INTERVAL '7 days' THEN count+1 ELSE 1 END in the ON CONFLICT DO UPDATE clause"
  - "reset_record_stats uses TRUNCATE (not DELETE) — fastest for full-table clear, no WHERE clause needed"
  - "get_top_searched joins record_stats to v_collection so orphaned release_ids (not in collection) are excluded from results"
  - "Alembic downgrade base trips a pre-existing T-07-02 accepted risk (boundary_history CHECK constraint vs wizard/reshuffle rows) — not regressions from 0008"
metrics:
  duration: "~6 minutes"
  completed: "2026-05-25"
  tasks: 2
  files: 3
---

# Phase 8 Plan 02: Record Stats Counters + Query Functions Summary

Durable privacy-preserving search/selection counter substrate: migration 0008 creating the `gruvax.record_stats` table and six async query functions consumed by the search/locate hooks (Plan 03) and diagnostics endpoint (Plan 04).

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Migration 0008 — gruvax.record_stats table | a45358d | migrations/versions/0008_record_stats.py |
| 2 | Counter + staleness + phantom + top-N query functions (TDD) | RED: 41d5752 / GREEN: 4a38375 | src/gruvax/db/queries.py, tests/unit/test_stats.py |

## What Was Built

**Migration 0008** (`migrations/versions/0008_record_stats.py`): Creates `gruvax.record_stats` with eight columns — `release_id BIGINT PRIMARY KEY`, `search_count`, `search_count_7d`, `selection_count`, `selection_count_7d` (all `BIGINT NOT NULL DEFAULT 0`), `last_searched_at`, `last_selected_at` (`TIMESTAMPTZ`), `updated_at` (`TIMESTAMPTZ NOT NULL DEFAULT now()`). Creates `ix_record_stats_search_count ON gruvax.record_stats (search_count DESC)`. Downgrade drops both. No `query`, `term`, or `text` column exists — privacy gate enforced by docstring and test.

**Six query functions** (`src/gruvax/db/queries.py`):

1. `get_sync_staleness_seconds(pool)` — `EXTRACT(EPOCH FROM now() - max(synced_at)) FROM gruvax.v_collection`; returns `float | None` (None when view is empty).
2. `increment_search_count(pool, release_id)` — INSERT … ON CONFLICT DO UPDATE upsert; rolling 7-day bucket via CASE WHEN on `last_searched_at`.
3. `increment_selection_count(pool, release_id)` — same upsert shape for the selection path.
4. `get_top_searched(pool, limit=10)` — JOIN to `v_collection` for display fields, ORDER BY `search_count DESC LIMIT %s`.
5. `get_phantom_boundary_count(pool)` — NOT EXISTS subquery counting non-empty boundaries absent from `v_collection`.
6. `reset_record_stats(pool)` — TRUNCATE `gruvax.record_stats`.

**Test suite** (`tests/unit/test_stats.py`): 15 tests covering all six functions, privacy assertion via `information_schema.columns`, 7-day bucket reset after 8-day-old `last_searched_at`, ordering assertion, and empty-list-after-reset.

## Verification Results

- `uv run alembic upgrade head` → `0008`: PASS
- `uv run alembic heads` → single head `0008`: PASS
- `gruvax.record_stats` exists with correct 8-column schema: PASS (verified via `information_schema.columns`)
- No query-text column in migration or table: PASS
- `uv run pytest tests/unit/test_stats.py` → 15 passed: PASS
- `uv run mypy --strict src/gruvax/db/queries.py` → no issues: PASS
- `uv run ruff check tests/unit/test_stats.py` → clean: PASS

## Deviations from Plan

**1. [Pre-existing — not a regression] Alembic downgrade base trips at migration 0007**

- **Found during:** Task 1 verification
- **Issue:** `uv run alembic downgrade base` fails at 0007 downgrade because the `boundary_history_source_check` constraint cannot be restored to the Phase 5 set (`manual, bulk, revert, cut_insert`) when the table already has rows with `wizard/reshuffle/csv/yaml` source values.
- **Classification:** Pre-existing T-07-02 accepted risk documented in migration 0007's docstring. Not introduced by 0008.
- **Fix:** No fix applied — this is expected dev/CI behavior per the migration's documented risk. Migration 0008 round-trips clean at the 0007→0008 level. `upgrade head` from current state works correctly.

None - plan executed exactly as written for 0008's own scope.

## Known Stubs

None. The six query functions are fully implemented and tested against the live dev DB. No hardcoded empty values or placeholder text in any returned data.

## Threat Flags

No new security-relevant surface beyond what the plan's threat model covers:

| Threat ID | Status |
|-----------|--------|
| T-08-05 (Information Disclosure — query text in schema) | Mitigated: no query/term/text column; test asserts via information_schema |
| T-08-06 (SQL Injection — new query functions) | Mitigated: all six functions use %s placeholders exclusively |
| T-08-07 (Discogsography data access) | Mitigated: all reads via gruvax.v_collection only |
| T-08-08 (Package installs) | N/A: no new packages added |

## Self-Check

Files created/modified:

- [x] `/Users/Robert/Code/public/GRUVAX/.claude/worktrees/agent-a8fe00b917b2b8a5e/migrations/versions/0008_record_stats.py` — EXISTS
- [x] `/Users/Robert/Code/public/GRUVAX/.claude/worktrees/agent-a8fe00b917b2b8a5e/src/gruvax/db/queries.py` — EXISTS (modified)
- [x] `/Users/Robert/Code/public/GRUVAX/.claude/worktrees/agent-a8fe00b917b2b8a5e/tests/unit/test_stats.py` — EXISTS

Commits:

- a45358d: feat(08-02): migration 0008 — gruvax.record_stats table (OBS-07)
- 41d5752: test(08-02): add failing tests for record_stats counter functions (RED)
- 4a38375: feat(08-02): add six OBS-07 query functions to queries.py (GREEN)

## Self-Check: PASSED

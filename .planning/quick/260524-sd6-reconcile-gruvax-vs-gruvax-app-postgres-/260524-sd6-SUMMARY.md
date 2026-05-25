---
phase: quick-260524-sd6
plan: 01
subsystem: database
tags: [postgres, role-naming, docs, grant, quick-task]
dependency_graph:
  requires: []
  provides: [consistent-postgres-grant-docs]
  affects: [migrations/versions/0002_v_collection_view.py, justfile]
tech_stack:
  added: []
  patterns: []
key_files:
  modified:
    - migrations/versions/0002_v_collection_view.py
    - justfile
  created: []
decisions:
  - "D-01 confirmed: canonical Postgres role name is `gruvax`; dev and prod both use the same role; no least-privilege split needed at this scale"
metrics:
  duration: ~3min
  completed: "2026-05-25T03:28:21Z"
  tasks: 2
  files: 2
---

# Quick Task 260524-sd6: Reconcile gruvax vs gruvax_app Postgres Role Naming Summary

**One-liner:** Replace stale `gruvax_app` role references in migration 0002 GRANT NOTE and justfile `provision-db` recipe with the canonical runtime role `gruvax`.

## What Was Done

Two doc/comment locations referenced a non-existent `gruvax_app` Postgres role while the runtime `DATABASE_URL` connects as `gruvax`. Left uncorrected, an operator following `just provision-db` on the shared discogsography Postgres would have granted SELECT access to the wrong role, breaking `gruvax.v_collection` reads in production.

Per locked decision D-01 (canonical role = `gruvax`), both occurrences were updated to `gruvax`. No executable SQL, runtime connection strings, or migration logic was changed.

## Tasks

### Task 1: Replace gruvax_app with gruvax in grant docs

- **Commit:** 250f7b9
- **Files:** `migrations/versions/0002_v_collection_view.py`, `justfile`
- **Changes:** Two `TO gruvax_app;` tokens in the GRANT NOTE docstring (lines 17, 20) and two `@echo` lines in the `provision-db` recipe (lines 69, 71) updated to `gruvax`. Comment-only; no SQL executed.

### Task 2: Mark the captured todo completed

- **Commit:** b79036b
- **Files:** `.planning/todos/pending/2026-05-25-reconcile-gruvax-vs-gruvax-app-postgres-role-naming.md` → `.planning/todos/completed/`
- **Changes:** `git mv` to `.planning/todos/completed/`; filename and content unchanged.

## Verification

```
grep -rn gruvax_app migrations/ justfile → zero matches (PASS)
todo file at .planning/todos/completed/ → PASS
todo absent from .planning/todos/pending/ → PASS
```

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `migrations/versions/0002_v_collection_view.py` — exists, contains `TO gruvax;`
- `justfile` — exists, `provision-db` recipe references `gruvax`
- Commit 250f7b9 — exists
- Commit b79036b — exists
- No `gruvax_app` remains in `migrations/` or `justfile`

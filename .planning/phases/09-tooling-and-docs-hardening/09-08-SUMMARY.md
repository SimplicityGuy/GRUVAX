---
phase: "09"
plan: "08"
subsystem: tooling
tags: [security, logging, ci, code-review-fixes]
dependency_graph:
  requires: [09-07]
  provides: []
  affects: [ci, logging, scripts]
tech_stack:
  added: []
  patterns: [sha256-pinned container images, idempotent logging setup]
key_files:
  modified:
    - .github/workflows/security.yml
    - src/gruvax/logging_config.py
    - tests/unit/test_logging_config.py
    - scripts/update-project.sh
    - frontend/src/routes/admin/Diagnostics.tsx
    - .github/workflows/build.yml
decisions:
  - "Pin semgrep container to @sha256 digest (v1.163.0); existing docker dependabot entry covers future updates"
  - "LogRingHandler dedup: remove existing handlers before addHandler in configure_logging() for idempotency"
  - "WR-04 (stalenessStatus null returns ok) deferred — pre-existing product behavior, out of scope for no-behavior-change phase"
metrics:
  duration: "~15 minutes"
  completed: "2026-05-25T20:00:00Z"
  tasks_completed: 5
  files_modified: 6
---

# Phase 9 Plan 08: Code Review Findings Fix Summary

Applies 5 of 6 findings from `09-REVIEW.md`. WR-04 deferred as pre-existing product behavior.

## Findings Applied

### CR-01 (Critical): Unpinned semgrep container image — supply-chain fix

**File:** `.github/workflows/security.yml`

Pinned `semgrep/semgrep` container to `@sha256:7cad2bc2d1e44f87f0bf4be6d1fa23aa90fb72015bebc89fb91385d813987a03` (v1.163.0) using a digest resolved via `docker buildx imagetools inspect semgrep/semgrep:latest`. This was the sole unpinned third-party image in CI; all GitHub Actions were already SHA-pinned.

The existing `docker` ecosystem entry in `.github/dependabot.yml` (directory: `/`) covers workflow container image references, so no new dependabot entry was needed.

**Pin method used:** `@sha256:` digest (not a version tag). Full supply-chain protection.

### WR-02 (Warning/Bug): Duplicate LogRingHandlers on repeated configure_logging() calls

**Files:** `src/gruvax/logging_config.py`, `tests/unit/test_logging_config.py`

Added handler deduplication before `addHandler`: iterate `gruvax_logger.handlers`, remove any existing `LogRingHandler` instances, then add the new one. This makes `configure_logging()` idempotent and honours the documented "safe to call multiple times" guarantee.

Added `test_configure_logging_no_duplicate_ring_handlers` asserting:
- Exactly 1 `LogRingHandler` on the gruvax logger after two `configure_logging()` calls
- Exactly 1 ring entry per record emitted (dedup-marker test)

All 10 logging unit tests pass.

### WR-01 (Warning): Dead branch in update-project.sh --major flag

**File:** `scripts/update-project.sh`

Fixed the else-branch to run `uv lock` (without `--upgrade`) instead of the identical `uv lock --upgrade`. Now:
- `--major`: runs `uv lock --upgrade` (bumps to latest, including major versions)
- default: runs `uv lock` (refreshes within existing pyproject.toml floor constraints)

shfmt auto-fixed comment spacing; included in the commit.

### WR-03 (Warning): Factually wrong eslint-disable comment in Diagnostics.tsx

**File:** `frontend/src/routes/admin/Diagnostics.tsx` (line 471)

Replaced the incorrect rationale ("setState calls execute after the awaited fetch resolves") with the accurate one: `setRefreshing(true)` and `setError(null)` run **synchronously before** the `await`, are intentional loading-state transitions, and React 18 batches them into one re-render. Suppression itself is correct; only the comment was wrong.

### WR-05 (Warning): Empty BUILD_TIMESTAMP on PR builds in build.yml

**File:** `.github/workflows/build.yml` (line 92)

Changed `BUILD_TIMESTAMP=${{ github.event.head_commit.timestamp }}` to
`BUILD_TIMESTAMP=${{ github.event.head_commit.timestamp || 'pr-build' }}`.
`github.event.head_commit` is null on `pull_request` events, producing an empty string that overrides the Dockerfile's `ARG BUILD_TIMESTAMP=unknown` default. Now PR builds get `pr-build` instead of `""`.

## Deferred Finding

### WR-04: stalenessStatus(null) returns 'ok' — deferred

**Decision:** Out of scope for this no-behavior-change review-fix pass. `stalenessStatus(null)` returning `'ok'` (green badge when sync age is unknown) is pre-existing product behavior, not introduced by Phase 9. The fix (adding an `'unknown'` status with a neutral badge + CSS class) is a UI behavior change that belongs in the next admin UI iteration, not a correctness-only patch wave. Tracked in deferred items.

## Final Gate Results

```
uv run pre-commit run --all-files
  [all hooks] Passed / Skipped

Exit code: 0
```

```
uv run pytest tests/unit/test_logging_config.py -v
  10 passed in 0.17s
```

```
uv run ruff check src/ tests/
  All checks passed!
```

Note: Full `uv run pytest tests/` run requires Postgres (not available in this environment). All failures observed are `psycopg_pool.PoolTimeout` — the same pre-existing Postgres-not-available failures present before these changes. The unit tests that do not require Postgres are green.

## Commits

| Hash | Description |
|------|-------------|
| `de48c6a` | fix(09): pin semgrep image in security.yml (CR-01 supply-chain) |
| `b6d07a1` | fix(09): dedupe LogRingHandler on re-config (WR-02) |
| `7eaaf18` | fix(09): update-project.sh --major dead branch; build.yml PR timestamp; Diagnostics comment (WR-01/03/05) |

## Self-Check: PASSED

---
phase: 09-tooling-and-docs-hardening
plan: "03"
subsystem: tooling
tags: [pre-commit, dependabot, prettier, ci-tooling, developer-experience]
dependency_graph:
  requires: [09-02]
  provides: [pre-commit-config, dependabot, prettier-frontend, update-script, lint-precommit]
  affects: [code-quality-gate, frontend-ci-coverage, dependency-freshness]
tech_stack:
  added: [prettier@3.8.3]
  patterns: [pre-commit-SHA-freezing, local-hooks-system-language, justfile-delegation]
key_files:
  created:
    - .pre-commit-config.yaml
    - .yamllint
    - .github/dependabot.yml
    - scripts/update-project.sh
    - frontend/.prettierrc.json
  modified:
    - frontend/package.json
    - frontend/package-lock.json
    - justfile
decisions:
  - "yamllint document-start disabled (not present: true) — GH Actions workflow files don't use --- header"
  - "pretty-format-json excludes frontend/tsconfig+package JSON to avoid noise"
  - "shfmt hook uses files: regex instead of args positional target"
  - "yamllint line-length raised to 200 (compose.yaml has 181-char line)"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-25"
  tasks_completed: 3
  files_created: 5
  files_modified: 3
---

# Phase 9 Plan 03: Pre-commit + Dependabot + Prettier tooling Summary

**One-liner:** SHA-frozen pre-commit hook set with frontend eslint/prettier/tsc + local mypy, weekly four-ecosystem dependabot, and shellcheck-clean update script delegating to justfile.

## What Was Built

### Task 1: Prettier in frontend/ (D-03 prerequisite)

Installed prettier@3.8.3 as a dev dependency in `frontend/package.json`. Created `frontend/.prettierrc.json` with conventional React/TS config (semi, double quotes, printWidth=100, trailingComma=all). Added `format` and `format:check` npm scripts. The frontend source (`frontend/src/`) was already prettier-clean — no files required reformatting.

### Task 2: .pre-commit-config.yaml + .yamllint (D-02)

Created `.pre-commit-config.yaml` from RESEARCH.md Pattern 6, adapted from discogsography:
- All 10 hook revs frozen to 40-char SHAs at current latest (verified via GitHub API 2026-05-25)
- Rust hooks (cargo-fmt, cargo-clippy) dropped — no Rust in GRUVAX
- `docker-compose-check` targets `^compose\.yaml$` (Pitfall 7 — not docker-compose.yml)
- `pretty-format-json` excludes `frontend/(tsconfig|package).*\.json$` to avoid noise
- `shfmt` scoped to `^scripts/update-project\.sh$` only
- Local hooks: `mypy` (uv run --strict src/gruvax/), `eslint`, `prettier`, `tsc` all via npm --prefix frontend
- mdformat omitted (disco disabled for CI/local inconsistency; GRUVAX skips entirely)

Created `.yamllint` adapted from discogsography — `document-start` disabled (GH Actions workflow files don't use `---` header), line-length relaxed to 200 (compose.yaml has 181-char line).

All three acceptance hooks pass: `check-yaml`, `actionlint`, `yamllint` each exit 0 on `--all-files`.

### Task 3: dependabot.yml + update-project.sh + lint-precommit

Created `.github/dependabot.yml` with four ecosystems (github-actions, docker, npm, pip), weekly Monday 09:00 America/Los_Angeles, SimplicityGuy assignee on all four, grouped where applicable. Single-dir fan-out (no 8-service disco fan-out, no cargo).

Created `scripts/update-project.sh` (executable, shellcheck-clean, shfmt-formatted): `just install` → `uv lock --upgrade` → `uv run pre-commit autoupdate` → `npm --prefix frontend update` → `just test`. Supports `--dry-run`, `--major`, `--skip-tests` flags for parity with disco's interface.

Added `lint-precommit` recipe to justfile wrapping `uv run pre-commit run --all-files`.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 092d292 | feat(09-03): install Prettier in frontend/ + .prettierrc.json (D-03) |
| 2 | 30894d3 | feat(09-03): add .pre-commit-config.yaml + .yamllint (D-02) |
| 3 | 4da1a56 | feat(09-03): add dependabot.yml + update-project.sh + lint-precommit recipe |
| fix | b1c61bf | chore(09-03): reformat .prettierrc.json via pretty-format-json hook |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] pretty-format-json rewrote frontend/.prettierrc.json key order**
- **Found during:** Final verification pass
- **Issue:** `pretty-format-json --autofix` reordered keys in `.prettierrc.json` alphabetically (plugins, printWidth, semi... instead of semi, singleQuote, printWidth...)
- **Fix:** Committed the hook-reformatted file; subsequent run passes cleanly
- **Files modified:** `frontend/.prettierrc.json`
- **Commit:** b1c61bf

**2. [Rule 1 - Config] yamllint document-start rule adjusted**
- **Found during:** Task 2 verification (yamllint --all-files)
- **Issue:** disco's `.yamllint` has `document-start: present: true` which fails on the 6 GH Actions workflow files from Plan 02 (they don't use `---` header, which is standard for GH Actions)
- **Fix:** Changed `document-start` to `disable` in `.yamllint`
- **Files modified:** `.yamllint`
- **Commit:** 30894d3

**3. [Rule 1 - Config] yamllint line-length raised to 200**
- **Found during:** Task 2 verification (yamllint --all-files)
- **Issue:** `compose.yaml` has a 181-char line; disco's 175 limit would fail
- **Fix:** Raised `line-length.max` to 200 in `.yamllint`
- **Files modified:** `.yamllint`
- **Commit:** 30894d3

## Known Stubs

None — all artifacts created in this plan are fully wired and functional.

## Threat Flags

No new security-relevant surface introduced. The pre-commit hook set enforces `bandit -x tests -s B608` (T-9-BANDIT mitigation) and all hook revs are SHA-frozen (T-9-HOOKPIN mitigation) per the plan's threat model.

## Self-Check: PASSED

All files verified present:
- FOUND: .pre-commit-config.yaml
- FOUND: .yamllint
- FOUND: .github/dependabot.yml
- FOUND: scripts/update-project.sh
- FOUND: frontend/.prettierrc.json

All commits verified in git log:
- FOUND commit: 092d292
- FOUND commit: 30894d3
- FOUND commit: 4da1a56
- FOUND commit: b1c61bf

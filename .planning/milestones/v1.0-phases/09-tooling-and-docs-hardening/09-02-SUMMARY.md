---
phase: "09"
plan: "02"
subsystem: ci
tags: [github-actions, workflow_call, ghcr, security, ci-orchestration]
dependency_graph:
  requires: []
  provides:
    - workflow_call gate: code-quality gates test and build (D-01)
    - GHCR publish: ghcr.io/simplicityguy/gruvax on push-to-main (D-04)
    - pre-commit single source of truth: code-quality runs pre-commit --all-files (D-02)
    - scheduled cleanup: monthly GHCR image pruning + PR cache deletion
  affects:
    - .github/workflows/ (supersedes ci.yml with six-file orchestration)
tech_stack:
  added:
    - GitHub Actions workflow_call orchestration pattern
    - docker/login-action v4.2.0 (SHA-pinned)
    - docker/metadata-action v6.1.0 (SHA-pinned)
    - docker/build-push-action v7.2.0 (SHA-pinned)
    - docker/setup-buildx-action v4.1.0 (SHA-pinned)
    - dataaxiom/ghcr-cleanup-action v1.2.0 (SHA-pinned)
    - google/osv-scanner-action v2.3.8 (SHA-pinned)
    - trufflesecurity/trufflehog v3.95.3 (SHA-pinned)
    - aquasecurity/trivy-action v0.36.0 (SHA-pinned)
    - github/codeql-action/upload-sarif v4.35.5 (SHA-pinned)
  patterns:
    - Workflow_call gate: code-quality must succeed before test/security/build run
    - Least-privilege: packages:write scoped to build job only
    - Supply-chain: all uses: pinned to 40-char commit SHAs, no @vN tags
    - No continue-on-error anywhere (honest gate, D-06)
key_files:
  created:
    - .github/workflows/build.yml
    - .github/workflows/code-quality.yml
    - .github/workflows/test.yml
    - .github/workflows/security.yml
    - .github/workflows/cleanup-cache.yml
    - .github/workflows/cleanup-images.yml
  modified: []
  deleted:
    - .github/workflows/ci.yml (superseded — hard gates preserved in test.yml)
decisions:
  - "GHCR image path is ghcr.io/simplicityguy/gruvax (lowercased via tr '[:upper:]' '[:lower:]'), not gruvax-api"
  - "packages:write scoped to build job only — workflow-level permission is contents:read (T-9-PERM)"
  - "security.yml drops rust-security job (no Rust in GRUVAX)"
  - "ci.yml deleted only after verifying test.yml contains Alembic round-trip and benchmark SLO gates"
metrics:
  duration: "~5 minutes"
  completed: "2026-05-25"
  tasks: 3
  files: 7
---

# Phase 9 Plan 02: GitHub Actions Workflow Orchestration Summary

Six-file discogsography-style `workflow_call` CI replacing the Phase 8 single-file `ci.yml`. The `code-quality` workflow gates `test`, `security`, and `build`; `build` publishes to GHCR with least-privilege permissions; cleanup workflows handle PR cache and monthly image pruning.

## What Was Built

Replaced `.github/workflows/ci.yml` with six named workflows:

| File | Role | Trigger |
|------|------|---------|
| `build.yml` | Orchestrator — fans out to all other workflows | push/PR to main |
| `code-quality.yml` | Gate — `pre-commit --all-files` (D-02 single source of truth) | workflow_call |
| `test.yml` | Test suite with postgres:18, Alembic round-trip, benchmark SLO | workflow_call |
| `security.yml` | pip-audit, bandit, osv-scanner, semgrep, trufflehog, trivy | workflow_call |
| `cleanup-cache.yml` | Delete GitHub Actions caches on PR close | pull_request closed |
| `cleanup-images.yml` | Prune old/untagged GHCR images monthly | schedule + dispatch |

## Key Implementation Details

**Gating preserved (D-01):** `run-tests` and `run-security` both declare `needs: [run-code-quality]`. The `build` job declares `needs: [run-tests, run-security]`. Code quality is the single gate before any test or deployment work runs.

**OBS-03 Alembic round-trip gate** copied verbatim from ci.yml:
```yaml
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

**SC5 benchmark SLO gate** copied verbatim from ci.yml:
```yaml
uv run pytest tests/unit/test_algorithm.py::test_locate_benchmark \
  tests/integration/test_search_benchmark.py::test_search_slo_benchmark \
  --benchmark-only --benchmark-json=benchmark.json -q
uv run python scripts/check_benchmark.py benchmark.json
```

**Repo hygiene (T-9-CSV):** `test.yml` seeds only `fixtures/synth_collection.sql`. The real collection CSV and `background/` are never referenced in any workflow.

**Supply chain (T-9-SC):** Every `uses:` line is pinned to a 40-char commit SHA. Zero `@vN` moving tags in any file. Zero `continue-on-error:` directives — D-06 mandates an honest gate.

**Permissions (T-9-PERM):** `packages: write` appears only in the `build` job. Workflow-level permission is `contents: read`. The `security` job gets `security-events: write` scoped to that job only (SARIF uploads).

**GHCR image path:** `ghcr.io/simplicityguy/gruvax` (not `gruvax-api`). Image name lowercased at runtime via `tr '[:upper:]' '[:lower:]'`. Docker login and push both guarded by `github.event_name != 'pull_request'`.

## Deviations from Plan

None — plan executed exactly as written.

The deletion of `ci.yml` was deferred until after verifying `test.yml` contained both the Alembic round-trip and benchmark SLO gates (as required by the plan). Both gates confirmed present before removal.

## Threat Surface Scan

All new workflow files were reviewed for embedded secrets — none found. All credentials use `secrets.GITHUB_TOKEN` or `secrets.GITHUB_TOKEN` (auto-provisioned). TruffleHog in `security.yml` will scan the new workflow files on every build. The threat register from the plan (T-9-PERM, T-9-SC, T-9-TOKEN, T-9-CSV, T-9-SECRETSCAN) is fully mitigated.

## Known Stubs

None. The workflow files reference `.pre-commit-config.yaml` (Plan 03) which does not yet exist. CI on `main` will pass the code-quality gate only after Plan 03 (pre-commit config) and Plan 04 (lint cleanup) land in Wave 2. This is intentional and documented in the plan objective.

## Self-Check: PASSED

Files created:
- .github/workflows/build.yml: EXISTS
- .github/workflows/code-quality.yml: EXISTS
- .github/workflows/test.yml: EXISTS
- .github/workflows/security.yml: EXISTS
- .github/workflows/cleanup-cache.yml: EXISTS
- .github/workflows/cleanup-images.yml: EXISTS
- .github/workflows/ci.yml: REMOVED (intentional)

Commits:
- 97c0aca: feat(09-02): add test.yml + code-quality.yml workflow_call workflows
- 5bf46fd: feat(09-02): add build.yml orchestrator + security.yml workflow_call workflows
- 8eeea38: feat(09-02): add cleanup-cache/images workflows; remove superseded ci.yml

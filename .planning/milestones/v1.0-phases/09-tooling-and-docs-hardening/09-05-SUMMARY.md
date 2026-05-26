---
phase: 09-tooling-and-docs-hardening
plan: 05
subsystem: deploy
tags: [compose, docker, deploy, pull-based, ghcr, override, gitignore, docs]
dependency_graph:
  requires: [09-02, 09-03]
  provides: [pull-based-deploy-config, compose-override-pattern, lux-genericized-compose-runbook]
  affects: [compose.yaml, compose.override.yaml.example, .gitignore, docs/runbook-fresh-host.md]
tech_stack:
  added: []
  patterns:
    - compose.override.yaml dev-only override shadows GHCR image for local build
    - gitignored override + committed .example (Pitfall 3 mitigation)
    - pull-based prod deploy via docker compose pull && docker compose up -d
key_files:
  created:
    - compose.override.yaml.example
  modified:
    - compose.yaml
    - .gitignore
    - docs/runbook-fresh-host.md
decisions:
  - Pull-based deploy: compose.yaml references ghcr.io/simplicityguy/gruvax:latest with no build block
  - compose.override.yaml is gitignored; .example committed per Pitfall 3 (override must never reach prod host)
  - lux genericized to "the deployment host" in compose.yaml (4 comment occurrences) and runbook (1 occurrence)
metrics:
  duration: ~8min
  completed: "2026-05-25"
  tasks: 3
  files: 4
---

# Phase 09 Plan 05: Pull-Based Deploy Flip Summary

Pull-based deploy established: `compose.yaml` references `ghcr.io/simplicityguy/gruvax:latest` with no `build:` block; local dev build context lives in a gitignored `compose.override.yaml` (committed template: `compose.override.yaml.example`); all `lux` host references genericized in compose.yaml and the runbook.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Flip compose.yaml to GHCR image + genericize lux comments | 71d8fe3 | compose.yaml |
| 2 | compose.override.yaml + .example + .gitignore entry | 0f13f9b | compose.override.yaml.example, .gitignore |
| 3 | Runbook lux-strip + GHCR image in expected ps output | 432d0c0 | docs/runbook-fresh-host.md |

## What Was Built

**Task 1 — compose.yaml flip:**
- `image: gruvax-api:local` + `build:` block replaced with `image: ghcr.io/simplicityguy/gruvax:latest`
- Four `lux` comment occurrences genericized to "the deployment host" (lines 15, 35, 56, 101)
- All production-hardening keys preserved: `healthcheck`, `restart: unless-stopped`, `logging` json-file driver
- `docker compose -f compose.yaml config -q` validates standalone

**Task 2 — override + gitignore:**
- `compose.override.yaml` (gitignored): dev-only override with `build: context: . / dockerfile: Dockerfile` and `image: gruvax-api:local` to shadow GHCR image for local builds
- `compose.override.yaml.example` (committed): identical content with full explanation of Pitfall 3 and copy-to-use instructions
- `.gitignore`: `compose.override.yaml` entry added with explanatory comment
- `git check-ignore compose.override.yaml` succeeds; `git check-ignore compose.override.yaml.example` fails (tracked)
- `docker compose config` (merged) resolves api to `gruvax-api:local` with build context

**Task 3 — runbook:**
- Line 1 reference: "fresh host (e.g. `lux`)" → "fresh deployment host (e.g. `your-server.local`)"
- Expected `docker compose ps` output updated to show `ghcr.io/simplicityguy/gruvax:latest`
- Prod deploy instructions: `docker compose pull && docker compose up -d` (pull-based, no override)
- Pitfall 3 warning: explicit note that `compose.override.yaml` must NOT be on the prod host
- Dev override-copy step documented: `cp compose.override.yaml.example compose.override.yaml`

## Verification

All acceptance criteria met:

| Check | Result |
|-------|--------|
| `grep -c 'image: ghcr.io/simplicityguy/gruvax:latest' compose.yaml` | 1 |
| `grep -c 'gruvax-api:local' compose.yaml` | 0 |
| `grep -cE '^\s+build:' compose.yaml` | 0 |
| `grep -c 'lux' compose.yaml` | 0 |
| `docker compose -f compose.yaml config -q` | PASS |
| `git check-ignore compose.override.yaml` | PASS (ignored) |
| `git check-ignore compose.override.yaml.example` | FAIL (tracked — correct) |
| `docker compose config` resolves to `gruvax-api:local` (override shadows GHCR) | PASS |
| `grep -c 'lux' docs/runbook-fresh-host.md` | 0 |
| `uv run pytest tests/unit/test_compose_config.py -v` (DEP-04/DEP-05) | 16 passed |

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. All compose configuration is functional — the GHCR image path is the canonical published image from Plan 02's build.yml.

## Threat Flags

No new security-relevant surface introduced. Threats mitigated per plan's threat register:

| Threat | Status |
|--------|--------|
| T-9-OVERRIDE (compose.override.yaml on prod) | Mitigated — gitignored, .example documents dev-only usage, runbook warns explicitly |
| T-9-IMGSPOOF (GHCR image pull) | Accepted per plan (open source, home LAN, plan 02 build provenance) |
| T-9-LUXLEAK (host names in compose/runbook) | Mitigated — `grep -c lux` returns 0 in both files |

## Self-Check: PASSED

- compose.yaml: FOUND
- compose.override.yaml.example: FOUND
- .gitignore with compose.override.yaml entry: FOUND
- docs/runbook-fresh-host.md with zero lux refs: FOUND
- Commits: 71d8fe3 (task 1), 0f13f9b (task 2), 432d0c0 (task 3) — all present in git log

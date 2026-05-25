---
phase: 9
slug: tooling-and-docs-hardening
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-25
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **No product behavior changes this phase** — validation focus is *regression
> prevention* across three observable seams: the diagnostics log-ring shape, the
> Phase 8 CI hard gates, and local-dev build under the new pull-based deploy model.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (async via pytest-asyncio) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/ tests/integration/test_diagnostics.py -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -q --tb=short` |
| **Estimated runtime** | ~quick <10s · full ~varies (shared dev Postgres) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ tests/integration/test_diagnostics.py -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite green AND `uv run pre-commit run --all-files` exits 0
- **Max feedback latency:** ~10 seconds (quick) / full suite per wave

---

## Per-Task Verification Map

| Concern | Plan/Wave | Threat Ref | Secure/Correct Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-----------|------------|--------------------------|-----------|-------------------|-------------|--------|
| Log ring shape preserved | structlog wave | — | `GET /api/admin/diagnostics` returns `recent_logs` of `{ts, level, logger, msg}` dicts | Integration | `uv run pytest tests/integration/test_diagnostics.py -q` | ✅ exists | ⬜ pending |
| Ring scoping (no leak) | structlog wave | T-9 (secret leak to admin UI) | Third-party loggers do NOT appear in `recent_logs` | Integration | Same test + new assertion on logger names | ❌ W0 (add assertion) | ⬜ pending |
| Env-driven log level | structlog wave | — | `LOG_LEVEL=DEBUG` env raises effective level on `gruvax` logger | Unit | `uv run pytest tests/unit/ -q -k log_level` | ❌ W0 (add test if absent) | ⬜ pending |
| Alembic round-trip gate | CI wave | — | `alembic upgrade head && downgrade base && upgrade head` clean | CI gate | preserved verbatim in new `test.yml` | ✅ exists in ci.yml | ⬜ pending |
| Benchmark SLO gate | CI wave | — | `scripts/check_benchmark.py` passes p95 SLO | CI gate | preserved verbatim in new `test.yml` | ✅ exists in ci.yml | ⬜ pending |
| Local dev build (deploy flip) | deploy wave | — | `compose.override.yaml` shadows GHCR image; `just up`/`just build` build locally | Smoke | `just demo` / manual | n/a | ⬜ pending |
| pre-commit honest-green | lint+tooling wave | — | `pre-commit run --all-files` exits 0 (all 69 ruff + infra-linter findings fixed) | pre-commit | `uv run pre-commit run --all-files` | ❌ W0 (config + cleanup) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Add ring-scoping assertion to `tests/integration/test_diagnostics.py` — covers
      "third-party logger records must NOT appear in `recent_logs`" (the secret-leak guard).
- [ ] Ensure an env-driven log-level test exists (`tests/unit/`) — covers D-02; add if absent.
- [ ] Prettier config (`frontend/.prettierrc.json` or `prettier` key in `package.json`) must
      exist before the `prettier --check` pre-commit hook can run (D-03 — prettier not yet installed).

*No new test files needed for the structlog migration — the ring-shape integration test
already exists; Wave 0 only adds assertions and the prettier config prerequisite.*

---

## Manual-Only Verifications

| Behavior | Why Manual | Test Instructions |
|----------|------------|-------------------|
| Pull-based deploy on host | No CI environment for a live host pull | On the deployment host: `docker compose pull && docker compose up -d`; confirm `gruvax-api` runs from `ghcr.io/simplicityguy/gruvax:latest`. |
| Local override shadows registry | Compose merge semantics; verify before calling done | Locally: `just up` (or `docker compose up --build`) builds from `compose.override.yaml` `build:` context, NOT the GHCR image. |
| GHCR publish + cleanup | Requires push-to-main + scheduled run | After merge to main: confirm `build.yml` pushed SHA + `latest` tags; `cleanup-images` prunes per keep-n/older-than policy. |
| Docs accuracy (ARCHITECTURE.md, lux strip) | Prose correctness is human-judged | Review `docs/ARCHITECTURE.md` against final endpoints/schema; `grep -rn 'lux\|nox'` in docs/CLAUDE.md/compose/runbook returns only intended (genericized) results. |

---

## Validation Sign-Off

- [ ] All regression-prevention concerns have an automated verify or a Wave 0 dependency
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (ring-scoping assertion, log-level test, prettier config)
- [ ] No watch-mode flags in any verify command
- [ ] Feedback latency < ~10s (quick) per task commit
- [ ] `nyquist_compliant: true` set in frontmatter (set by planner once per-task verify map is complete)

**Approval:** pending

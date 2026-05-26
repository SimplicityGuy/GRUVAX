---
phase: 9
slug: tooling-and-docs-hardening
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-25
validated: 2026-05-25
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
| Log ring shape preserved | 09-01 / W1 | T-9-SHAPE | `GET /api/admin/diagnostics` returns `recent_logs` of `{ts, level, logger, msg}` dicts | Integration | `uv run pytest tests/integration/test_diagnostics.py::test_recent_logs_shape -q` | ✅ `test_diagnostics.py:248` | ✅ green |
| Ring scoping (no leak) | 09-01 / W1 | T-9-IL (secret leak to admin UI) | Third-party loggers (psycopg/uvicorn/…) do NOT appear in `recent_logs` | Integration | `uv run pytest tests/integration/test_diagnostics.py::test_recent_logs_ring_scoping -q` | ✅ `test_diagnostics.py:290` | ✅ green |
| Env-driven log level | 09-01 / W1 | — | `LOG_LEVEL` env raises/lowers effective level on `gruvax` logger | Unit | `uv run pytest tests/unit/test_logging_config.py -q` | ✅ `test_logging_config.py` (Wave-0 regression) | ✅ green |
| Handler idempotency (re-config) | 09-08 / fix | — | `configure_logging()` twice does NOT duplicate ring entries (WR-02 fix) | Unit | `uv run pytest tests/unit/test_logging_config.py -q` | ✅ added in 09-08 | ✅ green |
| Alembic round-trip gate | 09-02 / W1 | — | `alembic upgrade head && downgrade base && upgrade head` clean | CI gate | preserved verbatim in `test.yml:83-85` (OBS-03) | ✅ `test.yml` | ✅ in CI |
| Benchmark SLO gate | 09-02 / W1 | — | `scripts/check_benchmark.py` passes p95 SLO | CI gate | preserved verbatim in `test.yml` (SC5) | ✅ `test.yml` | ✅ in CI |
| Local dev build (deploy flip) | 09-05 / W3 | T-9-OVERRIDE | `compose.override.yaml` shadows GHCR image; `just up`/`just build` build locally | Smoke | `just demo` / manual | n/a (manual) | ☐ manual-only |
| pre-commit honest-green | 09-03+09-04 / W2 | T-9-GATEHOLE | `pre-commit run --all-files` exits 0 (all 65 ruff + infra-linter findings fixed) | pre-commit | `uv run pre-commit run --all-files` | ✅ `.pre-commit-config.yaml` | ✅ green (exit 0) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · ☐ manual-only*

---

## Wave 0 Requirements

- [x] Add ring-scoping assertion to `tests/integration/test_diagnostics.py` — covers
      "third-party logger records must NOT appear in `recent_logs`" (the secret-leak guard). → `test_recent_logs_ring_scoping` (09-01).
- [x] Ensure an env-driven log-level test exists (`tests/unit/`) → `tests/unit/test_logging_config.py` Wave-0 regression (09-01).
- [x] Prettier config (`frontend/.prettierrc.json`) exists before the `prettier --check` hook runs (09-03).

*All Wave-0 prerequisites landed in Wave 1 / Wave 2; the structlog ring-shape integration
test already existed and was extended with the scoping assertion.*

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

- [x] All regression-prevention concerns have an automated verify or a Wave 0 dependency
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (ring-scoping assertion, log-level test, prettier config) — all landed
- [x] No watch-mode flags in any verify command
- [x] Feedback latency < ~10s (quick) per task commit
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-25 (post-execution audit — all automated concerns COVERED + green; deploy smoke is manual-only by nature)

---

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Concerns audited | 8 |
| COVERED (automated, green) | 7 (5 unit/integration + 2 CI gates) |
| Manual-only | 1 (pull-based deploy smoke on host) |
| MISSING | 0 |
| Resolved this audit | 0 (all closed during execution) |

**Verdict:** NYQUIST-COMPLIANT. All regression-prevention concerns for this no-product-behavior-change phase have automated verification (or are CI gates preserved verbatim in `test.yml`). The single manual-only item (live-host pull-based deploy) cannot be automated without a deploy host. Regression tests verified green this audit: `test_recent_logs_shape`, `test_recent_logs_ring_scoping`, `test_logging_config.py` (incl. handler-idempotency), `pre-commit run --all-files` exit 0, `ruff check` 0. (Note: integration tests require the dev Postgres up + synthetic-seeded — see [[project_compose_flip_teardown_dev_db]].)

**Approval:** pending

---
phase: 8
slug: observability-deployment-hardening
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-24
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconciled against delivered artifacts on 2026-05-25 (State A audit). DEP-04/DEP-05 config declarations promoted from manual-only to automated via `tests/unit/test_compose_config.py`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio, httpx, pytest-benchmark, Hypothesis) — backend; Vitest — frontend |
| **Config file** | `pyproject.toml` (pytest config, `addopts` includes `--benchmark-disable`); `frontend/vitest.config.*` |
| **Quick run command** | `uv run pytest tests/unit` (backend) · `cd frontend && npx vitest run` (frontend) |
| **Full suite command** | `just test` (full pytest) + `uv run pytest --benchmark-only` for SLO gate + CI Alembic round-trip |
| **Estimated runtime** | ~30–90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit` (quick)
- **After every plan wave:** Run `just test` (full suite)
- **Before `/gsd-verify-work`:** Full suite green, including Alembic round-trip + pytest-benchmark SLO gate
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Reconciled to delivered tests. Every requirement and tracked success-criterion has an automated command that runs green. The slow-query/benchmark instrumentation feeds both the runtime ring buffer and the pytest-benchmark gate (single timing path).

| Requirement | Plan | Threat Ref | Secure Behavior | Test Type | Automated Command | Test File | Status |
|-------------|------|------------|-----------------|-----------|-------------------|-----------|--------|
| OBS-01 | 08-01, 08-03 | T-08-09 | `/api/health` returns per-subsystem status + git-SHA version + `sync_age_seconds`; no secrets | integration | `uv run pytest tests/integration/test_health.py` | `tests/integration/test_health.py` | ✅ green |
| OBS-02 | 08-01 | T-08-02 | Logs serialize to JSON; `LOG_LEVEL` honored; ring scoped to `gruvax.*` INFO+ | unit | `uv run pytest tests/unit/test_logging.py` | `tests/unit/test_logging.py` | ✅ green |
| OBS-03 | 08-06 | T-08-23 | Alembic round-trip `upgrade head → downgrade base → upgrade head` (exercises 0008) | CI gate | `.github/workflows/ci.yml` (Alembic round-trip, hard-fail) | `.github/workflows/ci.yml` | ✅ green (CI) |
| OBS-04 | 08-01, 08-03 | T-08-01 | `/api/version` returns `git_sha`/`build_timestamp`/`environment` only | integration | `uv run pytest tests/integration/test_version.py` | `tests/integration/test_version.py` | ✅ green |
| OBS-05 | 08-01, 08-03, 08-04 | T-08-11 | Slow-query ring flags `/api/search` >200ms and `/api/locate` >50ms (total + DB ms) | unit | `uv run pytest tests/unit/test_slow_query.py` | `tests/unit/test_slow_query.py` | ✅ green |
| OBS-06 | 08-01/03/04/05 | T-08-17/18 | Sync staleness surfaced to admin (3d/14d) + kiosk (>14d) | integration + frontend | `uv run pytest tests/integration/test_diagnostics.py` · `npx vitest run src/routes/kiosk/StalenessBar.test.tsx` | `test_diagnostics.py`, `StalenessBar.test.tsx` | ✅ green |
| OBS-07 | 08-02, 08-03, 08-04 | T-08-05/06/07/10 | `release_id`-keyed counters, NO query-text column, top-N, reset | unit | `uv run pytest tests/unit/test_stats.py` | `tests/unit/test_stats.py` | ✅ green |
| DEP-04 | 08-06 | T-08-21 | Compose declares json-file log driver `max-size 10m` + `max-file 3` on prod services | unit (config) | `uv run pytest tests/unit/test_compose_config.py` | `tests/unit/test_compose_config.py` | ✅ green (new) |
| DEP-05 | 08-06 | — | Compose declares `healthcheck:` + `restart: unless-stopped` on prod services | unit (config) | `uv run pytest tests/unit/test_compose_config.py` | `tests/unit/test_compose_config.py` | ✅ green (new) |
| SC2 | 08-04 | T-08-13/14/15 | `/api/admin/diagnostics` returns 7 rows; admin session + CSRF gated | integration | `uv run pytest tests/integration/test_diagnostics.py` | `tests/integration/test_diagnostics.py` | ✅ green |
| SC3 | 08-05 | T-08-17 | Kiosk staleness banner threshold + copy (>14d only; whole-day; no jargon) | frontend | `npx vitest run src/routes/kiosk/StalenessBar.test.tsx` | `frontend/src/routes/kiosk/StalenessBar.test.tsx` | ✅ green |
| SC5 | 08-06 | T-08-18 | p95 `/api/search` ≤200ms + `/api/locate` ≤50ms on synthetic data | benchmark + CI gate | `uv run pytest tests/integration/test_search_benchmark.py tests/unit/test_algorithm.py::test_locate_benchmark --benchmark-only` → `scripts/check_benchmark.py` | `test_search_benchmark.py`, `test_algorithm.py`, `scripts/check_benchmark.py` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/integration/test_health.py` — `/api/health` returns version (git SHA, not `0.1.0`) + `sync_age_seconds` (OBS-01, OBS-04, OBS-06)
- [x] `tests/integration/test_version.py` — `/api/version` returns git SHA, build timestamp, environment (OBS-04)
- [x] `tests/unit/test_logging.py` — log records serialize to JSON, `LOG_LEVEL` honored (OBS-02)
- [x] `tests/unit/test_slow_query.py` — ring buffer flags `/api/search` >200 ms and `/api/locate` >50 ms with request-total + DB-time (OBS-05)
- [x] `tests/unit/test_stats.py` — search/selection counters increment by release_id, no query text persisted, all-time + recent-7d, reset action (OBS-07)
- [x] `tests/integration/test_diagnostics.py` — `/api/admin/diagnostics` returns the 7 SC#2 rows; admin session + CSRF gated (OBS-05/06/07, SC2)
- [x] `tests/integration/test_search_benchmark.py` — HTTP-level p95 `/api/search` ≤200 ms; locate benchmark in `tests/unit/test_algorithm.py::test_locate_benchmark` (SC5)
- [x] CI: `.github/workflows/ci.yml` Alembic round-trip job (upgrade head → downgrade base → upgrade head) on synthetic data (OBS-03)
- [x] `tests/unit/test_compose_config.py` — Compose log limits + healthcheck + restart on prod services (DEP-04, DEP-05) **[added 2026-05-25]**

*Wave 0 complete: all referenced tests exist and run green.*

---

## Manual-Only Verifications

> Reduced on 2026-05-25: DEP-04/DEP-05 *config declarations* are now automated (`test_compose_config.py`). What remains manual is genuinely runtime/visual.

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Log rotation actually caps disk under sustained pressure | DEP-04 (runtime) | Requires a long-running host / real disk pressure to observe rotation | Generate sustained logs; `docker inspect` confirms rotation; disk stays bounded (config presence already asserted by `test_compose_config.py`) |
| Fresh-host volume permissions for non-root container | Pitfall 14 | Requires a clean host bring-up | Follow `docs/runbook-fresh-host.md` on a fresh `docker compose up`; confirm no permission-denied on volumes |
| Admin diagnostics page visual rendering | SC2 (visual) | UI layout/typography (24/18/16/14px, Barlow ALL-CAPS, DM Mono), dark log terminal, inline reset confirm — not grep-assertable | Sign in; open `/admin/diagnostics`; confirm all 5 section cards per UI-SPEC; REFRESH reloads with no polling; RESET STATS confirm flow works |
| Kiosk staleness banner visual appearance | SC3 (visual) | Requires kiosk render + forced stale state | Force `sync_age > 14d`; load kiosk; banner ABOVE grid with correct copy/color/icon; search still works; no-results stays generic (D-02); banner clears when fresh |
| `just demo` proves SLO at the box level | SC5 (E2E) | End-to-end against fresh `docker compose up` | Run `just demo`; assert Core Value flow holds p95 search ≤200 ms |

---

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Gaps found | 2 (DEP-04, DEP-05 — manual-only, automatable at config layer) |
| Resolved | 2 |
| Escalated | 0 |

Generated `tests/unit/test_compose_config.py` (16 tests, green) via gsd-nyquist-auditor. All 12 tracked requirements/success-criteria now have green automated verification; remaining manual items are inherently runtime/visual.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-05-25

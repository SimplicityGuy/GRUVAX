---
phase: 8
slug: observability-deployment-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-24
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio, httpx, pytest-benchmark, Hypothesis) — backend; existing vanilla-DOM frontend test harness |
| **Config file** | `pyproject.toml` (pytest config) — existing |
| **Quick run command** | `just test` (or `uv run pytest tests/unit`) |
| **Full suite command** | `just test` (full pytest) + `uv run pytest --benchmark-only` for SLO gate |
| **Estimated runtime** | ~30–90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit` (quick)
- **After every plan wave:** Run `just test` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green, including Alembic round-trip + pytest-benchmark SLO gate
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Filled per-plan during planning. Each task references its requirement(s) and an automated command where possible. The slow-query/benchmark instrumentation feeds both the runtime ring buffer and the pytest-benchmark gate (single timing path).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 8-XX-XX | XX | X | OBS-XX | — | {expected behavior} | unit/integration | `{command}` | ✅ / ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_health.py` — assert `/api/health` returns version (git SHA, not `0.1.0`) + `sync_age_seconds` (OBS-01, OBS-04, OBS-06)
- [ ] `tests/unit/test_version.py` — assert `/api/version` returns git SHA, build timestamp, environment (OBS-04)
- [ ] `tests/unit/test_logging.py` — assert log records serialize to JSON, `LOG_LEVEL` honored (OBS-02)
- [ ] `tests/unit/test_slow_query.py` — assert ring buffer flags `/api/search` >200 ms and `/api/locate` >50 ms with request-total + DB-time (OBS-05)
- [ ] `tests/unit/test_stats.py` — assert search/selection counters increment by release_id, no query text persisted, all-time + recent-7d, reset action (OBS-07)
- [ ] `tests/unit/test_diagnostics.py` — assert `/api/admin/diagnostics` returns the 7 SC#2 rows; admin session + CSRF gated (OBS-05/06/07, SC2)
- [ ] `tests/benchmark/test_search_benchmark.py` — HTTP-level p95 `/api/search` ≤200 ms (new; locate benchmark already exists in `tests/unit/test_algorithm.py`) (SC5)
- [ ] CI: `.github/workflows/*.yml` Alembic round-trip job (upgrade head → downgrade base → upgrade head) on synthetic data (OBS-03)

*Existing infrastructure (pytest, pytest-benchmark 5.x already a dev dep, synthetic fixture) covers most needs — net-new is the HTTP search benchmark + CI workflow.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Compose `logging:` limits prevent disk exhaustion on `lux` | DEP-04 | Requires a long-running host / disk pressure | Inspect `docker inspect` log-opts; confirm `max-size`/`max-file` set on `gruvax-api` + `mosquitto` |
| Fresh-host volume permissions for non-root container | Pitfall 14 | Requires a clean host bring-up | Follow documented procedure on a fresh `docker compose up`; confirm no permission-denied on volumes |
| Kiosk staleness banner appears when `sync_age > 14d` | SC3 / D-01 | Requires kiosk render + staleness state | Force `sync_age > 14d`; load kiosk; confirm Nordic Grid banner shows; search still works |
| `just demo` proves SLO at the box level | SC5 | End-to-end against fresh `docker compose up` | Run `just demo`; assert Core Value flow holds p95 search ≤200 ms |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

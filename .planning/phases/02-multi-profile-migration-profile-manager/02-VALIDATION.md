---
phase: 2
slug: multi-profile-migration-profile-manager
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-28
updated: 2026-05-28
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio (asyncio_mode="auto") · Vitest (frontend) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` · `frontend/vite.config.ts` |
| **Quick run command** | `just test-unit` (backend) · `cd frontend && npm run lint` (frontend) |
| **Full suite command** | `just test` + `just slo` + `just migrate-roundtrip` · `cd frontend && npm run build` |
| **Estimated runtime** | ~90s backend unit · ~3–5 min full + slo + roundtrip |

---

## Sampling Rate

- **After every task commit:** Run `just test-unit` (backend) / `cd frontend && npm run lint` (frontend).
- **After every plan wave:** Run `just test` (backend waves) / `cd frontend && npm run build` (frontend waves).
- **Before `/gsd-verify-work`:** `just test` + `just slo` + `just migrate-roundtrip` all green; `cd frontend && npm run build` green.
- **Max feedback latency:** ~90 seconds (backend unit) per task commit.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-00-01 | 00 | 0 | PROF-04 / API-02 / SYN-02 | T-02-00-01 | Fixtures clean up seeded rows (order-independent) | scaffold | `uv run pytest --collect-only -q tests/integration/test_migrate_0010.py tests/unit/test_cache_registry.py tests/unit/test_profile_state_registry.py` | ✅ created here | ⬜ pending |
| 02-00-02 | 00 | 0 | PROF-02 / D2-04 / D2-08 / D2-10 | — | RED baseline for SSE 403/400 + cookie independence | scaffold | `uv run pytest --collect-only -q tests/integration/test_profile_manager_api.py tests/integration/test_sse_per_profile.py tests/integration/test_session_bootstrap.py` | ✅ created here | ⬜ pending |
| 02-01-01 | 01 | 1 | PROF-04 | T-02-01-02 | NULL profile_id RAISEs before tighten (no silent corruption) | integration | `just migrate && uv run pytest tests/integration/test_migrate_0010.py::test_not_null_on_five_data_tables tests/integration/test_migrate_0010.py::test_nullable_stays_on_two_infra_tables tests/integration/test_migrate_0010.py::test_composite_pks -x` | ✅ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PROF-04 | T-02-01-03 | upgrade↔downgrade fidelity (CI invariant) | integration | `just migrate-roundtrip && uv run pytest tests/integration/test_migrate_0010.py::test_roundtrip_clean -x` | ✅ W0 | ⬜ pending |
| 02-02-01 | 02 | 2 | API-02 / SYN-02 | T-02-02-02 | Per-profile registries keyed by str(uuid) → isolation by construction | unit | `uv run pytest tests/unit/test_cache_registry.py tests/unit/test_profile_state_registry.py tests/unit/test_event_bus.py -x` | ✅ W0 | ⬜ pending |
| 02-02-02 | 02 | 2 | API-02 | T-02-02-01 / T-02-02-03 / T-02-02-04 | 400/403/404 session validation; publish AFTER reload (Pitfall A); bus dep no get_pool | integration | `uv run pytest tests/integration/sync tests/integration/test_locate.py tests/integration/test_search.py -x -q` | ✅ existing | ⬜ pending |
| 02-03-01 | 03 | 3 | API-02 / SYN-02 | T-02-03-01 / T-02-03-04 | SSE no cross-profile leakage; no get_pool in events.py | integration (live) | `uv run pytest tests/integration/test_sse_per_profile.py tests/integration/test_sse.py -x` | ✅ W0 | ⬜ pending |
| 02-03-02 | 03 | 3 | API-02 | T-02-03-02 / T-02-03-03 | profile_id validated on search/locate/illuminate; SLO holds w/ 2 profiles | integration + benchmark | `uv run pytest tests/integration/test_search.py tests/integration/test_locate.py -x -q && just slo` | ✅ existing+W0 | ⬜ pending |
| 02-04-01 | 04 | 3 | PROF-02 / SYN-02 | T-02-04-01 / T-02-04-03 | No-PIN bootstrap; profiles[] excludes secrets; single-profile auto-bind | integration | `uv run pytest tests/integration/test_session_bootstrap.py::test_single_profile_auto_binds tests/integration/test_session_bootstrap.py::test_two_profiles_unbound tests/integration/test_session_bootstrap.py::test_bind_then_unbind -x` | ✅ W0 | ⬜ pending |
| 02-04-02 | 04 | 3 | PROF-02 / SYN-02 | T-02-04-02 | Browse cookie independent of admin session (D2-10) | integration | `uv run pytest tests/integration/test_session_bootstrap.py tests/integration/test_admin_auth.py -x` | ✅ W0+existing | ⬜ pending |
| 02-04-03 | 04 | 3 | PROF-02 | T-02-04-01 | Auto-bind + 2-profile picker + cookie independence on running instance | human-verify | manual (checkpoint:human-verify) | n/a | ⬜ pending |
| 02-05-01 | 05 | 3 | PROF-01 / PROF-02 | T-02-05-04 / T-02-05-05 | 202 immediate; bg-task exception captured; Pitfall 6 pool discipline | integration | `uv run pytest tests/integration/test_profile_manager_api.py::test_sync_202_poll -x` | ✅ W0 | ⬜ pending |
| 02-05-02 | 05 | 3 | PROF-01 / PROF-02 | T-02-05-01..03 / T-02-05-06 | PIN-gated CRUD; 409 user_id collision; soft-delete evicts registry | integration | `uv run pytest tests/integration/test_profile_manager_api.py -x` | ✅ W0 | ⬜ pending |
| 02-06-01 | 06 | 4 | PROF-02 / SYN-02 | T-02-06-02 / T-02-06-03 | Bootstrap routing; picker renders only display_name + sync meta; JSX no innerHTML | build/lint | `cd frontend && npm run build && npm run lint` | ✅ tooling | ⬜ pending |
| 02-06-02 | 06 | 4 | PROF-02 / SYN-02 | T-02-06-01 | Per-profile SSE/search/locate URL by bound id; switch + empty-state | build/lint | `cd frontend && npm run build && npm run lint` | ✅ tooling | ⬜ pending |
| 02-06-03 | 06 | 4 | PROF-02 / SYN-02 | T-02-06-01 | Auto-bind + 2-profile picker + switch + empty-state on running instance (SC#2) | human-verify | manual (checkpoint:human-verify) | n/a | ⬜ pending |
| 02-07-01 | 07 | 5 | PROF-02 / PROF-01 | T-02-07-03 | PROFILES nav + route + list + status badges; JSX no innerHTML | build/lint | `cd frontend && npm run build && npm run lint` | ✅ tooling | ⬜ pending |
| 02-07-02 | 07 | 5 | PROF-02 / PROF-01 | T-02-07-01 / T-02-07-04 | PAT masked + show/hide; friendly error copy (no HTTP codes); 2s poll | build/lint | `cd frontend && npm run build && npm run lint` | ✅ tooling | ⬜ pending |
| 02-07-03 | 07 | 5 | PROF-02 / PROF-01 | T-02-07-01..04 | Full create→connect→test-sync→async-ok loop + errors + delete (SC#1) | human-verify | manual (checkpoint:human-verify) | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/test_migrate_0010.py` — PROF-04 round-trip + NOT-NULL-on-5 + nullable-on-2 + composite PKs
- [ ] `tests/unit/test_cache_registry.py` — API-02 per-profile registry isolation
- [ ] `tests/unit/test_profile_state_registry.py` — SYN-02 per-profile staleness registry
- [ ] `tests/integration/test_profile_manager_api.py` — PROF-02 CRUD + connect + 202/poll + collision + soft-delete
- [ ] `tests/integration/test_sse_per_profile.py` — D2-04 SSE 403/400 + no-cross-profile-leakage
- [ ] `tests/integration/test_session_bootstrap.py` — D2-08 auto-bind + D2-10 cookie independence
- [ ] `tests/conftest.py` — `second_profile` two-profile fixture (SLO + leakage tests)
- [ ] Update `tests/integration/test_sse.py` — `/api/events` → `/api/events/{profile_id}` (done in Plan 02-03)
- [ ] Update `tests/integration/test_search_benchmark.py` — parameterize over a second profile (done in Plan 02-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Single-profile auto-bind skips the picker; 2-profile picker; switch flow; empty-collection affordance | SC#2 / D2-03/07/08/09 | Visual + multi-session browser interaction not expressible in a backend unit test | Plan 02-06 checkpoint:human-verify steps 1–6 |
| Create→connect→test-sync→async-sync-ok loop + friendly error copy + delete-confirm | SC#1 / PROF-02 / D2-12/13 | Visual feedback states (CONNECTING→SYNCING→toast) + drawer UX | Plan 02-07 checkpoint:human-verify steps 1–8 |
| Browse-binding cookie independence + auto-bind on a live instance | D2-08 / D2-10 | curl-level cookie inspection on a running server | Plan 02-04 checkpoint:human-verify steps 1–5 |

---

## Validation Sign-Off

- [x] All tasks have an `<automated>` verify or a human-verify checkpoint with a Wave 0 dependency
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (frontend build/lint covers 02-06/07; human-verify checkpoints are additive, not substitutes)
- [x] Wave 0 covers all MISSING references (RESEARCH §Wave 0 Gaps → Plan 02-00)
- [x] No watch-mode flags (all commands use `--run` / one-shot)
- [x] Feedback latency < 90s (backend unit)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready 2026-05-28

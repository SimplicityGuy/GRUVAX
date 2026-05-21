---
phase: 4
slug: realtime-live-updates
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-21
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `04-RESEARCH.md` § Validation Architecture. Verification is LOCAL (no CI).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Backend framework** | pytest + pytest-asyncio (per `pyproject.toml` `[tool.pytest.ini_options]`) |
| **Frontend framework** | vitest + jsdom + @testing-library/react (per `frontend/vite.config.ts` `test:` block) |
| **Backend quick run** | `pytest tests/ -x -q` |
| **Backend full suite** | `pytest tests/ --cov=gruvax --cov-report=term-missing` |
| **Frontend quick run** | `npm test --run` (from `frontend/`) |
| **Frontend full suite** | `npm test --run --coverage` (from `frontend/`) |
| **Estimated runtime** | ~30–60 seconds (full, both suites) |

Static gates (also local): backend `ruff check .` + `mypy src/`; frontend `npm run lint` + `npm run build`.

---

## Sampling Rate

- **After every task commit:** `pytest tests/unit/test_event_bus.py -x -q` (+ relevant `npm test --run -- <file>` for frontend tasks)
- **After every plan wave:** Full suites — `pytest tests/ -x` + `npm test --run`
- **Before `/gsd:verify-work`:** Full suites green **including** the `<500ms` latency integration test
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Task IDs are placeholders until PLAN.md files exist; the planner/Nyquist auditor binds each row to a concrete task. Mapped by requirement + locked decision from `04-RESEARCH.md`.

| Req / Decision | Behavior | Threat Ref | Test Type | Automated Command | File Exists | Status |
|----------------|----------|------------|-----------|-------------------|-------------|--------|
| ADMN-11 | Admin PUT → kiosk receives `boundary_changed` via SSE ≤500ms | T-04-01 / — | integration | `pytest tests/integration/test_sse.py::test_boundary_changed_latency -x` | ❌ W0 | ⬜ pending |
| RTM-01 | `GET /api/events` yields SSE events; client disconnect unsubscribes queue | — | unit | `pytest tests/unit/test_event_bus.py -x` | ❌ W0 | ⬜ pending |
| RTM-02 | Two concurrent searches complete without serialization | — | integration | `pytest tests/integration/test_sse.py::test_concurrent_searches -x` | ❌ W0 | ⬜ pending |
| RTM-03 | Optimistic admin mutation rolls back on server error | — | frontend unit | `npm test --run -- adminClient` | ❌ W0 | ⬜ pending |
| RTM-04 | `admin_editing` event drives shimmer state (+60s client TTL) | — | frontend unit | `npm test --run -- store` | ❌ W0 | ⬜ pending |
| D-05 | `boundary_changed` invalidates active `['locate', id]` (highlight follows) | — | frontend unit | `npm test --run -- EventSourceConsumer` | ❌ W0 | ⬜ pending |
| D-09 | SSE endpoint holds no pool connection during stream | T-04-02 / — | unit | `pytest tests/unit/test_event_bus.py::test_sse_no_pool_dep -x` | ❌ W0 | ⬜ pending |
| D-11 | Resync invalidates all boundary keys on (re)connect (`onopen`) | — | frontend unit | `npm test --run -- EventSourceConsumer` | ❌ W0 | ⬜ pending |
| Pitfall 8 | SSE response has `X-Accel-Buffering: no` + `Cache-Control: no-store` + 15s ping | T-04-03 / — | integration | `pytest tests/integration/test_sse.py::test_sse_headers -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_event_bus.py` — EventBus subscribe/publish/unsubscribe + slow-subscriber backpressure + `test_sse_no_pool_dep`
- [ ] `tests/integration/test_sse.py` — `test_boundary_changed_latency` (≤500ms), `test_sse_headers`, `test_concurrent_searches`
- [ ] `tests/integration/conftest.py` — `admin_session` fixture (signed cookie + CSRF token) reusing Phase 3 auth helpers; SSE reader helper
- [ ] `frontend/src/__tests__/EventSourceConsumer.test.tsx` — `MockEventSource` stub; asserts `sseConnected`, active-`locate` invalidation (D-05), resync-on-`onopen` (D-11)
- [ ] Frontend store + adminClient tests — shimmer state on `admin_editing` (RTM-04), optimistic rollback (RTM-03)

*All deps already present (`sse-starlette` 3.4.4, TanStack Query 5, Zustand 5) — no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Shimmer + re-glow feel on real hardware | RTM-04 / D-06 | Visual/motion quality; Pi 5 frame budget (Pitfall 16) can't be asserted in jsdom | On the Pi kiosk: open a cube editor on mobile → confirm subtle ambient shimmer on the affected range (no lit-cell recolor); commit → confirm shimmer clears and affected cube re-glows. Watch for jank (target <16ms p95). |
| End-to-end live update over the LAN | ADMN-11 | Real two-device latency feel | Kiosk on Pi + admin on phone, same LAN: edit a boundary → cube re-renders within ~500ms without refresh. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (EventBus + SSE integration + frontend consumer)
- [ ] No watch-mode flags (use `--run` for vitest, `-x` for pytest)
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter (after planner binds task IDs)

**Approval:** pending

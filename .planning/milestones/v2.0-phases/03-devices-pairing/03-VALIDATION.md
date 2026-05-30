---
phase: 3
slug: devices-pairing
status: draft
nyquist_compliant: true
wave_0_complete: false  # flips to true after Wave 0 (03-00) RED scaffolding runs in execute-phase
created: 2026-05-29
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `03-RESEARCH.md` § Validation Architecture. Per-task IDs are linked
> during planning/execution — this draft maps by requirement.
>
> **Note:** `wave_0_complete` stays `false` until plan 03-00 executes during
> `/gsd-execute-phase` — Wave 0 is the RED test scaffolding, which is authored
> at plan time but only *runs* at execution time. `nyquist_compliant: true`
> reflects that every plan task carries an `<automated>` verify and no run of
> three consecutive tasks lacks an automated signal (confirmed by gsd-plan-checker).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3.x (+ playwright/pytest-playwright, dev-only — Wave 0 installs) |
| **Frontend framework** | Vitest 4.x (`vitest run`) + tsc `--noEmit` for fast typecheck |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/unit/test_fingerprint_cookie.py tests/integration/test_devices.py -x -q` |
| **Full suite command** | `pytest tests/ -q --benchmark-skip` |
| **Browser test command** | `pytest tests/browser/test_reboot_persistence.py -x -q` |
| **Estimated runtime** | ~60 seconds (full suite, excluding browser); browser test ~20s |

---

## Sampling Rate

- **After every task commit (backend):** Run `pytest tests/unit/test_fingerprint_cookie.py tests/integration/test_devices.py -x -q`
- **After every task commit (frontend):** Run `cd frontend && npx tsc --noEmit` (sub-10s) plus the task's focused Vitest file
- **After every plan wave:** Run `pytest tests/ -q --benchmark-skip` (and `cd frontend && npm run build && npm run lint` for frontend waves)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds (backend); sub-10s focused (frontend tsc + Vitest)

---

## Per-Task Verification Map

> Task IDs (`3-NN-NN`) linked during planning/execution. Mapped by requirement until then.

| Task ID | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | DEV-01 | T-3-cookie | Fingerprint cookie: HttpOnly + SameSite=Strict + max_age ≥ 30 days (NOT a session cookie) | unit | `pytest tests/unit/test_fingerprint_cookie.py -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-01 | — | `devices` + `pairing_codes` migration round-trip (upgrade → downgrade → upgrade) | integration | `pytest tests/integration/test_migrate_0011.py -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-01 | T-3-reboot | Fingerprint cookie persists across Playwright persistent-context close/reopen | browser | `pytest tests/browser/test_reboot_persistence.py -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-02 | — | Admin bind: valid code → 200 + device row created | integration | `pytest tests/integration/test_devices.py::test_bind_success -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-02 | T-3-bruteforce | Admin bind: rate limit (11th attempt → 429) | integration | `pytest tests/integration/test_devices.py::test_bind_rate_limit -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-02 | T-3-revoke | Revoking a device → next request from that fingerprint → 403 | integration | `pytest tests/integration/test_devices.py::test_revoke_guard -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-02 | — | Profile soft-delete detaches device (sets profile_id NULL → reverts to picker) | integration | `pytest tests/integration/test_devices.py::test_profile_soft_delete_detaches -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | Pairing code generation → unique CHAR(4), 5-min TTL | integration | `pytest tests/integration/test_devices.py::test_generate_code -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | T-3-race | Concurrent bind on same code: first wins, second gets 404 (atomic UPDATE) | integration | `pytest tests/integration/test_devices.py::test_concurrent_bind -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | Kiosk poll (`GET /api/devices/me`): returns state=paired after bind | integration | `pytest tests/integration/test_devices.py::test_me_transitions_to_paired -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | `GET /api/session` returns device_id + paired flag for paired fingerprint | integration | `pytest tests/integration/test_devices.py::test_session_returns_device -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | T-3-revoke | `device_revoked` SSE event published on revoke (revoke half of criterion #3) | integration | `pytest tests/integration/test_devices.py::test_sse_device_revoked -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-02 | — | `device_reassigned` SSE event on the OLD profile channel when admin changes a paired device's profile (reassign half of criterion #3) | integration | `pytest tests/integration/test_devices.py::test_sse_device_reassigned -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | Expired pairing code → 404 (not consumed) | integration | `pytest tests/integration/test_devices.py::test_expired_code -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | `/pair` countdown formats M:SS and auto-rerolls the code on expiry (0:00) | frontend-unit | `cd frontend && npx vitest run src/routes/kiosk/PairView.test.tsx` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | DeviceDrawer NumericKeypad auto-submits bind on the 4th digit | frontend-unit | `cd frontend && npx vitest run src/routes/admin/DeviceDrawer.test.tsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_fingerprint_cookie.py` — cookie attribute contract: HttpOnly + SameSite=Strict + `expires > now + 1 day` (DEV-01)
- [ ] `tests/integration/test_devices.py` — full pairing + bind + revoke + reassign + concurrency + session/poll/SSE (DEV-02, DEV-03) — 11 backend tests (incl. `test_sse_device_reassigned`)
- [ ] `tests/integration/test_migrate_0011.py` — migration 0011 round-trip (DEV-01)
- [ ] `tests/browser/test_reboot_persistence.py` — Playwright persistent-context round-trip (DEV-01, D3-09)
- [ ] `tests/browser/__init__.py` — new test directory needs `__init__.py`
- [ ] `tests/browser/conftest.py` — `live_server` fixture (uvicorn-in-thread vs `create_app`, copied from `tests/integration/test_sse_per_profile.py`) for the Playwright test
- [ ] `frontend/src/routes/kiosk/PairView.test.tsx` — countdown M:SS + auto-reroll-on-expiry (DEV-03)
- [ ] `frontend/src/routes/admin/DeviceDrawer.test.tsx` — NumericKeypad auto-submit-on-4th-digit (DEV-02/DEV-03)
- [ ] `uv add --group dev playwright pytest-playwright` + `playwright install chromium` (verify on Python 3.14 image before locking — see RESEARCH A4)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real RPi reboot returns kiosk to bound profile | DEV-01 / criterion #2 | CI cannot reboot real hardware; Playwright persistent-context is the closest faithful simulation (D3-09) | Pair the kiosk, `sudo reboot`, confirm kiosk auto-loads the bound-profile search UI without re-pairing. Document in `deploy/kiosk/README`. |
| <30s end-to-end pairing UX | DEV-03 / criterion #1 | Wall-clock human-in-the-loop UX timing | Stopwatch: fresh kiosk → code shown → admin enters code + picks profile + labels → kiosk navigates. Confirm < 30s. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (confirmed by gsd-plan-checker)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (RED scaffolding planned in 03-00)
- [x] No watch-mode flags (Vitest uses `vitest run`; pytest one-shot; tsc `--noEmit`)
- [x] Feedback latency < 60s (backend full ~60s; frontend focused sub-10s via tsc + Vitest)
- [x] `nyquist_compliant: true` set in frontmatter
- [ ] Wave 0 actually executed (`wave_0_complete: true`) — *post-execution; flips after 03-00 runs in execute-phase*
- [ ] Full suite green before `/gsd-verify-work` — *post-execution*

**Approval:** pending (planning-time checklist complete; post-execution items remain)

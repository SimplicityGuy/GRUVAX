---
phase: 3
slug: devices-pairing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-29
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `03-RESEARCH.md` § Validation Architecture. Per-task IDs are linked
> during planning/execution — this draft maps by requirement.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x + pytest-asyncio 1.3.x (+ playwright/pytest-playwright, dev-only — Wave 0 installs) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `pytest tests/unit/test_fingerprint_cookie.py tests/integration/test_devices.py -x -q` |
| **Full suite command** | `pytest tests/ -q --benchmark-skip` |
| **Browser test command** | `pytest tests/browser/test_reboot_persistence.py -x -q` |
| **Estimated runtime** | ~60 seconds (full suite, excluding browser); browser test ~20s |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/unit/test_fingerprint_cookie.py tests/integration/test_devices.py -x -q`
- **After every plan wave:** Run `pytest tests/ -q --benchmark-skip`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

> Task IDs (`3-NN-NN`) linked during planning. Mapped by requirement until then.

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
| TBD | DEV-03 | T-3-revoke | `device_revoked` SSE event published on revoke | integration | `pytest tests/integration/test_devices.py::test_sse_device_revoked -x` | ❌ W0 | ⬜ pending |
| TBD | DEV-03 | — | Expired pairing code → 404 (not consumed) | integration | `pytest tests/integration/test_devices.py::test_expired_code -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_fingerprint_cookie.py` — cookie attribute contract: HttpOnly + SameSite=Strict + `expires > now + 1 day` (DEV-01)
- [ ] `tests/integration/test_devices.py` — full pairing + bind + revoke + concurrency + session/poll/SSE (DEV-02, DEV-03)
- [ ] `tests/integration/test_migrate_0011.py` — migration 0011 round-trip (DEV-01)
- [ ] `tests/browser/test_reboot_persistence.py` — Playwright persistent-context round-trip (DEV-01, D3-09)
- [ ] `tests/browser/__init__.py` — new test directory needs `__init__.py`
- [ ] `uv add --group dev playwright pytest-playwright` + `playwright install chromium` (verify on Python 3.14 image before locking — see RESEARCH A4)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real RPi reboot returns kiosk to bound profile | DEV-01 / criterion #2 | CI cannot reboot real hardware; Playwright persistent-context is the closest faithful simulation (D3-09) | Pair the kiosk, `sudo reboot`, confirm kiosk auto-loads the bound-profile search UI without re-pairing. Document in `deploy/kiosk/README`. |
| <30s end-to-end pairing UX | DEV-03 / criterion #1 | Wall-clock human-in-the-loop UX timing | Stopwatch: fresh kiosk → code shown → admin enters code + picks profile + labels → kiosk navigates. Confirm < 30s. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

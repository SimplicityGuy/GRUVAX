---
phase: 8
slug: qr-pairing-privacy-recently-pulled
status: draft
nyquist_compliant: true
wave_0_complete: false  # scaffolds created within plans (Wave-0 tasks)
created: 2026-06-01
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (backend) + vitest (frontend) |
| **Config file** | `pyproject.toml` (pytest) / `frontend/vitest.config.ts` |
| **Quick run command** | `just test` (or `uv run pytest -q` / `cd frontend && npm run test`) |
| **Full suite command** | `just test` |
| **Estimated runtime** | ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run the relevant quick command (backend `uv run pytest -q` or frontend `npm run test`)
- **After every plan wave:** Run `just test`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01 T1 | 01 | 1 | PRIV-02, PRIV-03 | T-08-01/02/03 | Query never logged; uvicorn.access suppressed; no search_log table | integration (pytest) | `uv run pytest tests/integration/test_08_privacy.py -x -q` | ❌ created in plan | ⬜ pending |
| 08-02 T1 | 02 | 1 | DEV-04 | T-08-QR-01/SC | QR renders/encodes code, re-renders on reroll, hidden when paired | unit (vitest) | `npm run test --prefix frontend -- --run PairView` | ❌ extend in plan | ⬜ pending |
| 08-02 T2 | 02 | 1 | DEV-04 | T-08-QR-03/04/05 | Prefill one-tap confirm (no auto-submit, D-04); single `handleBind` bind call site → identical audit (L-03) — DeviceDrawer test asserts `bindDevice` NOT called on mount + called exactly once on confirm | unit (vitest) | `npm run test --prefix frontend -- --run DeviceDrawer DevicesManager` | ❌ DeviceDrawer.test.tsx + DevicesManager.test.tsx created in 08-02 T2 | ⬜ pending |
| 08-03 T1 | 03 | 1 | PRIV-01, SRCH-09 | T-08-PR-01/02 | sessionStorage key, dedupe/cap-8, idle fire/reset | unit (vitest) | `npm run test --prefix frontend -- --run recentlyPulledStore useIdleTimer` | ❌ created in plan | ⬜ pending |
| 08-03 T2 | 03 | 1 | PRIV-04, SRCH-09 | T-08-PR-03/04 | Strip null-when-empty; alertdialog focus trap; ResetConfirmDialog confirm fires `onConfirm` once + ZERO `fetch` (behavioral L-05 gate) | unit (vitest) + lint/build | `npm run test --prefix frontend -- --run ResetConfirmDialog && npm run lint --prefix frontend && npm run build --prefix frontend` | ❌ ResetConfirmDialog.test.tsx created in 08-03 T2 | ⬜ pending |
| 08-03 T3 | 03 | 1 | PRIV-04, SRCH-09 | T-08-PR-03/04 | Reset hidden when admin (D-10); idle/reset clear client-side only; addItem on successful locate AND NOT on no-result locate (D-05 negative case) | unit (vitest) | `npm run test --prefix frontend -- --run KioskView` | ❌ created in plan | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/integration/test_08_privacy.py` — PRIV-02, PRIV-03 (08-01 T1)
- [ ] `frontend/src/state/recentlyPulledStore.test.ts` — PRIV-01, SRCH-09 store (08-03 T1)
- [ ] `frontend/src/hooks/useIdleTimer.test.ts` — SRCH-09 idle semantics (08-03 T1)
- [ ] Extend `frontend/src/routes/kiosk/PairView.test.tsx` — DEV-04 QR render (08-02 T1)
- [ ] `frontend/src/routes/admin/DeviceDrawer.test.tsx` — D-04 no-auto-submit + L-03 single bind call site (08-02 T2)
- [ ] `frontend/src/routes/admin/DevicesManager.test.tsx` — `?code=` prefill opens drawer + strips param (08-02 T2)
- [ ] `frontend/src/routes/kiosk/ResetConfirmDialog.test.tsx` — L-05 zero-fetch on confirm (08-03 T2)

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| QR scan → phone bind flow (end-to-end) | DEV-04 | Requires a physical phone camera scanning the kiosk display | Scan the kiosk QR on a phone, confirm it lands on the PIN-gated bind page prefilled with the code, complete one-tap pairing. (L-03 single-bind-call-site is automated in DeviceDrawer.test.tsx; this manual step is the camera-to-bind end-to-end confirmation only.) |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** planner-populated (per-task map + Wave-0 filled); sign-off at execute time

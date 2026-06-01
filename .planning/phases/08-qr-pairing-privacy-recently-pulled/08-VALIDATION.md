---
phase: 8
slug: qr-pairing-privacy-recently-pulled
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| _populated during planning_ | | | | | | | | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] _populated during planning — test stubs for DEV-04, PRIV-01..04, SRCH-09_

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| QR scan → phone bind flow | DEV-04 | Requires a physical phone camera scanning the kiosk display | Scan the kiosk QR on a phone, confirm it lands on the PIN-gated bind page prefilled with the code, complete one-tap pairing |

*If none: "All phase behaviors have automated verification."*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

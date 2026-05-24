---
phase: 6
slug: led-contract-over-mqtt-hardware-stubbed
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-23
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed validation architecture (invariants, property tests, golden cases) lives in
> `06-RESEARCH.md` §"Validation Architecture" — the planner maps those into the per-task table below.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + Hypothesis (backend); existing harness |
| **Config file** | `pyproject.toml` (pytest config + `pythonpath=[.]`) |
| **Quick run command** | `uv run pytest tests/unit -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~30–60 seconds (backend) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Populated by the planner from `06-RESEARCH.md` §"Validation Architecture". Candidate invariants
> already identified by research (property-testable): payload-schema validity, brightness clamping to
> ceilings, retained-clear idempotency, hot-path non-blocking (publish never raises into /api/illuminate),
> topic-prefix correctness, cube-topic enumeration from `gruvax.units`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| _TBD by planner_ | | | LED-01..10 / DEP-03 | | | unit/property | `uv run pytest ...` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Test stubs for the MQTT publishers (illuminate/span/sub/state/all-off/diagnostic payload builders)
- [ ] Property-test scaffolding (Hypothesis) for payload-schema + brightness-clamp invariants
- [ ] Fakes/fixtures for a stubbed aiomqtt client (assert publish args without a live broker)

*Finalized by the planner against the research's validation architecture.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Retained payloads visible on the broker | LED-08 / DEP-03 | Requires a running broker | `docker compose --profile debug up -d mqtt-explorer` (or `mosquitto_sub -t 'gruvax/v1/dev/leds/#' -v`) and observe payloads |
| Color-blind preview renders correctly | LED-05 (D-18) | Visual perception check | Open the admin LEDs settings section; verify deuteranopia/protanopia/tritanopia swatches |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending

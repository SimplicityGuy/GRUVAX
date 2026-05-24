---
phase: 6
slug: led-contract-over-mqtt-hardware-stubbed
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-23
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed validation architecture (invariants, property tests, golden cases) lives in
> `06-RESEARCH.md` §"Validation Architecture" — mapped into the per-task table below.

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

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01 T1 | 06-01 | 1 | LED-01/02/03/08/09/10 | T-06-01..04 | Wave-0 RED scaffold encodes payload/topic/fan-out/degraded contracts | unit + property | `uv run pytest tests/unit/test_mqtt_publishers.py tests/unit/test_illuminate_endpoint.py tests/property/test_led_brightness.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-01 T2 | 06-01 | 1 | LED-01/02/03/08/10, DEP-03 | T-06-02/03/05 | Pydantic schema validity; expiry props; prefix; clamp; V5 | unit + property | `uv run pytest tests/unit/test_mqtt_publishers.py tests/property/test_led_brightness.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-01 T3 | 06-01 | 1 | LED-09, DEP-03 | T-06-01/04 | fan-out endpoint; degraded returns published:false; 422 on bad body | unit (httpx, mocked mqtt) | `uv run pytest tests/unit/test_illuminate_endpoint.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-02 T1 | 06-02 | 2 | LED-04, LED-05 | T-06-08/11 | Wave-0 RED: color-blind distinguishability + settings persistence/cache | unit | `uv run pytest tests/unit/test_led_color.py tests/unit/test_admin_led_settings.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-02 T2 | 06-02 | 2 | LED-04, LED-05 | T-06-07/08/09/10 | GET/PUT LED keys; hex validation; cache refresh; allow-list | unit (httpx, admin_session) | `uv run pytest tests/unit/test_admin_led_settings.py tests/unit/test_led_color.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-02 T3 | 06-02 | 2 | LED-05 | T-06-11 | color-blind preview component; LEDs section; type-check | build + lint | `cd frontend && npm run build && npx eslint src/components/ColorBlindPreview.tsx src/routes/admin/Settings.tsx` | n/a (build) | ⬜ pending |
| 06-03 T1 | 06-03 | 3 | LED-06, LED-07 | T-06-12..17 | Wave-0 RED: all-off enumeration/idempotency, diagnostic seq, admin-gating, degraded | unit | `uv run pytest tests/unit/test_led_admin_endpoints.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-03 T2 | 06-03 | 3 | LED-06, LED-07 | T-06-15/16/17 | publish_all_off (units-enum, retain-clear); run_diagnostic (seq + status subscribe) | unit (mocked mqtt + pool) | `uv run pytest tests/unit/test_led_admin_endpoints.py -k "all_off or diagnostic or degraded" -x -q` | ✅ (after T1) | ⬜ pending |
| 06-03 T3 | 06-03 | 3 | LED-06, LED-07, DEP-03 | T-06-12/13/14 | admin-gated off + diagnostic endpoints; run_id ack; UI buttons | unit + build | `uv run pytest tests/unit/test_led_admin_endpoints.py -x -q && cd frontend && npm run build` | ✅ (after T1) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Mapped: `tests/unit/test_mqtt_publishers.py` — illuminate/span/sub/state payload builders + fan-out + expiry + prefix + degraded (06-01 T1)
- [x] Mapped: `tests/unit/test_illuminate_endpoint.py` — POST /api/illuminate (httpx + mocked app.state.mqtt; degraded; 422) (06-01 T1)
- [x] Mapped: `tests/property/test_led_brightness.py` — Hypothesis: brightness-clamp invariant + IlluminatePayload validity (06-01 T1)
- [x] Mapped: `tests/unit/test_led_color.py` — hex_to_rgb + color-blind distinguishability (06-02 T1)
- [x] Mapped: `tests/unit/test_admin_led_settings.py` — LED settings GET/PUT persistence + cache refresh (06-02 T1)
- [x] Mapped: `tests/unit/test_led_admin_endpoints.py` — all-off + diagnostic publisher + endpoint (06-03 T1)

Each plan's first task is the Wave-0 RED scaffold for that slice; the GREEN tasks turn it green.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Retained payloads + expiry visible on the broker | LED-08 / DEP-03 / D-12 | Requires a running broker + MQTT5 client | `docker compose up -d`; in mosquitto container `mosquitto_sub -V mqttv5 -t 'gruvax/v1/dev/leds/#' -v`; trigger a kiosk select; observe illuminate/span/sub commands + retained state/* with the expiry property |
| Color-blind preview renders correctly | LED-05 (D-18) | Visual perception check | Open /admin/settings → LEDS; verify deuteranopia/protanopia/tritanopia swatches per color; confirm gold/purple stay distinguishable |
| All-off clears retained ghosts idempotently | LED-06 (D-11) | Requires running broker | Click ALL OFF twice; `mosquitto_sub -t 'gruvax/v1/dev/leds/state/#' -v` shows no retained payloads after |
| Diagnostic cycles every cube + logs | LED-07 (D-08/09/10) | Requires running broker + log inspection | Click RUN DIAGNOSTIC; watch `mosquitto_sub -t 'gruvax/v1/dev/leds/#' -v` cycle + api logs for per-publish lines and the status-subscribe timeout |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (every plan's T1 is the Wave-0 scaffold; T2/T3 reference it)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has an automated command)
- [x] Wave 0 covers all MISSING references (six test files mapped across the three plans)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (ready for execution)

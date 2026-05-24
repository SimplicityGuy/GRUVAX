---
phase: 6
slug: led-contract-over-mqtt-hardware-stubbed
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-23
updated: 2026-05-24
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Detailed validation architecture (invariants, property tests, golden cases) lives in
> `06-RESEARCH.md` §"Validation Architecture" — mapped into the per-task table below.
>
> **Replanned 2026-05-24** for the expanded scope: the original 3-plan set became a 4-plan
> set. The publish spine (06-01), admin colors (now 06-03), and all-off/diagnostic (now 06-04)
> are reorganized; a NEW highlight-lifecycle slice (06-02: idle/ambient baseline + TTL revert +
> retain mode, LED-11/12/13) is inserted as Wave 2. The brightness-tier naming is corrected to
> `led_brightness.span` / `led_brightness.active` / `led_brightness.ambient` (D-24) throughout.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio + Hypothesis (backend); existing harness |
| **Config file** | `pyproject.toml` (pytest config + `pythonpath=[.]`) |
| **Quick run command** | `uv run pytest tests/unit -q` |
| **Full suite command** | `uv run pytest -q` |
| **Estimated runtime** | ~30–60 seconds (backend); lifecycle tests inject a near-zero clock so no real TTL wait |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit -q`
- **After every plan wave:** Run `uv run pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Plan / Wave Map

| Plan | Wave | Depends on | Slice |
|------|------|-----------|-------|
| 06-01 | 1 | — | MQTT 5 publish spine + illuminate fan-out + full settings seed + kiosk wire-up |
| 06-02 | 2 | 06-01 | Highlight lifecycle: idle/ambient baseline + TTL revert registry + retain mode |
| 06-03 | 2 | 06-01 | Admin LED settings (colors incl. ambient, span/active/ambient brightness, TTL, retain) + LEDs UI + color-blind preview |
| 06-04 | 3 | 06-01, 06-02, 06-03 | All-off + diagnostic admin slice |

06-02 and 06-03 share no files and both run in Wave 2 (parallel). 06-04 touches `publishers.py`
(shared with 06-02) and `Settings.tsx` / `adminClient.ts` (shared with 06-03) → Wave 3.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01 T1 | 06-01 | 1 | LED-01/02/03/08/09/10 | T-06-01..04 | Wave-0 RED scaffold encodes payload/topic/fan-out/degraded + D-24 span-tier naming | unit + property | `uv run pytest tests/unit/test_mqtt_publishers.py tests/unit/test_illuminate_endpoint.py tests/property/test_led_brightness.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-01 T2 | 06-01 | 1 | LED-01/02/03/08/10, DEP-03 | T-06-02/03/05 | Pydantic schema validity; expiry props; prefix; clamp; V5; full seed vocabulary | unit + property | `uv run pytest tests/unit/test_mqtt_publishers.py tests/property/test_led_brightness.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-01 T3 | 06-01 | 1 | LED-09, DEP-03 | T-06-01/04 | fan-out endpoint; degraded returns published:false; 422 on bad body | unit (httpx, mocked mqtt) | `uv run pytest tests/unit/test_illuminate_endpoint.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-02 T1 | 06-02 | 2 | LED-11, LED-12, LED-13 | T-06-18..22 | Wave-0 RED: ambient baseline publish, TTL revert (injected delay), default cancel-prior, retain accumulate, registry leak guard | unit (mocked mqtt + pool, injected clock) | `uv run pytest tests/unit/test_led_lifecycle.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-02 T2 | 06-02 | 2 | LED-11, LED-12, LED-13 | T-06-18/19/20 | HighlightRegistry; schedule_revert (injectable sleep); default vs retain branch; publish_ambient | unit (mocked mqtt + pool) | `uv run pytest tests/unit/test_led_lifecycle.py -k "ambient or revert or default_mode or retain or registry or cancel or degraded" -x -q` | ✅ (after T1) | ⬜ pending |
| 06-02 T3 | 06-02 | 2 | LED-11, LED-12 | T-06-22 | /api/illuminate drives lifecycle; lifespan creates registry + ambient baseline + cancels on shutdown | unit (httpx, app import) | `uv run pytest tests/unit/test_led_lifecycle.py tests/unit/test_illuminate_endpoint.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-03 T1 | 06-03 | 2 | LED-04, LED-05 | T-06-08/11 | Wave-0 RED: color-blind distinguishability + settings persistence/cache for ALL led keys + D-24 key separation | unit | `uv run pytest tests/unit/test_led_color.py tests/unit/test_admin_led_settings.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-03 T2 | 06-03 | 2 | LED-04, LED-05 | T-06-07/08/09/10 | GET/PUT all LED keys (colors incl. ambient, span/active/ambient, TTL, retain); hex validation; cache refresh; transition keys excluded | unit (httpx, admin_session) | `uv run pytest tests/unit/test_admin_led_settings.py tests/unit/test_led_color.py -x -q` | ✅ (after T1) | ⬜ pending |
| 06-03 T3 | 06-03 | 2 | LED-05 | T-06-11 | color-blind preview component; LEDs section (6 colors, 3 brightness sliders, TTL, retain); type-check | build + lint | `cd frontend && npm run build && npx eslint src/components/ColorBlindPreview.tsx src/routes/admin/Settings.tsx` | n/a (build) | ⬜ pending |
| 06-04 T1 | 06-04 | 3 | LED-06, LED-07 | T-06-12..17 | Wave-0 RED: all-off enumeration/idempotency, diagnostic seq + correct brightness tiers, admin-gating, degraded | unit | `uv run pytest tests/unit/test_led_admin_endpoints.py -q` | ❌ W0 (creates) | ⬜ pending |
| 06-04 T2 | 06-04 | 3 | LED-06, LED-07 | T-06-15/16/17 | publish_all_off (units-enum, retain-clear); run_diagnostic (seq + span/active tiers + status subscribe) | unit (mocked mqtt + pool) | `uv run pytest tests/unit/test_led_admin_endpoints.py -k "all_off or diagnostic or degraded or brightness_tiers" -x -q` | ✅ (after T1) | ⬜ pending |
| 06-04 T3 | 06-04 | 3 | LED-06, LED-07, DEP-03 | T-06-12/13/14 | admin-gated off + diagnostic endpoints; run_id ack; UI buttons | unit + build | `uv run pytest tests/unit/test_led_admin_endpoints.py -x -q && cd frontend && npm run build` | ✅ (after T1) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Mapped: `tests/unit/test_mqtt_publishers.py` — illuminate/span/sub/state payload builders + fan-out + expiry + prefix + degraded + D-24 span-tier naming guard (06-01 T1)
- [x] Mapped: `tests/unit/test_illuminate_endpoint.py` — POST /api/illuminate (httpx + mocked app.state.mqtt; degraded; 422) (06-01 T1; extended by 06-02 T3)
- [x] Mapped: `tests/property/test_led_brightness.py` — Hypothesis: brightness-clamp invariant + IlluminatePayload validity (06-01 T1)
- [x] Mapped: `tests/unit/test_led_lifecycle.py` — ambient baseline publish, TTL revert (injected delay), default-mode cancel-prior, retain-mode accumulate, registry leak guard, degraded (06-02 T1) — NEW
- [x] Mapped: `tests/unit/test_led_color.py` — hex_to_rgb + color-blind distinguishability (06-03 T1)
- [x] Mapped: `tests/unit/test_admin_led_settings.py` — LED settings GET/PUT persistence + cache refresh for ALL keys (colors incl. ambient, span/active/ambient brightness, TTL, retain) + D-24 span/ambient key separation + transition-keys-not-writable (06-03 T1) — EXTENDED
- [x] Mapped: `tests/unit/test_led_admin_endpoints.py` — all-off + diagnostic publisher + endpoint + correct brightness tiers (06-04 T1)

Each plan's first task is the Wave-0 RED scaffold for that slice; the GREEN tasks turn it green.

---

## New / Changed Tests vs the prior 3-plan set

| Test | Plan | Reason it is new/changed |
|------|------|--------------------------|
| `tests/unit/test_led_lifecycle.py` (whole file) | 06-02 | NEW lifecycle slice (LED-11/12/13): ambient retained baseline on every cube, TTL revert with an injectable delay/clock (no real 180s wait), default-mode next-search-reverts-prior, retain-mode accumulate, registry leak guard + shutdown cancel |
| `test_publish_ambient_writes_retained_state_for_every_cube` | 06-02 | Ambient baseline publish (D-20) |
| `test_revert_republishes_ambient_for_affected_cubes` | 06-02 | TTL revert re-publishes ambient state/* for the affected cubes (D-22), injected clock |
| `test_default_mode_next_search_reverts_prior` | 06-02 | Default mode cancel-prior (D-22) |
| `test_retain_mode_accumulates` | 06-02 | Retain mode accumulate, independent timeouts (D-23) |
| `test_cancel_and_revert_all_clears_registry` | 06-02 | Shutdown leak guard |
| `test_span_brightness_uses_span_tier` | 06-01 | D-24 rename: span payload clamps to `led_brightness.span`, NOT `led_brightness.ambient` |
| `test_admin_led_settings` extended for ambient/TTL/retain keys | 06-03 | D-25 new keys: `led_color.ambient`, `led_brightness.ambient`, `led_brightness.span` (rename), `led_highlight.active_ttl_seconds`, `led_highlight.retain_mode`, `led_highlight.retain_ttl_seconds` |
| `test_span_brightness_key_is_span_not_ambient` | 06-03 | D-24 two-distinct-keys guard at the settings layer |
| `test_transition_keys_not_writable` | 06-03 | D-17 transition keys excluded from the writable allow-list |
| `test_diagnostic_uses_correct_brightness_tiers` | 06-04 | D-24: diagnostic active sequence uses span/active tiers, never the idle ambient tier |
| seed migration `0006` extended | 06-01 T2 | Seeds the FULL vocabulary incl. ambient color/brightness + TTL/retain so 06-02/06-03 read keys that already exist (D-25) |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Retained payloads + expiry visible on the broker | LED-08 / DEP-03 / D-12 | Requires a running broker + MQTT5 client | `docker compose up -d`; in mosquitto container `mosquitto_sub -V mqttv5 -t 'gruvax/v1/dev/leds/#' -v`; trigger a kiosk select; observe illuminate/span/sub commands + retained state/* with the expiry property |
| Idle/ambient baseline on every cube at startup | LED-11 / D-20 | Requires a running broker | `mosquitto_sub -t 'gruvax/v1/dev/leds/state/#' -v`; on `docker compose up` observe ambient retained state/* on every cube |
| Timed revert to ambient (TTL or next-search) | LED-12 / D-21/D-22 | Requires a running broker + a wall-clock wait OR a lowered TTL | Set `led_highlight.active_ttl_seconds` low in admin; trigger a kiosk select; after the TTL the cubes revert to ambient; trigger a second search before the TTL → the first reverts immediately, the second lights |
| Retain mode accumulates a recently-found trail | LED-13 / D-23 | Requires a running broker | Flip `led_highlight.retain_mode` true in admin; two searches → both stay lit; each reverts on its own `led_highlight.retain_ttl_seconds` |
| Color-blind preview renders correctly | LED-05 / D-18 | Visual perception check | Open /admin/settings → LEDS; verify deuteranopia/protanopia/tritanopia swatches per color; confirm gold/purple stay distinguishable |
| All-off clears retained ghosts idempotently | LED-06 / D-11 | Requires a running broker | Click ALL OFF twice; `mosquitto_sub -t 'gruvax/v1/dev/leds/state/#' -v` shows no retained payloads after |
| Diagnostic cycles every cube + logs | LED-07 / D-08/09/10 | Requires a running broker + log inspection | Click RUN DIAGNOSTIC; watch `mosquitto_sub -t 'gruvax/v1/dev/leds/#' -v` cycle + api logs for per-publish lines and the status-subscribe timeout |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (every plan's T1 is the Wave-0 scaffold; T2/T3 reference it)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has an automated command)
- [x] Wave 0 covers all MISSING references (seven test files mapped across the four plans)
- [x] Lifecycle tests inject a near-zero clock — no real TTL wait in CI (D-22 testability)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** planned (ready for execution — 4-plan set, expanded scope)

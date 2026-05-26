---
status: complete
phase: 06-led-contract-over-mqtt-hardware-stubbed
source: [06-VERIFICATION.md]
started: "2026-05-24T00:00:00Z"
updated: 2026-05-26T00:00:00Z
resolution: deferred-to-hardware-milestone
resolution_at: 2026-05-26T00:00:00Z
---

## Current Test

[deferred to hardware milestone — 2026-05-26]

All 6 items below verify MQTT 5 wire-level contract behavior that requires a live Mosquitto broker and an MQTT 5 inspector (e.g., `mosquitto_sub -V mqttv5 -t '#' -v` or MQTT Explorer). Per the v1.0-MILESTONE-AUDIT.md recommendation #5, they are formally accepted as hardware/visual acceptance deferred to the hardware milestone — they verify wire-level contract details, not shipped software behavior. The 12/12 code-side must-haves on Phase 6 (covered by `06-VERIFICATION.md`) are all passing.

## Tests

### 1. Wire-level MQTT 5 property encoding
expected: Retained `state/*` publishes carry MessageExpiryInterval (default 4h, configurable); command topics use QoS 0 retain=false, state topics QoS 1 retain=true. Inspect with MQTT Explorer against the internal broker.
result: deferred
resolution: deferred-to-hardware-milestone
reason: requires live Mosquitto broker + MQTT 5 wire inspection; software code-side verified in 06-VERIFICATION.md

### 2. Span brightness above 128 reaches the wire (CR-02 fix)
expected: With `led_brightness.span` set to e.g. 200 in admin Settings, the published span payload brightness is 200 (not silently capped at 128).
result: deferred
resolution: deferred-to-hardware-milestone
reason: requires live Mosquitto broker + MQTT 5 wire inspection; software code-side verified in 06-VERIFICATION.md

### 3. Diagnostic restores ambient baseline (CR-04 fix)
expected: After running the admin "Run Diagnostic" sweep, every cube's `state/*` topic shows the configured ambient color/brightness (cubes are NOT left dark).
result: deferred
resolution: deferred-to-hardware-milestone
reason: requires live Mosquitto broker + MQTT 5 wire inspection; software code-side verified in 06-VERIFICATION.md

### 4. TTL revert timing
expected: An active highlight illuminates for the configured TTL (default 3 min) or until the next search, then a server-scheduled revert restores ambient. Retain mode (when enabled) accumulates a trail, each entry reverting independently after the longer timeout (default 15 min).
result: deferred
resolution: deferred-to-hardware-milestone
reason: requires live Mosquitto broker + MQTT 5 wire inspection; software code-side verified in 06-VERIFICATION.md

### 5. "All off" idempotency
expected: Repeated "All off" calls publish `retain=True payload=b''` on `gruvax/v1/leds/all` + per-cube `state/*` clears with no error and a stable end-state (all retained LED state cleared).
result: deferred
resolution: deferred-to-hardware-milestone
reason: requires live Mosquitto broker + MQTT 5 wire inspection; software code-side verified in 06-VERIFICATION.md

### 6. Concurrent diagnostic guard (CR-03 fix)
expected: Triggering a second diagnostic while one is running does not double-drain the shared `client.messages` queue; the second run logs a warning and skips the status-subscribe window.
result: deferred
resolution: deferred-to-hardware-milestone
reason: requires live Mosquitto broker + MQTT 5 wire inspection; software code-side verified in 06-VERIFICATION.md

## Summary

total: 6
passed: 0
issues: 0
pending: 0
skipped: 0
blocked: 0
deferred: 6
note: All 6 items formally deferred to the hardware milestone per v1.0-MILESTONE-AUDIT.md recommendation #5 — they require a live Mosquitto broker + MQTT 5 wire inspection. The 12/12 code-side must-haves on Phase 6 (06-VERIFICATION.md) all pass.

## Gaps

---
status: partial
phase: 06-led-contract-over-mqtt-hardware-stubbed
source: [06-VERIFICATION.md]
started: "2026-05-24T00:00:00Z"
updated: "2026-05-24T00:00:00Z"
---

## Current Test

[awaiting human testing — requires a live Mosquitto broker; these are the "hardware-stubbed" boundary items]

## Tests

### 1. Wire-level MQTT 5 property encoding
expected: Retained `state/*` publishes carry MessageExpiryInterval (default 4h, configurable); command topics use QoS 0 retain=false, state topics QoS 1 retain=true. Inspect with MQTT Explorer against the internal broker.
result: [pending]

### 2. Span brightness above 128 reaches the wire (CR-02 fix)
expected: With `led_brightness.span` set to e.g. 200 in admin Settings, the published span payload brightness is 200 (not silently capped at 128).
result: [pending]

### 3. Diagnostic restores ambient baseline (CR-04 fix)
expected: After running the admin "Run Diagnostic" sweep, every cube's `state/*` topic shows the configured ambient color/brightness (cubes are NOT left dark).
result: [pending]

### 4. TTL revert timing
expected: An active highlight illuminates for the configured TTL (default 3 min) or until the next search, then a server-scheduled revert restores ambient. Retain mode (when enabled) accumulates a trail, each entry reverting independently after the longer timeout (default 15 min).
result: [pending]

### 5. "All off" idempotency
expected: Repeated "All off" calls publish `retain=True payload=b''` on `gruvax/v1/leds/all` + per-cube `state/*` clears with no error and a stable end-state (all retained LED state cleared).
result: [pending]

### 6. Concurrent diagnostic guard (CR-03 fix)
expected: Triggering a second diagnostic while one is running does not double-drain the shared `client.messages` queue; the second run logs a warning and skips the status-subscribe window.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps

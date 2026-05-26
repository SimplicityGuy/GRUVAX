---
phase: 06-led-contract-over-mqtt-hardware-stubbed
plan: 01
subsystem: mqtt-publish-spine
tags: [mqtt, led, publish, schemas, fire-and-forget, tdd]
dependency_graph:
  requires: []
  provides:
    - gruvax.mqtt.topics (prefix-aware topic builders)
    - gruvax.mqtt.schemas (documented Pydantic payload models)
    - gruvax.mqtt.publishers (fan_out_illuminate, safe_publish, clamp_brightness)
    - POST /api/illuminate (public fire-and-forget endpoint)
    - LED settings vocabulary seeded (0006 migration)
  affects:
    - src/gruvax/mqtt/client.py (ProtocolVersion.V5 upgrade)
    - src/gruvax/settings.py (MQTT_TOPIC_PREFIX, MQTT_STATE_EXPIRY_SECONDS)
    - src/gruvax/app.py (illuminate_router registration)
    - frontend/src/api/client.ts (illuminateRecord export)
    - frontend/src/routes/kiosk/ResultsList.tsx (illuminate after locate)
tech_stack:
  added: []
  patterns:
    - aiomqtt 2.5.1 native timeout kwarg (no asyncio.wait_for)
    - paho MQTT 5 Properties (MessageExpiryInterval) for retained state/*
    - asyncio.gather for concurrent command topic publish
    - asyncio.create_task fire-and-forget from FastAPI endpoint
    - Pydantic v2 model_config populate_by_name + Field(alias=) for schema key
key_files:
  created:
    - src/gruvax/mqtt/topics.py
    - src/gruvax/mqtt/schemas.py
    - src/gruvax/mqtt/publishers.py
    - src/gruvax/api/illuminate.py
    - migrations/versions/0006_led_settings_seed.py
    - tests/unit/test_mqtt_publishers.py
    - tests/unit/test_illuminate_endpoint.py
    - tests/property/test_led_brightness.py
  modified:
    - src/gruvax/mqtt/client.py
    - src/gruvax/settings.py
    - src/gruvax/app.py
    - frontend/src/api/client.ts
    - frontend/src/routes/kiosk/ResultsList.tsx
decisions:
  - "fan_out_illuminate uses asyncio.gather for concurrent command publish then sequential state/* retained publishes"
  - "aiomqtt native timeout kwarg used (not asyncio.wait_for) per RESEARCH Pitfall F"
  - "led_brightness.span used for label-span tier per D-24 naming contract"
  - "IlluminatePayload uses schema_ with Field(alias='schema') and populate_by_name=True"
metrics:
  duration_minutes: 19
  completed_date: "2026-05-24"
  tasks_completed: 3
  files_created: 8
  files_modified: 5
---

# Phase 6 Plan 01: MQTT 5 Publish Spine + LED Contract Summary

MQTT 5 publish spine implemented end-to-end: topic builders, documented Pydantic payload schemas (gruvax.illuminate.v1 / gruvax.span.v1 / gruvax.sub_interval.v1), fan_out_illuminate publisher with concurrent command publish and retained state/* with MessageExpiryInterval, public /api/illuminate endpoint, full LED settings vocabulary seeded in migration 0006, and kiosk fire-and-forget illuminate after locate.

## Tasks Completed

| Task | Description | Commit | Key Files |
|------|-------------|--------|-----------|
| 1 | Wave-0 RED scaffold — publisher + endpoint + brightness property tests | ddb20e5 | tests/unit/test_mqtt_publishers.py, tests/unit/test_illuminate_endpoint.py, tests/property/test_led_brightness.py |
| 2 | MQTT 5 spine — topics, schemas, publishers, client V5, settings, seed migration (GREEN) | 759e169 | src/gruvax/mqtt/topics.py, schemas.py, publishers.py, client.py, settings.py, migrations/versions/0006_led_settings_seed.py |
| 3 | Public /api/illuminate endpoint + kiosk fire-and-forget wire-up (GREEN) | ab6f969 | src/gruvax/api/illuminate.py, src/gruvax/app.py, frontend/src/api/client.ts, frontend/src/routes/kiosk/ResultsList.tsx |

## What Was Built

### MQTT Topic Builders (src/gruvax/mqtt/topics.py)
Pure functions for all LED topic types: `illuminate_topic`, `span_topic`, `sub_topic`, `state_topic`, `all_off_topic`, `diagnostic_topic`, `status_wildcard`. All prefix-aware via `settings.MQTT_TOPIC_PREFIX` (D-14).

### Payload Schemas (src/gruvax/mqtt/schemas.py)
Documented Pydantic v2 BaseModel contracts living in the repo alongside topic builders (SC4/LED-08):
- `RGBColor` with field validators clamping channels to 0..255 (T-06-02)
- `TransitionSpec` with Literal style constraint
- `IlluminatePayload` (schema alias: "gruvax.illuminate.v1")
- `SubIntervalPayload` (schema alias: "gruvax.sub_interval.v1")
- `SpanPayload` (schema alias: "gruvax.span.v1")

### Publisher Spine (src/gruvax/mqtt/publishers.py)
- `hex_to_rgb` / `clamp_brightness` utilities
- `_make_expiry_props` using paho Properties(PacketTypes.PUBLISH).MessageExpiryInterval (D-12)
- `safe_publish` with native aiomqtt timeout kwarg (no asyncio.wait_for — Pitfall F)
- `fan_out_illuminate`: resolves presentation settings from settings_cache, builds payloads, publishes three command topics concurrently via asyncio.gather (QoS 0, retain=False), then publishes retained state/* with expiry (QoS 1, retain=True). Degraded mode (client=None) logs and returns without raising (D-01).

### MQTT 5 Client Upgrade (src/gruvax/mqtt/client.py)
Added `protocol=ProtocolVersion.V5` to aiomqtt.Client constructor so paho Properties are wire-encoded (D-12).

### Settings Knobs (src/gruvax/settings.py)
Added `MQTT_TOPIC_PREFIX: str = "gruvax/v1/dev/leds"` and `MQTT_STATE_EXPIRY_SECONDS: int = 14400` (D-14, D-12).

### Seed Migration 0006 (migrations/versions/0006_led_settings_seed.py)
Seeds 17 keys covering the full LED presentation vocabulary:
- `led_color.*` (position, label_span, error, setup, all_off, ambient)
- `led_brightness.span` (label-span tier, 128 — D-24), `led_brightness.active` (255), `led_brightness.ambient` (40 — idle)
- `led_transition.*` (position/span style + duration)
- `led_highlight.*` (active_ttl_seconds=180, retain_mode=false, retain_ttl_seconds=900)

ON CONFLICT DO NOTHING so 06-02/06-03/06-04 read keys that already exist (D-25).

### Public Endpoint (src/gruvax/api/illuminate.py)
`POST /api/illuminate` accepts IlluminateRequest (LocateResult shape), schedules fan_out_illuminate via asyncio.create_task, returns `{"published": true/false, "accepted_at": ...}`. No require_admin (D-03). Pydantic validates body → 422 on malformed (T-06-01).

### Kiosk Integration (frontend/)
- `client.ts`: `illuminateRecord(result)` — plain fetch, no adminFetch/CSRF (D-03)
- `ResultsList.tsx`: `void illuminateRecord(result).catch(() => {})` after setLocateResult in both auto-top-result effect and tap-to-select handler

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/unit/test_mqtt_publishers.py | 9 | PASS |
| tests/unit/test_illuminate_endpoint.py | 3 | PASS |
| tests/property/test_led_brightness.py | 2 | PASS |
| Full unit + property suite | 208 | PASS (no regressions) |

### TDD Gate Compliance

- RED gate: `ddb20e5` — `test(06-01)` commit with 14 failing tests
- GREEN gate: `759e169` + `ab6f969` — `feat(06-01)` commits making tests pass

## Deviations from Plan

None — plan executed exactly as written.

## Threat Flags

No new threat surface beyond what the plan's threat model documented. Verified:
- T-06-01: Pydantic IlluminateRequest validates → 422 on malformed body
- T-06-02: RGBColor field validators clamp channels to 0..255
- T-06-03: Topics built from validated ints via topics.py builders
- T-06-04: asyncio.create_task + native timeout=0.25; degraded mode returns published=false
- T-06-05: MQTT_TOPIC_PREFIX env split implemented
- T-06-06: DEP-03 confirmed — mosquitto has no host ports in compose.yaml, persistence on (mosquitto-data volume)

## Known Stubs

None — all functionality implemented. The MQTT publish path produces real payloads; the broker connection is best-effort (degraded mode is expected behavior, not a stub).

## Self-Check: PASSED

---
phase: 06
slug: led-contract-over-mqtt-hardware-stubbed
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-23
---

# Phase 06 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| kiosk browser → POST /api/illuminate | Unauthenticated client-supplied LocateResult body | Untrusted JSON (unit_id, row, col, sub_interval) |
| admin browser → PUT /api/admin/settings | Authenticated admin (session + CSRF) writing LED config | LED hex color, brightness int, TTL int, retain bool |
| admin browser → POST /api/admin/leds/{off,diagnostic} | Authenticated admin (session + CSRF) triggering broker fan-out | No body |
| gruvax-api → Mosquitto broker | Internal Compose network only; no host port | MQTT payloads (IlluminatePayload, SpanPayload, SubIntervalPayload, state/*) |
| in-process revert registry (app.state) | Server-owned asyncio tasks scheduling ambient reverts | cubes list, TTL int |
| gruvax-api → Mosquitto (status/#) | Transient subscribe during diagnostic only | Firmware status messages (none in v1) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-06-01 | Tampering | POST /api/illuminate body | mitigate | `IlluminateRequest(BaseModel)` at `illuminate.py:63`; Pydantic rejects malformed bodies → HTTP 422 automatically | closed |
| T-06-02 | Tampering | RGBColor / brightness fields | mitigate | `RGBColor.clamp_channel` field_validator at `schemas.py:40–44` clamps r/g/b to [0,255]; `clamp_brightness` at `publishers.py:72–82` bounds all brightness values | closed |
| T-06-03 | Tampering | Topic string from client input | mitigate | All topics built via pure int-keyed functions in `topics.py:26–88`; client-supplied unit_id/row/col are validated ints from the Pydantic model before reaching any topic builder | closed |
| T-06-04 | DoS | Broker hiccup blocking /api/illuminate | mitigate | `_spawn()` at `illuminate.py:47–60` fires coroutine via `asyncio.create_task` with strong-reference set (CR-01); `safe_publish` uses native `timeout=0.25` at `publishers.py:104–137`; degraded mode (client=None) returns `published:false` without raising | closed |
| T-06-05 | Tampering | Dev retained topics polluting prod | mitigate | `MQTT_TOPIC_PREFIX: str = "gruvax/v1/dev/leds"` at `settings.py:34`; applied via `settings.MQTT_TOPIC_PREFIX` at every `topics.*_topic()` call in `publishers.py:167,400,544,651` | closed |
| T-06-06 | Info Disclosure | Broker exposed to LAN | accept | No `ports:` directive on the `mosquitto` service block in `compose.yaml:123–143`; broker is reachable only on the `internal` Compose network. Persistence enabled (`persistence true`, `persistence_location /mosquitto/data/` at `mosquitto/mosquitto.conf:5–6`). See Accepted Risks Log. | closed |
| T-06-07 | Elevation of Privilege | PUT /api/admin/settings (LED keys) | mitigate | `Depends(require_admin)` at `admin/settings.py:175`; covers session + CSRF verification (inherited from Phase 3) | closed |
| T-06-08 | Tampering | LED color hex value | mitigate | `_HEX_COLOR_RE = re.compile(r'^#[0-9A-Fa-f]{6}$')` at `admin/settings.py:61`; validated for all color keys before write at `admin/settings.py:216–229`; raises HTTP 422 on malformed input | closed |
| T-06-09 | Tampering | Brightness / TTL out of range | mitigate | `_BRIGHTNESS_KEYS` frozenset at `admin/settings.py:95–99`; range check `0 <= int_value <= 255` with HTTP 422 at `admin/settings.py:244–252` (WR-03 fix); TTL stored as bare integer JSON | closed |
| T-06-10 | Tampering | Non-whitelisted settings key write | mitigate | `_ALLOWED_SETTINGS_KEYS` frozenset at `admin/settings.py:39–58`; `key_map` allow-list at `admin/settings.py:191–210`; `led_transition.*` keys deliberately absent (D-17); unknown body keys are silently skipped by the `if body_key not in body: continue` loop | closed |
| T-06-11 | Info Disclosure | Inaccessible color pair chosen by admin | mitigate | `simulateColorBlindness()` zero-dep matrix math at `frontend/src/lib/colorblind.ts:41–57`; `ColorBlindPreview` component at `frontend/src/components/ColorBlindPreview.tsx:33–52` renders deutan/protan/tritan swatches next to every color picker in the admin LEDs section | closed |
| T-06-12 | Elevation of Privilege | POST /api/admin/leds/{off,diagnostic} | mitigate | `Depends(require_admin)` at `admin/leds.py:41` (leds_all_off) and `admin/leds.py:66` (start_diagnostic) | closed |
| T-06-13 | CSRF | All-off / diagnostic POST | mitigate | `ledsAllOff()` and `ledsDiagnostic()` in `frontend/src/api/adminClient.ts:544,561` call `adminFetch`, which attaches `X-CSRF-Token` header for all mutating requests at `adminClient.ts:65–69` (double-submit cookie pattern) | closed |
| T-06-14 | DoS | Diagnostic blocking event loop | mitigate | `background_tasks.add_task(publishers.run_diagnostic, ...)` at `admin/leds.py:85–91` returns `run_id` immediately; `await asyncio.sleep(inter_cube_delay_s)` at `publishers.py:765` yields between cubes | closed |
| T-06-15 | DoS | Broker hiccup during all-off | mitigate | `asyncio.gather(*clear_tasks, return_exceptions=True)` at `publishers.py:573`; each clear task calls `safe_publish` which swallows exceptions; degraded mode returns 0 at `publishers.py:539–542` | closed |
| T-06-16 | Info Disclosure | Diagnostic subscribe too broad | mitigate | Subscribe only to `status_wildcard(prefix)` (= `{prefix}/status/#`) at `publishers.py:792`; disjoint from `illuminate/*`; CR-03 concurrency guard `client._gruvax_diag_active` at `publishers.py:784,794,808` prevents two concurrent diagnostics from racing on the shared `client.messages` iterator | closed |
| T-06-17 | Tampering | Stale retained ghosts on hardware boot | mitigate | `publish_all_off` publishes `b''` with `retain=True, qos=1` to every `state/*` topic at `publishers.py:563–568`; empty retained payload is the MQTT protocol mechanism for deleting retained messages (D-11) | closed |
| T-06-18 | DoS | Revert-task registry unbounded growth | mitigate | `schedule_revert` pops its own entry in `finally` at `lifecycle.py:167–168`; default mode cancels+pops prior entries at `lifecycle.py:237–255`; `_RETAIN_MODE_MAX_HIGHLIGHTS = 64` hard cap with oldest-first eviction at `lifecycle.py:74,261–282` (WR-02 fix); `cancel_and_revert_all` empties registry at shutdown | closed |
| T-06-19 | DoS | Rapid illuminate calls spawning unbounded tasks | mitigate | Default mode (`retain_mode=false`) iterates `registry.items()` and cancels all prior tasks at `lifecycle.py:237–255` before scheduling the new one — at most one active task in default mode; retain mode bounded by TTL expiry and the hard cap of 64 | closed |
| T-06-20 | DoS | Broker hiccup during revert blocking loop | mitigate | `publish_ambient` uses `asyncio.gather(*publish_coros, return_exceptions=True)` at `publishers.py:490`; each slot calls `safe_publish` with `timeout=0.5`; `client=None` guard at `publishers.py:394–398` short-circuits without raising | closed |
| T-06-21 | Tampering | TTL/retain values forced out of range | mitigate | TTL parsed via `int(str(ttl_raw).strip('"'))` with `except (ValueError, TypeError)` fallback at `lifecycle.py:301–308`; retain_mode parsed with string-lower comparison at `lifecycle.py:214–219`; settings writes are admin-gated + brightness range-validated (T-06-09) | closed |
| T-06-22 | Denial of teardown | Pending tasks surviving shutdown | mitigate | `cancel_and_revert_all(registry, mqtt, settings_cache)` called in lifespan teardown at `app.py:211–217` inside `try/except`; cancels every registered task and empties the registry | closed |
| T-06-SC | Tampering (supply chain) | npm/pip/cargo installs | mitigate | No new Python packages added (aiomqtt/paho pre-existing at `pyproject.toml:11`); `frontend/src/lib/colorblind.ts` is zero-dep pure matrix math with no `import` statements; no new npm packages introduced | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-06 | Mosquitto broker has no TLS and uses `allow_anonymous true` in dev. Mitigated by zero host port exposure — broker is reachable only on the internal Compose network (`networks: internal` in compose.yaml, confirmed no `ports:` block on the mosquitto service). Production deployment is on a home LAN with no public exposure. Single-user app; no per-device credentials in v1. Risk accepted per DEP-03. A passwd file stub is commented in compose.yaml and mosquitto.conf for the hardware milestone when ESP32s join the network. | Robert Wlodarczyk | 2026-05-23 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Threat Flags

The `## Threat Flags` sections of all four SUMMARYs (06-01 through 06-04) reported no new attack surface beyond what the per-plan threat models documented. Each summary explicitly mapped its flags back to the registered threat IDs. No unregistered flags were found.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-23 | 23 | 23 | 0 | gsd-security-auditor (Claude Sonnet 4.6) |

Post-review fixes applied before audit (from 06-REVIEW-FIX.md):
- CR-01: strong-reference set for fire-and-forget tasks (illuminate.py + app.py)
- CR-02: span brightness ceiling corrected from 128 to 255 in publishers.py
- CR-03: per-client `_gruvax_diag_active` concurrency guard in run_diagnostic
- CR-04: `publish_ambient` called at end of run_diagnostic (ambient baseline restored)
- WR-01: settings_cache mutated in-place (clear+update) instead of rebound
- WR-02: `_RETAIN_MODE_MAX_HIGHLIGHTS = 64` hard cap with oldest-first eviction
- WR-03: brightness range validation [0,255] with HTTP 422 on PUT /settings
- WR-04: response field semantics documented; `accepted` alias added
- WR-05: DB enumeration in publish_ambient wrapped in try/except
- WR-06: test helper sets highlight_registry for correct lifecycle coverage
- WR-07: pool=None guard added to run_diagnostic
- WR-09: inter_cube_ms clamped to [0,2000] with ValueError fallback

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-23

# Phase 6: LED Contract over MQTT (Hardware Stubbed) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-23
**Phase:** 6-LED Contract over MQTT (Hardware Stubbed)
**Areas discussed:** Publish trigger & hot path, Color & brightness model, Diagnostic & all-off, Retain hygiene & env prefix, Transitions & admin LED UI

---

## Publish trigger & hot path

### How should a kiosk select cause an MQTT publish?
| Option | Description | Selected |
|--------|-------------|----------|
| POST /api/illuminate | Kiosk POSTs after select; /api/locate stays pure CPU; fire-and-forget 250 ms timeout | ✓ |
| Auto-publish inside /api/locate | One fewer round-trip but couples read to side effect, risks 50 ms budget | |

### LED-09 layered command — how does one call carry span + position?
| Option | Description | Selected |
|--------|-------------|----------|
| Server fans out to 3 topics | One request → illuminate + span + sub per locked topic tree | ✓ |
| Single composite topic+payload | One nested payload; diverges from locked topic tree | |

### What does the kiosk send in the body?
| Option | Description | Selected |
|--------|-------------|----------|
| The LocateResult it already has | Reuse the estimate from the preceding /api/locate; server resolves + fans out | ✓ |
| Minimal {release_id}; server re-locates | Server recomputes; duplicates locate work | |

**User's choice:** All recommended.
**Notes:** /api/illuminate is public/unauthenticated per ARCHITECTURE; client-provided LocateResult must still validate against the Pydantic contract.

---

## Color & brightness model

### Separate vs shared palette (UI vs LEDs)?
| Option | Description | Selected |
|--------|-------------|----------|
| Separate palettes | Kiosk UI keeps Nordic Grid (lit=yellow); LEDs get own tunable palette | ✓ |
| Shared palette drives both | Forces recoloring lit cells (violates design language) or yellow LEDs (loses Pitfall 18) | |

### How much color freedom for the admin?
| Option | Description | Selected |
|--------|-------------|----------|
| Free picker + safe defaults & presets | Per-state picker, seeded gold/purple, design-token presets, custom hex allowed | ✓ |
| Constrained to design tokens only | Simplest/consistent but can't honor Pitfall 18 | |
| Free picker, no presets | Max freedom, no guardrails | |

### Color encoding in payload?
| Option | Description | Selected |
|--------|-------------|----------|
| Resolved RGB server-side | Firmware dumb; admin changes need no firmware update | ✓ |
| color_name token; firmware resolves | Smaller payloads; pushes palette to firmware | |

### Brightness ceilings (LED-04)?
| Option | Description | Selected |
|--------|-------------|----------|
| Two ceilings, server clamps every payload | Ambient ~30-50%, active 100%; brightness-as-information | ✓ |
| Single global ceiling | Simpler; loses span-vs-primary brightness signal | |

**User's choice:** All recommended.
**Notes:** Separate-palette choice is the deliberate resolution of the design-language vs Pitfall 18 tension.

---

## Diagnostic & all-off

### Diagnostic execution model?
| Option | Description | Selected |
|--------|-------------|----------|
| Background task, returns run_id immediately | Instant ack; sequence publishes in background | ✓ |
| Synchronous, blocks until done | Simpler but UI hangs for sequence length | |

### Diagnostic content (no hardware)?
| Option | Description | Selected |
|--------|-------------|----------|
| Cycle each cube through state colors | Exercises full color contract + every topic; mosquitto_sub-verifiable | ✓ |
| Simple all-on white → all-off | Minimal smoke test | |

### "Log status responses" with no v1 status publisher?
| Option | Description | Selected |
|--------|-------------|----------|
| Subscribe to status/# during run, log what arrives | Wires future hardware status seam now | ✓ |
| No subscription; only log publishes | Simpler; seam deferred to hardware milestone | |

### All-off behavior (LED-06)?
| Option | Description | Selected |
|--------|-------------|----------|
| Clear retained state/* + all/off, idempotent | Pitfall 3 idiom; clears ghosts | ✓ |
| Publish an 'off' command only | Leaves retained state → ghost cubes on hardware boot | |

**User's choice:** All recommended.

---

## Retain hygiene & env prefix

### message_expiry for retained state/*?
| Option | Description | Selected |
|--------|-------------|----------|
| 4h default, configurable | ARCHITECTURE / Pitfall 3 default; broker auto-drops stale | ✓ |
| Shorter (1h) | More aggressive cleanup | |
| No expiry | Max ghost risk; rejected | |

### Does v1 stub publish retained state/*?
| Option | Description | Selected |
|--------|-------------|----------|
| Yes, publish state/* now | Costs nothing; hardware milestone works without API change | ✓ |
| No, defer to hardware milestone | Less dev junk; adds a future contract change | |

### Dev vs prod topic separation?
| Option | Description | Selected |
|--------|-------------|----------|
| MQTT_TOPIC_PREFIX env | gruvax/v1/dev vs gruvax/v1; dev junk never pollutes prod | ✓ |
| Single prefix everywhere | Simpler; cross-contamination risk | |

### Where do LED settings live?
| Option | Description | Selected |
|--------|-------------|----------|
| Topology in env, presentation in DB | host/creds/prefix/expiry in env; colors/brightness/transitions in gruvax.settings | ✓ |
| Everything in gruvax.settings DB | All runtime-editable; admin could break topology | |
| Everything in env | Immutable; colors not admin-tunable (violates LED-05) | |

**User's choice:** All recommended.

---

## Transitions & admin LED UI

### LED-10 transition defaults?
| Option | Description | Selected |
|--------|-------------|----------|
| Per-state defaults | primary=pulse, span=fade, all-off=instant; motion as info channel | ✓ |
| Single global default (fade 250 ms) | Uniform; loses primary-vs-span motion signal | |
| Always instant | Minimal | |

### Transitions admin-editable in v1?
| Option | Description | Selected |
|--------|-------------|----------|
| Fixed defaults, schema supports override | No editor UI; effect not observable without firmware | ✓ |
| Admin-editable now | UI for a stubbed-only effect | |

### Color-blind preview now or defer?
| Option | Description | Selected |
|--------|-------------|----------|
| Build lightweight preview now | Cheap matrix sim; the one place Pitfall 18 prevention works | ✓ |
| Defer; ship safe defaults only | Smaller scope; relies on defaults + admin restraint | |

### Admin LED control surface?
| Option | Description | Selected |
|--------|-------------|----------|
| New 'LEDs' section in Settings.tsx | Swatches + sliders + All-off + Diagnostic; no new route | ✓ |
| Separate /admin/leds route | More room; adds routing + nav | |

**User's choice:** All recommended.

---

## Claude's Discretion

- Exact Pydantic model layout for per-topic payload schemas (follow ARCHITECTURE JSON shapes).
- Inter-cube delay / total duration of the diagnostic sequence.
- Default transition `duration_ms` values per state.
- Settings-cache key naming under `gruvax.settings` (follow `led_color.*` / `led_brightness.*`).

## Deferred Ideas

- Real LED firmware, broker host-port exposure, second LAN listener, per-device credentials, TLS — future hardware milestone.
- Transition editor UI — schema ships now; editor waits for firmware.
- Acting on firmware-published status beyond logging — hardware milestone.

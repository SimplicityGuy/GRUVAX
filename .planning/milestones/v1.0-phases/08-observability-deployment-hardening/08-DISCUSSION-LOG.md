# Phase 8: Observability + Deployment Hardening - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-24
**Phase:** 08-observability-deployment-hardening
**Areas discussed:** Sync-staleness behavior, Most-searched records, Slow-query log, Diagnostics page shape

---

## Sync-Staleness Behavior

### Thresholds
| Option | Description | Selected |
|--------|-------------|----------|
| Research defaults | Admin yellow >24h, red >7d; kiosk banner >7d (Pitfall 15 / SC3) | |
| Tighter | Yellow >12h, red >3d; kiosk banner >3d | |
| Looser | Yellow >3d, red >14d; kiosk banner >14d | ✓ |

**User's choice:** Looser (yellow >3d, red >14d; kiosk banner >14d)
**Notes:** Owner's discogsography syncs are batchy/infrequent — the research default would cry wolf.

### Kiosk experience when stale
| Option | Description | Selected |
|--------|-------------|----------|
| Banner + no-results hint | Persistent banner AND no-results text references staleness (full Pitfall 15 / SC3) | |
| Banner only | Always-on subtle banner; no-results page stays generic | ✓ |
| No-results hint only | No banner; staleness mentioned only on empty results | |

**User's choice:** Banner only
**Notes:** Descopes SC#3's "no-results suggestion references staleness" clause deliberately. Flagged in CONTEXT D-02 so the verifier won't fail the phase for the missing hint. Search still works fully regardless.

### Read path for the sync timestamp
| Option | Description | Selected |
|--------|-------------|----------|
| Extend v_collection | Add synced_at/updated_at column to the read-only view; last_synced = max(v_collection.synced_at) | ✓ |
| Separate read grant | Narrow read-only grant on collection_items.updated_at, queried separately | |
| Researcher confirms first | Inspect v_collection def; use existing column if present, else extend | |

**User's choice:** Extend v_collection
**Notes:** Preserves Pitfall 5 (single contact surface). Owner owns discogsography so the view change is in their control. CONTEXT D-03 still asks the researcher to confirm the actual view definition before authoring the change.

---

## Most-Searched Records

### Counted event
| Option | Description | Selected |
|--------|-------------|----------|
| Result selections | Increment release_id on /api/locate (what people actually look up) | |
| Searches by top result | Increment top-ranked result of each search submission | |
| Both as two metrics | Track searches and selections separately | ✓ |

**User's choice:** Both as two metrics
**Notes:** Two separate counters per release_id. No query text persisted (OBS-07 hard constraint).

### Accumulation window
| Option | Description | Selected |
|--------|-------------|----------|
| All-time cumulative | One ever-growing counter per record | |
| Rolling window | Only last N days count | |
| All-time + recent | Lifetime total and recent (7d) tally side by side | ✓ |

**User's choice:** All-time + recent
**Notes:** Recent window default 7d; storage shape (timestamped events vs rolling buckets) left to researcher/planner.

### Admin control
| Option | Description | Selected |
|--------|-------------|----------|
| Top-N + reset action | Display top-N + PIN-gated "Reset stats" | ✓ |
| Top-N read-only | Display only; no reset | |
| Let me describe it | Owner has a specific shape in mind | |

**User's choice:** Top-N + reset action
**Notes:** PIN-gated reset clears test/seed noise. Counting is server-side, not client-reported. Counters are durable → one new gruvax table.

---

## Slow-Query Log

### What it measures
| Option | Description | Selected |
|--------|-------------|----------|
| End-to-end round-trip | Total server time per request (perceived SLO) | |
| DB query time only | Just the Postgres query duration | |
| Both, broken down | Request-total AND DB-time component per slow request | ✓ |

**User's choice:** Both, broken down
**Notes:** Lets the owner see whether the budget went to Postgres or to framework/serialization overhead.

### Durability
| Option | Description | Selected |
|--------|-------------|----------|
| In-memory ring buffer | Last N entries; resets on restart; zero schema | ✓ |
| Persisted table | SLO breaches written to a gruvax table; durable, hot-path write | |
| Ring buffer + persist breaches | Live buffer + durable rows only on SLO breach | |

**User's choice:** In-memory ring buffer
**Notes:** Fits the home-LAN small-footprint constraint. Diagnostic aid, not an audit log.

### Threshold
| Option | Description | Selected |
|--------|-------------|----------|
| Per-endpoint SLO | search >200ms, locate >50ms (each its own budget) | ✓ |
| Single global threshold | One number for all instrumented endpoints | |
| Configurable | Thresholds via env / admin setting | |

**User's choice:** Per-endpoint SLO
**Notes:** Matches SC#5 exactly; same timing path feeds the pytest-benchmark gate.

---

## Diagnostics Page Shape

### Placement
| Option | Description | Selected |
|--------|-------------|----------|
| New /admin/diagnostics route | Dedicated route for all 7 SC2 rows | ✓ |
| Section in Settings.tsx | Add a Diagnostics section to the existing page | |
| Route + Settings summary | Full route plus a summary chip on Settings | |

**User's choice:** New /admin/diagnostics route
**Notes:** Keeps Settings focused on config; room for the 7 diagnostic rows. Admin-gated (PIN + CSRF).

### Refresh
| Option | Description | Selected |
|--------|-------------|----------|
| Manual refresh button | Load on open + Refresh button; no polling | ✓ |
| Auto-refresh while open | Re-poll ~15s while open | |
| Live via SSE | Reuse Phase 4 SSE for telemetry | |

**User's choice:** Manual refresh button
**Notes:** No steady CPU/network chatter on the Pi (anti-pattern table). Admin-only on mobile, not the kiosk.

### Recent log lines source
| Option | Description | Selected |
|--------|-------------|----------|
| In-memory log ring buffer | App keeps last N log records; diagnostics tails them | ✓ |
| Container log file / journald | Read recent lines from the actual log sink | |
| Errors/warnings only | Ring buffer capped to WARN+ records | |

**User's choice:** In-memory log ring buffer
**Notes:** Same pattern as the slow-query buffer; no container/host log-file coupling.

---

## Claude's Discretion

- Structured-JSON logging library/approach (OBS-02) and how the log ring buffer hooks the pipeline.
- `/version` git-SHA + build-timestamp injection, environment detection, public vs admin (OBS-04).
- CI from scratch on GitHub Actions (OBS-03 + SC5): Alembic round-trip, pytest-benchmark SLO gate, lint/type/test; fail-vs-advisory on the benchmark gate.
- Compose `logging:` driver values for api + mosquitto (DEP-04).
- Volume-permissions doc/verify (Pitfall 14).
- `just demo` box-level smoke script mechanics (SC5).
- Phantom-boundary count + psycopg pool stats sources for the diagnostics rows.

## Deferred Ideas

- No-results page staleness hint (descoped half of SC#3) — possible v1.x.
- External metrics/APM stack (Prometheus/Grafana/OTel) — out of scope for footprint.
- Durable/historical slow-query trend — ring buffer is intentionally ephemeral.
- Rich search analytics (time-of-day, per-visitor, query-text mining) — forbidden by no-query-text rule.
- Live disk-usage/log-volume diagnostics row — Compose log limits cover the disk problem; not SC2-required.

# Phase 8: Observability + Deployment Hardening - Context

**Gathered:** 2026-05-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Make v1 **operable, observable, and self-healing** — without growing the footprint.
The system already serves the Core Value flow; Phase 8 proves it keeps holding the
200 ms SLO and surfaces the few things the owner needs to keep it running on `lux`.

**In scope (9 requirements):**
- **OBS-01** — `/api/health` reports overall status + per-subsystem reachability (postgres, mqtt,
  discogsography_view_check) + version + started-at. *(Endpoint already exists from Phase 1 —
  enrich it, don't replace it.)*
- **OBS-02** — service logs as structured JSON; log level configurable via env var (`LOG_LEVEL`
  already exists; JSON formatting does not).
- **OBS-03** — Alembic migrations round-trip clean (`upgrade head → downgrade base → upgrade head`)
  proven in CI on every push.
- **OBS-04** — `/api/version` reports git SHA, build timestamp, environment.
- **OBS-05** — slow-query log: requests exceeding their per-endpoint SLO are flagged.
- **OBS-06** — admin diagnostics show discogsography-sync staleness.
- **OBS-07** — admin diagnostics aggregate top-N most-searched records (no per-query text persisted).
- **DEP-04** — each Compose service declares log-size limits (prevent disk exhaustion on `lux`).
- **DEP-05** — each Compose service declares a healthcheck integrated with `restart: unless-stopped`.
  *(compose.yaml ALREADY declares `healthcheck:` + `restart: unless-stopped` on all services —
  DEP-05 is largely satisfied; verify/round it out, focus net-new effort on DEP-04.)*

**Reconciliation notes (IMPORTANT for researcher/planner):**
- **`/healthz` (OBS-01 wording) == the existing `/api/health`.** Phase 1 shipped `/api/health`
  (`src/gruvax/api/health.py`) reporting `db`/`discogsography_view_check`/`mqtt`/`status`/`version`
  (hardcoded `"0.1.0"`)/`started_at`. SC#1 already names `/api/health`. Do NOT add a second
  `/healthz`; enrich this one with the **git SHA version (OBS-04 source)** and **sync-staleness
  (OBS-06)**.
- **SC#3 no-results-staleness clause is DESCOPED by owner decision** (see D-02). SC#3 reads
  "a no-results suggestion text references staleness when applicable"; the owner chose a
  **kiosk banner only** and a generic no-results page. The verifier must NOT fail the phase for
  the missing no-results hint — it was deliberately cut. The kiosk staleness *banner* (also in
  SC#3) IS in scope.

**Out of scope (other phases / backlog):** boundary wizards/import/export (Phase 7, done); LED
firmware (hardware milestone); per-query text logging or any analytics that stores what was typed
(privacy — OBS-07 forbids it); APM/Prometheus/Grafana or any external metrics stack (footprint
constraint — home LAN, no heavyweight services); rolling-window auto-trim infra beyond the simple
recent-counter the stats need; multi-host / cloud deployment (single-host v1).
</domain>

<decisions>
## Implementation Decisions

### Sync-Staleness (OBS-06 · SC3 · Pitfall 15)
- **D-01:** **Looser thresholds** than the research default. Admin diagnostics: **yellow at
  >3 days**, **red at >14 days**. Kiosk staleness **banner at >14 days**. Rationale: the owner's
  discogsography syncs are batchy/infrequent; the research default (24h/7d) would cry wolf.
- **D-02:** **Kiosk shows a banner only.** A subtle, persistent staleness banner appears on the
  kiosk when `sync_age > 14d`; the **no-results page stays generic** (no staleness hint). This
  **descopes the SC#3 no-results-staleness clause** — captured deliberately, not an oversight.
  Search continues to work fully regardless of staleness. (Banner copy = Nordic Grid, plain
  language, no jargon.)
- **D-03:** **Sync timestamp is exposed through `v_collection`.** Extend the read-only
  `v_collection` view to carry a `synced_at` (or equivalent `updated_at`) column;
  `last_synced = max(v_collection.synced_at)`. This **preserves Pitfall 5** (v_collection is the
  ONLY discogsography contact surface — no new direct read of `collection_items`). The owner owns
  discogsography, so the view change is in their control. **Researcher must confirm the actual
  `v_collection` definition first** — if a sync timestamp column already exists, use it; otherwise
  the view extension lands as part of this phase's migration/coordination story.

### Most-Searched Records (OBS-07)
- **D-04:** **Two separate metrics per record** — a **search count** and a **selection count**,
  both keyed by **`release_id` only**. "Search count" increments for the top result of a search
  submission; "selection count" increments when a record is actually looked up (`/api/locate` on a
  specific `release_id`). **No query text is ever persisted** (OBS-07 hard constraint).
- **D-05:** **All-time + recent (7-day) columns** for each metric. The diagnostics page shows
  lifetime totals alongside a recent tally so the owner sees both enduring favorites and current
  interest. (Recent window default = 7 days; researcher/planner pick the storage shape —
  timestamped events vs. rolling buckets — to keep it cheap.)
- **D-06:** **These counters are DURABLE** → one new **`gruvax` schema table** (the only new
  persistent storage this phase adds). Diagnostics shows **top-N**, plus a **PIN-gated "Reset
  stats"** admin action so the owner can clear test/seed noise. Counting happens **server-side** on
  the search/locate paths (not client-reported).

### Slow-Query Log (OBS-05 · the 200 ms SLO)
- **D-07:** **Measure both, broken down** — for each slow request log the **request-total** time
  AND the **DB-time component**, so the owner can see whether the budget went to Postgres or to
  framework/serialization overhead.
- **D-08:** **In-memory ring buffer** (last N entries; **resets on restart**). Zero schema, tiny
  footprint — fits the home-LAN small-footprint constraint. Not durable by design (this is a live
  diagnostic aid, not an audit log).
- **D-09:** **Per-endpoint SLO thresholds** — flag **`/api/search` >200 ms** and
  **`/api/locate` >50 ms**, each against its own budget (matches SC#5 exactly). Instrumentation is
  the same timing path that feeds the SC#5 `pytest-benchmark` gate.

### Diagnostics Surface (SC2)
- **D-10:** **New `/admin/diagnostics` route** (sibling to Settings), **admin-gated** behind the
  Phase 3 PIN/session + CSRF. Keeps `Settings.tsx` focused on config; gives the 7 SC#2 rows
  (sync staleness, top-N searched, slow-query log, MQTT status, Postgres pool `size_used`/`size_min`,
  phantom-boundary count, recent logs) room to breathe.
- **D-11:** **Manual refresh button** — data loads on open + an explicit Refresh. **No polling, no
  SSE** for telemetry: avoids steady CPU/network chatter on the Pi (anti-pattern table) and the
  page is admin-only on mobile, never on the kiosk.
- **D-12:** **Recent log lines come from an in-memory log ring buffer** (same pattern as D-08): the
  app keeps the last N log records in memory and diagnostics tails them. No container/host log-file
  or journald coupling.

### Storage Split (coherence summary — important for planner)
- **Persistent (new):** exactly **one `gruvax` table** for the search/selection counters (D-04/05/06).
- **Ephemeral (in-memory, reset on restart):** the **slow-query ring buffer** (D-08) and the
  **log ring buffer** (D-12).

### Claude's Discretion (delegated to researcher / planner / ui-phase)
- **Structured-JSON logging (OBS-02):** library/approach (stdlib `logging` + a JSON formatter vs.
  `structlog`) and how the in-memory log ring buffer (D-12) hooks the logging pipeline. Reuse
  `LOG_LEVEL` (already in `settings.py`/compose).
- **`/version` (OBS-04):** how git SHA + build timestamp are injected into the image (Docker build
  arg / generated file), how "environment" is detected, and whether `/version` is public like
  `/api/health` (default: yes, public — it's a LAN-only box). Feed the same SHA into
  `/api/health`'s `version` field (currently hardcoded `"0.1.0"`).
- **CI from scratch (OBS-03 + SC5):** there is **no `.github/workflows/` yet**. Create CI on
  **GitHub Actions** (aligns with discogsography). Gates: Alembic round-trip
  (`upgrade head → downgrade base → upgrade head`), `pytest-benchmark` proving p95
  `/api/search` ≤200 ms and `/api/locate` ≤50 ms against the **synthetic** dataset (never the real
  collection CSV — repo-hygiene constraint), plus the existing lint/type/test suite. Decide
  fail-the-build vs. advisory for the benchmark gate (lean: fail on regression).
- **Compose log limits (DEP-04):** the `logging:` driver values (`max-size` / `max-file`) for
  `api` and `mosquitto`. compose.yaml already has healthchecks + `restart: unless-stopped`
  (DEP-05) — verify, don't rebuild.
- **Volume permissions doc (Pitfall 14):** document + verify fresh-host volume perms for the
  non-root container; this is a docs/verify task, not new code.
- **`just demo` smoke script (SC5):** mechanics of a box-level smoke that runs the Core Value flow
  against a fresh `docker compose up` and asserts the SLO. Local recipe; CI may or may not invoke it.
- **Phantom-boundary count & pool stats rows (SC2):** the queries/sources for the
  phantom-boundary count and psycopg pool `size_used`/`size_min` — surface existing internals.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & Roadmap (the locked acceptance spec for this phase)
- `.planning/REQUIREMENTS.md` — definitions for **OBS-01..OBS-07** (lines 107–113) and
  **DEP-04 / DEP-05** (lines 132–133).
- `.planning/ROADMAP.md` §"Phase 8: Observability + Deployment Hardening" — goal + the **five
  success criteria (SC1–SC5)**. ⚠ Read SC#3 against **D-02** (no-results-staleness clause is
  descoped; kiosk banner is in scope).
- `.planning/PROJECT.md` — constraints: home-LAN only / no public exposure, single-PIN admin,
  **footprint ~$80–150 / no heavyweight services beyond what runs on `lux`** (drives the
  in-memory-buffer + no-APM choices), **repo hygiene** (collection CSV + `background/` never
  committed → CI benchmark uses synthetic data only).

### Research (authoritative for the observability/ops shape)
- `.planning/research/PITFALLS.md` — **Pitfall 5** (`v_collection` is the only contact surface →
  drives D-03), **Pitfall 14** (volume permissions break on first boot for the non-root container,
  ~line 450), **Pitfall 15** (sync staleness hides newly-added-but-unfindable records;
  `last_synced = max(v_collection.synced_at)`; thresholds; the no-results hint we descoped, ~line
  484), and the **ops-phase logging note** (Compose logging + journald, ~line 680).
- `.planning/research/FEATURES.md` — **Category 7** (admin diagnostics as a product differentiator:
  sync staleness, disk/log rows).
- `.planning/research/ARCHITECTURE.md` — the `/api/*` + `/api/admin/*` endpoint surface and where
  `/api/diagnostics`-style data belongs; admin route tree (`/admin/diagnostics` sits beside
  Settings).
- `.planning/research/STACK.md` — pinned stack; logging / SSE / observability guidance.

### Existing code to extend (NOT rebuild)
- `src/gruvax/api/health.py` — the existing `/api/health` to enrich (OBS-01 + git-SHA version +
  sync-staleness). Reads `app.state.{db_ok,discogsography_view_ok,mqtt_ok,started_at}`.
- `src/gruvax/settings.py` — `LOG_LEVEL` config (OBS-02) and pattern for new settings.
- `src/gruvax/app.py` — lifespan + (currently default) logging init; where structured-JSON logging
  and the log ring buffer get wired.
- `compose.yaml` — already has `healthcheck:` + `restart: unless-stopped` on `api` /
  `gruvax-dev-pg` / `mosquitto` (DEP-05); add `logging:` limits (DEP-04). `LOG_LEVEL` already passed.
- `src/gruvax/api/admin/leds.py` (+ `router.py`) — Phase 6 admin **diagnostic** precedent (background
  task, run_id ack) and the admin router registration pattern for the new diagnostics endpoints.
- `frontend/src/routes/admin/Settings.tsx`, `AdminShell.tsx` — admin route/nav pattern the new
  `/admin/diagnostics` route follows; `adminClient.ts` for fetches.
- `src/gruvax/db/queries.py` — all reads go through `gruvax.v_collection` (Pitfall 5); pattern for
  the staleness query and the most-searched counter reads.
- `justfile` — existing recipes (migration round-trip recipe may already exist here) + where
  `just demo` lands.

### Locked from Prior Phases (carry forward — do not re-decide)
- `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-CONTEXT.md` — admin **PIN/session + CSRF**
  gating (the `/admin/diagnostics` route + Reset-stats action sit behind this), `boundary_cache`.
- `.planning/phases/06-led-contract-over-mqtt-hardware-stubbed/06-CONTEXT.md` — the admin
  diagnostic/settings precedent, MQTT status source (`app.state.mqtt_ok`) for the diagnostics
  MQTT-status row.

### Design System & Conventions (consume tokens; never hardcode hex)
- `design/gruvax-design-language.md`, `design/gruvax-design-tokens.css`,
  `design/gruvax-design-tokens.json` — Nordic Grid for the `/admin/diagnostics` page + kiosk banner;
  yellow/red staleness states via tokens; DM Mono for counts/timings; ALL-CAPS Barlow labels;
  plain-language banner copy.
- `CLAUDE.md` / `.planning/codebase/CONVENTIONS.md` — **Mermaid-only diagrams**, vanilla-DOM
  frontend build (`el()` / `replaceChildren()`, never `innerHTML`), psycopg `%s` parameterized SQL,
  routers imported inside `create_app()`, `alembic_version` in `public` schema, `search_path` via
  connect-event listener.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets (Phase 8 is mostly enrichment + one new table + one new page)
- **`src/gruvax/api/health.py`** — `/api/health` already returns the OBS-01 subsystem map from
  `app.state` (no live probe on the hot path). Add `version` (real git SHA) + `sync_age_seconds`.
- **`app.state.{db_ok, discogsography_view_ok, mqtt_ok, started_at}`** — already maintained across
  lifespan + boundary-cache reload (Phase 4). The diagnostics MQTT/DB rows read these.
- **`src/gruvax/api/admin/leds.py`** — admin background-task + ack pattern; `router.py` admin-route
  registration to add `/admin/diagnostics` endpoints.
- **`src/gruvax/db/queries.py`** — `gruvax.v_collection` is the sole read surface; add the
  `max(synced_at)` staleness read here and the most-searched counter queries.
- **`frontend/src/routes/admin/Settings.tsx` + `AdminShell.tsx` + `adminClient.ts`** — pattern for
  the new admin route, nav entry, and fetch client.
- **`compose.yaml`** — healthchecks + `restart: unless-stopped` present; add `logging:` limits.

### Established Patterns
- **`/api/health` reflects startup/cached state — no live probe per request** (avoids latency +
  hammering Postgres). New health fields follow the same "read `app.state`/cached" rule; the
  staleness read is the one new lightweight DB touch (cache it like the boundary cache if needed).
- **`v_collection` is the only discogsography contact surface** (Pitfall 5) — the staleness read
  goes through the view; do not add a direct `collection_items` read.
- **Admin routes require session + CSRF** (Phase 3); admin-gated GET/POST in `api/admin/*`.
- **Alembic:** `alembic_version` in `public` schema; `search_path` via connect-event listener;
  migrations must round-trip clean. Latest migration is **`0007`** (Phase 7); the staleness view
  change + the most-searched counters table land as **new migration(s) from `0008`**.
- **Frontend:** React + react-router; component bodies build DOM via `el()` / `replaceChildren()`
  (never `innerHTML`); design tokens only, no hardcoded hex.
- **Tests/CI use the synthetic dataset** (`fixtures/synth_collection.sql`), never the real CSV.

### Integration Points
- **Enriched endpoint:** `/api/health` (+ version + sync staleness).
- **New endpoint:** `/api/version` (git SHA, build timestamp, environment).
- **New admin endpoints:** diagnostics read (staleness, top-N, slow-query buffer, MQTT, pool stats,
  phantom count, recent logs) + a PIN-gated reset-stats action — all session + CSRF gated.
- **New persistent storage:** one `gruvax` table for search/selection counters (migration `0008`+).
- **View change:** extend `gruvax.v_collection` to expose a sync timestamp (coordinate with
  discogsography; migration-managed).
- **New frontend route:** `/admin/diagnostics` (manual refresh) + admin-nav entry; **kiosk
  staleness banner** (>14d) in the kiosk SPA.
- **Cross-cutting:** structured-JSON logging + log ring buffer wired in `app.py`; slow-query timing
  middleware feeding the ring buffer + the `pytest-benchmark` gate.
- **CI (new, GitHub Actions):** lint/type/test + Alembic round-trip + `pytest-benchmark` SLO gate.
- **Compose:** `logging:` size limits on `api` + `mosquitto`.
</code_context>

<specifics>
## Specific Ideas

- **`/healthz` already exists as `/api/health`** — enrich, never duplicate.
- **The footprint constraint is the design driver:** ephemeral in-memory ring buffers (slow-query +
  logs) over any metrics stack; exactly one new durable table (the counters). No Prometheus/Grafana.
- **Privacy is non-negotiable (OBS-07):** counters are `release_id`-keyed aggregates; the raw query
  string is never written anywhere, ever — same spirit as Pitfall 12 (the PIN never leaves the DB).
- **Round-trip + SLO are the acceptance tests:** Alembic `upgrade→downgrade→upgrade` clean in CI;
  `pytest-benchmark` p95 search ≤200 ms / locate ≤50 ms on synthetic data; `just demo` proves it at
  the box level on a fresh `docker compose up`.
- **Staleness thresholds tuned to the owner's batchy sync cadence:** 3d/14d, not 24h/7d.
</specifics>

<deferred>
## Deferred Ideas

- **No-results page staleness hint** (the descoped half of SC#3) — could return in v1.x if the
  banner proves insufficient; deliberately cut now (D-02).
- **External metrics/APM stack** (Prometheus, Grafana, OpenTelemetry export) — out of scope for the
  home-LAN footprint; in-app diagnostics cover v1.
- **Durable/historical slow-query trend** (persisted breaches, charts over time) — the in-memory
  ring buffer (D-08) is intentionally ephemeral; a persisted history is a future enhancement.
- **Rich search analytics** (per-time-of-day, per-visitor, query-text mining) — forbidden by the
  no-query-text privacy rule and beyond v1; the two `release_id` counters are the whole story.
- **Disk-usage / log-volume diagnostics row** (Pitfall, ops-phase note ~line 680) — Compose log
  limits (DEP-04) prevent the disk problem; a live disk-usage row in diagnostics is a nice-to-have,
  not required by SC2.

Discussion stayed within phase scope — no scope-creep ideas were raised.
</deferred>

---

*Phase: 08-observability-deployment-hardening*
*Context gathered: 2026-05-24*

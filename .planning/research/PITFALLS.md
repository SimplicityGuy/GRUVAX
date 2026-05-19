# Pitfalls Research — GRUVAX

**Domain:** Personal-collection touchscreen kiosk (Chromium kiosk on Pi 5) + FastAPI + MQTT-stubbed LED layer, deployed via Docker Compose alongside an existing `discogsography` service sharing a Postgres instance.
**Researched:** 2026-05-18
**Confidence:** HIGH on category-specific pitfalls (anchored to STACK.md/FEATURES.md/ARCHITECTURE.md and verified against current `aiomqtt`/`sse-starlette` docs via Context7). MEDIUM on the position-estimation pitfalls (the algorithm is its own research stream; pitfalls here describe *contract-level* dangers, not algorithm choice).

This document is opinionated and project-specific. Generic "test your code" advice is omitted. Every prevention strategy references a concrete GRUVAX surface (a table, a view, a setting, an endpoint, a Compose service).

**Severity legend:**
- **Critical** — silently corrupts data or makes the system unusable.
- **Major** — multi-hour fix or forces a re-design.
- **Minor** — annoying but quickly fixable.

---

## Critical Pitfalls

### Pitfall 1: Catalog-number string comparison silently breaks natural sort

**What goes wrong:**
A user searches for `Blue Note BLP-4195`; the kiosk highlights the wrong cube. Investigation shows the boundary table has `last_catalog = 'BLP 4200'` and `BLP-4195` lexicographically *exceeds* `BLP 4200` because `' '` (0x20) < `'-'` (0x2D). The "deterministic ordering" invariant is broken not by user error but by ASCII.

**Specific symptom:**
- Two records from the same label land in different cubes than the owner's hand-sorted shelf says they should.
- Affected labels are usually the ones with mixed separators across catalog numbers (e.g., `BLP 4195` shelved next to `BLP-4196`).
- Bug is **silent**: kiosk renders a wrong-but-plausible cube; no error log.

**Why it happens:**
`(label, catalog#)` is treated as `TEXT` in `cube_boundaries`. Python and Postgres default string ordering is byte-wise (or locale-driven), neither of which respects the user's mental "BLP 4195 comes right before BLP-4196" model. The CSV documented in PROJECT.md shows the real catalog-number formats are inconsistent across labels and sometimes within a label.

**Warning signs (detect early):**
- During the position-estimator research stream: any property test that says "for any release in the CSV, `primary_cube` is in `label_span`" fails on a label whose catalog numbers mix separators or case.
- Manual spot-check after first wizard run: pick 5 records whose catalog numbers contain a digit and a separator, verify each lands in the cube the owner's eyes say it should.
- Slow-query log or `confidence: 0` rate climbs on a specific label after a reshuffle.

**Prevention:**
- Treat catalog-number comparison as the position estimator's responsibility, **not** the database's. `cube_boundaries.first_catalog`/`last_catalog` store the **original** (display) catalog number; the estimator normalizes both the boundary values and the queried record's catalog number through the same `normalize.py` (per ARCHITECTURE.md project structure) before comparing.
- Recommended normalization stages (each a step in `normalize.py`): case-fold, collapse runs of whitespace/`-`/`_`/`.` to a single canonical separator, then split into `(alpha_prefix, numeric_suffix, trailing)` and compare the parts independently with numeric-aware comparison on the digit run.
- Add Hypothesis property: "for every label in the seed CSV, sorting the label's catalog numbers via the estimator's comparator produces the same order as the hand-curated golden list for that label." Run on every commit.
- Boundary admin save path runs the same comparator: reject save if `first > last` per the comparator (not per string order).

**Recovery (if it slips past prevention):**
- Add the missing normalization rule, write a Hypothesis test that fails without it, ship.
- For affected boundaries already in production: a one-time admin "re-validate all boundaries" diagnostic that flags any cube whose boundaries the new comparator would reject. Owner reviews flagged cubes and edits via the wizard. The `boundary_history` append-only log means the reshuffle is auditable.

**Severity:** Critical (silently corrupts the answer the product exists to give).

**Phase to address:** Position-estimator research stream (algorithm), then Backend Phase (admin save validation using the same comparator), then Test Phase (Hypothesis property suite).

---

### Pitfall 2: Boundary points at a record that no longer exists in the collection

**What goes wrong:**
Owner sells a record, runs the next discogsography sync; the boundary `last_catalog` is now a `(label, catalog#)` pair that has no row in `v_collection`. The estimator still works (it does interval lookup, not exact match), but the *admin wizard's autocomplete* and the *cube-contents reveal* (FEATURES.md Category 2 differentiator) return empty for that boundary value. Worse, on the next reshuffle the wizard may "auto-suggest" a midpoint between two boundaries where one endpoint is a phantom record, producing nonsense.

**Specific symptom:**
- Admin wizard's autocomplete returns 0 results when typing the exact catalog number that the boundary already stores.
- Cube reverse-lookup (`/api/cubes/{unit}/{row}/{col}`) returns empty `sample_records` even though `is_empty: false`.
- Boundary validation passes (it checks against itself, not against `v_collection`).

**Why it happens:**
Two read-vs-write timelines: `cube_boundaries` is GRUVAX-owned and changes only on admin edits; `v_collection` reflects discogsography's sync of the owner's live Discogs collection. Selling a record is a discogsography-side event GRUVAX never sees.

**Warning signs:**
- Periodic admin diagnostic: count of `cube_boundaries` rows where `(first_label, first_catalog)` or `(last_label, last_catalog)` does not match any `v_collection` row. Surface in `/api/admin/diagnostics` as `phantom_boundary_count`.
- Sync staleness indicator (FEATURES.md Category 7) staying current but `phantom_boundary_count > 0` means the divergence is real, not a sync lag.

**Prevention:**
- **Pre-validate boundary edits against `v_collection` and reject if the `(label, catalog#)` isn't in the collection.** This is the concrete shape of the FEATURES.md Category 3 "Sanity validation against `collection_items`" item. The `POST /api/admin/cubes/validate` endpoint runs this check.
- **Tolerant trigram match for near-misses:** if no exact match, suggest the closest 3 collection items as "did you mean?" (FEATURES.md Category 1 differentiator reused here).
- **Stale-boundary detector job:** a daily Postgres `NOTIFY` (or a cheap polling endpoint hit by the admin diagnostics page) that recomputes `phantom_boundary_count` and lists the offending cubes. Doesn't auto-fix; informs the owner.

**Recovery:**
- Admin opens diagnostics, sees the phantom list, runs the wizard for affected cubes only (don't full-reshuffle). The wizard suggests the natural midpoint based on currently-collected releases between adjacent populated cubes.
- The undo/history log means a wrong-fix is one tap back.

**Severity:** Critical (affects accuracy of the wizard's suggestions; corrupts future reshuffles silently).

**Phase to address:** Backend Phase (validate endpoint + diagnostic count), Admin Phase (wizard consumes validate), Ops Phase (schedule the periodic check).

---

### Pitfall 3: Mosquitto retained-state messages persist beyond their useful life

**What goes wrong:**
The architecture publishes `gruvax/v1/leds/state/{unit}/{row}/{col}` as a **retained** topic so a freshly-booted ESP32 picks up current desired state. During v1 stub development, every test "illuminate" call leaves a retained payload on the broker. Six months later, the hardware milestone arrives, an ESP32 connects, and the shelves immediately light up cubes that were used in testing 6 months ago.

**Specific symptom:**
- First ESP32 boot after hardware integration produces nonsensical LED state (cubes 7 and 18 glowing purple because someone tested those during the v1 stub phase).
- `mosquitto_sub -t 'gruvax/v1/leds/state/#' -v` shows dozens of retained payloads with old `issued_at` timestamps.
- A redeploy of `gruvax-api` leaves the state topics intact (retained survives broker restarts and gruvax-api restarts because of `persistence true`).

**Why it happens:**
Retained messages are designed to survive broker restarts. There's no automatic TTL on retained payloads in MQTT 3.1.1; MQTT 5 supports message-expiry but Mosquitto's behavior depends on broker config. Once retained, a payload stays until it's overwritten with an empty payload (`payload=b''`, `retain=True` — the "clear retained" idiom) or the broker's persistence file is deleted.

**Warning signs (detect early):**
- During v1 stub development: `mosquitto_sub -t 'gruvax/v1/leds/state/#' -v` shows growing retained payloads with no clearing strategy.
- The diagnostic endpoint (`POST /api/admin/leds/diagnostic`) does not include a "clear all retained state" step.
- No "clear retained" admin button.

**Prevention:**
- **Set MQTT 5 message-expiry on every retained publish.** With `aiomqtt` 3.x (Context7-verified), pass `message_expiry_interval` on publish (e.g., 4 hours for `state/*`). After expiry the broker drops the retained payload.
- **`POST /api/admin/leds/off` clears retained state.** The "all off" panic button (FEATURES.md Category 4 table stakes) is implemented by publishing `retain=True, payload=b''` to every `state/{unit}/{row}/{col}` topic, *not* by publishing an "off" command. This is the idiomatic MQTT way to clear retained state.
- **Document the retained-state lifecycle** in the LED contract README so the hardware-milestone implementor knows what to expect on first boot.
- **Per-environment topic prefix:** use `gruvax/v1/dev/leds/...` in dev and `gruvax/v1/leds/...` in production so dev retained junk doesn't pollute prod. Configurable via `MQTT_TOPIC_PREFIX` env.

**Recovery:**
- One-shot script: `mosquitto_sub -t 'gruvax/v1/leds/state/#' -v` to list, then publish empty retained to each. Document this in the hardware-milestone runbook.
- Or: stop Mosquitto, delete `/mosquitto/data/mosquitto.db`, restart. Nuclear but effective.

**Severity:** Critical (impossible to debug the hardware milestone if retained state ghosts test runs from months prior).

**Phase to address:** Backend Phase (MQTT publish wrapper sets expiry; "all off" clears retained), Hardware Milestone (runbook).

---

### Pitfall 4: Squeekboard / on-screen keyboard breaks the kiosk admin fallback

**What goes wrong:**
PROJECT.md Active scope says "Kiosk admin fallback (touchscreen, used at the shelf)." STACK.md flags as an open issue: `squeekboard` does not currently render above fullscreen Chromium under labwc (verified open bug, `labwc/labwc#2926`). Result: an admin tries to type a PIN on the kiosk and there is no keyboard. They are physically locked out of admin from the device the requirement specifies.

**Specific symptom:**
- Admin tap on the PIN input field; nothing rises from the bottom of the screen.
- Tap-and-hold gives the standard `text` context menu but no keyboard.
- Switching off `--kiosk` flag makes the keyboard appear but exposes window chrome.

**Why it happens:**
labwc + fullscreen Chromium is a known interaction that suppresses overlay surfaces from input methods. The Pi Foundation's expected pattern is a non-fullscreen window or a different compositor; neither matches the v1 kiosk constraints.

**Warning signs (detect early):**
- Kiosk hardware setup phase: test "type something on the touchscreen with a focused input" *before* any product work depends on it.
- The phrase "in-app virtual keyboard" doesn't appear anywhere in the frontend backlog.

**Prevention:**
- **Build an in-app virtual keyboard inside the SPA.** STACK.md option (b) — this is the right call given (a) the bug is real and live, (b) admin is mobile-first by requirement, (c) only PIN entry and short text fields need to work on-kiosk. ~80 lines of React for a numeric keypad + alphabetic letter board with backspace and submit. Tap-target ≥ 44pt.
- **Make the kiosk PIN entry numeric-only** (PROJECT.md doesn't say otherwise — the PIN is single-secret on home LAN, so 6 digits is fine). Reduces the keyboard surface to a 10-key.
- **Treat squeekboard as not-available** in the architecture; do not load any state that assumes it exists.

**Recovery:**
- If shipped without the in-app keyboard: ship the in-app keyboard as a v1 hotfix. The data model and routes are unchanged.

**Severity:** Critical (a documented requirement — kiosk admin fallback — is non-functional without it).

**Phase to address:** UI Design / Frontend Phase (in-app keypad component); Hardware Setup Phase (verify the bug is still present, not silently fixed upstream).

---

### Pitfall 5: discogsography schema migration breaks `v_collection` and search dies

**What goes wrong:**
discogsography's maintainer renames `releases.label` to `releases.label_name`, or normalizes labels from a `TEXT` column into a separate `release_labels` join table. GRUVAX boots, `gruvax.v_collection` references the removed column, every `/api/search` request errors. The kiosk shows "no results" or 500s for every query. Failure is total.

**Specific symptom:**
- `/api/health` returns `discogsography_view_check: failed` (per ARCHITECTURE.md failure modes table) — *if* the health check is wired to validate the view.
- Without that wiring: every search returns 500; the SPA renders "No results" and the offline banner stays off because `/api/events` is healthy.
- `journalctl --user-unit gruvax` shows Postgres errors mentioning a missing column.

**Why it happens:**
GRUVAX is a downstream consumer of a schema GRUVAX doesn't control. ARCHITECTURE.md's "view as the read-only contract surface" pattern reduces blast radius from "the whole codebase" to "one view," but it does not prevent breakage; it makes breakage *localized and discoverable*.

**Warning signs:**
- discogsography has a release whose changelog mentions schema changes; you didn't notice because no automated alert is wired.
- `SELECT 1 FROM gruvax.v_collection LIMIT 1` at boot is **not** part of the FastAPI lifespan.

**Prevention:**
- **Implement the view-health-probe at startup** (ARCHITECTURE.md prescribes it). The lifespan runs `SELECT 1 FROM gruvax.v_collection LIMIT 1` before yielding; on failure, GRUVAX still boots but `/api/health` reports `discogsography_view_check: failed` and search returns 503 with a clear error pointing at the upstream schema.
- **Pin discogsography to a specific tag (or commit SHA) in the Compose stack on `lux`.** Don't auto-upgrade discogsography in the same docker-compose action as GRUVAX. Upgrade discogsography deliberately, verify GRUVAX still passes its integration test (which runs `SELECT 1 FROM gruvax.v_collection LIMIT 1` plus a representative search), then commit.
- **Subscribe to discogsography's release notes / watch the GitHub repo.** This is a one-time setup.
- **Integration test against a real discogsography schema:** in CI, spin up the *actual* discogsography Postgres dump (or a representative subset; see Section "Discogs/discogsography integration pitfalls" elsewhere), apply GRUVAX migrations, run the view-health probe, run one representative search end-to-end.

**Recovery:**
- Edit `migrations/versions/xxxx_update_v_collection.py` to match the new upstream column names; `alembic upgrade head`; redeploy. One-line view change per ARCHITECTURE.md.
- If the upstream change is structural (e.g., label moved to a join table): the view definition gets longer, but no application code changes. The whole point of the view pattern.

**Severity:** Critical (total search outage until fixed) but **bounded** (one view, predictable recovery).

**Phase to address:** Backend Phase (lifespan view probe + `/api/health` field), Ops Phase (CI integration test + discogsography pinning).

---

### Pitfall 6: instance_id vs release_id confusion in the LED publish path

**What goes wrong:**
Discogs distinguishes `release_id` (a release in the global catalog) from `instance_id` (a specific copy in a user's collection — important when an owner has two copies of the same record, or when collection state like "for sale" differs per copy). discogsography stores both. GRUVAX uses `release_id` everywhere because the position estimator does not care about specific copies (a label+catalog# is unique enough for shelf placement). But if any endpoint accidentally accepts `instance_id` and passes it through as `release_id`, lookups silently return wrong records.

**Specific symptom:**
- A search result `tap-to-illuminate` produces a `release_id` that exists in the catalog but is not in the owner's collection (the owner has the *other* copy, with a different `instance_id`).
- Position estimate returns 404 `release_not_in_collection` for a record visibly on the shelf.
- Or, worse, returns a confident cube for a wrong record (both copies of the release share `(label, catalog#)`, so the wrong-record case rarely fires for *position* but does fire for "what's in this cube?" reverse lookup if `collection_item_id` was confused with `release_id`).

**Why it happens:**
The ARCHITECTURE.md view exposes `collection_item_id`, `release_id`, and (implicitly via the join) the position-relevant fields. A handler that takes a `release_id` query param from the frontend and passes it as `collection_item_id` to a query is a one-character typo.

**Warning signs:**
- API search results emit a field literally named `id` (ambiguous) rather than `release_id`/`collection_item_id`.
- A 404 on `/api/locate?release_id=...` rate climbs after a release that the owner has two copies of.

**Prevention:**
- **Name the field explicitly everywhere:** `release_id`, `collection_item_id`. Never just `id`. Pydantic models on every endpoint reject ambiguity at the boundary.
- **The position-estimator contract (ARCHITECTURE.md) already takes `release_id`** — keep it that way. `collection_item_id` is only used in the cube-contents reverse-lookup (where it disambiguates which physical copy is in this cube — though for v1 with no per-copy tracking, this is moot).
- **Search endpoint returns both** `release_id` and `collection_item_id`. The illuminate endpoint takes `release_id`. The bridge in the SPA is explicit.
- **Integration test that exercises a real "owner has two copies" case:** synthetic CI dataset includes one duplicated release_id under two collection_item_ids; assertion is that both produce the same `/api/locate` result.

**Recovery:**
- Rename fields, add Pydantic models. Migration is a frontend change because the field names change on the wire.

**Severity:** Critical for the reverse-lookup view; Major for primary search→illuminate flow (position is the same per release).

**Phase to address:** Backend Phase (Pydantic model design), Test Phase (the "two copies" fixture).

---

## Major Pitfalls

### Pitfall 7: Half-finished reshuffle leaves cubes in inconsistent state

**What goes wrong:**
Owner runs the reshuffle wizard mid-haul, gets interrupted (Wi-Fi blip, phone battery, doorbell), comes back later. Some cubes have updated boundaries reflecting the new shelf order, some still have the old boundaries. Search returns confidently-wrong cubes for records affected by the partial change.

**Specific symptom:**
- A search lands on a cube that has the right label but the wrong catalog-number range; the user walks to a cube whose physical contents disagree with the kiosk.
- `boundary_history` shows a half-completed `change_set_id` (some cubes touched, some not).
- The wizard's "resume" path either doesn't exist or shows wrong "current" state.

**Why it happens:**
The wizard is a multi-step flow over multiple cubes; without an explicit transaction model, intermediate state lives in the SPA's `pendingChangeSet` (ARCHITECTURE.md Zustand store) but is *not* applied atomically to the DB until the final save. If "save" is per-cube instead of per-wizard-run, partial state lands in DB.

**Warning signs:**
- The `POST /api/admin/cubes/bulk` endpoint is implemented but the wizard issues `PUT /api/admin/cubes/{unit}/{row}/{col}/boundary` per-cube.
- The wizard has no "discard draft" button.
- Two `boundary_history` change_sets have timestamps within a few minutes of each other for the same reshuffle event.

**Prevention:**
- **Wizard accumulates in `pendingChangeSet` in Zustand; final "Save reshuffle" calls `POST /api/admin/cubes/bulk` with all changes.** Atomic in DB (one `change_set_id`, one transaction). Per-cube saves during the wizard go through `pendingChangeSet`, not the DB. (ARCHITECTURE.md already prescribes this; the pitfall is forgetting it under time pressure during the admin phase.)
- **Persist `pendingChangeSet` in `localStorage`** so a Wi-Fi blip or page reload doesn't lose progress. The Zustand persist middleware handles this in a few lines.
- **Idempotency-Key header on the bulk save** (ARCHITECTURE.md prescribes this). Reload of the wizard tab will not double-save.
- **The wizard's "resume" path reads from `localStorage`** and shows a "Continue your reshuffle" banner on next admin login.

**Recovery (if partial commit happens):**
- Admin opens history, sees the partial change set, taps "Revert change set" — `POST /api/admin/history/{change_set_id}/revert` writes inverse rows. Now the DB is back to pre-reshuffle. Run the wizard again, this time atomically.
- Because history is append-only, no state is lost.

**Severity:** Major (data loss avoided by ARCHITECTURE.md design, but UX disaster if implementation skips the atomic-bulk pattern).

**Phase to address:** Admin Phase (wizard uses bulk endpoint), Frontend Phase (Zustand persist + resume UX).

---

### Pitfall 8: SSE reverse-proxy buffering breaks live admin → kiosk updates

**What goes wrong:**
Admin saves a boundary on mobile, kiosk does not re-render. The SSE channel appears connected (network tab shows the request open), but events are buffered server-side or proxy-side and arrive in 30-second clumps. The "live cross-device refresh" UX is broken without a clear error.

**Specific symptom:**
- `EventSource` is `readyState === 1` (OPEN) on the kiosk but no events fire for 30 seconds, then several arrive at once.
- nginx or any reverse proxy (if added in front of FastAPI) shows `proxy_buffering on` (the default).
- `curl -N http://lux.local:PORT/api/events` from the Pi LAN shows event lines arriving in spurts, not streaming.

**Why it happens:**
HTTP/1.1 proxies buffer by default. nginx (verified via Context7 on `sse-starlette`) needs explicit `proxy_buffering off; chunked_transfer_encoding off;` for SSE. `sse-starlette` recommends `X-Accel-Buffering: no` and `Cache-Control: no-store` response headers to instruct nginx/cloud-buffering layers to not buffer this response.

**Warning signs:**
- A bench test of admin save → kiosk re-render shows >5 seconds latency on the LAN (should be <300 ms).
- Adding a reverse proxy to the stack later (e.g., a Traefik front-door) without re-testing SSE.

**Prevention:**
- **Set `X-Accel-Buffering: no` and `Cache-Control: no-store` response headers** on the SSE endpoint via `sse-starlette`'s `headers=` (Context7-verified pattern).
- **Use the default 15-second ping** in `sse-starlette` — it's specifically designed to flush proxy buffers and keep the connection alive (Context7-verified, default `ping=15`).
- **STACK.md recommends serving the SPA via FastAPI `StaticFiles` directly** (no nginx in front). Stick with that for v1; the buffering pitfall is mostly a future-nginx concern.
- **If nginx is ever added later:** copy the exact config from `sse-starlette`'s README — `proxy_http_version 1.1; proxy_set_header Connection ''; proxy_buffering off; chunked_transfer_encoding off;` on the `/api/events` location.
- **Integration test:** assert end-to-end "admin PUT → kiosk SSE event" latency < 500 ms; run on every CI build (synthetic discogsography schema + real GRUVAX API + curl SSE consumer).

**Recovery:**
- Add the headers / nginx config; restart. No data is affected.

**Severity:** Major (UX disaster for a named differentiator; no data loss).

**Phase to address:** Backend Phase (SSE response headers), Ops Phase (if reverse proxy is ever introduced).

---

### Pitfall 9: Chromium kiosk goes into a restart loop and the Pi is unreachable

**What goes wrong:**
Chromium crashes (memory leak, GPU driver glitch, an upstream JS exception in the SPA). `systemd --user` restarts it. Crash repeats. The Pi's local display shows the Chromium error or a black screen; the screen is the only user-visible feedback; SSH is the only way to reach the Pi. If SSH is not pre-configured, the device is bricked-feeling until physical recovery.

**Specific symptom:**
- 7" screen shows "Aw, Snap!" or a black screen.
- `journalctl --user -u kiosk-chromium` shows repeated start/exit cycles within seconds.
- No keyboard attached; ssh is the only escape.

**Why it happens:**
A `systemd --user` unit with `Restart=always` and no rate limit will retry instantly. If the crash is deterministic (an SPA exception on load), the loop is infinite. Per STACK.md, `Restart=always` with a small `RestartSec` is recommended — without a *burst limit*, the loop is uncapped.

**Warning signs (detect early):**
- The `systemd --user` unit file does not set `StartLimitIntervalSec=` and `StartLimitBurst=`.
- No second tty/console enabled by default on the Pi.
- ssh keys not configured on the Pi at provisioning.

**Prevention:**
- **Set `StartLimitIntervalSec=120` and `StartLimitBurst=5`** in the systemd unit so 5 crashes in 2 minutes drops the unit into `failed` state. Use `RestartSec=10` so each retry is 10 s apart, giving you a window to ssh.
- **Enable ssh on the Pi at provisioning, with key auth.** Standard Pi OS step but specifically necessary for kiosk recovery.
- **Enable autologin on tty1** to a regular user shell as a fallback. Plugging in a USB keyboard then drops you into a shell.
- **Add a `/healthz` SPA route** that the systemd unit's `ExecStartPost` curl-checks; if the route doesn't respond within 30 s of Chromium launch, treat the launch as failed.
- **Run the SPA's `index.html` with a try/catch'd minimal-mode bootstrap** that always renders *something* — even just "GRUVAX failed to load, ssh to lux to check `/api/health`" — so the screen is never a black hole.

**Recovery:**
- Ssh to the Pi (`ssh pi@<ip>`), `systemctl --user status kiosk-chromium`, read the journal, fix the root cause (often: rebuild SPA after a JS error, redeploy).
- If ssh is broken: physical USB keyboard + tty1 fallback.

**Severity:** Major (operationally painful; no data loss).

**Phase to address:** Kiosk Setup Phase (systemd unit, ssh, autologin tty), Frontend Phase (minimal-mode bootstrap).

---

### Pitfall 10: Connection pool exhaustion under SSE + concurrent search

**What goes wrong:**
Each SSE connection on `/api/events` holds resources (a coroutine, an event-bus subscriber queue, an HTTP keep-alive). If the implementation accidentally holds a DB connection from the pool per SSE client (e.g., a dependency injection that opens a connection at request scope for an SSE endpoint), then with the kiosk + mobile + ssh-tunneled-dev-browser open, three of `psycopg_pool`'s 10 connections are pinned forever. A burst of type-ahead requests under that condition starves on the remaining pool, and the 200 ms latency SLO is gone.

**Specific symptom:**
- p95 search latency climbs from 30 ms to >500 ms after the kiosk has been up for hours.
- `psycopg_pool` metric `pool.size_used` stays at or near `pool.size_min`.
- Slow-query log (FEATURES.md Category 7) flags the offending requests.

**Why it happens:**
FastAPI's `Depends(get_db_session)` pattern usually checks out a connection for the request lifetime. SSE endpoints have a request lifetime of *hours*, not milliseconds. A naive `Depends` on the SSE endpoint pins a pool slot.

**Warning signs (detect early):**
- The SSE endpoint uses a `Depends(get_db)` style dependency.
- The boundary cache (ARCHITECTURE.md Pattern 3) is not implemented yet, so search is doing direct DB lookups.

**Prevention:**
- **The SSE endpoint does not depend on a DB session.** It depends only on the in-process event bus (ARCHITECTURE.md Pattern 2 — `bus.subscribe()` returns an `asyncio.Queue`, no DB touch). If the SSE endpoint ever *needs* DB data, it acquires a connection from the pool inline (`async with pool.connection() as conn:`) for that one query and releases it immediately, not for the lifetime of the SSE stream.
- **The boundary cache (ARCHITECTURE.md Pattern 3) loads boundaries at startup and on `boundary_changed` events.** Locate calls don't touch DB.
- **Size the pool for: 2× max concurrent SSE clients + 5 spare for searches.** With kiosk + mobile + dev, that's 6 + 5 = ~10. The default `psycopg_pool` 10 connections is fine.
- **Pool health in `/api/health`:** include `pool.size_used` and `pool.size_min` so a runaway is visible.
- **Background task that periodically logs pool stats** at INFO level; spike in `size_used` after long SSE uptime is the warning sign.

**Recovery:**
- Restart `gruvax-api` (drops all SSE clients; they reconnect via `EventSource` browser default backoff).
- Code fix is one-liner: replace the offending `Depends(get_db)`.

**Severity:** Major (degrades the Core Value SLO; recovery is a restart but root cause is sneaky).

**Phase to address:** Backend Phase (SSE endpoint pattern), Ops Phase (pool stat surfacing).

---

### Pitfall 11: Mosquitto data volume not persisting across container recreations

**What goes wrong:**
ARCHITECTURE.md prescribes `mosquitto-data` and `mosquitto-log` as named Docker volumes for persistence. If the operator runs `docker compose down -v` (the `-v` removes volumes) or if the Compose file's `volumes:` block is mistakenly removed or renamed, every Mosquitto restart loses all retained state. ESP32s (future) would reset their displayed state every redeploy.

**Specific symptom:**
- `mosquitto_sub -t '$SYS/broker/uptime'` resets to 0 after every compose redeploy.
- `mosquitto_sub -t 'gruvax/v1/leds/state/#' -v` returns nothing after a redeploy even though `gruvax-api` has not republished.
- `gruvax-api`'s `server/hello` retained announcement is gone after a Mosquitto restart.

**Why it happens:**
Docker volumes are named in the Compose file but are easily lost via `docker compose down -v` or a Compose file edit that breaks the volume mapping. Mosquitto requires `persistence true` AND `persistence_location /mosquitto/data/` AND a writable volume at that location.

**Warning signs (detect early):**
- Compose file does not declare `mosquitto.conf` with `persistence true`.
- `docker volume ls` doesn't show `gruvax_mosquitto-data` after first run.
- No documented runbook for "redeploying without losing state."

**Prevention:**
- **Mosquitto config `persistence true; persistence_location /mosquitto/data/; autosave_interval 30`** baked into `mosquitto/mosquitto.conf` (ARCHITECTURE.md project structure).
- **Named volumes (not bind mounts) for `mosquitto-data` and `mosquitto-log`** in Compose (ARCHITECTURE.md compose example).
- **Document `docker compose down` (no `-v`) as the redeploy path** in the project README. Reserve `-v` for "I want to wipe state."
- **Runbook entry: "Wiping retained state intentionally"** so operators can do it deliberately rather than discovering it accidentally.
- **Per Pitfall 3, do not rely on retained state for correctness anyway.** Hardware-milestone firmware MUST tolerate "no retained state" (the first-ever boot case) gracefully.

**Recovery:**
- If retained state is lost: in v1 (no hardware), no impact. In hardware milestone: republish current desired state via a "refresh all" admin button (publish `state/{unit}/{row}/{col}` for every cube based on current `cube_boundaries`).

**Severity:** Major (matters in hardware milestone; harmless in v1 stub).

**Phase to address:** Ops Phase (Compose + Mosquitto config), Hardware Milestone (refresh-all admin button, firmware tolerant of empty initial state).

---

### Pitfall 12: Single PIN shared in plain text and never rotated

**What goes wrong:**
PIN is set once at deployment, stored Argon2id-hashed in `gruvax.settings` (per ARCHITECTURE.md), but the operator emails the plaintext PIN to a friend during a demo, or writes it on a sticky note near the kiosk. Two years later, the PIN is "everyone in three houses" and no one has rotated it.

**Specific symptom:**
- No mechanism in the admin UI to change the PIN.
- The PIN's hash in `gruvax.settings.auth.pin_hash` has not been updated in months/years.
- `gruvax.admin_sessions` has rows from unknown user agents.

**Why it happens:**
Single-PIN is a deliberate v1 simplification (PROJECT.md). It's the right call. But "change PIN" is small in scope and easily deferred forever in a one-operator product.

**Warning signs:**
- The admin Settings page has color picker rows but no "Change PIN" row.
- The deployment runbook says "set PIN_HASH in env" but doesn't say "rotate periodically."

**Prevention:**
- **Ship "Change PIN" in v1 admin Settings.** Tiny endpoint: `PUT /api/admin/settings/pin` (rate-limited, requires current PIN as a confirmation). Writes new Argon2id hash to `gruvax.settings`.
- **Login revokes all other sessions** of the same admin label on PIN change. `admin_sessions.revoked_at` set for all rows except the new one.
- **Diagnostics surface "PIN last changed Y days ago"** so the operator notices when it's been too long. Cosmetic, not enforced.
- **Argon2id hash with `passlib[argon2]`** (STACK.md) so even a DB leak doesn't expose PINs.
- **The PIN is never logged.** Login route logs `pin_attempt: redacted`, not the actual digits, even at DEBUG.

**Recovery:**
- If PIN exposure is suspected: open admin (with current PIN), change PIN, all sessions revoked. Sticky note story over.

**Severity:** Major (security hygiene; not catastrophic on a home LAN but unprofessional to omit).

**Phase to address:** Admin Phase (Change PIN endpoint + Settings UI row), Ops Phase (runbook line about rotation).

---

### Pitfall 13: CSRF on admin state-changing endpoints not enforced

**What goes wrong:**
Admin is logged in on mobile (session cookie present). Admin opens an unrelated site that issues a `POST /api/admin/cubes/bulk` from a `<form>` or `<img src>` (less for POST, but `fetch` with cookie credentials does it). Same-origin policy doesn't apply because the cookie's SameSite isn't tight enough, or the admin clicks a phishing link. Boundaries get overwritten without the admin's knowledge.

**Specific symptom:**
- `boundary_history` shows an unauthorized `change_set_id` not initiated by the admin.
- Cubes light up wrong on the kiosk; admin investigates and finds someone else's POST.

**Why it happens:**
Cookie-based auth is vulnerable to CSRF by default. ARCHITECTURE.md prescribes the double-submit cookie pattern (`gruvax_csrf` non-HttpOnly cookie + `X-CSRF-Token` header). If that's forgotten or partially implemented, CSRF risk is real.

**Warning signs:**
- The double-submit pattern is mentioned in ARCHITECTURE.md but not enforced in the admin middleware.
- No 403 returned when a request has a session cookie but no `X-CSRF-Token` header.

**Prevention:**
- **Implement the double-submit token check as middleware** on all admin state-changing routes. `PUT/POST/PATCH/DELETE` under `/api/admin/*` require `X-CSRF-Token` to equal the `gruvax_csrf` cookie value. Missing or mismatched → 403.
- **`SameSite=Strict` on the session cookie** (ARCHITECTURE.md uses `Lax` for the session, `Strict` for the CSRF). Strict on session cookie further reduces cross-site request risk but breaks "user clicks a link to /admin from email." For home LAN with no email-driven workflow, `SameSite=Strict` on both cookies is the right call.
- **The login response sets both cookies and returns the CSRF token in the response body** so the SPA can stash it. Frontend `fetch` wrapper adds `X-CSRF-Token` automatically on admin requests.
- **Test:** an integration test that sends an admin POST with a valid session cookie but missing CSRF header — expect 403.

**Recovery:**
- If a CSRF-fueled change happens: revert via `boundary_history` (one tap). Rotate PIN. Investigate.

**Severity:** Major (real attack vector even on home LAN if any houseguest's device is compromised).

**Phase to address:** Backend Phase (CSRF middleware + cookie configuration), Test Phase (negative test).

---

### Pitfall 14: Volume permissions break on first boot (non-root container can't write)

**What goes wrong:**
STACK.md Dockerfile creates a non-root user `gruvax` (uid 10001) and `USER gruvax` at the end. On first boot, Compose mounts the named volumes (e.g., for mosquitto, or any bind-mount for static files), and they're owned by root. The container starts as `gruvax` and gets `Permission denied` writing logs or migrating the DB.

**Specific symptom:**
- `docker compose up` fails with `PermissionError: [Errno 13] Permission denied: '/app/static/...'` or similar.
- Mosquitto fails with `Error: Unable to open '/mosquitto/data/mosquitto.db': Permission denied`.
- The Pi-OS bind-mounted `static/` directory has uid 1000:1000 from the host, not 10001:10001.

**Why it happens:**
Named Docker volumes are created with the *image's* user ownership at first use, but only if the Dockerfile `chowns` the mount point during build. For bind mounts to host directories, the host's uid is what counts. Mosquitto's official image uses uid 1883; if you `chown` the named volume to 10001, Mosquitto can't write.

**Warning signs:**
- The Dockerfile doesn't `chown` future-mount directories during build.
- The Compose file uses bind mounts (`./mosquitto/passwd:...:ro`) without verifying host-side ownership.

**Prevention:**
- **`mosquitto.conf` and `passwd` are bind-mounted read-only** (`:ro` per ARCHITECTURE.md) — the container doesn't need to write them, so host-side uid doesn't matter.
- **Named volumes for writable state** (`mosquitto-data`, `mosquitto-log`) inherit the container's uid on first use; Mosquitto's image handles this internally for its own uid.
- **GRUVAX container does not bind-mount writable host directories.** Static files are baked into the image (or copied at startup from a read-only mount).
- **If a writable bind mount is unavoidable:** `chown 10001:10001` the host path during provisioning (document in runbook).
- **Test: `docker compose up` on a fresh host (no existing volumes)** — must succeed first time.

**Recovery:**
- Bind-mount-related: `chown` the host path, retry.
- Named-volume-related: `docker volume rm <vol>` and recreate.

**Severity:** Major (blocks first-time deployment; well-understood once seen, easy to miss in dev).

**Phase to address:** Ops Phase (Dockerfile + Compose review on fresh host).

---

### Pitfall 15: discogsography sync staleness hides "newly added but unfindable"

**What goes wrong:**
Owner adds 30 records to their Discogs collection from a record-fair haul. discogsography's sync schedule (whatever it is) hasn't run yet. Owner walks to the kiosk to file the new haul into cubes, types a new title — "no results." They assume they typo'd; they try variants; they give up and shelve by hand without GRUVAX confirming the position. The new records are misshelved by humans who lost faith in the tool.

**Specific symptom:**
- Search returns no results for records the owner knows they just added.
- Admin diagnostics shows `last_synced` is 2-3 days old.
- The wizard's autocomplete is missing recently-added titles.

**Why it happens:**
discogsography runs its own sync schedule; GRUVAX is a passive reader. Sync latency is invisible from the GRUVAX UI unless explicitly surfaced.

**Warning signs (detect early):**
- The kiosk SPA has no indicator of sync staleness.
- No "force sync" admin action exists (it'd live in discogsography, not GRUVAX; but a one-click trigger would help).

**Prevention:**
- **Surface sync staleness in admin diagnostics** (FEATURES.md Category 7 differentiator). `last_synced` = `max(v_collection.synced_at)`. If older than 24 h, render a yellow warning. If older than 7 days, render red.
- **Kiosk shows a subtle banner if `last_synced` > 7 days:** "Collection last updated 8 days ago — recently added records may not appear yet." Doesn't disable search; informs the user.
- **Admin has a "request sync" button** that hits discogsography's API (or its MCP server) to trigger a sync. Out-of-band call; surfaces sync as a deliberate operator action, not a mystery.
- **Search "no results" page suggests checking sync staleness:** "No matches found. Last collection sync was X hours ago — try the admin Diagnostics page."

**Recovery:**
- Owner triggers sync in discogsography; GRUVAX picks up automatically.
- For the immediate shelf job: owner manually edits boundaries for the new records using catalog numbers (wizard works without `v_collection` validation if the user accepts a "force save" toggle — but this opens Pitfall 2, so default-off).

**Severity:** Major (UX disaster for the "I just got back from the fair" use case which is precisely when GRUVAX should shine).

**Phase to address:** Admin Phase (diagnostics + banner), Kiosk Phase (no-results suggestion text).

---

### Pitfall 16: Animations that look great in dev feel laggy on the Pi 5

**What goes wrong:**
The "selection lands" choreography (FEATURES.md Category 2 differentiator) is designed on a fast Mac in Chrome DevTools and approved by stakeholders. On the Pi 5 + 7" screen + Chromium-on-Wayland, the same GSAP timeline drops frames during the highlight pulse. The Core Value moment feels broken.

**Specific symptom:**
- DevTools Performance trace on the Pi shows long animation frames (>16 ms) during the "cube pulse" segment.
- The "feels snappy" promise of <200 ms TTI is undermined by a janky 600 ms animation that follows it.
- Layout thrashing during the multi-cube label-span dim-in.

**Why it happens:**
Pi 5 GPU is fine for WebGL but Chromium's compositor on Wayland + animating many DOM elements (32 cubes) with simultaneous `transform`, `opacity`, AND `box-shadow` transitions can blow the 60fps budget. Box-shadow especially is a known offender.

**Warning signs:**
- Animation tests only run on the developer's laptop.
- The cube grid uses `box-shadow` for the glow effect rather than a separate compositor layer.
- No `will-change` hints on animated elements.

**Prevention:**
- **Test animations on the actual Pi 5 + 7" screen as part of the frontend phase**, not deferred to "kiosk setup." Hardware-in-the-loop animation review before stakeholder sign-off.
- **Animate transform + opacity only** for the GPU-cheap path. The glow effect is a separate absolutely-positioned layer with `opacity` transitions, not `box-shadow` on the cube itself.
- **`will-change: transform, opacity`** on cubes that the user has interacted with (don't set globally — defeats the purpose).
- **Cap the animation timeline at 400 ms total**, not 600. Faster feels more responsive even if it loses some choreography drama.
- **Frame-budget test in CI** (Playwright + the Pi as a runner if practical): assert <16 ms p95 frame time during the "search lands" timeline.

**Recovery:**
- Profile, simplify animation, re-test.

**Severity:** Major (undermines Core Value perception; not data-related).

**Phase to address:** Frontend Phase (animation design), Hardware Setup Phase (Pi-side frame-budget check).

---

## Minor Pitfalls

### Pitfall 17: Touchscreen fingerprints make the dark theme unreadable

**What goes wrong:**
The mockup is dark/monospace/gold (PROJECT.md). Looks great in screenshots. On a touchscreen used daily near vinyl-handling (fingertips have a film of slipmat/dust), the dark theme amplifies fingerprint smears. Readability drops in real-world lighting.

**Specific symptom:**
- Two weeks in, the owner squints at the screen because the dark background reflects ambient and shows every smudge.
- Houseguests report needing to wipe the screen before searching.

**Why it happens:**
Mockups are evaluated under ideal lighting and clean screens. Real-world conditions for a kiosk *at the shelves* include uneven LED lighting, occasional sunlight if the shelves are near a window, and finger oils.

**Warning signs:**
- All UI evaluation happens in a non-kiosk environment.
- No "light mode" toggle even as an experimental setting.

**Prevention:**
- **Test the kiosk in its actual mounting location** during the UI design phase. Take a photo at the actual touchscreen position with normal kitchen/living-room lighting.
- **Use higher contrast than the mockup suggests** — pure black backgrounds suffer the most fingerprint impact. A near-black like `#0a0a0c` or even a deep neutral helps.
- **Ship an admin-toggled "high contrast" mode** as a v1 setting (cheap; same Tailwind tokens).
- **Buy a matte-finish screen protector** as part of the hardware budget — it kills 80% of fingerprint glare.

**Recovery:**
- Toggle high contrast. Buy screen protector. Done.

**Severity:** Minor (annoying, not blocking).

**Phase to address:** UI Design Phase (real-conditions evaluation), Hardware Setup Phase (screen protector).

---

### Pitfall 18: Color-blind admin can't distinguish label-span from primary-cube highlight

**What goes wrong:**
Admin-configurable colors (PROJECT.md Active scope) default to (e.g.) red for primary cube and green for label-span. A red-green color-blind visitor sees both highlights as similar olive, can't tell which cube to walk to. Even the admin, picking colors, doesn't realize the defaults fail accessibility.

**Specific symptom:**
- Houseguest with deuteranopia / protanopia uses the kiosk and asks "which cube?"
- Admin's chosen palette has too-similar luminance between primary and span.

**Why it happens:**
"RGB LED" implies color-as-information. For color-blind users (~8% of men), color-only signaling fails. Both UI and LED layers are affected.

**Warning signs:**
- Default color settings in `gruvax.settings.led_color.*` are red+green or other deuteranopia-collapsed pairs.
- The color picker UI doesn't show a contrast/distinguishability score.
- No non-color signal (animation, brightness, size) distinguishes primary from span.

**Prevention:**
- **Pick defaults that are color-blind-safe:** primary = warm yellow/gold (e.g. `#FFD700`), span = deep purple (e.g., `#7C3AED`). These have high luminance contrast AND distinct hue under all common forms of color blindness.
- **Brightness *and* color** differentiate: span at 30-50% brightness, primary at 100% brightness. Even if a viewer can't see hue at all, brightness conveys "this one matters more."
- **Distinct animation:** primary cube pulses, span cubes are static. Motion is an information channel.
- **Sub-cube position bar is always the *highest* contrast** against the cube background. It's the most precise affordance; don't hide it behind subtle color.
- **In the admin color picker, show a "color-blind preview"** that simulates deuteranopia/protanopia/tritanopia (matrix transformation; cheap, well-documented).
- **Sub-cube bar has a distinct shape (a thin horizontal line)** so position is conveyed by shape and location even without color.

**Recovery:**
- Admin re-picks colors. If a houseguest hits this once, the color-blind preview in the picker prevents repeat.

**Severity:** Minor (rare; admin-configurable; only critical if accessibility is a stated requirement).

**Phase to address:** UI Design Phase (defaults + color-blind preview), Backend Phase (settings schema supports per-state brightness as well as color).

---

### Pitfall 19: Browser cache holds stale SPA bundle after a redeploy

**What goes wrong:**
Operator redeploys GRUVAX with a fixed JS bug. The kiosk's Chromium loads the cached old `bundle-abc123.js` because the HTML still points there or because of an aggressive cache header. The bug appears fixed in dev but persists on the kiosk for hours.

**Specific symptom:**
- A confirmed-fixed bug still reproduces on the kiosk.
- DevTools Network panel on the kiosk (via remote debugging) shows the old bundle hash.
- Hard-refresh fixes it.

**Why it happens:**
Vite emits content-hashed asset filenames (`bundle-abc123.js` → `bundle-def456.js`), and `index.html` is regenerated to point at the new hash. But `index.html` itself, if cached with a long max-age or by a service worker, still points at the old hash. Or, if you serve `index.html` with `Cache-Control: public, max-age=3600`, the kiosk holds the stale one for up to an hour.

**Warning signs:**
- Static file serving (FastAPI `StaticFiles`) uses default cache headers.
- A service worker is added without a `skipWaiting`/`clientsClaim` strategy.

**Prevention:**
- **`index.html` is served with `Cache-Control: no-store, max-age=0`.** Always fresh.
- **Hashed assets (JS/CSS) are served with `Cache-Control: public, max-age=31536000, immutable`.** Hash change = new filename = automatic cache bust.
- **If a service worker is added (FEATURES.md Category 6 differentiator):** use Workbox `precacheAndRoute` with `skipWaiting()` and `clientsClaim()` on activate; the kiosk receives the new SW on next reload and immediately swaps.
- **Kiosk auto-reloads daily at, say, 4 AM** via a small SPA timer: if the build hash from `/api/version` differs from the loaded build hash, reload. Cheap insurance.

**Recovery:**
- Hard-refresh the kiosk; or, ssh + remote-debugging-port reload.

**Severity:** Minor (annoying after every deploy; trivially preventable).

**Phase to address:** Backend Phase (StaticFiles cache headers), Frontend Phase (build hash check + auto-reload).

---

### Pitfall 20: Log volume blows up disk on `lux` or Pi

**What goes wrong:**
Default Python logging at INFO + Uvicorn access logs + Mosquitto info logs + Compose default log driver (json-file with no size limit) → tens of MB per day → after a year, gigabytes of logs on `lux`'s SSD. Or on the Pi: kiosk Chromium dumps GPU warnings to journald, which grows unboundedly.

**Specific symptom:**
- `df -h` on `lux` shows /var/lib/docker filling up.
- `journalctl --disk-usage` on the Pi exceeds a GB.
- Performance unaffected until disk fills, then writes fail catastrophically.

**Why it happens:**
Docker's default `json-file` log driver has no rotation. Mosquitto in default config logs everything. Chromium emits a lot of warnings to stderr that journald captures.

**Warning signs:**
- Compose file lacks `logging:` directives.
- `mosquitto.conf` has `log_type all` or default verbose settings.

**Prevention:**
- **Compose `logging` directive on each service:** `driver: json-file, options: {max-size: "10m", max-file: "3"}`. Caps each service at 30 MB.
- **Mosquitto:** `log_type error, warning, notice` (drop `information` and `debug`).
- **Python logging at INFO in production, DEBUG only in dev.** `LOG_LEVEL` env (STACK.md).
- **Uvicorn `--access-log` only in dev**; in prod, structlog at INFO captures requests with timing and skips per-request access-log noise.
- **journald on the Pi:** set `SystemMaxUse=500M` in `/etc/systemd/journald.conf`.
- **Healthcheck-related: monitor disk in admin diagnostics** — `df` of `/var/lib/docker` exposed in `/api/admin/diagnostics`.

**Recovery:**
- `docker compose down && docker system prune --volumes=false` cleans logs. Then add the limits and restart.

**Severity:** Minor (catches operators who don't monitor; once limits are in place, never again).

**Phase to address:** Ops Phase (Compose logging + Mosquitto config + journald), Admin Phase (diagnostics disk row).

---

### Pitfall 21: Single-record label rendered identically to a multi-record label

**What goes wrong:**
A label that owns exactly one record produces a `label_span` with one cube and a `sub_cube_interval` that's a single point. The UI renders the interval bar at zero width — invisible. The user sees a cube highlighted but no precision indicator, and thinks the system is broken.

**Specific symptom:**
- Search lands on a cube; the cube glows but no sub-cube bar appears.
- For multi-record labels, the bar appears correctly.

**Why it happens:**
Interval rendering naively scales `(end - start) × cube_width`. For a zero-width or near-zero-width interval, the rendered element is invisible. Single-record labels are the edge case the implementation never sees in dev (where data is denser).

**Warning signs:**
- The CSV (3K records) has a tail of labels with a single record each.
- The frontend `SubCubeBar.tsx` does not have an explicit single-point case.

**Prevention:**
- **Single-record labels render a tick mark** (vertical line with a small dot) at the exact position, not an interval bar (FEATURES.md Category 2 differentiator already calls this out).
- **Interval-width threshold:** if `(end - start) < 0.02`, render as a tick. Otherwise render as a bar with rounded caps.
- **Position-estimator returns `crosses_boundary: false, sub_cube_interval: {start: X, end: X}` for single-record cases**; frontend branches on width.
- **Hypothesis property test:** for every label with `count(releases) == 1` in the seed CSV, `/api/locate` returns `sub_cube_interval.start == sub_cube_interval.end` (or a small fixed delta), and the frontend renders a visible tick.

**Recovery:**
- Add the tick render branch.

**Severity:** Minor (small UX bug; high-frequency for labels with 1 record).

**Phase to address:** Frontend Phase (SubCubeBar tick render).

---

### Pitfall 22: Auto-suggested boundary midpoint picks an empty zone

**What goes wrong:**
The wizard's "auto-suggest boundary" feature (FEATURES.md Category 3 differentiator) takes two adjacent cubes' boundaries and proposes the midpoint catalog number. If the owner's collection has a long gap in catalog numbers (e.g., they own `BLP 4001-4050` and then `BLP 4500+`, nothing in between), the midpoint (`BLP 4275`) is a catalog number with zero records, and the suggested boundary is a phantom.

**Specific symptom:**
- Wizard suggests `BLP 4275` as a boundary; user accepts; next time someone searches `BLP 4150`, the position estimator interpolates against a phantom anchor and returns a wrong cube.

**Why it happens:**
The suggestion algorithm computes a midpoint in *catalog number space*, not in *collection density space*. For dense labels, this is fine. For sparse labels with gaps, it's wrong.

**Warning signs:**
- The `POST /api/admin/cubes/suggest` endpoint takes adjacent cube IDs and returns a catalog number without consulting `v_collection`.
- Wizard does not show "this is between record X and record Y in your collection" alongside the suggestion.

**Prevention:**
- **Suggestion algorithm walks `v_collection`, not catalog-number space.** Given two adjacent cubes' last record and first record, suggest a midpoint *by index in the sorted collection*, not by string interpolation. The midpoint is *always* a real record (or, if there are an even number of records between, one of the two middle records).
- **Wizard UI shows "this is between [record A] and [record B]"** alongside the suggested boundary value so the user has context.
- **Suggestion is a hint, not a commit.** Wizard always shows a confirm step. The diff preview (FEATURES.md Category 3) is the safety net.

**Recovery:**
- If a phantom boundary is committed: admin opens history, reverts. Or runs the wizard for that cube only with the corrected algorithm.

**Severity:** Minor (rare; depends on collection sparsity per label) but worth fixing once.

**Phase to address:** Admin Phase (suggest endpoint algorithm), Frontend Phase (wizard context display).

---

### Pitfall 23: Idle timer doesn't expire on the kiosk because nobody's idle

**What goes wrong:**
Kiosk admin session is opened on the touchscreen during a reshuffle. The owner walks back and forth to the shelves, occasionally touching the screen to update boundaries. From the SPA's perspective, the session is active (each touch counts). But if the owner is interrupted (phone call, dinner) and walks away mid-session, the kiosk shows the admin view to anyone passing by until natural idle timeout (5-10 min).

**Specific symptom:**
- Admin walks away; visiting child taps "delete all boundaries" before idle timeout fires.

**Why it happens:**
Sliding-window TTL refreshes on every request. For an actively-used session, "actively used" means "touched within idle threshold," which doesn't distinguish "owner actively editing" from "the screen is just on and a visitor leaned on it."

**Warning signs:**
- No physical proximity sensor.
- Admin session length unlimited by anything other than idle.

**Prevention:**
- **Hard cap on admin session lifetime regardless of activity.** E.g., 30 minutes from login, even if continuously active. Forces re-PIN on long sessions; reduces window for an unattended admin view.
- **Visible idle countdown in admin UI** (FEATURES.md Category 3 already prescribes this for the < 60 s warning).
- **"Lock admin" button at the bottom of the admin view** — single tap re-shows PIN screen without logging out. Like a sleep button. Owner taps it before walking away.
- **Tab visibility hidden → reduce TTL to 60 s.** When the SPA's `document.visibilityState` becomes `hidden` (kiosk's screen goes off, or browser tabs away), kick off a 60 s shorter countdown.

**Recovery:**
- Idle timeout fires; or owner taps Lock; or worst case, history table's append-only nature means destructive operations are undoable.

**Severity:** Minor (single-operator home; the social risk is small but non-zero).

**Phase to address:** Backend Phase (hard cap in session middleware), Frontend Phase (Lock button, visibility hidden listener).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|---|---|---|---|
| Skip the `v_collection` view, query `discogsography.releases` directly | One less Alembic migration, no view to maintain | Every upstream schema change is a multi-file sweep across GRUVAX. The "view as read-only contract surface" pattern (ARCHITECTURE.md Pattern 4) loses its value. Pitfall 5 recovery time goes from minutes to hours. | **Never.** The view is cheap; the discipline pays off the first time discogsography refactors. |
| Skip CSRF middleware; rely on `SameSite=Lax` cookie | One less middleware to wire | Pitfall 13 is real on home LAN if any device on the LAN is ever compromised. CSRF on admin POST/PUT is table stakes. | **Never** for state-changing admin routes. Acceptable only for GET-only diagnostic endpoints (no state change → no CSRF surface). |
| Skip the boundary cache; query `cube_boundaries` on every `/api/locate` | One less data structure | Pitfall 10 + estimator latency budget gone (32 rows fetched, parsed, sorted on every call) | **Never** in production. The cache is ~50 lines (ARCHITECTURE.md Pattern 3). |
| Use Pydantic field names `id` everywhere instead of `release_id`/`collection_item_id` | Less typing | Pitfall 6 — silent confusion of identities | **Never** in API surfaces. Acceptable inside private functions where the type signature makes the meaning unambiguous. |
| Single-cube per-request save in the wizard instead of bulk | Simpler endpoint | Pitfall 7 — partial-commit during interruption | **Never** for the wizard's commit step. Acceptable for the per-cube *single edit* endpoint that exists for the cube editor route. |
| Hard-coded color defaults instead of configurable | Less data model surface | Pitfall 18 — accessibility miss | **Never** for the LED color path. Acceptable for very minor UI accents (focus rings, etc.). |
| Use `box-shadow` for the cube glow because it looks pretty | Looks good in mockup | Pitfall 16 — frame budget on Pi | **Never** without testing on the Pi. Acceptable for non-animated chrome (cards at rest). |
| Skip the in-app virtual keyboard, rely on squeekboard | One fewer component to build | Pitfall 4 — kiosk admin fallback non-functional | **Never** in v1. Acceptable only when labwc/labwc#2926 is officially closed-fixed and the fix has shipped in Raspberry Pi OS. |
| Skip Idempotency-Key on admin bulk endpoint | Tiny endpoint simpler | Pitfall 7's safety net is gone; a flaky Wi-Fi double-tap on Save commits twice. | **Never** for state-changing admin endpoints. |
| Use `--access-log` in production Uvicorn | One less custom logger | Pitfall 20 — log volume; AND Pitfall 9 isolation — every search shows up in access log, including search queries (privacy concern per FEATURES.md Category 9) | **Never** in production. Use structlog with explicit fields and suppress query bodies. |
| Bind-mount the SPA build directory from host to container | Hot reload on file change | Pitfall 14 — volume permissions; and "what the image contains" diverges from "what runs" | Acceptable only in dev. Production: bake the SPA into the image. |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|---|---|---|
| **discogsography Postgres** | `SELECT * FROM discogsography.releases r JOIN ...` directly in GRUVAX code | Define `gruvax.v_collection` view; application code reads only from the view (ARCHITECTURE.md Pattern 4). |
| **discogsography Postgres** | Granting `gruvax_app` user `INSERT/UPDATE/DELETE` on discogsography tables "for future flexibility" | Grant `SELECT` only. Migration is the only way to widen access. (ARCHITECTURE.md grant pattern.) |
| **discogsography FTS** | Building a separate `tsvector` on the GRUVAX side and indexing it | Use `releases.fts_vector` from discogsography (exposed via the view). If discogsography removes the column, GRUVAX builds a materialized view as fallback (ARCHITECTURE.md read-only contract table). |
| **Mosquitto** | Publishing without `keep_alive` set; broker disconnects after default 60 s of silence | `aiomqtt.Client(..., keep_alive=30)` per STACK.md / ARCHITECTURE.md Pattern 1. |
| **Mosquitto** | Setting `clean_start=True` and losing in-flight QoS 1 packets across reconnects | `clean_start=False, session_expiry_interval=86400` for persistent sessions (Context7-verified aiomqtt pattern). |
| **Mosquitto** | Forgetting LWT (last-will-and-testament); future ESP32s can't detect a dead `gruvax-api` | Configure `will=aiomqtt.Will("gruvax/v1/server/hello", payload=b'{"alive": false}', retain=True)` (ARCHITECTURE.md Pattern 1). |
| **Mosquitto** | Publishing every retained state on every API call, ballooning broker state | Only publish retained on `state/*` topics (the desired-state topics); commands (`illuminate`, `sub`, etc.) are non-retained (ARCHITECTURE.md topic design). |
| **Postgres connection pool** | Letting SSE endpoint hold a connection for its lifetime | SSE endpoint depends only on the in-process event bus; no DB dependency (Pitfall 10). |
| **Postgres connection pool** | Default pool size with no monitoring | Size the pool for `2× max concurrent SSE clients + 5`; expose `pool.size_used` in `/api/health` (Pitfall 10). |
| **Alembic** | Running `alembic upgrade head` from application startup *and* CI without coordination → race when two containers boot | Migrate before container starts (entrypoint script runs `alembic upgrade head`, then `exec uvicorn ...`). Only one container should run migrations; use a Compose `init` container or just rely on the single-instance reality of this deployment. |
| **Alembic** | Forgetting Alembic naming conventions on `Base.metadata` → unstable autogenerated migration filenames across machines | Set explicit naming convention on `MetaData` (STACK.md Alembic best practice). |
| **discogsography sync timing** | Assuming sync is real-time | Surface sync staleness in admin diagnostics + kiosk banner (Pitfall 15). |
| **discogsography release identifiers** | Using `id` interchangeably for `release_id` and `collection_item_id` | Always name fields explicitly; Pydantic models on every endpoint (Pitfall 6). |
| **Chromium kiosk** | Snap-packaged Chromium (missing GPU integration) | apt-packaged Chromium with `--ozone-platform=wayland` (STACK.md). |
| **Chromium kiosk** | `unclutter` for cursor hiding (X11 only) | Wayland cursor hiding via labwc config (STACK.md). |
| **Chromium kiosk** | Auto-restart with no rate limit; restart loop drains the Pi | `systemd --user` unit with `StartLimitIntervalSec=120, StartLimitBurst=5` (Pitfall 9). |
| **Chromium kiosk** | Letting compositor blank the screen → offline banner unreachable on touch | Black-screen-on-idle is an app-level concern (CSS+JS), not compositor-level (STACK.md). |
| **squeekboard on-screen keyboard** | Assuming it works under labwc fullscreen Chromium | It doesn't (labwc#2926). Build in-app keypad (Pitfall 4). |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|---|---|---|---|
| **No debounce on type-ahead** | Server CPU climbs per keystroke; results lag | 100-150 ms debounce + `useDeferredValue` (FEATURES.md) | When the user types fast (every typer). |
| **No boundary cache** | Locate latency variable; DB CPU climbs proportional to QPS | ARCHITECTURE.md Pattern 3 — load 32 rows into memory, invalidate on event | When `/api/locate` exceeds ~100 QPS (not realistic v1, but easy to forget) |
| **`useTransition` and `useDeferredValue` not used in React 19** | Render frames blocked by setState during typeahead | React 19 + Compiler handles most of this; opt into `useDeferredValue` for the deferred query string | Visible at low end of Pi 5 capability when frame rates are tight |
| **SSE without `ping=15`** | Proxies (if added later) kill the long-lived connection silently | `sse-starlette` default `ping=15` keeps the line warm (Context7-verified) | When any reverse proxy is introduced and not configured for SSE |
| **`box-shadow` animations on 32 elements** | Frame drops during cube highlight choreography | Animate `transform`+`opacity` only; glow as separate layer with opacity (Pitfall 16) | On Pi 5 under Wayland during the "selection lands" moment |
| **`Depends(get_db)` on SSE endpoint** | Pool exhaustion under multiple long-lived clients | SSE depends only on event bus, no DB (Pitfall 10) | After hours of kiosk uptime + admin sessions |
| **Full collection scan for "did you mean"** | First search after deploy is slow | `pg_trgm` GIN index on `releases.label`/`releases.title` (FEATURES.md Category 1) | When the index is missing or hasn't been analyzed |
| **Logging at DEBUG in production** | Disk fills, journald slows | LOG_LEVEL=info in prod; per-route filter on search endpoint (privacy) | Within weeks on a chatty service |
| **Per-request connection in MQTT publish** | TCP setup adds 5-10 ms per illuminate call; Mosquitto sees connect/disconnect churn | Single long-lived `aiomqtt.Client` in lifespan (ARCHITECTURE.md Pattern 1) | Always — never use per-request MQTT clients |
| **No `Idempotency-Key` on bulk save; user retries → double-commit** | Two `change_set_id` rows in history for one user action | Idempotency-Key header on all admin mutating endpoints (ARCHITECTURE.md) | First flaky Wi-Fi save during a wizard run |
| **No keyset pagination on history list** | `OFFSET` queries get slower as history grows | Cursor-based pagination (ARCHITECTURE.md) | Around 1k history rows (years out) |
| **Search returns 200 results when 20 suffice** | Frontend renders all rows; layout cost | `limit` default 20, max 50 (ARCHITECTURE.md) | Always — keep results bounded |
| **Recently-pulled list in localStorage grows unbounded** | localStorage quota hit; SPA fails to mount on next load | Cap at 10 items (FEATURES.md Category 1) | After heavy use sessions |
| **In-process event bus subscriber queue unbounded** | Slow SSE consumer backpressure → memory growth | `asyncio.Queue(maxsize=64)` with drop-on-full (ARCHITECTURE.md Pattern 2) | If a kiosk hangs but keeps the TCP connection open |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---|---|---|
| **PIN compared with `==` instead of constant-time** | Timing attack reveals PIN | `secrets.compare_digest` on a hash comparison; never compare raw PINs (STACK.md). |
| **PIN logged in any form** | DB leak → PIN leak | Login route logs `pin_attempt: redacted`; never log the digits; verify with structlog field filter. |
| **PIN hash with `bcrypt` cost 4 for "fast tests"** | Brute force feasible | Argon2id with default `passlib` params; same config in tests (test slowness is fine — it's a single auth call per test). |
| **No rate limit on `/api/admin/login`** | Brute force from any LAN device | 5 attempts per 5 minutes per IP, exponential backoff (ARCHITECTURE.md failure modes). |
| **Session cookie without `HttpOnly`** | XSS reads session token | `HttpOnly=True, Secure=True, SameSite=Strict` on session cookie (ARCHITECTURE.md). |
| **CSRF cookie HttpOnly** | SPA can't read it to add the header → no CSRF protection | CSRF cookie is *not* HttpOnly; session cookie *is* HttpOnly (double-submit pattern, ARCHITECTURE.md). |
| **CSRF not enforced on admin mutating routes** | Cross-site request forgery from any LAN-shared device | Middleware enforces `X-CSRF-Token` header on `PUT/POST/PATCH/DELETE /api/admin/*` (Pitfall 13). |
| **Mosquitto broker exposed to LAN with no auth** | Anyone on LAN can publish "all off" or arbitrary LED states | v1: no `ports:` mapping (broker Compose-internal only). Hardware milestone: `ports: ["1883:1883"]` bound to LAN interface AND username/password auth required (ARCHITECTURE.md v1 stub vs hardware milestone table). |
| **Mosquitto username/password in plaintext in env var visible via `docker inspect`** | Inspect leaks credential | Use Docker secrets, or restrict `docker` socket to root, or accept the LAN-only blast radius. For v1 home LAN, env var in `.env` (gitignored) is the pragmatic call; rotate on any compromise. |
| **Static-served frontend exposing source maps in production** | Code structure visible to anyone with kiosk URL | Vite config: `build.sourcemap = false` for production builds. |
| **Search query body logged in plaintext** | Privacy floor breach (FEATURES.md Category 9) | Search endpoint logs `query: redacted` at INFO; only counts go to `gruvax.search_counters`. |
| **PIN-reset path that doesn't require knowing the old PIN** | Account takeover from anyone with admin URL | "Change PIN" requires current PIN as confirmation (Pitfall 12). For "I forgot my PIN" — recovery is operator with shell access running an SQL update; not a UI feature. |
| **Allowing search results to leak collection details to anyone on LAN** | Visiting devices on LAN can enumerate the collection | Acceptable per PROJECT.md (single-owner home LAN). Surface the fact in the README so future "extend to guest network" decisions are conscious; consider IP allowlist if the LAN spans untrusted Wi-Fi. |
| **No revocation of sessions on PIN change** | Old session still works after rotation | PIN change endpoint sets `revoked_at` on all other sessions (Pitfall 12). |
| **Long-lived session cookies persist after device loss** | Phone-out-of-pocket = open admin | Hard cap on session lifetime (Pitfall 23) + idle timeout. |
| **MQTT broker accepts anonymous in dev `mosquitto.conf` and the dev config ships** | Production accepts anonymous publishes | `allow_anonymous false` in `mosquitto.conf`; password file required. Same config in dev. |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---|---|---|
| **No "no results" state** | User types something, sees blank space, doesn't know if it's loading or empty | Explicit "No matches for X" with sync-staleness hint (Pitfall 15) |
| **Loading spinner < 300 ms** | Flicker more distracting than helpful | Show spinner only after 300 ms; render nothing for fast responses (FEATURES.md) |
| **Cube highlighted but no sub-cube indicator for single-record labels** | User stares at the screen looking for the bar | Render tick for single-record (Pitfall 21) |
| **Sub-cube bar at zero width** | Same as above | Same fix |
| **Animation drama > 600 ms** | Feels slow even if the API was fast | Cap at 400 ms; interruptible (Pitfall 16) |
| **Empty cube rendered identically to populated cube** | User confused about which cubes contain records | Distinct empty-state visual (FEATURES.md Category 2) |
| **Reverse-lookup not supported ("what's in cube 18?")** | User points at a cube, can't ask the kiosk | Tap a cube → side panel shows first/last + sample (FEATURES.md Category 2 differentiator) |
| **Search history visible across visitors** | Houseguest searches Y, owner sees on next visit | Session-scoped only; "Reset kiosk" button (FEATURES.md Category 9) |
| **Tap target < 44pt** | Touchscreen frustration | All interactive elements ≥ 44pt (FEATURES.md Category 1 — Clear button) |
| **Dark theme + bright lighting + fingerprint smears** | Unreadable in real-world conditions | Test in actual environment; high-contrast mode (Pitfall 17) |
| **Color-only signaling (label-span vs primary)** | Color-blind users can't distinguish | Brightness + motion + color (Pitfall 18) |
| **Idle screen blank with no way to wake** | Visitor touches screen, nothing happens for 2 seconds | Screen wakes on touch immediately; offline banner reachable through black screen |
| **Admin session expires mid-wizard, work lost** | Wizard form resets to blank on re-login | Persist wizard state in localStorage; resume on next login (Pitfall 7) |
| **Kiosk admin requires physical keyboard** | No keyboard available; squeekboard broken | In-app numeric keypad (Pitfall 4) |
| **"Reset" / "Clear" semantics ambiguous** | User unsure if "Reset" wipes the boundary or just clears the form | Distinct labels: "Clear form" (UI only) vs "Reset to saved" (re-fetch) vs "Restore default" (per-cube empty) |
| **Offline banner doesn't say "search disabled while offline"** | User keeps tapping the disabled input | Placeholder text changes to "Reconnecting…"; clear visual disabled state (FEATURES.md Category 6) |
| **Reconnection success has no feedback** | User unsure if connection came back | Brief green tick / banner fade (FEATURES.md Category 6) |
| **Wizard doesn't show progress** | User unsure how many cubes are left | Progress indicator ("Cube 5 of 32") in wizard header |
| **No "find it again" affordance after closing the result** | User searches the same record three times in a row | Recently-pulled list (FEATURES.md Category 1 differentiator) |
| **Admin diagnostics buried** | Operator never finds the sync-staleness indicator | Diagnostics is a top-level route under `/admin/diagnostics` (ARCHITECTURE.md route tree) |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Search:** Often missing typo tolerance — verify `pg_trgm` extension installed AND GIN index built; test with a deliberately misspelled query.
- [ ] **Position estimator:** Often missing single-record-label case — verify Hypothesis property "single-record label produces a tick, not a bar" passes.
- [ ] **Position estimator:** Often missing multi-cube label-span case — verify a label with records spanning ≥2 cubes (use the seed CSV — Blue Note runs are the canonical case) produces `label_span.length >= 2`.
- [ ] **Position estimator:** Often missing the "label not in any cube boundary" case — verify confidence=0 result, not a 500.
- [ ] **Boundary save:** Often missing validation against `v_collection` — verify saving a `(label, catalog#)` that doesn't exist in the collection is rejected (or warned with a "force save" affordance gated by acknowledging Pitfall 2).
- [ ] **Boundary save:** Often missing comparator-based first <= last check — verify `first_catalog > last_catalog` per the *normalized* comparator (not raw string) is rejected.
- [ ] **Wizard:** Often missing atomic-bulk save — verify mid-wizard interruption leaves DB unchanged; only "Save reshuffle" mutates.
- [ ] **Wizard:** Often missing resume-on-reload — verify reloading the page mid-wizard preserves `pendingChangeSet` from localStorage.
- [ ] **CSV/YAML import:** Often missing per-row error reporting — verify a single bad row produces a clear error message AND blocks the whole import (no partial commit).
- [ ] **CSV/YAML import:** Often missing dry-run preview — verify upload shows diff before committing.
- [ ] **Admin auth:** Often missing CSRF — verify state-changing admin request with no `X-CSRF-Token` returns 403.
- [ ] **Admin auth:** Often missing PIN rotation — verify admin Settings has "Change PIN" and changing revokes other sessions.
- [ ] **Admin auth:** Often missing rate limiting on login — verify 6 wrong PIN attempts in a minute returns 429.
- [ ] **Admin auth:** Often missing hard cap on session — verify a continuously-active session forces re-PIN after 30 min.
- [ ] **Admin auth:** Often missing "Lock admin" button — verify the kiosk admin UI has a one-tap re-lock affordance.
- [ ] **SSE:** Often missing `X-Accel-Buffering: no` header — verify the SSE response includes this header (curl -I).
- [ ] **SSE:** Often missing 15 s ping — verify `sse-starlette` is configured with `ping=15` (default; check the configuration didn't get overridden).
- [ ] **SSE:** Often missing reconnection-friendly headers — verify `Cache-Control: no-store` on SSE response.
- [ ] **SSE:** Often missing graceful shutdown — verify `event: server_shutdown` is emitted on lifespan shutdown, and reconnects pick up `event: server_hello` on reboot.
- [ ] **SSE:** Often missing pool-free implementation — verify the SSE endpoint does not pin a DB connection (use `psycopg_pool` stats to verify under load).
- [ ] **MQTT publish:** Often missing fire-and-forget timeout — verify a stopped Mosquitto does NOT block `/api/illuminate` more than 250 ms.
- [ ] **MQTT publish:** Often missing retained-state expiry — verify `gruvax/v1/leds/state/#` payloads have `message_expiry_interval` set.
- [ ] **MQTT publish:** Often missing LWT — verify `mosquitto_sub -t 'gruvax/v1/server/hello' -v` shows `{"alive": true}` while gruvax-api is up.
- [ ] **MQTT publish:** Often missing "all off" actually clearing retained — verify `POST /api/admin/leds/off` publishes empty retained payloads to each `state/{unit}/{row}/{col}`, not just an "off" command.
- [ ] **MQTT publish:** Often missing per-environment topic prefix — verify dev and prod use distinct topic prefixes.
- [ ] **MQTT auth:** Often missing `allow_anonymous false` — verify Mosquitto config rejects unauthenticated connections.
- [ ] **MQTT auth:** Often missing per-device ACLs (hardware milestone only) — flag for that milestone.
- [ ] **discogsography read-only contract:** Often missing the view — verify all SQL in GRUVAX references `gruvax.v_collection`, never `discogsography.releases` directly. Grep `discogsography\.` in `src/` should return zero hits (outside the migration that creates the view).
- [ ] **discogsography read-only contract:** Often missing the grant — verify the `gruvax_app` Postgres role has only `SELECT` on discogsography schema.
- [ ] **discogsography read-only contract:** Often missing the view-health probe — verify `/api/health` includes `discogsography_view_check`.
- [ ] **Sync staleness:** Often missing UI surface — verify admin Diagnostics shows "last synced N hours ago" prominently.
- [ ] **Sync staleness:** Often missing kiosk banner — verify kiosk shows banner if sync > 7 days old.
- [ ] **Kiosk:** Often missing in-app keypad — verify the kiosk PIN entry works without an external keyboard.
- [ ] **Kiosk:** Often missing systemd restart limits — verify the unit file has `StartLimitIntervalSec` and `StartLimitBurst`.
- [ ] **Kiosk:** Often missing ssh + tty1 fallback — verify ssh works AND a USB keyboard at tty1 drops into a shell.
- [ ] **Kiosk:** Often missing minimal-mode SPA bootstrap — verify if JS errors prevent SPA mount, the user sees a non-empty page with a recovery hint.
- [ ] **Kiosk:** Often missing the auto-reload-on-build-hash-change — verify the kiosk picks up a new build within minutes of redeploy.
- [ ] **Kiosk:** Often missing cache-headers correctness — verify `index.html` has `no-store`; hashed assets have `immutable`.
- [ ] **Kiosk:** Often missing animation-on-Pi verification — verify frame times in the "selection lands" animation are < 16 ms p95 on the Pi.
- [ ] **Kiosk:** Often missing real-environment screen evaluation — verify the design has been viewed at the actual kiosk position with actual lighting.
- [ ] **Color settings:** Often missing color-blind preview — verify the picker shows a deuteranopia simulation.
- [ ] **Color settings:** Often missing brightness-as-information — verify primary cube and label-span differ in brightness, not just hue.
- [ ] **Idempotency:** Often missing on bulk admin endpoints — verify a duplicate `Idempotency-Key` does not double-commit.
- [ ] **Offline:** Often missing connectivity detection logic — verify the offline banner appears within 30 s of `lux` becoming unreachable.
- [ ] **Offline:** Often missing reconnection animation — verify a green tick / banner-fade appears on reconnect.
- [ ] **Volumes:** Often missing first-boot test on fresh host — verify `docker compose up` on a host with no pre-existing volumes succeeds first try.
- [ ] **Volumes:** Often missing log limits — verify Compose `logging.options.max-size` is set on each service.
- [ ] **Logs:** Often missing access-log suppression in prod — verify `--access-log` is not passed in production Uvicorn args.
- [ ] **Logs:** Often missing search-query redaction — verify search query content is not in logs.

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---|---|---|
| **1** Catalog comparator wrong | MEDIUM | Add normalization rule, add failing Hypothesis test, ship; admin "re-validate all boundaries" tool surfaces affected cubes. |
| **2** Phantom boundary | LOW | Run wizard for affected cubes (diagnostics surfaces the list); auto-suggested midpoint based on `v_collection` indexing. |
| **3** Retained-state ghosts | LOW (v1), MEDIUM (hardware milestone) | One-shot script publishes empty retained to each ghost topic; or delete `/mosquitto/data/mosquitto.db` for nuclear option. |
| **4** Squeekboard breaks kiosk admin | LOW | Ship the in-app keypad as a hotfix; no data impact. |
| **5** discogsography view breaks | LOW | One-line view migration; `alembic upgrade head`; redeploy. |
| **6** release_id vs instance_id confusion | MEDIUM | Rename fields, add Pydantic models; frontend update; ship together. |
| **7** Partial wizard commit | LOW | Admin reverts the partial change set in history view; runs wizard atomically. |
| **8** SSE proxy buffering | LOW | Add response headers; if nginx, add `proxy_buffering off`; no data impact. |
| **9** Chromium restart loop | LOW | Ssh to Pi; `systemctl --user stop kiosk-chromium`; fix root cause; restart. |
| **10** Pool exhaustion | LOW | Restart gruvax-api; fix offending `Depends(get_db)`; redeploy. |
| **11** Mosquitto volume lost | LOW (v1), MEDIUM (hardware) | v1: no impact. Hardware: republish-all admin button. |
| **12** PIN exposure | LOW | Change PIN in admin Settings; sessions revoked automatically. |
| **13** CSRF breach | LOW | Revert via history; rotate PIN; investigate. |
| **14** Volume permissions | LOW | `chown` host path or recreate named volume; document in runbook. |
| **15** Sync staleness UX | LOW | Add banner + diagnostics; force a sync in discogsography. |
| **16** Pi animation jank | MEDIUM | Profile, simplify (animate transform+opacity only), retest on Pi. |
| **17** Dark-theme fingerprint | LOW | Toggle high contrast mode; add screen protector. |
| **18** Color-blind misread | LOW | Admin re-picks colors using color-blind preview. |
| **19** Stale SPA cache | LOW | Hard-refresh; or wait for auto-reload-on-build-hash. |
| **20** Log disk fill | LOW | `docker compose down && docker system prune --volumes=false`; add Compose logging limits; restart. |
| **21** Single-record label tick missing | LOW | Add tick render branch in `SubCubeBar.tsx`. |
| **22** Auto-suggested phantom boundary | LOW | Admin reverts; reshape suggest algorithm to walk `v_collection`. |
| **23** Unattended admin session | LOW | Idle timeout fires; or history-revert any destructive action. |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls. Phase names below are project-domain labels — exact phase identifiers belong to the roadmap.

| Pitfall | Severity | Prevention Phase | Verification |
|---|---|---|---|
| **1** Catalog-number sort | Critical | Position-estimator Research → Backend Phase | Hypothesis property tests pass for the seed CSV's mixed-separator labels |
| **2** Phantom boundaries | Critical | Backend Phase (validate endpoint) → Admin Phase (UI wires it) → Ops (periodic diagnostic) | Integration test: save a `(label, catalog#)` that's not in `v_collection` is rejected; `/api/admin/diagnostics` exposes `phantom_boundary_count` |
| **3** MQTT retained-state ghosts | Critical | Backend Phase (publish wrapper) → Hardware Milestone (runbook) | `mosquitto_sub -t 'gruvax/v1/leds/state/#' -v` returns nothing after `POST /api/admin/leds/off` |
| **4** Squeekboard / kiosk admin | Critical | UI Design / Frontend Phase | Manual: PIN entry on a clean Pi 5 + 7" works without external keyboard |
| **5** discogsography schema change | Critical | Backend Phase (view-health probe) → Ops Phase (CI integration + pinning) | `/api/health` shows `discogsography_view_check: ok`; CI test passes on a current discogsography schema |
| **6** release_id confusion | Critical | Backend Phase (Pydantic models) → Test Phase (two-copies fixture) | Integration test: synthetic CI dataset with duplicate release_id passes |
| **7** Partial wizard commit | Major | Admin Phase (bulk endpoint + Idempotency-Key) → Frontend Phase (localStorage persist) | Manual: kill the page mid-wizard; reload preserves draft; DB unchanged |
| **8** SSE proxy buffering | Major | Backend Phase (response headers) | Integration test: admin PUT → kiosk SSE event < 500 ms; verify `X-Accel-Buffering: no` header present |
| **9** Chromium restart loop | Major | Kiosk Setup Phase (systemd + ssh + tty1) → Frontend Phase (minimal-mode bootstrap) | Manual: simulate a JS error; verify systemd backs off after 5 restarts; ssh works |
| **10** Pool exhaustion | Major | Backend Phase (SSE endpoint pattern + pool stats in /health) | Load test: 5 SSE clients + 100 QPS search; `pool.size_used` stays < 80% |
| **11** Mosquitto volume loss | Major | Ops Phase (Compose + Mosquitto config) → Hardware Milestone (republish-all button + tolerant firmware) | Test: `docker compose restart mosquitto`; verify retained state survives |
| **12** PIN rotation | Major | Admin Phase (Change PIN endpoint + Settings UI) | Manual: change PIN; verify other sessions revoked; verify rate limit on login |
| **13** CSRF on admin | Major | Backend Phase (CSRF middleware) → Test Phase (negative test) | Integration test: admin POST with session cookie but no `X-CSRF-Token` returns 403 |
| **14** Volume permissions | Major | Ops Phase (Dockerfile + Compose review on fresh host) | Test: `docker compose up` on a fresh VM succeeds first try |
| **15** Sync staleness UX | Major | Admin Phase (diagnostics) → Kiosk Phase (banner + no-results hint) | Manual: stop discogsography sync for 8 days; verify red diagnostics + kiosk banner |
| **16** Pi animation jank | Major | Frontend Phase (animation design) → Hardware Setup Phase (Pi-side test) | Playwright frame-budget test on Pi 5: p95 frame time < 16 ms during "selection lands" |
| **17** Fingerprint readability | Minor | UI Design Phase (real-conditions evaluation) → Hardware Setup Phase (screen protector) | Manual: review the kiosk at its mounting location with normal lighting |
| **18** Color-blind safety | Minor | UI Design Phase (defaults + color-blind preview) → Backend Phase (brightness in settings) | Visual review of admin color picker; verify defaults pass deuteranopia simulation |
| **19** Stale SPA cache | Minor | Backend Phase (StaticFiles cache headers) → Frontend Phase (build-hash auto-reload) | Manual: deploy a change; verify kiosk picks it up within minutes without hard-refresh |
| **20** Log disk fill | Minor | Ops Phase (Compose logging + Mosquitto config + journald) | Manual: `du -sh /var/lib/docker/containers/*/` is bounded after a week |
| **21** Single-record label tick | Minor | Frontend Phase (SubCubeBar) | Hypothesis test + visual: a single-record label renders a visible tick |
| **22** Auto-suggested phantom | Minor | Admin Phase (suggest endpoint algorithm) → Frontend Phase (wizard context) | Unit test: suggest endpoint walks `v_collection`, returns a real record's catalog number |
| **23** Unattended admin session | Minor | Backend Phase (hard cap) → Frontend Phase (Lock button + visibility listener) | Manual: open admin, walk away; verify hard cap fires at 30 min even with continuous activity |

---

## Project / Process Pitfalls

Distinct from technical pitfalls — these are about *what to build when* and how to avoid sinking time into the wrong slice.

### P1: Over-engineering the boundary admin UX before the search loop works

**What:** Investing weeks in the wizard / CSV / diff-preview before the search → locate → cube-highlight path is end-to-end demoable.

**Why it bites:** Without the search loop, you have no way to validate that the data model (boundary semantics, sort order, label-span) actually answers the Core Value question. You can ship a beautiful admin UI for boundaries that *can't be queried correctly* and not realize until much later.

**Prevention:** ARCHITECTURE.md's "Critical path to a demoable v1" (~6.5 days) gets a stub estimator behind the real `/api/locate` contract before any admin UX work. **Build the search loop end-to-end with a stub estimator first**; only then build the admin tools that populate the boundaries. The boundary data can be seeded from a hand-edited YAML during the search-first phase.

**Severity:** Major.

---

### P2: Building the position estimator without the real data

**What:** Designing the algorithm using a synthetic dataset that doesn't reflect the real CSV's quirks (mixed case, mixed separators, single-record labels, sparse labels with gaps).

**Why it bites:** The synthetic dataset is too clean. The real CSV has labels like `Twelve 002` vs `TWELVE 003` (PROJECT.md). An estimator that passes synthetic-data tests can fail on the real data the first day in production.

**Prevention:**
- Position-estimator research stream uses the local CSV (gitignored per PROJECT.md) for validation runs.
- CI uses a *shape-matching* synthetic dataset (similar label distribution, similar format mix) — STACK.md prescribes this.
- Hypothesis tests assert invariants that the real data must satisfy (e.g., "no two boundaries claim the same release").

**Severity:** Major.

---

### P3: Designing LED endpoints in a vacuum (without imagining the firmware)

**What:** Locking the LED MQTT contract based on what's convenient for `gruvax-api` to publish, not what's reasonable for an ESP32 + WS2812B to consume.

**Why it bites:** The hardware milestone implementor inherits an awkward contract — pixel ranges that don't map cleanly to physical strips, color formats that require firmware-side translation, retain semantics that fight the WS2812B's stateful nature. v1 ships LED endpoints that need a breaking change before hardware lands.

**Prevention:**
- ARCHITECTURE.md's MQTT topic design already pre-validates against recordShelf's contract and the ESP-WIFI-NEOPIXEL-CONTROL reference patterns (FEATURES.md sources).
- Normalize `sub_cube_interval` as 0..1 (not pixel indices) so firmware owns the pixel count (ARCHITECTURE.md).
- Use JSON payloads with a `schema` field so the contract can evolve incrementally (ARCHITECTURE.md).
- Have a research artifact: "if I were the firmware, what messages would I want to receive?" Write a one-page mock firmware loop in pseudocode that consumes the contract. Adjust the contract if pseudocode is awkward.

**Severity:** Major.

---

### P4: Deferring offline behavior until too late

**What:** Building the kiosk SPA assuming `lux` is always reachable; bolting on the offline banner at the end.

**Why it bites:** The first time `lux` reboots after a Compose update, the kiosk shows a JS error screen for 30 seconds before the SPA realizes it's offline. Refresh logic, query-cache strategy, SSE reconnection all become hostile add-ons rather than first-class concerns.

**Prevention:**
- Build offline detection in the same phase as the SSE channel — they share the connectivity state machine (ARCHITECTURE.md Zustand store: `connectivity.sseConnected`).
- TanStack Query stale-while-revalidate is the default, not an addition. Adopt early.
- FEATURES.md flagged the service-worker cache as "RECONSIDER for v1" — decide in requirements phase rather than deferring forever.

**Severity:** Minor (in the sense that it's recoverable, but adds friction if deferred).

---

### P5: Scoping the screensaver in v1 by accident

**What:** PROJECT.md is explicit: "Screensaver / browse / cover-art slideshow mode — black screen on idle for v1." But scope-creep pressure leads to "just a simple slideshow…"

**Why it bites:** A slideshow adds: image caching, idle-state machine, screen blanking interaction, accessibility considerations, performance on the Pi, AND it interacts with the offline banner (what shows when offline-and-idle?). What looked like a Saturday-afternoon polish is a 2-week distraction.

**Prevention:**
- Treat PROJECT.md Out-of-Scope items as hard boundaries.
- If pressure builds, *first* land a "v1.x backlog ticket with rationale" rather than start implementing.
- The CSV is gitignored and `background/` is gitignored — physical reminders that the rich-media surface isn't the v1 target.

**Severity:** Minor (process; the harm is opportunity cost).

---

### P6: Treating discogsography as "free" when its schema is a moving target

**What:** Assuming GRUVAX can rely on whatever discogsography ships, treating the read-only view as a permanent stable surface.

**Why it bites:** discogsography is a separate project under active development by the same person. Schema changes will happen. Treating it as "free infrastructure" means GRUVAX has no protection.

**Prevention:**
- The `gruvax.v_collection` view is the contract surface (ARCHITECTURE.md Pattern 4).
- discogsography is pinned to a specific tag in Compose (Pitfall 5).
- The view-health probe runs at startup (Pitfall 5).
- The "read-only contract" table in ARCHITECTURE.md documents exactly which columns GRUVAX depends on; that table is the spec for "what discogsography MUST keep."
- Communicate the contract back upstream: open a GitHub discussion in discogsography ("GRUVAX depends on these columns") so the maintainer (the same person) has a written reminder.

**Severity:** Major.

---

### P7: Letting the position-estimator research stream block the rest of v1

**What:** Treating "the algorithm isn't done" as a reason to delay the search UI, the admin tools, the LED endpoints.

**Why it bites:** Per ARCHITECTURE.md, the algorithm is a research stream that can iterate indefinitely behind a fixed contract. If it's allowed to block other work, the demoable-in-6.5-days promise evaporates.

**Prevention:**
- ARCHITECTURE.md prescribes a stub estimator that returns plausible-but-trivial values behind the real contract.
- All non-algorithm work depends on the *contract*, not the algorithm. The contract is fixed in week 1.
- The algorithm gets its own quality bar (Hypothesis properties, golden tests, p95 latency) and ships when it meets the bar — independent of the rest of v1.

**Severity:** Major (process).

---

## Sources

### Authoritative (Context7-verified)

- **`/empicano/aiomqtt`** — automatic reconnection, retained-message semantics, QoS 1/2 retransmit, persistent sessions with `clean_start=False` (HIGH confidence; verified during this research)
- **`/sysid/sse-starlette`** — default 15 s ping, `X-Accel-Buffering: no` header recommendation, nginx config snippet (`proxy_buffering off; chunked_transfer_encoding off;`), `EventSource` client reconnection (HIGH confidence; verified during this research)

### Direct prior art / Domain references (via FEATURES.md research)

- **recordShelf (Hackaday)** — RFID reliability failure mode → motivates the computed-boundary approach; informs LED contract patterns. MEDIUM (Hackaday writeup).
- **DSpace batch metadata editing** — CSV-upload diff/preview pattern → informs Pitfall 7 prevention.
- **Postgres pg_trgm "did you mean" guide (Viget)** — verified the typo-tolerant search approach; underlies prevention for Pitfall 1's "did you mean" hint, Pitfall 2's near-miss suggestion.

### Stack & architecture references (via STACK.md / ARCHITECTURE.md)

- **STACK.md** — squeekboard fullscreen bug (`labwc/labwc#2926`); Chromium kiosk supervision via `systemd --user`; passlib[argon2] for PIN hashing; pinned versions for `aiomqtt`, `sse-starlette`, FastAPI 0.136.x.
- **ARCHITECTURE.md** — view-as-contract pattern (Pattern 4); boundary cache (Pattern 3); in-process event bus (Pattern 2); single MQTT client in lifespan (Pattern 1); history append-only (Pattern 5); compose volume + Mosquitto config; failure-mode table.
- **FEATURES.md** — privacy floor (Category 9); sync staleness UX (Category 7); reshuffle wizard (Category 3); LED contract surface (Category 4); offline banner + service-worker reconsider (Category 6).
- **PROJECT.md** — explicit v1 boundaries; CSV-gitignored constraint; single-PIN auth; deterministic ordering invariant.

### Community / Issue trackers

- **labwc/labwc#2926** — squeekboard fullscreen issue (HIGH confidence; it's an open bug, verified by reading the issue title in STACK.md sources).
- **Raspberry Pi forums (kiosk patterns)** — labwc autostart + Chromium kiosk supervision community patterns (MEDIUM).

### Confidence by category

| Pitfall category | Confidence | Reason |
|---|---|---|
| 1 Position estimation | MEDIUM-HIGH | Algorithm is open; pitfalls describe contract-level dangers that hold regardless of algorithm choice. |
| 2 Boundary table | HIGH | All anchored to PROJECT.md scope + ARCHITECTURE.md schema. |
| 3 Discogs / discogsography | HIGH | View pattern is well-defined; failure modes documented in ARCHITECTURE.md. |
| 4 Postgres / shared DB | HIGH | Well-trodden territory; specific to STACK.md/ARCHITECTURE.md choices. |
| 5 Chromium kiosk | HIGH | Squeekboard bug verified; systemd patterns standard. |
| 6 MQTT / LED stub | HIGH | Context7-verified aiomqtt semantics; topic design from ARCHITECTURE.md. |
| 7 SSE / realtime | HIGH | Context7-verified sse-starlette headers + ping. |
| 8 Auth / security | HIGH | Standard threat model for cookie-session apps; ARCHITECTURE.md prescribes double-submit. |
| 9 Docker Compose / ops | HIGH | Boring infrastructure; specific to ARCHITECTURE.md compose example. |
| 10 UX / human-at-kiosk | MEDIUM | UX research draws on general kiosk best practices; some accessibility points are well-supported, fingerprint observation is real-world. |
| 11 Project / process | HIGH | Pitfalls anchored to ARCHITECTURE.md critical-path analysis. |

---

*Pitfalls research for: GRUVAX — touchscreen kiosk + REST API + MQTT-stubbed LED layer for finding vinyl on Kallax shelves.*
*Researched: 2026-05-18*

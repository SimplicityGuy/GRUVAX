# GRUVAX Architecture

Canonical architecture reference, verified against the live codebase (`src/gruvax/`,
`migrations/`) as shipped through **v2.1 (Resilience + Privacy + UX polish)**. The
planning trail lives in [`.planning/`](../.planning/); shipped-milestone detail lives in
[`.planning/milestones/`](../.planning/milestones/).

GRUVAX has been through three milestones:

- **v1.0 MVP** — single implicit collection, read directly from discogsography's Postgres
  via a `gruvax.v_collection` view.
- **v2.0 Multi-User Collections** — re-architected onto discogsography's HTTP API with
  per-profile, owner-managed Personal Access Tokens (PATs); `v_collection` retired.
- **v2.1 Resilience + Privacy + UX polish** — member self-connect invites, QR pairing,
  offline/reconnect UX, collection-diff badges, shelf fill-overview.

This document describes the **v2.1 system as built and deployed**. Sections describing
functionality that does not exist yet in code are explicitly labeled **(Future)**.

---

## 1. Data Model

### Schema

GRUVAX owns exactly one Postgres schema, `gruvax`, in a Postgres instance shared with
discogsography. Unlike v1.0, GRUVAX **no longer reads discogsography's tables directly**
— the connection pool's `search_path` is the single literal `gruvax, public` (see
`src/gruvax/db/pool.py`). The only integration surface with discogsography is its HTTP
API (§7 "discogsography integration").

### Tables in `gruvax`

| Table | Purpose |
|-------|---------|
| `profiles` | One row per collection owner. `display_name`, `discogs_username`, `discogsography_user_id`, Fernet-encrypted `app_token_encrypted` (the PAT), `app_token_revoked`, `last_sync_at` / `last_sync_status` / `last_sync_error` / `last_sync_item_count`, `last_new_record_count` / `last_sync_is_initial` (collection-diff badge, v2.1), `deleted_at` (soft delete). A deterministic default row (`00000000-0000-0000-0000-000000000001`, `'Default'`) backfills v1 data. |
| `profile_collection` | Local per-profile cache of the owner's Discogs collection, paged in from discogsography's API and rebuilt on every sync (staging-swap). PK `(profile_id, release_id, folder_id)`. Weighted `fts_vector` (A=catalog_number, B=title, C=artist/label) + GIN(fts) + composite `(profile_id, label, catalog_number)` index + GIN trigram(artist, title). `first_seen_at` (v2.1) records GRUVAX-side cache arrival for the diff badge. **This table is GRUVAX's only source of collection data — there is no live read against discogsography's DB.** |
| `units` | Physical Kallax unit registry (id, label, position). Not profile-scoped (shared shelving hardware inventory). |
| `cube_boundaries` | Per-cube cut-point row: `profile_id`, `unit_id`, `row`, `col`, `first_label`, `first_catalog`, `is_empty` (Phase 5 migration 0005 dropped `last_*` columns — now derived). `profile_id` NOT NULL as of migration 0010. |
| `segment_overrides` | Optional admin-configured physical-width fractions per label-segment per bin, scoped to `profile_id`. |
| `boundary_history` | Append-only audit log of every boundary mutation, scoped to `profile_id`; `change_set_id` groups batch operations; one-tap undo works per change-set. |
| `admin_sessions` | PIN-gated admin session tokens (Starlette-style signed cookie; expires by `expires_at`; hard cap). Scoped to `profile_id`. |
| `settings` | Key/value LED and system settings (colors, brightness, TTL, nominal capacity, idle threshold, sync cadence, `auth.pin_hash`), scoped to `profile_id`. **The admin PIN hash lives here, not in an environment variable.** |
| `idempotency_keys` | Short-lived keys for wizard bulk-commit idempotency, scoped to `profile_id`. |
| `record_stats` | Durable per-`release_id` search and selection counters (no query text stored), scoped to `profile_id`. |
| `devices` | Persists the device-to-profile binding for a registered RPi kiosk. Identified by an opaque `HttpOnly` fingerprint cookie value. `profile_id` is nullable (`ON DELETE SET NULL`) — a profile soft-delete orphans the device rather than cascade-deleting it; the kiosk falls back to the profile picker. `revoked_at` gates access. |
| `pairing_codes` | Short-lived `CHAR(4)` kiosk pairing codes, 5-minute TTL, one-shot `consumed_at` guard (atomic `UPDATE ... WHERE consumed_at IS NULL RETURNING ...`, "first wins" under concurrent binds). |
| `profile_invite_codes` | Single-use, 1-hour-TTL UUID invite tokens for **member self-connect** (v2.1): a member redeems the link and pastes their own PAT directly — the owner never sees it. |

`cube_boundaries`, `segment_overrides`, `boundary_history`, `admin_sessions`,
`idempotency_keys`, `record_stats`, and `settings` are the "7-table fanout" that gained a
`profile_id` foreign key in migrations 0009 (nullable, default-UUID backfill) and 0010
(promoted to `NOT NULL`).

### `gruvax.v_collection` — retired

v1.0's cross-schema view (`gruvax.v_collection`, a read-only join over discogsography's
`releases` + `collection_items` tables) was **dropped in migration 0009** along with the
read-only grant. It no longer exists in the running schema. GRUVAX's only contact surface
with discogsography is now its HTTP API (§7); `profile_collection` is populated by
paging that API into GRUVAX's own tables, never by a live cross-database read.

---

## 2. API Surface

All routes are under the `/api` prefix. The `StaticFiles` SPA mount is registered last so
it does not intercept API paths (router registration order pitfall — see `app.py`).

Most collection-facing endpoints are **profile-scoped**: they accept an optional
`profile_id` query parameter and otherwise resolve the authoritative profile from the
`gruvax_browse_binding` session cookie or the `gruvax_device_fp` kiosk fingerprint cookie
via `resolve_profile_from_request`. A supplied `profile_id` that disagrees with the
resolved cookie/device profile returns `403 profile_mismatch`.

### Public / kiosk endpoints (no PIN)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/search` | Full-text + trigram + catalog-number-boosted search, scoped to a profile (`?q=&limit=&profile_id=`) |
| `GET` | `/api/locate` | Position estimate for a release (`?release_id=&profile_id=`) → `LocateResult` |
| `GET` | `/api/units` | Unit + cube grid configuration |
| `GET` | `/api/cubes` | All cubes with boundary data |
| `GET` | `/api/cubes/{unit_id}/{row}/{col}` | Single cube boundary + fill level + sample records |
| `POST` | `/api/illuminate` | LED fan-out via MQTT (`IlluminateRequest` payload, `?profile_id=`) — intentionally unauthenticated (D-03: worst case is lighting the wrong cube) |
| `GET` | `/api/events/{profile_id}` | Per-profile SSE stream — kiosk subscribes here for realtime updates |
| `GET` | `/api/health` | Per-subsystem reachability + default-profile sync staleness |
| `GET` | `/api/version` | Git SHA + build timestamp |
| `GET` | `/api/session` | Bootstrap: `{profile_count, bound_profile_id, profiles[]}`; auto-binds when exactly one active profile exists |
| `POST` | `/api/session/bind` | Set the browse-binding cookie for a chosen `profile_id` (profile picker) |
| `DELETE` | `/api/session/bind` | Clear the browse-binding cookie ("Switch profile") |
| `POST` | `/api/devices/pairing-codes` | Kiosk requests a 4-digit pairing code (5-min TTL); issues the fingerprint cookie on first call |
| `GET` | `/api/devices/me` | Kiosk polls its own device state: `unpaired` \| `pending` \| `paired` \| `revoked` |
| `GET` | `/api/invite-codes/{code}` | Look up an outstanding member self-connect invite (validity check) |
| `POST` | `/api/invite-codes/{code}/redeem` | Member redeems the invite and pastes their own PAT — owner never sees the plaintext token |

### Admin endpoints (PIN-gated — `POST /api/admin/login` required; CSRF double-submit on all mutating verbs)

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/admin/login` | Exchange PIN for signed session + CSRF cookies (rate-limited: 5 attempts / 5 min / IP → 429) |
| `POST` | `/api/admin/logout` | Revoke session row + clear cookies |
| `GET` | `/api/admin/session` | Check session validity / expiry |
| `GET` | `/api/admin/cubes` | List all cubes (admin view) |
| `GET` | `/api/admin/cubes/{u}/{r}/{c}/boundary` | Get single cube boundary |
| `PUT` | `/api/admin/cubes/{u}/{r}/{c}/boundary` | Update single cube boundary |
| `POST` | `/api/admin/cubes/validate` | Validate a proposed boundary set |
| `POST` | `/api/admin/cubes/suggest` | Suggest label/catalog autocomplete |
| `POST` | `/api/admin/cubes/bulk` | Wizard bulk-commit (idempotent via key) |
| `GET` | `/api/admin/cubes/{u}/{r}/{c}/segments` | Segment view for a cube |
| `PUT` | `/api/admin/cubes/{u}/{r}/{c}/cut` | Set/update a cut point |
| `POST` | `/api/admin/cubes/{u}/{r}/{c}/overrides` | Set label-segment width overrides |
| `POST` | `/api/admin/cubes/insert-cut` | Insert a new cut point within a cube |
| `GET` | `/api/admin/history` | Boundary change log |
| `POST` | `/api/admin/history/{change_set_id}/revert` | Undo a change set |
| `GET` | `/api/admin/settings` | Get LED + system settings |
| `PUT` | `/api/admin/settings` | Update settings |
| `POST` | `/api/admin/settings/pin` | Change admin PIN (hashed with Argon2id, stored in `gruvax.settings`) |
| `POST` | `/api/admin/editing` | Broadcast `admin_editing` SSE event |
| `GET` | `/api/admin/labels` | List unique labels (for autocomplete) |
| `GET` | `/api/admin/labels/{label}/catalogs` | List catalog numbers for a label |
| `GET` | `/api/admin/export/boundaries.yaml` | Download current boundaries as YAML |
| `GET` | `/api/admin/export/settings.yaml` | Download current settings as YAML |
| `POST` | `/api/admin/import/boundaries` | Import boundaries from YAML or CSV (`?dry_run=true` for preview) |
| `POST` | `/api/admin/import/settings` | Import settings from YAML |
| `POST` | `/api/admin/leds/off` | Send all-LEDs-off to MQTT (clears retained state) |
| `POST` | `/api/admin/leds/diagnostic` | Schedule server-driven LED state sweep over MQTT |
| `GET` | `/api/admin/diagnostics` | Ring buffers + slow-query ring + pool stats + per-profile sync diagnostics |
| `POST` | `/api/admin/diagnostics/reset-stats` | Reset `record_stats` counters |
| `GET` | `/api/admin/profiles` | List all profiles (name, last sync, item count, status badge) |
| `GET` | `/api/admin/profiles/{profile_id}` | Get one profile |
| `POST` | `/api/admin/profiles` | Create a profile (placeholder row, no PAT yet) |
| `PATCH` | `/api/admin/profiles/{profile_id}` | Rename / update a profile |
| `DELETE` | `/api/admin/profiles/{profile_id}` | Soft-delete a profile (detaches devices, schedules cache-purge) |
| `POST` | `/api/admin/profiles/{profile_id}/connect` | Owner pastes a member's PAT; server verifies via a `limit=1` test call, stores it Fernet-encrypted |
| `POST` | `/api/admin/profiles/{profile_id}/rotate` | Replace a profile's PAT |
| `POST` | `/api/admin/profiles/{profile_id}/sync` | Trigger an async "Sync now" (202 Accepted) |
| `POST` | `/api/admin/profiles/{profile_id}/invite` | Mint a single-use, 1-hour member self-connect invite link (v2.1) |
| `POST` | `/api/admin/devices/bind` | Redeem a kiosk's 4-digit pairing code, bind it to a profile, assign a label |
| `GET` | `/api/admin/devices` | List devices grouped by pending / paired / revoked, including the current active `profile_name` (null when unbound) |
| `PATCH` | `/api/admin/devices/{device_id}` | Rename / reassign a device's profile |
| `POST` | `/api/admin/devices/{device_id}/revoke` | Revoke a device (kiosk snaps back to the pairing screen live via SSE) |
| `POST` | `/api/admin/devices/{device_id}/reinstate` | Un-revoke a device |
| `DELETE` | `/api/admin/devices/{device_id}` | Delete a device row |

Malformed YAML/CSV uploads return 422 `parse_error` with field or line context.
Unknown cube addresses return 422 before filling or writing boundaries; valid
imports into a new profile can bootstrap its configured shelving units. Preview
entries identify changed cubes and carry `before`/`after` cut points; the UI shows
those transitions rather than inferring record movement from the legacy delta.

Boundary imports replace the profile's full address space: omitted cubes become
empty. Width overrides for emptied cubes are deleted in the same transaction.
Overrides on nonempty cubes are preserved when omitted from the file, including
CSV imports, which cannot carry overrides. Reimporting an emptied cube without
an override therefore uses the current collection's derived fractions.

Device assignment requires an active profile: unknown or soft-deleted profiles
return 404 `profile_not_found`; an occupied active profile returns 409
`profile_already_bound`. A failed assignment rolls back the entire request,
including any rename or pairing-code consumption.

Authenticated pairing-code redemption distinguishes an unconsumed expired code
(404 `code_expired`) so the admin can ask the kiosk to generate a new code.
Unknown and consumed codes return 404 `code_not_found`. This implements the
pairing UI contract; invite redemption retains its separate uniform-404 policy.


---

## 3. Position Estimation

Record location is **computed**, not stored per record. The deterministic shelf ordering
(alphabetical by label, then catalog number within label) means the boundary table alone
is enough to locate any record. As of v2.0, every cache feeding the estimator
(`BoundaryCache`, `CollectionSnapshot`, `SegmentCache`, settings) is **per-profile**,
held in `app.state.*_registry` dicts keyed by `str(profile_id)` and eager-loaded at
startup for every non-deleted profile.

### Two-level segment-aware interpolation (Phase 5)

```mermaid
flowchart TD
    Q["GET /api/locate?release_id&profile_id"] --> RES[resolve_profile_from_request]
    RES --> SN{"SegmentCache + CollectionSnapshot\navailable for this profile?"}
    SN -- No --> FALLBACK["Cube-only fallback\nestimator_version=cube-only-v1\nsub_cube_interval=null"]
    SN -- Yes --> LABEL[Find record's label in the profile's SegmentCache]
    LABEL --> BIN[Select bin + segment for label]
    BIN --> FRAC["Compute fractional offset:\npreceding label widths / bin width"]
    FRAC --> RANK["Interpolate by row-rank\nwithin the segment"]
    RANK --> RESULT["LocateResult\nestimator_version=segment-v1"]
    FALLBACK --> RESULT
```

The kiosk draws the returned position band only inside the primary cube. The label-span
underlay links neighboring cubes; crossing metadata does not encode a second position
interval, so no companion band is synthesized from its clamped endpoint.

**Estimation steps:**

1. Resolve the authoritative `profile_id` (cookie/device binding) and look up the
   record's `(label, catalog_number)` in that profile's `CollectionSnapshot` (loaded at
   startup / refreshed after each sync from `gruvax.profile_collection`).
2. That profile's `SegmentCache` (derived from `BoundaryCache` + `CollectionSnapshot` +
   `segment_overrides`) maps each label to a bin and a contiguous segment within that bin.
3. The fractional position is computed from the label's rank within the segment,
   weighted by optional `segment_overrides` physical widths.
4. Interpolation within the label uses the record's rank among same-label records by
   catalog sort key (Strategy C token-stream parser — zero external dependency, fully
   deterministic; `gruvax.estimator.normalize.parse_key`).

**Spacing:** bins shared by multiple labels use record midpoints within each applied
label width: `offset + ((rank_in_segment + 0.5) / segment_count) * applied_fraction`.
This separates adjacent labels' edge records. Single-segment bins retain the legacy
endpoint formula `rank_in_segment / (segment_count - 1)` (or a local midpoint for
a one-record segment belonging to a larger label). Crossing metadata is set only
when the actual record band reaches the edge of a continuing bin.

**Singleton:** a known label containing exactly one record receives a faint full-cube
position band `[0, 1]` at confidence 0.30 (`segment-v1`), as required by D-02. A lone
record within one segment of a larger label uses that segment's midpoint instead.

**Fallback:** if the profile's `CollectionSnapshot` is empty or the label has no segment
data, the estimator falls back to the cube-only result: `primary_cube` is set,
`sub_cube_interval` is `null`, confidence is 0.30, `estimator_version="cube-only-v1"`.

`locate_by_index` ("§4.1", pre-segment single-level interpolation) is **retired from the
public API** as of Phase 5 — it is kept in-tree only as a private regression fixture
(`_locate_by_index_v1`) proving the segment-aware path reproduces it exactly for a
single-segment bin. `estimator_version="index-v1"` is a **historical tag** and should not
appear in production responses.

### LocateResult contract

```python
LocateResult(
    release_id,
    primary_cube,       # {unit_id, row, col} | null
    label_span,         # list of {unit_id, row, col} — cubes the label occupies
    sub_cube_interval,  # {start, end, crosses_boundary, next_cube} | null
    confidence,         # float 0.0–1.0
    generated_at,       # UTC timestamp
    estimator_version,  # "segment-v1" (normal path) | "cube-only-v1" (fallback)
)
```

`GET /api/locate` returns `404 release_not_in_collection` if the release isn't in the
resolved profile's `profile_collection` cache, and `200` with `confidence=0.0` /
`primary_cube=null` / `label_span=[]` when the release *is* in the collection but no
boundary covers its label yet.

---

## 4. LED Contract

The LED illumination path is a publish-only MQTT fan-out from the GRUVAX API. The
hardware side (ESP32 firmware + WS2812B strips) is a **later, independent hardware
milestone (Future)** — the software contract described here is fully built and tested
against a broker, but nothing is physically wired to it yet.

### Topic structure

All topics are prefixed with `settings.MQTT_TOPIC_PREFIX`. The application, Compose,
and environment template default to `gruvax/v1/dev/leds`. Production operators must
explicitly set a distinct value, e.g. `gruvax/v1/leds`, and configure firmware with
that same prefix to separate retained state. `GRUVAX_ENV` does not switch the prefix;
custom `.env` values pass through unchanged (`gruvax.mqtt.topics`):

```
{prefix}/illuminate/{unit_id}/{row}/{col}   — QoS 0, non-retained: light a single cube
{prefix}/span/{change_id}                   — QoS 0, non-retained: light the label span (fresh UUID per publish)
{prefix}/sub/{unit_id}/{row}/{col}          — QoS 0, non-retained: sub-cube position bar
{prefix}/state/{unit_id}/{row}/{col}        — QoS 1, RETAINED: current LED state for this cube (firmware boot read)
{prefix}/all/off                            — QoS 1, non-retained: clear all LEDs
{prefix}/status/#                           — subscribe-only wildcard for firmware status/heartbeat responses
```

All payloads are Pydantic-validated JSON. The broker is `eclipse-mosquitto` on an
internal Compose network only (port 1883 is not exposed to the LAN).

### MQTT protocol settings

- MQTT 5 with `message_expiry_interval` (`MQTT_STATE_EXPIRY_SECONDS`, default 4h) on
  retained `state/*` messages, so a broker restart never serves a permanently stale
  cube state.
- Command topics (`illuminate`, `span`, `sub`, `all/off`) are **never retained** —
  retaining a command is a stale-command-replay footgun.
- `all/off` clears retained `state/*` topics by publishing an empty payload with
  `retain=True` (MQTT protocol: `retain=True` + empty payload = delete retained message).

Off has no RGB control: it deletes retained state and uses zero brightness in
the diagnostic sweep. Live settings and the admin UI expose only operative
colors; `PUT /api/admin/settings` rejects the retired `led_color_all_off` field.
Historical `led_color.all_off` database rows remain intact. Settings backups
continue exporting/importing that legacy value with normal hex validation for
export→reimport compatibility; it has no effect on LED output.

`POST /api/admin/leds/diagnostic` immediately returns a run ID and schedules a
server-driven sweep: each cube receives label-span → position → error → setup
frames on its retained QoS 1 `state/*` topic, followed by an empty retained off
frame. Configured inter-cube delay separates cubes. After the sweep, a guarded
five-second `status/#` subscription logs firmware replies, then the server
restores the idle ambient state on every cube. Firmware consumes these ordinary
state updates; no `{prefix}/diagnostic` command or separate payload schema exists.

Retained `state/*` uses the existing payload names: `gruvax.illuminate.v1`
for primary and ambient state, and `gruvax.span.v1` for non-primary span cubes.
`mqtt.schemas.StatePayload` documents this union. The primary retained value
wins when the cube also belongs to its label span; each cube is written once.
The span command still includes the full label span.

The API supervises a fresh MQTT client on each connection attempt. Disconnects
and publish failures immediately make MQTT health degraded; retries remain
noncritical to API startup, and shutdown awaits the client context cleanup.
The supervisor alone consumes the public incoming-message stream. A diagnostic
opens a bounded status capture before subscribing, sized for the cube census
times its five state replies plus equal duplicate/delay headroom (minimum 64).
Concurrent captures
are rejected, and completion, cancellation or disconnect disposes the queue.
`POST /api/illuminate` returns `accepted` and its legacy alias `published` as
queue acceptance by a currently healthy connection, not firmware delivery.
A known unavailable connection returns both fields as false.

### HighlightRegistry

An in-process `HighlightRegistry` (app-scoped) tracks active highlight tasks. Each
illuminate request uses `led_highlight.retain_mode` to choose its lifecycle:

- Default mode (`false`) cancels prior highlights and restores their affected cubes
  to ambient before publishing the new highlight. Its revert timer reads
  `led_highlight.active_ttl_seconds` (default 180 seconds).
- Retain mode (`true`) keeps prior highlights and gives each new highlight an
  independent revert timer using `led_highlight.retain_ttl_seconds` (default
  900 seconds).

On expiry, `publish_ambient` restores the configured ambient color and brightness
on only that highlight's affected cubes via retained `state/*` messages. It does
not publish `all/off` or clear every cube. These LED TTLs are separate from the
admin session's `session.idle_ttl_seconds`. The implementation is
[`mqtt/lifecycle.py`](../src/gruvax/mqtt/lifecycle.py).

---

## 5. Realtime

The kiosk subscribes to the SSE stream once on page load, scoped to the profile it is
bound to. It does not poll (except the pre-pairing `/api/devices/me` state check, which
polls every 3s until paired).

### SSE endpoint

`GET /api/events/{profile_id}` — long-lived HTTP/1.1 streaming response via
`sse-starlette`. The dependency (`get_bus_for_profile`) validates device/session binding
and the profile's revoke state **before** streaming begins; the generator body itself
touches only an in-memory `asyncio.Queue`, never the DB pool (kept pool-free by design so
a long-lived SSE connection can never hold a pool slot).

### Event types

| Event | Payload | Kiosk action |
|-------|---------|--------------|
| `server_hello` | `{version, profile_id}` | Confirms connection; resets backoff |
| `boundary_changed` | `{cube_ids: [{unit, row, col}], change_set_id}` | Refetch boundaries, re-render grid |
| `admin_editing` | `{cube_ids: [{unit, row, col}], editing}` | Set or clear the editing shimmer for the listed cubes |
| `collection_changed` | `{profile_id, new_record_count, is_initial_import}` | Refetch collection-derived state after a sync completes |
| `device_revoked` | `{device_id}` | Kiosk drops back to the pairing screen immediately |
| `device_reassigned` | `{device_id}` | Kiosk reloads into its newly assigned profile |
| `server_shutdown` | `{}` | Begin exponential backoff reconnect cycle |

Cube addresses in these events use the integer field `unit`, not `unit_id`.
`change_set_id` is a UUID string for history-producing writes, but is `null`
when deleting a segment override. `editing` and `is_initial_import` are booleans;
`new_record_count` is the number of newly added releases, not the total collection
size. Device events carry only the device UUID: reassignment is published on the
old profile's channel, without an `old_profile_id` payload field.

`server_hello` is generated directly for each new SSE connection, after binding
validation. Its `version` comes from `version.GIT_SHA` (the same build source as
`GET /api/version`), and `profile_id` is the canonical UUID string. It is not a
startup event replayed from the profile bus.

Producer sources: [`api/events.py`](../src/gruvax/api/events.py) (hello),
[`api/admin/cubes.py`](../src/gruvax/api/admin/cubes.py),
[`segments.py`](../src/gruvax/api/admin/segments.py),
[`import_.py`](../src/gruvax/api/admin/import_.py), and
[`history.py`](../src/gruvax/api/admin/history.py) (boundary changes),
[`editing.py`](../src/gruvax/api/admin/editing.py) (editing),
[`sync/profile_sync.py`](../src/gruvax/sync/profile_sync.py) (collection changes),
[`devices.py`](../src/gruvax/api/admin/devices.py) (revoke/reassignment), and
[`app.py`](../src/gruvax/app.py) (shutdown).

The `EventBus` is now **one instance per profile**, held in
`app.state.event_bus_registry[str(profile_id)]`. Admin writes call
`get_bus_for_profile(...).publish(...)` without awaiting subscriber drain; each
connected SSE client owns its own `asyncio.Queue` subscriber, unsubscribed on disconnect.
A P1-compatible `app.state.event_bus` alias still points at the default profile's bus for
a handful of admin routes pending full per-profile migration (documented tech debt,
non-blocking).

```mermaid
flowchart LR
    ADM["Admin PUT boundary\n(profile-scoped)"] --> BUS["EventBus.publish\nboundary_changed"]
    SYNC["Nightly / manual sync\n(sync_profile)"] --> BUS2["EventBus.publish\ncollection_changed"]
    DEV["Admin revoke/reassign device"] --> BUS3["EventBus.publish\ndevice_revoked / device_reassigned"]
    BUS --> SSE["GET /api/events/{profile_id}\nsse-starlette"]
    BUS2 --> SSE
    BUS3 --> SSE
    SSE --> KIOSK["Kiosk React SPA\nrefetch + re-render"]
```

---

## 6. Observability

### `/api/health` subsystems

`GET /api/health` returns a structured JSON body with per-subsystem status, reflecting
state captured at lifespan startup and refreshed by a 60-second background task (never a
live DB probe on every call):

| Field | Source | Healthy value |
|-------|--------|---------------|
| `db` | psycopg pool liveness flag set at startup | `"ok"` |
| `discogsography_api_check` | Derived from the **default profile's** `last_sync_status` / `last_sync_at` / `app_token_revoked` (precedence: `failed` > `stale` > `ok`; replaces v1's `v_collection` probe, which no longer exists) | `"ok"` |
| `mqtt` | aiomqtt connection state | `"ok"` (`"degraded"` when MQTT is offline; other subsystems unaffected) |
| `sync_age_seconds` | 60s background refresh, from `profiles.last_sync_at` for the default profile | Recent float; `null` if never synced |
| `version` | Git SHA baked at Docker build time | string |
| `started_at` | ISO-8601 UTC app-startup timestamp | string |

`status` is `"ok"` only when `db` is up **and** `discogsography_api_check` is `"ok"`; a
degraded MQTT broker does **not** flip overall status (MQTT is non-critical). The
response is always HTTP 200 — callers inspect individual fields.

### In-memory ring buffers (reset on restart)

```mermaid
flowchart TD
    subgraph Logging["Logging flow"]
        A[structlog.get_logger call] --> B[structlog processor chain]
        C[stdlib logging.getLogger call] --> D[Foreign record]
        B --> E[ProcessorFormatter.wrap_for_formatter]
        D --> E
        E --> F["ProcessorFormatter\nforeign_pre_chain + processors"]
        F --> G["JSONRenderer + orjson\nstdout JSON line"]
        E --> H["LogRingHandler.emit\nscoped to gruvax logger"]
        H --> I["deque maxlen=200\napp.state.log_ring_buffer"]
        I --> J["GET /api/admin/diagnostics\nrecent_logs field"]
    end
```

| Ring | Size | Content |
|------|------|---------|
| `app.state.log_ring_buffer` | 200 entries | JSON log records from the `gruvax` logger (structlog + stdlib bridge) |
| `app.state.slow_query_ring` | 50 entries | Requests that exceeded the p95 SLO threshold |

Both rings are in-process memory and reset on container restart. They are not persisted.

### `/api/admin/diagnostics`

Returns:
- `sync_age_seconds`, `mqtt`, `pool` — as above
- `top_searched` — `record_stats` top-searched releases for the requesting profile (durable, survives restart)
- `phantom_boundary_count` — boundary rows referencing labels not found in `profile_collection`
- `recent_logs` — last 20 entries from the log ring, newest first
- `slow_queries` — entries from the slow-query ring, newest first
- `profiles` — per-profile diagnostics array (v2.0/D4-15): `id`, `display_name`, `last_sync_at`, `last_sync_status`, `last_sync_item_count`, `last_sync_error`, `app_token_revoked`, `last_new_record_count`, `last_sync_is_initial` for every non-deleted profile

Never exposed: connection strings, env vars, PIN, PAT plaintext, or raw search query text.

---

## 7. discogsography Integration

**(v2.0 onward — this section has no v1.0 equivalent.)**

GRUVAX integrates with discogsography via its HTTP API only — `DiscogsographyClient`
(`src/gruvax/discogsography/client.py`), an async `httpx`-based, construct-per-sync
client wrapping `GET /api/user/collection` (paged, `Authorization: Bearer <PAT>`).

- **Auth:** each profile owner mints a scoped Personal Access Token in discogsography and
  hands it to the GRUVAX owner (`connect`), or — as of v2.1 — redeems a single-use invite
  link and pastes their own PAT directly (self-connect; the owner never sees the token).
  The PAT is Fernet-encrypted at rest (`GRUVAX_SECRET_KEY`) and never logged
  (`gruvax.discogsography.log_redactor` defends against accidental interpolation).
- **Label/catalog authority:** discogsography returns `label` and `catalog_number`
  from the same persisted first-label source pair. Either member can be null;
  legacy releases without known source provenance return null for both until
  upstream source-bearing reingest backfills them. GRUVAX preserves that pair and
  NFKC-normalizes only the catalog number (ADR-0001); it never selects another
  label from graph relationships or fills a missing member from an old pair.
- **Retry policy:** `401`/`403` → `PATRejected`, no retry. `429` → honor `Retry-After`,
  then exponential backoff (max 3 retries). `5xx` → exponential backoff (max 3 retries).
  Network errors → 1 retry.
- **Sync flow** (`gruvax.sync.profile_sync.sync_profile`): acquire a per-profile Postgres
  advisory lock → mark `last_sync_status='in_progress'` → page the full collection into a
  staging table → atomically swap into `profile_collection` inside one transaction →
  update `profiles.last_sync_at` / `last_sync_status` / `last_sync_item_count` /
  `last_new_record_count` / `last_sync_is_initial` → rebuild that profile's
  `BoundaryCache` + `SegmentCache` + `CollectionSnapshot` → publish `collection_changed`
  on the profile's `EventBus`.
- **Sync triggers:** on profile connect (synchronous `limit=1` test call, then async full
  sync), manual "Sync now" (admin button, 202 Accepted), and a nightly background loop
  (`gruvax.sync.nightly`, DST-safe, configurable cadence: 24h/12h/6h/off, default 03:00
  local in the configured IANA `TZ` (default `America/Los_Angeles`), fire hours
  read from `gruvax.settings`). A startup catch-up sweep syncs any
  stale non-revoked profile in a tracked background task before the nightly loop
  begins; HTTP readiness does not wait for upstream catch-up. A local startup
  purge sweep removes
  `profile_collection` rows for soft-deleted profiles never cleaned up at delete-time.
- **Dev/CI:** `fake-discogsography` (`src/gruvax/_internal/fake_discogsography.py`) is a
  sibling FastAPI service implementing the same contract against seeded synthetic data,
  used by `compose.yaml` and CI so no real discogsography instance is required for local
  dev or tests.

---

## 8. Auth & Session Model

Four independent cookie-based mechanisms coexist; none of them share state:

| Cookie | Set by | Scope | Notes |
|--------|--------|-------|-------|
| `gruvax_session` | `POST /api/admin/login` | Admin PIN session | `HttpOnly`, `SameSite=Strict`; itsdangerous-signed session UUID; global default-profile `session.idle_ttl_seconds` refreshed per authenticated request (`SESSION_TTL_SECONDS` fallback, default 600s), clamped to the immutable cap minted at login from `session.hard_cap_seconds` (fallback 1800s) |
| `gruvax_csrf` | `POST /api/admin/login` | Admin PIN session | NOT `HttpOnly` (SPA reads it); double-submit — echoed as `X-CSRF-Token` on every mutating admin request; `require_admin` rejects mismatches with 403 |
| `gruvax_browse_binding` | `POST /api/session/bind` (or auto-bind on `GET /api/session` when exactly one profile exists) | Read-only browsing | NOT `HttpOnly` (SPA derives the per-profile SSE URL from it); `SameSite=Strict`; max-age 7 days; plain UUID, validated against the active-profiles set server-side on every request — no PIN required to browse/search on the trusted home LAN |
| `gruvax_device_fp` | `POST /api/devices/pairing-codes` (first call) | Kiosk device identity | `HttpOnly` (JS never reads it — session-equivalent secret); max-age 30 days so it survives reboots; identifies a `devices` row independent of the browse-binding cookie |

The admin PIN itself is hashed with Argon2id (`passlib`) and stored under the
`auth.pin_hash` key in `gruvax.settings` (per-profile) — **never** in an environment
variable. `POST /api/admin/login` rate-limits to 5 attempts / 5 minutes / IP (429 on
breach) and never logs the raw PIN (`pin_attempt=redacted`).

`resolve_profile_from_request` is the single choke point every profile-scoped endpoint
depends on: it derives the authoritative `profile_id` from the device fingerprint (kiosk)
or browse-binding cookie (browser), enforcing that cross-profile data leakage is
impossible by construction — no endpoint trusts a client-supplied `profile_id` without
validating it against the resolved binding.

---

## 9. Deploy

### Compose services

```mermaid
flowchart LR
    subgraph Deploy["Compose deploy model"]
        PROD["compose.yaml\nimage: ghcr.io/simplicityguy/gruvax:latest"] -->|docker compose pull && up| HOST[deployment host]
        DEV["just up / just build\n(--build flag)"] -->|builds from Dockerfile| LOCAL[local dev]
    end
```

| Service | Purpose | Notes |
|---------|---------|-------|
| `api` | GRUVAX FastAPI app + built SPA | Same `image:`/`build:` block serves both prod (pull) and dev (build); healthcheck hits `/api/health` |
| `gruvax-dev-pg` | Postgres 18 | Starts only with the `dev` profile enabled by `just up`; host access binds to loopback. Production configures an external `DATABASE_URL`. |
| `mosquitto` | `eclipse-mosquitto:2.1.2-alpine` | No `ports:` mapping — internal-only in both dev and prod |
| `fake-discogsography` | Synthetic discogsography API stand-in | Serves the synthetic seed only with the `dev` Compose profile. Production uses an explicitly configured external API. |
| `init-sync` | One-shot idempotent bootstrap job | Runs `gruvax-sync --profile default` once, only if `profile_collection` is empty for the default profile; requires `GRUVAX_ADMIN_PIN` |
| `mqtt-explorer` | MQTT broker inspector web UI | Gated behind `docker compose --profile debug up mqtt-explorer` — never starts on a plain `up` |

The API container:
- Runs as non-root user `gruvax` (created in the Dockerfile at build time).
- Multi-stage build: `node:26-slim` builds the Vite/React SPA → `python:3.14-slim` +
  `uv` installs Python deps → lean `python:3.14-slim` runtime copies in the `.venv` and
  built `static/`.
- On startup (`docker-entrypoint.sh`): runs `alembic upgrade head`, then starts Uvicorn.
  The app's own lifespan then opens the psycopg pool, probes
  `gruvax.profile_collection` for the default profile, eager-loads per-profile
  `BoundaryCache` + `CollectionSnapshot` + `SegmentCache` + settings for every
  non-deleted profile, connects to Mosquitto (best-effort — degraded mode if offline),
  runs sync startup sweeps, and schedules the 60s state-refresh and nightly-sync
  background tasks.
- Serves the React SPA as `StaticFiles` from `/static`, mounted only if the directory
  exists (guards local dev before the first `npm run build`).

### GHCR pull-based deploy

Production uses the pre-built image from GitHub Container Registry — no build step on
the deployment host when using the default production profile. The bundled Postgres
and synthetic API require the `dev` profile; `just up` enables it and builds the local
application images for development.
The base Compose file includes `build:` for local source builds without an override file.

```bash
docker compose pull
docker compose up -d
```

The image is built and pushed by the `build.yml` CI orchestration on every push to `main`.

### CI orchestration

```mermaid
flowchart LR
    subgraph CI["GitHub Actions CI orchestration"]
        PR[push / pull_request] --> BLD["build.yml\norchestrator"]
        BLD --> CQ["code-quality.yml\nworkflow_call GATE"]
        CQ -->|pass| TEST["test.yml\nworkflow_call"]
        CQ -->|pass| BUILD["build job\nDocker + GHCR push"]
        CQ -->|pass| SEC["security.yml\nworkflow_call"]
        TEST -->|"Alembic round-trip\nBenchmark SLO"| DONE[aggregate-results]
        BUILD --> DONE
        SEC --> DONE
    end
    subgraph Cleanup["Scheduled cleanup"]
        SCHED[monthly schedule] --> IMGS["cleanup-images.yml\ndataaxiom/ghcr-cleanup-action"]
        PRCLOSE[PR closed] --> CACHE["cleanup-cache.yml\ngh cache delete loop"]
    end
```

`code-quality.yml` is the GATE step: Ruff, mypy `--strict`, and pre-commit checks.
`test.yml` runs the full pytest suite, the Alembic round-trip (`upgrade head → downgrade
base → upgrade head` — migration 0009's downgrade leg re-creates `v_collection`
verbatim, so a legacy synthetic collection is seeded just for that leg), and the p95 SLO
benchmark gate against synthetic data.

### Startup sequence and lifespan

```mermaid
flowchart TD
    START[Container start] --> LOG[Configure structlog + LogRingHandler]
    LOG --> POOL["Open psycopg pool\nmin=2 max=10"]
    POOL --> PROBE["Probe gruvax.profile_collection\nfor the default profile"]
    PROBE -->|fail| DEGRADED["profile_collection_ready=False\nsearch/locate → 503"]
    PROBE -->|ok| REGISTRIES["Eager-load per-profile registries:\nBoundaryCache, CollectionSnapshot,\nSegmentCache, settings, EventBus\n(for every non-deleted profile)"]
    REGISTRIES --> ALIAS["Wire P1-compat singular\napp.state.* aliases → default profile"]
    ALIAS --> MQTT[Connect MQTT best-effort]
    MQTT --> HIGHLIGHT[Init HighlightRegistry]
    HIGHLIGHT --> STATE["Schedule 60s all-profiles\nstate-refresh task"]
    STATE --> SWEEPS["Nightly-sync startup sweeps:\nlocal purge, then background catch-up"]
    SWEEPS --> SYNCLOOP[Schedule nightly-sync loop task]
    SYNCLOOP --> AMBIENT[Publish ambient LED baseline]
    AMBIENT --> SERVE[Yield — serving requests]
    SERVE --> SHUTDOWN["server_shutdown event\n(broadcast to every profile's EventBus)"]
    SHUTDOWN --> REVERT[cancel_and_revert_all LED tasks]
    REVERT --> DISC[Disconnect MQTT + close pool]
```

### Environment variables

Runtime configuration is validated at startup via `pydantic-settings`
(`src/gruvax/settings.py`) — a missing or malformed required value crashes boot rather
than surfacing later at request time. Full list in `.env.example`.

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | yes | SQLAlchemy/psycopg async DSN, e.g. `postgresql+psycopg://user:pass@host/db`. Env-first in compose: a `DATABASE_URL` set in `.env` wins outright; only when it is absent does compose assemble one from `GRUVAX_DB_HOST`/`_USER`/`_PASSWORD`/`_NAME`/`_PORT` (compose-only pieces, not read directly by the app) (gruvax-95qp) |
| `DISCOGSOGRAPHY_BASE_URL` | yes | Base URL of the discogsography HTTP API (prod: real service; dev: `fake-discogsography`) |
| `GRUVAX_SECRET_KEY` | yes | 32-byte URL-safe base64 Fernet key for PAT-at-rest encryption; boot fails on a malformed key |
| `SESSION_SECRET` | yes | Signing key for the admin session cookie |
| `SESSION_TTL_SECONDS` | no (default 600) | Sliding idle TTL for admin sessions |
| `MQTT_HOST` / `MQTT_PORT` | no (default `localhost` / `1883`) | Mosquitto broker address |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | no | Broker credentials |
| `MQTT_TOPIC_PREFIX` | no (default `gruvax/v1/dev/leds`) | Retained LED namespace; production explicitly sets a distinct prefix matching firmware; no automatic environment switch |
| `MQTT_STATE_EXPIRY_SECONDS` | no (default 14400 / 4h) | `message_expiry_interval` on retained `state/*` topics |
| `LOG_LEVEL` | no (default `INFO`) | `structlog` log level |

Compose-only variables (not read by `Settings`, only used to build the vars above or to
bootstrap containers): `GRUVAX_DB_HOST`/`_PORT`/`_USER`/`_PASSWORD`/`_NAME` (build
`DATABASE_URL`), `GRUVAX_ADMIN_PIN` (required by the `init-sync` one-shot job only),
`GIT_SHA`/`BUILD_TIMESTAMP` (Docker build args baked into `_version.py`).

`GRUVAX_ENV` is **not** build-arg-only (gruvax-b51h corrects the previous misfiling here) —
it is baked into `_version.py` at build time (`compose.yaml`'s `build.args`) **and** read at
container-runtime by `docker-entrypoint.sh`, which gates dev-only bootstrap behind
`GRUVAX_ENV=development`: creating the `gruvax_dev` migration-0002 stub schema, seeding
`gruvax.profile_collection` with the ~3,000-row synthetic dataset, and seeding synthetic cube
boundaries. `.env.example` ships this UNSET by default; setting it to `development` against
a real deployment permanently short-circuits the initial Discogs sync (see
`docs/runbook-fresh-host.md`).

The v1.0 `ADMIN_PIN_HASH` env var and `OBSERVED_DISCOGSOGRAPHY_SCHEMA` env var described
in earlier drafts of this document no longer exist — the PIN hash lives in
`gruvax.settings` (§8) and the schema-selection env var was retired when the pool moved
to a single literal `search_path`.

---

## 10. Future / Not Yet Built

These are documented, decided, or partially scaffolded, but have no corresponding
runtime code yet:

- **Real LED hardware** — ESP32 firmware + WS2812B strips subscribing to the MQTT
  contract in §4. Independent hardware milestone; the software side is complete and
  tested against a broker.
- **LED "party" mode / "sound-reactive" mode** — captured in the backlog
  (`.planning/ROADMAP.md` Phase 999.2); no requirements or code yet.
- **OAuth2 device-authorization grant** for discogsography auth (`REQ-oauth2-device-grant`,
  targeted v2.2) — v2.1 auth is PAT-only (owner-managed connect or member self-connect).
- **Shelf overview mini-Kallax** beyond the v2.1 fill/occupancy widget delivered in Phase
  10 — further visual polish is backlog-only.
- **TLS on the LAN** — GRUVAX assumes an HTTP-only trusted home LAN throughout; a TLS
  posture decision is explicitly deferred (see `.planning/STATE.md` pending todos).

---

## See Also

- [`.planning/PROJECT.md`](../.planning/PROJECT.md) — Core Value, requirements, key decisions
- [`.planning/ROADMAP.md`](../.planning/ROADMAP.md) — milestone and phase history (v1.0 → v2.1)
- [`docs/runbook-fresh-host.md`](runbook-fresh-host.md) — First-time deployment on a new host
- [`design/gruvax-design-language.md`](../design/gruvax-design-language.md) — Nordic Grid design spec
- [`migrations/`](../migrations/versions/) — Alembic migration history (schema source of truth)

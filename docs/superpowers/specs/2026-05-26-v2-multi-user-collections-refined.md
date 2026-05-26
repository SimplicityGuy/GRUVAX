# GRUVAX v2.0 — Multi-User Collections via discogsography API (Refined)

**Date:** 2026-05-26
**Status:** Approved (design) — ready to route into `/gsd-new-milestone v2.0 --reset-phase-numbers`
**Supersedes:** [`2026-05-25-v2-multi-user-collections-design.md`](./2026-05-25-v2-multi-user-collections-design.md) (the original approved design — kept for historical context; this refinement is the authoritative v2.0 design as of this date)
**Author:** brainstorming session (Robert + Claude)

---

## What changed since 2026-05-25

This refinement preserves all 7 locked decisions (D1–D7) from the 2026-05-25 draft and adds explicit choices for the 6 open questions plus several new structural decisions surfaced during refinement:

| # | Topic | 2026-05-25 status | 2026-05-26 decision |
|---|-------|------------------|--------------------|
| 1 | Catalog# exposure on discogsography API | HIGH-risk unknown | Verification spike is the FIRST step of discogsography v2 P1; three documented outcome branches drive subsequent scope |
| 2 | Cross-repo coordination | Two repos, two cadences | **Sequential** — discogsography v2 ships first, then GRUVAX v2.0 starts |
| 3 | discogsography reqs in GRUVAX milestone? | Implicit "phase 1" | **External prereq** — tracked in `.planning/intel/context.md`; GRUVAX v2.0 = 13 reqs only |
| 4 | Token handoff UX | Owner-managed (default) vs self-connect (privacy variant) | **Owner-managed PAT only**. Self-connect → v2.1, OAuth2 device-grant → v2.2 |
| 5 | RPi kiosk pairing | "pairing code?" left open | **4-digit code on kiosk**, owner types in mobile admin (reuses v1 numeric keypad). QR deferred to v2.1 |
| 6 | Sync cadence | Configurable, no default | **Manual + nightly background at 03:00 local**, configurable (24h / 12h / 6h / off) |
| 7 | Browser session binding | Not addressed | **Sessions and devices are independent**: profile picker for any LAN browser, devices table only for registered RPi kiosks |
| 8 | Phase 9 housekeeping (v1.x scope) | TODO in draft | **Already shipped** (memory was stale) — drop the 8 housekeeping reqs from v2.0 |
| 9 | 9 SPIDR-deferred v1 reqs (SRCH-09, OFF-01..04, PRIV-01..04) | "Surface this question" | **Stay deferred** — v2.1 resilience+privacy milestone |
| 10 | Phase numbering | Continue from v1.0? | **Reset to P1–P4 for v2.0** (`--reset-phase-numbers`) |

A separate per-repo brief (`background/discogsography-v2-app-tokens-brief.md`, gitignored) was authored for the discogsography agent session. That work is in flight as of this writing.

---

## Context & Problem

GRUVAX v1.0 (Phases 1–10, complete 2026-05-26) reads discogsography's Postgres **directly** via a read-only `gruvax.v_collection` view + grant. That model assumes a **single implicit collection** and tightly couples GRUVAX to discogsography's database (Pitfall 5: the view is the *only* contact surface).

discogsography is a genuinely **multi-user** system (users keyed by UUID; per-user `user_collections`). A household may have multiple members, each with their **own** Discogs collection on their **own** physical Kallax shelves. v2.0 re-architects GRUVAX to:

1. Integrate with discogsography's **HTTP API** (not its DB) to fetch a *specific authorized user's* collection.
2. Require each user to **authorize** GRUVAX's access to their collection.
3. Support **multiple collections per GRUVAX deployment**, while a single RPi kiosk serves a single user's collection.

This is a milestone, not a phase. v_collection is retired. The data-source surface is rebuilt.

---

## Locked Decisions (unchanged from 2026-05-25)

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Topology:** one central GRUVAX server holds all profiles; thin RPi kiosks bind to a profile. A profile may have **≥1 RPi**. | Matches "single deployment handles multiple users; single RPi = single user's collection". |
| D2 | **discogsography auth: scoped Personal Access Tokens (PAT), device-grant-ready.** A logged-in discogsography user mints a revocable `collection:read` token for GRUVAX. | Smallest discogsography-side build; genuinely multi-app; revocable. Layered design so OAuth2 device-grant can land later. |
| D3 | **GRUVAX identity: single-PIN owner manages "collection profiles."** Each profile = a fully isolated GRUVAX context. | Keeps GRUVAX's existing single-PIN admin; no new account system. *Authorization* is the member minting their PAT in discogsography. |
| D4 | **Shelving is per-profile.** Units, cube boundaries, segment cuts + physical-width overrides, settings, LED config, and usage stats all gain a `profile_id` scope. | Each member's records sit on their own physical shelves. Reuses v1's wizards & editors. |
| D5 | **Shelving layout belongs to the profile** (shared across that profile's RPis); each RPi binds to a profile. | A user's collection may be shown on >1 kiosk; the physical layout is the user's, not the device's. |
| D6 | **Collection access: pull-and-cache.** GRUVAX pages the collection from discogsography into its **own** per-profile tables; positioning runs off the local cache. | Forced by 200ms SLO + Phase 4 offline resilience. Live remote queries not viable. |
| D7 | **Retire `gruvax.v_collection` + the read-only DB grant.** The API becomes the **only** integration point. | Decouples GRUVAX from discogsography's DB; GRUVAX can run anywhere with network access. |

## Refinement Decisions (new, 2026-05-26)

| # | Decision | Rationale |
|---|----------|-----------|
| R1 | **Sequential cross-repo coordination.** discogsography v2 (app_tokens + catalog# verification/exposure) ships completely before GRUVAX v2.0 P1 starts. | Solo dev, no idle problem worth avoiding. Sequential = no stubs, no contract drift, no rework. |
| R2 | **discogsography work is an EXTERNAL prereq, not part of GRUVAX v2.0.** Tracked in `.planning/intel/context.md`. GRUVAX v2.0 milestone lists only the 13 GRUVAX-side reqs. | Cross-repo work doesn't fit cleanly inside one GSD milestone's phase numbering. External prereq + sequential = the cleanest framing. |
| R3 | **Owner-managed PAT only for v2.0.** Member mints PAT in discogsography → hands to owner → owner pastes into admin. | Adequate for household scope. Self-connect adds invite-token model + connect endpoint + mobile UI. Defer to v2.1. |
| R4 | **RPi pairing flow A — 4-digit code on kiosk.** Owner types code in mobile admin bind UI. Reuses v1 in-app numeric keypad. QR/scan deferred to v2.1. | Simplest, no camera permission, no QR library, no offline-debug headache. 5-min TTL × 10k keyspace + PIN-gated admin endpoint = sufficient. |
| R5 | **Sync triggers:** on profile connect, manual "Sync now", periodic background — 24h cadence at 03:00 local default, configurable (24h / 12h / 6h / off). | Vinyl change frequency ≪ daily. 24h baseline matches reality; hourly would be wasteful. |
| R6 | **Sessions and devices are independent.** Browser sessions on LAN pick a profile via picker; registered RPi kiosks bind via pairing flow. A profile may have 0+ devices AND 0+ sessions simultaneously. | Two binding models because two access patterns: persistent (RPi, survives reboot, dedicated screen) vs ephemeral (any phone/laptop on LAN, session-cookie scoped). |
| R7 | **Open profile picker on LAN — no PIN for read-only browsing.** Browser hits gruvax.lan/ → profile picker → click → session-cookie binds, search UI loads. PIN still gates admin actions. | LAN-trusted home network. Friction on browse-only viewing is unnecessary; admin actions remain gated. |
| R8 | **9 SPIDR-deferred v1 reqs stay deferred to v2.1.** v2.0 focuses on multi-user core. | Resilience (OFF-*) and privacy (PRIV-*) are orthogonal to the multi-user architecture. Scope discipline. |
| R9 | **Walking-skeleton-first phase ordering.** P1 = single-profile API client + cache (v_collection retired). P2 = multi-profile migration + profile manager. P3 = devices + pairing. P4 = polish. | Vertical MVP slicing matches v1.0's pattern. Each phase ships user-observable capability. |
| R10 | **Reset phase numbering to P1–P4** (use `--reset-phase-numbers` on `/gsd-new-milestone`). | Each milestone gets its own phase namespace. v1.0 phases archived; v2.0 starts clean. |

---

## Topology

```
┌────────────────────────────────────────────────────────────┐
│  GRUVAX server (Docker Compose on deployment host)         │
│  - FastAPI: profiles, devices, /api/locate, /api/sync     │
│  - Postgres schema `gruvax`: profiles, devices,            │
│    profile_collection, boundaries + segments + LED         │
│    config (all profile-scoped)                             │
│  - Mosquitto MQTT (LED contract from v1.0 Phase 6)         │
│  - NO direct reads of discogsography's DB                  │
└────────────────────────────────────────────────────────────┘
                            ↑
              bearer PAT (per profile, encrypted Fernet)
                            ↓
┌────────────────────────────────────────────────────────────┐
│  discogsography HTTP API (separate repo, separate Postgres)│
│  app_tokens-authenticated /api/user/collection paged reads │
└────────────────────────────────────────────────────────────┘
                            ↑
                    LAN (kiosk-host link)
                            ↓
   ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
   │  RPi kiosk A    │   │  RPi kiosk B    │   │  Mobile admin   │
   │  bound:         │   │  bound:         │   │  + browser      │
   │  profile "Rob"  │   │  profile "Sam"  │   │  sessions on    │
   │  (devices row)  │   │  (devices row)  │   │  LAN (picker)   │
   └─────────────────┘   └─────────────────┘   └─────────────────┘
```

---

## Data Model

### `profiles`

```sql
CREATE TABLE profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name            TEXT NOT NULL,
    discogs_username        TEXT,                            -- cosmetic; populated post-sync
    discogsography_user_id  UUID,                            -- bound at first successful sync
    app_token_encrypted     BYTEA NOT NULL,                  -- Fernet(GRUVAX_SECRET_KEY)
    app_token_revoked       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_sync_at            TIMESTAMPTZ,
    last_sync_status        TEXT,                            -- 'ok' | 'failed' | 'in_progress'
    last_sync_error         TEXT,
    last_sync_item_count    INT,
    deleted_at              TIMESTAMPTZ                      -- soft delete
);

CREATE UNIQUE INDEX idx_profiles_display_name_active
    ON profiles (LOWER(display_name)) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX idx_profiles_discogsography_user_id_active
    ON profiles (discogsography_user_id) WHERE deleted_at IS NULL;
```

### `profile_collection`

```sql
CREATE TABLE profile_collection (
    profile_id      UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    release_id      BIGINT NOT NULL,
    instance_id     BIGINT NOT NULL,
    artist          TEXT NOT NULL,
    title           TEXT NOT NULL,
    label           TEXT,
    catalog_number  TEXT,
    year            INT,
    fts_vector      TSVECTOR,            -- generated; weighted A=catalog, B=title, C=artist/label
    synced_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (profile_id, instance_id)
);

CREATE INDEX idx_profile_collection_fts            ON profile_collection USING GIN (fts_vector);
CREATE INDEX idx_profile_collection_label          ON profile_collection (profile_id, label, catalog_number);
CREATE INDEX idx_profile_collection_pgtrgm_artist  ON profile_collection USING GIN (artist gin_trgm_ops);
CREATE INDEX idx_profile_collection_pgtrgm_title   ON profile_collection USING GIN (title gin_trgm_ops);
```

### `devices` + `pairing_codes`

```sql
CREATE TABLE devices (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint     TEXT NOT NULL,                  -- server-issued HttpOnly cookie value
    label           TEXT,
    profile_id      UUID REFERENCES profiles(id) ON DELETE SET NULL,
    paired_at       TIMESTAMPTZ,
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_agent      TEXT,
    revoked_at      TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_devices_fingerprint_active
    ON devices (fingerprint) WHERE revoked_at IS NULL;
CREATE INDEX idx_devices_profile_active
    ON devices (profile_id) WHERE revoked_at IS NULL;

CREATE TABLE pairing_codes (
    code            CHAR(4) PRIMARY KEY,
    fingerprint     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,           -- created_at + 5 minutes
    consumed_at     TIMESTAMPTZ
);

CREATE INDEX idx_pairing_codes_expires ON pairing_codes (expires_at);
```

### `profile_id` fan-out (v1 tables that gain a NOT NULL `profile_id` FK in P2)

- `cube_boundaries`
- `segments` (Phase 5)
- `change_log` (Phase 3)
- `change_sets` (Phase 3)
- `settings` (LED colors, brightness, etc.)
- `record_stats` (Phase 8)
- `ambient_baseline` (Phase 6)

v1 data backfills to a deterministic "default" profile row (id `00000000-0000-0000-0000-000000000001`, display_name `'Default'`, renameable in admin).

---

## discogsography-side prereq (EXTERNAL, briefed in `background/discogsography-v2-app-tokens-brief.md`)

Tracked in `.planning/intel/context.md` as the v2.0 milestone gating dependency. Out of scope for GRUVAX v2.0 milestone, but the contract drives everything GRUVAX builds.

**Contract GRUVAX consumes:**

```http
GET /api/user/collection?page=1&per_page=200
Authorization: Bearer <pat>

200 OK
{
  "items": [{
    "release_id": int, "instance_id": int,
    "artist": str, "title": str,
    "label": str | null,
    "catalog_number": str | null,   ← required for GRUVAX positioning
    "year": int | null
  }, ...],
  "page": int, "per_page": int, "total": int,
  "user_id": "uuid"                 ← location TBD by discogsography agent (header or envelope)
}

401 → missing/invalid/revoked token
403 → token missing `collection:read` scope
429 → rate-limited (Retry-After present)
```

discogsography ships:
1. Verification spike (catalog# exposure check — three outcome branches)
2. `app_tokens` table + Alembic migration
3. "Connect an app" settings UI (mint / list / revoke)
4. `require_app_token` FastAPI dependency
5. Auth + rate limits applied to the 3 collection endpoints
6. `docs/specs/v2-gruvax-integration.md` contract artifact

See `background/discogsography-v2-app-tokens-brief.md` for the full briefing.

---

## API Client + Sync

### Client

```python
class DiscogsographyClient:
    def __init__(self, base_url: str, pat: str, *, timeout: float = 30.0): ...
    async def iter_collection(self, *, per_page: int = 200) -> AsyncIterator[dict]: ...
    async def _retry_request(self, ...) -> httpx.Response:
        # 401/403 → raise PATRejected immediately (no retry)
        # 429    → respect Retry-After + exponential backoff (max 3 retries)
        # 5xx    → exponential backoff (max 3 retries)
        # net    → 1 retry then fail with last_sync_status='failed', last_sync_error='network'
```

### Sync flow (per profile)

```
1. Acquire per-profile advisory lock on profile_id (skip if already locked).
2. UPDATE profiles SET last_sync_status='in_progress'.
3. INSERT staging rows from client.iter_collection() into profile_collection_staging temp table.
4. On success:
   BEGIN
     DELETE FROM profile_collection WHERE profile_id = :id
     INSERT INTO profile_collection SELECT ... FROM staging
     UPDATE profiles SET last_sync_at=NOW(), last_sync_status='ok',
                        last_sync_item_count=count,
                        discogsography_user_id = COALESCE(existing, :user_id_from_response)
   COMMIT
5. Drop staging temp table.
6. Release advisory lock.
7. Publish SSE: {"type":"collection_changed","profile_id":"..."} on /api/events/{profile_id}.
8. Rebuild this profile's BoundaryCache + SegmentCache + CollectionSnapshot.
```

### Sync triggers

| Trigger | Source | Behavior |
|---------|--------|----------|
| On profile connect | Profile manager UI saves PAT | Synchronous `per_page=1` test sync → captures `user_id` → kicks off full async sync |
| Manual "Sync now" | Admin button | Async; UI shows progress until complete |
| Nightly background | `asyncio.create_task(_sync_loop())` started in lifespan | 03:00 local default; cadence configurable (24h / 12h / 6h / off); iterates all non-revoked profiles sequentially |

### Staleness redefinition

Per-profile API-sync age replaces v1's `max(v_collection.synced_at)`:

```python
profile.staleness_age = now() - profile.last_sync_at
# Banner: <3d none; 3-14d yellow; ≥14d red  (v1.0 Phase 8 thresholds)
```

---

## RPi Pairing Flow A (4-digit code)

```
KIOSK                                      SERVER                          ADMIN (mobile, PIN session)
1. Open gruvax.lan/
2. Set-Cookie: fingerprint=<opaque>
3. GET /api/devices/me → {state:'unpaired'}
4. POST /api/devices/pairing-codes
                                          Generate '4729', TTL 5min
                                          → {code:'4729', expires_at:...}
5. Render pairing page (Nordic Grid,
   large DM Mono digits, countdown)
   Poll /api/devices/me every 3s
                                                                          6. Admin → Devices → "Enter code"
                                                                          7. Type 4729 (in-app keypad), pick profile,
                                                                             label "Basement kiosk"
                                                                          8. POST /api/admin/devices/bind
                                          Validate PIN, lookup code,
                                          INSERT devices row, mark code
                                          consumed
                                                                          9. "Bound" toast
10. Poll returns {state:'paired',
    profile_id:'...'}
    Navigate to search UI in bound profile
```

**Failure modes:** mistyped code → "Code not found"; TTL expires before bind → kiosk auto-rerolls; concurrent bind → first wins; revoked devices snap back to pairing page on next request.

---

## Profile Manager Admin UI

Extends v1's mobile-first PIN admin with new `Admin → Profiles` section:

- **List** — name, last sync, item count, status badge (connected / pending / re-auth-required)
- **Create** — display_name form; placeholder row until PAT connected
- **Connect PAT** — paste → server verifies via `per_page=1` test call → on 200 stores encrypted blob + locks `discogsography_user_id`
- **Rotate PAT** — paste new, replaces old
- **Rename** — case-insensitive uniqueness check
- **Soft-delete** — confirmation modal lists item count + bound device count; on confirm: detach devices, set `deleted_at`, schedule cache-purge background task
- **Sync now** — PIN-gated button; shows progress; completion toast

New `Admin → Devices` section per §5.5: PENDING / PAIRED / REVOKED groupings, drawer per device (rename / change-profile / unbind / revoke).

---

## Browser Session Profile Picker

```
Browser visits gruvax.lan/
   ├─ 0 profiles configured        → onboarding screen ("log in as owner")
   ├─ 1 active profile             → auto-bind, skip picker (kiosk-friendly)
   └─ 2+ active profiles           → picker (cards: name, last_sync_at, item count)
                                        Click → session cookie sets bound_profile_id
                                        Load search UI in chosen profile

Kiosk corner button: "Switch profile" → unbind session → back to picker
   (Devices ignore this — their binding lives in the devices table, not session cookie)
```

---

## Phase Decomposition

External prereq: **DGS-PREREQ** — discogsography v2 ships first (contract artifact at `docs/specs/v2-gruvax-integration.md` in discogsography repo).

**GRUVAX v2.0 milestone (P1–P4):**

### P1 — Walking skeleton (~4 plans)
- Read DGS contract; new `profile_collection` table + Alembic migration; default-profile row; `gruvax-set-pat` CLI; `DiscogsographyClient` (paged + retry); staging-swap sync routine; **drop `gruvax.v_collection` view + revoke grant**; rewire v1 search + locate paths against `profile_collection` (single profile_id); rewire `CollectionSnapshot`; staleness from `profiles.last_sync_at`.
- **Exit:** search → cube highlight works against API-sourced data; v1 SLOs hold; v_collection gone.

### P2 — Multi-profile (~5 plans)
- Full `profiles` table with Fernet PAT storage; `profile_id` NOT NULL migration across 7 v1 tables (default backfill); composite uniqueness updates; in-memory caches keyed by profile_id (`dict[UUID, …]`); per-profile SSE channel `/api/events/{profile_id}`; profile manager admin UI; browser session profile picker.
- **Exit:** two profiles operate independently; sessions can show different profiles concurrently; per-profile SSE invalidation; p95 SLOs hold with 2+ profiles cached.

### P3 — Devices + pairing (~4 plans)
- `devices` + `pairing_codes` schemas; fingerprint cookie middleware (HttpOnly, SameSite=Strict, persistent); pairing endpoints; kiosk pairing page (Nordic Grid, large DM Mono code, countdown, auto-reroll); devices admin UI (PENDING / PAIRED / REVOKED + drawer); Pi setup script — persist Chromium `--user-data-dir` so fingerprint survives reboot.
- **Exit:** fresh RPi paired to profile in <30s; reboot preserves binding; revoking immediately drops kiosk to pairing screen; re-assigning auto-reloads kiosk via SSE.

### P4 — Polish (~4 plans)
- Background sync scheduler (lifespan `asyncio.create_task`, 03:00 local default, cadence persisted in settings); 401 reauth UI (profile-list badge + kiosk inline banner); per-profile `/admin/diagnostics` cards; profile soft-delete cache-purge background task; "Sync now" progress + completion toast.
- **Exit:** nightly sync fires for all connected profiles; cadence config persists; 401 surfaces immediately; diagnostics accurate per-profile; all v1.0 invariants hold.

**Total:** 17 plans across 4 phases. If v1.0 cadence holds (≈1 phase/day with worktree-parallel execute-phase), v2.0 lands in 4–6 days *after* DGS-PREREQ closes.

---

## Requirements (13 in scope for GRUVAX v2.0)

Active (12):
- REQ-profiles-table
- REQ-profile-manager-admin-ui
- REQ-v1-default-profile-migration
- REQ-api-client-paged-sync
- REQ-sync-triggers
- REQ-positioning-runs-off-local-cache
- REQ-phase8-staleness-redefinition
- REQ-profile-id-migration
- REQ-devices-table
- REQ-rpi-device-binding
- REQ-kiosk-pairing-provisioning
- REQ-retire-v-collection

Deferred (1 — in REQUIREMENTS.md "Deferred" section, NOT planned in P1–P4):
- REQ-oauth2-device-grant (v2.2)

External prereq (5 — tracked in `.planning/intel/context.md`, NOT in GRUVAX REQUIREMENTS.md):
- REQ-app-tokens-table (discogsography)
- REQ-app-token-settings-ui (discogsography)
- REQ-require-app-token-dependency (discogsography)
- REQ-catalog-number-exposure (discogsography, gating)
- REQ-token-rate-limiting (discogsography)

---

## Constraints

### Carried unchanged from v1.0

Python 3.13.x + FastAPI 0.136.x; React 19 + Vite 8; Postgres shared with discogsography (own `gruvax` schema only); Docker Compose; single PIN (Argon2id + sliding session); Nordic Grid design language; in-app numeric keypad; `/api/search` p95 ≤ 200ms; `/api/locate` p95 ≤ 50ms; Alembic upgrade↔downgrade round-trip clean; LAN-only no public exposure; MQTT broker internal-only; structured logs + log ring buffer; repo hygiene (CSV + `background/` gitignored).

### New in v2.0

| Constraint | Rationale |
|------------|-----------|
| GRUVAX never holds a Discogs OAuth credential | Only `app_tokens` minted by discogsography |
| Plaintext PAT never logged (even at DEBUG) | Logging middleware redaction for `Authorization` header |
| `GRUVAX_SECRET_KEY` env var required at boot | Fernet key for PAT encryption; boot fails if missing |
| Profile uniqueness enforced server-side | Partial-unique indexes on `display_name` and `discogsography_user_id` |
| One discogsography user ↔ one profile | A PAT resolving to a `user_id` already represented is rejected at connect |
| Soft-delete preserves change-log lineage | All profile-scoped tables FK; deleted_at doesn't cascade-purge audit |
| Sync is opt-in per profile | Profile-without-PAT skipped by scheduler |
| Sync staleness is per-profile | One stale profile doesn't visually affect another's kiosk |
| Cross-profile data leakage impossible by construction | Every endpoint filters by explicit `profile_id` from session/device binding |

---

## Security review touchpoints (post-implementation)

For explicit verification in `/gsd-secure-phase` after v2.0 ships:

1. PAT-at-rest encryption (Fernet key in env, key rotation procedure)
2. PAT-in-transit redaction (no plaintext in logs/error responses)
3. Fingerprint cookie hardening (HttpOnly + SameSite=Strict + Secure-when-TLS-lands + reasonable max-age)
4. Pairing code brute-force resistance (5min TTL × 10k keyspace × admin PIN-gating × rate-limit on `/api/admin/devices/bind`)
5. Per-profile data isolation (every endpoint derives `profile_id` from session/device, never trusts client-provided id)
6. PAT revocation propagation (≤24h worst case via nightly sync; manual sync = immediate)
7. Soft-delete data hygiene (owner-driven hard-purge tool for GDPR-style removal)
8. PIN admin endpoint inventory (every new `/api/admin/profiles/*` and `/api/admin/devices/*` uses `require_admin`)
9. CSRF on admin POST/PATCH/DELETE (carries from v1 admin flows)
10. discogsography rate-limit etiquette (respects 429 + Retry-After)

v2.0 introduces no new security libraries — extends v1.0's `passlib[argon2]`, `cryptography.fernet`, FastAPI `SessionMiddleware` + `itsdangerous`.

---

## Risks & Open Questions

1. **Catalog# exposure outcome** — discogsography agent's verification spike result determines whether their P1 is small (already exposed) or larger (missing column + Discogs ingestion update). User to be informed when known. Mitigated by sequential coordination.
2. **Fingerprint cookie persistence across RPi reboot** — Chromium with `--user-data-dir` on persistent storage should preserve cookies. Verify during P3 implementation; mitigation = if cookies don't persist, fall back to re-pair on each reboot (acceptable but worse UX).
3. **`profile_id` migration scope** — touches 7 v1 tables. Highest-risk implementation item. Mitigated by Alembic round-trip CI invariant + per-table staged commits during P2.
4. **Cross-repo timing** — GRUVAX P1 cannot start until DGS-PREREQ closes. GRUVAX team idle during this window unless they pick up other work (v1.x backlog, hardware milestone prep, etc.).
5. **PAT trust within household** — owner sees raw PAT at paste time. Self-connect (v2.1) closes this; for v2.0 the assumption is household-owner-trust matches the existing single-PIN trust model.
6. **Cookie storage on iOS Safari** (browser session profile-picker path) — Safari restricts cross-site cookies. Same-site is fine since all traffic is to `gruvax.lan`; verify nonetheless.
7. **Discogsography API rate limits in practice** — full sync of 3,000 items at `per_page=200` = 15 requests; well under any reasonable limit. But a manual "Sync all profiles now" hitting 4 profiles back-to-back = 60 requests in <1 min; check against the rate-limit policy documented in the contract artifact.

---

## Out of Scope / Deferred

| Item | When |
|------|------|
| Per-profile self-connect PAT (invite-token model) | v2.1 |
| OAuth2 device-authorization grant (upgrade PAT path) | v2.2 (REQ-oauth2-device-grant) |
| QR-code RPi pairing | v2.1 |
| 9 SPIDR-deferred v1 reqs (SRCH-09, OFF-01..04, PRIV-01..04) | v2.1 (resilience + privacy floor) |
| Phase 999.1 (shelf-overview mini-Kallax) | Backlog |
| Phase 999.2 (LED party / sound-reactive modes) | Backlog |
| Real LED hardware end-to-end | Independent hardware milestone |
| Webhook push from discogsography → GRUVAX | Future (post-v2.0) |
| Collection diff highlighting ("5 new records") | v2.1 candidate |
| Cross-profile admin operations (e.g. copy boundaries) | v2.x candidate |
| Profile export/import CLI | v2.x candidate |

---

## Next steps after this spec is approved

1. **GRUVAX side** — invoke `/gsd-new-milestone v2.0 --reset-phase-numbers`. The roadmapper will consume:
   - `.planning/intel/SYNTHESIS.md` (the synthesized intel from the 2026-05-25 spec ingest)
   - This refined spec at `docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md`
   - The decisions in §"Refinement Decisions" above
   - Output: `.planning/REQUIREMENTS.md` (13 reqs), `.planning/ROADMAP.md` (P1–P4), `.planning/STATE.md` (reset to v2.0 P1).
2. **discogsography side** — already in flight per `background/discogsography-v2-app-tokens-brief.md`. GRUVAX waits for the "shipped" signal.
3. **Memory hygiene** — update stale `project_tooling_alignment_handoff` memory to reflect Phase 9 close per Q2 decision.
4. **Once DGS-PREREQ closes** — read `docs/specs/v2-gruvax-integration.md` from discogsography repo; reconcile any contract drift against this spec's assumptions; proceed to `/gsd-discuss-phase 1`.

# Intel — Constraints

Technical contracts, schemas, and non-functional constraints extracted from the v2.0 design SPEC. SPEC content has higher precedence than DOC/PRD per the standard ordering (ADR > SPEC > PRD > DOC).

---

## CON-app-tokens-schema

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design)
- **type:** schema (discogsography-side)
- **content:**

```
app_tokens (
  id            -- primary key
  user_id       FK -> users.id
  name          -- human-friendly label (e.g., "GRUVAX kiosk")
  scope         text[]  -- e.g., {"collection:read"}
  token_hash    -- store only a hash; plaintext shown once at mint time
  created_at    timestamptz
  last_used_at  timestamptz (nullable)
  revoked_at    timestamptz (nullable)
)
```

---

## CON-profiles-schema

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ GRUVAX-Side Design → Profiles)
- **type:** schema (GRUVAX-side, gruvax schema)
- **content:**

```
profiles (
  id                    -- primary key
  display_name          -- human-friendly name
  discogs_username      -- the underlying discogsography user
  app_token_encrypted   -- Fernet-encrypted PAT
  created_at            timestamptz
  last_sync_at          timestamptz (nullable)
  last_sync_status      -- e.g., "ok" | "failed" | "in_progress"
  ...                   -- additional sync metadata fields per spec "…"
)
```

---

## CON-devices-schema

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ RPi device binding)
- **type:** schema (GRUVAX-side, gruvax schema)
- **content:**

```
devices (
  id             -- primary key
  label          -- human label
  profile_id     FK -> profiles.id  (NOT NULL once bound)
  registered_at  timestamptz
  last_seen_at   timestamptz (nullable)
)
```

---

## CON-profile-id-fk-fanout

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ `profile_id` migration)
- **type:** schema (GRUVAX-side)
- **content:** Add `profile_id` (FK -> `profiles.id`) to the following tables and treat as part of the primary access path:
  - `cube_boundaries`
  - segments tables (per Phase 5 model)
  - settings table(s)
  - LED config table(s)
  - Phase 8 stats counters (`record_stats` aggregate-only counters)

  All existing v1.0 rows backfill to the "default" profile during migration.

---

## CON-collection-cache-fields

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **type:** schema (GRUVAX-side, gruvax schema)
- **content:** Per-profile collection cache table must include at minimum the fields positioning needs:
  - release_id
  - label
  - catalog_number
  - artist
  - title
  - … (additional fields as positioning requires)
  - profile_id (FK)

  Source of truth for these rows is the discogsography HTTP API; this is a **cache**, not a system of record.

---

## CON-discogsography-api-surface

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Context & Problem; § discogsography-Side Design)
- **type:** api-contract (consumed)
- **content:**
  - **Base:** FastAPI HTTP API on `:8004` (per discogsography current reality verified 2026-05-25).
  - **Endpoint:** `GET /api/user/collection` (paginated 50–200 per page).
  - **Auth:** bearer = PAT minted via `app_tokens` (see CON-app-tokens-schema). Validation via the new `require_app_token` dependency on the discogsography side.
  - **Related endpoints expected available:** `/api/user/collection/stats`, `/api/user/collection/timeline`.
  - **Catalog number availability:** unverified at design time. MUST be exposed (see REQ-catalog-number-exposure).

---

## CON-pat-bearer-flow

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Data Flow + § Locked Decisions D2)
- **type:** protocol
- **content:**
  - Member logs into discogsography and mints a scoped PAT (scope: `collection:read`, name: "GRUVAX kiosk").
  - PAT is shown plaintext exactly once at mint time; only its hash is stored on the discogsography side.
  - PAT is handed to the GRUVAX owner (or self-connected per-profile in a future privacy-improving variant), who stores it (Fernet-encrypted) on the profile row.
  - All collection-read API calls from GRUVAX use the PAT as bearer.
  - Revoking the PAT on the discogsography side immediately invalidates the GRUVAX profile's sync ability.

---

## CON-200ms-slo-preserved

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache; § Locked Decisions D6)
- **type:** nfr
- **content:** v1.0's perceived ≤200 ms type-ahead SLO carries into v2.0. Forces the pull-and-cache model — live remote queries through the discogsography API on every keystroke are not viable.
- **inherits-from-v1:** `/api/search` p95 ≤ 200 ms; `/api/locate` p95 ≤ 50 ms (Phase 8 CI gates). v2.0 must not regress these.

---

## CON-offline-resilience-preserved

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **type:** nfr
- **content:** Phase 4 offline behavior preserved. Kiosk must continue searching and locating from local cache when the discogsography API is unreachable.

---

## CON-staleness-redefinition

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **type:** nfr
- **content:** Sync staleness measured as `now - profiles.last_sync_at`, replacing v1's `max(v_collection.synced_at)`. Thresholds (3 days warning / 14 days banner) from v1.0 carry over. Kiosk staleness banner is per-profile.

---

## CON-rpi-binds-to-one-profile

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Locked Decisions D1, D5; § RPi device binding)
- **type:** protocol / invariant
- **content:** A single RPi kiosk renders **exactly one** profile's collection at a time. Profile binding is a server-side admin action; the kiosk does not switch profiles client-side. A profile may have ≥1 RPi bound to it.

---

## CON-rate-limit-collection-api

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design)
- **type:** nfr (discogsography-side)
- **content:** Modest per-token rate limit on the collection endpoints. Home-LAN scale; specific budget TBD in the discogsography phase.

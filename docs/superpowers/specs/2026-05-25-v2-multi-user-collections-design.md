# GRUVAX v2.0 — Multi-User Collections via discogsography API

**Date:** 2026-05-25
**Status:** Approved (design) — ready to route into GSD (`/gsd-new-milestone` for v2.0; `/gsd-phase` for the v1.x Phase 9)
**Author:** brainstorming session (Robert + Claude)

---

## Context & Problem

GRUVAX v1.0 (Phases 1–8, complete) reads discogsography's Postgres **directly** via a read-only
`gruvax.v_collection` view + grant. That model assumes a **single implicit collection** and tightly
couples GRUVAX to discogsography's database (Pitfall 5: the view is the *only* contact surface).

discogsography is a genuinely **multi-user** system (users keyed by UUID; per-user `user_collections`).
A household may have multiple members, each with their **own** Discogs collection on their **own**
physical Kallax shelves. v2.0 re-architects GRUVAX to:

1. Integrate with discogsography's **HTTP API** (not its DB) to fetch a *specific authorized user's* collection.
2. Require each user to **authorize** GRUVAX's access to their collection.
3. Support **multiple collections per GRUVAX deployment**, while a single RPi kiosk serves a single user's collection.

This requires changes in **both** repos. It re-architects GRUVAX's entire data source, so it is a
**new milestone (v2.0)**, not a single phase.

### Current discogsography reality (verified 2026-05-25)

- FastAPI HTTP API on `:8004`. Auth is **first-party only**: email/password → JWT (`require_user`),
  plus **Discogs OAuth 1.0a** for connecting *discogsography's own* users to *their* Discogs accounts.
- **There is no third-party app-authorization concept today** — nothing lets an external app (GRUVAX)
  request scoped access to a user's collection. This must be built.
- Collection endpoints exist: `GET /api/user/collection` (paginated 50–200), `…/stats`, `…/timeline`, etc.
- Data model: `users(id UUID)`, `user_collections(user_id, release_id, instance_id, title, artist, year,
  formats JSONB, label, condition, rating, notes, …)`, `oauth_tokens(user_id, provider, …)`.
- Redis (OAuth state), Fernet (credential encryption) already present — reusable for app tokens.

---

## Locked Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **Topology:** one central GRUVAX server holds all profiles; thin RPi kiosks bind to a profile. A profile may have **≥1 RPi**. | Matches "single deployment handles multiple users; single RPi = single user's collection" and today's "gruvax-api serves the SPA, RPi runs Chromium against it." |
| D2 | **discogsography auth: scoped Personal Access Tokens (PAT), device-grant-ready.** A logged-in discogsography user mints a revocable `collection:read` token for GRUVAX. | Smallest discogsography-side build; genuinely multi-app; revocable. Token model designed so an OAuth2 **device-authorization grant** can layer on later for a slicker kiosk flow. |
| D3 | **GRUVAX identity: single-PIN owner manages "collection profiles."** Each profile = a fully isolated GRUVAX context. | Keeps GRUVAX's existing single-PIN admin; no new account system; right-sized for a home box. The *authorization* is the member minting their PAT in discogsography; GRUVAX stores it (encrypted). |
| D4 | **Shelving is per-profile.** Units, cube boundaries, segment cuts + physical-width overrides, settings, LED config, and usage stats all gain a `profile_id` scope. | Each member's records sit on their own physical shelves. Reuses the v1 Phase 3/5/7 wizards & editors, run in a profile's context. |
| D5 | **Shelving layout belongs to the profile** (shared across that profile's RPis); each RPi binds to a profile. | A user's collection may be shown on >1 kiosk; the physical layout is the user's, not the device's. |
| D6 | **Collection access: pull-and-cache.** GRUVAX pages the collection from the discogsography API into its **own** per-profile tables; positioning runs off the local cache. | Forced by the 200 ms SLO + Phase 4 offline resilience + the positioning model (needs the full sorted collection). Live remote queries are not viable. |
| D7 | **Retire `gruvax.v_collection` + the read-only DB grant.** The API becomes the **only** integration point. | Decouples GRUVAX from discogsography's DB; GRUVAX can run anywhere with network access to the API. |

---

## discogsography-Side Design (cross-repo)

A "profile" in GRUVAX = a `{ discogsography user, PAT }`. discogsography must expose generic, scoped,
revocable app authorization:

- **`app_tokens` table:** `(id, user_id FK, name, scope[], token_hash, created_at, last_used_at, revoked_at)`.
  Store only a hash of the token (show the plaintext once at mint time). Scope set starts with `collection:read`.
- **Settings UI ("Connect an app"):** logged-in user mints / lists / revokes tokens, names them ("GRUVAX kiosk").
- **`require_app_token` dependency:** validates a bearer app-token, checks scope, resolves `user_id`,
  updates `last_used_at`. Applied to the collection read endpoints GRUVAX needs.
- **⚠ Catalog-number exposure (biggest unknown):** GRUVAX positions by **label → catalog# within label**.
  `user_collections` exposes `label` but catalog# was not visibly present (may live in release data or
  `metadata` JSONB). This phase MUST verify and, if needed, expose catalog# on the collection API.
  Without it, GRUVAX cannot compute positions.
- **Rate limiting / abuse:** modest per-token rate limit on the collection endpoints (home-LAN scale).

**Future (deferred):** OAuth2 **device authorization grant** — RPi shows a short code + URL, user approves
on their phone via their existing discogsography session. Layers onto the same token store.

---

## GRUVAX-Side Design

### Profiles
- `profiles` table: `(id, display_name, discogs_username, app_token_encrypted (Fernet), created_at,
  last_sync_at, last_sync_status, …)`.
- Single-PIN admin gains a **profile manager**: create / rename / delete profiles, connect a PAT,
  "Sync now," view per-profile staleness.
- v1's existing single collection becomes the **"default" profile** during migration.

### Collection sync-and-cache
- **API client** pages `GET /api/user/collection` (bearer = profile's PAT) into GRUVAX's own per-profile
  collection cache table (release_id, label, catalog#, artist, title, … — whatever positioning needs).
- **Triggers:** on profile connect, manual "Sync now" (admin), periodic background sync (configurable cadence).
- Positioning (parser/comparator, §4.1/§5 estimators), search (FTS), and `/api/locate` all run off the
  **local per-profile cache** — preserving the 200 ms SLO and Phase 4 offline behavior.
- **Phase 8 staleness redefinition:** "sync staleness" becomes **API-sync age per profile**
  (`now - profiles.last_sync_at`), replacing `max(v_collection.synced_at)`. Thresholds (3d/14d) carry over.

### `profile_id` migration
- Add `profile_id` to `cube_boundaries`, segments, settings, LED config, and the Phase 8 stats counters.
- Backfill all existing v1 rows to the "default" profile.
- All reads/writes (boundary cache, estimator snapshot, SSE invalidation, diagnostics) become profile-scoped.

### RPi device binding
- `devices` table: `(id, label, profile_id FK, registered_at, last_seen_at)`.
- A kiosk registers and is **bound to a profile**; it only ever renders its bound profile (units,
  collection, positioning, LED, staleness banner). Admin assigns/reassigns the binding.
- Provisioning flow TBD in its phase (e.g., kiosk shows a short pairing code; admin binds it on the phone).

### What is retired
- `gruvax.v_collection`, the read-only grant onto discogsography tables, and the direct-DB probe
  (Pitfall 5 contact-surface assumption) — replaced by the API client + cache.

---

## Data Flow (v2.0)

```mermaid
sequenceDiagram
    actor Member as Household member
    participant Disc as discogsography (API)
    participant Admin as GRUVAX admin (mobile, PIN)
    participant Srv as GRUVAX server
    participant Kiosk as RPi kiosk (bound to profile)

    Member->>Disc: log in, mint scoped PAT (collection:read) for "GRUVAX"
    Member-->>Admin: hand over PAT (or self-connect per-profile, future)
    Admin->>Srv: create profile + store PAT (encrypted)
    Srv->>Disc: GET /api/user/collection (bearer PAT, paged)
    Disc-->>Srv: collection items (label, catalog#, …)
    Srv->>Srv: cache per-profile; build snapshot/boundary cache
    Admin->>Srv: run setup wizard → units + cuts for this profile
    Admin->>Kiosk: bind kiosk to profile
    Kiosk->>Srv: search / locate (profile-scoped, off local cache, ≤200 ms)
    Srv-->>Kiosk: cube highlight + sub-cube position
```

---

## Phase Decomposition (v2.0 milestone)

1. **(discogsography) Scoped app tokens** + verify/expose catalog# on the collection API.
   *Cross-repo; gates everything.*
2. **(GRUVAX) API client + sync-and-cache — single profile.**
   **Walking skeleton:** Core Value end-to-end against one API-sourced collection; `v_collection` retired.
3. **(GRUVAX) Profiles + owner-managed multi-collection.** Profile CRUD, per-profile PAT + cache,
   `profile_id` migration (v1 data → default profile).
4. **(GRUVAX) Per-profile shelving + RPi device binding.** Wizards/editors scoped per profile;
   device registration + bind-to-profile; kiosk renders its bound profile.
5. **(GRUVAX) Sync / staleness / offline / diagnostics polish** per profile.
6. *(optional, later)* **OAuth2 device-authorization grant** — upgrade PATs to a slick kiosk connect flow.

---

## Phase 9 (v1.x — done now, separate from v2.0)

Low-ambiguity tooling/housekeeping; templates adapted from discogsography:

- **structlog** migration (replace the stdlib `JsonFormatter`/`LogRingHandler` wiring from Phase 8 with
  structlog while preserving the in-memory log ring buffer the diagnostics page reads).
- **Env-driven log level** (already partly via `LOG_LEVEL`; ensure debug level is settable via env).
- **GitHub workflows** adapted from discogsography: `test`, `code-quality`, `security`, `build`,
  **`cleanup-cache`**, **`cleanup-images`** (bring over both cleanup actions).
- **`.github/dependabot.yml`** (multi-ecosystem, grouped, weekly).
- **`.pre-commit-config.yaml`** (ruff, mypy, bandit, hadolint, actionlint, yamllint, shellcheck, …).
- **`scripts/update-project.sh`** adapted from discogsography (justfile-delegating).
- **Docs refresh:** capture the final Phase 1–8 design; **remove all `lux` and `nox` references**
  (deployment-host names that should not be baked into the docs).

> Note: Phase 9's CI should account for the **64 pre-existing ruff errors** in Phase 1–7 files
> (carried as `continue-on-error` in the Phase 8 CI) — either clean them as part of the lint-tooling work
> or keep them advisory until a dedicated lint-debt pass.

---

## Risks & Open Questions

1. **Catalog-number exposure (HIGH):** verify discogsography's collection API returns catalog# per item;
   if not, discogsography phase 1 must add it. Positioning is impossible without it.
2. **Cross-repo coordination:** two repos, two release cadences; the GRUVAX walking skeleton (v2 phase 2)
   depends on discogsography phase 1 shipping the token + catalog# first.
3. **`profile_id` migration:** touches most v1 tables; needs a clean Alembic round-trip and a correct
   v1→default-profile backfill.
4. **Kiosk provisioning/binding UX:** how a headless RPi is paired and bound to a profile (pairing code?).
5. **Token handling within a household:** owner-managed PAT now; per-profile self-connect (member pastes
   own token, owner never sees it) is a privacy-improving variant to consider.
6. **PAT vs device-grant timing:** PAT-first ships v2.0; device grant is an optional later phase.

---

## Out of Scope / Deferred

- OAuth2 device-authorization grant (optional later v2 phase).
- Per-user self-service GRUVAX accounts (rejected — single-PIN owner manages profiles).
- Real LED hardware (separate future milestone, unchanged by v2.0).
- Backlog items `999.1` (shelf-overview mini-Kallax) and `999.2` (LED party mode) remain backlog.

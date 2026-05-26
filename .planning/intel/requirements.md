# Intel — Requirements

Requirements extracted from the v2.0 design SPEC. The source doc is a SPEC, not a PRD, but it contains explicit phase decomposition + a goal hierarchy that downstream consumers (`gsd-roadmapper`) will turn into REQ rows. Capturing them here keeps provenance intact.

All requirements are scoped to **v2.0 milestone** unless noted otherwise. A separate "v1.x housekeeping" bucket at the bottom captures Phase 9 items — see auto-resolved conflict #1 in `INGEST-CONFLICTS.md` for the status of those.

---

## v2.0 — discogsography-side (cross-repo, gates everything)

### REQ-app-tokens-table

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design)
- **scope:** discogsography repo
- **description:** Add `app_tokens` table for scoped, revocable third-party app authorization.
- **acceptance:**
  - Columns: `(id, user_id FK, name, scope[], token_hash, created_at, last_used_at, revoked_at)`.
  - Store only a hash of the token; plaintext shown once at mint time.
  - Initial scope set includes `collection:read`.

### REQ-app-token-settings-ui

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design)
- **scope:** discogsography repo
- **description:** Settings UI ("Connect an app") lets a logged-in user mint, list, name, and revoke tokens.
- **acceptance:**
  - User can name tokens (e.g., "GRUVAX kiosk").
  - User can list active tokens with `last_used_at`.
  - User can revoke a token (sets `revoked_at`).

### REQ-require-app-token-dependency

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design)
- **scope:** discogsography repo
- **description:** `require_app_token` FastAPI dependency validates bearer app-token, checks scope, resolves `user_id`, updates `last_used_at`.
- **acceptance:**
  - Applied to the collection-read endpoints GRUVAX needs.
  - Returns 401 on missing/expired/revoked tokens; 403 on insufficient scope.

### REQ-catalog-number-exposure

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design + Risks #1)
- **scope:** discogsography repo
- **description:** Verify and, if needed, expose catalog number per item on the collection API.
- **acceptance:**
  - `GET /api/user/collection` items expose catalog number per item.
  - If the field already lives in release data or `metadata` JSONB, it must surface on the collection-read response shape used by GRUVAX.
- **risk:** HIGH — flagged as biggest unknown in the spec. Positioning is impossible without this. Gates GRUVAX walking skeleton.

### REQ-token-rate-limiting

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ discogsography-Side Design)
- **scope:** discogsography repo
- **description:** Modest per-token rate limit on the collection endpoints (home-LAN scale).

---

## v2.0 — GRUVAX-side

### REQ-profiles-table

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ GRUVAX-Side Design → Profiles)
- **scope:** GRUVAX repo
- **description:** Add `profiles` table to GRUVAX schema.
- **acceptance:**
  - Columns: `(id, display_name, discogs_username, app_token_encrypted (Fernet), created_at, last_sync_at, last_sync_status, …)`.
  - `app_token_encrypted` uses Fernet (same encryption story as discogsography).

### REQ-profile-manager-admin-ui

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ GRUVAX-Side Design → Profiles)
- **scope:** GRUVAX repo
- **description:** Single-PIN admin gains a profile manager.
- **acceptance:**
  - Admin can create, rename, delete profiles.
  - Admin can connect a PAT to a profile.
  - Admin can trigger "Sync now" per profile.
  - Admin can view per-profile staleness.

### REQ-v1-default-profile-migration

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ GRUVAX-Side Design → Profiles)
- **scope:** GRUVAX repo
- **description:** v1's existing single collection becomes the **"default" profile** during migration. Backfill all existing v1 rows to the "default" profile.

### REQ-api-client-paged-sync

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **scope:** GRUVAX repo
- **description:** API client pages `GET /api/user/collection` (bearer = profile's PAT) into GRUVAX's own per-profile collection cache table.
- **acceptance:**
  - Cache row fields include at minimum: release_id, label, catalog#, artist, title (anything positioning needs).
  - Handles paginated responses (50–200 per page per discogsography spec).

### REQ-sync-triggers

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **scope:** GRUVAX repo
- **description:** Sync triggers: on profile connect, manual "Sync now" (admin), periodic background sync (configurable cadence).

### REQ-positioning-runs-off-local-cache

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **scope:** GRUVAX repo
- **description:** Positioning (parser/comparator, §4.1/§5 estimators), search (FTS), and `/api/locate` all run off the **local per-profile cache**.
- **acceptance:**
  - 200 ms SLO from v1.0 (PERF-01) preserved (now p95 ≤ 200 ms `/api/search`, p95 ≤ 50 ms `/api/locate`, per Phase 8 CI gates).
  - Phase 4 offline behavior preserved.

### REQ-phase8-staleness-redefinition

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Collection sync-and-cache)
- **scope:** GRUVAX repo
- **description:** "Sync staleness" becomes **API-sync age per profile** (`now - profiles.last_sync_at`), replacing `max(v_collection.synced_at)`.
- **acceptance:** Thresholds (3d/14d) from v1.0 Phase 8 carry over.

### REQ-profile-id-migration

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ `profile_id` migration)
- **scope:** GRUVAX repo
- **description:** Add `profile_id` to `cube_boundaries`, segments, settings, LED config, and the Phase 8 stats counters; all reads/writes become profile-scoped.
- **acceptance:**
  - Boundary cache, estimator snapshot, SSE invalidation, diagnostics all profile-scoped.
  - Clean Alembic round-trip (upgrade↔downgrade — established v1.0 CI invariant).
  - Correct v1→default-profile backfill.
- **risk:** Migration touches most v1 tables (spec Risk #3).

### REQ-devices-table

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ RPi device binding)
- **scope:** GRUVAX repo
- **description:** Add `devices` table.
- **acceptance:** Columns: `(id, label, profile_id FK, registered_at, last_seen_at)`.

### REQ-rpi-device-binding

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ RPi device binding)
- **scope:** GRUVAX repo
- **description:** A kiosk registers and is bound to a profile; it only ever renders its bound profile (units, collection, positioning, LED, staleness banner).
- **acceptance:**
  - Admin can assign/reassign the binding.
  - Kiosk reflects its bound profile across all UI surfaces.

### REQ-kiosk-pairing-provisioning

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ RPi device binding + Risks #4)
- **scope:** GRUVAX repo
- **description:** Provisioning flow for headless RPi pairing/binding.
- **acceptance:** TBD in its phase (suggested: kiosk shows a short pairing code; admin binds it on the phone).
- **risk:** UX open question (spec Risk #4).

### REQ-retire-v-collection

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ What is retired)
- **scope:** GRUVAX repo
- **description:** Retire `gruvax.v_collection`, the read-only grant onto discogsography tables, and the direct-DB probe.
- **acceptance:**
  - View dropped (Alembic migration).
  - GRUVAX no longer requires Postgres grants into the discogsography schema.
  - Health/probe code updated to check discogsography HTTP API reachability instead.

---

## v2.0 — Deferred / optional

### REQ-oauth2-device-grant

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Future deferred + Phase 6 of decomposition)
- **scope:** v2.0 optional, later phase
- **description:** OAuth2 device-authorization grant — RPi shows a short code + URL, user approves on their phone via their existing discogsography session.
- **acceptance:** Layers onto the same `app_tokens` store; not required for v2.0 close.

---

## v1.x / Phase 9 (housekeeping)

**See auto-resolved conflict #1 in `INGEST-CONFLICTS.md`.** The v2.0 spec lists Phase 9 housekeeping items as to-be-done, but MILESTONES.md records Phase 9 as **shipped at v1.0 close (2026-05-26)**. The requirements below are preserved verbatim from the spec for traceability; the roadmapper should reconcile against MILESTONES.md.

### REQ-structlog-migration

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "Migrated to structlog (preserving the Phase 8 log ring buffer)."

### REQ-env-driven-log-level

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "env-driven log level."

### REQ-github-workflows

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "GitHub Actions tooling adapted from discogsography (lint/type/test + cleanup-cache + cleanup-images)."

### REQ-dependabot

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "dependabot."

### REQ-pre-commit-config

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "pre-commit hooks."

### REQ-update-project-script

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "`update-project.sh`."
- **note:** User-memory (`project_tooling_alignment_handoff`) flags an unfinished 1706-line `update-project.sh` adaptation on branch `chore/align-discogsography-tooling`. Roadmapper should reconcile whether that branch landed before v1.0 close — see auto-resolved conflict #1.

### REQ-docs-refresh-strip-lux-nox

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **scope:** v1.x housekeeping
- **status-in-v1:** **Shipped** per MILESTONES.md Phase 9: "Phase 1–8 docs refresh stripping `lux`/`nox` references."

### REQ-lint-debt-pass

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9 note)
- **scope:** v1.x housekeeping
- **description:** 64 pre-existing ruff errors carried as `continue-on-error` in Phase 8 CI; either clean them as part of lint-tooling work or keep advisory until a dedicated lint-debt pass.
- **status-in-v1:** Ambiguous — MILESTONES.md does not record whether the 64 ruff errors were cleared as part of Phase 9. User memory `project_tooling_alignment_handoff` cites "83 ruff errors remaining" on an in-flight tooling branch. Roadmapper should verify post-v1.0 state.

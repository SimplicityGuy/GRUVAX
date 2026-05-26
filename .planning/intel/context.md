# Intel — Context

Background notes, narrative framing, and open questions extracted from the v2.0 design SPEC. These are not contracts or requirements per se — they inform downstream planning but do not directly produce tasks.

---

## Topic — Problem framing: v1.0 single-collection assumption

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Context & Problem)
- **note:** GRUVAX v1.0 (Phases 1–8, complete) reads discogsography's Postgres directly via a read-only `gruvax.v_collection` view + grant. That model assumes a **single implicit collection** and tightly couples GRUVAX to discogsography's database (Pitfall 5: the view is the *only* contact surface).
- **note:** discogsography is a genuinely **multi-user** system (users keyed by UUID; per-user `user_collections`). A household may have multiple members, each with their **own** Discogs collection on their **own** physical Kallax shelves.

---

## Topic — Why this is a milestone, not a phase

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Context & Problem closing paragraph)
- **note:** v2.0 re-architects GRUVAX's entire data source, requires changes in **both** repos, and is a **new milestone (v2.0)**, not a single phase. The walking skeleton (v2 phase 2) is gated on a discogsography release; cadence coordination matters.

---

## Topic — discogsography current reality (verified 2026-05-25)

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Current discogsography reality)
- **notes:**
  - FastAPI HTTP API on `:8004`.
  - Auth is first-party only: email/password → JWT (`require_user`), plus Discogs OAuth 1.0a for connecting *discogsography's own* users to *their* Discogs accounts.
  - **There is no third-party app-authorization concept today** — nothing lets an external app (GRUVAX) request scoped access to a user's collection. This must be built.
  - Collection endpoints exist: `GET /api/user/collection` (paginated 50–200), `…/stats`, `…/timeline`, etc.
  - Data model relevant to GRUVAX: `users(id UUID)`, `user_collections(user_id, release_id, instance_id, title, artist, year, formats JSONB, label, condition, rating, notes, …)`, `oauth_tokens(user_id, provider, …)`.
  - Redis (OAuth state), Fernet (credential encryption) already present — reusable for app tokens.

---

## Topic — Data flow narrative (v2.0)

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Data Flow)
- **mermaid:** The spec includes a sequence diagram covering: member mints PAT in discogsography → hands off to GRUVAX owner → admin creates profile + stores encrypted PAT → server pages `/api/user/collection` and caches → admin runs setup wizard for the profile → admin binds kiosk to profile → kiosk searches and locates off the local cache ≤ 200 ms. The full Mermaid block is in the source spec; reproduce it verbatim into PROJECT.md if used downstream.

---

## Topic — Phase decomposition (v2.0)

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase Decomposition)
- **phases:**
  1. **(discogsography) Scoped app tokens** + verify/expose catalog# on the collection API. *Cross-repo; gates everything.*
  2. **(GRUVAX) API client + sync-and-cache — single profile.** Walking skeleton: Core Value end-to-end against one API-sourced collection; `v_collection` retired.
  3. **(GRUVAX) Profiles + owner-managed multi-collection.** Profile CRUD, per-profile PAT + cache, `profile_id` migration (v1 data → default profile).
  4. **(GRUVAX) Per-profile shelving + RPi device binding.** Wizards/editors scoped per profile; device registration + bind-to-profile; kiosk renders its bound profile.
  5. **(GRUVAX) Sync / staleness / offline / diagnostics polish** per profile.
  6. *(optional, later)* **OAuth2 device-authorization grant** — upgrade PATs to a slick kiosk connect flow.
- **dependency-graph:** GRUVAX Phase 2 (walking skeleton) is blocked on discogsography Phase 1. All other GRUVAX phases follow Phase 2.

---

## Topic — Phase 9 (v1.x housekeeping, done now, separate from v2.0)

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Phase 9)
- **note:** Spec frames Phase 9 as low-ambiguity tooling/housekeeping templates adapted from discogsography (structlog migration, env-driven log level, GitHub workflows, dependabot, pre-commit, `update-project.sh`, docs refresh removing `lux`/`nox`).
- **conflict-with-existing-context:** MILESTONES.md records Phase 9 as **shipped at v1.0 close (2026-05-26)**. See `INGEST-CONFLICTS.md` auto-resolved #1. User memory `project_tooling_alignment_handoff` notes an in-flight branch (`chore/align-discogsography-tooling`) with 83 ruff errors remaining + the 1706-line `update-project.sh` adaptation. Roadmapper should reconcile whether all spec-listed items closed before v1.0 was archived.

---

## Topic — Risks & open questions (carried from spec)

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Risks & Open Questions)
- **risks:**
  1. **Catalog-number exposure (HIGH):** verify discogsography's collection API returns catalog# per item; if not, discogsography phase 1 must add it. Positioning is impossible without it.
  2. **Cross-repo coordination:** two repos, two release cadences; the GRUVAX walking skeleton (v2 phase 2) depends on discogsography phase 1 shipping the token + catalog# first.
  3. **`profile_id` migration:** touches most v1 tables; needs a clean Alembic round-trip and a correct v1→default-profile backfill.
  4. **Kiosk provisioning/binding UX:** how a headless RPi is paired and bound to a profile (pairing code?).
  5. **Token handling within a household:** owner-managed PAT now; per-profile self-connect (member pastes own token, owner never sees it) is a privacy-improving variant to consider.
  6. **PAT vs device-grant timing:** PAT-first ships v2.0; device grant is an optional later phase.

---

## Topic — Out of scope / deferred for v2.0

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` (§ Out of Scope / Deferred)
- **deferred:**
  - OAuth2 device-authorization grant (optional later v2 phase).
  - Per-user self-service GRUVAX accounts (rejected — single-PIN owner manages profiles).
  - Real LED hardware (separate future milestone, unchanged by v2.0).
  - Backlog items `999.1` (shelf-overview mini-Kallax) and `999.2` (LED party mode) remain backlog.

---

## Topic — v2.0 also opens a path for v1-deferred reqs

- **source:** synthesizer note, cross-referenced with `/Users/Robert/Code/public/GRUVAX/.planning/milestones/v1.0-REQUIREMENTS.md` and `PROJECT.md` Next Milestone Goals.
- **note:** The 9 SPIDR-deferred v1.0 requirements (SRCH-09, OFF-01..04, PRIV-01..04) are **not** explicitly absorbed by the v2.0 spec, but several are natural fits for the new milestone:
  - **PRIV-01..04** (session-only history, no server query text, aggregate-only stats, no-PIN reset-kiosk) become more relevant once multiple household members touch the same kiosk — the kiosk-pairing/profile-binding flow may make these strictly required.
  - **OFF-01..04** (offline banner, disabled input, reconnect backoff, success indicator) tie directly into CON-offline-resilience-preserved and the staleness-banner redefinition.
  - **SRCH-09** (per-session recently-pulled list) is orthogonal but cheap.
- **action:** Roadmapper should consider whether to absorb any/all of these into the v2.0 scope, leave them as backlog, or split them.

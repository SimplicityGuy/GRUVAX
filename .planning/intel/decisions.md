# Intel — Decisions

Embedded decisions extracted from classified docs. The source spec is classified as SPEC (precedence 0 via manifest override), so these decisions surface here as **embedded ADR-like decisions inside a SPEC** rather than standalone ADRs.

None of the entries below are `locked: true` in the GSD sense (the classification has `locked: false`). The spec calls them "Locked Decisions" internally to signal that the design phase is closed for them, but per precedence rules they are treated as SPEC-level constraints that downstream phases can revisit if implementation surfaces a contradiction.

---

## D1 — Topology: central GRUVAX server holds all profiles; thin RPi kiosks bind to a profile

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** v2.0 deployment topology
- **decision:** One central GRUVAX server holds all profiles. Thin RPi kiosks bind to a profile. A profile may have ≥1 RPi.
- **rationale:** Matches existing "gruvax-api serves the SPA, RPi runs Chromium against it" deployment shape; aligns with "single deployment handles multiple users; single RPi = single user's collection."

## D2 — discogsography auth: scoped Personal Access Tokens (PAT), device-grant-ready

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** cross-repo authentication
- **decision:** A logged-in discogsography user mints a revocable `collection:read` token for GRUVAX. PAT-first ships v2.0; OAuth2 device-authorization grant deferred to optional later phase.
- **rationale:** Smallest discogsography-side build; genuinely multi-app; revocable. Token model designed so an OAuth2 device-authorization grant can layer on later.

## D3 — GRUVAX identity: single-PIN owner manages "collection profiles"

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** GRUVAX identity & admin authentication
- **decision:** Each profile = a fully isolated GRUVAX context. The single-PIN owner manages all profiles; no new account system. The *authorization* is the member minting their PAT in discogsography; GRUVAX stores it (encrypted).
- **rationale:** Keeps GRUVAX's existing single-PIN admin (preserved from v1.0); right-sized for a home box. Reuses Fernet encryption already present in discogsography.
- **relationship-to-v1:** Extends — v1's single-PIN admin (PROJECT.md Key Decisions: "Auth = single PIN (Argon2id) with sliding-window session timeout") is preserved; profile management is a new admin capability layered on top.

## D4 — Shelving is per-profile

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** v2.0 data model
- **decision:** Units, cube boundaries, segment cuts + physical-width overrides, settings, LED config, and usage stats all gain a `profile_id` scope. Each member's records sit on their own physical shelves. Reuses the v1 Phase 3/5/7 wizards & editors, run in a profile's context.
- **rationale:** Each member's records sit on their own physical shelves.

## D5 — Shelving layout belongs to the profile (shared across that profile's RPis)

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** v2.0 device binding semantics
- **decision:** A user's collection may be shown on >1 kiosk; the physical layout is the user's, not the device's. Each RPi binds to a profile.

## D6 — Collection access: pull-and-cache

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** integration model with discogsography
- **decision:** GRUVAX pages the collection from the discogsography API into its **own** per-profile tables; positioning runs off the local cache. Live remote queries are not viable.
- **rationale:** Forced by the 200 ms SLO + Phase 4 offline resilience + the positioning model (needs the full sorted collection).
- **supersedes-on-v2-milestone:** v1.0 decision "`gruvax.v_collection` view as the single contact surface with discogsography" (PROJECT.md Key Decisions; MILESTONES.md Phase 1). This was correct for v1.0's scope (single implicit collection, same-host Postgres). v2.0 changes the scope to multi-user collections + decoupled deployments, which the view model cannot serve.

## D7 — Retire `gruvax.v_collection` + the read-only DB grant

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** integration surface
- **decision:** The discogsography HTTP API becomes the **only** integration point. `gruvax.v_collection` view, the read-only grant onto discogsography tables, and the direct-DB probe (Pitfall 5 contact-surface assumption) are retired.
- **rationale:** Decouples GRUVAX from discogsography's DB; GRUVAX can run anywhere with network access to the API.
- **supersedes-on-v2-milestone:** v1.0 "Dedicated `gruvax` schema in the same Postgres instance, reads via `gruvax.v_collection` view" (PROJECT.md Key Decisions). The `gruvax` schema for GRUVAX-owned data (boundaries, segments, settings, history, profiles, devices, collection cache) remains; only the cross-schema read into discogsography is retired.

## D-meta — Cross-repo scope acknowledgment

- **source:** `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md`
- **status:** approved-design (v2.0 milestone)
- **scope:** milestone framing
- **decision:** v2.0 requires changes in **both** repos (GRUVAX + discogsography). The GRUVAX walking skeleton (v2 phase 2) depends on discogsography phase 1 shipping the token + catalog# first.
- **rationale:** Cross-repo coordination is an explicit risk (Risk #2 in the spec).

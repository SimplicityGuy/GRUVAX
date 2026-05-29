# Phase 2: Multi-profile migration + profile manager - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-28
**Phase:** 2-multi-profile-migration-profile-manager
**Areas discussed:** Cache architecture, Per-profile SSE shape, Profile picker UX, Profile manager admin UI

---

## Cache architecture

### Q1 — Cache shape

| Option | Description | Selected |
|--------|-------------|----------|
| Registry of instances | app.state holds dict[UUID, Cache]; one instance per profile; isolation by construction; cache classes internally unchanged; registry manages lifecycle. | ✓ |
| Profile-keyed internal dict | Each cache class gains self._by_profile dict; every method takes profile_id; minimal app.state churn; isolation depends on every call passing the right id. | |

**User's choice:** Registry of instances
**Notes:** Chosen for the by-construction isolation guarantee (an explicit v2 constraint), accepting the registry/factory lifecycle cost.

### Q2 — Load timing

| Option | Description | Selected |
|--------|-------------|----------|
| Eager at lifespan startup | Load all non-deleted profiles' caches at boot; honors p95 SLO on first request; household-scale memory trivial. | ✓ |
| Lazy on first bind | Load on first session bind; lower idle memory but first cold request risks blowing the 200ms SLO + needs a load guard on every read. | |

**User's choice:** Eager at lifespan startup
**Notes:** Registry mutation lifecycle (build-on-first-sync, evict-on-soft-delete) + unsynced-empty-profile behavior left to planner discretion (user chose "Next area").

---

## Per-profile SSE shape

### Q1 — Request routing

| Option | Description | Selected |
|--------|-------------|----------|
| Session-derived everywhere | Server reads bound_profile_id from session cookie; path-clean URLs; honors no-trust-client-id by construction; diverges from spec's literal URL. | |
| profile_id in URL, validated | /api/events/{profile_id}; server validates path-id == session bound_profile_id, 403 on mismatch; matches spec literally; explicit/debuggable. | ✓ |

**User's choice:** profile_id in URL, validated

### Q2 — Bus routing

| Option | Description | Selected |
|--------|-------------|----------|
| Single bus, server-side filter | One EventBus; subscribe(profile_id) tags the queue; publish enqueues only to matching subscribers + a global lane; smallest change to bus.py. | |
| Per-profile bus registry | dict[UUID, EventBus]; SSE endpoint resolves the bus by profile_id; physically separate fan-out; mirrors the cache registry for symmetry. | ✓ |

**User's choice:** Per-profile bus registry
**Notes:** Chosen for symmetry with the cache registry-of-instances decision. Bus lifecycle + 403/400 edge cases left to planner discretion (user chose "Next area").

---

## Profile picker UX

### Q1 — Picker route

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated /select route | / redirects to /select when unbound + 2+ profiles; pick → cookie → redirect to /; KioskView assumes a bound profile; matches spec's separate screen. | ✓ |
| Inline gate in KioskView | Picker rendered as a view-state of KioskView at /; no new route; risk of picker flash. | |

**User's choice:** Dedicated /select route

### Q2 — Bind logic

| Option | Description | Selected |
|--------|-------------|----------|
| Server-driven bootstrap | GET /api/session returns {profile_count, bound_profile_id, profiles[]}; single-profile auto-binds server-side (no flash); 0-profile → onboarding. | ✓ |
| Client-driven | SPA fetches GET /api/profiles, counts, decides; more client logic + possible flash. | |

**User's choice:** Server-driven bootstrap

### Q3 — Switch control

| Option | Description | Selected |
|--------|-------------|----------|
| Persistent corner button | Always-visible Nordic-Grid corner button → unbinds session → picker; matches spec; small confirm to avoid accidental taps. | ✓ |
| Tucked in a menu | Hidden behind menu/long-press; less discoverable, lower accidental-tap risk. | |
| You decide | Planner/UI-spec picks placement. | |

**User's choice:** Persistent corner button
**Notes:** Picker card contents, 0-profile onboarding, confirm copy left to Nordic Grid / UI-spec discretion. The browse-binding session being independent of the admin PIN session was captured as a planner note (not separately discussed — user chose "Next area").

---

## Profile manager admin UI

### Q1 — UI layout

| Option | Description | Selected |
|--------|-------------|----------|
| List + bottom-sheet drawer | /admin/profiles; tap card → drawer with connect/rotate/rename/sync/delete; matches v1 mobile sheet pattern. | ✓ |
| List + detail route | /admin/profiles + /admin/profiles/:id detail page; more room, more routes; heavier than P2 needs. | |

**User's choice:** List + bottom-sheet drawer

### Q2 — Connect flow

| Option | Description | Selected |
|--------|-------------|----------|
| Sync test then async full sync | Inline per_page=1 test-sync (~1s) → store PAT + capture user_id → kick off async full sync → syncing badge + poll; matches spec; surfaces PAT-rejected / collision / network errors. | ✓ |
| Fully blocking | test-sync AND full sync inline; simplest but blocks ~10-30s. | |

**User's choice:** Sync test then async full sync

### Q3 — Sync UX

| Option | Description | Selected |
|--------|-------------|----------|
| 202 + poll status | POST → 202 → poll GET /api/admin/profiles/{id} every ~2s; spinner while in_progress; completion toast; reuses status fields. | ✓ |
| Blocking + spinner | Keep P1's blocking /sync; spinner until response; zero endpoint change, no granular progress. | |
| SSE progress events | Sync publishes progress on the profile SSE channel; richest but mixes progress into the invalidation channel. | |

**User's choice:** 202 + poll status
**Notes:** Implies converting P1's currently-blocking trigger_sync endpoint to background-task + 202; D-14 inline cache refresh + SSE publish move to the end of the background task. After all four areas, user chose "Ready for context" — declined the optional migration-mechanics and admin-UI deep-dives.

---

## Claude's Discretion

- `profile_id NOT NULL` migration mechanics (composite-uniqueness per table, one-big vs per-table, downgrade fidelity) — follow P1's one-migration pattern + the Alembic round-trip CI invariant.
- `discogsography_user_id` collision error copy in the connect drawer.
- PAT-rotation drawer flow — mirror the connect flow with the D-09 strict user_id-match.
- Soft-delete confirmation modal contents (item count; no device count in P2).
- Picker card contents, 0-profile onboarding screen, confirm-modal copy, empty-profile "no records yet" affordance.
- Bootstrap endpoint name + the browse-binding cookie's name/TTL/attributes.
- Cache registry mutation lifecycle, per-profile bus lifecycle, and the unbound/mismatched-session 403/400 contract.

## Deferred Ideas

- Soft-delete cache-purge background task → P4 (P2 evicts in-memory registry entries + flips deleted_at + detaches from picker).
- "Sync now" completion-toast polish + sync-all-profiles → P4.
- 401 reauth UI (badge + kiosk banner) → P4.
- Per-profile /admin/diagnostics cards → P4.
- Nightly background sync scheduler + cadence config → P4.
- Devices + pairing + fingerprint cookie + RPi pairing UX → P3.
- Per-profile self-connect PAT (invite token) → v2.1 (AUTH-02).
- SSE-based sync progress events — considered for sync UX, rejected in favor of 202+poll.

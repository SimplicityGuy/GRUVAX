# Phase 2: Multi-profile migration + profile manager - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Lift the single-profile walking skeleton (P1) into a true multi-profile deployment. After P2, multiple owner-managed profiles operate fully independently — each with its own collection cache, cube boundaries, segments, settings, LED config, and stats — and browser sessions on the LAN can independently choose which profile to view. The owner manages profiles (create / connect-PAT / rotate-PAT / rename / soft-delete / sync-now) from a mobile-first PIN-gated admin UI. Per-profile SSE invalidation isolates each profile's cache refreshes so cross-profile data leakage is impossible by construction.

**In scope (P2):**
- `profile_id NOT NULL` migration: tighten the 5 per-profile data tables that received `profile_id` in migration 0009 — `cube_boundaries`, `settings`, `record_stats`, `segment_overrides`, `boundary_history` — to NOT NULL, plus composite-uniqueness updates. `admin_sessions` and `idempotency_keys` (the other 2 of the 7 fan-out tables) **keep** their nullable `profile_id` — they are global/infra, not per-profile data, and forcing NOT NULL would require touching every insert site for no isolation benefit. (Nullable column + default-profile backfill already shipped in P1 per D-11 via migration 0009; P2 tightens to NOT NULL.) **Reconciliation note (2026-05-28):** the original v2 spec/ROADMAP named `segments`/`change_log`/`change_sets`/`ambient_baseline`, but those table names never shipped — P1's migration 0009 implemented `segment_overrides`/`boundary_history` (+ `idempotency_keys`/`admin_sessions`) instead. Migration 0009's fan-out list is authoritative.
- Multi-profile cache routing: registry of per-profile `BoundaryCache` / `SegmentCache` / `CollectionSnapshot` (and per-profile `settings_cache`), eager-loaded at startup.
- Per-profile SSE channel `/api/events/{profile_id}` backed by a per-profile `EventBus` registry; `collection_changed` + `boundary_changed` events invalidate only the affected profile's caches.
- Per-profile request routing for search / locate / illuminate / events (profile_id in URL, validated against the session's `bound_profile_id`).
- Profile manager admin UI (`/admin/profiles`): list + bottom-sheet drawer.
- Browser session profile picker (`/select` route) + server-driven bootstrap + single-profile auto-bind + persistent kiosk "Switch profile" corner button.
- Per-profile staleness (generalize P1's single `app.state.default_profile_*` task to all profiles).
- "Sync now" wired to the existing `POST /api/admin/profiles/{id}/sync` endpoint, extended to non-default profiles, converted to background-task + 202 + poll.

**Out of scope (P3/P4 per refined spec):**
- `devices` + `pairing_codes` schemas, fingerprint cookie, 4-digit RPi pairing flow, devices admin UI (P3).
- Nightly background sync scheduler + cadence config (P4).
- 401 reauth UI (profile-list badge + kiosk inline banner) — P4 reads the `app_token_revoked` flag P1/P2 set.
- Per-profile `/admin/diagnostics` cards (P4).
- Soft-delete cache-purge **background task** (P4). P2's soft-delete flips `deleted_at` + detaches the profile from picker/admin and evicts its in-memory registry entries; the deferred async purge of `profile_collection` rows is P4.
- "Sync now" completion **toast** polish + sync-all-profiles (P4 owns the polish; P2 delivers the functional 202+poll button).

</domain>

<decisions>
## Implementation Decisions

### Cache architecture
- **D2-01: Registry of per-profile cache instances.** `app.state` holds a registry mapping `profile_id → cache instance` for each of `BoundaryCache`, `SegmentCache`, `CollectionSnapshot` (and `settings_cache`). One instance per profile; each cache class stays internally unchanged. **Rationale:** isolation by construction — a caller resolves the instance by `profile_id` first, so cross-profile leakage is structurally impossible (satisfies the explicit v2 constraint "cross-profile data leakage impossible by construction"). Preferred over a profile-keyed internal dict because the by-construction guarantee beats the smaller-signature-churn alternative.
- **D2-02: Eager load at lifespan startup.** Load every non-deleted profile's caches when the app boots (matches v1's startup-load pattern). Every request — including the first for any profile — honors the p95 SLO with no cold-load penalty. Household-scale memory (2–5 profiles × ~3k rows) is trivial.
- **D2-03 (planner discretion): registry mutation lifecycle.** Build a profile's registry entry on its first successful sync (extends P1's D-14 inline refresh); evict the entry on soft-delete. A bound-but-unsynced profile (created, no PAT/sync yet) has empty caches — search/locate return empty; kiosk shows a "no records yet / sync pending" affordance (UI-spec discretion).

### Per-profile SSE shape
- **D2-04: profile_id in URL, validated against the session.** `/api/events/{profile_id}`; search / locate / illuminate also carry `profile_id`. The server validates the path/query `profile_id` against the session's `bound_profile_id` and returns **403 on mismatch** — it never trusts the client-provided id as authoritative, only validates it (satisfies "never trust client-provided profile_id; derive from session/device binding"). Matches the refined spec's literal URL; explicit, debuggable URLs and per-profile cache observability.
- **D2-05: Per-profile `EventBus` registry.** `dict[UUID, EventBus]`; the SSE endpoint resolves the bus by `profile_id` and subscribes there. Physically separate fan-out per profile, symmetric with the cache registry-of-instances choice (D2-01).
- **D2-06 (planner discretion): bus lifecycle + edge cases.** Mirror the cache registry — eager per-profile bus at startup, add on profile create, remove on soft-delete. `server_hello` / `server_shutdown` broadcast across all buses. Unbound session subscribing → 400; session/path mismatch → 403.

### Profile picker UX (browser sessions)
- **D2-07: Dedicated `/select` route.** Browser hits `/` → if the session is unbound **and** 2+ active profiles exist, redirect to `/select`; picking a card sets the binding cookie and redirects to `/`. `KioskView` at `/` always assumes a bound profile. Clean separation, its own URL (good for the Switch-profile flow + browser back), matches the spec's separate picker screen.
- **D2-08: Server-driven bootstrap.** `GET /api/session` returns `{profile_count, bound_profile_id, profiles[]}`; the SPA routes from it. The **single-profile case auto-binds server-side** (binding cookie written on first GET) so the kiosk never flashes a picker; the 0-profile case returns an onboarding signal ("log in as owner"). Single source of truth; honors derive-binding-server-side.
- **D2-09: Persistent Nordic-Grid corner "Switch profile" button** on `KioskView` → unbinds the session → `/select`. A small confirm guards against accidental fat-finger taps on a wall-mounted screen.
- **D2-10: Browse-binding session is INDEPENDENT of the admin PIN session.** A LAN browser binds a profile and browses read-only with **no PIN** (R7); the admin PIN layers on top only for mutating actions. The `bound_profile_id` cookie is a separate concern from the v1 admin session cookie. (Planner: confirm cookie name/TTL/SameSite; do not couple the two sessions.)

### Profile manager admin UI
- **D2-11: List + bottom-sheet drawer** at `/admin/profiles`. List of profile cards (name, last_sync, item count, status badge: connected / pending / re-auth-required); tapping a card opens a bottom-sheet drawer with connect / rotate-PAT / rename / sync-now / soft-delete actions. Matches v1's established mobile sheet pattern (`RecordPickerSheet`, `SegmentStrip`) and the sketch-findings mobile-first direction. Preferred over a dedicated `/admin/profiles/:id` detail route (heavier than P2 needs).
- **D2-12: Connect-PAT = synchronous test-sync, then async full sync.** Paste PAT → server runs an inline `per_page=1` test-sync (~1s, blocks the request) → on 200: store the Fernet-encrypted PAT, capture/validate `discogsography_user_id`, flip `app_token_revoked = FALSE` → return success **and kick off the full sync as a background task** → the card shows a "syncing" badge and polls status → "connected" on done. Reuses the P1 `sync_profile(profile_id, app_state)` routine. Error states surfaced synchronously from the test-sync: PAT rejected (401/403 → `PATRejected`), `discogsography_user_id` collision with another active profile (D-09 strict-match, server-side partial-unique index), network/timeout.
- **D2-13: "Sync now" (and post-connect full sync) report progress via 202 + poll.** The button POSTs → **202 Accepted** → the UI polls `GET /api/admin/profiles/{id}` (~2s cadence), shows a spinner while `last_sync_status = 'in_progress'`, and fires a completion toast on `'ok'` / `'failed'`. No new realtime infra; reuses the existing status fields. **Implication:** P1's currently-blocking `POST /api/admin/profiles/{profile_id}/sync` (`trigger_sync`, `src/gruvax/api/admin/profile_sync.py:74`) is converted to kick off a background task + return 202; D-14's inline cache refresh + the new per-profile SSE `collection_changed` publish move to the **end of the background task** (not before the HTTP response).

### Claude's / planner's discretion
- `profile_id NOT NULL` migration mechanics — composite-uniqueness shape per table, one-big-migration vs per-table staging, downgrade fidelity. Follow P1's one-migration pattern + the v1.0 CI Alembic upgrade↔downgrade round-trip invariant. (Flagged as risk #3 — highest-risk implementation item; per-table staged commits during execution recommended.)
- `discogsography_user_id` collision error copy in the connect drawer (friendly variant of D-09's CLI message: "This PAT belongs to a discogsography user who already has a profile.").
- PAT-rotation drawer flow — same strict user_id-match invariant as connect (D-09); planner mirrors the connect flow.
- Soft-delete confirmation modal contents — item count (no device count in P2; devices are P3).
- Picker card contents, 0-profile onboarding screen, confirm-modal copy, "no records yet" empty-profile affordance — Nordic Grid / UI-spec discretion.
- Bootstrap endpoint name (`GET /api/session` vs reuse/extend an existing endpoint) and the browse-binding cookie's name/TTL/attributes.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 carry-forward (load first — P2 builds directly on it)
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-CONTEXT.md` — All P1 decisions (D-01..D-19) cascade into P2. Especially: D-01 (full `profiles` schema already shipped), D-02 (default-profile seed), D-03/D-04 (`profile_collection` PK + columns), D-05/D-06 (sync state machine + `app_token_revoked`), D-09 (strict user_id-match), D-11 (nullable `profile_id` already added — P2 tightens to NOT NULL), D-13 (`/api/health` field), D-14 (inline cache refresh → becomes SSE publish in P2).
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-SUMMARY.md` files (01-00..01-10) — what actually shipped vs. planned.

### v2.0 design specs (authoritative)
- `docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md` — **Refined design spec.** Load-bearing for P2: §Data Model (profiles, profile_collection, profile_id fan-out), §API Client + Sync (sync flow + triggers + staleness redefinition), §Profile Manager Admin UI, §Browser Session Profile Picker, §Phase Decomposition → **P2**, §Constraints → New in v2.0. D2-04/D2-05 (URL-validated routing + per-profile bus registry) and D2-13 (202+poll) refine the spec's sketch.
- `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` — Original SPEC; superseded by the refined version for any contradiction. Reference for the D1–D7 "Locked Decisions" framing.

### Intel (ingested, pre-synthesized)
- `.planning/intel/SYNTHESIS.md` — entry point for the ingested intel.
- `.planning/intel/decisions.md` — D1–D7 + D-meta locked at design time (D4/D5 = shelving is per-profile; D6/D7 = pull-and-cache, retire v_collection).
- `.planning/intel/constraints.md` — CON-200ms-slo-preserved, CON-staleness-redefinition, CON-profiles-schema, CON-profile-id-fk-fanout, CON-rate-limit-collection-api. The "cross-profile data leakage impossible by construction" + "sync staleness is per-profile" constraints drive D2-01/D2-04.
- `.planning/intel/requirements.md` — REQ-profiles-table, REQ-profile-manager-admin-ui, REQ-profile-id-migration, REQ-positioning-runs-off-local-cache, REQ-phase8-staleness-redefinition map to P2.
- `.planning/intel/context.md` — risks; risk #3 (`profile_id` migration scope) is the highest-risk P2 item.

### Project context
- `.planning/PROJECT.md` — Current State + Current Milestone (v2.0) + Key Decisions table.
- `.planning/REQUIREMENTS.md` — v2.0 active requirements; P2 owns **PROF-01, PROF-02, PROF-04, API-02 (multi-profile cache routing), SYN-02 (per-profile staleness)**.
- `.planning/ROADMAP.md` — §Phase 2 success criteria (5 criteria the verifier scores against).
- `.planning/STATE.md` — current position (Phase 1 complete, ready to plan Phase 2).
- `.planning/codebase/CONVENTIONS.md` — Nordic Grid design language + Mermaid/README conventions.

### Sketch findings (UI direction)
- `.claude/skills/sketch-findings-gruvax/SKILL.md` — validated Nordic Grid CSS patterns + mobile-first sheet/drawer direction. Drives D2-11 (list + bottom-sheet drawer) and the picker/switch-profile visual design.

### Existing code P2 modifies or extends
- `src/gruvax/app.py` — lifespan wires `app.state.boundary_cache` (167), `app.state.collection_snapshot` (177), `app.state.segment_cache` (190), `app.state.settings_cache` (198), `app.state.event_bus` (206), and the single-profile `app.state.default_profile_*` staleness task (235–255). **P2 generalizes all of these to per-profile registries.**
- `src/gruvax/estimator/boundary_cache.py`, `segment_cache.py`, `collection_snapshot.py` — the three cache classes that become registry-managed per-profile instances (D2-01).
- `src/gruvax/events/bus.py` — `EventBus` (single, in-process asyncio.Queue fan-out). P2 builds the per-profile registry (D2-05) around it.
- `src/gruvax/api/events.py` — `GET /api/events` SSE endpoint → becomes `/api/events/{profile_id}` with session validation (D2-04); depends ONLY on the bus, never `get_pool` (preserve Pitfall 10).
- `src/gruvax/api/admin/profile_sync.py:74` — `trigger_sync` `POST /api/admin/profiles/{profile_id}/sync`; converted to background-task + 202 (D2-13).
- `src/gruvax/sync/profile_sync.py:394` — `sync_profile(profile_id, app_state)`; already profile-keyed (advisory lock on profile_id). P2 moves the cache-refresh + SSE publish to the end as a per-profile operation.
- `src/gruvax/api/deps.py` — `get_pool`, `get_event_bus`, `require_admin`; P2 adds per-profile resolution deps (resolve cache/bus by validated profile_id).
- `src/gruvax/auth/sessions.py` — v1 admin session/cookie helpers; P2 adds the **independent** browse-binding (`bound_profile_id`) cookie (D2-10).
- `src/gruvax/db/queries.py` — search/locate/staleness queries (single default UUID in P1) parameterize over `profile_id`.
- `frontend/src/App.tsx` — add `/select` route; `KioskView` assumes a bound profile + gets the Switch-profile corner button.
- `frontend/src/routes/admin/` — new profile-manager screens; reuse `RecordPickerSheet`/`SegmentStrip` drawer patterns, `NumericKeypad`, `PinOverlay`, `AdminShell` nav.
- `migrations/versions/` — new migration tightening `profile_id` to NOT NULL across 7 tables + composite uniqueness; round-trip required.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`sync_profile(profile_id, app_state)`** (`src/gruvax/sync/profile_sync.py:394`) — already profile-parameterized with a per-profile pg advisory lock (`_lock_key`), staging-swap, and inline cache refresh. P2 reuses it verbatim for non-default profiles; only the post-swap step changes (per-profile cache reload + SSE `collection_changed` publish instead of the single-instance refresh).
- **`POST /api/admin/profiles/{profile_id}/sync`** (`trigger_sync`, `profile_sync.py:74`) — already PIN-gated and profile-keyed; P2 converts it to background-task + 202 (D2-13) and the "Sync now" button + connect flow both call it.
- **`EventBus`** (`src/gruvax/events/bus.py`) — drop-oldest asyncio.Queue fan-out; P2 instantiates one per profile in a registry (D2-05). Pitfall A ordering (publish AFTER commit + cache.load) and Pitfall 10 (SSE depends only on the bus) must be preserved.
- **Cache classes** (`boundary_cache.py`, `segment_cache.py`, `collection_snapshot.py`) — `invalidate()` / `load()` / `reload()` seams from Phase 4; reused per-profile (D2-01).
- **v1 mobile admin patterns** — `RecordPickerSheet`, `SegmentStrip`, `NumericKeypad`, `PinOverlay`, `AdminShell` (`frontend/src/routes/admin/`) — the bottom-sheet drawer + PIN gate + nav the profile manager reuses (D2-11).
- **Admin PIN dependency** (`require_admin`, `src/gruvax/api/deps.py`) — gates every new `/api/admin/profiles/*` mutating endpoint.
- **`gruvax-set-pat` strict-rotation logic** (`src/gruvax/cli/set_pat.py`, D-09) — the user_id-match invariant the admin connect/rotate drawer mirrors server-side.

### Established Patterns
- **No live probes on `/api/health`** — all subsystem fields derived from cached app-state. P2's per-profile staleness keeps this (generalize `default_profile_*` task).
- **Caches load at lifespan startup** — D2-02 eager-load extends this pattern to N profiles.
- **SSE depends ONLY on the bus, never `get_pool`** (Pitfall 10) — preserved when sharding the bus per profile.
- **Alembic upgrade↔downgrade round-trip enforced in CI** — the NOT NULL migration (risk #3) must honor it.
- **Parameterized `%s` SQL, no f-string interpolation** — all profile-keyed query rewrites follow it.
- **One env var per integration target; binding derived server-side, never trusted from the client** — D2-04/D2-10.

### Integration Points
- **Per-profile cache + bus registries on `app.state`** replace today's single `boundary_cache` / `segment_cache` / `collection_snapshot` / `settings_cache` / `event_bus`.
- **`GET /api/session` bootstrap** — new (or extended) endpoint returning `{profile_count, bound_profile_id, profiles[]}`; SPA routing source of truth (D2-08).
- **`/select` route + `bound_profile_id` cookie** — independent of the admin PIN session (D2-10).
- **`/api/events/{profile_id}`** + profile_id on search/locate/illuminate, validated against the session (D2-04).
- **`/admin/profiles`** screen + bottom-sheet drawer; connect/rotate/rename/sync/soft-delete endpoints under `/api/admin/profiles/*`.

</code_context>

<specifics>
## Specific Ideas

- **Symmetry is intentional:** the per-profile **cache registry** (D2-01) and the per-profile **EventBus registry** (D2-05) are deliberately the same architectural shape (`dict[UUID, X]` on `app.state`, eager at startup, add-on-create / evict-on-soft-delete). Plan their lifecycle together.
- **The 202+poll choice (D2-13) reshapes the P1 sync endpoint:** `trigger_sync` stops being blocking. The full sync runs as a background task; `last_sync_status` transitions `in_progress → ok|failed` are the polled signal; the per-profile SSE `collection_changed` publish + cache reload happen at the **end** of that task. This is the natural evolution of P1's D-14 (inline refresh → background-task refresh + SSE publish).
- **Security touchpoints already enumerated** for the post-implementation `/gsd-secure-phase`: per-profile data isolation (every endpoint derives/validates profile_id from session — D2-04), PIN admin endpoint inventory for `/api/admin/profiles/*`, CSRF on admin mutations (carries from v1), PAT-at-rest Fernet + in-transit redaction (carries from P1).
- **Two independent binding models, but only one exists in P2:** browse-binding via session cookie (this phase). Device-binding via the `devices` table is P3 — the kiosk "Switch profile" button explicitly ignores device binding because devices don't exist yet.

</specifics>

<deferred>
## Deferred Ideas

### Surfaced during discussion but belong in other phases / milestones
- **Soft-delete cache-purge background task** — P2 evicts in-memory registry entries + flips `deleted_at` + detaches from picker; the deferred async purge of `profile_collection` rows is **P4** (per refined spec).
- **"Sync now" completion-toast polish + sync-all-profiles** — functional 202+poll button lands in P2; the polish + multi-profile sync UX is **P4**.
- **401 reauth UI** (profile-list re-auth badge + kiosk inline banner) — **P4**, reading the `app_token_revoked` flag P2's connect flow sets.
- **Per-profile `/admin/diagnostics` cards** — **P4**.
- **Nightly background sync scheduler + cadence config** — **P4**.
- **Devices + pairing + fingerprint cookie + RPi pairing UX** — **P3**; the kiosk "Switch profile" button (D2-09) is browser-session-only in P2 and will coexist with device binding in P3.
- **Per-profile self-connect PAT (invite token)** — **v2.1** (AUTH-02); P2 stays owner-pasted-PAT.
- **SSE-based sync progress events** — considered for D2-13, rejected in favor of 202+poll to avoid mixing sync-progress into the cache-invalidation channel; revisit only if a richer progress UX is requested later.

### Reconciled risks (from refined spec)
- **`profile_id` migration scope (risk #3)** — the highest-risk P2 item; mitigated by D-11's P1 head start (nullable column + backfill already shipped) + the Alembic round-trip CI invariant + per-table staged commits during execution.
- **Cookie storage on iOS Safari / same-site (risk #6)** — same-site only (all traffic to `gruvax.lan`); verify the browse-binding cookie during P2 implementation.

</deferred>

---

*Phase: 2-multi-profile-migration-profile-manager*
*Context gathered: 2026-05-28*

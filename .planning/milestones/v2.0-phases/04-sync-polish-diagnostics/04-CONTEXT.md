# Phase 4: Sync polish + diagnostics - Context

**Gathered:** 2026-05-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Sync becomes **autonomous and observable**, closing the v2.0 milestone. P4 layers polish over scaffolding that already exists from P1/P2 — it builds little net-new infrastructure:

- **Nightly background sync scheduler** — `asyncio.create_task(_sync_loop())` started in lifespan; runs at 03:00 server-local default; cadence configurable in `/admin/settings` (24h / 12h / 6h / off) and persisted; iterates all non-revoked profiles sequentially.
- **401 / PAT-revocation surfacing** — the *detection* already exists (`sync_profile` sets `app_token_revoked=TRUE` + `last_sync_error='pat_rejected'` on a rejected PAT). P4 surfaces it: a re-auth-required badge in the Profiles admin UI and a non-blocking inline banner on the kiosk directing the owner to rotate the PAT. Worst-case latency ≤24h (nightly); immediate on manual "Sync now".
- **Per-profile `/admin/diagnostics` cards** — `last_sync_at`, `last_sync_status`, `last_sync_item_count`, `last_sync_error` per non-deleted profile, in Nordic Grid styling (v1.0 Phase 8).
- **Soft-delete cache-purge background task** — soft_delete already evicts the six in-memory registries (P2 D2-03) and detaches bound devices (P3); P4 adds the deferred purge of the bulky `profile_collection` rows, without cascading the audit lineage (`change_log` / `change_sets` keep their FKs).
- **"Sync now" progress + completion feedback** — the 202+poll path already exists (P2 D2-13, gap-closed in 02-08); P4 makes it first-class with progress UI + a completion toast.

**In scope (P4):** SYN-01 (three sync triggers — nightly is the new piece; connect + manual already shipped), SYN-02 closure (per-profile staleness UX polish + diagnostics cards).

**Out of scope (other phases / milestones):**
- "Sync all profiles now" manual button — deferred (nightly already syncs all; backlog candidate).
- Configurable timezone setting — out (server-local TZ is authoritative for a single-home deployment).
- Hard-delete of profile rows — never (soft-deleted rows persist forever for audit lineage).
- Per-profile self-connect PAT (v2.1), OAuth2 device-grant (AUTH-01 → v2.2), QR pairing (DEV-04 → v2.1).
- Real LED/WS2812B hardware — independent hardware milestone.

</domain>

<decisions>
## Implementation Decisions

### Nightly scheduler semantics (SYN-01)
- **D4-01: Wall-clock anchored to 03:00 server-local time.** The loop computes the next 03:00-local occurrence (DST-aware) and sleeps until it; reschedules after each run. Chosen over fixed-interval-from-startup, which drifts off 03:00 and runs at arbitrary times depending on last restart — contradicting the "nightly overnight sync" product promise.
- **D4-02: Catch-up on startup when stale.** On loop start, sync any non-revoked profile whose `last_sync_at` is older than the configured cadence, then resume the 03:00 schedule. Ensures staleness / PAT revocation surfaces soon after a restart instead of waiting up to a full cadence.
- **D4-03: Cadence runs anchored as multiples of the 03:00 base.** 24h → 03:00; 12h → 03:00 + 15:00; 6h → 03:00 / 09:00 / 15:00 / 21:00. Always includes the overnight run, lands on clean clock times. (24/12/6 divide 24 evenly, so "every N hours from a single 03:00 base" is functionally identical — planner may implement either as a single base + interval or enumerated clock times.)
- **D4-04: Skip policy — skip profiles with `app_token_revoked=TRUE` and skip profiles currently `last_sync_status='in_progress'`.** Revoked profiles would just re-401 and spam discogsography's logs (the badge already says "re-auth required"; nightly resumes them automatically after a successful rotate). Mid-sync profiles (e.g., a manual "Sync now" running) are skipped this tick to avoid racing the advisory lock for a guaranteed no-op. Correctness is still guaranteed by the existing advisory lock; these skips are efficiency, not safety.
- **D4-05: Timezone = server process local time** (the deployment host / Compose container TZ). No new setting, no UI. Single-home-LAN, one physical location → host clock is the owner's clock. Document that TZ comes from the container env.
- **D4-06: Loop re-reads cadence each iteration; "off" parks the loop.** The loop reads the cadence setting at the start of every tick. `off` → loop stays alive but sleeps (e.g., re-checks periodically) and runs nothing. Changing cadence in `/admin/settings` takes effect on the next tick — no restart needed. Cadence is a **global** setting stored under the default-profile UUID via the existing `_ALLOWED_SETTINGS_KEYS` whitelist (same pattern as `auth.pin_hash`); add a `sync.cadence` key.

### 401 / PAT re-auth surfacing (SYN-02)
- **D4-07: `app_token_revoked` boolean is the canonical "needs re-auth" signal for the UI badge.** Already set TRUE on `PATRejected`. A dedicated boolean is unambiguous and survives a later non-PAT failure (`rate_limited` / `network`) overwriting `last_sync_error`. Surface it on `GET /api/admin/profiles` + `GET /api/admin/profiles/{id}`. (Chosen over deriving the badge from `last_sync_error='pat_rejected'`, which a subsequent failure tag would mask.)
- **D4-08: The kiosk inline banner learns of re-auth via a field on `GET /api/session`.** The kiosk already calls `GET /api/session` for bootstrap/binding; add a `needs_reauth` (+ reason) field for the bound profile and render the banner from it. Picks up on the kiosk's normal session refresh cadence — no new endpoint, no new SSE event type. (A realtime SSE push was considered and rejected — the ≤24h bar doesn't need it.)
- **D4-09: Banner / badge auto-clears on a successful rotate+sync; no manual dismiss.** A successful PAT rotate triggers a test sync; on 200 set `app_token_revoked=FALSE`. The state is purely a function of sync health, so badge + kiosk banner disappear on the next list/session read. **Planner MUST confirm the rotate path resets `app_token_revoked=FALSE` and wire it if missing** (likely not yet handled — connect/rotate landed before this flag's UI mattered).
- **D4-10: Kiosk banner is non-blocking — search keeps working off the cached `profile_collection`.** Re-auth means sync is stale, not that the cache is gone; the cube-search core value must keep working off the last good cache. Persistent inline banner only (consistent with the v1.0 staleness-banner pattern). No full-screen re-auth overlay.

### Soft-delete cache-purge background task
- **D4-11: Purge triggered at delete-time AND backstopped by a lifespan startup safety sweep.** `soft_delete_profile` schedules the purge immediately (create_task / BackgroundTasks); lifespan additionally runs a one-shot startup sweep for any profile soft-deleted while the purge didn't complete (process killed mid-purge). Belt-and-suspenders, restart-safe. (Delete-time-only orphans rows forever if the process dies; nightly-loop-only delays cleanup up to a cadence and couples unrelated concerns.)
- **D4-12: Sweep predicate = `deleted_at IS NOT NULL AND profile_collection rows still exist` — no new column.** Self-clearing: once the rows are gone the profile no longer matches. (A `purged_at` timestamp column was considered but the state is already derivable from row presence; avoid the migration.)
- **D4-13: Purge removes `profile_collection` rows ONLY.** Keeps the profile row (soft-deleted), per-profile config (`cube_boundaries`, `segment_overrides`, `settings`, `record_stats`), and audit lineage (`change_log` / `change_sets` keep FKs). Smallest blast radius; matches criterion #4 verbatim. Devices are already detached at delete-time (P3); registries already evicted synchronously (P2 D2-03).
- **D4-14: The profile row is never hard-deleted in v2.0.** `deleted_at` marks it; the row persists so audit-lineage FKs stay valid. Purge only reclaims the bulky collection cache.

### Diagnostics cards + Sync-now UX (SYN-02)
- **D4-15: Per-profile diagnostics cards live in a new "Profiles" section on `/admin/diagnostics`** (below the existing system-level Phase 8 diagnostics), reusing the Nordic Grid card styling already on that page. The Profiles admin list keeps its compact P2 status badge; `/admin/diagnostics` is the detailed per-profile view. Matches criterion #3's "/admin/diagnostics cards" wording.
- **D4-16: Cards stay current via poll / refetch** (TanStack Query `refetchInterval` and/or refetch-on-focus against `GET /api/admin/diagnostics`). Matches the existing admin polling pattern (ProfileDrawer); diagnostics don't need sub-second freshness. (SSE-live was rejected as unnecessary for an admin-only screen; static-on-load was rejected because a sync completing elsewhere wouldn't reflect.)
- **D4-17: "Sync now" shows an indeterminate spinner + elapsed, reusing the existing 202+poll.** Keep the `in_progress → terminal` poll; show "Syncing…" (optional elapsed seconds) until terminal, then fire the completion toast. The staging-swap sync is atomic and doesn't naturally expose page-level progress, so indeterminate is honest and needs zero backend change. Satisfies criterion #5 ("shows progress until complete"). (A real page/item progress bar was rejected as over-engineered for a ~15-request, few-second sync.)

### Claude's / planner's discretion
- Exact next-03:00-local computation (zoneinfo + DST handling), the loop's sleep granularity, and how `off` parks (sleep-and-recheck interval).
- Whether the catch-up-on-startup sweep and the soft-delete purge startup sweep are one combined lifespan startup pass or two.
- `sync.cadence` setting value encoding (e.g., `"24h"|"12h"|"6h"|"off"` string vs hours int with 0/null = off) and validation in the settings whitelist.
- Toast copy, spinner styling, banner/badge copy — Nordic Grid / UI-spec discretion (`/gsd-ui-phase 4` is available; ROADMAP UI hint = yes).
- Diagnostics card layout/grid, refetch interval value, and whether a per-card "Sync now" button is added (vs only in the Profiles list/drawer).
- How the startup catch-up avoids a sync-storm (e.g., sequential with the same skip policy as nightly).

### Locked by ROADMAP / refined spec (flow into planning as-is — not re-decided here)
- The 5 success criteria in `.planning/ROADMAP.md` §"Phase 4" — what the verifier scores against.
- Nightly is `asyncio.create_task(_sync_loop())` in lifespan, sequential over non-revoked profiles (spec §Sync triggers).
- Staleness thresholds carry from v1.0 Phase 8: `<3d` none, `3–14d` yellow, `≥14d` red (spec §Staleness redefinition); banner reads `now() - profiles.last_sync_at`.
- Audit lineage (`change_log` / `change_sets`) retained on soft-delete (criterion #4).
- All v1.0 invariants hold at v2.0 close: Alembic upgrade↔downgrade round-trip clean, p95 SLOs (`/api/search` ≤200ms, `/api/locate` ≤50ms), structured logs, log-ring buffer, in-app keypad (criterion #5).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v2.0 design specs (authoritative)
- `docs/superpowers/specs/2026-05-26-v2-multi-user-collections-refined.md` — **Refined design spec.** Load-bearing for P4: §Sync triggers (nightly `asyncio.create_task(_sync_loop())`, 03:00 local, cadence 24h/12h/6h/off, sequential over non-revoked profiles); §Staleness redefinition (per-profile `now() - last_sync_at`, 3d/14d thresholds); §Profile Manager Admin UI (status badge: connected / pending / re-auth-required; "Sync now" progress + completion toast; soft-delete → schedule cache-purge background task); §Phase Decomposition → **P4** (exit criteria); §Security review touchpoints.
- `docs/superpowers/specs/2026-05-25-v2-multi-user-collections-design.md` — Original SPEC; superseded by the refined version on any contradiction.

### Phase carry-forward (load first — P4 polishes P1/P2/P3 work directly)
- `.planning/phases/01-walking-skeleton-api-client-single-profile-sync/01-CONTEXT.md` — P1 sync state machine (D-05 3-value `last_sync_status`, D-06 `last_sync_error` tag set), `sync_profile()`, default-profile seed, lifespan probe + background-task pattern.
- `.planning/phases/02-multi-profile-migration-profile-manager/02-CONTEXT.md` — D2-02 (per-profile cache/bus/state registries on app.state + per-profile refresh loop — the model the nightly loop sits beside), D2-03 (soft-delete evicts the six registries; **this is the synchronous half — P4 adds the row purge**), D2-04/D2-05 (per-profile SSE + EventBus), D2-13 (202+poll convention — "Sync now" reuses it).
- `.planning/phases/03-devices-pairing/03-CONTEXT.md` — D3-05 (profile soft-delete detaches bound devices, `devices.profile_id` → NULL — already done; P4's purge does NOT re-touch devices), `GET /api/session` is the SPA/kiosk bootstrap (P4 D4-08 adds `needs_reauth` here).

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — P4 owns **SYN-01** (three sync triggers; nightly is the P4-new piece) and **SYN-02** closure (per-profile staleness UX polish + diagnostics cards). Note: PROF-02's P4-flavored surfaces (Sync-now progress + 401 badge) are covered by SYN-01/SYN-02, not a split REQ.
- `.planning/ROADMAP.md` §"Phase 4: Sync polish + diagnostics" — the 5 success criteria the verifier scores against.
- `.planning/PROJECT.md` — Current State + v2.0 milestone framing + Key Decisions table.
- `.planning/STATE.md` — current position (Phase 3 shipped via PR #16; ready to plan Phase 4) + Open Questions (discogsography rate limits for back-to-back syncs).

### Intel (ingested, pre-synthesized)
- `.planning/intel/SYNTHESIS.md` — entry point for the ingested intel.
- `.planning/intel/constraints.md` / `decisions.md` / `requirements.md` / `context.md` — design-time constraints (per-profile staleness; cross-profile isolation) + R5 (sync triggers) + the catalog#/rate-limit considerations.

### Existing code P4 modifies or extends
- `src/gruvax/app.py` — lifespan; already has `app.state.background_tasks` set + `create_task` pattern and the per-profile 60s state-refresh loop. **P4 adds**: the nightly `_sync_loop()` (D4-01..06), the startup catch-up sweep (D4-02), and the soft-delete purge startup safety sweep (D4-11).
- `src/gruvax/sync/profile_sync.py` — `sync_profile()` + the `last_sync_status` / `last_sync_error` state machine + `app_token_revoked` set on `PATRejected`. **P4 reuses** this for the nightly loop; verify it sets `app_token_revoked=FALSE` somewhere on success (D4-09).
- `src/gruvax/api/admin/profile_sync.py` — `POST /api/admin/profiles/{id}/sync` 202+poll + `_run_sync_background`. "Sync now" UX (D4-17) reuses this unchanged.
- `src/gruvax/api/admin/profiles.py` — `soft_delete_profile` (sets `deleted_at`, evicts registries; explicitly notes "async row purge deferred to Phase 4"); `list_profiles` / `get_profile` (D4-07 adds `app_token_revoked` to their responses); `rotate_pat` / `connect_pat` (D4-09 reset-on-success). **P4 wires the purge here.**
- `src/gruvax/api/admin/diagnostics.py` — `GET /diagnostics` (system-level, Phase 8). **P4 extends** with per-profile sync metadata (D4-15/D4-16).
- `src/gruvax/api/admin/settings.py` — `_ALLOWED_SETTINGS_KEYS` whitelist + `GET/PUT /settings`. **P4 adds** the `sync.cadence` global key (D4-06).
- `src/gruvax/api/session.py` — `GET /api/session`. **P4 adds** the `needs_reauth` field for the bound profile (D4-08).
- `frontend/src/routes/admin/Diagnostics.tsx` + `Diagnostics.css` — Phase 8 diagnostics page. **P4 adds** the per-profile cards section (D4-15).
- `frontend/src/routes/admin/ProfileDrawer.tsx` + `frontend/src/api/adminClient.ts` — existing Sync-now poll; re-auth badge (D4-07), Sync-now spinner+toast polish (D4-17).
- `frontend/src/api/session.ts` + `frontend/src/api/types.ts` — session bootstrap types; add `needs_reauth` (D4-08); kiosk banner consumer.
- `migrations/versions/` — **likely NO new migration** (cadence is a settings row; purge is a DELETE; `app_token_revoked` already exists). Confirm during research; if any column is needed, the Alembic upgrade↔downgrade round-trip CI invariant must hold (current head = 0011 from P3).

### UI direction
- `.claude/skills/sketch-findings-gruvax/SKILL.md` — validated Nordic Grid CSS patterns + mobile-first sheet/drawer direction; drives the diagnostics cards, the re-auth badge, the kiosk banner, and the Sync-now spinner/toast styling. (Auto-loaded during UI implementation per CLAUDE.md.) A `/gsd-ui-phase 4` pass is available (ROADMAP UI hint = yes).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`sync_profile()` + the full `last_sync_status`/`last_sync_error`/`app_token_revoked` state machine** (`src/gruvax/sync/profile_sync.py`) — the nightly loop and catch-up sweep call this directly; the advisory lock inside it already serializes concurrent syncs.
- **202+poll "Sync now"** (`src/gruvax/api/admin/profile_sync.py` + ProfileDrawer `refetchInterval`) — the manual-sync path is done; D4-17 only adds spinner + completion-toast polish.
- **Lifespan background-task pattern** (`app.state.background_tasks` set + `create_task`, per-profile 60s refresh loop in `app.py`) — the nightly `_sync_loop()` and the two startup sweeps follow this exact pattern.
- **Per-profile registries on app.state** (boundary/snapshot/segment/settings/event_bus, P2 D2-02) — `soft_delete` already evicts them; the purge only adds the DB row delete.
- **`_ALLOWED_SETTINGS_KEYS` whitelist + global-settings-under-default-UUID pattern** (`api/admin/settings.py`) — `sync.cadence` slots in here exactly like LED keys and `auth.pin_hash`.
- **`GET /api/session` bootstrap** (`api/session.py`) — the kiosk/SPA routing source of truth; `needs_reauth` rides on it (D4-08).
- **System diagnostics page + Nordic Grid cards** (`frontend/src/routes/admin/Diagnostics.tsx`) — per-profile cards reuse the page + styling.

### Established Patterns
- **3-value `last_sync_status` + tagged `last_sync_error`** (D-05/D-06) — never expose a non-terminal, non-`in_progress` status during a sync (02-08 audit); the diagnostics cards read these verbatim.
- **Failure tags set on a separate connection** so a mid-sync exception still records `failed` (profile_sync.py) — preserved.
- **Advisory lock in `sync_profile`** guarantees correctness under concurrent triggers — the skip policy (D4-04) is efficiency on top, not the safety mechanism.
- **Global settings live under the default-profile UUID** (composite PK `(profile_id, key)`) — `sync.cadence` follows this (memory: P02 settings per-profile composite PK).
- **Per-profile SSE depends ONLY on the bus, never `get_pool`** (Pitfall 10) — unchanged in P4.
- **Alembic upgrade↔downgrade round-trip enforced in CI** — holds if any migration is added (current head = 0011).
- **Parameterized `%s` SQL, no f-string interpolation** (bandit B608) — the purge DELETE follows it.
- **PAT/secret redaction in structured logs** — nightly-loop logging must not leak PATs (existing `dscg_*` redactor).

### Integration Points
- **Nightly `_sync_loop()`** in lifespan — new fire-and-forget task; reads `sync.cadence` each tick; sequential over non-revoked, non-in-progress profiles (D4-01..06).
- **Startup catch-up sweep** (D4-02) + **soft-delete purge startup sweep** (D4-11) — one or two one-shot lifespan passes (planner discretion).
- **`app_token_revoked` exposed** on `GET /api/admin/profiles[/{id}]` (D4-07) and reset on rotate success (D4-09).
- **`needs_reauth` field** on `GET /api/session` (D4-08) → kiosk inline banner.
- **`sync.cadence` key** added to the settings whitelist + `/admin/settings` UI control (D4-06).
- **`GET /api/admin/diagnostics` extension** with per-profile sync metadata (D4-15/D4-16).
- **Soft-delete purge** in `soft_delete_profile` (DELETE `profile_collection` rows, D4-11..13).

</code_context>

<specifics>
## Specific Ideas

- **"03:00 local" is taken literally** (D4-01/D4-05): wall-clock-anchored using the host/container timezone, not interval-from-startup. The owner's mental model is "it syncs overnight."
- **The 401 path is already built — P4 is a UI/surfacing phase for it.** `app_token_revoked` and `last_sync_error='pat_rejected'` already get set inside `sync_profile`. The risk item to verify is the *reset on rotate success* (D4-09), which probably predates this flag mattering for UI.
- **Criterion #4's asymmetry is deliberate:** devices were already detached at soft-delete time (P3 D3-05); registries were already evicted synchronously (P2 D2-03). P4's purge is narrowly the *bulky `profile_collection` rows* — everything else about soft-delete is done.
- **Most of P4's "infrastructure" already exists** — the realistic plan count is small (~4 plans per the refined spec). The net-new code is: one lifespan loop + two startup sweeps, one settings key, one `GET /api/session` field, one `app_token_revoked` exposure + reset, one diagnostics extension, and the purge DELETE — plus the frontend cards/badge/banner/spinner-toast.
- **Watch discogsography rate limits** (STATE Open Question): the catch-up-on-startup sweep + nightly are both sequential over profiles; back-to-back full syncs of ~4 profiles ≈ 60 requests/min. Sequential (not parallel) iteration is the mitigation already chosen by the spec.

</specifics>

<deferred>
## Deferred Ideas

### Surfaced during discussion but belong elsewhere
- **"Sync all profiles now" manual button** — convenience beyond criterion #5 (singular "Sync now"); the nightly loop already covers all-profiles syncing. Backlog candidate; not P4.
- **Configurable timezone setting** — out of scope; server-local TZ is authoritative for a single-home-LAN deployment (D4-05). Revisit only if GRUVAX ever runs multi-site.
- **Real page/item Sync-now progress bar** — rejected as over-engineered for a ~15-request, few-second staging-swap sync (D4-17); indeterminate spinner + elapsed is the chosen UX.
- **`purged_at` audit column** — rejected; purge state is derivable from `profile_collection` row presence (D4-12). Revisit only if an explicit purge-audit trail is ever needed.
- **SSE-live diagnostics / SSE-pushed re-auth** — rejected; poll for diagnostics (D4-16) and `GET /api/session` field for re-auth (D4-08) are sufficient for an admin screen + a ≤24h SLA.

### Carried (milestone-level, not P4)
- Per-profile self-connect PAT → v2.1; OAuth2 device-authorization grant (AUTH-01) → v2.2; QR-code RPi pairing (DEV-04) → v2.1.
- Real LED/WS2812B hardware → independent hardware milestone.

</deferred>

---

*Phase: 4-sync-polish-diagnostics*
*Context gathered: 2026-05-29*

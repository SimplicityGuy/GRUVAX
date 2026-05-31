# Phase 6: Safe Boundaries + Live Device Lifecycle - Context

**Gathered:** 2026-05-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the two v2.0 tech-debt items that block safe multi-profile use:

1. **DATA-01 — Profile-scoped boundary writes.** `write_boundary` currently omits
   `profile_id` from its WHERE clause; on a multi-profile DB (PK is now
   `(profile_id, unit_id, row, col)`) an edit can match/clobber the wrong — or
   multiple — profiles' rows at the same physical position. Add `profile_id`
   scoping to every write path and make `boundary_changed` (and `admin_editing`)
   SSE fan-out per-profile instead of default-bus-only.
2. **DEV-05 — Live device lifecycle.** The server already publishes
   `device_revoked` / `device_reassigned` on the correct per-profile bus; the
   kiosk SSE consumer (`KioskView.tsx`) does not handle them. Wire the kiosk to
   react live — revoke → re-pair screen; reassign → live re-bind to the new
   profile — with no manual reload.

**Out of scope:** new admin profile-selector UI (browse-binding supplies the
profile context); QR pairing (Phase 8); offline/reconnect UX (Phase 9);
migration changes (this phase is pure code — no schema change). UI hint: **no**
(one frontend SSE-handler addition only).

</domain>

<decisions>
## Implementation Decisions

### Edit-profile source (DATA-01)
- **D-01:** `profile_id` for admin boundary writes is resolved from the
  **browse-binding cookie** (`gruvax_browse_binding`) via
  `resolve_profile_from_request`, layered onto the existing `require_admin` (PIN)
  dependency on every write route. The owner picks a profile via the existing
  `/select` picker; boundary edits apply to that bound profile. **No new admin
  profile-selector UI.**
- **D-02:** If the admin reaches a boundary editor with **no profile bound**
  (no browse-binding cookie), writes **fail loudly** — `400 session_unbound`
  (the existing resolve behavior) — and the admin UI routes the owner to
  `/select`. Never fall back to the default profile for an unbound admin.
- **D-03:** **All six** `write_boundary` call sites are scoped this phase, each
  with its `boundary_changed` fan-out retargeted to the resolved profile's bus:
  - `api/admin/cubes.py` — `put_cube_boundary` (per-cube), `bulk_write_cubes` (bulk)
  - `api/admin/segments.py` — single segment edit, bulk segment edit
  - `api/admin/import_.py` — CSV/YAML import
  - `api/admin/history.py` — undo
  Grep-verify no call site is missed before merging. Partial coverage leaves a
  corruption hole (e.g., import/undo clobbering another profile).

### SSE fan-out scoping (DATA-01)
- **D-04:** Admin-originated SSE events fan out to the **resolved profile's bus**
  from `event_bus_registry[str(profile_id)]`, not the default
  `app.state.event_bus` fallback. This covers **both** `boundary_changed` **and**
  `admin_editing` (shimmer) — no admin SSE event leaks across profiles.

### Revoke landing (DEV-05)
- **D-05:** On `device_revoked`, the kiosk shows a brief full-screen notice
  ("This screen was removed — re-pair to continue", ~2–3s) then routes to
  `/pair`. Not an instant jump (a mid-search visitor needs the reason); not
  `/select` (a revoked device wants re-pairing, and success criteria says
  "pairing screen").
- **D-06:** A terminal `403 device_revoked` returned by **any** in-flight API
  call routes to the **same** revoke handler as the SSE event (unify the path —
  the SSE event and the 403 race each other). Phase 9's offline terminal-revoke
  path depends on this unification.
- **D-07:** On the way out, the kiosk tears down its now-dead local state: clear
  the device binding client-side and stop the SSE connection to the old channel.

### Reassign UX (DEV-05)
- **D-08:** On `device_reassigned` (delivered on the **old** profile's bus,
  payload carries only `device_id`), the kiosk: re-fetches its session
  (`GET /api/session`) to learn the **new** profile → reconnects SSE to the new
  profile channel → refreshes the grid → shows a brief "Moved to &lt;Profile&gt;"
  toast/banner (~2–3s). Not silent (a watcher sees the collection change with no
  reason); not a full-screen interstitial (too heavy for a fast LAN round-trip).
- **D-09:** The new profile's **display name** for the flash must be available
  from the session re-fetch. **Plan-time check:** confirm `GET /api/session`
  returns the profile display name; if it returns only the id, add a follow-up
  fetch.

### Write-isolation feedback (DATA-01)
- **D-10:** A scoped write that affects **0 rows** (stale/wrong profile, or
  position not present for that profile) returns **404** ("boundary not found for
  this profile"); the admin UI surfaces a brief error and **refetches the grid**
  so the owner sees true current state. Loud-fail — a stale edit can never look
  like it succeeded (this is the exact silent-failure mode the phase eliminates).
- **D-11:** Bulk writes / change-sets stay **transactional**: if any cube in a
  bulk matches 0 rows, the **whole transaction aborts** with 404 — no partial
  application. Matches the existing atomic change-set model.

### Claude's Discretion
- Exact wording/styling of the revoke notice and reassign flash (use Nordic Grid
  tokens; ALL-CAPS labels, sentence-case instructions per the design language).
- Whether the revoke notice is tappable-to-skip vs. fixed timer.
- HTTP status nuance for 0-row writes was decided as 404 (D-10); 409 was
  considered and rejected (404 fits a profile-mismatch better than a concurrency
  conflict).
- Mechanism for threading the resolved `profile_id` through the 6 call sites
  (shared dependency vs. per-route resolve) — planner/researcher's call, as long
  as every write + fan-out is covered.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` §"Phase 6: Safe Boundaries + Live Device Lifecycle" — goal + 4 success criteria
- `.planning/REQUIREMENTS.md` — DATA-01 (write_boundary profile scoping + per-profile fan-out, **load-bearing**), DEV-05 (live device switch/revoke via SSE, closes DEV-02 tech debt)

### Research (v2.1)
- `.planning/research/SUMMARY.md` §"Phase 1: Tech-Debt Closure" — rationale, Pitfalls 33/34/35; "Grep-verify all write_boundary call sites before merging"
- `.planning/research/ARCHITECTURE.md` — per-profile registry isolation model; `write_boundary` fix as pure Python change (no migration)
- `.planning/research/PITFALLS.md` — Pitfall 33 (cross-profile boundary corruption), 34 (SSE fan-out to wrong profile), 35 (terminal-revoke handling)

### Backend surfaces (verified during scout)
- `src/gruvax/db/queries.py:641` — `write_boundary` (UPDATE on `gruvax.cube_boundaries`; WHERE missing `profile_id`)
- `src/gruvax/api/admin/cubes.py:315,756` — `put_cube_boundary`, `bulk_write_cubes` + `boundary_changed` publish (~367–373, ~800)
- `src/gruvax/api/admin/segments.py:276,650` — segment write paths + publishes (306,454,685)
- `src/gruvax/api/admin/import_.py:505` — import write path
- `src/gruvax/api/admin/history.py:165,236` — undo write path + publish
- `src/gruvax/api/deps.py:179` — `resolve_profile_from_request` (fingerprint → browse-binding); `:383` `get_event_bus` registry lookup
- `src/gruvax/app.py:178,259` — `event_bus_registry` init/keying (`str(profile_id)`)
- `src/gruvax/api/admin/devices.py:215,460,470` — `_publish_device_event`, reassign + revoke publishers (already per-profile — server side is done)
- `src/gruvax/api/events.py:3` — emitted event list
- `src/gruvax/auth/sessions.py:42,53` — `BROWSE_BINDING_COOKIE`, `FINGERPRINT_COOKIE`
- `migrations/versions/0010_profile_id_not_null.py` — `cube_boundaries` PK `(profile_id, unit_id, row, col)`; default profile UUID `00000000-0000-0000-0000-000000000001`

### Frontend surfaces (verified during scout)
- `frontend/src/routes/kiosk/KioskView.tsx:212–350` — SSE consumer; handles `boundary_changed`/`admin_editing`/`server_hello`/`server_shutdown`/`collection_changed`; **missing** `device_revoked`/`device_reassigned`
- `frontend/src/routes/ProfilePicker.tsx` — `/select` picker + `/pair` button
- `frontend/src/stores/sessionStore.ts` — `boundProfileId`, `clearBoundProfile()`
- `frontend/src/App.tsx:99` — `/select` route (and `/pair`)

### Design
- `design/gruvax-design-language.md` + tokens — revoke notice / reassign flash must use Nordic Grid tokens (no hardcoded hex; ALL-CAPS labels, sentence-case instructions)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `resolve_profile_from_request` (deps.py:179) — already returns `(profile_id, device_id|None)` and raises `400 session_unbound` / `403 device_revoked`; reuse on admin write routes for D-01/D-02.
- `event_bus_registry` (app.py) + `get_event_bus` lookup (deps.py:383) — the per-profile bus mechanism already exists; D-03/D-04 just retarget publishes to it.
- Server-side device lifecycle publishing (`_publish_device_event`, devices.py:215) — **already correct per-profile**; no server change needed for DEV-05's emit side.
- `/select` + `/pair` routes and `clearBoundProfile()` — landing targets for D-05/D-07.

### Established Patterns
- Atomic change-set model for bulk boundary edits → D-11 transactional abort fits existing behavior.
- `KioskView` SSE consumer is a switch over event names → D-05/D-08 add two cases + connection lifecycle teardown.
- Admin routes compose `Depends(require_admin)`; D-01 adds profile resolution alongside it.

### Integration Points
- The 6 write paths are the DATA-01 surface; the kiosk SSE switch is the DEV-05 surface. They share nothing except the per-profile bus contract.
- DEV-05 terminal-403 handler (D-06) is a shared seam Phase 9 (offline UX) will build on.

</code_context>

<specifics>
## Specific Ideas

- Verification for success criterion #3 is an explicit **two-profile integration
  test**: a boundary edit on profile A must not modify profile B's cube at the
  same `(unit_id, row, col)`. Required deliverable, not optional.
- Reuse the existing `gruvax-dev-pg` multi-profile test setup; force-stale /
  multi-profile fixtures already used in prior phases apply here.

</specifics>

<deferred>
## Deferred Ideas

- A dedicated admin **profile-selector UI** for boundary editing (decoupled from
  browse-binding) — explicitly rejected for this phase (D-01 uses browse-binding,
  UI hint: no). Revisit only if owners report friction switching profiles via
  `/select`.
- None other — discussion stayed within phase scope.

</deferred>

---

*Phase: 6-Safe Boundaries + Live Device Lifecycle*
*Context gathered: 2026-05-30*

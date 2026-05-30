# Phase 5: Close v2.0 integration gaps (B-01 + B-02) — Context

**Gathered:** 2026-05-30
**Status:** Ready for planning
**Source:** Milestone-audit-as-spec (`.planning/v2.0-MILESTONE-AUDIT.md`) + operator decisions (no discuss-phase; research skipped)

<domain>
## Phase Boundary

Closure phase (mirrors v1.0 Phase 10). The v2.0 milestone audit passed every per-phase
VERIFICATION.md but found cross-phase SSE/session wiring seams no single-phase check could
catch. This phase closes the **two BLOCKERS only**:

- **B-01** — `collection_changed` SSE event is published by sync but never consumed by the
  kiosk → search results are stale after a nightly or manual "Sync now" until a manual reload.
- **B-02** — `profile_id` query param is omitted when `boundProfileId` is null, and the backend
  declares it as a required param → `/api/search` + `/api/locate` return 422 before session
  bootstrap resolves the bound profile.

**Delivers (user-observable):**
1. After a nightly/manual sync completes, the kiosk's currently-displayed search results refresh
   live — no manual reload.
2. A user who types before the session bootstrap resolves the bound profile gets results (or a
   clean empty/loading state), never a 422 results-list error.

</domain>

<decisions>
## Implementation Decisions (LOCKED)

### B-01 — kiosk consumes `collection_changed`
- Add a `collection_changed` SSE listener in `frontend/src/routes/kiosk/KioskView.tsx`, mirroring
  the **existing `boundary_changed` listener registration pattern** in the same file (same
  `es.addEventListener(...)` + cleanup idiom used for `boundary_changed` / `admin_editing` /
  `server_hello` / `server_shutdown`).
- On `collection_changed`, invalidate the **search and locate query keys** — not only
  `['units']` / `['cubes']`. The existing `resync()` only invalidates `['units']` / `['cubes']`;
  it must also invalidate the `['search', ...]` (and locate) keys so the visible results refetch.
- Source of the event: `src/gruvax/sync/profile_sync.py` (`_refresh_profile_caches` →
  `bus.publish('collection_changed')`, ~line 356). Backend already publishes correctly; this is
  a **frontend-only** fix. Do not change the publisher.

### B-02 — tolerate omitted `profile_id` (BOTH backend-tolerant + frontend gate)
**Backend (authoritative fix):**
- Make `profile_id` **optional** on both `src/gruvax/api/search.py` (line 43) and
  `src/gruvax/api/locate.py` (line 78): `profile_id: str | None = Query(default=None)`.
- When `profile_id` is **omitted**, derive the authoritative profile from
  `resolve_profile_from_request(request, pool)` — the same single authoritative path that
  `get_snapshot_for_profile` / the locate snapshot dep already use for D2-04 cookie validation
  (`src/gruvax/api/deps.py:179`) — and pass that resolved UUID to the data query
  (`search_collection(...)` / `get_release_for_locate(...)`).
- When `profile_id` is **present**, preserve the existing D2-04 validation exactly: 400 if
  unbound, 403 if mismatch against the `gruvax_browse_binding` cookie. No behavior change for
  callers that already send it.
- Net: a request with no `profile_id` + a valid browse-binding cookie returns **200 scoped to the
  bound profile**, not 422.

**Frontend (defense-in-depth gate):**
- Gate the search & locate TanStack Query on `boundProfileId` being non-null
  (`enabled: !!boundProfileId && <existing query-length gate>`) in
  `frontend/src/api/client.ts` callers / the kiosk query hooks, so no request fires until session
  bootstrap resolves the bound profile. Keep the existing
  `if (profileId) paramObj.profile_id = profileId` builder (`client.ts:19,30`) — it is now correct
  against the tolerant backend.

### Testing (no RESEARCH.md / VALIDATION.md this run — research was skipped)
- Follow this repo's RED-test-first convention. Add tests **before** the fix:
  - Backend: `GET /api/search` and `GET /api/locate` with `profile_id` **omitted** + a valid
    browse-binding cookie → expect **200** scoped to the bound profile (currently 422). Preserve
    existing 400-unbound / 403-mismatch cases when `profile_id` is supplied.
  - Frontend: `collection_changed` SSE event invalidates the search/locate query keys (results
    refetch); search query is disabled while `boundProfileId` is null.
- Endpoint tests use `dependency_overrides`, not `patch` (project convention).

</decisions>

<scope_fence>
## Out of Scope (DO NOT expand)

The audit's four WARNINGS are explicit tech debt and are **NOT** part of this phase, even where
thematically adjacent:
- **W-01** — kiosk `StalenessBar` reads default-profile staleness (touches B-01's area but is a
  separate fix). Out.
- **W-02** — `PairView` navigates without refreshing the session store. Out.
- **W-03** — admin `boundary_changed` published to default bus only (explicitly deferred as D2-04
  in `app.py:280`). Out.
- **W-04** — no kiosk handler for `device_revoked` / `device_reassigned`. Out.

Also out: closing Phase 1's draft VALIDATION.md and the other documentation-drift tech-debt items
in the audit frontmatter (those are `/gsd-validate-phase` / doc-update work, not this phase).

</scope_fence>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Scope source
- `.planning/v2.0-MILESTONE-AUDIT.md` — defines B-01 / B-02 (and the out-of-scope W-01..W-04) with
  exact file:line, root cause, and consequence.

### B-01 (frontend SSE wiring)
- `frontend/src/routes/kiosk/KioskView.tsx` — existing SSE listeners (`boundary_changed` etc.) +
  `resync()`; add `collection_changed` here.
- `src/gruvax/sync/profile_sync.py` — publisher (`_refresh_profile_caches`, ~line 356); read-only
  reference, do not modify.

### B-02 (backend optional param + frontend gate)
- `src/gruvax/api/search.py` (line 43) and `src/gruvax/api/locate.py` (line 78) — `profile_id`
  Query param to make optional.
- `src/gruvax/api/deps.py` (`resolve_profile_from_request`, line 179; `get_snapshot_for_profile`,
  line 293) — the authoritative profile-resolution path to fall back to.
- `frontend/src/api/client.ts` (lines 19, 30) — `profile_id` param builders; add the
  `boundProfileId` query gate at the call sites.

### Conventions
- `./CLAUDE.md` — stack, Nordic Grid design language, GSD workflow.
- Endpoint tests: `dependency_overrides` not `patch`; session-scoped `db_pool`; `loop_scope="session"`.

</canonical_refs>

<specifics>
## Specific Ideas

- Requirements re-asserted by this phase (degraded end-to-end in the audit, restored here):
  **API-02** (positioning/search/locate off the per-profile cache), **SYN-01** (sync triggers →
  kiosk reflects the result), **SYN-02** (per-profile staleness UX — B-01 half).
- Both fixes are in already-shipped, well-understood code paths; this is wiring, not new design.
- Likely 2–3 plans: a RED-test scaffolding step, the B-01 frontend listener, and the B-02
  backend+frontend pair (planner decides exact wave/plan split).

</specifics>

<deferred>
## Deferred Ideas

- W-01..W-04 warnings and the documentation-drift / Phase-1-VALIDATION tech debt — see scope fence.
  Promote separately if/when desired.

</deferred>

---

*Phase: 05-close-v2-0-integration-gaps-kiosk-collection-changed-listene*
*Context gathered: 2026-05-30 via milestone-audit-as-spec (operator decisions: proceed without discuss-phase, skip research, B-02 = both backend-tolerant + frontend gate)*

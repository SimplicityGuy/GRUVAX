# Phase 2: Multi-profile migration + profile manager — Research

**Researched:** 2026-05-28
**Domain:** Multi-profile schema migration, per-profile cache registry, per-profile SSE, background-task 202+poll sync, browse-binding cookie, React Router 7 SPA bootstrap
**Confidence:** HIGH (core mechanics verified against official Alembic/FastAPI docs and live codebase reads)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D2-01:** `app.state` holds a registry `dict[UUID, X]` for `BoundaryCache`, `SegmentCache`, `CollectionSnapshot`, and `settings_cache`. One instance per profile. Cache classes stay internally unchanged.
- **D2-02:** Eager load at lifespan startup — every non-deleted profile's caches populate on boot.
- **D2-03 (planner discretion):** Build registry entry on first successful sync; evict on soft-delete. Unsynced profile → empty caches → search/locate returns empty + "no records yet" affordance.
- **D2-04:** `/api/events/{profile_id}` (and search/locate/illuminate carry `profile_id`). Server validates path `profile_id` against session `bound_profile_id`: 403 on mismatch, 400 on unbound.
- **D2-05:** `dict[UUID, EventBus]` registry; SSE endpoint resolves bus by `profile_id`.
- **D2-06 (planner discretion):** Mirror cache registry lifecycle — eager per-profile bus at startup, add on create, remove on soft-delete. `server_hello`/`server_shutdown` broadcast across all buses.
- **D2-07:** `/select` route — unbound session + 2+ profiles → redirect to `/select`; single-profile → auto-bind server-side.
- **D2-08:** `GET /api/session` returns `{profile_count, bound_profile_id, profiles[]}`. Single-profile auto-bind server-side on first GET. SPA routes from this.
- **D2-09:** Persistent Nordic-Grid corner "Switch profile" button → unbind → `/select`. Confirm guard.
- **D2-10:** Browse-binding `bound_profile_id` cookie is INDEPENDENT of admin PIN session. No PIN for read-only browsing (R7).
- **D2-11:** List + bottom-sheet drawer at `/admin/profiles`. Reuses `RecordPickerSheet` CSS + drawer pattern.
- **D2-12:** Connect-PAT = synchronous `per_page=1` test-sync → success → store encrypted PAT + kick full async sync as background task.
- **D2-13:** "Sync now" → 202 Accepted → poll `GET /api/admin/profiles/{id}` at 2s cadence. `last_sync_status` transitions `in_progress → ok|failed` are the signal.

### Claude's Discretion

- `profile_id NOT NULL` migration mechanics — composite-uniqueness shape per table, one-big-migration vs per-table staging, downgrade fidelity.
- `discogsography_user_id` collision error copy in connect drawer.
- PAT-rotation drawer flow — same strict user_id-match invariant (D-09).
- Soft-delete confirmation modal contents (item count; no device count — devices are P3).
- Picker card contents, 0-profile onboarding, confirm-modal copy, "no records yet" affordance.
- Bootstrap endpoint name and browse-binding cookie name/TTL/attributes.

### Deferred Ideas (OUT OF SCOPE)

- Soft-delete cache-purge background task → P4
- "Sync now" completion-toast polish + sync-all-profiles → P4
- 401 reauth UI → P4
- Per-profile `/admin/diagnostics` cards → P4
- Nightly background sync scheduler + cadence config → P4
- Devices + pairing + fingerprint cookie + RPi pairing UX → P3
- Per-profile self-connect PAT → v2.1
- SSE-based sync progress events → rejected (keeps sync out of cache-invalidation channel)
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PROF-01 | `profiles` table with Fernet-encrypted PAT storage, soft-delete via `deleted_at`, partial-unique indexes on `display_name` (case-insensitive) and `discogsography_user_id` | Already shipped in migration 0009. P2 adds admin CRUD + connect/rotate/rename/soft-delete endpoints + UI. |
| PROF-02 | Profile manager admin UI: list + status badges; create / connect-PAT / rotate-PAT / rename / soft-delete; "Sync now" button per profile | 12 new React components per UI-SPEC; reuse `RecordPickerSheet` CSS; 202+poll pattern for sync. |
| PROF-04 | `profile_id NOT NULL` migration across 7 v1 tables with composite-uniqueness updates and clean Alembic round-trip | Migration 0010: `op.alter_column(nullable=False)` on actual 7 tables (see §Critical Migration Discovery); PK changes required for `settings`, `record_stats`, `cube_boundaries`, `segment_overrides`. |
| API-02 | Positioning / search / locate off local cache; p95 `/api/search` ≤ 200 ms and `/api/locate` ≤ 50 ms SLOs preserved with 2+ profiles cached | Per-profile registry (D2-01); benchmark gate parameterized over `profile_id`; `DEFAULT_PROFILE_UUID` fallback removed from `queries.py`. |
| SYN-02 | Staleness redefinition per-profile: `now() - profiles.last_sync_at`; banner per-kiosk-view per-profile | Generalize `_refresh_default_profile_state` background task to all profiles; `health.py` reports per-profile. |
</phase_requirements>

---

## Summary

Phase 2 generalizes the single-profile skeleton (P1) to N profiles across five
interlocking concerns: (1) schema — tighten the nullable `profile_id` columns that
0009 added to the 7 actual v1 tables to NOT NULL and add composite uniqueness; (2)
in-memory caches — replace 5 single-instance `app.state.*` attributes with
`dict[UUID, X]` registries; (3) SSE — shard the single `EventBus` into one per
profile keyed by validated `profile_id`; (4) async sync — convert the blocking
`trigger_sync` endpoint to background task + 202 + poll; and (5) frontend — new
`/select` route + server-driven bootstrap + Switch-profile button + profile manager
admin UI (12 new components, all consuming existing Nordic Grid CSS tokens).

**The highest-risk item** is the NOT NULL migration. Migration 0009 added `profile_id`
to 7 v1 tables (actually `admin_sessions`, `boundary_history`, `cube_boundaries`,
`idempotency_keys`, `record_stats`, `segment_overrides`, `settings` — not the tables
named in the spec/ROADMAP), backfilled them to the default UUID, and left them
nullable. P2 migration 0010 must (a) verify there are no remaining NULLs, (b) promote
to NOT NULL, and (c) where the table's existing PRIMARY KEY needs `profile_id` in its
composite, drop and re-create the PK. Four tables require PK changes: `cube_boundaries`,
`settings`, `record_stats`, `segment_overrides`. The remaining three (`admin_sessions`,
`boundary_history`, `idempotency_keys`) carry `profile_id` only as a FK reference —
their PKs are unchanged.

**Primary recommendation:** Plan migration 0010 as a single file with per-table
sections following the verified three-step pattern: (1) backfill check, (2) PK
drop + re-create for the four affected tables, (3) `op.execute("ALTER TABLE ...
ALTER COLUMN profile_id SET NOT NULL")` for all seven. Do NOT use
`op.alter_column(nullable=False)` — prefer the raw SQL form to avoid Alembic's
reflection path misidentifying the FK constraints on these tables. Downgrade must
reverse all PK changes and drop the NOT NULL constraint. The `just migrate-roundtrip`
CI gate validates the round-trip.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Profile CRUD (create / rename / soft-delete) | API / Backend | — | Mutates `profiles` table; admin-PIN gated. |
| PAT connect / rotate (test-sync + store) | API / Backend | — | Fernet encrypt, user_id capture, uniqueness guard — all server-side. |
| Browse-binding cookie (`bound_profile_id`) | API / Backend | Browser | Server writes cookie on `GET /api/session`; browser stores and sends it. |
| `GET /api/session` bootstrap | API / Backend | — | Single source of truth for SPA routing decisions. |
| Profile picker (`/select` route) | Browser / Client | — | Pure client-side SPA route; no SSR. |
| Admin profile manager UI (`/admin/profiles`) | Browser / Client | API / Backend | React components consume `/api/admin/profiles` REST API. |
| Per-profile cache registry | API / Backend | — | `app.state.boundary_cache_registry` etc.; lives in-process. |
| Per-profile SSE channel | API / Backend | Browser | Server resolves bus by `profile_id`; browser subscribes to `/api/events/{profile_id}`. |
| Staleness background refresh | API / Backend | — | 60s task reads `profiles.last_sync_at` for all active profiles. |
| NOT NULL schema migration | Database / Storage | — | Alembic migration 0010; pure DDL + backfill verification. |
| SLO benchmark gate | API / Backend | — | `just slo` runs pytest-benchmark parameterized over profile_id. |

---

## Standard Stack

### Core (no new packages — all already in pyproject.toml)

| Library | Current Version | Purpose | Why Standard |
|---------|----------------|---------|--------------|
| FastAPI | 0.136.3 (PyPI) | BackgroundTasks, status_code=202 | Already in use; `BackgroundTasks` built-in. [VERIFIED: PyPI] |
| Alembic | 1.18.4 (PyPI) | Migration 0010 NOT NULL + PK changes | Already in use; op.execute raw SQL is the correct path. [VERIFIED: PyPI] |
| psycopg 3.2 | pinned in pyproject | Async DB driver | Already in use; all new queries follow existing `%s` pattern. [ASSUMED: matches project lock] |
| React Router 7 | 7.15.1 (npm) | `/select` route + SPA navigation | Already in use in `App.tsx`. [VERIFIED: npm registry] |
| TanStack Query 5 | 5.100.14 (npm) | 2s poll for `GET /api/admin/profiles/{id}` | Already in use; `useQuery` with `refetchInterval`. [VERIFIED: npm registry] |
| Zustand 5 | 5.0.14 (npm) | `bound_profile_id` local state | Already in use. [VERIFIED: npm registry] |
| lucide-react | existing | Icons (`RefreshCw`, `Loader2`, `Eye`/`EyeOff`) | Already in use per UI-SPEC. [ASSUMED: matches project lock] |
| sse-starlette | 3.4+ (pyproject) | Preserve existing SSE pattern | Already in use; per-profile bus is transparent to sse-starlette. [ASSUMED: matches project lock] |

### No new packages required for P2
P2 is a structural expansion of existing patterns. All required capabilities
(BackgroundTasks, per-profile dicts, React Router routes, TanStack Query polling)
are already available in the locked dependency set. No `npm install` or `pip install`
steps are needed beyond what P1 shipped.

**Installation:** No new packages to install.

---

## Package Legitimacy Audit

No new external packages are installed in Phase 2. All libraries referenced are
already in the locked `pyproject.toml` and `package.json` from Phase 1.

| Package | Registry | Notes | slopcheck | Disposition |
|---------|----------|-------|-----------|-------------|
| (none new) | — | P2 uses existing locked deps only | n/a | n/a |

*slopcheck was unavailable at research time, but no new packages are being introduced.*

---

## Architecture Patterns

### System Architecture Diagram

```mermaid
graph TD
    Browser[Browser / Kiosk SPA]
    SessionEndpoint[GET /api/session]
    SelectRoute[/select route<br/>ProfilePicker]
    KioskView[KioskView + SwitchProfileButton]
    AdminProfiles[/admin/profiles<br/>ProfilesManager]

    ProfileAPI[GET|POST /api/admin/profiles/*]
    SearchAPI[GET /api/search?profile_id=X]
    LocateAPI[GET /api/locate?profile_id=X]
    EventsAPI[GET /api/events/profile_id]
    SyncEndpoint[POST /api/admin/profiles/id/sync → 202]

    CacheRegistry["app.state<br/>boundary_cache_registry: dict[UUID, BoundaryCache]<br/>segment_cache_registry: dict[UUID, SegmentCache]<br/>snapshot_registry: dict[UUID, CollectionSnapshot]<br/>settings_cache_registry: dict[UUID, dict]<br/>event_bus_registry: dict[UUID, EventBus]"]

    BackgroundSync[sync_profile background task<br/>→ UPDATE profiles SET last_sync_status<br/>→ staging-swap<br/>→ reload registry caches<br/>→ bus.publish collection_changed]

    DB[(PostgreSQL gruvax schema<br/>profiles · profile_collection<br/>cube_boundaries · settings · ...)]

    Browser -->|GET /api/session| SessionEndpoint
    SessionEndpoint -->|writes bound_profile_id cookie| Browser
    SessionEndpoint -->|if unbound + 2+ profiles| SelectRoute
    SelectRoute -->|card tap → POST /api/session/bind| Browser
    Browser --> KioskView
    Browser --> AdminProfiles
    KioskView -->|profile_id from session cookie| SearchAPI
    KioskView -->|profile_id from session cookie| LocateAPI
    KioskView -->|profile_id from session cookie| EventsAPI
    AdminProfiles --> ProfileAPI
    ProfileAPI -->|connect PAT test-sync inline| BackgroundSync
    SyncEndpoint -->|202 + enqueue| BackgroundSync
    BackgroundSync --> DB
    BackgroundSync -->|cache reload| CacheRegistry
    BackgroundSync -->|collection_changed| CacheRegistry
    SearchAPI --> CacheRegistry
    LocateAPI --> CacheRegistry
    EventsAPI -->|resolves bus by profile_id| CacheRegistry
```

### Recommended Project Structure Changes

```
src/gruvax/
├── app.py                     # lifespan: single instances → registry dicts
├── api/
│   ├── deps.py                # add get_cache_for_profile(), get_bus_for_profile()
│   ├── events.py              # /api/events/{profile_id} with session validation
│   ├── session.py             # NEW: GET /api/session + POST /api/session/bind + unbind
│   ├── admin/
│   │   ├── profile_sync.py    # trigger_sync → BackgroundTasks + 202
│   │   └── profiles.py        # NEW: CRUD for profiles (create/rename/soft-delete/rotate)
├── sync/
│   └── profile_sync.py        # cache reload + bus.publish at END of background task
└── auth/
    └── sessions.py            # add browse-binding cookie helpers

frontend/src/
├── App.tsx                    # add /select route + bootstrap effect
├── api/
│   └── session.ts             # NEW: GET /api/session client
├── routes/
│   ├── ProfilePicker.tsx      # NEW: /select route
│   ├── ProfilePickerCard.tsx  # NEW
│   ├── OnboardingScreen.tsx   # NEW: 0-profile state
│   ├── kiosk/
│   │   ├── KioskView.tsx      # add profile_id routing + Switch button + empty state
│   │   ├── SwitchProfileButton.tsx    # NEW: fixed corner pill
│   │   ├── SwitchProfileConfirm.tsx   # NEW: confirm modal
│   │   └── EmptyCollectionState.tsx   # NEW: unsynced profile affordance
│   └── admin/
│       ├── ProfilesManager.tsx        # NEW: /admin/profiles list
│       ├── ProfileCard.tsx            # NEW
│       ├── ProfileDrawer.tsx          # NEW: bottom-sheet (reuses RecordPickerSheet CSS)
│       ├── ProfileStatusBadge.tsx     # NEW
│       ├── SyncProgressSection.tsx    # NEW: spinner + item count
│       └── AdminShell.tsx             # add PROFILES nav tab

migrations/versions/
└── 0010_profile_id_not_null.py       # NEW: NOT NULL + PK changes across 7 tables
```

### Pattern 1: Per-profile Registry on app.state

**What:** Replace single-instance cache attributes with `dict[UUID, CacheType]`.
**When to use:** Any access to a profile's cache or bus.

```python
# startup (lifespan) — eager-load all non-deleted profiles
app.state.boundary_cache_registry: dict[str, BoundaryCache] = {}
app.state.event_bus_registry: dict[str, EventBus] = {}

async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(
        "SELECT id FROM gruvax.profiles WHERE deleted_at IS NULL"
    )
    rows = await cur.fetchall()

for (profile_id_str,) in rows:
    cache = BoundaryCache()
    await cache.load(pool, profile_id=profile_id_str)  # existing load() sig extended
    app.state.boundary_cache_registry[profile_id_str] = cache
    bus = EventBus()
    app.state.event_bus_registry[profile_id_str] = bus
    # ... repeat for snapshot, segment_cache, settings_cache
```

**Key constraint:** The registry key MUST be a plain `str` (UUID as string), not a
`uuid.UUID` object, so it matches the session cookie value without conversion surprises.
[ASSUMED: consistent with existing `DEFAULT_PROFILE_UUID` string constant pattern]

### Pattern 2: per-profile deps resolution

**What:** New deps that resolve registry entry by validated `profile_id`.
**When to use:** All per-profile endpoints (search, locate, events, illuminate).

```python
# src/gruvax/api/deps.py
def get_boundary_cache_for_profile(
    profile_id: str,            # from path param
    request: Request,
) -> BoundaryCache:
    bound = request.cookies.get("gruvax_browse_binding")
    if not bound:
        raise HTTPException(status_code=400, detail={"type": "session_unbound"})
    if bound != profile_id:
        raise HTTPException(status_code=403, detail={"type": "profile_mismatch"})
    registry = getattr(request.app.state, "boundary_cache_registry", {})
    cache = registry.get(profile_id)
    if cache is None:
        raise HTTPException(status_code=404, detail={"type": "profile_not_found"})
    return cache
```

[ASSUMED: exact cookie name and dep signature — planner resolves final names]

### Pattern 3: NOT NULL Migration (migration 0010)

**What:** Three-step pattern per table: (1) backfill verification, (2) PK reconstruction where needed, (3) SET NOT NULL.
**When to use:** All 7 tables from migration 0009.

```python
# migration 0010 — per-table pattern (no f-string SQL)
# Step 1: verify no NULLs remain (the backfill was in 0009)
_VERIFY_NO_NULLS = (
    "DO $$ BEGIN "
    "  IF EXISTS (SELECT 1 FROM gruvax.cube_boundaries WHERE profile_id IS NULL) "
    "  THEN RAISE EXCEPTION 'NULL profile_id in cube_boundaries — backfill 0009 incomplete'; "
    "  END IF; "
    "END $$",
    # ... repeat for other 6 tables
)

# Step 2: PK reconstruction for tables needing composite PK
# cube_boundaries: PK (unit_id, row, col) → (profile_id, unit_id, row, col)
_CUBE_BOUNDARIES_PK = (
    "ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT cube_boundaries_pkey",
    "ALTER TABLE gruvax.cube_boundaries ADD PRIMARY KEY (profile_id, unit_id, row, col)",
)
# settings: PK (key) → (profile_id, key)
_SETTINGS_PK = (
    "ALTER TABLE gruvax.settings DROP CONSTRAINT settings_pkey",
    "ALTER TABLE gruvax.settings ADD PRIMARY KEY (profile_id, key)",
)
# record_stats: PK (release_id) → (profile_id, release_id)
_RECORD_STATS_PK = (
    "ALTER TABLE gruvax.record_stats DROP CONSTRAINT record_stats_pkey",
    "ALTER TABLE gruvax.record_stats ADD PRIMARY KEY (profile_id, release_id)",
)
# segment_overrides: PK (unit_id, row, col, label) → (profile_id, unit_id, row, col, label)
_SEGMENT_OVERRIDES_PK = (
    "ALTER TABLE gruvax.segment_overrides DROP CONSTRAINT segment_overrides_pkey",
    "ALTER TABLE gruvax.segment_overrides ADD PRIMARY KEY (profile_id, unit_id, row, col, label)",
)

# Step 3: SET NOT NULL for ALL 7 tables (safe since backfill completed in 0009)
_SET_NOT_NULL = (
    "ALTER TABLE gruvax.admin_sessions ALTER COLUMN profile_id SET NOT NULL",
    "ALTER TABLE gruvax.boundary_history ALTER COLUMN profile_id SET NOT NULL",
    "ALTER TABLE gruvax.cube_boundaries ALTER COLUMN profile_id SET NOT NULL",
    "ALTER TABLE gruvax.idempotency_keys ALTER COLUMN profile_id SET NOT NULL",
    "ALTER TABLE gruvax.record_stats ALTER COLUMN profile_id SET NOT NULL",
    "ALTER TABLE gruvax.segment_overrides ALTER COLUMN profile_id SET NOT NULL",
    "ALTER TABLE gruvax.settings ALTER COLUMN profile_id SET NOT NULL",
)
```

Source: [Alembic ops.html — op.alter_column](https://alembic.sqlalchemy.org/en/latest/ops.html) [CITED] and [squawkhq.com — adding-not-nullable-field](https://squawkhq.com/docs/adding-not-nullable-field) [CITED]

### Pattern 4: BackgroundTasks + 202 + poll

**What:** Convert blocking sync endpoint to async background task.
**When to use:** `POST /api/admin/profiles/{id}/sync` (D2-13).

```python
# src/gruvax/api/admin/profile_sync.py (revised)
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

@router.post("/profiles/{profile_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    profile_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    _admin: dict = Depends(require_admin),
) -> JSONResponse:
    # 1. validate UUID
    # 2. pre-flight 404 check (tight pool checkout, released before add_task)
    # 3. set last_sync_status = 'in_progress' synchronously
    # 4. kick background task
    background_tasks.add_task(
        _run_sync_background,
        profile_id=str(uid),
        app_state=request.app.state,
    )
    return JSONResponse(
        status_code=202,
        content={"status": "accepted", "profile_id": str(uid)},
    )


async def _run_sync_background(profile_id: str, app_state: Any) -> None:
    """Background task wrapper — catches all exceptions, updates DB status."""
    try:
        await sync_profile(profile_id, app_state)
        # sync_profile internally: commits swap → reloads per-profile registry entries
        # → publishes collection_changed on the per-profile bus (D2-13 / Pitfall A)
    except Exception as exc:
        # Background tasks do NOT propagate exceptions to the HTTP response.
        # Exception handlers registered on the app do NOT fire for background tasks
        # (FastAPI issue #3589). Catch + log here.
        logger.exception(
            "background sync failed for profile=%s: %s", profile_id, exc
        )
        # Status is already 'failed' via _record_failure in sync_profile's except chain.
```

Source: [FastAPI BackgroundTasks docs](https://fastapi.tiangolo.com/tutorial/background-tasks/) [CITED], [FastAPI issue #3589 — background task exception handlers](https://github.com/fastapi/fastapi/issues/3589) [CITED]

### Pattern 5: Browse-binding cookie (D2-10)

**What:** `gruvax_browse_binding` cookie set by `GET /api/session`, independent of admin session.
**Cookie attributes for home LAN / HTTP (gruvax.lan):**
- `httponly=False` — the SPA must read `bound_profile_id` to route correctly (or expose via JSON endpoint)
- `samesite="strict"` — all traffic is same-site (`gruvax.lan`) so `Strict` is safe and prevents CSRF [CITED: risk #6 in spec]
- `secure=False` — LAN HTTP only; set `True` when TLS is added
- `max_age=None` (session cookie) or a long TTL (e.g. 7 days) — for kiosk convenience. Planner decides; session cookie is simpler, long TTL is kiosk-friendly
- Name: `gruvax_browse_binding` (avoid `gruvax_profile` — too close to admin session cookie names)

**iOS Safari note:** Safari `SameSite=Strict` is well-supported for same-site traffic.
The known WebKit bugs affect cross-site `SameSite=None` cookies (not applicable here —
all GRUVAX traffic is to `gruvax.lan`). [MEDIUM confidence: based on WebKit bug tracker
research; same-site same-domain cookies are consistently honored] [CITED: WebKit bug
#198181 — affects None/invalid, not Strict on same-site]

**Single-profile auto-bind:** On `GET /api/session`, if `profile_count == 1` and no
binding cookie is present, the server queries the one active profile, writes the
binding cookie in the response, and returns `{profile_count: 1, bound_profile_id: uuid}`.
The SPA routes directly to `/` without ever visiting `/select`.

### Pattern 6: React Router 7 SPA bootstrap

**What:** App.tsx reads `GET /api/session` on mount and routes accordingly.
**When to use:** KioskView mount and after unbind (Switch profile).

```tsx
// App.tsx addition (declarative mode — no loaders needed)
// useEffect on mount → fetch /api/session → set Zustand state → navigate
function App() {
  const navigate = useNavigate()
  const setSession = useSessionStore((s) => s.setSession)

  useEffect(() => {
    fetch('/api/session')
      .then(r => r.json())
      .then((data: SessionData) => {
        setSession(data)
        if (data.profile_count === 0) {
          navigate('/select', { replace: true })
        } else if (!data.bound_profile_id) {
          navigate('/select', { replace: true })
        }
        // if bound_profile_id set: stay at '/'
      })
  }, [])
  // ...
}
```

Source: [React Router useNavigate docs](https://reactrouter.com/api/hooks/useNavigate) [CITED]

**Important:** React Router 7 in declarative/SPA mode does NOT support `loader` functions
at the route level without the data router mode. The bootstrap fetch must be a `useEffect`
in `App.tsx` or a top-level wrapper component. [CITED: reactrouter.com/start/modes]

### Anti-Patterns to Avoid

- **`op.alter_column(nullable=False)` via Alembic's reflection path on tables with compound PKs:** Alembic's `alter_column` reflects existing constraints and may misidentify or duplicate FK constraints during the reflection round-trip on PostgreSQL when the table has composite PKs involving the new column. Use raw `op.execute("ALTER TABLE ... ALTER COLUMN ... SET NOT NULL")` — identical behavior, no reflection surprises. [MEDIUM confidence]
- **Publishing SSE before cache reload:** The Pitfall A ordering (publish AFTER commit AND AFTER cache.load) must be preserved in the background task. `sync_profile` already handles this; the background wrapper must not call `bus.publish` before `sync_profile` returns.
- **Holding a pool slot during background sync:** The existing Pitfall 6 pattern (tight pool checkout for 404 preflight, released before `add_task`) must be preserved. BackgroundTasks fires AFTER the response is sent, so the pool slot from the request is already returned — but the explicit `async with pool.connection()` guard must still close before `add_task`.
- **Sharing admin PIN session cookie with browse-binding:** D2-10 is explicit — two independent cookies. Do not extend `gruvax_session` to carry `bound_profile_id`; keep them separate so a profile unbind does not terminate an admin session.
- **Trusting client-provided `profile_id` without session validation:** Every per-profile endpoint derives the authorized `profile_id` from the session cookie and validates the path param against it (D2-04). Never use the path param as the authoritative source.
- **Using `app.state.event_bus` (singular) after P2:** P1's single `event_bus` must be replaced by the `event_bus_registry` dict. Keep backward-compatible fallback during the migration plan's transition wave.

---

## Critical Migration Discovery

**The 7 actual tables in migration 0009 differ from the tables named in CONTEXT.md/ROADMAP.md.**

The spec/ROADMAP lists: `cube_boundaries, segments, change_log, change_sets, settings, record_stats, ambient_baseline`

Migration 0009 (the code that actually shipped) added `profile_id` to:
`admin_sessions, boundary_history, cube_boundaries, idempotency_keys, record_stats, segment_overrides, settings`

This is documented in migration 0009's comment (lines 164–167):
> "The actual v1 user-data tables in the gruvax schema are... `admin_sessions`, `boundary_history`, `cube_boundaries`, `idempotency_keys`, `record_stats`, `segment_overrides`, `settings` (plus `units` — excluded)."

**P2 migration 0010 must work on the 7 actual tables, not the spec's list.** [VERIFIED: codebase read of `migrations/versions/0009_v2_profiles_and_collection_cache.py`]

### Per-table NOT NULL + composite uniqueness analysis

| Table | Existing PK | Existing `profile_id` | P2 Change Required |
|-------|-------------|----------------------|-------------------|
| `admin_sessions` | `id UUID PRIMARY KEY` | FK only | SET NOT NULL only |
| `boundary_history` | `id BIGSERIAL PRIMARY KEY` | FK only | SET NOT NULL only |
| `cube_boundaries` | `(unit_id, row, col)` | FK, to be included in PK | Drop old PK + new PK `(profile_id, unit_id, row, col)` + SET NOT NULL |
| `idempotency_keys` | `id/key TEXT PRIMARY KEY` | FK only | SET NOT NULL only |
| `record_stats` | `release_id BIGINT PRIMARY KEY` | FK, to be included in PK | Drop old PK + new PK `(profile_id, release_id)` + SET NOT NULL |
| `segment_overrides` | `(unit_id, row, col, label)` | FK, to be included in PK | Drop old PK + new PK `(profile_id, unit_id, row, col, label)` + SET NOT NULL |
| `settings` | `key TEXT PRIMARY KEY` | FK, to be included in PK | Drop old PK + new PK `(profile_id, key)` + SET NOT NULL |

**Downgrade for 0010** must reverse PK changes (re-create old PK after dropping new, drop NOT NULL via `ALTER COLUMN profile_id DROP NOT NULL`). Because the P1 backfill seeded all rows to the default profile, downgrade produces a valid nullable-column state identical to what 0009 left.

**Round-trip gate:** `just migrate-roundtrip` (alembic upgrade → downgrade base → upgrade) must pass. Note: `downgrade base` reverts all the way to 0001; the legacy seed at `tests/fixtures/legacy/synth_collection.sql` must be present before the roundtrip (the CI `test_migrate_0009.py` documents this dependency). [VERIFIED: codebase read of test_migrate_0009.py]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Background task status tracking | Custom in-memory task registry with IDs | Read `profiles.last_sync_status` from the DB | The profile row already carries `last_sync_status ∈ {ok, failed, in_progress}`; polling `GET /api/admin/profiles/{id}` is the status endpoint (D2-13). |
| Fan-out SSE to multiple browser tabs of the same profile | Custom session tracking + selective fan-out | One `EventBus` per profile; all tabs on the same profile subscribe to the same bus | The existing `EventBus.subscribe()` fan-out already handles multiple simultaneous queue subscribers (one per SSE connection). |
| Composite PK migration logic | Loop + reflection-based ALTER | Static raw SQL strings per table (project convention from 0009) | Avoids the Alembic reflection path's FK confusion; matches project's existing no-formatted-SQL convention. |
| Browse-binding session storage | JWT cookie or server-side session table | Plain signed cookie (`itsdangerous.URLSafeSerializer`) — same signing as admin session | No table needed; the binding is trivially simple (one UUID). Admin session uses itsdangerous already. |
| Profile-list count query in drawer | Separate `COUNT(*)` endpoint | `last_sync_item_count` from `profiles` row | Already maintained by `sync_profile`; no extra DB hit needed for the confirmation modal. |

**Key insight:** The polling status pattern (D2-13) eliminates the need for any new realtime infrastructure — `last_sync_status` IS the status endpoint, accessed via the existing `GET /api/admin/profiles/{id}`.

---

## Common Pitfalls

### Pitfall 1: PK constraint names not known without reflection
**What goes wrong:** `ALTER TABLE ... DROP CONSTRAINT cube_boundaries_pkey` — if the
actual constraint name in the DB differs from what the migration hardcodes, it fails.
**Why it happens:** Alembic autogenerate uses naming conventions; direct `CREATE TABLE`
SQL may produce names Postgres auto-assigns (e.g. `cube_boundaries_pkey` is Postgres
default for PK on table `cube_boundaries`).
**How to avoid:** The existing migrations use raw `CREATE TABLE` DDL, so Postgres
assigns the standard name `{tablename}_pkey`. Use `{tablename}_pkey` as the constraint
name in the DROP statements. Verify against a fresh `alembic upgrade head` if uncertain.
**Warning signs:** Migration fails with `constraint "xyz" does not exist`.

### Pitfall 2: registry key type mismatch (str vs uuid.UUID)
**What goes wrong:** `app.state.boundary_cache_registry[uuid.UUID("00000000-...")]`
raises `KeyError` when the registry was keyed with `str`.
**Why it happens:** Python's dict does not coerce `uuid.UUID` to `str`.
**How to avoid:** Store and look up with `str(profile_id)` everywhere. The existing
`DEFAULT_PROFILE_UUID` constant is a string; follow the same pattern.
**Warning signs:** 503 on a profile that exists in the registry — with `KeyError` in logs.

### Pitfall 3: background task exception swallowed by FastAPI
**What goes wrong:** `sync_profile` raises `PATRejected` inside a `BackgroundTasks`
task; the exception is not visible in the response and may not appear in logs.
**Why it happens:** FastAPI exception handlers registered on the app do NOT fire for
background tasks (confirmed: fastapi/fastapi#3589, fastapi/fastapi#2505).
**How to avoid:** The `_run_sync_background` wrapper must catch all exceptions directly
and call `logger.exception(...)`. Do not rely on the app-level `@app.exception_handler`
for background task errors.
**Warning signs:** Sync silently never completes; `last_sync_status` stays `'in_progress'`
indefinitely (or reverts to previous state) with no log entry.

### Pitfall 4: Pitfall A violation — publish before cache reload in background task
**What goes wrong:** `collection_changed` SSE event fires before the per-profile
`CollectionSnapshot` is reloaded; kiosk fetches stale data.
**Why it happens:** The background task restructures `sync_profile`'s post-swap logic;
if the SSE publish is extracted to the wrong place, it fires before `snapshot.load()`.
**How to avoid:** The post-swap section in `sync_profile` already follows Pitfall A
(commit → cache.load → bus.publish). P2's change is to switch from inline cache
refresh to per-profile registry entry reload, then publish. Order: `cache.invalidate()
→ cache.load(pool, profile_id=...) → bus.publish(...)`.
**Warning signs:** Kiosk search returns stale results immediately after sync, then
updates on SSE reconnect.

### Pitfall 5: `admin_sessions` profile_id FK semantics
**What goes wrong:** Making `admin_sessions.profile_id NOT NULL` means every admin
session must reference a valid profile. But admin sessions exist BEFORE any profile
connection (the admin logs in to create the first profile).
**Why it happens:** The backfill in 0009 set all admin_sessions rows to the default
profile UUID. NOT NULL is technically safe. BUT if the admin session creation code
doesn't set `profile_id`, new sessions will fail.
**How to avoid:** `admin_sessions.profile_id` semantics differ from the other tables —
it's a "which profile was active during this session" field, not an ownership FK.
Decide: (a) keep NOT NULL, update `create_session()` to always set `profile_id` from
the context; or (b) leave admin_sessions `profile_id` nullable in 0010 (it's a
monitoring field, not a routing FK). Option (b) is safer — admin sessions are not
per-profile-isolated.
**Warning signs:** Login fails with FK violation on INSERT into `admin_sessions`.

**Research recommendation:** Leave `admin_sessions.profile_id` nullable in 0010.
The field is useful as metadata ("admin was managing profile X at time T") but not
structurally required for P2 routing. The 6 remaining tables cover all the per-profile
data isolation needs. [ASSUMED: open for planner to override]

### Pitfall 6: `idempotency_keys.profile_id` semantics
**What goes wrong:** `idempotency_keys` deduplicates bulk-write requests per 24h TTL.
Its key is the request dedup token, not a per-profile datum. Making `profile_id NOT NULL`
means every bulk-write must pass `profile_id` in the dedup context.
**Why it happens:** `idempotency_keys` is an infrastructure/dedup table, not a
per-profile data table. Its FK to profiles is loose.
**How to avoid:** Similar to Pitfall 5 — consider keeping `idempotency_keys.profile_id`
nullable in 0010, or ensure the bulk-write endpoint (Phase 3 admin) sets `profile_id`
on every new key row. [ASSUMED: planner resolves]

### Pitfall 7: lifespan startup with no profiles (fresh deploy)
**What goes wrong:** `SELECT id FROM gruvax.profiles WHERE deleted_at IS NULL` returns
zero rows on a fresh DB (default profile not yet synced). Registry is empty. First
search fails with 404.
**Why it happens:** The default profile row IS seeded by migration 0009, but it has
`app_token_revoked = TRUE`. The registry should include it (empty caches are valid).
**How to avoid:** Eager-load ALL non-deleted profiles regardless of `app_token_revoked`
status. An empty `BoundaryCache` / `CollectionSnapshot` is the correct state for a
profile with no PAT/sync yet (the "no records yet" affordance handles this in the UI).
**Warning signs:** 503 on first request; empty `boundary_cache_registry` despite profile
row existing.

---

## Runtime State Inventory

Phase 2 is not a rename/refactor phase, so a full runtime state inventory is not
applicable. However, the registry migration in `app.py` must handle in-flight connections:

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | `profiles` table: 1 default row (already backfilled). 7 v1 tables: `profile_id` nullable, all rows point to default UUID. | Migration 0010: SET NOT NULL + PK changes. |
| Live service config | Single `event_bus` on `app.state` consumed by existing SSE test (`test_sse.py`). | Plan must include a backward-compatibility step: keep `app.state.event_bus` as an alias or update `test_sse.py` to use registry. |
| OS-registered state | None — no OS-level registrations reference profile_id. | None. |
| Secrets/env vars | `GRUVAX_SECRET_KEY` (Fernet key) — already in use. No new secrets in P2. | None. |
| Build artifacts | None relevant to P2. | None. |

---

## Code Examples

### Verified: existing `_refresh_default_profile_state` — generalize to all profiles

```python
# app.py — replace single-profile task with per-profile task
# Source: src/gruvax/app.py lines 241-275 (verified by codebase read)

async def _refresh_all_profiles_state() -> None:
    while True:
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, last_sync_at, last_sync_status, app_token_revoked "
                    "FROM gruvax.profiles "
                    "WHERE deleted_at IS NULL"
                )
                rows = await cur.fetchall()
            # update app.state.profile_state_registry (dict[str, dict]) per profile
            for (pid, last_sync_at, last_sync_status, revoked) in rows:
                app.state.profile_state_registry[str(pid)] = {
                    "last_sync_at": last_sync_at,
                    "last_sync_status": last_sync_status,
                    "app_token_revoked": bool(revoked),
                }
        except Exception as exc:
            logger.warning("all-profiles state refresh failed: %s", exc)
        await asyncio.sleep(60)
```

### Verified: existing `EventBus.subscribe()` pattern for per-profile SSE

```python
# Existing events.py pattern (verified by codebase read of src/gruvax/api/events.py)
# P2 extends it with profile_id in path + session validation

@router.get("/events/{profile_id}")
async def stream_events(
    profile_id: str,
    request: Request,
    bus: EventBus = Depends(get_bus_for_profile),  # new dep — resolves registry
) -> EventSourceResponse:
    async def generator() -> AsyncIterator[ServerSentEvent]:
        q = bus.subscribe()
        try:
            yield ServerSentEvent(comment="connected")
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=1.0)
                    yield ServerSentEvent(event=event.name, data=json.dumps(event.data))
                except TimeoutError:
                    continue
        finally:
            bus.unsubscribe(q)
    return EventSourceResponse(
        generator(), ping=15,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )
```

### Verified: TanStack Query 2s polling pattern for sync status

```tsx
// frontend — poll GET /api/admin/profiles/{id} at 2s cadence
// Source: TanStack Query v5 refetchInterval pattern [CITED: tanstack.com/query/v5]
const { data: profile } = useQuery({
  queryKey: ['profile', profileId],
  queryFn: () => fetch(`/api/admin/profiles/${profileId}`).then(r => r.json()),
  refetchInterval: (query) =>
    query.state.data?.last_sync_status === 'in_progress' ? 2000 : false,
})
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|-----------------|--------------|--------|
| Single `app.state.event_bus` | `dict[UUID, EventBus]` registry per profile | P2 | Cross-profile SSE leakage impossible by construction |
| Single `app.state.boundary_cache` | `dict[UUID, BoundaryCache]` registry | P2 | Per-profile cache isolation |
| Blocking `sync_profile` in HTTP request | `BackgroundTasks.add_task` + 202 + poll | P2 | Request does not block; client polls status |
| Single-profile staleness `_refresh_default_profile_state` | Per-profile registry refresh | P2 | Health/banner accurate per-profile |
| `DEFAULT_PROFILE_UUID` hardcoded in `queries.py` call sites | `profile_id` from session cookie at all call sites | P2 | Multi-profile isolation by construction |

**Deprecated/outdated in P2:**
- `app.state.boundary_cache` (singular): replaced by `app.state.boundary_cache_registry`
- `app.state.collection_snapshot` (singular): replaced by `app.state.snapshot_registry`
- `app.state.segment_cache` (singular): replaced by `app.state.segment_cache_registry`
- `app.state.event_bus` (singular): replaced by `app.state.event_bus_registry`
- `app.state.settings_cache` (singular): replaced by `app.state.settings_cache_registry`
- `app.state.default_profile_*` trio: replaced by `app.state.profile_state_registry`

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PK constraint names follow Postgres default pattern `{tablename}_pkey` for tables created with raw DDL in migrations 0001–0005 | Pattern 3 / Migration | Migration fails at PK drop step; must look up actual names via `\d tablename` |
| A2 | `admin_sessions.profile_id` and `idempotency_keys.profile_id` should remain nullable in 0010 | Critical Migration Discovery / Pitfall 5+6 | If made NOT NULL, admin login and bulk-write will fail unless call sites are updated simultaneously |
| A3 | Browse-binding cookie name is `gruvax_browse_binding` | Pattern 5 | Cookie name is aesthetic; planner can pick any non-colliding name |
| A4 | Profiles state registry key is `str` (UUID string) | Pattern 1 | KeyError on lookup if mixed types used |
| A5 | `itsdangerous.URLSafeSerializer` (already imported in sessions.py) is sufficient for signing the browse-binding cookie value | Pattern 5 | If unsigned, session binding is spoofable — but on home LAN the risk is minimal |
| A6 | React Router 7 declarative mode is already what App.tsx uses (BrowserRouter + Routes) | Pattern 6 | If data router mode is actually in use, `loader` functions should be used instead of `useEffect` |
| A7 | `segment_overrides` PK was created as `PRIMARY KEY (unit_id, row, col, label)` in migration 0005 | Critical Migration Discovery | If actual PK name or columns differ, PK drop will fail |

---

## Open Questions (RESOLVED)

1. **`admin_sessions.profile_id` + `idempotency_keys.profile_id` — nullable or NOT NULL?**
   - What we know: these tables have their own PKs; `profile_id` is a loose FK reference
   - What's unclear: does any P2 code path REQUIRE `profile_id NOT NULL` on these tables?
   - Recommendation: leave nullable in 0010; plan can tighten in a later phase if needed
   - **RESOLVED (2026-05-28, Plan 02-01):** stay nullable — owner decision this session (5 per-profile data tables go NOT NULL; `admin_sessions` + `idempotency_keys` are global/infra and keep nullable `profile_id`).

2. **Browse-binding cookie: session (expires on browser close) or persistent (e.g. 7-day)?**
   - What we know: kiosk Chromium reopens and re-hits the server; session cookies may not survive kiosk restart
   - What's unclear: does the kiosk Chromium retain session cookies across a kiosk restart?
   - Recommendation: use persistent 7-day `max_age`; kiosk gets auto-bound without hitting `/select` on each restart. Mobile browser users can still unbind via the switch-profile flow.
   - **RESOLVED (2026-05-28, Plan 02-04):** persistent 7-day `max_age`, HttpOnly, SameSite=Lax, independent of the admin PIN session (D2-10).

3. **Backward compatibility for `app.state.event_bus` (singular) during the wave where it's replaced**
   - What we know: `test_sse.py` uses the live server and references `GET /api/events` (not `/{profile_id}`)
   - What's unclear: does the P2 wave introducing the registry need a migration shim, or does the test suite update happen in the same plan?
   - Recommendation: update `test_sse.py` in the same plan that introduces the registry; do not maintain a shim.
   - **RESOLVED (2026-05-28, Plan 02-03):** no shim — `test_sse.py` is updated to `/api/events/{profile_id}` in the same plan that introduces the per-profile bus registry.

4. **`settings` seeded rows and composite PK migration**
   - What we know: migration 0004 seeds 3 rows into `gruvax.settings` (cube.nominal_capacity, session.idle_ttl_seconds, session.hard_cap_seconds) with the default profile_id backfilled by 0009
   - What's unclear: after P2 changes the PK to `(profile_id, key)`, will the seed rows need to be duplicated for each new profile?
   - Recommendation: yes — when a new profile is created via the admin API, seed it with the same default settings values. The profile-creation endpoint must INSERT seed rows into `settings` for the new profile_id.
   - **RESOLVED (2026-05-28, Plan 02-05):** profile-creation endpoint seeds the 3 default `settings` rows for the new `profile_id`.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | Backend | ✓ | 3.14.5 | — (note: project targets 3.13 per CLAUDE.md) |
| Node.js | Frontend build | ✓ | 26.0.0 | — |
| just | Task runner | ✓ | 1.51.0 | `uv run pytest ...` directly |
| PostgreSQL | Tests + migrations | Requires live DB | — | Use CI Postgres 18 service |
| `uv` | Package management | [ASSUMED: installed per project conventions] | — | `pip` |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 1.3.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (`asyncio_mode = "auto"`) |
| Quick run command | `just test-unit` |
| Full suite command | `just test` |
| SLO benchmark command | `just slo` |
| Migration round-trip command | `just migrate-roundtrip` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROF-04 | NOT NULL migration backfills v1 data to default profile + round-trip clean | integration/alembic | `just migrate-roundtrip` + `pytest tests/integration/test_migrate_0010.py` | ❌ Wave 0 |
| PROF-04 | composite PKs correct on 4 tables after upgrade | integration | `pytest tests/integration/test_migrate_0010.py::test_composite_pks` | ❌ Wave 0 |
| API-02 | search/locate SLOs hold with 2+ profiles in registry | benchmark | `just slo` (parameterized over profile_id) | Partial (slo target exists, needs profile_id param) |
| API-02 | per-profile cache registry returns isolated results | unit | `pytest tests/unit/test_cache_registry.py` | ❌ Wave 0 |
| SYN-02 | per-profile staleness background task updates all profiles | unit | `pytest tests/unit/test_profile_state_registry.py` | ❌ Wave 0 |
| PROF-02 | connect-PAT → 202 sync + poll returns ok | integration | `pytest tests/integration/test_profile_manager_api.py::test_connect_pat_flow` | ❌ Wave 0 |
| PROF-02 | POST /api/admin/profiles/id/sync → 202 immediately; poll → in_progress → ok | integration | `pytest tests/integration/test_profile_manager_api.py::test_sync_202_poll` | ❌ Wave 0 |
| PROF-02 | duplicate discogsography_user_id → 409 on connect | integration | `pytest tests/integration/test_profile_manager_api.py::test_user_id_collision` | ❌ Wave 0 |
| PROF-02 | soft-delete → profile absent from registry + picker | integration | `pytest tests/integration/test_profile_manager_api.py::test_soft_delete_evicts` | ❌ Wave 0 |
| D2-04 | per-profile SSE 403 on profile mismatch / 400 on unbound | integration (live server) | `pytest tests/integration/test_sse_per_profile.py` | ❌ Wave 0 |
| D2-04 | collection_changed only reaches affected profile's clients | integration (live server) | `pytest tests/integration/test_sse_per_profile.py::test_no_cross_profile_leakage` | ❌ Wave 0 |
| D2-08 | GET /api/session auto-binds single profile | integration | `pytest tests/integration/test_session_bootstrap.py` | ❌ Wave 0 |
| D2-10 | browse-binding cookie independent of admin session | integration | `pytest tests/integration/test_session_bootstrap.py::test_binding_independent_of_admin` | ❌ Wave 0 |
| SC-5 | p95 /api/search ≤ 200ms w/ 2 profiles | benchmark | `just slo` (parameterized) | Partial |
| SC-5 | p95 /api/locate ≤ 50ms w/ 2 profiles | benchmark | `just slo` (parameterized) | Partial |

### Sampling Rate
- **Per task commit:** `just test-unit`
- **Per wave merge:** `just test`
- **Phase gate:** `just test` + `just slo` + `just migrate-roundtrip` green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/integration/test_migrate_0010.py` — covers PROF-04 round-trip + PK shape
- [ ] `tests/unit/test_cache_registry.py` — covers API-02 registry isolation
- [ ] `tests/unit/test_profile_state_registry.py` — covers SYN-02 per-profile staleness
- [ ] `tests/integration/test_profile_manager_api.py` — covers PROF-02 CRUD + 202+poll
- [ ] `tests/integration/test_sse_per_profile.py` — covers D2-04 per-profile SSE + no-leakage
- [ ] `tests/integration/test_session_bootstrap.py` — covers D2-08 auto-bind + D2-10 independence
- [ ] Update `tests/integration/test_sse.py` — replace `GET /api/events` with `GET /api/events/{profile_id}`
- [ ] Update `tests/integration/test_search_benchmark.py` — parameterize over profile_id (add second profile fixture)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes — browse-binding (no-PIN) + admin PIN (existing) | Starlette `SessionMiddleware`; no new auth library |
| V3 Session Management | yes — `bound_profile_id` cookie TTL + same-site | `itsdangerous` signing; `samesite=strict` |
| V4 Access Control | yes — profile isolation per endpoint | Session-derived `profile_id`; 403 on mismatch (D2-04) |
| V5 Input Validation | yes — `profile_id` path param must be UUID | `uuid.UUID(profile_id)` parse; 400 on failure |
| V6 Cryptography | carried from P1 — Fernet PAT encryption | `cryptography.fernet`; `GRUVAX_SECRET_KEY` at boot |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Profile ID spoofing via path param | Spoofing | Server derives `profile_id` from session cookie; path param only validated, never authoritative (D2-04) |
| Stale binding cookie after soft-delete | Elevation | Evict from registry on soft-delete; dep returns 404 when registry entry absent for deleted profile |
| Admin session confused with browse-binding | Spoofing | Two independent cookies with different names; `require_admin` does not read `gruvax_browse_binding` |
| Background sync exception swallowed | Tampering | `_run_sync_background` wrapper catches + logs all exceptions; status updated to `'failed'` |
| Cross-profile SSE event delivery | Information Disclosure | Per-profile `EventBus` registry; SSE endpoint validates session cookie before resolving bus |

---

## Sources

### Primary (HIGH confidence)

- [Alembic 1.18.4 ops.html — op.alter_column](https://alembic.sqlalchemy.org/en/latest/ops.html) — nullable parameter, raw SQL vs reflection path
- [FastAPI BackgroundTasks docs](https://fastapi.tiangolo.com/tutorial/background-tasks/) — add_task API, 202 pattern
- Codebase reads: `src/gruvax/app.py`, `migrations/versions/0009_v2_profiles_and_collection_cache.py`, `src/gruvax/api/admin/profile_sync.py`, `src/gruvax/sync/profile_sync.py`, `src/gruvax/api/events.py`, `src/gruvax/api/deps.py`, `src/gruvax/auth/sessions.py`, `tests/integration/test_sse.py`, `tests/integration/test_migrate_0009.py`, `frontend/src/App.tsx`, all v1 migration files

### Secondary (MEDIUM confidence)

- [squawkhq.com — adding-not-nullable-field](https://squawkhq.com/docs/adding-not-nullable-field) — staged NOT NULL constraint pattern; PG 12+ optimization
- [FastAPI issues #3589](https://github.com/fastapi/fastapi/issues/3589) and [#2505](https://github.com/fastapi/fastapi/issues/2505) — background task exception swallowing
- [WebKit bug #198181](https://bugs.webkit.org/show_bug.cgi?id=198181) — SameSite cookie iOS Safari (affects None/invalid, not Strict on same-site)
- [React Router useNavigate](https://reactrouter.com/api/hooks/useNavigate) and [picking a mode](https://reactrouter.com/start/modes) — SPA declarative mode vs data router

### Tertiary (LOW confidence)

- WebSearch results on PostgreSQL lock-minimizing NOT NULL patterns (GoCardless blog, Handshake blog) — relevant for production; GRUVAX is household scale with no zero-downtime requirement; not a concern here

---

## Metadata

**Confidence breakdown:**
- Schema migration (0010 NOT NULL + PK changes): HIGH — codebase verified which 7 tables exist and their PKs; migration pattern from official Alembic docs
- Per-profile registry pattern: HIGH — code shape mirrors existing P1 single-instance pattern; no new libraries
- BackgroundTasks + 202 + poll: HIGH — official FastAPI docs; existing endpoint structure read
- Browse-binding cookie attributes: MEDIUM — Safari same-site behavior confirmed from WebKit tracker; LAN HTTP specifics assumed
- React Router 7 SPA bootstrap: MEDIUM — declarative mode confirmed from App.tsx; loader vs useEffect tradeoff documented from official docs

**Research date:** 2026-05-28
**Valid until:** 2026-06-28 (stable library ecosystem; main uncertainty is Alembic PK constraint exact names)

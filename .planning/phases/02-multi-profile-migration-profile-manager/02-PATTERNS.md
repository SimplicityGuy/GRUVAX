# Phase 2: Multi-profile migration + profile manager — Pattern Map

**Mapped:** 2026-05-28
**Files analyzed:** 18 new/modified files
**Analogs found:** 17 / 18 (1 partial — `api/session.py` new endpoint with no direct analog)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `migrations/versions/0010_profile_id_not_null.py` | migration | batch/DDL | `migrations/versions/0009_v2_profiles_and_collection_cache.py` | exact |
| `src/gruvax/app.py` | config/lifespan | CRUD + event-driven | `src/gruvax/app.py` (self — modify) | self |
| `src/gruvax/api/deps.py` | middleware/utility | request-response | `src/gruvax/api/deps.py` (self — extend) | self |
| `src/gruvax/api/events.py` | controller | event-driven/SSE | `src/gruvax/api/events.py` (self — modify) | self |
| `src/gruvax/api/admin/profile_sync.py` | controller | request-response | `src/gruvax/api/admin/profile_sync.py` (self — modify) | self |
| `src/gruvax/api/admin/profiles.py` | controller | CRUD | `src/gruvax/api/admin/profile_sync.py` | role-match |
| `src/gruvax/api/session.py` | controller | request-response | `src/gruvax/auth/sessions.py` + `src/gruvax/api/deps.py` | partial |
| `src/gruvax/auth/sessions.py` | utility | request-response | `src/gruvax/auth/sessions.py` (self — extend) | self |
| `src/gruvax/sync/profile_sync.py` | service | batch/CRUD | `src/gruvax/sync/profile_sync.py` (self — modify) | self |
| `src/gruvax/db/queries.py` | utility | CRUD | `src/gruvax/db/queries.py` (self — modify) | self |
| `src/gruvax/events/bus.py` | utility | event-driven | `src/gruvax/events/bus.py` (self — no change) | self |
| `frontend/src/App.tsx` | component | request-response | `frontend/src/App.tsx` (self — extend) | self |
| `frontend/src/api/session.ts` | utility | request-response | `frontend/src/routes/admin/` + `App.tsx` | role-match |
| `frontend/src/routes/ProfilePicker.tsx` | component | request-response | `frontend/src/routes/admin/RecordPickerSheet.tsx` | role-match |
| `frontend/src/routes/kiosk/SwitchProfileButton.tsx` | component | event-driven | `frontend/src/routes/admin/AdminShell.tsx` (nav buttons) | role-match |
| `frontend/src/routes/admin/ProfilesManager.tsx` | component | CRUD | `frontend/src/routes/admin/CubesGrid.tsx` | role-match |
| `frontend/src/routes/admin/ProfileDrawer.tsx` | component | CRUD | `frontend/src/routes/admin/RecordPickerSheet.tsx` | exact |
| `frontend/src/routes/admin/AdminShell.tsx` | component | request-response | `frontend/src/routes/admin/AdminShell.tsx` (self — extend) | self |

---

## Pattern Assignments

### `migrations/versions/0010_profile_id_not_null.py` (migration, batch/DDL)

**Analog:** `migrations/versions/0009_v2_profiles_and_collection_cache.py`

**Module structure pattern** (0009 lines 1–68):
```python
"""One-line summary; multi-line docstring with reconciliation notes.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-28

... operational notes, round-trip gate reference, naming-convention note ...
"""

from __future__ import annotations
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | None = None
depends_on: str | None = None
```

**Module-level SQL constant pattern** (0009 lines 83–218):
```python
# ALL SQL is module-level string literals — never inside functions,
# never f-strings, never concatenation. bandit B608 is in skip list
# but the longhand approach removes the warning at source.

_VERIFY_NO_NULLS_CUBE_BOUNDARIES = (
    "DO $$ BEGIN "
    "  IF EXISTS (SELECT 1 FROM gruvax.cube_boundaries WHERE profile_id IS NULL) "
    "  THEN RAISE EXCEPTION 'NULL profile_id in cube_boundaries — 0009 backfill incomplete'; "
    "  END IF; "
    "END $$"
)

# PK reconstruction — four tables require composite PK change.
# Use Postgres default constraint names ({tablename}_pkey) — matches
# tables created by raw CREATE TABLE DDL in 0001–0008 migrations.
_DROP_PK_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT cube_boundaries_pkey"
)
_ADD_PK_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries ADD PRIMARY KEY (profile_id, unit_id, row, col)"
)

# Raw SQL form — NOT op.alter_column(nullable=False) — avoids Alembic's
# reflection path misidentifying FK constraints on composite-PK tables.
_SET_NOT_NULL_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries ALTER COLUMN profile_id SET NOT NULL"
)

# Downgrade: DROP NOT NULL + restore old PK shape
_DROP_NOT_NULL_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries ALTER COLUMN profile_id DROP NOT NULL"
)
_DROP_NEW_PK_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries DROP CONSTRAINT cube_boundaries_pkey"
)
_RESTORE_OLD_PK_CUBE_BOUNDARIES = (
    "ALTER TABLE gruvax.cube_boundaries ADD PRIMARY KEY (unit_id, row, col)"
)
```

**upgrade() / downgrade() pattern** (0009 lines 255–319):
```python
def upgrade() -> None:
    # Verify no NULLs remain from 0009 backfill (fail fast — don't proceed if broken)
    op.execute(_VERIFY_NO_NULLS_CUBE_BOUNDARIES)
    # ... verify all 5 per-profile-data tables

    # PK reconstruction for the 4 composite-PK tables
    op.execute(_DROP_PK_CUBE_BOUNDARIES)
    op.execute(_ADD_PK_CUBE_BOUNDARIES)
    # ... repeat for settings, record_stats, segment_overrides

    # SET NOT NULL for the 5 per-profile-data tables
    # (admin_sessions + idempotency_keys stay nullable per Pitfall 5/6)
    op.execute(_SET_NOT_NULL_CUBE_BOUNDARIES)
    # ... repeat for settings, record_stats, segment_overrides, boundary_history


def downgrade() -> None:
    # Reverse order: DROP NOT NULL first, then restore old PKs
    op.execute(_DROP_NOT_NULL_CUBE_BOUNDARIES)
    # ... repeat for all 5 tables

    # Restore old PKs for the 4 composite-PK tables
    op.execute(_DROP_NEW_PK_CUBE_BOUNDARIES)
    op.execute(_RESTORE_OLD_PK_CUBE_BOUNDARIES)
    # ... repeat for settings, record_stats, segment_overrides
```

**NOT NULL scope (5 tables — NOT all 7):** `cube_boundaries`, `settings`, `record_stats`, `segment_overrides`, `boundary_history`. Leave `admin_sessions` and `idempotency_keys` nullable (Pitfall 5/6 in RESEARCH.md).

---

### `src/gruvax/app.py` — lifespan modification (config/lifespan, CRUD + event-driven)

**Analog:** self (modify lines 159–276)

**Single-instance → registry pattern** (lines 159–211, replace):
```python
# P2 replaces ALL five single-instance attributes with registry dicts:
#   app.state.boundary_cache       → app.state.boundary_cache_registry
#   app.state.collection_snapshot  → app.state.snapshot_registry
#   app.state.segment_cache        → app.state.segment_cache_registry
#   app.state.settings_cache       → app.state.settings_cache_registry
#   app.state.event_bus            → app.state.event_bus_registry

# Eager startup pattern (D2-02): load ALL non-deleted profiles at boot.
# Registry key = str(profile_id) — plain string, NOT uuid.UUID (Pitfall 2).
app.state.boundary_cache_registry: dict[str, BoundaryCache] = {}
app.state.snapshot_registry: dict[str, CollectionSnapshot] = {}
app.state.segment_cache_registry: dict[str, SegmentCache] = {}
app.state.settings_cache_registry: dict[str, dict] = {}
app.state.event_bus_registry: dict[str, EventBus] = {}

async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(
        "SELECT id FROM gruvax.profiles WHERE deleted_at IS NULL"
    )
    profile_rows = await cur.fetchall()

for (pid,) in profile_rows:
    pid_str = str(pid)
    # Cache instances — same try/except + logger.error + proceed pattern
    # as the existing single-instance steps (lines 159-202).
    cache = BoundaryCache()
    try:
        await cache.load(pool, profile_id=pid_str)
    except Exception as exc:
        logger.error("BoundaryCache load failed for profile=%s: %s", pid_str, exc)
    app.state.boundary_cache_registry[pid_str] = cache
    # ... repeat for snapshot, segment_cache, settings_cache

    bus = EventBus()
    try:
        await bus.publish("server_hello", {"version": "0.1.0", "profile_id": pid_str})
    except Exception as exc:
        logger.error("EventBus server_hello failed for profile=%s: %s", pid_str, exc)
    app.state.event_bus_registry[pid_str] = bus
```

**Background task pattern** (lines 241–275, generalize):
```python
# P2: replace _refresh_default_profile_state with _refresh_all_profiles_state.
# Same asyncio.create_task + strong-reference (CR-01) + done-callback pattern.
app.state.profile_state_registry: dict[str, dict] = {}

async def _refresh_all_profiles_state() -> None:
    while True:
        try:
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id, last_sync_at, last_sync_status, app_token_revoked "
                    "FROM gruvax.profiles WHERE deleted_at IS NULL"
                )
                rows = await cur.fetchall()
            for (pid, last_sync_at, last_sync_status, revoked) in rows:
                app.state.profile_state_registry[str(pid)] = {
                    "last_sync_at": last_sync_at,
                    "last_sync_status": last_sync_status,
                    "app_token_revoked": bool(revoked),
                }
        except Exception as exc:
            logger.warning("all-profiles state refresh failed: %s", exc)
        await asyncio.sleep(60)

_state_task = asyncio.create_task(_refresh_all_profiles_state())
app.state.background_tasks.add(_state_task)          # CR-01 strong reference
_state_task.add_done_callback(app.state.background_tasks.discard)
```

**server_shutdown broadcast pattern** (lines 299–300, extend):
```python
# P2 teardown: broadcast shutdown across ALL per-profile buses.
for bus in app.state.event_bus_registry.values():
    with contextlib.suppress(Exception):
        await bus.publish("server_shutdown", {})
```

---

### `src/gruvax/api/deps.py` — extend with per-profile deps (middleware/utility, request-response)

**Analog:** `src/gruvax/api/deps.py` (self, extend)

**Existing dep pattern to copy exactly** (lines 48–66 for `get_boundary_cache`):
```python
def get_boundary_cache(request: Request) -> BoundaryCache:
    cache: BoundaryCache | None = getattr(request.app.state, "boundary_cache", None)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Boundary cache not ready",
        )
    return cache
```

**New per-profile dep pattern** — add for each cache type + bus:
```python
def get_boundary_cache_for_profile(
    profile_id: str,       # from path param — NOT trusted as authoritative
    request: Request,
) -> BoundaryCache:
    """Resolve boundary cache by session-validated profile_id (D2-04).

    Validates the path profile_id against the session cookie; never trusts
    the path param as authoritative. Raises 400 on unbound, 403 on mismatch,
    404 on missing registry entry, 503 on uninitialised registry.
    """
    bound = request.cookies.get("gruvax_browse_binding")
    if not bound:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "session_unbound"},
        )
    if bound != profile_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"type": "profile_mismatch"},
        )
    registry: dict[str, BoundaryCache] | None = getattr(
        request.app.state, "boundary_cache_registry", None
    )
    if registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache registry not ready",
        )
    cache = registry.get(profile_id)
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
    return cache

# Mirror the same pattern for get_bus_for_profile — resolves event_bus_registry.
# Mirror for get_snapshot_for_profile, get_segment_cache_for_profile too.
```

---

### `src/gruvax/api/events.py` — modify to per-profile SSE (controller, event-driven/SSE)

**Analog:** `src/gruvax/api/events.py` (self — modify)

**Full current SSE pattern** (lines 35–75) — copy structure, add profile_id:
```python
# BEFORE (P1): @router.get("/events")
# AFTER  (P2): @router.get("/events/{profile_id}")

@router.get("/events/{profile_id}")
async def stream_events(
    profile_id: str,
    request: Request,
    bus: EventBus = Depends(get_bus_for_profile),  # NEW dep — validates session cookie
    # NOTE: NO get_pool — Pitfall 10 preserved. get_bus_for_profile does the
    # 400/403 session validation itself; it only reads request.app.state.
) -> EventSourceResponse:
    # Generator body is UNCHANGED from P1 — same subscribe/yield/unsubscribe shape:
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
        generator(),
        ping=15,
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
    )
```

---

### `src/gruvax/api/admin/profile_sync.py` — convert to 202+poll (controller, request-response)

**Analog:** `src/gruvax/api/admin/profile_sync.py` (self — modify, lines 74–155)

**Current blocking pattern** (lines 74–155) — replace with BackgroundTasks:
```python
# IMPORT ADDITION at top of file:
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status

@router.post("/profiles/{profile_id}/sync", status_code=status.HTTP_202_ACCEPTED)
async def trigger_sync(
    profile_id: str,
    request: Request,
    background_tasks: BackgroundTasks,                   # ADD
    _admin: dict[str, Any] = Depends(require_admin),
    # Still NO pool injection — Pitfall 6 preserved.
) -> JSONResponse:
    # UUID parse (unchanged from lines 98-104)
    try:
        uid = uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
        ) from None

    # 404 pre-flight (unchanged from lines 107-117 — tight pool checkout)
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
            (str(uid),),
        )
        if await cur.fetchone() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"type": "profile_not_found"},
            )
    # Pool slot RETURNED here before add_task.

    # Set in_progress synchronously so poller sees it immediately
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET last_sync_status = 'in_progress', "
            "last_sync_error = NULL WHERE id = %s::uuid",
            (str(uid),),
        )
        await conn.commit()

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
    """Background task wrapper — catches ALL exceptions (Pitfall 3).

    FastAPI exception handlers do NOT fire for background tasks
    (fastapi/fastapi#3589). Must catch + log here directly.
    """
    try:
        await sync_profile(profile_id, app_state)
        # sync_profile handles: commit → per-profile cache reload → bus.publish
        # (Pitfall A ordering preserved inside sync_profile)
    except Exception as exc:
        logger.exception(
            "background sync failed for profile=%s: %s", profile_id, exc
        )
        # last_sync_status is already 'failed' via _record_failure inside
        # sync_profile's except chain — no double-write needed here.
```

---

### `src/gruvax/api/admin/profiles.py` — new profile CRUD endpoints (controller, CRUD)

**Analog:** `src/gruvax/api/admin/profile_sync.py` (role-match — same admin router, same auth pattern)

**Imports pattern** (from profile_sync.py lines 49–69):
```python
from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from gruvax.api.deps import require_admin
from gruvax.discogsography.errors import (
    NetworkError,
    PATRejected,
    RateLimitExhausted,
    ServerError,
)
```

**Auth pattern** (profile_sync.py lines 78–79):
```python
@router.post("/profiles")
async def create_profile(
    request: Request,
    body: CreateProfileRequest,
    _admin: dict[str, Any] = Depends(require_admin),
    # NO pool injection via Depends — reach into request.app.state.db_pool
    # directly so the slot is tight-checked and released before any long op.
) -> JSONResponse:
```

**UUID parse + 404 preflight pattern** (profile_sync.py lines 98–118):
```python
try:
    uid = uuid.UUID(profile_id)
except ValueError:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
    ) from None

db_pool = request.app.state.db_pool
async with db_pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(
        "SELECT 1 FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
        (str(uid),),
    )
    if await cur.fetchone() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"type": "profile_not_found"},
        )
# Pool slot released before any long-running operation.
```

**Error taxonomy pattern** (profile_sync.py lines 123–143):
```python
# PATRejected → 401 {"type": "pat_rejected"}
# discogsography_user_id collision → 409 {"type": "user_id_collision", "message": "..."}
# RateLimitExhausted → 503 {"type": "rate_limited_upstream"}
# ServerError / NetworkError → 503 {"type": "upstream_unavailable"}
```

**%s SQL pattern** (profile_sync.py + queries.py — every query):
```python
# Always %s placeholders, never f-strings or .format(). No exception.
await cur.execute(
    "SELECT id, display_name, last_sync_at, last_sync_status, app_token_revoked "
    "FROM gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at",
)
```

---

### `src/gruvax/api/session.py` — new GET /api/session + POST /api/session/bind (controller, request-response)

**Analog:** `src/gruvax/auth/sessions.py` (cookie helpers) + `src/gruvax/api/deps.py` (dep pattern)

**Cookie write pattern** (sessions.py lines 115–131 — copy structure for browse-binding cookie):
```python
# browse-binding cookie (D2-10 — INDEPENDENT of admin session cookie)
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"  # name constant in sessions.py

# Set cookie attributes — matches CSRF cookie: httponly=False (SPA must read it),
# samesite="strict" (home LAN all same-site), secure=False (LAN HTTP).
response.set_cookie(
    BROWSE_BINDING_COOKIE,
    profile_id_str,          # plain UUID string — no signing needed for LAN
    httponly=False,           # SPA reads to derive profile_id for SSE URL
    samesite="strict",
    secure=False,
    max_age=7 * 24 * 3600,   # 7 days — kiosk survives restarts without hitting /select
)
```

**Session endpoint pattern** (deps.py + app.py style):
```python
@router.get("/session")
async def get_session(
    request: Request,
    # NO require_admin — browse-binding is PIN-free (D2-10 / R7)
) -> JSONResponse:
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, display_name, last_sync_status, app_token_revoked "
            "FROM gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at"
        )
        rows = await cur.fetchall()
    profiles = [{"id": str(r[0]), "display_name": r[1], ...} for r in rows]
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)

    # Single-profile auto-bind (D2-08): write binding cookie in the response.
    if len(profiles) == 1 and not bound:
        bound = profiles[0]["id"]
        # Set cookie on response before returning (caller sets on JSONResponse)

    return JSONResponse(content={
        "profile_count": len(profiles),
        "bound_profile_id": bound,
        "profiles": profiles,
    })
```

---

### `src/gruvax/auth/sessions.py` — add browse-binding cookie helpers (utility, request-response)

**Analog:** `src/gruvax/auth/sessions.py` (self — extend)

**Cookie name constants pattern** (lines 33–34 — add alongside):
```python
# EXISTING:
SESSION_COOKIE = "gruvax_session"
CSRF_COOKIE = "gruvax_csrf"

# ADD for P2 (D2-10 — independent browse-binding, no admin coupling):
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"
```

**New helper — mirrors `clear_session_cookies` structure** (lines 197–226):
```python
def set_browse_binding_cookie(
    response: Response,
    profile_id: str,
    secure: bool = False,
    max_age: int = 7 * 24 * 3600,
) -> None:
    """Set the browse-binding cookie (D2-10).

    httponly=False: SPA reads the cookie to build per-profile SSE URL.
    samesite=strict: home LAN same-site, protects against CSRF.
    max_age=7 days: kiosk Chromium survives restarts without hitting /select.
    NOT signed — home LAN, server validates against registry anyway (D2-04).
    """
    response.set_cookie(
        BROWSE_BINDING_COOKIE,
        profile_id,
        httponly=False,
        samesite="strict",
        secure=secure,
        max_age=max_age,
    )


def clear_browse_binding_cookie(response: Response, secure: bool = False) -> None:
    """Clear the browse-binding cookie (Switch profile → unbind)."""
    response.delete_cookie(
        BROWSE_BINDING_COOKIE,
        path="/",
        httponly=False,
        samesite="strict",
        secure=secure,
    )
```

---

### `src/gruvax/sync/profile_sync.py` — cache reload + SSE publish in background task (service, batch/CRUD)

**Analog:** `src/gruvax/sync/profile_sync.py` lines 494–517 (modify `_refresh_app_caches`)

**Current inline refresh** (lines 500–509):
```python
# P1 — single-instance refresh:
try:
    await _refresh_app_caches(app_state)
except Exception as exc:
    logger.exception("sync_profile: cache refresh failed AFTER commit ...")
    raise _CacheRefreshFailed(exc) from exc
```

**P2 replacement — per-profile registry refresh** (new `_refresh_profile_caches`):
```python
# P2: replace _refresh_app_caches(app_state) with per-profile registry update.
# Order MUST be: commit → cache.invalidate() + cache.load() → bus.publish()
# (Pitfall A ordering — publish last, after cache is fresh).
async def _refresh_profile_caches(profile_id: str, app_state: Any) -> None:
    """Reload the registry entries for one profile and publish collection_changed."""
    pool = app_state.db_pool

    # Reload BoundaryCache for this profile
    cache: BoundaryCache = app_state.boundary_cache_registry[profile_id]
    cache.invalidate()
    await cache.load(pool, profile_id=profile_id)

    # Reload CollectionSnapshot for this profile
    snapshot: CollectionSnapshot = app_state.snapshot_registry[profile_id]
    await snapshot.load(pool, profile_id=profile_id)

    # Re-derive SegmentCache (CPU-only, no DB call)
    seg: SegmentCache = app_state.segment_cache_registry[profile_id]
    seg.derive(cache, snapshot, cache.overrides)

    # Publish AFTER all caches are fresh (Pitfall A)
    bus: EventBus = app_state.event_bus_registry[profile_id]
    await bus.publish("collection_changed", {"profile_id": profile_id})
```

---

### `frontend/src/App.tsx` — add /select route + bootstrap effect (component, request-response)

**Analog:** `frontend/src/App.tsx` (self — extend, lines 1–66)

**Route addition pattern** (lines 42–65 — add alongside existing):
```tsx
// ADD import:
import { ProfilePicker } from './routes/ProfilePicker'

// ADD route inside <Routes> BEFORE the /admin nested route:
<Route path="/select" element={<ProfilePicker />} />
```

**Bootstrap effect** (app.py lifespan + React Router useNavigate pattern from RESEARCH.md §Pattern 6):
```tsx
// ADD to App() function — declarative mode (BrowserRouter is already in use):
import { useEffect } from 'react'
import { useNavigate } from 'react-router'
import { useSessionStore } from './state/sessionStore'  // new Zustand slice

function App() {
  const navigate = useNavigate()
  const setSession = useSessionStore((s) => s.setSession)

  useEffect(() => {
    fetch('/api/session')
      .then((r) => r.json())
      .then((data: SessionData) => {
        setSession(data)
        // D2-08: auto-bind handled server-side for single profile.
        // SPA only navigates to /select when truly unbound.
        if (!data.bound_profile_id) {
          navigate('/select', { replace: true })
        }
      })
      .catch(() => {/* degrade gracefully — stay at current route */})
  }, [])

  return (/* existing JSX unchanged */ ...)
}
```

---

### `frontend/src/routes/ProfilePicker.tsx` + `ProfilePickerCard.tsx` + `OnboardingScreen.tsx` (component, request-response)

**Analog:** `frontend/src/routes/admin/RecordPickerSheet.tsx` (sheet/overlay structure)

**Sheet structure pattern** (RecordPickerSheet.tsx lines 273–399):
```tsx
// ProfilePicker.tsx — NOT a bottom-sheet, but a full-page card grid.
// Reuse: sheet-scrim scrim layer for card hover state; sheet-heading heading style;
// editor-btn-primary for the "SELECT" card CTA; sheet-error for error display.

// ProfilePickerCard.tsx — reuse RecordPickerSheet's action button pattern:
<button
  type="button"
  className="editor-btn-primary"
  onClick={() => void handleSelect(profile.id)}
  aria-busy={isSelecting}
>
  {isSelecting ? 'BINDING…' : 'SELECT'}
</button>
```

**useQuery fetch pattern** (RecordPickerSheet.tsx lines 161–168):
```tsx
// Data fetch — same queryKey convention as other admin queries:
const { data: sessionData, isLoading } = useQuery({
  queryKey: ['session'],
  queryFn: () => fetch('/api/session').then((r) => r.json()),
  staleTime: 0,   // always fresh on /select mount
})
```

---

### `frontend/src/routes/kiosk/SwitchProfileButton.tsx` + `SwitchProfileConfirm.tsx` (component, event-driven)

**Analog:** `frontend/src/routes/admin/AdminShell.tsx` (nav button + lock pattern)

**Fixed corner button pattern** (AdminShell.tsx lines 222–247 — lock button):
```tsx
// SwitchProfileButton: same admin-icon-btn class, fixed position in corner.
// Confirm guard (D2-09): same pattern as AdminShell isLocked state machine.
const [showConfirm, setShowConfirm] = useState(false)

<button
  type="button"
  className="admin-icon-btn switch-profile-btn"   // NEW class, fixed corner
  onClick={() => setShowConfirm(true)}
  aria-label="Switch profile"
>
  {/* Lucide Users icon */}
</button>

{showConfirm && (
  <SwitchProfileConfirm
    onConfirm={() => { void handleUnbindAndSwitch() }}
    onCancel={() => setShowConfirm(false)}
  />
)}
```

**Unbind + navigate pattern** (sessions.py clear_session_cookies + useNavigate):
```tsx
async function handleUnbindAndSwitch() {
  await fetch('/api/session/bind', { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } })
  sessionStore.clearBoundProfile()
  navigate('/select', { replace: true })
}
```

---

### `frontend/src/routes/admin/ProfilesManager.tsx` (component, CRUD)

**Analog:** `frontend/src/routes/admin/CubesGrid.tsx` (list page with TanStack Query)

**TanStack Query list pattern** (CubesGrid.tsx style):
```tsx
const { data: profiles, isLoading, error } = useQuery({
  queryKey: ['admin', 'profiles'],
  queryFn: () => fetch('/api/admin/profiles').then((r) => r.json()),
  staleTime: 30_000,
})
```

**Status badge pattern** (same ALL CAPS label style from admin.css):
```tsx
// ProfileStatusBadge.tsx — ALL CAPS Barlow Condensed label, token colors.
// connected → --gruvax-yellow bg; pending → --gruvax-off-white; re-auth → warn
<span className={`profile-status-badge profile-status-badge--${status}`}>
  {status.toUpperCase()}
</span>
```

---

### `frontend/src/routes/admin/ProfileDrawer.tsx` (component, CRUD + event-driven)

**Analog:** `frontend/src/routes/admin/RecordPickerSheet.tsx` (exact bottom-sheet pattern)

**Bottom sheet DOM structure** (RecordPickerSheet.tsx lines 273–399 — copy verbatim, adapt content):
```tsx
// ProfileDrawer.tsx — reuse the exact same sheet markup classes:
return (
  <>
    {/* Scrim */}
    <div className="sheet-scrim" aria-hidden="true" onClick={onClose} />

    {/* Bottom sheet */}
    <div
      ref={sheetRef}
      className="record-picker-sheet"      // reuse existing CSS class
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
    >
      <div className="sheet-drag-pill" aria-hidden="true" />
      <div className="sheet-body">
        <h2 id={headingId} className="sheet-heading">
          {profile.display_name.toUpperCase()}
        </h2>

        {/* Actions: CONNECT PAT / ROTATE PAT / RENAME / SYNC NOW / DELETE */}
        {/* ... one button per action, editor-btn-primary for primary, sheet-cancel-btn for Cancel */}
        {saveError && <p className="sheet-error" role="alert">{saveError}</p>}
      </div>
    </div>
  </>
)
```

**Focus trap + sheetRef pattern** (RecordPickerSheet.tsx lines 263–271):
```tsx
const sheetRef = useRef<HTMLDivElement>(null)
useEffect(() => {
  const el = sheetRef.current
  if (!el) return
  const focusable = el.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  )
  if (focusable.length > 0) focusable[0].focus()
}, [])
```

**isSaving + saveError state pattern** (RecordPickerSheet.tsx lines 156–159):
```tsx
const [isSaving, setIsSaving] = useState(false)
const [saveError, setSaveError] = useState<string | null>(null)
```

**202+poll pattern for "Sync now"** (RESEARCH.md §Pattern 4 + TanStack Query):
```tsx
// After POST → 202, start polling GET /api/admin/profiles/{id}:
const { data: profile } = useQuery({
  queryKey: ['admin', 'profiles', profileId],
  queryFn: () => fetch(`/api/admin/profiles/${profileId}`).then((r) => r.json()),
  refetchInterval: (query) =>
    query.state.data?.last_sync_status === 'in_progress' ? 2000 : false,
})
```

---

### `frontend/src/routes/admin/AdminShell.tsx` — add PROFILES nav tab (component, request-response)

**Analog:** `frontend/src/routes/admin/AdminShell.tsx` (self — extend, lines 158–207)

**NavLink tab pattern** (lines 158–207 — copy exactly for PROFILES):
```tsx
<NavLink
  to="/admin/profiles"
  className={({ isActive }) =>
    `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
  }
>
  PROFILES
</NavLink>
```

---

## Shared Patterns

### Authentication (PIN gate)
**Source:** `src/gruvax/api/deps.py` lines 137–224
**Apply to:** All mutating endpoints under `/api/admin/profiles/*`
```python
_admin: dict[str, Any] = Depends(require_admin)
# require_admin: reads gruvax_session cookie (itsdangerous-signed),
# checks admin_sessions row validity + sliding TTL refresh,
# verifies X-CSRF-Token header on POST/PUT/PATCH/DELETE.
```

### Pool slot discipline (Pitfall 6)
**Source:** `src/gruvax/api/admin/profile_sync.py` lines 74–118
**Apply to:** Any admin endpoint that calls a long-running operation (sync, test-sync)
```python
# PATTERN: tight async-with block for preflight, then CLOSE before long call.
db_pool = request.app.state.db_pool
async with db_pool.connection() as conn, conn.cursor() as cur:
    # ... short-lived 404 preflight only
    pass
# block CLOSED — pool slot returned BEFORE add_task / await sync_profile
```

### Parameterized SQL
**Source:** `src/gruvax/db/queries.py` + all migration files
**Apply to:** All new backend files that execute SQL
```python
# ALWAYS %s placeholders. NEVER f-strings, .format(), or concatenation.
await cur.execute(
    "SELECT ... FROM gruvax.profiles WHERE id = %s::uuid AND deleted_at IS NULL",
    (str(uid),),
)
```

### Error response structure
**Source:** `src/gruvax/api/admin/profile_sync.py` lines 100–143
**Apply to:** All new admin API endpoints
```python
# Structured detail with "type" discriminator, never bare strings.
raise HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail={"type": "invalid_uuid", "message": "profile_id must be a UUID"},
)
```

### CR-01 strong reference for background tasks
**Source:** `src/gruvax/app.py` lines 262–265
**Apply to:** Any asyncio.create_task call in lifespan or background context
```python
task = asyncio.create_task(some_coroutine())
app.state.background_tasks.add(task)          # CR-01: strong reference
task.add_done_callback(app.state.background_tasks.discard)
```

### SSE: no get_pool, headers, ping=15
**Source:** `src/gruvax/api/events.py` lines 35–75
**Apply to:** `src/gruvax/api/events.py` (the per-profile SSE endpoint)
```python
# Pitfall 10: SSE depends ONLY on get_bus_for_profile — NEVER on get_pool.
# Pitfall 8: ping=15, X-Accel-Buffering: no, Cache-Control: no-store.
return EventSourceResponse(
    generator(),
    ping=15,
    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-store"},
)
```

### React: sheet/drawer CSS classes
**Source:** `frontend/src/routes/admin/RecordPickerSheet.tsx` + `admin.css`
**Apply to:** `ProfileDrawer.tsx`, `SwitchProfileConfirm.tsx`
```
Classes to reuse verbatim:
  sheet-scrim          — semi-transparent backdrop, onClick → dismiss
  record-picker-sheet  — slide-up container
  sheet-drag-pill      — top drag affordance
  sheet-body           — padding container
  sheet-heading        — ALL CAPS Barlow Condensed h2
  sheet-actions        — flex row for action buttons
  editor-btn-primary   — filled primary CTA button
  sheet-cancel-btn     — ghost cancel button
  sheet-error          — red error message below actions
```

### React: admin nav tab
**Source:** `frontend/src/routes/admin/AdminShell.tsx` lines 158–207
**Apply to:** `AdminShell.tsx` (PROFILES tab addition)
```tsx
<NavLink
  to="/admin/profiles"
  className={({ isActive }) =>
    `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
  }
>
  PROFILES
</NavLink>
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `frontend/src/api/session.ts` | utility | request-response | No existing session-fetch client module; closest is `adminClient.ts` but that wraps PIN auth. Planner should model on `adminClient.ts` fetch style without the auth headers. |
| `frontend/src/state/sessionStore.ts` | store | — | No browse-binding Zustand slice exists yet; model on `frontend/src/state/adminStore.ts` (same pattern, simpler state shape). |

---

## Critical Pitfall Reference (from RESEARCH.md — enforce in every plan)

| Pitfall | Where It Applies | Guard |
|---|---|---|
| P1: PK constraint names | migration 0010 | Use `{tablename}_pkey` (Postgres DDL default) |
| P2: registry key type | app.py + all deps | `str(profile_id)` everywhere, never `uuid.UUID` |
| P3: background task exception swallowed | profile_sync.py `_run_sync_background` | catch-all + `logger.exception` in wrapper |
| P4: Pitfall A — publish before cache reload | sync/profile_sync.py | Order: invalidate → load → publish |
| P5: admin_sessions NOT NULL | migration 0010 | Leave `admin_sessions.profile_id` nullable |
| P6: idempotency_keys NOT NULL | migration 0010 | Leave `idempotency_keys.profile_id` nullable |
| P10: SSE + get_pool | api/events.py | `get_bus_for_profile` dep, zero pool access in SSE |

---

## Metadata

**Analog search scope:** `src/gruvax/`, `frontend/src/`, `migrations/versions/`
**Files read:** 14 source files + both planning docs
**Pattern extraction date:** 2026-05-28

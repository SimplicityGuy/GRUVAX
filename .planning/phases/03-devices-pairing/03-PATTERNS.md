# Phase 3: Devices + Pairing — Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 18 new/modified files
**Analogs found:** 15 / 18

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/gruvax/auth/sessions.py` (modify) | middleware/utility | request-response | self — `set_browse_binding_cookie` (lines 205–258) | exact — add alongside existing helper |
| `src/gruvax/api/deps.py` (modify) | middleware/dependency | request-response | self — `get_boundary_cache_for_profile` (lines 156–196) | exact — extend same dep pattern |
| `src/gruvax/api/session.py` (modify) | controller | request-response | self — `get_session` handler (lines 69–129) | exact — extend response payload |
| `src/gruvax/api/devices.py` (new) | controller | request-response | `src/gruvax/api/admin/login.py` + `src/gruvax/api/session.py` | role-match |
| `src/gruvax/api/admin/devices.py` (new) | controller | CRUD | `src/gruvax/api/admin/profiles.py` | exact — same admin CRUD pattern |
| `src/gruvax/api/admin/limiter.py` (modify) | utility | request-response | self — `_LOGIN_RATE` + `_rate_limiter` (lines 33–39) | exact — add `_BIND_RATE` constant |
| `src/gruvax/events/bus.py` (read-only reference) | service | pub-sub | self | exact — consume as-is, do not modify |
| `src/gruvax/api/events.py` (modify) | controller | streaming | self — `get_bus_for_profile` dep wiring (lines 36–79) | exact — extend profile-resolution dep |
| `migrations/versions/0011_devices_and_pairing_codes.py` (new) | migration | batch | `migrations/versions/0010_profile_id_not_null.py` | exact — same conventions |
| `frontend/src/routes/kiosk/PairView.tsx` (new) | component | request-response | `frontend/src/routes/kiosk/KioskView.tsx` + `frontend/src/routes/admin/PinOverlay.tsx` | role-match |
| `frontend/src/routes/admin/DevicesManager.tsx` (new) | component | CRUD | `frontend/src/routes/admin/ProfilesManager.tsx` | exact — same list + drawer pattern |
| `frontend/src/routes/admin/DeviceCard.tsx` (new) | component | request-response | `frontend/src/routes/admin/ProfileCard.tsx` | exact — same card button pattern |
| `frontend/src/routes/admin/DeviceDrawer.tsx` (new) | component | CRUD | `frontend/src/routes/admin/ProfileDrawer.tsx` | exact — same sheet-* markup pattern |
| `frontend/src/routes/admin/DeviceStateBadge.tsx` (new) | component | request-response | `frontend/src/routes/admin/ProfileStatusBadge.tsx` | exact — same color-mix badge pattern |
| `frontend/src/App.tsx` (modify) | component | request-response | self — route table (lines 80–98) | exact — add `/pair` route |
| `frontend/src/routes/ProfilePicker.tsx` (modify) | component | request-response | self + `frontend/src/routes/OnboardingScreen.tsx` | exact — add affordance button |
| `tests/integration/test_devices.py` (new) | test | request-response | `tests/integration/test_admin_auth.py` | exact — same ASGI + rate-limit reset pattern |
| `deploy/kiosk/` (new — 3 files) | config | event-driven | no analog in codebase | greenfield — spec is CLAUDE.md §Recommended Stack — Raspberry Pi Kiosk |

---

## Pattern Assignments

### `src/gruvax/auth/sessions.py` — add fingerprint cookie helpers (modify)

**Analog:** same file, `set_browse_binding_cookie` and `clear_browse_binding_cookie` (lines 205–258)

**Cookie constant pattern** (lines 42–44, existing):
```python
BROWSE_BINDING_COOKIE = "gruvax_browse_binding"
# httponly=False: SPA reads it to derive per-profile SSE URL.
# max_age=7 days: kiosk Chromium survives restarts.
```

**New constants to add immediately after line 44:**
```python
FINGERPRINT_COOKIE = "gruvax_device_fp"
# HttpOnly=True: JS must NEVER read the fingerprint (it is a session-equivalent secret).
# max_age=30 days: Chromium writes to disk only when max_age is set (Pitfall 1 in RESEARCH.md).
# Secure=False for home-LAN HTTP; set True when TLS lands (mirrors set_browse_binding_cookie).
FINGERPRINT_MAX_AGE = 30 * 24 * 3600
```

**Cookie setter pattern** (lines 205–238 — exact template for new `issue_fingerprint_cookie`):
```python
def set_browse_binding_cookie(
    response: Response,
    profile_id: str,
    secure: bool = False,
    max_age: int = 7 * 24 * 3600,
) -> None:
    response.set_cookie(
        BROWSE_BINDING_COOKIE,
        profile_id,
        httponly=False,      # <-- fingerprint: change to True
        samesite="strict",
        secure=secure,
        max_age=max_age,     # <-- fingerprint: FINGERPRINT_MAX_AGE, required for disk persistence
    )
```

**New functions to add** (mirroring `set_browse_binding_cookie` / `clear_browse_binding_cookie`):
- `issue_fingerprint_cookie(response, secure=False) -> str` — generates `secrets.token_urlsafe(32)`, calls `response.set_cookie` with `httponly=True`, `samesite="strict"`, `max_age=FINGERPRINT_MAX_AGE`, returns the raw token.
- `get_fingerprint(request) -> str | None` — `return request.cookies.get(FINGERPRINT_COOKIE)`
- `clear_fingerprint_cookie(response, secure=False) -> None` — mirrors `clear_browse_binding_cookie`; `delete_cookie` attributes must match `set_cookie` (CR-04 invariant, line 248 comment).

**Import to add** (secrets already imported at line 21):
```python
import secrets  # already present — no new import needed
```

---

### `src/gruvax/api/deps.py` — device-aware profile resolution + revoke guard (modify)

**Analog:** same file, `get_boundary_cache_for_profile` (lines 156–196) and `get_bus_for_profile` (lines 271–307)

**Imports pattern** (lines 1–24):
```python
from __future__ import annotations
from datetime import UTC, datetime, timedelta
import secrets
from typing import TYPE_CHECKING, Any
from fastapi import Depends, HTTPException, Request, status
from gruvax.auth.sessions import BROWSE_BINDING_COOKIE, CSRF_COOKIE, get_session_id
```

**New import to add** (line 15, after `BROWSE_BINDING_COOKIE`):
```python
from gruvax.auth.sessions import (
    BROWSE_BINDING_COOKIE, CSRF_COOKIE, FINGERPRINT_COOKIE, get_session_id
)
```

**Existing per-profile dep pattern** (lines 156–196 — template for device-aware resolution):
```python
def get_boundary_cache_for_profile(
    profile_id: str,
    request: Request,
) -> BoundaryCache:
    bound = request.cookies.get(BROWSE_BINDING_COOKIE)
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
    # ...
```

**New helper to add — `resolve_profile_from_request`** (async, takes `request` + `pool`):
- Checks `FINGERPRINT_COOKIE` first. If present: queries `gruvax.devices WHERE fingerprint = %s` (parameterized `%s`, not f-string — bandit B608). Raises 403 `device_unknown` if no row. Raises 403 `device_revoked` if `revoked_at IS NOT NULL`. Returns `(profile_id_str, device_id_str)` if `profile_id IS NOT NULL`. Falls through to browse-binding if `profile_id IS NULL` (orphaned device).
- Falls back to `request.cookies.get(BROWSE_BINDING_COOKIE)`. Raises 400 `session_unbound` if absent.
- Each per-profile dep (`get_boundary_cache_for_profile`, `get_snapshot_for_profile`, `get_segment_cache_for_profile`) calls this helper instead of reading the cookie directly.

**Pitfall 10 — `get_bus_for_profile` extension** (lines 271–307):
The SSE dep reads ONLY `app.state`. The device check must happen before entering the generator, using an early pool acquire+release. Pattern: validate in the dep (which CAN use pool), then enter the generator that reads only the bus queue. The dep function is `async` so it can `await pool.connection()` before returning the bus.

**Pool pattern** (lines 354–395 in `require_admin`, exact acquire/release template):
```python
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute("SELECT ... FROM gruvax... WHERE ... = %s", (value,))
    row = await cur.fetchone()
# pool slot released here — never held across a generator boundary
```

---

### `src/gruvax/api/session.py` — extend GET /api/session for device binding (modify)

**Analog:** same file, `get_session` handler (lines 69–129)

**Existing response shape** (lines 119–127):
```python
content = {
    "profile_count": len(profiles),
    "bound_profile_id": bound_profile_id,
    "profiles": profiles,
}
response = JSONResponse(content=content)
```

**Extension pattern** (D3-04): Before constructing `content`, extract the fingerprint cookie and query `gruvax.devices`. If matched to a PAIRED device, override `bound_profile_id` with `devices.profile_id` and add `device_id` + `is_device_paired: True` to `content`. If orphaned (profile_id NULL), let `bound_profile_id` remain null (picker). If no fingerprint, proceed as today.

**SQL module-level constant convention** (lines 46–60 — copy style for new device query):
```python
_SELECT_ACTIVE_PROFILES = (
    "SELECT id, display_name, ..."
    " FROM gruvax.profiles"
    " WHERE deleted_at IS NULL"
    " ORDER BY created_at"
)
# Add:
_SELECT_DEVICE_BY_FINGERPRINT = (
    "SELECT id, profile_id, revoked_at"
    " FROM gruvax.devices WHERE fingerprint = %s"
)
```

**DB access pattern** (lines 91–94):
```python
db_pool = request.app.state.db_pool
async with db_pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(_SELECT_ACTIVE_PROFILES)
    rows = await cur.fetchall()
```

---

### `src/gruvax/api/devices.py` (new — kiosk endpoints)

**Analog:** `src/gruvax/api/admin/login.py` (rate-limit pattern) + `src/gruvax/api/session.py` (no-auth, cookie-setting pattern)

**Imports pattern** (copy from `session.py` lines 28–44 + `login.py` lines 30–43):
```python
from __future__ import annotations
import logging
import secrets
from typing import Any
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from gruvax.auth.sessions import FINGERPRINT_COOKIE, get_fingerprint, issue_fingerprint_cookie
```

**Router declaration** (mirror `session.py` line 44):
```python
router = APIRouter(tags=["devices"])
```

**SQL constants** (module-level, no f-strings, parameterized `%s`):
```python
_INSERT_PAIRING_CODE = (
    "INSERT INTO gruvax.pairing_codes (code, fingerprint, expires_at)"
    " VALUES (%s, %s, NOW() + INTERVAL '5 minutes')"
    " ON CONFLICT (code) DO NOTHING"
    " RETURNING code"
)
_SELECT_DEVICE_BY_FINGERPRINT = (
    "SELECT id, profile_id, revoked_at"
    " FROM gruvax.devices WHERE fingerprint = %s"
)
```

**Fingerprint auto-issue pattern** — `POST /api/devices/pairing-codes`:
1. Call `get_fingerprint(request)`. If None, call `issue_fingerprint_cookie(response)` to generate + set cookie in the same response, capturing the raw value.
2. Loop up to 3 times: generate `f"{random.randint(0, 9999):04d}"`, execute `_INSERT_PAIRING_CODE`, break on non-None row (mirrors RESEARCH.md Pattern 2 collision-handling).
3. Return `{code, expires_at}`. Never log the fingerprint value (RESEARCH.md Pitfall 7).

**`GET /api/devices/me`** — return device state for the fingerprint:
```python
@router.get("/devices/me")
async def get_device_me(request: Request) -> JSONResponse:
    fp = get_fingerprint(request)
    if not fp:
        return JSONResponse(content={"state": "unpaired"})
    # query gruvax.devices by fingerprint, return {state, profile_id}
```

---

### `src/gruvax/api/admin/devices.py` (new — admin CRUD endpoints)

**Analog:** `src/gruvax/api/admin/profiles.py` (full file — exact CRUD pattern)

**Imports pattern** (lines 28–55 of `profiles.py`):
```python
from __future__ import annotations
import logging
from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
import psycopg.errors
from pydantic import BaseModel
from gruvax.api.deps import get_pool, require_admin
```

**`_parse_uuid` helper** (lines 106–114 of `profiles.py` — copy verbatim):
```python
def _parse_uuid(device_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(device_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"type": "invalid_uuid", "message": "device_id must be a UUID"},
        ) from None
```

**`require_admin` guard pattern** (lines 170–173 of `profiles.py` — copy for all mutation endpoints):
```python
@router.post("/bind")
async def bind_device(
    request: Request,
    body: BindRequest,
    pool: Any = Depends(get_pool),
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
```

**Atomic bind pattern** (RESEARCH.md Pattern 2):
```python
_BIND_CODE = (
    "UPDATE gruvax.pairing_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING fingerprint"
)
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(_BIND_CODE, (code,))
    row = await cur.fetchone()
    await conn.commit()
if row is None:
    raise HTTPException(status_code=404, detail={"type": "code_not_found"})
```

**Rate-limit usage pattern** (lines 50–74 of `login.py` — mirror `_check_login_rate_limit`):
```python
from gruvax.api.admin.limiter import _BIND_RATE, _rate_limiter

def _check_bind_rate_limit(request: Request) -> None:
    client_ip: str = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_BIND_RATE, "device_bind", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"type": "rate_limited", "message": "Too many attempts. Wait a moment and try again."},
        )
```

**PATCH/DELETE pattern** (lines 362–389 and 590–629 of `profiles.py`):
```python
@router.patch("/devices/{device_id}")
async def rename_device(
    device_id: str,
    request: Request,
    body: RenameDeviceRequest,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    uid = _parse_uuid(device_id)
    db_pool = request.app.state.db_pool
    async with db_pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.devices SET display_name = %s WHERE id = %s::uuid",
            (body.display_name, str(uid)),
        )
        await conn.commit()
    return JSONResponse(content={"id": str(uid), "display_name": body.display_name})
```

**SSE publish on mutation** (after successful DB write — publish to the device's current profile bus):
```python
bus_registry: dict[str, Any] | None = getattr(request.app.state, "event_bus_registry", None)
if bus_registry and current_profile_id:
    bus = bus_registry.get(current_profile_id)
    if bus:
        await bus.publish("device_revoked", {"device_id": str(uid)})
```

---

### `src/gruvax/api/admin/limiter.py` — add `_BIND_RATE` (modify)

**Analog:** same file (full file — 39 lines)

**Existing pattern** (lines 33–39):
```python
limiter: MemoryStorage = MemoryStorage()
_rate_limiter: FixedWindowRateLimiter = FixedWindowRateLimiter(limiter)
_LOGIN_RATE = parse_limit("5/5minutes")
```

**Addition after line 39:**
```python
# Device bind rate limit — 10 attempts per 5-minute window per IP.
# Shared storage singleton; namespace key is "device_bind" (vs "login" for login).
_BIND_RATE = parse_limit("10/5minutes")
```

---

### `src/gruvax/api/events.py` — extend `get_bus_for_profile` dep for device validation (modify)

**Analog:** same file + `src/gruvax/api/deps.py` `get_bus_for_profile` (lines 271–307)

**Critical constraint** (line 8 comment): `Depends ONLY on get_bus_for_profile — NEVER on get_pool (D-09, Pitfall 10).`

The device check must happen INSIDE `get_bus_for_profile` (in `deps.py`) before the SSE generator starts, with the pool acquired and released in the dep. The generator body (lines 51–70 of `events.py`) must remain pool-free:

```python
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
```

The dep `get_bus_for_profile` in `deps.py` must become `async` so it can call `resolve_profile_from_request` (pool acquire+release happens inside the dep, not inside the generator).

---

### `migrations/versions/0011_devices_and_pairing_codes.py` (new)

**Analog:** `migrations/versions/0010_profile_id_not_null.py` (full file — 544 lines)

**Header convention** (lines 1–65 of 0010):
```python
"""Create devices + pairing_codes tables (P3 / DEV-01).

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-29

...narrative...

Conventions (carried from 0001-0010):
  - from __future__ import annotations; from alembic import op
  - revision = "0011"; down_revision = "0010"; branch_labels/depends_on = None
  - ALL SQL as module-level string constants; op.execute(_CONST) in upgrade()/
    downgrade(); never inline triple-quoted strings inside functions; never
    f-strings / runtime concatenation.
  - downgrade() fully reverses upgrade() — the CI round-trip gate enforces fidelity.
"""

from __future__ import annotations
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | None = None
depends_on: str | None = None
```

**SQL constant style** (lines 89–114 of 0010 — all module-level, string concatenation only):
```python
_CREATE_DEVICES = (
    "CREATE TABLE IF NOT EXISTS gruvax.devices ("
    "  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  fingerprint TEXT NOT NULL,"
    "  profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE SET NULL,"
    "  display_name TEXT NOT NULL DEFAULT 'Unnamed device',"
    "  revoked_at TIMESTAMPTZ,"
    "  last_seen_at TIMESTAMPTZ,"
    "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    ")"
)
_CREATE_PAIRING_CODES = (
    "CREATE TABLE IF NOT EXISTS gruvax.pairing_codes ("
    "  code CHAR(4) PRIMARY KEY,"
    "  fingerprint TEXT NOT NULL,"
    "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  expires_at TIMESTAMPTZ NOT NULL,"
    "  consumed_at TIMESTAMPTZ"
    ")"
)
# Partial-unique indexes (spec §Data Model)
_IDX_DEVICES_FP_ACTIVE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_fingerprint_active"
    " ON gruvax.devices (fingerprint)"
    " WHERE revoked_at IS NULL"
)
_IDX_DEVICES_FP_PLAIN = (
    "CREATE INDEX IF NOT EXISTS idx_devices_fingerprint"
    " ON gruvax.devices (fingerprint)"
    # non-partial — for revoke-guard lookups that must find revoked rows too
    # (RESEARCH.md Pitfall 5 / Open Question 2)
)
_IDX_DEVICES_PROFILE_ACTIVE = (
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_devices_profile_active"
    " ON gruvax.devices (profile_id)"
    " WHERE revoked_at IS NULL AND profile_id IS NOT NULL"
)
_IDX_PAIRING_CODES_EXPIRES = (
    "CREATE INDEX IF NOT EXISTS idx_pairing_codes_expires"
    " ON gruvax.pairing_codes (expires_at)"
)
```

**`upgrade()` / `downgrade()` pattern** (lines 465–543 of 0010):
```python
def upgrade() -> None:
    op.execute(_CREATE_DEVICES)
    op.execute(_CREATE_PAIRING_CODES)
    op.execute(_IDX_DEVICES_FP_ACTIVE)
    op.execute(_IDX_DEVICES_FP_PLAIN)
    op.execute(_IDX_DEVICES_PROFILE_ACTIVE)
    op.execute(_IDX_PAIRING_CODES_EXPIRES)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gruvax.idx_pairing_codes_expires")
    op.execute("DROP INDEX IF EXISTS gruvax.idx_devices_profile_active")
    op.execute("DROP INDEX IF EXISTS gruvax.idx_devices_fingerprint")
    op.execute("DROP INDEX IF EXISTS gruvax.idx_devices_fingerprint_active")
    op.execute("DROP TABLE IF EXISTS gruvax.pairing_codes")
    op.execute("DROP TABLE IF EXISTS gruvax.devices")
```

---

### `frontend/src/routes/kiosk/PairView.tsx` (new)

**Analog:** `frontend/src/routes/kiosk/KioskView.tsx` (structure) + `frontend/src/routes/admin/PinOverlay.tsx` (full-viewport centered card with countdown)

**Imports pattern** (KioskView lines 1–18):
```typescript
import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { Loader2, CheckCircle2 } from 'lucide-react'
import './pair.css'
```

**TanStack Query poll pattern** (ProfileDrawer lines 128–136 — `refetchInterval` until terminal state):
```typescript
const { data: deviceState } = useQuery({
  queryKey: ['devices', 'me'],
  queryFn: () => fetch('/api/devices/me').then((r) => r.json()),
  refetchInterval: (query) => {
    return query.state.data?.state === 'paired' ? false : 3000
  },
})
```

**Code fetch + auto-reroll pattern** (new — no direct analog, but follows `useQuery` + `refetchInterval` from ProfileDrawer):
```typescript
const { data: pairingCode, refetch: refetchCode } = useQuery({
  queryKey: ['devices', 'pairing-code'],
  queryFn: () => fetch('/api/devices/pairing-codes', { method: 'POST' })
    .then((r) => r.json()),
  staleTime: 0,
})
// On countdown expiry: call refetchCode()
```

**Already-paired routing guard** (D3-03 — mirror App.tsx lines 62–77):
```typescript
const navigate = useNavigate()
useEffect(() => {
  if (deviceState?.state === 'paired' && deviceState.profile_id) {
    // D3-03: already paired → go straight to search
    void navigate('/', { replace: true })
  }
}, [deviceState, navigate])
```

**CSS pattern** — new `pair.css` sibling (copy `.kiosk-page` structure from `kiosk.css` lines 1–12):
```css
/* pair.css — ALL values reference CSS custom properties from gruvax-design-tokens.css */
.pair-page {
  min-height: 100dvh;
  background: var(--gruvax-white);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--gruvax-space-6);
  font-family: var(--gruvax-font-ui);
}
```

---

### `frontend/src/routes/admin/DevicesManager.tsx` (new)

**Analog:** `frontend/src/routes/admin/ProfilesManager.tsx` (full file — 116 lines)

**Imports pattern** (lines 1–18 of `ProfilesManager.tsx`):
```typescript
import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { SyncToast } from '../../components/SyncToast'
```

**State + drawer pattern** (lines 22–48):
```typescript
type DrawerTarget = DeviceRow | 'bind' | null

export function DevicesManager() {
  const queryClient = useQueryClient()
  const [drawerTarget, setDrawerTarget] = useState<DrawerTarget>(null)
  const [actionToast, setActionToast] = useState<{ message: string } | null>(null)

  const { data: devices, isLoading, isError } = useQuery({
    queryKey: ['admin', 'devices'],
    queryFn: getAdminDevices,
    staleTime: 30_000,
  })
  // ...
```

**Grouped list pattern** (new — no direct analog, but uses `<ul>` + `<li>` from lines 78–88 of `ProfilesManager.tsx`):
- Group into `paired`, `pending`, `revoked` arrays before render.
- Render each group with a section header only if the group is non-empty (spec: "empty groups are omitted").

**"ADD DEVICE" dashed row** (lines 91–98 of `ProfilesManager.tsx`):
```typescript
<button
  type="button"
  className="profiles-add-row"  // → new class "devices-add-row" in admin.css
  onClick={() => setDrawerTarget('bind')}
  aria-label="Add a new device"
>
  + ADD DEVICE
</button>
```

---

### `frontend/src/routes/admin/DeviceCard.tsx` (new)

**Analog:** `frontend/src/routes/admin/ProfileCard.tsx` (full file — 74 lines)

**Component signature pattern** (lines 43–73):
```typescript
interface DeviceCardProps {
  device: DeviceRow
  onClick: () => void
  index: number
}

export function DeviceCard({ device, onClick, index }: DeviceCardProps) {
  const isEven = index % 2 === 0
  return (
    <button
      type="button"
      className={`device-card${isEven ? ' device-card--even' : ''}`}
      onClick={onClick}
      aria-label={`Edit device ${device.display_name}`}
    >
      <div className="device-card-main">
        <span className="device-card-name">{device.display_name}</span>
        <DeviceStateBadge state={device.state} />
      </div>
      <p className="device-card-meta">
        {/* device: {id8} · {profile_name} · {last_seen} */}
      </p>
    </button>
  )
}
```

**Last-seen formatting** (mirror `formatLastSync` lines 26–35 of `ProfileCard.tsx`):
```typescript
function formatLastSeen(lastSeenAt: string | null | undefined): string {
  if (!lastSeenAt) return 'never'
  const diff = Date.now() - new Date(lastSeenAt).getTime()
  const minutes = Math.floor(diff / 60_000)
  if (minutes <= 2) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
```

---

### `frontend/src/routes/admin/DeviceDrawer.tsx` (new)

**Analog:** `frontend/src/routes/admin/ProfileDrawer.tsx` (full file — 624 lines)

**Sheet markup pattern** (lines 286–310):
```typescript
return (
  <>
    <div className="sheet-scrim" aria-hidden="true" onClick={onClose} />
    <div
      ref={sheetRef}
      className="record-picker-sheet"
      role="dialog"
      aria-modal="true"
      aria-labelledby={headingId}
    >
      <div className="sheet-drag-pill" aria-hidden="true" />
      <div className="sheet-body">
        <h2 id={headingId} className="sheet-heading">
          {heading}
        </h2>
        {saveError && (
          <p className="sheet-error" role="alert">{saveError}</p>
        )}
        <div className="sheet-actions">
          {/* context-sensitive actions */}
        </div>
      </div>
    </div>
  </>
)
```

**Focus trap pattern** (lines 101–108):
```typescript
const sheetRef = useRef<HTMLDivElement>(null)
useEffect(() => {
  const el = sheetRef.current
  if (!el) return
  const focusable = el.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
  )
  if (focusable.length > 0) focusable[0].focus()
}, [])
```

**Drawer mode state pattern** (lines 77–96):
```typescript
type DrawerMode = 'view' | 'rename' | 'bind-code' | 'revoke-confirm' | 'delete-confirm' | 'unbind-confirm'
const [drawerMode, setDrawerMode] = useState<DrawerMode>('view')
const [saveError, setSaveError] = useState<string | null>(null)
const [isSaving, setIsSaving] = useState(false)
```

**NumericKeypad integration** (mirror `PinOverlay.tsx` lines 105–116 for auto-submit on 4th digit):
```typescript
const [codeDigits, setCodeDigits] = useState<string[]>([])
const handleCodeDigit = useCallback((d: string) => {
  if (codeDigits.length >= 4) return
  const next = [...codeDigits, d]
  setCodeDigits(next)
  if (next.length === 4) {
    void handleBind(next.join(''))
  }
}, [codeDigits])
```

**Destructive confirm mode pattern** (lines 412–434 of `ProfileDrawer.tsx`):
```typescript
{drawerMode === 'revoke-confirm' && (
  <div className="profile-delete-confirm" role="alertdialog" aria-labelledby="revoke-confirm-heading">
    <h3 id="revoke-confirm-heading" className="profile-delete-confirm-heading">
      Revoke this device?
    </h3>
    <p className="profile-delete-confirm-body">
      The kiosk will be locked out immediately. It can be reinstated later.
    </p>
  </div>
)}
```

---

### `frontend/src/routes/admin/DeviceStateBadge.tsx` (new)

**Analog:** `frontend/src/routes/admin/ProfileStatusBadge.tsx` (full file — 43 lines)

**Exact copy pattern** (lines 15–43):
```typescript
export type DeviceState = 'paired' | 'pending' | 'revoked'

const STATE_LABELS: Record<DeviceState, string> = {
  paired: 'PAIRED',
  pending: 'PENDING',
  revoked: 'REVOKED',
}

export function DeviceStateBadge({ state }: { state: DeviceState }) {
  const label = STATE_LABELS[state]
  return (
    <span
      className={`device-state-badge device-state-badge--${state}`}
      aria-label={`Status: ${label}`}
    >
      {label}
    </span>
  )
}
```

**CSS pattern** (follow `ProfileStatusBadge` color-mix formula, add to `admin.css` under `/* ── P3: Devices ──` comment block):
```css
/* PAIRED → success tint (matches CONNECTED badge formula) */
.device-state-badge--paired {
  background: color-mix(in srgb, var(--gruvax-success) 12%, transparent);
  color: var(--gruvax-success);
}
/* PENDING → warning tint */
.device-state-badge--pending {
  background: color-mix(in srgb, var(--gruvax-warning) 12%, transparent);
  color: var(--gruvax-warning);
}
/* REVOKED → error tint */
.device-state-badge--revoked {
  background: color-mix(in srgb, var(--gruvax-error) 10%, transparent);
  color: var(--gruvax-error);
}
```

---

### `frontend/src/App.tsx` — add `/pair` route (modify)

**Analog:** same file, route table (lines 80–98)

**Route addition pattern** (lines 80–98 — insert new top-level Route before `/admin`):
```typescript
import { PairView } from './routes/kiosk/PairView'

// In AppInner bootstrap effect (lines 62–77): check device binding from GET /api/session.
// If data.is_device_paired && data.bound_profile_id → stay on '/' (D3-03 routing rule).
// If no bound_profile_id AND window.location.pathname !== '/pair' → navigate to '/select'.

<Routes>
  <Route path="/" element={<KioskView />} />
  <Route path="/pair" element={<PairView />} />  {/* D3-01 — new */}
  <Route path="/select" element={<ProfilePicker />} />
  {/* /admin routes unchanged */}
</Routes>
```

**Session store extension** (in `frontend/src/state/sessionStore.ts`, extend `SessionData` shape):
```typescript
// In frontend/src/api/session.ts — extend SessionData:
export interface SessionData {
  profile_count: number
  bound_profile_id: string | null
  profiles: ProfileSummary[]
  device_id?: string | null        // new — non-secret device UUID
  is_device_paired?: boolean        // new — true when fingerprint maps to a paired device
}
```

---

### `frontend/src/routes/ProfilePicker.tsx` — add "PAIR THIS SCREEN" affordance (modify)

**Analog:** same file (lines 47–57) + `frontend/src/routes/OnboardingScreen.tsx` (lines 15–28)

**Button addition pattern** (after profile grid, before end of `return`):
```typescript
import { useNavigate } from 'react-router'

// Inside ProfilePicker, after the picker-grid:
<button
  type="button"
  className="picker-pair-btn"   // new CSS class in picker.css
  onClick={() => void navigate('/pair')}
>
  PAIR THIS SCREEN AS A DEVICE
</button>
```

**`OnboardingScreen` addition** (after existing CTA, new button + instruction):
```typescript
<Link to="/admin" className="onboarding-cta">OPEN ADMIN PANEL</Link>
<Link to="/pair" className="onboarding-cta onboarding-cta--secondary">
  PAIR THIS SCREEN AS A DEVICE
</Link>
<p className="onboarding-pair-instruction">
  Already have profiles set up? Link this screen to one.
</p>
```

---

### `tests/integration/test_devices.py` (new)

**Analog:** `tests/integration/test_admin_auth.py` (full file)

**Module header + fixtures pattern** (lines 1–89):
```python
from __future__ import annotations
import os
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
import pytest
import pytest_asyncio
from gruvax.app import create_app

@pytest.fixture(autouse=True)
def reset_bind_rate_limit() -> None:  # type: ignore[return]
    """Reset bind rate-limit counter before each test (mirrors reset_login_rate_limit)."""
    from gruvax.api.admin.limiter import limiter
    limiter.reset()

@pytest_asyncio.fixture(scope="module")
async def client(db_pool):  # type: ignore[no-untyped-def]
    if not os.environ.get("SESSION_SECRET"):
        os.environ["SESSION_SECRET"] = "test-session-secret-for-pytest-only"
    app = create_app()
    async with (
        LifespanManager(app) as manager,
        AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as ac,
    ):
        yield ac
```

**Test assertion pattern** (lines 92–107):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_generate_code(client) -> None:
    response = await client.post("/api/devices/pairing-codes")
    assert response.status_code == 200
    data = response.json()
    assert len(data["code"]) == 4
    assert data["code"].isdigit()
    assert "gruvax_device_fp" in response.cookies
    # HttpOnly check via raw Set-Cookie header
    set_cookie = response.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
```

**Rate-limit test pattern** (lines 111–124):
```python
@pytest.mark.asyncio(loop_scope="session")
async def test_bind_rate_limit(client) -> None:
    for _ in range(10):
        await client.post("/api/admin/devices/bind", json={"code": "9999"})
    response = await client.post("/api/admin/devices/bind", json={"code": "9999"})
    assert response.status_code == 429
```

---

### `tests/unit/test_fingerprint_cookie.py` (new)

**Analog:** `tests/unit/test_sessions.py` (full file — pure-function unit tests)

**Pattern** (lines 1–20 of `test_sessions.py`):
```python
"""Unit tests for fingerprint cookie helpers (DEV-01).

Targets pure helpers in gruvax.auth.sessions.
Analog: tests/unit/test_sessions.py.
"""
from __future__ import annotations

def test_fingerprint_cookie_is_httponly() -> None:
    """Cookie attributes: HttpOnly + SameSite=Strict + max_age >= 30 days (D3-09)."""
    from unittest.mock import MagicMock
    from gruvax.auth.sessions import issue_fingerprint_cookie, FINGERPRINT_MAX_AGE
    response_mock = MagicMock()
    fp = issue_fingerprint_cookie(response_mock)
    assert len(fp) >= 40, "fingerprint must be at least 40 chars (secrets.token_urlsafe(32))"
    response_mock.set_cookie.assert_called_once()
    call_kwargs = response_mock.set_cookie.call_args[1]
    assert call_kwargs["httponly"] is True
    assert call_kwargs["samesite"] == "strict"
    assert call_kwargs["max_age"] >= 30 * 24 * 3600
```

---

## Shared Patterns

### Cookie Helper Convention
**Source:** `src/gruvax/auth/sessions.py` lines 205–258
**Apply to:** `src/gruvax/auth/sessions.py` new functions, `src/gruvax/api/devices.py`
- `response.set_cookie(NAME, value, httponly=..., samesite="strict", secure=secure, max_age=...)`
- `response.delete_cookie(NAME, path="/", httponly=..., samesite="strict", secure=secure)` — attributes must match set_cookie exactly (CR-04)
- Never log the cookie value (credential-equivalent — RESEARCH.md Pitfall 7)

### Admin Auth Guard
**Source:** `src/gruvax/api/deps.py` `require_admin` (lines 310–397)
**Apply to:** All `/api/admin/devices/*` endpoints
```python
_admin: dict[str, Any] = Depends(require_admin)
```

### Parameterized SQL (no f-strings)
**Source:** Throughout `src/gruvax/api/admin/profiles.py` and `src/gruvax/api/session.py`
**Apply to:** All new device/pairing_codes SQL queries
```python
_QUERY = (
    "SELECT ... FROM gruvax.devices WHERE fingerprint = %s"
)
await cur.execute(_QUERY, (fp_value,))  # never f-string interpolation (bandit B608)
```

### Pool Acquire/Release (tight checkout)
**Source:** `src/gruvax/api/admin/profiles.py` `_require_profile` (lines 117–129) and `require_admin` (lines 354–395)
**Apply to:** All device endpoint DB operations
```python
async with db_pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(_QUERY, (param,))
    row = await cur.fetchone()
# pool slot released immediately after the with-block
```

### EventBus Publish (after DB commit)
**Source:** `src/gruvax/events/bus.py` `publish` (lines 63–76) + usage pattern in `profiles.py`
**Apply to:** `src/gruvax/api/admin/devices.py` revoke/reassign mutations
```python
# Always AFTER conn.commit() — never inside the transaction
await bus.publish("device_revoked", {"device_id": str(device_id)})
```

### SSE Generator — No Pool
**Source:** `src/gruvax/api/events.py` full generator (lines 51–70) + comment on line 8
**Apply to:** `src/gruvax/api/events.py` extended `get_bus_for_profile` dep
- The dep validates device status (acquires+releases pool). The generator body reads only `asyncio.Queue` — zero pool interaction (Pitfall 10).

### Rate-Limit Pattern
**Source:** `src/gruvax/api/admin/limiter.py` + `src/gruvax/api/admin/login.py` `_check_login_rate_limit` (lines 51–74)
**Apply to:** `src/gruvax/api/admin/devices.py` bind endpoint
```python
from gruvax.api.admin.limiter import _BIND_RATE, _rate_limiter
# call _check_bind_rate_limit(request) as first line of the bind handler
```

### Admin Tab Nav
**Source:** `frontend/src/routes/admin/AdminShell.tsx` lines 158–215 (`NavLink` pattern)
**Apply to:** Add "DEVICES" `NavLink` tab alongside existing PROFILES/SETTINGS/CUBES tabs
```typescript
<NavLink
  to="/admin/devices"
  className={({ isActive }) =>
    `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
  }
>
  DEVICES
</NavLink>
```

### TanStack Query Invalidation on Mutation
**Source:** `frontend/src/routes/admin/ProfilesManager.tsx` `handleSyncComplete` (lines 45–48)
**Apply to:** `DevicesManager.tsx` and `DeviceDrawer.tsx` after every device mutation
```typescript
void queryClient.invalidateQueries({ queryKey: ['admin', 'devices'] })
```

### Design Token Usage (CSS)
**Source:** `frontend/src/routes/admin/admin.css` throughout; `frontend/src/routes/kiosk/kiosk.css` lines 1–12
**Apply to:** All new CSS in `pair.css` and `admin.css` P3 block
- All colors: `var(--gruvax-*)` only — no hardcoded hex
- All spacing: `var(--gruvax-space-*)` tokens only
- All type: `var(--gruvax-font-display/ui/mono)` + `var(--gruvax-text-*)` tokens

---

## No Analog Found

Files with no close match in the codebase — planner uses RESEARCH.md patterns instead:

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `deploy/kiosk/start-kiosk.sh` | config | event-driven | No existing shell launcher in repo; use CLAUDE.md §Recommended Stack — Raspberry Pi Kiosk + RESEARCH.md Pattern 6 |
| `deploy/kiosk/gruvax-kiosk.service` | config | event-driven | No systemd units exist in repo; use RESEARCH.md Pattern 6 verbatim |
| `deploy/kiosk/README.md` | docs | n/a | New directory; use RESEARCH.md Pattern 6 for content |
| `tests/browser/test_reboot_persistence.py` | test | event-driven | No Playwright tests exist yet; use RESEARCH.md Pattern 5 verbatim |

---

## Metadata

**Analog search scope:** `src/gruvax/` (all Python), `frontend/src/` (all TypeScript/TSX), `migrations/versions/`, `tests/`
**Files scanned:** ~70
**Pattern extraction date:** 2026-05-29

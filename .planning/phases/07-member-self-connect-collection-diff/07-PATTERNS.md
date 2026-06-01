# Phase 7: Member Self-Connect + Collection Diff — Pattern Map

**Mapped:** 2026-06-01
**Files analyzed:** 13 new/modified files
**Analogs found:** 13 / 13

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `migrations/versions/0012_invite_codes_and_first_seen_at.py` | migration | batch | `migrations/versions/0011_devices_and_pairing_codes.py` | exact |
| `src/gruvax/api/invite_codes.py` | controller | request-response | `src/gruvax/api/admin/devices.py` (bind + `src/gruvax/api/admin/profiles.py` connect) | exact |
| `src/gruvax/api/admin/router.py` | config | request-response | `src/gruvax/api/admin/router.py` (self) | exact |
| `src/gruvax/sync/profile_sync.py` | service | batch + event-driven | `src/gruvax/sync/profile_sync.py` (self — extend) | exact |
| `src/gruvax/api/admin/profiles.py` | controller | request-response | `src/gruvax/api/admin/profiles.py` (self — extend) | exact |
| `frontend/src/routes/redeem/RedeemPage.tsx` | component | request-response | `frontend/src/routes/admin/ProfileDrawer.tsx` (PAT input + connect flow) | role-match |
| `frontend/src/routes/redeem/RedeemPage.css` | config | — | `frontend/src/routes/admin/ProfileDrawer.tsx` (CSS module pattern) | role-match |
| `frontend/src/api/inviteClient.ts` | service | request-response | `frontend/src/api/adminClient.ts` | role-match |
| `frontend/src/api/types.ts` | model | — | `frontend/src/api/types.ts` (self — extend) | exact |
| `frontend/src/routes/admin/ProfileDrawer.tsx` | component | request-response | `frontend/src/routes/admin/ProfileDrawer.tsx` (self — extend) | exact |
| `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` | component | event-driven | `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` (self — extend) | exact |
| `frontend/src/routes/kiosk/KioskView.tsx` | component | event-driven | `frontend/src/routes/kiosk/KioskView.tsx` (self — extend) | exact |
| `frontend/src/App.tsx` | config | — | `frontend/src/App.tsx` (self — extend) | exact |
| `tests/integration/test_invite_codes.py` | test | request-response | `tests/integration/test_devices.py` | exact |

---

## Pattern Assignments

---

### `migrations/versions/0012_invite_codes_and_first_seen_at.py` (migration, batch)

**Analog:** `migrations/versions/0011_devices_and_pairing_codes.py`

**File header + revision declarations** (lines 1–52):
```python
"""Create profile_invite_codes table + first_seen_at column (Phase 7 / AUTH-02, API-04).

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-XX

Phase 7 / v2.1:
  gruvax.profile_invite_codes — single-use, 1-hour TTL invite tokens for member self-connect.
    UUID PK (not CHAR(4)); profile_id FK ON DELETE CASCADE; consumed_at one-shot guard.
    Atomicity: UPDATE ... WHERE consumed_at IS NULL AND expires_at > NOW() RETURNING profile_id.

  gruvax.profile_collection.first_seen_at — GRUVAX-cache arrival timestamp.
    Nullable for backfill; set to NOW() on staging-INSERT going forward.

  gruvax.profiles.last_new_record_count, .last_sync_is_initial — stored diff state.
    Persists until next sync (D-08). Updated atomically inside _swap_inside_tx.

Conventions (carried from 0001-0011):
  - from __future__ import annotations; from alembic import op
  - revision = "0012"; down_revision = "0011"; branch_labels/depends_on = None
  - ALL SQL as module-level string constants; op.execute(_CONST) in upgrade()/downgrade()
  - Never inline triple-quoted strings inside functions; never f-strings (bandit B608)
  - downgrade() fully reverses upgrade()
"""

from __future__ import annotations

from alembic import op


revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | None = None
depends_on: str | None = None
```

**CREATE TABLE constant pattern** (analog lines 89–97):
```python
# Copy structure from _CREATE_PAIRING_CODES. Swap CHAR(4) → UUID, fingerprint → profile_id FK,
# 5-minute → 1-hour TTL, FK ON DELETE CASCADE (invite invalidated when profile deleted, D-11).
_CREATE_INVITE_CODES = (
    "CREATE TABLE IF NOT EXISTS gruvax.profile_invite_codes ("
    "  code UUID PRIMARY KEY DEFAULT gen_random_uuid(),"
    "  profile_id UUID NOT NULL REFERENCES gruvax.profiles(id) ON DELETE CASCADE,"
    "  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),"
    "  expires_at TIMESTAMPTZ NOT NULL,"
    "  consumed_at TIMESTAMPTZ"
    ")"
)
```

**Index pattern** (analog lines 139–141):
```python
# Plain index on expires_at for TTL-based cleanup + expiry checks.
# Mirrors idx_pairing_codes_expires from 0011.
_IDX_INVITE_CODES_EXPIRES = (
    "CREATE INDEX IF NOT EXISTS idx_profile_invite_codes_expires"
    " ON gruvax.profile_invite_codes (expires_at)"
)

# Index on profile_id for the "void prior invite for this profile" query (D-09).
_IDX_INVITE_CODES_PROFILE = (
    "CREATE INDEX IF NOT EXISTS idx_profile_invite_codes_profile"
    " ON gruvax.profile_invite_codes (profile_id)"
)
```

**ALTER TABLE pattern** (no direct analog — new for this phase):
```python
# Add first_seen_at to profile_collection — nullable for online migration (Pitfall 3).
_ADD_FIRST_SEEN_AT = (
    "ALTER TABLE gruvax.profile_collection"
    " ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ"
)

# Add stored diff columns to profiles (D-08: persists until next sync).
_ADD_PROFILE_DIFF_COLUMNS = (
    "ALTER TABLE gruvax.profiles"
    " ADD COLUMN IF NOT EXISTS last_new_record_count BIGINT DEFAULT 0,"
    " ADD COLUMN IF NOT EXISTS last_sync_is_initial BOOLEAN DEFAULT FALSE"
)
```

**upgrade() / downgrade() pattern** (analog lines 157–179):
```python
def upgrade() -> None:
    op.execute(_CREATE_INVITE_CODES)
    op.execute(_IDX_INVITE_CODES_EXPIRES)
    op.execute(_IDX_INVITE_CODES_PROFILE)
    op.execute(_ADD_FIRST_SEEN_AT)
    op.execute(_ADD_PROFILE_DIFF_COLUMNS)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS gruvax.idx_profile_invite_codes_profile")
    op.execute("DROP INDEX IF EXISTS gruvax.idx_profile_invite_codes_expires")
    op.execute("DROP TABLE IF EXISTS gruvax.profile_invite_codes")
    op.execute(
        "ALTER TABLE gruvax.profile_collection DROP COLUMN IF EXISTS first_seen_at"
    )
    op.execute(
        "ALTER TABLE gruvax.profiles"
        " DROP COLUMN IF EXISTS last_new_record_count,"
        " DROP COLUMN IF EXISTS last_sync_is_initial"
    )
```

---

### `src/gruvax/api/invite_codes.py` (controller, request-response)

**Analogs:**
- Owner-side (generate + void): `src/gruvax/api/admin/profiles.py:430–522` (connect_pat flow)
- Member-side (consume + PAT store): same
- Atomic consume SQL: `src/gruvax/api/admin/devices.py:80–87` (`_BIND_CODE`)
- Rate limiting: `src/gruvax/api/admin/devices.py:172–189` (`_check_bind_rate_limit`)

**Imports pattern** (analog: devices.py lines 21–37, profiles.py lines 28–56):
```python
from __future__ import annotations

import logging
from typing import Any
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.api.admin.limiter import _rate_limiter
from gruvax.api.admin.profile_sync import _run_sync_background
from gruvax.api.deps import get_pool, require_admin
from gruvax.discogsography.errors import NetworkError, PATRejected, RateLimitExhausted, ServerError
from gruvax.settings import settings
from gruvax.sync import profile_sync
from gruvax.sync.pat_crypto import encrypt_pat
```

**SQL constants pattern** (analog: devices.py lines 73–87 and profiles.py connect flow):
```python
# Void prior unredeemed invite for a profile (D-09 one-active-per-profile rule).
# Both steps run in one transaction (Pitfall 5 context: void + insert must be atomic).
_VOID_PRIOR_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE profile_id = %s::uuid"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
)

# Insert a new 1-hour invite code (D-01 TTL).
_INSERT_INVITE = (
    "INSERT INTO gruvax.profile_invite_codes (code, profile_id, expires_at)"
    " VALUES (gen_random_uuid(), %s::uuid, NOW() + INTERVAL '1 hour')"
    " RETURNING code::text, expires_at"
)

# Atomic "first wins" consume — PostgreSQL READ COMMITTED row lock.
# Returns profile_id so we know which profile this invite is for.
# Uniform: does NOT distinguish expired from consumed from non-existent (Pitfall 2).
_CONSUME_INVITE = (
    "UPDATE gruvax.profile_invite_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s::uuid"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING profile_id"
)

# Lookup invite by code for the public GET (validate without consuming).
_SELECT_INVITE = (
    "SELECT p.display_name, pic.expires_at"
    " FROM gruvax.profile_invite_codes pic"
    " JOIN gruvax.profiles p ON p.id = pic.profile_id"
    " WHERE pic.code = %s::uuid"
    "   AND pic.consumed_at IS NULL"
    "   AND pic.expires_at > NOW()"
    "   AND p.deleted_at IS NULL"
)
```

**Rate-limit pattern** (analog: devices.py lines 172–189):
```python
# Parsed once at module load (Pitfall 1 guard: no re-parse on every request).
_REDEEM_RATE = parse_limit("5/10minutes")   # per-IP throttle on public endpoint

def _check_redeem_rate_limit(request: Request) -> None:
    """Enforce per-IP rate limit on the public redeem endpoint."""
    client_ip: str = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_REDEEM_RATE, "invite_redeem", client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"type": "rate_limited", "message": "Too many attempts. Wait a moment and try again."},
        )
```

**Owner-side generate endpoint** (analog: profiles.py connect_pat lines 430–522):
```python
@router.post("/profiles/{profile_id}/invite")
async def generate_invite(
    profile_id: str,
    request: Request,
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
    """Generate a one-time invite link for a profile (PIN-gated, D-09).

    Voids any prior unredeemed invite for the same profile (D-09) and inserts
    a new UUID code with a 1-hour TTL (D-01). Both in one transaction.
    Returns {code, url, expires_at}.
    """
    uid = _parse_uuid(profile_id)
    db_pool = request.app.state.db_pool

    async with db_pool.connection() as conn, conn.cursor() as cur:
        # D-09: void prior before inserting new (single transaction).
        await cur.execute(_VOID_PRIOR_INVITE, (str(uid),))
        await cur.execute(_INSERT_INVITE, (str(uid),))
        row = await cur.fetchone()
        await conn.commit()

    code_str, expires_at = row
    url = str(request.base_url) + f"redeem/{code_str}"
    return JSONResponse(content={
        "code": code_str,
        "url": url,
        "expires_at": expires_at.isoformat(),
    })
```

**Public GET endpoint (validate without consuming)** (no close analog — new pattern):
```python
@public_router.get("/invite-codes/{code}")
async def get_invite(code: str, pool: Any = Depends(get_pool)) -> JSONResponse:
    """Public: validate a code and return the profile display_name.

    Pitfall 8: this router is registered on the main app, NOT under /admin.
    Returns 404 for all negative cases (expired/used/invalid) — no oracle (Pitfall 2).
    """
    try:
        code_uuid = uuid.UUID(code)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"type": "invite_not_found"}) from None

    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_SELECT_INVITE, (str(code_uuid),))
        row = await cur.fetchone()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"type": "invite_not_found"})

    display_name, expires_at = row
    return JSONResponse(content={"display_name": display_name,
                                 "expires_at": expires_at.isoformat()})
```

**Public POST redeem endpoint** (analog: profiles.py connect_pat lines 450–522, devices.py bind_device lines 241–336):
```python
@public_router.post("/invite-codes/{code}/redeem")
async def redeem_invite(
    code: str,
    request: Request,
    body: RedeemRequest,
    background_tasks: BackgroundTasks,
    pool: Any = Depends(get_pool),
) -> JSONResponse:
    """Public: validate PAT, store encrypted, auto-sync.

    Pool-isolation discipline (Pitfall 1 analog / profiles.py Pitfall 6):
      1. Consume invite (pool acquired + released) — tight checkout.
      2. Validate PAT via _run_test_sync (NO pool slot held during HTTP call).
      3. User-id collision check (new pool slot + released).
      4. Store encrypted PAT (new pool slot + released).
      5. Add BackgroundTask for sync.

    Error taxonomy (all negative invite cases → 404, no oracle — Pitfall 2):
      404 invite_not_found — expired, consumed, or non-existent
      401 pat_rejected     — discogsography returned 401/403
      409 user_id_collision — user_id already on another profile
      503 upstream_unavailable — rate-limited or server error from discogsography
    """
    _check_redeem_rate_limit(request)

    try:
        code_uuid = uuid.UUID(code)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"type": "invite_not_found"}) from None

    # Step 1: atomic consume (pool acquired + released before HTTP call — Pitfall 1).
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(_CONSUME_INVITE, (str(code_uuid),))
        row = await cur.fetchone()
        await conn.commit()

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail={"type": "invite_not_found"})

    profile_id: str = str(row[0])

    # Step 2: validate PAT — no pool slot held during HTTP call (mirrors connect_pat).
    try:
        new_user_id = await _run_test_sync(body.pat)
    except PATRejected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail={"type": "pat_rejected"}) from None
    except RateLimitExhausted as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"type": "upstream_unavailable", "message": str(exc)}) from exc
    except (ServerError, NetworkError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail={"type": "upstream_unavailable", "message": str(exc)}) from exc

    # Step 3: collision check (mirrors connect_pat lines 476–497).
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles"
            " WHERE discogsography_user_id = %s::uuid"
            "   AND id != %s::uuid AND deleted_at IS NULL",
            (new_user_id, profile_id),
        )
        collision = await cur.fetchone()

    if collision is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail={"type": "user_id_collision"})

    # Step 4: store encrypted PAT + flip revoked=FALSE (mirrors connect_pat lines 499–512).
    ciphertext = encrypt_pat(body.pat)
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE gruvax.profiles SET"
            "    app_token_encrypted = %s::bytea,"
            "    app_token_revoked = FALSE,"
            "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid),"
            "    last_sync_status = NULL,"
            "    last_sync_error = NULL"
            " WHERE id = %s::uuid AND deleted_at IS NULL",
            (ciphertext, new_user_id, profile_id),
        )
        await conn.commit()

    # Step 5: kick background sync (D-04 auto-sync mirrors connect_pat lines 514–519).
    background_tasks.add_task(
        _run_sync_background,
        profile_id=profile_id,
        app_state=request.app.state,
    )

    return JSONResponse(content={"status": "connected", "profile_id": profile_id})
```

---

### `src/gruvax/api/admin/router.py` (config — extend)

**Analog:** `src/gruvax/api/admin/router.py` (self)

**Registration pattern** (lines 18–56 — copy pattern, add invite owner-side router):
```python
# Add to existing imports:
from gruvax.api.invite_codes import owner_router as invite_owner_router

# Inside create_admin_router(), add alongside other include_router calls:
router.include_router(invite_owner_router)
```

The public member-facing router from `invite_codes.py` (`public_router`) is registered directly on the main FastAPI app in `app.py` — NOT inside `create_admin_router()`. See the Pitfall 8 note in RESEARCH.md.

---

### `src/gruvax/sync/profile_sync.py` (service — extend `_swap_inside_tx` and `_refresh_profile_caches`)

**Analog:** `src/gruvax/sync/profile_sync.py` (self — verified lines 281–356)

**Current `_swap_inside_tx` signature** (lines 281–286):
```python
async def _swap_inside_tx(
    conn: AsyncConnection[Any],
    profile_id: str,
    row_count: int,
    user_id: str,
) -> None:
```

**Extended signature — returns diff result:**
```python
async def _swap_inside_tx(
    conn: AsyncConnection[Any],
    profile_id: str,
    row_count: int,
    user_id: str,
) -> tuple[int, bool]:
    """Returns (new_record_count, is_initial_import)."""
```

**Pre-swap capture pattern** (Pitfall 4 — read last_sync_at BEFORE the UPDATE):
```python
# Capture is_initial_import BEFORE the UPDATE sets last_sync_at (Pitfall 4).
async with conn.cursor() as cur:
    await cur.execute(
        "SELECT last_sync_at IS NULL AS is_initial FROM gruvax.profiles"
        " WHERE id = %s::uuid",
        (profile_id,),
    )
    row = await cur.fetchone()
    is_initial_import: bool = bool(row[0]) if row else True
```

**Arrival count — pre-DELETE count pattern** (RESEARCH.md Pattern 4 recommended approach):
```python
# Count existing rows that match staging rows (pre-DELETE count for arrivals).
# Runs inside the same transaction — TEMP table is still in scope (Pitfall 3 invariant).
async with conn.cursor() as cur:
    await cur.execute(
        "SELECT COUNT(*) FROM gruvax.profile_collection pc"
        " JOIN profile_collection_staging s"
        "   ON pc.release_id = s.release_id"
        "  AND pc.folder_id IS NOT DISTINCT FROM s.folder_id"
        " WHERE pc.profile_id = %s::uuid",
        (profile_id,),
    )
    existing_row = await cur.fetchone()
    existing_count: int = int(existing_row[0]) if existing_row else 0

new_record_count: int = max(0, row_count - existing_count)
```

**Existing DELETE + INSERT pattern** (lines 294–304 — extend INSERT to add `first_seen_at`):
```python
# Existing DELETE (line 294–296 — unchanged):
await conn.execute(
    "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
    (profile_id,),
)

# Extended INSERT adds first_seen_at = NOW() for all rows in this sync (API-04).
# NULL-able column: existing rows from before migration retain NULL (Pitfall 3).
await conn.execute(
    "INSERT INTO gruvax.profile_collection"
    " (profile_id, release_id, folder_id, artist, title,"
    "  label, catalog_number, year, first_seen_at)"
    " SELECT %s::uuid, release_id, folder_id, artist, title,"
    "        label, catalog_number, year, NOW()"
    " FROM profile_collection_staging",
    (profile_id,),
)
```

**Existing UPDATE pattern** (lines 305–315 — extend with diff columns):
```python
# Extended UPDATE adds last_new_record_count + last_sync_is_initial (D-08, Pattern 7).
await conn.execute(
    "UPDATE gruvax.profiles SET"
    "    last_sync_at = NOW(),"
    "    last_sync_status = 'ok',"
    "    last_sync_item_count = %s,"
    "    last_sync_error = NULL,"
    "    discogsography_user_id = COALESCE(discogsography_user_id, %s::uuid),"
    "    app_token_revoked = FALSE,"
    "    last_new_record_count = %s,"
    "    last_sync_is_initial = %s"
    " WHERE id = %s::uuid",
    (row_count, user_id, new_record_count, is_initial_import, profile_id),
)
return new_record_count, is_initial_import
```

**Current `_refresh_profile_caches` SSE publish** (lines 354–356):
```python
# Current (line 354–356):
await bus.publish("collection_changed", {"profile_id": profile_id})
```

**Extended publish** — caller passes diff result through from `_swap_inside_tx`:
```python
# Extended (Pattern 5 from RESEARCH.md):
await bus.publish("collection_changed", {
    "profile_id": profile_id,
    "new_record_count": new_record_count,    # int >= 0
    "is_initial_import": is_initial_import,  # bool
})
```

The caller (`sync_profile`) must thread `(new_record_count, is_initial_import)` from `_swap_inside_tx`'s return value into `_refresh_profile_caches` — update both function signatures accordingly.

---

### `src/gruvax/api/admin/profiles.py` (controller — extend list/get SELECT)

**Analog:** `src/gruvax/api/admin/profiles.py` (self — verified lines 183–275)

**Current SELECT in `list_profiles`** (lines 194–197):
```python
await cur.execute(
    "SELECT id, display_name, last_sync_at, last_sync_status, "
    "       last_sync_item_count, app_token_revoked, last_sync_error "
    "FROM gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at",
)
```

**Extended SELECT — add `has_token` derivation + diff columns** (Pitfall 7 fix):
```python
await cur.execute(
    "SELECT id, display_name, last_sync_at, last_sync_status,"
    "       last_sync_item_count, app_token_revoked, last_sync_error,"
    "       (app_token_encrypted IS NOT NULL AND length(app_token_encrypted) > 1)::bool AS has_token,"
    "       last_new_record_count, last_sync_is_initial"
    " FROM gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at",
)
```

**Response serialization — add new fields** (current pattern lines 212–228):
```python
# Add to each profile dict:
"has_token": bool(row[has_token_idx]),
"last_new_record_count": row[last_new_record_count_idx],
"last_sync_is_initial": bool(row[last_sync_is_initial_idx]),
```

Apply the same SELECT and serialization extension to `get_profile` (lines 244–274).

---

### `frontend/src/routes/redeem/RedeemPage.tsx` (component, request-response)

**Analog:** `frontend/src/routes/admin/ProfileDrawer.tsx` (PAT input + connect flow pattern)

**Imports pattern** (ProfileDrawer.tsx lines 28–42):
```typescript
import { useCallback, useEffect, useState } from 'react'
import { Eye, EyeOff, Loader2, CheckCircle2 } from 'lucide-react'
import { getInviteCode, redeemInviteCode } from '../../api/inviteClient'
import type { InviteCodeInfo, RedeemResult } from '../../api/types'
```

**PAT input + show/hide toggle pattern** (ProfileDrawer.tsx lines 89–100 state + render pattern):
```typescript
// State
const [patValue, setPatValue] = useState('')
const [showPat, setShowPat] = useState(false)
const [isSubmitting, setIsSubmitting] = useState(false)
const [error, setError] = useState<string | null>(null)

// PAT input JSX (copy from ProfileDrawer PAT field):
<input
  id="pat-input"
  type={showPat ? 'text' : 'password'}
  value={patValue}
  onChange={(e) => setPatValue(e.target.value)}
  placeholder="Paste your token here"
  autoComplete="off"
  className="redeem-pat-input"
  disabled={isSubmitting}
/>
<button
  type="button"
  className="redeem-pat-toggle"
  aria-label={showPat ? 'Hide token' : 'Show token'}
  onClick={() => setShowPat((v) => !v)}
>
  {showPat ? <EyeOff size={16} /> : <Eye size={16} />}
</button>
```

**Error mapping pattern** (ProfileDrawer.tsx lines 48–68 `mapConnectError`):
```typescript
function mapRedeemError(err: unknown): string {
  if (err instanceof RedeemApiError) {
    switch (err.errorType) {
      case 'pat_rejected':
        return "This token was not accepted. Check that it's valid and has collection access, then try again."
      case 'user_id_collision':
        return 'This token belongs to someone who already has a profile. Each person needs their own token.'
      case 'upstream_unavailable':
        return 'Could not reach Discogs right now. Try again in a moment.'
      default:
        return 'Something went wrong. Try again in a moment.'
    }
  }
  return 'Something went wrong. Try again in a moment.'
}
```

**Page load sequence** (UI-SPEC §Interaction Contracts):
```typescript
type PageState = 'loading' | 'invalid' | 'active' | 'submitting' | 'success'

useEffect(() => {
  setPageState('loading')
  getInviteCode(code)
    .then((info) => {
      setCodeInfo(info)
      setPageState('active')
    })
    .catch(() => setPageState('invalid'))
}, [code])
```

**Terminal success state** (UI-SPEC §Surface 1 terminal success state):
```typescript
// When pageState === 'success':
<div role="status" className="redeem-success">
  <CheckCircle2 size={32} className="redeem-success-icon" />
  <h1 className="redeem-success-heading">CONNECTED</h1>
  <p className="redeem-success-body">Your collection is importing. You can close this page.</p>
</div>
```

**Error state for invalid/expired codes** (UI-SPEC §States):
```typescript
// When pageState === 'invalid':
<div role="alert" className="redeem-error-card">
  <p>This invite link has expired. Ask the owner to send you a new one.</p>
</div>
```

---

### `frontend/src/routes/redeem/RedeemPage.css` (config)

**Analog:** `frontend/src/routes/admin/ProfileDrawer.tsx` (CSS module naming convention)

All CSS must use `var(--gruvax-*)` tokens exclusively. Key classes from UI-SPEC:
- `.redeem-page` — `min-height: 100dvh` (mobile viewport), centered card
- `.redeem-card` — `max-width: 480px; margin: 0 auto; padding: var(--gruvax-space-5)`
- `.redeem-pat-input` — focus ring `outline: 2px solid var(--gruvax-yellow)` (not `--gruvax-blue`)
- `.redeem-cta-btn` — `background: var(--gruvax-blue); color: var(--gruvax-white); min-height: 44px; width: 100%`
- `.redeem-success-icon` — `color: var(--gruvax-success)`
- `.redeem-success-heading` — `color: var(--gruvax-success)`

---

### `frontend/src/api/inviteClient.ts` (service, request-response)

**Analog:** `frontend/src/api/adminClient.ts` (lines 1–80 structure)

**Key difference:** invite GET/POST redeem routes are public — no CSRF token, no admin session cookie required. Use plain `fetch` with `credentials: 'omit'` for the public endpoints. The owner-side `POST /api/admin/profiles/{id}/invite` uses `adminFetch` (CSRF + session).

**Public fetch pattern** (new — no analog for public routes):
```typescript
/** Public fetch — no CSRF, no session cookie (redeem endpoints). */
async function publicFetch(path: string, options: RequestInit = {}): Promise<Response> {
  return fetch(path, {
    ...options,
    credentials: 'omit',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string>),
    },
  })
}

export async function getInviteCode(code: string): Promise<InviteCodeInfo> {
  const res = await publicFetch(`/api/invite-codes/${code}`)
  if (!res.ok) throw new RedeemApiError(await res.json())
  return res.json() as Promise<InviteCodeInfo>
}

export async function redeemInviteCode(code: string, pat: string): Promise<RedeemResult> {
  const res = await publicFetch(`/api/invite-codes/${code}/redeem`, {
    method: 'POST',
    body: JSON.stringify({ pat }),
  })
  if (!res.ok) throw new RedeemApiError(await res.json())
  return res.json() as Promise<RedeemResult>
}
```

**Owner-side generate invite** (uses `adminFetch` from adminClient.ts):
```typescript
import { adminFetch } from './adminClient'

export async function generateInvite(profileId: string): Promise<GeneratedInvite> {
  const res = await adminFetch(`/api/admin/profiles/${profileId}/invite`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to generate invite')
  return res.json() as Promise<GeneratedInvite>
}
```

---

### `frontend/src/api/types.ts` (model — extend)

**Analog:** `frontend/src/api/types.ts` (self — verified lines 384–412)

**Extend `AdminProfile`** (current lines 385–394 — add three fields):
```typescript
export interface AdminProfile {
  id: string
  display_name: string
  last_sync_at: string | null
  last_sync_status: 'ok' | 'failed' | 'in_progress' | null
  last_sync_error: string | null
  last_sync_item_count: number | null
  app_token_revoked: boolean
  status: ProfileStatus
  // Phase 7 additions:
  has_token: boolean                     // derived server-side (Pitfall 7)
  last_new_record_count: number          // 0 if no sync yet
  last_sync_is_initial: boolean          // true on first-ever sync (D-07)
}
```

**New invite types** (add after existing profile types):
```typescript
/** Response from GET /api/invite-codes/{code} — public validation. */
export interface InviteCodeInfo {
  display_name: string
  expires_at: string   // ISO-8601
}

/** Response from POST /api/admin/profiles/{id}/invite. */
export interface GeneratedInvite {
  code: string
  url: string
  expires_at: string   // ISO-8601
}

/** Response from POST /api/invite-codes/{code}/redeem. */
export interface RedeemResult {
  status: 'connected'
  profile_id: string
}
```

---

### `frontend/src/routes/admin/ProfileDrawer.tsx` (component — extend)

**Analog:** `frontend/src/routes/admin/ProfileDrawer.tsx` (self — verified lines 1–100)

**New state** (add alongside existing `connectState`, `drawerMode` etc.):
```typescript
// Invite section state
const [inviteInfo, setInviteInfo] = useState<GeneratedInvite | null>(null)
const [inviteError, setInviteError] = useState<string | null>(null)
const [isGeneratingInvite, setIsGeneratingInvite] = useState(false)
const [copiedAt, setCopiedAt] = useState<number | null>(null)   // for 2s "COPIED!" feedback
```

**TTL countdown pattern** (UI-SPEC §Interaction Contracts):
```typescript
// Count down from expires_at — setInterval cleared on unmount or when inviteInfo changes.
useEffect(() => {
  if (!inviteInfo) return
  const interval = setInterval(() => {
    const secsLeft = Math.max(0, Math.floor((new Date(inviteInfo.expires_at).getTime() - Date.now()) / 1000))
    setTtlSeconds(secsLeft)
    if (secsLeft === 0) setInviteInfo(null)   // auto-expire in UI
  }, 1000)
  return () => clearInterval(interval)
}, [inviteInfo])
```

**Copy-to-clipboard pattern** (UI-SPEC §Copy Flow):
```typescript
const handleCopyLink = useCallback(async () => {
  if (!inviteInfo) return
  try {
    await navigator.clipboard.writeText(inviteInfo.url)
    setCopiedAt(Date.now())
    setTimeout(() => setCopiedAt(null), 2000)
  } catch {
    setInviteError('Could not copy. Tap the link to copy manually.')
  }
}, [inviteInfo])
```

**INVITE LINK section JSX** (UI-SPEC §Surface 2 structure — add between existing action rows and DELETE PROFILE):
```tsx
{/* INVITE LINK section — shown in drawerMode === 'view' */}
<div className="profile-invite-section">
  <span className="profile-section-label">INVITE LINK</span>
  {inviteInfo ? (
    <>
      <div className="profile-invite-link-box">
        <span className="profile-invite-url">{inviteInfo.url}</span>
        <span className={`profile-invite-ttl ${ttlColor}`}>
          Expires in {formatMmSs(ttlSeconds)}
        </span>
      </div>
      <button
        type="button"
        className="profile-btn-primary"
        onClick={handleCopyLink}
      >
        {copiedAt ? 'COPIED!' : 'COPY LINK'}
      </button>
    </>
  ) : (
    <button
      type="button"
      className="profile-btn-secondary"
      onClick={handleGenerateInvite}
      disabled={isGeneratingInvite}
    >
      {isGeneratingInvite ? <><Loader2 size={16} className="spinning" /> GENERATING…</> : 'GENERATE INVITE LINK'}
    </button>
  )}
  {inviteError && <span className="sheet-error">{inviteError}</span>}
</div>
```

---

### `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` (component — extend)

**Analog:** `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` (self — verified lines 37–93)

**Existing row pattern** (lines 58–64 LAST SYNC row — copy for NEW RECORDS):
```tsx
{/* Copy existing diag-status-row pattern: */}
<div className="diag-status-row">
  <div className="diag-status-left">
    <span className="diag-row-label">LAST SYNC</span>
  </div>
  <span className="diag-cell-mono">{lastSyncLabel}</span>
</div>
```

**New NEW RECORDS row** (insert between ITEMS and LAST ERROR rows):
```tsx
{/* NEW RECORDS row — insert between ITEMS and LAST ERROR */}
<div className="diag-status-row">
  <div className="diag-status-left">
    <span className="diag-row-label">
      {profile.last_sync_is_initial ? 'IMPORTED' : 'NEW RECORDS'}
    </span>
  </div>
  <span
    className="diag-cell-mono"
    style={{
      color: (profile.last_new_record_count ?? 0) > 0
        ? 'var(--gruvax-success)'
        : 'var(--gruvax-text-muted)',
    }}
  >
    {profile.last_new_record_count != null && profile.last_new_record_count > 0
      ? profile.last_new_record_count.toLocaleString('en-US')
      : '—'}
  </span>
</div>
```

The `profile` prop type (`ProfileDiagnosticEntry` from adminClient.ts) must be extended with `last_new_record_count: number | null` and `last_sync_is_initial: boolean | null`.

---

### `frontend/src/routes/kiosk/KioskView.tsx` (component — extend SSE handler)

**Analog:** `frontend/src/routes/kiosk/KioskView.tsx` (self — verified lines 338–356)

**Current handler** (lines 342–345 — no-argument form, no JSON parse):
```typescript
es.addEventListener('collection_changed', () => {
  void queryClient.invalidateQueries({ queryKey: ['search'] })
  resync()
})
```

**Extended handler** (RESEARCH.md Pattern 5 — add payload parsing, backward-compatible):
```typescript
es.addEventListener('collection_changed', (e) => {
  void queryClient.invalidateQueries({ queryKey: ['search'] })
  resync()
  // Parse extended payload (Phase 7 — backward-compatible: e.data may be absent/empty).
  try {
    const payload = e.data ? (JSON.parse(e.data) as Record<string, unknown>) : {}
    const count = typeof payload.new_record_count === 'number' ? payload.new_record_count : 0
    const isInitial = Boolean(payload.is_initial_import)
    if (count > 0) setNewRecordState({ count, isInitial })
  } catch {
    // Graceful degrade — no indicator shown (T-05-04 accept).
  }
})
```

**New kiosk pill state**:
```typescript
const [newRecordState, setNewRecordState] = useState<{ count: number; isInitial: boolean } | null>(null)

// Clear on next collection_changed — the handler above replaces the value.
// Pill renders when newRecordState !== null && newRecordState.count > 0.
```

**Kiosk pill JSX** (UI-SPEC §Surface 3 kiosk indicator):
```tsx
{newRecordState && newRecordState.count > 0 && (
  <div
    role="status"
    aria-live="polite"
    aria-label={
      newRecordState.isInitial
        ? `Imported ${newRecordState.count} records`
        : `${newRecordState.count} new records since last sync`
    }
    className="kiosk-new-records-pill"
  >
    <span className="kiosk-pill-count">{newRecordState.count.toLocaleString('en-US')}</span>
    {' '}
    {newRecordState.isInitial ? 'IMPORTED RECORDS' : 'NEW RECORDS'}
  </div>
)}
```

CSS for `.kiosk-new-records-pill`: `background: var(--gruvax-yellow); color: var(--gruvax-blue-darker); border-radius: var(--gruvax-radius-pill); font: 700 18px var(--gruvax-font-display)`.

---

### `frontend/src/App.tsx` (config — extend routes)

**Analog:** `frontend/src/App.tsx` (self — verified lines 131–168)

**Add import** (follow existing pattern at top of file):
```typescript
import { RedeemPage } from './routes/redeem/RedeemPage'
```

**Add route** (inside `<Routes>` before the `/admin` nest, outside the AdminShell guard):
```tsx
{/* Phase 7: public member redeem route — outside /admin PIN gate (D-03) */}
<Route path="/redeem/:code" element={<RedeemPage />} />
```

The route sits alongside `/pair` and `/select` (both also public), at the same nesting level as the `<Route path="/admin">` element.

---

### `tests/integration/test_invite_codes.py` (test, request-response)

**Analog:** `tests/integration/test_devices.py` (verified lines 1–80)

**File header + module-scoped ASGI client fixture** (copy from test_devices.py):
```python
"""Integration tests for member self-connect invite flow (AUTH-02) + collection diff (API-04).

All tests use the module-scoped ASGI client fixture pattern from test_devices.py.
Rate-limit reset autouse fixtures (reset_login_rate_limit + reset_redeem_rate_limit)
mirror the pattern in test_devices.py lines 50–75.
"""

from __future__ import annotations
import pytest
from gruvax.api.admin.limiter import limiter

@pytest.fixture(autouse=True)
def reset_rate_limits() -> None:
    limiter.reset()
```

**Module-scoped client fixture** (copy from test_devices.py lines 78+):
```python
@pytest_asyncio.fixture(scope="module")
async def client():
    """Module-scoped ASGI httpx client. Same pattern as test_devices.py."""
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient
    from gruvax.app import create_app

    app = create_app()
    async with LifespanManager(app) as manager:
        async with AsyncClient(
            transport=ASGITransport(app=manager.app),
            base_url="http://test",
        ) as c:
            yield c
```

**Login helper** (copy from test_devices.py login pattern):
```python
async def _login(client) -> dict:
    """POST /api/admin/login and return the response cookies."""
    resp = await client.post("/api/admin/login", json={"pin": _TEST_PIN})
    assert resp.status_code == 200
    return resp.cookies
```

**Test structure** (follows test_devices.py naming convention):
```python
async def test_generate_invite(client): ...
async def test_new_invite_voids_prior(client): ...
async def test_get_valid_code(client): ...
async def test_redeem_success(client): ...
async def test_redeem_second_use_rejected(client): ...
async def test_redeem_bad_pat(client): ...
async def test_redeem_expired(client): ...
async def test_profile_has_token_field(client): ...
async def test_redeem_rotates_token(client): ...
async def test_initial_import_flag(client): ...
async def test_arrival_count_accuracy(client): ...
async def test_profile_new_record_fields(client): ...
```

---

## Shared Patterns

### Atomic Single-Use Token Consume
**Source:** `src/gruvax/api/admin/devices.py` lines 80–87 (`_BIND_CODE`)
**Apply to:** `_CONSUME_INVITE` SQL constant in `invite_codes.py`
```python
_BIND_CODE = (
    "UPDATE gruvax.pairing_codes"
    " SET consumed_at = NOW()"
    " WHERE code = %s"
    "   AND consumed_at IS NULL"
    "   AND expires_at > NOW()"
    " RETURNING fingerprint"
)
```
The invite analog swaps `gruvax.pairing_codes` → `gruvax.profile_invite_codes`, `code = %s` → `code = %s::uuid`, and `RETURNING fingerprint` → `RETURNING profile_id`.

### PAT Encryption at Rest
**Source:** `src/gruvax/sync/pat_crypto.py` lines 71–101 (`encrypt_pat`, `decrypt_pat`)
**Apply to:** `invite_codes.py` redeem endpoint (step 4 — encrypt before INSERT)
```python
def encrypt_pat(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())
```
Import and call exactly as `connect_pat` does (profiles.py line 500): `ciphertext = encrypt_pat(body.pat)`.

### PAT Validation via `_run_test_sync`
**Source:** `src/gruvax/api/admin/profiles.py` lines 145–158
**Apply to:** `invite_codes.py` redeem endpoint (step 2) — reuse verbatim.
```python
async def _run_test_sync(pat: str) -> str:
    client = profile_sync._make_client(settings.DISCOGSOGRAPHY_BASE_URL, pat)
    try:
        page = await client._get_page(limit=1, offset=0)
        user_id = str(page["user_id"])
    finally:
        with contextlib.suppress(Exception):
            await client.aclose()
    return user_id
```
Import from `profiles.py` or duplicate into `invite_codes.py` (prefer import to avoid drift).

### Pool-Isolation Discipline (Pitfall 6 analog)
**Source:** `src/gruvax/api/admin/profiles.py` lines 453–512 (`connect_pat` flow)
**Apply to:** `invite_codes.py` redeem endpoint
Pattern: pool slot acquired → released → HTTP call (no pool slot held) → pool slot acquired → released. Never wrap the `_run_test_sync` call inside an `async with pool.connection()` block.

### Rate Limiting
**Source:** `src/gruvax/api/admin/limiter.py` (entire file) + `devices.py` lines 172–189
**Apply to:** `invite_codes.py` public redeem endpoint
```python
from limits import parse as parse_limit
from gruvax.api.admin.limiter import _rate_limiter, limiter

_REDEEM_RATE = parse_limit("5/10minutes")

def _check_redeem_rate_limit(request: Request) -> None:
    client_ip = request.client.host if request.client else "unknown"
    allowed = _rate_limiter.hit(_REDEEM_RATE, "invite_redeem", client_ip)
    if not allowed:
        raise HTTPException(status_code=429, detail={"type": "rate_limited", ...})
```
Reuse the shared `limiter` singleton and `_rate_limiter` strategy. Use a distinct namespace key (`"invite_redeem"`) to avoid sharing the login or bind counter.

### Admin Router Registration
**Source:** `src/gruvax/api/admin/router.py` lines 18–56
**Apply to:** Owner-side router from `invite_codes.py`
Follow the `include_router` pattern exactly. Public member-facing router goes on the main FastAPI app (in `app.py`), not here.

### SSE Publish After Commit
**Source:** `src/gruvax/sync/profile_sync.py` lines 354–356, `src/gruvax/api/admin/devices.py` comment lines 13–18
**Apply to:** `_refresh_profile_caches` extension — publish happens AFTER the swap transaction commits, never inside it.

### Migration Module-Level SQL Constants
**Source:** `migrations/versions/0011_devices_and_pairing_codes.py` lines 33–41 conventions block
**Apply to:** `0012_invite_codes_and_first_seen_at.py`
All SQL in module-level string constants (`_CONSTANT_NAME = "..."`). `op.execute(_CONSTANT)` in `upgrade()` and `downgrade()`. No f-strings. No inline triple-quoted SQL inside functions.

### Frontend CSS Tokens
**Source:** `design/gruvax-design-tokens.css`; enforced by CLAUDE.md convention
**Apply to:** `RedeemPage.css`, all inline styles in KioskView pill, ProfileDrawer invite section
Never hardcode hex. All colors, spacing, and typography via `var(--gruvax-*)`. Exception: the PAT input focus ring uses `--gruvax-yellow` (not `--gruvax-blue`) per UI-SPEC §Color.

### AdminFetch for Mutating Admin Calls
**Source:** `frontend/src/api/adminClient.ts` lines 66–80
**Apply to:** `inviteClient.ts` `generateInvite()` (owner-side, PIN-gated)
```typescript
export async function adminFetch(path: string, options: RequestInit = {}): Promise<Response>
```
Import from `adminClient.ts` and reuse. Public redeem routes use plain `fetch` with `credentials: 'omit'`.

---

## No Analog Found

All files in Phase 7 have close analogs. No files require falling back to RESEARCH.md patterns exclusively.

| File | Role | Data Flow | Note |
|------|------|-----------|------|
| `frontend/src/routes/redeem/RedeemPage.css` | config | — | No CSS-module analog for a public standalone page; use existing token vocabulary, no new patterns needed |

---

## Metadata

**Analog search scope:** `src/gruvax/api/`, `src/gruvax/sync/`, `migrations/versions/`, `frontend/src/routes/`, `frontend/src/api/`, `tests/integration/`
**Files scanned:** 14 source files read directly
**Pattern extraction date:** 2026-06-01

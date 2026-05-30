# Phase 4: Sync Polish + Diagnostics - Pattern Map

**Mapped:** 2026-05-29
**Files analyzed:** 16 (new or modified)
**Analogs found:** 15 / 16

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `src/gruvax/sync/nightly.py` | service | event-driven | `src/gruvax/app.py` lines 313–346 (`_refresh_all_profiles_state`) | exact |
| `src/gruvax/app.py` | config/lifespan | event-driven | self — modify in place, follow surrounding lifespan conventions | — |
| `src/gruvax/api/admin/profiles.py` | controller | CRUD | self — modify in place: purge DELETE follows existing `%s::uuid` parameterized SQL pattern | — |
| `src/gruvax/api/admin/diagnostics.py` | controller | request-response | self — modify in place: per-profile section added to `return {}` dict, follows existing DB query + dict-comprehension pattern | — |
| `src/gruvax/api/admin/settings.py` | controller | request-response | self — modify in place: `sync.cadence` added to `_ALLOWED_SETTINGS_KEYS` frozenset and `key_map`; validation follows existing `_BRIGHTNESS_KEYS` / `_COLOR_KEYS` enum-check pattern | — |
| `src/gruvax/api/session.py` | controller | request-response | self — modify in place: `needs_reauth` field derived from `profiles[]` before the `content` dict is assembled | — |
| `tests/property/test_nightly_scheduler.py` | test | batch | `tests/property/test_estimator_props.py` | exact |
| `tests/unit/test_nightly_scheduler.py` | test | request-response | `tests/unit/test_admin_led_settings.py` | role-match |
| `frontend/src/routes/admin/Diagnostics.tsx` | component | request-response | self — modify in place: `ProfilesDiagnosticsSection` follows same `<section className="settings-section">` + `SectionSkeleton` pattern | — |
| `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` | component | request-response | `frontend/src/routes/admin/Diagnostics.tsx` `SystemStatusSection` / `StalenessSection` | role-match |
| `frontend/src/routes/admin/ProfileDrawer.tsx` | component | request-response | self — modify in place: re-auth badge wires `app_token_revoked → profileStatus`, elapsed counter follows `SyncProgressSection` extension pattern | — |
| `frontend/src/routes/admin/SyncProgressSection.tsx` | component | request-response | self — extend in place: add elapsed seconds counter alongside existing spinner | — |
| `frontend/src/routes/kiosk/ReauthBanner.tsx` | component | request-response | `frontend/src/routes/admin/Diagnostics.tsx` inline `diag-badge` + `diag-staleness-row` | partial |
| `frontend/src/api/adminClient.ts` | utility | request-response | self — modify in place: `ProfileDiagnosticEntry` type and `profiles[]` on `DiagnosticsData` follow existing type definitions | — |
| `frontend/src/api/session.ts` | utility | request-response | self — modify in place: add `needs_reauth?: boolean` to `SessionData` following `app_token_revoked: boolean` already present on `ProfileSummary` | — |
| `frontend/src/api/types.ts` | utility | request-response | self — modify in place: follows surrounding type conventions | — |

---

## Pattern Assignments

### `src/gruvax/sync/nightly.py` (service, event-driven) — PRIMARY NEW FILE

**Analog:** `src/gruvax/app.py` lines 313–356 (`_refresh_all_profiles_state` + task registration)

**Imports pattern** (app.py lines 28–61, representative subset):
```python
from __future__ import annotations

import asyncio
from datetime import datetime
import logging

# Internal imports from the sync layer:
from gruvax.sync.profile_sync import sync_profile
```

**Core loop pattern** (app.py lines 313–346 — COPY THIS STRUCTURE EXACTLY):
```python
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
            for pid, last_sync_at, last_sync_status, revoked in rows:
                pid_str = str(pid)
                app.state.profile_state_registry[pid_str] = {
                    "last_sync_at": last_sync_at,
                    "last_sync_status": last_sync_status,
                    "app_token_revoked": bool(revoked),
                }
                # ...
        except Exception as exc:
            logger.warning("all-profiles state refresh failed: %s", exc)
        await asyncio.sleep(60)
```

Key structural rules for `_sync_loop()`:
- `while True` with outer `try/except Exception` (NOT `BaseException`) — `asyncio.CancelledError` is a `BaseException` and passes through automatically
- Per-profile `try/except Exception` wrapping each `sync_profile()` call — one failed profile never aborts the pass
- `logger.warning(...)` for non-fatal errors; `logger.info(...)` for normal progress
- `asyncio.CancelledError` gets an explicit `raise` only if nested inside an inner `try/except` that might catch `BaseException`

**CR-01 strong-reference registration** (app.py lines 343–346 — COPY VERBATIM):
```python
_state_task = asyncio.create_task(_refresh_all_profiles_state())
# CR-01: strong reference so the GC cannot cancel the task mid-flight.
app.state.background_tasks.add(_state_task)
_state_task.add_done_callback(app.state.background_tasks.discard)
```

Add the optional exception logger callback (app.py lines 349–356):
```python
def _log_state_task_exc(t: asyncio.Task) -> None:  # type: ignore[type-arg]
    if not t.cancelled() and t.exception() is not None:
        logger.warning(
            "all_profiles_state background task exited unexpectedly: %s",
            t.exception(),
        )

_state_task.add_done_callback(_log_state_task_exc)
```

**Skip-policy SQL** (parameterized `%s`, no f-strings — bandit B608):
```python
await cur.execute(
    "SELECT id::text FROM gruvax.profiles "
    "WHERE deleted_at IS NULL "
    "  AND app_token_revoked = FALSE "
    "  AND (last_sync_status IS NULL OR last_sync_status != 'in_progress') "
    "ORDER BY created_at"
)
```

**Cadence settings read** (mirrors settings.py lines 133–137 — same `%s::uuid` + `ANY(%s)` pattern):
```python
await cur.execute(
    "SELECT value FROM gruvax.settings "
    "WHERE profile_id = %s::uuid AND key = 'sync.cadence'",
    (DEFAULT_PROFILE_UUID,)
)
```

**DST-safe `next_fire_after()` function** (pure, no analog in codebase — from RESEARCH.md Pattern 1):
```python
from datetime import datetime, timedelta

def next_fire_after(now_aware: datetime, hour: int = 3) -> datetime:
    """DST-correct next occurrence of server-local hour:00:00.
    Uses fold=1 to prefer the post-transition wall clock on any ambiguous hour.
    """
    tz = now_aware.tzinfo
    today = now_aware.date()
    candidate_naive = datetime(today.year, today.month, today.day, hour, 0, 0)
    candidate = candidate_naive.replace(tzinfo=tz, fold=1)
    if candidate <= now_aware:
        tomorrow = today + timedelta(days=1)
        candidate_naive = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, 0, 0)
        candidate = candidate_naive.replace(tzinfo=tz, fold=1)
    return candidate

def now_local() -> datetime:
    """Server-local TZ-aware datetime (respects OS/container TZ env)."""
    return datetime.now().astimezone()
```

**Purge helper** (SQL-only, follows profiles.py `%s::uuid` convention):
```python
async def _purge_profile_collection(pool, profile_id: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (profile_id,),
        )
        await conn.commit()
    logger.info("purge_profile_collection: removed rows for profile=%s", profile_id)
```

---

### `src/gruvax/app.py` — lifespan modifications

**Modify in place.** Follow the established lifespan section pattern exactly.

Three additions, placed in order after the existing `_state_task` registration (line 346):

1. **`_startup_catchup_sweep()` one-shot await** — before `asyncio.create_task(_sync_loop(...))`. Pattern: same `pool.connection()` context + sequential `await sync_profile(pid, app_state)` per stale profile. Error per profile logged with `logger.warning(...)`, never raises.

2. **`_startup_purge_sweep()` one-shot await** — same location, can be combined with catch-up sweep into one pass (planner's discretion). Uses the `DISTINCT p.id::text ... JOIN profile_collection ... WHERE p.deleted_at IS NOT NULL` predicate (D4-12). Calls `_purge_profile_collection(pool, pid)`.

3. **`_sync_loop` task registration** — identical CR-01 pattern as `_state_task` registration (lines 343–346). Place immediately after the two startup sweeps.

Section comment style follows lines 295–312 (multi-line `# ── N. Description ──` header with D-ref annotation).

---

### `src/gruvax/api/admin/profiles.py` — purge + `app_token_revoked` verification

**Modify in place.** Two surgical changes:

**Change 1 — purge call in `soft_delete_profile`** (after line 641):

The existing `soft_delete_profile` (lines 593–641) sets `deleted_at`, detaches devices, evicts registries, and returns 200. P4 adds a `BackgroundTasks` purge call. The function signature already imports `BackgroundTasks` (line 34). Add parameter:

```python
async def soft_delete_profile(
    profile_id: str,
    request: Request,
    background_tasks: BackgroundTasks,        # ← add this
    _admin: dict[str, Any] = Depends(require_admin),
) -> JSONResponse:
```

Then after `_evict_profile_registries(...)` and before the `return`:
```python
background_tasks.add_task(
    _purge_profile_collection,
    pool=request.app.state.db_pool,
    profile_id=str(uid),
)
logger.info("profile soft-deleted: id=%s; purge scheduled", str(uid))
```

**Change 2 — D4-09 verification** (connect_pat lines 471–484, rotate_pat lines 565–577):

Both already contain:
```python
await conn.execute(
    "UPDATE gruvax.profiles SET "
    "    app_token_encrypted = %s::bytea, "
    "    app_token_revoked = FALSE, "
    ...
```

Confirm `app_token_revoked = FALSE` is present — it is (VERIFIED: RESEARCH.md line 501). No code change needed; note for the plan as "verified, no action".

---

### `src/gruvax/api/admin/settings.py` — `sync.cadence` key

**Modify in place.** Three additions following the existing frozenset pattern (lines 43–113):

**Add to `_ALLOWED_SETTINGS_KEYS`** (after line 63):
```python
"sync.cadence",
```

**Add a new `_CADENCE_VALUES` frozenset** (after `_BOOL_KEYS` at line 100):
```python
_CADENCE_VALUES = frozenset({"24h", "12h", "6h", "off"})
```

**Add to `key_map`** in `update_settings` (after line 226):
```python
"sync_cadence": "sync.cadence",
```

**Add validation case** in the PUT validator loop (after the `elif db_key in _BOOL_KEYS` block, lines 289–295):
```python
elif db_key == "sync.cadence":
    value = body[body_key]
    if value not in _CADENCE_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "type": "invalid_cadence",
                "field": body_key,
                "message": f"sync.cadence must be one of {sorted(_CADENCE_VALUES)}",
            },
        )
    json_value = f'"{value}"'  # Store as JSON string — same as auth.pin_hash pattern (line 280)
```

**Add to `get_settings` return dict** following `_get_color`/`_get_int`/`_get_bool` helpers (lines 141–183):
```python
"sync_cadence": _get_color("sync.cadence", "24h").strip('"'),  # or a dedicated _get_str helper
```

Note: `auth.pin_hash` lives in the same settings table under `DEFAULT_PROFILE_UUID` (line 270). `sync.cadence` follows the exact same composite PK `(profile_id, key)` pattern.

---

### `src/gruvax/api/admin/diagnostics.py` — per-profile section extension

**Modify in place.** The existing `get_diagnostics` (lines 44–108) ends with a `return {}` dict. P4 adds one DB query block and one new `profiles` key.

Follow the **exact query + dict-comprehension pattern** from lines 88–107:
```python
# Add BEFORE the return statement:
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(
        "SELECT id::text, display_name, last_sync_at, last_sync_status, "
        "       last_sync_item_count, last_sync_error, app_token_revoked "
        "FROM gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at"
    )
    profile_rows = await cur.fetchall()

profile_diagnostics = [
    {
        "id": row[0],
        "display_name": row[1],
        "last_sync_at": row[2].isoformat() if row[2] else None,
        "last_sync_status": row[3],
        "last_sync_item_count": row[4],
        "last_sync_error": row[5],
        "app_token_revoked": bool(row[6]),
    }
    for row in profile_rows
]

return {
    # ... all existing keys unchanged ...
    "profiles": profile_diagnostics,  # D4-15
}
```

The `require_admin` guard (line 48) already covers the new data — no new auth logic needed.

---

### `src/gruvax/api/session.py` — `needs_reauth` field

**Modify in place.** The existing `get_session` builds a `content` dict (lines 77–onward). After the `profiles` list is assembled and `bound_profile_id` is resolved, derive `needs_reauth` from the already-fetched `profiles` list:

```python
# After bound_profile_id is resolved, BEFORE the content dict:
needs_reauth = False
if bound_profile_id:
    bound_profile = next(
        (p for p in profiles if str(p["id"]) == bound_profile_id), None
    )
    if bound_profile is not None:
        needs_reauth = bound_profile.get("app_token_revoked", False)

content: dict[str, Any] = {
    # ... existing keys ...
    "needs_reauth": needs_reauth,   # D4-08
}
```

No new DB query — `app_token_revoked` is already fetched in `_SELECT_ACTIVE_PROFILES` (line 51–56 of session.py).

---

### `tests/property/test_nightly_scheduler.py` (NEW — property tests)

**Analog:** `tests/property/test_estimator_props.py` (exact match for structure)

**Imports pattern** (test_estimator_props.py lines 1–27):
```python
from __future__ import annotations

from hypothesis import HealthCheck, given, settings, strategies as st
import pytest

from gruvax.sync.nightly import next_fire_after, now_local
```

**Session-scoped fixture pattern** (test_estimator_props.py lines 33–46): Not needed for pure-function tests; `next_fire_after` takes only primitives.

**`@given` + `@settings` decorator pattern** (test_estimator_props.py lines 58–80):
```python
from hypothesis import given, settings, strategies as st
from datetime import datetime, timezone, timedelta

@given(
    epoch_seconds=st.integers(
        min_value=int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()),
        max_value=int(datetime(2027, 12, 31, tzinfo=timezone.utc).timestamp()),
    ),
    hour=st.integers(min_value=0, max_value=23),
)
@settings(max_examples=500)
def test_next_fire_always_future(epoch_seconds: int, hour: int) -> None:
    """next_fire_after() always returns a time strictly after now."""
    now = datetime.fromtimestamp(epoch_seconds).astimezone()
    result = next_fire_after(now, hour)
    assert result > now
```

Two invariants required (from RESEARCH.md lines 740–760):
1. `test_next_fire_always_future` — result always > input
2. `test_next_fire_interval_in_22_26h_window` — successive 03:00 firings always [22h, 26h] apart

---

### `tests/unit/test_nightly_scheduler.py` (NEW — unit tests)

**Analog:** `tests/unit/test_admin_led_settings.py` (role-match: unit tests for a settings/service component)

**Imports + mock pattern** (test_admin_led_settings.py lines 1–30):
```python
from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient
import pytest
```

For the scheduler unit tests, mock `pool` and `sync_profile`:
- Use `unittest.mock.AsyncMock` for pool and `sync_profile`
- Test cadence anchoring with concrete `datetime` inputs (not Hypothesis — these are parametric unit tests)
- Test skip policy by stubbing the DB cursor return (revoked=TRUE profile skipped)
- Test `off` cadence: `_sync_loop` sleeps and doesn't call `sync_profile`
- Test `_read_sync_cadence` fallback: absent row → returns `"24h"`

---

### `frontend/src/routes/admin/Diagnostics.tsx` — per-profile cards section

**Modify in place.** Add `ProfilesDiagnosticsSection` as a new sub-component following the established section component pattern.

**Section component template** (Diagnostics.tsx lines 73–97, `StalenessSection`):
```tsx
interface ProfilesDiagnosticsSectionProps {
  profiles: ProfileDiagnosticEntry[]
  loading: boolean
  onSyncNow?: (profileId: string) => void
}

function ProfilesDiagnosticsSection({
  profiles,
  loading,
}: ProfilesDiagnosticsSectionProps): React.ReactElement {
  return (
    <section className="settings-section">
      <h2 className="diag-heading">PROFILES</h2>
      {loading ? (
        <SectionSkeleton />
      ) : (
        <div className="diag-profiles-grid">
          {profiles.map((p) => (
            <ProfileDiagnosticsCard key={p.id} profile={p} />
          ))}
        </div>
      )}
    </section>
  )
}
```

Add to main `Diagnostics()` return (lines 520–543) after `<SystemStatusSection .../>` and before `<RecentLogsSection .../>`:
```tsx
<ProfilesDiagnosticsSection
  profiles={data?.profiles ?? []}
  loading={isLoading && !data}
/>
```

**Polling pattern** (D4-16 — TanStack Query `refetchInterval: 30_000`): The current `Diagnostics` page uses imperative `useEffect` + manual `load()` (line 469–476). For the profiles section to poll, either:
- Convert the `getDiagnostics()` call to a `useQuery` with `refetchInterval: 30_000`, or
- Keep the existing manual-refresh pattern and note that auto-refresh is not critical for this admin screen

The planner should pick `useQuery + refetchInterval: 30_000` per D4-16. This requires changing the `useEffect`+`useState` pattern to `useQuery` — a larger refactor. Alternative: add a separate `useQuery` only for the profiles section while keeping the existing manual-refresh for the rest. Follow whichever matches the UI-SPEC more closely.

---

### `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx` (NEW)

**Analog:** `Diagnostics.tsx` `SystemStatusSection` (lines 297–369) — card with status dots, labeled rows, DM Mono values.

**Template pattern** (from `SystemStatusSection` structure):
```tsx
interface ProfileDiagnosticsCardProps {
  profile: ProfileDiagnosticEntry
}

export function ProfileDiagnosticsCard({ profile }: ProfileDiagnosticsCardProps): React.ReactElement {
  const stalenessClass = stalenessStatus(
    profile.last_sync_at ? (Date.now() - new Date(profile.last_sync_at).getTime()) / 1000 : null
  )

  return (
    <div className="diag-profile-card">
      <div className="diag-profile-card-header">
        <span className="diag-row-label">{profile.display_name.toUpperCase()}</span>
        {profile.app_token_revoked && (
          <span className="diag-badge diag-badge--warning" aria-label="Re-auth required">
            RE-AUTH REQUIRED
          </span>
        )}
      </div>
      <div className="diag-status-row">
        <span className="diag-row-label">LAST SYNC</span>
        <span className="diag-cell-mono">{formatRelativeTime(profile.last_sync_at)}</span>
        <span className={`diag-badge diag-badge--${stalenessClass}`}>
          {stalenessClass === 'ok' ? 'OK' : stalenessClass === 'stale' ? 'STALE' : 'OUTDATED'}
        </span>
      </div>
      {/* ... item count, error tag rows follow same diag-status-row pattern */}
    </div>
  )
}
```

Use the existing `formatRelativeTime` helper (Diagnostics.tsx lines 43–52) — extract to a shared `lib/time.ts` or duplicate locally. Use `stalenessStatus` (lines 36–41) for the per-profile badge color.

---

### `frontend/src/routes/admin/ProfileDrawer.tsx` — re-auth badge + elapsed counter

**Modify in place.** Two additions:

**Re-auth badge** — `profileStatus` is already derived from `currentProfile?.status` (line 283). The `_profile_status()` helper in `profiles.py` (lines 86–103) already returns `'re-auth-required'` when `app_token_revoked=True`. Wire it:
```tsx
{profileStatus === 're-auth-required' && (
  <div className="profile-reauth-banner" role="alert">
    <span className="profile-reauth-badge">RE-AUTH REQUIRED</span>
    <span className="profile-reauth-text">
      Token was rejected. Rotate PAT to resume syncing.
    </span>
  </div>
)}
```
Place in the sheet-body above the PAT input section (before line 334).

**Elapsed seconds counter** — extend `SyncProgressSection` props (see below). Thread `syncStartedAt` from `ProfileDrawer`. When `handleSyncNow()` succeeds (line 257), record `Date.now()` in a ref or state.

---

### `frontend/src/routes/admin/SyncProgressSection.tsx` — elapsed counter

**Modify in place.** Current component (lines 1–33) takes only `itemCount`. Add `syncStartedAt?: number | null`:

```tsx
interface SyncProgressSectionProps {
  itemCount: number | null | undefined
  syncStartedAt?: number | null   // ← add: Date.now() when sync was triggered
}

export function SyncProgressSection({ itemCount, syncStartedAt }: SyncProgressSectionProps) {
  const [elapsed, setElapsed] = useState<number>(0)

  useEffect(() => {
    if (!syncStartedAt) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - syncStartedAt) / 1000))
    }, 1000)
    return () => clearInterval(interval)   // cleanup on unmount / when syncStartedAt clears
  }, [syncStartedAt])

  const countText = itemCount != null
    ? `${itemCount.toLocaleString('en-US')} items processed`
    : null

  return (
    <div className="sync-progress-section" aria-live="polite" aria-busy="true">
      <div className="sync-progress-row">
        <div className="sync-progress-spinner" aria-hidden="true" />
        <span className="sync-progress-label">
          Syncing…
          {syncStartedAt && <span className="sync-progress-count"> ({elapsed}s)</span>}
        </span>
      </div>
      {countText && <p className="sync-progress-count">{countText}</p>}
    </div>
  )
}
```

Note: `sync-progress-count` CSS class already exists; it renders DM Mono 14px per UI-SPEC.

---

### `frontend/src/routes/kiosk/ReauthBanner.tsx` (NEW)

**Analog:** `Diagnostics.tsx` inline staleness badge pattern (lines 78–97) — conditional render with `aria-live`, Nordic Grid badge classes.

**No exact analog for a persistent kiosk banner.** Closest structural reference is the `StalenessSection` + `diag-badge` pattern:

```tsx
interface ReauthBannerProps {
  profileName?: string
}

export function ReauthBanner({ profileName }: ReauthBannerProps): React.ReactElement {
  return (
    <div className="reauth-banner" role="alert" aria-live="polite">
      <span className="reauth-banner-icon" aria-hidden="true">!</span>
      <span className="reauth-banner-text">
        {profileName
          ? `${profileName}: token expired — ask the owner to rotate the PAT.`
          : 'Collection token expired — ask the owner to rotate the PAT.'}
      </span>
    </div>
  )
}
```

Render in `KioskView.tsx` with a conditional: derive `needsReauth` from `sessionStore.profiles` + `boundProfileId`:
```tsx
const boundProfile = profiles.find(p => p.id === boundProfileId)
const needsReauth = boundProfile?.app_token_revoked ?? false

{needsReauth && <ReauthBanner profileName={boundProfile?.display_name} />}
```

Non-blocking: search grid, search input, and all other kiosk UI remain interactive (D4-10).

---

## Shared Patterns

### asyncio.create_task + strong-reference (CR-01)
**Source:** `src/gruvax/app.py` lines 291–293 (`app.state.background_tasks = set()`) and lines 343–346
**Apply to:** All new `asyncio.create_task()` calls in the lifespan (nightly loop)
```python
# Pattern — copy verbatim for every new long-lived task:
_task = asyncio.create_task(_some_loop(...))
app.state.background_tasks.add(_task)
_task.add_done_callback(app.state.background_tasks.discard)
```

### Parameterized SQL (bandit B608)
**Source:** Throughout `src/gruvax/api/admin/profiles.py` (e.g., lines 473–483, 620–634)
**Apply to:** All new SQL in `nightly.py` (skip-policy SELECT, cadence SELECT, purge DELETE)
```python
# Always %s placeholders, never f-strings:
await conn.execute(
    "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
    (profile_id,),
)
```

### Settings key frozenset pattern
**Source:** `src/gruvax/api/admin/settings.py` lines 43–113
**Apply to:** `sync.cadence` addition — must appear in `_ALLOWED_SETTINGS_KEYS`, have a `key_map` entry, have a dedicated validation frozenset (`_CADENCE_VALUES`), and be handled in both GET response and PUT validation loop

### `require_admin` auth guard
**Source:** `src/gruvax/api/admin/diagnostics.py` line 48 / `settings.py` line 121
**Apply to:** All new or modified admin endpoints — `Depends(require_admin)` on every mutating route, no exceptions

### `try/except Exception` + `logger.warning` per-item isolation
**Source:** `src/gruvax/app.py` lines 339–341 (per-profile state refresh error handling)
**Apply to:** Per-profile iteration in `_sync_loop`, startup sweeps, purge sweep — each profile's error is logged and discarded, never propagates to cancel the loop

### Nordic Grid section component
**Source:** `frontend/src/routes/admin/Diagnostics.tsx` lines 73–97 (`StalenessSection`)
**Apply to:** `ProfilesDiagnosticsSection`, `ProfileDiagnosticsCard`
- Container: `<section className="settings-section">`
- Heading: `<h2 className="diag-heading">UPPER CASE LABEL</h2>`
- Loading: `{loading ? <SectionSkeleton /> : <content />}`
- Badges: `diag-badge diag-badge--{ok|stale|outdated|warning}`
- Status rows: `diag-status-row` > `diag-status-left` + `diag-status-dot--{ok|warning|error}` + `diag-row-label`
- Mono values: `diag-cell-mono` (DM Mono)

### 202+poll `refetchInterval` pattern
**Source:** `frontend/src/routes/admin/ProfileDrawer.tsx` lines 128–136
**Apply to:** `ProfileDiagnosticsCard` TanStack Query for diagnostics polling (30s); per-card "Sync now" if added
```tsx
const { data } = useQuery({
  queryKey: ['admin', 'diagnostics'],
  queryFn: getDiagnostics,
  refetchInterval: 30_000,   // D4-16
})
```

---

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `src/gruvax/sync/nightly.py` `next_fire_after()` | utility | — | Pure DST-safe datetime function; no datetime scheduling exists in the codebase. RESEARCH.md Pattern 1 (verified via Python 3.14 execution) is the authoritative reference. |

---

## Metadata

**Analog search scope:** `src/gruvax/`, `tests/unit/`, `tests/property/`, `frontend/src/routes/admin/`, `frontend/src/api/`
**Files read:** 10 source files fully read
**Pattern extraction date:** 2026-05-29

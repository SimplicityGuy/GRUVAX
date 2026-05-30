---
phase: 04-sync-polish-diagnostics
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 26
files_reviewed_list:
  - src/gruvax/sync/nightly.py
  - src/gruvax/app.py
  - src/gruvax/api/admin/settings.py
  - src/gruvax/api/admin/profiles.py
  - src/gruvax/api/admin/diagnostics.py
  - src/gruvax/api/session.py
  - frontend/src/api/session.ts
  - frontend/src/api/adminClient.ts
  - frontend/src/api/types.ts
  - frontend/src/lib/time.ts
  - frontend/src/routes/kiosk/ReauthBanner.tsx
  - frontend/src/routes/kiosk/ReauthBanner.css
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/admin/Diagnostics.tsx
  - frontend/src/routes/admin/Diagnostics.css
  - frontend/src/routes/admin/ProfileDiagnosticsCard.tsx
  - frontend/src/routes/admin/ProfileDrawer.tsx
  - frontend/src/routes/admin/ProfileStatusBadge.tsx
  - frontend/src/routes/admin/SyncProgressSection.tsx
  - frontend/src/routes/admin/Settings.tsx
  - frontend/src/routes/admin/admin.css
  - tests/property/test_nightly_scheduler.py
  - tests/unit/test_nightly_scheduler.py
  - tests/unit/test_session.py
  - tests/integration/sync/test_purge.py
  - tests/integration/api/test_diagnostics.py
  - tests/integration/api/test_admin_settings.py
findings:
  critical: 2
  warning: 7
  info: 4
  total: 13
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-05-29T00:00:00Z
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

## Summary

Phase 4 introduces a nightly asyncio scheduler with DST-safe scheduling, a soft-delete cache
purge, `sync.cadence` settings, `needs_reauth` session field, per-profile diagnostics, and
their frontend surfaces. The overall architecture is solid: asyncio patterns are correct
(CancelledError propagates, strong-ref via background_tasks set), SQL is parameterized, PATs
are not logged, and the Nordic Grid token contract is respected in CSS.

Two blockers were found: a Python 2–style bare tuple `except` syntax (`except TypeError,
ValueError`) that is a **SyntaxError** in Python 3 and will prevent the module from loading;
and a DST scheduling bug where `next_fire_after` uses naive `replace(tzinfo=tz)` instead of
`localize`/`astimezone`, which can produce a strictly-non-future candidate when wall-clock
times are ambiguous during fall-back — violating the invariant the scheduler depends on.

Warnings cover: `sync_cadence` served via the wrong helper (`_get_color` instead of a plain
string getter, causing silent default degradation when the stored value is not a string-quote-
wrapped value); a dual-fetch double network hit on the Diagnostics page; a mislabeled status
mapping in `ProfileDiagnosticsCard` that renders `failed` as `connected`; stale-closure risk
in a `formatRelativeTime` usage; and missing cleanup on the cadence `success` auto-reset timer.

---

## Structural Findings (fallow)

No structural pre-pass was provided.

---

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Python 3 SyntaxError — bare-tuple `except` in `settings.py`

**File:** `src/gruvax/api/admin/settings.py:159` and `:261` and `:315`

**Issue:** The code uses `except TypeError, ValueError:` — a Python 2 construct that is a
**SyntaxError in Python 3**. Python 3 requires `except (TypeError, ValueError):` with
parentheses. The `except` with a bare comma is parsed as an `except ExcType as name:` statement
(comma = `as`), making `ValueError` a name binding, not a second exception type. Under
CPython 3, this raises `SyntaxError: invalid syntax` at **import time**, making the entire
`settings` module unloadable — all settings endpoints return 500.

Affected lines (same pattern, three occurrences):
- Line 159: `_get_int` helper
- Line 261: brightness validation in `update_settings`
- Line 315: integer storage branch in `update_settings`

**Fix:**
```python
# Replace every:
except TypeError, ValueError:
# with:
except (TypeError, ValueError):
```

---

### CR-02: DST scheduling bug — `replace(tzinfo=tz)` does not localize correctly for ambiguous wall-clock times

**File:** `src/gruvax/sync/nightly.py:83-91`

**Issue:** `next_fire_after` builds the candidate datetime with:

```python
candidate_naive = datetime(today.year, today.month, today.day, hour, 0, 0)
candidate = candidate_naive.replace(tzinfo=tz)
```

`datetime.replace(tzinfo=tz)` performs a **mechanical substitution** of the tzinfo object
without adjusting the UTC offset — it does not call `localize()` or account for the fold. When
the `tzinfo` comes from `datetime.now().astimezone()`, the object is a Python `datetime.timezone`
fixed-offset instance (or a `zoneinfo.ZoneInfo`); using `replace` on a `ZoneInfo`-carrying tzinfo
with a naive naive datetime bypasses DST disambiguation. Specifically:

1. If `tz` is a `ZoneInfo` instance (the common result of `.astimezone()` on Linux/macOS with a
   TZ env variable), then `naive.replace(tzinfo=zoneinfo_obj)` produces the **DST-ambiguous**
   wall-clock time without the fold hint for the *target* date — the `fold=1` is only set, but
   a `ZoneInfo`-attached datetime's UTC value depends on the fold value being respected at
   `utcoffset()` call time. The comment says `fold=1` is set and this handles DST; however, the
   test invariant (result > now_aware) can fail when `now_aware` has the non-DST offset and
   the candidate is constructed with the DST offset (or vice versa) due to mismatched UTC.

2. More concretely: the strictly-future invariant can be violated when the current time is
   within the DST ambiguous hour and the OS `tz` object is a fixed-offset tzinfo from the
   *current* session rather than the *target* date. A 0-second sleep (busy loop) results.

The correct, portable approach uses `datetime.combine` + `ZoneInfo` with fold, or re-anchors via
UTC:

```python
from datetime import datetime, timedelta, timezone
import zoneinfo

def next_fire_after(now_aware: datetime, hour: int = 3) -> datetime:
    tz = now_aware.tzinfo
    today = now_aware.date()
    # Build wall-clock candidate using fold=1 (post-DST-back side)
    candidate = datetime(today.year, today.month, today.day, hour, 0, 0, fold=1)
    # Interpret in target TZ using astimezone to get a properly-offset aware dt
    candidate_aware = candidate.replace(tzinfo=tz)
    if candidate_aware <= now_aware:
        tomorrow = today + timedelta(days=1)
        candidate = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, 0, 0, fold=1)
        candidate_aware = candidate.replace(tzinfo=tz)
    # Final guard: if still not future (e.g. offset mismatch at DST boundary),
    # advance by 1 hour increments until it is — cap at 26h
    while candidate_aware <= now_aware:
        candidate_aware += timedelta(hours=1)
    return candidate_aware
```

The absolute safest fix is to compute via UTC:

```python
def next_fire_after(now_aware: datetime, hour: int = 3) -> datetime:
    """Always returns a strictly-future local wall-clock fire time."""
    tz = now_aware.tzinfo
    # Walk forward one day at a time until we find a strictly-future fire time.
    candidate_date = now_aware.date()
    for _ in range(3):  # at most 3 days forward (handles all DST edge cases)
        naive = datetime(candidate_date.year, candidate_date.month, candidate_date.day, hour, 0, 0)
        candidate = naive.replace(tzinfo=tz, fold=1)
        if candidate > now_aware:
            return candidate
        candidate_date += timedelta(days=1)
    # Fallback: should never be reached
    raise RuntimeError("next_fire_after: could not find strictly-future time within 3 days")
```

The nightly loop uses `max(sleep_secs, 1)` as a guard, which prevents a true 0-second busy loop,
but a 1-second sleep repeated for an entire DST hour (3600 iterations before the next real fire)
would cause unnecessary load and incorrect firing times. The DST-corner-case is a behavioral
defect even with the 1-second floor.

---

## Warnings

### WR-01: `sync_cadence` served via `_get_color()` — incorrect helper, silent fallback to default on stored value mismatch

**File:** `src/gruvax/api/admin/settings.py:176`

**Issue:** The `sync_cadence` key is read using `_get_color("sync.cadence", "24h")`:

```python
"sync_cadence": _get_color("sync.cadence", "24h"),
```

`_get_color` strips `"` from the stored value (`raw.strip('"')`), which works for the JSON-string
storage format (`'"24h"'` → `"24h"`). However, `_get_color` is the **color** helper — semantically
wrong, and its default branch returns `default` when `raw` is not a `str`, which can mask future
type-storage bugs silently. A cadence value returned as an integer or JSONB boolean (possible if a
migration or import writes the wrong type) would be silently swapped for `"24h"` with no log.

The correct helper is `_get_color` for this specific stored format only by accident — a dedicated
path (or at minimum using the correct name via a `_get_str` helper) prevents future maintainers
from misreading the intent and accidentally breaking cadence reads when refactoring color handling.

**Fix:**
```python
def _get_str(key: str, default: str) -> str:
    """Get a JSON-string value, stripping outer quotes if present."""
    raw = settings_map.get(key, default)
    if isinstance(raw, str):
        return raw.strip('"')
    return default

# Then in the return dict:
"sync_cadence": _get_str("sync.cadence", "24h"),
```

---

### WR-02: `ProfileDiagnosticsCard.deriveProfileStatus` maps `last_sync_status='failed'` → `'connected'`

**File:** `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx:32`

**Issue:**

```typescript
if (profile.last_sync_status === 'failed') return 'connected' // connected but last sync failed
```

A profile with `last_sync_status = 'failed'` returns the `connected` status, which renders a
green `CONNECTED` badge. This is incorrect and misleading: a profile that failed its last sync
is not in a healthy connected state. The comment acknowledges this is intentional, but it
contradicts the backend `_profile_status` in `profiles.py` (lines 87–104), which returns
`"connected"` only for `last_sync_status == 'ok'`, and returns `"pending"` for any
non-ok/non-in_progress state.

There is no `'failed'` variant in `ProfileStatus` type — the frontend type only has
`connected | pending | syncing | re-auth-required`. A separate `'failed'` variant should be
added, or this should return `'pending'` (matching the backend logic) to avoid showing a
misleading green badge for a broken profile.

**Fix:**
```typescript
// Add 'failed' to the ProfileStatus type in ProfileStatusBadge.tsx:
export type ProfileStatus = 'connected' | 'pending' | 'syncing' | 're-auth-required' | 'failed'

// Then in deriveProfileStatus:
if (profile.last_sync_status === 'failed') return 'failed'

// Add STATUS_LABELS entry and CSS class for 'failed' in ProfileStatusBadge.tsx.
```

Or at minimum, keep the existing type and return `'pending'` instead of `'connected'` for
failed:

```typescript
if (profile.last_sync_status === 'failed') return 'pending'
```

---

### WR-03: `Diagnostics.tsx` fires `getDiagnostics()` twice on mount — double network request

**File:** `frontend/src/routes/admin/Diagnostics.tsx:475-503`

**Issue:** The component has both:
1. A `useQuery` hook calling `getDiagnostics` with `refetchInterval: 30_000` (line 475)
2. An imperative `load()` function that also calls `getDiagnostics` (line 485), triggered by `useEffect` on mount (line 497)

On mount, both the `useQuery` initial fetch and `load()` fire immediately, causing two
simultaneous `GET /api/admin/diagnostics` requests. The `profilesQueryData` from `useQuery`
and the `data` from `setData(result)` are kept in separate state, and the page renders from
`data` (imperative) for most sections but from `profilesQueryData` for the profiles section —
creating two sources of truth that can diverge between 30s polling ticks.

**Fix:** Remove the duplicate imperative `load()` pattern and use a single `useQuery` for all
diagnostic data. Use `refetch()` from the `useQuery` return for the REFRESH button:

```typescript
const { data, isLoading, refetch } = useQuery({
  queryKey: ['admin', 'diagnostics'],
  queryFn: getDiagnostics,
  refetchInterval: 30_000,
  staleTime: 0,
})

const handleRefresh = useCallback(() => { void refetch() }, [refetch])
```

This eliminates the dual-fetch, the separate `loading`/`refreshing` state, and the two-source-
of-truth for profiles vs the rest of the page.

---

### WR-04: `stalenessStatusFromIso(null)` returns `'ok'` for never-synced profiles — misleading UI signal

**File:** `frontend/src/lib/time.ts:45-49`

**Issue:**

```typescript
export function stalenessStatusFromIso(isoString: string | null): 'ok' | 'stale' | 'outdated' {
  if (isoString === null) return 'ok'
  ...
}
```

A never-synced profile (`last_sync_at: null`) returns `'ok'`, which renders a green `OK`
staleness badge on the `ProfileDiagnosticsCard`. A profile that has never synced is not "OK"
in any meaningful sense — the admin will see a green badge on a profile that has never
successfully fetched data. `stalenessStatus(null)` in the same file also returns `'ok'` for
this reason.

Both functions are called from `ProfileDiagnosticsCard` with the profile's `last_sync_at`,
which is `null` for pending/newly-connected profiles. The combined effect: a profile stuck in
`pending` shows `CONNECTED` (WR-02) with a green `OK` staleness badge — fully misleading.

**Fix:**
```typescript
export function stalenessStatusFromIso(isoString: string | null): 'ok' | 'stale' | 'outdated' | 'unknown' {
  if (isoString === null) return 'unknown'
  ...
}
```

Add a corresponding `diag-badge--unknown` CSS class that renders a neutral/grey badge, and
update `ProfileDiagnosticsCard` to display `NEVER` for the `'unknown'` case.

---

### WR-05: `_startup_purge_sweep` logs profile IDs but does not log row counts — silent failure for partial purge

**File:** `src/gruvax/sync/nightly.py:288-294`

**Issue:** After collecting orphaned profile IDs, the sweep logs the IDs and calls
`_purge_profile_collection` per ID. `_purge_profile_collection` itself logs "removed rows"
on completion but **does not surface the actual row count deleted** (`cur.rowcount` or a
`RETURNING` clause). If the DELETE silently operates on 0 rows (e.g. because a concurrent
sweep already cleared them), the log says "removed rows for profile=..." which misleads
operators into thinking rows were actually deleted.

Additionally, `_purge_profile_collection` uses `conn.execute()` (connection-level execute)
rather than a cursor, so `rowcount` is not directly accessible without opening a cursor.

**Fix:**
```python
async def _purge_profile_collection(pool: Any, profile_id: str) -> None:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (profile_id,),
        )
        deleted = cur.rowcount
        await conn.commit()
    logger.info(
        "purge_profile_collection: removed %d rows for profile=%s",
        deleted,
        profile_id,
    )
```

---

### WR-06: `Settings.tsx` `handleSaveSettings` optimistically reads `updated` as `AdminSettings` — silent broken re-read

**File:** `frontend/src/routes/admin/Settings.tsx:111-112`

**Issue:**

```typescript
const updated = await putAdminSettings({...})
setCapacity(updated.cube_nominal_capacity ?? capacity)
setIdleMin(Math.round((updated.session_idle_ttl_seconds ?? idleMin * 60) / 60))
```

The comment on `putAdminSettings` in `adminClient.ts` (line 156-157) explicitly states:
"The backend returns `{updated: string[]}` (list of DB key names updated), not a full
`AdminSettings` object." The return type is `Promise<Partial<AdminSettings>>`.

`updated.cube_nominal_capacity` and `updated.session_idle_ttl_seconds` will always be
`undefined` because the backend returns `{"updated": ["cube.nominal_capacity", ...]}`, not
the actual values. The `?? capacity` and `?? idleMin * 60` fallbacks silently revert the
displayed values to the *pre-save* stale local state rather than the persisted server values.
The user sees no error, but the displayed capacity after save may not match what was stored.

**Fix:** After a successful save, re-fetch settings to confirm the stored values:
```typescript
await putAdminSettings({ cube_nominal_capacity: capacity, session_idle_ttl_seconds: idleMin * 60 })
// Optionally re-fetch to confirm:
const fresh = await getAdminSettings()
setCapacity(fresh.cube_nominal_capacity)
setIdleMin(Math.round(fresh.session_idle_ttl_seconds / 60))
setSettingsStatus('saved')
```

Or remove the lines that try to read `updated.cube_nominal_capacity` — the local state
already holds the intended values since they were set by `setCapacity`/`setIdleMin` before
the PUT.

---

### WR-07: `handleSaveCadence` timer in `Settings.tsx` leaks on component unmount

**File:** `frontend/src/routes/admin/Settings.tsx:130-134`

**Issue:**

```typescript
setTimeout(() => setCadenceStatus('idle'), 2500)
```

The `setTimeout` handle is not stored, so the timer cannot be cancelled on unmount. If the
admin navigates away within 2.5s of saving the cadence, the `setCadenceStatus` state update
fires on an unmounted component, triggering a React warning ("Can't perform a React state
update on an unmounted component" in dev mode) and potentially a no-op state update in
production. This is the same pattern as `handleSaveSettings` (line 114) and `handleSaveLeds`
(line 195), but those use `setSettingsStatus`/`setLedsStatus` on a function-scoped `setTimeout`
without cleanup — same root issue.

**Fix:** Use a `useRef` + cleanup effect pattern consistent with `TopSearchedSection`
(which already does this correctly for `successTimerRef`):

```typescript
const cadenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

// In handleSaveCadence:
if (cadenceTimerRef.current) clearTimeout(cadenceTimerRef.current)
cadenceTimerRef.current = setTimeout(() => setCadenceStatus('idle'), 2500)

// Cleanup effect:
useEffect(() => () => {
  if (cadenceTimerRef.current) clearTimeout(cadenceTimerRef.current)
}, [])
```

---

## Info

### IN-01: `_DEFAULT_PROFILE_UUID` redeclared as local variable in three endpoint functions

**File:** `src/gruvax/api/admin/settings.py:137`, `:296`, `:405`

**Issue:** The constant `_DEFAULT_PROFILE_UUID = "00000000-0000-0000-0000-000000000001"` is
re-declared as a local variable inside `get_settings`, `update_settings`, and `change_pin`.
`app.py` and `profiles.py` use the module-level `DEFAULT_PROFILE_UUID` imported from
`gruvax.db.queries`. The local redeclarations create three independent copies of the same
magic string with no deduplication — a drift risk if the value ever changes.

**Fix:** Import `DEFAULT_PROFILE_UUID` from `gruvax.db.queries` at the top of `settings.py`
and remove the three local redeclarations.

---

### IN-02: `connect_pat` / `rotate_pat` in `profiles.py` cast `discogsography_user_id` as `%s::uuid` but `new_user_id` is a string from `str(page["user_id"])`

**File:** `src/gruvax/api/admin/profiles.py:457-462`

**Issue:** The D-09 collision check casts `new_user_id` to `::uuid`:

```python
await cur.execute(
    "SELECT id::text FROM gruvax.profiles "
    "WHERE discogsography_user_id = %s::uuid "
    ...
    (new_user_id, str(uid)),
)
```

`new_user_id` is `str(page["user_id"])` from the test-sync response. If the discogsography
API returns a numeric user ID (integer), `str()` converts it to e.g. `"12345678"`, and
`%s::uuid` will fail with a PostgreSQL cast error, returning an unhandled 500 instead of the
intended 409. The `discogsography_user_id` column type should be clarified — if it stores an
integer Discogs user ID, the cast should be `::bigint`, not `::uuid`.

This is an observational finding (the migration schema is not in scope) — worth verifying the
column type against the migration to confirm correctness.

---

### IN-03: `formatRelativeTime` in `Diagnostics.tsx` computes `Date.now()` at render time — stale after initial mount

**File:** `frontend/src/routes/admin/Diagnostics.tsx:396`

**Issue:** The log entry timestamps are formatted inside a `useEffect` that runs when `logs`
changes. `new Date(entry.ts * 1000).toISOString()` (for display timestamp) is correct and
static. However, `formatRelativeTime(entry.ts)` in `SlowQuerySection` (line 272) is called
during the React render cycle and captures `Date.now()` at that moment. The relative time
label ("3s ago") becomes stale immediately after mount and never updates — slow query entries
from 5 minutes ago will show "3s ago" for the rest of the admin session unless the user
manually refreshes.

This is an info-level issue (stale display only, no data loss) but can confuse operators
diagnosing active issues.

**Fix:** For slow query and log entries, either (a) show an absolute time (ISO string, already
available as `new Date(ts * 1000).toISOString()`), or (b) use a `useEffect`-driven 1-minute
interval to re-render the relative times.

---

### IN-04: `test_session.py` app factory bypasses lifespan — `get_pool` dependency may fail

**File:** `tests/unit/test_session.py:102-120`

**Issue:** `_make_app(revoked)` creates the app with `create_app()` but injects a fake pool
via direct attribute assignment (`app.state.db_pool = fake_pool`) without going through the
lifespan. The `GET /api/session` handler reads `request.app.state.db_pool` directly (not via
`get_pool` Depends), so this works. However, if future refactoring moves session to use
`get_pool` (a `Depends` that reads from `app.state`), this test will silently use the real
pool. More immediately, the `lifespan` on `create_app()` initialises several `app.state`
attributes that handlers may expect (`profile_state_registry`, `boundary_cache_registry`,
etc.) which are absent here — if `get_session` ever reads those, the test would raise
`AttributeError`. The tests are not using `LifespanManager`, which is the established pattern
for other tests in this suite.

**Fix:** Either use `LifespanManager` (and the real DB pool from `db_pool` fixture) for proper
integration, or document in the test that it deliberately exercises only the session handler's
DB path in isolation and will need updating if the handler grows.

---

_Reviewed: 2026-05-29T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

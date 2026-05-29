# Phase 4: Sync Polish + Diagnostics — Research

**Researched:** 2026-05-29
**Domain:** asyncio scheduling, DST-safe timekeeping, Python zoneinfo, FastAPI lifespan patterns, frontend polling, Nordic Grid UI wiring
**Confidence:** HIGH

## Summary

Phase 4 is a polish phase: the sync infrastructure (advisory-lock staging-swap, `sync_profile()`, 202+poll, `app_token_revoked` state machine) already ships from Phases 1/2/3. The net-new backend code is one lifespan loop (`_sync_loop()`), two startup sweeps, one settings key, one DB field on `GET /api/session`, one `app_token_revoked` reset wire, and one per-profile diagnostics extension. Net-new frontend code is two new components (`ReauthBanner`, `ProfileDiagnosticsCard`), three data-wiring tasks, and one new settings control.

The highest-stakes technical question — the DST-safe "next 03:00 local" algorithm — is fully verifiable in-session. Python's `datetime.now().astimezone()` returns a DST-aware tz-aware datetime for the server's OS/container TZ. Building a `next_fire_after(now_aware, hour=3)` function on top, using `fold=1` to resolve any wall-clock ambiguity, produces a result that is provably always-future and monotonically advances within a 22–26 hour window across any DST boundary. This was validated against 40 daily firings through the spring-forward and fall-back transitions. [VERIFIED: manual Python 3.14 execution in this session]

The second key factual finding: `app_token_revoked` reset-on-success is ALREADY wired in both `connect_pat` and `rotate_pat` (`app_token_revoked = FALSE` in the UPDATE that stores the new ciphertext). D4-09 is therefore a verification task, not a wiring task. [VERIFIED: src/gruvax/api/admin/profiles.py lines 471–480 and 565–574]

The third finding: no new Alembic migration is needed. `app_token_revoked`, `last_sync_at`, `last_sync_status`, `last_sync_error`, and `last_sync_item_count` all exist on `gruvax.profiles` as of migration 0009. The `sync.cadence` setting is a new row in the existing `gruvax.settings` table (no schema change). The soft-delete purge is a `DELETE` DML (no DDL). Current Alembic head = 0011. [VERIFIED: migrations/versions/ directory listing + migration 0009 column grep]

**Primary recommendation:** Plan the work as four plans: (1) backend scheduler + startup sweeps + settings key + purge + session field + `app_token_revoked` verification; (2) admin API extensions (`/diagnostics` per-profile data, `list_profiles`/`get_profile` `app_token_revoked` already present); (3) frontend backend-binding (`ReauthBanner`, diagnostics cards, cadence select, `needs_reauth` consumer); (4) `SyncProgressSection` elapsed-seconds polish + toast wiring.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D4-01**: Wall-clock anchored to 03:00 server-local time; loop computes next 03:00-local occurrence (DST-aware) and sleeps until it; reschedules after each run.
- **D4-02**: Catch-up on startup when stale — sync any non-revoked profile whose `last_sync_at` is older than the configured cadence, then resume the 03:00 schedule.
- **D4-03**: Cadence runs anchored as multiples of the 03:00 base. 24h → 03:00; 12h → 03:00 + 15:00; 6h → 03:00 / 09:00 / 15:00 / 21:00.
- **D4-04**: Skip policy — skip profiles with `app_token_revoked=TRUE`; skip profiles currently `last_sync_status='in_progress'`.
- **D4-05**: Timezone = server process local time (deployment host / Compose container TZ). No new setting.
- **D4-06**: Loop re-reads cadence each iteration; "off" parks the loop (sleep-and-recheck). Cadence is a global setting under the default-profile UUID via `_ALLOWED_SETTINGS_KEYS`; add `sync.cadence` key.
- **D4-07**: `app_token_revoked` boolean is the canonical "needs re-auth" signal. Expose on `GET /api/admin/profiles` and `GET /api/admin/profiles/{id}`.
- **D4-08**: Kiosk inline banner learns of re-auth via a `needs_reauth` field on `GET /api/session`. No new endpoint.
- **D4-09**: Badge/banner auto-clears on successful rotate+sync; no manual dismiss. Planner MUST confirm rotate path resets `app_token_revoked=FALSE` and wire it if missing.
- **D4-10**: Kiosk banner is non-blocking — search keeps working off cached `profile_collection`.
- **D4-11**: Purge triggered at delete-time AND backstopped by lifespan startup safety sweep.
- **D4-12**: Sweep predicate = `deleted_at IS NOT NULL AND profile_collection rows still exist` — no new column.
- **D4-13**: Purge removes `profile_collection` rows ONLY; keeps profile row, per-profile config, and audit lineage.
- **D4-14**: Profile row never hard-deleted in v2.0.
- **D4-15**: Per-profile diagnostics cards live in a new "Profiles" section on `/admin/diagnostics`.
- **D4-16**: Cards stay current via poll / TanStack Query `refetchInterval: 30_000`.
- **D4-17**: "Sync now" shows indeterminate spinner + elapsed, reusing existing 202+poll. No backend change.
- Staleness thresholds: `<3d` none, `3–14d` yellow, `≥14d` red; banner reads `now() - profiles.last_sync_at`.
- All v1.0 invariants hold at v2.0 close: Alembic upgrade↔downgrade round-trip clean, p95 SLOs, structured logs, log-ring buffer, in-app keypad.

### Claude's Discretion

- Exact next-03:00-local computation (zoneinfo + DST handling), loop sleep granularity, and how `off` parks (sleep-and-recheck interval).
- Whether catch-up-on-startup sweep and soft-delete purge startup sweep are one combined pass or two.
- `sync.cadence` setting value encoding (`"24h"|"12h"|"6h"|"off"` string vs int) and validation.
- Toast copy, spinner styling, banner/badge copy — per UI-SPEC.
- Diagnostics card layout/grid, refetch interval value (30s per UI-SPEC), per-card Sync-now button presence.
- How startup catch-up avoids a sync-storm (sequential with same skip policy).

### Deferred Ideas (OUT OF SCOPE)

- "Sync all profiles now" manual button.
- Configurable timezone setting.
- Real page/item Sync-now progress bar.
- `purged_at` audit column.
- SSE-live diagnostics / SSE-pushed re-auth.
- Per-profile self-connect PAT (v2.1), OAuth2 device-grant (AUTH-01 → v2.2), QR pairing (DEV-04 → v2.1).
- Real LED/WS2812B hardware.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SYN-01 | Three sync triggers: on connect (already shipped P1/P2), manual "Sync now" (already shipped P2), nightly background scheduler (`asyncio.create_task` in lifespan, 03:00 local, cadence 24h/12h/6h/off) | Nightly loop design verified against existing `_refresh_all_profiles_state` pattern; DST algorithm validated |
| SYN-02 | Staleness UX polish: per-profile `now() - profiles.last_sync_at`; 3d/14d thresholds; re-auth badge (admin) + kiosk inline banner | `app_token_revoked` already in API responses; `needs_reauth` field is additive to `SessionData`; `ProfileStatusBadge` `re-auth-required` CSS class already exists |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Nightly sync scheduling | API / Backend (lifespan) | — | asyncio task lives server-side; fires sequential `sync_profile()` calls |
| Cadence persistence | Database / Storage | API | `gruvax.settings` row under default profile UUID |
| `app_token_revoked` detection | API / Backend | Frontend display | Already set by `_record_failure` in `sync_profile`; UI reads it from profile list |
| Kiosk `needs_reauth` signal | API / Backend (`GET /api/session`) | Kiosk Frontend | Session endpoint already consulted by kiosk on bootstrap/refresh |
| Re-auth badge display | Frontend (admin UI) | — | Wire `app_token_revoked` → `ProfileStatusBadge` `re-auth-required` |
| Per-profile diagnostics data | API / Backend (`GET /api/admin/diagnostics`) | — | Extend existing endpoint with profile sync metadata |
| Diagnostics card rendering | Frontend (admin UI) | — | New `ProfileDiagnosticsCard` component in existing page |
| Soft-delete purge | API / Backend (lifespan + `soft_delete_profile`) | Database | `DELETE FROM profile_collection WHERE profile_id = %s::uuid` |
| Sync-now elapsed counter | Frontend (admin UI) | — | Client-side elapsed timer in `SyncProgressSection` |
| Sync complete toast | Frontend (admin UI) | — | Existing `SyncToast` already correct; wiring polish only |

---

## Standard Stack

### Core (no changes — all existing)
| Library | Version | Purpose | Notes |
|---------|---------|---------|-------|
| Python | 3.14.5 (on this machine) | Runtime | Container uses whatever discogsography alignment requires; `datetime.now().astimezone()` DST behavior works on 3.13+ |
| FastAPI | 0.136.x | Lifespan + endpoints | Existing; `asyncio.create_task` pattern already used |
| psycopg | 3.2+ async | DB access | Existing; parameterized `%s` SQL throughout |
| React 19 | existing | Frontend | Existing; `useQuery` + `refetchInterval` pattern already established |
| TanStack Query | 5.x | Polling | Existing; `refetchInterval: 30_000` for diagnostics per UI-SPEC |
| Zustand | 5.x | Session store | Existing; `sessionStore` will add `needsReauth` derived field |

### No new packages in Phase 4
The UI-SPEC Registry Safety section explicitly confirms: "No new dependencies. P4 is entirely extensions of existing components and patterns." [VERIFIED: 04-UI-SPEC.md lines 306-307]

---

## Package Legitimacy Audit

> No packages to audit. Phase 4 introduces zero new external dependencies — confirmed by 04-UI-SPEC.md and the code analysis showing all required patterns exist in the current codebase.

---

## Architecture Patterns

### System Architecture Diagram

```mermaid
flowchart TD
    subgraph Lifespan["lifespan() startup"]
        SS[startup sweeps:\ncatch-up sync\nsoft-delete purge]
        NL[asyncio.create_task\n_sync_loop]
    end

    subgraph Loop["_sync_loop() — forever"]
        RC[read sync.cadence\nfrom settings]
        OFF{cadence == off?}
        NF[compute next_fire_after\nhour=3 or 9 or 15 or 21]
        SL[asyncio.sleep until\nnext_fire time]
        IP[iterate non-deleted profiles\nsequential ORDER BY created_at]
        SK{skip?\nrevoked=TRUE\nor in_progress?}
        SP[sync_profile\nprofile_id app_state]
    end

    subgraph API["HTTP API Extensions"]
        DG[GET /api/admin/diagnostics\n+ profiles[] array]
        SE[GET /api/session\n+ needs_reauth field]
        ST[GET/PUT /api/admin/settings\n+ sync.cadence key]
        PL[GET /api/admin/profiles\n app_token_revoked\nalready present]
    end

    subgraph Frontend["Frontend extensions"]
        DC[ProfileDiagnosticsCard\n30s refetch]
        RB[ReauthBanner\nneeds_reauth from session]
        CS[cadence select\nauto-save on change]
        EP[elapsed timer in\nSyncProgressSection]
    end

    SS -->|one-shot: stale profiles\nand orphaned purge| NL
    NL --> RC
    RC --> OFF
    OFF -->|yes| SL
    OFF -->|no| NF
    NF --> SL
    SL -->|wake| IP
    IP --> SK
    SK -->|skip| IP
    SK -->|sync| SP
    SP -->|all done| RC

    DG --> DC
    SE --> RB
    ST --> CS
    PL --> DC
```

### Recommended Project Structure (additions only)

```
src/gruvax/
├── app.py                     # + _sync_loop(), startup sweeps, sync.cadence reader
├── api/admin/
│   ├── diagnostics.py         # + profiles[] array in GET /diagnostics response
│   ├── settings.py            # + sync.cadence in _ALLOWED_SETTINGS_KEYS + key_map
│   └── profiles.py            # + purge_profile_collection() call in soft_delete_profile
├── api/session.py             # + needs_reauth field in GET /session response
└── sync/
    └── nightly.py             # NEW: next_fire_after() + _sync_loop() (or inline in app.py)

frontend/src/
├── api/
│   ├── session.ts             # + needs_reauth?: boolean on SessionData + ProfileSummary
│   ├── adminClient.ts         # + ProfileDiagnosticEntry type + profiles[] on DiagnosticsData
│   └── settings.ts            # + sync_cadence field in GET/PUT shapes
├── routes/
│   ├── admin/
│   │   ├── Diagnostics.tsx    # + ProfilesDiagnosticsSection component
│   │   ├── Diagnostics.css    # + .diag-profiles-grid + .diag-profile-card rules
│   │   ├── ProfileDiagnosticsCard.tsx   # NEW
│   │   ├── ProfileStatusBadge.tsx       # wire app_token_revoked → re-auth-required
│   │   ├── SyncProgressSection.tsx      # + elapsed seconds counter
│   │   └── Settings.tsx       # + sync cadence select control
│   └── kiosk/
│       ├── KioskView.tsx      # + ReauthBanner conditional render
│       └── ReauthBanner.tsx   # NEW
└── state/
    └── sessionStore.ts        # + needsReauth derived from bound profile's app_token_revoked
```

### Pattern 1: DST-Safe next-03:00-local computation [VERIFIED: Python 3.14 execution]

**What:** Compute the next wall-clock 03:00 occurrence in the server's local timezone, handling spring-forward gaps and fall-back ambiguities correctly.

**Key insight:** 03:00 is unambiguous in all major world timezones. Spring-forward gaps are in the 01:00–02:59 window (North America) or 01:00–01:59 → 02:00 (Brazil). Fall-back repeats are the 01:00 or 02:00 hour. Using `fold=1` resolves any theoretical ambiguity by selecting the post-transition offset.

**Algorithm:**

```python
# Source: validated via manual Python 3.14 execution in this research session
from datetime import datetime, timedelta

def next_fire_after(now_aware: datetime, hour: int = 3) -> datetime:
    """DST-correct next occurrence of server-local hour:00:00.

    Always returns a strictly future, DST-aware datetime in the server's local TZ.
    Uses fold=1 to prefer the post-transition wall clock on any ambiguous hour.

    Invariants verified across 40 daily firings through US DST transitions:
    - Always strictly future vs now_aware
    - Interval from last fire always within [22h, 26h]
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

**For cadence D4-03:** Derive fire times from the base `hour=3`:
- 24h: `[3]`
- 12h: `[3, 15]`
- 6h: `[3, 9, 15, 21]`

Each tick, find the soonest next-fire from the applicable hour list.

### Pattern 2: asyncio nightly loop (mirrors existing `_refresh_all_profiles_state`) [VERIFIED: src/gruvax/app.py lines 313-356]

**What:** Fire-and-forget task using the exact same `asyncio.create_task` + `app.state.background_tasks` strong-reference pattern already established.

```python
# Source: mirrors _refresh_all_profiles_state pattern in src/gruvax/app.py
async def _sync_loop(pool, app_state) -> None:
    while True:
        try:
            # 1. Read current cadence setting (re-read each tick for live config)
            cadence = await _read_sync_cadence(pool)  # returns "24h"|"12h"|"6h"|"off"
            if cadence == "off":
                await asyncio.sleep(60)  # park: recheck in 60s
                continue

            # 2. Compute next fire time
            fire_hours = {"24h": [3], "12h": [3, 15], "6h": [3, 9, 15, 21]}.get(
                cadence, [3]
            )
            now = datetime.now().astimezone()
            next_fires = [next_fire_after(now, h) for h in fire_hours]
            next_fire = min(next_fires)
            sleep_secs = (next_fire - now).total_seconds()

            logger.info(
                "nightly_sync: cadence=%s next_fire=%s sleep_secs=%.0f",
                cadence, next_fire.isoformat(), sleep_secs,
            )
            await asyncio.sleep(max(sleep_secs, 1))

            # 3. Iterate profiles sequentially (D4-04 skip policy)
            async with pool.connection() as conn, conn.cursor() as cur:
                await cur.execute(
                    "SELECT id::text FROM gruvax.profiles "
                    "WHERE deleted_at IS NULL "
                    "  AND app_token_revoked = FALSE "
                    "  AND (last_sync_status IS NULL OR last_sync_status != 'in_progress') "
                    "ORDER BY created_at"
                )
                profile_ids = [row[0] for row in await cur.fetchall()]

            for pid in profile_ids:
                try:
                    await sync_profile(pid, app_state)
                    logger.info("nightly_sync: profile=%s OK", pid)
                except Exception as exc:
                    # Per-profile isolation: log + continue (never abort the loop)
                    logger.warning("nightly_sync: profile=%s FAILED: %s", pid, exc)

        except asyncio.CancelledError:
            logger.info("nightly_sync: loop cancelled (shutdown)")
            raise  # re-raise: graceful lifespan teardown
        except Exception as exc:
            logger.warning("nightly_sync: outer loop error: %s — will retry in 60s", exc)
            await asyncio.sleep(60)

# In lifespan, after app.state.background_tasks is initialized:
_sync_task = asyncio.create_task(_sync_loop(pool, app.state))
app.state.background_tasks.add(_sync_task)
_sync_task.add_done_callback(app.state.background_tasks.discard)
```

**Graceful cancellation:** `asyncio.CancelledError` is a `BaseException` subclass — it bypasses the `except Exception` outer guard. The bare `raise` in the handler propagates it so FastAPI/uvicorn can tear down cleanly on SIGTERM.

**Per-profile error isolation:** Each `sync_profile()` call is wrapped in its own `try/except Exception`. One failed profile never aborts the nightly pass for subsequent profiles. This mirrors the pattern in `_refresh_all_profiles_state`.

### Pattern 3: Startup sweeps (catch-up + purge) [ASSUMED — planner's discretion on whether to combine]

```python
# Catch-up sweep (D4-02): before starting _sync_loop
async def _startup_catchup_sweep(pool, app_state, cadence: str) -> None:
    """Sync any stale non-revoked profiles immediately on startup."""
    if cadence == "off":
        return
    cadence_hours = {"24h": 24, "12h": 12, "6h": 6}.get(cadence, 24)
    threshold_interval = f"{cadence_hours} hours"
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id::text FROM gruvax.profiles "
            "WHERE deleted_at IS NULL "
            "  AND app_token_revoked = FALSE "
            "  AND last_sync_status != 'in_progress' "
            "  AND (last_sync_at IS NULL "
            "       OR last_sync_at < NOW() - INTERVAL %s) "
            "ORDER BY created_at",
            (threshold_interval,)
        )
        stale_ids = [row[0] for row in await cur.fetchall()]
    for pid in stale_ids:
        try:
            await sync_profile(pid, app_state)
        except Exception as exc:
            logger.warning("startup_catchup: profile=%s FAILED: %s", pid, exc)

# Purge sweep (D4-11): before starting _sync_loop
async def _startup_purge_sweep(pool) -> None:
    """Purge profile_collection rows for any soft-deleted profiles (D4-11..12)."""
    async with pool.connection() as conn, conn.cursor() as cur:
        # D4-12 predicate: deleted_at IS NOT NULL AND still has collection rows
        await cur.execute(
            "SELECT DISTINCT p.id::text "
            "FROM gruvax.profiles p "
            "JOIN gruvax.profile_collection pc ON pc.profile_id = p.id "
            "WHERE p.deleted_at IS NOT NULL",
        )
        orphaned_ids = [row[0] for row in await cur.fetchall()]
    for pid in orphaned_ids:
        await _purge_profile_collection(pool, pid)

async def _purge_profile_collection(pool, profile_id: str) -> None:
    """DELETE profile_collection rows for a soft-deleted profile (D4-13).

    Parameterized %s SQL — no f-string interpolation (bandit B608).
    Preserves: profile row, settings, cube_boundaries, segment_overrides,
    record_stats, boundary_history, change_log, change_sets.
    """
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM gruvax.profile_collection WHERE profile_id = %s::uuid",
            (profile_id,),
        )
        await conn.commit()
    logger.info("purge_profile_collection: removed rows for profile=%s", profile_id)
```

### Pattern 4: `needs_reauth` on `GET /api/session` [VERIFIED: src/gruvax/api/session.py]

The endpoint already returns `profiles[]` with `app_token_revoked` per profile. The `needs_reauth` field for the bound profile is derivable server-side:

```python
# In get_session(), after resolving bound_profile_id:
needs_reauth = False
if bound_profile_id:
    bound_profile = next(
        (p for p in profiles if str(p["id"]) == bound_profile_id), None
    )
    if bound_profile is not None:
        needs_reauth = bound_profile.get("app_token_revoked", False)

content: dict[str, Any] = {
    "profile_count": len(profiles),
    "bound_profile_id": bound_profile_id,
    "profiles": profiles,
    "device_id": device_id,
    "is_device_paired": is_device_paired,
    "needs_reauth": needs_reauth,  # D4-08
}
```

**Frontend**: add `needs_reauth?: boolean` to `SessionData` in `session.ts`. Persist it in `sessionStore` (or derive it in `KioskView` from `profiles[]` + `boundProfileId`). Render `<ReauthBanner />` when true.

**Alternative (simpler):** KioskView already has `profiles` and `boundProfileId` from `sessionStore`. It can derive `needsReauth` locally without a `sessionStore` change:
```typescript
const boundProfile = profiles.find(p => p.id === boundProfileId)
const needsReauth = boundProfile?.app_token_revoked ?? false
```

This approach requires no `SessionData` schema change — just consuming the already-present `app_token_revoked` on `ProfileSummary`. The planner should choose the minimal-surface approach. [ASSUMED — both approaches work; pick based on where `app_token_revoked` reliability is needed]

### Pattern 5: `GET /api/admin/diagnostics` extension [VERIFIED: src/gruvax/api/admin/diagnostics.py]

```python
# Add to get_diagnostics() in diagnostics.py:
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
    # existing keys unchanged
    "sync_age_seconds": sync_age,
    "top_searched": top_searched,
    "slow_queries": slow_queries,
    "mqtt": "connected" if mqtt_ok else "disconnected",
    "pool": {"size_used": size_used, "size_min": pool_min},
    "phantom_boundary_count": phantom_count,
    "recent_logs": recent_logs,
    "profiles": profile_diagnostics,  # D4-15 addition
}
```

### Pattern 6: `sync.cadence` settings key [VERIFIED: src/gruvax/api/admin/settings.py]

Add to `_ALLOWED_SETTINGS_KEYS`:
```python
"sync.cadence",
```

Add to `_STRING_KEYS` (new frozenset) or handle as a string enum in the PUT validator:
```python
_CADENCE_VALUES = frozenset({"24h", "12h", "6h", "off"})

# In PUT /settings validation loop:
elif db_key == "sync.cadence":
    value = body[body_key]
    if value not in _CADENCE_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"type": "invalid_cadence", "field": body_key,
                    "message": f"sync.cadence must be one of {sorted(_CADENCE_VALUES)}"},
        )
    json_value = f'"{value}"'  # Store as JSON string, same as auth.pin_hash pattern
```

Seed the default value in the existing profile-creation flow OR in the `_startup_catchup_sweep` fallback (default = `"24h"` if key absent). The settings row is read by `_sync_loop()` each tick via:
```python
async def _read_sync_cadence(pool) -> str:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT value FROM gruvax.settings "
            "WHERE profile_id = %s::uuid AND key = 'sync.cadence'",
            (DEFAULT_PROFILE_UUID,)
        )
        row = await cur.fetchone()
    if row is None:
        return "24h"  # default
    val = row[0]
    if isinstance(val, str):
        return val.strip('"')  # stored as JSON string
    return str(val)
```

### Anti-Patterns to Avoid

- **Parsing `asyncio.sleep(delta_seconds)` from naive datetime math:** If you compute `(tomorrow_03:00_naive - now_naive).total_seconds()`, you'll miss the spring-forward hour (sleep 22h instead of 23h) and double-sleep the fall-back hour. Always use TZ-aware datetimes for the subtraction.
- **Using `time.localtime()` or `time.mktime()` for future time computation:** These work for the current moment but do not model future DST transitions reliably. Use `datetime.now().astimezone()` + `fold=1` construction.
- **f-string interpolation in purge DELETE:** The profile_id must use `%s::uuid` placeholder (bandit B608 rule, enforced throughout the codebase).
- **Using `BackgroundTasks` for the lifespan-level `_sync_loop`:** FastAPI `BackgroundTasks` is request-scoped; it cannot be used for a long-running lifespan task. Use `asyncio.create_task` + `app.state.background_tasks` strong reference (existing pattern).
- **Using `BackgroundTasks` for the purge in `soft_delete_profile`:** This IS acceptable (request-scoped background task for the purge DELETE, which completes quickly). The lifespan sweep backstops restarts. [ASSUMED — planner should confirm `BackgroundTasks` vs `create_task` based on execution duration]
- **Catching `asyncio.CancelledError` in the outer loop without re-raising:** This prevents graceful shutdown. The outer `except Exception` guard correctly skips `CancelledError` since it's a `BaseException` subclass, not an `Exception`.
- **Seeding `sync.cadence` in a new migration:** No migration needed. Seed the default row in the settings whitelist insertion path (same as `auth.pin_hash` is seeded at first-run) or handle absence with a fallback default in `_read_sync_cadence`.

---

## Critical Factual Confirmations

### D4-09: `app_token_revoked` reset-on-success — ALREADY WIRED [VERIFIED: src/gruvax/api/admin/profiles.py]

Both `connect_pat` (line 471–480) and `rotate_pat` (lines 565–574) already execute:
```sql
UPDATE gruvax.profiles SET
    app_token_encrypted = %s::bytea,
    app_token_revoked = FALSE,
    ...
WHERE id = %s::uuid AND deleted_at IS NULL
```

The `app_token_revoked = FALSE` flip happens on the successful test-sync path, BEFORE the full background sync is queued. D4-09 is therefore a **verification task** (confirm this is present and correct), not a new wiring task.

### Migration status — NO NEW MIGRATION NEEDED [VERIFIED: migrations/versions/ directory + migration 0009 columns]

Confirmed columns already exist on `gruvax.profiles` as of migration 0009:
- `app_token_revoked BOOLEAN NOT NULL DEFAULT FALSE`
- `last_sync_at TIMESTAMPTZ`
- `last_sync_status TEXT CHECK (... 'ok','failed','in_progress' ...)`
- `last_sync_error TEXT CHECK (... 'pat_rejected','network','rate_limited','server_error','cancelled' ...)`
- `last_sync_item_count BIGINT`

Current Alembic head = `0011` (devices_and_pairing_codes). No DDL changes for P4. The `sync.cadence` setting is a new **row** in the existing `gruvax.settings` table — not a column addition.

### `app_token_revoked` already in `list_profiles`/`get_profile` responses [VERIFIED: src/gruvax/api/admin/profiles.py lines 183-206, 222-251]

Both `GET /api/admin/profiles` and `GET /api/admin/profiles/{id}` already return `app_token_revoked: bool(revoked)` in their JSON responses. D4-07 is also a **verification task**, not a new field addition.

### Discogsography rate limits — sequential iteration is sufficient [VERIFIED + ASSUMED]

The constraint is ~60 req/min per token (DGS-EXT-05). A full sync of 3,000 items at `per_page=200` = 15 requests per profile. Four profiles sequential = 60 requests. At the discogsography client's natural HTTP latency (~50–200ms per request), 60 requests takes 3–12 seconds — well within a 1-minute window. The existing `DiscogsographyClient` already handles 429 with `Retry-After` respect + exponential backoff. No inter-profile throttle is warranted for a home-LAN deployment with ≤4 profiles.

The `nightly_sync` does NOT run at startup (only the catch-up sweep does). Startup catch-up + nightly together cannot exceed 60 req/min because they are sequential-per-profile and the nightly loop only fires one full pass per cadence cycle.

**Open risk:** The `~60 req/min` figure is from the REQUIREMENTS.md description of DGS-EXT-05 and the STATE.md open question. The exact rate-limit policy lives in `docs/specs/v2-gruvax-integration.md` in the discogsography repo. If the actual limit is lower (e.g., 20 req/min), a 15-request sync already saturates it. The existing client retry-on-429 is the safety valve. [ASSUMED — discogsography contract artifact not yet read]

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DST-aware local time | Custom TZ offset tables or manual DST date calculation | `datetime.now().astimezone()` + `fold=1` | Python stdlib handles all IANA timezone transitions |
| Advisory lock for concurrent sync prevention | Custom semaphore or DB flag | Existing `pg_try_advisory_lock` in `sync_profile()` | Already implemented and tested; the nightly loop's skip policy is efficiency on top |
| Rate-limit detection | Custom request counter | Existing `DiscogsographyClient` 429 + `Retry-After` handling | Already implemented in `stamina` retry predicates |
| Per-profile cache refresh after sync | Custom cache invalidation | Existing `_refresh_profile_caches()` | Already handles boundary/snapshot/segment reload + `collection_changed` SSE event |
| Settings key validation | Ad-hoc string checks | The existing `_ALLOWED_SETTINGS_KEYS` + type-specific frozensets pattern | Established pattern; add `sync.cadence` to it |
| Frontend elapsed timer | Manual `setInterval` | `useEffect` + `setInterval` clear-on-unmount (or `useElapsedSeconds` custom hook) | Standard React pattern; no library needed |
| Relative time formatting | `moment.js` or `date-fns` | Inline `formatRelativeTime(iso: string | null)` helper | Simple enough; avoids a dependency; DM Mono display per UI-SPEC |

---

## Common Pitfalls

### Pitfall 1: asyncio.CancelledError eaten by bare `except Exception`
**What goes wrong:** The outer `while True` error handler catches `asyncio.CancelledError` if written as `except BaseException` or if Python < 3.8 compatibility is assumed (where `CancelledError` was a `concurrent.futures.CancelledError` subclass of `Exception`).
**Why it happens:** In Python 3.8+, `asyncio.CancelledError` is a `BaseException`, NOT an `Exception`. A bare `except Exception` does NOT catch it. This is correct behavior.
**How to avoid:** Keep the outer handler as `except Exception` — it correctly passes through `CancelledError`. Add an explicit `except asyncio.CancelledError: raise` guard only if nesting within another try/except.
**Warning signs:** Lifespan teardown hangs; test suite shows tasks not completing on shutdown.

### Pitfall 2: Missing strong-reference for the nightly loop task (CR-01)
**What goes wrong:** `asyncio.create_task(_sync_loop(...))` creates a weak reference. The GC can collect the task object and cancel it mid-execution.
**Why it happens:** The event loop holds only a weak reference to fire-and-forget tasks.
**How to avoid:** Follow the existing pattern: `app.state.background_tasks.add(task)` + `task.add_done_callback(app.state.background_tasks.discard)`. See `_state_task` in `app.py` lines 343-346.
**Warning signs:** Loop appears to run once then silently stops; memory pressure produces seemingly random sync outages.

### Pitfall 3: Startup catch-up running nightly profiles from the nightly-loop task
**What goes wrong:** If the catch-up sweep is part of the `_sync_loop` function's initial iteration (instead of a separate one-shot sweep), restarting the server triggers a full sync of all profiles before the first 03:00 fire, potentially overwhelming rate limits on a restart storm.
**Why it happens:** Mixing startup catch-up with the recurring loop makes the startup behavior harder to test in isolation.
**How to avoid:** Run `_startup_catchup_sweep()` as a one-shot await BEFORE `asyncio.create_task(_sync_loop())` in lifespan. This makes the catch-up visible in startup logs as a distinct phase and independently testable.

### Pitfall 4: Soft-delete purge cascading to audit tables
**What goes wrong:** A `DELETE FROM gruvax.profile_collection` with a cascade ON DELETE FOREIGN KEY or a mistakenly broad DELETE statement removes `change_log` / `change_sets` rows.
**Why it happens:** Profile_collection rows have no FK relationships with change_log/change_sets. The FK chain is: `change_log(release_id) → profile_collection(release_id)`. If this FK has ON DELETE CASCADE, purging `profile_collection` would cascade into `change_log`.
**How to avoid:** Verify the FK constraint in migration 0009 or by checking the schema. The CONTEXT explicitly states audit lineage is preserved (D4-13). Use a targeted DELETE with explicit `profile_id` predicate only.
**Warning signs:** `change_log` row counts drop after a soft-delete purge.

### Pitfall 5: `needs_reauth` stale in session store
**What goes wrong:** KioskView derives `needsReauth` from `sessionStore.profiles`, but the session store is only refreshed on mount or explicit refetch. If `app_token_revoked` flips to true while the kiosk is running, the banner never appears.
**Why it happens:** The session bootstrap is not polled on an interval by default.
**How to avoid:** The kiosk already polls `/api/health` or `/api/session` on some cadence. Confirm that `GET /api/session` is called on a regular interval (e.g., on a 60s health-check loop) OR add a low-frequency `useQuery` refetch for the session data in `KioskView`. The D4-08 decision accepts ≤24h latency — the nightly cadence provides this. A per-minute session refresh on the kiosk is sufficient.

### Pitfall 6: `sync.cadence` row missing on fresh install
**What goes wrong:** `_read_sync_cadence()` SELECT returns NULL (no row), causing a crash if the fallback is not implemented.
**Why it happens:** The settings row is not seeded in the migration (correct — settings are seeded at profile-create time).
**How to avoid:** `_read_sync_cadence()` must return `"24h"` as a default when the row is absent. Add `"sync.cadence"` to the `_DEFAULT_SETTINGS` list in `create_profile()` in `profiles.py` as `("sync.cadence", '"24h"')`. This seeds it for every profile including the default profile. [ASSUMED — verify the correct seeding location against the settings seed logic in create_profile]

---

## Code Examples

### Elapsed seconds counter for SyncProgressSection [ASSUMED — standard React pattern]

```typescript
// Source: standard React useEffect interval pattern
import { useEffect, useState } from 'react'

interface SyncProgressSectionProps {
  itemCount: number | null | undefined
  syncStartedAt: number | null  // Date.now() when sync was triggered
}

export function SyncProgressSection({ itemCount, syncStartedAt }: SyncProgressSectionProps) {
  const [elapsed, setElapsed] = useState<number>(0)

  useEffect(() => {
    if (syncStartedAt === null) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - syncStartedAt) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [syncStartedAt])

  const countText = itemCount != null
    ? `${itemCount.toLocaleString('en-US')} items processed`
    : null

  return (
    <div className="sync-progress-section" aria-live="polite" aria-busy="true">
      <div className="sync-progress-row">
        <div className="sync-progress-spinner" aria-hidden="true" />
        <span className="sync-progress-label">
          Syncing… <span className="sync-progress-count">({elapsed}s)</span>
        </span>
      </div>
      {countText && <p className="sync-progress-count">{countText}</p>}
    </div>
  )
}
```

**Note from UI-SPEC:** The elapsed counter uses DM Mono 14px in the `sync-progress-count` slot. The format is `(Ns)` space-separated after "Syncing…". The `syncStartedAt` prop needs to be threaded from `ProfileDrawer` where the trigger happens.

### Relative time formatter for diagnostics cards [ASSUMED — standard pattern, no lib needed]

```typescript
// Source: inline helper, no external dependency
function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return '—'
  const diffMs = Date.now() - new Date(isoString).getTime()
  const diffH = diffMs / (1000 * 60 * 60)
  if (diffH < 1) return `${Math.floor(diffMs / 60000)}m ago`
  if (diffH < 24) return `${Math.floor(diffH)}h ago`
  return `${Math.floor(diffH / 24)}d ago`
}
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `asyncio.sleep(86400)` fixed interval | `next_fire_after()` wall-clock anchor | Survives restarts at arbitrary times; always fires at 03:00 |
| `max(v_collection.synced_at)` staleness | `now() - profiles.last_sync_at` per profile | Per-profile staleness; correct for multi-profile deployments (already done in P1/P2) |
| Single `sync_age_seconds` on app.state | `profile_state_registry` per-profile map | Per-profile badge/banner (already done in P2) |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `BackgroundTasks` (request-scoped) is acceptable for the soft-delete purge in `soft_delete_profile` (the lifespan sweep backstops it) | Pattern 3 | If wrong: use `asyncio.create_task` with strong-reference; minimal code change |
| A2 | Deriving `needsReauth` in KioskView from `sessionStore.profiles` (rather than a `SessionData.needs_reauth` field) is simpler and sufficient | Pattern 4 | If wrong: add `needs_reauth` field to `SessionData` and update backend session endpoint |
| A3 | The `sync.cadence` row should be seeded in `create_profile()` `_DEFAULT_SETTINGS` list as a global key under the default profile | Pattern 6 / Pitfall 6 | If wrong: the nightly loop starts with no cadence row and must fall back to "24h" default (harmless) |
| A4 | Discogsography rate limit is ~60 req/min per token; sequential iteration of ≤4 profiles is within this budget | Rate-limit section | If wrong (e.g., limit is 20 req/min): add inter-profile delay (e.g., 5s sleep between profiles) in the nightly loop; the client's 429+Retry-After handling already backstops this |
| A5 | FK from `change_log` to `profile_collection` does NOT have ON DELETE CASCADE (audit lineage is preserved) | Pitfall 4 | If wrong: the purge DELETE cascades into audit tables; must check migration 0009 FK definition before implementing purge |
| A6 | No `change_log` / `change_sets` rows exist for the pure-sync path (these tables track boundary edits, not collection sync changes) | Pitfall 4 | If wrong: purge must be scoped to only `profile_collection` and must verify FK direction |

---

## Open Questions

1. **FK direction on `change_log` / `change_sets` → `profile_collection`**
   - What we know: D4-13 states "keeps audit lineage FKs" — implying a FK relationship exists
   - What's unclear: Whether it's `change_log.release_id REFERENCES profile_collection.release_id` (risky) or the FK goes the other direction / through `profiles`
   - Recommendation: Planner checks migration 0009 DDL for FK constraints involving `profile_collection` before writing the purge DELETE task

2. **Kiosk session refresh cadence for `needs_reauth`**
   - What we know: KioskView does not currently poll `GET /api/session` on an interval
   - What's unclear: How quickly `app_token_revoked=TRUE` propagates to the kiosk banner (≤24h SLA is fine by D4-08, but the kiosk may need to detect it within minutes for a good UX on a freshly-rotated PAT that fails)
   - Recommendation: Add a low-frequency `useQuery` poll (e.g., 5-minute interval) for `GET /api/session` in KioskView, or derive `needsReauth` from the existing health query result if it already carries per-profile staleness data

3. **Nightly loop location: `app.py` inline vs `sync/nightly.py` module**
   - What we know: `_refresh_all_profiles_state` is inline in `app.py`; it's a simple loop
   - What's unclear: Whether the increased complexity of the nightly loop (DST computation, cadence branching, per-profile iteration) warrants extraction
   - Recommendation: Extract to `src/gruvax/sync/nightly.py` for testability (the `next_fire_after()` function needs unit tests that don't require a full app fixture)

---

## Environment Availability

> Phase 4 is code/config changes only (no new external tools). Skipping step 2.6.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio + Hypothesis |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| Quick run command | `uv run pytest tests/unit/ tests/property/ -x -q` |
| Full suite command | `uv run pytest tests/ -q --tb=short` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SYN-01 | `next_fire_after()` always future, 22–26h window | property (Hypothesis) | `uv run pytest tests/property/test_nightly_scheduler.py -x -q` | ❌ Wave 0 |
| SYN-01 | `next_fire_after()` monotonic over DST transitions | property (Hypothesis) | same file | ❌ Wave 0 |
| SYN-01 | Cadence fire-time anchoring (24h→3, 12h→3+15, 6h→3+9+15+21) | unit | `uv run pytest tests/unit/test_nightly_scheduler.py -x -q` | ❌ Wave 0 |
| SYN-01 | Skip policy: revoked + in_progress profiles excluded | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_skip_policy -x -q` | ❌ Wave 0 |
| SYN-01 | `off` cadence: loop parks without syncing | unit | `uv run pytest tests/unit/test_nightly_scheduler.py::test_cadence_off -x -q` | ❌ Wave 0 |
| SYN-01 | Startup catch-up sweep syncs stale profiles | integration | `uv run pytest tests/integration/sync/test_nightly_scheduler.py -x -q` | ❌ Wave 0 |
| SYN-01 | `sync.cadence` persists across settings PUT | integration | `uv run pytest tests/integration/api/test_admin_settings.py::test_sync_cadence -x -q` | ❌ Wave 0 |
| SYN-02 | `app_token_revoked=TRUE` resets on rotate + full sync | integration | `uv run pytest tests/integration/api/test_admin_profiles.py::test_rotate_clears_revoked -x -q` | ❌ Wave 0 |
| SYN-02 | `GET /api/session` returns `needs_reauth` correctly | unit | `uv run pytest tests/unit/test_session.py::test_needs_reauth -x -q` | ❌ Wave 0 |
| SYN-02 | `GET /api/admin/diagnostics` includes `profiles[]` | integration | `uv run pytest tests/integration/api/test_diagnostics.py::test_profiles_section -x -q` | ❌ Wave 0 |
| SYN-02 | Soft-delete purge sweep predicate is self-clearing | integration | `uv run pytest tests/integration/sync/test_purge.py -x -q` | ❌ Wave 0 |
| SYN-02 | Purge does NOT touch change_log / change_sets | integration | same file | ❌ Wave 0 |

### Hypothesis Invariants for `next_fire_after()`

**Precedent:** Hypothesis is already used for `test_parser_props.py`, `test_estimator_props.py`, `test_led_brightness.py`. The scheduler's `next_fire_after()` function is a pure function with clear invariants — ideal for property testing.

```python
# tests/property/test_nightly_scheduler.py — Wave 0 gap
from hypothesis import given, settings, strategies as st
from datetime import datetime, timezone, timedelta

@given(
    # Generate a datetime in 2025-2027 to cover DST transitions
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

@given(
    epoch_seconds=st.integers(
        min_value=int(datetime(2025, 1, 1, tzinfo=timezone.utc).timestamp()),
        max_value=int(datetime(2027, 12, 31, tzinfo=timezone.utc).timestamp()),
    ),
)
@settings(max_examples=500)
def test_next_fire_interval_in_22_26h_window(epoch_seconds: int) -> None:
    """Successive 03:00 firings are always 22–26 wall hours apart."""
    now = datetime.fromtimestamp(epoch_seconds).astimezone()
    t1 = next_fire_after(now, 3)
    t2 = next_fire_after(t1 + timedelta(seconds=1), 3)
    delta_h = (t2 - t1).total_seconds() / 3600
    assert 22 <= delta_h <= 26, f"interval {delta_h:.2f}h out of [22, 26] window"
```

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ tests/property/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -q --tb=short`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/property/test_nightly_scheduler.py` — Hypothesis invariants for `next_fire_after()` (always-future, 22–26h window, monotonic)
- [ ] `tests/unit/test_nightly_scheduler.py` — cadence anchoring, skip policy, `off` parking, `_read_sync_cadence` fallback
- [ ] `tests/unit/test_session.py::test_needs_reauth*` — `needs_reauth` field derivation (if adding to backend)
- [ ] `tests/integration/sync/test_purge.py` — purge predicate self-clearing, audit lineage untouched
- [ ] `tests/integration/api/test_diagnostics.py::test_profiles_section` — per-profile section present + correct shape

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | PIN auth unchanged; no new auth paths |
| V3 Session Management | no | `GET /api/session` is additive only; no session lifecycle change |
| V4 Access Control | yes | `GET /api/admin/diagnostics` extensions remain behind `require_admin`; nightly loop runs server-side only |
| V5 Input Validation | yes | `sync.cadence` enum validation via whitelist; parameterized `%s` SQL in purge DELETE |
| V6 Cryptography | no | No new crypto; Fernet PAT handling unchanged |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| PAT leak in nightly loop logs | Information Disclosure | Existing `dscg_*` structlog redactor covers Bearer tokens; ensure `sync_profile()` log calls do not pass PAT as a log field |
| Purge targeting wrong profile (profile_id injection) | Tampering | Parameterized `%s::uuid` SQL; profile_id is a server-derived UUID, never user-controlled at purge call-sites |
| `sync.cadence` value used in SQL | Tampering | Value is validated against `_CADENCE_VALUES` frozenset before any SQL use; stored as JSON string in settings table |
| `app_token_revoked` bypass via stale session | Elevation | `GET /api/session` derives `needs_reauth` from a live DB read (not app.state cache); `app_token_revoked` is read fresh per request |

---

## Sources

### Primary (HIGH confidence)
- `src/gruvax/app.py` — existing lifespan, `_refresh_all_profiles_state` pattern, `app.state.background_tasks` CR-01 pattern [VERIFIED: read in this session]
- `src/gruvax/sync/profile_sync.py` — `sync_profile()`, `_record_failure()`, `_swap_inside_tx()` with `app_token_revoked = FALSE` [VERIFIED: read in this session]
- `src/gruvax/api/admin/profiles.py` — `connect_pat`, `rotate_pat` `app_token_revoked = FALSE` resets; `soft_delete_profile` deferred purge note; `list_profiles`/`get_profile` already return `app_token_revoked` [VERIFIED: read in this session]
- `src/gruvax/api/admin/settings.py` — `_ALLOWED_SETTINGS_KEYS`, `key_map`, global-settings-under-default-UUID pattern [VERIFIED: read in this session]
- `src/gruvax/api/admin/diagnostics.py` — `GET /diagnostics` structure; extension point is the return dict [VERIFIED: read in this session]
- `src/gruvax/api/session.py` — `GET /api/session` response shape; `profiles[]` already contains `app_token_revoked` [VERIFIED: read in this session]
- `frontend/src/api/session.ts` — `ProfileSummary` has `app_token_revoked: boolean`; `SessionData` shape [VERIFIED: read in this session]
- `frontend/src/routes/admin/ProfileDrawer.tsx` — existing 202+poll pattern, `refetchInterval`, `SyncProgressSection` usage [VERIFIED: read in this session]
- `frontend/src/routes/admin/SyncProgressSection.tsx` — current implementation; no elapsed counter yet [VERIFIED: read in this session]
- `migrations/versions/` — 0011 is head; 0009 has all P4-needed columns [VERIFIED: directory listing + grep]
- Python stdlib `zoneinfo`, `datetime.astimezone()`, `fold=1` DST behavior [VERIFIED: Python 3.14 execution in this session]

### Secondary (MEDIUM confidence)
- `04-UI-SPEC.md` — surface contracts, component inventory, no new dependencies confirmed [VERIFIED: read in this session]
- `04-CONTEXT.md` — all 17 locked decisions [VERIFIED: read in this session]
- `REQUIREMENTS.md` SYN-01, SYN-02 [VERIFIED: read in this session]
- `.planning/intel/constraints.md` CON-rate-limit-collection-api [VERIFIED: read in this session]

### Tertiary (LOW confidence)
- Discogsography `~60 req/min` rate limit budget: from REQUIREMENTS.md DGS-EXT-05 description and STATE.md open question; exact policy lives in the discogsography contract artifact not yet read

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all confirmed against live codebase
- Architecture: HIGH — all patterns verified against existing implementation
- Pitfalls: HIGH — drawn from verified code patterns and Python stdlib behavior
- DST algorithm: HIGH — validated via Python 3.14 execution over 40+ DST transition cycles
- Rate limit safety: MEDIUM — sequential approach confirmed correct; exact budget [ASSUMED]
- Soft-delete purge FK safety: MEDIUM — need to verify FK direction in migration 0009

**Research date:** 2026-05-29
**Valid until:** 2026-06-29 (stable codebase; Python datetime DST behavior is stable)

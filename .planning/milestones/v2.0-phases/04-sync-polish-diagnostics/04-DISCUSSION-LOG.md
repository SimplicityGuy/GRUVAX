# Phase 4: Sync polish + diagnostics - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-29
**Phase:** 4-sync-polish-diagnostics
**Areas discussed:** Nightly scheduler semantics, 401 re-auth surfacing, Soft-delete cache-purge task, Diagnostics cards + Sync-now UX

---

## Nightly scheduler semantics

### Timing model
| Option | Description | Selected |
|--------|-------------|----------|
| Wall-clock anchored to 03:00 local | Compute next 03:00-local occurrence, sleep until then, reschedule after each run; matches "03:00 local" literally, predictable | ✓ |
| Fixed interval from startup | Sleep cadence-hours from startup; simpler but drifts off 03:00, runs at arbitrary times | |

### Missed runs
| Option | Description | Selected |
|--------|-------------|----------|
| Catch-up on startup if stale | On loop start, sync any non-revoked profile with last_sync_at older than cadence, then resume schedule | ✓ |
| Wait for next scheduled 03:00 | No catch-up; can leave a profile stale/un-reauthed for nearly a full cadence after downtime | |

### Cadence anchor
| Option | Description | Selected |
|--------|-------------|----------|
| Anchored multiples of 03:00 | 24h→03:00; 12h→03+15; 6h→03/09/15/21; always includes overnight run, clean clock times | ✓ |
| Every N hours from a single 03:00 base | Functionally identical for 24/12/6; planner-discretion implementation detail | |

### Skip policy (multi-select)
| Option | Description | Selected |
|--------|-------------|----------|
| Skip profiles with a revoked PAT | Avoid re-401 spam against discogsography; nightly auto-resumes after rotate | ✓ |
| Skip profiles already mid-sync | Avoid racing the advisory lock for a guaranteed no-op | ✓ |
| Don't skip — always attempt all | Relies entirely on advisory lock; accepts repeated 401s | |

### Timezone
| Option | Description | Selected |
|--------|-------------|----------|
| Server process local time | Deployment host / container TZ; no new setting; single-home-LAN | ✓ |
| Configurable timezone setting | Adds setting + validation + UI; likely YAGNI for single-household | |

### Off + live reload
| Option | Description | Selected |
|--------|-------------|----------|
| Loop re-reads cadence each tick; "off" parks it | Cadence change / off takes effect next tick, no restart | ✓ |
| Cadence read once at startup | Requires container restart to change; control would be inert | |

**User's choice:** All recommended options.
**Notes:** Cadence stored as a global `sync.cadence` settings key under the default-profile UUID (existing pattern). "03:00 local" taken literally per owner's "syncs overnight" mental model.

---

## 401 re-auth surfacing

### Canonical signal
| Option | Description | Selected |
|--------|-------------|----------|
| app_token_revoked boolean | Dedicated boolean, unambiguous, survives later non-PAT error overwriting last_sync_error | ✓ |
| last_sync_error == 'pat_rejected' | A subsequent rate_limited/network failure would mask it; less robust | |
| Both — boolean badge + error-tag detail copy | Richest UX, more wiring | |

### Kiosk delivery
| Option | Description | Selected |
|--------|-------------|----------|
| Field on GET /api/session | Kiosk already consumes it; no new endpoint or SSE event type | ✓ |
| Push via per-profile SSE | Most immediate but ≤24h bar doesn't need realtime; new event type | |
| Dedicated poll endpoint | Redundant with GET /api/session | |

### Clearing
| Option | Description | Selected |
|--------|-------------|----------|
| Auto-clear on successful rotate+sync | State = function of sync health; no manual dismiss | ✓ |
| Auto-clear + manual kiosk dismiss | Risks hiding a real unresolved problem | |

### Kiosk UX
| Option | Description | Selected |
|--------|-------------|----------|
| Non-blocking banner; search works on cached data | Re-auth = stale sync, not lost cache; preserves core value | ✓ |
| Block/overlay until re-authed | Defeats "search always works" core value | |

**User's choice:** All recommended options.
**Notes:** Detection already exists server-side. Planner must confirm the rotate path resets `app_token_revoked=FALSE` and wire it if missing (D4-09).

---

## Soft-delete cache-purge task

### Trigger
| Option | Description | Selected |
|--------|-------------|----------|
| At delete-time + startup safety sweep | Prompt cleanup + restart-safe recovery for interrupted purges | ✓ |
| At delete-time only | Orphans rows forever if process dies before task runs | |
| Swept by the nightly loop only | Delays cleanup up to a cadence; couples unrelated concerns | |

### Predicate
| Option | Description | Selected |
|--------|-------------|----------|
| deleted_at NOT NULL AND profile_collection rows exist | Natural, self-clearing, no schema change | ✓ |
| Add a purged_at column | Explicit audit but needs a migration for a derivable state | |

### Scope
| Option | Description | Selected |
|--------|-------------|----------|
| profile_collection rows only | Matches criterion #4; keeps config + audit lineage | ✓ |
| profile_collection + per-profile config tables | Goes beyond criterion; forecloses future undelete | |

### Row lifecycle
| Option | Description | Selected |
|--------|-------------|----------|
| No — stays soft-deleted forever | Keeps change_log/change_sets FKs valid (criterion #4) | ✓ |
| Hard-delete after purge | Breaks audit-lineage FKs | |

**User's choice:** All recommended options.
**Notes:** Devices already detached at delete-time (P3 D3-05); registries already evicted synchronously (P2 D2-03). P4's purge is narrowly the bulky profile_collection rows.

---

## Diagnostics cards + Sync-now UX

### Placement
| Option | Description | Selected |
|--------|-------------|----------|
| New "Profiles" section on /admin/diagnostics | Matches criterion #3 wording; reuses Nordic Grid cards | ✓ |
| Inside the Profiles admin list instead | Contradicts criterion; duplicates diagnostics page role | |
| Both surfaces | Most complete but small marginal value (badge already exists) | |

### Freshness
| Option | Description | Selected |
|--------|-------------|----------|
| Poll on an interval / refetch | Matches existing admin polling; no SSE wiring for admin screen | ✓ |
| Live via per-profile SSE | Realtime but unnecessary for admin diagnostics | |
| Static on load + manual refresh | Won't reflect a sync completing elsewhere | |

### Progress UX
| Option | Description | Selected |
|--------|-------------|----------|
| Indeterminate spinner + elapsed, reuse 202+poll | Atomic staging-swap has no natural page progress; zero backend change | ✓ |
| Real page/item progress bar | Over-engineered for a ~15-request, few-second sync | |

### Sync all
| Option | Description | Selected |
|--------|-------------|----------|
| Defer — per-profile "Sync now" only | Criterion #5 is singular; nightly already syncs all | ✓ |
| Include "Sync all profiles now" | New capability beyond criterion; rate-limit consideration | |

**User's choice:** All recommended options.
**Notes:** "Sync all" noted as a backlog candidate. Diagnostics cards extend GET /api/admin/diagnostics with per-profile sync metadata.

---

## Claude's Discretion

- Exact next-03:00-local computation (zoneinfo + DST), loop sleep granularity, how "off" parks (sleep-and-recheck interval).
- Whether catch-up-on-startup and soft-delete-purge startup sweeps are one combined lifespan pass or two.
- `sync.cadence` value encoding (string vs hours-int with 0/null=off) + settings-whitelist validation.
- Toast/spinner/banner/badge copy + styling (Nordic Grid; `/gsd-ui-phase 4` available).
- Diagnostics card layout/grid, refetch interval, optional per-card "Sync now" button.
- Startup-catch-up sync-storm avoidance (sequential, same skip policy as nightly).

## Deferred Ideas

- "Sync all profiles now" manual button → backlog (nightly already covers it).
- Configurable timezone setting → out (server-local TZ authoritative for single-home-LAN).
- Real page/item Sync-now progress bar → rejected (over-engineered for the data volume).
- `purged_at` audit column → rejected (state derivable from row presence).
- SSE-live diagnostics / SSE-pushed re-auth → rejected (poll + GET /api/session field suffice).
- Milestone-level carries: self-connect PAT → v2.1; OAuth2 device-grant (AUTH-01) → v2.2; QR pairing (DEV-04) → v2.1; real LED hardware → independent milestone.

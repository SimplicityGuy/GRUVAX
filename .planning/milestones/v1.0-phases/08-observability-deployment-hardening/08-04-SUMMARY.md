---
phase: 08
plan: 04
subsystem: admin-diagnostics
tags: [observability, admin, diagnostics, frontend, react, fastapi]
dependency_graph:
  requires: ["08-02", "08-03"]
  provides: ["diagnostics-endpoint", "admin-diagnostics-page"]
  affects: ["admin-router", "admin-shell-nav", "app-routes"]
tech_stack:
  added: []
  patterns:
    - "Admin-gated GET + POST via Depends(require_admin) — same as leds.py"
    - "app.state getattr fallback for ring buffers (slow_query_ring, log_ring_buffer)"
    - "psycopg pool.get_stats() (sync, non-blocking) for size_used/size_min"
    - "React useEffect-on-mount + explicit Refresh (no polling, no SSE)"
    - "Inline confirm flow: RESET STATS → CONFIRM RESET? → YES, RESET / KEEP STATS"
    - "el() + replaceChildren() for recent logs terminal (never innerHTML)"
    - "Token-only CSS (no hardcoded hex)"
key_files:
  created:
    - src/gruvax/api/admin/diagnostics.py
    - tests/integration/test_diagnostics.py
    - frontend/src/routes/admin/Diagnostics.tsx
    - frontend/src/routes/admin/Diagnostics.css
  modified:
    - src/gruvax/api/admin/router.py
    - frontend/src/api/adminClient.ts
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/App.tsx
decisions:
  - "psycopg pool.get_stats() is sync + non-blocking (confirmed in RESEARCH OQ7)"
  - "sync_age_seconds prefers app.state cached value over live DB query"
  - "recent_logs capped at last 20 reversed entries (newest-first, D-12)"
  - "slow_queries: full ring buffer reversed (newest-first; backend caps at 50)"
  - "human-verify checkpoint auto-approved (--auto mode); visual UAT deferred to phase verifier"
metrics:
  duration: "11 minutes"
  completed_date: "2026-05-25"
  tasks: 3
  files_changed: 8
---

# Phase 8 Plan 04: Admin Diagnostics Page Summary

**One-liner:** Admin-gated `/api/admin/diagnostics` (7 SC#2 rows) + inline reset-stats POST + `/admin/diagnostics` React page with Nordic Grid styling and manual-refresh only.

## What Was Built

### Task 1: Diagnostics Backend

`src/gruvax/api/admin/diagnostics.py` — new admin sub-router with two endpoints:

- `GET /api/admin/diagnostics` — returns 7 SC#2 rows:
  1. `sync_age_seconds` — from `app.state` cache or live `get_sync_staleness_seconds()`
  2. `top_searched` — top 10 by all-time search count via `get_top_searched(pool, 10)`
  3. `slow_queries` — ring buffer (`app.state.slow_query_ring`) reversed (newest-first)
  4. `mqtt` — `"connected"` / `"disconnected"` from `app.state.mqtt_ok`
  5. `pool` — `{size_used, size_min}` from `db_pool.get_stats()` (sync, non-blocking)
  6. `phantom_boundary_count` — via `get_phantom_boundary_count(pool)`
  7. `recent_logs` — last 20 from `app.state.log_ring_buffer`, reversed (newest-first)

- `POST /api/admin/diagnostics/reset-stats` — calls `reset_record_stats(pool)`, logs the action

Both endpoints use `Depends(require_admin)` — session + CSRF gated (T-08-13). No secrets
in payload (no connection string, env dump, PIN, or raw query text — T-08-14).

`src/gruvax/api/admin/router.py` — `diagnostics_router` added to `create_admin_router()`.

`tests/integration/test_diagnostics.py` — 6 integration tests:
- `test_staleness` — sync_age_seconds is float or null
- `test_counters` — all 7 keys present; pool has size_used/size_min
- `test_no_secrets` — no session_secret/database_url/pin in body
- `test_unauthenticated_get` — 401/403 without session
- `test_unauthenticated_reset` — 401/403 without session
- `test_reset_stats` — seed → GET (non-empty) → POST reset → GET (empty)

All 6 pass. `mypy --strict` exits 0.

### Task 2: Frontend Page

`frontend/src/routes/admin/Diagnostics.tsx` — React page with 6 sections:

1. **DiagnosticsToolbar** — REFRESH button + "Last refreshed: {relative time}". REFRESHING… + disabled while loading.
2. **StalenessSection** — single row with DM Mono age value + pill badge (OK/STALE/OUTDATED at 3d/14d).
3. **TopSearchedSection** — 5-column table (artist/title, 4 count columns) + inline reset confirm flow per UI-SPEC copy contract ("RESET STATS" → "CONFIRM RESET?" + "YES, RESET" / "KEEP STATS"). Stats cleared success auto-hides after 3s.
4. **SlowQuerySection** — 5-column table (endpoint, total ms, DB ms, threshold, time) with SLO sub-label.
5. **SystemStatusSection** — 3 status rows with 8px colored dots: MQTT BROKER, POSTGRES POOL, PHANTOM BOUNDARIES.
6. **RecentLogsSection** — dark terminal (`--gruvax-blue-darker` bg) built via `el()`/`replaceChildren()`, never innerHTML. Level color-coded (ERROR/WARNING/INFO/DEBUG).

Data loads in single `useEffect` on mount. Explicit REFRESH re-calls `getDiagnostics()`. No polling, no SSE (D-11 locked).

`frontend/src/routes/admin/Diagnostics.css` — token-only CSS. All colors via `var(--gruvax-*)`. Four typography sizes: 24px / 16px / 14px (18px is kiosk-banner only). Barlow Condensed ALL CAPS labels, DM Mono data, Space Grotesk body. Shimmer skeleton via `@keyframes diag-shimmer`. 44px min-height touch targets. Focus rings via `outline: 2px solid var(--gruvax-blue)`.

`frontend/src/api/adminClient.ts` — added `DiagnosticsData` type (7 keys), `TopSearchedRow`, `SlowQueryEntry`, `LogEntry` interfaces, `getDiagnostics()` and `resetStats()` functions.

`frontend/src/routes/admin/AdminShell.tsx` — DIAGNOSTICS NavLink appended after IMPORT.

`frontend/src/App.tsx` — `/admin/diagnostics` route registered under AdminShell.

`tsc --noEmit` passes. `npm run build` succeeds.

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Checkpoint: Auto-approved (--auto mode)

**Task 3: checkpoint:human-verify** was auto-approved per the `--auto` mode execution
instructions. The orchestrator instructs: complete all implementation, run automated
verification, note the deferred manual verification.

**Automated verification completed:**
- `uv run pytest tests/integration/test_diagnostics.py -q` → 6 passed
- `uv run mypy --strict src/gruvax/api/admin/diagnostics.py` → 0 errors
- `cd frontend && npx tsc --noEmit` → 0 errors
- `cd frontend && npm run build` → success

**Deferred to human UAT (phase verifier):**
- Open `/admin/diagnostics`, confirm all 5 section cards render with Nordic Grid styling
- REFRESH reloads data; network tab confirms no continuous polling
- RESET STATS → CONFIRM RESET? inline (no modal); KEEP STATS no-op; YES, RESET clears top_searched
- Typography uses only 24/18/16/14px sizes; ALL-CAPS Barlow labels

## Known Stubs

None — all 7 data rows are wired to live backend functions from Plan 02 and Plan 03.

## Threat Flags

No new threat surface beyond what is documented in the plan's STRIDE register:
- GET /api/admin/diagnostics — covered by T-08-14 (admin-gated, no secrets)
- POST /api/admin/diagnostics/reset-stats — covered by T-08-13 (admin+CSRF gated)

## Self-Check: PASSED

Files exist:
- `src/gruvax/api/admin/diagnostics.py` — FOUND
- `tests/integration/test_diagnostics.py` — FOUND
- `frontend/src/routes/admin/Diagnostics.tsx` — FOUND
- `frontend/src/routes/admin/Diagnostics.css` — FOUND

Commits exist:
- `3800824` — feat(08-04): admin-gated diagnostics GET + reset-stats POST + tests
- `243d036` — feat(08-04): /admin/diagnostics React page + adminClient + nav + route

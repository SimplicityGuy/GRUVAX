---
status: partial
phase: 02-multi-profile-migration-profile-manager
source: [02-VERIFICATION.md, 02-04-SUMMARY.md, 02-06-SUMMARY.md, 02-07-SUMMARY.md]
started: 2026-05-28
updated: 2026-05-28
---

## Current Test

[awaiting human testing — requires a running stack: `just up-d` / `docker compose up -d`, with at least two profiles created via /admin/profiles]

## Tests

### 1. Single-profile auto-bind
expected: With exactly one active profile and no cookie, loading the kiosk at `/` goes straight to the search UI with NO `/select` flash; the Switch-profile button is hidden. `GET /api/session` sets `gruvax_browse_binding` and returns `profile_count:1` + non-null `bound_profile_id`.
result: [pending]

### 2. Two-profile picker
expected: With two profiles and no cookie, the kiosk redirects to `/select` showing two Nordic-Grid cards ("CHOOSE A COLLECTION"). Tapping one binds the cookie and lands on `/`. `GET /api/session` returns `profile_count:2`, `bound_profile_id:null` before selection.
result: [pending]

### 3. Switch-profile flow
expected: With 2 profiles, the Switch corner button (RefreshCw + SWITCH pill, bottom-right, `--gruvax-blue`) is visible; tapping shows the "Switch collection?" confirm modal; SWITCH returns to `/select`, STAY HERE dismisses.
result: [pending]

### 4. Two concurrent sessions, different profiles (SC#2)
expected: Two browser sessions on the LAN can concurrently view two different profiles, each bound by its own `gruvax_browse_binding` cookie.
result: [pending]

### 5. Admin connect-PAT → sync feedback (SC#1)
expected: `/admin/profiles` → + ADD PROFILE → name + paste valid PAT → CONNECT PAT shows CONNECTING… (synchronous test-sync) → SYNCING (animated badge, poll cadence ~2s, "N items processed") → CONNECTED + completion toast "Sync complete — N,### records".
result: [pending]

### 6. Cookie independence from admin PIN session (D2-10)
expected: Browse bind/unbind operations never affect the admin `gruvax_session` cookie, and vice versa. The browse cookie is non-HttpOnly + SameSite=Strict.
result: [pending]

### 7. Bound-but-unsynced empty-collection state (D2-03)
expected: Binding to a freshly-created (unsynced) profile shows "No records yet / This collection is syncing…" (not "No results"); the shelf grid shows dim/empty cells.
result: [pending]

## Summary

total: 7
passed: 0
issues: 0
pending: 7
skipped: 0
blocked: 0

## Gaps

## Known Limitations (from 02-VERIFICATION.md — confirm acceptable for V1)

- **Admin boundary-edit SSE reaches only the default profile.** Admin edit endpoints (cubes/segments/editing/history/import) still use the P1-compat `get_event_bus` dep aliased to the default profile's bus. A `boundary_changed` from an admin edit notifies only the default profile's kiosk SSE stream; non-default profiles' kiosks won't auto-refresh on admin boundary edits (no cross-profile leakage — just no notification). Flagged as intentional P1-compat; revisit if per-profile admin-edit push is needed.
- **SLO 2-profile guarantee is ambient.** The `search_client` benchmark fixture doesn't declare `second_profile` as an explicit dependency, so the "2+ profiles cached" condition for the p95 SLO gate is ambient rather than enforced.

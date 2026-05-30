---
phase: 02-multi-profile-migration-profile-manager
plan: "04"
subsystem: session-bootstrap
tags: [session, browse-binding, cookie, api, auth]
dependency_graph:
  requires: ["02-02"]
  provides: ["browse-binding-session-layer", "GET /api/session", "POST /api/session/bind", "DELETE /api/session/bind"]
  affects: ["src/gruvax/auth/sessions.py", "src/gruvax/api/deps.py", "src/gruvax/api/session.py", "src/gruvax/app.py"]
tech_stack:
  added: []
  patterns: ["browse-binding-cookie-D2-10", "single-profile-auto-bind-D2-08", "no-pin-browse-api-R7"]
key_files:
  created:
    - src/gruvax/api/session.py
  modified:
    - src/gruvax/auth/sessions.py
    - src/gruvax/api/deps.py
    - src/gruvax/app.py
    - tests/integration/test_session_bootstrap.py
decisions:
  - "Browse-binding cookie uses plain UUID string value (not signed) — server validates against active-profiles registry on per-profile endpoints (D2-04 / T-02-04-01)"
  - "Module-local admin_session override in test_session_bootstrap.py to bypass conftest's client.app dependency (httpx AsyncClient does not expose .app)"
  - "Cookie-clear in test_two_profiles_unbound uses client.cookies.delete() because module-scoped client accumulates cookies across tests"
metrics:
  duration: "~45 minutes"
  completed: "2026-05-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 4
---

# Phase 02 Plan 04: Browse-Binding Session Layer Summary

**One-liner:** No-PIN browse-binding session layer with GET /api/session single-profile auto-bind (D2-08), POST/DELETE /api/session/bind, and an independent gruvax_browse_binding cookie decoupled from the admin PIN session (D2-10).

## What Was Built

### Cookie Contract (sessions.py)

Three new exports alongside the existing `SESSION_COOKIE` / `CSRF_COOKIE`:

- `BROWSE_BINDING_COOKIE = "gruvax_browse_binding"` — public constant (promoted from `_BROWSE_BINDING_COOKIE` private literal in deps.py)
- `set_browse_binding_cookie(response, profile_id, secure=False, max_age=7*24*3600)` — httponly=False, samesite="strict", 7-day max_age
- `clear_browse_binding_cookie(response, secure=False)` — matching delete_cookie attrs per CR-04

Cookie attributes rationale:
- `httponly=False` — SPA must read the value to build the per-profile SSE URL
- `samesite="strict"` — blocks cross-site POST forgery on home LAN (T-02-04-04)
- `secure=False` — home-LAN HTTP; activates when TLS is added
- `max_age=7 days` — kiosk Chromium survives Pi restarts without hitting /select

### Session API (src/gruvax/api/session.py)

**GET /api/session** — No PIN required (R7, D2-10):
- Queries `gruvax.profiles WHERE deleted_at IS NULL ORDER BY created_at`
- Returns `{profile_count, bound_profile_id, profiles[]}`
- Single-profile auto-bind (D2-08): when `len(profiles)==1` and no cookie, sets `gruvax_browse_binding` cookie on the response and returns the profile id as `bound_profile_id`
- Multi-profile unbound: returns `bound_profile_id: null` so SPA routes to /select
- T-02-04-03 mitigation: `profiles[]` excludes `app_token_encrypted` and `discogsography_user_id`

**POST /api/session/bind** — No PIN required:
- Validates `profile_id` as UUID (400 `invalid_uuid`)
- Validates against active profiles (404 `profile_not_found`)
- Sets `gruvax_browse_binding` cookie; returns `{status: "bound", profile_id}`

**DELETE /api/session/bind** — No PIN required:
- Clears `gruvax_browse_binding` cookie; returns `{status: "unbound"}`

### GET /api/session JSON shape (for frontend Plan 02-06)

```json
{
  "profile_count": 1,
  "bound_profile_id": "00000000-0000-0000-0000-000000000001",
  "profiles": [
    {
      "id": "00000000-0000-0000-0000-000000000001",
      "display_name": "Default",
      "last_sync_at": "2026-05-28T18:54:54.544705+00:00",
      "last_sync_status": "completed",
      "last_sync_item_count": 3000,
      "app_token_revoked": false
    }
  ]
}
```

### Router Registration (app.py)

`session_router` registered with `app.include_router(session_router, prefix="/api")` BEFORE the StaticFiles mount (Pitfall 3 — the html=True catch-all must not intercept /api/session).

### deps.py Promotion

`_BROWSE_BINDING_COOKIE` (private literal) replaced with `BROWSE_BINDING_COOKIE` imported from `gruvax.auth.sessions` — single source of truth for the cookie name string `"gruvax_browse_binding"`.

## Test Results

All 4 tests in `tests/integration/test_session_bootstrap.py` GREEN:
- `test_single_profile_auto_binds` — auto-bind sets cookie + returns bound_profile_id
- `test_two_profiles_unbound` — multi-profile, no cookie → bound_profile_id null
- `test_bind_then_unbind` — POST sets cookie with profile_id; DELETE clears it
- `test_binding_independent_of_admin` — bind/unbind does not touch gruvax_session; admin logout does not touch gruvax_browse_binding

`tests/integration/test_admin_auth.py` — 8 tests GREEN (admin auth regression passes).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Module-scoped httpx client accumulates cookies across tests**
- **Found during:** Task 1 — test_two_profiles_unbound received bound_profile_id from test_single_profile_auto_binds' auto-bind cookie
- **Issue:** Module-scoped `AsyncClient` stores cookies in jar; test_two_profiles_unbound comment says "No cookies" but the prior test's auto-bind cookie persisted
- **Fix:** Added `client.cookies.delete(BROWSE_BINDING_COOKIE)` before the GET call in test_two_profiles_unbound
- **Files modified:** `tests/integration/test_session_bootstrap.py`
- **Commit:** da16a74

**2. [Rule 3 - Blocking] conftest admin_session fixture uses client.app which AsyncClient lacks**
- **Found during:** Task 2 — test_binding_independent_of_admin ERROR because conftest's admin_session does `client.app.state.db_pool` but test module's client is a plain `AsyncClient`
- **Issue:** test_session_bootstrap.py provides an httpx `AsyncClient` (no `.app` attr); conftest admin_session was designed for TestClient wrappers
- **Fix:** Added a module-local `admin_session` fixture override that uses the existing seeded PIN and calls `/api/admin/login` directly; PIN is already seeded by the module's `client` fixture
- **Files modified:** `tests/integration/test_session_bootstrap.py`
- **Commit:** 65ee914

## Known Stubs

None — all endpoints return real DB data; cookie values are real UUID strings.

## Threat Flags

No new threat surface beyond what was documented in the plan's `<threat_model>`. The three endpoints cross the LAN-browser trust boundary as designed (T-02-04-01/02/03/04 all addressed).

## Self-Check: PASSED

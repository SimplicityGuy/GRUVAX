---
phase: "03"
plan: "02"
subsystem: "admin-auth"
tags: [auth, pin, sessions, csrf, rate-limit, frontend, admin]
dependency_graph:
  requires: ["03-01"]
  provides: ["admin-auth-layer", "admin-session-management", "frontend-admin-routes"]
  affects: ["03-03", "03-04", "03-05"]
tech_stack:
  added:
    - "passlib[argon2] — Argon2id PIN hashing"
    - "slowapi + limits — inline rate limiting (no SlowAPIMiddleware)"
    - "itsdangerous — URLSafeSerializer for session cookie signing"
    - "Zustand persist middleware — pendingChangeSet only, auth state NOT persisted"
    - "react-router v7 — /admin/* route tree"
  patterns:
    - "Double-submit CSRF: HttpOnly gruvax_session + non-HttpOnly gruvax_csrf + X-CSRF-Token header"
    - "Sliding session window (idle TTL) + hard cap (30 min) stored in gruvax.admin_sessions"
    - "Rate limit inline (limits.FixedWindowRateLimiter.hit()) — avoids BaseHTTPMiddleware ASGI state leak"
    - "Zustand store with partialize — only pendingChangeSet persisted to localStorage"
key_files:
  created:
    - "src/gruvax/auth/pin.py"
    - "src/gruvax/auth/sessions.py"
    - "src/gruvax/api/admin/limiter.py"
    - "src/gruvax/api/admin/login.py"
    - "src/gruvax/api/admin/settings.py"
    - "src/gruvax/api/admin/router.py"
    - "src/gruvax/api/deps.py"
    - "scripts/set_pin.py"
    - "tests/unit/test_pin.py"
    - "tests/unit/test_sessions.py"
    - "tests/integration/test_admin_auth.py"
    - "frontend/src/api/adminClient.ts"
    - "frontend/src/state/adminStore.ts"
    - "frontend/src/routes/admin/PinOverlay.tsx"
    - "frontend/src/routes/admin/AdminShell.tsx"
    - "frontend/src/routes/admin/Settings.tsx"
    - "frontend/src/routes/admin/admin.css"
  modified:
    - "src/gruvax/app.py"
    - "frontend/src/App.tsx"
    - "frontend/src/api/types.ts"
decisions:
  - "Rate limit enforced inline via limits.FixedWindowRateLimiter.hit() — SlowAPIMiddleware removed to avoid BaseHTTPMiddleware ASGI scope state leak in test transport"
  - "secure=False on all cookies intentionally — home-LAN HTTP, not public HTTPS deployment"
  - "httponly=False on CSRF cookie intentionally — SPA must read gruvax_csrf to echo as X-CSRF-Token"
  - "Zustand auth state NOT persisted — on mount, poll /api/admin/session to restore login"
  - "PIN never logged — always log pin_attempt=redacted (Pitfall 12, T-03-06)"
  - "set-pin CLI at scripts/set_pin.py (registered as gruvax-set-pin in pyproject.toml)"
metrics:
  duration: "~3 hours (across two sessions)"
  completed: "2026-05-21T05:03:24Z"
  tasks_completed: 2
  tests_added: 16
---

# Phase 03 Plan 02: Admin Auth + Frontend Admin Slice Summary

Argon2id PIN auth with sliding-window server-side sessions, double-submit CSRF, inline rate limiting (5/5min per IP), `require_admin` FastAPI dependency, `gruvax-set-pin` CLI, and the complete `/admin` React route tree (PinOverlay, AdminShell, Settings stub).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Backend auth module + admin endpoints + set-pin CLI | `9354a40` | 11 files created/modified |
| 2 | Frontend admin slice — adminClient, store, routing, components | `1282e9c` | 8 files created/modified |

## Verification Results

All plan success criteria met:

- `uv run pytest tests/unit/test_pin.py tests/unit/test_sessions.py tests/integration/test_admin_auth.py` — **16 passed**
- `uv run ruff check src/gruvax/auth src/gruvax/api/admin src/gruvax/api/deps.py` — **All checks passed**
- `uv run mypy src/gruvax/auth src/gruvax/api/admin src/gruvax/api/deps.py` — **Success: no issues found in 9 source files**
- `cd frontend && npx tsc --noEmit` — **0 errors**
- `cd frontend && npm run build` — **built in 199ms**

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SlowAPIMiddleware ASGI state leak causes rate limit counter to stick at 1**

- **Found during:** Task 1 — integration test `test_rate_limit` showed the rate limit firing only once (counter never incrementing past 1 across requests)
- **Root cause:** `SlowAPIMiddleware` (a `BaseHTTPMiddleware`) sets `_rate_limiting_complete=True` on `request.state` after the first request. The `LifespanManager` + httpx `ASGITransport` pattern shares the ASGI scope's `"state"` dict across all requests in the same process, causing the flag to leak from request N to request N+1. The SlowAPI decorator sees the flag and skips counter accumulation on every subsequent request.
- **Fix:** Removed `SlowAPIMiddleware` from `app.py` entirely. Implemented rate limiting inline in the login endpoint body using `limits.strategies.FixedWindowRateLimiter.hit()` directly — no SlowAPI state flags, no decorator wrapper. Set `request.state.view_rate_limit` before `hit()` so the `_rate_limit_exceeded_handler` can inject `X-RateLimit-*` response headers.
- **Files modified:** `src/gruvax/app.py`, `src/gruvax/api/admin/login.py`, `src/gruvax/api/admin/limiter.py`
- **Commits:** `9354a40`

**2. [Rule 1 - Bug] Rate limit counter persists across tests causing cascading failures**

- **Found during:** Task 1 — `test_login_success` and other tests failed with 429 after `test_rate_limit` exhausted the per-IP counter
- **Fix:** Added `autouse=True` fixture in `test_admin_auth.py` that calls `limiter.reset()` before each test to restore a clean counter state
- **Files modified:** `tests/integration/test_admin_auth.py`
- **Commits:** `9354a40`

**3. [Rule 3 - Blocking] TypeScript `erasableSyntaxOnly` flag rejects parameter property syntax**

- **Found during:** Task 2 — frontend build failed on `AuthError` and `RateLimitError` constructor definitions using `public readonly` parameter properties
- **Fix:** Rewrote error class constructors using explicit property declarations (field declaration + assignment in body) instead of TypeScript parameter property shorthand
- **Files modified:** `frontend/src/api/adminClient.ts`
- **Commits:** `1282e9c`

**4. [Rule 1 - Bug] Ruff lint failures: unused imports, noqa directives, EN dash in docstring**

- **Found during:** Task 1 post-commit lint run
- **Fix:** Ran `uv run ruff check --fix` then manual cleanup — removed `CSRF_COOKIE`/`SESSION_COOKIE` unused imports from `login.py`, removed unnecessary `noqa` directives, replaced EN dash with hyphen in docstring
- **Files modified:** `src/gruvax/api/admin/login.py`
- **Commits:** `9354a40`

## Known Stubs

- **`frontend/src/routes/admin/Settings.tsx`** — Settings UI renders form fields for `nominal_capacity` and `idle_ttl_minutes` with `useQuery`/`useMutation` wired to `getAdminSettings`/`putAdminSettings`, but the change-PIN sub-form and undo/redo controls are placeholder state. Plan 03-03 (manual entry + undo) will flesh these out.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: csrf-bypass-on-login | `src/gruvax/api/admin/login.py` | Login POST is intentionally exempt from CSRF (no session yet exists to read the CSRF cookie from). This is correct — no pre-session state to protect — but future reviewers should confirm this exemption remains intentional if the login flow changes. |

## Self-Check

**Files exist:**
- `src/gruvax/auth/pin.py` — FOUND
- `src/gruvax/auth/sessions.py` — FOUND
- `src/gruvax/api/admin/login.py` — FOUND
- `src/gruvax/api/admin/settings.py` — FOUND
- `src/gruvax/api/admin/router.py` — FOUND
- `src/gruvax/api/deps.py` — FOUND
- `scripts/set_pin.py` — FOUND
- `frontend/src/api/adminClient.ts` — FOUND
- `frontend/src/state/adminStore.ts` — FOUND
- `frontend/src/routes/admin/PinOverlay.tsx` — FOUND
- `frontend/src/routes/admin/AdminShell.tsx` — FOUND
- `frontend/src/routes/admin/admin.css` — FOUND

**Commits exist:**
- `9354a40` — FOUND
- `1282e9c` — FOUND

## Self-Check: PASSED

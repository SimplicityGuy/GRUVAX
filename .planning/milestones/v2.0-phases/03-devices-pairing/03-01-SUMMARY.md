---
phase: "03-devices-pairing"
plan: "01"
subsystem: "data-model + auth"
tags: ["migration", "alembic", "devices", "pairing", "cookie", "auth", "DEV-01"]
dependency_graph:
  requires:
    - "03-00 (RED tests: test_migrate_0011.py + test_fingerprint_cookie.py)"
    - "migration 0010 (Alembic head before this plan)"
  provides:
    - "gruvax.devices table + four indexes"
    - "gruvax.pairing_codes table"
    - "issue_fingerprint_cookie / get_fingerprint / clear_fingerprint_cookie helpers"
    - "FINGERPRINT_COOKIE + FINGERPRINT_MAX_AGE constants"
  affects:
    - "03-02 (endpoints build on gruvax.devices + gruvax.pairing_codes + fingerprint helpers)"
    - "03-03 (SSE device events build on devices table)"
    - "03-04 (frontend PairView uses fingerprint cookie issued by these helpers)"
tech_stack:
  added: []
  patterns:
    - "Alembic migration: ALL SQL as module-level string constants (no f-strings, no inline triple-quotes)"
    - "Partial-unique index for active-row uniqueness + plain index for revoked-row lookup (Pitfall 5)"
    - "ON DELETE SET NULL FK for device-to-profile orphaning on soft-delete (D3-05)"
    - "secrets.token_urlsafe(32) for 256-bit CSPRNG fingerprint token (T-03-01)"
    - "max_age=30d for Chromium disk persistence of HttpOnly cookie (Pitfall 1)"
    - "CR-04 invariant: delete_cookie attributes match set_cookie exactly"
key_files:
  created:
    - "migrations/versions/0011_devices_and_pairing_codes.py"
  modified:
    - "src/gruvax/auth/sessions.py"
decisions:
  - "Non-partial idx_devices_fingerprint added alongside partial idx_devices_fingerprint_active to enable revoke-guard lookups of revoked rows (RESEARCH Pitfall 5 / Open Question 2 confirmed — ADD)"
  - "ON DELETE SET NULL on devices.profile_id so soft-delete orphans the device rather than cascade-deleting (D3-05)"
  - "FINGERPRINT_MAX_AGE = 30*24*3600 (30 days) — outlives any Pi reboot cycle; revocation is authoritative"
  - "get_fingerprint takes Any (not Request) to avoid importing fastapi.Request at module level, consistent with existing sessions.py TYPE_CHECKING pattern"
metrics:
  duration: "~10 minutes"
  completed_date: "2026-05-29"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
---

# Phase 3 Plan 01: Migration 0011 + Fingerprint Cookie Helpers Summary

**One-liner:** Alembic migration 0011 creating gruvax.devices + gruvax.pairing_codes with four spec-locked indexes and round-trip clean, plus three HttpOnly fingerprint cookie helpers in auth/sessions.py (issue/get/clear) with 30-day max_age for Chromium disk persistence.

## What Was Built

### Task 1: Migration 0011 — devices + pairing_codes

`migrations/versions/0011_devices_and_pairing_codes.py` introduces the device persistence model (DEV-01).

**gruvax.devices** — persists the RPi kiosk device-to-profile binding:
- `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
- `fingerprint TEXT NOT NULL` — opaque HttpOnly cookie value (256-bit CSPRNG token)
- `profile_id UUID REFERENCES gruvax.profiles(id) ON DELETE SET NULL` — nullable; NULL = orphaned device
- `display_name TEXT NOT NULL DEFAULT 'Unnamed device'`
- `revoked_at TIMESTAMPTZ` — non-NULL means device is revoked
- `last_seen_at TIMESTAMPTZ` — updated per request (throttled)
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

**gruvax.pairing_codes** — short-lived 4-digit code table with one-shot bind guard:
- `code CHAR(4) PRIMARY KEY` — zero-padded '0000'..'9999'
- `fingerprint TEXT NOT NULL` — the kiosk's fingerprint at code generation time
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `expires_at TIMESTAMPTZ NOT NULL` — 5-minute TTL
- `consumed_at TIMESTAMPTZ` — NULL = not consumed; "first wins" atomic UPDATE sets this

**Four indexes:**
1. `idx_devices_fingerprint_active` — UNIQUE partial WHERE revoked_at IS NULL (active device uniqueness per fingerprint)
2. `idx_devices_fingerprint` — plain non-partial (revoke-guard lookups MUST find revoked rows — RESEARCH Pitfall 5)
3. `idx_devices_profile_active` — UNIQUE partial WHERE revoked_at IS NULL AND profile_id IS NOT NULL (one active device per profile)
4. `idx_pairing_codes_expires` — plain on expires_at (TTL cleanup + range queries)

Round-trip verified: `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` exits 0.

### Task 2: Fingerprint cookie helpers in auth/sessions.py

Two new constants added after `BROWSE_BINDING_COOKIE`:
- `FINGERPRINT_COOKIE = "gruvax_device_fp"` — cookie name
- `FINGERPRINT_MAX_AGE = 30 * 24 * 3600` — 30 days; Chromium only persists cookies with explicit max_age (RESEARCH Pitfall 1)

Three new functions added between `clear_browse_binding_cookie` and `clear_session_cookies`:

**`issue_fingerprint_cookie(response, secure=False) -> str`**
- Generates `secrets.token_urlsafe(32)` (32 bytes = ~43 chars, 256-bit CSPRNG, T-03-01)
- Calls `response.set_cookie(FINGERPRINT_COOKIE, fp, httponly=True, samesite="strict", secure=secure, max_age=FINGERPRINT_MAX_AGE)`
- Returns the raw token value (caller stores to DB; never log — T-03-02)

**`get_fingerprint(request) -> str | None`**
- Returns `request.cookies.get(FINGERPRINT_COOKIE)` or None

**`clear_fingerprint_cookie(response, secure=False) -> None`**
- Calls `response.delete_cookie(FINGERPRINT_COOKIE, path="/", httponly=True, samesite="strict", secure=secure)`
- CR-04 invariant enforced: delete_cookie attributes match set_cookie attributes exactly

## Verification Evidence

```
pytest tests/unit/test_fingerprint_cookie.py tests/integration/test_migrate_0011.py -q
7 passed, 1 warning in 5.34s
```

```
alembic upgrade head && alembic downgrade -1 && alembic upgrade head
→ 0011 applied, 0011 reversed, 0011 re-applied (all exit 0)
```

## Deviations from Plan

None — plan executed exactly as written. The PATTERNS.md provided exact DDL constants and function signatures; the implementation follows them verbatim.

## Known Stubs

None. No stub values in the files created/modified by this plan. The migration creates real tables with real schemas; the cookie helpers are fully functional implementations.

## Threat Flags

No new network endpoints, auth paths, or file access patterns introduced beyond what was planned. The migration adds two tables within the existing `gruvax` schema trust boundary. The cookie helpers operate on the same session-management surface documented in the plan's threat model.

## Self-Check: PASSED

Files created/modified:
- `migrations/versions/0011_devices_and_pairing_codes.py` FOUND
- `src/gruvax/auth/sessions.py` (modified) FOUND

Commits:
- `c7ffc0c` feat(03-01): migration 0011 — devices + pairing_codes tables FOUND
- `1c990bf` feat(03-01): add HttpOnly fingerprint cookie helpers to auth/sessions.py FOUND

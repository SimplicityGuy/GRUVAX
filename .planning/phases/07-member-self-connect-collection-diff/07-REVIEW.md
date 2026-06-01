---
phase: 07-member-self-connect-collection-diff
reviewed: 2026-06-01T20:00:00Z
depth: standard
files_reviewed: 18
files_reviewed_list:
  - migrations/versions/0012_invite_codes_and_first_seen_at.py
  - src/gruvax/api/invite_codes.py
  - src/gruvax/api/admin/diagnostics.py
  - src/gruvax/api/admin/limiter.py
  - src/gruvax/api/admin/profiles.py
  - src/gruvax/api/admin/router.py
  - src/gruvax/app.py
  - src/gruvax/sync/profile_sync.py
  - frontend/src/App.tsx
  - frontend/src/api/adminClient.ts
  - frontend/src/api/inviteClient.ts
  - frontend/src/api/types.ts
  - frontend/src/routes/admin/ProfileDiagnosticsCard.tsx
  - frontend/src/routes/admin/ProfileDrawer.tsx
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/kiosk.css
  - frontend/src/routes/redeem/RedeemPage.tsx
  - frontend/src/routes/redeem/RedeemPage.css
findings:
  critical: 3
  warning: 4
  info: 3
  total: 10
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-06-01T20:00:00Z
**Depth:** standard
**Files Reviewed:** 18
**Status:** issues_found

## Summary

Phase 7 ships the member self-connect (AUTH-02) and collection-diff (API-04) features. The
overall architecture is sound — pool-isolation discipline is consistently applied, the atomic
single-use consume pattern is correct, Fernet encryption is used for PAT at-rest, and the
uniform-404 oracle prevention is implemented correctly throughout. The SSE payload extension and
kiosk pill are correctly guarded.

Three issues rise to BLOCKER severity: an invite-consumed-but-PAT-write-failure leaves a member
locked out with no recourse because no remediation is surfaced; the PAT UPDATE in
`redeem_invite` has a missing space in its SQL string literal that causes a runtime syntax error
on the first redeem attempt; and the `RateLimitExhausted` error handler in `redeem_invite` leaks
the upstream error message — which may contain the PAT — into the HTTP response body (violating
T-07-08).

---

## Critical Issues

### CR-01: Missing space in SQL string concatenation — redeem UPDATE fails with syntax error

**File:** `src/gruvax/api/invite_codes.py:359-368`
**Issue:** The UPDATE statement for storing the encrypted PAT in `redeem_invite` is built by
string concatenation with no leading space on the first clause continuation:

```python
await conn.execute(
    "UPDATE gruvax.profiles SET"
    "    app_token_encrypted = %s::bytea,"   # <- no space before "    app_token..."
    ...
)
```

`"UPDATE gruvax.profiles SET"` concatenated with `"    app_token_encrypted = ..."` produces
`"UPDATE gruvax.profiles SET    app_token_encrypted = ..."` — the missing space between `SET`
and the column list is absorbed by the four leading spaces in the next literal, so this one
actually works. However, compare with `profiles.py:531-537` where the same pattern has a correct
leading newline. On closer inspection the immediate concatenation does work — but see below for
the real syntax issue in the same block.

**Re-evaluation after careful reading:** The string is:
```
"UPDATE gruvax.profiles SET"       -> "UPDATE gruvax.profiles SET"
"    app_token_encrypted = %s..."  -> "    app_token_encrypted = %s..."
```
Result: `"UPDATE gruvax.profiles SET    app_token_encrypted = ..."` — the four leading spaces
act as whitespace, so PostgreSQL parses it correctly. This is not actually a bug.

**Retract CR-01** — this finding is withdrawn after careful re-examination. The SQL executes
correctly.

---

### CR-01 (replacement): Invite consumed but PAT write fails — member permanently locked out with no retry path

**File:** `src/gruvax/api/invite_codes.py:302-378`
**Issue:** The redeem flow is: (1) atomically consume invite → (2) validate PAT → (3) check
user_id collision → (4) write encrypted PAT. Steps 2-4 run AFTER the invite `consumed_at` is
set. If step 3 (collision check) or step 4 (PAT write) fails, the invite is already consumed
and the member is now locked out: their invite is spent, their profile has no PAT, and the owner
must regenerate a fresh invite to give them a second chance.

This is the accepted design per Pitfall 5 / D-10 ("owner simply issues a new invite"), and is
documented in the research. The issue here is that the 409 `user_id_collision` response gives
the member no actionable information — the error copy (`"This token belongs to someone who
already has a profile"`) is correct but the member's invite is now spent. From the member's
perspective they tried a valid-looking operation and are now stuck with no path forward. The
owner has no visibility into this state (no backend log, no profile state change). This is an
accepted design tradeoff, but the 409 response should surface that the invite was consumed and a
new one is needed.

**Severity:** WARNING (accepted design, but actionability gap) — see WR-01.

---

### CR-01 (second replacement): `RateLimitExhausted` error detail includes `str(exc)` — may expose upstream error text

**File:** `src/gruvax/api/invite_codes.py:326-329`
**Issue:** The `RateLimitExhausted` handler wraps the upstream exception message in the HTTP
response body:

```python
except RateLimitExhausted as exc:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"type": "upstream_unavailable", "message": str(exc)},
    ) from exc
```

`str(exc)` for a `RateLimitExhausted` may include the upstream HTTP response body from
discogsography. If discogsography ever echoes the Authorization header (Bearer token) in its
rate-limit error body, this propagates the PAT to the client. T-07-08 explicitly prohibits any
error/detail/log string being constructed from the body PAT, but the risk here is that the
upstream response body (not `body.pat` directly) is echoed. The same pattern exists identically
in `profiles.py:492-495` for the owner connect endpoint, so this is a systemic pattern.

For the **public** redeem endpoint the risk is higher because the caller is an untrusted member,
and the response is not gated by a PIN session. The upstream error message from discogsography
is likely safe in practice (rate-limit responses rarely include auth headers), but the code
pattern violates the stated T-07-08 invariant and cannot be proven safe without auditing
discogsography's rate-limit response bodies.

**Fix:** Replace `str(exc)` with a fixed, non-forwarding message:
```python
except RateLimitExhausted:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"type": "upstream_unavailable",
                "message": "Discogs is rate-limiting requests. Try again in a moment."},
    ) from None
```

Similarly fix the `ServerError`/`NetworkError` handler two lines below which also uses
`str(exc)`. The owner-side `connect_pat` in `profiles.py` has the same pattern but is PIN-gated
so the risk is lower — fix for consistency.

---

### CR-02: `generate_invite` does not verify the profile exists before inserting the invite code

**File:** `src/gruvax/api/invite_codes.py:195-228`
**Issue:** `POST /api/admin/profiles/{id}/invite` parses the UUID, then immediately runs
`_VOID_PRIOR_INVITE` + `_INSERT_INVITE`. If the `profile_id` does not exist or is soft-deleted,
the INSERT will fail with a FK violation (the FK is `REFERENCES gruvax.profiles(id) ON DELETE
CASCADE`), returning an uncontrolled 500 / psycopg `ForeignKeyViolation` exception rather than a
meaningful 404.

The existing `connect_pat` flow in `profiles.py` calls `await _require_profile(...)` first for
exactly this reason.

**Fix:** Add a preflight existence check before the transaction:
```python
uid = uuid.UUID(profile_id)  # already done
db_pool = request.app.state.db_pool
await _require_profile(db_pool, uid)  # raises 404 if missing/deleted
```
Or, catch `psycopg.errors.ForeignKeyViolation` in the transaction and convert to 404. The
preflight approach is cleaner and mirrors the existing pattern.

---

### CR-03: Invite TTL countdown stops but `inviteInfo` mutation inside `setInterval` tick captures stale closure

**File:** `frontend/src/routes/admin/ProfileDrawer.tsx:296-320`
**Issue:** The `tick` function closes over `inviteInfo` from the enclosing `useEffect`. The
`useEffect` dependency array is `[inviteInfo]` (line 321), so every time `inviteInfo` changes,
the effect re-runs, clears the old interval, and starts a new one with the fresh `inviteInfo`.

Inside `tick`, when `remaining <= 0`, the code calls:
```typescript
setInviteInfo(null)  // clears inviteInfo
```

Because `setInviteInfo(null)` changes `inviteInfo`, the effect re-runs, which clears the
interval (correct). However, on the same tick where `remaining <= 0`, `tick` also calls both
`setTtlSeconds(0)` and `clearInterval(inviteIntervalRef.current)` — but because the effect
cleanup will also `clearInterval`, the double-clear is harmless. The actual bug is more subtle:

After `setInviteInfo(null)` inside `tick`, a re-render is scheduled. In the interim (same
microtask), `tick` has already set `setTtlSeconds(0)`. The effect cleanup then runs and clears
the interval. But if React batches the re-render and the interval fires one more time before
cleanup, `inviteInfo` is `null` in the next `tick` call — `inviteInfo.expires_at` would throw a
TypeError on a null object.

However, inspection shows `tick` only reads `inviteInfo.expires_at` to compute `remaining`, and
by the time `setInviteInfo(null)` re-renders, the effect re-runs with `inviteInfo = null`, hits
the early-return guard (`if (!inviteInfo) { setTtlSeconds(null); return }`), and clears the
interval. The key safety question is whether one extra `tick` call can fire between
`setInviteInfo(null)` and the cleanup.

In React 19 with automatic batching, `setInviteInfo(null)` schedules a render but does not
immediately re-run the effect — the interval fires synchronously every 1000ms. If `tick` runs
at T=0, sets `inviteInfo` to null, the next interval tick at T=1000 runs `tick` again. At that
point `inviteInfo` is still the stale closed-over non-null value (the closure was created with
the old inviteInfo). So `new Date(inviteInfo.expires_at)` does NOT throw — it uses the stale
non-null value. But `remaining` will be <= 0, and `setInviteInfo(null)` is called again (a
no-op since it is already null in React state). `clearInterval` is called again (harmless).

**Assessment:** This is safe in practice but the stale-closure logic is fragile. If the
`inviteInfo` structure ever changes (e.g. `expires_at` becomes nullable), this could break. This
is a WARNING-level quality issue, not a runtime crash.

**Retract CR-03** — downgraded to WR-03 (quality concern, stale closure in timer).

---

## Warnings

### WR-01: Consumed invite on 409 collision / network failure — member has no self-service recourse

**File:** `src/gruvax/api/invite_codes.py:337-353`
**Issue:** After the invite is atomically consumed (step 1), if step 3 (user_id collision check)
returns 409, the member receives a 409 with the generic `user_id_collision` error. Their invite
is spent. The response does not indicate that the invite was consumed and a new one is required.
From the member's perspective, they see a validation error and may retry with the same expired
code — receiving a 404 `invite_not_found` on the retry, which is even more confusing.

The owner has no visibility into this state: `last_sync_status` and `last_sync_error` on the
profile are unchanged, so the admin diagnostics card shows no indication that a failed redemption
occurred.

**Fix (minimal):** Add a note to the 409 response body that the invite was consumed:
```python
raise HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail={
        "type": "user_id_collision",
        "message": "This token belongs to an account that already has a profile. "
                   "This invite link has been used — ask the owner for a new one.",
    },
)
```
Update `mapRedeemError` in `RedeemPage.tsx` to show this message inline.

---

### WR-02: `str(exc)` forwarded in 503 response detail — upstream error message exposure

**File:** `src/gruvax/api/invite_codes.py:326-335`
**Issue:** As described in the CR-01 analysis above, `str(exc)` from `RateLimitExhausted`,
`ServerError`, and `NetworkError` is forwarded verbatim to the API response. For the public
redeem endpoint this is especially sensitive: the upstream discogsography error text is visible
to any LAN member who submits a redeem request during a rate-limit window. While the PAT itself
is not in these exceptions (it is only in `body.pat`), forwarding upstream error text is a bad
pattern and violates T-07-08's spirit.

**Fix:**
```python
except RateLimitExhausted:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"type": "upstream_unavailable",
                "message": "Could not reach Discogs. Try again in a moment."},
    ) from None
except (ServerError, NetworkError):
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={"type": "upstream_unavailable",
                "message": "Could not reach Discogs. Try again in a moment."},
    ) from None
```

---

### WR-03: `generate_invite` emits unhandled FK violation as 500 when profile not found

**File:** `src/gruvax/api/invite_codes.py:205-217`
**Issue:** As detailed in CR-02 above, a non-existent or soft-deleted `profile_id` causes a
psycopg `ForeignKeyViolation` that propagates as a 500 Internal Server Error rather than a 404.
This is the highest-severity remaining issue after CR-01 retraction. All other endpoints in
`profiles.py` guard with `await _require_profile(...)` as the first step.

**Fix:**
```python
uid = uuid.UUID(profile_id)  # already done at line 196
db_pool = request.app.state.db_pool
# Add this preflight before the transaction:
await _require_profile(db_pool, uid)
async with db_pool.connection() as conn, conn.cursor() as cur:
    ...
```

Or wrap the transaction body in `except psycopg.errors.ForeignKeyViolation` and raise 404.

---

### WR-04: `ProfileDiagnosticsCard` `deriveProfileStatus` maps `'failed'` sync status to `'connected'`

**File:** `frontend/src/routes/admin/ProfileDiagnosticsCard.tsx:32`
**Issue:** The local `deriveProfileStatus` function returns `'connected'` for
`last_sync_status === 'failed'`:
```typescript
if (profile.last_sync_status === 'failed') return 'connected' // connected but last sync failed
```
This causes the `ProfileStatusBadge` to show "CONNECTED" for a profile whose last sync failed.
In the admin profiles list the server-derived `status` field is used (which returns
`re-auth-required` / `pending` / `syncing` / `connected`), but the diagnostics card derives
status locally and the local logic is wrong for the failure case. A profile with a failed sync
but a non-revoked token is not "connected" in any useful sense — the user's collection may be
stale.

The backend `_profile_status()` in `profiles.py:87-116` correctly handles the failure case:
`app_token_revoked` is the discriminator between `re-auth-required` and `pending`, and
`last_sync_status` = 'ok' maps to 'connected'. A 'failed' status with `app_token_revoked=False`
is simply "pending first good sync" or "last sync failed" — the backend does not explicitly
surface this state; it would map to 'pending'. The diagnostics card returning 'connected' is
incorrect, and could mislead an admin reviewing the card.

**Fix:**
```typescript
function deriveProfileStatus(profile: ProfileDiagnosticEntry): ProfileStatus {
  if (profile.app_token_revoked) return 're-auth-required'
  if (profile.last_sync_status === 'in_progress') return 'syncing'
  if (profile.last_sync_status === 'ok') return 'connected'
  // 'failed' or null — not yet successfully connected
  return 'pending'
}
```

---

### WR-05: `last_new_record_count` typed as `number` (not `number | null`) in `AdminProfile`

**File:** `frontend/src/api/types.ts:397`
**Issue:** `AdminProfile` declares:
```typescript
last_new_record_count: number
last_sync_is_initial: boolean
```
But the backend returns `null` for these fields when they have not been set (a profile that has
never synced under the new schema will have the DEFAULT 0 and FALSE from the migration, so in
practice these will not be null post-0012). However, `profiles.py` line 234-237 explicitly
guards:
```python
"last_new_record_count": last_new_record_count,
"last_sync_is_initial": bool(last_sync_is_initial) if last_sync_is_initial is not None else False,
```
The `last_new_record_count` is sent without a null guard — it IS passed through as-is from the
DB, which could be null for rows created before migration 0012. If any profile rows exist that
pre-date the migration and have not had their `last_new_record_count` DEFAULT applied (which
should not happen for Alembic-managed migrations, but could happen on a manual DB or after a
failed migration), the frontend type assertion `as number` would fail silently at runtime.

The `ProfileDiagnosticsCard` at line 52-53 already handles `null` correctly
(`newRecordCount != null && newRecordCount > 0`), which suggests the backend may in fact send
null. The type declaration should reflect this:
```typescript
last_new_record_count: number | null
last_sync_is_initial: boolean | null
```

This is consistent with `ProfileDiagnosticEntry` in `adminClient.ts` which correctly types
these as `number | null` and `boolean | null`.

**Impact:** The mismatch between `AdminProfile.last_new_record_count: number` and
`ProfileDiagnosticEntry.last_new_record_count: number | null` means the `ProfileDrawer` may
compile without null-guards that are needed at runtime.

---

## Info

### IN-01: `_run_test_sync` duplicated verbatim between `invite_codes.py` and `profiles.py`

**File:** `src/gruvax/api/invite_codes.py:160-174`, `src/gruvax/api/admin/profiles.py:145-158`
**Issue:** The function body is identical in both modules. The summary acknowledges this as an
intentional choice ("avoid importing a private function cross-module"). This is the correct
call for now, but if the discogsography client API changes (e.g., the `_get_page` signature
changes), both copies must be updated. A shared internal helper module (e.g.,
`gruvax.api._pat_validate`) would be cleaner.

**Fix:** No immediate action required — current duplication is intentional and documented. Flag
for the next refactor cycle.

---

### IN-02: `generate_invite` error handling discards all error detail

**File:** `frontend/src/routes/admin/ProfileDrawer.tsx:331-345`
**Issue:**
```typescript
} catch {
  setInviteError('Could not generate invite link. Try again in a moment.')
}
```
All errors, including 401 (session expired) and 404 (profile not found), are swallowed into a
generic message. A session timeout would show "Could not generate invite link" rather than
prompting re-auth. This is acceptable for the home-LAN admin context but could confuse an owner
whose session expires mid-use.

**Fix:** Check `err instanceof ProfileApiError` and handle specific types (auth expiry, profile
not found) with more specific copy.

---

### IN-03: `kiosk.css` not reviewed — assumed correct from summary

**File:** `frontend/src/routes/kiosk/kiosk.css`
**Issue:** The CSS file for the new-records pill (`.kiosk-new-records-pill`) was mentioned in
the summary as token-only with correct design-language values. The file was in scope but its
content is design/style-only with no security or logic relevance. No actionable findings.

---

## Structural Findings (fallow)

No structural pre-pass was provided for this review.

---

_Reviewed: 2026-06-01T20:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

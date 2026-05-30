---
phase: 03-devices-pairing
reviewed: 2026-05-29T00:00:00Z
depth: standard
files_reviewed: 22
files_reviewed_list:
  - src/gruvax/api/devices.py
  - src/gruvax/api/admin/devices.py
  - src/gruvax/api/admin/limiter.py
  - src/gruvax/api/admin/router.py
  - src/gruvax/api/admin/profiles.py
  - src/gruvax/api/deps.py
  - src/gruvax/api/session.py
  - src/gruvax/api/events.py
  - src/gruvax/app.py
  - src/gruvax/auth/sessions.py
  - migrations/versions/0011_devices_and_pairing_codes.py
  - frontend/src/routes/kiosk/PairView.tsx
  - frontend/src/routes/admin/DevicesManager.tsx
  - frontend/src/routes/admin/DeviceCard.tsx
  - frontend/src/routes/admin/DeviceDrawer.tsx
  - frontend/src/App.tsx
  - frontend/src/api/devices.ts
  - frontend/src/api/session.ts
  - deploy/kiosk/start-kiosk.sh
  - deploy/kiosk/gruvax-kiosk.service
  - tests/integration/test_devices.py
  - tests/unit/test_fingerprint_cookie.py
findings:
  critical: 2
  warning: 6
  info: 4
  total: 12
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-29
**Depth:** standard
**Files Reviewed:** 22
**Status:** issues_found

## Summary

Phase 3 implements the device pairing / binding subsystem: a kiosk fingerprint
cookie, a 4-digit pairing-code table, an atomic admin bind, a per-request revoke
guard, and the supporting React admin UI + Pi provisioning artifacts.

The security-sensitive backend primitives are mostly solid: the fingerprint
cookie is `HttpOnly + SameSite=Strict + max_age` (DEV-01), pairing codes use a
CSPRNG (`secrets.randbelow`) with a 5-min TTL + `consumed_at` one-shot guard, all
SQL is parameterized, device IDs are UUID-validated before DB use, and the revoke
guard in `deps.py` denies revoked/unknown fingerprints on every per-profile
request. The fingerprint value is never logged or returned in any response.

However two BLOCKERS will break the feature in production:

1. **The React admin device client (`frontend/src/api/devices.ts`) sends every
   mutating request with raw `fetch()` and no `X-CSRF-Token` header.** The backend
   `require_admin` dependency rejects mutating requests without a matching CSRF
   header with 403. Every admin device action (bind, rename, revoke, reinstate,
   delete, change-profile) will fail in the browser. The integration tests pass
   because they inject the CSRF token manually, so they do not catch this.

2. **The bind endpoint consumes the pairing code and creates the device row in
   two separate transactions.** If the device upsert fails after the code is
   consumed, the code is permanently burned and the kiosk can never re-bind it,
   while the API returns 500 — a data-flow / availability defect in the core
   pairing path.

The remaining findings are quality and robustness issues.

## Critical Issues

### CR-01: Admin device mutations omit the CSRF token — every admin action 403s

**File:** `frontend/src/api/devices.ts:80-153` (also `:60-66`, `:89-100`)
**Issue:**
All admin device mutations call raw `fetch()` directly instead of the shared
`adminFetch` wrapper in `frontend/src/api/adminClient.ts`. `adminFetch` is the
only place that (a) reads the `gruvax_csrf` token from the Zustand admin store and
attaches it as `X-CSRF-Token`, and (b) sets `credentials: 'same-origin'`. The
backend `require_admin` dependency (`src/gruvax/api/deps.py:436-443`) rejects every
`POST/PUT/PATCH/DELETE` whose `X-CSRF-Token` header does not match the
`gruvax_csrf` cookie with HTTP 403 "CSRF check failed". Therefore `bindDevice`,
`renameDevice`, `changeDeviceProfile`, `unbindDevice`, `revokeDevice`,
`reinstateDevice`, and `deleteDevice` will all 403 in the real SPA. The entire
admin Devices UI (DeviceDrawer bind/rename/revoke/reinstate/delete) is
non-functional.

This is invisible to the test suite: `tests/integration/test_devices.py` injects
`headers={"X-CSRF-Token": admin["csrf_token"]}` on every admin call manually, so
the missing-header path is never exercised.

**Fix:** Route all admin device calls through `adminFetch` (same module the rest of
the admin client uses), e.g.:
```ts
import { adminFetch } from './adminClient'  // export it if not already

export async function bindDevice(body: BindDeviceRequest): Promise<DeviceRow> {
  const res = await adminFetch('/api/admin/devices/bind', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({})) as BindDeviceError
    throw Object.assign(new Error('Bind failed'), { status: res.status, detail: err.detail })
  }
  return res.json() as Promise<DeviceRow>
}
```
Apply the same change to `getAdminDevices`, `renameDevice`, `changeDeviceProfile`,
`revokeDevice`, `reinstateDevice`, and `deleteDevice`. (GET calls also benefit from
`credentials: 'same-origin'` so the session cookie is reliably attached.) Add a
frontend test that asserts `bindDevice` issues a request carrying `X-CSRF-Token`.

### CR-02: Bind is non-atomic across code-consumption and device-upsert — burns the code on failure

**File:** `src/gruvax/api/admin/devices.py:286-347`
**Issue:**
`bind_device` consumes the pairing code in one connection/transaction
(`_BIND_CODE` … `await conn.commit()` at lines 286-289) and then creates/updates
the device row in a *second, separate* connection/transaction (lines 324-340).
The code's `consumed_at` is already committed before the device upsert runs. If the
device upsert raises — for example a `psycopg.errors.UniqueViolation` on
`idx_devices_profile_active` (the partial-unique "one active device per profile"
index) when Priority 2's `_UPDATE_DEVICE_BY_PROFILE` does not match but Priority 3's
plain `_INSERT_DEVICE` collides with an existing active device for the same
profile, or any transient DB error — the endpoint returns 500, the kiosk's code is
permanently consumed, and the kiosk can never bind with that code again. The
operator must regenerate a code on the kiosk and retry. This is a data-flow defect
in the primary DEV-03 path and undermines the "first wins" guarantee (the code is
spent even though no device was bound).

Additionally, `_INSERT_DEVICE` (line 117-121) has no `ON CONFLICT` clause, so any
collision on the partial-unique fingerprint or profile index surfaces as an
unhandled exception → 500 rather than a clean error.

**Fix:** Perform the code consumption and the device upsert in a *single*
transaction so a device-upsert failure rolls back the `consumed_at` write, leaving
the code reusable:
```python
async with pool.connection() as conn, conn.cursor() as cur:
    await cur.execute(_BIND_CODE, (body.code,))
    row = await cur.fetchone()
    if row is None:
        await conn.rollback()
        raise HTTPException(status_code=404, detail={"type": "code_not_found"})
    fingerprint = row[0]
    # ... resolve profile_id_str / display_name ...
    await cur.execute(_UPDATE_DEVICE_BY_FINGERPRINT, (profile_id_str, display_name, fingerprint))
    device_row = await cur.fetchone()
    if device_row is None:
        await cur.execute(_UPDATE_DEVICE_BY_PROFILE, (fingerprint, display_name, profile_id_str))
        device_row = await cur.fetchone()
    if device_row is None:
        await cur.execute(_INSERT_DEVICE, (fingerprint, profile_id_str, display_name))
        device_row = await cur.fetchone()
    await conn.commit()
```
Also wrap the upsert in a `try/except psycopg.errors.UniqueViolation` that
`rollback()`s and returns a clean 409 (e.g. `{"type": "profile_already_bound"}`)
instead of a 500, so a profile-already-has-an-active-device case is reported
meaningfully and the code is not burned.

## Warnings

### WR-01: `GET /api/devices/me` is not covered by the per-request revoke guard

**File:** `src/gruvax/api/devices.py:118-155`
**Issue:**
`get_device_me` reads the device row directly and returns `{"state": "revoked"}`
for a revoked fingerprint with HTTP 200 — it does **not** use
`resolve_profile_from_request` (the D3-07 guard). This is acceptable for the *poll*
endpoint by design (the kiosk needs to learn it was revoked), but note the guard's
authoritative-denial contract (D3-07: "revoked/unknown fingerprint → 401/403")
only holds for the per-profile endpoints wired through `deps.py`
(search/locate/illuminate/events). Any future kiosk-facing endpoint added to
`devices.py` must explicitly opt into the guard or it will silently serve revoked
devices. The current set is fine, but the asymmetry is a latent footgun and should
be documented at the router level. Confirm that no profile-scoped data is reachable
via `/api/devices/*` without the guard.

**Fix:** Add a module-level comment in `devices.py` stating that endpoints here are
intentionally guard-exempt and MUST NOT expose per-profile collection data; route
any such data through the `deps.py` per-profile dependencies instead.

### WR-02: DeviceDrawer maps `code_expired`, but the backend never returns it

**File:** `frontend/src/routes/admin/DeviceDrawer.tsx:58-69` and `frontend/src/api/devices.ts:54`
**Issue:**
`mapBindError` handles a `'code_expired'` error type and the `BindDeviceError`
type union includes it, but the bind endpoint's atomic UPDATE
(`src/gruvax/api/admin/devices.py:79-86`) folds expiry into the not-found path and
always returns `{"type": "code_not_found"}` (lines 291-295). An expired code
therefore shows the generic "wasn't found" copy, never the more accurate
"that code has expired" message. `tests/integration/test_devices.py::test_expired_code`
(lines 867-910) explicitly accepts either type, masking the gap. This is a UX
mismatch, not a security issue, but the dead `code_expired` branch is misleading.

**Fix:** Either (a) have the bind endpoint distinguish expiry from not-found (a
follow-up `SELECT` on the code to check `expires_at <= NOW()` after a 0-row UPDATE,
returning `{"type": "code_expired"}`), or (b) remove the `code_expired` branch from
the frontend and the type union to reflect actual backend behavior. Pick one so the
contract is honest.

### WR-03: `_UPDATE_DEVICE_BY_PROFILE` rebinds a kiosk silently and can mismatch the consuming fingerprint

**File:** `src/gruvax/api/admin/devices.py:131-137, 329-333`
**Issue:**
Priority 2 of the bind upsert updates the existing active device row for a profile
to the *new* fingerprint when no row matches the new fingerprint. If an admin binds
a freshly-generated code (fingerprint B) to a profile that already has a different
active kiosk (fingerprint A), the existing kiosk A is silently rebound to
fingerprint B — kiosk A keeps cookie A, which now has no device row, so kiosk A
falls through to "device_unknown"/picker on its next request with no signal to the
operator. This may be intended ("re-pair this kiosk") but it is indistinguishable
from an accidental hijack of another screen's binding, and there is no LIMIT on the
UPDATE.

**Fix:** Make the rebind explicit. Either require the admin to pick "rebind existing
kiosk" vs "add new kiosk", or detect the profile-already-bound case and return a
409 that the UI surfaces ("This profile is already paired to another screen — unbind
it first"). At minimum, log a structured `device_rebound` event (device_id only,
never the fingerprint) so the silent takeover is auditable.

### WR-04: `last_seen_at` update opens a second connection per guarded request

**File:** `src/gruvax/api/deps.py:204-223`
**Issue:**
`resolve_profile_from_request` acquires one pool connection for the device SELECT
(lines 204-205), releases it, then acquires a *second* connection for the throttled
`_UPDATE_LAST_SEEN` (lines 220-222). On every guarded per-profile request (search,
locate, illuminate) this doubles the pool checkouts even though the WHERE clause
makes the UPDATE a no-op most of the time. With `max_size=10`
(`src/gruvax/app.py:128`) and SSE connections also touching the pool through this
dep, two checkouts per request narrows the headroom. The two operations could share
a single connection.

**Fix:** Issue the `_UPDATE_LAST_SEEN` on the same connection used for the SELECT
(open one `async with pool.connection()` block, run both statements, commit once),
or move the throttled touch into the same cursor block. This halves pool pressure on
the hot path without changing semantics.

### WR-05: PairView countdown reroll fires before the device-poll can observe `paired`

**File:** `frontend/src/routes/kiosk/PairView.tsx:157-166, 179-186`
**Issue:**
The 1s countdown interval and the 3s `/api/devices/me` poll are independent. When a
code reaches 0:00, `fetchNewCode()` fires immediately (line 165) and the displayed
code changes to "Generating new code…". If the admin bound the *old* code within
its last ~3 seconds, the bind succeeds server-side, but the kiosk has already
rerolled and the user sees a confusing flash of a new code before the next 3s poll
flips to `paired`. Not a correctness bug (the poll still converges to `paired`), but
the UX races. Also, `pairStatus` is intentionally excluded from the countdown
effect deps (line 174) while being read inside the interval at line 157 — the
closure captures the `pairStatus` value from the render that created the interval,
so the `pairStatus !== 'expired' && pairStatus !== 'paired'` guard reads a stale
value. The `pairedHandledRef`/`rerollTriggeredRef` guards mostly paper over this,
but the stale-closure read is fragile.

**Fix:** Gate the reroll on the latest device state (read a ref updated by the poll)
so a code is not rerolled while a `paired` transition is in flight, and read
`pairStatus` from a ref inside the interval to avoid the stale closure. Lower risk:
on `state === 'paired'`, clear the countdown interval before scheduling the navigate
(already done in `handlePaired`) and also suppress the pending reroll.

### WR-06: Migration 0011 down-revision chain and FK soft-delete assumption

**File:** `migrations/versions/0011_devices_and_pairing_codes.py:70`, `src/gruvax/api/admin/profiles.py:617-633`
**Issue:**
The migration declares `profile_id ... ON DELETE SET NULL` and the docstring claims
this "handles soft-delete detach". It does not — `ON DELETE SET NULL` only fires on
physical row deletion, and gruvax uses logical soft-delete (`deleted_at = NOW()`).
The actual detach is correctly done by an explicit `UPDATE gruvax.devices SET
profile_id = NULL` in `soft_delete_profile` (profiles.py:628-632), which is good —
but the migration comment (and the table comment at lines 12-14) is misleading and
could lead a future maintainer to assume the FK handles it and remove the explicit
UPDATE. Also note `soft_delete_profile` nulls `profile_id` for *all* matching
devices including already-revoked ones; that is harmless but worth a comment.

**Fix:** Correct the migration docstring/comment to state that soft-delete detach is
enforced by the application (`soft_delete_profile`), and that `ON DELETE SET NULL`
is only a safety net for hard deletes. Keep the explicit UPDATE.

## Info

### IN-01: Dead/unused SQL constants in admin/devices.py

**File:** `src/gruvax/api/admin/devices.py:92-114`
**Issue:**
`_UPSERT_DEVICE` and `_UPSERT_DEVICE_SAFE` are defined but never used — the bind
path uses the three-step `_UPDATE_DEVICE_BY_FINGERPRINT` / `_UPDATE_DEVICE_BY_PROFILE`
/ `_INSERT_DEVICE` sequence instead. Dead constants add confusion (a reader must
work out which upsert strategy is live). `_UPSERT_DEVICE_SAFE` also contains an
invalid clause (`ON CONFLICT (fingerprint) WHERE revoked_at IS NULL DO UPDATE` is
not valid Postgres syntax for an arbiter without an existing matching index name),
so leaving it as a "fallback" is a trap.
**Fix:** Delete `_UPSERT_DEVICE` and `_UPSERT_DEVICE_SAFE`.

### IN-02: `profile_name` is expected by the UI but never returned by the API

**File:** `frontend/src/api/devices.ts:36`, `frontend/src/routes/admin/DeviceCard.tsx:62-67`, `src/gruvax/api/admin/devices.py:225-236`
**Issue:**
`DeviceRow.profile_name` is part of the frontend type and `DeviceCard` renders it
in the metadata line, but `_row_to_device` (the only producer of device payloads)
never includes `profile_name` — it returns `profile_id` only. The card's profile
segment is therefore always omitted (the `&& device.profile_name` guard is always
falsy). Paired devices show no human-readable profile, only the raw `profile_id`
is available client-side (and it is not displayed). Functional but a silent feature
gap.
**Fix:** Either JOIN `gruvax.profiles.display_name` into the device list query and
include `profile_name` in `_row_to_device`, or drop the unused `profile_name` field
and the DeviceCard segment.

### IN-03: `DeviceMeResponse` omits revoked-state guidance for the kiosk

**File:** `frontend/src/api/devices.ts:26-29`, `src/gruvax/api/devices.py:147-148`
**Issue:**
`get_device_me` returns `{"state": "revoked"}` but `DeviceMeResponse` and PairView
only branch on `paired`. The PairView poll
(`frontend/src/routes/kiosk/PairView.tsx:179-208`) does nothing on `state ===
'revoked'` — a revoked kiosk keeps showing the pairing code as if pending. Per D3-07
the SPA should route a revoked device to a "this screen was revoked" / re-pair
state. Minor for v1 (the device cannot reach profile data anyway), but the kiosk
gives no user feedback.
**Fix:** Handle `state === 'revoked'` in PairView (show a revoked notice / restart
pairing) and document the expected behavior.

### IN-04: start-kiosk.sh crash-flag sed is brittle across Chromium Preferences formats

**File:** `deploy/kiosk/start-kiosk.sh:28-31`
**Issue:**
The `sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/'` assumes Chromium writes
the Preferences JSON with no spaces around the colon and the exact key adjacency.
Chromium sometimes writes `"exit_type": "Crashed"` (with a space) or reorders keys;
the substitution then silently no-ops (the `|| true` hides any failure), and the
"Restore tabs?" dialog can reappear on the kiosk. This is best-effort and guarded,
so low impact, but the brittleness is worth a note in the README.
**Fix:** Use a regex tolerant of optional whitespace
(`sed -E 's/("exit_type"[[:space:]]*:[[:space:]]*)"Crashed"/\1"Normal"/'`) or set
`"exited_cleanly": true` as well; document that this is a heuristic.

---

_Reviewed: 2026-05-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

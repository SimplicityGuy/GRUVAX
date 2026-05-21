---
phase: 03-admin-loop-pin-manual-entry-undo
reviewed: 2026-05-20T00:00:00Z
depth: standard
files_reviewed: 38
files_reviewed_list:
  - src/gruvax/auth/pin.py
  - src/gruvax/auth/sessions.py
  - src/gruvax/api/deps.py
  - src/gruvax/api/admin/login.py
  - src/gruvax/api/admin/cubes.py
  - src/gruvax/api/admin/history.py
  - src/gruvax/api/admin/validation.py
  - src/gruvax/api/admin/limiter.py
  - src/gruvax/api/admin/settings.py
  - src/gruvax/api/admin/router.py
  - src/gruvax/api/admin/__init__.py
  - src/gruvax/auth/__init__.py
  - src/gruvax/api/units.py
  - src/gruvax/app.py
  - src/gruvax/settings.py
  - src/gruvax/db/queries.py
  - src/gruvax/estimator/boundary_math.py
  - migrations/versions/0004_admin_tables.py
  - scripts/set_pin.py
  - frontend/src/api/adminClient.ts
  - frontend/src/api/client.ts
  - frontend/src/api/types.ts
  - frontend/src/api/cubeTypes.ts
  - frontend/src/state/adminStore.ts
  - frontend/src/App.tsx
  - frontend/src/routes/admin/AdminShell.tsx
  - frontend/src/routes/admin/PinOverlay.tsx
  - frontend/src/routes/admin/NumericKeypad.tsx
  - frontend/src/routes/admin/Settings.tsx
  - frontend/src/routes/admin/CubesGrid.tsx
  - frontend/src/routes/admin/CubeEditor.tsx
  - frontend/src/routes/admin/AlphaRail.tsx
  - frontend/src/routes/admin/FillBar.tsx
  - frontend/src/routes/admin/DiffPreviewSheet.tsx
  - frontend/src/routes/admin/HistoryView.tsx
  - frontend/src/routes/admin/admin.css
  - frontend/src/routes/kiosk/Cube.tsx
  - frontend/src/routes/kiosk/CubeContentsPanel.tsx
  - frontend/src/routes/kiosk/FillBar.tsx
  - frontend/src/routes/kiosk/KioskView.tsx
  - frontend/src/routes/kiosk/ShelfGrid.tsx
  - frontend/src/routes/kiosk/kiosk.css
findings:
  critical: 4
  warning: 11
  info: 7
  total: 22
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-05-20
**Depth:** standard
**Files Reviewed:** 38 (the two glob entries `frontend/src/routes/admin` and `frontend/src/routes/kiosk` expanded to the individual files listed above)
**Status:** issues_found

## Summary

Phase 3 introduces PIN auth, server-side sessions, CSRF double-submit, login rate-limiting, and privileged DB mutations (boundary edits, atomic bulk commit, conflict-aware undo). The backend security primitives are mostly well-built: Argon2id via passlib, signed session cookies via itsdangerous, server-side session rows with sliding TTL + hard cap + revocation, every admin/mutation route gated by `require_admin`, public reveal endpoints correctly NOT gated, and 100% `%s`-placeholder SQL with zero f-string interpolation. The migration, boundary math, and atomic transaction ordering (cache invalidate strictly AFTER commit — Pitfall A) are solid.

However, the **frontend↔backend API contract is broken in several places** that make the core admin loop non-functional: field-name mismatches (`label_first` vs `first_label`), wrong request envelope keys (`{edits}` vs `{updates}`), and a `movement_counts` type that is an array on the wire but read as an object in the UI. These are BLOCKERs because the admin editor, validate dry-run, and diff preview cannot work as written. There is also a real cookie-attribute defect that prevents logout from clearing cookies in production (Secure mismatch), a stale in-process settings cache after PUT /settings, and several robustness gaps around input validation and the slowapi private-attribute coupling.

The CLAUDE.md "no hardcoded hex in frontend" constraint is honored (all colors are `var(--gruvax-*)` tokens), psycopg3 is used throughout, and React 19 patterns are generally followed.

## Critical Issues

### CR-01: Admin cube payloads use mismatched field names — entire editor/validate/bulk flow breaks

**File:** `frontend/src/api/types.ts:121-129` (and `194-220`); `src/gruvax/api/admin/cubes.py:54-66`
**Issue:** The frontend `CubeBoundaryEdit`, `AdminCube`, and `AdminCubeBoundary` types use `label_first / catalog_first / label_last / catalog_last`. The backend Pydantic models (`BoundaryEdit`, `PerCubeBoundaryEdit`) and all response builders use `first_label / first_catalog / last_label / last_catalog`.

Consequences:
- `validateBoundary` / `adminBulkSave` send `label_first`; Pydantic ignores the unknown key and defaults `first_label=None`, so the comparator/phantom logic runs on empty strings. A bulk commit would write all-NULL non-empty boundaries → either wrong data or a `empty_or_complete` CHECK violation (`0001_create_schema.py:63`).
- `adminGetCubes` / `adminGetCubeBoundary` responses contain `first_label`, but `CubesGrid` (`CubeEditor.tsx:193`) reads `boundary.label_first` → `undefined` → the editor renders blank fields and the grid shows empty labels.

**Fix:** Pick one canonical naming and align both sides. Recommended: keep the DB/backend `first_label` form and change the TS interfaces + all `.tsx` reads to match:
```ts
export interface CubeBoundaryEdit {
  unit_id: number; row: number; col: number;
  first_label: string; first_catalog: string;
  last_label: string; last_catalog: string;
}
// AdminCube / AdminCubeBoundary: same rename.
// CubeEditor.tsx, CubesGrid.tsx, DiffPreviewSheet.tsx: read first_label/first_catalog/...
```

### CR-02: `validateBoundary` sends `{ edits }` but the endpoint expects `{ updates }` — every validate request 422s

**File:** `frontend/src/api/adminClient.ts:188-199`; `src/gruvax/api/admin/cubes.py:79-83,330-333`
**Issue:** `ValidateRequest` declares `updates: list[BoundaryEdit]`. The client posts `body: JSON.stringify({ edits })`. FastAPI returns 422 (missing required field `updates`). The dry-run validation in `CubeEditor` and the movement-count fetch in `DiffPreviewSheet` therefore always fail (their `.catch` swallows the error, so phantom warnings and movement counts silently never appear).

**Fix:**
```ts
body: JSON.stringify({ updates: edits }),
```
(`adminBulkSave` already correctly sends `{ updates }`.)

### CR-03: `movement_counts` is an array on the wire but read as an object in the UI → runtime NaN / broken overstuffed warning

**File:** `src/gruvax/api/admin/cubes.py:444-490` (returns a list); `frontend/src/api/types.ts:152-173`; `frontend/src/routes/admin/DiffPreviewSheet.tsx:164-170,207-216`
**Issue:** Backend `_compute_movement_counts` returns a **list** with one dict (`return [ {...} ]`), and each validate result sets `"movement_counts": movement_counts` (a list). The frontend type declares `movement_counts?: MovementCount` (a single object), and `DiffPreviewSheet` reads `validateResult.movement_counts.records_after` (`:168`) and renders `mc.records_before` after `const moveCounts = hasMoves ? [hasMoves] : []` (`:165`, wrapping the already-array in another array). `records_after` on an array is `undefined`, so the overstuffed comparison is `undefined > number` → always false, and the movement line renders `undefined → undefined`.

Additionally the backend `MovementCount` payload includes `delta`, `fill_level_before`, `fill_level_after` not present in the TS type, and omits nothing the UI needs — but the array/object shape is the breaking part.

**Fix:** Make the contract consistent. Simplest: have the endpoint return a single object per item:
```python
# in validate_boundary, store the dict not the list:
"movement_counts": _compute_movement_counts(...)[0],
```
and in `_compute_movement_counts` return the dict (or index `[0]`). Then update `DiffPreviewSheet` to use `validateResult.movement_counts` directly without re-wrapping.

### CR-04: Logout cannot clear cookies in production — `delete_cookie` attributes do not match `set_cookie`

**File:** `src/gruvax/auth/sessions.py:113-127` (set) vs `195-204` (clear)
**Issue:** Cookies are set with `samesite="strict"`, `httponly=True/False`, `secure=False` and the default path `/`. `clear_session_cookies` calls `response.delete_cookie(SESSION_COOKIE, samesite="strict")` without `secure` / `httponly` / `path`. Browsers only delete a cookie when the clearing `Set-Cookie` matches the original's `Path`, `Secure`, and `SameSite` attributes. The comment at `:112` explicitly says `secure` will be flipped to `True` in production HTTPS — at that point the delete (with `secure` defaulting to False) will **not** match and the session cookie will persist client-side after logout. Combined with the fact that logout DOES revoke the server row, the practical risk today is low, but the moment `secure=True` ships, logout silently leaves a (revoked but present) cookie, and any change to path would break clearing entirely.

**Fix:** Mirror every attribute when deleting, and centralize the cookie flags so set/clear cannot drift:
```python
def clear_session_cookies(response: Response, secure: bool = False) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", samesite="strict",
                           httponly=True, secure=secure)
    response.delete_cookie(CSRF_COOKIE, path="/", samesite="strict",
                           httponly=False, secure=secure)
```
Drive `secure` (and the set-cookie `secure`) from settings so dev HTTP and prod HTTPS are both correct.

## Warnings

### WR-01: GET /api/admin/settings response keys do not match the frontend `AdminSettings` type

**File:** `src/gruvax/api/admin/settings.py:48-52`; `frontend/src/api/types.ts:98-108`; `frontend/src/routes/admin/Settings.tsx:32-34`
**Issue:** The endpoint returns `{cube_nominal_capacity, session_idle_ttl_seconds}`. The TS `AdminSettings` type is `{nominal_capacity, idle_ttl_seconds}`, and `Settings.tsx:33-34` reads `s.nominal_capacity` / `s.idle_ttl_seconds` → both `undefined` → `setCapacity(undefined)` and `Math.round(undefined/60)` → `NaN` in the inputs on first load. The PUT path also mismatches: client sends `{nominal_capacity, idle_ttl_seconds}` (per `AdminSettingsPut`) but `update_settings` (`:71-74`) only recognizes `cube_nominal_capacity` / `session_idle_ttl_seconds`, so saves silently update nothing (`updated: []`).

**Fix:** Align the keys on both sides (GET, PUT, and the TS types). E.g. standardize on `nominal_capacity` / `idle_ttl_seconds` end to end, or rename the TS type fields to the `cube_*` / `session_*` forms.

### WR-02: PUT /api/admin/settings does not refresh `app.state.settings_cache` — capacity/TTL changes ignored until restart

**File:** `src/gruvax/api/admin/settings.py:55-91`; `src/gruvax/app.py:105-117`; `src/gruvax/api/units.py:96-98,193-195`; `src/gruvax/api/admin/cubes.py:107-114`
**Issue:** `nominal_capacity` is read everywhere from `request.app.state.settings_cache` (loaded once at lifespan startup). `update_settings` writes the DB but never updates `settings_cache`, so fill-level computations on both the public kiosk and admin grid keep using the old capacity until the process restarts. Same for `session.idle_ttl_seconds` — `require_admin` reads `settings.SESSION_TTL_SECONDS` (env, `deps.py:163`), so the admin-configurable idle timeout in the Settings UI has **no effect at all** on actual session expiry.

**Fix:** After committing in `update_settings`, reload the cache (`app.state.settings_cache = await load_settings_cache(pool)`), and have `require_admin` source the idle TTL from the settings cache rather than the env-only `settings.SESSION_TTL_SECONDS` (or document that the UI control is cosmetic).

### WR-03: PinOverlay fabricates session expiry instead of reading server values — countdown is wrong after a custom idle-TTL

**File:** `frontend/src/routes/admin/PinOverlay.tsx:78-85`
**Issue:** On successful login the component hardcodes `expires = now + 10min`, `hardCap = now + 30min` with a comment "for simplicity." If an admin set idle timeout to 5 or 30 minutes, the countdown is wrong until the first `/session` poll (up to 30 s later) corrects it, and the local "idle expiry check" in AdminShell (`AdminShell.tsx:76-82`) can log the user out early or late based on the fabricated value.

**Fix:** Have `POST /login` return `expires_at` and `hard_cap_at` (the create_session helper already computes them), or call `adminGetSession()` immediately after login and seed the store from the real values.

### WR-04: Login does not validate PIN shape before hashing/verifying — empty/oversized input reaches the hasher

**File:** `src/gruvax/api/admin/login.py:119-149`
**Issue:** `pin = str(body.get("pin", ""))` is passed straight to `verify_pin` with no length/charset bound. `change_pin` validates `new_pin` is 4 digits but NOT `current_pin`, and `login` validates neither. An attacker can submit an arbitrarily large `pin` body to force Argon2id work (a cheap DoS amplifier), and malformed JSON bodies raise an unhandled `json.JSONDecodeError` → 500 instead of 400/422. The rate limit (5/5min) bounds this, but per-request input bounds are still warranted.

**Fix:** Reject non-4-digit PINs before the DB/hash call (return 401/422 uniformly to avoid an oracle), and wrap `await request.json()` to return 400 on decode failure. Prefer a Pydantic body model (`class LoginBody(BaseModel): pin: constr(pattern=r"^\d{4}$")`) for login and change-pin so FastAPI returns 422 automatically.

### WR-05: Rate-limit key trusts `request.client` (REMOTE_ADDR) with no proxy awareness

**File:** `src/gruvax/api/admin/login.py:72`; `src/gruvax/api/admin/limiter.py:19`
**Issue:** `get_remote_address` returns the socket peer. Behind the documented kiosk/reverse-proxy or Docker setup, that is the proxy/gateway IP, so all clients share one bucket — either trivially exhausting the 5/5min limit for everyone, or (if every request looks like one IP) making the per-IP brute-force protection meaningless. There is no `ProxyHeadersMiddleware` / trusted-proxy config.

**Fix:** For a single-host LAN deployment this may be acceptable, but document it explicitly. If a proxy sits in front, configure Uvicorn `--proxy-headers` + trusted hosts (or a key_func that reads a validated `X-Forwarded-For`), never an unvalidated forwarded header.

### WR-06: Inline rate-limiter depends on slowapi private internals (`_limiter`, `_storage`, `_key_prefix`)

**File:** `src/gruvax/api/admin/login.py:75-94`
**Issue:** `_check_login_rate_limit` reaches into `limiter._key_prefix`, `limiter._limiter.hit(...)`, and constructs a private `slowapi.wrappers.Limit(...)` with a positional/keyword signature that is not part of slowapi's public API. A minor slowapi/limits upgrade can rename or reorder these and break login entirely (or worse, silently disable the limit). Given the MEMORY.md "always latest versions" directive, this is fragile.

**Fix:** Use the public `limits` API directly: own a `limits.strategies.FixedWindowRateLimiter(storage)` and a parsed `RateLimitItem`, call `.hit(item, *identifiers)`, and raise your own `HTTPException(429, ...)` with a `Retry-After` header rather than reconstructing slowapi's internal `Limit`. This removes the slowapi-internals coupling and the unused `app.state.limiter`/exception-handler indirection.

### WR-07: Revert restores `is_empty=False` with NULL boundaries → `empty_or_complete` CHECK violation aborts the whole revert

**File:** `src/gruvax/api/admin/history.py:132-145`; `src/gruvax/db/queries.py:562-599`
**Issue:** `prev_is_empty = bool(hist.get("prev_is_empty", True))` is restored together with `prev_first_label`…`prev_last_catalog`. If any historical row has `prev_is_empty=False` but one of the prev_* columns is NULL (possible if an earlier write or external edit left inconsistent prev data, or a future code path writes partial prevs), `write_boundary` sets `is_empty=False` with a NULL column → the `empty_or_complete` CHECK fails, the `conn.transaction()` rolls back, and the whole revert 500s with no cubes restored. The revert path has no guard re-deriving `is_empty` from completeness.

**Fix:** Before writing, coerce: `prev_is_empty = prev_is_empty or any(prev_* is None)` — i.e. if any boundary column is NULL, force `is_empty=True`. Or add a defensive completeness check and surface the offending cube in `skipped[]` instead of aborting.

### WR-08: Stale CSRF cookie after Change-PIN session revocation can wedge the keeping session

**File:** `src/gruvax/api/admin/settings.py:160-166`; `src/gruvax/auth/sessions.py:172-192`
**Issue:** `change_pin` revokes all *other* sessions but does not rotate the surviving session's CSRF token or session id. That is acceptable, but note the surviving client keeps the same CSRF cookie/store value — fine. The real gap: revoked clients still hold a valid-looking CSRF cookie and a (now-revoked) session cookie; their next mutating request passes the CSRF double-submit check and only fails at the session-row revocation check (401). That ordering is correct, but the 401 path never instructs the client to clear cookies, so a revoked device keeps retrying with stale credentials. Low severity, but the UX/′lost device′ story in the docstring (T-03-08) is only half-delivered.

**Fix:** On any 401 from `require_admin` due to revocation/expiry, also emit `clear_session_cookies` (or have the SPA clear store + reload on 401, which `AdminShell.pollSession` partially does but only for the GET /session poll).

### WR-09: `validate_boundary` summary `valid` flag is true for an empty `updates` list

**File:** `src/gruvax/api/admin/cubes.py:433`
**Issue:** `all_valid = all(r.get("valid", False) for r in results)` returns `True` for an empty `results` list (vacuous truth). A client sending `{updates: []}` gets `{valid: true}` and the diff preview's COMMIT button enables with nothing to commit. Minor, but it misrepresents "valid" for a no-op.

**Fix:** `all_valid = bool(results) and all(...)`.

### WR-10: CubeEditor never sends `force` and cannot edit `is_empty` — phantom "USE ANYWAY" is a dead end; comparator errors are invisible

**File:** `frontend/src/routes/admin/CubeEditor.tsx:251-261,329-338,432-466`
**Issue:** The editor toggles `forceFirst` / `forceLast` locally but never includes `force` in the `validateBoundary` payload or in the `CubeBoundaryEdit` it pushes to the pending change-set, so on bulk commit the backend re-runs the phantom check with `force=False` and rejects the very value the admin chose "USE ANYWAY" — the commit fails (and `DiffPreviewSheet.handleCommit` only shows a generic "Could not save"). Also, `CubeBoundaryEdit` has no `is_empty`, so marking a cube empty is impossible through this flow. Comparator failures (`valid:false, error:'boundary_order_error'`) are not surfaced in the editor at all (only `phantom` is read at `:265`).

**Fix:** Add `force` and `is_empty` to `CubeBoundaryEdit` (and the backend already accepts them), thread `forceFirst||forceLast` into the validate + pending edit, and render the `boundary_order_error` result with a blocking message so the admin can't commit an out-of-order boundary.

### WR-11: `revert_change_set` second 404 masks a real "nothing to do" outcome

**File:** `src/gruvax/api/admin/history.py:173-178`
**Issue:** After the transaction, `if not reverted and not skipped: raise 404`. But `fetch_change_set_rows` already returned non-empty rows (otherwise we 404'd earlier). The only way to reach here is if every row was processed yet neither list filled — which cannot happen given the loop always appends to one of the two lists. This branch is effectively dead, but if the loop logic ever changes (e.g. a `continue` that skips both appends), a successful no-op revert would be reported to the user as "change set not found," which is misleading.

**Fix:** Remove the dead branch, or replace with a precise "already fully reverted" response (`reverted: [], skipped: [...]` is the meaningful signal, not 404).

## Info

### IN-01: `secrets.compare_digest` not used on the CSRF compare path

**File:** `src/gruvax/api/deps.py:122`
**Issue:** CSRF tokens are compared with `csrf_header != csrf_cookie` (non-constant-time). The PIN path is fine (passlib `verify` is constant-time), but the project auth contract calls for `secrets.compare_digest`. For a LAN app the timing-oracle risk is negligible, but it is a one-line hardening.
**Fix:** `if not csrf_header or not secrets.compare_digest(csrf_header, csrf_cookie): raise 403`.

### IN-02: Migration seeds `session.hard_cap_seconds` and `session.idle_ttl_seconds` that the runtime never reads from the DB

**File:** `migrations/versions/0004_admin_tables.py:113-130`; `src/gruvax/auth/sessions.py:33`; `src/gruvax/api/deps.py:163`
**Issue:** The hard cap is hardcoded `HARD_CAP_SECONDS = 1800` in code and the idle TTL comes from env `SESSION_TTL_SECONDS`; the seeded `session.*` settings rows are dead config that can silently diverge from actual behavior (see WR-02).
**Fix:** Either read these from the settings cache at session-create / validate time, or drop the seed rows to avoid the impression they are authoritative.

### IN-03: `DiffPreviewSheet` "BEFORE/AFTER" table only shows AFTER

**File:** `frontend/src/routes/admin/DiffPreviewSheet.tsx:178-204`
**Issue:** Header/comment say "Before / After table" but only an AFTER column is rendered; there is no BEFORE column despite the validate response providing `records_before`. Misleading for a pre-commit review screen.
**Fix:** Add the BEFORE values (available from `validateResult.movement_counts` once CR-03 is fixed) or rename the section.

### IN-04: Cube address numbering is inconsistent across views (0-based vs 1-based)

**File:** `frontend/src/routes/admin/CubesGrid.tsx:127` (`{row}/{col}` 0-based) vs `frontend/src/routes/admin/DiffPreviewSheet.tsx:27-29` and `HistoryView.tsx:38-40` (`row+1`/`col+1` 1-based) vs `kiosk/CubeContentsPanel.tsx:35-40` (letter+`col+1`)
**Issue:** The same cube shows as `1/0/0` in the grid, `1/1/1` in the diff/history, and `A1` on the kiosk. Confusing for an operator cross-referencing screens.
**Fix:** Pick one display convention for admin cube addresses and apply it consistently.

### IN-05: `is_catalog_query` / search SQL doc-comments reference findings from a prior phase ("CR-04", "CR/WR-01")

**File:** `src/gruvax/db/queries.py:238,270`
**Issue:** Inline comments cite review IDs (`CR-04`, `CR/WR-01`) that are meaningless without the originating review. Harmless but noisy.
**Fix:** Replace with the requirement IDs (SRCH-*) already used elsewhere.

### IN-06: PinOverlay auto-submit effect disables exhaustive-deps and depends only on `digits`

**File:** `frontend/src/routes/admin/PinOverlay.tsx:46-51`
**Issue:** The auto-submit effect lists only `[digits]` and suppresses the lint rule; `submitPin` and `status` are referenced but omitted. It works today because of the `status === 'idle'` guard, but it is fragile under React 19 effect semantics and future edits.
**Fix:** Move the "4th digit" trigger into `handleDigit` (compute the next array and submit inline) so there is no effect-on-state-change at all.

### IN-07: `_find_next_populated_cube` returns a plain dict but is documented as crossing units in shelf order without unit-boundary semantics

**File:** `src/gruvax/api/admin/cubes.py:586-616`
**Issue:** Suggest-midpoint walks all boundaries sorted by `(unit_id, row, col)` and returns the next non-empty cube even if it is in a different unit; the same-label guard at `:551` then usually returns `null` for cross-unit/cross-label cases, so suggestions silently fail at unit edges. Behavior is safe (returns `{suggestion: null}`) but the feature quietly does nothing for the last populated cube of a label.
**Fix:** Document the cross-label/cross-unit limitation in the UI hint, or extend midpoint to handle the cross-label case (currently explicitly out of scope at `:552-554`).

---

_Reviewed: 2026-05-20_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_

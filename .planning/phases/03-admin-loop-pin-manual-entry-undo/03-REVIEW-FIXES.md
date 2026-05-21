---
phase: 03-admin-loop-pin-manual-entry-undo
fixed_at: 2026-05-20T00:00:00Z
review_path: .planning/phases/03-admin-loop-pin-manual-entry-undo/03-REVIEW.md
iteration: 1
findings_in_scope: 15
fixed: 12
skipped: 3
status: partial
---

# Phase 3: Code Review Fix Report

**Fixed at:** 2026-05-20
**Source review:** `.planning/phases/03-admin-loop-pin-manual-entry-undo/03-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 15 (4 Critical + 11 Warning; Info findings handled selectively)
- Fixed: 12
- Skipped: 3 (WR-03, WR-05, WR-06 — see rationale below)

## Fixed Issues

### CR-01: Frontend field names aligned to backend contract

**Files modified:** `frontend/src/api/types.ts`, `frontend/src/routes/admin/CubesGrid.tsx`, `frontend/src/routes/admin/CubeEditor.tsx`, `frontend/src/routes/admin/DiffPreviewSheet.tsx`
**Commit:** 2760fd0
**Applied fix:** Renamed `label_first/catalog_first/label_last/catalog_last` → `first_label/first_catalog/last_label/last_catalog` in `CubeBoundaryEdit`, `AdminCube`, and `AdminCubeBoundary` TS interfaces, and in every `.tsx` read/write of those fields. Backend is the source of truth (Pydantic `BoundaryEdit` model and DB columns). Also added `is_empty?: boolean` and `force?: boolean` to `CubeBoundaryEdit` for WR-10.

### CR-02: validateBoundary sends {updates} not {edits}

**Files modified:** `frontend/src/api/adminClient.ts`
**Commit:** 7bde0fa
**Applied fix:** Changed `JSON.stringify({ edits })` to `JSON.stringify({ updates: edits })` in `validateBoundary`. The backend `ValidateRequest` model uses key `updates`. `adminBulkSave` already correctly used `{ updates }`.

### CR-03: movement_counts treated as list (not object) in DiffPreviewSheet

**Files modified:** `frontend/src/api/types.ts`, `frontend/src/routes/admin/DiffPreviewSheet.tsx`
**Commit:** 2760fd0 (bundled with CR-01 — same files)
**Applied fix:**
- Changed `MovementCount` type to include `delta`, `fill_level_before`, `fill_level_after` fields that the backend actually emits.
- Changed `movement_counts?: MovementCount` to `movement_counts?: MovementCount[]` (list) in `ValidateItem`.
- `DiffPreviewSheet`: replaced `const hasMoves = validateResult?.movement_counts; const moveCounts = hasMoves ? [hasMoves] : []` with `const moveCounts = validateResult?.movement_counts ?? []` (iterate the list directly). Overstuffed check now uses `moveCounts[0]`. Field name reads updated for CR-01 simultaneously.

### CR-04: clear_session_cookies mirrors set_cookie attributes

**Files modified:** `src/gruvax/auth/sessions.py`
**Commit:** f18e44c
**Applied fix:** `clear_session_cookies` now explicitly sets `path="/"`, `httponly=True/False`, `samesite="strict"`, and a `secure` parameter (default `False` for dev HTTP). Added `secure: bool = False` parameter so callers can pass `True` in production HTTPS. Without matching attributes, browsers ignore the clearing `Set-Cookie` when `secure=True` ships.

### WR-01: Settings GET/PUT key alignment

**Files modified:** `frontend/src/api/types.ts`, `frontend/src/api/adminClient.ts`, `frontend/src/routes/admin/Settings.tsx`, `src/gruvax/api/admin/settings.py`
**Commit:** bf2eb4b
**Applied fix:** `AdminSettings` and `AdminSettingsPut` TS types now use `cube_nominal_capacity` / `session_idle_ttl_seconds` to match the backend response. `Settings.tsx` reads and writes the corrected keys. `putAdminSettings` return type is `Partial<AdminSettings>` since the backend returns `{updated:[...]}` not a full settings object. Note: the settings endpoint itself was already consistent on the backend side — only the frontend types were misaligned.

### WR-02: Settings cache refreshed after PUT /settings

**Files modified:** `src/gruvax/api/admin/settings.py`
**Commit:** bf2eb4b
**Applied fix:** After committing the DB write in `update_settings`, `app.state.settings_cache` is reloaded from the DB via `load_settings_cache(pool)`. Non-fatal — if the reload fails, the DB write is preserved and a warning is logged. This ensures fill-level computations in the public kiosk and admin grid pick up a new `cube_nominal_capacity` without a process restart.

### WR-04: PIN shape validation before Argon2 + JSON decode guard

**Files modified:** `src/gruvax/api/admin/login.py`
**Commit:** 6352fb3
**Applied fix:** Login endpoint now (1) wraps `await request.json()` in try/except and returns HTTP 400 on malformed JSON, and (2) validates that `pin` is exactly 4 digits before any DB/hash work, returning a uniform 401 (same status as wrong PIN — no oracle). `change_pin` already validated `new_pin` format; login now consistently validates the incoming PIN upfront.

### WR-07: Revert coerces is_empty from completeness to prevent CHECK violation

**Files modified:** `src/gruvax/api/admin/history.py`
**Commit:** a098c56
**Applied fix:** Before calling `write_boundary`, the revert path now checks whether all four `prev_*` columns are non-NULL. If any column is NULL, `prev_is_empty` is forced to `True` to prevent the `empty_or_complete` CHECK constraint (`NOT is_empty → all four boundary columns NOT NULL`) from aborting the transaction.

### WR-09: validate_boundary vacuous-truth fix for empty updates list

**Files modified:** `src/gruvax/api/admin/cubes.py`
**Commit:** 4bb247f
**Applied fix:** Changed `all_valid = all(r.get("valid", False) for r in results)` to `all_valid = bool(results) and all(...)`. An empty `updates` list now returns `{valid: false}` instead of the vacuously-true `{valid: true}`, preventing the COMMIT button from enabling with nothing to commit.

### WR-10: Thread `force` flag into CubeBoundaryEdit (partial fix)

**Files modified:** `frontend/src/routes/admin/CubeEditor.tsx`
**Commit:** b3c0788
**Applied fix:** `handleAddToPending` now includes `force: forceFirst || forceLast` in the edit pushed to `pendingChangeSet`. This means the bulk commit endpoint receives `force=True` when the admin accepted a phantom via USE ANYWAY, preventing the backend re-validation from re-blocking the commit. The debounce validate call intentionally does NOT pre-set `force` so the phantom warning still appears. The `is_empty` flag is not threaded (marking cubes empty via the editor is deferred — UI does not expose an is_empty toggle in the current form).

### WR-11: Remove dead 404 branch in revert_change_set

**Files modified:** `src/gruvax/api/admin/history.py`
**Commit:** a098c56
**Applied fix:** Removed the `if not reverted and not skipped: raise HTTPException(404)` branch after the transaction. This branch was unreachable because the loop always appends each cube to `reverted` or `skipped`. A fully-conflicted revert now correctly returns `{reverted:[], skipped:[...]}` rather than a misleading 404.

### IN-01: CSRF comparison uses secrets.compare_digest

**Files modified:** `src/gruvax/api/deps.py`
**Commit:** b3c0788
**Applied fix:** The CSRF double-submit check in `require_admin` now uses `secrets.compare_digest(csrf_header, csrf_cookie)` instead of `csrf_header != csrf_cookie`. Constant-time comparison prevents a timing oracle. One-line hardening as the reviewer noted.

## Skipped Issues

### WR-03: PinOverlay fabricates session expiry times

**File:** `frontend/src/routes/admin/PinOverlay.tsx:78-85`
**Reason:** deferred — low user impact before WR-01/WR-02 are solid; the correct fix is to return `expires_at` / `hard_cap_at` from `POST /login` and seed the store, which requires a backend contract change. The frontend already polls `/session` every 30 s which corrects any fabricated value quickly. Recommend addressing in a follow-on iteration alongside WR-02's idle-TTL wiring.

### WR-05: Rate-limit key trusts REMOTE_ADDR with no proxy awareness

**File:** `src/gruvax/api/admin/login.py:72`; `src/gruvax/api/admin/limiter.py:19`
**Reason:** deferred — this is a deployment/infrastructure concern. For the documented single-host home-LAN deployment with no reverse proxy, `request.client` is the direct client IP and the rate limit works correctly. Adding `ProxyHeadersMiddleware` or a custom key_func risks SSRF if an untrusted `X-Forwarded-For` header is accepted without validating the proxy chain. Adding a code comment documenting this limitation is sufficient for Phase 3.

### WR-06: slowapi private internals coupling in _check_login_rate_limit

**File:** `src/gruvax/api/admin/login.py:75-94`
**Reason:** deferred — this is a medium-risk refactor. The current implementation uses `limiter._key_prefix`, `limiter._limiter.hit(...)`, and `slowapi.wrappers.Limit(...)`. While fragile across slowapi minor upgrades, the code has a detailed module docstring explaining the rationale. Refactoring to own a `limits.strategies.FixedWindowRateLimiter` directly would decouple from slowapi internals but requires careful testing to avoid breaking the 429 response shape (the `RateLimitExceeded` exception handler reads `view_rate_limit` attributes). Deferred to a maintenance pass.

## Contract Decision (CR-01/CR-02)

Backend is the source of truth per the task instructions. All field renames and key fixes were applied to the frontend only. The backend Pydantic models (`BoundaryEdit`, `ValidateRequest`) are correct and unchanged.

## Test Results

```
tests/unit/test_pin.py ....                    4 passed
tests/unit/test_sessions.py ....               4 passed
tests/unit/test_boundary_validation.py .....   5 passed
tests/unit/test_diff_preview.py .              1 passed
                                              14 passed, 2 warnings
```

Integration tests (test_admin_auth, test_boundary_editor, test_change_set, test_cube_public) require a running PostgreSQL instance and were not run in this fix pass — they are covered by the CI pipeline.

TypeScript: `npx tsc --noEmit` — clean (0 errors).
Ruff: all checks passed on 6 modified Python files.
mypy: no issues found in 6 modified Python files.

---

_Fixed: 2026-05-20_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_

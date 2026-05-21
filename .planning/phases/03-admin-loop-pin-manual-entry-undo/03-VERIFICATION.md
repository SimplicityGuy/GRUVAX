---
phase: 03-admin-loop-pin-manual-entry-undo
verified: 2026-05-20T00:00:00Z
status: human_needed
score: 5/5 must-haves verified
overrides_applied: 0
human_verification:
  - test: "Open /admin on a phone-sized viewport and on the kiosk viewport. Tap the keypad to enter the correct PIN. Confirm the PinOverlay appears, keypad dots register, entering the PIN lands on the admin shell without any system keyboard appearing on the kiosk."
    expected: "Admin shell loads with GRUVAX ADMIN wordmark, countdown pill, Lock icon, and Log out icon. No system keyboard appears."
    why_human: "Touch behavior of NumericKeypad (tap target feel, kiosk mode, no system keyboard) cannot be grepped. The in-app keypad is the kiosk-safety requirement."
  - test: "Watch the countdown pill in the admin shell header. After login the pill immediately shows a value. Wait until fewer than 60 seconds remain. Confirm the pill changes to the warning color and is announced by a screen reader (aria-live='polite')."
    expected: "Countdown ticks down in mm:ss; pill turns to --gruvax-warning color in last 60 s; aria-live announcement fires."
    why_human: "Color change and screen-reader announcement are visual/assistive-tech behaviors that require live testing. Note: the initial countdown value is fabricated (10 min hardcoded) and corrects to the real server value within 30 s of the first /session poll (WR-03, deferred)."
  - test: "Tap Lock. Confirm the PIN overlay returns without logging out (session stays active). Re-enter the PIN. Confirm the same session countdown continues (session not reset). Tap Logout. Confirm immediate logout with no confirmation dialog."
    expected: "Lock re-shows PinOverlay while preserving the session. Logout is immediate (ADMN-08)."
    why_human: "Session continuity across Lock and the 'no-confirm logout' flow are interactive behaviors that need click-through verification."
  - test: "Open the cubes grid at /admin/cubes. Confirm each cube card shows a fill bar. Tap a cube to open the editor. In the label field, confirm only labels from the collection appear. Select a label. Confirm the catalog# field is disabled until a label is chosen, then shows only catalogs for that label."
    expected: "Two-step dependent autocomplete: label list from v_collection, catalog list scoped to selected label, catalog field disabled before label selection (ADMN-03)."
    why_human: "Dropdown population from real v_collection data and disabled-state UX need interactive verification."
  - test: "Type a catalog# that is NOT in the collection. Confirm a phantom warning appears with tappable near-miss chips. Tap a chip to fill the field. Then tap 'USE ANYWAY' and confirm it sets force mode. Then attempt to set first_catalog AFTER last_catalog and confirm the boundary_order_error message blocks preview/save."
    expected: "Phantom blocked with trigram near-misses; force path works; first>last rejected via POS-01 (ADMN-06)."
    why_human: "Phantom chip rendering, tappable suggestions, and the comparator error message are UI behaviors."
  - test: "For a cube between two populated cubes, tap 'SUGGEST MIDPOINT'. Confirm the suggested record is a real record in the collection (verify by searching for it), that it is pre-filled as editable, and that it is not auto-applied."
    expected: "Real owned RecordRow from index space, editable, not committed until ADD TO PENDING (ADMN-12, Pitfall 22)."
    why_human: "Verifying the suggested record actually exists in the collection requires cross-referencing the kiosk search — a human lookup."
  - test: "Edit one cube boundary (ADD TO PENDING). Tap PREVIEW CHANGES. Confirm the diff sheet shows the changed cube ringed on the mini Kallax grid, the AFTER boundary values, and record-movement counts. Tap COMMIT CHANGE SET. Confirm the 'Saved — change set {id}' checkmark and that the kiosk grid reflects the new boundary on next load."
    expected: "Diff preview shows changed cubes + AFTER values + movement counts (ADMN-07). Commit writes atomically and cache reloads (ADMN-09)."
    why_human: "Mini-grid ring rendering, movement count display, and post-commit kiosk reflection need end-to-end visual verification."
  - test: "Navigate to /admin/history. Confirm change-sets appear newest-first with a short UUID, source badge, timestamp, and cube count. Tap REVERT on a change-set. Confirm the destructive confirm dialog appears. Confirm the revert. Verify a REVERTED pill appears and the boundaries are restored. Then verify a new revert change-set appears in the history (so the revert is undoable)."
    expected: "History list newest-first; one-tap conflict-aware revert; undoable inverse change-set recorded (ADMN-09)."
    why_human: "The REVERTED pill, card rendering, and multi-step revert flow require click-through."
  - test: "Create conflict scenario: commit change-set A (edit cube B1). Then commit change-set B (edit cube B1 again). Then try to REVERT change-set A. Confirm the conflict banner appears naming the skipped cube, and that B1 is not silently clobbered."
    expected: "Conflict-aware revert: non-conflicting cubes reverted, conflicting cubes skipped+reported, no silent clobber (D-12)."
    why_human: "The conflict banner and skip-report message need visual verification."
  - test: "Open the kiosk view (no login). Confirm cubes with boundary data show a fill bar at the bottom edge. Check fill-bar color thresholds: under 80% is blue-light, 80-100% is yellow, over 100% is red/error. Tap a populated cube. Confirm the bottom-sheet panel slides up with the cube address, record count + fill%, FIRST/LAST records, and ~7 sampled records. Tap an empty cube. Confirm the 'No records assigned to this cube yet' copy appears. Dismiss by tapping outside. While logged in as admin, confirm the EDIT THIS CUBE shortcut appears in the panel."
    expected: "Public fill bars (CUBE-07) and cube contents panel (CUBE-09) work correctly. EDIT THIS CUBE gated on isLoggedIn."
    why_human: "Fill-bar color thresholds, panel slide-up animation, and the D-16 admin shortcut toggling are visual behaviors."
---

# Phase 3: Admin Loop (PIN + Manual Entry + Undo) Verification Report

**Phase Goal:** Owner can sign in (mobile-first, kiosk fallback with in-app numeric keypad), enter cube boundaries by hand with autocomplete + diff preview, see every mutation logged, and undo by change-set — boundaries become a maintained artifact, not a fixture.

**Verified:** 2026-05-20
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|---------|
| 1 | Owner opens /admin, enters PIN via Argon2id check against gruvax.settings, reaches boundary editor; session is sliding-window with visible 60 s countdown | VERIFIED (automated) / HUMAN NEEDED (UI) | `pin.py` exports `hash_pin`/`verify_pin` using passlib Argon2id; `sessions.py` creates session row with `expires_at`/`hard_expires_at`; `require_admin` slides window on each request; `AdminShell.tsx` has `WARNING_THRESHOLD_MS = 60_000` + `admin-countdown--warning` class + `aria-live="polite"`. 8/8 auth integration tests pass. Kiosk keypad UX needs human verification. |
| 2 | Owner edits cube boundaries via two-step autocomplete fed by gruvax.v_collection; phantom values blocked unless confirmed; shared parser rejects first>last | VERIFIED (automated) / HUMAN NEEDED (UI) | `validation.py` uses `parse_key` only; `cubes.py` `POST /validate` and `PUT /boundary` both run comparator + phantom check + near-miss lookup; `CubeEditor.tsx` disables catalog field until label chosen; 4/4 boundary editor tests pass. Interactive autocomplete and phantom chip rendering need human check. |
| 3 | Diff preview before commit; commit writes boundary_history with change_set_id; History view lists change-sets with one-tap revert | VERIFIED (automated) / HUMAN NEEDED (UI) | `cubes.py` `POST /bulk` writes atomically with shared `change_set_id`; `history.py` `POST /revert` writes `source='revert'`; `DiffPreviewSheet.tsx` calls `adminBulkSave` with `Idempotency-Key`; `HistoryView.tsx` calls `revertChangeSet` with conflict banner. 5/5 change-set tests pass. Visual diff-sheet and history card rendering need human verification. |
| 4 | Each cube shows fill-level indicator; tapping a cube opens side panel with first/last records + sample subset | VERIFIED (automated) / HUMAN NEEDED (UI) | `units.py` returns `fill_level`, `total_count`, `sample_records` from in-memory snapshot; `FillBar.tsx` renders in `Cube.tsx`; `CubeContentsPanel.tsx` fetches `fetchCubeContents` with TanStack Query; 3/3 cube public tests pass. Fill-bar color thresholds and panel touch feel need human check. |
| 5 | "Suggest midpoint" walks collection-INDEX space (not catalog-string space), editable, never auto-applied | VERIFIED | `boundary_math.py` `suggest_midpoint` sorts by `parse_key`, finds indices `i_a`/`i_b`, returns `records[mid]` only when `i_a < mid < i_b`; `cubes.py` calls it and returns `{suggestion: {...}}`; `CubeEditor.tsx` pre-fills field on result, does not auto-commit. No `normalize_catalog` usage in `boundary_math.py`. 3/3 midpoint tests + 3/3 property tests pass. |

**Score:** 5/5 truths have sufficient codebase evidence (all have mechanical verification passing; UI interaction behaviors deferred to human).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `migrations/versions/0004_admin_tables.py` | DDL for 4 admin tables + seeded settings | VERIFIED | Creates `boundary_history`, `admin_sessions`, `settings`, `idempotency_keys`. Seeds `cube.nominal_capacity=95`, `session.idle_ttl_seconds=600`, `session.hard_cap_seconds=1800`. `down_revision='0003'` correct. |
| `src/gruvax/auth/pin.py` | Argon2id hash_pin/verify_pin | VERIFIED | `CryptContext(schemes=['argon2'])`, `_ctx.verify()` only, never `==` on hashes. |
| `src/gruvax/auth/sessions.py` | create_session / get_session_id / revoke helpers + clear_session_cookies (CR-04 fixed) | VERIFIED | All helpers present. `clear_session_cookies` mirrors `path='/'`, `httponly`, `samesite`, `secure` attributes to prevent cookie-clear mismatch in HTTPS. |
| `src/gruvax/api/deps.py` | require_admin (cookie + CSRF + sliding TTL) | VERIFIED | `get_session_id` → CSRF double-submit (`secrets.compare_digest`, IN-01 fixed) → session row validity → sliding window UPDATE. |
| `src/gruvax/api/admin/login.py` | Rate-limited login/logout/session endpoints | VERIFIED | Inline `FixedWindowRateLimiter.hit()` (not SlowAPIMiddleware, WR-06 deferred). 4-digit PIN shape validated before hash (WR-04 fixed). PIN never logged. |
| `src/gruvax/api/admin/settings.py` | GET/PUT settings + change-pin with session revocation | VERIFIED | Settings keys aligned (WR-01 fixed). Cache refreshed after PUT (WR-02 fixed). Change-pin revokes other sessions. |
| `src/gruvax/api/admin/cubes.py` | GET cubes, GET boundary, POST validate, POST suggest, POST bulk | VERIFIED | All endpoints present with `require_admin`. `parse_key`/`compare_catalogs` used for comparator (never raw string). `Idempotency-Key` header read and short-circuited. `cache.invalidate()`+`cache.load()` called AFTER transaction (Pitfall A). Validate returns 200 for dry-run (WR-09 fixed). |
| `src/gruvax/api/admin/history.py` | GET history, POST revert (conflict-aware) | VERIFIED | `has_newer_changes` called before inverse write. `source='revert'` on inverse rows. `is_empty` coerced from completeness check (WR-07 fixed). Dead 404 branch removed (WR-11 fixed). |
| `src/gruvax/estimator/boundary_math.py` | count_records_in_boundary, sample_records, suggest_midpoint | VERIFIED | All three exported. Labels use `.casefold()`, catalogs use `parse_key`/`catalog_in_range`. `normalize_catalog` count is 0. 21/21 unit+property tests pass. |
| `src/gruvax/settings.py` | SESSION_SECRET (no default), SESSION_TTL_SECONDS | VERIFIED | `SESSION_SECRET: str` with no default (crash-on-missing). `SESSION_TTL_SECONDS: int = 600`. |
| `scripts/set_pin.py` | gruvax-set-pin bootstrap CLI | VERIFIED | Uses `getpass`, validates 4-digit numeric, calls `hash_pin`, UPSERTs into `gruvax.settings`. Registered in `pyproject.toml` as `gruvax-set-pin`. |
| `frontend/src/routes/admin/PinOverlay.tsx` | PIN overlay with in-app keypad, role="dialog" aria-modal | VERIFIED | `role="dialog" aria-modal="true"` present. Uses `NumericKeypad`. Auto-submits on 4th digit. Shake/flash on wrong PIN. Rate-limit countdown message. 107+ lines. |
| `frontend/src/routes/admin/AdminShell.tsx` | Admin chrome with countdown / Lock / Logout | VERIFIED | Countdown pill with `aria-live="polite"`, `admin-countdown--warning` at last 60 s. Lock button (`aria-label="Lock screen"`). Logout button (`aria-label="Log out"`). Polls `/session` every 30 s. |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx` | Pre-commit diff preview + commit | VERIFIED | Mini Kallax grid with changed-cube rings. COMMIT CHANGE SET + BACK TO EDITOR buttons. `adminBulkSave` with `Idempotency-Key` (= `pendingChangeSet.id`). Clears `pendingChangeSet` on success. Note: BEFORE column not shown, only AFTER (IN-03 from review — info level, not fixed). |
| `frontend/src/routes/admin/HistoryView.tsx` | Change-set list + revert | VERIFIED | TanStack Query on `['admin','history']`. REVERT confirm dialog with destructive copy. REVERTED pill. Conflict banner for skipped[] cubes. Empty state. |
| `frontend/src/routes/kiosk/FillBar.tsx` | Token-driven fill-level bar (CUBE-07) | VERIFIED | Color thresholds via CSS tokens: `--gruvax-blue-light` / `--gruvax-yellow` / `--gruvax-error`. No hardcoded hex. Rendered inside `Cube.tsx`. |
| `frontend/src/routes/kiosk/CubeContentsPanel.tsx` | Reverse-lookup side panel (CUBE-09) | VERIFIED | Fetches `fetchCubeContents`; shows count+fill%; FIRST/LAST boundary records; ~7 sample rows; "No records assigned to this cube yet." empty-state; D-16 EDIT THIS CUBE gated on `isLoggedIn`. |
| `frontend/src/state/adminStore.ts` | Admin Zustand store with pendingChangeSet + persist | VERIFIED | `pendingChangeSet: ChangeSet | null`. `persist` middleware with `partialize` wrapping only `pendingChangeSet`. Auth state NOT persisted. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `PinOverlay.tsx` | `/api/admin/login` | `adminClient.adminLogin` | VERIFIED | `adminLogin(pin)` in `adminClient.ts`; called in `submitPin()`. |
| `login.py` | `gruvax.auth.pin.verify_pin` | PIN hash from `gruvax.settings auth.pin_hash` | VERIFIED | `verify_pin(pin, stored_hash)` called after DB fetch of `auth.pin_hash`. |
| `app.py` | `create_admin_router()` | `include_router` before `StaticFiles` | VERIFIED | Line 188-190: admin router registered with `prefix="/api"` before `SpaStaticFiles` mount. |
| `cubes.py POST /bulk` | `boundary_cache.invalidate + load` | After transaction context exits (Pitfall A) | VERIFIED | Lines 761-763: `cache.invalidate(); await cache.load(pool)` outside `conn.transaction()`. |
| `history.py POST /revert` | `boundary_history source='revert'` | `write_history_row(..., source='revert')` | VERIFIED | Line 171 in `history.py` passes `source="revert"`. |
| `DiffPreviewSheet.tsx` | `/api/admin/cubes/bulk` | `adminBulkSave` with `Idempotency-Key` header | VERIFIED | `adminBulkSave(edits, idempotencyKey)` at line 93; `adminClient.ts` sends `Idempotency-Key` header. |
| `CubeContentsPanel.tsx` | `/api/cubes/{u}/{r}/{c}` | `fetchCubeContents` in `client.ts` | VERIFIED | `fetchCubeContents` imported and called in `useQuery`. |
| `Cube.tsx` | `FillBar.tsx` | FillBar rendered inside each cube cell | VERIFIED | `import { FillBar }` at line 2; rendered at line 107. |
| `CubeEditor.tsx` | `/api/admin/cubes/suggest` | `adminClient.suggestMidpoint` | VERIFIED | `suggestMidpoint(unitId, rowNum, colNum)` called on "SUGGEST MIDPOINT" press. |
| `validation.py` | `normalize.parse_key` | `validate_boundary_order` uses `parse_key` | VERIFIED | `from gruvax.estimator.normalize import parse_key` at line 18; used at line 56. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|--------------------|--------|
| `cubes.py GET /cubes` | `cubes` list with `fill_level` | `count_records_in_boundary(boundary_row, snapshot)` / `pool.connection()` SQL | YES — real boundary rows + snapshot computation | FLOWING |
| `history.py GET /history` | `change_sets` | `list_change_sets(pool)` → `SELECT ... FROM gruvax.boundary_history GROUP BY change_set_id` | YES — real DB rows | FLOWING |
| `cubes.py POST /bulk` | `boundary_history` rows | `write_history_row(conn, ...)` inside `conn.transaction()` | YES — atomic DB write | FLOWING |
| `DiffPreviewSheet.tsx` | `validateResults` | `validateBoundary(pendingChangeSet.edits)` → `POST /api/admin/cubes/validate` | YES — real snapshot movement counts | FLOWING |
| `HistoryView.tsx` | `data` (history items) | `getHistory()` → `GET /api/admin/history` | YES — real DB rows | FLOWING |
| `CubeContentsPanel.tsx` | `data` (`CubeContentsResponse`) | `fetchCubeContents()` → `GET /api/cubes/{u}/{r}/{c}` | YES — extended endpoint with `fill_level`, `total_count`, `sample_records` from snapshot | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Argon2id hash/verify imports | `uv run python -c "import passlib.hash, slowapi; print('deps ok')"` | deps ok | PASS |
| Frontend TypeScript | `cd frontend && npx tsc --noEmit; echo $?` | exit 0 | PASS |
| Frontend build | `cd frontend && npm run build; echo $?` | exit 0 (size warning only) | PASS |
| Ruff lint on auth + admin | `uv run ruff check src/gruvax/auth src/gruvax/api/admin src/gruvax/api/deps.py` | All checks passed | PASS |
| mypy type check | `uv run mypy src/gruvax/auth src/gruvax/api/admin src/gruvax/api/deps.py src/gruvax/estimator/boundary_math.py` | Success: no issues in 13 source files | PASS |
| 8 auth integration tests | `uv run pytest tests/integration/test_admin_auth.py` | 8 passed | PASS |
| 4 boundary editor tests | `uv run pytest tests/integration/test_boundary_editor.py` | 4 passed | PASS |
| 5 change-set tests | `uv run pytest tests/integration/test_change_set.py` | 5 passed | PASS |
| 3 cube public tests | `uv run pytest tests/integration/test_cube_public.py` | 3 passed | PASS |
| 21 boundary math tests | `uv run pytest tests/unit/test_fill_level.py tests/unit/test_cube_contents.py tests/unit/test_midpoint.py tests/property/test_fill_level_property.py tests/property/test_midpoint_property.py` | 21 passed | PASS |
| Pitfall A: no invalidate inside transaction | `grep -n "invalidate" src/gruvax/api/admin/cubes.py` | Lines 761-763 are outside `conn.transaction()` block | PASS |
| Pitfall 22: no normalize_catalog in boundary_math | `grep -c "normalize_catalog" src/gruvax/estimator/boundary_math.py` | 0 | PASS |
| No f-string SQL in admin files | `grep -c "f\"SELECT\|f\"INSERT\|f\"UPDATE\|f\"DELETE" src/gruvax/api/admin/cubes.py src/gruvax/api/admin/history.py src/gruvax/db/queries.py` | 0 | PASS |
| No hardcoded hex in admin CSS | `grep -rE "#[0-9a-fA-F]{3,6}" frontend/src/routes/admin/admin.css` | No matches | PASS |
| No debt markers (TBD/FIXME/XXX) | `grep -rn "TBD\|FIXME\|XXX" src/gruvax/api/admin src/gruvax/auth` | No output | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|---------|
| ADMN-01 | 03-02 | PIN login (Argon2id) on mobile or kiosk | SATISFIED | `pin.py` + `login.py` + `PinOverlay.tsx` + `NumericKeypad.tsx`. 8/8 auth tests green. |
| ADMN-02 | 03-02 | Sliding-window session timeout; 60 s countdown | SATISFIED | `require_admin` refreshes `expires_at`; `AdminShell.tsx` `WARNING_THRESHOLD_MS = 60_000`. Human check needed for visual countdown. |
| ADMN-03 | 03-04 | Manual boundary entry with autocomplete from collection | SATISFIED | `CubeEditor.tsx` two-step dependent autocomplete; `GET /api/admin/labels` and `/catalogs` from `gruvax.v_collection` only. Human check needed. |
| ADMN-06 | 03-04 | Boundary saves validated against collection; trigram near-misses | SATISFIED | `cube_exact_match` + `find_boundary_near_misses` (pg_trgm, `UndefinedFunction` fallback). 4/4 boundary editor tests green. |
| ADMN-07 | 03-05 | Diff preview with affected cubes highlighted before commit | SATISFIED | `DiffPreviewSheet.tsx` mini-grid + per-cube AFTER values + movement counts. Human check for rendering. |
| ADMN-08 | 03-02 | Admin can log out manually from any screen | SATISFIED | `POST /api/admin/logout` revokes session row + clears cookies; `handleLogout` in `AdminShell.tsx` immediate, no confirm. |
| ADMN-09 | 03-05 | Append-only change log grouped by change-set; revert by change-set | SATISFIED | `boundary_history` table; `POST /bulk` writes `change_set_id`; `HistoryView.tsx` + `POST /revert` with conflict detection. 5/5 change-set tests green. |
| ADMN-12 | 03-04 | Suggest-midpoint catalog# from natural sort of adjacent cubes | SATISFIED | `suggest_midpoint` in `boundary_math.py` uses index-space (Pitfall 22); `POST /cubes/suggest` returns real RecordRow; `CubeEditor.tsx` pre-fills, does not auto-apply. |
| CUBE-07 | 03-03 | Fill-level indicator per cube computed from boundary range | SATISFIED | `FillBar.tsx` token-driven color thresholds; `units.py` bulk endpoint extended with `fill_level`. Human check for color rendering. |
| CUBE-09 | 03-03 | Tap cube to reveal first/last records + representative subset | SATISFIED | `CubeContentsPanel.tsx` bottom-sheet with `total_count`, `fill_level`, `sample_records`; `units.py` extended endpoint. Human check for panel UX. |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `frontend/src/routes/admin/PinOverlay.tsx:83-84` | Fabricates `expires` and `hardCap` from hardcoded 10 min / 30 min instead of reading from server (WR-03, deferred per 03-REVIEW-FIXES.md) | INFO | Countdown shows wrong value for up to 30 s after login; corrects itself on first `/session` poll. Session revocation and hard cap still enforced server-side. |
| `frontend/src/routes/admin/DiffPreviewSheet.tsx:180-204` | BEFORE column absent from diff table — only AFTER values shown (IN-03 from review, info level) | INFO | Operator sees new boundary but not what it was before commit. Does not block goal — pre-commit review shows movement counts via before/after record delta. |
| `src/gruvax/api/admin/login.py:109` | Docstring claims `{csrf_token, expires_at, hard_cap_at}` return but actual return is `{csrf_token, message}` | INFO | Documentation drift only. Code behavior is correct (session created, CSRF returned). |
| `src/gruvax/api/admin/login.py:75-94` | slowapi private internals (`limiter._key_prefix`, `limiter._limiter.hit(...)`) — WR-06, deferred | INFO | Medium-risk coupling to slowapi minor releases. Documented rationale in module docstring. LAN-only deployment reduces exploitability. |
| `src/gruvax/api/admin/login.py:72` | Rate-limit key trusts `request.client` (REMOTE_ADDR) with no proxy awareness — WR-05, deferred | INFO | Acceptable for documented single-host home-LAN deployment with no reverse proxy. |

### Human Verification Required

The automated verification passes all mechanical checks. The following behaviors require a human to click-test the live UI. These items were also identified as `checkpoint:human-verify` tasks in the PLANs (Plans 02, 03, 04, 05 each had a blocking human-verify checkpoint) and are repeated here as the end-of-phase consolidation per the `workflow.human_verify_mode = end-of-phase` pattern.

#### 1. PIN login end-to-end on mobile + kiosk

**Test:** Open `/admin` on a phone-sized viewport AND on the kiosk/touch viewport. Enter the correct PIN using the in-app keypad.
**Expected:** PIN overlay appears, keypad dots register on each tap, entering the PIN lands on the authenticated admin shell with no system keyboard appearing (kiosk-safe).
**Why human:** Touch behavior, absence of system keyboard, and smooth UX cannot be grepped.

#### 2. Countdown pill: last-60 s warning + aria-live

**Test:** Watch the countdown pill. Let it reach the last 60 s.
**Expected:** Pill color changes to `--gruvax-warning`; screen reader announces remaining time via `aria-live="polite"`.
**Why human:** Color change and screen-reader announcement are visual/assistive-tech behaviors. Note: the initial countdown value is derived from a hardcoded 10 min after login (WR-03, deferred) and corrects to the real server value within 30 s; this imprecision is acknowledged.

#### 3. Lock / Logout interaction

**Test:** Tap Lock — confirm PIN overlay returns without ending session; re-enter PIN, same countdown continues. Tap Logout — confirm immediate logout, no confirmation dialog.
**Expected:** Lock preserves session. Logout is immediate (ADMN-08).
**Why human:** Session continuity across Lock and the no-confirm logout flow are interactive states.

#### 4. Two-step dependent autocomplete

**Test:** At `/admin/cubes/:unit/:row/:col`, pick a label. Confirm catalog# field is disabled before label selection, then shows only catalogs for that label.
**Expected:** Catalog field disabled until label chosen; catalog list scoped to label from `v_collection` only (ADMN-03).
**Why human:** Dropdown population and disabled-state UX need live verification.

#### 5. Phantom blocking + force path + comparator error

**Test:** Enter a catalog# not in the collection. Confirm phantom warning + tappable near-miss chips. Tap "USE ANYWAY". Then set first after last — confirm boundary_order_error blocks.
**Expected:** Phantom blocked; near-miss chips tappable; force path accepted; first>last rejected via POS-01 (ADMN-06).
**Why human:** Phantom chip rendering, force toggle, and error message display are UI behaviors.

#### 6. Suggest-midpoint: real record from index space

**Test:** Tap "SUGGEST MIDPOINT" for a cube between two populated cubes. Verify the suggested record exists in the collection by searching for it on the kiosk. Confirm it is pre-filled as editable and not auto-applied.
**Expected:** Real owned RecordRow; editable; not committed until ADD TO PENDING (ADMN-12, Pitfall 22).
**Why human:** Verifying the suggested record exists in the collection requires cross-referencing the kiosk search.

#### 7. Diff preview + atomic commit + cache reload

**Test:** Edit a cube (ADD TO PENDING). Tap PREVIEW CHANGES. Confirm mini-grid, AFTER values, and record-movement counts. Tap COMMIT CHANGE SET. Confirm "Saved — change set {id}" checkmark. Navigate to kiosk and confirm new boundary is reflected.
**Expected:** Diff preview shows affected cubes (ADMN-07); commit writes atomically; cache reloaded (ADMN-09).
**Why human:** Mini-grid ring rendering, movement count display, and kiosk update require visual end-to-end verification.

#### 8. History view + revert + undoable inverse

**Test:** Navigate to `/admin/history`. Confirm change-sets appear newest-first with short UUID + source badge + timestamp + cube count. Tap REVERT, confirm destructive dialog, confirm revert. Verify REVERTED pill appears and a new revert change-set is added to history.
**Expected:** History list; one-tap revert; undoable inverse change-set (ADMN-09).
**Why human:** Card rendering, multi-step revert flow, and undo entry need click-through.

#### 9. Conflict-aware revert: skip + report, no silent clobber

**Test:** Commit change-set A (edit cube B1). Commit change-set B (edit B1 again). REVERT change-set A. Confirm conflict banner names the skipped cube. Confirm B1 is not silently overwritten.
**Expected:** Non-conflicting cubes reverted; conflicting cube skipped + reported (D-12).
**Why human:** Conflict banner and skip-report message are visual behaviors.

#### 10. Kiosk fill bars + cube contents panel (CUBE-07 + CUBE-09)

**Test:** Open kiosk view. Confirm fill bars appear and show correct color thresholds (under-80% blue-light, 80-100% yellow, over-100% red). Tap a populated cube — confirm panel slides up with cube address, count + fill%, FIRST/LAST, ~7 sample records. Tap empty cube — confirm "No records assigned" copy. Dismiss panel by tapping outside. While admin-logged-in, confirm EDIT THIS CUBE link appears.
**Expected:** CUBE-07 fill indicators and CUBE-09 reverse-lookup panel working as designed.
**Why human:** Color thresholds, animation feel, and EDIT THIS CUBE toggle need visual verification. Pi 5 touch-screen test recommended for tap target adequacy.

### Gaps Summary

No mechanical gaps found. All 5 roadmap success criteria have supporting implementation in the codebase, all 10 requirement IDs are accounted for, 4 critical review blockers (CR-01 through CR-04) and 8 warnings (WR-01, WR-02, WR-04, WR-07, WR-08, WR-09, WR-10, WR-11) were fixed.

Three items are intentionally deferred per `03-REVIEW-FIXES.md`:
- **WR-03**: PinOverlay fabricates session expiry (corrects within 30 s via `/session` poll). Low user impact.
- **WR-05**: Rate-limit key trusts `REMOTE_ADDR` (acceptable for single-host LAN, no reverse proxy).
- **WR-06**: slowapi private internals coupling (medium-risk refactor, documented with rationale).

Two info-level items remain unfixed:
- **IN-03**: DiffPreviewSheet shows only AFTER column, not BEFORE (admin sees movement delta via record counts but not the before-boundary values in the table).
- Doc drift in `login.py` docstring claiming `expires_at`/`hard_cap_at` in response body (actual response omits them).

Status is `human_needed` because the phase goal includes interactive UI behaviors (kiosk keypad, touch panel, countdown warning, diff-preview visual) that are blocked from automated verification.

---

_Verified: 2026-05-20_
_Verifier: Claude (gsd-verifier)_

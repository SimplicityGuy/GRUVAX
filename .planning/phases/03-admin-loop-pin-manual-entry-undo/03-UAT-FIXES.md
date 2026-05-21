---
phase: 03-admin-loop-pin-manual-entry-undo
fixed_at: 2026-05-21T09:51:00Z
source_findings: 03-UAT-FINDINGS.md
findings_in_scope: 6
fixed: 6
skipped: 0
status: all_fixed
---

# Phase 3 — UAT Fix Report

**Fixed at:** 2026-05-21
**Source findings:** `03-UAT-FINDINGS.md`

**Summary:**
- Findings in scope: F2–F7 (F1 already fixed, F8 deferred)
- Fixed: 6
- Skipped: 0

---

## Fixed Issues

### F2: `gruvax-set-pin` CLI broken (`ModuleNotFoundError: No module named 'scripts'`)

**Files modified:**
- `src/gruvax/cli/__init__.py` (new)
- `src/gruvax/cli/set_pin.py` (new — copy of scripts/set_pin.py with ruff fixes)
- `pyproject.toml`

**Commit:** `dc0481c`

**Applied fix:**
Created `src/gruvax/cli/` package with `set_pin.py` containing the same logic as
`scripts/set_pin.py`. Updated `pyproject.toml` `[project.scripts]` entry from
`scripts.set_pin:main` to `gruvax.cli.set_pin:main`. The `gruvax.cli` package is
inside the installed source tree so it resolves correctly at runtime. Ran `uv sync`
to rebuild the entry-point. The old `scripts/set_pin.py` is preserved for direct
invocation. Ruff auto-fixed two style issues (SIM117 nested-with, remove unused noqa).

**Verification:** `uv run python -c "from gruvax.cli.set_pin import main; print('OK')"` — OK.
`uv run ruff check src/gruvax` — clean. `uv run mypy src/gruvax` — clean.

---

### F3: `compose.yaml` does not pass `SESSION_SECRET` to the API container

**Files modified:**
- `compose.yaml`

**Commit:** `2e69855`

**Applied fix:**
Added `env_file: [{path: .env, required: false}]` to the `gruvax-api` service,
placed above the `environment:` block. `required: false` keeps `docker compose up`
working when `.env` is absent (CI, fresh clones). Explicit `environment:` entries
override `.env` values. `SESSION_SECRET` (which has no default and is required by
`pydantic-settings`) is now loaded from `.env` at container start.

**Verification:** `docker compose config` parses successfully. The `.env` file on
the dev host contains `SESSION_SECRET`; the service will pick it up on next
`docker compose up`.

---

### F4: Commit error surfacing + no client-side gate

**Files modified:**
- `frontend/src/api/adminClient.ts`
- `frontend/src/api/types.ts`
- `frontend/src/routes/admin/DiffPreviewSheet.tsx`

**Commit:** `f24ff60`

**Applied fix:**
Three parts:

1. **`adminBulkSave` preserves error body:** On non-200 response, attempts to parse
   the JSON body and extract `type` and `message` fields. Throws `BulkSaveError`
   (new exported class) with `errorType`, `serverMessage`, and `status` properties.
   Generic `Error` was replaced with the typed subclass.

2. **`handleCommit` surfaces server message:** Catch block checks
   `err instanceof BulkSaveError && err.serverMessage` and shows the server's
   human-readable message (e.g. "First record comes after last record. Check the
   order.") instead of the generic "check your connection" text. Generic fallback
   is kept for true network errors.

3. **COMMIT gated on validation errors:** The validate dry-run now populates
   `hasValidationErrors` and `validateErrorMessage` state. If any cube is invalid
   (order or phantom), an inline `diff-validate-error` alert is shown above COMMIT
   and the button is `disabled`. The validate catch path still does not block commit
   (server re-checks on bulk save) — network failure of the dry-run does not gate.

`ValidateItem` type extended with `message?: string` to match the server's
response shape.

---

### F5: Diff table missing BEFORE column

**Files modified:**
- `frontend/src/routes/admin/DiffPreviewSheet.tsx`
- `frontend/src/api/adminClient.ts` (imported `adminGetCubeBoundary`)

**Commit:** `f24ff60`

**Applied fix:**
On mount, `adminGetCubeBoundary(unit_id, row, col)` is called for every edited cube
in parallel with the validate call (via `Promise.all`). Results populate a
`beforeBoundaries: Map<string, AdminCubeBoundary>` keyed by `"unit_id-row-col"`.
The diff table now renders three columns: FIELD | BEFORE | AFTER. Before values come
from the fetched boundaries (`before?.first_label`, etc.); AFTER values are the
pending edits. If a boundary fetch fails (404 or network error), the BEFORE cell
shows `—` gracefully. A `diff-field-before` class is added to the before-value cells
for optional distinct styling.

---

### F6: Cube address 0-vs-1-indexed inconsistency

**Files modified:**
- `frontend/src/routes/admin/DiffPreviewSheet.tsx`

**Commit:** `f24ff60`

**Applied fix:**
`cubeAddress()` now returns `${unit_id}/${row}/${col}` (raw 0-indexed values) instead
of `${unit_id}/${row+1}/${col+1}`. This matches `CubesGrid` (`{cube.unit_id}/{cube.row}/{cube.col}`)
and `CubeEditor` (`EDIT {unitId}/{rowNum}/{colNum}`). The mini-grid `aria-label`
was also updated from `Cube ${uid}/${r+1}/${c+1}` to `Cube ${uid}/${r}/${c}`.
The kiosk's A1–D4 letter scheme (`ShelfGrid`) is a different surface and was not
changed.

---

### F7: Phantom near-miss alert rendered under the wrong record

**Files modified:**
- `src/gruvax/api/admin/cubes.py`
- `frontend/src/api/types.ts`
- `frontend/src/routes/admin/CubeEditor.tsx`

**Commit:** `f24ff60`

**Applied fix:**
The validate endpoint (`POST /admin/cubes/validate`) now includes
`"phantom_field": "first" | "last"` in the phantom error result, indicating which
boundary record triggered the phantom check. This is determined by the existing
`not first_exists` / `not last_exists` logic already present in the endpoint.

`ValidateItem` TypeScript type extended with `phantom_field?: 'first' | 'last'`.

`CubeEditor.runValidation` now uses `item.phantom_field ?? 'first'` to determine
`PhantomWarning.field`, and sources the correct label/catalog for the warning from
the appropriate half of the form (`f.labelFirst`/`f.catalogFirst` vs
`f.labelLast`/`f.catalogLast`). Previously the heuristic always used `'first'` and
always sourced `f.labelFirst`/`f.catalogFirst`, so typing a phantom value into the
LAST RECORD catalog would show the alert and near-miss chips under FIRST RECORD.

---

## Test results

### Backend
```
uv run pytest tests/unit/test_pin.py tests/unit/test_sessions.py \
    tests/unit/test_boundary_validation.py tests/integration/test_admin_auth.py \
    tests/integration/test_boundary_editor.py tests/integration/test_change_set.py \
    tests/integration/test_cube_public.py -q

28 passed, 5 skipped, 11 warnings in 1.54s
```

### Lint + types
```
uv run ruff check src/gruvax   → All checks passed!
uv run mypy src/gruvax         → Success: no issues found in 36 source files
```

### Frontend
```
npx tsc --noEmit               → (no output — clean)
npm run build                  → ✓ built in 461ms
npx vitest run                 → 6 passed (1 test file)
```

---

---

## Security Follow-up Fixes (WR-06 + WR-05)

_Applied: 2026-05-21 — separate commit from the UAT F2–F7 batch above._

### WR-06: Login rate-limiter rebuilt on public `limits` API (no more slowapi private internals)

**Files modified:**
- `src/gruvax/api/admin/limiter.py`
- `src/gruvax/api/admin/login.py`
- `src/gruvax/app.py`
- `pyproject.toml`

**Commit:** `9f6e70b`

**Problem:** `_check_login_rate_limit()` in `login.py` reached into slowapi private
attributes — `limiter._key_prefix`, `limiter._limiter.hit(...)` — and imported
`slowapi.wrappers.Limit` to construct a wrapper used only for header injection.
Any slowapi upgrade could silently disable the brute-force guard.

**Fix:**

- **`limiter.py`** — replaced `slowapi.Limiter(key_func=get_remote_address)` with:
  - `limiter: MemoryStorage` — the shared in-process storage; `limiter.reset()` is called
    by the test fixture to clear state between tests.
  - `_rate_limiter: FixedWindowRateLimiter(limiter)` — the rate-limit strategy.
  - `_LOGIN_RATE = parse("5/5minutes")` — the parsed rate spec.

- **`login.py`** — `_check_login_rate_limit()` now:
  - Imports `_rate_limiter` and `_LOGIN_RATE` from `limiter.py` (public names).
  - Derives client IP via `request.client.host` (falls back to `"unknown"` if
    `request.client` is `None`).
  - Calls `_rate_limiter.hit(_LOGIN_RATE, "login", client_ip)`.
  - Raises `HTTPException(status_code=429, detail={"type": "rate_limited", "message": ...})`
    on breach — no slowapi exception handler required.
  - All slowapi imports (`RateLimitExceeded`, `get_remote_address`, `Limit`) removed.

- **`app.py`** — removed the entire slowapi wiring block:
  `from slowapi import _rate_limit_exceeded_handler`, `from slowapi.errors import RateLimitExceeded`,
  `app.state.limiter = admin_limiter`, and `app.add_exception_handler(...)`.
  The 429 is now a plain `HTTPException` that FastAPI handles natively.

- **`pyproject.toml`** — removed `slowapi>=0.1.9`; added `limits>=5.8` as a direct
  dependency (it was previously only transitive through slowapi).

**slowapi completely removed:** `grep -rn "slowapi" src/ pyproject.toml` returns only
prose comments — zero imports of any slowapi symbol anywhere in the codebase.

---

### WR-05: Rate-limit key proxy-awareness documented at derivation site

**Files modified (comments only):**
- `src/gruvax/api/admin/limiter.py`
- `src/gruvax/api/admin/login.py`

**Commit:** `9f6e70b` (same commit as WR-06)

**Problem:** The rate-limit key used the direct socket peer IP without any comment
explaining this assumption or its implication if a reverse proxy is added.

**Fix:** Added explicit comments at both the module level in `limiter.py` and at the
IP-derivation site in `login.py` (`_check_login_rate_limit()`):

> Rate-limit key is the direct socket peer IP (`request.client.host`), correct for
> GRUVAX's single-host home-LAN deployment with NO reverse proxy. If a proxy is
> introduced, configure trusted X-Forwarded-For / ProxyHeaders handling so the
> limit keys on the real client IP rather than the proxy.

No behavior change.

---

### Verification (WR-06 + WR-05)

```
uv run pytest tests/integration/test_admin_auth.py tests/unit/test_pin.py \
    tests/unit/test_sessions.py -q

16 passed, 7 warnings in 1.25s
```

The `test_rate_limit` test (6th login attempt → 429) passes, confirming the
`HTTPException(429)` path is exercised. The `reset_login_rate_limit` autouse
fixture calls `limiter.reset()` successfully against the new `MemoryStorage` singleton.

```
uv run ruff check src/gruvax   → All checks passed!
uv run mypy src/gruvax         → Success: no issues found in 36 source files
uv run python -c "import gruvax.app; print('OK')"  → OK
grep -rn "slowapi" src/ pyproject.toml  → only prose comments, no imports
```

---

_Fixed: 2026-05-21_
_Fixer: Claude (gsd-code-fixer)_

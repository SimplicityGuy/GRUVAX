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

_Fixed: 2026-05-21_
_Fixer: Claude (gsd-code-fixer)_

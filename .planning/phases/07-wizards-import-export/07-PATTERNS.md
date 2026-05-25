# Phase 7: Wizards + Import/Export — Pattern Map

**Mapped:** 2026-05-24
**Files analyzed:** 17 (7 new, 10 modified)
**Analogs found:** 17 / 17

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/gruvax/api/admin/export.py` | controller | request-response (read-only YAML) | `src/gruvax/api/admin/settings.py` | role-match |
| `src/gruvax/api/admin/import_.py` | controller | CRUD (file-upload → parse → validate → bulk write) | `src/gruvax/api/admin/cubes.py` | role-match |
| `src/gruvax/io/boundary_yaml.py` | utility | transform (Python to/from YAML) | `src/gruvax/api/admin/settings.py` (key-namespace pattern) | partial-match |
| `src/gruvax/io/boundary_csv.py` | utility | transform (CSV→internal) | `src/gruvax/api/admin/settings.py` (parse-then-validate) | partial-match |
| `migrations/versions/0007_wizard_source_labels.py` | migration | batch (ALTER TABLE CHECK) | `migrations/versions/0005_segment_model.py` | exact |
| `src/gruvax/api/admin/cubes.py` (EDIT) | controller | CRUD | self | exact (extend existing) |
| `src/gruvax/api/admin/router.py` (EDIT) | config | request-response | self | exact (register new routers) |
| `frontend/src/routes/admin/Wizard.tsx` | component | event-driven (step-walk + draft) | `frontend/src/routes/admin/Settings.tsx` | role-match |
| `frontend/src/routes/admin/Import.tsx` | component | request-response (upload + diff) | `frontend/src/routes/admin/HistoryView.tsx` | role-match |
| `frontend/src/routes/admin/ReshuffleBanner.tsx` | component | event-driven (store watch) | `frontend/src/routes/admin/AdminShell.tsx` | partial-match |
| `frontend/src/routes/admin/ConfirmationScreen.tsx` | component | request-response | `frontend/src/routes/admin/HistoryView.tsx` | role-match |
| `frontend/src/state/adminStore.ts` (EDIT) | store | event-driven (localStorage persist) | self | exact (extend existing) |
| `frontend/src/api/adminClient.ts` (EDIT) | service | request-response | self | exact (extend existing) |
| `frontend/src/routes/admin/HistoryView.tsx` (EDIT) | component | request-response | self | exact (extend badge map) |
| `frontend/src/routes/admin/AdminShell.tsx` (EDIT) | component | event-driven | self | exact (add nav tabs + banner mount) |
| `frontend/src/routes/admin/Settings.tsx` (EDIT) | component | request-response | self | exact (add BACKUP & RESTORE section) |
| `frontend/src/routes/admin/CubesGrid.tsx` (EDIT) | component | request-response | self | exact (add export button) |

---

## Pattern Assignments

### `src/gruvax/api/admin/export.py` (controller, request-response)

**Analog:** `src/gruvax/api/admin/settings.py`

**Imports pattern** (`settings.py` lines 1–32):
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response   # use Response, not JSONResponse

import yaml  # pyyaml already a dep

from gruvax.api.deps import get_pool, get_boundary_cache, require_admin
from gruvax.estimator.boundary_cache import BoundaryCache

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-export"])
```

**Auth/guard pattern** (`settings.py` lines 102–107):
```python
@router.get("/settings")
async def get_settings(
    request: Request,
    pool: Any = Depends(get_pool),
    _admin: dict[str, str] = Depends(require_admin),   # session-only, no CSRF (GET is read-only)
) -> dict[str, Any]:
```

**Core YAML-export pattern** (RESEARCH.md Pattern 6 / Code Examples section):
```python
@router.get("/export/boundaries.yaml")
async def export_boundaries(
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    _admin: dict = Depends(require_admin),
) -> Response:
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT unit_id, row, col, label, fraction FROM gruvax.segment_overrides"
        )
        override_rows = await cur.fetchall()

    overrides_index: dict[tuple, dict[str, float]] = {}
    for uid, r, c, lbl, frac in override_rows:
        overrides_index.setdefault((uid, r, c), {})[lbl] = float(frac)

    cubes = []
    for b in sorted(cache.get_boundaries(), key=lambda b: (b.unit_id, b.row, b.col)):
        entry = {"unit_id": b.unit_id, "row": b.row, "col": b.col, "is_empty": b.is_empty}
        if not b.is_empty:
            entry["first_label"] = b.first_label
            entry["first_catalog"] = b.first_catalog
            ovr = overrides_index.get((b.unit_id, b.row, b.col), {})
            if ovr:
                entry["overrides"] = dict(sorted(ovr.items()))
        cubes.append(entry)

    payload = yaml.dump(
        {"version": "1", "cubes": cubes},
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=True,
    )
    return Response(
        content=payload,
        media_type="application/x-yaml",
        headers={"Content-Disposition": 'attachment; filename="boundaries.yaml"'},
    )
```

**Settings-export pattern** — reads ONLY `_ALLOWED_SETTINGS_KEYS` (settings.py lines 39–58 + 102–120):
```python
@router.get("/export/settings.yaml")
async def export_settings(
    pool: Any = Depends(get_pool),
    _admin: dict = Depends(require_admin),
) -> Response:
    from gruvax.api.admin.settings import _ALLOWED_SETTINGS_KEYS
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT key, value FROM gruvax.settings WHERE key = ANY(%s)",
            (list(_ALLOWED_SETTINGS_KEYS),),  # auth.pin_hash NOT in this set (D-14)
        )
        rows = await cur.fetchall()
    # build nested YAML dict from flat key.subkey rows then:
    return Response(content=payload, media_type="application/x-yaml",
                    headers={"Content-Disposition": 'attachment; filename="settings.yaml"'})
```

**Error handling pattern** (`settings.py` lines 218–231):
```python
raise HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    detail={
        "type": "invalid_hex_color",
        "field": body_key,
        "message": f"Color value must be a valid #RRGGBB hex string. Got: {value!r}",
    },
)
```

---

### `src/gruvax/api/admin/import_.py` (controller, CRUD)

**Analog:** `src/gruvax/api/admin/cubes.py` (bulk_write_cubes + validate_boundary patterns)

**Imports pattern** (`cubes.py` lines 41–66):
```python
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from gruvax.api.deps import get_boundary_cache, get_pool, get_segment_cache, require_admin

import yaml  # yaml.safe_load ONLY (never yaml.load without Loader — security requirement)
import csv as _csv  # stdlib

logger = logging.getLogger(__name__)
router = APIRouter(tags=["admin-import"])
```

**File-upload + parse pattern** (RESEARCH.md Concrete Schemas section):
```python
@router.post("/import/boundaries")
async def import_boundaries(
    request: Request,
    file: UploadFile = File(...),
    pool: Any = Depends(get_pool),
    cache: BoundaryCache = Depends(get_boundary_cache),
    _admin: dict = Depends(require_admin),
) -> JSONResponse:
    content = await file.read()
    if len(content) > 100_000:   # 100 KB hard limit on upload size
        raise HTTPException(status_code=413, detail={"type": "file_too_large"})

    filename = file.filename or ""
    if filename.endswith(".yaml") or filename.endswith(".yml"):
        data = yaml.safe_load(content)   # safe_load enforced
        entries = _parse_yaml_boundaries(data)
    elif filename.endswith(".csv"):
        entries = _parse_csv_boundaries(content.decode())
    else:
        raise HTTPException(status_code=422, detail={"type": "unsupported_format"})
    # entries → list[BoundaryEdit] → call validate then bulk
```

**Settings-import pattern** — reuses existing validated PUT path (settings.py lines 171–313):
```python
@router.post("/import/settings")
async def import_settings(
    request: Request,
    file: UploadFile = File(...),
    pool: Any = Depends(get_pool),
    _admin: dict = Depends(require_admin),
) -> dict[str, Any]:
    from gruvax.api.admin.settings import _ALLOWED_SETTINGS_KEYS
    content = await file.read()
    data = yaml.safe_load(content)
    # Reject auth.* keys immediately (D-14 hard exclusion):
    for key in _flatten_yaml_keys(data):
        if key.startswith("auth."):
            raise HTTPException(status_code=422, detail={"type": "auth_key_rejected", "key": key})
        if key not in _ALLOWED_SETTINGS_KEYS:
            raise HTTPException(status_code=422, detail={"type": "unknown_key", "key": key})
    # Then call update_settings() internally with the validated payload
```

**Idempotency-key pattern** (`cubes.py` lines 710–715):
```python
idempotency_key = request.headers.get("Idempotency-Key")
if idempotency_key:
    cached = await check_idempotency(pool, idempotency_key)
    if cached is not None:
        return JSONResponse(content=cached)
```

**Atomic transaction + cache invalidate** (`cubes.py` lines 743–798):
```python
change_set_id = str(_uuid.uuid4())

async with pool.connection() as conn, conn.transaction():
    for edit in body.updates:
        prev = await fetch_current_boundary(conn, edit.unit_id, edit.row, edit.col)
        await write_boundary(conn, edit.unit_id, edit.row, edit.col,
                             new_first_label, new_first_catalog, edit.is_empty)
        await write_history_row(conn, change_set_id, edit.unit_id, edit.row, edit.col,
                                prev, new_first_label, new_first_catalog, edit.is_empty,
                                source=body.source)   # 'csv' | 'yaml'
    if idempotency_key:
        await store_idempotency(conn, idempotency_key, response_body)
    await cleanup_idempotency(conn)

# AFTER the with block exits (Pitfall A — never inside the transaction):
cache.invalidate()
await cache.load(pool)
```

---

### `src/gruvax/io/boundary_yaml.py` (utility, transform)

**Analog:** `src/gruvax/api/admin/settings.py` (key-namespace parsing + type coercion pattern)

**Internal cut-point model** (RESEARCH.md Concrete Schemas section):
```python
from dataclasses import dataclass

@dataclass
class CutPointEntry:
    unit_id: int
    row: int
    col: int
    first_label: str | None
    first_catalog: str | None
    is_empty: bool
    overrides: dict[str, float]  # label -> fraction; empty dict when not present
```

**Parse pattern** — mirrors settings.py coerce-by-type approach:
```python
def parse_yaml_boundaries(content: bytes | str) -> list[CutPointEntry]:
    """Parse YAML import file into CutPointEntry list. Uses yaml.safe_load only."""
    data = yaml.safe_load(content)
    if not isinstance(data, dict) or data.get("version") != "1":
        raise ValueError("Missing or unsupported version field")
    entries = []
    for cube in data.get("cubes", []):
        entries.append(CutPointEntry(
            unit_id=int(cube["unit_id"]),
            row=int(cube["row"]),
            col=int(cube["col"]),
            first_label=cube.get("first_label"),
            first_catalog=cube.get("first_catalog"),
            is_empty=bool(cube.get("is_empty", False)),
            overrides={str(k): float(v) for k, v in cube.get("overrides", {}).items()},
        ))
    return entries
```

**Serialize pattern** (RESEARCH.md Code Examples — YAML export):
```python
def serialize_boundaries_yaml(entries: list[CutPointEntry]) -> str:
    """Serialize to YAML with sorted keys for round-trip identity."""
    cubes = []
    for e in sorted(entries, key=lambda x: (x.unit_id, x.row, x.col)):
        cube: dict = {"unit_id": e.unit_id, "row": e.row, "col": e.col, "is_empty": e.is_empty}
        if not e.is_empty:
            cube["first_label"] = e.first_label
            cube["first_catalog"] = e.first_catalog
            if e.overrides:
                cube["overrides"] = dict(sorted(e.overrides.items()))
        cubes.append(cube)
    return yaml.dump({"version": "1", "cubes": cubes},
                     default_flow_style=False, allow_unicode=True, sort_keys=True)
```

---

### `src/gruvax/io/boundary_csv.py` (utility, transform)

**Analog:** `src/gruvax/api/admin/settings.py` (parse-and-validate, explicit key whitelist)

**CSV parse pattern** (RESEARCH.md Concrete Schemas — CSV Import Schema):
```python
import csv as _csv
import io

REQUIRED_HEADERS = {"unit_id", "row", "col", "first_label", "first_catalog", "is_empty"}

def parse_csv_boundaries(content: str) -> list[CutPointEntry]:
    """Parse flat CSV import file. Uses csv.DictReader (handles BOM, quoting)."""
    reader = _csv.DictReader(io.StringIO(content))
    if not REQUIRED_HEADERS.issubset(set(reader.fieldnames or [])):
        raise ValueError(f"CSV missing required headers. Expected: {REQUIRED_HEADERS}")
    entries = []
    for row in reader:
        is_empty = row["is_empty"].strip().lower() in ("true", "1", "yes")
        entries.append(CutPointEntry(
            unit_id=int(row["unit_id"]),
            row=int(row["row"]),
            col=int(row["col"]),
            first_label=row["first_label"].strip() or None,
            first_catalog=row["first_catalog"].strip() or None,
            is_empty=is_empty,
            overrides={},  # CSV carries no overrides (flat format)
        ))
    return entries
```

---

### `migrations/versions/0007_wizard_source_labels.py` (migration, batch)

**Analog:** `migrations/versions/0005_segment_model.py` (lines 63–75 and 108–116)

**Migration structure** — copy this shape exactly:
```python
"""Extend boundary_history.source CHECK for wizard/import source labels.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-24

Phase 7: Adds 'wizard', 'reshuffle', 'csv', 'yaml' to the source CHECK
constraint so wizard commits and imports appear with legible labels in
the History view (D-04).

Conventions (carried from 0001-0006):
- All DDL via op.execute() with explicit constraint/index names.
- downgrade() reverses back to the Phase 5 set (no data loss).
- alembic_version in public; search_path via connect listener (env.py).
"""

from __future__ import annotations
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE gruvax.boundary_history"
        " DROP CONSTRAINT IF EXISTS boundary_history_source_check"
    )
    op.execute("""
        ALTER TABLE gruvax.boundary_history
            ADD CONSTRAINT boundary_history_source_check
            CHECK (source IN (
                'manual', 'bulk', 'revert', 'cut_insert',
                'wizard', 'reshuffle', 'csv', 'yaml'
            ))
    """)


def downgrade() -> None:
    op.execute(
        "ALTER TABLE gruvax.boundary_history"
        " DROP CONSTRAINT IF EXISTS boundary_history_source_check"
    )
    op.execute("""
        ALTER TABLE gruvax.boundary_history
            ADD CONSTRAINT boundary_history_source_check
            CHECK (source IN ('manual', 'bulk', 'revert', 'cut_insert'))
    """)
```

---

### `src/gruvax/api/admin/cubes.py` — EDIT: add `source` field to `BulkWriteRequest`

**Analog:** Self — lines 113–124 (BulkWriteRequest) and lines 770–781 (write_history_row call)

**Minimal extension** (RESEARCH.md Pattern 1):
```python
# Lines 113–124 — ADD source field (default 'bulk' for backward compat):
class BulkWriteRequest(BaseModel):
    updates: list[BoundaryEdit]
    source: str = "bulk"  # NEW: 'bulk' | 'wizard' | 'reshuffle' | 'csv' | 'yaml'

# Lines ~780 — change the hardcoded source= to body.source:
await write_history_row(
    conn, change_set_id, edit.unit_id, edit.row, edit.col,
    prev, new_first_label, new_first_catalog, edit.is_empty,
    source=body.source,  # was: source="bulk"
)
```

---

### `src/gruvax/api/admin/router.py` — EDIT: register export + import routers

**Analog:** Self — lines 14–42

**Registration pattern** (`router.py` lines 24–41):
```python
def create_admin_router() -> APIRouter:
    # ... existing imports ...
    from gruvax.api.admin.export import router as export_router   # NEW
    from gruvax.api.admin.import_ import router as import_router  # NEW

    router = APIRouter(prefix="/admin", tags=["admin"])
    router.include_router(login_router)
    router.include_router(cubes_router)
    router.include_router(history_router)
    router.include_router(settings_router)
    router.include_router(editing_router)
    router.include_router(segments_router)
    router.include_router(labels_router)
    router.include_router(leds_router)
    router.include_router(export_router)   # NEW
    router.include_router(import_router)   # NEW
    return router
```

---

### `frontend/src/routes/admin/Wizard.tsx` (component, event-driven)

**Analog:** `frontend/src/routes/admin/Settings.tsx` (multi-section form, useState per field, async submit pattern)

**Imports pattern** (`Settings.tsx` lines 19–24):
```typescript
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useAdminStore } from '../../state/adminStore'
import { validateBoundary, adminBulkSave } from '../../api/adminClient'
import type { CubeBoundaryEdit } from '../../api/types'
import './admin.css'
```

**Two-mode state pattern** — mirrors Settings.tsx useState per concern:
```typescript
type WizardMode = 'setup' | 'reshuffle'
type WizardPhase = 'walking' | 'review' | 'committing' | 'done'

export function Wizard() {
  const navigate = useNavigate()
  const { reshuffleDraft, setReshuffleDraft } = useAdminStore()

  const [mode, setMode] = useState<WizardMode>(() =>
    reshuffleDraft ? 'reshuffle' : 'setup'
  )
  const [phase, setPhase] = useState<WizardPhase>('walking')
  const [currentStep, setCurrentStep] = useState(0)
  const [cuts, setCuts] = useState<Record<string, CutEntry>>(() =>
    reshuffleDraft?.cuts ?? {}
  )
  const [commitError, setCommitError] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
```

**Async commit pattern** (`Settings.tsx` lines ~130–175 pattern):
```typescript
async function handleCommit() {
  setIsSubmitting(true)
  setCommitError('')
  const idempKey = reshuffleDraft?.idempotencyKey ?? crypto.randomUUID()
  // Persist key before network call (retry safety — RESEARCH Pattern 4)
  setReshuffleDraft({ ...reshuffleDraft, idempotencyKey: idempKey })
  try {
    const updates = buildUpdatesFromCuts(cuts, mode)
    const result = await adminBulkSave(updates, idempKey, mode)
    setReshuffleDraft(null)   // clears localStorage draft (D-07)
    navigate(`/admin/history?highlight=${result.change_set_id}`)
  } catch (err) {
    setCommitError('Something went wrong checking your changes. Check your connection and try again.')
  } finally {
    setIsSubmitting(false)
  }
}
```

**JSX + className + data-* pattern** (HistoryView.tsx lines 136–180):
```tsx
return (
  <div className="wizard-route">
    <div className="wizard-mode-badge" data-mode={mode}>
      {mode === 'setup' ? 'SETUP' : 'RESHUFFLE'}
    </div>
    <div className="wizard-locator-header">
      {/* LocatorHeader reused with totalSteps, completedSteps props */}
    </div>
    <div className="wizard-progress-bar">
      <div className="wizard-progress-fill"
           style={{ width: `${(currentStep / totalSteps) * 100}%` }} />
    </div>
    {/* RecordPickerSheet trigger card for current step */}
  </div>
)
```

---

### `frontend/src/routes/admin/Import.tsx` (component, request-response)

**Analog:** `frontend/src/routes/admin/HistoryView.tsx` (async fetch + state machine + JSX list rendering)

**Imports pattern** (`HistoryView.tsx` lines 17–22):
```typescript
import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { validateBoundary, adminBulkSave } from '../../api/adminClient'
import type { CubeBoundaryEdit, ValidateResponse } from '../../api/types'
import './admin.css'
```

**State machine pattern** (`HistoryView.tsx` lines 42–65):
```typescript
type ImportPhase = 'idle' | 'validating' | 'validated' | 'committing' | 'done' | 'error'

interface ImportState {
  phase: ImportPhase
  file: File | null
  filename: string
  errors: ValidationError[]
  diff: MovementCount[]
  commitError: string
  idempotencyKey: string | null
}

export function Import() {
  const queryClient = useQueryClient()
  const [state, setState] = useState<ImportState>({
    phase: 'idle', file: null, filename: '', errors: [],
    diff: [], commitError: '', idempotencyKey: null,
  })
```

**Async validate-then-commit pattern** (mirrors HistoryView.tsx `handleRevert` at lines 80–103):
```typescript
async function handleFileSelect(file: File) {
  setState((prev) => ({ ...prev, file, filename: file.name, phase: 'validating', errors: [] }))
  try {
    const result = await uploadAndValidate(file)
    setState((prev) => ({ ...prev, phase: 'validated', errors: result.errors, diff: result.diff }))
  } catch {
    setState((prev) => ({ ...prev, phase: 'error', commitError: 'Validation failed.' }))
  }
}

async function handleCommit() {
  const key = state.idempotencyKey ?? crypto.randomUUID()
  setState((prev) => ({ ...prev, phase: 'committing', idempotencyKey: key }))
  try {
    const result = await adminImportCommit(state.file!, key)
    await queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    // navigate to confirmation screen with change_set_id
  } catch {
    setState((prev) => ({
      ...prev,
      phase: 'error',
      commitError: 'Import failed — check your connection. Your collection has not changed.',
    }))
  }
}
```

**JSX error card pattern** (HistoryView.tsx lines 152–180 — card + badge):
```tsx
{state.errors.map((err, i) => (
  <div key={i} className="import-error-card" data-error-type={err.type}>
    <div className="import-error-header">
      <span className="import-error-row">ROW {err.row}</span>
      <span className="import-error-badge">ERROR</span>
    </div>
    <p className="import-error-body">
      {/* Values via JSX string interpolation — textContent semantics (project constraint) */}
      {`"${err.first_label}" · "${err.first_catalog}" — not found in your collection.`}
    </p>
    {err.near_misses.length > 0 && (
      <div className="import-suggestion-row">
        <span className="import-suggestion-label">Did you mean?</span>
        {err.near_misses.map((miss) => (
          <button key={miss.label + miss.catalog}
                  className="import-suggestion-chip"
                  onClick={() => applyMiss(i, miss)}>
            {miss.label} · {miss.catalog}
          </button>
        ))}
      </div>
    )}
  </div>
))}
```

---

### `frontend/src/routes/admin/ReshuffleBanner.tsx` (component, event-driven)

**Analog:** `frontend/src/routes/admin/AdminShell.tsx` (store subscription + conditional render pattern)

**Store subscription + guard pattern** (`AdminShell.tsx` lines 36–40):
```typescript
import { useState } from 'react'
import { useAdminStore } from '../../state/adminStore'
import './admin.css'

export function ReshuffleBanner() {
  const { reshuffleDraft, setReshuffleDraft } = useAdminStore()
  const [confirming, setConfirming] = useState(false)

  if (!reshuffleDraft) return null   // renders nothing when no draft

  const startedAgo = formatRelativeTime(reshuffleDraft.startedAt)
  const stepsText = `${reshuffleDraft.completedSteps} OF ${totalCubes} STEPS DONE`
```

**Inline confirm pattern** — replaces content in-place (no modal, no navigate):
```tsx
{confirming ? (
  <div className="reshuffle-banner-confirm">
    <p className="reshuffle-banner-confirm-text">
      Are you sure? This will delete your in-progress reshuffle draft.
    </p>
    <button className="admin-btn admin-btn--destructive"
            onClick={() => { setReshuffleDraft(null); setConfirming(false) }}>
      YES, DISCARD
    </button>
    <button className="admin-btn admin-btn--outline"
            onClick={() => setConfirming(false)}>
      KEEP DRAFT
    </button>
  </div>
) : (
  /* Normal banner with CONTINUE / DISCARD buttons */
)}
```

---

### `frontend/src/routes/admin/ConfirmationScreen.tsx` (component, request-response)

**Analog:** `frontend/src/routes/admin/HistoryView.tsx` (change_set_id display, revert tap)

**Source-label map** — extends the HistoryView source label pattern (`HistoryView.tsx` lines 149–150):
```typescript
const SOURCE_HEADINGS: Record<string, string> = {
  wizard:    'BOUNDARIES COMMITTED',
  reshuffle: 'RESHUFFLE COMMITTED',
  csv:       'IMPORT COMMITTED',
  yaml:      'IMPORT COMMITTED',
}

const SOURCE_SUBLINES: Record<string, string> = {
  wizard:    'Operation: Wizard setup',
  reshuffle: 'Operation: Reshuffle',
  csv:       'Operation: CSV import',
  yaml:      'Operation: YAML import',
}
```

**change_set_id display + clipboard copy**:
```tsx
<div className="confirmation-changeset">
  <span className="confirmation-changeset-label">Change set</span>
  <span className="confirmation-changeset-id">
    {changeSetId}   {/* JSX text node — textContent semantics */}
  </span>
  <button className="confirmation-copy-btn"
          aria-label="Copy change set ID"
          onClick={() => { void navigator.clipboard.writeText(changeSetId); setCopied(true) }}>
    {/* Lucide Copy icon; swap to Lucide Check for 1500ms after tap */}
  </button>
</div>
```

**Revert tap** (reuses Phase 3 path, mirrors HistoryView.tsx lines 80–103):
```tsx
<button className="admin-btn admin-btn--outline"
        onClick={() => navigate(`/admin/history?highlight=${changeSetId}`)}>
  REVERT THIS CHANGE SET
</button>
```

---

### `frontend/src/state/adminStore.ts` — EDIT: add `reshuffleDraft` slice

**Analog:** Self — lines 44–64 (`pendingChangeSet` slice) and lines 97–104 (`partialize`)

**New interface additions** (`adminStore.ts` lines 20–64 pattern):
```typescript
interface ReshuffleDraft {
  mode: 'setup' | 'reshuffle'
  completedSteps: number
  cuts: Record<string, {          // key: `${unit_id}/${row}/${col}`
    first_label: string | null
    first_catalog: string | null
    is_empty: boolean
  }>
  idempotencyKey: string | null   // crypto.randomUUID(); persisted for retry
  startedAt: string               // ISO timestamp — for relative time display
}

// Add to AdminStore interface alongside pendingChangeSet:
reshuffleDraft: ReshuffleDraft | null
setReshuffleDraft: (draft: ReshuffleDraft | null) => void
```

**Zustand action pattern** (`adminStore.ts` lines 82–95):
```typescript
// Inside create<AdminStore>()(persist((set) => ({
reshuffleDraft: null,
setReshuffleDraft: (draft) => set({ reshuffleDraft: draft }),
```

**Partialize extension** (`adminStore.ts` lines 97–103):
```typescript
partialize: (state) => ({
  pendingChangeSet: state.pendingChangeSet,
  reshuffleDraft: state.reshuffleDraft,   // ADD alongside existing
}),
```

---

### `frontend/src/api/adminClient.ts` — EDIT: add wizard/import/export calls

**Analog:** Self — `adminBulkSave` (lines 266–289), `getHistory` (lines 291–297), `putAdminSettings` (lines 143–152)

**Bulk-save with source param** (extends `adminBulkSave` lines 266–289):
```typescript
export async function adminBulkSave(
  updates: CubeBoundaryEdit[],
  idempotencyKey: string,
  source: 'bulk' | 'wizard' | 'reshuffle' | 'csv' | 'yaml' = 'bulk',  // ADD
): Promise<CommitResponse> {
  const res = await adminFetch('/api/admin/cubes/bulk', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ updates, source }),   // source added to body
  })
  // ... existing error handling unchanged ...
}
```

**Export download pattern** — browser anchor trigger (avoids pop-up blockers, no external dep):
```typescript
export async function downloadBoundariesYaml(): Promise<void> {
  const res = await adminFetch('/api/admin/export/boundaries.yaml')
  if (!res.ok) throw new Error(`Export failed: ${res.status}`)
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'boundaries.yaml'
  a.click()
  URL.revokeObjectURL(url)
}
```

**File-upload pattern** (consistent with `adminFetch` CSRF pattern lines 52–77):
```typescript
export async function uploadImportBoundaries(
  file: File,
  idempotencyKey: string,
): Promise<CommitResponse> {
  const form = new FormData()
  form.append('file', file)
  // Content-Type header intentionally omitted — browser sets multipart boundary.
  // adminFetch injects X-CSRF-Token for POST automatically.
  const res = await adminFetch('/api/admin/import/boundaries', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: form,
  })
  if (!res.ok) {
    let errorType: string | undefined
    try { const b = await res.json(); errorType = typeof b.type === 'string' ? b.type : undefined }
    catch { /* ignore */ }
    throw new BulkSaveError(res.status, errorType)
  }
  return res.json() as Promise<CommitResponse>
}
```

**Error class reuse** — all new functions throw `BulkSaveError` (lines 599–610) for 400, `AuthError` for 401, `Error` otherwise.

---

### `frontend/src/routes/admin/HistoryView.tsx` — EDIT: extend source badge map

**Analog:** Self — lines 149–150 (sourceLabel derivation)

**Badge map extension** (current code at lines 149–150):
```typescript
// BEFORE (existing):
const sourceLabel = item.source === 'revert' ? 'UNDO' : 'EDIT'

// AFTER (Phase 7 extension):
const SOURCE_BADGE_MAP: Record<string, string> = {
  manual:     'EDIT',
  bulk:       'BULK EDIT',
  revert:     'UNDO',
  cut_insert: 'CUT EDIT',
  wizard:     'WIZARD SETUP',
  reshuffle:  'RESHUFFLE',
  csv:        'CSV IMPORT',
  yaml:       'YAML IMPORT',
}
const sourceLabel = SOURCE_BADGE_MAP[item.source] ?? item.source.toUpperCase()
```

**Badge data-attribute** (line 160 — already uses `data-source={item.source}` for CSS targeting):
```tsx
<span className="history-source-badge" data-source={item.source}>
  {sourceLabel}
</span>
```
CSS targets `[data-source="wizard"]` and `[data-source="reshuffle"]` for the yellow-tinted badge style (UI-SPEC Surface 5). No JSX change beyond the map.

---

### `frontend/src/routes/admin/AdminShell.tsx` — EDIT: add nav tabs + mount ReshuffleBanner

**Analog:** Self — lines 157–182 (nav tabs) and lines 149–156 (Outlet mount)

**Nav tab addition** (`AdminShell.tsx` lines 166–181):
```tsx
{/* Add after existing HISTORY NavLink: */}
<NavLink
  to="/admin/wizard"
  className={({ isActive }) =>
    `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
  }
>
  WIZARD
</NavLink>
<NavLink
  to="/admin/import"
  className={({ isActive }) =>
    `admin-nav-tab${isActive ? ' admin-nav-tab--active' : ''}`
  }
>
  IMPORT
</NavLink>
```

**ReshuffleBanner mount** — above Outlet inside the main content area:
```tsx
<main className="admin-main">
  <ReshuffleBanner />   {/* ADD — component returns null when no draft in store */}
  <Outlet />
</main>
```

---

### `frontend/src/routes/admin/Settings.tsx` — EDIT: add BACKUP & RESTORE section

**Analog:** Self — existing Phase 6 LEDs section (pattern: section heading + grouped action buttons)

**Section pattern** (copy existing Phase 6 section structure from lines ~300–450):
```tsx
<section className="settings-section" aria-labelledby="backup-restore-heading">
  <h2 id="backup-restore-heading" className="settings-section-heading">
    BACKUP &amp; RESTORE
  </h2>
  <div className="settings-backup-actions">
    <button className="admin-btn admin-btn--outline"
            onClick={() => void downloadBoundariesYaml()}>
      EXPORT BOUNDARIES
    </button>
    <button className="admin-btn admin-btn--outline"
            onClick={() => void downloadSettingsYaml()}>
      EXPORT SETTINGS
    </button>
  </div>
  {/* Settings import: label triggers hidden file input */}
  <label className="admin-btn admin-btn--outline" htmlFor="settings-import-input">
    IMPORT SETTINGS
  </label>
  <input id="settings-import-input" type="file" accept=".yaml,.yml"
         className="admin-file-input-hidden"
         onChange={(e) => {
           if (e.target.files?.[0]) void handleSettingsImport(e.target.files[0])
         }} />
  {/* Inline result: Space Grotesk 400 14px in --gruvax-success on success */}
</section>
```

---

## Shared Patterns

### Authentication / Guard
**Source:** `src/gruvax/api/admin/settings.py` lines 102–107 and `src/gruvax/api/admin/cubes.py` lines 145–149
**Apply to:** All new backend endpoints in `export.py`, `import_.py`

```python
# GET endpoints (export): session-only, no CSRF — GET is read-only
_admin: dict[str, str] = Depends(require_admin)

# POST/PUT endpoints (import): session + CSRF enforced inside require_admin
_admin: dict[str, str] = Depends(require_admin)
```

All new mutating endpoints import `require_admin` from `gruvax.api.deps`. The double-submit CSRF check lives inside `require_admin`; no additional work needed in endpoint bodies.

### CSRF on Frontend
**Source:** `frontend/src/api/adminClient.ts` lines 52–77 (`adminFetch`)
**Apply to:** All new frontend API calls in `adminClient.ts`

All calls route through `adminFetch`, which auto-attaches `X-CSRF-Token` for POST/PUT/DELETE. File-upload via `FormData` must omit `Content-Type` (browser sets multipart boundary) — `adminFetch` still injects the CSRF header correctly.

### Error Handling — Backend
**Source:** `src/gruvax/api/admin/settings.py` lines 218–231, `src/gruvax/api/admin/history.py` lines 104–107
**Apply to:** All new backend endpoints

```python
# Structured 422 pattern (input validation):
raise HTTPException(
    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    detail={"type": "invalid_hex_color", "field": key, "message": "..."},
)

# Structured 400 pattern (business rule violation):
return JSONResponse(
    status_code=status.HTTP_400_BAD_REQUEST,
    content={"type": "phantom_boundary", "message": "...", "near_misses": [...]},
)

# 404 pattern:
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail={"type": "change_set_not_found", "change_set_id": change_set_id},
)
```

### Error Handling — Frontend
**Source:** `frontend/src/api/adminClient.ts` lines 570–610 (`BulkSaveError`, `AuthError`)
**Apply to:** All new `adminClient.ts` functions

New functions: throw `BulkSaveError` on 400 (parse structured body), throw `AuthError` on 401, throw generic `Error` on other non-OK responses.

### Atomic Bulk Write + Cache Invalidate
**Source:** `src/gruvax/api/admin/cubes.py` lines 743–814
**Apply to:** `import_.py` boundary-import commit path

Full pattern: idempotency check-short-circuit → phantom validate loop → single `async with pool.connection() as conn, conn.transaction()` → write_boundary + write_history_row per cube → store_idempotency + cleanup_idempotency inside same transaction → `cache.invalidate()` + `cache.load(pool)` AFTER the `with` block (not inside it — Pitfall A).

### SQL Parameterization
**Source:** `src/gruvax/api/admin/history.py` line 25, `src/gruvax/api/admin/settings.py` line 17
**Apply to:** All new backend SQL in `export.py`, `import_.py`

All SQL uses `%s` placeholders — zero f-string interpolation. Required in every module docstring per established convention.

### DOM Build Constraint (Frontend)
**Source:** `frontend/src/routes/admin/RecordPickerSheet.tsx` lines 12–16
**Apply to:** All new frontend components

Project constraint from `boundary-editing.md` + `CLAUDE.md`: all user-supplied strings from API responses must be rendered via React JSX `{}` interpolation (textContent semantics). Never assign raw strings to DOM node properties directly. The `el()` + `replaceChildren()` helpers enforce this constraint in non-React code; in React components the equivalent is JSX-only string interpolation.

### Design Token Constraint
**Source:** `CLAUDE.md` Conventions section, `frontend/src/routes/admin/HistoryView.tsx` line 15
**Apply to:** All new TSX files, all admin CSS additions

No hardcoded hex values. All colors via CSS custom properties from `design/gruvax-design-tokens.css`: `--gruvax-blue`, `--gruvax-yellow`, `--gruvax-yellow-faint`, `--gruvax-off-white`, `--gruvax-error`, `--gruvax-success`, `--gruvax-warning`, etc.

### Logging Pattern
**Source:** `src/gruvax/api/admin/settings.py` lines 30, 288
**Apply to:** All new backend modules

```python
logger = logging.getLogger(__name__)  # module-level, __name__
logger.info("Admin import committed: %s", change_set_id)  # % formatting, not f-strings
# Never log PIN values or raw user-supplied input
```

---

## No Analog Found

All Phase 7 files have analogs in the existing codebase.

| File | Notes |
|------|-------|
| `src/gruvax/io/boundary_yaml.py` | YAML parse/dump via stdlib pyyaml; transform shape mirrors BoundaryEdit from cubes.py; no structural predecessor in the `io/` directory (it is new). |
| `src/gruvax/io/boundary_csv.py` | csv.DictReader via stdlib; parse-and-validate mirrors settings.py whitelist pattern; same note — `io/` directory is new. |

These are thin stdlib wrappers. Model their file structure on the type-annotated function convention used throughout the backend (no class required, functions at module scope, dataclass for the output type).

---

## Metadata

**Analog search scope:** `src/gruvax/api/admin/`, `migrations/versions/`, `frontend/src/routes/admin/`, `frontend/src/state/`, `frontend/src/api/`
**Files scanned:** 17 source files read directly
**Pattern extraction date:** 2026-05-24

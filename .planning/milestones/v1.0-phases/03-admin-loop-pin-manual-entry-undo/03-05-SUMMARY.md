---
phase: 03-admin-loop-pin-manual-entry-undo
plan: "05"
subsystem: admin-backend + admin-frontend
tags: [change-set, boundary-history, idempotency, conflict-revert, diff-preview, history-view]
dependency_graph:
  requires: ["03-01", "03-02", "03-04"]
  provides: ["atomic-bulk-commit", "conflict-aware-revert", "diff-preview-ui", "history-ui"]
  affects: ["boundary-cache", "cube-boundaries", "boundary-history", "idempotency-keys"]
tech_stack:
  added: []
  patterns:
    - "Atomic transaction with single change_set_id across all cubes"
    - "Idempotency-Key replay: cached response, no double-write (Pitfall 7)"
    - "Conflict detection via has_newer_changes before inverse write (D-12)"
    - "Pitfall A: cache.invalidate()+load() strictly AFTER transaction commit"
    - "append-only boundary_history with source IN ('manual','bulk','revert')"
    - "useEffect for validation dry-run on DiffPreviewSheet mount"
    - "TanStack Query invalidation after commit and revert"
key_files:
  created:
    - src/gruvax/api/admin/history.py
    - frontend/src/routes/admin/DiffPreviewSheet.tsx
    - frontend/src/routes/admin/HistoryView.tsx
  modified:
    - src/gruvax/api/admin/cubes.py
    - src/gruvax/api/admin/router.py
    - src/gruvax/db/queries.py
    - frontend/src/api/adminClient.ts
    - frontend/src/api/types.ts
    - frontend/src/routes/admin/CubeEditor.tsx
    - frontend/src/routes/admin/AdminShell.tsx
    - frontend/src/routes/admin/admin.css
    - frontend/src/App.tsx
decisions:
  - "DiffPreviewSheet runs as /admin/preview route (not a modal) — simpler routing for the kiosk's single-tab browser context"
  - "Idempotency-Key == pendingChangeSet.id (client-generated UUID at change-set creation time) — reuse on retries is automatic"
  - "History rows fetched via SELECT ... GROUP BY newest-first; cube-level detail deferred to a future expand-on-tap UX"
  - "DiffPreviewSheet calls validateBoundary on mount for movement counts; dry-run failures don't block commit"
metrics:
  duration: "~27 minutes"
  completed: "2026-05-20"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 9
---

# Phase 03 Plan 05: Admin Maintenance Loop — Diff Preview + Atomic Commit + Conflict-Aware Undo — Summary

Closed the full admin maintenance loop: atomic idempotent bulk commit to `boundary_history` with a shared `change_set_id`, cache reload after commit, and a conflict-aware revert that writes an undoable inverse change-set — plus the `DiffPreviewSheet` and `HistoryView` frontend components wired into the editor's commit flow.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Atomic bulk commit + idempotency + conflict-aware revert history endpoints | `7dc21c5` | cubes.py, history.py, router.py, queries.py |
| 2 | DiffPreviewSheet + HistoryView + commit/revert wiring | `8150078` | types.ts, adminClient.ts, DiffPreviewSheet.tsx, HistoryView.tsx, CubeEditor.tsx, AdminShell.tsx, admin.css, App.tsx |

## What Was Built

### Backend (Task 1)

**`POST /api/admin/cubes/bulk`** — atomic idempotent change-set commit:
- Idempotency-Key short-circuit at top: `check_idempotency(pool, key)` → return cached if seen before
- Pre-flight validation via the existing POS-01 comparator
- Single `async with pool.connection() as conn, conn.transaction():` for ALL cubes — no partial commits
- Per cube: `fetch_current_boundary` (reads prev_*) → `write_boundary` → `write_history_row(source='bulk')`
- `store_idempotency` + `cleanup_idempotency` (24h TTL, Pitfall E) inside transaction
- After transaction: `cache.invalidate(); await cache.load(pool)` (Pitfall A — never inside transaction)
- Returns `{change_set_id, applied}`

**`GET /api/admin/history`** — change-sets grouped by `change_set_id`, newest-first with source, changed_at, cube_count.

**`POST /api/admin/history/{change_set_id}/revert`** — conflict-aware inverse change-set:
- Fetches all history rows for the target change-set (404 if empty)
- Per cube: `has_newer_changes(conn, unit_id, row, col, original_changed_at)` → skip if conflict
- Non-conflicting cubes: restore prev_* to `cube_boundaries`, write new history row with `source='revert'`
- Entire non-conflicting set is atomic
- Returns `{change_set_id: new_id, reverted: [...], skipped: [...]}`
- Cache reloaded only if any cubes were actually reverted

**9 new query functions** added to `db/queries.py`:
`fetch_current_boundary`, `write_boundary`, `write_history_row`, `check_idempotency`, `store_idempotency`, `cleanup_idempotency`, `list_change_sets`, `fetch_change_set_rows`, `has_newer_changes` — all using `%s` placeholders, zero f-string SQL.

### Frontend (Task 2)

**`DiffPreviewSheet.tsx`** (`/admin/preview` route, UI-SPEC §E):
- Mini Kallax grid: changed cubes ringed in `var(--gruvax-blue)`, unchanged cubes dim
- Per-cube AFTER table showing new boundary values (label_first/catalog_first/label_last/catalog_last)
- Record movement counts from `validateBoundary` dry-run (fetched on mount via `useEffect`)
- Empty/overstuffed warnings from validate results
- "COMMIT CHANGE SET" primary button: calls `adminBulkSave(edits, idempotencyKey)`, invalidates `['admin','cubes']` cache, clears `pendingChangeSet` on success
- Success state: "Saved — change set {short-id}" checkmark, navigates back to `/admin/cubes` after 2 s
- "BACK TO EDITOR" text button: returns without committing

**`HistoryView.tsx`** (`/admin/history` route, UI-SPEC §F):
- `useQuery(['admin','history'], getHistory)` — change-set cards newest-first
- Card: short UUID + source badge (EDIT/UNDO) + timestamp + cube count
- "REVERT" button with inline destructive confirm: "Revert this change set? This will restore the previous boundary values as a new, undoable change." + REVERT / KEEP CHANGES buttons
- On revert success: REVERTED pill on the card; if skipped[] non-empty: conflict report banner "N cube(s) were skipped — changed since this edit..."
- Empty state: "No changes yet — Save your first boundary edit to see it here."

**Client additions** (`adminClient.ts`):
- `adminBulkSave(updates, idempotencyKey)` — POST with Idempotency-Key header
- `getHistory()` — GET /api/admin/history
- `revertChangeSet(changeSetId)` — POST /api/admin/history/{id}/revert

**Type additions** (`types.ts`): `CommitResponse`, `ChangeSetHistoryItem`, `HistoryResponse`, `RevertedCube`, `RevertResponse`

**CubeEditor.tsx**: "PREVIEW CHANGES" primary button appears when pendingChangeSet has edits → navigates to `/admin/preview`

**AdminShell.tsx**: HISTORY nav tab added linking to `/admin/history`

**App.tsx**: `/admin/preview` and `/admin/history` child routes registered

**admin.css**: ~260 lines of token-driven styles for DiffPreviewSheet (mini grid, detail cards, before/after table, warnings, committed state) and HistoryView (cards, REVERTED pill, conflict banner, confirm dialog)

## Security Threat Mitigations Implemented

| Threat ID | Mitigation |
|-----------|-----------|
| T-03-18 | `require_admin` (session + CSRF) on both `POST /cubes/bulk` and `POST /history/{id}/revert` |
| T-03-19 | Single DB transaction (all-or-nothing) + Idempotency-Key replay returns cached response |
| T-03-20 | Append-only `boundary_history` with prev/new values, source, changed_at per change-set |
| T-03-21 | `has_newer_changes` conflict check before writing inverse; skip+report, never silent clobber |
| T-03-22 | `invalidate()+load()` only after successful commit — failed transaction never empties cache |
| T-03-23 | 24h `cleanup_idempotency` DELETE on each bulk (indexed on created_at) |
| T-03-24 | All SQL uses `%s` placeholders; zero f-string interpolation confirmed by grep check |

## Verification Results

| Check | Result |
|-------|--------|
| `pytest tests/integration/test_change_set.py` | 5/5 PASS (test_bulk_writes_history, test_idempotency_key_replay, test_revert_writes_inverse, test_revert_conflict_skip, test_revert_is_undoable) |
| `pytest tests/unit/test_diff_preview.py` | 1/1 PASS |
| Full backend suite | 211 passed, 5 skipped |
| `ruff check src/gruvax/api/admin src/gruvax/db/queries.py` | All checks passed |
| `mypy src/gruvax/api/admin src/gruvax/db/queries.py` | Success: no issues |
| `tsc --noEmit` | 0 errors |
| `npm run build` | Built in 509ms (0 errors) |
| No hex colors in DiffPreviewSheet.tsx, HistoryView.tsx | PASS (grep returns empty) |

## Deviations from Plan

None — plan executed exactly as written. The `useState` → `useEffect` swap in DiffPreviewSheet for the validation dry-run fetch is an implicit correctness requirement (React Rules of Hooks), not a plan deviation.

## Known Stubs

None. All data flows are wired end-to-end:
- DiffPreviewSheet pulls boundary edits from `pendingChangeSet` (Zustand, localStorage-persisted)
- `adminBulkSave` writes to the DB via the backend; success clears `pendingChangeSet`
- HistoryView fetches from `GET /api/admin/history` — real DB data

## Human Verification Needed

The checkpoint in this plan is auto-approved (autonomous mode). A human should verify:

1. **Diff preview flow**: Log in, edit a cube boundary (ADD TO PENDING), confirm the "PREVIEW CHANGES" button appears, tap it. Verify the diff sheet shows the cube ringed on the mini grid, the AFTER boundary values, and any movement counts. Tap "COMMIT CHANGE SET" — confirm success state ("Saved — change set {id}") and that the kiosk grid reflects the new boundary on next load.

2. **Multi-cube change-set**: Edit two cubes in one session (both ADD TO PENDING), PREVIEW CHANGES, confirm both cubes appear in the diff. COMMIT — confirm History shows ONE change-set covering both cubes.

3. **History + revert**: Navigate to /admin/history. Confirm the change-set card appears with correct timestamp and cube count. Tap REVERT, confirm the destructive confirm dialog appears ("Revert this change set? This will restore..."). Confirm REVERT, verify the REVERTED pill appears and boundaries are restored AND a new revert change-set appears (undoable).

4. **Conflict revert**: Commit change-set A (edits cube B1). Then edit cube B1 again (commit change-set B). Go to History, try to REVERT change-set A. Confirm the conflict banner appears: "1 cube(s) were skipped — changed since this edit and not reverted: 1/2/1." (or similar) — no silent clobber.

5. **Idempotency**: Submit the same pending change-set twice rapidly (simulate by direct API call with the same Idempotency-Key). Confirm only ONE history entry appears, not two.

6. **Back to editor**: On the diff preview sheet, tap "BACK TO EDITOR". Confirm navigation returns to the editor without committing (pendingChangeSet is still present).

## Threat Flags

No new security-relevant surface introduced beyond what the plan's `<threat_model>` covers. All new endpoints are guarded by `require_admin`.

## Self-Check: PASSED

- `src/gruvax/api/admin/history.py` — FOUND
- `frontend/src/routes/admin/DiffPreviewSheet.tsx` — FOUND
- `frontend/src/routes/admin/HistoryView.tsx` — FOUND
- Commit `7dc21c5` — FOUND (feat(03-05): atomic bulk commit...)
- Commit `8150078` — FOUND (feat(03-05): DiffPreviewSheet + HistoryView...)
- All 6 `test_change_set.py` tests GREEN — CONFIRMED
- `tsc --noEmit` 0 errors — CONFIRMED
- `npm run build` succeeded — CONFIRMED

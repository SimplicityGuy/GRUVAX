/**
 * DiffPreviewSheet — pre-commit review panel (UI-SPEC §E, ADMN-07).
 *
 * Shows:
 *  - Mini Kallax grid: changed cubes ringed in --gruvax-blue; unchanged dim.
 *  - Per-cube BEFORE / AFTER boundary-value table with record-movement counts.
 *  - Empty/overstuffed warnings derived from the validate dry-run.
 *  - "COMMIT CHANGE SET" primary button: calls adminBulkSave with an
 *    Idempotency-Key, clears pendingChangeSet on success, invalidates the
 *    ['admin','cubes'] TanStack Query cache.
 *  - "BACK TO EDITOR" secondary text button: returns without committing.
 *
 * On commit success: shows "Saved — change set {short-id}" checkmark for 2 s,
 * then navigates back to /admin/cubes.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { BulkSaveError, adminBulkSave, adminGetCubeBoundary, validateBoundary } from '../../api/adminClient'
import { useAdminStore } from '../../state/adminStore'
import { RollbackToast } from './RollbackToast'
import type { AdminCubeBoundary, CubeBoundaryEdit, ValidateItem } from '../../api/types'

/** Format cube address for display.
 *
 * Uses 0-indexed row/col to match CubesGrid and CubeEditor (F6 fix).
 * The kiosk A1–D4 letter scheme is a separate surface — do not use it here.
 */
function cubeAddress(unit_id: number, row: number, col: number): string {
  return `${unit_id}/${row}/${col}`
}

/** One row in the diff table. */
interface DiffRow {
  edit: CubeBoundaryEdit
  validateResult?: ValidateItem
}

export function DiffPreviewSheet() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { pendingChangeSet, setPendingChangeSet } = useAdminStore()

  const [committedId, setCommittedId] = useState<string | null>(null)
  /** Toast visible after a rollback (D-07). */
  const [showRollbackToast, setShowRollbackToast] = useState(false)

  // Validate results fetched on mount for movement counts / warnings
  const [validateResults, setValidateResults] = useState<ValidateItem[]>([])
  const [isValidating, setIsValidating] = useState(false)
  // True when the dry-run found any invalid cubes (order or phantom errors)
  const [hasValidationErrors, setHasValidationErrors] = useState(false)
  const [validateErrorMessage, setValidateErrorMessage] = useState<string | null>(null)

  // Before-state for each edited cube (keyed by "unit_id-row-col")
  const [beforeBoundaries, setBeforeBoundaries] = useState<Map<string, AdminCubeBoundary>>(
    new Map(),
  )

  // Fetch validation + current boundaries once on mount (dry-run — no DB write)
  useEffect(() => {
    if (!pendingChangeSet || pendingChangeSet.edits.length === 0) return

    const editsSnap = pendingChangeSet.edits

    // Extract effect body into a local async function so setIsValidating(true)
    // runs inside the async function body (not as a synchronous in-effect setState).
    async function runMountValidation() {
      setIsValidating(true)

      // Run validate + per-cube boundary fetches in parallel
      const validatePromise = validateBoundary(editsSnap)
      const boundaryPromises = editsSnap.map((edit) =>
        adminGetCubeBoundary(edit.unit_id, edit.row, edit.col).then((b) => ({
          key: `${edit.unit_id}-${edit.row}-${edit.col}`,
          boundary: b,
        })).catch(() => null)
      )

      try {
        const [validateRes, boundaryResults] = await Promise.all([validatePromise, Promise.all(boundaryPromises)])
        setValidateResults(validateRes.results)
        // Surface any validation errors so the COMMIT button can be disabled/warned
        const invalid = validateRes.results.filter((r) => !r.valid)
        if (invalid.length > 0) {
          setHasValidationErrors(true)
          const firstError = invalid[0]
          setValidateErrorMessage(
            firstError.message ?? firstError.error ?? 'One or more cubes have validation errors.',
          )
        } else {
          setHasValidationErrors(false)
          setValidateErrorMessage(null)
        }

        // Populate before-state map
        const map = new Map<string, AdminCubeBoundary>()
        for (const result of boundaryResults) {
          if (result) {
            map.set(result.key, result.boundary)
          }
        }
        setBeforeBoundaries(map)
      } catch {
        // CR review WR-02: the dry-run validation could not complete (network /
        // server error). Fail SAFE — guard the commit and warn the user rather
        // than silently leaving the button enabled with unverified changes.
        setHasValidationErrors(true)
        setValidateErrorMessage(
          "Couldn't check these changes against the collection. Try again before saving.",
        )
      } finally {
        setIsValidating(false)
      }
    }

    void runMountValidation()
    // Only run on mount — pendingChangeSet identity does not change during preview
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  /**
   * Optimistic commit mutation (RTM-03, D-07, D-08).
   *
   * onMutate: snapshot + optimistic setQueryData on admin keys only (D-08).
   * onError:  restore snapshot + show RollbackToast; pendingChangeSet NOT cleared
   *           (D-07 — values retained for retry).
   * onSuccess: clear pendingChangeSet, invalidate admin history.
   * onSettled: invalidate ['admin','cubes'] — NEVER kiosk keys (D-08).
   *            Kiosk updates only on committed boundary_changed SSE (Plan 01).
   */
  const commitMutation = useMutation({
    mutationFn: ({
      edits: e,
      idempotencyKey: ik,
    }: {
      edits: CubeBoundaryEdit[]
      idempotencyKey: string
    }) => adminBulkSave(e, ik),

    onMutate: async ({ edits: e }) => {
      // Cancel any in-flight refetches so they don't overwrite our optimistic update
      await queryClient.cancelQueries({ queryKey: ['admin', 'cubes'] })

      // Snapshot the previous admin cubes data for rollback
      const previousAdminCubes = queryClient.getQueryData(['admin', 'cubes'])

      // Optimistic update: reflect edits on admin cubes query (admin keys only — D-08)
      queryClient.setQueryData(
        ['admin', 'cubes'],
        (old: unknown) => {
          if (!old || typeof old !== 'object') return old
          return { ...(old as object), _optimistic: true, edits: e }
        },
      )

      return { previousAdminCubes }
    },

    onError: (_err, _vars, context) => {
      // Restore the admin cubes snapshot (rollback the optimistic update)
      if (context?.previousAdminCubes !== undefined) {
        queryClient.setQueryData(['admin', 'cubes'], context.previousAdminCubes)
      }
      // Show the plain-language rollback toast (D-07 — locked copy)
      setShowRollbackToast(true)
      // pendingChangeSet is intentionally NOT cleared here (D-07 — values retained for retry)
    },

    onSuccess: (result) => {
      setCommittedId(result.change_set_id)
      // Clear the pending change-set on success (only on success, not on error)
      setPendingChangeSet(null)
      // Invalidate admin history so it reflects the new change-set
      void queryClient.invalidateQueries({ queryKey: ['admin', 'history'] })
      // Navigate back to cubes grid after 2s
      setTimeout(() => {
        void navigate('/admin/cubes')
      }, 2000)
    },

    onSettled: () => {
      // Always re-sync admin cubes after settle (success or error)
      void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
      // NEVER invalidate kiosk keys here (D-08, T-04-10):
      //   ['cubes'] and ['cube-contents'] are NOT invalidated.
      //   The kiosk learns of committed changes via boundary_changed SSE (Plan 01).
    },
  })

  if (!pendingChangeSet || pendingChangeSet.edits.length === 0) {
    return (
      <div className="diff-sheet-empty">
        <p className="diff-sheet-empty-text">No pending changes to preview.</p>
        <button
          type="button"
          className="editor-btn-secondary"
          onClick={() => void navigate('/admin/cubes')}
        >
          BACK TO CUBES
        </button>
      </div>
    )
  }

  const edits = pendingChangeSet.edits
  const idempotencyKey = pendingChangeSet.id  // client-generated UUID per change-set

  const diffRows: DiffRow[] = edits.map((edit) => ({
    edit,
    validateResult: validateResults.find(
      (r) => r.unit_id === edit.unit_id && r.row === edit.row && r.col === edit.col,
    ),
  }))

  function handleCommit() {
    commitMutation.mutate({ edits, idempotencyKey })
  }

  const isCommitting = commitMutation.isPending
  const commitError = commitMutation.isError
    ? (commitMutation.error instanceof BulkSaveError && commitMutation.error.serverMessage
        ? commitMutation.error.serverMessage
        : 'Could not save — check your connection and try again.')
    : null

  // Derive the unique units present in this change-set for mini-grid
  const unitIds = [...new Set(edits.map((e) => e.unit_id))].sort()

  return (
    <div className="diff-sheet">
      {/* Header */}
      <header className="diff-sheet-header">
        <h1 className="diff-sheet-heading">REVIEW CHANGES</h1>
        <p className="diff-sheet-subheading">
          {edits.length} cube{edits.length !== 1 ? 's' : ''} will be updated
        </p>
      </header>

      {/* Mini grid: one row per unit, changed cubes ringed */}
      <section className="diff-mini-grid-section" aria-label="Changed cubes">
        {unitIds.map((uid) => {
          const unitEdits = edits.filter((e) => e.unit_id === uid)
          // Determine grid dimensions from edits (assume 4×4 Kallax)
          const ROWS = 4
          const COLS = 4
          const editKeys = new Set(unitEdits.map((e) => `${e.row}-${e.col}`))

          return (
            <div key={uid} className="diff-mini-unit">
              <span className="diff-mini-unit-label">UNIT {uid}</span>
              <div
                className="diff-mini-grid"
                style={{ gridTemplateColumns: `repeat(${COLS}, 1fr)` }}
                aria-label={`Unit ${uid} boundary grid`}
              >
                {Array.from({ length: ROWS }, (_, r) =>
                  Array.from({ length: COLS }, (_, c) => {
                    const changed = editKeys.has(`${r}-${c}`)
                    return (
                      <div
                        key={`${r}-${c}`}
                        className={`diff-mini-cell${changed ? ' diff-mini-cell--changed' : ''}`}
                        aria-label={changed ? `Cube ${uid}/${r}/${c} — changed` : undefined}
                      />
                    )
                  })
                )}
              </div>
            </div>
          )
        })}
      </section>

      {/* Per-cube before/after table */}
      {isValidating ? (
        <p className="diff-sheet-validating" aria-live="polite">Checking movement counts...</p>
      ) : (
        <section className="diff-detail-section" aria-label="Boundary changes">
          {diffRows.map(({ edit, validateResult }) => {
            // movement_counts is a list on the wire (CR-03): use [0] for the single-cube case
            const moveCounts = validateResult?.movement_counts ?? []
            const mc = moveCounts[0]
            // WR-05: prefer the canonical is_empty flag; fall back to the field
            // check only when the edit doesn't carry it (editor-created edits).
            const isEmpty = edit.is_empty ?? (!edit.last_label && !edit.last_catalog)
            // CR-03: use the server-computed fill level (records_after / nominal
            // capacity). The old `records_after > records_before*1.1 + 1` heuristic
            // fired a false positive for empty cubes (threshold 1 → any 2+ records).
            const isOverstuffed = mc ? mc.fill_level_after > 1.0 : false

            // Before-state: fetched from GET /boundary on mount (F5)
            const beforeKey = `${edit.unit_id}-${edit.row}-${edit.col}`
            const before = beforeBoundaries.get(beforeKey)

            return (
              <div key={`${edit.unit_id}-${edit.row}-${edit.col}`} className="diff-cube-card">
                <div className="diff-cube-address">
                  {cubeAddress(edit.unit_id, edit.row, edit.col)}
                </div>

                {/* Before / After table — field names match backend (CR-01) */}
                <table className="diff-before-after-table" aria-label={`Changes for cube ${cubeAddress(edit.unit_id, edit.row, edit.col)}`}>
                  <thead>
                    <tr>
                      <th className="diff-col-label">FIELD</th>
                      <th className="diff-col-label">BEFORE</th>
                      <th className="diff-col-label">AFTER</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="diff-field-label">FIRST LABEL</td>
                      <td className="diff-field-value diff-field-before">{before?.first_label || '—'}</td>
                      <td className="diff-field-value">{edit.first_label || '—'}</td>
                    </tr>
                    <tr>
                      <td className="diff-field-label">FIRST CATALOG</td>
                      <td className="diff-field-value diff-field-before">{before?.first_catalog || '—'}</td>
                      <td className="diff-field-value">{edit.first_catalog || '—'}</td>
                    </tr>
                    <tr>
                      <td className="diff-field-label">LAST LABEL</td>
                      <td className="diff-field-value diff-field-before">{before?.last_label || '—'}</td>
                      <td className="diff-field-value">{edit.last_label || '—'}</td>
                    </tr>
                    <tr>
                      <td className="diff-field-label">LAST CATALOG</td>
                      <td className="diff-field-value diff-field-before">{before?.last_catalog || '—'}</td>
                      <td className="diff-field-value">{edit.last_catalog || '—'}</td>
                    </tr>
                  </tbody>
                </table>

                {/* Record movement counts — iterate the list (CR-03) */}
                {moveCounts.map((moveItem, i) => (
                  <p key={i} className="diff-movement-count">
                    Records: {moveItem.records_before} → {moveItem.records_after}
                    {moveItem.records_after > moveItem.records_before
                      ? ` (+${moveItem.records_after - moveItem.records_before})`
                      : moveItem.records_after < moveItem.records_before
                        ? ` (${moveItem.records_after - moveItem.records_before})`
                        : ' (no change)'}
                  </p>
                ))}

                {/* Warnings */}
                {isEmpty && (
                  <div className="diff-warning diff-warning--empty" role="alert">
                    <span aria-hidden="true">!</span>
                    This cube will become empty.
                  </div>
                )}
                {isOverstuffed && (
                  <div className="diff-warning diff-warning--overstuffed" role="alert">
                    <span aria-hidden="true">!</span>
                    This cube may exceed nominal capacity.
                  </div>
                )}
              </div>
            )
          })}
        </section>
      )}

      {/* Actions */}
      <div className="diff-sheet-actions">
        {committedId ? (
          <div className="diff-committed-state" role="status" aria-live="polite">
            <span className="diff-committed-check" aria-hidden="true">✓</span>
            <span className="diff-committed-text">
              Saved — change set {committedId.slice(0, 8)}
            </span>
          </div>
        ) : (
          <>
            {validateErrorMessage && (
              <div className="diff-validate-error" role="alert">
                <span aria-hidden="true">!</span>
                {validateErrorMessage} Fix the issue in the editor before committing.
              </div>
            )}
            {commitError && (
              <p className="diff-commit-error" role="alert">
                {commitError}
              </p>
            )}
            <button
              type="button"
              className="editor-btn-primary"
              onClick={() => void handleCommit()}
              disabled={isCommitting || isValidating || hasValidationErrors}
              aria-busy={isCommitting}
            >
              {isCommitting ? 'COMMITTING...' : 'COMMIT CHANGE SET'}
            </button>
            <button
              type="button"
              className="diff-back-btn"
              onClick={() => void navigate(-1)}
              disabled={isCommitting}
            >
              BACK TO EDITOR
            </button>
          </>
        )}
      </div>

      {/* Rollback toast — shown on error; pendingChangeSet NOT cleared (D-07) */}
      {showRollbackToast && (
        <RollbackToast
          message="Couldn't save that change — reverted."
          onDismiss={() => setShowRollbackToast(false)}
        />
      )}
    </div>
  )
}

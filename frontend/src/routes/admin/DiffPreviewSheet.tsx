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
import { useQueryClient } from '@tanstack/react-query'
import { adminBulkSave, validateBoundary } from '../../api/adminClient'
import { useAdminStore } from '../../state/adminStore'
import type { CubeBoundaryEdit, ValidateItem } from '../../api/types'

/** Format cube address for display. Row and col are 0-indexed; display as 1-indexed. */
function cubeAddress(unit_id: number, row: number, col: number): string {
  return `${unit_id}/${row + 1}/${col + 1}`
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

  const [isCommitting, setIsCommitting] = useState(false)
  const [commitError, setCommitError] = useState<string | null>(null)
  const [committedId, setCommittedId] = useState<string | null>(null)

  // Validate results fetched on mount for movement counts / warnings
  const [validateResults, setValidateResults] = useState<ValidateItem[]>([])
  const [isValidating, setIsValidating] = useState(false)

  // Fetch validation data once on mount (dry-run — no DB write)
  useEffect(() => {
    if (!pendingChangeSet || pendingChangeSet.edits.length === 0) return
    setIsValidating(true)
    void validateBoundary(pendingChangeSet.edits).then((res) => {
      setValidateResults(res.results)
      setIsValidating(false)
    }).catch(() => {
      setIsValidating(false)
    })
    // Only run on mount — pendingChangeSet identity does not change during preview
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

  async function handleCommit() {
    setIsCommitting(true)
    setCommitError(null)
    try {
      const result = await adminBulkSave(edits, idempotencyKey)
      // Invalidate the admin cubes cache so the grid reflects the new boundaries
      await queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
      setCommittedId(result.change_set_id)
      // Clear the pending change-set on success
      setPendingChangeSet(null)
      // Navigate back to cubes grid after 2 s
      setTimeout(() => {
        void navigate('/admin/cubes')
      }, 2000)
    } catch {
      setCommitError('Could not save — check your connection and try again.')
    } finally {
      setIsCommitting(false)
    }
  }

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
                        aria-label={changed ? `Cube ${uid}/${r + 1}/${c + 1} — changed` : undefined}
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
            const isEmpty = !edit.last_label && !edit.last_catalog
            const isOverstuffed = mc
              ? mc.records_after > (mc.records_before * 1.1 + 1)
              : false

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
                      <th className="diff-col-label">AFTER</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="diff-field-label">FIRST LABEL</td>
                      <td className="diff-field-value">{edit.first_label || '—'}</td>
                    </tr>
                    <tr>
                      <td className="diff-field-label">FIRST CATALOG</td>
                      <td className="diff-field-value">{edit.first_catalog || '—'}</td>
                    </tr>
                    <tr>
                      <td className="diff-field-label">LAST LABEL</td>
                      <td className="diff-field-value">{edit.last_label || '—'}</td>
                    </tr>
                    <tr>
                      <td className="diff-field-label">LAST CATALOG</td>
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
            {commitError && (
              <p className="diff-commit-error" role="alert">
                {commitError}
              </p>
            )}
            <button
              type="button"
              className="editor-btn-primary"
              onClick={() => void handleCommit()}
              disabled={isCommitting || isValidating}
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
    </div>
  )
}

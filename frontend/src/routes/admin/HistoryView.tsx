/**
 * HistoryView — change-set list with one-tap conflict-aware revert (UI-SPEC §F, ADMN-09).
 *
 * Fetches GET /api/admin/history via TanStack Query.
 * Renders change-set cards newest-first: short UUID + timestamp + cube count.
 * Each card has a "REVERT" action with a destructive confirm dialog.
 * On revert:
 *   - Calls revertChangeSet(changeSetId)
 *   - Shows a "REVERTED" pill on the card
 *   - If skipped[] is non-empty: shows a conflict report banner
 *   - Invalidates ['admin','history'] + ['admin','cubes'] query caches
 *
 * Empty state: "No changes yet — Save your first boundary edit to see it here."
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getHistory, revertChangeSet } from '../../api/adminClient'
import type { ChangeSetHistoryItem, RevertedCube } from '../../api/types'

/** Format ISO-8601 string to a human-readable local timestamp. */
function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

/** Format cube ref for display. */
function formatCubeRef(cube: RevertedCube): string {
  return `${cube.unit_id}/${cube.row + 1}/${cube.col + 1}`
}

interface RevertState {
  /** null = no confirm open, string = confirm open for that change_set_id */
  confirmingId: string | null
  /** IDs that have been successfully reverted in this session */
  revertedIds: Set<string>
  /** skipped cubes keyed by change_set_id of the original (now-reverted) set */
  skippedByOriginalId: Record<string, RevertedCube[]>
  /** error message keyed by change_set_id */
  errorById: Record<string, string>
  /** loading flag keyed by change_set_id */
  loadingId: string | null
}

export function HistoryView() {
  const queryClient = useQueryClient()

  const [revertState, setRevertState] = useState<RevertState>({
    confirmingId: null,
    revertedIds: new Set(),
    skippedByOriginalId: {},
    errorById: {},
    loadingId: null,
  })

  const { data, isLoading, isError } = useQuery({
    queryKey: ['admin', 'history'],
    queryFn: () => getHistory().then((r) => r.history),
    refetchOnWindowFocus: false,
  })

  function openConfirm(changeSetId: string) {
    setRevertState((prev) => ({ ...prev, confirmingId: changeSetId, errorById: {} }))
  }

  function closeConfirm() {
    setRevertState((prev) => ({ ...prev, confirmingId: null }))
  }

  async function handleRevert(changeSetId: string) {
    setRevertState((prev) => ({ ...prev, loadingId: changeSetId, confirmingId: null }))
    try {
      const result = await revertChangeSet(changeSetId)
      // Invalidate both history + cubes caches
      await queryClient.invalidateQueries({ queryKey: ['admin', 'history'] })
      await queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })

      setRevertState((prev) => ({
        ...prev,
        loadingId: null,
        revertedIds: new Set([...prev.revertedIds, changeSetId]),
        skippedByOriginalId: result.skipped.length > 0
          ? { ...prev.skippedByOriginalId, [changeSetId]: result.skipped }
          : prev.skippedByOriginalId,
      }))
    } catch {
      setRevertState((prev) => ({
        ...prev,
        loadingId: null,
        errorById: { ...prev.errorById, [changeSetId]: 'Revert failed — check your connection.' },
      }))
    }
  }

  if (isLoading) {
    return (
      <div className="history-view">
        <p className="history-loading" aria-live="polite">Loading history...</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="history-view">
        <p className="history-error" role="alert">Failed to load history. Try refreshing.</p>
      </div>
    )
  }

  const items: ChangeSetHistoryItem[] = data ?? []

  if (items.length === 0) {
    return (
      <div className="history-view">
        <div className="history-empty">
          <h2 className="history-empty-heading">No changes yet</h2>
          <p className="history-empty-body">
            Save your first boundary edit to see it here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="history-view">
      <header className="history-header">
        <h1 className="history-heading">CHANGE HISTORY</h1>
        <p className="history-subheading">{items.length} change set{items.length !== 1 ? 's' : ''}</p>
      </header>

      <ul className="history-list" role="list" aria-label="Change sets">
        {items.map((item) => {
          const isReverted = revertState.revertedIds.has(item.change_set_id)
          const skipped = revertState.skippedByOriginalId[item.change_set_id] ?? []
          const revertError = revertState.errorById[item.change_set_id]
          const isLoading = revertState.loadingId === item.change_set_id
          const isConfirming = revertState.confirmingId === item.change_set_id
          const sourceLabel = item.source === 'revert' ? 'UNDO' : 'EDIT'

          return (
            <li key={item.change_set_id} className="history-card">
              <div className="history-card-header">
                <div className="history-card-meta">
                  <span className="history-change-set-id">
                    {item.change_set_id.slice(0, 8)}
                  </span>
                  <span className="history-source-badge" data-source={item.source}>
                    {sourceLabel}
                  </span>
                  {isReverted && (
                    <span className="history-reverted-pill" aria-label="This change set has been reverted">
                      REVERTED
                    </span>
                  )}
                </div>
                <div className="history-card-right">
                  <span className="history-timestamp">
                    {formatTimestamp(item.changed_at)}
                  </span>
                  <span className="history-cube-count">
                    {item.cube_count} cube{item.cube_count !== 1 ? 's' : ''}
                  </span>
                </div>
              </div>

              {/* Conflict report banner (after revert with skips) */}
              {skipped.length > 0 && (
                <div className="history-conflict-banner" role="alert" aria-live="polite">
                  {skipped.length} cube{skipped.length !== 1 ? 's' : ''} were skipped
                  — changed since this edit and not reverted:
                  {' '}{skipped.map(formatCubeRef).join(', ')}.
                </div>
              )}

              {/* Error message */}
              {revertError && (
                <p className="history-revert-error" role="alert">
                  {revertError}
                </p>
              )}

              {/* Revert action */}
              {!isReverted && (
                <div className="history-card-actions">
                  {!isConfirming ? (
                    <button
                      type="button"
                      className="history-revert-btn"
                      onClick={() => openConfirm(item.change_set_id)}
                      disabled={isLoading}
                      aria-busy={isLoading}
                    >
                      {isLoading ? 'REVERTING...' : 'REVERT'}
                    </button>
                  ) : (
                    <div className="history-confirm-row" role="dialog" aria-label="Confirm revert">
                      <p className="history-confirm-copy">
                        Revert this change set? This will restore the previous boundary
                        values as a new, undoable change.
                      </p>
                      <div className="history-confirm-buttons">
                        <button
                          type="button"
                          className="history-confirm-revert-btn"
                          onClick={() => void handleRevert(item.change_set_id)}
                        >
                          REVERT
                        </button>
                        <button
                          type="button"
                          className="history-confirm-cancel-btn"
                          onClick={closeConfirm}
                        >
                          KEEP CHANGES
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

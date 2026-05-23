/**
 * SegmentEditorPanel — inline per-bin segment editor (UI-SPEC §E).
 *
 * Shows full 88px SegmentStrip + SegmentLegend for one bin.
 * Drag handles let the admin override segment fractions.
 * "PREVIEW CHANGES" CTA navigates to /admin/preview once a change is staged.
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { LocatorHeader } from './LocatorHeader'
import { SegmentStrip } from './SegmentStrip'
import { SegmentLegend } from './SegmentLegend'
import { RecordPickerSheet } from './RecordPickerSheet'
import { setOverrides } from '../../api/adminClient'
import { useAdminStore } from '../../state/adminStore'
import type { Segment } from '../../api/cubeTypes'

interface SegmentEditorPanelProps {
  /** Bin identity. */
  unitId: number
  row: number
  col: number
  /** 1-based display number for this bin (shown in heading). */
  binDisplay: number
  /** Shelf display name, e.g. "SHELF A". */
  shelfName?: string
  /** Initial segments from server (GET /segments). */
  initialSegments: Segment[]
  /** Grid dimensions (default 4×4 Kallax). */
  rows?: number
  cols?: number
  /** Called when user taps "EDIT CUT POINT" to re-open the cut picker. */
  onEditCutPoint?: () => void
}

export function SegmentEditorPanel({
  unitId,
  row,
  col,
  binDisplay,
  shelfName = 'SHELF A',
  initialSegments,
  rows = 4,
  cols = 4,
  onEditCutPoint,
}: SegmentEditorPanelProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { pendingChangeSet, setPendingChangeSet } = useAdminStore()

  const [segments, setSegments] = useState<Segment[]>(initialSegments)
  const [hasChanges, setHasChanges] = useState(false)
  const [isSavingOverride, setIsSavingOverride] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [showCutPicker, setShowCutPicker] = useState(false)

  /** Stage override edits in the pending change-set for diff-preview. */
  const stageOverrideInPending = useCallback(
    (updatedSegs: Segment[]) => {
      const now = new Date().toISOString()
      const overrideEdit = {
        unit_id: unitId,
        row,
        col,
        first_label: '',
        first_catalog: '',
        last_label: '',
        last_catalog: '',
        segment_overrides: updatedSegs
          .filter((s) => s.is_override)
          .map((s) => ({ label: s.label, fraction: s.fraction })),
      }
      const existing = pendingChangeSet
      if (existing) {
        const others = existing.edits.filter(
          (e) => !(e.unit_id === unitId && e.row === row && e.col === col),
        )
        setPendingChangeSet({ ...existing, edits: [...others, overrideEdit] })
      } else {
        setPendingChangeSet({ id: crypto.randomUUID(), created_at: now, edits: [overrideEdit] })
      }
    },
    [unitId, row, col, pendingChangeSet, setPendingChangeSet],
  )

  /** Called when user finishes dragging a handle. */
  const handleDragSetOverride = useCallback(
    async (index: number, newFraction: number) => {
      const updated = segments.map((seg, i) => {
        if (i === index) {
          return { ...seg, fraction: newFraction, is_override: true }
        }
        if (i === index + 1) {
          const leftSum = segments.slice(0, index).reduce((a, s) => a + s.fraction, 0)
          const rightSum = segments.slice(0, index + 2).reduce((a, s) => a + s.fraction, 0)
          return { ...seg, fraction: rightSum - leftSum - newFraction, is_override: true }
        }
        return seg
      })
      setSegments(updated)
      setHasChanges(true)
      setSaveError(null)

      setIsSavingOverride(true)
      try {
        const idempotencyKey = crypto.randomUUID()
        await setOverrides(
          unitId,
          row,
          col,
          { overrides: updated.map((s) => ({ label: s.label, fraction: s.is_override ? s.fraction : null })) },
          idempotencyKey,
        )
        stageOverrideInPending(updated)
        void queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId, row, col] })
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Could not save override — try again.'
        setSaveError(msg)
      } finally {
        setIsSavingOverride(false)
      }
    },
    [segments, unitId, row, col, queryClient, stageOverrideInPending],
  )

  /** Resync an overridden segment to its auto fraction. */
  const handleResync = useCallback(
    async (label: string, autoFraction: number) => {
      const updated = segments.map((seg) =>
        seg.label === label ? { ...seg, fraction: autoFraction, is_override: true } : seg,
      )
      setSegments(updated)
      setHasChanges(true)
      setSaveError(null)

      setIsSavingOverride(true)
      try {
        const idempotencyKey = crypto.randomUUID()
        await setOverrides(
          unitId,
          row,
          col,
          { overrides: updated.map((s) => ({ label: s.label, fraction: s.is_override ? s.fraction : null })) },
          idempotencyKey,
        )
        stageOverrideInPending(updated)
        void queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId, row, col] })
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Could not save override — try again.'
        setSaveError(msg)
      } finally {
        setIsSavingOverride(false)
      }
    },
    [segments, unitId, row, col, queryClient, stageOverrideInPending],
  )

  return (
    <div className="segment-editor-panel">
      <h2 className="segment-editor-heading">BIN {binDisplay} SEGMENTS</h2>

      <LocatorHeader
        unitId={unitId}
        row={row}
        col={col}
        shelfName={shelfName}
        binNumber={binDisplay}
        rows={rows}
        cols={cols}
      />

      {/* Edit cut point link */}
      {onEditCutPoint && (
        <button
          type="button"
          className="editor-btn-secondary"
          onClick={() => setShowCutPicker(true)}
        >
          ✎ EDIT CUT POINT
        </button>
      )}

      {/* Full segment strip (draggable) */}
      <SegmentStrip
        segments={segments}
        onDragSetOverride={(idx, frac) => void handleDragSetOverride(idx, frac)}
        isReadOnly={false}
      />

      {/* Legend */}
      <SegmentLegend
        segments={segments}
        onResync={(label, autoFraction) => void handleResync(label, autoFraction)}
      />

      {/* Status */}
      {isSavingOverride && (
        <p className="editor-status-validating" aria-live="polite">Saving override…</p>
      )}
      {saveError && (
        <p className="editor-save-error" role="alert">{saveError}</p>
      )}
      {!hasChanges && (
        <p className="segment-editor-no-change">No changes made yet.</p>
      )}

      {/* Preview CTA */}
      <button
        type="button"
        className="editor-btn-primary"
        onClick={() => void navigate('/admin/preview')}
        disabled={!hasChanges}
      >
        PREVIEW CHANGES
      </button>

      {/* Record picker sheet (cut point edit) */}
      {showCutPicker && (
        <RecordPickerSheet
          mode="edit"
          unitId={unitId}
          row={row}
          col={col}
          onCommit={() => {
            setShowCutPicker(false)
            setHasChanges(true)
            void queryClient.invalidateQueries({
              queryKey: ['admin', 'segments', unitId, row, col],
            })
          }}
          onCancel={() => setShowCutPicker(false)}
        />
      )}
    </div>
  )
}

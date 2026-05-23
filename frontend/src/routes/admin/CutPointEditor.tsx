/**
 * CutPointEditor — bin-card list for cut-point + segment editing (UI-SPEC §D).
 *
 * Route: /admin/cubes/:unit/:row/:col
 * Replaces Phase 3 per-cube first/last form for all boundary editing.
 *
 * Screen structure:
 *   - Locator Header (mini-Kallax, edited bin lit yellow)
 *   - Vertical list of bin cards, one per CONFIGURED cube in this unit
 *   - Insert-cut dividers between cards (44px tap target)
 *   - A single compact "add cut" affordance at the bottom for unconfigured cubes
 *   - Inline SegmentEditorPanel expands when "EDIT SEGMENTS" is tapped
 *   - RecordPickerSheet slides up for insert-cut actions
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { LocatorHeader } from './LocatorHeader'
import { SegmentStrip } from './SegmentStrip'
import { SegmentEditorPanel } from './SegmentEditorPanel'
import { RecordPickerSheet } from './RecordPickerSheet'
import { getUnitSegments, adminGetCubes } from '../../api/adminClient'
import { shelfName } from '../../lib/shelf'
import type { AdminCube } from '../../api/types'
import type { Segment } from '../../api/cubeTypes'

/** One locally-inserted (pending) new bin, shown after a user inserts a cut. */
interface NewBin {
  /** The position of the card AFTER which this new bin appears. */
  afterRow: number
  afterCol: number
  display: number
}

export function CutPointEditor() {
  const { unit, row, col } = useParams<{
    unit: string
    row: string
    col: string
  }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const unitId = Number(unit)
  const editRow = Number(row)
  const editCol = Number(col)

  const ROWS = 4
  const COLS = 4

  // Track which bin's editor panel is expanded (default: the routed-to bin)
  const [expandedBin, setExpandedBin] = useState<{ row: number; col: number } | null>(
    { row: editRow, col: editCol },
  )

  // Track insert-cut state: which cube we're inserting after
  const [insertAfterCube, setInsertAfterCube] = useState<AdminCube | null>(null)

  // Track locally inserted new bins (display only — actual cut persisted on commit)
  const [newBins, setNewBins] = useState<NewBin[]>([])

  // Track renumber-hint visibility (shown after insert)
  const [showRenumberHint, setShowRenumberHint] = useState(false)

  // ── Fetch all cubes for this unit (one request, no per-card requests) ──────
  const { data: cubesData, isLoading: cubesLoading } = useQuery({
    queryKey: ['admin', 'cubes'],
    queryFn: adminGetCubes,
    staleTime: 60_000,
  })

  // Filter to configured cubes for this unit (non-empty = has a boundary set)
  const configuredCubes = useMemo(() => {
    if (!cubesData) return []
    return cubesData.cubes.filter(
      (c) => c.unit_id === unitId && !c.is_empty,
    )
  }, [cubesData, unitId])

  // ── Fetch segment data for the currently edited bin ───────────────────────
  const { data: editedBinSegments, isLoading: segsLoading } = useQuery({
    queryKey: ['admin', 'segments', unitId, editRow, editCol],
    queryFn: () => getUnitSegments(unitId, editRow, editCol),
    staleTime: 30_000,
  })

  // Compute edit bin display number (1-based, row-major)
  const editBinDisplay = editRow * COLS + editCol + 1

  const isLoading = cubesLoading || segsLoading

  function handleEditSegments(cube: AdminCube) {
    setExpandedBin(
      expandedBin && expandedBin.row === cube.row && expandedBin.col === cube.col
        ? null
        : { row: cube.row, col: cube.col },
    )
  }

  function handleInsertCommit() {
    if (insertAfterCube) {
      const afterDisplay = insertAfterCube.row * COLS + insertAfterCube.col + 1
      setNewBins((prev) => [
        ...prev,
        {
          afterRow: insertAfterCube.row,
          afterCol: insertAfterCube.col,
          display: afterDisplay + 1,
        },
      ])
      setShowRenumberHint(true)
    }
    setInsertAfterCube(null)
    // Invalidate cubes + segments so the list refreshes
    void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId] })
  }

  if (isLoading) {
    return (
      <div className="cut-point-editor-loading" aria-live="polite">
        Loading…
      </div>
    )
  }

  const editedSegments = editedBinSegments?.segments ?? []
  const hasUnconfigured = configuredCubes.length < ROWS * COLS

  return (
    <div className="cut-point-editor">
      {/* Back nav + heading */}
      <header className="cut-point-editor-header">
        <button
          type="button"
          className="cut-point-editor-back"
          onClick={() => void navigate('/admin/cubes')}
          aria-label="Back to cubes grid"
        >
          ← CUBES
        </button>
        <h1 className="cut-point-editor-title">
          EDIT SHELF {String.fromCharCode(64 + unitId)}
        </h1>
      </header>

      {/* Locator Header (mini-Kallax — edited bin lit yellow) */}
      <LocatorHeader
        unitId={unitId}
        row={editRow}
        col={editCol}
        shelfName={shelfName(unitId)}
        binNumber={editBinDisplay}
        rows={ROWS}
        cols={COLS}
      />

      {/* Bin-card cut-point list — only configured cubes */}
      <div className="cut-point-list">
        {configuredCubes.map((cube, idx) => {
          const isEditing =
            expandedBin &&
            expandedBin.row === cube.row &&
            expandedBin.col === cube.col
          const isCurrentBin = cube.row === editRow && cube.col === editCol
          const cubeDisplay = cube.row * COLS + cube.col + 1

          // Pending new bins inserted after this cube
          const newBinsAfter = newBins.filter(
            (nb) => nb.afterRow === cube.row && nb.afterCol === cube.col,
          )

          // Segments for this bin: real data for current bin, mini strip data
          // from adminGetCubes for others (no per-card fetch)
          const cardSegments: Segment[] = isCurrentBin
            ? editedSegments
            : [] // mini strip shows empty for non-current bins (real data loads on expand)

          return (
            <div key={`${cube.row}-${cube.col}`}>
              {/* Insert-cut divider ABOVE first card */}
              {idx === 0 && (
                <InsertCutDivider
                  label="insert cut before first bin"
                  onTap={() => setInsertAfterCube({ ...cube, row: -1, col: -1 })}
                />
              )}

              {/* Bin card */}
              <div
                className={`bin-card${isEditing ? ' bin-card--editing' : ''}`}
              >
                <div className="bin-card-header">
                  {/* Bin-number chip */}
                  <div className="bin-number-chip">
                    <span className="bin-number-chip-text">B{cubeDisplay}</span>
                  </div>

                  {/* "starts at" label + value */}
                  <div className="bin-card-info">
                    <span className="bin-starts-at">STARTS AT</span>
                    <span className="bin-cut-record">
                      {cube.first_label ?? 'Not configured'}
                      {cube.first_catalog ? ` · ${cube.first_catalog}` : ''}
                    </span>
                  </div>
                </div>

                {/* Mini segment strip (read-only; real segments only for current bin) */}
                <SegmentStrip
                  segments={cardSegments}
                  isReadOnly={true}
                />

                {/* Actions */}
                <div className="bin-card-actions">
                  <button
                    type="button"
                    className="bin-edit-segments-btn"
                    onClick={() => handleEditSegments(cube)}
                    aria-expanded={!!isEditing}
                    aria-controls={`seg-panel-${cube.row}-${cube.col}`}
                  >
                    ✎ EDIT SEGMENTS
                  </button>
                </div>
              </div>

              {/* Inline segment editor panel */}
              {isEditing && isCurrentBin && (
                <div id={`seg-panel-${cube.row}-${cube.col}`}>
                  <SegmentEditorPanel
                    unitId={unitId}
                    row={cube.row}
                    col={cube.col}
                    binDisplay={cubeDisplay}
                    shelfName={shelfName(unitId)}
                    initialSegments={editedSegments}
                    rows={ROWS}
                    cols={COLS}
                    onEditCutPoint={() => undefined}
                  />
                </div>
              )}

              {/* Renumber hint (after new-bin inserts) */}
              {showRenumberHint && newBinsAfter.length > 0 && (
                <div className="renumber-hint" role="status">
                  <Info size={16} className="renumber-hint-icon" aria-hidden="true" />
                  <span className="renumber-hint-text">
                    New BIN {cubeDisplay + 1} will be inserted · higher bins
                    renumber — e.g. BIN {cubeDisplay + 1}→{cubeDisplay + 2}
                  </span>
                </div>
              )}

              {/* Display locally-inserted pending bins after this card */}
              {newBinsAfter.map((nb) => (
                <div key={`new-${nb.afterRow}-${nb.afterCol}-${nb.display}`} className="bin-card bin-card--new">
                  <div className="bin-card-header">
                    <div className="bin-number-chip">
                      <span className="bin-number-chip-text">B{nb.display}</span>
                      <span className="bin-new-badge">NEW</span>
                    </div>
                    <div className="bin-card-info">
                      <span className="bin-starts-at">STARTS AT</span>
                      <span className="bin-cut-record">
                        New cut — see diff preview
                      </span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Insert-cut divider BELOW this card */}
              <InsertCutDivider
                label={`Insert cut after BIN ${cubeDisplay}`}
                onTap={() => setInsertAfterCube(cube)}
              />
            </div>
          )
        })}

        {/* Empty-state: no configured bins yet */}
        {configuredCubes.length === 0 && (
          <p className="segment-editor-no-change">
            No bins configured for this shelf yet.
          </p>
        )}

        {/* Single compact "add cut" affordance for unconfigured capacity */}
        {hasUnconfigured && (
          <div className="cut-point-add-affordance">
            <button
              type="button"
              className="bin-edit-segments-btn"
              onClick={() => {
                const last = configuredCubes[configuredCubes.length - 1]
                setInsertAfterCube(
                  last ?? {
                    unit_id: unitId, row: 0, col: -1,
                    is_empty: false,
                    first_label: '', first_catalog: '',
                    last_label: '', last_catalog: '',
                    fill_level: 0,
                  },
                )
              }}
            >
              + ADD CUT POINT ({ROWS * COLS - configuredCubes.length} unconfigured)
            </button>
          </div>
        )}
      </div>

      {/* Insert-cut record picker sheet */}
      {insertAfterCube && (
        <RecordPickerSheet
          mode="insert"
          unitId={unitId}
          row={insertAfterCube.row < 0 ? 0 : insertAfterCube.row}
          col={insertAfterCube.col < 0 ? 0 : insertAfterCube.col}
          afterBinDisplay={
            insertAfterCube.row < 0
              ? 0
              : insertAfterCube.row * COLS + insertAfterCube.col + 1
          }
          onCommit={() => handleInsertCommit()}
          onCancel={() => setInsertAfterCube(null)}
        />
      )}
    </div>
  )
}

/** Dashed insert-cut divider button. */
function InsertCutDivider({
  label,
  onTap,
}: {
  label: string
  onTap: () => void
}) {
  return (
    <div
      className="insert-cut-divider"
      role="button"
      tabIndex={0}
      aria-label={label}
      onClick={onTap}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onTap()
        }
      }}
    >
      <span className="insert-cut-divider-label">＋ insert cut</span>
    </div>
  )
}

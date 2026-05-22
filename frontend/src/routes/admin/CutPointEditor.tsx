/**
 * CutPointEditor — bin-card list for cut-point + segment editing (UI-SPEC §D).
 *
 * Route: /admin/cubes/:unit/:row/:col
 * Replaces Phase 3 per-cube first/last form for all boundary editing.
 *
 * Screen structure:
 *   - Locator Header (mini-Kallax, edited bin lit yellow)
 *   - Vertical list of bin cards, one per Kallax cube
 *   - Insert-cut dividers between cards (44px tap target)
 *   - Inline SegmentEditorPanel expands when "EDIT SEGMENTS" is tapped
 *   - RecordPickerSheet slides up for insert-cut actions
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Info } from 'lucide-react'
import { LocatorHeader } from './LocatorHeader'
import { SegmentStrip } from './SegmentStrip'
import { SegmentEditorPanel } from './SegmentEditorPanel'
import { RecordPickerSheet } from './RecordPickerSheet'
import { getUnitSegments } from '../../api/adminClient'
import type { Segment } from '../../api/cubeTypes'

/** One bin card entry in the cut-point list. */
interface BinCard {
  /** 0-based row within the unit. */
  row: number
  /** 0-based col within the unit. */
  col: number
  /** 1-based display number. */
  display: number
  firstLabel: string | null
  firstCatalog: string | null
  segments: Segment[]
  isNew?: boolean
}

/** Derive a simple grid of bin cards for a 4×4 Kallax unit. */
function buildBinCards(rows: number, cols: number): BinCard[] {
  const cards: BinCard[] = []
  let display = 1
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      cards.push({
        row: r,
        col: c,
        display,
        firstLabel: null,
        firstCatalog: null,
        segments: [],
      })
      display++
    }
  }
  return cards
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

  // Track which bin's editor panel is expanded
  const [expandedBin, setExpandedBin] = useState<{ row: number; col: number } | null>(
    { row: editRow, col: editCol },
  )

  // Track insert-cut state: which divider was tapped
  const [insertAfterBin, setInsertAfterBin] = useState<BinCard | null>(null)

  // Track locally inserted new bins (display only — actual cut persisted on commit)
  const [newBins, setNewBins] = useState<BinCard[]>([])

  // Track renumber-hint visibility (shown after insert, hidden on preview)
  const [showRenumberHint, setShowRenumberHint] = useState(false)

  // Build card list for this unit (4×4 default)
  const [cards] = useState<BinCard[]>(() => buildBinCards(ROWS, COLS))

  // Fetch segment data for the currently edited bin
  const { data: editedBinSegments, isLoading } = useQuery({
    queryKey: ['admin', 'segments', unitId, editRow, editCol],
    queryFn: () => getUnitSegments(unitId, editRow, editCol),
    staleTime: 30_000,
  })

  // Compute edit bin display number (1-based, row-major)
  const editBinDisplay = editRow * COLS + editCol + 1

  function handleEditSegments(card: BinCard) {
    setExpandedBin(
      expandedBin && expandedBin.row === card.row && expandedBin.col === card.col
        ? null
        : { row: card.row, col: card.col },
    )
  }

  function handleInsertCutDivider(afterCard: BinCard) {
    setInsertAfterBin(afterCard)
  }

  function handleInsertCommit() {
    // Add a display-only "new" bin below the target
    if (insertAfterBin) {
      const newBin: BinCard = {
        row: insertAfterBin.row,
        col: insertAfterBin.col,
        display: insertAfterBin.display + 1,
        firstLabel: null,
        firstCatalog: null,
        segments: [],
        isNew: true,
      }
      setNewBins((prev) => [...prev, newBin])
      setShowRenumberHint(true)
    }
    setInsertAfterBin(null)
    // Invalidate segments for the edited bin
    void queryClient.invalidateQueries({
      queryKey: ['admin', 'segments', unitId],
    })
  }

  if (isLoading) {
    return (
      <div className="cut-point-editor-loading" aria-live="polite">
        Loading segments…
      </div>
    )
  }

  const editedSegments = editedBinSegments?.segments ?? []

  return (
    <div className="cut-point-editor">
      {/* Back nav + heading */}
      <header className="cube-editor-header">
        <button
          type="button"
          className="cube-editor-back"
          onClick={() => void navigate('/admin/cubes')}
          aria-label="Back to cubes grid"
        >
          ← CUBES
        </button>
        <h1 className="cube-editor-title">
          EDIT UNIT {unitId}
        </h1>
      </header>

      {/* Locator Header (mini-Kallax — edited bin lit yellow) */}
      <LocatorHeader
        unitId={unitId}
        row={editRow}
        col={editCol}
        shelfName="SHELF A"
        binNumber={editBinDisplay}
        rows={ROWS}
        cols={COLS}
      />

      {/* Bin-card cut-point list */}
      <div className="cut-point-list">
        {cards.map((card, idx) => {
          const isEditing =
            expandedBin && expandedBin.row === card.row && expandedBin.col === card.col
          const isCurrentBin = card.row === editRow && card.col === editCol

          // Check if any locally-inserted new bins follow this card
          const newBinsAfter = newBins.filter(
            (nb) => nb.row === card.row && nb.col === card.col,
          )

          return (
            <div key={`${card.row}-${card.col}`}>
              {/* Insert-cut divider ABOVE first card */}
              {idx === 0 && (
                <InsertCutDivider
                  afterBin={card}
                  isFirst
                  onTap={() => handleInsertCutDivider({ ...card, display: 0 })}
                />
              )}

              {/* Bin card */}
              <div
                className={`bin-card${isEditing ? ' bin-card--editing' : ''}${isCurrentBin ? ' bin-card--current' : ''}`}
              >
                <div className="bin-card-header">
                  {/* Bin-number chip */}
                  <div className="bin-card-chip">
                    <span className="bin-card-chip-label">B{card.display}</span>
                  </div>

                  {/* "starts at" label */}
                  <div className="bin-card-starts">
                    <span className="bin-card-starts-label">STARTS AT</span>
                    {isCurrentBin && editedSegments.length > 0 ? (
                      <span className="bin-card-starts-value">
                        {editedSegments[0].label}{' '}
                        <span className="bin-card-catalog">
                          {/* catalog shown via segment label only — first record data not available here */}
                        </span>
                      </span>
                    ) : (
                      <span className="bin-card-starts-value bin-card-starts-empty">
                        Not configured
                      </span>
                    )}
                  </div>
                </div>

                {/* Mini segment strip */}
                <div className="bin-card-strip">
                  <SegmentStrip
                    segments={isCurrentBin ? editedSegments : []}
                    isReadOnly={true}
                  />
                </div>

                {/* Actions */}
                <div className="bin-card-actions">
                  <button
                    type="button"
                    className="bin-card-edit-btn"
                    onClick={() => handleEditSegments(card)}
                    aria-expanded={!!isEditing}
                    aria-controls={`seg-panel-${card.row}-${card.col}`}
                  >
                    ✎ EDIT SEGMENTS
                  </button>
                </div>
              </div>

              {/* Inline segment editor panel */}
              {isEditing && isCurrentBin && (
                <div
                  id={`seg-panel-${card.row}-${card.col}`}
                  className="bin-card-seg-panel"
                >
                  <SegmentEditorPanel
                    unitId={unitId}
                    row={card.row}
                    col={card.col}
                    binDisplay={card.display}
                    shelfName="SHELF A"
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
                    New BIN {card.display + 1} will be inserted · higher bins
                    renumber — e.g. BIN {card.display + 1}→{card.display + 2}
                  </span>
                </div>
              )}

              {/* Display new bins inserted after this card */}
              {newBinsAfter.map((nb) => (
                <div key={`new-${nb.row}-${nb.col}`} className="bin-card bin-card--new">
                  <div className="bin-card-header">
                    <div className="bin-card-chip">
                      <span className="bin-card-chip-label">B{nb.display}</span>
                      <span className="bin-card-chip-new-badge">NEW</span>
                    </div>
                    <div className="bin-card-starts">
                      <span className="bin-card-starts-label">STARTS AT</span>
                      <span className="bin-card-starts-value bin-card-starts-empty">
                        New cut — see diff preview
                      </span>
                    </div>
                  </div>
                </div>
              ))}

              {/* Insert-cut divider BELOW this card (between cards and at end) */}
              <InsertCutDivider
                afterBin={card}
                onTap={() => handleInsertCutDivider(card)}
              />
            </div>
          )
        })}
      </div>

      {/* Insert-cut record picker sheet */}
      {insertAfterBin && (
        <RecordPickerSheet
          mode="insert"
          unitId={unitId}
          row={insertAfterBin.row}
          col={insertAfterBin.col}
          afterBinDisplay={insertAfterBin.display}
          onCommit={() => handleInsertCommit()}
          onCancel={() => setInsertAfterBin(null)}
        />
      )}
    </div>
  )
}

/** Dashed insert-cut divider button. */
function InsertCutDivider({
  afterBin,
  isFirst = false,
  onTap,
}: {
  afterBin: BinCard
  isFirst?: boolean
  onTap: () => void
}) {
  return (
    <div
      className="insert-cut-divider"
      role="button"
      tabIndex={0}
      aria-label={
        isFirst
          ? 'Insert cut before first bin'
          : `Insert cut after BIN ${afterBin.display}`
      }
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

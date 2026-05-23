/**
 * ShelfBinList — bin-card list for one shelf unit (faithful port of sketch 002 Variant A).
 *
 * Route: /admin/cubes/:unit
 * Nav flow: CUBES → ShelfBinList → tap "✎ EDIT SEGMENTS" → BinWidthEditor
 *
 * Screen structure (mirrors sketch 002 Variant A exactly):
 *   - Back nav ("← CUBES") + title "EDIT SHELF A"
 *   - Locator header: mini 4×4 Kallax + "SHELF A"
 *   - Vertical list: CONFIGURED bins ONLY (non-empty cubes for this unit)
 *   - Dashed "＋ insert cut" dividers between bins (and before first / after last)
 *   - Each bin card: bin-number chip B{n}, "STARTS AT {label} · {record}", mini read-only strip, ✎ EDIT SEGMENTS
 *   - Insert opens RecordPickerSheet; NEW badge + renumber hint on insert
 *
 * Design tokens only — no hardcoded hex (CLAUDE.md constraint).
 * No innerHTML — all DOM built with React JSX.
 */

import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { LocatorHeader } from './LocatorHeader'
import { SegmentStrip } from './SegmentStrip'
import { RecordPickerSheet } from './RecordPickerSheet'
import { adminGetCubes, getUnitSegments } from '../../api/adminClient'
import { shelfName, shelfLetter } from '../../lib/shelf'
import type { AdminCube } from '../../api/types'
import type { Segment } from '../../api/cubeTypes'

const ROWS = 4
const COLS = 4

/** Stable display bin number (1-based, row-major). */
function binNum(cube: AdminCube): number {
  return cube.row * COLS + cube.col + 1
}

interface InsertState {
  /** The cube after which we're inserting (null = before first bin). */
  afterCube: AdminCube | null
  /** After-bin display number. */
  afterDisplay: number
}

interface NewBinPlaceholder {
  afterRow: number
  afterCol: number
  display: number
  label: string
  record: string
}

export function ShelfBinList() {
  const { unit } = useParams<{ unit: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const unitId = Number(unit)

  // ── Sheet state ──────────────────────────────────────────────────────────────
  const [insertState, setInsertState] = useState<InsertState | null>(null)
  const [editingCube, setEditingCube] = useState<AdminCube | null>(null)

  // New bins inserted locally (display-only until commit)
  const [newBins, setNewBins] = useState<NewBinPlaceholder[]>([])
  const [showRenumberHint, setShowRenumberHint] = useState(false)

  // ── Data ─────────────────────────────────────────────────────────────────────
  const { data: cubesData, isLoading, isError } = useQuery({
    queryKey: ['admin', 'cubes'],
    queryFn: adminGetCubes,
    staleTime: 60_000,
  })

  const configuredBins = useMemo(() => {
    if (!cubesData) return []
    return cubesData.cubes
      .filter((c) => c.unit_id === unitId && !c.is_empty)
      .sort((a, b) => a.row !== b.row ? a.row - b.row : a.col - b.col)
  }, [cubesData, unitId])

  // ── Handlers ─────────────────────────────────────────────────────────────────
  function openInsertAfter(afterCube: AdminCube | null) {
    const afterDisplay = afterCube ? binNum(afterCube) : 0
    setInsertState({ afterCube, afterDisplay })
  }

  function openEditCut(cube: AdminCube) {
    setEditingCube(cube)
  }

  function handleInsertCommit() {
    if (insertState) {
      const afterCube = insertState.afterCube
      const newDisplay = insertState.afterDisplay + 1
      setNewBins((prev) => [
        ...prev,
        {
          afterRow: afterCube?.row ?? -1,
          afterCol: afterCube?.col ?? -1,
          display: newDisplay,
          label: '',
          record: '',
        },
      ])
      setShowRenumberHint(true)
    }
    setInsertState(null)
    void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    void queryClient.invalidateQueries({ queryKey: ['admin', 'segments', unitId] })
  }

  function handleEditCommit() {
    setEditingCube(null)
    void queryClient.invalidateQueries({ queryKey: ['admin', 'cubes'] })
    void queryClient.invalidateQueries({
      queryKey: ['admin', 'segments', unitId],
    })
  }

  // ── Loading / error ──────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="cut-point-editor-loading" aria-live="polite">
        Loading…
      </div>
    )
  }

  if (isError || !cubesData) {
    return (
      <div className="cubes-grid-error" role="alert">
        Failed to load bins. Please try again.
      </div>
    )
  }

  const shelfLtr = shelfLetter(unitId)
  const shelfDisplayName = shelfName(unitId)
  const totalBins = ROWS * COLS
  const unconfiguredCount = totalBins - configuredBins.length

  return (
    <div className="sbl-screen">
      {/* Header — back + title */}
      <header className="sbl-header">
        <button
          type="button"
          className="sbl-back"
          onClick={() => void navigate('/admin/cubes')}
          aria-label="Back to shelves"
        >
          ← CUBES
        </button>
        <h1 className="sbl-title">EDIT SHELF {shelfLtr}</h1>
      </header>

      {/* Locator header — mini Kallax, no specific bin lit */}
      <div className="sbl-locator">
        <LocatorHeader
          unitId={unitId}
          row={-1}
          col={-1}
          shelfName={shelfDisplayName}
          rows={ROWS}
          cols={COLS}
        />
      </div>

      {/* Bin-card list */}
      <div className="sbl-list">
        {/* Insert-cut divider BEFORE first bin */}
        {configuredBins.length > 0 && (
          <InsertCutDivider onTap={() => openInsertAfter(null)} />
        )}

        {configuredBins.map((cube) => {
          const display = binNum(cube)
          // New bins inserted after this cube
          const newBinsAfter = newBins.filter(
            (nb) => nb.afterRow === cube.row && nb.afterCol === cube.col,
          )

          return (
            <div key={`${cube.row}-${cube.col}`}>
              <BinCard
                cube={cube}
                display={display}
                unitId={unitId}
                onEditSegments={() =>
                  void navigate(`/admin/cubes/${unitId}/${cube.row}/${cube.col}`)
                }
                onEditCut={() => openEditCut(cube)}
              />

              {/* Renumber hint after insert */}
              {showRenumberHint && newBinsAfter.length > 0 && (
                <div className="sbl-renumber-hint" role="status">
                  New BIN {display + 1} will be inserted · higher bins renumber
                  (e.g. {display + 1}→{display + 2}).
                </div>
              )}

              {/* Locally-inserted new bin placeholders */}
              {newBinsAfter.map((nb) => (
                <NewBinCard
                  key={`new-${nb.afterRow}-${nb.afterCol}-${nb.display}`}
                  display={nb.display}
                />
              ))}

              {/* Insert-cut divider AFTER each bin */}
              <InsertCutDivider onTap={() => openInsertAfter(cube)} />
            </div>
          )
        })}

        {/* Empty-state */}
        {configuredBins.length === 0 && (
          <div className="sbl-empty">
            <p className="sbl-empty-text">No bins configured for this shelf yet.</p>
            <InsertCutDivider onTap={() => openInsertAfter(null)} />
          </div>
        )}

        {/* Unconfigured capacity hint */}
        {unconfiguredCount > 0 && configuredBins.length > 0 && (
          <p className="sbl-unconfigured-hint">
            {unconfiguredCount} of {totalBins} bins unconfigured
          </p>
        )}
      </div>

      {/* RecordPickerSheet — insert mode */}
      {insertState && (
        <RecordPickerSheet
          mode="insert"
          unitId={unitId}
          row={insertState.afterCube?.row ?? 0}
          col={insertState.afterCube?.col ?? 0}
          afterBinDisplay={insertState.afterDisplay}
          onCommit={handleInsertCommit}
          onCancel={() => setInsertState(null)}
        />
      )}

      {/* RecordPickerSheet — edit cut mode */}
      {editingCube && (
        <RecordPickerSheet
          mode="edit"
          unitId={unitId}
          row={editingCube.row}
          col={editingCube.col}
          onCommit={handleEditCommit}
          onCancel={() => setEditingCube(null)}
        />
      )}
    </div>
  )
}

/** ── BinCard — faithful port of sketch 002 Variant A bin card ─────────────── */
function BinCard({
  cube,
  display,
  unitId,
  onEditSegments,
  onEditCut,
}: {
  cube: AdminCube
  display: number
  unitId: number
  onEditSegments: () => void
  onEditCut: () => void
}) {
  // Fetch segments for this bin's mini strip (only when visible — React Query caches)
  const { data: segsData } = useQuery({
    queryKey: ['admin', 'segments', unitId, cube.row, cube.col],
    queryFn: () => getUnitSegments(unitId, cube.row, cube.col),
    staleTime: 60_000,
  })

  const segments: Segment[] = segsData?.segments ?? []

  return (
    <div className="sbl-bincard">
      <div className="sbl-bincard-top">
        {/* Square bin-number chip */}
        <div className="sbl-binno">{display}</div>

        {/* "STARTS AT label · record" */}
        <div className="sbl-cutinfo">
          <span className="sbl-cutinfo-k">STARTS AT</span>
          <div className="sbl-cutinfo-v">
            <span className="sbl-cutinfo-lab">{cube.first_label}</span>
            <span className="sbl-cutinfo-rec">{cube.first_catalog}</span>
          </div>
        </div>

        {/* Edit cut-point button */}
        <button
          type="button"
          className="sbl-editbtn"
          title="Edit cut point"
          onClick={onEditCut}
          aria-label={`Edit cut point for bin ${display}`}
        >
          ✎
        </button>
      </div>

      {/* Mini read-only segment strip */}
      <div className="sbl-ministrip-wrap">
        <SegmentStrip segments={segments} isReadOnly />
      </div>

      {/* Edit segments action */}
      <button
        type="button"
        className="sbl-edit-segments-btn"
        onClick={onEditSegments}
      >
        ✎ EDIT SEGMENTS
      </button>
    </div>
  )
}

/** ── NewBinCard — placeholder for a locally-inserted new bin ──────────────── */
function NewBinCard({ display }: { display: number }) {
  return (
    <div className="sbl-bincard sbl-bincard--new">
      <div className="sbl-bincard-top">
        <div className="sbl-binno sbl-binno--new">{display}</div>
        <div className="sbl-cutinfo">
          <span className="sbl-cutinfo-k">STARTS AT</span>
          <div className="sbl-cutinfo-v">
            <span className="sbl-cutinfo-lab">New cut</span>
            <span className="sbl-badge-new">NEW</span>
          </div>
        </div>
      </div>
    </div>
  )
}

/** ── InsertCutDivider — dashed "＋ insert cut" line between bins ─────────────── */
function InsertCutDivider({ onTap }: { onTap: () => void }) {
  return (
    <div className="sbl-insert">
      <div className="sbl-insert-line" />
      <button
        type="button"
        className="sbl-insert-btn"
        onClick={onTap}
        aria-label="Insert cut point"
      >
        ＋ insert cut
      </button>
      <div className="sbl-insert-line" />
    </div>
  )
}

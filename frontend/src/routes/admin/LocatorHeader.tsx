/**
 * LocatorHeader — compact 4×4 mini-Kallax header for the segment editor.
 *
 * Shows fill-shaded cubes via a blue-saturation gradient (--fill custom property),
 * empty cubes in the CUBE-05 desaturated state, and the edited bin lit yellow
 * (--gruvax-cell-lit + LED glow). Tapping a cell reveals an inline popover
 * with the bin ID and exact record count + percentage.
 *
 * Backward-compatible: when `cubes` is absent, falls back to dim/lit behavior.
 *
 * Uses --gruvax-cell-size-sm (28px) cells, --gruvax-cell-gap-sm (4px) gap.
 * Design tokens only — no hardcoded hex.
 */

import { useState, useMemo, useEffect } from 'react'
import type { AdminCube } from '../../api/types'
import { shelfLetter } from '../../lib/shelf'

interface LocatorHeaderProps {
  unitId: number
  /** 0-based row of the edited bin */
  row: number
  /** 0-based col of the edited bin */
  col: number
  /** Display name for the shelf, e.g. "SHELF A" */
  shelfName?: string
  /** Human-readable bin number (1-based) */
  binNumber?: number
  /** Grid dimensions (default 4×4 for Kallax) */
  rows?: number
  cols?: number
  /** Fill/occupancy data for the whole shelf — passed from ShelfBinList.
   *  When absent the component falls back to dim/lit behavior. */
  cubes?: AdminCube[]
}

/** Derive the bin ID string, e.g. unitId=1, row=0, col=0, cols=4 → "A1" */
function binId(unitId: number, r: number, c: number, cols: number): string {
  return `${shelfLetter(unitId)}${r * cols + c + 1}`
}

/**
 * True fill percentage for the numeric readout, capped at 999% to avoid layout
 * blowups on wildly overstuffed cubes. Mirrors the kiosk's `formatFillPct`
 * (CubeContentsPanel.tsx) so the admin overview and the kiosk agree on the same
 * cube (e.g. an overfull bin reads "263%", not "100%").
 *
 * NOTE: this is intentionally NOT the D-03 clamp. D-03 clamps the `--fill`
 * *shading* at 1.0 so the colour never oversaturates; the displayed number must
 * still reflect the real overflow.
 */
function fillPct(fillLevel: number): number {
  return Math.min(Math.round(fillLevel * 100), 999)
}

/** Popover content for a given cube. */
function popoverContent(
  cube: AdminCube | undefined,
  id: string,
): React.ReactNode {
  if (!cube || cube.is_empty) {
    return (
      <>
        <span className="locator-fill-popover-id">{id}</span>
        <span className="locator-fill-popover-empty">Empty bin</span>
      </>
    )
  }
  const pct = fillPct(cube.fill_level)
  return (
    <>
      <span className="locator-fill-popover-id">{id}</span>
      <span className="locator-fill-popover-data">
        {cube.record_count} records · {pct}%
      </span>
    </>
  )
}

export function LocatorHeader({
  unitId,
  row,
  col,
  shelfName = 'SHELF A',
  binNumber,
  rows = 4,
  cols = 4,
  cubes,
}: LocatorHeaderProps) {
  // Map keyed "${row}-${col}" filtered to this unit for O(1) per-cell lookup
  const cubeMap = useMemo(() => {
    const m = new Map<string, AdminCube>()
    cubes?.forEach((c) => {
      if (c.unit_id === unitId) m.set(`${c.row}-${c.col}`, c)
    })
    return m
  }, [cubes, unitId])

  // Active popover: null = closed, number = r * cols + c index
  const [activeIdx, setActiveIdx] = useState<number | null>(null)

  // Tap-away dismiss: pointerdown outside .locator-mini-grid-wrap closes popover
  useEffect(() => {
    if (activeIdx === null) return
    function handleTapAway(e: PointerEvent) {
      if (!(e.target as Element).closest('.locator-mini-grid-wrap')) {
        setActiveIdx(null)
      }
    }
    document.addEventListener('pointerdown', handleTapAway)
    return () => document.removeEventListener('pointerdown', handleTapAway)
  }, [activeIdx])

  // Escape dismiss
  useEffect(() => {
    if (activeIdx === null) return
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setActiveIdx(null)
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [activeIdx])

  // Derive active cell details for popover rendering
  const activeRow = activeIdx !== null ? Math.floor(activeIdx / cols) : -1
  const activeCol = activeIdx !== null ? activeIdx % cols : -1
  const activeCube =
    activeIdx !== null ? cubeMap.get(`${activeRow}-${activeCol}`) : undefined
  const activeBinId =
    activeIdx !== null ? binId(unitId, activeRow, activeCol, cols) : ''

  return (
    <div className="locator-header">
      <div className="locator-header-labels">
        <span className="locator-header-shelf">{shelfName}</span>
        {binNumber != null && (
          <span className="locator-header-bin">BIN {binNumber}</span>
        )}
      </div>
      <div className="locator-mini-grid-wrap">
        <div
          className="locator-mini-grid"
          style={{ gridTemplateColumns: `repeat(${cols}, var(--gruvax-cell-size-sm))` }}
          aria-label={
            row !== -1
              ? `Mini Kallax — edited bin at row ${row + 1}, col ${col + 1}`
              : 'Mini Kallax — shelf fill overview'
          }
        >
          {Array.from({ length: rows }, (_, r) =>
            Array.from({ length: cols }, (_, c) => {
              const cube = cubeMap.get(`${r}-${c}`)
              const isEdited = r === row && c === col && row !== -1
              const isEmpty = cube?.is_empty ?? false
              const fillLevel = Math.min(cube?.fill_level ?? 0, 1)

              const cellClass = isEdited
                ? 'locator-cell locator-cell--lit'
                : isEmpty
                  ? 'locator-cell locator-cell--empty'
                  : cubes !== undefined
                    ? 'locator-cell locator-cell--fill'
                    : 'locator-cell locator-cell--dim'

              const cellStyle =
                !isEdited && !isEmpty && cubes !== undefined
                  ? ({ '--fill': fillLevel } as React.CSSProperties)
                  : undefined

              const idx = r * cols + c
              const isActive = activeIdx === idx

              const id = binId(unitId, r, c, cols)
              const ariaDetail = isEdited
                ? 'edited bin'
                : isEmpty
                  ? 'empty'
                  : `${fillPct(cube?.fill_level ?? 0)}% full`

              return (
                <button
                  key={`${r}-${c}`}
                  type="button"
                  className={cellClass}
                  style={cellStyle}
                  data-row={r}
                  data-col={c}
                  aria-label={`${id}: ${ariaDetail}`}
                  aria-pressed={isActive}
                  onClick={() =>
                    setActiveIdx((prev) => (prev === idx ? null : idx))
                  }
                />
              )
            })
          )}
        </div>
        {activeIdx !== null && (
          <div
            className="locator-fill-popover"
            role="tooltip"
            aria-live="polite"
            style={{
              top:
                activeRow < 2
                  ? `calc((${activeRow + 1}) * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)) + 2px)`
                  : undefined,
              bottom:
                activeRow >= 2
                  ? `calc((${rows - activeRow}) * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)) + 2px)`
                  : undefined,
              // Horizontal flip (mirrors the vertical flip above): left-half
              // columns anchor left and open rightward; right-half columns anchor
              // right and open leftward so the popover never overflows the grid's
              // right edge / viewport (WR-02).
              left:
                activeCol < cols / 2
                  ? `calc(${activeCol} * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)))`
                  : undefined,
              right:
                activeCol >= cols / 2
                  ? `calc(${cols - 1 - activeCol} * (var(--gruvax-cell-size-sm) + var(--gruvax-cell-gap-sm)))`
                  : undefined,
            }}
          >
            {popoverContent(activeCube, activeBinId)}
          </div>
        )}
      </div>
    </div>
  )
}

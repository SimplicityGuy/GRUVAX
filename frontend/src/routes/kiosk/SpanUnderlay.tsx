/**
 * SpanUnderlay — connecting band drawn UNDER all cubes in a label span.
 *
 * Visually links spanned cubes as one contiguous run. Renders at z-index 0
 * so the primary lit cell (z-index 1) is always above — lit-cell rule (D-04).
 *
 * Geometry is computed from cellSize/cellGap props (from design token constants)
 * rather than getBoundingClientRect() — deterministic and Pi-stable.
 *
 * Row/unit-wrapping spans produce multiple band segments (one per unique
 * (unit_id, row) pair) rather than a single band crossing the unit gap.
 *
 * Design tokens only — no hardcoded hex.
 */

import type { CSSProperties } from 'react'
import type { CubeRef } from '../../api/types'

interface SpanUnderlayProps {
  /** Sorted cubes in the label span (unit_id, row, col) — from /api/locate */
  labelSpan: CubeRef[]
  /** Cell size in px — var(--gruvax-cell-size-xl) = 80 (from gridGeometry.ts) */
  cellSize: number
  /** Cell gap in px — var(--gruvax-cell-gap-xl) = 12 (from gridGeometry.ts) */
  cellGap: number
}

interface BandSegment {
  unitId: number
  row: number
  colMin: number
  colMax: number
}

/**
 * Group labelSpan cubes into one segment per (unit_id, row).
 * Each segment produces one pill-shaped band.
 */
function groupIntoSegments(labelSpan: CubeRef[]): BandSegment[] {
  const segmentMap = new Map<string, BandSegment>()

  for (const cube of labelSpan) {
    const key = `${cube.unit_id}-${cube.row}`
    const existing = segmentMap.get(key)
    if (existing) {
      if (cube.col < existing.colMin) existing.colMin = cube.col
      if (cube.col > existing.colMax) existing.colMax = cube.col
    } else {
      segmentMap.set(key, {
        unitId: cube.unit_id,
        row: cube.row,
        colMin: cube.col,
        colMax: cube.col,
      })
    }
  }

  return Array.from(segmentMap.values())
}

/**
 * Compute the pixel offset of a unit within the shelf-area parent.
 *
 * Units are laid out left-to-right in DOM order by unit_id. Each unit
 * occupies a shelf-grid of 4 columns × (cellSize + cellGap) − cellGap wide.
 * Units are separated by var(--gruvax-space-6) = 32px gap (flex gap on .shelf-area).
 *
 * For now we derive the unit x-offset from its index in the sorted units.
 * SpanUnderlay receives the sorted unit list implicitly via the labelSpan data,
 * which is already sorted by (unit_id, row, col). We compute the x-offset
 * from the unit_id assuming unit ordering follows unit_id (the backend sorts by
 * unit ordering which maps 1:1 with unit_id for typical Kallax setups).
 *
 * The grid width for one unit = 4 × cellSize + 3 × cellGap (4 cols, 3 gaps).
 * The shelf-area flex gap between units = 32px (--gruvax-space-6).
 */
const SHELF_FLEX_GAP = 32 // --gruvax-space-6 in px; shelf-area gap between units
const GRID_COLS = 4

function unitColumnOffset(unitId: number, cellSize: number, cellGap: number): number {
  // unit_id is 1-based; convert to 0-based index
  const unitIndex = unitId - 1
  const gridWidth = GRID_COLS * cellSize + (GRID_COLS - 1) * cellGap
  return unitIndex * (gridWidth + SHELF_FLEX_GAP)
}

/**
 * SpanUnderlay renders absolutely-positioned pill bands connecting spanned cubes.
 * It must be placed inside a position:relative container (the .shelf-area or
 * per-unit shelf-section wrapper).
 *
 * No GSAP here — KioskView owns the timeline (opacity 0 → 0.60 animation).
 */
export function SpanUnderlay({ labelSpan, cellSize, cellGap }: SpanUnderlayProps) {
  if (labelSpan.length < 2) return null

  const segments = groupIntoSegments(labelSpan)

  return (
    <>
      {segments.map((seg) => {
        const xOffset = unitColumnOffset(seg.unitId, cellSize, cellGap)

        // left: start at the left edge of colMin
        const left = xOffset + seg.colMin * (cellSize + cellGap)
        // width: from colMin left edge to colMax right edge
        const width = (seg.colMax - seg.colMin) * (cellSize + cellGap) + cellSize
        // top: vertically centered in the bottom 30% of the cube row
        // Formula from UI-SPEC: unitRowOffset + row × (cellSize + cellGap) + cellSize × 0.75
        // unitRowOffset = 0 because each shelf-grid is its own relative container
        // (SpanUnderlay is positioned within the shelf-section's shelf-grid context)
        const top = seg.row * (cellSize + cellGap) + cellSize * 0.75 - 6 // 6 = half of band height (12px)

        const style: CSSProperties = {
          left: `${left}px`,
          width: `${width}px`,
          top: `${top}px`,
          // Color/border come from .span-underlay__band in kiosk.css (tokens only)
        }

        return (
          <div
            key={`${seg.unitId}-${seg.row}`}
            className="span-underlay__band"
            style={style}
            aria-hidden="true"
          />
        )
      })}
    </>
  )
}

import type { CubeRef, CubeState, SubInterval } from '../../api/types'
import { FillBar } from './FillBar'
import { SubCubeBar } from './SubCubeBar'

interface CubeProps {
  unitId: number
  row: number
  col: number
  state: CubeState
  /** Address label, e.g. "A1", "C3" — Shelf A rows A-D, Shelf B rows E-H */
  address: string
  /**
   * Sub-cube position interval from /api/locate.
   * When provided and this cube is the primary lit cube, renders a SubCubeBar.
   * When provided and this cube is the next_cube (crosses_boundary companion),
   * also renders a companion SubCubeBar. (CUBE-04 / D-01)
   */
  subInterval?: SubInterval | null
  /** Position confidence — passed through to SubCubeBar for opacity (D-01) */
  confidence?: number
  /**
   * When true, this cube is the next_cube companion for a crosses_boundary interval.
   * Renders a SubCubeBar from 0 to interval.end × 100% on the left edge. (CUBE-04)
   */
  isCompanionBar?: boolean
  /**
   * Fill level 0.0–1.0+ from the collection snapshot (CUBE-07, D-13).
   * When provided and > 0, renders a FillBar at the bottom edge of the cell.
   * 0 or undefined → no bar rendered (is_empty / unknown cubes).
   */
  fillLevel?: number
  /**
   * Called when the user taps this cube (CUBE-09, D-14).
   * Passes back a CubeRef so KioskView can open the contents panel.
   */
  onTap?: (cube: CubeRef) => void
}

/**
 * A single Kallax cube cell.
 *
 * State is driven via the data-state attribute so CSS transitions can target it
 * cleanly without JavaScript animation logic. The address overlay is always
 * rendered in the top-left corner (CUBE-06).
 *
 * data-state ∈ { dim | lit | empty | hover }
 * See kiosk.css for the state-driven transition rules.
 *
 * Phase 2: When subInterval is present and this is the primary (lit) cube or
 * the companion cube for a crosses_boundary interval, renders SubCubeBar inside.
 */
export function Cube({
  unitId,
  row,
  col,
  state,
  address,
  subInterval,
  confidence = 0,
  isCompanionBar = false,
  fillLevel,
  onTap,
}: CubeProps) {
  // Determine whether to render a SubCubeBar in this cube
  const isPrimary = state === 'lit' && subInterval != null
  const isCompanion = isCompanionBar && subInterval != null && subInterval.crosses_boundary

  const shouldRenderBar = isPrimary || isCompanion

  let barInterval = subInterval
  if (isCompanion && subInterval != null && subInterval.crosses_boundary) {
    // Companion bar: from 0 to subInterval.end (left edge of this cube)
    barInterval = {
      start: 0,
      end: subInterval.end,
      crosses_boundary: false,
    }
  }

  const isSingleton = barInterval != null && barInterval.start === 0 && barInterval.end === 1

  const handleClick = onTap
    ? () => onTap({ unit_id: unitId, row, col })
    : undefined

  return (
    <div
      className="cube"
      data-state={state}
      data-unit-id={unitId}
      data-row={row}
      data-col={col}
      aria-label={`Cube ${address}`}
      onClick={handleClick}
      style={onTap ? { cursor: 'pointer' } : undefined}
    >
      <span className="cube__address">{address}</span>
      {shouldRenderBar && barInterval != null && (
        <SubCubeBar
          interval={barInterval}
          confidence={confidence}
          isSingleton={isSingleton}
        />
      )}
      {/* Fill-level bar at the bottom edge (CUBE-07, D-13) — only when fill > 0 */}
      {fillLevel != null && fillLevel > 0 && (
        <FillBar fillLevel={fillLevel} heightPx={4} />
      )}
    </div>
  )
}

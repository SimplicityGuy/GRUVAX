import type { CubeState, SubInterval } from '../../api/types'
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
export function Cube({ unitId, row, col, state, address, subInterval, confidence = 0, isCompanionBar = false }: CubeProps) {
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

  return (
    <div
      className="cube"
      data-state={state}
      data-unit-id={unitId}
      data-row={row}
      data-col={col}
      aria-label={`Cube ${address}`}
    >
      <span className="cube__address">{address}</span>
      {shouldRenderBar && barInterval != null && (
        <SubCubeBar
          interval={barInterval}
          confidence={confidence}
          isSingleton={isSingleton}
        />
      )}
    </div>
  )
}

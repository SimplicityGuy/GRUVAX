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
   */
  subInterval?: SubInterval | null
  /** Position confidence — passed through to SubCubeBar for opacity (D-01) */
  confidence?: number
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
  /**
   * When true, renders a decorative ambient shimmer overlay on this cube (D-01/D-02/RTM-04).
   * The overlay is opacity-only — it never recolors the cube, never sets data-state,
   * and is aria-hidden so assistive technology ignores it (D-02: never alter data-state).
   * Default false.
   */
  shimmerActive?: boolean
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
 * Phase 2: Only the primary (lit) cube renders the supplied position band.
 * The label-span underlay links neighboring cubes without inventing a position.
 */
export function Cube({
  unitId,
  row,
  col,
  state,
  address,
  subInterval,
  confidence = 0,
  fillLevel,
  onTap,
  shimmerActive = false,
}: CubeProps) {
  const shouldRenderBar = state === 'lit' && subInterval != null
  const isSingleton = subInterval != null && subInterval.start === 0 && subInterval.end === 1

  const handleClick = onTap ? () => onTap({ unit_id: unitId, row, col }) : undefined

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
      {shouldRenderBar && subInterval != null && (
        <SubCubeBar interval={subInterval} confidence={confidence} isSingleton={isSingleton} />
      )}
      {/* Fill-level bar at the bottom edge (CUBE-07, D-13) — only when fill > 0 */}
      {fillLevel != null && fillLevel > 0 && <FillBar fillLevel={fillLevel} heightPx={4} />}
      {/* Shimmer overlay — decorative ambient cue while admin is mid-edit (D-01/D-02/RTM-04).
          aria-hidden: purely decorative, not data-state — never recolors the cube. */}
      {shimmerActive && <div className="cube-shimmer-overlay" aria-hidden="true" />}
    </div>
  )
}

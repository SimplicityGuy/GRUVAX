import type { CubeState } from '../../api/types'

interface CubeProps {
  unitId: number
  row: number
  col: number
  state: CubeState
  /** Address label, e.g. "A1", "C3" — Shelf A rows A-D, Shelf B rows E-H */
  address: string
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
 */
export function Cube({ unitId, row, col, state, address }: CubeProps) {
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
    </div>
  )
}

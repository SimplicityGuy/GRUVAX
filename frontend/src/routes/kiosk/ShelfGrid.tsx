import { Cube } from './Cube'
import type { CubeRef, CubeState, Unit } from '../../api/types'

interface ShelfGridProps {
  unit: Unit
  /** 0-based shelf index used to assign row letter labels (0 → A-D, 1 → E-H, etc.) */
  shelfIndex: number
  /** Which cube is currently lit — null if none */
  litCube: CubeRef | null
}

/**
 * 4×4 CSS Grid for one Kallax unit.
 *
 * Column/row sizing driven by var(--gruvax-cell-size-xl) and gap by
 * var(--gruvax-cell-gap-xl) — never hardcoded px values.
 *
 * Address scheme:
 *   Shelf A (shelfIndex=0) rows A-D, columns 1-4 → "A1".."D4"
 *   Shelf B (shelfIndex=1) rows E-H, columns 1-4 → "E1".."H4"
 * (CUBE-06)
 */
export function ShelfGrid({ unit, shelfIndex, litCube }: ShelfGridProps) {
  const ROW_LETTERS = 'ABCDEFGH'
  const baseRowOffset = shelfIndex * 4

  const cells: React.ReactNode[] = []

  for (let r = 0; r < unit.rows; r++) {
    for (let c = 0; c < unit.cols; c++) {
      const rowLetter = ROW_LETTERS[baseRowOffset + r] ?? '?'
      const colNumber = c + 1
      const address = `${rowLetter}${colNumber}`

      // 1-based row/col to match the API CubeRef convention
      const rowApi = r + 1
      const colApi = c + 1

      let state: CubeState = 'dim'
      if (
        litCube &&
        litCube.unit_id === unit.id &&
        litCube.row === rowApi &&
        litCube.col === colApi
      ) {
        state = 'lit'
      }

      cells.push(
        <Cube
          key={address}
          unitId={unit.id}
          row={rowApi}
          col={colApi}
          state={state}
          address={address}
        />,
      )
    }
  }

  return <div className="shelf-grid">{cells}</div>
}

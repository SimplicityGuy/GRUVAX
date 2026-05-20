import { Cube } from './Cube'
import type { CubeRef, CubeState, Unit } from '../../api/types'

interface ShelfGridProps {
  unit: Unit
  /** 0-based shelf index used to assign row letter labels (0 → A-D, 1 → E-H, etc.) */
  shelfIndex: number
  /** Which cube is currently lit — null if none */
  litCube: CubeRef | null
  /** Set of cube keys flagged as empty, formatted "unitId-row-col" (0-based) */
  emptyCubes?: Set<string>
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
 *
 * API convention: row and col are 0-based (matching cube_boundaries seed).
 * The human-readable address label (rowLetter + (c+1)) is display-only.
 */
export function ShelfGrid({ unit, shelfIndex, litCube, emptyCubes }: ShelfGridProps) {
  const ROW_LETTERS = 'ABCDEFGH'
  const baseRowOffset = shelfIndex * 4

  const cells: React.ReactNode[] = []

  for (let r = 0; r < unit.rows; r++) {
    for (let c = 0; c < unit.cols; c++) {
      // Human-readable address label — display only, not used for API matching
      const rowLetter = ROW_LETTERS[baseRowOffset + r] ?? '?'
      const colNumber = c + 1
      const address = `${rowLetter}${colNumber}`

      // API convention: row/col are 0-based — match directly against loop indices
      const isLit =
        litCube != null &&
        litCube.unit_id === unit.id &&
        litCube.row === r &&
        litCube.col === c

      const isEmpty =
        !isLit && (emptyCubes?.has(`${unit.id}-${r}-${c}`) ?? false)

      let state: CubeState = 'dim'
      if (isLit) state = 'lit'
      else if (isEmpty) state = 'empty'

      cells.push(
        <Cube
          key={address}
          unitId={unit.id}
          row={r}
          col={c}
          state={state}
          address={address}
        />,
      )
    }
  }

  return <div className="shelf-grid">{cells}</div>
}

import { Cube } from './Cube'
import { SpanUnderlay } from './SpanUnderlay'
import { CELL_GAP_XL, CELL_SIZE_XL } from './gridGeometry'
import type { CubeRef, CubeState, SubInterval, Unit } from '../../api/types'

interface ShelfGridProps {
  unit: Unit
  /** 0-based shelf index used to assign row letter labels (0 → A-D, 1 → E-H, etc.) */
  shelfIndex: number
  /** Which cube is currently lit — null if none */
  litCube: CubeRef | null
  /** Set of cube keys flagged as empty, formatted "unitId-row-col" (0-based) */
  emptyCubes?: Set<string>
  /**
   * Label span — all cubes occupied by the label (sorted unit_id,row,col).
   * When length > 1, renders SpanUnderlay connecting the spanned cubes. (CUBE-03)
   */
  labelSpan?: CubeRef[]
  /**
   * Sub-cube position interval from /api/locate.
   * Passed to the primary lit Cube to render SubCubeBar. (CUBE-04)
   */
  subCubeInterval?: SubInterval | null
  /** Position confidence 0.0–1.0 — passed to SubCubeBar for opacity (D-01) */
  confidence?: number
  /**
   * Fill level per cube, keyed "unitId-row-col" (0-based).
   * When present, FillBar renders at the bottom of each cube cell (CUBE-07, D-13).
   * Cubes not in the map render no fill bar.
   */
  fillLevels?: Map<string, number>
  /**
   * Called when the user taps a cube (CUBE-09, D-14).
   * KioskView uses this to open the CubeContentsPanel for the tapped cube.
   */
  onCubeTap?: (cube: CubeRef) => void
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
 *
 * Phase 2: Renders SpanUnderlay as a sibling of the shelf-grid when the label
 * spans multiple cubes. Passes subCubeInterval/confidence to the lit Cube.
 */
export function ShelfGrid({
  unit,
  shelfIndex,
  litCube,
  emptyCubes,
  labelSpan = [],
  subCubeInterval = null,
  confidence = 0,
  fillLevels,
  onCubeTap,
}: ShelfGridProps) {
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

      // Determine if this cube is the companion bar (crosses_boundary next_cube)
      const isCompanion =
        subCubeInterval?.crosses_boundary === true &&
        subCubeInterval.next_cube != null &&
        subCubeInterval.next_cube.unit_id === unit.id &&
        subCubeInterval.next_cube.row === r &&
        subCubeInterval.next_cube.col === c

      const cubeKey = `${unit.id}-${r}-${c}`
      const cubeFillLevel = fillLevels?.get(cubeKey)

      cells.push(
        <Cube
          key={address}
          unitId={unit.id}
          row={r}
          col={c}
          state={state}
          address={address}
          subInterval={isLit || isCompanion ? subCubeInterval : null}
          confidence={isLit || isCompanion ? confidence : 0}
          isCompanionBar={isCompanion}
          fillLevel={cubeFillLevel}
          onTap={onCubeTap}
        />,
      )
    }
  }

  // Cubes in this unit that belong to the label span
  const unitLabelSpan = labelSpan.filter((c) => c.unit_id === unit.id)
  const hasSpan = unitLabelSpan.length > 1

  return (
    <div style={{ position: 'relative' }}>
      <div className="shelf-grid">{cells}</div>
      {hasSpan && (
        <SpanUnderlay
          labelSpan={unitLabelSpan}
          cellSize={CELL_SIZE_XL}
          cellGap={CELL_GAP_XL}
        />
      )}
    </div>
  )
}

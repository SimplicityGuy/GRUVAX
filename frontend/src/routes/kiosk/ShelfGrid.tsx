import { Cube } from './Cube'
import { rowLetter, unitRowOffset } from '../../lib/shelf'
import { SpanUnderlay } from './SpanUnderlay'
import { CELL_GAP_XL, CELL_SIZE_XL } from './gridGeometry'
import type { CubeRef, CubeState, SubInterval, Unit } from '../../api/types'

interface ShelfGridProps {
  unit: Unit
  /** Full configured layout; row addresses follow ordering and actual unit row counts. */
  units?: readonly Unit[]
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
  /**
   * Set of cube keys (format "unit-row-col") that are currently in shimmer state
   * (admin is mid-edit — Phase 4 / D-01/D-02/RTM-04).
   * Each matching Cube receives shimmerActive=true to render the decorative overlay.
   * Defaults to an empty Set so callers without shimmer support stay unaffected.
   */
  shimmerCubes?: Set<string>
}

/**
 * CSS Grid using the configured dimensions of one Kallax unit.
 *
 * Column/row sizing driven by var(--gruvax-cell-size-xl) and gap by
 * var(--gruvax-cell-gap-xl) — never hardcoded px values.
 *
 * Address scheme:
 *   Rows use cumulative configured row counts in unit ordering, continuing past Z.
 *   Addresses are display-only; React keys use durable unit/row/col coordinates.
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
  units = [unit],
  litCube,
  emptyCubes,
  labelSpan = [],
  subCubeInterval = null,
  confidence = 0,
  fillLevels,
  onCubeTap,
  shimmerCubes = new Set(),
}: ShelfGridProps) {
  const baseRowOffset = unitRowOffset(unit.id, units)

  const cells: React.ReactNode[] = []

  for (let r = 0; r < unit.rows; r++) {
    for (let c = 0; c < unit.cols; c++) {
      // Human-readable address label — display only, not used for API matching
      const letter = rowLetter(baseRowOffset + r)
      const colNumber = c + 1
      const address = `${letter}${colNumber}`

      // API convention: row/col are 0-based — match directly against loop indices
      const isLit =
        litCube != null && litCube.unit_id === unit.id && litCube.row === r && litCube.col === c

      const isEmpty = !isLit && (emptyCubes?.has(`${unit.id}-${r}-${c}`) ?? false)

      let state: CubeState = 'dim'
      if (isLit) state = 'lit'
      else if (isEmpty) state = 'empty'

      const cubeKey = `${unit.id}-${r}-${c}`
      const cubeFillLevel = fillLevels?.get(cubeKey)

      cells.push(
        <Cube
          key={cubeKey}
          unitId={unit.id}
          row={r}
          col={c}
          state={state}
          address={address}
          subInterval={isLit ? subCubeInterval : null}
          confidence={isLit ? confidence : 0}
          fillLevel={cubeFillLevel}
          onTap={onCubeTap}
          shimmerActive={shimmerCubes.has(`${unit.id}-${r}-${c}`)}
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
        <SpanUnderlay labelSpan={unitLabelSpan} cellSize={CELL_SIZE_XL} cellGap={CELL_GAP_XL} />
      )}
    </div>
  )
}

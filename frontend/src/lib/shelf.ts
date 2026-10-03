import type { CubeRef, Unit } from '../api/types'

/** Ordering is display-only; ties use stable IDs, never their numeric magnitude as an ordinal. */
export function orderedUnits(units: readonly Unit[]): Unit[] {
  return [...units].sort((a, b) => a.ordering - b.ordering || a.id - b.id)
}

/** Zero-based alphabetic index: A..Z, AA..AZ, BA..., without a row ceiling. */
export function rowLetter(index: number): string {
  let letters = ''
  for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) {
    letters = String.fromCharCode(65 + ((value - 1) % 26)) + letters
  }
  return letters
}

/** Cumulative actual rows before the selected unit in physical ordering. */
export function unitRowOffset(unitId: number, units: readonly Unit[]): number {
  let offset = 0
  for (const unit of orderedUnits(units)) {
    if (unit.id === unitId) return offset
    offset += unit.rows
  }
  return 0
}

/** Shared kiosk grid/panel address; cube coordinates remain the durable identity. */
export function cubeAddress(cube: CubeRef, units: readonly Unit[]): string {
  return `${rowLetter(unitRowOffset(cube.unit_id, units) + cube.row)}${cube.col + 1}`
}

/** Configured names win; an unnamed shelf uses its ordered position, never its ID. */
export function shelfName(unitId: number, units: readonly Unit[]): string {
  const ordered = orderedUnits(units)
  const index = ordered.findIndex((unit) => unit.id === unitId)
  if (index < 0) return 'SHELF'
  return ordered[index].display_name.trim() || `SHELF ${rowLetter(index)}`
}

import type { CubeRef, Unit } from '../api/types'

/**
 * Shelf naming helpers — canonical letter-notation for Kallax units.
 *
 * Unit 1 → "A", Unit 2 → "B", … (String.fromCharCode(64 + unitId))
 *
 * Kiosk convention per ShelfLabel.tsx and ShelfGrid tests: a unit is always
 * displayed as "SHELF A" / "SHELF B". Use these helpers everywhere a shelf
 * or unit ID is shown in the admin UI to keep naming consistent.
 */

/**
 * Return the letter for a unit ID: 1 → "A", 2 → "B", etc.
 * Supports up to 26 units (the full alphabet).
 */
export function shelfLetter(unitId: number): string {
  return String.fromCharCode(64 + unitId)
}

/**
 * Return the full display name for a unit: 1 → "SHELF A", 2 → "SHELF B", etc.
 */
export function shelfName(unitId: number): string {
  return `SHELF ${shelfLetter(unitId)}`
}

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

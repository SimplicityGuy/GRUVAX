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

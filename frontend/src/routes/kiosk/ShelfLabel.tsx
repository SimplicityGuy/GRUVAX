interface ShelfLabelProps {
  name: string
}

/**
 * Shelf identifier — "SHELF A" / "SHELF B"
 * Barlow Condensed 900 24px ALL CAPS, per 01-UI-SPEC.md §Typography.
 * All sizing/color from CSS tokens in kiosk.css.
 */
export function ShelfLabel({ name }: ShelfLabelProps) {
  return <div className="shelf-label">{name}</div>
}

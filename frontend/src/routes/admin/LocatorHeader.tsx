/**
 * LocatorHeader — compact 4×4 mini-Kallax header for the segment editor.
 *
 * Shows the edited bin lit yellow (--gruvax-cell-lit + LED glow) and all
 * other cells dim. Purely display — non-interactive.
 *
 * Uses --gruvax-cell-size-sm (28px) cells, --gruvax-cell-gap-sm (4px) gap.
 * Design tokens only — no hardcoded hex.
 */

interface LocatorHeaderProps {
  unitId: number
  /** 0-based row of the edited bin */
  row: number
  /** 0-based col of the edited bin */
  col: number
  /** Display name for the shelf, e.g. "SHELF A" */
  shelfName?: string
  /** Human-readable bin number (1-based) */
  binNumber?: number
  /** Grid dimensions (default 4×4 for Kallax) */
  rows?: number
  cols?: number
}

export function LocatorHeader({
  row,
  col,
  shelfName = 'SHELF A',
  binNumber,
  rows = 4,
  cols = 4,
}: LocatorHeaderProps) {
  return (
    <div className="locator-header">
      <div className="locator-header-labels">
        <span className="locator-header-shelf">{shelfName}</span>
        {binNumber != null && (
          <span className="locator-header-bin">BIN {binNumber}</span>
        )}
      </div>
      <div
        className="locator-mini-grid"
        style={{ gridTemplateColumns: `repeat(${cols}, var(--gruvax-cell-size-sm))` }}
        aria-label={`Mini Kallax — edited bin at row ${row + 1}, col ${col + 1}`}
      >
        {Array.from({ length: rows }, (_, r) =>
          Array.from({ length: cols }, (_, c) => {
            const isEdited = r === row && c === col
            return (
              <div
                key={`${r}-${c}`}
                className={`locator-cell${isEdited ? ' locator-cell--lit' : ' locator-cell--dim'}`}
                aria-label={isEdited ? 'Edited bin' : undefined}
                aria-current={isEdited ? 'true' : undefined}
              />
            )
          })
        )}
      </div>
    </div>
  )
}

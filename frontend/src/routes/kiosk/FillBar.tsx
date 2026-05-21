/**
 * FillBar — horizontal fill-level indicator for a Kallax cube.
 *
 * Rendered at the bottom edge of each cube cell (CUBE-07, UI-SPEC §I).
 * Presentational only — data-attribute / CSS-custom-property driven.
 *
 * Fill-level color rules (UI-SPEC §I / §C):
 *   0        → no bar (transparent; is_empty cubes show nothing)
 *   1–79%    → --gruvax-blue-light
 *   80–100%  → --gruvax-yellow
 *   >100%    → --gruvax-error  (overstuffed)
 *
 * Design tokens only — never hardcode hex values (CLAUDE.md constraint).
 *
 * Analog: SubCubeBar.tsx (same presentational + token-driven pattern).
 */

interface FillBarProps {
  /** Fill level: 0.0 = empty, 1.0 = 100% full, >1.0 = overstuffed */
  fillLevel: number
  /** Bar height in px — 4 on the kiosk main grid (80px cells), 3 on admin compact grid */
  heightPx?: number
}

/**
 * Horizontal fill-level bar at the bottom of a cube cell.
 *
 * Width is clamped to [0, 100%] so overstuffed cubes still fill the cell
 * (the color change to --gruvax-error communicates overstuffed state).
 * aria-hidden because the fill percentage is conveyed in the panel heading
 * when the user taps the cube.
 */
export function FillBar({ fillLevel, heightPx = 4 }: FillBarProps) {
  if (fillLevel <= 0) return null

  const color =
    fillLevel < 0.8
      ? 'var(--gruvax-blue-light)'
      : fillLevel <= 1.0
        ? 'var(--gruvax-yellow)'
        : 'var(--gruvax-error)'

  const widthPct = Math.min(fillLevel, 1.0) * 100

  return (
    <div
      className="fill-bar"
      style={{
        width: `${widthPct}%`,
        height: `${heightPx}px`,
        backgroundColor: color,
      }}
      aria-hidden="true"
    />
  )
}

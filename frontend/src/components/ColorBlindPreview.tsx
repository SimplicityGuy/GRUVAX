/**
 * ColorBlindPreview — in-SPA color-blind simulation preview.
 *
 * Renders three small swatches (DEUTERANOPIA / PROTANOPIA / TRITANOPIA)
 * computed via 3×3 RGB matrix multiplication. Zero new dependencies (D-18).
 *
 * Matrix math is in src/lib/colorblind.ts so this file only exports components
 * (react-refresh/only-export-components compliance).
 *
 * Usage:
 *   <ColorBlindPreview hex="#FFD700" />
 *
 * Phase 6 / LED-05 / D-18
 */

import { CB_TYPES, simulateColorBlindness } from '../lib/colorblind'

// ── Component ─────────────────────────────────────────────────────────────────

interface ColorBlindPreviewProps {
  /** The hex color to simulate (#RRGGBB format) */
  hex: string
}

/**
 * ColorBlindPreview renders three small color swatches showing how the given
 * hex color appears to people with deuteranopia, protanopia, and tritanopia.
 *
 * Pure computation — no server calls, no new packages (D-18).
 * Placed next to each color picker in the admin LEDs section so an
 * inaccessible color pair is caught at pick time (LED-05).
 */
export function ColorBlindPreview({ hex }: ColorBlindPreviewProps) {
  return (
    <div className="colorblind-preview" aria-label="Color-blind simulation preview">
      {CB_TYPES.map(({ type, label }) => {
        const simulated = simulateColorBlindness(hex, type)
        return (
          <div key={type} className="colorblind-preview__swatch" title={type}>
            <div
              className="colorblind-preview__color"
              style={{ backgroundColor: simulated }}
              role="img"
              aria-label={`${label}: ${simulated}`}
            />
            <span className="colorblind-preview__label">{label}</span>
          </div>
        )
      })}
    </div>
  )
}

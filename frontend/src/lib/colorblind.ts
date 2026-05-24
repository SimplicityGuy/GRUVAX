/**
 * Color-blind simulation utility — pure functions, zero new dependencies (D-18).
 *
 * Matrices: colorjack.com matrices via gist.github.com/Lokno/df7c3bfdc9ad32558bb7
 * (Vienot 1999 algorithm, well-established color-blindness simulation basis)
 *
 * Extracted to lib/ so ColorBlindPreview.tsx only exports components
 * (react-refresh/only-export-components fast-refresh requirement).
 *
 * Phase 6 / LED-05 / D-18
 */

// ── Color-blind simulation matrices (VERBATIM from RESEARCH.md §Code Examples) ──

const MATRICES = {
  deuteranopia: [
    [0.625, 0.375, 0.000],
    [0.700, 0.300, 0.000],
    [0.000, 0.300, 0.700],
  ],
  protanopia: [
    [0.567, 0.433, 0.000],
    [0.558, 0.442, 0.000],
    [0.000, 0.242, 0.758],
  ],
  tritanopia: [
    [0.950, 0.050, 0.000],
    [0.000, 0.433, 0.567],
    [0.000, 0.475, 0.525],
  ],
} as const

export type ColorBlindType = keyof typeof MATRICES

/**
 * Simulate how a hex color appears under a color vision deficiency.
 *
 * Returns the simulated hex string, or the original color on parse failure
 * (guards against malformed hex from the color picker intermediate state).
 */
export function simulateColorBlindness(
  hex: string,
  type: ColorBlindType,
): string {
  // Guard against malformed hex (e.g. empty string or partial input)
  if (!/^#[0-9A-Fa-f]{6}$/.test(hex)) {
    return hex
  }
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const m = MATRICES[type]
  const nr = Math.min(255, Math.max(0, Math.round((m[0][0] * r + m[0][1] * g + m[0][2] * b) * 255)))
  const ng = Math.min(255, Math.max(0, Math.round((m[1][0] * r + m[1][1] * g + m[1][2] * b) * 255)))
  const nb = Math.min(255, Math.max(0, Math.round((m[2][0] * r + m[2][1] * g + m[2][2] * b) * 255)))
  return `#${nr.toString(16).padStart(2, '0')}${ng.toString(16).padStart(2, '0')}${nb.toString(16).padStart(2, '0')}`
}

export const CB_TYPES: { type: ColorBlindType; label: string }[] = [
  { type: 'deuteranopia', label: 'DEUTAN' },
  { type: 'protanopia', label: 'PROTAN' },
  { type: 'tritanopia', label: 'TRITAN' },
]

/**
 * Grid geometry constants derived from design/gruvax-design-tokens.json.
 *
 * JSON keys: grid.cell.sizeXl ("80px") and grid.gap.xl ("12px").
 * Used by SpanUnderlay for coordinate math — no runtime getBoundingClientRect() calls.
 * Passed as props so tests can exercise the geometry math without touching the DOM.
 */

// From design/gruvax-design-tokens.json: grid.cell.sizeXl = "80px"
export const CELL_SIZE_XL = 80

// From design/gruvax-design-tokens.json: grid.gap.xl = "12px"
export const CELL_GAP_XL = 12

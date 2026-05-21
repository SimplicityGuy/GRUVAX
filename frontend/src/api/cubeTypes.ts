/**
 * Cube-contents types for GET /api/cubes/{unit_id}/{row}/{col}.
 *
 * Isolated from types.ts to preserve exclusive file-ownership between
 * plan 03 (kiosk reveal) and plans 02/04 (admin) which both run in Wave 3.
 * Any plan-04 file that needs these types imports from ./cubeTypes, not ./types.
 *
 * Public endpoint — no admin auth required (D-15).
 */

export interface SampleRecord {
  release_id: number
  label: string
  catalog_number: string
}

export interface CubeContentsResponse {
  unit_id: number
  row: number
  col: number
  first_label: string | null
  first_catalog: string | null
  last_label: string | null
  last_catalog: string | null
  is_empty: boolean
  total_count: number
  fill_level: number   // 0.0+; > 1.0 means overstuffed
  sample_records: SampleRecord[]
}

/**
 * Extended CubeBoundary with fill_level from the bulk GET /api/cubes endpoint.
 * The base CubeBoundary in types.ts (owned by plans 02/04) cannot be modified here.
 * KioskView uses this type when consuming the fill_level field added by plan 03.
 */
export interface CubeBoundaryWithFill {
  unit_id: number
  row: number
  col: number
  is_empty: boolean
  fill_level: number   // 0.0+; > 1.0 means overstuffed
}

/** Extended cubes response including fill_level per cube. */
export interface CubesWithFillResponse {
  cubes: CubeBoundaryWithFill[]
}

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

// ── Phase 5: Segment model types ──────────────────────────────────────────────

/**
 * One label's segment within a bin, as returned by GET /api/admin/cubes/{u}/{r}/{c}/segments.
 * The fraction fields are always 0–1 and all fractions in a bin sum to 1.0.
 */
export interface Segment {
  label: string
  fraction: number         // applied fraction (override ?? auto)
  is_override: boolean     // true if fraction was set by admin
  auto_fraction: number    // count-derived fraction (always present)
  continues: boolean       // true if this label straddles into the next bin
  segment_count: number    // row count for this label in this bin
}

/** Response from GET /api/admin/cubes/{u}/{r}/{c}/segments */
export interface SegmentsResponse {
  segments: Segment[]
}

/** Body for PUT /api/admin/cubes/{u}/{r}/{c}/cut */
export interface CutPointBody {
  first_label: string
  first_catalog: string
  force?: boolean
}

/** One override entry for POST /api/admin/cubes/{u}/{r}/{c}/overrides */
export interface OverrideEntry {
  label: string
  fraction: number | null  // null = remove override
}

/** Body for POST /api/admin/cubes/{u}/{r}/{c}/overrides */
export interface OverridesBody {
  overrides: OverrideEntry[]
}

/** Body for POST /api/admin/cubes/insert-cut */
export interface InsertCutBody {
  after_unit_id: number
  after_row: number
  after_col: number
  new_first_label: string
  new_first_catalog: string
  force?: boolean
}

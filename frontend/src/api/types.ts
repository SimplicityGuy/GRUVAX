/**
 * API types matching the plan-03 response shapes from FastAPI endpoints.
 *
 * GET /api/search?q=&limit= → SearchResponse
 * GET /api/locate?release_id= → LocateResult
 * GET /api/units → UnitsResponse
 */

export interface SearchResult {
  release_id: number
  title: string
  primary_artist: string
  label: string
  catalog_number: string
  format: string
  year: number | null
  rank: number
}

export interface SearchResponse {
  items: SearchResult[]
  took_ms: number
  /** Trigram-similarity suggestion returned when FTS finds nothing strong (SRCH-07/D-11).
   *  null when pg_trgm is unavailable or no strong candidate exists. */
  did_you_mean: string | null
}

export interface CubeRef {
  unit_id: number
  row: number
  col: number
}

/** Normalized sub-cube interval returned by /api/locate (Phase 2: plan 01 backend). */
export interface SubInterval {
  /** Normalized start position within the cube: 0.0–1.0 */
  start: number
  /** Normalized end position within the cube: 0.0–1.0; ≥ start */
  end: number
  /** True when the range extends past this cube into next_cube */
  crosses_boundary: boolean
  /** Present when crosses_boundary === true (omitted from JSON when false) */
  next_cube?: CubeRef
}

export interface LocateResult {
  release_id: number
  primary_cube: CubeRef | null
  label_span: CubeRef[]
  /** Sub-cube position interval — null when only cube-level location is known */
  sub_cube_interval: SubInterval | null
  confidence: number
  generated_at: string
  estimator_version: string
}

export interface Unit {
  id: number
  display_name: string
  rows: number
  cols: number
  ordering: number
}

export interface UnitsResponse {
  units: Unit[]
}

/** One row from GET /api/cubes — includes is_empty for CUBE-05 empty state. */
export interface CubeBoundary {
  unit_id: number
  row: number
  col: number
  is_empty: boolean
}

export interface CubesResponse {
  cubes: CubeBoundary[]
}

/** Cube state driven by UI logic — fed into data-state attribute on each Cube cell. */
export type CubeState = 'dim' | 'lit' | 'empty' | 'hover'

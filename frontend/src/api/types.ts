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

// ── Admin API types ────────────────────────────────────────────────────────

/** Response from POST /api/admin/login — includes CSRF token for double-submit. */
export interface LoginResponse {
  csrf_token: string
  message: string
}

/** Response from GET /api/admin/session — session expiry times. */
export interface AdminSession {
  expires_at: string   // ISO-8601 UTC
  hard_cap_at: string  // ISO-8601 UTC
}

/** Response from GET /api/admin/settings — nominal capacity + idle TTL. */
export interface AdminSettings {
  nominal_capacity: number
  idle_ttl_seconds: number
}

/** Payload for PUT /api/admin/settings. */
export interface AdminSettingsPut {
  nominal_capacity?: number
  idle_ttl_seconds?: number
}

/** Payload for POST /api/admin/settings/pin — change PIN. */
export interface ChangePinPayload {
  current_pin: string
  new_pin: string
}

/**
 * One boundary edit in a pending change-set.
 * Stored in localStorage via Zustand persist — shape is declared now so
 * plans 04 and 05 can reuse it without re-deciding.
 */
export interface CubeBoundaryEdit {
  unit_id: number
  row: number
  col: number
  label_first: string
  catalog_first: string
  label_last: string
  catalog_last: string
}

/**
 * A pending change-set: the collection of boundary edits accumulated before commit.
 * Persisted to localStorage so a session timeout / reload preserves in-progress work.
 */
export interface ChangeSet {
  id: string              // client-generated UUID
  created_at: string      // ISO-8601 when the change-set was started
  edits: CubeBoundaryEdit[]
}

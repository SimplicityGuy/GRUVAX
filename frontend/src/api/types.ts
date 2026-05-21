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

/** Response from GET /api/admin/settings — nominal capacity + idle TTL.
 *
 * Key names match the backend response (WR-01):
 * cube_nominal_capacity / session_idle_ttl_seconds.
 */
export interface AdminSettings {
  cube_nominal_capacity: number
  session_idle_ttl_seconds: number
}

/** Payload for PUT /api/admin/settings.
 *
 * Key names match what the backend update_settings handler recognises (WR-01).
 */
export interface AdminSettingsPut {
  cube_nominal_capacity?: number
  session_idle_ttl_seconds?: number
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
 *
 * Field names match the backend Pydantic model (BoundaryEdit) and DB columns:
 * first_label / first_catalog / last_label / last_catalog (CR-01).
 */
export interface CubeBoundaryEdit {
  unit_id: number
  row: number
  col: number
  first_label: string
  first_catalog: string
  last_label: string
  last_catalog: string
  is_empty?: boolean
  force?: boolean
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

// ── Admin cubes editor types (plan 03-04) ────────────────────────────────────

/** A near-miss record from pg_trgm similarity on phantom label/catalog. */
export interface NearMiss {
  release_id: number
  label: string
  catalog_number: string
  score: number
}

/** Movement estimate for a boundary validate/save response. */
export interface MovementCount {
  unit_id: number
  row: number
  col: number
  records_before: number
  records_after: number
  delta: number
  fill_level_before: number
  fill_level_after: number
}

/** One item in the validate endpoint results array. */
export interface ValidateItem {
  unit_id: number
  row: number
  col: number
  valid: boolean
  /** Present when valid === false due to comparator (POS-01). */
  comparator_error?: string
  /** Present when valid === false due to boundary_order_error. */
  error?: string
  /** Human-readable message from the server (boundary_order_error / phantom_boundary). */
  message?: string
  /** True when the value is not in v_collection (phantom). */
  phantom?: boolean
  /** Which boundary record triggered the phantom: "first" or "last" (F7). */
  phantom_field?: 'first' | 'last'
  /** Near-miss candidates from pg_trgm (only when phantom === true). */
  near_misses?: NearMiss[]
  /** movement_counts is a LIST (one item per cube) from the backend (CR-03). */
  movement_counts?: MovementCount[]
}

/** Response from POST /api/admin/cubes/validate (dry-run — always HTTP 200). */
export interface ValidateResponse {
  valid: boolean
  results: ValidateItem[]
}

/** A midpoint suggestion from POST /api/admin/cubes/suggest. */
export interface MidpointSuggestion {
  release_id: number
  label: string
  catalog_number: string
}

/** Response from POST /api/admin/cubes/suggest. */
export interface SuggestResponse {
  suggestion: MidpointSuggestion | null
}

/** One cube row from GET /api/admin/cubes. */
export interface AdminCube {
  unit_id: number
  row: number
  col: number
  first_label: string
  first_catalog: string
  last_label: string
  last_catalog: string
  is_empty: boolean
  fill_level: number     // 0.0–1.0 fraction of nominal capacity
}

/** Response from GET /api/admin/cubes. */
export interface AdminCubesResponse {
  cubes: AdminCube[]
}

/** Response from GET /api/admin/cubes/{u}/{r}/{c}/boundary. */
export interface AdminCubeBoundary {
  unit_id: number
  row: number
  col: number
  first_label: string
  first_catalog: string
  last_label: string
  last_catalog: string
}

/** Label option from GET /api/admin/labels. */
export interface LabelOption {
  label: string
}

/** Catalog option from GET /api/admin/labels/{label}/catalogs. */
export interface CatalogOption {
  release_id: number
  catalog_number: string
}

// ── Change-set commit + history types (plan 03-05) ───────────────────────────

/** Response from POST /api/admin/cubes/bulk. */
export interface CommitResponse {
  change_set_id: string
  applied: number
}

/** One entry in the GET /api/admin/history response. */
export interface ChangeSetHistoryItem {
  change_set_id: string
  source: 'manual' | 'bulk' | 'revert'
  changed_at: string   // ISO-8601 timestamp
  cube_count: number
}

/** Response from GET /api/admin/history. */
export interface HistoryResponse {
  history: ChangeSetHistoryItem[]
}

/** One reverted/skipped cube in a RevertResponse. */
export interface RevertedCube {
  unit_id: number
  row: number
  col: number
}

/** Response from POST /api/admin/history/{change_set_id}/revert. */
export interface RevertResponse {
  change_set_id: string   // the new inverse change-set UUID
  reverted: RevertedCube[]
  skipped: RevertedCube[]
}

/**
 * API types matching the plan-03 response shapes from FastAPI endpoints.
 *
 * GET /api/search?q=&limit= → SearchResponse
 * GET /api/locate?release_id= → LocateResult
 * GET /api/units → UnitsResponse
 * GET /api/health → HealthResponse
 */

/** Response from GET /api/health.
 *
 * P1 / D-13: ``discogsography_api_check`` (renamed from the v1 legacy field;
 * see CONTEXT D-13) widens the union to ``'ok' | 'failed' | 'stale'`` — derived
 * from cached default-profile sync state on the backend (no live probe).
 *
 * State mapping (per CONTEXT.md D-13 + UI-SPEC):
 *   ok      — last_sync_status='ok' AND app_token_revoked=FALSE (or in_progress)
 *   failed  — last_sync_status='failed' OR app_token_revoked=TRUE
 *   stale   — last_sync_at IS NULL OR now() - last_sync_at > 24h
 */
export interface HealthResponse {
  status: 'ok' | 'degraded'
  db: 'ok' | 'error'
  discogsography_api_check: 'ok' | 'failed' | 'stale'
  mqtt: 'ok' | 'degraded'
  version: string
  started_at: string             // ISO-8601 UTC
  sync_age_seconds: number | null
}

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

/** Response from GET /api/admin/settings — nominal capacity, idle TTL, and LED knobs.
 *
 * Phase 3: cube_nominal_capacity / session_idle_ttl_seconds.
 * Phase 6: LED color, brightness, and highlight lifecycle keys (LED-04, LED-05, D-24, D-25).
 *
 * Key names match the backend response (WR-01).
 */
export interface AdminSettings {
  cube_nominal_capacity: number
  session_idle_ttl_seconds: number
  // Phase 6 — LED colors (one per system state, LED-05)
  led_color_position?: string        // default "#FFD700" (gold)
  led_color_label_span?: string      // default "#7C3AED" (purple)
  led_color_error?: string           // default "#E63946"
  led_color_setup?: string           // default "#0077B6"
  led_color_all_off?: string         // default "#000000"
  led_color_ambient?: string         // default "#0051A2" — idle/resting baseline color
  // Phase 6 — LED brightness tiers (LED-04, D-24)
  led_brightness_span?: number       // 0..255, ~50% — label-span tier (D-24: NOT ambient)
  led_brightness_active?: number     // 0..255, 100% — position/primary tier
  led_brightness_ambient?: number    // 0..255, low — idle/resting baseline brightness
  // Phase 6 — LED highlight lifecycle (D-25)
  led_highlight_active_ttl_seconds?: number   // default 180s
  led_highlight_retain_mode?: boolean         // default false
  led_highlight_retain_ttl_seconds?: number   // default 900s
  // Phase 4 — Sync cadence (D4-06)
  sync_cadence?: '24h' | '12h' | '6h' | 'off'
}

/** Payload for PUT /api/admin/settings.
 *
 * Phase 3: cube capacity + idle TTL.
 * Phase 6: LED color/brightness/highlight fields (all optional; send only what changed).
 *
 * Key names match what the backend update_settings handler recognises (WR-01).
 */
export interface AdminSettingsPut {
  cube_nominal_capacity?: number
  session_idle_ttl_seconds?: number
  // Phase 6 — LED colors
  led_color_position?: string
  led_color_label_span?: string
  led_color_error?: string
  led_color_setup?: string
  led_color_all_off?: string
  led_color_ambient?: string
  // Phase 6 — LED brightness tiers (D-24)
  led_brightness_span?: number       // label-span tier — NEVER labeled ambient
  led_brightness_active?: number     // position/primary tier
  led_brightness_ambient?: number    // idle baseline — NEVER labeled span
  // Phase 6 — LED highlight lifecycle
  led_highlight_active_ttl_seconds?: number
  led_highlight_retain_mode?: boolean
  led_highlight_retain_ttl_seconds?: number
  // Phase 4 — Sync cadence (D4-06)
  sync_cadence?: '24h' | '12h' | '6h' | 'off'
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
  /** Optional — wizard/reshuffle paths set these to ""; single-cube edit keeps them. */
  last_label?: string
  /** Optional — wizard/reshuffle paths set these to ""; single-cube edit keeps them. */
  last_catalog?: string
  is_empty?: boolean
  force?: boolean
}

// ── Phase 7: Wizard + Import/Export types (plan 07-04) ──────────────────────

/**
 * In-progress reshuffle/setup draft persisted to localStorage via Zustand.
 * Keyed by `${unit_id}/${row}/${col}` for O(1) step lookup.
 * null = no draft in progress.
 */
export interface ReshuffleDraft {
  mode: 'setup' | 'reshuffle'
  completedSteps: number
  cuts: Record<string, {
    first_label: string | null
    first_catalog: string | null
    is_empty: boolean
  }>
  /** crypto.randomUUID() generated before network call; reused on retry (D-04, Pattern 4). */
  idempotencyKey: string | null
  /** ISO-8601 timestamp — used for relative-time display in ReshuffleBanner. */
  startedAt: string
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
  /** Source widened in Phase 7 to include wizard/import sources (D-04). */
  source: 'manual' | 'bulk' | 'revert' | 'cut_insert' | 'wizard' | 'reshuffle' | 'csv' | 'yaml'
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

// ── Phase 2: Profile Manager types (plan 02-07) ──────────────────────────────

/** Status enum for a profile (derived server-side from DB columns). */
export type ProfileStatus =
  | 'pending'
  | 'syncing'
  | 'connected'
  | 're-auth-required'

/** A profile from GET /api/admin/profiles or GET /api/admin/profiles/{id}. */
export interface AdminProfile {
  id: string                                  // UUID
  display_name: string
  last_sync_at: string | null                 // ISO-8601 or null
  last_sync_status: 'ok' | 'failed' | 'in_progress' | null
  last_sync_error: string | null
  last_sync_item_count: number | null
  app_token_revoked: boolean
  status: ProfileStatus
  /** Phase 7 (API-04): true when an encrypted PAT is stored for this profile. */
  has_token: boolean
  /** Phase 7 (API-04): number of new records from the most recent non-initial sync. */
  last_new_record_count: number
  /** Phase 7 (API-04): true when the most recent sync was the profile's initial import. */
  last_sync_is_initial: boolean
}

/** Response from GET /api/admin/profiles. */
export type AdminProfilesResponse = AdminProfile[]

/** Payload for POST /api/admin/profiles. */
export interface CreateProfilePayload {
  display_name: string
}

/** Payload for PATCH /api/admin/profiles/{id}. */
export interface RenameProfilePayload {
  display_name: string
}

/** Payload for POST /api/admin/profiles/{id}/connect or /rotate. */
export interface ConnectPatPayload {
  pat: string
}

// ── Phase 7: Invite code + redeem types (plan 07-03) ─────────────────────────

/** Info returned by GET /api/invite-codes/{code} (public, no auth). */
export interface InviteCodeInfo {
  display_name: string
  expires_at: string   // ISO-8601 UTC
}

/** Response from POST /api/admin/profiles/{id}/invite (owner, PIN-gated). */
export interface GeneratedInvite {
  code: string
  url: string
  expires_at: string  // ISO-8601 UTC
}

/** Response from POST /api/invite-codes/{code}/redeem (public, no auth). */
export interface RedeemResult {
  status: 'connected'
  profile_id: string
}

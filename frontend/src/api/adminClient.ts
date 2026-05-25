/**
 * Admin API client for GRUVAX.
 *
 * Every mutating request (POST/PUT/DELETE) must include the ``X-CSRF-Token``
 * header equal to the ``gruvax_csrf`` cookie value so the backend's
 * ``require_admin`` dependency accepts it (double-submit CSRF pattern).
 *
 * ``adminFetch`` is the central wrapper — it reads the CSRF token from the
 * Zustand admin store and attaches it to mutating requests.  All other
 * functions in this module call ``adminFetch`` instead of raw ``fetch``.
 *
 * Credentials are always ``'same-origin'`` so the HttpOnly ``gruvax_session``
 * cookie is sent automatically by the browser.
 */

import type {
  AdminCubeBoundary,
  AdminCubesResponse,
  AdminSession,
  AdminSettings,
  AdminSettingsPut,
  CatalogOption,
  ChangePinPayload,
  CommitResponse,
  CubeBoundaryEdit,
  HistoryResponse,
  LabelOption,
  LoginResponse,
  RevertResponse,
  SuggestResponse,
  ValidateResponse,
} from './types'
import type {
  CutPointBody,
  InsertCutBody,
  OverridesBody,
  SegmentsResponse,
} from './cubeTypes'

const BASE = ''

// Import the admin store to read the CSRF token.
// This is a direct import (not lazy) — the store module has no circular
// dependency on adminClient because adminClient does not import from the store.
import { useAdminStore } from '../state/adminStore'

/** Read CSRF token from the Zustand store at call time (avoids stale closure). */
function getCsrfToken(): string {
  return useAdminStore.getState().csrfToken ?? ''
}

/** Central fetch wrapper: adds credentials + optional CSRF header.
 *
 * When ``body`` is a ``FormData`` instance, the ``Content-Type`` default is
 * intentionally omitted so the browser can set the multipart boundary
 * automatically (file upload pattern — PATTERNS.md §adminClient.ts).
 */
async function adminFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const method = (options.method ?? 'GET').toUpperCase()
  const isMutating = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)

  // Skip the application/json default when body is FormData so the browser
  // sets the multipart Content-Type + boundary automatically.
  const isFormData = options.body instanceof FormData
  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string>),
  }

  if (isMutating) {
    const csrf = getCsrfToken()
    if (csrf) {
      headers['X-CSRF-Token'] = csrf
    }
  }

  return fetch(`${BASE}${path}`, {
    ...options,
    credentials: 'same-origin',
    headers,
  })
}

// ── Auth ─────────────────────────────────────────────────────────────────────

/**
 * POST /api/admin/login
 * Returns the CSRF token on success (200).
 * Throws ``AuthError`` on wrong PIN (401), ``RateLimitError`` on 429.
 */
export async function adminLogin(pin: string): Promise<LoginResponse> {
  const res = await fetch(`${BASE}/api/admin/login`, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  })
  if (res.status === 429) {
    const retryAfter = res.headers.get('Retry-After')
    throw new RateLimitError(retryAfter ? parseInt(retryAfter, 10) : 300)
  }
  if (res.status === 401) {
    throw new AuthError('invalid_pin')
  }
  if (!res.ok) {
    throw new Error(`Login failed: ${res.status}`)
  }
  return res.json() as Promise<LoginResponse>
}

/** POST /api/admin/logout — clears session + CSRF cookies server-side. */
export async function adminLogout(): Promise<void> {
  const res = await adminFetch('/api/admin/logout', { method: 'POST' })
  if (!res.ok && res.status !== 401) {
    throw new Error(`Logout failed: ${res.status}`)
  }
}

/** GET /api/admin/session — returns current expiry times. */
export async function adminGetSession(): Promise<AdminSession> {
  const res = await adminFetch('/api/admin/session')
  if (res.status === 401) {
    throw new AuthError('session_expired')
  }
  if (!res.ok) {
    throw new Error(`Session fetch failed: ${res.status}`)
  }
  return res.json() as Promise<AdminSession>
}

// ── Settings ──────────────────────────────────────────────────────────────────

/** GET /api/admin/settings — returns nominal capacity + idle TTL. */
export async function getAdminSettings(): Promise<AdminSettings> {
  const res = await adminFetch('/api/admin/settings')
  if (!res.ok) {
    throw new Error(`Settings fetch failed: ${res.status}`)
  }
  return res.json() as Promise<AdminSettings>
}

/** PUT /api/admin/settings — updates whitelisted settings keys.
 *
 * The backend returns ``{updated: string[]}`` (list of DB key names updated),
 * not a full AdminSettings object. Return type is relaxed to Partial<AdminSettings>
 * to let the caller handle missing fields gracefully (WR-01).
 */
export async function putAdminSettings(payload: AdminSettingsPut): Promise<Partial<AdminSettings>> {
  const res = await adminFetch('/api/admin/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`Settings update failed: ${res.status}`)
  }
  return res.json() as Promise<Partial<AdminSettings>>
}

/** POST /api/admin/settings/pin — change PIN (requires current PIN). */
export async function changePin(payload: ChangePinPayload): Promise<void> {
  const res = await adminFetch('/api/admin/settings/pin', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (res.status === 401) {
    throw new AuthError('invalid_current_pin')
  }
  if (!res.ok) {
    throw new Error(`Change PIN failed: ${res.status}`)
  }
}

// ── Admin cubes (plan 03-04) ──────────────────────────────────────────────────

/** GET /api/admin/cubes — returns all cubes with boundary + fill_level. */
export async function adminGetCubes(): Promise<AdminCubesResponse> {
  const res = await adminFetch('/api/admin/cubes')
  if (!res.ok) {
    throw new Error(`Failed to fetch admin cubes: ${res.status}`)
  }
  return res.json() as Promise<AdminCubesResponse>
}

/** GET /api/admin/cubes/{unit_id}/{row}/{col}/boundary — returns one cube boundary. */
export async function adminGetCubeBoundary(
  unitId: number,
  row: number,
  col: number,
): Promise<AdminCubeBoundary> {
  const res = await adminFetch(`/api/admin/cubes/${unitId}/${row}/${col}/boundary`)
  if (res.status === 404) {
    throw new Error(`Cube ${unitId}/${row}/${col} not found`)
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch cube boundary: ${res.status}`)
  }
  return res.json() as Promise<AdminCubeBoundary>
}

/**
 * POST /api/admin/cubes/validate — dry-run boundary validation (always HTTP 200).
 * Never writes to the database.
 *
 * The backend ValidateRequest model uses key `updates` (CR-02).
 */
export async function validateBoundary(
  edits: CubeBoundaryEdit[],
): Promise<ValidateResponse> {
  const res = await adminFetch('/api/admin/cubes/validate', {
    method: 'POST',
    body: JSON.stringify({ updates: edits }),
  })
  if (!res.ok) {
    throw new Error(`Validate failed: ${res.status}`)
  }
  return res.json() as Promise<ValidateResponse>
}

/**
 * POST /api/admin/cubes/suggest — get index-space midpoint suggestion
 * for the cube after (unit_id, row, col).
 */
export async function suggestMidpoint(
  unitId: number,
  row: number,
  col: number,
): Promise<SuggestResponse> {
  const res = await adminFetch('/api/admin/cubes/suggest', {
    method: 'POST',
    body: JSON.stringify({ unit_id: unitId, row, col }),
  })
  if (!res.ok) {
    throw new Error(`Suggest failed: ${res.status}`)
  }
  return res.json() as Promise<SuggestResponse>
}

/** GET /api/admin/labels — distinct labels from v_collection. */
export async function getDistinctLabels(): Promise<LabelOption[]> {
  const res = await adminFetch('/api/admin/labels')
  if (!res.ok) {
    throw new Error(`Failed to fetch labels: ${res.status}`)
  }
  return res.json() as Promise<LabelOption[]>
}

/** GET /api/admin/labels/{label}/catalogs — catalog numbers for a specific label. */
export async function getCatalogsForLabel(label: string): Promise<CatalogOption[]> {
  const res = await adminFetch(
    `/api/admin/labels/${encodeURIComponent(label)}/catalogs`,
  )
  if (!res.ok) {
    throw new Error(`Failed to fetch catalogs for label: ${res.status}`)
  }
  return res.json() as Promise<CatalogOption[]>
}

// ── Change-set commit + history (plan 03-05) ──────────────────────────────────

/**
 * POST /api/admin/cubes/bulk — atomic change-set commit.
 *
 * Sends the Idempotency-Key header so a double-tap on a flaky connection
 * replays the cached response instead of writing a second change-set.
 * Generate a UUID per commit attempt with `crypto.randomUUID()`, persist it
 * alongside the pendingChangeSet so retries reuse the same key.
 *
 * Phase 7 (D-04): ``source`` widens from the legacy 'bulk' default to include
 * 'wizard' and 'reshuffle' so HistoryView can render legible source badges.
 *
 * On 400, throws ``BulkSaveError`` carrying the server's ``message`` and
 * ``type`` fields so callers can surface structured error text to the user.
 */
export async function adminBulkSave(
  updates: CubeBoundaryEdit[],
  idempotencyKey: string,
  source: 'bulk' | 'wizard' | 'reshuffle' | 'csv' | 'yaml' = 'bulk',
): Promise<CommitResponse> {
  const res = await adminFetch('/api/admin/cubes/bulk', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ updates, source }),
  })
  if (!res.ok) {
    // Attempt to parse structured error body (boundary_order_error / phantom_boundary)
    let errorMessage: string | undefined
    let errorType: string | undefined
    try {
      const body = await res.json() as Record<string, unknown>
      if (typeof body.message === 'string') errorMessage = body.message
      if (typeof body.type === 'string') errorType = body.type
    } catch {
      // Non-JSON body — fall through to generic message
    }
    throw new BulkSaveError(res.status, errorType, errorMessage)
  }
  return res.json() as Promise<CommitResponse>
}

/** GET /api/admin/history — returns change-sets newest-first. */
export async function getHistory(): Promise<HistoryResponse> {
  const res = await adminFetch('/api/admin/history')
  if (!res.ok) {
    throw new Error(`History fetch failed: ${res.status}`)
  }
  return res.json() as Promise<HistoryResponse>
}

/**
 * POST /api/admin/history/{change_set_id}/revert — conflict-aware revert.
 *
 * Writes an inverse change-set (source='revert') that is itself undoable.
 * Cubes modified by a newer change-set are skipped and reported.
 */
export async function revertChangeSet(changeSetId: string): Promise<RevertResponse> {
  const res = await adminFetch(`/api/admin/history/${changeSetId}/revert`, {
    method: 'POST',
  })
  if (res.status === 404) {
    throw new Error('change_set_not_found')
  }
  if (!res.ok) {
    throw new Error(`Revert failed: ${res.status}`)
  }
  return res.json() as Promise<RevertResponse>
}

// ── Admin editing heartbeat (Phase 4 / RTM-04) ───────────────────────────────

/**
 * POST /api/admin/editing — fire the admin_editing heartbeat so the kiosk
 * can shimmer the affected cube range while the owner is mid-edit (D-01, RTM-04).
 *
 * Network errors are swallowed and logged: a heartbeat failure must never
 * break the editor UX. The kiosk clears the shimmer after ~60s idle (D-03)
 * even if the close/commit signal is missed.
 */
export async function signalEditing(
  cubeIds: Array<{ unit: number; row: number; col: number }>,
  editing: boolean,
): Promise<void> {
  try {
    await adminFetch('/api/admin/editing', {
      method: 'POST',
      body: JSON.stringify({ cube_ids: cubeIds, editing }),
    })
  } catch (err) {
    // Swallow — heartbeat failure is non-fatal
    console.debug('[gruvax] signalEditing network error (non-fatal):', err)
  }
}

/**
 * Debounced admin_editing heartbeat.
 *
 * Returns an object with two methods:
 *  - ``signal(cubeIds, true)``  — debounced ~300ms; fires editing:true after
 *    the owner pauses typing.
 *  - ``signal(cubeIds, false)`` — immediate; fires editing:false on close/commit
 *    so the kiosk shimmer clears without waiting for the debounce.
 *
 * Usage::
 *
 *   const heartbeat = createEditingHeartbeat()
 *   // on every value change:
 *   heartbeat.signal(cubeIds, true)
 *   // on editor close or commit:
 *   heartbeat.signal(cubeIds, false)
 *
 * The debounce avoids flooding the bus at ~keystroke rate (T-04-09).
 * Immediate false guarantees the shimmer never outlasts the editing session.
 */
export function createEditingHeartbeat(): {
  signal: (cubeIds: Array<{ unit: number; row: number; col: number }>, editing: boolean) => void
} {
  let timeout: ReturnType<typeof setTimeout> | null = null
  const DEBOUNCE_MS = 300

  return {
    signal(cubeIds, editing) {
      if (!editing) {
        // Immediate on close/commit — clear shimmer without debounce delay
        if (timeout !== null) {
          clearTimeout(timeout)
          timeout = null
        }
        void signalEditing(cubeIds, false)
        return
      }
      // Debounce the editing:true signal
      if (timeout !== null) clearTimeout(timeout)
      timeout = setTimeout(() => {
        timeout = null
        void signalEditing(cubeIds, true)
      }, DEBOUNCE_MS)
    },
  }
}

// ── Cube boundary mutation (Phase 4 / RTM-03) ────────────────────────────────

/**
 * PUT /api/admin/cubes/{unit_id}/{row}/{col}/boundary — single-cube write.
 *
 * Used by the optimistic useMutation in DiffPreviewSheet as the per-cube
 * variant; the bulk path (adminBulkSave) remains the primary commit path.
 * Error handling mirrors adminGetCubeBoundary (BulkSaveError on 400,
 * Error on 404 and other non-OK statuses).
 */
export async function putCubeBoundary(
  boundary: CubeBoundaryEdit,
): Promise<AdminCubeBoundary> {
  const res = await adminFetch(
    `/api/admin/cubes/${boundary.unit_id}/${boundary.row}/${boundary.col}/boundary`,
    { method: 'PUT', body: JSON.stringify(boundary) },
  )
  if (res.status === 400) {
    const body = await res.json() as Record<string, unknown>
    throw new BulkSaveError(
      400,
      typeof body.type === 'string' ? body.type : undefined,
      typeof body.message === 'string' ? body.message : undefined,
    )
  }
  if (res.status === 404) throw new Error('cube_not_found')
  if (!res.ok) throw new Error(`Boundary update failed: ${res.status}`)
  return res.json() as Promise<AdminCubeBoundary>
}

// ── Phase 5: Segment endpoints ────────────────────────────────────────────────

/**
 * GET /api/admin/cubes/{unit_id}/{row}/{col}/segments
 * Returns derived segment data for one bin (reads SegmentCache — no DB write).
 */
export async function getUnitSegments(
  unitId: number,
  row: number,
  col: number,
): Promise<SegmentsResponse> {
  const res = await adminFetch(`/api/admin/cubes/${unitId}/${row}/${col}/segments`)
  if (res.status === 404) {
    throw new Error(`Cube ${unitId}/${row}/${col} not found`)
  }
  if (!res.ok) {
    throw new Error(`Failed to fetch segments: ${res.status}`)
  }
  return res.json() as Promise<SegmentsResponse>
}

/**
 * PUT /api/admin/cubes/{unit_id}/{row}/{col}/cut
 * Replace the cut point (first_label + first_catalog) for a bin.
 */
export async function setCutPoint(
  unitId: number,
  row: number,
  col: number,
  body: CutPointBody,
): Promise<void> {
  const res = await adminFetch(`/api/admin/cubes/${unitId}/${row}/${col}/cut`, {
    method: 'PUT',
    body: JSON.stringify(body),
  })
  if (res.status === 400) {
    const errBody = await res.json() as Record<string, unknown>
    throw new BulkSaveError(
      400,
      typeof errBody.type === 'string' ? errBody.type : undefined,
      typeof errBody.message === 'string' ? errBody.message : undefined,
    )
  }
  if (res.status === 404) throw new Error('cube_not_found')
  if (!res.ok) throw new Error(`Set cut point failed: ${res.status}`)
}

/**
 * POST /api/admin/cubes/{unit_id}/{row}/{col}/overrides
 * Upsert or remove per-label width overrides for a bin.
 * Supports Idempotency-Key header for safe retry on flaky connections.
 */
export async function setOverrides(
  unitId: number,
  row: number,
  col: number,
  overrides: OverridesBody,
  idempotencyKey?: string,
): Promise<void> {
  const extraHeaders: Record<string, string> = {}
  if (idempotencyKey) extraHeaders['Idempotency-Key'] = idempotencyKey

  const res = await adminFetch(`/api/admin/cubes/${unitId}/${row}/${col}/overrides`, {
    method: 'POST',
    headers: extraHeaders,
    body: JSON.stringify(overrides),
  })
  if (res.status === 400) {
    const errBody = await res.json() as Record<string, unknown>
    throw new BulkSaveError(
      400,
      typeof errBody.type === 'string' ? errBody.type : undefined,
      typeof errBody.message === 'string' ? errBody.message : undefined,
    )
  }
  if (!res.ok) throw new Error(`Set overrides failed: ${res.status}`)
}

/** Response from POST /api/admin/cubes/insert-cut (segments.py insert_cut). */
export interface InsertCutResult {
  change_set_id: string
  inserted_after: { unit_id: number; row: number; col: number }
  new_cut: { first_label: string; first_catalog: string }
  /** Number of cubes the cascade rewrote in this change-set. */
  affected: number
}

/**
 * POST /api/admin/cubes/insert-cut
 * Insert a new cut point after the specified bin; the backend cascades all
 * subsequent cut points right by one in a single undoable change-set.
 * Returns the committed change-set summary; raises BulkSaveError on 400.
 */
export async function insertCut(body: InsertCutBody): Promise<InsertCutResult> {
  const res = await adminFetch('/api/admin/cubes/insert-cut', {
    method: 'POST',
    body: JSON.stringify(body),
  })
  if (res.status === 400) {
    const errBody = await res.json() as Record<string, unknown>
    throw new BulkSaveError(
      400,
      typeof errBody.type === 'string' ? errBody.type : undefined,
      typeof errBody.message === 'string' ? errBody.message : undefined,
    )
  }
  if (!res.ok) throw new Error(`Insert cut failed: ${res.status}`)
  return res.json() as Promise<InsertCutResult>
}

// ── Phase 6: LED admin endpoints ─────────────────────────────────────────────

/**
 * POST /api/admin/leds/off — idempotent all-off.
 *
 * Clears every retained state/* topic by publishing an empty payload.
 * Safe to call repeatedly (D-11).  Returns {published: N} where N is the
 * number of cube state-clear publishes made.
 *
 * Degraded mode (broker offline): returns {published: 0}, no error thrown.
 *
 * CSRF handled by adminFetch (T-06-13).
 */
export async function ledsAllOff(): Promise<{ published: number }> {
  const res = await adminFetch('/api/admin/leds/off', { method: 'POST' })
  if (!res.ok) {
    throw new Error(`LEDs all-off failed: ${res.status}`)
  }
  return res.json() as Promise<{ published: number }>
}

/**
 * POST /api/admin/leds/diagnostic — start a diagnostic sweep.
 *
 * Returns {run_id, started_at} immediately (D-08 — instant ack).
 * The diagnostic runs in a background task on the server; observe results
 * via ``mosquitto_sub`` or the server logs.
 *
 * CSRF handled by adminFetch (T-06-13).
 */
export async function ledsDiagnostic(): Promise<{ run_id: string; started_at: string }> {
  const res = await adminFetch('/api/admin/leds/diagnostic', { method: 'POST' })
  if (!res.ok) {
    throw new Error(`LED diagnostic failed: ${res.status}`)
  }
  return res.json() as Promise<{ run_id: string; started_at: string }>
}

// ── Phase 8: Diagnostics endpoints ───────────────────────────────────────────

/** Shape of a single top-searched row from the backend. */
export interface TopSearchedRow {
  release_id: number
  title: string
  primary_artist: string
  search_count: number
  search_count_7d: number
  selection_count: number
  selection_count_7d: number
}

/** Shape of a slow-query ring buffer entry from the backend. */
export interface SlowQueryEntry {
  path: string
  total_ms: number
  db_ms: number
  threshold_ms: number
  ts: number
}

/** Shape of a recent-log ring buffer entry from the backend. */
export interface LogEntry {
  ts: number
  level: string
  logger: string
  msg: string
}

/** The full diagnostics payload returned by GET /api/admin/diagnostics. */
export interface DiagnosticsData {
  sync_age_seconds: number | null
  top_searched: TopSearchedRow[]
  slow_queries: SlowQueryEntry[]
  mqtt: 'connected' | 'disconnected'
  pool: {
    size_used: number
    size_min: number
  }
  phantom_boundary_count: number
  recent_logs: LogEntry[]
}

/**
 * GET /api/admin/diagnostics — return the 7 SC#2 diagnostic rows.
 *
 * Admin-gated (session cookie + CSRF via adminFetch). Returns the current
 * operational state: staleness, counters, ring buffers, pool stats, phantom count.
 */
export async function getDiagnostics(): Promise<DiagnosticsData> {
  const res = await adminFetch('/api/admin/diagnostics')
  if (!res.ok) {
    throw new Error(`Diagnostics fetch failed: ${res.status}`)
  }
  return res.json() as Promise<DiagnosticsData>
}

/**
 * POST /api/admin/diagnostics/reset-stats — truncate gruvax.record_stats.
 *
 * PIN-gated Reset stats action (D-06). Admin session + CSRF required (handled
 * by adminFetch — CSRF auto-attached for POST). Returns {reset: true} on success.
 */
export async function resetStats(): Promise<{ reset: boolean }> {
  const res = await adminFetch('/api/admin/diagnostics/reset-stats', {
    method: 'POST',
  })
  if (!res.ok) {
    throw new Error(`Reset stats failed: ${res.status}`)
  }
  return res.json() as Promise<{ reset: boolean }>
}

// ── Phase 7: Export / Import endpoints ───────────────────────────────────────

/**
 * GET /api/admin/export/boundaries.yaml — download boundaries as YAML.
 *
 * Fetches via adminFetch (CSRF read-only GET), converts the response to a
 * Blob, creates an object URL, and triggers a browser download via a hidden
 * ``<a download>`` element.  No external dependency — browser builtin only.
 */
export async function downloadBoundariesYaml(): Promise<void> {
  const res = await adminFetch('/api/admin/export/boundaries.yaml')
  if (!res.ok) {
    throw new Error(`Boundaries export failed: ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'boundaries.yaml'
  document.body.appendChild(a)
  a.click()
  // Defer cleanup: Firefox ignores clicks on a detached anchor and Safari
  // revokes the object URL before the download starts if revoked synchronously.
  setTimeout(() => {
    a.remove()
    URL.revokeObjectURL(url)
  }, 0)
}

/**
 * GET /api/admin/export/settings.yaml — download settings as YAML.
 *
 * Same browser-anchor download pattern as downloadBoundariesYaml (no popup blockers).
 */
export async function downloadSettingsYaml(): Promise<void> {
  const res = await adminFetch('/api/admin/export/settings.yaml')
  if (!res.ok) {
    throw new Error(`Settings export failed: ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'settings.yaml'
  document.body.appendChild(a)
  a.click()
  // Defer cleanup: Firefox ignores clicks on a detached anchor and Safari
  // revokes the object URL before the download starts if revoked synchronously.
  setTimeout(() => {
    a.remove()
    URL.revokeObjectURL(url)
  }, 0)
}

/**
 * Dry-run preview response from POST /api/admin/import/boundaries?dry_run=true.
 *
 * The backend returns this shape on a successful (zero-error) dry_run — no DB
 * write is performed.  ``diff_preview`` is empty when the file is byte-equal
 * to the committed state (W5 identity re-import).
 */
export interface BoundariesDryRunPreview {
  total_cubes: number
  file_cube_count: number
  diff_preview: Array<{
    unit_id: number
    row: number
    col: number
    delta: number
    will_be_empty: boolean
  }>
}

/**
 * POST /api/admin/import/boundaries — upload a CSV or YAML boundaries file.
 *
 * Sends the raw file bytes with the correct Content-Type header derived from the
 * file extension (.csv → ``text/csv``; .yaml / .yml → ``application/x-yaml``).
 * Never wraps the file in FormData — the backend reads the RAW request body.
 * ``adminFetch`` still injects X-CSRF-Token for the POST (CSRF safe, T-0708-CSRF).
 *
 * ``dryRun=true``:  Calls ``POST /api/admin/import/boundaries?dry_run=true``.
 *   The backend runs the full parse + validation pipeline with NO DB write and
 *   returns a ``BoundariesDryRunPreview`` body (200) or a 400 validation-error
 *   body.  No Idempotency-Key is sent (dry_run is stateless).
 *
 * ``dryRun=false`` (default):  Calls ``POST /api/admin/import/boundaries`` (no
 *   query param).  The caller MUST supply an ``idempotencyKey`` — it is sent as
 *   the ``Idempotency-Key`` header to prevent double-commits on retry.
 *   Returns a ``CommitResponse`` on success.
 *
 * On 400/422, throws ``BulkSaveError`` with the full parsed JSON body attached
 * as ``.body`` (W6 contract).  The caller can pass ``err.body`` directly to
 * ``parseServerErrors`` / ``parseDiff`` without re-parsing a stringified message.
 */
export async function uploadImportBoundaries(
  file: File,
  idempotencyKey: string | null,
  dryRun: boolean = false,
): Promise<CommitResponse | BoundariesDryRunPreview> {
  // Derive Content-Type from file extension; fall back to file.type if set.
  const ext = file.name.split('.').pop()?.toLowerCase()
  const contentType =
    ext === 'csv' ? 'text/csv'
    : (ext === 'yaml' || ext === 'yml') ? 'application/x-yaml'
    : file.type || 'application/octet-stream'

  const path = dryRun
    ? '/api/admin/import/boundaries?dry_run=true'
    : '/api/admin/import/boundaries'

  const extraHeaders: Record<string, string> = { 'Content-Type': contentType }
  // Idempotency-Key is only sent for the real commit (not dry_run).
  if (!dryRun && idempotencyKey) {
    extraHeaders['Idempotency-Key'] = idempotencyKey
  }

  const res = await adminFetch(path, {
    method: 'POST',
    headers: extraHeaders,
    body: file,
  })
  if (!res.ok) {
    let parsedBody: Record<string, unknown> = {}
    let errorType: string | undefined
    let errorMessage: string | undefined
    try {
      parsedBody = await res.json() as Record<string, unknown>
      if (typeof parsedBody.type === 'string') errorType = parsedBody.type
      if (typeof parsedBody.message === 'string') errorMessage = parsedBody.message
    } catch { /* ignore */ }
    throw new BulkSaveError(res.status, errorType, errorMessage, parsedBody)
  }
  return res.json() as Promise<CommitResponse | BoundariesDryRunPreview>
}

/**
 * POST /api/admin/import/settings — upload a YAML settings file.
 *
 * Sends the raw file bytes with ``Content-Type: application/x-yaml`` — the
 * backend reads the raw request body and calls ``yaml.safe_load``.  Never
 * wraps the file in FormData (which would cause a 422 from the raw-body reader).
 * No Idempotency-Key (settings import is idempotent by nature).
 *
 * Returns ``{ updated: string[] }`` — the list of DB key names written.
 * (The backend ``import_settings`` returns ``{"updated": [...]}``; there is no
 * ``applied`` field server-side — B2 contract fix.)
 *
 * On non-OK, throws ``BulkSaveError`` with the full parsed JSON attached as
 * ``.body`` (W6 contract) so Settings.tsx can show the locked failure copy.
 */
export async function uploadImportSettings(file: File): Promise<{ updated: string[] }> {
  const res = await adminFetch('/api/admin/import/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-yaml' },
    body: file,
  })
  if (!res.ok) {
    let parsedBody: Record<string, unknown> = {}
    let errorType: string | undefined
    let errorMessage: string | undefined
    try {
      parsedBody = await res.json() as Record<string, unknown>
      if (typeof parsedBody.type === 'string') errorType = parsedBody.type
      if (typeof parsedBody.message === 'string') errorMessage = parsedBody.message
    } catch { /* ignore */ }
    throw new BulkSaveError(res.status, errorType, errorMessage, parsedBody)
  }
  return res.json() as Promise<{ updated: string[] }>
}

// ── Error types ───────────────────────────────────────────────────────────────

/** Thrown when the server returns 401 — wrong PIN or expired session. */
export class AuthError extends Error {
  readonly code: string
  constructor(code: string) {
    super(`Auth error: ${code}`)
    this.name = 'AuthError'
    this.code = code
  }
}

/** Thrown when the server returns 429 — rate limit exceeded. */
export class RateLimitError extends Error {
  readonly retryAfterSeconds: number
  constructor(retryAfterSeconds: number) {
    super(`Rate limited — retry after ${retryAfterSeconds}s`)
    this.name = 'RateLimitError'
    this.retryAfterSeconds = retryAfterSeconds
  }
}

/**
 * Thrown by ``adminBulkSave`` and the import upload functions on a non-200 response.
 *
 * ``errorType``    mirrors the server's ``type`` field (e.g. ``boundary_order_error``,
 *                  ``phantom_boundary``).  ``undefined`` for non-400 HTTP errors.
 * ``serverMessage`` mirrors the server's ``message`` field.  ``undefined`` when the
 *                  body was not JSON or contained no ``message`` key.
 * ``body``         the FULL parsed JSON response object (W6 contract).  Callers such as
 *                  ``Import.tsx`` pass ``err.body`` directly to ``parseServerErrors`` /
 *                  ``parseDiff`` without re-parsing a stringified message.  Always set on
 *                  throws from ``uploadImportBoundaries`` and ``uploadImportSettings``; may
 *                  be an empty object ``{}`` when the server returned non-JSON.
 */
export class BulkSaveError extends Error {
  readonly status: number
  readonly errorType: string | undefined
  readonly serverMessage: string | undefined
  readonly body: Record<string, unknown>
  constructor(
    status: number,
    errorType?: string,
    serverMessage?: string,
    body: Record<string, unknown> = {},
  ) {
    super(serverMessage ?? `Bulk save failed: ${status}`)
    this.name = 'BulkSaveError'
    this.status = status
    this.errorType = errorType
    this.serverMessage = serverMessage
    this.body = body
  }
}

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

const BASE = ''

// Import the admin store to read the CSRF token.
// This is a direct import (not lazy) — the store module has no circular
// dependency on adminClient because adminClient does not import from the store.
import { useAdminStore } from '../state/adminStore'

/** Read CSRF token from the Zustand store at call time (avoids stale closure). */
function getCsrfToken(): string {
  return useAdminStore.getState().csrfToken ?? ''
}

/** Central fetch wrapper: adds credentials + optional CSRF header. */
async function adminFetch(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const method = (options.method ?? 'GET').toUpperCase()
  const isMutating = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
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
 * On 400, throws ``BulkSaveError`` carrying the server's ``message`` and
 * ``type`` fields so callers can surface structured error text to the user.
 */
export async function adminBulkSave(
  updates: CubeBoundaryEdit[],
  idempotencyKey: string,
): Promise<CommitResponse> {
  const res = await adminFetch('/api/admin/cubes/bulk', {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ updates }),
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
 * Thrown by ``adminBulkSave`` on a non-200 response.
 *
 * ``errorType``    mirrors the server's ``type`` field (e.g. ``boundary_order_error``,
 *                  ``phantom_boundary``).  ``undefined`` for non-400 HTTP errors.
 * ``serverMessage`` mirrors the server's ``message`` field.  ``undefined`` when the
 *                  body was not JSON or contained no ``message`` key.
 */
export class BulkSaveError extends Error {
  readonly status: number
  readonly errorType: string | undefined
  readonly serverMessage: string | undefined
  constructor(status: number, errorType?: string, serverMessage?: string) {
    super(serverMessage ?? `Bulk save failed: ${status}`)
    this.name = 'BulkSaveError'
    this.status = status
    this.errorType = errorType
    this.serverMessage = serverMessage
  }
}

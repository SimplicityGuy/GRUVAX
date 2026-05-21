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
  AdminSession,
  AdminSettings,
  AdminSettingsPut,
  ChangePinPayload,
  LoginResponse,
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

/** PUT /api/admin/settings — updates whitelisted settings keys. */
export async function putAdminSettings(payload: AdminSettingsPut): Promise<AdminSettings> {
  const res = await adminFetch('/api/admin/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    throw new Error(`Settings update failed: ${res.status}`)
  }
  return res.json() as Promise<AdminSettings>
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

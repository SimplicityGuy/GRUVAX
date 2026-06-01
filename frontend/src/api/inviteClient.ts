/**
 * Invite-code API client for GRUVAX (Phase 7 / AUTH-02 + API-04).
 *
 * Two call patterns:
 *   - Public (no auth): publicFetch helper — credentials 'omit', no CSRF.
 *     Used for GET /api/invite-codes/{code} and POST /api/invite-codes/{code}/redeem.
 *   - Owner (PIN-gated): uses the shared adminFetch from adminClient.ts — CSRF attached.
 *     Used for POST /api/admin/profiles/{id}/invite.
 *
 * T-07-13: PAT travels only in the POST body; it is never stored in
 * localStorage/sessionStorage/URL by this client.
 */

import { adminFetch } from './adminClient'
import type { GeneratedInvite, InviteCodeInfo, RedeemResult } from './types'

const BASE = ''

/** Error thrown by public invite endpoints — carries `errorType` from detail.type. */
export class RedeemApiError extends Error {
  readonly status: number
  readonly errorType: string | undefined
  constructor(status: number, errorType?: string, message?: string) {
    super(message ?? `Redeem API error: ${status}`)
    this.name = 'RedeemApiError'
    this.status = status
    this.errorType = errorType
  }
}

/** Parse a RedeemApiError from a non-OK Response. */
async function parseRedeemError(res: Response): Promise<RedeemApiError> {
  let errorType: string | undefined
  let message: string | undefined
  try {
    const body = await res.json() as Record<string, unknown>
    // Backend wraps error info in detail object (FastAPI HTTPException pattern)
    const detail = body.detail
    if (detail && typeof detail === 'object') {
      const d = detail as Record<string, unknown>
      if (typeof d.type === 'string') errorType = d.type
      if (typeof d.message === 'string') message = d.message
    } else if (typeof body.type === 'string') {
      errorType = body.type
      if (typeof body.message === 'string') message = body.message
    }
  } catch {
    // Non-JSON body — leave errorType/message undefined
  }
  return new RedeemApiError(res.status, errorType, message)
}

/**
 * Public fetch helper: no credentials, no CSRF.
 * Used only for the public invite endpoints (no session cookie needed — D-03).
 */
async function publicFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  return fetch(`${BASE}${path}`, {
    ...options,
    credentials: 'omit',
    headers,
  })
}

/**
 * GET /api/invite-codes/{code} — validate invite code (public, no auth).
 *
 * Returns InviteCodeInfo on success (200).
 * Throws RedeemApiError with errorType 'invite_not_found' on 404.
 * The backend returns a uniform 404 for expired / used / invalid codes (T-07-10).
 */
export async function getInviteCode(code: string): Promise<InviteCodeInfo> {
  const res = await publicFetch(`/api/invite-codes/${encodeURIComponent(code)}`)
  if (!res.ok) {
    throw await parseRedeemError(res)
  }
  return res.json() as Promise<InviteCodeInfo>
}

/**
 * POST /api/invite-codes/{code}/redeem — redeem invite code with a PAT (public, no auth).
 *
 * Returns RedeemResult { status: 'connected', profile_id } on success (200).
 * Throws RedeemApiError on:
 *   - 404: invite_not_found (expired / used / invalid)
 *   - 401: pat_rejected
 *   - 409: user_id_collision
 *   - 503: upstream_unavailable
 *   - 429: rate_limited
 *
 * T-07-13: pat is sent only in the POST body and is never persisted by this client.
 */
export async function redeemInviteCode(code: string, pat: string): Promise<RedeemResult> {
  const res = await publicFetch(`/api/invite-codes/${encodeURIComponent(code)}/redeem`, {
    method: 'POST',
    body: JSON.stringify({ pat }),
  })
  if (!res.ok) {
    throw await parseRedeemError(res)
  }
  return res.json() as Promise<RedeemResult>
}

/**
 * POST /api/admin/profiles/{id}/invite — generate a 1-hour invite link (owner, PIN-gated).
 *
 * Uses adminFetch so the CSRF token and session cookie are attached automatically.
 * Returns GeneratedInvite { code, url, expires_at } on success (200).
 * D-09: server voids any prior active invite for the same profile atomically.
 */
export async function generateInvite(profileId: string): Promise<GeneratedInvite> {
  const res = await adminFetch(`/api/admin/profiles/${profileId}/invite`, {
    method: 'POST',
  })
  if (!res.ok) {
    throw new Error(`Failed to generate invite: ${res.status}`)
  }
  return res.json() as Promise<GeneratedInvite>
}

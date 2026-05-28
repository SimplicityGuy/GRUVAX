/**
 * Session API client — browse-binding session layer (Plan 02-04).
 *
 * No auth headers (R7 — browse-binding is PIN-free).
 * Cookie gruvax_browse_binding is set/cleared server-side on bind/unbind.
 * The SPA reads the cookie value to build per-profile SSE URLs (httponly=False).
 */

export interface ProfileSummary {
  id: string
  display_name: string
  last_sync_at: string | null
  last_sync_status: string | null
  last_sync_item_count: number | null
  app_token_revoked: boolean
}

export interface SessionData {
  profile_count: number
  bound_profile_id: string | null
  profiles: ProfileSummary[]
}

/**
 * GET /api/session — returns the current browse-binding state.
 *
 * Single-profile auto-bind: the server sets gruvax_browse_binding cookie
 * and returns bound_profile_id in the same response (D2-08).
 * Multi-profile unbound: returns bound_profile_id: null → SPA routes to /select.
 */
export async function getSession(): Promise<SessionData> {
  const res = await fetch('/api/session')
  if (!res.ok) {
    throw new Error(`Session fetch failed: ${res.status}`)
  }
  return res.json() as Promise<SessionData>
}

/**
 * POST /api/session/bind — bind the browse session to a profile.
 * Sets gruvax_browse_binding cookie on success (non-destructive, no confirm needed).
 */
export async function bindProfile(profileId: string): Promise<void> {
  const res = await fetch('/api/session/bind', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile_id: profileId }),
  })
  if (!res.ok) {
    throw new Error(`Bind failed: ${res.status}`)
  }
}

/**
 * DELETE /api/session/bind — unbind the browse session (clears cookie).
 * Used by SwitchProfileButton's confirm flow.
 */
export async function unbindProfile(): Promise<void> {
  const res = await fetch('/api/session/bind', { method: 'DELETE' })
  if (!res.ok) {
    throw new Error(`Unbind failed: ${res.status}`)
  }
}

import type { CubeContentsResponse, CubesWithFillResponse } from './cubeTypes'
import type { CubesResponse, LocateResult, SearchResponse, UnitsResponse } from './types'
import { useSessionStore } from '../state/sessionStore'

/**
 * Fetch wrappers for the GRUVAX backend API.
 *
 * In dev, Vite proxies /api → localhost:8000 (vite.config.ts).
 * In production, FastAPI serves the built SPA and /api routes from the same origin.
 *
 * Phase 6 (06-02): shared 403 device_revoked intercept (D-06, T-06-06).
 * When any fetch returns HTTP 403 and the JSON body has detail.type === 'device_revoked',
 * this module calls useSessionStore.getState().triggerRevoke() (mount-independent —
 * no React component needs to be mounted) and throws Error('device_revoked').
 * The App.tsx global revoke effect consumes revokePending as the SINGLE handler.
 */

const BASE = ''

/**
 * Shared 403 device_revoked check — called by every fetch wrapper after a non-ok response.
 *
 * Reads the JSON body; if detail.type === 'device_revoked', fires the revoke signal
 * (mount-independent) and throws Error('device_revoked').
 *
 * Returns the original response so the caller can continue its own error handling
 * if this check does not throw.
 */
async function check403Revoke(res: Response): Promise<Response> {
  if (res.status === 403) {
    try {
      const body = await res.json() as { detail?: { type?: string } }
      if (body?.detail?.type === 'device_revoked') {
        // Fire mount-independent revoke signal — even if no component is mounted (D-06)
        useSessionStore.getState().triggerRevoke()
        throw new Error('device_revoked')
      }
    } catch (err) {
      // Re-throw device_revoked errors; swallow JSON parse failures (malformed body)
      if (err instanceof Error && err.message === 'device_revoked') {
        throw err
      }
    }
  }
  return res
}

export async function searchCollection(
  q: string,
  limit = 10,
  profileId?: string,
): Promise<SearchResponse> {
  const paramObj: Record<string, string> = { q, limit: String(limit) }
  if (profileId) paramObj.profile_id = profileId
  const params = new URLSearchParams(paramObj)
  const res = await fetch(`${BASE}/api/search?${params}`)
  if (!res.ok) {
    await check403Revoke(res)
    throw new Error(`Search failed: ${res.status}`)
  }
  return res.json() as Promise<SearchResponse>
}

export async function locateRelease(releaseId: number, profileId?: string): Promise<LocateResult> {
  const paramObj: Record<string, string> = { release_id: String(releaseId) }
  if (profileId) paramObj.profile_id = profileId
  const params = new URLSearchParams(paramObj)
  const res = await fetch(`${BASE}/api/locate?${params}`)
  if (!res.ok) {
    await check403Revoke(res)
    if (res.status === 404) {
      throw new Error('release_not_in_collection')
    }
    throw new Error(`Locate failed: ${res.status}`)
  }
  return res.json() as Promise<LocateResult>
}

export async function fetchUnits(): Promise<UnitsResponse> {
  const res = await fetch(`${BASE}/api/units`)
  if (!res.ok) {
    await check403Revoke(res)
    throw new Error(`Units fetch failed: ${res.status}`)
  }
  return res.json() as Promise<UnitsResponse>
}

export async function fetchCubes(): Promise<CubesResponse> {
  const res = await fetch(`${BASE}/api/cubes`)
  if (!res.ok) {
    await check403Revoke(res)
    throw new Error(`Cubes fetch failed: ${res.status}`)
  }
  return res.json() as Promise<CubesResponse>
}

/**
 * Fetch all cube boundaries including fill_level from the in-memory snapshot.
 *
 * Returns the same shape as fetchCubes() but with fill_level added per cube
 * (CUBE-07 — used to render fill bars on the kiosk grid).
 */
export async function fetchCubesWithFill(): Promise<CubesWithFillResponse> {
  const res = await fetch(`${BASE}/api/cubes`)
  if (!res.ok) {
    await check403Revoke(res)
    throw new Error(`Cubes fetch failed: ${res.status}`)
  }
  return res.json() as Promise<CubesWithFillResponse>
}

/**
 * Fetch one cube's boundary metadata + fill level + sampled records.
 *
 * Public endpoint — no auth required (D-15). Used by CubeContentsPanel
 * to show the reverse-lookup side panel on cube tap (CUBE-09, D-14).
 *
 * Throws Error('cube_not_found') on 404 (nonexistent cube).
 */
export async function fetchCubeContents(
  unitId: number,
  row: number,
  col: number,
): Promise<CubeContentsResponse> {
  const res = await fetch(`${BASE}/api/cubes/${unitId}/${row}/${col}`)
  if (!res.ok) {
    await check403Revoke(res)
    if (res.status === 404) throw new Error('cube_not_found')
    throw new Error(`Cube contents fetch failed: ${res.status}`)
  }
  return res.json() as Promise<CubeContentsResponse>
}

/**
 * POST /api/illuminate — fire-and-forget LED fan-out after a locate.
 *
 * Phase 6: sends the LocateResult the kiosk already holds to the server so it
 * can fan out MQTT messages to the physical LED strips.
 *
 * D-03: public endpoint — no auth header, no CSRF, no adminFetch.
 * The caller should .catch(() => {}) because the broker may be in degraded mode.
 *
 * Throws Error on non-2xx so the caller can decide whether to swallow it.
 */
export async function illuminateRecord(result: LocateResult): Promise<void> {
  const res = await fetch(`${BASE}/api/illuminate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(result),
  })
  if (!res.ok) {
    await check403Revoke(res)
    throw new Error(`Illuminate failed: ${res.status}`)
  }
}

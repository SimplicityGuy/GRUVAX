import type { CubeContentsResponse, CubesWithFillResponse } from './cubeTypes'
import type { CubesResponse, LocateResult, SearchResponse, UnitsResponse } from './types'

/**
 * Fetch wrappers for the GRUVAX backend API.
 *
 * In dev, Vite proxies /api → localhost:8000 (vite.config.ts).
 * In production, FastAPI serves the built SPA and /api routes from the same origin.
 */

const BASE = ''

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
    throw new Error(`Units fetch failed: ${res.status}`)
  }
  return res.json() as Promise<UnitsResponse>
}

export async function fetchCubes(): Promise<CubesResponse> {
  const res = await fetch(`${BASE}/api/cubes`)
  if (!res.ok) {
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
    throw new Error(`Illuminate failed: ${res.status}`)
  }
}

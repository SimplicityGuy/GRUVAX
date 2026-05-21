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
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q, limit: String(limit) })
  const res = await fetch(`${BASE}/api/search?${params}`)
  if (!res.ok) {
    throw new Error(`Search failed: ${res.status}`)
  }
  return res.json() as Promise<SearchResponse>
}

export async function locateRelease(releaseId: number): Promise<LocateResult> {
  const params = new URLSearchParams({ release_id: String(releaseId) })
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

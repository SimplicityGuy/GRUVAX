import type { LocateResult, SearchResponse, UnitsResponse } from './types'

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

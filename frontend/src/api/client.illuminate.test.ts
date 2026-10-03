import { afterEach, describe, expect, it, vi } from 'vitest'
import { illuminateRecord } from './client'
import type { LocateResult } from './types'

const result: LocateResult = {
  release_id: 42,
  primary_cube: { unit_id: 1, row: 0, col: 0 },
  label_span: [],
  sub_cube_interval: null,
  confidence: 0.8,
  generated_at: '2026-10-03T00:00:00Z',
  estimator_version: 'test',
}

afterEach(() => vi.unstubAllGlobals())

describe('profile settings on illumination', () => {
  it.each(['aabbccdd-1234-5678-9012-123456789012', 'profile with spaces'])(
    'sends the captured profile %s',
    async (profile) => {
      const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
      vi.stubGlobal('fetch', fetch)
      await illuminateRecord(result, profile)
      const [url, request] = fetch.mock.calls[0]
      expect(new URL(url, 'http://test').searchParams.get('profile_id')).toBe(profile)
      expect(request.method).toBe('POST')
      expect(JSON.parse(request.body)).toEqual(result)
    },
  )

  it('preserves the public unbound/default request', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await illuminateRecord(result)
    expect(fetch.mock.calls[0][0]).toBe('/api/illuminate')
  })
})

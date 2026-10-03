/**
 * ResultsList locate-scoping regression tests (gap 02-09 follow-up).
 *
 * The /api/locate endpoint declares `profile_id` as a REQUIRED query param
 * (locate.py). ResultsList previously called locateRelease(release_id) WITHOUT
 * the bound profile id, so every auto-locate / select 422'd and was swallowed
 * by the .catch — leaving NO cube lit AND never setting shelfLayoutUnavailable
 * (the affordance was unreachable). These tests lock in that ResultsList passes
 * the bound profileId on both the auto-locate-top path and the explicit-select
 * path, matching KioskView's relocate path.
 *
 * Test 1: auto-locate-top calls locateRelease(id, boundProfileId)
 * Test 2: explicit row select calls locateRelease(id, boundProfileId)
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'

// ── Module mock (must be top-level for vitest hoisting) ──────────────────────
vi.mock('../../api/client', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/client')>()
  return {
    ...real,
    locateRelease: vi.fn().mockResolvedValue({
      release_id: 1156,
      primary_cube: null,
      label_span: [],
      sub_cube_interval: null,
      confidence: 0,
    }),
    illuminateRecord: vi.fn().mockResolvedValue(undefined),
  }
})

// Import after vi.mock so we get the mocked versions
import { illuminateRecord, locateRelease } from '../../api/client'
import { ResultsList } from './ResultsList'
import { useGruvaxStore } from '../../state/store'
import { useSessionStore } from '../../state/sessionStore'
import type { LocateResult, SearchResult } from '../../api/types'

const TEST_PROFILE_ID = '00000000-0000-0000-0000-000000000001'

const ITEMS: SearchResult[] = [
  {
    release_id: 1156,
    title: 'Verve Title 6',
    primary_artist: 'Artist 1156',
    label: 'Verve',
    catalog_number: 'V-6',
    format: 'LP',
    year: 1960,
    rank: 1,
  },
  {
    release_id: 1157,
    title: 'Verve Title 7',
    primary_artist: 'Artist 1157',
    label: 'Verve',
    catalog_number: 'V-7',
    format: 'LP',
    year: 1961,
    rank: 2,
  },
]

beforeEach(() => {
  useGruvaxStore.setState({ selectedReleaseId: null, shelfLayoutUnavailable: false })
  useSessionStore.setState({
    profileCount: 1,
    boundProfileId: TEST_PROFILE_ID,
    profiles: [],
  })
  vi.mocked(locateRelease).mockClear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('ResultsList locate profile scoping (02-09 regression)', () => {
  it('Test 1: auto-locate-top passes the bound profileId to locateRelease', async () => {
    await act(async () => {
      render(<ResultsList items={ITEMS} showNoResults={false} open />)
      await Promise.resolve()
    })

    expect(locateRelease).toHaveBeenCalledWith(1156, TEST_PROFILE_ID)
  })

  it('Test 2: explicit row select passes the bound profileId to locateRelease', async () => {
    await act(async () => {
      render(<ResultsList items={ITEMS} showNoResults={false} open />)
      await Promise.resolve()
    })
    vi.mocked(locateRelease).mockClear()

    // Click the second result row (explicit select path).
    const row = screen.getByText(/Verve Title 7/)
    await act(async () => {
      row.click()
      await Promise.resolve()
    })

    expect(locateRelease).toHaveBeenCalledWith(1157, TEST_PROFILE_ID)
  })
})

describe('ResultsList pending locate cleanup (gruvax-d5p6)', () => {
  it('does not light or illuminate a result after the list unmounts', async () => {
    useGruvaxStore.getState().clearSearch()
    let resolve!: (result: LocateResult) => void
    vi.mocked(locateRelease).mockReturnValueOnce(
      new Promise<LocateResult>((yes) => {
        resolve = yes
      }),
    )
    const view = render(<ResultsList items={ITEMS} showNoResults={false} open />)
    view.unmount()
    await act(async () => {
      resolve({
        release_id: ITEMS[0].release_id,
        primary_cube: { unit_id: 1, row: 0, col: 0 },
        label_span: [],
        sub_cube_interval: null,
        confidence: 0.8,
        generated_at: '2026-10-03T00:00:00Z',
        estimator_version: 'test',
      })
    })
    expect(useGruvaxStore.getState().highlight.primaryCube).toBeNull()
    expect(illuminateRecord).not.toHaveBeenCalled()
  })
})

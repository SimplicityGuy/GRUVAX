/**
 * RecentlyPulledStrip — chip-tap locate wiring test (gruvax-5zu).
 *
 * Regression test for: tapping a recently-pulled chip only wrote
 * selectedReleaseId to the store and never called /api/locate, so the strip
 * did nothing on tap (no cube highlight, no MQTT illuminate). The fix routes
 * the tap through the same locateAndIlluminate sequence ResultsList uses.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

import { RecentlyPulledStrip } from './RecentlyPulledStrip'
import { useGruvaxStore } from '../../state/store'
import { useRecentlyPulledStore } from '../../state/recentlyPulledStore'
import { useSessionStore } from '../../state/sessionStore'

const TEST_PROFILE_ID = '00000000-0000-0000-0000-000000000099'

// vi.mock factories are hoisted — the mocked LocateResult must be declared via
// vi.hoisted so it exists before the factory (below) runs.
const { LOCATED } = vi.hoisted(() => ({
  LOCATED: {
    release_id: 42,
    primary_cube: { unit_id: 1, row: 0, col: 0 },
    label_span: [],
    sub_cube_interval: null,
    confidence: 0.8,
    generated_at: new Date().toISOString(),
    estimator_version: 'v1',
  },
}))

vi.mock('../../api/client', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/client')>()
  return {
    ...real,
    locateRelease: vi.fn().mockResolvedValue(LOCATED),
    illuminateRecord: vi.fn().mockResolvedValue(undefined),
  }
})

import { illuminateRecord, locateRelease } from '../../api/client'

beforeEach(() => {
  useSessionStore.setState({ boundProfileId: TEST_PROFILE_ID })

  useGruvaxStore.setState({
    selectedReleaseId: null,
    highlight: { primaryCube: null },
  })

  useRecentlyPulledStore.setState({ items: [] })
  useRecentlyPulledStore.getState().addItem({
    release_id: 42,
    title: 'Kind of Blue',
    primary_artist: 'Miles Davis',
    catalog_number: 'CS 8163',
  })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('RecentlyPulledStrip — chip tap', () => {
  it('fires locate + illuminate and updates the store, not just selectedReleaseId', async () => {
    render(<RecentlyPulledStrip />)

    const chip = screen.getByRole('button', {
      name: /Miles Davis – Kind of Blue, catalog number CS 8163/i,
    })
    fireEvent.click(chip)

    // Bookkeeping write still happens...
    expect(useGruvaxStore.getState().selectedReleaseId).toBe(42)

    // ...but critically, it must ALSO trigger the locate call (the bug: it didn't).
    expect(locateRelease).toHaveBeenCalledTimes(1)
    expect(locateRelease).toHaveBeenCalledWith(42, TEST_PROFILE_ID)

    await vi.waitFor(() => {
      expect(useGruvaxStore.getState().highlight.primaryCube).toEqual(LOCATED.primary_cube)
    })
    expect(illuminateRecord).toHaveBeenCalledTimes(1)
    expect(illuminateRecord).toHaveBeenCalledWith(LOCATED)
  })
})

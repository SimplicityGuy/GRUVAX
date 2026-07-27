/**
 * KioskView — the lit cube scrolls into view (gruvax-k0zj).
 *
 * Regression test for: nothing in the kiosk ever called scrollIntoView, so a
 * search that lit a cube below the fold left the visible viewport showing an
 * unlit grid (.shelf-area is min-height:100dvh and just grows). This asserts
 * the GSAP selection-lands effect calls scrollIntoView on the newly-lit
 * `[data-state="lit"]` element every time a locate result lands.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { KioskView } from './KioskView'
import { useGruvaxStore } from '../../state/store'
import { useRecentlyPulledStore } from '../../state/recentlyPulledStore'
import { useSessionStore } from '../../state/sessionStore'

const mockAdminState = { isLoggedIn: false }

vi.mock('../../state/adminStore', () => {
  return {
    useAdminStore: (selector: (s: { isLoggedIn: boolean }) => unknown) =>
      selector(mockAdminState),
  }
})

// vi.mock factories are hoisted — SEARCH_ITEM must be declared via vi.hoisted
// so it exists before the factory (below) runs.
const { SEARCH_ITEM } = vi.hoisted(() => ({
  SEARCH_ITEM: {
    release_id: 42,
    title: 'Kind of Blue',
    primary_artist: 'Miles Davis',
    label: 'Columbia',
    catalog_number: 'CS 8163',
    format: 'Vinyl',
    year: 1959,
    rank: 1,
  },
}))

vi.mock('../../api/client', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/client')>()
  return {
    ...real,
    locateRelease: vi.fn().mockResolvedValue({
      release_id: 42,
      // Row 3 (0-indexed) of the 4x4 fallback grid — same shape a below-the-fold
      // row-4 lit cube takes; the fix must not care which row it is.
      primary_cube: { unit_id: 1, row: 3, col: 0 },
      label_span: [],
      sub_cube_interval: null,
      confidence: 0.8,
      generated_at: new Date().toISOString(),
      estimator_version: 'v1',
    }),
    illuminateRecord: vi.fn().mockResolvedValue(undefined),
    searchCollection: vi.fn().mockResolvedValue({ items: [SEARCH_ITEM], took_ms: 1, did_you_mean: null }),
    fetchUnits: vi.fn().mockResolvedValue({ units: [] }),
    fetchCubesWithFill: vi.fn().mockResolvedValue({ cubes: [] }),
  }
})

vi.mock('../../api/session', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/session')>()
  return {
    ...real,
    getSession: vi.fn(),
  }
})

import { getSession } from '../../api/session'

class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener() {}
  close() {}
}
vi.stubGlobal('EventSource', MockEventSource)

function makeStorageMock() {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v
    },
    removeItem: (k: string) => {
      delete store[k]
    },
    clear: () => {
      for (const k in store) delete store[k]
    },
    get length() {
      return Object.keys(store).length
    },
    key: (i: number) => Object.keys(store)[i] ?? null,
  }
}
vi.stubGlobal('localStorage', makeStorageMock())
vi.stubGlobal('sessionStorage', makeStorageMock())

const TEST_PROFILE_ID = '00000000-0000-0000-0000-000000000099'

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
}

function renderKiosk() {
  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <KioskView />
    </QueryClientProvider>,
  )
}

async function typeQuery(text: string) {
  const input = screen.getByRole('searchbox', { name: /search vinyl collection/i })
  fireEvent.change(input, { target: { value: text } })
  await act(async () => {
    await new Promise((r) => setTimeout(r, 300))
  })
}

let scrollIntoViewSpy: ReturnType<typeof vi.fn>

beforeEach(() => {
  MockEventSource.instances = []

  // jsdom does not implement scrollIntoView at all — stub it so the real
  // implementation's guard (`typeof el.scrollIntoView === 'function'`) takes
  // the call path instead of skipping it.
  scrollIntoViewSpy = vi.fn()
  Element.prototype.scrollIntoView = scrollIntoViewSpy as unknown as Element['scrollIntoView']

  vi.mocked(getSession).mockResolvedValue({
    profile_count: 1,
    bound_profile_id: TEST_PROFILE_ID,
    profiles: [
      {
        id: TEST_PROFILE_ID,
        display_name: 'Test Profile',
        last_sync_at: null,
        last_sync_status: 'completed',
        last_sync_item_count: 100,
        app_token_revoked: false,
      },
    ],
    is_device_paired: true,
    needs_reauth: false,
  })

  useSessionStore.setState({
    profileCount: 1,
    boundProfileId: TEST_PROFILE_ID,
    profiles: [
      {
        id: TEST_PROFILE_ID,
        display_name: 'Test Profile',
        last_sync_at: null,
        last_sync_status: 'completed',
        last_sync_item_count: 100,
        app_token_revoked: false,
      },
    ],
    revokePending: false,
    reassignBanner: null,
  })

  useGruvaxStore.setState({
    selectedReleaseId: null,
    selectedResult: null,
    query: '',
    highlight: { primaryCube: null },
    connectivity: { sseConnected: false, lastSeenAt: 0, everConnected: false, bannerVisible: false },
  })

  mockAdminState.isLoggedIn = false
  useRecentlyPulledStore.getState().clear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('KioskView — lit cube scrolls into view (gruvax-k0zj)', () => {
  it('calls scrollIntoView on the [data-state="lit"] cube once a locate result lands', async () => {
    await act(async () => {
      renderKiosk()
    })

    await typeQuery('miles')

    await waitFor(() => {
      expect(scrollIntoViewSpy).toHaveBeenCalled()
    })

    // Called on the actual lit element, not some other node in the grid.
    const litEl = document.querySelector('[data-state="lit"]')
    expect(litEl).not.toBeNull()
    expect(scrollIntoViewSpy.mock.instances[scrollIntoViewSpy.mock.calls.length - 1]).toBe(litEl)
    expect(scrollIntoViewSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ block: 'center' }),
    )
  })
})

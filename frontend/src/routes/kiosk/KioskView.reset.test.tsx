/**
 * KioskView — Reset kiosk / idle wipe must close the results dropdown (gruvax-b76z).
 *
 * Regression test for: handleReset and the idle timer called only clearSearch()
 * (a Zustand store action) which cannot reach debouncedQuery/dismissedQuery
 * (component-local useState). resultsOpen stayed derived from the stale
 * debouncedQuery, so RESET KIOSK emptied the search box but left the previous
 * user's results dropdown open indefinitely (PRIV-04 wipe incomplete).
 *
 * Covers exactly the two behaviors the fix promises:
 *   1. Reset → dropdown closed.
 *   2. Retype the SAME query afterwards → dropdown opens again (proves
 *      dismissedQuery was reset too, not just debouncedQuery — a stale
 *      dismissedQuery equal to the retyped query would otherwise suppress it).
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
    useAdminStore: (selector: (s: { isLoggedIn: boolean }) => unknown) => selector(mockAdminState),
  }
})

const SEARCH_ITEM = {
  release_id: 42,
  title: 'Kind of Blue',
  primary_artist: 'Miles Davis',
  label: 'Columbia',
  catalog_number: 'CS 8163',
  format: 'Vinyl',
  year: 1959,
  rank: 1,
}

vi.mock('../../api/client', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/client')>()
  return {
    ...real,
    locateRelease: vi.fn().mockResolvedValue({
      release_id: 42,
      primary_cube: { unit_id: 1, row: 0, col: 0 },
      label_span: [],
      sub_cube_interval: null,
      confidence: 0.8,
      generated_at: new Date().toISOString(),
      estimator_version: 'v1',
    }),
    illuminateRecord: vi.fn().mockResolvedValue(undefined),
    searchCollection: vi
      .fn()
      .mockImplementation((query: string) =>
        Promise.resolve(
          query.trim().length > 0
            ? { items: [SEARCH_ITEM], took_ms: 1, did_you_mean: null }
            : { items: [], took_ms: 1, did_you_mean: null },
        ),
      ),
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
  // SearchBox debounces onDebouncedQuery by 250ms (SRCH-06).
  await act(async () => {
    await new Promise((r) => setTimeout(r, 300))
  })
}

beforeEach(() => {
  MockEventSource.instances = []

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
    connectivity: {
      sseConnected: false,
      lastSeenAt: 0,
      everConnected: false,
      bannerVisible: false,
    },
  })

  mockAdminState.isLoggedIn = false
  useRecentlyPulledStore.getState().clear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('KioskView — Reset kiosk clears the results dropdown (gruvax-b76z)', () => {
  it('reset closes the dropdown, and retyping the same query afterwards reopens it', async () => {
    await act(async () => {
      renderKiosk()
    })

    // 1. Search — dropdown opens with a result.
    await typeQuery('miles')
    await waitFor(() => {
      expect(screen.getByRole('listbox', { name: /search results/i })).toBeInTheDocument()
    })

    // 2. Reset kiosk (confirm through the alertdialog).
    fireEvent.click(screen.getByRole('button', { name: /reset kiosk/i }))
    fireEvent.click(screen.getByRole('button', { name: /clear and reset/i }))

    // The search box itself is emptied...
    const input = screen.getByRole('searchbox', { name: /search vinyl collection/i })
    expect(input).toHaveValue('')

    // ...AND the results dropdown must be gone — not left stuck open over an
    // empty box showing the previous user's results (the bug).
    await waitFor(() => {
      expect(screen.queryByRole('listbox', { name: /search results/i })).not.toBeInTheDocument()
    })

    // 3. Retype the SAME query as before the reset — the dropdown must reopen.
    // (Proves dismissedQuery was reset too: a stale dismissedQuery === 'miles'
    // would otherwise suppress resultsOpen even though debouncedQuery matches.)
    await typeQuery('miles')
    await waitFor(() => {
      expect(screen.getByRole('listbox', { name: /search results/i })).toBeInTheDocument()
    })
  })
})

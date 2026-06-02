/**
 * KioskView — recently-pulled strip + Reset button wiring tests (08-03 Task 3).
 *
 * Tests:
 *   1. POSITIVE: a successful locate (selectedResult non-null + cube highlight) calls
 *      addItem exactly once with { release_id, title, primary_artist, catalog_number }
 *   2. NEGATIVE (D-05 guard): a search returning no cube highlight (null result) does
 *      NOT call addItem — typo/no-result searches never enter the recently-pulled list
 *   3. Reset button is absent when useAdminStore.isLoggedIn is true (D-10)
 *   4. Reset button is present when useAdminStore.isLoggedIn is false (D-10)
 *
 * These tests are RED until KioskView wires addItem and the Reset button in Task 3.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { KioskView } from './KioskView'
import { useGruvaxStore } from '../../state/store'
import { useRecentlyPulledStore } from '../../state/recentlyPulledStore'
import { useSessionStore } from '../../state/sessionStore'

// ── Module mock — needed to prevent real API calls and stub admin state ───────
// vi.mock factories are hoisted — do NOT reference outer const variables inside.
// Set mock return values in beforeEach instead.

// isLoggedIn state for the adminStore mock — toggled per test
const mockAdminState = { isLoggedIn: false }

vi.mock('../../state/adminStore', () => {
  return {
    useAdminStore: (selector: (s: { isLoggedIn: boolean }) => unknown) =>
      selector(mockAdminState),
  }
})

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
    searchCollection: vi.fn().mockResolvedValue({ items: [], took_ms: 1, did_you_mean: null }),
    fetchUnits: vi.fn().mockResolvedValue({ units: [] }),
    fetchCubesWithFill: vi.fn().mockResolvedValue({ cubes: [] }),
  }
})

vi.mock('../../api/session', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/session')>()
  return {
    ...real,
    // Return value configured in beforeEach to avoid outer-variable hoisting issue
    getSession: vi.fn(),
  }
})

import { getSession } from '../../api/session'

// Stub EventSource to avoid errors from the SSE useEffect
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor(url: string) { this.url = url; MockEventSource.instances.push(this) }
  addEventListener() {}
  close() {}
}
vi.stubGlobal('EventSource', MockEventSource)

// Provide in-memory localStorage / sessionStorage so Zustand persist doesn't error
function makeStorageMock() {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v },
    removeItem: (k: string) => { delete store[k] },
    clear: () => { for (const k in store) delete store[k] },
    get length() { return Object.keys(store).length },
    key: (i: number) => Object.keys(store)[i] ?? null,
  }
}
vi.stubGlobal('localStorage', makeStorageMock())
vi.stubGlobal('sessionStorage', makeStorageMock())

const TEST_PROFILE_ID = '00000000-0000-0000-0000-000000000099'

const TEST_RESULT = {
  release_id: 42,
  title: 'Kind of Blue',
  primary_artist: 'Miles Davis',
  catalog_number: 'CS 8163',
  label: 'Columbia',
  format: 'Vinyl',
  year: 1959,
  rank: 1,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })
}

function renderKiosk(qc: QueryClient) {
  return render(
    <QueryClientProvider client={qc}>
      <KioskView />
    </QueryClientProvider>,
  )
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  MockEventSource.instances = []

  // Configure getSession mock return value here (not in the factory — hoisting issue)
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

  // Seed session store with a bound profile
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

  // Clear KioskView store state
  useGruvaxStore.setState({
    selectedReleaseId: null,
    selectedResult: null,
    query: '',
    highlight: { primaryCube: null },
    connectivity: { sseConnected: false, lastSeenAt: 0, everConnected: false, bannerVisible: false },
  })

  // Set admin state (not logged in by default)
  mockAdminState.isLoggedIn = false

  // Clear recently-pulled store
  useRecentlyPulledStore.getState().clear()
})

afterEach(() => {
  vi.clearAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('KioskView — recently-pulled strip + Reset button wiring', () => {
  it('POSITIVE: successful locate (cube highlight + selectedResult) calls addItem once with identity fields', async () => {
    const addItemSpy = vi.spyOn(useRecentlyPulledStore.getState(), 'addItem')
    const qc = makeQueryClient()

    await act(async () => {
      renderKiosk(qc)
    })

    // Simulate a successful locate: set selectedResult AND a cube highlight
    await act(async () => {
      useGruvaxStore.setState({
        selectedResult: TEST_RESULT,
        highlight: { primaryCube: { unit_id: 1, row: 0, col: 0 } },
        animationToken: 1,
      })
      await Promise.resolve()
      await Promise.resolve()
    })

    // addItem should have been called exactly once with identity fields only
    expect(addItemSpy).toHaveBeenCalledTimes(1)
    expect(addItemSpy).toHaveBeenCalledWith({
      release_id: TEST_RESULT.release_id,
      title: TEST_RESULT.title,
      primary_artist: TEST_RESULT.primary_artist,
      catalog_number: TEST_RESULT.catalog_number,
    })
  })

  it('NEGATIVE (D-05): null selectedResult (no cube highlight) does NOT call addItem', async () => {
    const addItemSpy = vi.spyOn(useRecentlyPulledStore.getState(), 'addItem')
    const qc = makeQueryClient()

    await act(async () => {
      renderKiosk(qc)
    })

    // Simulate a no-result search: highlight is null, selectedResult is null
    await act(async () => {
      useGruvaxStore.setState({
        selectedResult: null,
        highlight: { primaryCube: null },
        animationToken: 2,
      })
      await Promise.resolve()
      await Promise.resolve()
    })

    // addItem must NOT be called for no-result searches (D-05 guard)
    expect(addItemSpy).not.toHaveBeenCalled()
  })

  it('Reset button is ABSENT when useAdminStore.isLoggedIn is true (D-10)', async () => {
    // Admin is logged in — Reset button must be hidden
    mockAdminState.isLoggedIn = true
    const qc = makeQueryClient()

    await act(async () => {
      renderKiosk(qc)
    })

    // The Reset button should not be in the DOM when admin is logged in
    const resetBtn = screen.queryByRole('button', { name: /reset kiosk/i })
    expect(resetBtn).toBeNull()
  })

  it('Reset button is PRESENT when useAdminStore.isLoggedIn is false (D-10)', async () => {
    // Admin is not logged in — Reset button must be visible
    mockAdminState.isLoggedIn = false
    const qc = makeQueryClient()

    await act(async () => {
      renderKiosk(qc)
    })

    // The Reset button should be in the DOM when admin is not logged in
    const resetBtn = screen.queryByRole('button', { name: /reset kiosk/i })
    expect(resetBtn).not.toBeNull()
  })
})

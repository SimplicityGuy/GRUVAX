/**
 * ShelfBinList SSE invalidation tests — Plan 10-02 (D-04), extended 260602-oxg (WARNING-2).
 *
 * Uses MockEventSource to drive the admin SSE consumer in ShelfBinList without
 * a real server. The hook invalidates ['admin','cubes'] on both SSE events.
 *
 * Test 1: collection_changed invalidates ['admin','cubes']
 * Test 2: boundary_changed invalidates ['admin','cubes']
 * Test 3: server_hello invalidates ['admin','cubes'] (WARNING-2 — fill shading refreshes after server restart)
 * Test 3 (close): unmounting ShelfBinList calls es.close() (no leaked connection)
 *
 * Analog: frontend/src/routes/kiosk/KioskView.EventSource.test.tsx
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useSessionStore } from '../../state/sessionStore'
import { ShelfBinList } from './ShelfBinList'
import { MemoryRouter, Route, Routes } from 'react-router'

// ── Module mocks (top-level for vitest hoisting) ────────────────────────────

vi.mock('../../api/adminClient', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/adminClient')>()
  return {
    ...real,
    adminGetCubes: vi.fn().mockResolvedValue({
      cubes: [
        {
          unit_id: 1,
          row: 0,
          col: 0,
          first_label: 'Blue Note',
          first_catalog: 'BLP-4001',
          is_empty: false,
          fill_level: 0.75,
          record_count: 30,
        },
      ],
    }),
    getUnitSegments: vi.fn().mockResolvedValue({ segments: [] }),
  }
})

const TEST_PROFILE_ID = '00000000-0000-0000-0000-000000000001'
const TEST_UNIT = '1'

// ── MockEventSource ──────────────────────────────────────────────────────────
//
// Identical to KioskView.EventSource.test.tsx:69-95. Replaces the global
// EventSource in jsdom. Stores instances for test access.
//
// vi.stubGlobal must happen before the useEffect runs (before render).
// Stubbed at module scope so it applies globally for all tests in this file.

class MockEventSource {
  static instances: MockEventSource[] = []

  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners: Record<string, Array<(e: { data: string }) => void>> = {}
  closeCalled = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(name: string, fn: (e: { data: string }) => void) {
    this.listeners[name] = [...(this.listeners[name] ?? []), fn]
  }

  close() {
    this.closeCalled = true
  }

  /** Helper: dispatch a named SSE event with serialized JSON data. */
  dispatchEvent(name: string, data: unknown) {
    const payload = { data: JSON.stringify(data) }
    this.listeners[name]?.forEach((fn) => fn(payload))
  }
}

vi.stubGlobal('EventSource', MockEventSource)

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
}

/**
 * Render ShelfBinList wrapped in QueryClientProvider + MemoryRouter (unit=1)
 * and wait for effects to flush. Returns the latest MockEventSource instance
 * and the unmount function.
 */
async function renderShelfBinListAndFlush(
  queryClient: QueryClient,
): Promise<{ es: MockEventSource; unmount: () => void }> {
  let unmount!: () => void
  await act(async () => {
    const result = render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/admin/cubes/${TEST_UNIT}`]}>
          <Routes>
            <Route path="/admin/cubes/:unit" element={<ShelfBinList />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    unmount = result.unmount
  })
  const es = MockEventSource.instances[MockEventSource.instances.length - 1]
  return { es, unmount }
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  MockEventSource.instances = []
  // Seed sessionStore with a non-null boundProfileId so the hook opens an EventSource.
  // (With null boundProfileId the hook returns early — no EventSource created.)
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
})

afterEach(() => {
  vi.clearAllMocks()
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('ShelfBinList SSE invalidation (useAdminCubesInvalidation)', () => {
  it('Test 1: collection_changed invalidates [admin, cubes]', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')

    const { es } = await renderShelfBinListAndFlush(qc)

    await act(async () => {
      es.dispatchEvent('collection_changed', {})
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )
    expect(calledKeys).toContainEqual(['admin', 'cubes'])
  })

  it('Test 2: boundary_changed invalidates [admin, cubes]', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')

    const { es } = await renderShelfBinListAndFlush(qc)

    await act(async () => {
      es.dispatchEvent('boundary_changed', {
        cube_ids: [{ unit: 1, row: 0, col: 0 }],
        change_set_id: 'test-set-abc',
      })
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )
    expect(calledKeys).toContainEqual(['admin', 'cubes'])
  })

  it('Test 3: server_hello invalidates [admin, cubes]', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')

    const { es } = await renderShelfBinListAndFlush(qc)

    await act(async () => {
      es.dispatchEvent('server_hello', {})
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )
    expect(calledKeys).toContainEqual(['admin', 'cubes'])
  })

  it('Test 3: unmounting ShelfBinList calls es.close() (no leaked connection)', async () => {
    const qc = makeQueryClient()
    const { es, unmount } = await renderShelfBinListAndFlush(qc)

    // Verify the EventSource was opened at the expected profile URL
    expect(es.url).toBe(`/api/events/${TEST_PROFILE_ID}`)

    // Unmount the component
    await act(async () => {
      unmount()
    })

    // The hook's useEffect cleanup must call es.close()
    expect(es.closeCalled).toBe(true)
  })

  it('Null profileId: no EventSource opened when boundProfileId is null', async () => {
    // Override session store: unbound state (no profile bound yet)
    useSessionStore.setState({ profileCount: 0, boundProfileId: null, profiles: [] })
    MockEventSource.instances = []

    const qc = makeQueryClient()
    await renderShelfBinListAndFlush(qc)

    // Hook must return early — no EventSource should have been created
    expect(MockEventSource.instances.length).toBe(0)
  })
  it('follows null → A → B → null and ignores callbacks from closed streams', async () => {
    useSessionStore.setState({ boundProfileId: null })
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const { unmount } = await renderShelfBinListAndFlush(qc)
    expect(MockEventSource.instances).toHaveLength(0)

    await act(async () => {
      useSessionStore.setState({ boundProfileId: TEST_PROFILE_ID })
    })
    expect(MockEventSource.instances).toHaveLength(1)
    const streamA = MockEventSource.instances[0]
    expect(streamA.url).toBe(`/api/events/${TEST_PROFILE_ID}`)
    await act(async () => streamA.dispatchEvent('server_hello', {}))
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['admin', 'cubes'] })
    invalidateSpy.mockClear()

    const profileB = '00000000-0000-0000-0000-000000000002'
    await act(async () => {
      useSessionStore.setState({ boundProfileId: profileB })
      // A queued callback can run before React flushes the effect cleanup.
      streamA.dispatchEvent('server_hello', {})
    })
    expect(invalidateSpy).not.toHaveBeenCalled()
    expect(streamA.closeCalled).toBe(true)
    expect(MockEventSource.instances).toHaveLength(2)
    const streamB = MockEventSource.instances[1]
    expect(streamB.url).toBe(`/api/events/${profileB}`)
    await act(async () => streamA.dispatchEvent('boundary_changed', {}))
    expect(invalidateSpy).not.toHaveBeenCalled()
    await act(async () => streamB.dispatchEvent('collection_changed', {}))
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['admin', 'cubes'] })
    invalidateSpy.mockClear()

    await act(async () => useSessionStore.setState({ boundProfileId: null }))
    expect(streamB.closeCalled).toBe(true)
    expect(MockEventSource.instances).toHaveLength(2)
    await act(async () => streamB.dispatchEvent('server_hello', {}))
    expect(invalidateSpy).not.toHaveBeenCalled()
    await act(async () => unmount())
    await act(async () => streamB.dispatchEvent('boundary_changed', {}))
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})

/**
 * KioskView EventSource consumer tests — D-05 (re-locate) + D-11 (resync on onopen).
 *
 * Uses MockEventSource to drive the SSE consumer in KioskView without a real
 * server. The locate call is imperative (no ['locate', id] query key) — tests
 * assert that locateRelease() is called with the active selectedReleaseId.
 *
 * Test 1: onopen sets sseConnected = true (D-10)
 * Test 2: onopen triggers resync — invalidates ['units'] and ['cubes'] (D-11)
 * Test 3: boundary_changed with active selection re-calls locateRelease(id) (D-05)
 * Test 4: boundary_changed with NO selection does NOT call locateRelease (D-05 guard)
 *
 * Tests 3 and 4 are RED until Task 2 wires the re-locate in KioskView.tsx.
 *
 * Phase 6 additions (06-02):
 * Test D-05-a: device_revoked SSE event sets revokePending via triggerRevoke() (D-06)
 * Test D-08-a: device_reassigned SSE event calls getSession + setSession + setReassignBanner
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KioskView } from './KioskView'
import { useGruvaxStore } from '../../state/store'

// ── Module mock (must be top-level for vitest hoisting) ──────────────────────
//
// vi.mock replaces the module at the import level — the component's binding to
// locateRelease resolves to our mock function. vi.spyOn alone does not work for
// ESM named exports because the component holds its own live binding.
vi.mock('../../api/client', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/client')>()
  return {
    ...real,
    locateRelease: vi.fn().mockResolvedValue({
      primary_cube: { unit_id: 1, row: 0, col: 0 },
      label_span: [],
      sub_cube_interval: null,
      confidence: 0.8,
    }),
    searchCollection: vi.fn().mockResolvedValue({ items: [], took_ms: 1, did_you_mean: null }),
  }
})

// Mock getSession for device_reassigned test (D-08, D-09)
vi.mock('../../api/session', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/session')>()
  return {
    ...real,
    getSession: vi.fn(),
  }
})

// Import after vi.mock so we get the mocked version
import { locateRelease, searchCollection } from '../../api/client'
import { getSession } from '../../api/session'
import { useSessionStore } from '../../state/sessionStore'

const TEST_PROFILE_ID = '00000000-0000-0000-0000-000000000001'

// ── MockEventSource ──────────────────────────────────────────────────────────
//
// Replaces the global EventSource in jsdom (which has no real implementation).
// Stores instances for test access; supports addEventListener, onopen/onerror
// fields, and a dispatchEvent helper that calls named listeners.
//
// IMPORTANT: vi.stubGlobal must happen before the useEffect runs (i.e., before
// render). We stub it at module scope so it applies globally for all tests.

class MockEventSource {
  static instances: MockEventSource[] = []

  url: string
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners: Record<string, Array<(e: { data: string }) => void>> = {}

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(name: string, fn: (e: { data: string }) => void) {
    this.listeners[name] = [...(this.listeners[name] ?? []), fn]
  }

  close() {}

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
 * Render KioskView and wait for effects to flush.
 * Returns the MockEventSource instance created during the SSE useEffect.
 */
async function renderKioskAndFlush(queryClient: QueryClient): Promise<MockEventSource> {
  // act() flushes useEffect hooks after render
  await act(async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <KioskView />
      </QueryClientProvider>,
    )
  })
  return MockEventSource.instances[MockEventSource.instances.length - 1]
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  MockEventSource.instances = []
  // Reset store to clean state before each test
  useGruvaxStore.setState({
    selectedReleaseId: null,
    connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
  })
  // D2-04: seed sessionStore with a bound profile so the SSE effect creates
  // an EventSource (per-profile guard: no profile → no EventSource created).
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
  })
  // Reset locateRelease and searchCollection mock call counts
  vi.mocked(locateRelease).mockClear()
  vi.mocked(searchCollection).mockClear()
  // Provide a default getSession mock so the session polling query doesn't error
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
  // Reset lifecycle state
  useSessionStore.setState({ revokePending: false, reassignBanner: null })
})

afterEach(() => {
  vi.clearAllMocks()
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('KioskView EventSource consumer', () => {
  it('Test 1: onopen sets sseConnected = true (D-10)', async () => {
    const qc = makeQueryClient()
    const es = await renderKioskAndFlush(qc)

    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(false)

    await act(async () => {
      es.onopen?.()
    })

    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(true)
  })

  it('Test 2: onopen triggers resync — invalidates [units] and [cubes] (D-11)', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const es = await renderKioskAndFlush(qc)

    await act(async () => {
      es.onopen?.()
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )

    expect(calledKeys).toContainEqual(['units'])
    expect(calledKeys).toContainEqual(['cubes'])
  })

  it('Test 3: boundary_changed with active selection re-calls locateRelease(id) (D-05)', async () => {
    const qc = makeQueryClient()
    const es = await renderKioskAndFlush(qc)

    // Set selectedReleaseId AFTER render — the KioskView clearSearch effect fires on mount
    // (when debouncedQuery is empty) and resets selectedReleaseId to null. We must set
    // the active selection after the initial effects have flushed.
    await act(async () => {
      useGruvaxStore.setState({ selectedReleaseId: 42 })
    })

    // Connect (simulates browser connect event); clears any locate calls from resync
    await act(async () => {
      es.onopen?.()
    })
    vi.mocked(locateRelease).mockClear()

    // Dispatch boundary_changed — should trigger re-locate for selectedReleaseId=42
    await act(async () => {
      es.dispatchEvent('boundary_changed', {
        cube_ids: [{ unit: 1, row: 0, col: 0 }],
        change_set_id: 'test-set-123',
      })
    })

    // D2-04: locateRelease now receives (releaseId, profileId) — assert both
    expect(locateRelease).toHaveBeenCalledWith(42, TEST_PROFILE_ID)
  })

  it('Test 4: boundary_changed with NO selection does NOT call locateRelease (D-05 guard)', async () => {
    const qc = makeQueryClient()
    // Ensure no active selection
    useGruvaxStore.setState({ selectedReleaseId: null })
    const es = await renderKioskAndFlush(qc)

    await act(async () => {
      es.onopen?.()
    })
    vi.mocked(locateRelease).mockClear()

    // Dispatch boundary_changed with no active selection
    await act(async () => {
      es.dispatchEvent('boundary_changed', {
        cube_ids: [{ unit: 1, row: 0, col: 0 }],
        change_set_id: 'test-set-456',
      })
    })

    expect(locateRelease).not.toHaveBeenCalled()
  })

  // B-01: collection_changed SSE event must invalidate the ['search'] query key
  it('collection_changed invalidates search query key (B-01)', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const es = await renderKioskAndFlush(qc)

    await act(async () => {
      es.dispatchEvent('collection_changed', {})
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )
    expect(calledKeys).toContainEqual(['search'])   // RED until B-01 listener is added
  })

  // Phase 6 (D-06): device_revoked SSE event sets revokePending via triggerRevoke()
  // RED until Task 2 adds the device_revoked addEventListener in KioskView.tsx.
  it('device_revoked SSE event sets revokePending = true (D-06)', async () => {
    useSessionStore.setState({ revokePending: false })
    const qc = makeQueryClient()
    const es = await renderKioskAndFlush(qc)

    await act(async () => {
      es.dispatchEvent('device_revoked', { device_id: 'test-device-id' })
    })

    // The SSE handler must call useSessionStore.getState().triggerRevoke()
    // (the SAME signal the 403 path uses — App.tsx is the single handler, D-06)
    expect(useSessionStore.getState().revokePending).toBe(true)
  })

  // Phase 6 (D-08, D-09): device_reassigned SSE event calls getSession + sets reassignBanner
  // RED until Task 2 adds the device_reassigned addEventListener in KioskView.tsx.
  it('device_reassigned SSE event calls getSession + sets reassignBanner (D-08, D-09)', async () => {
    const NEW_PROFILE_ID = '00000000-0000-0000-0000-000000000099'
    const REASSIGNED_SESSION = {
      profile_count: 1,
      bound_profile_id: NEW_PROFILE_ID,
      profiles: [
        {
          id: NEW_PROFILE_ID,
          display_name: 'New Profile',
          last_sync_at: null,
          last_sync_status: 'completed',
          last_sync_item_count: 50,
          app_token_revoked: false,
        },
      ],
      is_device_paired: true,
      needs_reauth: false,
    }

    const qc = makeQueryClient()
    const es = await renderKioskAndFlush(qc)

    // Clear initial state and override getSession to return the reassigned session
    // (the polling query has already consumed the default mock during render)
    useSessionStore.setState({ reassignBanner: null })
    vi.mocked(getSession).mockResolvedValue(REASSIGNED_SESSION)

    await act(async () => {
      es.dispatchEvent('device_reassigned', { device_id: 'test-device-id' })
    })

    // Wait for async getSession resolution
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50))
    })

    // getSession must have been called
    expect(getSession).toHaveBeenCalled()

    // reassignBanner must be set to the new profile's display_name (D-09)
    expect(useSessionStore.getState().reassignBanner).toBe('New Profile')
  })

  // B-02 frontend: search query must be disabled when boundProfileId is null
  it('search query is disabled when boundProfileId is null (B-02)', async () => {
    // Override session store: unbound state (no profile bound yet — session bootstrap pending)
    useSessionStore.setState({ profileCount: 0, boundProfileId: null, profiles: [] })
    // Ensure getSession also returns an unbound session so the polling query doesn't
    // overwrite boundProfileId to a non-null value during the test
    vi.mocked(getSession).mockResolvedValue({
      profile_count: 0,
      bound_profile_id: null,
      profiles: [],
      is_device_paired: false,
      needs_reauth: false,
    })

    const qc = makeQueryClient()
    // Spy on the mocked searchCollection to assert it is NOT called
    const searchSpy = vi.mocked(searchCollection)
    searchSpy.mockClear()

    const { container } = await act(async () =>
      render(
        <QueryClientProvider client={qc}>
          <KioskView />
        </QueryClientProvider>,
      ),
    )

    // Simulate user typing in the search box to drive debouncedQuery
    const input = container.querySelector<HTMLInputElement>('input[type="search"]')
    if (input) {
      await act(async () => {
        fireEvent.change(input, { target: { value: 'Blue Note' } })
      })
      // Advance past the 250ms SearchBox debounce so debouncedQuery updates
      await act(async () => {
        await new Promise((r) => setTimeout(r, 300))
      })
    }

    // Even with a non-empty query, searchCollection must NOT be called when boundProfileId is null.
    // RED: current enabled gate only checks query length, not boundProfileId — so
    // searchCollection WILL be called before the fix (failing this assertion).
    expect(searchSpy).not.toHaveBeenCalled()
  })

  // ── Phase 9 (OFF-01/OFF-02/OFF-04): offline banner + degraded mode ───────

  // Phase 9 / Blocker 1 (OFF-04): on initial page load, after the FIRST onopen fires,
  // the "Back online" toast must NOT appear. bannerVisible starts false (not a real
  // reconnect) so the toast guard correctly suppresses it.
  it('Phase 9 Blocker 1: initial onopen does NOT show the Back online toast', async () => {
    const qc = makeQueryClient()
    // Ensure clean state — bannerVisible=false (initial store state)
    useGruvaxStore.setState({
      connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
    })

    const { container } = await act(async () =>
      render(
        <QueryClientProvider client={qc}>
          <KioskView />
        </QueryClientProvider>,
      ),
    )
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]

    // Simulate the first onopen on a fresh page load
    await act(async () => {
      es.onopen?.()
    })

    // The "Back online" toast must NOT appear — bannerVisible was false before onopen
    // so it was not a genuine offline→online transition
    const toast = container.querySelector('.sync-toast')
    expect(toast).toBeNull()
  })

  // Phase 9 / OFF-01 (offline transition): onerror fires → OfflineBanner appears (role=alert)
  // and SearchBox becomes disabled
  it('Phase 9 OFF-01: onerror shows the OfflineBanner and disables SearchBox', async () => {
    const qc = makeQueryClient()
    const { container } = await act(async () =>
      render(
        <QueryClientProvider client={qc}>
          <KioskView />
        </QueryClientProvider>,
      ),
    )
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]

    // Connect first
    await act(async () => {
      es.onopen?.()
    })

    // Simulate an SSE error (connection dropped)
    await act(async () => {
      es.onerror?.()
    })

    // OfflineBanner must be visible (role=alert)
    const banner = container.querySelector('[role="alert"]')
    expect(banner).not.toBeNull()

    // SearchBox input must be disabled
    const input = container.querySelector<HTMLInputElement>('input[type="search"]')
    expect(input).not.toBeNull()
    expect(input?.disabled).toBe(true)

    // connectivity store state should reflect disconnected
    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(false)
    expect(useGruvaxStore.getState().connectivity.bannerVisible).toBe(true)
  })

  // Phase 9 / OFF-04 (reconnect transition): after offline, onopen fires → banner clears
  // AND "Back online" toast appears (bannerVisible was true → genuine reconnect)
  it('Phase 9 OFF-04: reconnect after offline clears banner and shows Back online toast', async () => {
    const qc = makeQueryClient()
    const { container } = await act(async () =>
      render(
        <QueryClientProvider client={qc}>
          <KioskView />
        </QueryClientProvider>,
      ),
    )
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]

    // Connect, then disconnect (simulates onerror)
    await act(async () => {
      es.onopen?.()
    })
    await act(async () => {
      es.onerror?.()
    })

    // Verify offline state
    expect(useGruvaxStore.getState().connectivity.bannerVisible).toBe(true)

    // Simulate reconnect (onopen fires again after auto-reconnect)
    await act(async () => {
      es.onopen?.()
    })

    // Banner must be cleared (sseConnected=true → OfflineBanner returns null)
    const banner = container.querySelector('.offline-banner')
    expect(banner).toBeNull()

    // "Back online" toast must appear
    const toast = container.querySelector('.sync-toast')
    expect(toast).not.toBeNull()

    // connectivity store state should reflect connected
    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(true)
    expect(useGruvaxStore.getState().connectivity.bannerVisible).toBe(false)
  })

  // ── Phase 9 gap-closure 09-04 ─────────────────────────────────────────────

  // SC4 (09-04): resync() must invalidate ['search'] on reconnect so stale search
  // results are flushed on onopen and server_hello, not only on collection_changed.
  it('SC4: onopen (resync) invalidates the search query key', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const es = await renderKioskAndFlush(qc)

    // Clear calls accumulated during render (health, session, units, cubes queries)
    invalidateSpy.mockClear()

    await act(async () => {
      es.onopen?.()
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )

    // resync() must invalidate ['units'], ['cubes'], AND ['search'] (ROADMAP SC4)
    expect(calledKeys).toContainEqual(['units'])
    expect(calledKeys).toContainEqual(['cubes'])
    expect(calledKeys).toContainEqual(['search'])
  })

  // SC4 (09-04): server_hello also calls resync() and must therefore invalidate ['search']
  it('SC4: server_hello (resync) invalidates the search query key', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const es = await renderKioskAndFlush(qc)

    // Connect first so the SSE handler is registered
    await act(async () => {
      es.onopen?.()
    })
    invalidateSpy.mockClear()

    await act(async () => {
      es.dispatchEvent('server_hello', {})
    })

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )

    expect(calledKeys).toContainEqual(['search'])
  })

  // WR-02 (09-04): "Back online" toast must be cleared when onerror fires within 4s
  // of a reconnect — prevents OfflineBanner + toast appearing simultaneously.
  it('WR-02: onerror clears the Back online toast (no dual-banner state)', async () => {
    const qc = makeQueryClient()
    const { container } = await act(async () =>
      render(
        <QueryClientProvider client={qc}>
          <KioskView />
        </QueryClientProvider>,
      ),
    )
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]

    // Set up offline state so the next onopen will show the toast
    await act(async () => {
      es.onopen?.()
    })
    await act(async () => {
      es.onerror?.()
    })
    expect(useGruvaxStore.getState().connectivity.bannerVisible).toBe(true)

    // Reconnect — "Back online" toast should appear
    await act(async () => {
      es.onopen?.()
    })
    const toastAfterReconnect = container.querySelector('.sync-toast')
    expect(toastAfterReconnect).not.toBeNull()

    // Now disconnect again within the 4s toast window — toast must clear
    await act(async () => {
      es.onerror?.()
    })

    // Toast must be gone; OfflineBanner is back instead
    const toastAfterDisconnect = container.querySelector('.sync-toast')
    expect(toastAfterDisconnect).toBeNull()

    const banner = container.querySelector('[role="alert"]')
    expect(banner).not.toBeNull()
  })

  // WR-02 (09-04): server_shutdown must also clear the "Back online" toast
  it('WR-02: server_shutdown clears the Back online toast', async () => {
    const qc = makeQueryClient()
    const { container } = await act(async () =>
      render(
        <QueryClientProvider client={qc}>
          <KioskView />
        </QueryClientProvider>,
      ),
    )
    const es = MockEventSource.instances[MockEventSource.instances.length - 1]

    // Set up offline→reconnect so toast is visible
    await act(async () => {
      es.onopen?.()
    })
    await act(async () => {
      es.onerror?.()
    })
    await act(async () => {
      es.onopen?.()
    })
    expect(container.querySelector('.sync-toast')).not.toBeNull()

    // server_shutdown fires — store goes disconnected AND toast must clear
    await act(async () => {
      es.dispatchEvent('server_shutdown', {})
    })

    expect(container.querySelector('.sync-toast')).toBeNull()
    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(false)
  })
})

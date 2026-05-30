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
    searchCollection: vi.fn().mockResolvedValue({ results: [], total: 0, took_ms: 1, did_you_mean: null }),
  }
})

// Import after vi.mock so we get the mocked version
import { locateRelease, searchCollection } from '../../api/client'
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

  // B-02 frontend: search query must be disabled when boundProfileId is null
  it('search query is disabled when boundProfileId is null (B-02)', async () => {
    // Override session store: unbound state (no profile bound yet — session bootstrap pending)
    useSessionStore.setState({ profileCount: 0, boundProfileId: null, profiles: [] })

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
})

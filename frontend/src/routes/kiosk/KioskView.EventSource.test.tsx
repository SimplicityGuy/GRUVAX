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
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { KioskView } from './KioskView'
import { useGruvaxStore } from '../../state/store'
import * as client from '../../api/client'

// ── MockEventSource ──────────────────────────────────────────────────────────
//
// Replaces the global EventSource in jsdom (which has no real implementation).
// Stores instances for test access; supports addEventListener, onopen/onerror
// fields, and a dispatchEvent helper that calls named listeners.

class MockEventSource {
  static instances: MockEventSource[] = []

  onopen: (() => void) | null = null
  onerror: (() => void) | null = null
  private listeners: Record<string, Array<(e: { data: string }) => void>> = {}

  constructor(public url: string) {
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

function renderKiosk(queryClient: QueryClient) {
  render(
    <QueryClientProvider client={queryClient}>
      <KioskView />
    </QueryClientProvider>,
  )
  // Return the first MockEventSource instance created during render
  return MockEventSource.instances[MockEventSource.instances.length - 1]
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  MockEventSource.instances = []
  // Reset the store to a clean state before each test
  useGruvaxStore.setState({
    selectedReleaseId: null,
    connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

// ── Tests ────────────────────────────────────────────────────────────────────

describe('KioskView EventSource consumer', () => {
  it('Test 1: onopen sets sseConnected = true (D-10)', () => {
    const qc = makeQueryClient()
    const es = renderKiosk(qc)

    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(false)
    es.onopen?.()
    expect(useGruvaxStore.getState().connectivity.sseConnected).toBe(true)
  })

  it('Test 2: onopen triggers resync — invalidates [units] and [cubes] (D-11)', async () => {
    const qc = makeQueryClient()
    const invalidateSpy = vi.spyOn(qc, 'invalidateQueries')
    const es = renderKiosk(qc)

    es.onopen?.()

    // Allow microtasks to flush (invalidateQueries calls are void-wrapped)
    await Promise.resolve()

    const calledKeys = invalidateSpy.mock.calls.map(
      (args) => (args[0] as { queryKey?: unknown[] }).queryKey,
    )

    expect(calledKeys).toContainEqual(['units'])
    expect(calledKeys).toContainEqual(['cubes'])
  })

  it('Test 3: boundary_changed with active selection re-calls locateRelease(id) (D-05)', async () => {
    // Set up a mock for locateRelease so we can assert it was called
    const locateMock = vi.spyOn(client, 'locateRelease').mockResolvedValue({
      primary_cube: { unit_id: 2, row: 1, col: 1 },
      label_span: [],
      sub_cube_interval: null,
      confidence: 0.8,
    })

    const qc = makeQueryClient()
    // Set an active selection in the store BEFORE rendering
    useGruvaxStore.setState({ selectedReleaseId: 42 })
    const es = renderKiosk(qc)

    // Connect first (matches real browser behavior)
    es.onopen?.()

    // Clear any locate calls that may have happened from auto-select on render
    locateMock.mockClear()

    // Dispatch boundary_changed event
    es.dispatchEvent('boundary_changed', {
      cube_ids: [{ unit: 1, row: 0, col: 0 }],
      change_set_id: 'test-set-123',
    })

    // Allow microtasks to flush (void promise chain)
    await Promise.resolve()

    expect(locateMock).toHaveBeenCalledWith(42)
  })

  it('Test 4: boundary_changed with NO selection does NOT call locateRelease (D-05 guard)', async () => {
    const locateMock = vi.spyOn(client, 'locateRelease').mockResolvedValue({
      primary_cube: { unit_id: 1, row: 0, col: 0 },
      label_span: [],
      sub_cube_interval: null,
      confidence: 0.8,
    })

    const qc = makeQueryClient()
    // Ensure no active selection
    useGruvaxStore.setState({ selectedReleaseId: null })
    const es = renderKiosk(qc)

    es.onopen?.()
    locateMock.mockClear()

    // Dispatch boundary_changed with no active selection
    es.dispatchEvent('boundary_changed', {
      cube_ids: [{ unit: 1, row: 0, col: 0 }],
      change_set_id: 'test-set-456',
    })

    await Promise.resolve()

    expect(locateMock).not.toHaveBeenCalled()
  })
})

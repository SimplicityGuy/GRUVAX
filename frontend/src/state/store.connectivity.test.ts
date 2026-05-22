/**
 * Tests for Phase 4 SSE connectivity + shimmer store slice.
 *
 * Covers:
 *   - setShimmerCubes: populates shimmerCubes and stamps shimmerExpiresAt ≈ now+60_000 (D-03 TTL math)
 *   - clearShimmerCubes: removes matching cubes; leaves others intact (D-03 primary on-commit clear)
 *   - setSseConnected: updates sseConnected; stamps lastSeenAt on connect; leaves it unchanged on disconnect
 *   - shimmerExpiresAt math (the 60s client TTL safety validated against the store directly)
 */
import { beforeEach, describe, expect, it, vi, afterEach } from 'vitest'
import { useGruvaxStore } from './store'

// Reset the Zustand store to its initial state before each test to prevent
// test bleed-through.
function resetStore() {
  useGruvaxStore.setState({
    query: '',
    selectedReleaseId: null,
    selectedResult: null,
    highlight: { primaryCube: null },
    labelSpan: [],
    subCubeInterval: null,
    confidence: 0,
    animationToken: 0,
    connectivity: { sseConnected: false, lastSeenAt: 0, bannerVisible: false },
    shimmerCubes: [],
    shimmerExpiresAt: 0,
  })
}

describe('store.connectivity – shimmer state (admin_editing + D-03 TTL)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetStore()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('setShimmerCubes populates shimmerCubes with the given cubes', () => {
    const cubes = [{ unit: 1, row: 0, col: 0 }]
    // setShimmerCubes accepts ShimmerCube[] (unit/row/col shape from the store)
    useGruvaxStore.getState().setShimmerCubes([{ unit: 1, row: 0, col: 0 }])
    const { shimmerCubes } = useGruvaxStore.getState()
    expect(shimmerCubes).toHaveLength(1)
    expect(shimmerCubes[0]).toMatchObject({ unit: 1, row: 0, col: 0 })
    void cubes // silence unused
  })

  it('setShimmerCubes stamps shimmerExpiresAt ≈ Date.now() + 60_000 (D-03 TTL math)', () => {
    const now = Date.now()
    // Advance fake timers so Date.now() returns a known value
    vi.setSystemTime(now)

    useGruvaxStore.getState().setShimmerCubes([{ unit: 1, row: 0, col: 0 }])
    const { shimmerExpiresAt } = useGruvaxStore.getState()

    // Must be within a 100ms tolerance window of now + 60_000
    expect(shimmerExpiresAt).toBeGreaterThanOrEqual(now + 60_000 - 100)
    expect(shimmerExpiresAt).toBeLessThanOrEqual(now + 60_000 + 100)
  })

  it('clearShimmerCubes removes matching cubes, leaves others intact', () => {
    useGruvaxStore.getState().setShimmerCubes([
      { unit: 1, row: 0, col: 0 },
      { unit: 1, row: 1, col: 2 },
    ])

    // Clear only the first cube
    useGruvaxStore.getState().clearShimmerCubes([{ unit: 1, row: 0, col: 0 }])
    const { shimmerCubes } = useGruvaxStore.getState()

    expect(shimmerCubes).toHaveLength(1)
    expect(shimmerCubes[0]).toMatchObject({ unit: 1, row: 1, col: 2 })
  })

  it('clearShimmerCubes with all cubes results in an empty shimmerCubes array', () => {
    useGruvaxStore.getState().setShimmerCubes([
      { unit: 1, row: 0, col: 0 },
      { unit: 2, row: 3, col: 1 },
    ])

    useGruvaxStore.getState().clearShimmerCubes([
      { unit: 1, row: 0, col: 0 },
      { unit: 2, row: 3, col: 1 },
    ])

    expect(useGruvaxStore.getState().shimmerCubes).toHaveLength(0)
  })

  it('clearShimmerCubes with a cube not in the set leaves shimmerCubes unchanged', () => {
    useGruvaxStore.getState().setShimmerCubes([{ unit: 1, row: 0, col: 0 }])
    useGruvaxStore.getState().clearShimmerCubes([{ unit: 2, row: 3, col: 3 }])

    expect(useGruvaxStore.getState().shimmerCubes).toHaveLength(1)
  })
})

describe('store.connectivity – SSE connection state (D-10)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    resetStore()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('setSseConnected(true) sets sseConnected true and stamps lastSeenAt', () => {
    const now = 1_700_000_000_000
    vi.setSystemTime(now)

    useGruvaxStore.getState().setSseConnected(true)
    const { connectivity } = useGruvaxStore.getState()

    expect(connectivity.sseConnected).toBe(true)
    expect(connectivity.lastSeenAt).toBeGreaterThanOrEqual(now - 100)
    expect(connectivity.lastSeenAt).toBeLessThanOrEqual(now + 100)
  })

  it('setSseConnected(false) sets sseConnected false and leaves lastSeenAt unchanged', () => {
    const firstAt = 1_700_000_000_000
    vi.setSystemTime(firstAt)
    useGruvaxStore.getState().setSseConnected(true)

    // Advance time then disconnect
    vi.setSystemTime(firstAt + 30_000)
    useGruvaxStore.getState().setSseConnected(false)

    const { connectivity } = useGruvaxStore.getState()
    expect(connectivity.sseConnected).toBe(false)
    // lastSeenAt must still be the connect-time stamp, not the disconnect time
    expect(connectivity.lastSeenAt).toBeGreaterThanOrEqual(firstAt - 100)
    expect(connectivity.lastSeenAt).toBeLessThanOrEqual(firstAt + 100)
  })

  it('initial connectivity state is disconnected with lastSeenAt=0', () => {
    const { connectivity } = useGruvaxStore.getState()
    expect(connectivity.sseConnected).toBe(false)
    expect(connectivity.lastSeenAt).toBe(0)
    expect(connectivity.bannerVisible).toBe(false)
  })
})

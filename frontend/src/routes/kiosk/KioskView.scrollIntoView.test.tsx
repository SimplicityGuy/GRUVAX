/**
 * KioskView — the lit cube scrolls into view (gruvax-k0zj).
 *
 * Regression test for: nothing in the kiosk ever called scrollIntoView, so a
 * search that lit a cube below the fold left the visible viewport showing an
 * unlit grid (.shelf-area is min-height:100dvh and just grows). This asserts
 * the GSAP selection-lands effect calls scrollIntoView on the newly-lit
 * `[data-state="lit"]` element every time a locate result lands.
 */
import gsap from 'gsap'
import type { LocateResult } from '../../api/types'
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
    searchCollection: vi
      .fn()
      .mockResolvedValue({ items: [SEARCH_ITEM], took_ms: 1, did_you_mean: null }),
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

  useGruvaxStore.getState().clearSearch()
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
  vi.restoreAllMocks()
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
    expect(scrollIntoViewSpy).toHaveBeenLastCalledWith(expect.objectContaining({ block: 'center' }))
  })
})

function locatedAt(col: number, interval: LocateResult['sub_cube_interval'] = null): LocateResult {
  return {
    release_id: 42,
    primary_cube: { unit_id: 1, row: 0, col },
    label_span: [],
    sub_cube_interval: interval,
    confidence: 0.8,
    generated_at: new Date().toISOString(),
    estimator_version: 'v1',
  }
}

describe('KioskView — real GSAP interruption and primary bands (gruvax-csxz)', () => {
  it.each(['select another cube', 'clear', 'unmount'])(
    'restores the interrupted cube inline transform on %s',
    async (action) => {
      let view: ReturnType<typeof renderKiosk>
      await act(async () => {
        view = renderKiosk()
      })
      const cube = document.querySelector<HTMLElement>('.cube[data-col="0"]')!
      // Revert must preserve an existing inline style, not indiscriminately clear it.
      cube.style.transform = 'matrix(0.97, 0, 0, 0.97, 0, 0)'
      const originalTransform = cube.style.transform
      const timeline = vi.spyOn(gsap, 'timeline')
      act(() => useGruvaxStore.getState().setLocateResult(locatedAt(0)))
      const active = timeline.mock.results.at(-1)!.value as gsap.core.Timeline
      act(() => {
        active.pause().time(0.05)
      })
      expect(Number(gsap.getProperty(cube, 'scaleX'))).toBeGreaterThan(1)
      expect(cube.style.transform).not.toBe(originalTransform)
      expect(cube.style.transform).not.toContain('NaN')
      expect(cube).toHaveClass('is-animating')

      act(() => {
        if (action === 'select another cube')
          useGruvaxStore.getState().setLocateResult(locatedAt(1))
        else if (action === 'clear') useGruvaxStore.getState().clearSearch()
        else view!.unmount()
      })
      expect(cube.style.transform).toBe(originalTransform)
      expect(cube).not.toHaveClass('is-animating')
      expect(active.parent).toBeNull()
    },
  )

  it('animates the primary edge band and span underlay and restores initial styles on unmount', async () => {
    let view: ReturnType<typeof renderKiosk>
    await act(async () => {
      view = renderKiosk()
    })
    const timeline = vi.spyOn(gsap, 'timeline')
    act(() =>
      useGruvaxStore.getState().setLocateResult({
        ...locatedAt(0, {
          start: 0.95,
          end: 1,
          crosses_boundary: true,
          next_cube: { unit_id: 1, row: 0, col: 1 },
        }),
        label_span: [
          { unit_id: 1, row: 0, col: 0 },
          { unit_id: 1, row: 0, col: 1 },
        ],
      }),
    )
    const bars = Array.from(document.querySelectorAll<HTMLElement>('.sub-cube-bar'))
    expect(bars).toHaveLength(1)
    expect(bars[0].style.left).toBe('95%')
    expect(parseFloat(bars[0].style.width)).toBeCloseTo(5)
    expect(bars[0]).not.toHaveClass('sub-cube-bar--singleton')
    expect(document.querySelector('.cube[data-col="1"] .sub-cube-bar')).toBeNull()
    const span = document.querySelector<HTMLElement>('.span-underlay__band')!
    expect(span).not.toBeNull()
    const active = timeline.mock.results.at(-1)!.value as gsap.core.Timeline
    act(() => {
      active.pause().time(0.3)
    })
    const scales = bars.map((bar) => Number(gsap.getProperty(bar, 'scaleX')))
    scales.forEach((scale) => {
      expect(scale).toBeGreaterThan(0)
      expect(scale).toBeLessThan(1)
    })
    expect(Number(gsap.getProperty(span, 'opacity'))).toBeCloseTo(0.6)
    expect(span).toHaveClass('is-animating')
    bars.forEach((bar) => expect(bar).toHaveClass('is-animating'))
    act(() => view!.unmount())
    expect(span.style.opacity).toBe('')
    expect(span).not.toHaveClass('is-animating')
    bars.forEach((bar) => {
      expect(bar.style.transform).toBe('')
      expect(bar.style.transformOrigin).toBe('')
      expect(bar).not.toHaveClass('is-animating')
      expect(bar.style.width).not.toBe('')
    })
  })

  it('keeps singleton bars fading without scale and releases will-change on completion', async () => {
    await act(async () => {
      renderKiosk()
    })
    const timeline = vi.spyOn(gsap, 'timeline')
    act(() =>
      useGruvaxStore.getState().setLocateResult(
        locatedAt(0, {
          start: 0,
          end: 1,
          next_cube: null,
          crosses_boundary: false,
        }),
      ),
    )
    const bar = document.querySelector<HTMLElement>('.sub-cube-bar')!
    const active = timeline.mock.results.at(-1)!.value as gsap.core.Timeline
    act(() => {
      active.pause().time(0.15)
    })
    expect(Number(gsap.getProperty(bar, 'opacity'))).toBeGreaterThan(0)
    expect(Number(gsap.getProperty(bar, 'opacity'))).toBeLessThan(0.18)
    expect(bar.style.transform).toBe('')
    act(() => {
      active.progress(1)
    })
    expect(Number(gsap.getProperty(bar, 'opacity'))).toBeCloseTo(0.18)
    expect(bar).not.toHaveClass('is-animating')
  })
})

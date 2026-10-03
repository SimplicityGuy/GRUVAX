import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BinWidthEditor } from './BinWidthEditor'
import { useAdminStore } from '../../state/adminStore'
import { getUnitSegments, setOverrides } from '../../api/adminClient'
import type { Segment } from '../../api/cubeTypes'

vi.mock('../../api/adminClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/adminClient')>()),
  getUnitSegments: vi.fn(),
  setOverrides: vi.fn(),
  adminGetCubes: vi.fn().mockResolvedValue({ cubes: [] }),
}))

function segments(fractions = [0.5, 0.5]): Segment[] {
  return fractions.map((fraction, i) => ({
    label: `Label ${i}`,
    fraction,
    auto_fraction: fraction,
    is_override: false,
    continues: false,
    segment_count: Math.round(fraction * 90),
  }))
}

let stripWidth = 600

beforeEach(() => {
  stripWidth = 600
  vi.mocked(getUnitSegments).mockReset().mockResolvedValue({ segments: segments() })
  vi.mocked(setOverrides).mockReset().mockResolvedValue(undefined)
  useAdminStore.getState().setPendingChangeSet(null)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({
    x: 0,
    y: 0,
    top: 0,
    left: 0,
    right: stripWidth,
    bottom: 88,
    width: stripWidth,
    height: 88,
    toJSON: () => ({}),
  }))
  vi.stubGlobal(
    'PointerEvent',
    class extends MouseEvent {
      pointerId: number
      constructor(type: string, options: PointerEventInit = {}) {
        super(type, options)
        this.pointerId = options.pointerId ?? 1
      }
    },
  )
  vi.stubGlobal('ResizeObserver', undefined)
  HTMLElement.prototype.setPointerCapture = vi.fn()
  HTMLElement.prototype.releasePointerCapture = vi.fn()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  useAdminStore.getState().setPendingChangeSet(null)
})

async function renderEditor(count = 2) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  const view = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/cubes/1/0/0']}>
        <Routes>
          <Route path="/admin/cubes/:unit/:row/:col" element={<BinWidthEditor />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await waitFor(() => expect(document.querySelectorAll('.bwe-seg')).toHaveLength(count))
  return view
}

function dragHandle(handle: Element, from: number, to: number) {
  fireEvent.pointerDown(handle, { pointerId: 1, clientX: from })
  fireEvent.pointerMove(document, { pointerId: 1, clientX: to })
  fireEvent.pointerUp(document, { pointerId: 1, clientX: to })
}

describe('BinWidthEditor visible override contract (gruvax-y75)', () => {
  it('saves and stages null overrides for a sub-threshold nudge reported as AUTO', async () => {
    await renderEditor()
    dragHandle(document.querySelector('.bwe-handle')!, 300, 301)
    expect(document.querySelectorAll('.bwe-chip--auto')).toHaveLength(2)
    expect(document.querySelectorAll('.bwe-seg--overridden')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Save overrides' }))
    expect(await screen.findByText('Saved · all widths auto-computed')).toBeVisible()
    expect(vi.mocked(setOverrides).mock.calls[0][3]).toEqual({
      overrides: [
        { label: 'Label 0', fraction: null },
        { label: 'Label 1', fraction: null },
      ],
    })
    expect(useAdminStore.getState().pendingChangeSet!.edits[0]).toMatchObject({
      segment_overrides: [],
    })
  })

  it('keeps significant drags visible and resettable in both request and staged draft', async () => {
    await renderEditor()
    dragHandle(document.querySelector('.bwe-handle')!, 300, 330)
    expect(document.querySelectorAll('.bwe-chip--set')).toHaveLength(2)
    expect(screen.getAllByRole('button', { name: 'reset to 50%' })).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: 'Save overrides' }))
    expect(await screen.findByText('Saved · 2 overrides written')).toBeVisible()
    const saved = vi.mocked(setOverrides).mock.calls[0][3].overrides
    expect(saved[0].fraction).toBeCloseTo(0.55)
    expect(saved[1].fraction).toBeCloseTo(0.45)
    expect(useAdminStore.getState().pendingChangeSet!.edits[0]).toMatchObject({
      segment_overrides: saved,
    })
  })
})

describe('BinWidthEditor safe touch geometry and fractions (gruvax-yl6b)', () => {
  it('omits thin adjacent handles and never submits a negative fraction for a realistic sliver bin', async () => {
    const fractions = [1, 1, 2, 40, 46].map((n) => n / 90)
    vi.mocked(getUnitSegments).mockResolvedValue({ segments: segments(fractions) })
    await renderEditor(5)
    const handles = Array.from(document.querySelectorAll<HTMLElement>('.bwe-handle'))
    expect(handles.map((h) => h.dataset.boundaryIndex)).toEqual(['3'])
    dragHandle(handles[0], (600 * 44) / 90, -100)
    const widths = Array.from(document.querySelectorAll<HTMLElement>('.bwe-seg')).map((s) =>
      parseFloat(s.style.width),
    )
    widths.forEach((width) => expect(width).toBeGreaterThan(0))
    expect(widths.reduce((sum, width) => sum + width, 0)).toBeCloseTo(100, 2)
    fireEvent.click(screen.getByRole('button', { name: 'Save overrides' }))
    await screen.findByText(/Saved/)
    const overrides = vi.mocked(setOverrides).mock.calls[0][3].overrides
    overrides
      .filter((o) => o.fraction !== null)
      .forEach((o) => expect(o.fraction).toBeGreaterThanOrEqual(0.05 - 1e-12))
    expect(overrides.reduce((sum, o) => sum + (o.fraction ?? 0), 0)).toBeLessThan(1)
  })

  it('keeps visible handle centers 44px apart and recalculates after a resize', async () => {
    const fractions = [0.06, 0.06, 0.06, 0.06, 0.76]
    vi.mocked(getUnitSegments).mockResolvedValue({ segments: segments(fractions) })
    await renderEditor(5)
    const centers = () =>
      Array.from(document.querySelectorAll<HTMLElement>('.bwe-handle')).map(
        (h) => (parseFloat(h.style.left) / 100) * stripWidth,
      )
    expect(centers()).toHaveLength(2)
    const first = centers()
    expect(first[1] - first[0]).toBeGreaterThanOrEqual(44)
    stripWidth = 400
    fireEvent(window, new Event('resize'))
    const resized = centers()
    expect(resized).toHaveLength(2)
    expect(resized[1] - resized[0]).toBeGreaterThanOrEqual(44)
    expect(document.querySelectorAll('.bwe-handle')[1]).toHaveAttribute('data-boundary-index', '2')
  })

  it.each([-100, 1000])(
    'clamps an extreme pointer at %s while keeping both labels positive and the sum intact',
    async (clientX) => {
      await renderEditor()
      dragHandle(document.querySelector('.bwe-handle')!, 300, clientX)
      fireEvent.click(screen.getByRole('button', { name: 'Save overrides' }))
      await screen.findByText('Saved · 2 overrides written')
      const values = vi.mocked(setOverrides).mock.calls[0][3].overrides.map((o) => o.fraction!)
      expect(Math.min(...values)).toBeCloseTo(0.05)
      expect(values.reduce((sum, value) => sum + value, 0)).toBeCloseTo(1)
    },
  )

  it.each([
    [-0.1, 1.1],
    [0.6, 0.6],
    [0, 1],
    [NaN, 0.5],
    [Infinity, 0.5],
  ])('blocks invalid widths %j before a request or success message', async (...fractions) => {
    vi.mocked(getUnitSegments).mockResolvedValue({ segments: segments(fractions) })
    await renderEditor()
    fireEvent.click(screen.getByRole('button', { name: 'Save overrides' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Widths must be positive and total 100%',
    )
    expect(setOverrides).not.toHaveBeenCalled()
    expect(screen.queryByText(/Saved/)).not.toBeInTheDocument()
    expect(useAdminStore.getState().pendingChangeSet).toBeNull()
  })
})

it('keeps native Reset controls reachable when a narrow override has no drag handle', async () => {
  const narrow = segments([0.03, 0.97])
  narrow[0] = { ...narrow[0], auto_fraction: 0.01, is_override: true }
  narrow[1].auto_fraction = 0.99
  vi.mocked(getUnitSegments).mockResolvedValue({ segments: narrow })
  await renderEditor()
  expect(document.querySelectorAll('.bwe-handle')).toHaveLength(0)
  const reset = screen.getByRole('button', { name: 'reset to 1%' })
  reset.focus()
  expect(reset).toHaveFocus()
  fireEvent.click(reset)
  expect(document.querySelectorAll('.bwe-chip--auto')).toHaveLength(2)
  expect(parseFloat(document.querySelector<HTMLElement>('.bwe-seg')!.style.width)).toBeCloseTo(1)
  fireEvent.click(screen.getByRole('button', { name: 'Save overrides' }))
  await screen.findByText('Saved · all widths auto-computed')
  expect(vi.mocked(setOverrides).mock.calls[0][3].overrides.every((o) => o.fraction === null)).toBe(
    true,
  )
})

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

async function renderEditor() {
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
  await waitFor(() => expect(document.querySelectorAll('.bwe-seg')).toHaveLength(2))
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

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { AdminCube, Unit } from '../../api/types'
import { useAdminStore } from '../../state/adminStore'
import { useSessionStore } from '../../state/sessionStore'
import { useGruvaxStore } from '../../state/store'
import { CubesGrid } from './CubesGrid'
import { ShelfBinList } from './ShelfBinList'
import { BinWidthEditor } from './BinWidthEditor'
import { LocatorHeader } from './LocatorHeader'
import { Wizard } from './Wizard'
import { KioskView } from '../kiosk/KioskView'

vi.mock('../../api/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/client')>()),
  fetchUnits: vi.fn(),
  fetchCubeContents: vi.fn().mockResolvedValue({
    unit_id: 2,
    row: 0,
    col: 0,
    first_label: 'LabelA',
    first_catalog: 'A 001',
    is_empty: false,
    total_count: 1,
    fill_level: 0.1,
    sample_records: [],
  }),
}))
import { fetchUnits } from '../../api/client'

const units: Unit[] = [
  { id: 7, display_name: 'Right Kallax', rows: 4, cols: 4, ordering: 2 },
  { id: 99, display_name: '  ', rows: 4, cols: 4, ordering: 3 },
  { id: 42, display_name: 'Left Kallax', rows: 4, cols: 4, ordering: 1 },
]
const cubes: AdminCube[] = [7, 99, 42].map((unit_id) => ({
  unit_id,
  row: 0,
  col: 0,
  first_label: 'LabelA',
  first_catalog: 'A 001',
  is_empty: false,
  fill_level: 0.5,
  record_count: 40,
}))

class TestEventSource {
  addEventListener() {}
  close() {}
}

beforeEach(() => {
  vi.stubGlobal('EventSource', TestEventSource)
  vi.mocked(fetchUnits).mockReset().mockResolvedValue({ units })
  useAdminStore.setState({ reshuffleDraft: null, pendingChangeSet: null, isLoggedIn: false })
  useSessionStore.setState({ boundProfileId: null, profiles: [], profileCount: 0 })
  useGruvaxStore.getState().clearSearch()
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function Location() {
  return <output>{useLocation().pathname}</output>
}
function mount(
  element: React.ReactNode,
  path = '/admin/cubes',
  route = '/admin/cubes',
  layout: Unit[] | null = units,
) {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (layout !== null) query.setQueryData(['units'], { units: layout })
  query.setQueryData(['admin', 'cubes'], { cubes })
  query.setQueryData(['admin', 'segments', 7, 0, 1], {
    segments: [
      {
        label: 'LabelA',
        fraction: 1,
        auto_fraction: 1,
        is_override: false,
        continues: false,
        segment_count: 40,
      },
    ],
  })
  query.setQueryData(['cubes'], { cubes: [] })
  query.setQueryData(['health'], { sync_age_seconds: null })
  query.setQueryData(['session'], {
    profile_count: 0,
    bound_profile_id: null,
    profiles: [],
    is_device_paired: false,
  })
  return render(
    <QueryClientProvider client={query}>
      <MemoryRouter initialEntries={[path]}>
        <Location />
        <Routes>
          <Route path={route} element={element} />
          <Route path="/admin/cubes/:unit" element={<Location />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('authoritative shelf names and physical ordering', () => {
  it('shows the same names and ordered fallback in kiosk and admin overview while navigation retains IDs', () => {
    const kiosk = mount(<KioskView />, '/', '/')
    expect(
      Array.from(kiosk.container.querySelectorAll('.shelf-label'), (node) => node.textContent),
    ).toEqual(['Left Kallax', 'Right Kallax', 'SHELF C'])
    kiosk.unmount()
    const admin = mount(<CubesGrid />)
    expect(
      Array.from(admin.container.querySelectorAll('.shelf-card-name'), (node) => node.textContent),
    ).toEqual(['Left Kallax', 'Right Kallax', 'SHELF C'])
    fireEvent.click(admin.container.querySelector('.shelf-card')!)
    expect(screen.getAllByText('/admin/cubes/42').length).toBeGreaterThan(0)
  })
  it('uses the actual name in the shelf bin-list heading', () => {
    mount(<ShelfBinList />, '/admin/cubes/7', '/admin/cubes/:unit')
    expect(screen.getByRole('heading', { name: 'EDIT Right Kallax' })).toBeVisible()
  })
  it('uses the same name in the width editor and back navigation', async () => {
    mount(<BinWidthEditor />, '/admin/cubes/7/0/1', '/admin/cubes/:unit/:row/:col')
    expect(await screen.findByRole('heading', { name: 'Right Kallax · BIN 2' })).toBeVisible()
    expect(screen.getByRole('button', { name: 'Back to Right Kallax bin list' })).toBeVisible()
  })
  it('walks configured cubes in physical unit order and names the first shelf consistently', () => {
    mount(<Wizard />, '/admin/wizard?mode=setup', '/admin/wizard')
    expect(screen.getByText(/Left Kallax · STEP/)).toBeVisible()
    expect(document.querySelector('.locator-header-shelf')).toHaveTextContent('Left Kallax')
  })
  it('waits for delayed authoritative ordering before creating a reshuffle draft or enabling edits', async () => {
    let resolveUnits!: (value: { units: Unit[] }) => void
    vi.mocked(fetchUnits).mockReturnValue(
      new Promise((resolve) => {
        resolveUnits = resolve
      }),
    )
    mount(<Wizard />, '/admin/wizard?mode=reshuffle', '/admin/wizard', null)
    await waitFor(() => expect(fetchUnits).toHaveBeenCalled())
    expect(
      screen.queryByRole('button', { name: 'THIS BIN IS EMPTY / SKIP' }),
    ).not.toBeInTheDocument()
    expect(useAdminStore.getState().reshuffleDraft).toBeNull()
    await act(async () => resolveUnits({ units }))
    expect(await screen.findByText(/Left Kallax · STEP/)).toBeVisible()
    fireEvent.click(screen.getByRole('button', { name: 'THIS BIN IS EMPTY / SKIP' }))
    expect(screen.getByText(/Right Kallax · STEP/)).toBeVisible()
    const draft = useAdminStore.getState().reshuffleDraft!
    expect(draft.completedSteps).toBe(1)
    expect(draft.cuts['42/0/0'].is_empty).toBe(true)
    expect(draft.cuts['7/0/0'].is_empty).toBe(false)
  })
  it('preserves a resumed draft and its physical step while metadata is pending', async () => {
    const draft = {
      mode: 'reshuffle' as const,
      completedSteps: 1,
      cuts: { '42/0/0': { first_label: 'Saved', first_catalog: 'S 01', is_empty: false } },
      idempotencyKey: 'resumed-key',
      startedAt: '2026-10-03T00:00:00Z',
    }
    useAdminStore.setState({ reshuffleDraft: draft })
    let resolveUnits!: (value: { units: Unit[] }) => void
    vi.mocked(fetchUnits).mockReturnValue(
      new Promise((resolve) => {
        resolveUnits = resolve
      }),
    )
    mount(<Wizard />, '/admin/wizard?mode=reshuffle', '/admin/wizard', null)
    await waitFor(() => expect(fetchUnits).toHaveBeenCalled())
    expect(
      screen.queryByRole('button', { name: 'THIS BIN IS EMPTY / SKIP' }),
    ).not.toBeInTheDocument()
    expect(useAdminStore.getState().reshuffleDraft).toEqual(draft)
    await act(async () => resolveUnits({ units }))
    expect(await screen.findByText(/Right Kallax · STEP/)).toBeVisible()
    expect(useAdminStore.getState().reshuffleDraft).toEqual(draft)
  })
  it('does not create a draft from a resolved empty layout', async () => {
    mount(<Wizard />, '/admin/wizard?mode=reshuffle', '/admin/wizard', [])
    expect(screen.getByRole('alert')).toHaveTextContent('Could not load shelf layout')
    expect(useAdminStore.getState().reshuffleDraft).toBeNull()
    expect(
      screen.queryByRole('button', { name: 'THIS BIN IS EMPTY / SKIP' }),
    ).not.toBeInTheDocument()
  })
  it('blocks the walk on failed layout fetch and starts physical ordering only after a successful retry', async () => {
    vi.mocked(fetchUnits).mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ units })
    mount(<Wizard />, '/admin/wizard?mode=reshuffle', '/admin/wizard', null)
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load shelf layout')
    expect(
      screen.queryByRole('button', { name: 'THIS BIN IS EMPTY / SKIP' }),
    ).not.toBeInTheDocument()
    expect(useAdminStore.getState().reshuffleDraft).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'TRY AGAIN' }))
    expect(await screen.findByText(/Left Kallax · STEP/)).toBeVisible()
    expect(useAdminStore.getState().reshuffleDraft?.completedSteps).toBe(0)
  })
  it('uses the kiosk row address in an admin locator popover for non-contiguous IDs', () => {
    const { container } = render(
      <LocatorHeader unitId={7} row={-1} col={-1} units={units} shelfName="Right Kallax" />,
    )
    fireEvent.click(container.querySelector('[data-row="1"][data-col="1"]')!)
    expect(container.querySelector('.locator-fill-popover')).toHaveTextContent('F2')
  })
  it.each(['empty', 'failed'] as const)(
    'shares nonduplicate fallback addresses and panel layout when unit metadata is %s',
    async (state) => {
      if (state === 'failed') vi.mocked(fetchUnits).mockRejectedValue(new Error('offline'))
      const { container } = mount(<KioskView />, '/', '/', state === 'empty' ? [] : null)
      await waitFor(() => expect(container.querySelectorAll('.cube')).toHaveLength(32))
      const labels = Array.from(container.querySelectorAll('.cube'), (cell) =>
        cell.getAttribute('aria-label'),
      )
      expect(new Set(labels).size).toBe(32)
      const unit2 = container.querySelector('[data-unit-id="2"][data-row="0"][data-col="0"]')!
      expect(unit2).toHaveAttribute('aria-label', 'Cube E1')
      fireEvent.click(unit2)
      expect(await screen.findByRole('dialog', { name: 'CUBE E1' })).toBeVisible()
      if (state === 'failed') await waitFor(() => expect(fetchUnits).toHaveBeenCalled())
    },
  )
})

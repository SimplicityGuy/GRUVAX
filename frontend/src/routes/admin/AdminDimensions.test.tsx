import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { AdminCube, Unit } from '../../api/types'
import { useAdminStore } from '../../state/adminStore'
import { CubesGrid } from './CubesGrid'
import { BinWidthEditor } from './BinWidthEditor'
import { Wizard } from './Wizard'
import { ShelfBinList } from './ShelfBinList'
import { useSessionStore } from '../../state/sessionStore'
import Import from './Import'

vi.mock('../../api/adminClient', async (original) => ({
  ...(await original<typeof import('../../api/adminClient')>()),
  uploadImportBoundaries: vi.fn(),
}))
import { uploadImportBoundaries } from '../../api/adminClient'
vi.mock('../../api/client', async (original) => ({
  ...(await original<typeof import('../../api/client')>()),
  fetchUnits: vi.fn(),
}))
import { fetchUnits } from '../../api/client'
beforeEach(() => useSessionStore.setState({ boundProfileId: null }))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  useAdminStore.setState({ reshuffleDraft: null, pendingChangeSet: null })
})

function mount(
  element: React.ReactNode,
  unit: Unit,
  path: string,
  {
    route = path,
    metadata = true,
    emptyLast = false,
  }: { route?: string; metadata?: boolean; emptyLast?: boolean } = {},
) {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const cubes: AdminCube[] = Array.from({ length: unit.rows * unit.cols }, (_, index) => ({
    unit_id: unit.id,
    row: Math.floor(index / unit.cols),
    col: index % unit.cols,
    first_label: 'Label',
    first_catalog: `A ${index}`,
    is_empty: emptyLast && index === unit.rows * unit.cols - 1,
    fill_level: 0.5,
    record_count: 10,
  }))
  query.setQueryData(['units'], { units: metadata ? [unit] : [] })
  query.setQueryData(['admin', 'cubes'], { cubes })
  for (const cube of cubes)
    query.setQueryData(['admin', 'segments', unit.id, cube.row, cube.col], { segments: [] })
  query.setQueryData(['admin', 'segments', unit.id, unit.rows - 1, unit.cols - 1], {
    segments: [
      {
        label: 'Label',
        fraction: 1,
        auto_fraction: 1,
        is_override: false,
        continues: false,
        segment_count: 10,
      },
    ],
  })
  return render(
    <QueryClientProvider client={query}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path={route} element={element} />
          <Route path="/admin/wizard/done" element={<span>Import committed</span>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const layouts: Unit[] = [
  { id: 7, display_name: '2x3 Kallax', rows: 2, cols: 3, ordering: 1 },
  { id: 42, display_name: '5x2 Kallax', rows: 5, cols: 2, ordering: 1 },
  { id: 1, display_name: 'Default Kallax', rows: 4, cols: 4, ordering: 1 },
]
it.each(layouts)('uses configured card geometry/capacity for $display_name', (unit) => {
  const view = mount(<CubesGrid />, unit, '/admin/cubes')
  const total = unit.rows * unit.cols
  expect(
    screen.getByRole('button', {
      name: `${unit.display_name}: ${total} of ${total} bins configured`,
    }),
  ).toBeVisible()
  expect(view.container.querySelectorAll('.shelf-mini-cell')).toHaveLength(total)
  expect(view.container.querySelector('.shelf-mini-kallax')).toHaveStyle({
    gridTemplateColumns: `repeat(${unit.cols}, 12px)`,
    gridTemplateRows: `repeat(${unit.rows}, 12px)`,
  })
})
it.each(layouts)(
  'uses configured row-major last-bin numbering and locator geometry for $display_name',
  async (unit) => {
    const view = mount(
      <BinWidthEditor />,
      unit,
      `/admin/cubes/${unit.id}/${unit.rows - 1}/${unit.cols - 1}`,
      { route: '/admin/cubes/:unit/:row/:col' },
    )
    expect(
      await screen.findByRole('heading', {
        name: `${unit.display_name} · BIN ${unit.rows * unit.cols}`,
      }),
    ).toBeVisible()
    expect(view.container.querySelectorAll('.locator-cell')).toHaveLength(unit.rows * unit.cols)
  },
)
it.each(layouts)(
  'shows the physical final wizard bin using configured columns for $display_name',
  (unit) => {
    useAdminStore.setState({
      reshuffleDraft: {
        mode: 'reshuffle',
        completedSteps: unit.rows * unit.cols - 1,
        cuts: {},
        idempotencyKey: 'test-key',
        startedAt: '2026-10-03T00:00:00Z',
      },
    })
    const view = mount(<Wizard />, unit, '/admin/wizard?mode=reshuffle', { route: '/admin/wizard' })
    expect(view.container.querySelector('.locator-header-bin')).toHaveTextContent(
      `BIN ${unit.rows * unit.cols}`,
    )
    expect(view.container.querySelectorAll('.locator-cell')).toHaveLength(unit.rows * unit.cols)
    expect(view.container.querySelector('.locator-cell--lit')).toHaveAttribute(
      'data-row',
      String(unit.rows - 1),
    )
    expect(view.container.querySelector('.locator-cell--lit')).toHaveAttribute(
      'data-col',
      String(unit.cols - 1),
    )
  },
)
it.each(layouts)(
  'shows the changed last-row cube in the configured import preview for $display_name',
  async (unit) => {
    vi.mocked(uploadImportBoundaries).mockResolvedValue({
      total_cubes: unit.rows * unit.cols,
      file_cube_count: unit.rows * unit.cols,
      diff_preview: [
        {
          unit_id: unit.id,
          row: unit.rows - 1,
          col: unit.cols - 1,
          delta: 0,
          will_be_empty: false,
          before: { first_label: 'Label', first_catalog: 'OLD', is_empty: false },
          after: { first_label: 'Label', first_catalog: 'NEW', is_empty: false },
        },
      ],
    })
    const view = mount(<Import />, unit, '/admin/import')
    fireEvent.change(view.container.querySelector('input[type="file"]')!, {
      target: { files: [new File(['synthetic'], 'boundaries.yaml', { type: 'text/plain' })] },
    })
    expect(
      await screen.findByText(`1 cube changing · ${unit.rows * unit.cols - 1} cubes unchanged`),
    ).toBeVisible()
    expect
      .soft(view.container.querySelectorAll('.import-diff-cell'))
      .toHaveLength(unit.rows * unit.cols)
    expect.soft(view.container.querySelectorAll('.import-diff-cell--changing')).toHaveLength(1)
    expect(screen.getByText(`${unit.rows}/${unit.cols}`)).toBeVisible()
    expect(uploadImportBoundaries).toHaveBeenCalledExactlyOnceWith(expect.any(File), null, true)
  },
)

it('retains the established 4×4 overview/editor geometry when metadata is absent', async () => {
  const unit = layouts[2]
  const card = mount(<CubesGrid />, unit, '/admin/cubes', { metadata: false })
  expect(screen.getByRole('button', { name: 'SHELF: 16 of 16 bins configured' })).toBeVisible()
  expect(card.container.querySelectorAll('.shelf-mini-cell')).toHaveLength(16)
  card.unmount()
  const editor = mount(<BinWidthEditor />, unit, '/admin/cubes/1/3/3', {
    route: '/admin/cubes/:unit/:row/:col',
    metadata: false,
  })
  expect(await screen.findByRole('heading', { name: 'SHELF · BIN 16' })).toBeVisible()
  expect(editor.container.querySelectorAll('.locator-cell')).toHaveLength(16)
})

it('keeps configured-layout preview read-only and commits only through the existing import action', async () => {
  const unit = layouts[1]
  vi.mocked(uploadImportBoundaries)
    .mockResolvedValueOnce({
      total_cubes: 10,
      file_cube_count: 10,
      diff_preview: [
        {
          unit_id: unit.id,
          row: 4,
          col: 1,
          delta: 0,
          will_be_empty: false,
          before: { first_label: 'Label', first_catalog: 'OLD', is_empty: false },
          after: { first_label: 'Label', first_catalog: 'NEW', is_empty: false },
        },
      ],
    })
    .mockResolvedValueOnce({ change_set_id: '12345678-1234-4234-8234-123456789012', applied: 1 })
  const view = mount(<Import />, unit, '/admin/import')
  const file = new File(['synthetic'], 'boundaries.yaml', { type: 'text/plain' })
  fireEvent.change(view.container.querySelector('input[type="file"]')!, {
    target: { files: [file] },
  })
  expect(await screen.findByText('1 cube changing · 9 cubes unchanged')).toBeVisible()
  expect(uploadImportBoundaries).toHaveBeenCalledExactlyOnceWith(file, null, true)
  fireEvent.click(screen.getByRole('button', { name: /COMMIT IMPORT/ }))
  expect(await screen.findByText('Import committed')).toBeVisible()
  expect(uploadImportBoundaries).toHaveBeenNthCalledWith(2, file, expect.any(String), false)
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(2)
})

it.each(layouts)(
  'uses configured list census, last configured bin and insert caption for $display_name',
  (unit) => {
    const total = unit.rows * unit.cols
    const view = mount(<ShelfBinList />, unit, `/admin/cubes/${unit.id}`, {
      route: '/admin/cubes/:unit',
      emptyLast: true,
    })
    expect(screen.getByText(`1 of ${total} bins unconfigured`)).toBeVisible()
    expect(view.container.querySelectorAll('.locator-cell')).toHaveLength(total)
    expect(
      screen.getByRole('button', { name: `Edit cut point for bin ${total - 1}` }),
    ).toBeVisible()
    const insertButtons = screen.getAllByRole('button', { name: 'Insert cut point' })
    fireEvent.click(insertButtons[insertButtons.length - 1])
    expect(screen.getByRole('heading', { name: `INSERT CUT AFTER BIN ${total - 1}` })).toBeVisible()
  },
)

function mountColdImport(units?: Unit[]) {
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  if (units) query.setQueryData(['units'], { units })
  const view = render(
    <QueryClientProvider client={query}>
      <MemoryRouter>
        <Import />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  vi.mocked(uploadImportBoundaries).mockResolvedValueOnce({
    total_cubes: 10,
    file_cube_count: 10,
    diff_preview: [
      {
        unit_id: 42,
        row: 4,
        col: 1,
        delta: 0,
        will_be_empty: false,
        before: null,
        after: { first_label: 'Label', first_catalog: 'NEW', is_empty: false },
      },
    ],
  })
  fireEvent.change(view.container.querySelector('input[type="file"]')!, {
    target: { files: [new File(['synthetic'], 'boundaries.yaml')] },
  })
  return view
}

it('retains the dry-run while deferred layout metadata blocks incomplete preview and commit', async () => {
  let resolve!: (value: { units: Unit[] }) => void
  vi.mocked(fetchUnits).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  const view = mountColdImport()
  await waitFor(() => expect(uploadImportBoundaries).toHaveBeenCalledTimes(1))
  expect(await screen.findByText('Loading shelf layout…')).toBeVisible()
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeDisabled()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: /COMMIT IMPORT/ }))
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
  await act(async () => resolve({ units: [layouts[1]] }))
  expect(await screen.findByText('1 cube changing · 9 cubes unchanged')).toBeVisible()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(10)
  expect(screen.getByText('5/2')).toBeVisible()
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeEnabled()
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
})

it('retains the dry-run after layout failure and retries metadata without another upload', async () => {
  vi.mocked(fetchUnits)
    .mockRejectedValueOnce(new Error('offline'))
    .mockResolvedValueOnce({ units: [layouts[1]] })
  const view = mountColdImport()
  expect(
    await screen.findByText(
      'Shelf layout unavailable. Retry before reviewing and committing the import.',
    ),
  ).toBeVisible()
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeDisabled()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(0)
  fireEvent.click(screen.getByRole('button', { name: 'Retry shelf layout' }))
  expect(await screen.findByText('1 cube changing · 9 cubes unchanged')).toBeVisible()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(10)
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeEnabled()
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
  expect(fetchUnits).toHaveBeenCalledTimes(2)
})

it.each([
  { name: 'empty layout', units: [] },
  { name: 'layout missing the changed unit', units: [layouts[0]] },
  { name: 'zero rows', units: [{ ...layouts[1], rows: 0 }] },
  { name: 'zero columns', units: [{ ...layouts[1], cols: 0 }] },
  { name: 'changed column outside the known unit', units: [{ ...layouts[1], cols: 1 }] },
])('blocks committing an unreviewable preview with $name', async ({ units }) => {
  vi.mocked(fetchUnits).mockResolvedValueOnce({ units })
  const view = mountColdImport()
  expect(
    await screen.findByText(
      'Shelf layout unavailable. Retry before reviewing and committing the import.',
    ),
  ).toBeVisible()
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeDisabled()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(0)
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
})

it('refreshes stale cached dimensions before showing or committing an omitted changed cube', async () => {
  vi.mocked(fetchUnits).mockResolvedValueOnce({ units: [layouts[1]] })
  const view = mountColdImport([{ ...layouts[1], rows: 4, cols: 4 }])
  expect(
    await screen.findByText(
      'Shelf layout unavailable. Retry before reviewing and committing the import.',
    ),
  ).toBeVisible()
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeDisabled()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(0)
  expect(fetchUnits).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: /COMMIT IMPORT/ }))
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: 'Retry shelf layout' }))
  expect(await screen.findByText('1 cube changing · 9 cubes unchanged')).toBeVisible()
  expect(view.container.querySelectorAll('.import-diff-cell')).toHaveLength(10)
  expect(view.container.querySelectorAll('.import-diff-cell--changing')).toHaveLength(1)
  expect(screen.getByText('5/2')).toBeVisible()
  expect(screen.getByRole('button', { name: /COMMIT IMPORT/ })).toBeEnabled()
  expect(fetchUnits).toHaveBeenCalledTimes(1)
  expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
})

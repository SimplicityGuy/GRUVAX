import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { CubeContentsResponse } from '../../api/cubeTypes'
import { fetchCubeContents } from '../../api/client'
import { useAdminStore } from '../../state/adminStore'
import { CubeContentsPanel } from './CubeContentsPanel'

vi.mock('../../api/client', () => ({ fetchCubeContents: vi.fn() }))
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  useAdminStore.setState({ isLoggedIn: false })
})

// Exact public response contract: Phase 5 persisted first cut points only.
const contents = {
  unit_id: 7,
  row: 1,
  col: 2,
  first_label: 'LabelA',
  first_catalog: 'A 001',
  is_empty: false,
  total_count: 2,
  fill_level: 0.5,
  sample_records: [
    { release_id: 101, label: 'LabelA', catalog_number: 'A 001' },
    { release_id: 102, label: 'LabelB', catalog_number: 'B 002' },
  ],
} satisfies CubeContentsResponse

it('renders the actual first-cut response and samples without an obsolete last endpoint', async () => {
  vi.mocked(fetchCubeContents).mockResolvedValue(contents)
  useAdminStore.setState({ isLoggedIn: true })
  const query = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={query}>
      <CubeContentsPanel
        cube={{ unit_id: 7, row: 1, col: 2 }}
        units={[{ id: 7, display_name: 'Shelf', rows: 2, cols: 3, ordering: 1 }]}
        onDismiss={() => {}}
      />
    </QueryClientProvider>,
  )
  expect(await screen.findByText('2 RECORDS · 50% FULL')).toBeInTheDocument()
  expect(fetchCubeContents).toHaveBeenCalledWith(7, 1, 2)
  expect(screen.getByRole('dialog')).toHaveAccessibleName('CUBE B3')
  expect(screen.getByText('FIRST')).toBeInTheDocument()
  expect(screen.getByText('LabelA A 001')).toBeInTheDocument()
  const samples = screen.getByRole('list', { name: 'Sample records' })
  expect(within(samples).getAllByRole('listitem')).toHaveLength(2)
  expect(within(samples).getByText('B 002')).toBeInTheDocument()
  expect(screen.queryByText('LAST')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'EDIT THIS CUBE' })).toHaveAttribute(
    'href',
    '/admin/cubes/7/1/2',
  )
})

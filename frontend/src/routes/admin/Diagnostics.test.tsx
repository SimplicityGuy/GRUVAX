import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Diagnostics } from './Diagnostics'
import { getDiagnostics, type DiagnosticsData } from '../../api/adminClient'

vi.mock('../../api/adminClient', async (original) => ({
  ...(await original<typeof import('../../api/adminClient')>()),
  getDiagnostics: vi.fn(),
}))

const data: DiagnosticsData = {
  sync_age_seconds: null,
  top_searched: [],
  slow_queries: [],
  mqtt: 'connected',
  pool: { size_used: 2, size_min: 5 },
  phantom_boundary_count: 0,
  recent_logs: [],
  profiles: [],
}

beforeEach(() => {
  vi.mocked(getDiagnostics).mockReset()
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function mount(response: Promise<DiagnosticsData>) {
  vi.mocked(getDiagnostics).mockReturnValue(response)
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <Diagnostics />
    </QueryClientProvider>,
  )
}

it('renders actual pool statistics from a normal diagnostics response', async () => {
  mount(Promise.resolve(data))
  expect(await screen.findByText('2 / 5')).toBeVisible()
  expect(screen.getByText('Connected')).toBeVisible()
})

it('retains the initial loading state without reading absent data', () => {
  mount(new Promise(() => {}))
  expect(screen.getByRole('button', { name: 'Refresh diagnostics' })).toBeDisabled()
  expect(screen.queryByText('connections used / min pool size')).not.toBeInTheDocument()
})

it('renders the fetch failure and retry action without crashing', async () => {
  mount(Promise.reject(new Error('offline')))
  expect(await screen.findByText(/Could not load diagnostics/)).toBeVisible()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled()
})

it('keeps the system panel mounted when a future partial 200 response omits pool', async () => {
  const partial: Partial<DiagnosticsData> = { ...data }
  delete partial.pool
  // Deliberate contract drift: this malformed response is not emitted by today's backend.
  mount(Promise.resolve(partial as DiagnosticsData))
  expect(await screen.findByText('0 / 0')).toBeVisible()
  expect(screen.getByText('Connected')).toBeVisible()
  expect(screen.getByRole('heading', { name: 'SYSTEM' })).toBeVisible()
})

it.each([
  [47 * 3600, '47h ago'],
  [48 * 3600, '2d ago'],
  [14 * 86400 + 1, '14d ago'],
])(
  'shows the same sync-age tier in global and profile diagnostics at %s seconds',
  async (age, expected) => {
    const now = Date.parse('2026-10-03T12:00:00Z')
    vi.spyOn(Date, 'now').mockReturnValue(now)
    mount(
      Promise.resolve({
        ...data,
        sync_age_seconds: Number(age),
        profiles: [
          {
            id: '00000000-0000-0000-0000-000000000007',
            display_name: 'Owned profile',
            last_sync_at: new Date(now - Number(age) * 1000).toISOString(),
            last_sync_status: 'ok',
            last_sync_item_count: 10,
            last_sync_error: null,
            app_token_revoked: false,
            last_new_record_count: null,
            last_sync_is_initial: null,
          },
        ],
      }),
    )
    await waitFor(() => expect(screen.getAllByText(expected)).toHaveLength(2))
    if (Number(age) > 14 * 86400)
      expect(screen.getAllByLabelText('Sync status: outdated')).toHaveLength(2)
  },
)

it('preserves distinct global and profile never-synced labels', async () => {
  mount(
    Promise.resolve({
      ...data,
      profiles: [
        {
          id: '00000000-0000-0000-0000-000000000007',
          display_name: 'Owned profile',
          last_sync_at: null,
          last_sync_status: null,
          last_sync_item_count: null,
          last_sync_error: null,
          app_token_revoked: false,
          last_new_record_count: null,
          last_sync_is_initial: null,
        },
      ],
    }),
  )
  expect(await screen.findByText('Never synced')).toBeVisible()
  const global = screen.getByText('DISCOGSOGRAPHY LAST SYNC').closest('.diag-staleness-row')!
  expect(global.querySelector('.diag-row-value')).toHaveTextContent('—')
})

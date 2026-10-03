import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
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

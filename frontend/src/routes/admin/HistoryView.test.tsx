import { StrictMode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getHistory, revertChangeSet } from '../../api/adminClient'
import type { ChangeSetHistoryItem, HistoryResponse } from '../../api/types'
import { useSessionStore } from '../../state/sessionStore'
import { HistoryView } from './HistoryView'

vi.mock('../../api/adminClient', async (original) => ({
  ...(await original<typeof import('../../api/adminClient')>()),
  getHistory: vi.fn(),
  revertChangeSet: vi.fn(),
}))
const profileP = '00000000-0000-0000-0000-000000000007'
const profileQ = '00000000-0000-0000-0000-000000000042'
const target = '12345678-1234-4234-8234-123456789012'
const collision = '12345678-9999-4999-8999-999999999999'
const other = 'abcdefab-1234-4234-8234-123456789012'
const scroll = vi.fn()
function item(id: string, count = 1): ChangeSetHistoryItem {
  return {
    change_set_id: id,
    source: 'manual',
    changed_at: '2026-10-03T12:00:00Z',
    cube_count: count,
  }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}
beforeEach(() => {
  vi.mocked(getHistory).mockReset()
  vi.mocked(revertChangeSet).mockReset()
  scroll.mockReset()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: scroll,
  })
  useSessionStore.setState({ boundProfileId: profileP })
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useSessionStore.setState({ boundProfileId: null })
})
function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <output data-testid="location">{location.search}</output>
      <button
        onClick={() => {
          useSessionStore.setState({ boundProfileId: profileQ })
          void navigate(`/admin/history?highlight=${target}&keep=yes`)
        }}
      >
        Switch profile
      </button>
    </>
  )
}
function mount(
  path = '/admin/history',
  query = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  const view = render(
    <QueryClientProvider client={query}>
      <MemoryRouter initialEntries={[path]}>
        <HistoryView />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...view, query }
}
it('preserves ordinary recent history loading without a targeted query or scroll', async () => {
  vi.mocked(getHistory).mockResolvedValue({ history: [item(other)] })
  mount()
  expect(await screen.findByText('1 cube')).toBeVisible()
  expect(getHistory).toHaveBeenCalledExactlyOnceWith()
  expect(scroll).not.toHaveBeenCalled()
})
it('matches the full UUID, highlights and scrolls the second card, and preserves other URL parameters', async () => {
  vi.mocked(getHistory).mockResolvedValue({ history: [item(collision), item(target, 2)] })
  mount(`/admin/history?highlight=${target}&keep=yes`)
  const card = (await screen.findByText('2 cubes')).closest('li')!
  await waitFor(() => expect(card).toHaveClass('history-card--highlighted'))
  expect(scroll).toHaveBeenCalledTimes(1)
  expect(scroll.mock.contexts[0]).toBe(card)
  expect(screen.getByText('1 cube').closest('li')).not.toHaveClass('history-card--highlighted')
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('?keep=yes'))
  expect(getHistory).toHaveBeenCalledExactlyOnceWith()
})
it('retrieves an older target after recent history loads, then clears the link only after display', async () => {
  const recent = deferred<HistoryResponse>()
  const older = deferred<HistoryResponse>()
  vi.mocked(getHistory).mockImplementation((id?: string) => (id ? older.promise : recent.promise))
  mount(`/admin/history?highlight=${target}&keep=yes`)
  expect(screen.getByText('Loading history...')).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
  expect(getHistory).toHaveBeenCalledTimes(1)
  await act(async () => recent.resolve({ history: [item(other)] }))
  expect(await screen.findByText('Loading linked change set…')).toBeVisible()
  expect(getHistory).toHaveBeenNthCalledWith(2, target)
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
  expect(scroll).not.toHaveBeenCalled()
  await act(async () => older.resolve({ history: [item(target, 3)] }))
  const card = (await screen.findByText('3 cubes')).closest('li')!
  await waitFor(() => expect(card).toHaveClass('history-card--highlighted'))
  expect(screen.getByText('1 cube')).toBeVisible()
  expect(scroll.mock.contexts[0]).toBe(card)
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('?keep=yes'))
  expect(screen.getByText('3 cubes').closest('li')).toHaveClass('history-card--highlighted')
})
it('does not silently consume a foreign or nonexistent linked change set', async () => {
  vi.mocked(getHistory).mockImplementation(async (id?: string) => ({
    history: id ? [] : [item(other)],
  }))
  mount(`/admin/history?highlight=${target}`)
  expect(await screen.findByText('Linked change set unavailable for this profile.')).toBeVisible()
  expect(screen.getByText('1 cube')).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
  expect(scroll).not.toHaveBeenCalled()
})
it('retains recent cards and the deep link when targeted retrieval fails', async () => {
  vi.mocked(getHistory).mockImplementation(async (id?: string) => {
    if (id) throw new Error('offline')
    return { history: [item(other)] }
  })
  mount(`/admin/history?highlight=${target}`)
  expect(await screen.findByText('Could not load linked change set. Try refreshing.')).toBeVisible()
  expect(screen.getByText('1 cube')).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
})
it('reports a malformed deep link without requesting a target or consuming it', async () => {
  vi.mocked(getHistory).mockResolvedValue({ history: [] })
  mount('/admin/history?highlight=12345678&keep=yes')
  expect(await screen.findByText('Invalid change-set link.')).toBeVisible()
  expect(getHistory).toHaveBeenCalledExactlyOnceWith()
  expect(screen.getByTestId('location')).toHaveTextContent('highlight=12345678')
})
it('does not show a previous profile recent/target cache or consume its highlight after a profile transition', async () => {
  const query = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  query.setQueryData(['admin', 'history', profileP, 'recent'], [item(target, 7)])
  query.setQueryData(['admin', 'history', profileP, 'change-set', target], [item(target, 7)])
  query.setQueryData(['admin', 'history'], [item(target, 7)]) // Legacy unscoped cache must be ignored.
  const newRecent = deferred<HistoryResponse>()
  const newTarget = deferred<HistoryResponse>()
  vi.mocked(getHistory).mockImplementation((id?: string) => {
    if (useSessionStore.getState().boundProfileId === profileP)
      return Promise.resolve({ history: [item(target, 7)] })
    return id ? newTarget.promise : newRecent.promise
  })
  mount('/admin/history', query)
  expect(await screen.findByText('7 cubes')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Switch profile' }))
  expect(screen.queryByText('7 cubes')).not.toBeInTheDocument()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
  expect(scroll).not.toHaveBeenCalled()
  await act(async () => newRecent.resolve({ history: [item(other)] }))
  expect(await screen.findByText('Loading linked change set…')).toBeVisible()
  expect(screen.queryByText('7 cubes')).not.toBeInTheDocument()
  await act(async () => newTarget.resolve({ history: [] }))
  expect(await screen.findByText('Linked change set unavailable for this profile.')).toBeVisible()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
  expect(screen.queryByText('7 cubes')).not.toBeInTheDocument()
  expect(query.getQueryData(['admin', 'history', profileQ, 'recent'])).toEqual([item(other)])
  expect(scroll).not.toHaveBeenCalled()
})
it('preserves normal history fetch failures without a target request', async () => {
  vi.mocked(getHistory).mockRejectedValue(new Error('offline'))
  mount(`/admin/history?highlight=${target}`)
  expect(await screen.findByText('Failed to load history. Try refreshing.')).toBeVisible()
  expect(getHistory).toHaveBeenCalledExactlyOnceWith()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
})
it('keeps the exact UUID revert confirmation and prefix cache invalidations', async () => {
  vi.mocked(getHistory).mockResolvedValue({ history: [item(target)] })
  vi.mocked(revertChangeSet).mockResolvedValue({
    change_set_id: other,
    reverted: [{ unit_id: 1, row: 0, col: 0 }],
    skipped: [],
  })
  const { query } = mount()
  const invalidate = vi.spyOn(query, 'invalidateQueries')
  fireEvent.click(await screen.findByRole('button', { name: 'REVERT' }))
  expect(screen.getByRole('dialog', { name: 'Confirm revert' })).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'REVERT' }))
  expect(await screen.findByText('REVERTED')).toBeVisible()
  expect(revertChangeSet).toHaveBeenCalledExactlyOnceWith(target)
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['admin', 'history'] })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['admin', 'cubes'] })
})

it('acknowledges a mounted target once under StrictMode', async () => {
  vi.mocked(getHistory).mockResolvedValue({ history: [item(target, 2)] })
  render(
    <StrictMode>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={[`/admin/history?highlight=${target}&keep=yes`]}>
          <HistoryView />
          <LocationProbe />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  )
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('?keep=yes'))
  expect(screen.getByText('2 cubes').closest('li')).toHaveClass('history-card--highlighted')
  expect(scroll).toHaveBeenCalledTimes(1)
})

it('retires a retained older displayed target when the bound profile changes', async () => {
  vi.mocked(getHistory).mockImplementation(async (id?: string) => {
    if (useSessionStore.getState().boundProfileId === profileQ)
      return { history: id ? [] : [item(other)] }
    return { history: [id ? item(target, 3) : item(other)] }
  })
  mount(`/admin/history?highlight=${target}`)
  await waitFor(() => expect(screen.getByTestId('location').textContent).toBe(''))
  expect(await screen.findByText('3 cubes')).toBeVisible()
  fireEvent.click(screen.getByRole('button', { name: 'Switch profile' }))
  expect(screen.queryByText('3 cubes')).not.toBeInTheDocument()
  expect(await screen.findByText('Linked change set unavailable for this profile.')).toBeVisible()
  expect(screen.queryByText('3 cubes')).not.toBeInTheDocument()
  expect(screen.getByTestId('location')).toHaveTextContent(`highlight=${target}`)
  expect(scroll).toHaveBeenCalledTimes(1)
})

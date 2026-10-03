import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getAdminSettings, putAdminSettings } from '../../api/adminClient'
import type { AdminSettings } from '../../api/types'
import { Settings } from './Settings'

vi.mock('../../api/adminClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/adminClient')>()),
  getAdminSettings: vi.fn(),
  putAdminSettings: vi.fn(),
}))

beforeEach(() => {
  vi.mocked(getAdminSettings).mockReset()
  vi.mocked(putAdminSettings).mockReset()
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

function pendingSave() {
  let resolve!: (value: Partial<AdminSettings>) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<Partial<AdminSettings>>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

async function openCadence() {
  vi.mocked(getAdminSettings).mockResolvedValue({
    cube_nominal_capacity: 95,
    session_idle_ttl_seconds: 600,
    sync_cadence: '24h',
  })
  await act(async () => {
    render(
      <MemoryRouter>
        <Settings />
      </MemoryRouter>,
    )
  })
  return screen.getByLabelText('SYNC CADENCE')
}

it('rolls a failed optimistic cadence change back to the confirmed value', async () => {
  const save = pendingSave()
  vi.mocked(putAdminSettings).mockReturnValue(save.promise)
  const select = await openCadence()
  fireEvent.change(select, { target: { value: '6h' } })
  expect(select).toHaveValue('6h')
  await act(async () => {
    save.reject(new Error('unreachable'))
  })
  expect(select).toHaveValue('24h')
  expect(select).toBeEnabled()
  expect(screen.getByText('Could not save. Try again.')).toBeInTheDocument()
  expect(putAdminSettings).toHaveBeenCalledExactlyOnceWith({ sync_cadence: '6h' })
})

it.each(['success', 'failure'] as const)(
  'keeps cadence pending through the prior timer until %s',
  async (outcome) => {
    vi.useFakeTimers()
    const next = pendingSave()
    vi.mocked(putAdminSettings).mockResolvedValueOnce({}).mockReturnValueOnce(next.promise)
    const select = await openCadence()
    await act(async () => {
      fireEvent.change(select, { target: { value: '6h' } })
    })
    expect(select).toHaveValue('6h')
    expect(select).toBeEnabled()
    expect(screen.getByText('Saved')).toBeInTheDocument()
    fireEvent.change(select, { target: { value: '12h' } })
    expect(select).toBeDisabled()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2500)
    })
    expect(select).toBeDisabled()
    await act(async () => {
      if (outcome === 'success') next.resolve({})
      else next.reject(new Error('second save failed'))
    })
    expect(select).toBeEnabled()
    expect(select).toHaveValue(outcome === 'success' ? '12h' : '6h')
    expect(putAdminSettings).toHaveBeenCalledTimes(2)
  },
)

function Location() {
  return <output data-testid="path">{useLocation().pathname}</output>
}

it('does not advertise an unsupported drift alert and keeps override review', async () => {
  vi.mocked(getAdminSettings).mockResolvedValue({
    cube_nominal_capacity: 95,
    session_idle_ttl_seconds: 600,
  })
  const write = vi.spyOn(Storage.prototype, 'setItem')
  render(
    <MemoryRouter>
      <Settings />
      <Location />
    </MemoryRouter>,
  )
  await waitFor(() => expect(getAdminSettings).toHaveBeenCalled())
  expect(screen.queryByLabelText('DRIFT ALERT THRESHOLD (% POINTS)')).toBeNull()
  expect(screen.queryByRole('button', { name: 'SAVE THRESHOLD' })).toBeNull()
  expect(screen.queryByText(/Show a review alert when an override drifts/)).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'REVIEW OVERRIDES' }))
  expect(screen.getByTestId('path')).toHaveTextContent('/admin/cubes')
  expect(write).not.toHaveBeenCalled()
  expect(putAdminSettings).not.toHaveBeenCalled()
})

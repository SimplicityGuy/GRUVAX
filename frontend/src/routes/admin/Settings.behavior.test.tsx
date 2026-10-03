import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { getAdminSettings, putAdminSettings } from '../../api/adminClient'
import { Settings } from './Settings'

vi.mock('../../api/adminClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/adminClient')>()),
  getAdminSettings: vi.fn(),
  putAdminSettings: vi.fn(),
}))

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

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

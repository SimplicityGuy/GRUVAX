import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { BrowserRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'
import { getAdminSettings, putAdminSettings } from '../../api/adminClient'
import { Settings } from './Settings'

vi.mock('../../api/adminClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/adminClient')>()),
  getAdminSettings: vi.fn(),
  putAdminSettings: vi.fn(),
}))
afterEach(cleanup)

it('offers operative colors and saves them without the legacy off knob', async () => {
  vi.mocked(getAdminSettings).mockResolvedValue({
    cube_nominal_capacity: 95,
    session_idle_ttl_seconds: 600,
    led_color_position: '#123456',
  })
  vi.mocked(putAdminSettings).mockResolvedValue({ led_color_position: '#ABCDEF' })
  render(
    <BrowserRouter>
      <Settings />
    </BrowserRouter>,
  )
  await waitFor(() => expect(screen.getByLabelText('POSITION COLOR')).toHaveValue('#123456'))
  expect(screen.queryByLabelText('ALL OFF COLOR')).toBeNull()
  fireEvent.change(screen.getByLabelText('POSITION COLOR'), { target: { value: '#ABCDEF' } })
  fireEvent.click(screen.getByRole('button', { name: 'SAVE LED SETTINGS' }))
  await waitFor(() => expect(putAdminSettings).toHaveBeenCalled())
  expect(vi.mocked(putAdminSettings).mock.calls[0][0]).toMatchObject({
    led_color_position: '#abcdef',
  })
  expect(vi.mocked(putAdminSettings).mock.calls[0][0]).not.toHaveProperty('led_color_all_off')
})

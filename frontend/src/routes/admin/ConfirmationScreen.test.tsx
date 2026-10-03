import { StrictMode } from 'react'
import { afterEach, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router'
import { ConfirmationRoute } from './ConfirmationScreen'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function WizardDestination() {
  const navigate = useNavigate()
  return <button onClick={() => navigate(-1)}>Wizard destination: go back</button>
}

function mountConfirmation(path: string) {
  return render(
    <StrictMode>
      <MemoryRouter initialEntries={['/previous', path]} initialIndex={1}>
        <Routes>
          <Route path="/previous" element={<p>Previous route</p>} />
          <Route path="/admin/wizard" element={<WizardDestination />} />
          <Route path="/admin/wizard/done" element={<ConfirmationRoute />} />
        </Routes>
      </MemoryRouter>
    </StrictMode>,
  )
}

it.each(['/admin/wizard/done', '/admin/wizard/done?change_set_id='])(
  'redirects missing change-set IDs with replacement and no render warning: %s',
  async (path) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    mountConfirmation(path)
    fireEvent.click(await screen.findByRole('button', { name: /Wizard destination/ }))
    expect(await screen.findByText('Previous route')).toBeVisible()
    expect(warn).not.toHaveBeenCalled()
    expect(error).not.toHaveBeenCalled()
  },
)

it('keeps a valid change-set confirmation mounted under StrictMode', () => {
  const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
  const error = vi.spyOn(console, 'error').mockImplementation(() => {})
  const id = '11111111-1111-4111-8111-111111111111'
  mountConfirmation(`/admin/wizard/done?change_set_id=${id}&applied=3&source=csv`)
  expect(screen.getByRole('heading', { name: 'IMPORT COMMITTED' })).toBeVisible()
  expect(screen.getByText(id)).toBeVisible()
  expect(screen.getByText('Operation: CSV import · 3 cubes')).toBeVisible()
  expect(screen.queryByRole('button', { name: /Wizard destination/ })).not.toBeInTheDocument()
  expect(warn).not.toHaveBeenCalled()
  expect(error).not.toHaveBeenCalled()
})

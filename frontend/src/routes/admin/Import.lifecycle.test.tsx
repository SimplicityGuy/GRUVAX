import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router'

vi.mock('../../api/adminClient', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/adminClient')>()),
  uploadImportBoundaries: vi.fn(),
}))

import {
  BulkSaveError,
  uploadImportBoundaries,
  type BoundariesDryRunPreview,
} from '../../api/adminClient'
import Import from './Import'

function preview(label: string): BoundariesDryRunPreview {
  return {
    total_cubes: 1,
    file_cube_count: 1,
    diff_preview: [
      {
        unit_id: 1,
        row: 0,
        col: 0,
        delta: 0,
        will_be_empty: false,
        before: { first_label: 'Before', first_catalog: 'B1', is_empty: false },
        after: { first_label: label, first_catalog: 'A1', is_empty: false },
      },
    ],
  }
}

function validationError() {
  return new BulkSaveError(422, 'phantom_boundary', 'Old file error', {
    errors: [
      {
        row: 1,
        type: 'phantom_boundary',
        first_label: 'Old label',
        first_catalog: 'OLD1',
        near_misses: [{ label: 'Suggested label', catalog: 'S1' }],
      },
    ],
    ...preview('Old preview'),
  })
}

function deferred() {
  let resolve!: (value: BoundariesDryRunPreview) => void
  let reject!: (error: Error) => void
  const promise = new Promise<BoundariesDryRunPreview>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}

function mountImport() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(['units'], {
    units: [{ id: 1, rows: 1, cols: 1, ordering: 1, display_name: 'Shelf' }],
  })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/admin/import']}>
        <Routes>
          <Route path="/admin/import" element={<Import />} />
          <Route path="/admin/wizard/done" element={<p>Committed destination</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return document.querySelector('input[type="file"]') as HTMLInputElement
}

function pick(input: HTMLInputElement, file: File) {
  fireEvent.change(input, { target: { files: [file] } })
}

beforeEach(() => vi.mocked(uploadImportBoundaries).mockReset())
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

it.each(['size', 'type'])(
  'clears prior errors and native input after rejecting file %s, then retries and commits',
  async (reason) => {
    vi.mocked(uploadImportBoundaries).mockRejectedValueOnce(validationError())
    const input = mountImport()
    pick(input, new File(['old'], 'old.csv'))
    expect(await screen.findByRole('button', { name: 'Suggested label · S1' })).toBeVisible()
    const name = reason === 'size' ? 'corrected.csv' : 'corrected.txt'
    const bad = new File([reason === 'size' ? 'x'.repeat(100001) : 'x'], name)
    // JSDOM cannot set a native nonempty file value; retain its resettable value seam.
    Object.defineProperty(input, 'value', {
      configurable: true,
      writable: true,
      value: `C:\\fakepath\\${name}`,
    })
    pick(input, bad)
    expect(screen.getByRole('alert')).toHaveTextContent(
      reason === 'size' ? 'File is too large' : 'Unsupported file format',
    )
    expect(screen.queryByRole('button', { name: 'Suggested label · S1' })).not.toBeInTheDocument()
    expect(screen.queryByText('1 error found')).not.toBeInTheDocument()
    expect(screen.queryByText(/Old preview/)).not.toBeInTheDocument()
    expect(input.value).toBe('')
    expect(uploadImportBoundaries).toHaveBeenCalledTimes(1)
    const corrected = new File(['valid'], 'corrected.csv')
    vi.mocked(uploadImportBoundaries).mockResolvedValueOnce(preview('Corrected'))
    pick(input, corrected)
    expect(await screen.findByText('Cube 1/0/0: Before B1 → Corrected A1')).toBeVisible()
    vi.mocked(uploadImportBoundaries).mockResolvedValueOnce({
      change_set_id: 'result-id',
      applied: 1,
    })
    fireEvent.click(screen.getByRole('button', { name: 'COMMIT IMPORT' }))
    expect(await screen.findByText('Committed destination')).toBeVisible()
    expect(uploadImportBoundaries).toHaveBeenNthCalledWith(2, corrected, null, true)
    expect(uploadImportBoundaries).toHaveBeenNthCalledWith(3, corrected, expect.any(String), false)
  },
)

it.each(['success', 'validation', 'network'])(
  'ignores late old preview %s after rejection',
  async (outcome) => {
    const old = deferred()
    vi.mocked(uploadImportBoundaries).mockReturnValueOnce(old.promise)
    const input = mountImport()
    pick(input, new File(['old'], 'old.csv'))
    pick(input, new File(['x'.repeat(100001)], 'large.csv'))
    await act(async () => {
      if (outcome === 'success') old.resolve(preview('Old preview'))
      else
        old.reject(outcome === 'validation' ? validationError() : new Error('Old network failure'))
    })
    expect(screen.getByRole('alert')).toHaveTextContent('File is too large')
    expect(screen.queryByText(/Old preview/)).not.toBeInTheDocument()
    expect(screen.queryByText('1 error found')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'COMMIT IMPORT' })).toBeDisabled()
  },
)

it.each(['success', 'error'])(
  'keeps the replacement preview when old %s finishes last',
  async (outcome) => {
    const old = deferred()
    vi.mocked(uploadImportBoundaries)
      .mockReturnValueOnce(old.promise)
      .mockResolvedValueOnce(preview('Newest'))
    const input = mountImport()
    pick(input, new File(['old'], 'same.csv'))
    pick(input, new File(['new'], 'same.csv'))
    expect(await screen.findByText('Cube 1/0/0: Before B1 → Newest A1')).toBeVisible()
    await act(async () => {
      if (outcome === 'success') old.resolve(preview('Old preview'))
      else old.reject(validationError())
    })
    expect(screen.getByText('Cube 1/0/0: Before B1 → Newest A1')).toBeVisible()
    expect(screen.queryByText(/Old preview/)).not.toBeInTheDocument()
    expect(screen.queryByText('1 error found')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'COMMIT IMPORT' })).toBeEnabled()
  },
)

it('keeps a cleared import empty after the pending preview completes', async () => {
  const old = deferred()
  vi.mocked(uploadImportBoundaries).mockReturnValueOnce(old.promise)
  const input = mountImport()
  pick(input, new File(['old'], 'old.csv'))
  fireEvent.click(screen.getByRole('button', { name: 'Clear selected file' }))
  await act(async () => old.resolve(preview('Old preview')))
  expect(screen.getByText('DROP A FILE OR TAP TO UPLOAD')).toBeVisible()
  expect(screen.queryByText(/Old preview/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'COMMIT IMPORT' })).not.toBeInTheDocument()
})

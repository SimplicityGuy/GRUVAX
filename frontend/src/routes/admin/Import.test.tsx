/**
 * Import.tsx ErrorCard rendering tests (gruvax-imeq).
 *
 * Regression: a non-phantom, non-contiguity server error (e.g. `parse_error` from
 * a malformed YAML/CSV upload) has no `first_label` to key off. ErrorCard's render
 * only handled the phantom (`first_label` truthy) and `contiguity_violation`
 * branches, so this case rendered NOTHING but "ROW —" + the ERROR badge — even
 * though the backend composed a precise, actionable fix string.
 *
 * This test drives the real component: selecting a file triggers
 * uploadImportBoundaries (mocked to reject with a BulkSaveError carrying the
 * flattened body adminClient now produces — see adminClient.test.ts for the
 * flattening coverage) and asserts the backend's exact message text renders.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'

vi.mock('../../api/adminClient', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/adminClient')>()
  return {
    ...real,
    uploadImportBoundaries: vi.fn(),
  }
})

import { uploadImportBoundaries, BulkSaveError } from '../../api/adminClient'
import Import from './Import'

function makeFile(name: string): File {
  return new File(['irrelevant'], name, { type: 'text/plain' })
}

beforeEach(() => {
  vi.mocked(uploadImportBoundaries).mockReset()
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Import — ErrorCard renders the backend fix string for non-phantom errors', () => {
  it('renders the exact parse_error message from a malformed YAML upload', async () => {
    const message =
      "Missing or unsupported version field — YAML boundary documents must contain version: '1'"

    vi.mocked(uploadImportBoundaries).mockRejectedValue(
      new BulkSaveError(422, 'parse_error', message, { type: 'parse_error', message }),
    )

    render(
      <MemoryRouter>
        <Import />
      </MemoryRouter>,
    )

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    expect(fileInput).toBeTruthy()

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [makeFile('boundaries.yaml')] } })
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    // Old code: blank card ("ROW —" + ERROR badge, no message text anywhere).
    expect(screen.getByText(message)).toBeTruthy()
    expect(screen.getByText('ROW —')).toBeTruthy()
  })

  it('renders a generic fallback message when the server gives no structured error at all', async () => {
    vi.mocked(uploadImportBoundaries).mockRejectedValue(
      new BulkSaveError(422, undefined, undefined, {}),
    )

    render(
      <MemoryRouter>
        <Import />
      </MemoryRouter>,
    )

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [makeFile('boundaries.csv')] } })
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(screen.getByText('Validation error.')).toBeTruthy()
  })
})

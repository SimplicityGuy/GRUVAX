/**
 * ResetConfirmDialog — Wave-0 RED tests (PRIV-04 / L-05 / T-08-PR-03).
 *
 * Tests:
 *   1. Clicking "Clear and reset" calls onConfirm exactly once (behavioral gate)
 *   2. Clicking "Clear and reset" makes ZERO fetch calls (L-05 / T-08-PR-03 gate)
 *   3. Clicking "Keep recent searches" calls onCancel exactly once
 *   4. Pressing Escape calls onCancel
 *   5. Component renders with role="alertdialog"
 *   6. Initial focus lands on the Cancel button ("Keep recent searches")
 *
 * These tests are RED until ResetConfirmDialog.tsx is created (Task 2 GREEN phase).
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'

import { ResetConfirmDialog } from './ResetConfirmDialog'

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, gcTime: 0 },
    },
  })
}

function renderDialog(props: {
  onConfirm: () => void
  onCancel: () => void
}) {
  const qc = makeQueryClient()
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ResetConfirmDialog {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

let fetchSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  // Install a fetch spy BEFORE rendering — any fetch call during confirm should be caught
  fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok: false,
    json: async () => ({}),
  } as Response)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ResetConfirmDialog', () => {
  it('clicking "Clear and reset" calls onConfirm exactly once', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()

    renderDialog({ onConfirm, onCancel })

    const confirmBtn = screen.getByRole('button', { name: /clear and reset/i })
    await act(async () => {
      fireEvent.click(confirmBtn)
    })

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('clicking "Clear and reset" makes ZERO fetch calls (L-05 / T-08-PR-03 behavioral gate)', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()

    renderDialog({ onConfirm, onCancel })

    const confirmBtn = screen.getByRole('button', { name: /clear and reset/i })
    await act(async () => {
      fireEvent.click(confirmBtn)
    })

    // ZERO fetch calls — this is the behavioral gate for L-05 / T-08-PR-03
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('clicking "Keep recent searches" calls onCancel exactly once', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()

    renderDialog({ onConfirm, onCancel })

    const cancelBtn = screen.getByRole('button', { name: /keep recent searches/i })
    await act(async () => {
      fireEvent.click(cancelBtn)
    })

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('pressing Escape calls onCancel', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()

    renderDialog({ onConfirm, onCancel })

    await act(async () => {
      fireEvent.keyDown(document, { key: 'Escape' })
    })

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('renders with role="alertdialog"', () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()

    renderDialog({ onConfirm, onCancel })

    // The dialog container must have role="alertdialog"
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toBeInTheDocument()
  })

  it('initial focus lands on the Cancel button (safer default for destructive action)', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()

    renderDialog({ onConfirm, onCancel })

    // After mount, focus should be on the Cancel button
    await act(async () => {
      await Promise.resolve()
    })

    const cancelBtn = screen.getByRole('button', { name: /keep recent searches/i })
    expect(document.activeElement).toBe(cancelBtn)
  })
})

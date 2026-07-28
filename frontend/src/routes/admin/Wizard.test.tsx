/**
 * Wizard poisoned-draft regression tests (gruvax-cw8).
 *
 * Regression: a reshuffleDraft.completedSteps persisted at (or past) totalSteps —
 * from skipping the last reshuffle step, or from a failed commit — left
 * currentStepIndex out of range on re-entry. `steps[currentStepIndex]` is then
 * `undefined`, and the render used it unguarded (`const step = currentStep!`,
 * then `step.unit_id`), throwing and unmounting the whole React root (no error
 * boundary exists anywhere in the SPA).
 *
 * These tests seed a poisoned draft directly into the admin store (mirroring the
 * localStorage-persisted draft) and assert the Wizard renders a real step instead
 * of throwing.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// ── Module mock (must be top-level for vitest hoisting) ──────────────────────
vi.mock('../../api/adminClient', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/adminClient')>()
  return {
    ...real,
    adminGetCubes: vi.fn(),
  }
})

import { adminGetCubes } from '../../api/adminClient'
import { Wizard } from './Wizard'
import { useAdminStore } from '../../state/adminStore'
import type { AdminCubesResponse } from '../../api/types'

// ── Fixtures ─────────────────────────────────────────────────────────────────

const TWO_CUBES: AdminCubesResponse = {
  cubes: [
    { unit_id: 1, row: 0, col: 0, first_label: 'AAA', first_catalog: '001', is_empty: false, fill_level: 0.5, record_count: 10 },
    { unit_id: 1, row: 0, col: 1, first_label: 'BBB', first_catalog: '002', is_empty: false, fill_level: 0.5, record_count: 10 },
  ],
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: 0, gcTime: 0 } },
  })
}

async function renderWizard() {
  const qc = makeQueryClient()
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/admin/wizard']}>
        <Wizard />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  await Promise.resolve()
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.mocked(adminGetCubes).mockReset()
  vi.mocked(adminGetCubes).mockResolvedValue(TWO_CUBES)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  useAdminStore.setState({ reshuffleDraft: null })
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('Wizard re-entry with a poisoned reshuffle draft (gruvax-cw8)', () => {
  it('does not white-screen when completedSteps === totalSteps (skipped-last-step case)', async () => {
    useAdminStore.setState({
      reshuffleDraft: {
        mode: 'reshuffle',
        completedSteps: 2, // === totalSteps — the exact poisoned value from the old bug
        cuts: {},
        idempotencyKey: 'test-idempotency-key',
        startedAt: new Date().toISOString(),
      },
    })

    await act(async () => { await renderWizard() })

    await waitFor(() => {
      expect(screen.queryByText(/step/i)).not.toBeNull()
    }, { timeout: 3000 })

    // Clamped back onto the last real step (index 1 of 2) instead of crashing.
    expect(screen.getByText('2 / 2')).toBeTruthy()
  })

  it('does not white-screen when completedSteps is arbitrarily out of range (failed-commit case)', async () => {
    useAdminStore.setState({
      reshuffleDraft: {
        mode: 'reshuffle',
        completedSteps: 99,
        cuts: {},
        idempotencyKey: 'test-idempotency-key',
        startedAt: new Date().toISOString(),
      },
    })

    await act(async () => { await renderWizard() })

    await waitFor(() => {
      expect(screen.queryByText(/step/i)).not.toBeNull()
    }, { timeout: 3000 })

    expect(screen.getByText('2 / 2')).toBeTruthy()
  })
})

/**
 * DiffPreviewSheet optimistic mutation tests — Phase 4 RTM-03, D-07, D-08.
 *
 * Verifies:
 *  - On server rejection, the rollback toast ("Couldn't save that change — reverted.")
 *    appears (D-07 locked copy).
 *  - pendingChangeSet is NOT cleared on error (D-07 — values retained for retry).
 *  - No kiosk query keys (['cubes']) are invalidated on error (D-08, T-04-10).
 *  - Dismiss button hides the toast.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router'

// ── vi.mock calls must come before any import that uses them ──────────────────
// vi.mock is hoisted so the factory cannot reference module-level variables
// declared with const/let above it. Use vi.fn() directly inside the factory.

vi.mock('../../api/adminClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/adminClient')>()
  return {
    ...actual,
    // adminBulkSave is replaced with a vi.fn() — each test configures return behavior
    adminBulkSave: vi.fn(),
    validateBoundary: vi.fn().mockResolvedValue({ results: [] }),
    adminGetCubeBoundary: vi.fn().mockResolvedValue({
      first_label: 'Blue Note',
      first_catalog: 'BLP 4001',
      last_label: 'Blue Note',
      last_catalog: 'BLP 4020',
      is_empty: false,
    }),
  }
})

// Mock adminStore to avoid the persist middleware's localStorage dependency
vi.mock('../../state/adminStore', () => {
  const mockSetPendingChangeSet = vi.fn()
  const makeState = () => ({
    pendingChangeSet: {
      id: 'test-uuid-1234',
      edits: [
        {
          unit_id: 1,
          row: 0,
          col: 0,
          first_label: 'Test Label',
          first_catalog: 'TST 001',
          last_label: 'Test Label',
          last_catalog: 'TST 010',
          is_empty: false,
        },
      ],
      created_at: new Date().toISOString(),
    },
    setPendingChangeSet: mockSetPendingChangeSet,
    isLoggedIn: true,
    csrfToken: 'test-csrf',
    sessionExpiresAt: Date.now() + 600_000,
    hardCapExpiresAt: Date.now() + 1_800_000,
  })

  const useAdminStore = Object.assign(
    (selector?: (s: ReturnType<typeof makeState>) => unknown) => {
      const state = makeState()
      return typeof selector === 'function' ? selector(state) : state
    },
    {
      getState: () => makeState(),
      setState: vi.fn(),
      subscribe: vi.fn(() => () => {}),
    },
  )
  return { useAdminStore }
})

// ── Imports that depend on mocked modules ─────────────────────────────────────

import { BulkSaveError, adminBulkSave } from '../../api/adminClient'
import { DiffPreviewSheet } from './DiffPreviewSheet'

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function renderDiffSheet(queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/admin/diff']}>
        <DiffPreviewSheet />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DiffPreviewSheet — optimistic mutation (RTM-03, D-07, D-08)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows rollback toast on server rejection and does not clear pendingChangeSet (D-07)', async () => {
    // Arrange: server rejects the commit
    vi.mocked(adminBulkSave).mockRejectedValue(
      new BulkSaveError(400, 'boundary_order_error', 'Labels must be in alphabetical order'),
    )

    const queryClient = makeQueryClient()
    queryClient.setQueryData(['admin', 'cubes'], { cubes: [] })

    renderDiffSheet(queryClient)

    // Wait for async mount validation to complete
    await waitFor(() =>
      expect(screen.queryByText(/checking movement/i)).not.toBeInTheDocument(),
    )

    // Act: trigger commit
    const commitBtn = screen.getByRole('button', { name: /commit change set/i })
    await act(async () => {
      fireEvent.click(commitBtn)
    })

    // Assert: rollback toast with locked D-07 copy appears
    await waitFor(() =>
      expect(
        screen.getByText("Couldn't save that change — reverted."),
      ).toBeInTheDocument(),
    )

    // Assert: adminBulkSave was called (the mutation fired)
    expect(adminBulkSave).toHaveBeenCalledTimes(1)
  })

  it('does not invalidate kiosk query keys on error (D-08, T-04-10)', async () => {
    // Arrange: server rejects
    vi.mocked(adminBulkSave).mockRejectedValue(
      new BulkSaveError(500, undefined, undefined),
    )

    const queryClient = makeQueryClient()
    queryClient.setQueryData(['admin', 'cubes'], { cubes: [] })

    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    renderDiffSheet(queryClient)

    await waitFor(() =>
      expect(screen.queryByText(/checking movement/i)).not.toBeInTheDocument(),
    )

    const commitBtn = screen.getByRole('button', { name: /commit change set/i })
    await act(async () => {
      fireEvent.click(commitBtn)
    })

    // Wait for rollback state
    await waitFor(() =>
      expect(
        screen.getByText("Couldn't save that change — reverted."),
      ).toBeInTheDocument(),
    )

    // Assert: the kiosk top-level 'cubes' key was NEVER invalidated (D-08)
    const kioskInvalidations = invalidateSpy.mock.calls.filter((args) => {
      const opts = args[0] as { queryKey?: unknown[] } | undefined
      const qk = opts?.queryKey
      return Array.isArray(qk) && qk.length > 0 && qk[0] === 'cubes'
    })
    expect(kioskInvalidations).toHaveLength(0)
  })

  it('Dismiss button hides the toast', async () => {
    vi.mocked(adminBulkSave).mockRejectedValue(
      new BulkSaveError(400, 'boundary_order_error', 'Test error'),
    )

    const queryClient = makeQueryClient()
    renderDiffSheet(queryClient)

    await waitFor(() =>
      expect(screen.queryByText(/checking movement/i)).not.toBeInTheDocument(),
    )

    const commitBtn = screen.getByRole('button', { name: /commit change set/i })
    await act(async () => {
      fireEvent.click(commitBtn)
    })

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't save that change — reverted."),
      ).toBeInTheDocument(),
    )

    // Click Dismiss — triggers exit animation (150ms) then onDismiss callback
    const dismissBtn = screen.getByRole('button', { name: /dismiss/i })
    await act(async () => {
      fireEvent.click(dismissBtn)
    })

    // After 150ms animation, the toast should be gone from the DOM
    await waitFor(
      () =>
        expect(
          screen.queryByText("Couldn't save that change — reverted."),
        ).not.toBeInTheDocument(),
      { timeout: 500 },
    )
  })
})

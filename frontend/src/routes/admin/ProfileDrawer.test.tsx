/**
 * ProfileDrawer poll-until-terminal regression tests (02-08 / UAT gap test 8).
 *
 * Regression: old refetchInterval stopped polling on ANY non-'in_progress' value:
 *   refetchInterval: (query) => query.state.data?.last_sync_status === 'in_progress' ? 2000 : false
 * A transient tick returning last_sync_status: null would halt the poll before
 * the terminal 'ok' was ever fetched, leaving the drawer stuck on SYNCING.
 *
 * Fix: poll until TERMINAL status observed:
 *   refetchInterval: (query) => {
 *     const status = query.state.data?.last_sync_status
 *     return status === 'ok' || status === 'failed' ? false : 2000
 *   }
 *
 * Test 1: end-to-end via Sync Now — poll sequence in_progress → null → ok.
 *         Drawer shows sync-success + calls onSyncComplete (RED on old code).
 * Test 2: poll sequence ending in 'failed' stops polling + surfaces sheet-error.
 * Test 3: assert getAdminProfile called >= 3 times across in_progress → null → ok sequence.
 *
 * Timer strategy: vi.useFakeTimers() is used so refetchInterval timers are controlled.
 * waitFor uses real timers internally, so we restore real timers just before the
 * final DOM assertion in Tests 1 and 2 to avoid waitFor deadlock.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

// ── Module mock (must be top-level for vitest hoisting) ──────────────────────
vi.mock('../../api/adminClient', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../api/adminClient')>()
  return {
    ...real,
    getAdminProfile: vi.fn(),
    syncAdminProfile: vi.fn(),
    connectAdminProfilePat: vi.fn(),
  }
})

import {
  getAdminProfile,
  syncAdminProfile,
} from '../../api/adminClient'
import { ProfileDrawer } from './ProfileDrawer'
import type { AdminProfile } from '../../api/types'

// ── Fixtures ─────────────────────────────────────────────────────────────────

const PROFILE_ID = 'aaaaaaaa-0000-0000-0000-000000000001'

const CONNECTED_PROFILE: AdminProfile = {
  id: PROFILE_ID,
  display_name: 'Test Profile',
  last_sync_at: '2026-05-29T00:00:00Z',
  last_sync_status: 'ok',
  last_sync_error: null,
  last_sync_item_count: 3000,
  app_token_revoked: false,
  status: 'connected',
}

const IN_PROGRESS_TICK: AdminProfile = {
  ...CONNECTED_PROFILE,
  last_sync_status: 'in_progress',
  last_sync_item_count: 1500,
}

const TRANSIENT_NULL_TICK: AdminProfile = {
  ...CONNECTED_PROFILE,
  // null is not 'in_progress' but also not terminal — the transient window
  last_sync_status: null,
  last_sync_item_count: 3000,
}

const TERMINAL_OK_TICK: AdminProfile = {
  ...CONNECTED_PROFILE,
  last_sync_status: 'ok',
  last_sync_item_count: 3000,
  status: 'connected',
}

const TERMINAL_FAILED_TICK: AdminProfile = {
  ...CONNECTED_PROFILE,
  last_sync_status: 'failed',
  last_sync_error: 'server_error',
  last_sync_item_count: null,
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        gcTime: 60_000,
      },
    },
  })
}

/**
 * Render the ProfileDrawer with a CONNECTED target, click SYNC NOW, and
 * flush the initial promises so the component enters the 'syncing' state.
 */
async function renderAndStartSync(
  queryClient: QueryClient,
  onSyncComplete: ReturnType<typeof vi.fn>,
) {
  render(
    <QueryClientProvider client={queryClient}>
      <ProfileDrawer
        target={CONNECTED_PROFILE}
        onClose={vi.fn()}
        onSyncComplete={onSyncComplete}
      />
    </QueryClientProvider>,
  )

  const syncBtn = screen.getByRole('button', { name: /sync now/i })
  await act(async () => {
    syncBtn.click()
    // Flush the syncAdminProfile promise
    await Promise.resolve()
    await Promise.resolve()
  })
}

/**
 * Advance fake timers by ms and flush the resulting microtask queue.
 * This drives one TanStack Query refetchInterval tick.
 */
async function driveOneTick(ms = 2100) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

// ── Setup / Teardown ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: false })
  vi.mocked(getAdminProfile).mockReset()
  vi.mocked(syncAdminProfile).mockReset()
  vi.mocked(syncAdminProfile).mockResolvedValue(undefined as never)
})

afterEach(() => {
  cleanup()
  // Only run pending timers if fake timers are still active (some tests call
  // vi.useRealTimers() before the assertion to unblock waitFor).
  try {
    vi.runOnlyPendingTimers()
  } catch {
    // Timers already real — nothing to do.
  }
  vi.useRealTimers()
  vi.clearAllMocks()
})

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ProfileDrawer poll-until-terminal', () => {
  /**
   * Test 1 — reproduces UAT gap test 8 (transient-tick bug).
   *
   * Poll sequence after Sync Now:
   *   tick 1 → { last_sync_status: 'in_progress', last_sync_item_count: 1500 }
   *   tick 2 → { last_sync_status: null }  (transient — bug trigger on old code)
   *   tick 3 → { last_sync_status: 'ok', last_sync_item_count: 3000 }
   *
   * OLD behaviour: poll stops at tick 2 (null !== 'in_progress' → false).
   * Terminal 'ok' is never fetched; drawer stays stuck on SYNCING.
   *
   * NEW behaviour: poll continues through null; tick 3 delivers 'ok' and the
   * useEffect transitions the drawer to idle (success copy + onSyncComplete call).
   */
  it('Test 1: drawer auto-transitions to CONNECTED through a transient null tick', async () => {
    vi.mocked(getAdminProfile)
      .mockResolvedValueOnce(IN_PROGRESS_TICK)
      .mockResolvedValueOnce(TRANSIENT_NULL_TICK)
      .mockResolvedValueOnce(TERMINAL_OK_TICK)
      .mockResolvedValue(TERMINAL_OK_TICK) // fallback so query data is never undefined

    const onSyncComplete = vi.fn()
    const queryClient = makeQueryClient()
    await renderAndStartSync(queryClient, onSyncComplete)

    // tick 1: in_progress — initial fetch via enabled guard
    await driveOneTick(500)

    // tick 2: transient null — old code halts here
    await driveOneTick(2100)

    // tick 3: terminal ok — new code fetches this
    await driveOneTick(2100)

    // Restore real timers so waitFor's internal setInterval works
    vi.useRealTimers()

    await waitFor(() => {
      expect(screen.queryByText(/sync complete/i)).not.toBeNull()
    }, { timeout: 3000 })

    expect(onSyncComplete).toHaveBeenCalledOnce()
    expect(onSyncComplete).toHaveBeenCalledWith('Sync complete — 3,000 records')
  })

  /**
   * Test 2: poll sequence ending in 'failed' stops polling and surfaces error.
   *
   * Assert: inline sheet-error "Sync failed. Tap Sync Now to try again." appears.
   */
  it('Test 2: poll ending in failed surfaces the sheet-error', async () => {
    vi.mocked(getAdminProfile)
      .mockResolvedValueOnce(IN_PROGRESS_TICK)
      .mockResolvedValueOnce(TERMINAL_FAILED_TICK)
      .mockResolvedValue(TERMINAL_FAILED_TICK)

    const onSyncComplete = vi.fn()
    const queryClient = makeQueryClient()
    await renderAndStartSync(queryClient, onSyncComplete)

    // tick 1: in_progress
    await driveOneTick(500)

    // tick 2: terminal failed
    await driveOneTick(2100)

    // Restore real timers for waitFor
    vi.useRealTimers()

    await waitFor(() => {
      expect(
        screen.queryByText(/sync failed\. tap sync now to try again/i),
      ).not.toBeNull()
    }, { timeout: 3000 })

    expect(onSyncComplete).not.toHaveBeenCalled()
  })

  /**
   * Test 3: refetchInterval keeps polling through 'in_progress' AND null ticks.
   *
   * Key assertion: getAdminProfile is called >= 3 times across a sequence containing
   * a transient null tick. Old code halted at the null tick (2 calls).
   * New code continues polling (>= 3 calls).
   */
  it('Test 3: poll continues through in_progress AND null ticks (>= 3 fetches)', async () => {
    vi.mocked(getAdminProfile)
      .mockResolvedValueOnce(IN_PROGRESS_TICK)    // tick 1
      .mockResolvedValueOnce(TRANSIENT_NULL_TICK)  // tick 2 — bug trigger
      .mockResolvedValueOnce(IN_PROGRESS_TICK)    // tick 3 — should be called by new code
      .mockResolvedValueOnce(TERMINAL_OK_TICK)    // tick 4
      .mockResolvedValue(TERMINAL_OK_TICK)

    const queryClient = makeQueryClient()
    await renderAndStartSync(queryClient, vi.fn())

    // Drive ticks 1, 2, 3
    await driveOneTick(500)
    await driveOneTick(2100)
    await driveOneTick(2100)

    // Old code: 2 calls (halted on null). New code: >= 3 calls.
    expect(vi.mocked(getAdminProfile).mock.calls.length).toBeGreaterThanOrEqual(3)
  })
})
